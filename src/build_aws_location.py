"""
AWS 시간자료에 지점 위치(구·위도·경도·해발고도)를 붙인다.
입력(원본, 수정하지 않음):
  data/AWS/OBS_AWS_TIM_{연도}.csv      기상자료개방포털 방재기상관측(AWS) 시간자료, CP949
  data/AWS/AWS_지점정보_원본.csv        기상자료개방포털 메타데이터 > 관측지점정보, CP949
출력:
  data/AWS/AWS_지점정보_서울.csv        지점·기간별 구/위도/경도/해발고도 정리표
  data/AWS/위치포함/AWS_TIM_{연도}_위치포함.csv
규칙: 시간자료의 일시가 지점정보의 [시작일, 종료일) 기간에 드는 행의 위치를 붙인다(종료일 없음 = 현재).
      구는 지점주소의 '서울특별시 ○○구'에서 추출한다. 행 수가 원본과 같은지 확인한다.
"""
import glob, os, re
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AWS = os.path.join(ROOT, "data", "AWS")

def main():
    M = pd.read_csv(os.path.join(AWS, "AWS_지점정보_원본.csv"), encoding="cp949")
    M = M.rename(columns={"노장해발고도(m)": "해발고도(m)"})
    M["시작일"] = pd.to_datetime(M["시작일"]); M["종료일"] = pd.to_datetime(M["종료일"])
    M["구"] = M["지점주소"].str.extract(r"서울특별시\s+(\S+구)")
    S = M[["지점", "지점명", "시작일", "종료일", "지점주소", "구", "위도", "경도", "해발고도(m)"]].sort_values(["지점", "시작일"])
    S.to_csv(os.path.join(AWS, "AWS_지점정보_서울.csv"), index=False, encoding="utf-8-sig")
    os.makedirs(os.path.join(AWS, "위치포함"), exist_ok=True)
    for f in sorted(glob.glob(os.path.join(AWS, "OBS_AWS_TIM_*.csv"))):
        y = re.search(r"(\d{4})", os.path.basename(f)).group(1)
        d = pd.read_csv(f, encoding="cp949", low_memory=False)
        d["일시"] = pd.to_datetime(d["일시"])
        m = d.merge(S[["지점", "시작일", "종료일", "구", "위도", "경도", "해발고도(m)"]], on="지점", how="left")
        ok = (m["일시"] >= m["시작일"]) & ((m["일시"] < m["종료일"]) | m["종료일"].isna())
        m = m[ok].drop(columns=["시작일", "종료일"]).drop_duplicates(subset=["지점", "일시"], keep="last")
        assert len(m) == len(d), f"{f}: 행 수 불일치 {len(m)} vs {len(d)}"
        assert m["구"].notna().all(), f"{f}: 구 매칭 실패 행 존재"
        out = os.path.join(AWS, "위치포함", f"AWS_TIM_{y}_위치포함.csv")
        m.to_csv(out, index=False, encoding="utf-8-sig")
        print(f"{y}: {len(m):,}행, 지점 {m['지점'].nunique()}개 -> {os.path.basename(out)}")

if __name__ == "__main__":
    main()
