# Status 스냅샷 정리 (17일~오늘)

| | |
|---|---|
| **담당** | AI·데이터 ① |
| **작성** | 2026-07-22 |
| **한 줄** | 루프 CSV가 **정본**. `extracted` status는 **단발 샘플**일 뿐. |

---

## 바로 찾기 (이 PC 절대 경로)

탐색기 주소창에 붙여넣기:

```
C:\Users\PC\Desktop\electronic-aimodel\git-elctronic\apps\data-pipeline\evaluation\personal\experiments\SANDBOX_20260717_status_periodic_collection\data\snapshots
```

| 뭐 | 절대 경로 |
|---|---|
| **정본 폴더** (CSV 323개) | `C:\Users\PC\Desktop\electronic-aimodel\git-elctronic\apps\data-pipeline\evaluation\personal\experiments\SANDBOX_20260717_status_periodic_collection\data\snapshots` |
| **회차 목록** | `...\data\index.csv` |
| **일자 표** | `...\data\inventory\status_inventory_by_day.csv` |
| **파일 전체 목록** | `...\data\inventory\status_inventory_files.csv` |
| **단발 샘플** (비정본) | `C:\Users\PC\Desktop\electronic-aimodel\git-elctronic\docs\data\extracted\daegu_charger_status_20260717_194107.csv` |

Cursor에서: `Ctrl+P` → `status_inventory_by_day` 또는 `daegu_charger_status_20260722`

---

## 어디에 있나?

| 구분 | 경로 | 쓰는 곳 |
|---|---|---|
| **정본 (루프)** | `apps/data-pipeline/evaluation/personal/experiments/SANDBOX_20260717_status_periodic_collection/data/snapshots/` | D1 빌드 · 일일 점검 · 패널 |
| **목록** | 같은 샌드박스 `data/index.csv` | 회차·행수·호출수 |
| **일자 요약** | 같은 샌드박스 `data/inventory/` | 이 문서와 함께 보는 표 |
| **단발 (비정본)** | [`extracted/daegu_charger_status_20260717_194107.csv`](./extracted/daegu_charger_status_20260717_194107.csv) | 구경·샘플만. **D1에 넣지 않음** |

```text
docs/data/extracted/     ← 단발 추출 (info·tour 등과 함께 둠)
        └── status 1개   ← 루프와 섞지 말 것

SANDBOX_.../data/snapshots/   ← 10분마다 쌓이는 정본 (flat, 날짜 폴더 없음)
```

파일을 `YYYYMMDD/` 폴더로 옮기지 **않는다**.  
수집·로더·D1이 `snapshots/*.csv` flat glob을 가정한다.

---

## 2026-07-17 ~ 07-22 일자표

인벤토리 CSV:  
`.../SANDBOX_.../data/inventory/status_inventory_by_day.csv`

| 날짜 | 회차 | 첫 스냅샷 | 끝 스냅샷 | 행수 중앙값 | index=디스크 |
|---|---:|---|---|---:|---|
| 07-17 | 33 | 13:41 | 21:40 | 521 | 일치 |
| 07-18 | 62 | 07:20 | 22:36 | 502.5 | 일치 |
| 07-19 | 55 | 07:49 | 21:02 | 455 | 일치 |
| 07-20 | 64 | 08:14 | 22:41 | 453.5 | 일치 |
| 07-21 | 72 | 08:30 | 22:53 | 452.5 | 일치 |
| 07-22 | 37+ | 08:18 | (수집 중) | 450 | 일치 |
| **합** | **323** | | | | |

야간·PC 꺼짐 구간은 회차가 비는 것이 정상이다 (아래 검증 gaps).

---

## 이번 정리에서 한 일

1. **디스크 ↔ index 대조** → 일치하도록 맞춤  
   - `20260720_161548` 가 index에 **2줄** 들어가 있던 중복 제거 (raw CSV는 손대지 않음)  
   - 백업: `data/index.csv.bak_dedup`
2. **일자별 inventory** 생성 (`data/inventory/`)
3. **`validate_collection.py --write-report`** 실행

---

## 검증 결과 (2026-07-22)

보고서: `.../data/logs/validation_report.json`

| 항목 | 결과 |
|---|---|
| 스냅샷 파일 | **323** 전부 읽힘 |
| index 교차검증 | disk=index, 고아/누락 **0** |
| 키 컬럼 null | **0** |
| 잘못된 stat 코드 | **0** |
| 누적 유니크 충전기 | **16,706** |
| 스냅샷 내 (statId,chgerId) 중복 | 일부 회차에 있음 (읽기 시 dedup) |
| 큰 gap | 주로 **야간** (PC off). 주간 2건(~15:00대, 7/20·7/21) |

> 검증 스크립트의 “기대 간격 15분”은 초창기 설정 기준. 현재 루프는 **10분**. gap 숫자는 “밤새 꺼짐”을 과대 집계할 수 있다.

---

## 다시 요약 뽑기

```bash
# 검증
python apps/data-pipeline/evaluation/personal/experiments/SANDBOX_20260717_status_periodic_collection/src/validate_collection.py --write-report

# 일자표는 inventory CSV 참고 (재생성 시 동일 경로에 덮어씀)
```

쉬운 루프 설명: [`수집루프_쉬운설명.md`](./수집루프_쉬운설명.md)

## 타당성 테스트 (폐기 여부)

폴더: `apps/data-pipeline/evaluation/viability_tests/`

```bash
python apps/data-pipeline/evaluation/viability_tests/run_all_viability.py
```

결과: `apps/data-pipeline/evaluation/results/go_nogo/`

```
DA➀ | status snapshot inventory 17-22 | 2026-07-22
```
