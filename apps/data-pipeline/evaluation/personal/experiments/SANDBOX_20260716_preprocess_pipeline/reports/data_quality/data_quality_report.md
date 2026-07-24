# Data Quality Report — SANDBOX_20260716_preprocess_pipeline

## 범위
- 원본: `docs/data/extracted/` (읽기 전용)
- 산출: 본 샌드박스 `data/processed/`
- 제외: `daegu_traffic_*_mock(1).csv`

## 파일별 규모
- **charger_info**: 25334 rows × 14 cols
- **charger_status**: 525 rows × 6 cols
- **city_tour**: 239 rows × 12 cols
- **parking_info**: 12 rows × 21 cols
- **parking_realtime**: 10 rows × 12 cols
- **tour_attractions**: 57 rows × 13 cols
- **traffic_incident**: 8 rows × 20 cols
- **traffic_linkspeed**: 12 rows × 17 cols
- **walk_parks**: 107 rows × 13 cols
- **weather_ultra_fcst**: 66 rows × 9 cols
- **weather_ultra_ncst**: 8 rows × 7 cols
- **weather_vilage**: 1000 rows × 9 cols

## 상태정보 수집 커버리지
- 충전기 기준: **2.0723%** (status rows=525 / info=25334)
- 충전소 기준: **9.173%**
- 해석: 변경분(`period`) 수집 → **미관측 ≠ 사용 불가**

## 좌표 이상(격리) 건수: 27
- 파일: `data/quarantine/charger_coordinate_suspects.csv`

## Tour 인코딩 복구 행수: 53

## 주차
- 기본만 있고 실시간 없음: `['MOCK-150-0-000007', 'MOCK-150-0-000010']` → UNKNOWN

## 기상
- grids: `[('89', '90')]`
- single_grid_only: **True** → 대구 전역 날씨로 해석 금지

## 목데이터
- parking_*, traffic_linkspeed_mock, traffic_incident_mock (`isMock=True` 유지)

## 조인
- statNm join restored rows (info match): 525
- tour↔city match candidates: 16

## 모델링에 바로 쓰기 어려운 것
- status 미관측 다수 → 가용률 왜곡 위험
- 단일 시점 스냅샷 → 도착시 예측 학습 부족
- city_tour 무좌표
- Tour 인코딩 이슈(복구 시도함)
- 기상 1격자

## 산출 테이블
- `charger_current_view` → `data/processed/charger_current_view.csv|.parquet`
- `charger_master` → `data/processed/charger_master.csv|.parquet`
- `charger_status_current` → `data/processed/charger_status_current.csv|.parquet`
- `parking_current` → `data/processed/parking_current.csv|.parquet`
- `poi_city_tour_attrs_long` → `data/processed/poi_city_tour_attrs_long.csv|.parquet`
- `poi_city_tour_attrs_wide` → `data/processed/poi_city_tour_attrs_wide.csv|.parquet`
- `poi_city_tour_no_coords` → `data/processed/poi_city_tour_no_coords.csv|.parquet`
- `poi_master` → `data/processed/poi_master.csv|.parquet`
- `poi_tour_city_match_candidates` → `data/processed/poi_tour_city_match_candidates.csv|.parquet`
- `tour_attractions_clean` → `data/processed/tour_attractions_clean.csv|.parquet`
- `traffic_incident_current` → `data/processed/traffic_incident_current.csv|.parquet`
- `traffic_link_current` → `data/processed/traffic_link_current.csv|.parquet`
- `walk_parks_clean` → `data/processed/walk_parks_clean.csv|.parquet`
- `weather_hourly` → `data/processed/weather_hourly.csv|.parquet`
- `weather_ultra_fcst_long` → `data/processed/weather_ultra_fcst_long.csv|.parquet`
- `weather_ultra_ncst_long` → `data/processed/weather_ultra_ncst_long.csv|.parquet`
- `weather_vilage_long` → `data/processed/weather_vilage_long.csv|.parquet`
