# Team Developer Log

팀·에이전트 공통 개발 기록과 로컬 실행·세팅 안내입니다.

> 이 파일은 팀 공용 정본이다. `apps/web/docs/teamdeveloper.md`,
> `apps/api/docs/teamdeveloper.md`는 같은 내용으로 동기화한다.

## 팀원 온보딩 — 실행·세팅

### 0. 전제

| 항목 | 내용 |
|---|---|
| 워크스페이스 | 이 저장소 루트에서 `apps/web`, `apps/api`, `apps/data-pipeline`을 함께 관리 |
| Frontend | `apps/web` — Next.js 초기화 전 골격 |
| Backend | `apps/api` — Express 초기화 전 골격 |
| Node | 20+ 권장 |
| Python | 3.11+ 권장 (데이터 파이프라인) |
| DB | 서비스 단계에서 환경변수로만 연결. 실 접속값은 문서화·커밋 금지 |

### 1. 세팅 순서

1. 각 앱의 `package.json` 및 `.env.example`을 확인한다.
2. Backend를 초기화·기동하고 health endpoint를 확인한다.
3. Frontend를 초기화·기동하고 지도 화면을 확인한다.
4. DB·TMAP·OAuth 등 실값은 각자 로컬 `.env`에만 넣는다.

### 2. Backend (`apps/api`)

```powershell
cd apps/api
copy .env.example .env
# 초기화 후: npm install
# 초기화 후 package.json의 dev 스크립트로 기동
```

현재 `apps/api`는 Express 의존성과 실행 스크립트를 추가하기 전의 골격이다. API 키·DB 접속값은 `.env`에만 두며, 프론트엔드에 전달하지 않는다.

### 3. Frontend (`apps/web`)

```powershell
cd apps/web
copy .env.example .env.local
# 초기화 후: npm install
# 초기화 후 package.json의 dev 스크립트로 기동
```

`NEXT_PUBLIC_`에는 브라우저 노출이 전제된 지도 SDK 키만 넣는다. DB 비밀번호·서버 REST 키·TMAP REST 키는 넣지 않는다.

### 4. 일상 실행

```text
터미널 A: apps/api  → 백엔드 dev 서버
터미널 B: apps/web  → 프론트 dev 서버
터미널 C: apps/data-pipeline → 수집·D1·품질 작업
```

### 5. 자주 막히는 것

| 증상 | 대처 |
|---|---|
| `mysql` 명령을 찾지 못함 | Python DB 패키지가 아니라 MySQL CLI 설치·PATH 등록이 필요. GUI 접속은 HeidiSQL 세션 사용 |
| API/Frontend가 실행되지 않음 | 현재 두 앱은 초기화 전 골격이므로 의존성·실행 스크립트를 먼저 추가 |
| stations가 비어 있음 | DB 연결·적재·서비스 구현 전에는 정상일 수 있음 |
| 키 관련 오류 | 실제 값은 로컬 `.env`에만 입력하고 `.env.example`에는 키 이름만 유지 |

## 기록·보안 규칙

- 시크릿, API 키, 비밀번호, 개인정보, 내부 호스트·계정의 실제 값은 적지 않는다.
- 의미 있는 구현 완료 뒤 `한 일 / 결정 / 다음` 형식으로 짧게 추가한다.
- 공용 정본은 이 파일이며 `apps/web/docs/teamdeveloper.md`, `apps/api/docs/teamdeveloper.md`와 동기화한다.
- `.env`, `.env.local`은 커밋하지 않고 `.env.example`만 관리한다.

## 로컬 실행 요약

| 구분 | 명령 / 확인 |
|---|---|
| API | `cd apps/api` → 프로젝트별 실행 안내에 따라 서버 기동 |
| Web | `cd apps/web` → 프로젝트별 실행 안내에 따라 개발 서버 기동 |
| 데이터 | `apps/data-pipeline/`의 `.env`에서 키를 읽고 원천별 수집·가공 실행 |
| DB | 로컬 환경변수에만 접속 정보를 입력하고, 문서·소스에 실제 값을 기록하지 않음 |

## 팀 합의

- 추천 점수·위험도·추천 이유·ETA 정책은 AI·데이터 ② 및 백엔드의 책임이다.
- AI·데이터 ①은 원천 수집, 품질, 공간조인, D1/D2 입력과 null·신선도 계약을 제공한다.
- 상태 미관측은 사용 불가가 아니며, 상태 갱신·마지막 관측 시각을 함께 노출한다.
- API 응답·공용 스키마 변경은 관련 담당자와 문서로 먼저 합의한다.

## 2026-07-27 — 동적 원천·D1 갱신

### 한 일

- 서버 상태·교통 루프를 동기화하고, 교육장 프로필의 UTIC 키로 돌발 수집·공간조인을 실행했다.
- 최신 원천 기준 D1, KPI, 통합 준비도와 7/27 시간대 가용률 자료를 재생성했다.
- KOTSA 전국 주차 원천은 대구광역시 행정구역 기준 필터·재개·중복 제거 방식을 검토했으나, 폐기 결정으로 운영하지 않는다.

### 결정

- 주차 정본은 Team5 PIS만 유지한다. KOTSA는 실시간 값 부재·부분 추출·MVP 사용처 부재로 폐기한다.
- KOTSA partial·checkpoint·예외 로그·KOTSA 전용 probe 결과를 삭제했다.

### 다음

- Team5 realtime 이력이 14일 이상 누적되면 주차 보조 정보의 점수 반영 가능성만 재검증한다.

## 2026-07-27 — 개발 기록 자동 동기화 규칙

### 한 일

- `.cursor/rules/team-developer-log.mdc`를 추가해 의미 있는 작업 완료 뒤 공용 Team Developer Log와 web·api 동기본을 갱신하도록 설정했다.

### 결정

- 질문만 답한 경우, 보존되는 변경이 없는 실패 실험, 사소한 한 줄 수정은 기록하지 않는다.
- 시크릿·실키·비밀번호·개인정보·내부 접속 실값은 로그에 기록하지 않는다.

### 다음

- 이후 의미 있는 구현 완료 시 이 형식의 블록을 공용 정본에 추가하고 두 동기본에 같은 내용으로 반영한다.

## 2026-07-27 — Team5 주차 점수 반영 검증

### 한 일

- `validate_parking_score_utility.py`를 추가해 Team5 realtime·STRONG 공존 후보만으로 주차 피처의 점수 반영 게이트를 재현 가능하게 만들었다.
- 현재 자료의 상태 panel 6일과 Team5 realtime 3일을 시간 동기화해 확인했고, STRONG 57개 충전소 중 동기화된 주차 행과 `t+15` 주차 동기화 미래 라벨은 0건이었다.
- D1 불변식·원천 품질 검사를 다시 실행했다.

### 결정

- 현 시점 판정은 `PARKING_AUXILIARY_ONLY`다. 주차 잔여면·점유율은 추천 점수·순위에 반영하지 않고, 검증된 공존 후보의 보조 안내로만 유지한다.
- KOTSA 부분·정적 추출본과 1km 근접 조인은 이번 점수 검증의 입력에서 제외했다.

### 다음

- Team5 주차와 충전 상태를 같은 시간대에 14일 이상 누적한 뒤, `t+15` 도착 가용성 기준의 시간 분리 성능 비교를 재실행한다.
