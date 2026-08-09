# HGB 적합도 — 도착 ETA 라벨 (2026-08-08)

| 항목 | 값 |
|---|---|
| **모델** | HistGradientBoosting (확정 기준) |
| **타겟** | `target_available_at_arrival` |
| **샘플** | 453,830행 · 양성률 0.881 |
| **구간** | 2026-07-17 13:41:56 ~ 2026-08-08 11:07:45 |
| **권장 spec** | `D_horizon_only_eta_family` |
| **valid PR-AUC** | 0.9840856906632983 |
| **valid neg-recall** | 0.8439543389116702 |
| **valid Brier** | 0.14280950150768074 |
| **test PR-AUC** | 0.9830030251029342 |

## 권장 피처

```
available_count,total_chargers,known_charger_count,observation_coverage,single_charger,hour,weekday,is_weekend,avail_rate_lag_15m,avail_rate_lag_60m,horizon_minutes,tmap_eta_min,haversine_km
```

## 산출

- `docs/data/analysis/hgb_arrival_eta_fitness_20260808/`
- 지표: PR-AUC / negative recall / Brier (accuracy 금지)
- `eta_is_proxy` 학습 입력 금지 · ETA family는 horizon|tmap_eta|haversine 택1

```
DA① | HGB arrival-ETA fitness | 20260808
```
