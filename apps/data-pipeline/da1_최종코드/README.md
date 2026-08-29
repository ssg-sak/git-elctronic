# DA① 내가 작업한 코드 — 여기만 보면 됨

경로: `apps/data-pipeline/da1_최종코드/`

샌드박스·깊은 경로 뒤질 필요 없음. **아래 폴더를 열어서 파일을 직접 보면 된다.**  
(원본 위치에서 복사해 둔 확인용. 내용이 곧 작업 코드다.)

| 폴더 | 뭐가 있나 | 대표 파일 |
|---|---|---|
| `01_현재표_시간표_전처리/` | dedupe · gap-safe · 현재표 · 시간표 | `load_snapshots.py` `build_panel.py` `build_d1_snapshot.py` `build_d2_panel.py` `gap_safe_panel.py` |
| `02_신뢰도_상태/` | 신선도 · 상태표준 · 피처집계 | `reliability.py` `status_standard.py` `status_as_of.py` `station_features.py` |
| `03_라벨_ETA/` | 도착 라벨 · ETA · lag | `build_station_eta_and_labels.py` `build_station_horizon_training.py` … |
| `04_품질_KPI/` | validate · KPI · 품질 | `validate_recommendation_inputs.py` `report_kpi.py` … |
| `05_EDA/` | E1~E5 · 혼잡 | `eda_e1_…` ~ `eda_e5_…` |
| `06_피처선정/` | 9피처 · 적합 · 과적합 | `finalize_hgb_feature_selection.py` … |
| `07_공간조인_HOLD/` | 주차·UTIC·usage | `join_parking_team5.py` … |
| `08_테스트/` | 핵심 테스트 | `test_gap_safe_panel.py` … |

**총 49개 .py** (확인용 모음. 실행·수정 정본은 `processing/` · `evaluation/`)

```
da1_최종코드 | 작업코드 모아보기
```
