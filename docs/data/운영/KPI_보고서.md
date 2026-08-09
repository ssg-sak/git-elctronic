# DA➀ KPI 보고서

<!-- DA1_DONE_BANNER_20260809 -->
> **✅ DA① 완료 (2026-08-09)** · 상태: **DA1_READY_FOR_DA2_MODEL_EVALUATION**  
> 상세: [데이터파트_①_완료상태_20260809.md](../../데이터파트_①_완료상태_20260809.md)


| | |
|---|---|
| **생성** | 2026-08-09T13:52:33.064321+09:00 |
| **기준일** | 2026-08-09 |
| **정의 정본** | [`KPI.md`](./KPI.md) |
| **갱신** | `python apps/data-pipeline/processing/analysis/report_kpi.py` |

> 이 파일은 **스크립트가 덮어쓴다**. 수동 메모는 [`KPI.md`](./KPI.md) §6 기준선에 남긴다.

---

## 1. 판정 요약

| ID | KPI | 현재 값 | 목표 | 상태 |
|---|---|---|---|---|
| K1 | status 루프 연속성 | 틱 44 · median 10.0분 · gap>12=1 | ≈5분 · gap≤2 | **OK** |
| K2 | EvCharger 일일 호출 | 178 / 1000 | ≤800 | **OK** |
| K3 | UTIC 돌발 루프 | 오늘 0회 · age=2901.0분 · 대구 22건 | ≈15분 · 최근 1시간 내 성공 | **FAIL** |
| K4 | UTIC 조인 커버 | 942/4201 (rate=0.2242) | matched > 0 | **OK** |
| K5 | D1 관측 가용률 | 0.738 | 추세 보고용 (단정 금지) | **OK** |
| K6 | 확정 가용 소 비율 | 81.5% (3430/4210) | ≥50% | **OK** |
| K7 | 미관측률 | 0.186 | ≤0.5 | **OK** |
| K8 | D1 신선도 | 2026-08-09T07:23:21+09:00 (age=6.49h) | 당일·최근 (핸드오프 전 재빌드) | **WARN** |
| K9 | mock 혼입 | traffic=utic/mock=False · parking=team5_pis | traffic 실 · 주차 mock거리 미투입 | **WARN** |
| K10 | 일일 점검 health | status_daily/ 참고 (자동 판정은 루프 체크포인트) | healthy 또는 사유 기록 | **OK** |
| K11 | D1 미관측 충전소 비율 | 13.2% (554) | 추세 모니터링 | **OK** |
| K12 | info 일별 statId 증감 | dump=2026-08-09 · statId=4224 · +0/-2 · gap=0d | 일일 덤프 + diff 기록 | **OK** |

**OK 9/12**

---

## 2. 운영 상세

### Status (K1·K2)

- 당일 틱: **44**
- 구간: 2026-08-09 00:08:50 ~ 2026-08-09 07:23:21
- 간격 median/max: 10.0 / 14.12 분
- gap>12분: 1
- API 호출: **178 / 1000** (quota date=2026-08-09)
- 최신 스냅샷: `daegu_charger_status_20260809_072321.csv` · 행 393 · period 가용 84.7%

> period 가용%는 변경분만 분모 — 대구 전체 가용률로 말하지 말 것.

### UTIC (K3·K4)

- 당일 추출: **0**
- 최신 fetched_at: 2026-08-07T13:31:33.291496+09:00 (age 2901.0분)
- 대구/전국: 22 / 149
- 조인: 942 / 4201 (rate=0.2242)

---

## 3. D1 품질 (K5–K9)

- as_of: `2026-08-09T07:23:21+09:00` (age 6.49h)
- 행: 4210
- 관측 가용률 mean: **0.738**
- 미관측률 mean: **0.186**
- 확정 가용: **81.5%** (3430/4210)
- traffic: source=`utic` mock=`False`
- parking: source=`team5_pis` mock=`False`
- reliability: `{'CHECK_REQUIRED': 3769, 'HIGH': 287, 'NORMAL': 154}`

### 공용 후보만 (recommend_public_default)

> 일반 사용자 추천은 **이쪽 숫자**를 본다. 전체와 섞지 말 것.

- 공용 / 제한: **1853** / 2357 (전체 4210)
- 공용 관측 가용률 mean: **0.852**
- 공용 미관측률 mean: **0.181**
- 공용 확정 가용: **81.2%** (1504/1853)
- 공용 소 usage_level: `{'많음': 72, '보통': 66, '적음': 54}`
- 이용강도 커버: 전체 200 · 공용 192

---

## 4. 이용강도 피처 (보조)

- 조인: **201/219** (rate=0.9178, 80.0m)
- 기간: 2024-10-18 ~ 2026-03-31
- 피처 행: 230 · D1 merge=True
- 파일: `docs/data/spatial_join/join_usage_history_statId.csv` · `station_history_features_latest.csv`

---

## 5. 커버리지 (K11·K12)

- 일일 info 덤프: `docs/data/extracted/daily/2026-08-09/daegu_charger_info_20260809_latest.csv` (export_date=2026-08-09)
- info 행/statId: 25484 / 4224
- K12 diff: +0 / -2 (vs `docs/data/extracted/daily/2026-08-08/daegu_charger_info_20260808_latest.csv`)
- 덤프 공백(일): 0
- D1 UNOBSERVED: 13.2% (554)

> 덤프 조건 고정: `dump_daily_charger_info.py` · zcode=27 · numOfRows=999

---

## 6. 다음 액션

- 루프 OFF 전이면 저녁에 한 번 더 `report_kpi.py` 실행
- K8 WARN이면 D1 재빌드 후 재실행
- K3 FAIL이면 UTIC 키/IP 확인 (학원 vs 집)
- K12 FAIL이면 `dump_daily_charger_info.py` 실행 (일일 쿼터 주의)
- 기준선 한 줄은 [`KPI.md`](./KPI.md) §6에 수동 추가

```
DA➀ | KPI report | 2026-08-09
```
