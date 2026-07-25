# loops 레이아웃 (일자 분류)

| 루프 | 역할 | 일자별 경로 |
|---|---|---|
| **loop1** | EvCharger status | `loop1/snapshots/YYYYMMDD/daegu_charger_status_*.csv` |
| **loop2** | UTIC 돌발 (PC) | `loop2/` (기존) |
| **loop3** | 대구 소통·돌발 | `loop3/YYYYMMDD/daegu_traffic_*.csv` |

- loop3 루트에만 `*_latest.csv` 포인터 유지
- 재정리: `python apps/data-pipeline/processing/analysis/organize_loops_by_date.py`
- pull은 일자 폴더로 merge (`scripts/pull_lightsail_loops.ps1`)

```
DA① | loops by date | 20260725
```
