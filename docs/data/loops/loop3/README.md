# loop3 — 대구 ITS 소통·돌발 (15분)

| | |
|---|---|
| **API** | `linkspeed` · `dgincident` (`DATA_GO_KR_KEY`) |
| **루프** | `python apps/data-pipeline/processing/loops/run_daegu_traffic_loop.py --interval-minutes 15` |
| **보고** | [`../교통소통_데이터_보고.md`](../../품질보고/교통소통_데이터_보고.md) |

| 파일 | 내용 |
|---|---|
| `daegu_traffic_linkspeed_*.csv` | 소통 **1,960 링크** |
| `daegu_traffic_incident_*.csv` | dgincident 돌발 |
| `daegu_traffic_meta_*.json` | 메타 |

**이전 폴더명:** `daegu_traffic/`
