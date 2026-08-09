# derived_v0 부착 완료 — 20260806

| 항목 | 값 |
|---|---|
| 라벨 행 | 2,659,927 |
| 충전소 | 1621 |
| RETAIN | `single_charger` + (`horizon_minutes` 권장 / `eta_bucket` 대안) |
| EXCLUDE 학습 | `eta_is_proxy` · 여유충전기 · 경과×ETA |
| HOLD | `avail_ratio_t0` · 오래됨/미관측(패널 컬럼 부재) |

## 파일

- 라벨+파생: `apps/data-pipeline/evaluation/results/datasets/arrival_labels_tmap_eta_v1_with_derived.parquet`
- D1+ETA+파생: `.../station_feature_snapshot_with_eta_derived_latest.csv`
- 스키마: `.../derived_v0_schema.json`
- 검토 원문: [`파생변수_검토_도착라벨_20260806.md`](../파생변수_검토_도착라벨_20260806.md)

## HOLD 재검증 요약

- 가용비율 AUC≈0.45655506247678435 → HOLD 유지
- 단수충전기 → RETAIN 확인
- 오래됨/미관측 → 패널에 tick 단위 age/state 없음 → HOLD_BLOCKED

```
DA① | derived_v0 attached | 20260806
```
