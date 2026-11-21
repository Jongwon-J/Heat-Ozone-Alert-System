"""gate1_results.pkl → output/week2_gate1_report.md (표는 계산 결과에서 자동 생성)"""
import os
import pickle

import pandas as pd

from gate1_analysis import OUT, gate_class

r = pickle.load(open(os.path.join(OUT, "gate1_results.pkl"), "rb"))
N = r["n_seasons"]
main = r["main"]
st = r["station_level"]
B = r["B"]


def md(df, floatfmt=1):
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]
    for _, row in df.iterrows():
        cells = [f"{v:,.{floatfmt}f}" if isinstance(v, float) else (f"{v:,}" if isinstance(v, int) else str(v)) for v in row]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def dist_classes(s):
    c = pd.cut(s, [-1, 10 - 1e-9, 30 - 1e-9, 1e9], labels=["축소", "재판정", "진행"]).value_counts()
    return f"진행 {c.get('진행', 0)} / 재판정 {c.get('재판정', 0)} / 축소 {c.get('축소', 0)}"


def top5(col):
    t = st.sort_values(f"{col}_per_year", ascending=False).head(5)
    return ", ".join(f"{n}({ty[:2]}) {v:.1f}" for n, ty, v in zip(t["station_name"], t["station_type"], t[f"{col}_per_year"]))


def pct(a, b):
    return f"{(a / b - 1) * 100:+.1f}%"


L = []
add = L.append
add("# Week 2 Gate 1 리포트 — 타임스탬프 검증 · 집계방식 비교 · 정식 Type A/B\n")
add(f"- 분석 대상: 서울 40개 측정소(도시대기 25 + 도로변대기 15), **{r['years'][0]}~{r['years'][-1]}년 5~9월 ({N}시즌)**. "
    "2026년은 에어코리아 5~9월 자료가 없어 제외.")
add("- 조건: 오존 ≥ 0.09 ppm, 체감온도 33℃, 근무시간대 = 10~18시 라벨(18시 포함), 폭염특보일 = 일 최고 체감온도 33℃ 이상 2일 연속(정의문서 5절).")
add("- 표의 시간은 모두 **연평균 시간 = 8시즌 합계 ÷ 8**. 재현 확인: 이전 단계 병합 CSV와 행 수 "
    f"{r['repro']['prev_rows']:,} = {r['repro']['now_rows']:,}, 체감온도 최대 차이 {r['repro']['AT_maxdiff']:.1e}.")
add("- **판정 기준(정의문서 7절)**: 연평균 30h 이상 = 진행 / 10~30h = 임계값 조정 후 재판정 / 10h 미만 = PART 1 축소.\n")

# ---------- 요약 ----------
d = main
add("## 0. 한 줄 요약\n")
add(f"- Type A+B 연평균: **방식 1(측정소 평균) {d['mean_D']:.1f}h → 진행**, **방식 2(하나라도) {d['any_D']:.1f}h → 진행**, "
    f"**방식 3(측정소별) 중앙값 {d['st_D'].median():.1f}h → 진행** (측정소 40개 중 진행 27 / 재판정 10 / 축소 3).")
add(f"- 다만 **방식 1은 30h 경계와 가깝다**: 타임스탬프를 +1h 이동하면 {B['+1h']['mean_D']:.1f}h(재판정), 근무시간에서 18시 라벨을 빼면 "
    f"{r['sens']['근무시간 10~17시(18시 라벨 제외)']['mean']:.1f}h(재판정)가 된다. 방식 2·3은 어떤 변형에서도 진행.")
add("- **타임스탬프 정의는 원본 파일 안에서 찾지 못했다.** 어느 정렬이 맞는지는 이 리포트에서 정하지 않았다(아래 B).")
add("- 사각지대의 대부분은 Type A(비특보일). **Type B는 연평균 1.2h(방식 1) / 7.8h(방식 2)로 매우 작다.**\n")

# ---------- A ----------
add("## A. 지난 결과 중 불명확했던 3가지\n")
add("### A-1. 기온·습도 QC플래그 = 1(오류) 처리\n")
add("- 코드(`src/merge_and_scatter.py` `load_asos`): `QC플래그 == 1`이면 해당 기온/습도를 **NaN(결측)으로 바꾸고**, "
    "이후 `merged[merged['AT'].notna()]`에서 체감온도가 NaN인 시각은 **병합 결과에서 제외**된다. 즉 '결측 처리 → 결과적으로 제외'.")
add("- **실제 영향은 0행이다.** 시즌(5~9월, ASOS 32,784행) QC분포: 기온 QC = 공란 30,571 / 0 = 2,213 / **1 = 0건 / 9 = 0건**, "
    "습도도 동일 양상(공란 30,600 / 0 = 2,184). 값 결측도 0건, 2018-05~2025-09 시각 누락도 0건. "
    "(QC 공란은 정상으로 취급.)\n")
add("### A-2. 에어코리아 datetime 역할 컬럼\n")
add("- 원본 컬럼명은 **`측정일시`** (정수 `YYYYMMDDHH`, HH = 01~24, 예: `2022070101`). 별도의 날짜/시간 컬럼은 없다. "
    "코드에서 `datetime`으로 rename하고 24시는 익일 00:00으로 변환한다.")
add("- xlsx 100개 전체의 헤더 동일 확인(`지역, 망, 측정소코드, 측정소명, 측정일시, SO2, CO, O3, NO2, PM10, PM25, 주소`). "
    "예외 1개: `2022년 4월.xlsx`는 값이 없는 빈 컬럼 2개가 더 있음(영향 없음).\n")
add("### A-3. '오존 0.09 이상' 행 수 — 155 vs 18,173의 차이\n")
add("두 숫자는 **같은 대상(개별 측정소 station-hour 행, 2018~2025년 5~9월)이지만 시간대 조건이 다르다.** "
    "155 = 0~9시만, 18,173 = 10~18시(근무시간대)만. 도시평균/개별측정소 차이가 아니다.\n")
a3 = r["A3"]
rows = [
    ("① 개별 측정소 행, 전 시간대", a3["전체 station-hour 행 (전 시간대)"], "≥0.09"),
    ("   ├ 0~9시 (지난 보고의 '155')", a3["  0~9시"], "≥0.09"),
    ("   ├ 10~18시 (지난 보고의 '18,173')", a3["  10~18시 (근무시간대)"], "≥0.09"),
    ("   └ 19~23시", a3["  19~23시"], "≥0.09"),
    ("② 개별 측정소 행, 10~18시 & 체감온도<33℃ (지난 보고의 '14,403')", a3["10~18시 & AT<33 (station-hour 행)"], "≥0.09"),
    ("③ 10~18시 고유 시각 수, 측정소 평균 ≥0.09", a3["10~18시 고유 시각 수 (측정소 평균 ≥0.09)"], "시각 단위"),
    ("④ 10~18시 고유 시각 수, 하나라도 ≥0.09", a3["10~18시 고유 시각 수 (어느 측정소든 ≥0.09)"], "시각 단위"),
    ("⑤ ③ 중 체감온도<33℃ (연평균 33.0h의 8시즌 합)", a3["10~18시 & AT<33: 측정소 평균"], "시각 단위"),
    ("⑥ ④ 중 체감온도<33℃ (연평균 164.0h의 8시즌 합)", a3["10~18시 & AT<33: 어느 측정소든"], "시각 단위"),
]
add(md(pd.DataFrame(rows, columns=["집계", "8시즌 합계", "단위"])))
add(f"\n※ ①=0~9시+10~18시+19~23시 (155+18,173+2,010=20,338). 참고로 초과(>0.09) 기준으로 세면 {a3['전체 station-hour 행, 초과(>0.09) 기준']:,}행. 이 리포트는 모두 ≥0.09 기준.\n")

# ---------- B ----------
add("## B. 타임스탬프 정렬 검증\n")
add("### B-1. 원본 파일에서 '측정시간' 정의 확인\n")
add("- **xlsx 100개 전수**: 시트 이름 `Data` 1개, 주석·메모·도형(drawing) 관련 파일 없음, 헤더는 동일(A-2). "
    "**대표 3개(2018-07, 2022-07, 2026-04)**: 문자열 테이블에 '시간·시각·기준·평균·참고·비고·단위' 등 설명성 텍스트 없음; "
    "2022-07은 마지막 행까지 데이터뿐(각주 행 없음), 문서 속성은 작성자 `keco`뿐.")
add("- **결론: 원본 파일 안에서는 `측정일시`(01~24)가 '구간 시작'인지 '구간 끝(시각 종료)'인지 정의를 찾지 못했다.** → B-2 수행.\n")
add("### B-2. ±1시간 이동 재병합 비교\n")
add("이동 방식: 에어코리아 `datetime`에 Δ를 더한 뒤 ASOS(`일시`)와 병합. **원본(0h)** = 측정일시 HH ↔ ASOS HH:00 (지금까지 사용). "
    "**−1h** = 측정일시 HH ↔ ASOS (HH−1):00. **+1h** = 측정일시 HH ↔ ASOS (HH+1):00. 근무시간대 필터(10~18시)는 이동 후 시각 기준.\n")
rowsC, rowsD = [], []
for k, v in B.items():
    rowsC.append((k, v["mean_C"], v["any_C"], v["st_C_med"]))
    rowsD.append((k, v["mean_A"], v["mean_B"], v["mean_D"], gate_class(v["mean_D"]), v["any_D"], gate_class(v["any_D"]),
                  v["st_D_med"], gate_class(v["st_D_med"])))
add("**(1) 지시하신 조건: 근무시간 & 오존≥0.09 & 체감온도<33℃ — 연평균 시간**\n")
c = pd.DataFrame(rowsC, columns=["정렬", "방식1 측정소 평균", "방식2 하나라도", "방식3 측정소별 중앙값"])
b0 = B["원본(0h)"]
c["변화율(방식1 / 2 / 3)"] = [
    "—" if k == "원본(0h)" else f"{pct(B[k]['mean_C'], b0['mean_C'])} / {pct(B[k]['any_C'], b0['any_C'])} / {pct(B[k]['st_C_med'], b0['st_C_med'])}"
    for k in B]
add(md(c))
add("\n**(2) 참고: 정식 Type A+B 기준 연평균 시간과 Gate 1 등급**\n")
add(md(pd.DataFrame(rowsD, columns=["정렬", "방식1 A", "방식1 B", "방식1 A+B", "방식1 등급", "방식2 A+B", "방식2 등급", "방식3 중앙값 A+B", "방식3 등급"])))
add(f"""
### B-3. 결론 (어느 정렬이 맞는지는 정하지 않음)

- 세 결과의 차이는 **−1h: 약 +6~9%, +1h: 약 −13~14%** 수준이다(위 변화율). 규모는 비슷하고, 방식 2·3의 Gate 등급은 세 정렬 모두 **진행**으로 같다.
- 그러나 **방식 1(측정소 평균)은 등급이 바뀔 수 있다**: 원본 {B['원본(0h)']['mean_D']:.1f}h·−1h {B['-1h']['mean_D']:.1f}h는 진행이지만 **+1h는 {B['+1h']['mean_D']:.1f}h로 30h 미만(재판정)**. "영향 없음"이라고 결론짓기 어렵다 — 방식 1을 쓴다면 이 정렬 문제가 판정을 좌우할 수 있다.
- 어느 쪽이 맞는지는 **에어코리아 확정자료 정의(공식 문서)로 확인해야** 하며, 여기서는 임의로 정하지 않았다. 원본(0h)을 기본으로 표시했을 뿐, 그것이 옳다는 판단은 아니다.
""")

# ---------- C ----------
add("## C. Gate 1 집계 방식 3가지 비교 (채택은 결정하지 않음)\n")
add(f"조건 = 근무시간(10~18시) & 오존 ≥ 0.09 & 체감온도 < 33℃ (특보일 구분 없음). 정렬은 원본(0h). 측정소 평균은 그 시각 관측된 측정소만 평균 "
    f"(시각별 관측 측정소 수: 최소 {r['city_n']['min']} / 중앙 {r['city_n']['median']:.0f} / 최대 {r['city_n']['max']}, 근무시간대 총 {r['city_n']['hours']:,}시각).\n")
sc = st["C_per_year"]
tab = pd.DataFrame([
    ("1. 측정소 평균", "그 시각 40개 측정소 평균 오존 ≥ 0.09", f"{main['mean_C']:.1f}", gate_class(main["mean_C"]), "—"),
    ("2. 하나라도", "40개 중 1곳이라도 조건 충족", f"{main['any_C']:.1f}", gate_class(main["any_C"]), "—"),
    ("3. 측정소별", "측정소마다 따로 센 연평균의 분포", f"최소 {sc.min():.1f} / 중앙 {sc.median():.1f} / 최대 {sc.max():.1f}",
     gate_class(sc.median()) + " (중앙값 기준)", dist_classes(sc)),
], columns=["방식", "정의", "연평균 시간", "Gate 1 등급(참고)", "측정소 등급 분포"])
add(md(tab))
add(f"\n**방식 3 상위 5개 측정소 (연평균 h):** {top5('C')}")
low = st.sort_values("C_per_year").head(3)
add(f"**방식 3 하위 3개:** " + ", ".join(f"{n}({t[:2]}) {v:.1f}" for n, t, v in zip(low["station_name"], low["station_type"], low["C_per_year"])))
ty = st.groupby("station_type")["C_per_year"].agg(["count", "median", "min", "max"])
add("**측정소 유형별(방식 3):** " + "; ".join(f"{i} {int(row['count'])}곳 중앙 {row['median']:.1f}h (범위 {row['min']:.1f}~{row['max']:.1f})" for i, row in ty.iterrows())
    + " → 도시대기와 도로변대기의 차이가 크다(다음 단계 '측정소 유형별 분리분석' 대상).")
add("\n- 세 방식의 값이 5배 이상 다르다(33 vs 164). 방식 1은 서울 평균 오존이 높은 '광역 고오존' 시간만, 방식 2는 어느 한 곳이라도 높은 시간을 센다.")
add("- 정의문서에 추가할 문구 초안: **`output/제안_집계방식.md`** (제안 — 윤서 확인 필요, 미확정). `docs/정의문서_v1.md` 원본은 수정하지 않았다.\n")

# ---------- D ----------
add("## D. 정식 Type A/B와 Gate 1 판정표\n")
add("### D-1. 폭염특보일 재현 (정의문서 5절)\n")
add("- 일 최고 체감온도(ASOS 시간자료 24시간 중 최댓값) ≥ 33℃인 날이 **2일 이상 연속**이면 그 구간의 모든 날을 '폭염특보일'로 판정(구간 안의 첫날도 포함).")
add(f"- 시즌 경계(5/1, 9/30) 33℃ 이상 날: {len(r['edge_hot'])}건 → 시즌 밖 자료 부재로 인한 연속 판정 왜곡 없음. 특보 구간 총 {r['warn_runs']}개.\n")
ws = r["warn_summary"].rename(columns={"year": "연도", "hot_days": "일최고AT≥33 일수", "warn_days": "폭염특보일 수"})
ws["연도"] = ws["연도"].astype(str)
add(md(ws))
add("\n### D-2. 정의 (정의문서 6절)\n")
add("- **Type A** = 폭염특보 기준 미충족일 & 근무시간대 & 오존 ≥ 0.09  (체감온도 조건 없음)")
add("- **Type B** = 폭염특보일 & 근무시간대 & 해당 시각 체감온도 < 33℃ & 오존 ≥ 0.09")
add("- A와 B는 특보일 여부로 갈라지므로 겹치지 않는다. A+B = 합산 시간.\n")
add("### D-3. 최종 Gate 1 판정표 (연평균 시간, 정렬 = 원본 0h)\n")
sB = st["B_per_year"]; sA = st["A_per_year"]; sD = st["D_per_year"]
final = pd.DataFrame([
    ("1. 측정소 평균", f"{main['mean_A']:.1f}", f"{main['mean_B']:.1f}", f"**{main['mean_D']:.1f}**", "**" + gate_class(main["mean_D"]) + "**"),
    ("2. 하나라도", f"{main['any_A']:.1f}", f"{main['any_B']:.1f}", f"**{main['any_D']:.1f}**", "**" + gate_class(main["any_D"]) + "**"),
    ("3. 측정소별 (중앙값)", f"{sA.median():.1f}", f"{sB.median():.1f}", f"**{sD.median():.1f}**", "**" + gate_class(sD.median()) + "**"),
], columns=["집계방식", "Type A", "Type B", "A+B", "Gate 1 등급"])
add(md(final))
add("\n※ 방식 3 행의 A·B·A+B는 각각 40개 측정소의 중앙값이므로 A+B가 A와 B의 합과 같지 않다.")
add(f"\n방식 3 세부: 측정소 40개 A+B 연평균 최소 {sD.min():.1f} / 중앙 {sD.median():.1f} / 최대 {sD.max():.1f}, 등급 분포 = {dist_classes(sD)}. "
    f"상위 5: {top5('D')}.\n")
add("### D-4. 판정에 영향을 줄 수 있는 변동 요인\n")
sens = r["sens"]
sv = [("기본 (근무시간 10~18시, 특보일=연속 구간 전체, 정렬 0h)", main["mean_D"], main["any_D"], sD.median()),
      ("정렬 −1h", B["-1h"]["mean_D"], B["-1h"]["any_D"], B["-1h"]["st_D_med"]),
      ("정렬 +1h", B["+1h"]["mean_D"], B["+1h"]["any_D"], B["+1h"]["st_D_med"])]
for k, v in sens.items():
    sv.append((k, v["mean"], v["any"], v["st_med"]))
sv = pd.DataFrame([(a, f"{b:.1f} ({gate_class(b).split('(')[0]})", f"{c:.1f} ({gate_class(c).split('(')[0]})", f"{d_:.1f} ({gate_class(d_).split('(')[0]})") for a, b, c, d_ in sv],
                  columns=["변형", "방식1 A+B", "방식2 A+B", "방식3 중앙값 A+B"])
add(md(sv))
add("\n- 방식 1만 변형에 따라 등급이 진행↔재판정으로 바뀐다(+1h, 18시 라벨 제외). 방식 2·3은 모든 변형에서 진행.")
by = r["by_year"].rename(columns={"year": "연도"})
by_show = by[["연도", "mean_A", "mean_B", "mean_D", "any_A", "any_B", "any_D"]].rename(columns={
    "mean_A": "방식1 A", "mean_B": "방식1 B", "mean_D": "방식1 A+B", "any_A": "방식2 A", "any_B": "방식2 B", "any_D": "방식2 A+B"})
add("\n**연도별 시간 (해당 연도 5~9월 합계, 연평균 아님):**\n")
by_show = by_show.astype(int).assign(연도=by_show["연도"].astype(str))
add(md(by_show))
add(f"\n- 방식 1의 8시즌 평균 {main['mean_D']:.1f}h는 2023~2025년(34/89/55h)이 끌어올린 값이며, 연도별 중앙값은 {by['mean_D'].median():.1f}h, "
    f"2018~2022년 5시즌은 모두 30h 미만이다. 정의문서 7절은 '연평균'이므로 위 판정은 8시즌 평균 기준이지만, 연도 편차가 크다는 점은 함께 봐야 한다.\n")

# ---------- 한계 ----------
add("## 가정과 미확정 사항 (윤서 확인 필요)\n")
add("1. **타임스탬프 정렬**: 원본에 정의 없음(B). 확정 전에는 방식 1의 판정을 최종으로 쓰기 어렵다.")
add("2. **근무시간 경계**: 정의문서는 '10:00~18:00 [잠정]'. 이 분석은 10~18시 라벨 9개(18시 포함). 18시 라벨을 빼면 방식 1이 29.1h로 내려간다(D-4).")
add("3. **특보일 정의**: '2일 연속 충족한 구간의 모든 날'로 재현. '2일째부터'로 바꾸면 방식 1 A+B 35.0h(D-4).")
add("4. **집계 방식 미선택**: C의 3가지 중 무엇을 Gate 1에 쓸지는 결정하지 않았다(제안 파일 참조). 결과를 이미 본 상태에서 정하는 것이므로, 선택 근거는 결과와 무관한 논리(예: 노출 단위)로 기록하는 것이 7절 원칙('결과 확인 후 기준 변경 금지')에 부합한다.")
add("5. **2026년 미포함**: 5~9월 오존 자료가 없어 8시즌(2018~2025) 평균. 2020~2021 코로나 기간 제외 민감도는 아직 안 함(정의문서 6주차 계획).")
add("6. Type A는 '특보 미충족일'이면 그날 체감온도가 33℃를 넘는 시간이 있어도 포함한다(정의문서 6절 그대로 구현).\n")
add("## 산출물\n")
add("- `output/week2_gate1_report.md` (이 파일), `output/제안_집계방식.md`, `output/gate1_station_level.csv`(측정소별 시간), `output/gate1_results.pkl`, `output/_cache_ozone_seoul_may_sep.parquet`(재실행 가속용 캐시)")
add("- 코드: `src/gate1_analysis.py`(계산), `src/make_gate1_report.py`(이 리포트 생성). 재사용: `merge_and_scatter.py`, `apparent_temperature.py`.")

open(os.path.join(OUT, "week2_gate1_report.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
print("saved report")
