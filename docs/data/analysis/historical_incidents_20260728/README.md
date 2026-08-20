# 과거 돌발 이력 분석 (20260728)

이 폴더는 공공데이터포털에서 다운로드한 2025년 대구 과거 교통 돌발상황정보의 분석 결과입니다.
원본 CSV: `C:/Users/PC/Downloads/대구광역시_교통 돌발상황정보_20250430 (1).csv`

- **표준화**: CP949 인코딩 해결 및 좌표 정상 건 필터링 (`historical_incidents_standardized.csv`)
- **유형 분류**: 사고, 공사, 행사, 통제, 기타로 분류 (`incident_types.png`)
- **공간 결합**: D1 충전소 목록 기준 반경 1km 이내에 발생했던 과거 돌발 횟수 집계 (`historical_incident_exposure.csv`)

> **주의**: 이 파일의 `historical_incident_exposure_1km` 값은 모델링/탐색용 보조 데이터이며, 실시간 추천의 `nearest_incident_m`를 절대 덮어쓰지 않습니다.

## 요약

```json
{
  "source_file": "C:\\Users\\PC\\Downloads\\대구광역시_교통 돌발상황정보_20250430 (1).csv",
  "total_incidents_raw": 1213,
  "valid_incidents": 1213,
  "total_stations_evaluated": 4210,
  "stations_with_exposure": 3784,
  "max_exposure_count": 68,
  "types": {
    "공사": 720,
    "사고": 493
  }
}
```
