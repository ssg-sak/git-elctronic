# 실제 TMAP ETA + 도착 가용 라벨 — 20260806

| 항목 | 값 |
|---|---|
| 출발지 | 동대구역 인근 |
| ETA 커버 | **1848** (공용 추천 후보) |
| 그중 TMAP 실측 | **859** (`eta_is_proxy=false`) |
| 그중 보정 프록시 | **989** (429 QUOTA · **8/7 재개 예정**) |
| 라벨 행 | 2,138,025 |
| 라벨 소 | 1596 |
| 패널 구간 | 2026-07-17 ~ **2026-08-06 08:16** (D2 재빌드 반영) |
| 양성률 (도착 시 가용) | 0.979 |
| 라벨 컬럼 | `target_available_at_arrival` |

## 파일 (repo)

- ETA: `apps/data-pipeline/evaluation/results/datasets/station_tmap_eta_latest.csv`
- 라벨: `.../arrival_labels_tmap_eta_v1.parquet`
- D1+ETA: `.../station_feature_snapshot_with_eta_latest.csv`
- 계획: [`핵심갭_개선계획_20260806.md`](../핵심갭_개선계획_20260806.md)

## ② 사용

- 학습 타겟: `target_available_at_arrival` (고정 10/15/30 replay는 보조)
- 피처 시점: `feature_as_of` (누수 금지)
- `eta_is_proxy`는 **평가 층화만** (학습 입력 금지) · 파생 확정: [`파생변수_검토_도착라벨_20260806.md`](../파생변수_검토_도착라벨_20260806.md)
- 양성률 높음 = t0 available 후보 필터 → PR-AUC / negative recall
- 서빙 최종 3~5: BE TMAP 재호출 권장
- usage·주차 점수로 이 구멍을 메우지 말 것 (HOLD_SPARSE)

```
DA① | real TMAP ETA + arrival labels | 20260806
```
