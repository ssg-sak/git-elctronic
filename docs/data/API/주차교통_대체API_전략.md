# 필수 — 주차·교통 대체 API (대구 원천 장애 대응)

| 항목 | 내용 |
|---|---|
| **성격** | **명령·필수**. mock만으로 주차·교통을 끝내지 않는다 |
| **작성** | 2026-07-20 · AI·데이터 ① |
| **배경** | 주차=`pis.daegu.go.kr` **AWS IP 전용(로컬 401)** · 교통=대구 ITS **7/22 복구** (linkspeed 1,960) |
| **원칙** | 원천 복구를 **기다리지 않고** 대체 API를 **반드시** 확보·연동한다. 원천은 병행 유지 |

---

## 0. 한 줄 결론

| 도메인 | 원천 (막힘) | **필수 대체 (당장 신청·연동)** | 보조 |
|---|---|---|---|
| **주차** | 대구 PIS (IP 화이트리스트) | **한국교통안전공단 주차정보 API** (`DATA_GO_KR_KEY`) | 카카오 Local `PK6`(위치만) · AWS에서 PIS 병행 |
| **교통 소통** | ~~404~~ **복구** | **대구 ITS `linkspeed`** (`DATA_GO_KR_KEY`) | UTIC 소통 URL ❌ · TMAP(ETA) |
| **교통 돌발** | UTIC ✅ · 대구 `dgincident` ✅ | D1은 UTIC 조인 중 · dgincident 전환 검토 | odcloud 이력 CSV |

---

## 1. 주차 — 필수 대체 API

### 1.1 1순위 (필수 신청) — 한국교통안전공단_주차정보 제공 API

| | |
|---|---|
| **포털** | https://www.data.go.kr/data/15099883/openapi.do |
| **기관** | 한국교통안전공단 |
| **키** | 기존 `DATA_GO_KR_KEY` (공공데이터포털) — **대구 PIS 키 불필요** |
| **IP 제한** | 포털 일반 트래픽 (개발 10,000/일). **로컬 PC에서 호출 가능** |
| **승인** | 심의승인 (개발/운영) — 신청 후 대기 필요 |
| **엔드포인트** | 서비스 `http://apis.data.go.kr/B553881/Parking` |
| | 시설: `.../Parking/PrkSttusInfo` (주소·위경도·총구획) |
| | 운영: 동 포털 상세의 운영정보 |
| | **실시간**: 동 포털 「주차장 실시간 정보 조회」 |
| **대구 활용** | 응답 주소/좌표로 **대구 필터** (`addr` 또는 lat/lng bbox) |
| **한계** | 문서상 실시간·운영 건수가 시설보다 **적을 수 있음** → `realtime_missing` 플래그 유지 |
| **스키마 매핑** | `prk_center_id`→내부 `pkltId`(또는 별도 키) · `prk_plce_entrc_la/lo`→lat/lng · 잔여면→`remaining` |

**해야 할 일 (즉시)**  
1. data.go.kr에서 위 데이터셋 **활용신청**  
2. 승인되면 `scripts/api-tests/probe-kotsa-parking.ps1` 작성·대구 bbox 샘플 추출  
3. `parking_is_mock=false`, `parking_source=kotsa` 로 D1/조인 파이프라인 연결  

### 1.2 2순위 (위치·밀도 보조) — 카카오 Local 주차장

| | |
|---|---|
| **문서** | `docs/data/API/카카오_로컬_API.md` · 카테고리 `PK6` |
| **키** | `KAKAO_REST_KEY` |
| **주는 것** | 충전소 주변 **주차장 POI** (이름·좌표·거리) |
| **안 주는 것** | 실시간 잔여면·점유율 |
| **용도** | F12 `nearest_parking_m` / `poi` 성격 보강. **혼잡 대체 아님** |
| **플래그** | `parking_occupancy_known=false` |

### 1.3 3순위 (원천 병행) — 대구 PIS on AWS

| | |
|---|---|
| **URL** | `https://pis.daegu.go.kr/api/serviceApply/prkInfo` · `rltmPrkInfo` |
| **키** | `DAEGU_PARKING_KEY` / `DAEGU_PARKING_RT_KEY` |
| **조건** | IP=`3.39.251.72` (팀 AWS)에서만 |
| **역할** | 대체 API와 **병행**. 로컬 개발의 **유일한** 주차 경로로 두지 말 것 |

### 1.4 주차 대체 — 하지 말 것

- mock CSV를 실데이터처럼 점수에 넣기  
- 실시간 없는 POI를 “만차/여유”로 추정하기  

---

## 2. 교통 — 필수 대체 API

### 2.1 1순위 (필수 신청) — 도시교통정보센터(UTIC)

| | |
|---|---|
| **신청** | https://www.utic.go.kr/guide/newUtisDataWrite.do |
| **선택 데이터** | **소통정보** + **돌발** (둘 다 체크) |
| **인증** | 발급 **key + 신청 IP** (로컬/서버 IP 등록) |
| **돌발 레퍼런스** | http://www.utic.go.kr/guide/utisRefIncident.do |
| **돌발 샘플** | `http://www.utic.go.kr/guide/imsOpenData.do?key=(인증키)` |
| **소통 레퍼런스** | http://www.utic.go.kr/guide/utisRefTraffic.do |
| **포맷** | XML (돌발) · 소통은 URL/키 방식 |
| **대구** | 전국 데이터 → **지역코드/좌표로 대구 필터** |
| **준수** | 출처 「경찰청 도시교통정보센터」 표기 필수 · 목적 외 사용 금지 |
| **팀 준수 문서** | [`UTIC_개방데이터_준수사항.md`](./UTIC_개방데이터_준수사항.md) |
| **스키마** | 돌발: id·유형·좌표·등급·시간 → `traffic_incident_*` · `traffic_is_mock=false`, `traffic_source=utic` |

**해야 할 일 (즉시)**  
1. UTIC 개방데이터 신청 (소속·이메일·**신청 IP**·목적: EV 충전 추천 연구)  
2. 승인 키 → `.env`에 `UTIC_API_KEY=` (커밋 금지)  
3. `probe-utic-incident.ps1` / 소통 프로브 → 대구 bbox CSV  
4. 공간조인·D1 `nearest_incident_m` 실데이터 경로 연결  

공공데이터포털 연계 안내:  
- 경찰청_교통돌발정보서비스 https://www.data.go.kr/data/15088841/openapi.do  
- (CCTV 등) UTIC 관련 https://www.data.go.kr/data/15148511/openapi.do  

→ **실제 키 발급 창구는 UTIC 사이트 신청**이 본체.

### 2.2 2순위 (이미 확보·즉시 파이프라인) — odcloud 보관

| 파일 (extracted) | 내용 |
|---|---|
| `daegu_traffic_incident_stats_*` | 돌발 · **좌표 O** · 이력 |
| `daegu_traffic_link_hourly_stats_*` | 링크 속도 · 좌표 없음 |
| `daegu_traffic_control_*` | 통제 |

| | |
|---|---|
| **역할** | UTIC 승인 전 **어댑터로 실스키마 연결** (realtime이 아닌 이력/통계) |
| **플래그** | `traffic_source=odcloud`, `traffic_is_realtime=false` |
| **가이드** | `evaluation/.../phase2_realdata/README.md` |

### 2.3 3순위 (이동시간) — TMAP

| | |
|---|---|
| **키** | `TMAP_APP_KEY` |
| **용도** | F09 `eta_minutes` · 경로 혼잡 반영 |
| **한계** | 표준링크 속도 테이블 **대체가 아님**. 추천 요청 시 ETA용 |

### 2.4 참고 (범위 주의)

| 소스 | 비고 |
|---|---|
| 국토부_교통소통정보 | 고속·국도 중심 → 대구 **시내 전역** 대용으로는 부족 |
| 대구 ITS 원천 | **2026-07-22 복구** · `loops/daegu_traffic/` · [`교통소통_데이터_보고.md`](../품질보고/교통소통_데이터_보고.md) |
| 경기 ITS OpenAPI | 지역 불일치 → 사용 안 함 |

---

## 3. 필수 실행 체크리스트 (①)

### 주차
- [ ] KOTSA 주차 API 활용신청 (data.go.kr/15099883)
- [ ] 승인 후 대구 필터 프로브 + CSV
- [ ] 전처리 어댑터 (`parking_source=kotsa`)
- [ ] (병행) 카카오 PK6 주변 주차 POI
- [ ] (병행) AWS에서 PIS 실수집 스케줄 — 수집 담당과 합의

### 교통
- [x] UTIC 개방데이터 신청 · 키 확보 (`UTIC_API_KEY` → `.env`, 2026-07-21)
- [x] 돌발 프로브 성공 (`scripts/api-tests/probe-utic-incident.ps1`)
- [x] 돌발 **대구 추출** (`extract_utic_incident.py` → `docs/data/loops/utic/daegu_traffic_incident_utic_latest.csv`)
- [x] D1 조인 · `traffic_is_mock=false` · `traffic_source=utic` (`join_utic_incident.py`)
- [x] 소통 **15분 루프** (`run_daegu_traffic_loop.py` → `loops/daegu_traffic/`)
- [ ] 충전소 링크 조인 (좌표 없음 → 링크맵 후속)
- [ ] UTIC 소통 URL — 후보 전부 404 (대구 linkspeed로 대체)
- [ ] **주차 mock 해제** — KOTSA 승인·카카오 키·AWS PIS 중 하나 (오늘 프로브: 401)
- [x] UTIC **주기 루프** (`run_utic_loop.py` 15분, status와 분리) — 2026-07-21 가동

문서: [`수집루프_쉬운설명.md`](../운영/수집루프_쉬운설명.md) · [`실데이터_목데이터_트랙.md`](../운영/실데이터_목데이터_트랙.md)  
- [ ] odcloud → 스키마 어댑터 (승인 전 브리지)
- [ ] D1/조인 `traffic_is_mock` 갱신 정책 문서화
- [ ] TMAP ETA는 백엔드/②와 인터페이스만 확인

### 공통
- [ ] `.env` 키만 사용 · 커밋 금지
- [ ] 소스 플래그: `parking_source` / `traffic_source` / `*_is_mock` / `*_is_realtime`
- [ ] mock CSV는 **스키마 회귀용**으로만 유지

---

## 4. 책임·경계

| 담당 | 할 일 |
|---|---|
| **① 파이프라인** | 대체 API 신청 지원·프로브·전처리·조인·플래그·문서 |
| **수집** | PIS AWS 스케줄·공식 `collection/` 이관 시 합의 |
| **②** | 점수 가중치 (대체 소스 품질을 보고 설계) |

---

## 5. 관련 문서

| 문서 | 내용 |
|---|---|
| `docs/_archive/data/API_셋업보고_20260716.md` | 원천 404·주차 IP 기록 |
| `docs/data/운영/API_연동_현황.md` | 공공 API **현재** 상태 |
| `docs/troubleshooting/2026-07-15_공공API_이슈.md` | 장애 이력 |
| `apps/data-pipeline/AGENTS.md` | 원천 엔드포인트 |
| **UTIC 준수사항** | [`UTIC_개방데이터_준수사항.md`](./UTIC_개방데이터_준수사항.md) |
| **팀 공유 (키·프로브·준수)** | [`docs/팀공유_UTIC_20260721.md`](../../팀공유/팀공유_UTIC_20260721.md) |

---

## 6. 다음에 코드로 할 일 (승인 전/후)

| 순서 | 작업 |
|---|---|
| 1 | 신청 완료 스크린/키 수령 |
| 2 | `scripts/api-tests/probe-kotsa-parking.ps1` |
| 3 | `scripts/api-tests/probe-utic-traffic.ps1` |
| 4 | odcloud 돌발 → `traffic_incident_current` 어댑터 |
| 5 | D1 `nearest_parking_m` / `nearest_incident_m` 재생성 |
