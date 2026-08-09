# ETA 보정 샘플 — 20260806

| 항목 | 값 |
|---|---|
| 역할 | DA① **오프라인 보정** (런타임 ETA 권한 아님) |
| 출발지 | 4곳 × 각 16소 (≤8.0km) |
| TMAP 성공 | **64/64** |
| 전역 보정비 (tmap/hv@30) median | **1.9375** |
| 후보 | 공용·coord_ok (`apps/data-pipeline/evaluation/results/datasets/station_feature_snapshot_latest.csv`) |

## ②·BE 쓰는 법

1. **서빙 정본:** 최종 후보 3~5곳만 BE가 TMAP 호출 → `eta_minutes`
2. **학습/리플레이 보조:** `eta_proxy_min ≈ haversine_km/30*60 * ratio_band`  
   (`data/calibration.json` · `eta_ratio_by_distance_band.csv`)
3. D1 `eta_minutes` **일괄 채우지 않음**
4. 도착×useTime 게이트 샘플 컬럼 `da_arrival_gate` 참고

## 그림

- `figures/01_tmap_vs_haversine.png`
- `figures/02_ratio_by_band.png`

```
DA① | ETA calibration sample | 20260806
```
