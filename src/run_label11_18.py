"""
정의문서 v2 기준 재계산: 근무시간대 라벨 11~18 (실제 10:00~18:00), 2018~2025 (8시즌).
기존 src/gate1_analysis.py 의 함수를 그대로 재사용한다 (로직 변경 없음, WORK 인자만 바꿈).
1) 라벨 10~18 로 돌려 v2 문서의 기존 수치(34.2 / 166.6 / 52.1)를 먼저 재현 → 파이프라인 검증
2) 라벨 11~18 로 재계산 (±1h 정렬 민감도 포함)
3) 보조: 창 민감도 (9~21 / 13~18), 연도별, 측정소 유형별
"""
import os, sys, pickle
import pandas as pd
sys.path.insert(0, os.path.dirname(__file__))
import gate1_analysis as g1

OUT = g1.OUT
oz = g1.load_ozone_cached()
oz = oz[oz["datetime"].dt.year <= 2025]
asos = g1.load_asos_with_at()
dmax, hot, warn = g1.heatwave_days(asos)

base = g1.merge_shift(oz, asos, warn, 0)
n_seasons = base["datetime"].dt.year.nunique()
print("병합 행수:", len(base), "시즌 수:", n_seasons, sorted(base["datetime"].dt.year.unique()))
print("AT 5개 검증은 apparent_temperature.py 로 별도 확인")

def run(work, shift=0, warn_map=warn):
    m = base if (shift == 0 and warn_map is warn) else g1.merge_shift(oz, asos, warn_map, shift)
    r = g1.summarize(m, n_seasons, work=work)
    st = r["station"].copy()
    for k in "ABD":
        st[k + "_py"] = st[k] / n_seasons
    row = {"window": f"{work[0]}-{work[1]}", "shift_h": shift}
    for k in "ABD":
        row[f"m1_mean_{k}"] = r[f"mean_{k}"]
        row[f"m2_any_{k}"] = r[f"any_{k}"]
        row[f"m3_stmedian_{k}"] = float(st[k + "_py"].median())
    row["m3_urban_D"] = float(st.loc[st.station_type == "도시대기", "D_py"].median())
    row["m3_road_D"] = float(st.loc[st.station_type == "도로변대기", "D_py"].median())
    row["m3_urban_A"] = float(st.loc[st.station_type == "도시대기", "A_py"].median())
    row["m3_road_A"] = float(st.loc[st.station_type == "도로변대기", "A_py"].median())
    row["n_station"] = len(st)
    return row, r, st

rows = []
# 1) 재현: 라벨 10~18
r10, R10, S10 = run((10, 18))
rows.append(r10)
# 2) 본 계산: 라벨 11~18, 정렬 이동
r11, R11, S11 = run((11, 18))
rows.append(r11)
for s in (-1, 1):
    rr, _, _ = run((11, 18), shift=s); rows.append(rr)
# 3) 창 민감도
for w in [(9, 21), (13, 18), (10, 17)]:
    rr, _, _ = run(w); rows.append(rr)
# 특보일 대안정의(연속 2일째부터)
_, _, warn_alt = g1.heatwave_days(asos, alt=True)
ra, _, _ = run((11, 18), warn_map=warn_alt); ra["window"] += " (warn=2nd day on)"; rows.append(ra)

summ = pd.DataFrame(rows)
summ.to_csv(os.path.join(OUT, "gate1_label11_18_summary.csv"), index=False, encoding="utf-8-sig", float_format="%.2f")
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 50)
print(summ.round(1).to_string())

# 연도별 (라벨 11~18, 원본 정렬): 방식 1/2 은 city-level, 방식 3 은 측정소별 연도 값의 중앙값
m = g1.flags(base, (11, 18))
w = m[m["hour"].between(11, 18)].copy()
w["year"] = w["datetime"].dt.year
per_st_year = w.groupby(["station_code", "station_type", "year"])[["A", "B", "D"]].sum().reset_index()
yr3 = per_st_year.groupby("year")[["A", "B", "D"]].median().add_prefix("m3_stmedian_")
c = R11["city"].assign(year=lambda d: d["datetime"].dt.year).groupby("year")[
    ["mean_A", "mean_B", "mean_D", "any_A", "any_B", "any_D"]].sum()
c.columns = ["m1_" + x for x in c.columns[:3]] + ["m2_" + x for x in c.columns[3:]]
nst = w.groupby("year")["station_code"].nunique().rename("active_stations")
byyear = pd.concat([nst, c, yr3], axis=1).reset_index()
byyear.to_csv(os.path.join(OUT, "gate1_label11_18_by_year.csv"), index=False, encoding="utf-8-sig", float_format="%.2f")
print(byyear.round(1).to_string())
# 유형별 × 연도 (방식 3)
ty = per_st_year.groupby(["station_type", "year"])["D"].median().unstack(0)
print(ty)
S11.to_csv(os.path.join(OUT, "gate1_label11_18_station_level.csv"), index=False, encoding="utf-8-sig", float_format="%.3f")
with open(os.path.join(OUT, "label11_18_results.pkl"), "wb") as f:
    pickle.dump({"summ": summ, "byyear": byyear}, f)
