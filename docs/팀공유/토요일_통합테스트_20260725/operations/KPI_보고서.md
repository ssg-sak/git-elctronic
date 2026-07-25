# DA➀ KPI 보고서

| | |
|---|---|
| **생성** | 2026-07-25T17:10:04.021458+09:00 |
| **기준일** | 2026-07-25 |
| **정의 정본** | [`KPI.md`](./KPI.md) |
| **갱신** | `python apps/data-pipeline/processing/analysis/report_kpi.py` |

> 이 파일은 **스크립트가 덮어쓴다**. 수동 메모는 [`KPI.md`](./KPI.md) §6 기준선에 남긴다.

---

## 1. 판정 요약

| ID | KPI | 현재 값 | 목표 | 상태 |
|---|---|---|---|---|
| K1 | status 루프 연속성 | 틱 96 · median 0.68분 · gap>12=0 | ≈5분 · gap≤2 | **OK** |
| K2 | EvCharger 일일 호출 | 556 / 1000 | ≤800 | **OK** |
| K3 | UTIC 돌발 루프 | 오늘 2회 · age=43.2분 · 대구 6건 | ≈15분 · 최근 1시간 내 성공 | **OK** |
| K4 | UTIC 조인 커버 | 266/4201 (rate=0.0633) | matched > 0 | **OK** |
| K5 | D1 관측 가용률 | 0.693 | 추세 보고용 (단정 금지) | **OK** |
| K6 | 확정 가용 소 비율 | 75.5% (3180/4210) | ≥50% | **OK** |
| K7 | 미관측률 | 0.267 | ≤0.5 | **OK** |
| K8 | D1 신선도 | 2026-07-25T15:15:36.262723+09:00 (age=1.91h) | 당일·최근 (핸드오프 전 재빌드) | **OK** |
| K9 | mock 혼입 | traffic=utic/mock=False · parking=team5_pis | traffic 실 · 주차 mock거리 미투입 | **WARN** |
| K10 | 일일 점검 health | status_daily/ 참고 (자동 판정은 루프 체크포인트) | healthy 또는 사유 기록 | **OK** |

**OK 9/10**

---

## 2. 운영 상세

### Status (K1·K2)

- 당일 틱: **96**
- 구간: 2026-07-25 07:49:07 ~ 2026-07-25 15:13:38
- 간격 median/max: 0.68 / 11.42 분
- gap>12분: 0
- API 호출: **556 / 1000** (quota date=2026-07-25)
- 최신 스냅샷: `daegu_charger_status_20260725_151338.csv` · 행 499 · period 가용 63.3%

> period 가용%는 변경분만 분모 — 대구 전체 가용률로 말하지 말 것.

### UTIC (K3·K4)

- 당일 추출: **2**
- 최신 fetched_at: 2026-07-25T16:26:49.365803+09:00 (age 43.2분)
- 대구/전국: 6 / 115
- 조인: 266 / 4201 (rate=0.0633)

---

## 3. D1 품질 (K5–K9)

- as_of: `2026-07-25T15:15:36.262723+09:00` (age 1.91h)
- 행: 4210
- 관측 가용률 mean: **0.693**
- 미관측률 mean: **0.267**
- 확정 가용: **75.5%** (3180/4210)
- traffic: source=`utic` mock=`False`
- parking: source=`team5_pis` mock=`False`
- reliability: `{'CHECK_REQUIRED': 3640, 'HIGH': 426, 'NORMAL': 144}`

### 공용 후보만 (recommend_public_default)

> 일반 사용자 추천은 **이쪽 숫자**를 본다. 전체와 섞지 말 것.

- 공용 / 제한: **1853** / 2357 (전체 4210)
- 공용 관측 가용률 mean: **0.744**
- 공용 미관측률 mean: **0.265**
- 공용 확정 가용: **71.8%** (1330/1853)
- 공용 소 usage_level: `{'많음': 72, '보통': 66, '적음': 54}`
- 이용강도 커버: 전체 200 · 공용 192

---

## 4. 이용강도 피처 (보조)

- 조인: **201/219** (rate=0.9178, 80.0m)
- 기간: 2024-10-18 ~ 2026-03-31
- 피처 행: 230 · D1 merge=False
- 파일: `docs/data/spatial_join/join_usage_history_statId.csv` · `station_history_features_latest.csv`

---

## 5. 다음 액션

- 루프 OFF 전이면 저녁에 한 번 더 `report_kpi.py` 실행
- K8 WARN이면 D1 재빌드 후 재실행
- K3 FAIL이면 UTIC 키/IP 확인 (학원 vs 집)
- 기준선 한 줄은 [`KPI.md`](./KPI.md) §6에 수동 추가

```
DA➀ | KPI report | 2026-07-25
```
