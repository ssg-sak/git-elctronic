# 시간대별 충전 가용률 — 2026-07-29 갱신

AWS Lightsail에서 pull한 loop1 충전 상태 스냅샷을 기준으로 다시 만든 팀 공유 자료입니다.

| 항목 | 값 |
|---|---:|
| 상태 스냅샷 | 1,382개 |
| 관측 기간 | 2026-07-17 ~ 2026-07-29 |
| 관측 행 | 651,476건 |
| 고유 충전소 | 3,624개 |
| 고유 충전기 | 19,647개 |
| 패널 기준 평균 가용률 | 63.5% |
| 상태 갱신 경과 중앙값 / p95 | 4.40분 / 9.15분 |
| 25분 초과 수집 공백 | 11건 |

## 바로 볼 그림

- `figures/08_hourly_union_profile.png`: 전체 시간대별 가용률
- `figures/09_hourly_public_vs_residential.png`: 공용·주거 유형 비교
- `figures/01_availability_timeseries.png`: 시간 흐름에 따른 가용률
- `figures/05_reliability_grades.png`: 상태 갱신 신뢰도 등급

## 해석 주의

- 가용률은 관측된 충전기 상태 기준이며, 상태 미확인을 사용 불가로 간주하지 않습니다.
- 패널 가용률은 짧은 수집 공백을 보정한 값입니다.
- 25분 초과 공백 11건은 시간대 패턴 해석 시 함께 확인해야 합니다.

## 데이터

- `data/availability_by_hour_union.csv`
- `data/availability_by_hour_public_vs_residential.csv`
- `data/availability_tod.csv`
- `data/reliability_checks.json`

`DA➀ | hourly availability team share | 20260729`
