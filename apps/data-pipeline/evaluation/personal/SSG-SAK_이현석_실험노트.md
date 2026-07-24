# SSG-SAK | 이현석 개인 실험 노트

```
 ███████╗███████╗ ██████╗       ███████╗ █████╗ ██╗  ██╗
 ██╔════╝██╔════╝██╔════╝       ██╔════╝██╔══██╗██║ ██╔╝
 ███████╗███████╗██║  ███╗      ███████╗███████║█████╔╝
 ╚════██║╚════██║██║   ██║      ╚════██║██╔══██║██╔═██╗
 ███████║███████║╚██████╔╝      ███████║██║  ██║██║  ██╗
 ╚══════╝╚══════╝ ╚═════╝       ╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝
```

**담당**: AI·데이터 ① — 데이터·파이프라인  
**프로젝트**: EV SafeCharge  
**용도**: 정의·품질·전처리·EDA·특성·데이터셋·status 시계열 근거

> **역할·완료 기준:** [`apps/data-pipeline/README-이현석.md`](../../README-이현석.md)  
> **범위 밖:** 점수·추천 이유·ML·평가는 AI·데이터 ② (관련 EXP·코드는 제거함)

---

## 폴더 규칙

| 위치 | 넣는 것 | 넣지 않는 것 |
|---|---|---|
| `experiments/` | **실험 노트 MD만** | CSV, DB, 대용량 파일 · 점수/ML 실험 |
| `docs/data/extracted/` | 실/mock CSV | — |
| `evaluation/results/` | 실행 결과 JSON/MD | — |

### 실험 원칙

> **실험할 때는 확보된 데이터를 전부 고려한다.**  
> 초점이 교통·충전이어도 입력 표에는 실/mock/미확보 **전 소스**를 올리고,  
> 미사용분은 “참조” 또는 “N/A”로 명시한다.

상세: [`experiments/README.md`](./experiments/README.md)

실험·가공 전 필수: [`NOTE_20260716_전소스_데이터품질이슈.md`](./experiments/NOTE_20260716_전소스_데이터품질이슈.md)

**보고·학습 (전처리):**  
- 전처리 보고: [`EXP-004`](./experiments/EXP-004_20260716_전소스전처리_실험보고서.md)  
- 전처리 학습서: [`LEARNING_GUIDE_전처리`](./experiments/SANDBOX_20260716_preprocess_pipeline/reports/LEARNING_GUIDE_전소스전처리.md)

### 로드맵

| 단계 | 위치 | 상태 |
|---|---|---|
| 로드맵 | [`_PHASES.md`](./experiments/_PHASES.md) | — |
| 전처리 SANDBOX | [`SANDBOX_20260716_preprocess_pipeline/`](./experiments/SANDBOX_20260716_preprocess_pipeline/) | ✅ |
| status 수집 | [`SANDBOX_20260717_status_periodic_collection/`](./experiments/SANDBOX_20260717_status_periodic_collection/) | 🚀 계속 |
| 실데이터 확장 | [`phase2_realdata/`](./experiments/phase2_realdata/) | ⏸ 대기 |
| 품질 비교 | [`compare_1vs2/`](./experiments/compare_1vs2/) | ⏸ 확장 후 |

---

## 실험 목록

| ID | 날짜 | 제목 | 상태 | 상세 |
|---|---|---|---|---|
| EXP-001 | 2026-07-16 | 추출 CSV 가공 베이스라인 | ✅ 완료 | [EXP-001](./experiments/EXP-001_20260716_추출CSV가공베이스라인.md) |
| EXP-002 | 2026-07-16 | 교통·돌발 mock 조인 | 📝 계획 | [EXP-002](./experiments/EXP-002_20260716_교통돌발mock조인_계획.md) |
| EXP-003 | 2026-07-16 | 다중원 CSV 인벤토리·품질 | 📝 계획 | [EXP-003](./experiments/EXP-003_20260716_다중원CSV인벤토리_계획.md) |
| NOTE | 2026-07-16 | 전 소스 데이터 품질 이슈 | ✅ 반영 | [NOTE](./experiments/NOTE_20260716_전소스_데이터품질이슈.md) |
| SANDBOX | 2026-07-16 | 전소스 전처리 파이프라인 (격리) | ✅ 실행 | [SANDBOX](./experiments/SANDBOX_20260716_preprocess_pipeline/README.md) |
| EXP-004 | 2026-07-16 | 전소스 전처리 실험 보고서 | ✅ 보고 | [EXP-004](./experiments/EXP-004_20260716_전소스전처리_실험보고서.md) |
| GUIDE | 2026-07-16 | 전소스 전처리 학습서 | ✅ | [학습서](./experiments/SANDBOX_20260716_preprocess_pipeline/reports/LEARNING_GUIDE_전소스전처리.md) |
| EXP-012 | 2026-07-17 | status 주기 수집 (**interval 10 / period 15**, 2026-07-20 재시작) | 🚀 가동 | [EXP-012](./experiments/EXP-012_20260717_status주기수집_시작.md) · [학습서](./experiments/SANDBOX_20260717_status_periodic_collection/LEARNING_GUIDE_status주기수집.md) |
| EXP-022 | 2026-07-20 | 이중 신선도 F04b + D1 갱신 | ✅ | `EDA_보고서.md` §15 |
| EXP-023 | 2026-07-20 | **공식 DATA_PART 가이드** 반영 · json 목 · gap_safe_panel | ✅ | [`DATA_PART_WORK_GUIDE`](../../../docs/데이터파트_작업가이드.md) |
| PLAN | 2026-07-20 | **DA➀ 실행계획서** (문서 로드맵·Phase 2–5) | 📋 | [`데이터파트_①_실행계획서`](../../../docs/데이터파트_①_실행계획서.md) |
| EXP-019 | 2026-07-18 | status 수집 데이터 검증 (무결성·중복) | ✅ 보고 | [EXP-019](./experiments/EXP-019_20260718_status수집검증_실험보고서.md) |
| EXP-020 | 2026-07-18 | status 수집 데이터 가치 시각 평가 | ✅ 보고 | [EXP-020](./experiments/EXP-020_20260718_status수집_데이터가치_시각평가.md) |
| EXP-021 | 2026-07-19 | status 일일 자동 점검 운영 | 🚀 가동 | [EXP-021](./experiments/EXP-021_20260719_status일일자동점검_운영보고서.md) |
| EXP-017 | (나중) | 실데이터 전처리·공간결합 확장 | ⏸ 예약 | [phase2](./experiments/phase2_realdata/) |
| EXP-018 | (나중) | 데이터 품질·커버리지 비교 | ⏸ 예약 | [compare](./experiments/compare_1vs2/) |

---

## 실험 실행 방법

```bash
cd git-elctronic
python apps/data-pipeline/evaluation/run_experiment.py

cd apps/data-pipeline/evaluation
pytest tests/ -v
```

새 실험 기록:
1. `experiments/_TEMPLATE.md` 복사 → `EXP-00N_날짜_제목.md`
2. 위 표에 한 줄 추가
3. CSV는 `extracted/` 경로만 노트에 기입
4. 점수·모델·추천 이유 실험은 만들지 않는다 (②)

---

## 입력 데이터 (고정 참조 — 최신)

| 데이터 | 경로 |
|---|---|
| 충전소 info | `docs/data/extracted/daegu_charger_info_20260716_170553.csv` |
| 충전기 status | `docs/data/extracted/daegu_charger_status_20260716_170553.csv` |
| 기상 초단기 | `docs/data/extracted/daegu_weather_ultra_*_20260716_205706.csv` |
| 기상 단기 | `docs/data/extracted/daegu_weather_vilage_fcst_20260716_205822.csv` |
| TourAPI | `docs/data/extracted/daegu_tour_attractions_20260716_205706.csv` |
| 대구시 관광지 | `docs/data/extracted/daegu_city_tour_20260716_232150.csv` |
| 산책로 | `docs/data/extracted/daegu_walk_parks_20260716_210115.csv` |
| 주차 mock | `docs/data/extracted/daegu_parking_*_mock.csv` |
| 교통 소통 mock | `docs/data/extracted/daegu_traffic_linkspeed_mock.csv` |
| 교통 돌발 mock | `docs/data/extracted/daegu_traffic_incident_mock.csv` |

---

## 메모

- **실험 = 전 데이터 고려** (충전·기상·관광·산책·주차·교통 mock 포함)
- **품질 이슈 필수 참조**: [`NOTE_20260716_전소스_데이터품질이슈.md`](./experiments/NOTE_20260716_전소스_데이터품질이슈.md)
  - status 초기 스냅샷 커버리지 낮음 → 미관측≠사용불가 (② 점수 전에 ①이 데이터셋에 명시)
  - Tour 한글 깨짐 / 기상 1격자 / 주차 실시간 제한 등
- status API `period` = **최근 N분 변경분**. 우리 `interval` = 호출 주기. 둘은 다름 → EXP-012
- status 주기 수집: interval 15분 / period 20 / SANDBOX 스냅샷
- status 검증(EXP-019): 무결성 양호, 로더에서 dedup, 원본 스냅샷 보존
- 시계열 로드: `SANDBOX_.../src/load_snapshots.py` (회차 내 중복 제거)
- 가용률 집계(EXP-020): 관측행 평균 금지, `build_panel.py` 공백 안전 패널(25분 초과 시 초기화)
- 주차·교통 mock은 스키마·조인 검증용. 실API 연동 시에도 **데이터 결합**이 ①, 점수 반영은 ②
