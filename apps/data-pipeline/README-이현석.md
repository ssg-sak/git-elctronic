# 이현석 — AI·데이터 ① 데이터·파이프라인

> **공식 가이드 (정본):** [`docs/데이터파트_작업가이드.md`](../../docs/데이터파트_작업가이드.md) · **실행계획:** [`docs/데이터파트_①_실행계획서.md`](../../docs/데이터파트_①_실행계획서.md) · 완료체크 [`docs/데이터파트_①_완료체크.md`](../../docs/데이터파트_①_완료체크.md)

**역할**: AI·데이터 ① — 데이터·파이프라인 (가이드 **DA➀**)
**작업 브랜치**: `feature/이현석`  
**담당 디렉터리**: `apps/data-pipeline/processing/`, `apps/data-pipeline/evaluation/`  
**원본 수집 API·스케줄**: `collection/` 담당과 협의 (인터페이스·포맷 변경 시 합의)  
**GitHub 필수 준수**: [`깃허브_필수준수.md`](./깃허브_필수준수.md) ← 커밋·PR·브랜치 체크리스트

### 수집 담당과의 경계 (침범 방지)

- **공식 수집**은 `apps/data-pipeline/collection/` 담당 영역이다. 여기 코드·스케줄·적재 경로를 임의로 바꾸지 않는다.
- **학습·EDA·특성용 status 시계열**은 `evaluation/personal/experiments/SANDBOX_20260717_status_periodic_collection/` 에서만 돌린다.
- SANDBOX는 `docs/data/extracted/` 를 **덮어쓰지 않는다.** 스냅샷은 SANDBOX `data/snapshots/` 에만 쌓는다.
- EvCharger 일 한도(1,000)는 공식 수집과 **같은 키를 쓰므로** 호출량을 공유한다. 한도 근접 시 SANDBOX가 회차를 스킵한다.
- `collection/` 스키마·경로를 서비스에 올릴 때는 수집 담당과 합의 후 이관한다.

### AI·데이터 ②(모델·평가·서빙)와의 경계

①은 **재료**(정의·품질·특성·데이터셋)까지다. 아래는 **하지 않는다** (② 영역).

- 규칙/ML 점수식·가중치 확정, Top-N 랭킹, 추천 이유 문장
- 위험도 등급 설계, LightGBM 등 모델 실험·평가 비교표
- `packages/recommendation-core/` · 추론·서빙·fallback

특성·데이터셋 스키마를 바꾸면 ②에게 알린다. 점수·위험도·서빙은 ②·백엔드·루트 `AGENTS.md` 합의.

공통 규칙: 루트 `AGENTS.md`, 데이터팀 `apps/data-pipeline/AGENTS.md`

---

## 1. 담당 업무와 완료 기준

| 업무 | 세부 내용 | 완료 기준 | 산출물·코드 |
|---|---|---|---|
| 데이터 정의 | 출처, 컬럼, 타입, 단위, 키, 갱신주기 정의 | 데이터 사전 완성 | `docs/data/` 사전 · `evaluation/` 인벤토리 |
| 품질 점검 | 결측치, 중복, 이상값, 좌표, 시간 형식 분석 | 데이터별 품질 요약표 작성 | 품질 리포트 · `NOTE_*` · status 일일 점검 |
| 상태 표준화 | 사용 가능·사용 중·고장·점검·미확인으로 통일 | 원천값–표준값 매핑표 작성 | `processing/core/cleansing.py` · 매핑 문서 |
| 전처리 | 의미별 결측치 처리, 중복 제거, 좌표 검증 | 처리 전후와 처리 사유 기록 | `processing/` · SANDBOX 전처리 · quarantine |
| 공간 결합 | 충전소와 주차장·관광지·교통정보 연결 | 매칭 성공률과 실패 목록 기록 | 조인 실험 · 후보/실패 CSV |
| EDA | 시간대·요일·충전기 수·최신성별 가용성 분석 | 추천 변수와 연결되는 분석 결과 작성 | `docs/보고/EDA_보고서.md` · EDA 계획 · status 패널 |
| 특성 생성 | 가용 비율, 갱신 경과시간, ETA, 운영 여부, 신뢰도 | 변수 정의서와 생성 코드 일치 | `feature_generator.py` · `reliability.py` |
| 데이터셋 | 규칙 추천용 및 모델 학습용 **입력 테이블** 생성 | 기준시각과 행 단위가 명확함 | `evaluation/` · 학습/규칙용 피처 테이블 |

표준 상태값: **사용 가능 / 사용 중 / 고장 / 점검 / 미확인**  
신뢰도 등급 기준(경과시간)은 루트 `AGENTS.md`를 따른다. **점수 가중치·위험도 구간은 ②**가 문서화한다.

---

## 2. 파이프라인 흐름

```
원본 (collection / extracted CSV)
  → 정의·품질 점검
  → 상태 표준화 · 전처리
  → 공간 결합
  → EDA · 특성 생성
  → 규칙/학습용 입력 데이터셋  (점수·모델은 ②)
```

상세 코드 가이드: `apps/data-pipeline/processing/README.md`  
실험·보고: `apps/data-pipeline/evaluation/`

---

## 3. 추출 데이터 현황 (2026-07-16 기준, 이후 status 주기 수집 누적 중)

저장 위치: `docs/data/extracted/`  
status 시계열(SANDBOX): `evaluation/personal/experiments/SANDBOX_20260717_status_periodic_collection/`

### 확보 완료

| 데이터 | 파일 | 건수 |
|---|---|---:|
| 충전소 기본정보 | `daegu_charger_info_20260716_135041.csv` | 25,326 |
| 충전기 상태 (변경분) | `daegu_charger_status_20260716_135041.csv` | 494 |
| 기상 초단기실황·예보 | `daegu_weather_ultra_*` | ncst 8 / fcst 66 |
| TourAPI 관광지 | `daegu_tour_attractions_20260716_151338.csv` | 57 |
| 주차 기본·실시간 | `daegu_parking_*_team5_latest.csv` | **실** (team_5 PIS) · [계획](../../docs/data/주차/주차_실데이터_계획_team5_20260723.md) |
| status 주기 스냅샷 | SANDBOX `data/snapshots/` | 일 단위 누적 |

### 미확보·제한

| 데이터 | 사유 |
|---|---|
| 교통소통 / 돌발 | 제공기관 404 또는 권한 |
| 주차 실데이터 | AWS IP 제한 → mock |
| 카카오·일부 Tour | 키·승인 재확인 |

---

## 4. 실험·테스트

```bash
cd git-elctronic
pip install -r apps/data-pipeline/evaluation/requirements.txt
python apps/data-pipeline/evaluation/run_experiment.py
cd apps/data-pipeline/evaluation && pytest tests/ -v
```

개인 실험 목록: `evaluation/personal/SSG-SAK_이현석_실험노트.md`

---

## 5. 다음에 할 일 (역할 체크리스트)

- [x] 데이터 사전 — [`docs/data/스키마/데이터_사전.md`](../../docs/data/스키마/데이터_사전.md)
- [x] 원천값–표준 상태 매핑표 — [`docs/data/스키마/상태코드_매핑.md`](../../docs/data/스키마/상태코드_매핑.md)
- [x] 소스별 품질 요약표 — [`docs/data/스키마/품질_요약.md`](../../docs/data/스키마/품질_요약.md)
- [x] 전처리 전후·사유 로그 — [`docs/전처리/전후.md`](../../docs/전처리/전후.md)
- [x] 공간 결합 성공률·실패 목록 — [`docs/data/품질보고/공간조인_보고서.md`](../../docs/data/품질보고/공간조인_보고서.md)
- [x] EDA↔피처 후보 — [`docs/data/스키마/피처_카탈로그.md`](../../docs/data/스키마/피처_카탈로그.md)
- [x] 특성 정의서↔코드 정합 — 동 문서 §3 (`reliability`·`aggregation` 확인)
- [x] 데이터셋 기준시각·행 단위 — [`docs/data/스키마/데이터셋_명세.md`](../../docs/data/스키마/데이터셋_명세.md) (적재 스크립트는 후속)

**후속 구현:**
- [x] F01–F03 → `processing/features/station_features.py`
- [x] D1 스냅샷 적재 → `build_d1_snapshot.py` · `evaluation/results/datasets/`
- [x] D2 패널 적재 → `build_d2_panel.py` · 동일 datasets/
- [x] ② 핸드오프 샘플 → `evaluation/results/datasets/handoff_to_model/`
- [x] ② 공유 문서 → [`docs/팀공유/팀공유_핸드오프_①to②_20260720.md`](../../docs/팀공유/팀공유_핸드오프_①to②_20260720.md) (톡 복붙 포함)
- [x] F08 useTime 파서 고도화 → `processing/features/use_time.py`
- [x] D1을 최신 status 스냅샷 기준으로 주기 갱신 → `status_as_of.py` · `station_feature_snapshot_latest.*`
- [x] EDA 보완 계획 (시간대·요일·규모·최신성·D2) → [`docs/보고/EDA_계획_상태패널.md`](../../docs/보고/EDA_계획_상태패널.md)
- [x] EDA 보완 실행 → `EDA_보고서.md` §11–14 · `evaluation/results/eda/` · [`EDA_보고서_쉬운요약.md`](../../docs/보고/EDA_보고서_쉬운요약.md)
- [x] **이중 신선도** F04b/F05b · D1 `observation_age` / `reliability_grade_effective` → `status_as_of.py` · `station_features.py` · [`EDA_보고서.md` §15](../../docs/보고/EDA_보고서.md)
- [x] status loop **10분/15분** 재가동 (2026-07-20 15:55~) — **현재 PC에서 수집 중**
- [x] **공식 가이드 반영** — [`DATA_PART_WORK_GUIDE`](../../docs/데이터파트_작업가이드.md) · `json/` · `run_mock_pipeline.py`
- [ ] **필수** 주차·교통 대체 API — [`docs/data/API/주차교통_대체API_전략.md`](../../docs/data/API/주차교통_대체API_전략.md) (KOTSA·UTIC 신청 → 프로브)

---

## 6. status 수집 운영 (loop1, 2026-07-22 기준)

| 항목 | 값 |
|---|---|
| **상태** | **Lightsail 24h** (`52.79.224.112`) · **PC 루프 끄기** (한도 이중 소모 금지) |
| **간격** | interval **10분** · API period **10분** (5분이면 일 1000으로 저녁 skip) |
| **경로** | `evaluation/personal/experiments/SANDBOX_20260717_status_periodic_collection/` → 저장 `docs/data/loops/loop1/` |
| **재시작** | 2026-07-24 — interval 5→10 (전시간대 커버) |
| **한도** | EvCharger 일 1,000건 공유 — 한도 근접 시 틱 스킵 (`daily_limit_margin`) |
| **전시간대** | [`docs/보고/전시간대_수집_API한도_20260724.md`](../../docs/보고/전시간대_수집_API한도_20260724.md) |

```bash
# PC에서 수동 돌릴 때만 (평소엔 OFF — 서버만)
python apps/data-pipeline/evaluation/personal/experiments/SANDBOX_20260717_status_periodic_collection/src/run_loop.py --interval-minutes 10 --period-minutes 10
```

학습서: [`LEARNING_GUIDE_status주기수집.md`](evaluation/personal/experiments/SANDBOX_20260717_status_periodic_collection/LEARNING_GUIDE_status주기수집.md)

---

## 7. 참고 링크

| 문서 | 경로 |
|---|---|
| **데이터 사전** | `docs/data/스키마/데이터_사전.md` |
| **상태 매핑표** | `docs/data/스키마/상태코드_매핑.md` |
| **품질 요약표** | `docs/data/스키마/품질_요약.md` |
| **전처리 전후 로그** | `docs/전처리/전후.md` |
| **공간 결합** | `docs/data/품질보고/공간조인_보고서.md` |
| **피처 정의서** | `docs/data/스키마/피처_카탈로그.md` |
| **데이터셋 명세** | `docs/data/스키마/데이터셋_명세.md` |
| 가공 패키지 가이드 | `apps/data-pipeline/processing/README.md` |
| 실험 모듈 가이드 | `apps/data-pipeline/evaluation/README.md` |
| EDA 보고 | `docs/보고/EDA_보고서.md` |
| **EDA 쉬운 요약** | [`docs/보고/EDA_보고서_쉬운요약.md`](../../docs/보고/EDA_보고서_쉬운요약.md) |
| **EDA 계획 (패널 보완)** | [`docs/보고/EDA_계획_상태패널.md`](../../docs/보고/EDA_계획_상태패널.md) |
| API 연동 가이드 | `docs/data/운영/API_연동_현황.md` |
| 데이터팀 AGENTS | `apps/data-pipeline/AGENTS.md` |
| 개인 실험 노트 | `apps/data-pipeline/evaluation/personal/SSG-SAK_이현석_실험노트.md` |
| **①→② 핸드오프** | `docs/팀공유/팀공유_핸드오프_①to②_20260720.md` |
| **관측·가용 학습서** | [`docs/data/가이드/학습가이드_관측과가용.md`](../../docs/data/가이드/학습가이드_관측과가용.md) |
| **주차·교통 필수 대체 API** | [`docs/data/API/주차교통_대체API_전략.md`](../../docs/data/API/주차교통_대체API_전략.md) |
| **공식 데이터 파트 가이드** | [`docs/데이터파트_작업가이드.md`](../../docs/데이터파트_작업가이드.md) |
| **DA➀ 실행계획서** | [`docs/데이터파트_①_실행계획서.md`](../../docs/데이터파트_①_실행계획서.md) |
| **DA➀ 완료체크** | [`docs/데이터파트_①_완료체크.md`](../../docs/데이터파트_①_완료체크.md) |
| **목데이터 json/** | [`json/`](../../json/) |
| **UTIC 준수사항** | [`docs/data/API/UTIC_개방데이터_준수사항.md`](../../docs/data/API/UTIC_개방데이터_준수사항.md) |
| **UTIC 팀 공유 (2026-07-21)** | [`docs/팀공유_UTIC_20260721.md`](../../docs/팀공유/팀공유_UTIC_20260721.md) |
| **Mock 걷어내기·루프 분리** | [`docs/data/운영/실데이터_목데이터_트랙.md`](../../docs/data/운영/실데이터_목데이터_트랙.md) |
| **GitHub 필수 준수** | [`깃허브_필수준수.md`](./깃허브_필수준수.md) |
| **데이터 타당성 게이트 보고서 (2026-07-22)** | [`docs/보고/데이터타당성_게이트보고서_20260722.md`](../../docs/보고/데이터타당성_게이트보고서_20260722.md) |
| **Status 4층 저장 설계** | [`docs/data/운영/status_4층_저장설계.md`](../../docs/data/운영/status_4층_저장설계.md) |
