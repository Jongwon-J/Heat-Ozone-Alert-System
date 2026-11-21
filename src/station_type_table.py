"""
측정소 유형별 비교표 (5주차용): 2018~2025년 5~9월, 근무시간대 라벨 11~18만.
측정소별 평균 → 유형별 중앙값 (Gate 1 방식 3과 같은 구조).
임계값 초과 시간 = 측정소별 '연평균 시간'(8시즌 합 ÷ 8, Gate 1과 동일 분모).
"""
import os
import numpy as np, pandas as pd

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output")
oz = pd.read_parquet(os.path.join(OUT, "_cache_ozone_seoul_may_sep.parquet"))
oz = oz[(oz["datetime"].dt.year.between(2018, 2025)) & (oz["datetime"].dt.hour.between(11, 18))
        & (oz["datetime"].dt.month.between(5, 9))].copy()
SEASONS = 8
EXPECTED = 153 * 8 * SEASONS          # 5/1~9/30 = 153일 × 8라벨 × 8시즌 = 9,792
POL = {"O3": "ppm", "NO2": "ppm", "PM25": "ug/m3", "PM10": "ug/m3"}
TH = {  # (임계값, 구분)
    "O3": [(0.09, "main")],
    "NO2": [(0.10, "main")],
    "PM25": [(35, "main"), (75, "sens")],
    "PM10": [(100, "main"), (150, "sens")],
}
oz["type"] = oz["station_type"].map({"도시대기": "urban", "도로변대기": "roadside"})
print("행수", len(oz), oz.groupby("type").station_code.nunique().to_dict())

recs = []
for (code, name, typ), d in oz.groupby(["station_code", "station_name", "type"]):
    for p in POL:
        v = d[p].dropna()
        rec = {"station_code": code, "station_name": name, "type": typ, "pollutant": p,
               "unit": POL[p], "n_valid": len(v), "completeness_pct": 100 * len(v) / EXPECTED,
               "mean": v.mean()}
        for th, tag in TH[p]:
            rec[f"hrs_ge{th:g}_per_year"] = (v >= th).sum() / SEASONS
            rec[f"hrs_gt{th:g}_per_year"] = (v > th).sum() / SEASONS
            rec[f"pct_ge{th:g}"] = 100 * (v >= th).sum() / max(len(v), 1)
        recs.append(rec)
st = pd.DataFrame(recs)
st.to_csv(os.path.join(OUT, "station_type_per_station_label11_18.csv"), index=False,
          encoding="utf-8-sig", float_format="%.4f")

# 유형 × 오염물질 요약 (측정소별 값 → 유형별 중앙값)
rows = []
for (typ, p), d in st.groupby(["type", "pollutant"]):
    row = {"type": typ, "pollutant": p, "unit": POL[p], "n_stations": len(d),
           "mean_of_station_means_median": d["mean"].median(),
           "station_mean_mean": d["mean"].mean(), "station_mean_p25": d["mean"].quantile(.25),
           "station_mean_p75": d["mean"].quantile(.75), "station_mean_min": d["mean"].min(),
           "station_mean_max": d["mean"].max(),
           "completeness_min_pct": d["completeness_pct"].min(),
           "completeness_median_pct": d["completeness_pct"].median()}
    for th, tag in TH[p]:
        c = f"hrs_ge{th:g}_per_year"
        row[f"threshold_{tag}"] = th
        row[f"exceed_hrs_per_year_median_ge{th:g}"] = d[c].median()
        row[f"exceed_hrs_per_year_mean_ge{th:g}"] = d[c].mean()
        row[f"exceed_hrs_per_year_p25_ge{th:g}"] = d[c].quantile(.25)
        row[f"exceed_hrs_per_year_p75_ge{th:g}"] = d[c].quantile(.75)
        row[f"exceed_hrs_per_year_median_gt{th:g}"] = d[f"hrs_gt{th:g}_per_year"].median()
        row[f"exceed_pct_of_valid_hours_median_ge{th:g}"] = d[f"pct_ge{th:g}"].median()
    rows.append(row)
tab = pd.DataFrame(rows)
tab.to_csv(os.path.join(OUT, "station_type_comparison_label11_18_wide.csv"), index=False,
           encoding="utf-8-sig", float_format="%.4f")

# 보기 쉬운 long 형식: 오염물질×임계값 한 줄, 유형 두 개를 나란히
long = []
for p in POL:
    for th, tag in TH[p]:
        for typ in ("urban", "roadside"):
            d = st[(st.pollutant == p) & (st.type == typ)]
            long.append({"pollutant": p, "unit": POL[p], "threshold": th, "role": tag, "type": typ,
                         "n_stations": len(d),
                         "station_mean_median": d["mean"].median(),
                         "exceed_hrs_per_year_median": d[f"hrs_ge{th:g}_per_year"].median(),
                         "exceed_hrs_per_year_mean": d[f"hrs_ge{th:g}_per_year"].mean(),
                         "exceed_hrs_p25": d[f"hrs_ge{th:g}_per_year"].quantile(.25),
                         "exceed_hrs_p75": d[f"hrs_ge{th:g}_per_year"].quantile(.75),
                         "exceed_hrs_min": d[f"hrs_ge{th:g}_per_year"].min(),
                         "exceed_hrs_max": d[f"hrs_ge{th:g}_per_year"].max(),
                         "exceed_pct_of_valid_median": d[f"pct_ge{th:g}"].median(),
                         "strict_gt_exceed_hrs_median": d[f"hrs_gt{th:g}_per_year"].median(),
                         "completeness_min_pct": d["completeness_pct"].min()})
L = pd.DataFrame(long)
L.to_csv(os.path.join(OUT, "station_type_comparison_label11_18.csv"), index=False,
         encoding="utf-8-sig", float_format="%.4f")
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 50)
print(L.round(3).to_string())
print(st.groupby(["type","pollutant"])["completeness_pct"].describe().round(1).to_string())
