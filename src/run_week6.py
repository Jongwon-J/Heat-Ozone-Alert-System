"""
6주차 견고성 계산 (윤서 사전 확정 방법 그대로). 결과를 보고 기준을 바꾸지 않는다.
공통 설정: 2018~2025년 5~9월(8시즌), 서울 40개 측정소, 에어코리아 라벨 시각, 원본 정렬(0h),
           특보일=일 최고 체감온도 33℃ 이상 2일 연속 구간 전체, 집계=방식 3(측정소별 계산→측정소 중앙값),
           연평균 시간 = 8시즌 합계 ÷ 8, 오존 판정은 '임계값 이상(>=)'
"""
import os, sys, itertools
import numpy as np, pandas as pd
from scipy import stats
sys.path.insert(0, os.path.dirname(__file__))
import gate1_analysis as g1

OUT = g1.OUT
oz = g1.load_ozone_cached(); oz = oz[oz["datetime"].dt.year <= 2025]
asos = g1.load_asos_with_at()
dmax, hot, warn = g1.heatwave_days(asos)
base = g1.merge_shift(oz, asos, warn, 0)
NS = base["datetime"].dt.year.nunique(); assert NS == 8 and len(base) == 1144531, (NS, len(base))
THS = [0.06, 0.08, 0.09, 0.10, 0.12]

# ---------- 4. 임계값 5종 민감도 (라벨 11~18) ----------
rows = []
for th in THS:
    g1.O3_TH = th
    m = g1.flags(base.copy(), (11, 18))
    st = m.groupby("station_code")[["A", "B", "D"]].sum() / NS
    a, b, d = st["A"].median(), st["B"].median(), st["D"].median()
    rows.append({"임계값_ppm": th, "TypeA_연평균시간": a, "TypeB_연평균시간": b, "합계_연평균시간": d,
                 "Gate1기준_30h이상": "예" if d >= 30 else "아니오", "측정소수": len(st)})
sens = pd.DataFrame(rows)
# float_format="%.1f"을 전체 컬럼에 쓰면 임계값_ppm(0.06~0.12)까지 반올림되어 전부 "0.1"로 저장되고,
# 시간 값도 .x5 경계에서(예: 27.25 -> 27.2) 잘못 반올림된다. 임계값은 정확한 2자리 문자열로,
# 시간 값은 소수 셋째 자리(%.3f)로 컬럼별로 따로 포맷해서 저장한다(서식만 수정, 계산 로직은 그대로).
sens_out = sens.copy()
sens_out["임계값_ppm"] = sens_out["임계값_ppm"].map(lambda x: f"{x:.2f}")
for c in ["TypeA_연평균시간", "TypeB_연평균시간", "합계_연평균시간"]:
    sens_out[c] = sens_out[c].map(lambda x: f"{x:.3f}")
sens_out.to_csv(os.path.join(OUT, "6주차_오존임계값_민감도.csv"), index=False, encoding="utf-8-sig")
print(sens.round(2).to_string())
r09 = sens[sens["임계값_ppm"] == 0.09].iloc[0]
assert abs(r09["합계_연평균시간"] - 52.0) < 0.06 and abs(r09["TypeA_연평균시간"] - 49.8) < 0.06, "0.09 재현 실패"

# ---------- 5·8. 시각별(라벨 9~21) 분포 ----------
hrows = []
for th in THS:
    g1.O3_TH = th
    m = g1.flags(base.copy(), (9, 21))
    m = m[m["hour"].between(9, 21)].copy()
    m["O"] = m["O3"] >= th                       # 특보·체감온도와 무관하게 오존만 임계값 이상
    g = m.groupby(["station_code", "hour"])[["O", "A", "B", "D"]].sum() / NS
    med = g.groupby("hour").median()
    for h, r in med.iterrows():
        hrows.append({"임계값_ppm": th, "라벨시각": int(h), "실제구간": f"{int(h)-1:02d}:00~{int(h):02d}:00",
                      "오존초과_연평균시간(특보무관)": r["O"], "TypeA_연평균시간": r["A"],
                      "TypeB_연평균시간": r["B"], "합계_연평균시간": r["D"]})
hm = pd.DataFrame(hrows)
hm.to_csv(os.path.join(OUT, "6주차_시각별_사각지대_분포.csv"), index=False, encoding="utf-8-sig", float_format="%.2f")
h09 = hm[hm["임계값_ppm"] == 0.09]
print(h09.round(2).to_string())
print("0.09 시각별 합계의 합(참고, 중앙값 합이라 52.0과 일치 불필요):", round(h09[h09.라벨시각.between(11,18)]["합계_연평균시간"].sum(), 1))

# ---------- 6. 연도 추세 검정 ----------
g1.O3_TH = 0.09
m = g1.flags(base.copy(), (11, 18)); w = m[m["hour"].between(11, 18)].copy(); w["year"] = w["datetime"].dt.year
psy = w.groupby(["station_code", "year"])[["A", "B"]].sum().reset_index()
yr = psy.groupby("year")[["A", "B"]].median().rename(columns={"A": "TypeA", "B": "TypeB"})
yr["활성측정소수"] = w.groupby("year")["station_code"].nunique()
yr.reset_index().to_csv(os.path.join(OUT, "6주차_연도별값(추세검정 입력).csv"), index=False, encoding="utf-8-sig", float_format="%.1f")
print(yr)

def mk_s(y):
    n = len(y); return sum(np.sign(y[j] - y[i]) for i in range(n) for j in range(i + 1, n))
def perm_p(y):
    s0 = abs(mk_s(y)); n = len(y); cnt = tot = 0
    for p in itertools.permutations(range(n)):
        tot += 1; cnt += abs(mk_s([y[i] for i in p])) >= s0
    return cnt / tot
res = []
for label, years in [("2018~2025 (8점)", list(range(2018, 2026))), ("2020·2021 제외 (6점)", [2018, 2019, 2022, 2023, 2024, 2025])]:
    for typ in ("TypeA", "TypeB"):
        y = yr.loc[years, typ].to_numpy(float); x = np.array(years, float)
        tau, p_sc = stats.kendalltau(x, y, method="exact") if len(set(y)) == len(y) else (stats.kendalltau(x, y)[0], float("nan"))
        ties = len(set(y)) != len(y)
        sl, ic, lo, hi = stats.theilslopes(y, x, 0.95)
        pp = perm_p(list(y))
        res.append({"대상": label, "유형": typ, "점수": len(y), "동점(값 중복)": "있음" if ties else "없음",
                    "MK_S": mk_s(list(y)), "켄달tau": tau, "p값_정확검정(순열)": pp,
                    "p값_scipy_kendalltau_exact": p_sc, "TheilSen기울기_시간/년": sl,
                    "기울기_95%CI_하한": lo, "기울기_95%CI_상한": hi,
                    "판정(양측 0.05)": ("유의(증가)" if pp < .05 and sl > 0 else "유의(감소)" if pp < .05 else "유의하지 않음")})
tr = pd.DataFrame(res)
tr.to_csv(os.path.join(OUT, "6주차_연도추세검정.csv"), index=False, encoding="utf-8-sig", float_format="%.4f")
print(tr.round(4).to_string())
