# DA➀ 역할 정의 · 할 일 (요구사항 정의서 기준)

| | |
|---|---|
| **대상** | AI·데이터 ① (데이터·파이프라인) — 이현석 |
| **근거** | [`대구_EV_세이프차지_종합_요구사항_정의서_v1.0.md`](./대구_EV_세이프차지_종합_요구사항_정의서_v1.0.md) |
| **작성** | 2026-07-22 · **갱신** 2026-08-04 |
| **한 줄** | **추천 점수는 안 만든다.** 점수에 넣을 **깨끗한 재료(수집·전처리·피처·이력)** 를 만든다. |
| **로드맵** | [`../데이터파트_①_8월9일까지_로드맵.md`](../데이터파트_①_8월9일까지_로드맵.md) · 8/4 mid-cut까지 ✅ |

> 팀 공통: 루트 [`AGENTS.md`](../../AGENTS.md) · 데이터 가이드 [`데이터파트_작업가이드.md`](../데이터파트_작업가이드.md)  
> 요약본: [`요구사항_정리_전체_및_DA➀.md`](./요구사항_정리_전체_및_DA➀.md) · KPI: [`../data/KPI.md`](../data/운영/KPI.md)  
> **소통:** [`DA➀_소통_공유_설명서.md`](./DA➀_소통_공유_설명서.md)

---

## 1. 서비스에서 ①이 맡는 문장

요구사항 핵심 질문:

> “도착했을 때 충전할 가능성이 높은 충전소는?”

| 역할 | 담당 | ①인가? |
|---|---|:---:|
| 상태·돌발·날씨·주차 재료를 **모으고 정리** | DA➀ (+수집) | ✅ |
| 결측·중복·좌표·목/실 구분 | DA➀ | ✅ |
| 가용률·최신성·대수·돌발거리 등 **피처** | DA➀ | ✅ |
| 상태 **이력**(5~10분) 쌓기 · D1/D2 | DA➀ | ✅ |
| ETA·경로 API | 백엔드 | ❌ |
| 규칙 점수·실패위험·추천 이유 | **DA➁** | ❌ |
| 지도·카드 UI | 프론트 | ❌ |
| 추천 API 조립 | 백엔드 | ❌ |

요구사항 표의 「AI·데이터 담당」은 ①+②를 합친 표현이다.  
**① = COM-08 전처리 · COM-09 특성(점수 제외) · COM-16 이력 · 관련 DR/IFR**  
**② = COM-10~12 점수·위험·추천 · AIR-001/005**

---

## 2. 요구사항 ID ↔ ① 책임

### 2.1 직접 한다 (Must)

| ID | 요구 한 줄 | ①이 할 일 | 현재 |
|---|---|---|---|
| **DR-001** | 충전소·충전기 분리 | master / D1 grain=`statId` | ✅ |
| **DR-002** | 상태 이력 5~10분 | status 루프 **5분** · snapshots · D2 | ✅ 가동 |
| **DR-003** | 결측 정책 (상태≠0대체) | 미관측≠비가용 · 문서·코드 | ✅ |
| **DR-004** | 중복 제거 | 로더·POI dedup | ✅ |
| **DR-005** | 좌표·대구 범위 검증 | quarantine · `coord_ok` | ✅ |
| **DR-006** | 최신성→신뢰도 재료 | `status_age` · `reliability_grade*` | ✅ |
| **DR-007** | 목/실 구분 | `*_is_mock` · 트랙 문서 | ✅ |
| **IFR-001** | EvCharger 연동 | SANDBOX 수집 (공식 collection과 경계) | ✅ |
| **IFR-002** | 교통 | **돌발 UTIC** · 소통은 미완/대체 | 돌발 ✅ |
| **IFR-003** | 주차 연결 | Team5 실조인 · `PARKING_AUXILIARY_ONLY` (점수 금지) | ✅ |
| **IFR-004** | Tour·산책 통합 | 추출·조인·중복 제거 | ✅ |
| **NFR-006** | API 키 보호 | `.env`만 · 커밋 금지 | ✅ |
| **BR-004** 지원 | 데이터 투명성 | mock 플래그를 D1에 실어 ②·화면에 넘김 | ✅ |

### 2.2 입력만 만든다 (구현은 남)

| ID | 내용 | ① | 담당 |
|---|---|---|---|
| AIR-001 | 규칙 점수 | D1/D2 컬럼 제공 | ② |
| AIR-005 | 추천 이유 | 피처·플래그로 설명 가능하게 | ② |
| FR-006 | ETA | `eta_minutes` 자리만 | 백엔드 |
| FR-013~014 | 순위·위험도 | 피처만 | ② |
| FR-004~005 | 상태·최신성 **표시** | 표준코드·경과분 제공 | FE |
| AIR-002~004,006 | ML·라벨·평가 | 이력·라벨 재료 (향후) | ② 주 · ① 보조 |

### 2.3 안 한다 (명시)

- 추천 점수 가중합 · Top-N 정렬 · 실패위험 등급 임계값 확정  
- 지도·비교 UI · 길찾기  
- 공식 `collection/` 덮어쓰기 · `docs/data/extracted/` 무단 삭제  
- 예약·결제·전국 확장  

---

## 3. 세부 목표(§1.3) ↔ ① 할 일

| # | 요구사항 세부 목표 | ① 액션 |
|---|---|---|
| 1 | 실시간 상태·갱신시각 수집 | status 루프 유지 · 일일 KPI(K1·K2) |
| 2 | 교통 반영 ETA | 돌발 거리 피처 · ETA 값은 백엔드 |
| 3 | 대수·가용·고장·점검 분석 | D1 counts · 상태 표준화 · EDA |
| 4 | 주차 혼잡·진입 | mock 표시 유지 · KOTSA 실조인 대기 |
| 5 | 날씨·시간대 수요 | 날씨 추출·격자 · D2 시간대 EDA |
| 6 | 실패위험·추천 이유 | **피처만** → ② |
| 7 | 관광·산책 안내 | 조인 CSV·거리 피처 |
| 8 | ML용 상태 이력 | 루프 계속 · D2 패널 · (향후) D3 라벨 |

---

## 4. 데이터(§8) — ① 작업 체크

| 데이터 | MVP | ① 할 일 | 상태 |
|---|---|---|---|
| 충전소 기본정보 | 사용 | 단발 추출·마스터·대구 필터 | ✅ |
| 충전기 상태 | 5~10분 | **루프 상시** · 이력 누적 | ✅ |
| 교통 소통 | 사용 | linkspeed 루프·D1 조인 (경로 ETA 대체 금지) | ✅ |
| 돌발 | 사용 | UTIC 15분 루프 · 1km 조인 | ✅ |
| 주차 기본 | 사용 | Team5 PIS 1km 조인 · realtime≈428 | ✅ |
| 주차 혼잡 | 보조만 | 점수 금지 · realtime 한계 문서화 | ✅ |
| 날씨 | **중단** | 2026-07-22 팀 합의 — 미수집·D1 미포함 |
| Tour·관광·산책 | 사용 | 통합·중복 제거 | ✅ |
| (추가) 대구시 이용현황 CSV | 권장 | 조인·D1 `usage_level` · **HOLD_SPARSE** | ✅ |

---

## 5. 파생변수(§8.1) — ①이 채울 것

| 변수 | ① 산출 | 비고 |
|---|---|---|
| available_charger_count | `available_count` | ✅ |
| total_charger_count | `total_chargers` | ✅ |
| available_ratio | `availability_ratio_observed` | ✅ 분모 주의 |
| status_age_minutes | `status_age_minutes` + observation_* | ✅ |
| data_reliability_score | `reliability_grade*` | ✅ 재료 |
| operation_available | `is_operating_now` | ✅ |
| incident_* | `nearest_incident_m` · UTIC | ✅ |
| parking_* | `nearest_parking_m` · team5_pis · `parking_is_mock=false` | ✅ |
| weather_risk | 격자 조인 수준 | 부분 (미사용 합의) |
| historical_availability | usage 피처 · HOLD_SPARSE (MVP 제외) | ✅ 평가완료 |
| eta_minutes | 컬럼만 | 백엔드 채움 |
| charger_type_match | 규격 필드 정리 | FE 필터와 합의 |

**점수 가중치:** 요구사항 §9.1과 `AGENTS.md`가 다름 → **②·팀 합의**. ①은 입력 스키마만 안정 유지.

---

## 6. 지금 할 일 (우선순위)

### P0 — 매일 (운영)

1. status 루프(10분) · UTIC 루프(15분) 가동 유지  
2. [`KPI.md`](../data/운영/KPI.md) K1~K4 확인 · 수치는 [`KPI_보고서.md`](../data/운영/KPI_보고서.md) (`report_kpi.py`)  
3. 키·IP: 학원/집 UTIC 키 혼동 금지 · `.env`만  

### P1 — 이번 주

| # | 할 일 | 요구 | 산출 | 상태 |
|---|---|---|---|---|
| 1 | D1 **주기 재빌드** (루프 반영) | DR-002 · 핸드오프 | `station_feature_snapshot_latest` | ✅ 일일 |
| 2 | team_5 주차 export → 1km 조인 → D1 | IFR-003 · DR-007 | `parking_is_mock=false` | ✅ |
| 3 | 대구시 **이용현황 CSV** 입고 · 좌표→`statId` 조인 | historical | `station_history_features_latest` · D1 merge | ✅ HOLD_SPARSE |
| 4 | ②에게 D1·학습·replay 핸드오프 | AIR-001 입력 | `팀공유_핸드오프_①to②_20260804.md` | ✅ 2026-08-04 |
| 5 | 도착 replay 10/15/30 mid | 로드맵 8/4 | `arrival_availability_replay_20260804` | ✅ |
| 6 | 품질 모니터·pytest 게이트 | 로드맵 8/5 | monitor PASS · 65 passed | ✅ 선실행 |

### P2 — 여유 시 / 8/9 전

| # | 할 일 | 요구 |
|---|---|---|
| 7 | 저녁·최종 mid 패키지 zip (조장 모델 테스트) | 로드맵 8/6 ✅ 20260806 |
| 8 | 이상 징후(이용 급감) × 상태코드 교차 EDA | 품질 |
| 9 | 행정동 인프라 압력 (발표용) | 확장 분석 |
| 10 | 8/9 최종 `DA1_READY_FOR_DA2_MODEL_EVALUATION` | 로드맵 최종 |

### 하지 말 것 (시간 낭비)

- 처음부터 LightGBM “도착 시 가용” 모델  
- 요청마다 이용현황 12만 행 스캔  
- 과거 이용으로 실시간 상태 덮어쓰기  
- 점수 가중치를 ①이 임의 확정  

---

## 7. 산출물 위치 (어디에 두면 끝인가)

| 산출 | 경로 |
|---|---|
| status 이력 | `.../SANDBOX_20260717_.../data/snapshots/` |
| UTIC 돌발 | `docs/data/loops/utic/` |
| 단발 추출·목 | `docs/data/extracted/` |
| D1/D2 | `apps/data-pipeline/evaluation/results/datasets/` |
| 일일 점검 | `.../evaluation/results/status_daily/` |
| 피처 설명 | `docs/data/스키마/피처_카탈로그.md` · `데이터셋_명세.md` |
| ② 넘기기 | `docs/팀공유/팀공유_핸드오프_①to②_*.md` |

---

## 8. 완료 판정 (① MVP)

요구사항 관점에서 ①이 “됐다”고 말할 조건:

- [x] DR-001~007 핵심 정책·코드·문서  
- [x] 상태 이력 루프 가동 (DR-002)  
- [x] 돌발 실데이터 조인 (IFR-002 일부)  
- [x] D1/D2 + mock 구분으로 ② 핸드오프 가능  
- [x] 주차 Team5 실조인 + 점수 금지 계약 (`PARKING_AUXILIARY_ONLY`)  
- [x] D1 `as_of` 핸드오프 신선 (일일 갱신 · 2026-08-04 mid)  
- [x] 과거 이용강도 피처 + D1 merge · MVP는 HOLD_SPARSE  
- [x] horizon 학습·도착 replay mid · 품질 모니터 PASS  

점수·화면·ETA 숫자는 **① 완료 조건이 아님**.  
8/9 최종 패키지 선언은 로드맵 최종일 작업.

---

## 9. 한 장 요약

```text
① = 재료 공장
    모은다 → 깨끗이 한다 → 피처·이력으로 쌓는다 → ②·백엔드에 넘긴다

② = 점수·위험·이유
백엔드 = ETA·추천 API
프론트 = 지도·카드
수집 = 공식 collection 스케줄 (① SANDBOX와 분리)
```

```
DA➀ | role & todo from SRS v1.0 | 2026-08-04 mid-cut
```
