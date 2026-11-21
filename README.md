# 이동노동자 폭염·대기질 복합리스크 평가 및 대응 시스템 (팀 씨앗)

HUFS H-UP 12기. 서울 이동노동자가 **폭염특보가 없는데 오존이 높은 근무시간(사각지대)** 에 노출되는지 확인하고,
내일 오후 오존 고농도 예측과 구별 쉼터 접근성 분석으로 대응 방안을 만드는 프로젝트입니다.

| 단계 | 내용 | 상태 |
|---|---|---|
| Gate 1 | 사각지대 존재 확인 (2018–2025, 5–9월, 근무시간 라벨 11–18) | 완료: 연 52.0시간 |
| Gate 2 | 익일 오존 고농도 예측모델 판정 | 판정 기준 확정 (`docs/Gate2_예측모델_판정기준.md`) |
| Gate 3 | 구별 쉼터 접근성(회피불가능성) | 확정안 v14 (`docs/회피불가능성_변수_확정안_v14.docx`) |

---

## 1. 처음 한 번만: 환경 맞추기

모두 같은 결과가 나오도록 **패키지 버전을 고정**해 두었습니다. 둘 중 하나를 고르세요.

### A. 로컬 Python (분석 코드 실행용)
```bash
git clone https://github.com/Jongwon-J/Heat-Ozone-Alert-System.git
cd Heat-Ozone-Alert-System
git checkout part1-diagnosis

python3.11 -m venv .venv          # Python 3.11 권장 (Docker 이미지와 동일)
source .venv/bin/activate         # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### B. Docker (Airflow 파이프라인까지 똑같이 돌릴 때)
Docker Desktop 설치 후 프로젝트 폴더에서:
```bash
docker compose up -d              # Postgres + Airflow scheduler
```
이미지는 `docker/Dockerfile.airflow`(Python 3.11)와 `docker/requirements-airflow.txt`로 만들어지며,
`requirements.txt`와 같은 버전입니다.

### API 키
```bash
cp .env.example .env              # 그다음 .env에 각자 키 입력 (.env는 git에 올라가지 않음)
```

## 2. 데이터 받기 (git에 없음)

원본 데이터(약 430MB)는 용량 때문에 저장소에 넣지 않았습니다.

1. 구글 드라이브에서 `HUFS_H-UP_data.zip`을 받습니다: **<드라이브 링크>**
2. 프로젝트 폴더 바로 아래에 압축을 풀면 아래 구조가 됩니다.

```
data/
├── ASOS/ASOS_TIM_2018~2025.csv          기상청 ASOS 시간자료 (서울 108)
├── AWS/OBS_AWS_TIM_2018~2026.csv        기상청 AWS 시간자료 (서울)
│   ├── AWS_지점정보_원본.csv / AWS_지점정보_서울.csv
│   └── 위치포함/AWS_TIM_{연도}_위치포함.csv   (src/build_aws_location.py 산출물)
├── Ozone/2018~2026/*.xlsx               에어코리아 확정자료
├── HeatIllness/온열질환 발생 신고 데이터(2011-2025).csv
└── GIS/HangJeongDong_ver20261001.geojson   행정동 경계 (vuski/admdongkor ver20261001 고정)
output/_cache_ozone_seoul_may_sep.parquet   오존 캐시 (없으면 xlsx에서 다시 만듦, 느림)
```

## 3. 실행과 기대 결과

자세한 내용은 `output/재현_방법.md`. 같은 환경이면 아래 값이 **그대로** 나와야 합니다.

| 명령 | 기대 출력 |
|---|---|
| `python src/run_label11_18.py` | 라벨 11–18 행 `m3_stmedian_D=52.00` |
| `python src/run_week6.py` | `TypeA_연평균시간=49.8125 TypeB_연평균시간=2.1875` |
| `python src/run_week7.py` | `[2018 포함] 매칭 쌍 55개 ... p=0.189632` |
| `python src/make_heatmaps.py` | `output/6주차_시각별_히트맵_*.png` 저장 |
| `pytest tests/` | `8 passed, 1 skipped` (호스트) |
| `docker compose exec airflow-scheduler pytest /opt/project/tests` | `9 passed` (컨테이너) |
| `docker compose exec airflow-scheduler airflow dags trigger gate1_label11_18` | `airflow dags list-runs -d gate1_label11_18` 의 state가 `success` |

값이 다르면 먼저 Python·패키지 버전(`pip list`)과 `data/` 구조를 확인하세요.

## 4. 폴더 구조

```
src/      분석 코드 (gate1_analysis.py · apparent_temperature.py · merge_and_scatter.py 는 공통 함수)
tests/    pytest
dags/     Airflow DAG
docker/   Airflow 이미지
docs/     판정 기준·정의문서·확정안·실행계획
output/   분석 결과(csv·png·md). 대용량 중간 산출물(*.parquet, *.pkl)은 git 제외
```

## 5. 함께 작업할 때 규칙

- `data/`, `.env`, 행정 문서(`docs/reports/`)는 올리지 않습니다 (`.gitignore`에 등록됨).
- 공통 함수 파일(`src/gate1_analysis.py` 등)은 수정하지 말고, 새 분석은 새 파일로 추가합니다.
- 작업은 각자 브랜치에서 하고 Pull Request로 합칩니다.
- Gate 2 시험 연도(2025) 자료는 판정 기준 동결 전까지 통계를 보지 않습니다 (`docs/Gate2_예측모델_판정기준.md` 6장).
