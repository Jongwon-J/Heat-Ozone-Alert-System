"""
Week 2 후반: 타임스탬프 정렬 검증(B) · 집계방식 비교(C) · 정식 Type A/B + Gate 1 판정(D)
정의문서_v1.md 5절(폭염특보), 6절(사각지대), 7절(Gate 1) 기준.

재사용: merge_and_scatter.load_asos / load_ozone, apparent_temperature.apparent_temperature
실행: 프로젝트 루트에서  python3 src/gate1_analysis.py
결과: output/gate1_results.pkl (표 데이터), output/gate1_station_level.csv
"""
import os
import pickle

import pandas as pd

import merge_and_scatter as ms
from apparent_temperature import apparent_temperature

OUT = ms.OUT_DIR
CACHE = os.path.join(OUT, "_cache_ozone_seoul_may_sep.parquet")

O3_TH = ms.OZONE_THRESHOLD   # 0.09 (정의문서 4절)
AT_TH = 33                   # 정의문서 5절
WORK = (10, 18)              # 정의문서 1절 [잠정]. 이전 단계와 동일하게 10~18시 라벨 포함(양끝 포함)


def load_ozone_cached():
    if os.path.exists(CACHE):
        return pd.read_parquet(CACHE)
    air = ms.load_ozone()
    air = air[air["O3"].notna() & (air["O3"] >= 0)]
    air.to_parquet(CACHE)
    return air


def load_asos_with_at():
    a = ms.load_asos()
    ok = a["Ta"].notna() & a["RH"].notna()
    a["AT"] = float("nan")
    a.loc[ok, "AT"] = [apparent_temperature(t, h) for t, h in zip(a.loc[ok, "Ta"], a.loc[ok, "RH"])]
    a = a[a["AT"].notna()].copy()
    a["date"] = a["datetime"].dt.normalize()
    return a[["datetime", "date", "AT"]]


def heatwave_days(asos, alt=False):
    """정의문서 5절 재현: 일 최고 체감온도 33℃ 이상이 2일 연속이면 그 연속 구간의 모든 날이 '폭염특보일'.
    alt=True: 연속 2일째부터만 특보일 (발령 시점 관점의 민감도용)."""
    dmax = asos.groupby("date")["AT"].max()
    idx = pd.date_range(dmax.index.min(), dmax.index.max(), freq="D")
    hot = (dmax.reindex(idx) >= AT_TH).fillna(False)  # 시즌 밖 날짜(10~4월)는 자료 없음 → 비폭염 취급
    prev, nxt = hot.shift(1, fill_value=False), hot.shift(-1, fill_value=False)
    warn = (hot & prev) if alt else (hot & (prev | nxt))
    return dmax, hot, warn


def merge_shift(oz, asos, warn, shift_h):
    """에어코리아 datetime을 shift_h시간 이동한 뒤 ASOS와 병합, 근무시간대만 남긴다."""
    o = oz[["datetime", "station_code", "station_name", "station_type", "O3"]].copy()
    o["datetime"] = o["datetime"] + pd.Timedelta(hours=shift_h)
    m = o.merge(asos, on="datetime", how="inner")
    m["warn"] = m["date"].map(warn).fillna(False).astype(bool)
    m["hour"] = m["datetime"].dt.hour
    return m


def flags(m, work=WORK):
    w = m["hour"].between(*work)
    hi = m["O3"] >= O3_TH
    cool = m["AT"] < AT_TH
    m = m.assign(
        C=w & hi & cool,                        # 단순 조건 (특보일 무관)
        A=w & hi & ~m["warn"],                  # Type A: 비특보일 + 근무시간 + 오존 초과
        B=w & hi & m["warn"] & cool,            # Type B: 특보일 + 근무시간 + AT<33 + 오존 초과
    )
    m["D"] = m["A"] | m["B"]
    return m


def city_level(m, work=WORK):
    """시각별 측정소 평균 O3 + 조건 판정(방식 1), 어느 측정소든 충족(방식 2)."""
    w = m["hour"].between(*work)
    g = m[w].groupby("datetime").agg(O3=("O3", "mean"), n=("O3", "size"), AT=("AT", "first"),
                                    warn=("warn", "first"), any_C=("C", "any"), any_A=("A", "any"),
                                    any_B=("B", "any"), any_D=("D", "any")).reset_index()
    hi = g["O3"] >= O3_TH
    cool = g["AT"] < AT_TH
    g["mean_C"] = hi & cool
    g["mean_A"] = hi & ~g["warn"]
    g["mean_B"] = hi & g["warn"] & cool
    g["mean_D"] = g["mean_A"] | g["mean_B"]
    return g


def gate_class(x):
    return "진행(≥30h)" if x >= 30 else ("임계값 조정 후 재판정(10~30h)" if x >= 10 else "PART 1 축소(<10h)")


def summarize(m, n_seasons, work=WORK):
    """한 번의 (정렬·정의) 조합에 대해 방식 1/2/3 × C/A/B/D 연평균 시간."""
    m = flags(m, work)
    g = city_level(m, work)
    st = m.groupby(["station_code", "station_name", "station_type"])[["C", "A", "B", "D"]].sum().reset_index()
    out = {"city": g, "station": st, "n_seasons": n_seasons}
    for k in "CABD":
        out[f"mean_{k}"] = g[f"mean_{k}"].sum() / n_seasons
        out[f"any_{k}"] = g[f"any_{k}"].sum() / n_seasons
        out[f"st_{k}"] = st[k] / n_seasons  # 측정소별 연평균 (Series)
    return out


def main():
    oz = load_ozone_cached()
    asos = load_asos_with_at()
    dmax, hot, warn = heatwave_days(asos)
    _, _, warn_alt = heatwave_days(asos, alt=True)

    res = {}

    # ---- 재현 확인: 이전 단계 병합 CSV와 행 수 대조 ----
    prev = pd.read_csv(os.path.join(OUT, "merged_ozone_weather.csv"), encoding="utf-8-sig",
                       usecols=["datetime", "station_code", "O3", "AT"], parse_dates=["datetime"])
    base = merge_shift(oz, asos, warn, 0)
    res["repro"] = {"prev_rows": len(prev), "now_rows": len(base),
                    "AT_maxdiff": float((base.set_index(["datetime", "station_code"])["AT"]
                                         - prev.set_index(["datetime", "station_code"])["AT"]).abs().max())}
    n_seasons = base["datetime"].dt.year.nunique()
    res["n_seasons"] = n_seasons
    res["years"] = sorted(base["datetime"].dt.year.unique().tolist())

    # ---- A-3: 0.09 이상 행 수 재집계 ----
    hi = base[base["O3"] >= O3_TH]
    cnt = {
        "전체 station-hour 행 (전 시간대)": len(hi),
        "  0~9시": int((hi["hour"] <= 9).sum()),
        "  10~18시 (근무시간대)": int(hi["hour"].between(10, 18).sum()),
        "  19~23시": int((hi["hour"] >= 19).sum()),
        "10~18시 & AT<33 (station-hour 행)": int((hi["hour"].between(10, 18) & (hi["AT"] < AT_TH)).sum()),
        "전체 station-hour 행, 초과(>0.09) 기준": int((base["O3"] > O3_TH).sum()),
    }
    w = base[base["hour"].between(10, 18)]
    city_all = base.groupby("datetime").agg(O3=("O3", "mean"), AT=("AT", "first"), hour=("hour", "first")).reset_index()
    cw = city_all[city_all["hour"].between(10, 18)]
    cnt["10~18시 고유 시각 수 (어느 측정소든 ≥0.09)"] = int(w[w["O3"] >= O3_TH]["datetime"].nunique())
    cnt["10~18시 고유 시각 수 (측정소 평균 ≥0.09)"] = int((cw["O3"] >= O3_TH).sum())
    cnt["10~18시 & AT<33: 어느 측정소든"] = int(w[(w["O3"] >= O3_TH) & (w["AT"] < AT_TH)]["datetime"].nunique())
    cnt["10~18시 & AT<33: 측정소 평균"] = int(((cw["O3"] >= O3_TH) & (cw["AT"] < AT_TH)).sum())
    res["A3"] = cnt

    # ---- 폭염특보일 재현 결과 ----
    d = pd.DataFrame({"hot": hot, "warn": warn, "warn_alt": warn_alt})
    d = d[(d.index.year <= max(res["years"]))]
    d["year"] = d.index.year
    run_id = (d["warn"] != d["warn"].shift()).cumsum()
    n_runs = d[d["warn"]].groupby(run_id[d["warn"]]).size()
    res["warn_summary"] = d.groupby("year").agg(hot_days=("hot", "sum"), warn_days=("warn", "sum")).reset_index()
    res["warn_runs"] = len(n_runs)
    # 시즌 경계(5/1, 9/30)에 33℃ 이상인 날이 있으면 시즌 밖 이웃 날 자료 부재로 연속 판정이 왜곡될 수 있음
    res["edge_hot"] = [str(t.date()) for y in res["years"] for t in (pd.Timestamp(f"{y}-05-01"), pd.Timestamp(f"{y}-09-30"))
                       if t in hot.index and hot[t]]

    # ---- B: 정렬 이동 비교 (C 조건 = 근무시간 & O3≥0.09 & AT<33, 그리고 최종 D) ----
    shifts = {"원본(0h)": 0, "-1h": -1, "+1h": +1}
    res["B"] = {}
    for name, s in shifts.items():
        r = summarize(merge_shift(oz, asos, warn, s), n_seasons)
        res["B"][name] = {k: v for k, v in r.items() if k not in ("city", "station")}
        res["B"][name]["st_C_med"] = float(r["st_C"].median())
        res["B"][name]["st_D_med"] = float(r["st_D"].median())
        res["B"][name]["st_C_sum"] = float(r["st_C"].sum())
    # ---- C/D: 원본 정렬 ----
    r0 = summarize(base, n_seasons)
    res["main"] = r0
    res["station_level"] = r0["station"].assign(**{f"{k}_per_year": r0["station"][k] / n_seasons for k in "CABD"})
    res["station_level"].to_csv(os.path.join(OUT, "gate1_station_level.csv"), index=False, encoding="utf-8-sig")
    g = r0["city"]
    res["city_n"] = {"min": int(g["n"].min()), "median": float(g["n"].median()), "max": int(g["n"].max()),
                     "hours": len(g)}

    # 연도별 (방식 1/2 × D)
    yr = g.assign(year=g["datetime"].dt.year).groupby("year").agg(
        mean_C=("mean_C", "sum"), any_C=("any_C", "sum"), mean_A=("mean_A", "sum"), mean_B=("mean_B", "sum"),
        mean_D=("mean_D", "sum"), any_A=("any_A", "sum"), any_B=("any_B", "sum"), any_D=("any_D", "sum")).reset_index()
    res["by_year"] = yr

    # ---- 민감도: 근무시간 10~17시 / 특보일 대안 정의 ----
    sens = {}
    r = summarize(merge_shift(oz, asos, warn, 0), n_seasons, work=(10, 17))
    sens["근무시간 10~17시(18시 라벨 제외)"] = {k: r[f"{k}_D"] for k in ("mean", "any")} | {"st_med": float(r["st_D"].median())}
    r = summarize(merge_shift(oz, asos, warn_alt, 0), n_seasons)
    sens["특보일=연속 2일째부터"] = {k: r[f"{k}_D"] for k in ("mean", "any")} | {"st_med": float(r["st_D"].median())}
    res["sens"] = sens

    with open(os.path.join(OUT, "gate1_results.pkl"), "wb") as f:
        pickle.dump(res, f)
    print("저장 완료")


if __name__ == "__main__":
    main()
