"""
7주차: 온열질환 사각지대일 vs 대조일 비교 (윤서 사전 확정 정의, 결과를 본 뒤 기준을 바꾸지 않는다).

기존 기준(변경 금지, 재사용만): 근무시간=라벨 11~18 / 오존 임계값 0.09 / 방식 3(측정소별 계산→중앙값) /
특보일=체감온도 33℃ 이상 2일 이상 연속 구간 전체. 기준 결과 52.0h(A 49.8, B 2.2)가 재현되는지가 회귀 검증.
src/gate1_analysis.py 는 import만 하고 수정하지 않는다.

사전 확정한 정의 (질문-답변으로 확정, 결과를 본 뒤 바꾸지 않음):
  - 날짜 단위 도시 수준 집계: 측정소별 "그날 라벨11~18 중 Type A 시간 수"를 구한 뒤, 40개 측정소 값의 중앙값을 그날의 대표값으로 쓴다.
  - 사각지대일 = 비특보일 & 위 중앙값 >= 1시간
  - 대조일   = 비특보일 & 위 중앙값 == 0시간 (사각지대일 정의의 정확한 반대)
  - 매칭: 같은 연-월, 평일/주말 유형 동일(월~금=평일, 토~일=주말, 공휴일 미고려), 일 최고 체감온도 |ΔAT|<=1℃.
          1:1 최근접, 비복원. 그리디, 사각지대일을 날짜 오름차순으로 처리, 동률이면 날짜가 가까운 대조일 우선.
  - 결과 변수: 서울 일별 온열질환자 수 (발생시도='서울특별시', 감시기간 내 일자별 건수, 결측일=0건).
  - 감시기간: 매년 5/15~9/30, 단 2025년은 5/15~9/25. 기간 밖 날짜는 "관측 없음"이라 분석에서 아예 제외(0건 아님).
  - 검정: 쌍체 Wilcoxon 부호순위검정, 양측, α=0.05. scipy 기본(method='auto')을 그대로 쓴다.
  - 2018 포함/제외 두 버전을 모두 계산한다(2018=의료기관 소재지 기준, 2019+=발생지 기준이라 정의가 다름).

한계(결과와 무관하게 사전에 적어두는 것):
  - ±1℃, "1시간 이상", 1:1 비복원·그리디 순서(날짜 오름차순)는 모두 윤서가 정했거나 이번에 합의된 규칙이며,
    다른 규칙을 썼다면 결과가 달라질 수 있다.
  - 평일/주말은 달력상 월~금/토~일로만 나눴다. 공휴일(예: 광복절 평일)을 평일로 취급해 평일/주말 유형을 잘못
    맞출 수 있다.
  - 매칭 실패(같은 연-월·평일주말·±1℃ 대조일 후보가 없음)로 빠진 사각지대일이 2018 포함 32일, 2018 제외
    30일 있다. 이 날들은 비교에서 아예 빠졌고, 빠진 날이 무작위가 아니라면(예: 특정 월·요일에 쏠림) 결과가
    비뚤어질 수 있다.
  - 서울 일별 환자 수는 0~한 자릿수 수준이라 쌍체 검정의 검정력이 낮을 수 있다.
  - 온열질환은 "열"이 원인이라 오존의 영향을 직접 대변하지 않는다 — 이 비교는 "사각지대 시간대에 실제로
    온열질환이 더 보고되는가"를 보는 것이지 오존의 건강영향을 보는 것이 아니다.
"""
import os
import sys

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, os.path.dirname(__file__))
import gate1_analysis as g1

OUT = g1.OUT
HEAT_CSV = os.path.join(os.path.dirname(__file__), "..", "data", "HeatIllness", "온열질환 발생 신고 데이터(2011-2025).csv")
WORK = (11, 18)
AT_MATCH_TOL = 1.0

# ---------- (a) 기존 기준 재현 ----------
assert g1.O3_TH == 0.09, g1.O3_TH
oz = g1.load_ozone_cached()
oz = oz[oz["datetime"].dt.year <= 2025]
asos = g1.load_asos_with_at()
dmax, hot, warn = g1.heatwave_days(asos)
base = g1.merge_shift(oz, asos, warn, 0)
NS = base["datetime"].dt.year.nunique()
assert NS == 8 and len(base) == 1144531, (NS, len(base))

m = g1.flags(base.copy(), WORK)
st_year = m.groupby("station_code")[["A", "B", "D"]].sum() / NS
a_med, b_med, d_med = st_year["A"].median(), st_year["B"].median(), st_year["D"].median()
print(f"(a) 재현 확인 — 라벨11~18 측정소 중앙값: A={a_med:.2f} B={b_med:.2f} D={d_med:.2f} (기준 49.8/2.2/52.0)")
assert abs(d_med - 52.0) < 0.06 and abs(a_med - 49.8) < 0.06 and abs(b_med - 2.2) < 0.06, "기존 기준 52.0h 재현 실패"
print("(a) 통과\n")

# ---------- 날짜 단위 도시 수준 집계 ----------
w = m[m["hour"].between(*WORK)].copy()
w["date"] = w["datetime"].dt.normalize()
per_day_station_A = w.groupby(["date", "station_code"])["A"].sum().reset_index()
day_city_A = per_day_station_A.groupby("date")["A"].median()  # 날짜별, 측정소 중앙값 (방식3을 날짜 단위로)

day_warn = pd.Series({d: bool(warn.get(d, False)) for d in day_city_A.index})
nonwarn_days = day_warn[~day_warn].index

sacrifice_candidates = day_city_A[(day_city_A.index.isin(nonwarn_days)) & (day_city_A >= 1)]
control_candidates = day_city_A[(day_city_A.index.isin(nonwarn_days)) & (day_city_A == 0)]
print(f"전체(2018~2025, 5~9월) 사각지대일 후보 {len(sacrifice_candidates)}일, 대조일 후보 {len(control_candidates)}일\n")

# ---------- 감시기간 창 (관측 없음 구간 제외) ----------
def in_surveillance_window(dates: pd.DatetimeIndex) -> pd.Series:
    md = dates.strftime("%m-%d")
    year = dates.year
    lo_ok = md >= "05-15"
    hi_ok = np.where(year == 2025, md <= "09-25", md <= "09-30")
    return pd.Series(lo_ok & hi_ok, index=dates)

sac_idx = pd.DatetimeIndex(sacrifice_candidates.index)
ctl_idx = pd.DatetimeIndex(control_candidates.index)
sacrifice_days = sacrifice_candidates[in_surveillance_window(sac_idx).to_numpy()]
control_days = control_candidates[in_surveillance_window(ctl_idx).to_numpy()]
print(f"감시기간(5/15~9/30, 2025는 9/25까지) 내 사각지대일 {len(sacrifice_days)}일, 대조일 {len(control_days)}일\n")

# ---------- 온열질환 데이터 로드 ----------
raw = pd.read_csv(HEAT_CSV, encoding="utf-8")
raw["발생일자"] = pd.to_datetime(raw["발생일자"], errors="coerce")
seoul_raw = raw[raw["발생시도"] == "서울특별시"].copy()
assert seoul_raw["발생일자"].isna().sum() == 0, "서울 행에 발생일자 결측 존재"


def build_daily_counts(years):
    """해당 연도들의 감시기간 전체 날짜에 대해 서울 일별 건수를 만든다 (결측일=0건, 기간 밖=애초에 포함 안 함)."""
    frames = []
    for y in years:
        start, end = pd.Timestamp(f"{y}-05-15"), pd.Timestamp(f"{y}-09-25" if y == 2025 else f"{y}-09-30")
        frames.append(pd.date_range(start, end, freq="D"))
    full_idx = pd.DatetimeIndex(np.concatenate(frames))
    cnt = seoul_raw[seoul_raw["발생일자"].dt.year.isin(years)].groupby("발생일자").size()
    daily = cnt.reindex(full_idx, fill_value=0)
    daily.index.name = "date"
    return daily, full_idx


def weekday_type(dates: pd.DatetimeIndex) -> pd.Series:
    return pd.Series(np.where(dates.dayofweek < 5, "평일", "주말"), index=dates)


def match_and_test(years, label):
    sac = sacrifice_days[sacrifice_days.index.year.isin(years)].sort_index()
    ctl = control_days[control_days.index.year.isin(years)].sort_index()

    daily_counts, full_idx = build_daily_counts(years)
    # (c) 집계 건수 합 == 원본 서울 행 수 (해당 연도, 전부 감시기간 내에 있음을 사전 확인했음)
    raw_n = len(seoul_raw[seoul_raw["발생일자"].dt.year.isin(years)])
    assert int(daily_counts.sum()) == raw_n, (label, int(daily_counts.sum()), raw_n)
    print(f"[{label}] (c) 통과 — 일별 건수 합 {int(daily_counts.sum())} == 원본 서울 행수 {raw_n}")

    sac_at = dmax.reindex(sac.index)
    ctl_at = dmax.reindex(ctl.index)
    sac_wd = weekday_type(sac.index)
    ctl_wd = weekday_type(ctl.index)
    ctl_ym = ctl.index.strftime("%Y-%m")

    pool = pd.DataFrame({"date": ctl.index, "ym": ctl_ym, "wd": ctl_wd.values, "at": ctl_at.values})
    used = pd.Series(False, index=pool.index)

    pairs, unmatched = [], []
    for s_date in sac.index:  # 날짜 오름차순, 그리디 최근접
        ym, wd, at = s_date.strftime("%Y-%m"), sac_wd[s_date], sac_at[s_date]
        cand = pool[(~used) & (pool["ym"] == ym) & (pool["wd"] == wd) & ((pool["at"] - at).abs() <= AT_MATCH_TOL)]
        if cand.empty:
            unmatched.append(s_date)
            continue
        diff = (cand["at"] - at).abs()
        date_diff = (cand["date"] - s_date).abs()
        pick = cand.assign(_d=diff, _dd=date_diff).sort_values(["_d", "_dd", "date"]).index[0]
        used[pick] = True
        pairs.append((s_date, pool.loc[pick, "date"]))

    n_pairs = len(pairs)
    sac_vals = np.array([daily_counts[s] for s, c in pairs], dtype=float)
    ctl_vals = np.array([daily_counts[c] for s, c in pairs], dtype=float)

    # (b) 매칭 쌍 검증
    for s_date, c_date in pairs:
        assert s_date.strftime("%Y-%m") == c_date.strftime("%Y-%m"), (s_date, c_date)
        assert weekday_type(pd.DatetimeIndex([s_date])).iloc[0] == weekday_type(pd.DatetimeIndex([c_date])).iloc[0], (s_date, c_date)
        assert abs(dmax[s_date] - dmax[c_date]) <= AT_MATCH_TOL + 1e-9, (s_date, c_date)
    print(f"[{label}] (b) 통과 — 매칭 쌍 {n_pairs}개 전부 연-월/평일주말/±1℃ 조건 충족 (미매칭 사각지대일 {len(unmatched)}개)")

    diffs = sac_vals - ctl_vals
    note = ""
    if n_pairs == 0:
        stat_, p_ = np.nan, np.nan
        note = "매칭 쌍 없음 — 검정 불가"
    elif np.all(diffs == 0):
        stat_, p_ = np.nan, np.nan
        note = "모든 쌍의 차이가 0 — Wilcoxon 계산 불가(scipy ValueError)"
    else:
        try:
            res = stats.wilcoxon(sac_vals, ctl_vals, alternative="two-sided")
            stat_, p_ = float(res.statistic), float(res.pvalue)
        except ValueError as e:
            stat_, p_ = np.nan, np.nan
            note = f"Wilcoxon 계산 불가: {e}"

    row = {
        "버전": label,
        "사각지대일_후보수(감시기간내)": len(sac),
        "대조일_후보수(감시기간내)": len(ctl),
        "매칭쌍수": n_pairs,
        "미매칭_사각지대일수": len(unmatched),
        "사각지대일_일평균환자수(매칭쌍기준)": round(float(sac_vals.mean()), 3) if n_pairs else np.nan,
        "대조일_일평균환자수(매칭쌍기준)": round(float(ctl_vals.mean()), 3) if n_pairs else np.nan,
        "평균차이(사각지대일-대조일)": round(float(diffs.mean()), 3) if n_pairs else np.nan,
        "Wilcoxon_통계량": stat_,
        "p값": p_,
        "유의수준": 0.05,
        "비고": note,
    }
    print(f"[{label}] 일평균 환자수: 사각지대일 {row['사각지대일_일평균환자수(매칭쌍기준)']} vs 대조일 {row['대조일_일평균환자수(매칭쌍기준)']}"
          f" | Wilcoxon stat={stat_} p={p_}\n")
    return row


rows = [
    match_and_test(list(range(2018, 2026)), "2018 포함"),
    match_and_test(list(range(2019, 2026)), "2018 제외"),
]
result = pd.DataFrame(rows)
out_path = os.path.join(OUT, "7주차_온열질환_사각지대일_대조일_비교.csv")
result.to_csv(out_path, index=False, encoding="utf-8-sig")
print(f"저장: {out_path}")
print(result.to_string(index=False))

# ---------- 00_설정요약.csv: 이 파일명 행만 덮어쓰기 (다른 기존 행은 보존, 재실행해도 중복 안 생김) ----------
summ_path = os.path.join(OUT, "00_설정요약.csv")
summ = pd.read_csv(summ_path, encoding="utf-8-sig")
THIS_FILE = "7주차_온열질환_사각지대일_대조일_비교.csv"
summ = summ[summ["파일"] != THIS_FILE]  # 이전 실행에서 넣은 같은 파일명 행이 있으면 제거(업서트)
new_row = pd.DataFrame([{
    "파일": THIS_FILE,
    "어떤 설정으로 돌렸나": (
        "라벨 11~18 / 오존≥0.09 / 특보일=체감33℃ 2일연속 구간 전체 / 날짜 단위 도시집계=측정소별 그날 A시간의 중앙값 / "
        "사각지대일=비특보일&중앙값≥1h, 대조일=비특보일&중앙값=0h / 매칭=같은 연-월·평일주말(공휴일 미고려) 동일·"
        "|ΔAT|≤1℃·1:1 최근접 비복원(그리디, 사각지대일 날짜순) / 매칭 실패일은 비교에서 제외(포함 32일, 제외 30일) / "
        "결과변수=서울 일별 온열질환자수(발생시도=서울특별시, 감시기간 5/15~9/30·2025는 9/25까지, 기간밖은 관측없음으로 제외) / "
        "검정=쌍체Wilcoxon 양측 α=0.05 / 2018포함·제외 각각 계산(2018=의료기관소재지 기준, 2019+=발생지 기준이라 정의 다름) / "
        "기존기준 52.0h(A49.8,B2.2) 재현 확인됨"
    ),
}])
pd.concat([summ, new_row], ignore_index=True).to_csv(summ_path, index=False, encoding="utf-8-sig")
print(f"\n설정 요약 upsert 완료: {summ_path} (총 {len(summ) + 1}행, 이 파일 행 1개 포함)")
