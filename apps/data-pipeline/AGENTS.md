# 데이터 팀 에이전트 가이드 (수집 1명 + 가공 1명)

## 담당 범위

- **데이터 수집 (1명)** — `apps/data-pipeline/collection/`: 외부 공공 API 호출, 원본(raw) 데이터 적재, 수집 스케줄링
- **데이터 가공 (1명)** — `apps/data-pipeline/processing/`: 원본 데이터 정제·정규화, 신뢰도 계산, 집계 통계 생성

수집은 "원본을 빠짐없이 모으는 것", 가공은 "백엔드가 바로 쓸 수 있는 형태로 만드는 것"이 책임이다. 두 사람의 인터페이스는 **원본 적재 포맷**이며, 변경 시 상호 합의한다.

---

## 데이터 수집 담당

### 수집 대상 API

MVP는 대구 지역 중심. 신청·연동은 1차(완료) → 2차 → 3차 순서로 진행한다.

**1차 (발급·테스트 완료)**

| API | 수집 주기 | 비고 |
|---|---|---|
| 한국환경공단 EvCharger `getChargerInfo` (충전소·충전기 정보) | 1일 1회 | 정적 정보 |
| 한국환경공단 EvCharger `getChargerStatus` (실시간 상태) | 2~5분 간격 | `period` 파라미터로 변경분만 수집 |
| TMAP 자동차 경로 안내 | 요청 시 (백엔드 실시간 호출) | 수집 대상 아님. 최종 후보 충전소에만 호출 |
| 카카오 로컬 (주변 시설) | 1일 1회 또는 요청 시 | 카페, 음식점, 편의점 등 |

**2차**

| API | 수집 주기 | 비고 |
|---|---|---|
| 기상청 단기예보 (초단기실황·초단기예보·단기예보) | 1시간 | nx/ny 격자좌표 변환 필요 (아래 참고) |
| 대구 교통소통정보(신) | 5~10분 | 도로 구간별 통행속도, 표준 노드·링크 |
| 대구 돌발 교통정보(신) | 5~10분 | 사고·공사·행사·통제, 일 5,000건 |
| 대구 주차장 기본정보 | 1일 1회 | pis.daegu.go.kr 별도 키 (아래 참고) |
| 대구 실시간 주차 혼잡도 | 2~5분 | 잔여 주차면. 최근 1시간 내 수집 정보만 제공 |

**3차**

| API | 수집 주기 | 비고 |
|---|---|---|
| 한국관광공사 TourAPI | 1일 1회 또는 요청 시 | KorService2 기준 (구버전 KorService1 예제 사용 금지) |
| 대구 산책로정보 | 1주 1회 (정적) | 공원·산책로, 난이도, 편의시설 |

### API 신청·키 발급 정보

**공공데이터포털(data.go.kr) API는 계정당 발급되는 일반 인증키 하나를 모든 활용신청 API에 공통으로 사용한다.** `.env`의 `DATA_GO_KR_KEY` 하나로 아래 승인 완료 API 전부를 호출한다. 단, API별로 활용신청(승인)은 각각 되어 있어야 하고, 일 트래픽 한도는 API별로 따로 적용된다.

| API | 신청 주소 | `.env` 키 | 상태 |
|---|---|---|---|
| 한국환경공단 충전소 (XML, 일 1,000건) | https://www.data.go.kr/data/15076352/openapi.do | `DATA_GO_KR_KEY` | 승인 완료 |
| 기상청 단기예보 (일 10,000건) | https://www.data.go.kr/data/15084084/openapi.do | `DATA_GO_KR_KEY` | 승인 완료 |
| 대구 교통소통정보(신) | https://www.data.go.kr/data/15126266/openapi.do | `DATA_GO_KR_KEY` | 승인 완료 |
| 대구 돌발 교통정보(신) (일 5,000건) | https://www.data.go.kr/data/15126267/openapi.do | `DATA_GO_KR_KEY` | 승인 완료 |
| 한국관광공사 TourAPI (KorService2) | https://www.data.go.kr/data/15101578/openapi.do | `DATA_GO_KR_KEY` | 승인 완료 |
| 대구 관광지 | https://www.data.go.kr/data/3054892/openapi.do | `DATA_GO_KR_KEY` | 승인 완료 |
| 대구 산책로정보 | https://www.data.go.kr/data/15109626/openapi.do | `DATA_GO_KR_KEY` | 승인 완료 |
| TMAP (POI·경로) | https://openapi.sk.com/ → 앱 생성 → TMAP 상품 추가 | `TMAP_APP_KEY` | 발급 완료 |
| 카카오 로컬 | https://developers.kakao.com/ | `KAKAO_REST_KEY` | 발급 완료 |
| 대구 주차장정보·혼잡도 | https://pis.daegu.go.kr/opendata/apiList (별도 회원가입) | `DAEGU_PARKING_KEY` / `DAEGU_PARKING_RT_KEY` (API별 키 분리) | 발급 완료 (접속 IP 제한 있음) |

### 확인된 엔드포인트 (2026-07-15 검증, `scripts/api-tests/test-all-apis.ps1`)

| API | 엔드포인트 | 상태 |
|---|---|---|
| 충전소 정보/상태 | `apis.data.go.kr/B552584/EvCharger/getChargerInfo`, `/getChargerStatus` (XML) | 정상 |
| 기상청 초단기실황 | `apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtNcst` (대구 nx=89, ny=90) | 정상 |
| 대구 교통소통(신) | `apis.data.go.kr/6270000/service/rest1/linkspeed` | **원본 서버 404 — 제공기관 장애, 재확인 필요** |
| 대구 돌발(신) | `apis.data.go.kr/6270000/service/rest/dgincident` | **원본 서버 404 — 제공기관 장애, 재확인 필요** |
| TourAPI | `apis.data.go.kr/B551011/KorService2/locationBasedList2` (`MobileOS`, `MobileApp` 필수) | 정상 |
| 대구 관광지 | `apis.data.go.kr/6270000/getTourKorAttract/getTourKorAttractList` (XML) | 정상 |
| 대구 산책로 | `apis.data.go.kr/6270000/dgInParkwalk/getDgWalkParkList` — 파라미터 `lat`/`lot`(경도), `radius`(km), `type=json` | 정상 |
| TMAP POI/경로 | `apis.openapi.sk.com/tmap/pois`, `/tmap/routes` | 정상 |
| 카카오 로컬 | `dapi.kakao.com/v2/local/search/*.json` | 정상 |
| 대구 주차장 기본정보 | `pis.daegu.go.kr/api/serviceApply/prkInfo` (`Authentication` 헤더, 키: `DAEGU_PARKING_KEY`) | 키 발급 완료. **팀 AWS 서버(3.39.251.72)에서만 호출 가능** — 로컬 호출 시 401이 정상 |
| 대구 실시간 주차 혼잡도 | `pis.daegu.go.kr/api/serviceApply/rltmPrkInfo` (`Authentication` 헤더, 키: `DAEGU_PARKING_RT_KEY`) | 위와 동일 (AWS 서버 전용) |

공공 API는 간헐적으로 502/504를 반환하므로 수집기에 재시도(백오프)가 필수다.

### 연동 시 주의사항

- **기상청 격자좌표**: 단기예보는 위도·경도가 아니라 **nx, ny 격자좌표**(약 5km 격자)를 사용한다. 충전소 위도·경도 → nx/ny 변환 로직(기상청 제공 변환식)을 가공 단계에서 공통 유틸로 구현한다. 초단기예보는 발표 시점부터 최대 6시간 예보 제공.
- **대구 주차장 API는 공공데이터포털 키와 별개**: pis.daegu.go.kr에서 회원가입 후 발급받은 키를 `Authentication` 헤더에 넣는다. **등록된 접속 IP(팀 AWS 서버: 3.39.251.72)에서만 호출된다.** 따라서 이 API의 수집·호출 코드는 반드시 AWS 서버에서 실행해야 하며, 로컬 개발 PC에서 호출하면 401이 나는 것이 정상이다. 로컬 개발 시에는 목(mock) 데이터를 사용한다. API별로 키가 다르다 (기본정보 `DAEGU_PARKING_KEY` ≠ 혼잡도 `DAEGU_PARKING_RT_KEY`).
  - 기본정보: `GET https://pis.daegu.go.kr/api/serviceApply/prkInfo?numOfRows=10&pageNo=1`
  - 혼잡도: `GET https://pis.daegu.go.kr/api/serviceApply/rltmPrkInfo?numOfRows=10&pageNo=1`
  - 모든 주차장이 실시간 정보를 제공하지 않으므로 기본정보의 `sysgrpyYn` 필드로 실시간 지원 여부를 확인한다.
- **돌발 교통정보**: 경로와 돌발 발생 위치의 거리를 계산해 경로에서 일정 거리 이내인 돌발상황만 백엔드에 전달한다.
- **TourAPI**: 현재 서비스 계열은 `KorService2`다. 오래된 블로그의 KorService1 예제를 복사하지 않는다.

### 규칙

- 인증키는 `.env`에서 읽는다 (`EV_API_KEY` 등). 하드코딩 금지.
- **일 트래픽 한도 준수**: EvCharger는 1,000건/일. 상태 수집은 `zcode`(지역)와 `period`를 활용해 호출 수를 최소화한다. 호출 카운트를 로깅한다.
- 원본 응답은 가공하지 않고 그대로 저장한다 (수집 시각 타임스탬프 포함). 파싱 실패에 대비해 원본 보존이 원칙.
- **시각 이중 저장 (중요)**: `statUpdDt`는 API 조회 시각이 아니라 충전기 상태가 갱신·변경된 시각이다. 두 시각을 반드시 별도 컬럼으로 저장한다.
  - `statUpdatedAt` = API가 제공한 충전기 상태 시각 (`statUpdDt`)
  - `fetchedAt` = 우리 서버가 API를 조회한 시각
  - 신뢰도 등급과 도착 시 충전 가능성 계산은 `statUpdatedAt` 기준, 수집 파이프라인 모니터링은 `fetchedAt` 기준.
- API 장애·403·타임아웃 시 재시도(백오프) 후 실패 로그를 남긴다. 신규 키는 동기화에 약 1시간 걸림.
- 수집 스크립트는 단독 실행 가능해야 하고, 스케줄러(cron / Windows 작업 스케줄러 / APScheduler)로 자동화한다.

### 참고: EvCharger API 주요 응답 필드

`statNm`(충전소명), `addr`(주소), `lat`/`lng`(좌표), `chgerId`(충전기 ID), `chgerType`(충전 방식), `output`(충전용량), `stat`(상태 코드: 2=충전대기, 3=충전중, 5=점검중 등), `statUpdDt`(상태 갱신 시각), `useTime`(이용 가능시간), `busiNm`(운영기관), `parkingFree`(주차료 무료 여부)

---

## 데이터 가공 담당

### 처리 파이프라인

1. **정제**: 좌표·주소 정합성 검증, 결측치 처리, 충전기 타입·상태 코드를 공통 코드로 매핑
2. **충전소 단위 집계**: 충전기별 데이터를 충전소 단위로 묶어 전체/사용 가능/사용 중/고장·점검 충전기 수 계산
3. **신뢰도 계산**: `statUpdDt` 기준 경과 시간으로 신뢰도 등급 부여 — 기준은 루트 `AGENTS.md`의 "핵심 도메인 규칙" 표를 따른다 (5분 이내 높음 / 5~15분 보통 / 15분 이상 확인 필요)
4. **이용 패턴 집계**: 시간대·요일별 충전기 사용률 통계 (추후 혼잡도 예측 모델의 학습 데이터)
5. **적재**: 백엔드가 읽는 서비스 테이블에 저장

### 규칙

- 가공 결과 테이블 스키마는 백엔드 담당자와 합의 후 확정하고, 변경 시 사전 공지한다. (백엔드는 읽기 전용)
- 상태 코드, 충전기 타입 등 코드 매핑표는 문서로 관리한다 (`docs/data/` 권장).
- 가공 로직에는 단위 테스트를 작성한다 (특히 신뢰도 등급, 집계 계산).
- 대용량 원본 데이터 파일은 git에 커밋하지 않는다.

---

## 공통 기술 스택

- Python 3.11+ 권장: `requests`/`httpx`, `pandas`, `APScheduler`, `pytest`
- 저장소: 개발 초기 SQLite → 서비스 단계 PostgreSQL (백엔드와 동일 DB)
- 수집·가공 코드 모두 `.env` 기반 설정, 로깅 필수
