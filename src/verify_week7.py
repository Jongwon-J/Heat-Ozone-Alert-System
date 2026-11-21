"""
7주차 결과 독립 검증. run_week7.py 는 건드리지 않고, 그 결과 CSV를 기대값과 대조하고
(1) 93일->87일로 줄어든 이유를 날짜 집합으로 직접 확인
(2) 날짜 단위 집계를 groupby 와 pivot_table 두 가지 독립 방법으로 계산해 같은 날짜 집합이 나오는지 확인한다.
기대값과 다르면 멈추고 보고한다(코드를 고쳐서 맞추지 않는다).
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
import gate1_analysis as g1
from run_week7 import in_surveillance_window  # 기존 run_week7.py 함수 재사용

OUT = g1.OUT
WORK = (11, 18)

EXPECTED = {
    "2018 포함": dict(sac=87, ctl=889, pairs=55, unmatched=32, mean_sac=0.945, mean_ctl=0.836,
                      diff=0.109, stat=105.0, p=0.189632),
    "2018 제외": dict(sac=83, ctl=782, pairs=53, unmatched=30, mean_sac=0.925, mean_ctl=0.849,
                      diff=0.075, stat=102.0, p=0.262849),
}

mismatches = []


def check(label, actual, expected, tol):
    ok = abs(actual - expected) <= tol if isinstance(expected, (int, float)) else actual == expected
    mark = "OK" if ok else "**불일치**"
    print(f"  [{mark}] {label}: 실제={actual} 기대={expected}")
    if not ok:
        mismatches.append((label, actual, expected))


# ---------- (1) 결과 CSV를 기대값과 대조 ----------
res = pd.read_csv(os.path.join(OUT, "7주차_온열질환_사각지대일_대조일_비교.csv"), encoding="utf-8-sig")
res = res.set_index("버전")
for ver, exp in EXPECTED.items():
    print(f"\n[{ver}] CSV 대조")
    r = res.loc[ver]
    check("사각지대일 후보수", int(r["사각지대일_후보수(감시기간내)"]), exp["sac"], 0)
    check("대조일 후보수", int(r["대조일_후보수(감시기간내)"]), exp["ctl"], 0)
    check("매칭쌍수", int(r["매칭쌍수"]), exp["pairs"], 0)
    check("미매칭", int(r["미매칭_사각지대일수"]), exp["unmatched"], 0)
    check("사각지대일 평균", float(r["사각지대일_일평균환자수(매칭쌍기준)"]), exp["mean_sac"], 0.001)
    check("대조일 평균", float(r["대조일_일평균환자수(매칭쌍기준)"]), exp["mean_ctl"], 0.001)
    check("평균차이", float(r["평균차이(사각지대일-대조일)"]), exp["diff"], 0.001)
    check("Wilcoxon stat", float(r["Wilcoxon_통계량"]), exp["stat"], 0.01)
    check("p값", float(r["p값"]), exp["p"], 0.001)

if mismatches:
    print("\n*** 기대값과 다른 항목이 있어 아래부터는 진행하지 않고 멈춥니다 ***")
    for m in mismatches:
        print(" -", m)
    sys.exit(1)
print("\n(1) CSV 전 항목 기대값 일치 — 통과\n")

# ---------- (2) 93일 -> 87일: 날짜 집합으로 직접 확인 ----------
assert g1.O3_TH == 0.09
oz = g1.load_ozone_cached()
oz = oz[oz["datetime"].dt.year <= 2025]
asos = g1.load_asos_with_at()
dmax, hot, warn = g1.heatwave_days(asos)
base = g1.merge_shift(oz, asos, warn, 0)

m = g1.flags(base.copy(), WORK)
w = m[m["hour"].between(*WORK)].copy()
w["date"] = w["datetime"].dt.normalize()
per_day_station_A = w.groupby(["date", "station_code"])["A"].sum().reset_index()
day_city_A = per_day_station_A.groupby("date")["A"].median()
day_warn = pd.Series({d: bool(warn.get(d, False)) for d in day_city_A.index})
nonwarn_days = day_warn[~day_warn].index
sac_all = set(day_city_A[(day_city_A.index.isin(nonwarn_days)) & (day_city_A >= 1)].index)
print(f"(2) 전체(윈도 적용 전) 사각지대일 후보: {len(sac_all)}일 (기대 93)")
assert len(sac_all) == 93, len(sac_all)

in_win = in_surveillance_window(pd.DatetimeIndex(sorted(sac_all)))
sac_in = {d for d in sac_all if in_win[pd.Timestamp(d)]}
sac_out = sac_all - sac_in
print(f"    감시기간 안: {len(sac_in)}일 (기대 87) / 감시기간 밖(=관측없음이라 제외): {len(sac_out)}일")
assert len(sac_in) == 87 and len(sac_in) + len(sac_out) == 93

print("    감시기간 밖으로 빠진 날짜들:")
for d in sorted(sac_out):
    md = pd.Timestamp(d).strftime("%m-%d")
    reason = "9/25(2025 기준) 초과" if (pd.Timestamp(d).year == 2025 and md > "09-25") else \
             ("5/15 이전" if md < "05-15" else "9/30 초과")
    print(f"      {pd.Timestamp(d).date()}  ({reason})")
assert len(sac_out) == 93 - 87, "93->87 차이가 감시기간 필터만으로 설명되지 않음"
print(f"    => 93-87={93-87}일 전부 감시기간 밖(5/15~9/30, 2025는 9/25까지) 날짜였음을 날짜 목록으로 확인함\n")

# ---------- (3) groupby vs pivot_table 독립 교차검증 ----------
day_city_A_groupby = per_day_station_A.groupby("date")["A"].median()
pivot = per_day_station_A.pivot_table(index="date", columns="station_code", values="A", aggfunc="median")
day_city_A_pivot = pivot.median(axis=1, skipna=True)  # 측정소별 중앙값(행 방향), pivot은 열=측정소라 axis=1

# 두 방법이 완전히 같은 입력에서 같은 함수(median)를 쓰므로 값 자체가 동일해야 함 — 부동소수 오차만 허용
diff = (day_city_A_groupby.sort_index() - day_city_A_pivot.reindex(day_city_A_groupby.index).sort_index()).abs()
print(f"(3) groupby vs pivot_table 날짜별 중앙값 최대 차이: {diff.max():.10f}")
assert diff.max() < 1e-9, "groupby와 pivot_table 결과가 다름"

sac_groupby = set(day_city_A_groupby[(day_city_A_groupby.index.isin(nonwarn_days)) & (day_city_A_groupby >= 1)].index)
sac_pivot = set(day_city_A_pivot[(day_city_A_pivot.index.isin(nonwarn_days)) & (day_city_A_pivot >= 1)].index)
ctl_groupby = set(day_city_A_groupby[(day_city_A_groupby.index.isin(nonwarn_days)) & (day_city_A_groupby == 0)].index)
ctl_pivot = set(day_city_A_pivot[(day_city_A_pivot.index.isin(nonwarn_days)) & (day_city_A_pivot == 0)].index)

print(f"    사각지대일 집합: groupby {len(sac_groupby)}일 vs pivot {len(sac_pivot)}일, 차집합 {len(sac_groupby ^ sac_pivot)}개")
print(f"    대조일 집합:   groupby {len(ctl_groupby)}일 vs pivot {len(ctl_pivot)}일, 차집합 {len(ctl_groupby ^ ctl_pivot)}개")
assert sac_groupby == sac_pivot, f"사각지대일 날짜 집합이 다름: {sac_groupby ^ sac_pivot}"
assert ctl_groupby == ctl_pivot, f"대조일 날짜 집합이 다름: {ctl_groupby ^ ctl_pivot}"
print("(3) 두 방법의 사각지대일/대조일 날짜 집합이 완전히 동일 — 통과\n")

print("=== verify_week7.py 전체 통과 ===")
