# processing/tools — 일회성·공유·추출 스크립트

핵심 파이프라인(`processing/features`, `core`, D1/D2 빌더)과 **섞지 않기** 위한 자리.

| 폴더 | 넣을 것 | 넣지 말 것 |
|---|---|---|
| `share/` | 팀 zip 팩, 신축 대조, 사례 스크랩, 바탕화면 묶음 | D1/D2 빌드, KPI 정본 리포트 |
| (추후) `probes/` | 피처 유의성·수수료 탐침 등 실험 | 운영 스케줄 잡 |

## 실행 예

```bash
python apps/data-pipeline/processing/tools/share/pack_coverage_gap_unified.py
python apps/data-pipeline/processing/tools/share/pull_new_apt_charger_pack.py
```

`analysis/` 아래 옛 경로에 stub이 있으면 리다이렉트만 한다. 새 스크립트는 여기로 추가.
