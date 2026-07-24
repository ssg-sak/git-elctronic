# loop2 — UTIC 돌발 (15분)

| | |
|---|---|
| **API** | 경찰청 UTIC (`UTIC_API_KEY`) |
| **루프** | `python apps/data-pipeline/processing/loops/run_utic_loop.py --interval-minutes 15` |
| **조인** | `join_utic_incident.py` → `../spatial_join/` |

| 파일 | 내용 |
|---|---|
| `daegu_traffic_incident_utic_*.csv` | 대구 필터 돌발 |
| `daegu_traffic_incident_utic_latest.csv` | 최신 |
| `utic_incident_meta_*.json` | 메타 |

**이전 폴더명:** `utic/`
