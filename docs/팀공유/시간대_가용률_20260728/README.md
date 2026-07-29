# 시간대별 충전 가용률 — 2026-07-28 갱신

| 항목 | 값 |
|---|---:|
| 상태 스냅샷 | 1,254회 |
| 상태 행 | 592,165 |
| 관측 기간 | 2026-07-17 ~ 2026-07-28 |
| 전체 관측 가용률 평균 | 63.2% |
| 상태 갱신 경과 중앙값 / p95 | 4.40분 / 9.15분 |
| 신뢰도 검사 | 6개 중 5개 통과 |

## 바로 볼 그림

- igures/08_hourly_union_profile.png: 전체 시간대별 가용률
- igures/09_hourly_public_vs_residential.png: 공용·주거성 후보 시간대별 비교
- igures/01_availability_timeseries.png: 시간 흐름에 따른 가용률
- igures/05_reliability_grades.png: 상태 갱신 시각 기준 신뢰도 등급

## 해석

- 가용률은 **관측된 충전기 상태 기준**이다. 상태가 없다고 사용 불가로 해석하면 안 된다.
- 08~12시는 평균 가용률이 상대적으로 높게 관측됐지만, 시간대별 표본 수가 다르므로 도착 성공확률로 단정하지 않는다.
- 수집 공백 25분 초과가 11회 있어, 연속 시계열·장기 패턴 해석에는 이 구간을 함께 고려한다.
- ETA·최종 추천 점수는 이 자료에 포함하지 않는다.

## 데이터

- 시간대 평균: vailability_by_hour_union.csv
- 공용/주거성 비교: vailability_by_hour_public_vs_residential.csv
- 신뢰도 검사: 
eliability_checks.json

`	ext
DA① | hourly availability team share | 20260728
`
