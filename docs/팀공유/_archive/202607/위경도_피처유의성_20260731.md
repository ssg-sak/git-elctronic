# 위도·경도 피처 유의성 점검 (2026-07-31)

| 항목 | 내용 |
|---|---|
| **데이터** | `station_horizon_training_v1` + D1 lat/lng |
| **타겟** | `target_available` (도착 시 가용≥1) |
| **한 줄** | DO_NOT_ADD — univariate signal too weak; keep lat/lng for map/join only |

## 결과 (train split)

| feature | directional_auc | blocked_auc | auc_ci_low | point_biserial | decision |
|---|---:|---:|---:|---:|---|
| `lat` | 0.5138118564853502 | 0.5090061210820955 | 0.5013656838882342 | -0.014268644421792941 | DROP_LIKELY |
| `lng` | 0.5282838543139848 | 0.5336493862800369 | 0.5024165434285505 | 0.028596525641697547 | DROP_LIKELY |
| `dist_from_daegu_center_km` | 0.5496239283931594 | 0.5327190462716557 | 0.5003322429889386 | 0.020944520317327867 | DROP_LIKELY |
| `available_count` | 0.8317769015594652 | 0.8195973123112905 | 0.7920177045755841 | 0.24964565996605567 | BASELINE_REF |
| `horizon_minutes` | 0.5423522422944074 | 0.5475606108904402 | 0.5247264187941136 | 0.04233626458666566 | BASELINE_REF |
| `observation_age_minutes` | 0.5729661391064163 | 0.5974184184040774 | 0.5645581118304001 | -0.07840942133428508 | BASELINE_REF |

## 해석

- AUC≈0.5면 위치만으로 도착 가용을 거의 구분 못 함.
- `available_count` baseline보다 훨씬 약하면 **모델 피처로 불필요**.
- 위·경도는 **지도·거리·조인**용으로만 유지.

상세: `docs/data/analysis/coord_feature_significance_20260731/`

```
DA① | lat/lng significance vs target_available | 2026-07-31
```
