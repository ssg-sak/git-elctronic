# 위도·경도 피처 유의성 점검 (20260803)

| 항목 | 내용 |
|---|---|
| **데이터** | `station_horizon_training_v1` + D1 lat/lng |
| **타겟** | `target_available` (도착 시 가용≥1) |
| **한 줄** | DO_NOT_ADD — univariate signal too weak; keep lat/lng for map/join only |

## 결과 (train split)

| feature | directional_auc | blocked_auc | auc_ci_low | point_biserial | decision |
|---|---:|---:|---:|---:|---|
| `lat` | 0.5246441582162804 | 0.5200742410228922 | 0.5096702406857836 | -0.02855733886570877 | DROP_LIKELY |
| `lng` | 0.5268725931777919 | 0.5273247218265694 | 0.5133223572706819 | 0.02607596180734978 | DROP_LIKELY |
| `dist_from_daegu_center_km` | 0.542633918355065 | 0.512446787541707 | 0.5000590769230769 | 0.013905642061057556 | DROP_LIKELY |
| `observation_age_minutes` | 0.567191455061616 | 0.5719204706569283 | 0.5503429447409579 | -0.07416643549819352 | BASELINE_REF |
| `available_count` | 0.8219060634410397 | 0.819165047140909 | 0.7953356706615519 | 0.2402864811247465 | BASELINE_REF |
| `horizon_minutes` | 0.5415192098211987 | 0.5526416479295192 | 0.5339864435847714 | 0.04107548239600675 | BASELINE_REF |

## 해석

- AUC≈0.5면 위치만으로 도착 가용을 거의 구분 못 함.
- `available_count` baseline보다 훨씬 약하면 **모델 피처로 불필요**.
- 위·경도는 **지도·거리·조인**용으로만 유지.

상세: `docs/data/analysis/coord_feature_significance_20260803/`

```
DA① | lat/lng significance vs target_available | 20260803
```
