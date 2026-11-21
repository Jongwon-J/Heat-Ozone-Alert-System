"""
4주차 최소 인프라용 DAG. 새 분석 로직을 만들지 않고 src/gate1_analysis.py 의 기존 함수만 호출한다.
태스크: load_data(데이터 로드 확인) -> compute_sacrifice_hours(사각지대 계산, 라벨 11~18) -> load_to_postgres(DB 적재, 덮어쓰기)

컨테이너 안 경로(모두 docker-compose.yml 의 마운트와 짝을 맞춤):
  /opt/project/src     <- ./src        (ro)  gate1_analysis.py 등 기존 코드, 수정하지 않음
  /opt/project/data    <- ./data       (ro)  ASOS/Ozone 원본
  /opt/project/output  <- ./output     (rw)  캐시 읽기 + 결과 CSV 쓰기
경로 로직은 src/merge_and_scatter.py 의 ROOT=dirname(dirname(__file__)) 를 그대로 쓰므로,
/opt/project 아래에 src/data/output 을 이 구조로 두면 코드 수정 없이 그대로 동작한다.
"""
import os
from datetime import datetime

import pandas as pd
from airflow import DAG
from airflow.operators.python import PythonOperator

PROJECT_SRC = "/opt/project/src"
OUT_DIR = "/opt/project/output"
RESULT_CSV = os.path.join(OUT_DIR, "airflow_gate1_station_summary_label11_18.csv")
WORK = (11, 18)


def load_data(**_):
    import sys
    sys.path.insert(0, PROJECT_SRC)
    import gate1_analysis as g1

    oz = g1.load_ozone_cached()
    asos = g1.load_asos_with_at()
    print(f"오존 캐시 로드: {len(oz):,}행 / ASOS+체감온도 로드: {len(asos):,}행")
    assert len(oz) > 0 and len(asos) > 0, "데이터 로드 결과가 비어 있음"


def compute_sacrifice_hours(**_):
    import sys
    sys.path.insert(0, PROJECT_SRC)
    import gate1_analysis as g1

    assert g1.O3_TH == 0.09, g1.O3_TH
    oz = g1.load_ozone_cached()
    oz = oz[oz["datetime"].dt.year <= 2025]
    asos = g1.load_asos_with_at()
    dmax, hot, warn = g1.heatwave_days(asos)
    base = g1.merge_shift(oz, asos, warn, 0)
    n_seasons = base["datetime"].dt.year.nunique()
    assert n_seasons == 8 and len(base) == 1144531, (n_seasons, len(base))  # 기존 회귀 검증, 그대로 재사용

    m = g1.flags(base.copy(), WORK)
    st = m.groupby(["station_code", "station_name", "station_type"])[["A", "B", "D"]].sum().reset_index()
    for k in "ABD":
        st[k] = st[k] / n_seasons  # 연평균 시간
    d_med = st["D"].median()
    print(f"측정소 {len(st)}개, 연평균 D 중앙값={d_med:.2f} (기준 52.0)")
    assert abs(d_med - 52.0) < 0.06, d_med

    os.makedirs(OUT_DIR, exist_ok=True)
    st.to_csv(RESULT_CSV, index=False, encoding="utf-8-sig")
    print(f"저장: {RESULT_CSV} ({len(st)}행)")
    return RESULT_CSV


def load_to_postgres(**ctx):
    # pandas 2.3.2 의 to_sql/read_sql 은 SQLAlchemy>=2.0 을 요구하는데, Airflow 2.9.3 은 SQLAlchemy 1.4대를
    # 쓴다(버전 충돌). pandas 버전은 host와 맞춰야 하므로 낮추지 않고, DB 입출력만 psycopg2로 직접 처리한다.
    import psycopg2
    import psycopg2.extras

    csv_path = ctx["ti"].xcom_pull(task_ids="compute_sacrifice_hours") or RESULT_CSV
    df = pd.read_csv(csv_path, encoding="utf-8-sig")

    conn = psycopg2.connect(
        host=os.environ.get("PGHOST", "postgres"),
        port=os.environ.get("PGPORT", "5432"),
        dbname=os.environ.get("PGDATABASE", "airflow"),
        user=os.environ.get("PGUSER", "airflow"),
        password=os.environ.get("PGPASSWORD", "airflow"),
    )
    try:
        with conn, conn.cursor() as cur:
            cur.execute("CREATE SCHEMA IF NOT EXISTS gate1")
            # DROP 후 CREATE: 재실행해도 행이 늘지 않고(덮어쓰기) 항상 df와 같은 행수가 된다.
            cur.execute("DROP TABLE IF EXISTS gate1.station_summary_label11_18")
            cur.execute(
                """
                CREATE TABLE gate1.station_summary_label11_18 (
                    station_code TEXT, station_name TEXT, station_type TEXT,
                    "A" DOUBLE PRECISION, "B" DOUBLE PRECISION, "D" DOUBLE PRECISION
                )
                """
            )
            rows = list(df[["station_code", "station_name", "station_type", "A", "B", "D"]].itertuples(index=False, name=None))
            psycopg2.extras.execute_values(
                cur,
                "INSERT INTO gate1.station_summary_label11_18 VALUES %s",
                rows,
            )
            cur.execute("SELECT count(*) FROM gate1.station_summary_label11_18")
            n = cur.fetchone()[0]
    finally:
        conn.close()

    print(f"gate1.station_summary_label11_18 적재 완료: {n}행")
    assert n == len(df)


with DAG(
    dag_id="gate1_label11_18",
    description="라벨 11~18 사각지대 계산 -> PostgreSQL 적재 (기존 gate1_analysis 함수만 호출)",
    schedule=None,
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["gate1", "week4-infra"],
) as dag:
    t1 = PythonOperator(task_id="load_data", python_callable=load_data)
    t2 = PythonOperator(task_id="compute_sacrifice_hours", python_callable=compute_sacrifice_hours)
    t3 = PythonOperator(task_id="load_to_postgres", python_callable=load_to_postgres)
    t1 >> t2 >> t3
