# 실제 TMAP ETA + 도착 가용 라벨 — 20260808

| 항목 | 값 |
|---|---|
| 출발지 | 동대구역 인근 |
| ETA 성공 소 | 1848 |
| 라벨 행 | 2,521,157 |
| 라벨 소 | 1620 |
| 양성률 (도착 시 가용) | 0.979 |
| 라벨 컬럼 | `target_available_at_arrival` |

## 파일 (repo)

- ETA: `apps/data-pipeline/evaluation/results/datasets/station_tmap_eta_latest.csv`
- 라벨: `.../arrival_labels_tmap_eta_v1.parquet`
- D1+ETA: `.../station_feature_snapshot_with_eta_latest.csv`

## ⚠ 조장 필독

출발지 = **동대구역 고정**. 지리 대리 편향 가능.  
서빙 최종 3~5는 **BE 사용자 위치 TMAP만**. 이 테이블을 런타임 ETA로 쓰지 말 것.  
→ [`../ETA_동대구고정_한계_조장필독_20260808.md`](../ETA_동대구고정_한계_조장필독_20260808.md)

## ② 사용

- 학습 타겟: `target_available_at_arrival`
- 피처 시점: `feature_as_of` (누수 금지: 도착 이후 정보 사용 금지)
- 서빙: 최종 3~5는 BE TMAP 재호출 **필수**. 이 테이블은 학습·오프라인 평가용 실측 ETA.

```
DA① | real TMAP ETA + arrival labels | 20260808
```
