"""
4주차 최소 인프라 검증용 pytest. 기존 src/gate1_analysis.py, apparent_temperature.py 의 함수만 호출하고
새 분석 로직은 만들지 않는다. (1)(2)는 host에서도 돌아가지만, (3)은 Postgres(gate1-dag가 적재한 테이블)가
필요해 docker-compose 환경(컨테이너 안) 에서만 통과한다.
"""
import os
import sys

import pandas as pd
import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "src")
sys.path.insert(0, SRC)

import gate1_analysis as g1  # noqa: E402
from apparent_temperature import apparent_temperature  # noqa: E402


def test_label11_18_reproduces_52h():
    """(1) 라벨 11~18 / 임계값 0.09 / 방식3(측정소별 계산 -> 중앙값)에서 연평균 52.0h(A 49.8, B 2.2) 재현."""
    assert g1.O3_TH == 0.09
    oz = g1.load_ozone_cached()
    oz = oz[oz["datetime"].dt.year <= 2025]
    asos = g1.load_asos_with_at()
    _, _, warn = g1.heatwave_days(asos)
    base = g1.merge_shift(oz, asos, warn, 0)
    n_seasons = base["datetime"].dt.year.nunique()
    assert n_seasons == 8 and len(base) == 1144531

    m = g1.flags(base.copy(), (11, 18))
    st = m.groupby("station_code")[["A", "B", "D"]].sum() / n_seasons
    assert abs(st["D"].median() - 52.0) < 0.06
    assert abs(st["A"].median() - 49.8) < 0.06
    assert abs(st["B"].median() - 2.2) < 0.06


@pytest.mark.parametrize("Ta,RH,expected", [(30.2, 80, 32.3), (39.6, 45, 38.4)])
def test_apparent_temperature_known_values(Ta, RH, expected):
    """(2) 체감온도 공식 기지값(정의문서 검증표) 2건, 오차 0.1℃ 이내."""
    assert abs(apparent_temperature(Ta, RH) - expected) < 0.1


def test_postgres_table_matches_csv():
    """(3) gate1-dag가 적재한 Postgres 테이블의 행수·합계가 DAG이 쓴 CSV와 일치 (자기비교) +
    40행 / D열 중앙값 52.0 이라는 독립 기대값과도 일치하는지 보강 확인.
    psycopg2를 직접 쓴다 — pandas 2.3.2의 to_sql/read_sql은 SQLAlchemy>=2.0이 필요한데
    Airflow 컨테이너의 SQLAlchemy는 1.4대라(dags/gate1_label11_18_dag.py 참고) pd.read_sql을 쓰지 않는다."""
    import psycopg2

    csv_path = os.path.join(SRC, "..", "output", "airflow_gate1_station_summary_label11_18.csv")
    if not os.path.exists(csv_path):
        pytest.skip("DAG이 아직 결과 CSV를 쓰지 않음 — gate1_label11_18 DAG을 먼저 성공시켜야 함")
    csv_df = pd.read_csv(csv_path, encoding="utf-8-sig")

    host = os.environ.get("PGHOST")
    if not host:
        pytest.skip("PGHOST 미설정 — docker-compose 환경 밖에서는 이 테스트를 건너뜀")
    conn = psycopg2.connect(
        host=host, port=os.environ.get("PGPORT", "5432"),
        dbname=os.environ["PGDATABASE"], user=os.environ["PGUSER"], password=os.environ["PGPASSWORD"],
    )
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*), sum(\"D\"), percentile_cont(0.5) WITHIN GROUP (ORDER BY \"D\") "
                        "FROM gate1.station_summary_label11_18")
            n, d_sum, d_median = cur.fetchone()
    finally:
        conn.close()

    # 자기비교: DAG이 쓴 CSV와 DB가 같은가
    assert n == len(csv_df)
    assert float(d_sum) == pytest.approx(csv_df["D"].sum(), abs=1e-6)
    # 보강: CSV와 무관한 독립 기대값(측정소 40개, 라벨11~18 D 연평균 중앙값 52.0)과도 같은가
    assert n == 40
    assert float(d_median) == pytest.approx(52.0, abs=0.06)


def test_sensitivity_csv_threshold_column_fixed():
    """(4a) 6주차_오존임계값_민감도.csv 의 임계값_ppm 열이 서로 다른 5개 값이고,
    0.09 행 D=52.0, 0.10 행 D=27.25 (run_week6.py 의 CSV 포맷 수정 후 — 값으로 직접 찾는다)."""
    path = os.path.join(SRC, "..", "output", "6주차_오존임계값_민감도.csv")
    sens = pd.read_csv(path, encoding="utf-8-sig")
    assert sorted(sens["임계값_ppm"].unique()) == pytest.approx([0.06, 0.08, 0.09, 0.10, 0.12])
    assert len(sens["임계값_ppm"].unique()) == 5
    row09 = sens[sens["임계값_ppm"] == 0.09].iloc[0]
    assert float(row09["합계_연평균시간"]) == pytest.approx(52.0, abs=0.01)
    row10 = sens[sens["임계값_ppm"] == 0.10].iloc[0]
    assert float(row10["합계_연평균시간"]) == pytest.approx(27.25, abs=0.01)


def test_hourly_csv_threshold_column_has_5_values():
    """(4a계속) 6주차_시각별_사각지대_분포.csv 의 임계값_ppm 열이 5개 값."""
    path = os.path.join(SRC, "..", "output", "6주차_시각별_사각지대_분포.csv")
    hm = pd.read_csv(path, encoding="utf-8-sig")
    assert len(hm["임계값_ppm"].unique()) == 5


def test_trend_csv_typeA_significant():
    """(참고, C6 관련) 6주차_연도추세검정.csv 의 Type A(2018~2025, 8점) p < 0.001."""
    path = os.path.join(SRC, "..", "output", "6주차_연도추세검정.csv")
    tr = pd.read_csv(path, encoding="utf-8-sig")
    row = tr[(tr["대상"] == "2018~2025 (8점)") & (tr["유형"] == "TypeA")].iloc[0]
    assert float(row["p값_정확검정(순열)"]) < 0.001


def test_week7_matched_pairs_count():
    """(4c) 7주차 결과 CSV의 매칭쌍수가 2018 포함=55, 2018 제외=53."""
    path = os.path.join(SRC, "..", "output", "7주차_온열질환_사각지대일_대조일_비교.csv")
    res = pd.read_csv(path, encoding="utf-8-sig").set_index("버전")
    assert int(res.loc["2018 포함", "매칭쌍수"]) == 55
    assert int(res.loc["2018 제외", "매칭쌍수"]) == 53


def test_week7_pairs_satisfy_matching_constraints():
    """(4d) 7번의 모든 매칭 쌍이 같은 연-월·같은 평일/주말 유형·체감온도 차 <=1℃ 인지 독립 재확인.
    run_week7.match_and_test() 를 다시 호출해서(이 함수 자체가 매 쌍마다 이 세 조건을 assert 한다) 확인한다
    — 조건을 어기는 쌍이 하나라도 있으면 이 호출에서 AssertionError 가 나서 테스트가 실패한다."""
    import importlib

    import run_week7  # noqa: E402  (import 시점에 run_week7.py 전체가 한 번 더 실행됨 - 의도된 동작)
    importlib.reload(run_week7)  # 매 테스트마다 신선하게 재검증

    row_incl = run_week7.match_and_test(list(range(2018, 2026)), "2018 포함")
    row_excl = run_week7.match_and_test(list(range(2019, 2026)), "2018 제외")
    assert row_incl["매칭쌍수"] == 55
    assert row_excl["매칭쌍수"] == 53
