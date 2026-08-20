# 실제 TMAP ETA + 도착 가용 라벨 — 20260809

| 항목 | 값 |
|---|---|
| 출발지 | 동대구역 인근 |
| ETA 성공 소 | 1848 |
| 라벨 행 | 2,659,927 |
| 라벨 소 | 1621 |
| 양성률 (도착 시 가용) | 0.979 |
| 라벨 컬럼 | `target_available_at_arrival` |

## 파일 (repo)

- ETA: `apps/data-pipeline/evaluation/results/datasets/station_tmap_eta_latest.csv`
- 라벨: `.../arrival_labels_tmap_eta_v1.parquet`
- D1+ETA: `.../station_feature_snapshot_with_eta_latest.csv`

## ② 사용

- 학습 타겟: `target_available_at_arrival`
- 피처 시점: `feature_as_of` (누수 금지: 도착 이후 정보 사용 금지)
- 서빙: 최종 3~5는 BE TMAP 재호출 권장. 이 테이블은 학습·오프라인 평가용 실측 ETA.

```
DA① | real TMAP ETA + arrival labels | 20260809
```
