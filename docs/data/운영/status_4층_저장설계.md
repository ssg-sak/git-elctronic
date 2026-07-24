# Status 4층 저장 설계 — collector / snapshot / event / serving

| 항목 | 내용 |
|---|---|
| **작성** | 2026-07-22 |
| **배경** | [`데이터타당성_게이트보고서_20260722.md`](../../보고/데이터타당성_게이트보고서_20260722.md) §3.3 — `polled OK + unchanged` 명시 행 부재 |
| **원칙** | 원본 스냅샷 불변 · 미관측≠사용불가 · null≠0 · 현재상태≠ETA 예측 · lastSeenAt-only로 이력 대체 금지 |
| **운영** | loop1 interval **5분** · period **10분** |

이 문서는 **설계 정본**이다. 당장 기존 CSV를 지우거나 스키마를 강제 마이그레이션하지 않는다.  
현재 loop1 산출물을 **논리 계층에 매핑**하고, 다음 구현 단계에서 컬럼·파일을 맞춘다.

---

## 1. 한 줄 요약

| 층 | 이름 | 질문에 답하는 것 | 지금 어디에 있나 |
|---|---|---|---|
| **L1** | `collector_run` | 이번 틱에 API를 **성공적으로 돌렸는가?** | `index.csv` + `logs/call_log.jsonl` |
| **L2** | `status_snapshot_raw` | 이번 틱에 API가 **돌려준 변경분 원본**은? | `loop1/snapshots/*.csv` |
| **L3** | `status_event` | 충전기 상태가 **언제 무엇으로 바뀌었나?** | (파생 예정) 관측 시계열에서 추출 |
| **L4** | `status_serving` / D1 | **지금 추천에 쓸 최신 뷰**는? | D1 `station_feature_snapshot_latest` |

**금지:** L4만 두고 L1~L3를 버리면 → lastSeenAt-only와 동일하게 **과거 관측·수집 성공 이력이 소실**된다.

---

## 2. 왜 네 층인가

EvCharger `getChargerStatus(period=N)` 는 **전수 스냅샷이 아니라 변경분**이다.

| 현실 | 잘못된 해석 | 올바른 해석 |
|---|---|---|
| 틱에 충전기 행이 없음 | 사용불가(0) | **이번 period에 변경 없음** 이거나 **한 번도 관측 안 됨** |
| 수집 실패 | (행 없음과 동일 취급) | L1 `ok=false` / `skipped` — **상태 유지로 채우면 안 됨** |
| D1의 `last_seen`만 갱신 | 이력 충분 | L2·L3 없으면 **언제 바뀌었는지·언제 폴링했는지** 복구 불가 |

게이트에서 말한 공백:

> `polled OK + unchanged` 명시 행이 없다.

→ L1(성공 폴링) + L3(마지막 관측 상태) + max_hold 로 **패널에서만** 추론한다.  
원본에 “unchanged” 가짜 행을 심지 않는다(원본 오염 금지).

---

## 3. 계층 다이어그램

```text
                    ┌─────────────────────────┐
   EvCharger API ──►│ L1 collector_run        │  틱마다 1행 (성공/실패/스킵)
                    │    + call_log (상세)    │
                    └───────────┬─────────────┘
                                │ ok=true 일 때만
                                ▼
                    ┌─────────────────────────┐
                    │ L2 status_snapshot_raw  │  틱×변경분 CSV (불변)
                    └───────────┬─────────────┘
                                │ 파생 (읽기 전용)
                                ▼
                    ┌─────────────────────────┐
                    │ L3 status_event         │  상태 전환만 (이전≠이후)
                    └───────────┬─────────────┘
                                │ as_of / 집계
                                ▼
                    ┌─────────────────────────┐
                    │ L4 serving (D1)         │  충전소 최신 피처 1행
                    │ (+ 선택: charger_latest)│
                    └─────────────────────────┘

패널·ETA 라벨 (학습)
  L1.collection_success + L2/L3 관측
  → gap-safe / 5분 패널 (ffill은 max_hold·성공틱에서만)
```

---

## 4. L1 — `collector_run` (수집 실행 로그)

### 목적
- **수집 성공**과 **상태 미변경**을 분리하는 유일한 근거
- 일일 API 한도·재시도·스킵 모니터링

### 논리 스키마 `collector_run`

| 컬럼 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `run_id` | string | ✅ | = `snapshotId` (`YYYYMMDD_HHMMSS`) |
| `started_at` | datetime(KST) | ✅ | 틱 시작 |
| `finished_at` | datetime(KST) | | 종료 |
| `ok` | bool | ✅ | API·파싱·저장 성공 |
| `skipped` | bool | ✅ | 한도 등으로 **의도적 미호출** |
| `skip_reason` | string | | `daily_limit_margin` 등 |
| `interval_minutes` | int | ✅ | 스케줄러 간격 (현재 5) |
| `period_minutes` | int | ✅ | API period (현재 10, max 10) |
| `zcode` | string | ✅ | `27` |
| `api_calls` | int | ✅ | 이번 틱 페이지 호출 수 |
| `calls_today` | int | ✅ | 당일 누적 호출 |
| `rows_returned` | int | | L2 행 수 (성공 시) |
| `snapshot_path` | string | | L2 상대 경로 |
| `error` | string | | 실패 메시지 |

### 현재 매핑

| 설계 | 현재 파일 |
|---|---|
| `collector_run` | `docs/data/loops/loop1/index.csv` |
| 상세/스킵 | `docs/data/loops/loop1/logs/call_log.jsonl` |
| 일 quota | `logs/daily_quota.json` |

### 다음 구현 (가벼운 정렬)

`index.csv`에 컬럼 추가(기존 유지 + append):

- `skipped` (bool)
- `skip_reason`
- `interval_minutes`

`call_log.jsonl`은 이미 `skipped`·`reason`을 가짐 → **정본 로그**, index는 조회용 요약.

### 의미 규칙

| `ok` | `skipped` | 의미 | L2 | 패널 ffill |
|---|---|---|---|---|
| true | false | 정상 폴링 | 있음(0행 가능) | 허용(조건 충족 시) |
| false | true | 한도 스킵 등 | 없음 | **금지** |
| false | false | 장애 | 없음/부분 | **금지** |

---

## 5. L2 — `status_snapshot_raw` (원본 변경분)

### 목적
- API가 준 그대로 보존 (불변)
- 재처리·감사·패널 재구성의 유일한 원천

### 스키마 (현재 CSV와 동일 유지)

| 컬럼 | 설명 |
|---|---|
| `statId` | 충전소 |
| `chgerId` | 충전기 |
| `stat` | EvCharger 상태 코드 |
| `statNm` | 상태명(참고) |
| `statUpdDt` | API 상태 갱신 시각 (`YYYYMMDDHHMMSS`) |
| `fetchedAt` | 우리 수집 시각 |
| `snapshotId` | = L1 `run_id` |
| `pageNo` | 페이지 |

경로: `docs/data/loops/loop1/snapshots/daegu_charger_status_{run_id}.csv`

### 규칙

1. **쓰기 후 수정 금지** (immutable)
2. `docs/data/extracted/` 에 status 루프가 쓰지 않음
3. 틱에 행이 0개여도 L1 `ok=true`이면 유효 (조용한 period)
4. 행이 있다고 해서 전수 함정 ≠ 그 시각 전체 함대

---

## 6. L3 — `status_event` (상태 변화 이벤트)

### 목적
- “언제 상태가 바뀌었는지”만 남김
- lastSeenAt 테이블과 달리 **전환 이력** 보존
- ETA·패널의 `is_observed` 근거

### 생성 규칙 (파생, 원본 비파괴)

충전기 키 = `statId|chgerId`.  
L2를 `snapshotId` 시간순으로 읽고, **직전 관측 `stat`과 다를 때만** 1행.

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `event_id` | string | `{run_id}|{statId}|{chgerId}` 또는 해시 |
| `statId` | string | |
| `chgerId` | string | |
| `stat` | int | 새 상태 |
| `prev_stat` | int\|null | 직전 관측 상태 (첫 관측이면 null) |
| `statUpdDt` | datetime | API 시각 |
| `observed_at` | datetime | `fetchedAt` 또는 snapshot 시각 |
| `run_id` | string | L1/L2 키 |
| `is_first_seen` | bool | 시리즈 첫 관측 |
| `source` | string | `loop1_change_feed` |

### 저장 (권장 경로)

```text
docs/data/loops/loop1/events/
  status_events_YYYYMMDD.csv          # 일별 append 또는
  status_events_latest.parquet        # 누적 뷰 (재생성 가능)
```

또는 `evaluation/results/datasets/status_events_*.parquet`  
→ **항상 L2에서 재생성 가능**해야 함 (파생 손실 허용).

### 하지 않는 것

- 성공 틱마다 전 충전기에 `unchanged` 이벤트 양산 (용량·의미 왜곡)
- 미관측을 `stat=0` 이벤트로 기록

---

## 7. L4 — serving (최신 뷰)

### 7.1 충전기 단위 `charger_status_latest` (신규 권장)

| 컬럼 | 설명 |
|---|---|
| `statId`, `chgerId` | PK |
| `stat` | 마지막 **관측** 상태 |
| `statUpdDt` | API 갱신 |
| `last_observed_at` | 마지막 L2 등장 시각 |
| `last_run_id` | 마지막 관측 틱 |
| `observation_age_minutes` | `now - last_observed_at` |
| `status_age_minutes` | `now - statUpdDt` |

**주의:** 이 테이블만으로는 “5분마다 폴링했는지” 알 수 없음 → 항상 L1과 조인.

### 7.2 충전소 단위 D1 (기존 유지)

`station_feature_snapshot` = L4 집계 + 정적·주차·돌발 피처.  
명세: [`데이터셋_명세.md`](../스키마/데이터셋_명세.md) §D1.

규칙 재확인:

- `available_count`: **관측된** 가용만
- `unobserved_rate`: 미관측 비율 (0으로 채우지 않음)
- `source_status`: `sandbox_series` / `loop1` 등

### 7.3 lastSeenAt 정책

| 허용 | 금지 |
|---|---|
| serving에서 `last_observed_at` 갱신 | serving만 남기고 L2 스냅샷 삭제 |
| D1 재빌드 시 L2 as-of 재계산 | serving의 age만으로 수집 성공 추정 |

---

## 8. 패널·ETA와의 연결

게이트 `feasibility` 패널 규칙과 동일:

```text
cell = observed        if 충전기가 이 run_id의 L2에 있음
cell = ffill(prev)     if L1.ok
                         and prev 관측 있음
                         and age ≤ max_hold (25분, 운영 합의)
cell = null            otherwise  # 사용불가 아님
```

| 플래그 | 출처 |
|---|---|
| `collection_success` | L1.ok && !skipped |
| `is_observed` | L2에 행 존재 |
| `is_imputed` | ffill |
| `observation_age_minutes` | now/panel_ts − last_observed |

ETA 15분 타깃: **L2 실관측**만으로 1/0, null 유지 ([게이트 보고서](../../보고/데이터타당성_게이트보고서_20260722.md) §5).

---

## 9. 파일·DB 배치 (단계)

### Phase A — 문서·매핑 (지금)

- [x] 본 설계서
- [x] 기존 loop1 ↔ L1/L2 매핑
- [ ] `데이터셋_명세.md`에 L1~L4 절 링크
- [ ] 게이트 보고서 §3.3 → 본 문서로 링크

### Phase B — L1 컬럼 정렬 (수집기 소수 변경)

- `index.csv` / `collect_status.py`에 `skipped`, `interval_minutes` 기록
- 스킵 틱도 **index에 1행** 남김 (지금은 call_log만일 수 있음 → 확인 후 보강)

### Phase C — L3 파생 스크립트

- `processing/build_status_events.py` (또는 evaluation)
- L2 전량 읽어 event parquet 생성 (재실행 가능)
- pytest: 전환만 기록 · 동일 stat 연속 관측은 이벤트 1회만

### Phase D — L4 charger_latest + D1 파이프 명시

- `build_charger_latest.py` ← L2 as-of
- 기존 `build_d1_snapshot.py` 입력으로 문서화

### Phase E — (선택) Postgres

이미 `load_status_panel_to_pg.py` 계열이 있으면:

| 테이블 | 층 |
|---|---|
| `collector_run` | L1 |
| `status_snapshot_raw` 또는 파일 포인터 | L2 |
| `status_event` | L3 |
| `station_feature_snapshot` | L4 D1 |

---

## 10. 의사코드 (L3 생성)

```python
# 의사코드 — 구현 시 L2 immutable 유지
events = []
last = {}  # key -> stat
for run_id in sorted(successful_runs):  # L1.ok
    for row in load_snapshot(run_id):   # L2
        key = (row.statId, row.chgerId)
        prev = last.get(key)
        if prev is None or prev != row.stat:
            events.append(Event(key, prev, row.stat, run_id, ...))
            last[key] = row.stat
# 동일 틱 중복 (statId,chgerId) 는 load 시 dedup
```

---

## 11. 검증 체크리스트

| ID | 검사 | 기대 |
|---|---|---|
| V1 | L1 `ok=false` 틱에 ffill 없음 | 패널 null |
| V2 | L2 파일 수정 시각이 생성 이후 불변 | mtime/해시 정책 |
| V3 | L3는 prev≠stat 만 | 단위 테스트 |
| V4 | D1 `available_count=0` ≠ 전수 미관측 | unobserved_rate 별도 |
| V5 | serving 삭제 후에도 L2로 D1 재생성 | 복구 드릴 |
| V6 | ETA 라벨 null 비율 보고 | 0으로 치환 없음 |

---

## 12. 책임 경계

| 담당 | 범위 |
|---|---|
| DA➀ | L1~L3 적재·파생, D1 입력 테이블, 패널·타당성 |
| DA➁ | D1/D2 소비, 점수·모델, ETA 라벨 최종 정의 합의 |
| 수집(공식 collection/) | 서비스 이관 시 합의 — 현재 loop1은 SANDBOX·loops 경로 |

---

## 13. 관련 문서

| 문서 | 관계 |
|---|---|
| [데이터타당성_게이트보고서_20260722.md](../../보고/데이터타당성_게이트보고서_20260722.md) | 공백 지적 · CONDITIONAL GO |
| [데이터셋_명세.md](../스키마/데이터셋_명세.md) | D1/D2 |
| [수집루프_쉬운설명.md](./수집루프_쉬운설명.md) | loop1 5분 운영 |
| [loops/loop1/README.md](../loops/loop1/README.md) | 경로 |
| `evaluation/feasibility/` | 패널·ETA 검증 코드 |

---

```
SSG-SAK  |  status 4-layer design  |  2026-07-22
L1 collector_run · L2 snapshot_raw · L3 event · L4 serving/D1
```
