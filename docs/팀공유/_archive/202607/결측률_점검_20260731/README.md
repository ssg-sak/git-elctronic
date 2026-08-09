# 결측률 점검 (20260731)

| 항목 | 내용 |
|---|---|
| **작성** | AI·데이터 ① |
| **생성** | 2026-07-31T09:02:25.172208+09:00 |
| **한 줄** | D1·요금·상태·주차·링크 등 **현재 파일** 컬럼별 빈칸 비율 |
| **팀 쉬운 보고** | [`../결측률_팀원쉬운보고_20260731.md`](../결측률_팀원쉬운보고_20260731.md) |

## 읽는 법

- **결측** = 비어 있음 또는 `nan`/`null` 문자열
- 일부는 **의도적 null**(예: `eta_minutes`) → 100%여도 버그 아님
- 주차·돌발·이력은 **원천 커버리지** 때문에 결측이 클 수 있음

## 데이터셋 요약

| 데이터셋 | 행 | 열 | 완전(0%) | 거의결측(≥90%) |
|---|---:|---:|---:|---:|
| D1_station_feature_snapshot | 4,210 | 55 | 30 | 9 |
| fee_station_operator_hint | 4,210 | 12 | 6 | 0 |
| fee_operator_tariff | 232 | 8 | 5 | 0 |
| status_latest_snap | 618 | 8 | 7 | 1 |
| parking_realtime_latest_file | 11,880 | 13 | 11 | 0 |

## D1 피처 가족별 평균 결측%

| 가족 | 컬럼수 | 평균 결측% | 최대 | 최소 |
|---|---:|---:|---:|---:|
| eta | 1 | 100.0 | 100.0 | 100.0 |
| incident | 1 | 93.18 | 93.18 | 93.18 |
| parking_1h | 3 | 89.83 | 89.83 | 89.83 |
| usage_history | 3 | 63.5 | 95.25 | 0.0 |
| parking | 5 | 55.65 | 90.1 | 1.64 |
| linkspeed | 5 | 35.49 | 35.49 | 35.49 |
| status_asof | 7 | 4.28 | 14.99 | 0.0 |
| access | 4 | 0.0 | 0.0 | 0.0 |
| identity | 6 | 0.0 | 0.0 | 0.0 |
| poi | 1 | 0.0 | 0.0 | 0.0 |

## D1 결측 많은 컬럼 TOP

| 컬럼 | 결측% | 결측수 |
|---|---:|---:|
| `eta_minutes` | 100.0 | 4,210 |
| `usage_weekend_avg` | 95.3 | 4,012 |
| `usage_weekday_avg` | 95.25 | 4,010 |
| `sessions_per_charger` | 95.25 | 4,010 |
| `usage_charger_type` | 95.25 | 4,010 |
| `usage_level` | 95.25 | 4,010 |
| `nearest_incident_m` | 93.18 | 3,923 |
| `parking_congestion_status` | 90.14 | 3,795 |
| `parking_occupancy_rate` | 90.1 | 3,793 |
| `parking_realtime_ticks_1h` | 89.83 | 3,782 |
| `parking_remaining_std_1h` | 89.83 | 3,782 |
| `parking_remaining_spaces` | 89.83 | 3,782 |
| `parking_remaining_delta_1h` | 89.83 | 3,782 |
| `parking_total_spaces` | 89.83 | 3,782 |
| `link_cong_grade` | 35.49 | 1,494 |

## 요금 힌트 핵심 컬럼

| 컬럼 | 결측% |
|---|---:|
| `statId` | 0.0 |
| `busiId` | 0.0 |
| `busiNm` | 0.0 |
| `fee_operator_nm` | 2.92 |
| `fee_match_level` | 0.0 |
| `member_won_sample` | 2.95 |
| `nonmember_won_sample` | 24.06 |
| `capacity_class_sample` | 2.92 |

## 해석 (쉬운 말)

| 높은 결측 | 의미 |
|---|---|
| `eta_minutes` ~100% | **의도적 null 예약** (BE/TMAP) |
| usage_* 높음 | 이력 원천 커버리지 낮음 |
| parking realtime / 1h | realtime 붙은 소만 값 있음 |
| incident / link | 근처 매칭 없을 때 null |
| 요금 sample | 운영사 미매칭 ~3% |

상세: `docs/data/analysis/missingness_20260731/`

```
DA① | missingness check | 20260731
```
