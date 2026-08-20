# processing/tools — 공유·정리 유틸

핵심 파이프라인과 섞지 않기 위한 자리. 일회성 팩킹·스크랩 스크립트는 **삭제됨**.

## `share/` (남은 것만)

| 스크립트 | 용도 |
|---|---|
| `archive_team_share.py` | 팀공유 오래된 stamp 정리 |
| `archive_analysis_final.py` | analysis stamp 정리 |
| `copy_availability_share.py` | 가용률 차트 → 팀공유 |
| `copy_status_panel_share.py` | 상태 패널 차트 → 팀공유 |

```bash
python apps/data-pipeline/processing/tools/share/copy_availability_share.py
python apps/data-pipeline/processing/tools/share/archive_team_share.py
```
