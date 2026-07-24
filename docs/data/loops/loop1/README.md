# loop1 — EvCharger status (5분)

| | |
|---|---|
| **API** | `getChargerStatus` (data.go.kr / `DATA_GO_KR_KEY`) |
| **루프** | `python .../SANDBOX_20260717_status_periodic_collection/src/run_loop.py --interval-minutes 5 --period-minutes 10` |
| **설계** | 타당성 게이트(2026-07-22) 권고 — interval **5분** · API period **10분**(변경분 창, max 10) |

| 하위 | 내용 |
|---|---|
| `snapshots/` | 틱별 불변 CSV `daegu_charger_status_YYYYMMDD_HHMMSS.csv` |
| `daily/` | 일별 롤업 |
| `logs/` | API 콜·quota (일 1,000건 한도 · margin 50) |
| `index.csv` | 스냅샷 인덱스 |

**이전 위치:** `SANDBOX_20260717_status_periodic_collection/data/` → 여기로 통합.

**4층 설계:** [`status_4층_저장설계.md`](../../운영/status_4층_저장설계.md)  
(이 폴더 = L1 index/logs + L2 snapshots)
