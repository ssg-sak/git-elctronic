# DA➀ KPI 보고서

| | |
|---|---|
| **생성** | 2026-07-23T14:53:05.064659+09:00 |
| **기준일** | 2026-07-23 |
| **정의 정본** | [`KPI.md`](./KPI.md) |
| **갱신** | `python apps/data-pipeline/processing/analysis/report_kpi.py` |

> 이 파일은 **스크립트가 덮어쓴다**. 수동 메모는 [`KPI.md`](./KPI.md) §6 기준선에 남긴다.

---

## 1. 판정 요약

| ID | KPI | 현재 값 | 목표 | 상태 |
|---|---|---|---|---|
| K1 | status 루프 연속성 | 틱 0 · median None분 · gap>12=0 | ≈5분 · gap≤2 | **FAIL** |
| K2 | EvCharger 일일 호출 | 360 / 1000 | ≤800 | **OK** |
| K3 | UTIC 돌발 루프 | 오늘 0회 · age=1270.2분 · 대구 6건 | ≈15분 · 최근 1시간 내 성공 | **FAIL** |
| K4 | UTIC 조인 커버 | 435/4199 (rate=0.1036) | matched > 0 | **OK** |
| K5 | D1 관측 가용률 | 0.633 | 추세 보고용 (단정 금지) | **OK** |
| K6 | 확정 가용 소 비율 | 69.6% (2930/4208) | ≥50% | **OK** |
| K7 | 미관측률 | 0.341 | ≤0.5 | **OK** |
| K8 | D1 신선도 | 2026-07-22T13:36:33.147311+09:00 (age=25.28h) | 당일·최근 (핸드오프 전 재빌드) | **WARN** |
| K9 | mock 혼입 | traffic=utic/mock=False · parking=none | traffic 실 · 주차 mock거리 미투입 | **OK** |
| K10 | 일일 점검 health | status_daily/ 참고 (자동 판정은 루프 체크포인트) | healthy 또는 사유 기록 | **WARN** |

**OK 6/10**

---

## 2. 운영 상세

### Status (K1·K2)

- 당일 틱: **0**
- 구간: None ~ None
- 간격 median/max: None / None 분
- gap>12분: 0
- API 호출: **360 / 1000** (quota date=2026-07-22)
- 최신 스냅샷: `None` · 행 None · period 가용 None%

> period 가용%는 변경분만 분모 — 대구 전체 가용률로 말하지 말 것.

### UTIC (K3·K4)

- 당일 추출: **0**
- 최신 fetched_at: 2026-07-22T17:42:50.020456+09:00 (age 1270.2분)
- 대구/전국: 6 / 83
- 조인: 435 / 4199 (rate=0.1036)

---

## 3. D1 품질 (K5–K9)

- as_of: `2026-07-22T13:36:33.147311+09:00` (age 25.28h)
- 행: 4208
- 관측 가용률 mean: **0.633**
- 미관측률 mean: **0.341**
- 확정 가용: **69.6%** (2930/4208)
- traffic: source=`utic` mock=`False`
- parking: source=`none` mock=`True`
- reliability: `{'CHECK_REQUIRED': 3892, 'NORMAL': 316}`

### 공용 후보만 (recommend_public_default)

> 일반 사용자 추천은 **이쪽 숫자**를 본다. 전체와 섞지 말 것.

- 공용 / 제한: **1854** / 2354 (전체 4208)
- 공용 관측 가용률 mean: **0.699**
- 공용 미관측률 mean: **0.326**
- 공용 확정 가용: **65.4%** (1213/1854)
- 공용 소 usage_level: `{'많음': 72, '보통': 66, '적음': 54}`
- 이용강도 커버: 전체 200 · 공용 192

---

## 4. 이용강도 피처 (보조)

- 조인: **201/219** (rate=0.9178, 80.0m)
- 기간: 2024-10-18 ~ 2026-03-31
- 피처 행: 230 · D1 merge=True
- 파일: `docs/data/spatial_join/join_usage_history_statId.csv` · `station_history_features_latest.csv`

---

## 5. 다음 액션

- 루프 OFF 전이면 저녁에 한 번 더 `report_kpi.py` 실행
- K8 WARN이면 D1 재빌드 후 재실행
- K3 FAIL이면 UTIC 키/IP 확인 (학원 vs 집)
- 기준선 한 줄은 [`KPI.md`](./KPI.md) §6에 수동 추가

```
DA➀ | KPI report | 2026-07-23
```
