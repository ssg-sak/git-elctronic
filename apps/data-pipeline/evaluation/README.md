# 데이터 가공 실험 및 테스트 (evaluation)

**코드 찾기:** [`../DA1_핵심코드_인덱스.md`](../DA1_핵심코드_인덱스.md)  
(현재표·시간표는 `SANDBOX_20260716` / `SANDBOX_20260717`, EDA는 `eda/`, 테스트는 `tests/`)

`scripts/api-tests/`(API 연결 검증)와 **별도**로, AI·데이터 ① 파이프라인(정의·품질·전처리·EDA·특성·데이터셋) 실험·단위 테스트·팀 보고용 리포트를 담당합니다.

## 디렉터리

```
evaluation/
├── run_experiment.py      # 실험 실행 (팀 보고용 JSON/MD 생성)
├── experiment.py          # 지표 산출 로직
├── csv_loader.py          # docs/data/extracted CSV 로더
├── report.py              # Markdown 리포트 생성
├── fixtures/              # 단위 테스트용 샘플 CSV
├── tests/                 # pytest (가공 로직 + 실험 통합)
└── results/               # 실험 결과 저장 (experiment_*.json / *.md)
```

## 1. 실험 실행 (팀 보고용)

```bash
cd git-elctronic
pip install -r apps/data-pipeline/evaluation/requirements.txt
python apps/data-pipeline/evaluation/run_experiment.py
```

생성 파일:
- `evaluation/results/experiment_YYYYMMDD_HHMMSS.json` — 수치·분포 (원본)
- `evaluation/results/experiment_YYYYMMDD_HHMMSS.md` — 발표/보고용 요약

## 2. 단위 테스트

```bash
cd apps/data-pipeline/evaluation
pytest tests/ -v
```

## 3. 입력 데이터

기본 경로: `docs/data/extracted/`

| 파일 패턴 | 용도 |
|---|---|
| `daegu_charger_info_*.csv` | 충전소·충전기 정적 정보 |
| `daegu_charger_status_*.csv` | 실시간 상태 (변경분) |
| `daegu_parking_*_mock.csv` | 주차 mock |
| `daegu_tour_attractions_*.csv` | TourAPI |
| `daegu_weather_ultra_*.csv` | 기상 |

## 4. 실험 지표 (보고서에 포함)

- 입력 건수 (info/status/주차/tour/날씨)
- 정제 후 충전소·충전기 수
- 신뢰도 등급 분포 (HIGH / NORMAL / CHECK_REQUIRED)
- 충전기 상태 분포 (AVAILABLE / CHARGING / …)
- 평균 사용 가능 비율, 0대 충전소 수

## 5. api-tests 와 구분

| | `scripts/api-tests/` | `evaluation/` |
|---|---|---|
| 목적 | API 키·연결 PASS/FAIL | 가공 로직·데이터 품질 실험 |
| 입력 | live API | 추출 CSV |
| 출력 | 콘솔 | JSON + Markdown 리포트 |
