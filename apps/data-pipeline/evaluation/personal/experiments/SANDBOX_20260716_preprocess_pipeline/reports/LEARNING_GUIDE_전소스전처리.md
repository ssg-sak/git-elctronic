```
 ███████╗███████╗ ██████╗       ███████╗ █████╗ ██╗  ██╗
 ██╔════╝██╔════╝██╔════╝       ██╔════╝██╔══██╗██║ ██╔╝
 ███████╗███████╗██║  ███╗█████╗███████╗███████║█████╔╝
 ╚════██║╚════██║██║   ██║╚════╝╚════██║██╔══██║██╔═██╗
 ███████║███████║╚██████╔╝       ███████║██║  ██║██║  ██╗
 ╚══════╝╚══════╝ ╚═════╝        ╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝
```

# EV SafeCharge — 전 소스 데이터 전처리 학습서

| 항목 | 내용 |
|---|---|
| **대상** | 데이터 가공·분석 담당 / 신규 합류 멤버 |
| **선수** | Python, pandas 기초, CSV·조인 개념 |
| **실습 폴더** | `experiments/SANDBOX_20260716_preprocess_pipeline/` |
| **실험 보고** | [`EXP-004_...실험보고서.md`](../../EXP-004_20260716_전소스전처리_실험보고서.md) |
| **작성** | 이현석 · SSG-SAK · 2026-07-16 |

> 이 학습서는 **왜 이렇게 전처리하는지**와 **어떻게 재실행·확장하는지**를 담는다.  
> 코드는 샌드박스에 있고, 원본 CSV는 절대 수정하지 않는다.

---

## 0. 5분 안에 이해하기

### 서비스 목표

```
가까운 충전소 ❌
도착했을 때 실제로 충전할 수 있을 가능성 높은 충전소 ✅
```

점수 감각(팀 공통): 충전가능성 40% + 신뢰도 20% + 이동시간 15% + 대기위험 15% + 주변편의 10%.

### 데이터가 한 종류가 아닌 이유

| 단위 | 예 | 잘못 합치면 |
|---|---|---|
| 충전기 1대 | info row | 충전소로 착각 |
| 충전소 | `statId` | status 없는 대를 고장으로 처리 |
| 링크·돌발 | traffic mock | 충전소 row에 억지 concat |
| 격자 날씨 | nx,ny | 충전소별 날씨로 오해 |
| POI | Tour / 공원 / 시관광 | 좌표 없는 행을 지도에 찍음 |

→ **관계형 테이블**로 두고, 필요한 순간에만 조인한다.

---

## 1. 폴더 지도

```
SANDBOX_20260716_preprocess_pipeline/
├── README.md
├── data/
│   ├── raw/          # manifest만 (원본은 docs/data/extracted)
│   ├── interim/
│   ├── processed/    # 실험·모델이 읽는 정제본
│   └── quarantine/   # 좌표 이상 등 — 삭제가 아님
├── reports/
│   ├── data_quality/ # 품질 보고·결측 정책
│   └── LEARNING_GUIDE_전소스전처리.md  ← 본 문서
├── src/preprocessing/
└── tests/
```

원본: `git-elctronic/docs/data/extracted/`  
품질 이슈 선행 읽기: `../NOTE_20260716_전소스_데이터품질이슈.md`

---

## 2. 절대 규칙 (체크리스트)

학습·코딩 시 아래를 어기면 실험이 무효에 가깝다.

1. **원본 CSV 덮어쓰기 금지**
2. **결측을 평균·중앙값·최빈값으로 일괄 채우지 않기**
3. **실시간 없음 ≠ 사용불가 / 만차 / 혼잡**
4. **mock은 `isMock` 유지**, 실데이터와 섞여 보이게 두지 않기
5. **ID·코드·시각 코드는 문자열** (`chgerId` 앞자리 0 보존)
6. **좌표계 EPSG:4326** (`lot`이 경도인 스키마 주의 — 주차·공원)
7. **원본 컬럼 보존 + 정제 컬럼 분리** (`*_raw`, `*_num`, `*_norm`)
8. **전 소스 고려** — 실험 노트 입력 표에 전부 올리기
9. **`(1)` 복사본 무시**
10. **삭제 대신 격리·플래그** (좌표 이상 27건)

---

## 3. 결측 유형 분류법

| 유형 | 예 | 할 일 |
|---|---|---|
| 조인으로 복원 | status `statNm` | `statId+chgerId` → info |
| 구조적 정상 결측 | Tour `addr2`, 돌발 `note` | 결측 허용, 플래그만 |
| API 미수집 | status 97% 없음, 주차 실시간 2곳 | `*_missing` / `UNKNOWN` |
| 빈 문자열·`"null"` | 공백, `-` | 실제 NA로 변환 |
| 품질 오류 | 주소↔좌표 불일치 | quarantine + flag |

**나쁜 예**: status 없는 충전기 → AVAILABLE=0  
**좋은 예**: `status_missing=True`, 가용률은 **관측분 분모**로 따로 계산

---

## 4. 도메인별 학습 포인트

### 4.1 충전기

- 단위 = **충전기** (`statId + chgerId`), 충전소 아님  
- status는 `period` **변경분** → 커버리지 ~2.3%가 정상일 수 있음  
- `delYn=Y` → 삭제하지 말고 `is_service_target=False`  
- `limitYn=Y` → 위험 요인으로 유지  
- `output`/`useTime`/`parkingFree` 추정 금지  

상태 코드는 `config/stat_code_map.json` 만 신뢰. 미매핑 → `UNKNOWN_CODE`.

### 4.2 주차 (mock)

- 기본 12 ↔ 실시간 10  
- 없는 2곳 = **실시간 정보 없음**, 만차 아님  
- `전일운영` + 시간 공백일 때만 파생 `0000`–`2400` (원본 유지)

### 4.3 관광·공원

- Tour: 한글 깨짐 → **깨진 행만** 복구 시도 (`encoding_repaired`)  
- city_tour: `attr01` = `항목|내용` → long/wide. **좌표 없음** → 지오코딩 전제  
- Tour↔city fuzzy 매칭은 **자동 확정 금지** (`needs_review`)  
- 공원: `roadNmAddr` 80%+ 공백 → 삭제 금지, `ROAD → LOT → UNKNOWN`

### 4.4 교통 (mock)

- link: 거리·속도·시간 일관성 플래그  
- incident: `affectLinkId` FK, 활성 여부 `is_active_at_asof`  
- 종료 돌발 **삭제하지 않음**

### 4.5 기상

- 날짜·시간은 **문자열**로 읽어 0 패딩 유지  
- PCP `강수없음` → 0, `1mm 미만` 파싱  
- SKY/PTY는 코드형 유지  
- **nx=89, ny=90만** → “대구 전역 날씨”라고 쓰지 말 것  

---

## 5. 실습: 파이프라인 돌리기

### 5.1 환경

```bash
cd git-elctronic
pip install pandas pyarrow pytest
# pyarrow 없으면 parquet만 스킵되고 CSV는 생성됨
```

### 5.2 실행

```bash
python apps/data-pipeline/evaluation/personal/experiments/SANDBOX_20260716_preprocess_pipeline/src/preprocessing/run_pipeline.py
```

성공 시 콘솔에 `PIPELINE OK`, coverage% ≈ 2.34, quarantine ≈ 27.

### 5.3 테스트

```bash
python -m pytest apps/data-pipeline/evaluation/personal/experiments/SANDBOX_20260716_preprocess_pipeline/tests -v
```

### 5.4 결과 확인

| 볼 것 | 경로 |
|---|---|
| 정제 테이블 | `data/processed/*.csv` |
| 좌표 이상 | `data/quarantine/charger_coordinate_suspects.csv` |
| 품질 보고 | `reports/data_quality/data_quality_report.md` |
| 결측 정책 | `reports/data_quality/missing_value_policy.md` |

---

## 6. 통합 테이블 읽는 법

```
charger_master ──┐
                 ├── left join ──▶ charger_current_view
charger_status ──┘                    │
                                      ├─ status_missing?
parking_current (mock)                ├─ coordinate_quality_flag
traffic_* (mock)                      └─ availability_note
poi_master (coords) / poi_city_* (no coords)
weather_hourly (single grid)
```

서로 다른 grain을 `pd.concat`으로 세로 합치지 않는다.

---

## 7. 새 데이터 추가하는 방법 (확장)

1. `src/preprocessing/paths.py` 의 `FILES`에 파일명 추가  
2. `clean_*.py`에 정제 함수 추가 (원본 보존·플래그·mock 규칙 준수)  
3. `run_pipeline.py`에서 호출·`persist_all`에 테이블 등록  
4. `tests/`에 스키마·결측 토큰 테스트 1개 이상  
5. 실험 노트 입력 표에 **전 소스**로 한 줄 추가  
6. `NOTE`·품질 보고에 제한사항 기록  

---

## 8. 자주 하는 실수 FAQ

**Q. status가 없으면 그냥 고장 아닌가요?**  
A. 아니요. 수집이 안 된 것입니다. `NO_STATUS_OBSERVED`.

**Q. 공원 도로명이 비었으니 drop?**  
A. 아니요. 지번·좌표가 있습니다.

**Q. 기상으로 충전소별 날씨 점수?**  
A. 지금은 격자 1개뿐이라 공간 차별화 불가. 전역 보조 가중치 수준만.

**Q. city_tour를 지도에 바로?**  
A. 좌표 없음. 지오코딩 전까지는 속성 분석만.

**Q. 예측 모델 당장?**  
A. 스냅샷만으로는 부족. status 시계열 쌓인 뒤. MVP는 규칙 기반.

---

## 9. 추천 학습 순서

1. 본 학습서 §0–2  
2. `NOTE_20260716_전소스_데이터품질이슈.md`  
3. 파이프라인 1회 실행 + `charger_current_view` 열어보기  
4. EXP-004 실험 보고서  
5. EXP-012 (status 주기 수집) — 특성·데이터셋용 시계열  
6. `api-setup-report` / `api-integration-guide` (수집 맥락)  

> 점수·규칙 추천·ML은 AI·데이터 ② 영역이므로 이 학습 경로에 넣지 않는다.

---

## 10. 한 줄 요약

> **관측되지 않은 것을 실패로 만들지 말고,  
> 단위가 다른 데이터를 억지로 합치지 말며,  
> 원본은 남기고 샌드박스에서만 실험하라.**

```
SSG-SAK  |  EV SafeCharge  |  전소스 전처리 학습서  |  이현석
SANDBOX_20260716_preprocess_pipeline
```
