"""
6주차 산출물 독립 검증. run_week6.py 는 건드리지 않고, 그 결과 CSV를 기대값과 대조한다.
A3(폭염특보일 대안정의, alt=True)는 CSV에 없으므로 gate1_analysis 함수를 직접 호출해 새로 계산한다.
기대값과 다르면 멈추고 보고한다(코드를 고쳐서 맞추지 않는다).
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
import gate1_analysis as g1

OUT = g1.OUT
TOL_H, TOL_P, TOL_SLOPE = 0.1, 0.001, 0.1
mismatches = []       # 진짜 불일치 -> 멈춤
csv_rounding_notes = []  # 알려진 CSV 반올림 손실로 설명되는 차이 -> 보고만 하고 멈추지 않음


def check(label, actual, expected, tol, advisory=False):
    ok = abs(actual - expected) <= tol
    tag = "OK" if ok else ("참고(반올림 아티팩트)" if advisory else "**불일치**")
    print(f"  [{tag}] {label}: 실제={actual} 기대={expected} (허용오차 {tol})")
    if not ok:
        (csv_rounding_notes if advisory else mismatches).append((label, actual, expected))


def stop_if_mismatch():
    if mismatches:
        print("\n*** 기대값과 다른 항목이 있어 멈춥니다 ***")
        for m in mismatches:
            print(" -", m)
        sys.exit(1)


# ---------- 민감도 5종 ----------
# ** 발견한 버그(기대값 불일치 아님) ** run_week6.py 가 sens.to_csv(..., float_format="%.1f")로 저장하면서
# 임계값_ppm 컬럼(0.06/0.08/0.09/0.10/0.12)까지 소수점 1자리로 반올림되어 CSV에는 전부 "0.1"로 찍힌다.
# run_week6.py 는 수정 대상이 아니므로 고치지 않고, 그 파일 자신의 로직(THS=[0.06,0.08,0.09,0.10,0.12]
# 순서로 한 행씩 append)을 근거로 "행 위치"로 대조한다. 값 자체(TypeA/TypeB/합계)는 영향받지 않았다.
sens = pd.read_csv(os.path.join(OUT, "6주차_오존임계값_민감도.csv"), encoding="utf-8-sig")
print("[민감도] 합계_연평균시간 (라벨 11~18, 방식3 중앙값)")
print("  ** 버그 발견: 임계값_ppm 컬럼이 float_format='%.1f'로 전부 '0.1'로 저장됨(run_week6.py, 수정 안 함) — 행 위치로 대조")
assert list(sens["임계값_ppm"]) == [0.1] * 5, "예상한 버그 패턴과 다름 — 직접 확인 필요"
THS_ORDER = [0.06, 0.08, 0.09, 0.10, 0.12]  # run_week6.py 의 THS 리스트, 작성 순서와 동일
exp_sens = {0.06: 294.4, 0.08: 100.1, 0.09: 52.0, 0.10: 27.3, 0.12: 7.6}
for i, th in enumerate(THS_ORDER):
    row = sens.iloc[i]
    check(f"th={th}(행{i}) D, CSV값(반올림 손실 가능)", float(row["합계_연평균시간"]), exp_sens[th], TOL_H, advisory=True)
row09 = sens.iloc[THS_ORDER.index(0.09)]
check("th=0.09 A", float(row09["TypeA_연평균시간"]), 49.8, TOL_H)
check("th=0.09 B", float(row09["TypeB_연평균시간"]), 2.2, TOL_H)

# CSV는 float_format="%.1f"로 값 자체도 반올림 손실이 있을 수 있다(예: 27.25 -> banker's rounding -> "27.2").
# 그래서 CSV와 별개로 gate1_analysis 를 직접 호출해 5개 임계값을 새로 계산한 "진짜" 값으로도 확정한다.
print("  -- 위 CSV값과 별개로, gate1_analysis 직접 재계산(반올림 손실 없음) --")
assert g1.O3_TH == 0.09  # 재설정 전 기본값 확인
oz0 = g1.load_ozone_cached(); oz0 = oz0[oz0["datetime"].dt.year <= 2025]
asos0 = g1.load_asos_with_at()
_, _, warn0 = g1.heatwave_days(asos0)
base0 = g1.merge_shift(oz0, asos0, warn0, 0)
ns0 = base0["datetime"].dt.year.nunique()
for th in THS_ORDER:
    g1.O3_TH = th
    mm = g1.flags(base0.copy(), (11, 18))
    stt = mm.groupby("station_code")[["A", "B", "D"]].sum() / ns0
    check(f"th={th} D, 재계산(원값)", float(stt["D"].median()), exp_sens[th], TOL_H)
g1.O3_TH = 0.09  # 이후 블록을 위해 기본값 복원

# ---------- 시각별 분포 (라벨 9~21, 임계값 0.09) ----------
hm = pd.read_csv(os.path.join(OUT, "6주차_시각별_사각지대_분포.csv"), encoding="utf-8-sig")
h09 = hm[hm["임계값_ppm"] == 0.09].set_index("라벨시각")
print("\n[시각별, th=0.09]")
max_label = int(h09["합계_연평균시간"].idxmax())
check("최대 시각 라벨", max_label, 16, 0)
check("라벨16 D", float(h09.loc[16, "합계_연평균시간"]), 11.1, TOL_H)
check("라벨9 D", float(h09.loc[9, "합계_연평균시간"]), 0.0, TOL_H)
check("라벨10 D", float(h09.loc[10, "합계_연평균시간"]), 0.0, TOL_H)
sum_11_18 = float(h09.loc[11:18, "합계_연평균시간"].sum())
sum_9_21 = float(h09.loc[9:21, "합계_연평균시간"].sum())
check("라벨11~18 합", sum_11_18, 52.2, TOL_H)
check("라벨9~21 합", sum_9_21, 57.8, TOL_H)

# ---------- 연도 추세검정 ----------
tr = pd.read_csv(os.path.join(OUT, "6주차_연도추세검정.csv"), encoding="utf-8-sig")
print("\n[연도 추세검정]")


def trow(대상, 유형):
    return tr[(tr["대상"] == 대상) & (tr["유형"] == 유형)].iloc[0]


r = trow("2018~2025 (8점)", "TypeA")
check("TypeA(8점) p", float(r["p값_정확검정(순열)"]), 0.0004, TOL_P)
check("TypeA(8점) Theil-Sen 기울기", float(r["TheilSen기울기_시간/년"]), 6.8, TOL_SLOPE)
r = trow("2020·2021 제외 (6점)", "TypeA")
check("TypeA(6점, 2020·21제외) p", float(r["p값_정확검정(순열)"]), 0.0167, TOL_P)
check("TypeA(6점) Theil-Sen 기울기", float(r["TheilSen기울기_시간/년"]), 6.9, TOL_SLOPE)
r = trow("2018~2025 (8점)", "TypeB")
check("TypeB(8점) p", float(r["p값_정확검정(순열)"]), 0.149, TOL_P)
r = trow("2020·2021 제외 (6점)", "TypeB")
check("TypeB(6점, 2020·21제외) p", float(r["p값_정확검정(순열)"]), 0.567, TOL_P)

stop_if_mismatch()
if csv_rounding_notes:
    print(f"\n(참고) CSV 반올림 아티팩트로 설명되는 차이 {len(csv_rounding_notes)}건 (재계산 원값은 전부 통과):")
    for n in csv_rounding_notes:
        print(" -", n)
print("\n(2) 6주차 CSV·재계산 전 항목 기대값 일치(반올림 아티팩트 제외) — 통과\n")

# ---------- A3: 폭염특보일 대안정의(alt=True)로 다시 계산 ----------
print("[A3] heatwave_days(alt=True) 로 다시 계산")
assert g1.O3_TH == 0.09
oz = g1.load_ozone_cached()
oz = oz[oz["datetime"].dt.year <= 2025]
asos = g1.load_asos_with_at()
_, _, warn_alt = g1.heatwave_days(asos, alt=True)
base_alt = g1.merge_shift(oz, asos, warn_alt, 0)
n_seasons = base_alt["datetime"].dt.year.nunique()
m = g1.flags(base_alt.copy(), (11, 18))
st = m.groupby("station_code")[["A", "B", "D"]].sum() / n_seasons
check("alt=True A", float(st["A"].median()), 52.19, 0.01)
check("alt=True B", float(st["B"].median()), 1.19, 0.01)
check("alt=True D", float(st["D"].median()), 53.25, 0.01)

stop_if_mismatch()
print("\n=== verify_week6.py 전체 통과 ===")
