# IQR 이상치 검사 — 20260806

| 항목 | 값 |
|---|---|
| as_of | 2026-08-06T08:16:01+09:00 |
| stations | 4210 |
| 방법 | Tukey 1.5·IQR · 참고 3·IQR (IQR≈0이면 p01–p99) |

## 그림

- `figures/01_iqr_outlier_rates.png` — 지표별 이상치 비율
- `figures/02_iqr_boxplots_key_metrics.png` — boxplot
- `figures/03_top_outlier_distributions.png` — 상위 지표 분포+fence

## 주의

- `parking_occupancy_rate`는 **0~100(%)** 스케일
- 변경분 수집 특성상 age·가용 꼬리가 길 수 있음 → **무조건 오류·폐기 아님**
- ETA 작업 전 현황 스냅샷용

## ② 해석

→ [`IQR_이상치_모델해석_20260806.md`](../IQR_이상치_모델해석_20260806.md)  
한 줄: age·충전기 수 IQR 이상치는 **꼬리 특성**이지 재료 폐기 사유가 아님.

```
DA① | IQR outlier scan | 20260806
```
