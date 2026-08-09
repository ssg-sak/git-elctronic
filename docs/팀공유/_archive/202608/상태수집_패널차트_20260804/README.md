# 상태 수집 · 패널/편향 차트 (20260804)

**출처:** SANDBOX_20260717 
eports/ (오늘 재생성)  
**데이터:** loop1 status 스냅샷 누적 (~2247틱, last≈2026-08-04 08:47)

## 한 줄

관측행 평균은 바쁜 충전기를 과대평가한다.  
**패널 재구성(forward-fill)** 이 권장 집계.

## 그림

| 파일 | 내용 |
|---|---|
| chart_bias_comparison.png | 집계 방식 3종 비교 (권장=패널) |
| chart_availability_panel.png | 시간대별 가용률 (편향 제거) |
| chart_day_comparison_panel.png | 일자×시간대 (패널) |
| chart_day_comparison.png | 일자 비교 (참고) |
| chart_hourly_availability.png | 시간대 가용 |
| chart_collection_volume.png | 수집량 |
| chart_observation_histogram.png | 관측 횟수 분포 |
| chart_status_by_hour.png | 상태×시간 |
| chart_coverage_map.png | 커버리지 맵 |
| chart_reliability.png | 신뢰도 |
| dashboard_status_collection.png | 대시보드 |
| status_data_value_20260718.png | 데이터 가치 요약 (파일명 레거시, 내용 최신) |

## 재실행

`ash
# PYTHONPATH=.../SANDBOX_.../src
python .../plot_corrected_charts.py
python .../plot_extra_charts.py
python .../plot_advanced_charts.py
python .../plot_data_value.py
`

`
DA① | status panel charts share | 20260804
`
