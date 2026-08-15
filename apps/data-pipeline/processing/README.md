# 데이터·파이프라인 패키지 (`apps/data-pipeline/processing/`)

**코드 찾기:** [`../DA1_핵심코드_인덱스.md`](../DA1_핵심코드_인덱스.md) ← TOP7 · A~G 분류

본 디렉토리는 **AI·데이터 ① — 데이터·파이프라인** 담당 영역이다.  
수집된 원본을 정의·품질·표준화·전처리·공간결합·EDA·특성 생성까지 거쳐, **규칙 추천용·모델 학습용 데이터셋**으로 만든다.

역할·완료 기준: [`../README-이현석.md`](../README-이현석.md) · [`../AGENTS.md`](../AGENTS.md)  
경로 정본: [`../loop_paths.py`](../loop_paths.py)

---

## 폴더 매핑 (파이프라인별)

| 폴더 | 역할 | 주요 진입점 |
|---|---|---|
| `common/` | 인코딩 등 공통 | `repair_csv_mojibake.py` |
| `core/` | 정제·집계·신뢰도·SQLite 파이프라인 | `pipeline.py`, `cleansing.py` |
| `extract/` | 단발·루프용 API 추출 | `extract_daegu_traffic.py`, `extract_utic_incident.py`, `extract_tour_attractions.py` |
| `loops/` | 주기 수집 러너 | `run_daegu_traffic_loop.py`, `run_utic_loop.py` |
| `features/` | status 패널·이용이력·역 피처 | `build_usage_history_features.py`, `status_as_of.py`, `station_features.py` |
| `analysis/` | KPI·관광지·품질·라벨 | `report_kpi.py`, `analyze_tour_charger_usage.py` |
| `db/` | Postgres/SQLite 적재 | `load_status_panel_to_pg.py`, `sql/` |

데이터 저장:
- 라이브 루프 → `docs/data/loops/loop1|2|3/` (별칭 status / utic / daegu_traffic)
- 단발 추출 → `docs/data/extracted/{charger,tour,parking,...}/`
- 서버 풀 복사 → `docs/data/loops/_archive/`

---

## 실행 예 (repo root)

```bash
python apps/data-pipeline/processing/loops/run_daegu_traffic_loop.py --interval-minutes 15
python apps/data-pipeline/processing/loops/run_utic_loop.py --interval-minutes 15
python apps/data-pipeline/processing/analysis/analyze_tour_charger_usage.py
python apps/data-pipeline/processing/analysis/report_kpi.py
python apps/data-pipeline/processing/features/build_usage_history_features.py
```

진입 스크립트는 `_bootstrap.ensure_paths()` 로 `processing/` · `apps/data-pipeline/` 를 path에 올린다.
