# EV SafeCharge — AI 모델 설계 계획서

> **소유: AI·데이터 ② (모델·평가·서빙).** ①은 EDA·특성·데이터셋 입력만 담당.

| 항목 | 내용 |
|---|---|
| 목적 | 도착 시 실제 충전 가능성이 높은 충전소 추천 |
| 담당 | AI·데이터 ② |
| 기준 문서 | `docs/_archive/eda/EDA_계획서_20260716.md`, `docs/보고/EDA_보고서.md` |
| 기준 데이터 | `SANDBOX_20260716_preprocess_pipeline/data/processed/` |
| 작성일 | 2026-07-16 |
| 핵심 전제 | 현재 데이터만으로 완전한 예측모델 학습은 불가. MVP는 규칙 기반으로 시작 |

---

## 1. 모델링 목표

서비스의 목표는 “가까움”이 아니라 **도착 시 충전 성공 가능성**이다.

최종적으로 예측하고 싶은 값:

| 타깃 | 정의 |
|---|---|
| `available_at_arrival` | 사용자가 추천을 요청한 시각 + 예상 이동시간에 해당 충전기가 사용 가능한지 |

현재는 이 타깃의 라벨이 없다. 따라서 1단계는 **규칙 기반 위험점수**, 2단계는 반복 수집 후 **지도학습 예측모델**이다.

---

## 2. 단계별 전략

| 단계 | 이름 | 목표 | 상태 |
|---|---|---|---|
| Phase 0 | 데이터 품질·EDA | 전처리·커버리지·한계 확인 | 완료 |
| Phase 1 | 규칙 기반 MVP 점수 | 현재 스냅샷으로 설명 가능한 추천 | 가능 |
| Phase 2 | 반복 수집 피처 | status/traffic/parking/weather 시계열 구축 | 필요 |
| Phase 3 | `available_at_arrival` 모델 | 도착시 사용 가능성 예측 | 라벨 확보 후 |
| Phase 4 | 랭킹 모델 | 충전소 후보 간 순위 최적화 | 서비스 로그 후 |

---

## 3. Phase 1 — 규칙 기반 MVP

### 3.1 점수 구성

팀 공통 가중치를 따른다.

| 항목 | 가중치 | 현재 사용 변수 | 데이터 성격 |
|---|---:|---|---|
| 충전 가능성 | 40% | `available_count`, `known_status_count`, `unknown_status_rate` | 실측 + 미관측 분리 |
| 상태 신뢰도 | 20% | `status_age_seconds`, `is_status_stale` | 실측 |
| 이동시간 | 15% | `estimated_travel_time` | 현재 TMAP 필요 / mock 불가 |
| 충전기 수·대기위험 | 15% | `charger_count`, `single_charger_flag`, `charging_count` | 실측/관측 |
| 주차·운영·주변편의 | 10% | `parking_occupancy_rate`, `limitYn`, `is_24h`, `poi_count_500m` | 실측 + mock |

### 3.2 핵심 원칙

1. `status_missing=True` 를 사용 불가로 처리하지 않는다.
2. `availability_rate_among_known` 과 `unknown_status_rate` 를 반드시 분리한다.
3. mock 기반 변수는 점수 계산에 넣더라도 `isMock`을 보고서와 API 응답에 남긴다.
4. 좌표 이상 27건은 추천 후보에서 제외 또는 경고 플래그로 별도 처리한다.

### 3.3 추천 점수 후보

```text
safe_charge_score =
  0.40 * availability_component
+ 0.20 * reliability_component
+ 0.15 * travel_time_component
+ 0.15 * queue_risk_component
+ 0.10 * convenience_component
```

현재 `travel_time_component`는 TMAP 실키가 들어오기 전까지 mock 또는 거리 기반 placeholder로만 실험한다. 성능을 주장하지 않는다.

---

## 4. Phase 2 — 수집 설계

예측모델을 위해 필요한 반복 수집:

| 데이터 | 주기 | 필수 컬럼 |
|---|---|---|
| 충전기 상태 | 5분 | `statId`, `chgerId`, `status`, `statusUpdatedAt`, `fetchedAt` |
| 교통 링크 | 5~10분 | `linkId`, `speedKph`, `congGrade`, `source_event_time`, `fetchedAt` |
| 돌발상황 | 5~10분 | `incidentId`, `type`, `grade`, `startDt`, `endDt`, `affectedLinkId` |
| 주차 실시간 | API 제공 주기 | `pkltId`, `remaining`, `capacity`, `fetchedAt` |
| 날씨 | 발표 주기 | `base_time`, `forecast_time`, `category`, `value` |
| 사용자 로그 | 요청마다 | request time, origin, candidates, displayed rank, selected station |
| 결과 로그 | 도착/사용 시점 | actual arrival, actual station status, success/fail |

최소 4주, 권장 8주 이상. 평일/주말/공휴일과 출퇴근·비혼잡 시간을 포함한다.

---

## 5. Phase 3 — 지도학습 모델

### 5.1 타깃 정의

| 타깃 | 정의 |
|---|---|
| `available_at_arrival` | 요청시각 + 예상 이동시간 시점에 충전기 또는 충전소가 사용 가능했는가 |

충전기 단위 타깃과 충전소 단위 타깃을 분리한다.

| 단위 | 타깃 후보 |
|---|---|
| 충전기 | 해당 `statId+chgerId` 가 도착시 AVAILABLE |
| 충전소 | 해당 `statId` 에 도착시 AVAILABLE 충전기가 1대 이상 |

### 5.2 임시 탐색 타깃

현재 스냅샷에서는 `available_now`만 탐색 가능하다.

| 값 | 처리 |
|---|---|
| 관측 AVAILABLE | 1 |
| 관측 CHARGING/MAINTENANCE/COMM_ERROR 등 | 0 |
| 상태 미수집 | NA |

상태 미수집을 0으로 넣지 않는다.

---

## 6. 피처 설계

### 6.1 충전기·충전소

| 피처 | 설명 | 현재 |
|---|---|---|
| `charger_count` | 충전소별 전체 충전기 수 | 가능 |
| `known_status_count` | 상태 관측 충전기 수 | 가능 |
| `available_count` | 관측 AVAILABLE 수 | 가능 |
| `unknown_status_rate` | 상태 미관측 비율 | 가능 |
| `status_age_seconds` | 상태 갱신 경과 | 관측분 가능 |
| `output_kw` | 출력 | 결측 flag 필요 |
| `chgerType` | 충전기 유형 | 가능 |
| `limit_yn` | 이용 제한 | 가능 |
| `is_24h` | 24시간 운영 여부 | 파생 |
| `is_service_target` | 운영 제외 여부 | 파생 |

### 6.2 교통·도착시간

| 피처 | 설명 | 현재 |
|---|---|---|
| `estimated_travel_time` | 후보까지 이동시간 | TMAP 필요 |
| `traffic_speed_kph` | 주변 링크 속도 | mock |
| `congestion_grade` | 혼잡등급 | mock |
| `active_incident_count` | 경로/반경 내 활성 돌발 | mock |
| `incident_delay_factor` | 심각도 기반 지연계수 | mock |

### 6.3 주차·편의

| 피처 | 설명 | 현재 |
|---|---|---|
| `parking_occupancy_rate` | 점유율 | mock |
| `realtime_parking_missing` | 실시간 정보 없음 | 가능 |
| `poi_count_500m` | 반경 500m POI 수 | 가능 |
| `park_count_500m` | 반경 500m 공원 수 | 가능 |
| `nearest_poi_distance_m` | 최근접 POI 거리 | 가능 |

### 6.4 날씨

| 피처 | 설명 | 현재 |
|---|---|---|
| `temperature` | TMP/T1H | 단일 격자 |
| `precipitation` | PCP/RN1 | 단일 격자 |
| `humidity` | REH | 단일 격자 |
| `wind_speed` | WSD | 단일 격자 |
| `sky_code`, `pty_code` | 범주형 날씨 | 단일 격자 |

---

## 7. 후보 알고리즘

### 7.1 Baseline

| 모델 | 이유 |
|---|---|
| 규칙 기반 weighted score | 라벨 없이 가능, 설명력 높음 |
| Logistic Regression | 첫 supervised baseline, 해석 쉬움 |
| Gradient Boosting / LightGBM | 비선형·상호작용 반영 |
| Ranking model | 서비스 로그 확보 후 후보 간 순위 최적화 |

처음부터 복잡한 딥러닝은 필요하지 않다. 데이터 수집·라벨 품질이 우선이다.

### 7.2 추천 단위

| 방식 | 장점 | 단점 |
|---|---|---|
| 충전기 단위 예측 후 충전소 집계 | 세밀함 | status 미관측이 많으면 불안정 |
| 충전소 단위 예측 | 서비스와 직접 연결 | 충전기별 상태 손실 |
| 하이브리드 | 충전기→충전소 risk aggregation | 구현 복잡 |

MVP는 충전소 단위 점수, 향후 모델은 충전기 단위 확률을 충전소 단위로 집계하는 방식을 권장한다.

---

## 8. 검증 설계

### 8.1 데이터 분할

반복 수집 후:

| split | 기준 |
|---|---|
| train | 과거 기간 |
| validation | 이후 기간 |
| test | 가장 최신 기간 |

랜덤 row split 금지. 같은 시점/같은 충전소 정보가 train/test에 동시에 들어가면 누수 가능성이 있다.

### 8.2 평가 지표

| 지표 | 이유 |
|---|---|
| ROC-AUC | 전반적 분류 성능 |
| PR-AUC | 사용 가능/불가능 불균형 대비 |
| Calibration error | 확률 추천 서비스에 중요 |
| Top-K success rate | 추천 목록 품질 |
| NDCG / MAP | 랭킹 모델 시 |
| Coverage by station/operator | 특정 기관 편향 확인 |

정확도 단독 사용 금지.

---

## 9. 데이터 누수 위험

| 위험 | 예시 | 방지 |
|---|---|---|
| 미래 상태 누수 | 도착 이후 status를 피처에 포함 | feature cutoff time 적용 |
| 추천 결과 누수 | 사용자가 선택한 후 정보가 피처에 섞임 | request 시점 스냅샷만 사용 |
| 중복 시점 누수 | 같은 fetchedAt 행이 train/test 양쪽 | 시간 기반 split |
| mock 혼입 | mock을 실데이터처럼 학습 | `isMock` 분리, production 학습 제외 |
| city_tour 지오코딩 후 누수 | 사후 수동 보정 좌표 혼입 | versioned geocoding table |

---

## 10. 품질 게이트

모델 성능평가 이전에 아래 기준을 통과해야 한다.

| 게이트 | 기준 |
|---|---|
| 원본 보존 | raw CSV 수정 없음 |
| 키 무결성 | `statId+chgerId`, `pkltId`, `linkId` 중복 보고 |
| status coverage | 반복 수집 기간·커버리지 보고 |
| label definition | `available_at_arrival` 생성 SQL/로직 문서화 |
| missing policy | 미관측을 0으로 대체하지 않음 |
| coordinate QA | 이상 좌표 격리 |
| mock handling | 실험/학습/서비스에서 mock 구분 |
| time split | 시간 기준 train/val/test |
| leakage check | feature timestamp <= prediction timestamp |
| calibration | 확률 보정 평가 |

---

## 11. mock을 실데이터로 교체할 기준

| 데이터 | 교체 기준 |
|---|---|
| 교통 링크 | 공식 API 200, `linkId/speed/congGrade/fetchedAt` 확보 |
| 돌발 | 공식 API 200, `incidentId/start/end/affectedLink` 확보 |
| 주차 | AWS에서 실시간 수집, 기본↔실시간 조인률 보고 |
| 카카오 | REST 키 반영, 주변시설 좌표·카테고리 확보 |
| TMAP | routes 호출 성공, 후보별 이동시간 확보 |

교체 후 같은 EDA·품질 보고서를 다시 실행해 mock 기반 결과와 구분한다.

---

## 12. 로드맵

| 단계 | 작업 | 산출 |
|---|---|---|
| 1 | EDA 노트북 실행 | 품질·공급·상태·공간 보고 |
| 2 | 규칙 기반 점수 프로토타입 | score breakdown API |
| 3 | status 시계열 수집 | snapshot table |
| 4 | TMAP/주차/교통 실데이터 | travel/parking/traffic feature |
| 5 | `available_at_arrival` 라벨 | supervised dataset |
| 6 | baseline 모델 | Logistic/GBM report |
| 7 | 랭킹 실험 | Top-K success |

---

## 13. 첫 번째 모델 제안

| 항목 | 제안 |
|---|---|
| 타깃 | 충전소 단위 `available_at_arrival_station` |
| 관측 단위 | 추천 요청 × 후보 충전소 |
| baseline | 규칙 점수 |
| 1차 모델 | Logistic Regression |
| 2차 모델 | LightGBM |
| 랭킹 | 점수/확률 기반 Top-K |
| 필수 피처 | status coverage, known availability, charger_count, status_age, travel_time, limitYn, parking, incident, weather |

현재 데이터로는 이 모델을 학습하지 않는다. 현재는 **데이터셋 설계와 규칙 baseline**까지만 수행한다.

```
SSG-SAK | EV SafeCharge | AI MODEL DESIGN PLAN | 2026-07-16
```
