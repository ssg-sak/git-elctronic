# 도시 혼잡 시계열 (loop3)

| | |
|---|---|
| **생성** | 2026-08-07T16:20:40+09:00 |
| **틱** | 1472 |
| **구간** | 2026-07-22 16:47:00 ~ 2026-08-07 13:13:00 |
| **의미** | 대구 도로 링크(~1960)의 **원활/지체/정체** 비율 · 평균 속도 |
| **안 하는 것** | 충전소별 조인 · ETA 대체 |

## 그림

| 파일 | 한 줄 |
|---|---|
| `figures/01_congestion_timeseries.png` | 틱별 원활·혼잡·속도 |
| `figures/02_hourly_congestion_profile.png` | 0~23시 혼잡 구성 |
| `figures/03_hourly_vs_availability.png` | (있으면) 가용률과 나란히 |

## ②·BE에게

- 피처 후보: 시간대 `pct_congested` / `speed_mean` (도시 맥락)
- ETA 정본은 **TMAP**. 이건 보조·설명용.

```
DA① | city congestion | 20260807
```
