"""
오존-기상 데이터 병합 및 사각지대 탐색 산점도
정의문서_v1.md 1절(분석 범위), 6절(사각지대 정의), 8절(사용 데이터) 참고

입력 (프로젝트 루트 기준)
  data/ASOS/ASOS_TIM_{연도}.csv        기상청 ASOS 서울(108) 시간자료, CP949
  data/Ozone/{연도}/*.xlsx             에어코리아 확정자료, 월별 xlsx, 전국 (서울만 추출)
출력 (output/)
  merged_ozone_weather.csv             utf-8-sig
  scatter_hour_ozone_AT.png

실행: 프로젝트 루트에서  python3 src/merge_and_scatter.py
"""
import glob
import os
import re
import unicodedata
from multiprocessing import Pool

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.colors import TwoSlopeNorm

from apparent_temperature import apparent_temperature  # 검증 완료된 함수 재사용

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASOS_GLOB = os.path.join(ROOT, "data", "ASOS", "ASOS_TIM_*.csv")
OZONE_GLOB = os.path.join(ROOT, "data", "Ozone", "*", "*.xlsx")
OUT_DIR = os.path.join(ROOT, "output")

OZONE_THRESHOLD = 0.09          # 정의문서_v1.md 4절 기본값
HEAT_AT = 33                    # 폭염주의보 체감온도 기준 (정의문서_v1.md 5절), 색 중심값으로만 사용
SEASON_MONTHS = range(5, 10)    # 정의문서_v1.md 1절: 5~9월
NETWORKS = ["도시대기", "도로변대기"]  # 정의문서_v1.md 1절: 도시대기 + 도로변측정소

# 실제 컬럼명 (헤더 확인 결과)
ASOS_COLS = {
    "일시": "datetime",
    "기온(°C)": "Ta",
    "기온 QC플래그": "Ta_QC",
    "습도(%)": "RH",
    "습도 QC플래그": "RH_QC",
    "풍속(m/s)": "WS",
    "일사(MJ/m2)": "SR",
    "강수량(mm)": "RN",
}
AIR_COLS = {
    "지역": "region",
    "망": "station_type",       # 도시대기 / 도로변대기 — 측정소 유형별 분석용, 반드시 유지
    "측정소코드": "station_code",
    "측정소명": "station_name",
    "측정일시": "datetime",     # YYYYMMDDHH, HH = 01~24
    "O3": "O3",
    "NO2": "NO2",
    "PM10": "PM10",
    "PM25": "PM25",
}


def read_csv_robust(path):
    """공공데이터 CSV는 CP949인 경우가 많아 cp949 → euc-kr → utf-8 순으로 시도한다."""
    for enc in ["cp949", "euc-kr", "utf-8", "utf-8-sig"]:
        try:
            return pd.read_csv(path, encoding=enc), enc
        except UnicodeDecodeError:
            continue
    raise ValueError(f"{path}: 지원 인코딩으로 읽지 못함")


def load_asos():
    frames = []
    for path in sorted(glob.glob(ASOS_GLOB)):
        df, enc = read_csv_robust(path)
        print(f"[ASOS] {os.path.basename(path)} enc={enc} rows={len(df):,}")
        missing = set(ASOS_COLS) - set(df.columns)
        if missing:
            raise KeyError(f"{path}: 컬럼 누락 {missing}. 실제 컬럼: {list(df.columns)}")
        frames.append(df[list(ASOS_COLS)].rename(columns=ASOS_COLS))
    asos = pd.concat(frames, ignore_index=True)
    asos["datetime"] = pd.to_datetime(asos["datetime"])

    # QC플래그 1 = 오류 → 결측 처리 (9 = 결측은 값이 이미 비어 있음, 공란 = 정상)
    for v, q in [("Ta", "Ta_QC"), ("RH", "RH_QC")]:
        asos.loc[asos[q] == 1, v] = float("nan")
    # 강수량 공란은 결측이 아니라 무강수(0mm)
    asos["RN"] = asos["RN"].fillna(0)

    asos = asos[asos["datetime"].dt.month.isin(SEASON_MONTHS)]
    return asos.drop(columns=["Ta_QC", "RH_QC"]).drop_duplicates("datetime")


def _read_ozone_month(path):
    df = pd.read_excel(path, sheet_name=0)
    missing = set(AIR_COLS) - set(df.columns)
    if missing:
        raise KeyError(f"{path}: 컬럼 누락 {missing}. 실제 컬럼: {list(df.columns)}")
    df = df[list(AIR_COLS)].rename(columns=AIR_COLS)
    df = df[df["region"].str.startswith("서울") & df["station_type"].isin(NETWORKS)]
    print(f"[Ozone] {os.path.relpath(path, ROOT)} 서울 rows={len(df):,}", flush=True)
    return df


def _month_of(path):
    """경로에서 (연도, 월) 추출. '2022년 7월.xlsx' / '2019_07.xlsx' 두 형식.
    macOS 파일명은 NFD(자모 분리)라 NFC로 정규화한 뒤 매칭한다."""
    year = int(os.path.basename(os.path.dirname(path)))
    name = unicodedata.normalize("NFC", os.path.basename(path))
    m = re.search(r"(\d{1,2})월|_(\d{2})\.xlsx$", name)
    return year, int(m.group(1) or m.group(2))


def load_ozone():
    paths = [p for p in sorted(glob.glob(OZONE_GLOB)) if _month_of(p)[1] in SEASON_MONTHS]
    with Pool(4) as pool:
        frames = pool.map(_read_ozone_month, paths)
    air = pd.concat(frames, ignore_index=True)

    # 측정일시 HH는 01~24 (시각 종료 기준 표기). 24시 = 익일 00:00.
    # ASOS 일시(HH:00)와 같은 시각 라벨끼리 맞춘다.
    s = air["datetime"].astype(str)
    air["datetime"] = pd.to_datetime(s.str[:8], format="%Y%m%d") + pd.to_timedelta(
        s.str[8:10].astype(int), unit="h"
    )
    return air


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    asos = load_asos()
    air = load_ozone()

    # 체감온도: ASOS 시간별 (Ta, RH) 고유 조합에 대해 한 번만 계산 (측정소 행마다 재계산 방지)
    valid = asos["Ta"].notna() & asos["RH"].notna()
    asos["AT"] = float("nan")
    asos.loc[valid, "AT"] = [apparent_temperature(t, h) for t, h in zip(asos.loc[valid, "Ta"], asos.loc[valid, "RH"])]

    air = air[air["O3"].notna() & (air["O3"] >= 0)]  # 결측·음수(점검/보정 코드) 제외
    merged = pd.merge(asos, air, on="datetime", how="inner")  # 1시각 : 다수 측정소
    merged = merged[merged["AT"].notna()].copy()
    merged["hour"] = merged["datetime"].dt.hour
    merged = merged.sort_values(["datetime", "station_code"]).reset_index(drop=True)

    print(f"\n병합 결과: {len(merged):,}행, 기간 {merged['datetime'].min()} ~ {merged['datetime'].max()}")
    print(f"측정소 {merged['station_code'].nunique()}개, 유형별 행수: {merged['station_type'].value_counts().to_dict()}")
    print(f"연도별 행수: {merged['datetime'].dt.year.value_counts().sort_index().to_dict()}")

    out_csv = os.path.join(OUT_DIR, "merged_ozone_weather.csv")
    merged.to_csv(out_csv, index=False, encoding="utf-8-sig")
    print(f"저장: {out_csv}")

    plot(merged, os.path.join(OUT_DIR, "scatter_hour_ozone_AT.png"))


def plot(merged, out_png):
    plt.rcParams["font.family"] = "AppleGothic"
    plt.rcParams["axes.unicode_minus"] = False

    # 겹침(overplotting)으로 특정 색이 가려지지 않도록 그리는 순서를 섞는다.
    d = merged.sample(frac=1, random_state=0)
    # 색 기준점 = 폭염특보 체감온도 기준 33℃ (정의문서_v1.md 5절): 파랑 <33 / 빨강 ≥33
    norm = TwoSlopeNorm(vcenter=HEAT_AT, vmin=d["AT"].min(), vmax=d["AT"].max())
    fig, ax = plt.subplots(figsize=(11, 6.5))
    sc = ax.scatter(d["hour"], d["O3"], c=d["AT"], cmap="coolwarm", norm=norm, s=6, alpha=0.5,
                    linewidths=0, rasterized=True)
    cb = fig.colorbar(sc, ax=ax, label=f"체감온도 (℃)  [중심 {HEAT_AT:g}℃ = 폭염특보 기준]")
    cb.solids.set_alpha(1)  # 산점도 alpha가 색상 막대에 적용되어 흐려지는 것 방지
    ax.axhline(OZONE_THRESHOLD, color="red", linestyle="--", linewidth=1.2,
               label=f"오존 임계값 {OZONE_THRESHOLD} ppm")
    ax.set_xticks(range(24))
    ax.set_xlabel("시각 (0~23시)")
    ax.set_ylabel("오존 농도 (ppm)")
    ax.set_title(f"시각별 오존 농도, 색=체감온도 (서울 5~9월 2018~2025, n={len(d):,})")
    ax.legend(loc="upper left")
    fig.tight_layout()
    fig.savefig(out_png, dpi=150)
    print(f"저장: {out_png}")


if __name__ == "__main__":
    main()
