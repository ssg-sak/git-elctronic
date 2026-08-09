# EV SafeCharge 시각화 팩 (통합 · 20260806)

| 항목 | 내용 |
|---|---|
| **작성** | AI·데이터 ① |
| **생성** | 2026-08-06T20:48:38+09:00 |
| **용도** | 팀·조장 공유용 그림 모음 (점수/모델 아님) |

## 보는 순서

1. `01_시간대_가용률` — 패널 가용률·히트맵·공용/주거
2. `02_D1_최신화의미` — 공용/제한·주차·돌발 커버
3. `03_도시혼잡` — 소통 혼잡 시계열
4. `04_돌발_UTIC` — 돌발 건수·조인
5. `05_주차장_유료무료` — Team5 유료/무료
6. `06_피처적합도` — target_available 변별력
7. `07_daily_checkpoint` — 당일 수집 health
8. `08_상태수집_패널차트` — 편향/패널·관측분포·데이터가치 공식 차트
9. `00_가이드` — 핸드오프·계약 문서

## 폴더별 파일

### 00_가이드

- `README.md`
- `주차_realtime_428_한계_20260803.md`

### 01_시간대_가용률

- `01_availability_timeseries.png`
- `02_gap_distribution.png`
- `03_by_date.png`
- `04_hourly_heatmap.png`
- `05_reliability_grades.png`
- `06_reliability_by_day.png`
- `07_coverage_map.png`
- `08_hourly_union_profile.png`
- `09_hourly_public_vs_residential.png`

### 02_D1_최신화의미

- `01_public_vs_restricted.png`
- `02_public_availability.png`
- `03_usage_level.png`
- `04_parking_incident_coverage.png`

### 03_도시혼잡

- `01_congestion_timeseries.png`
- `02_hourly_congestion_profile.png`
- `03_hourly_vs_availability.png`

### 04_돌발_UTIC

- `01_incident_count_by_tick.png`
- `02_type_and_roads.png`
- `03_station_join_coverage.png`
- `04_incident_map.png`

### 05_주차장_유료무료

- `01_parking_paid_free_pie.png`
- `02_parking_paid_free_bar.png`
- `03_parking_paid_free_map.png`

### 06_피처적합도

- `01_feature_directional_auc.png`

### 07_daily_checkpoint

- `daily_checkpoint.png`

### 08_상태수집_패널차트

- `chart_availability_panel.png`
- `chart_bias_comparison.png`
- `chart_collection_volume.png`
- `chart_coverage_map.png`
- `chart_day_comparison.png`
- `chart_day_comparison_panel.png`
- `chart_hourly_availability.png`
- `chart_observation_histogram.png`
- `chart_reliability.png`
- `chart_status_by_hour.png`
- `dashboard_status_collection.png`
- `status_data_value_20260718.png`

## 주의

- 가용률 차트는 **변경분·패널 정의** 기준 — 대구 전체 순간 가용률로 단정 금지
- 주차 realtime≈428 · 유료/무료는 **주차장 마스터** 기준 (~1.7천)
- 피처 AUC는 단변량 — 모델 우승자 선정 ≠ ①

```
DA① | viz pack | 20260806
```
