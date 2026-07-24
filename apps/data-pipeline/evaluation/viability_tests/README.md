# DA➀ 타당성(GO/NO-GO) 테스트

단위 테스트(`evaluation/tests/`)와 **분리**.  
여기는 “이 데이터로 MVP 목표를  Mil 수 있나 / 폐기 검토인가”만 본다.

| 파일 | 대상 | 결과 |
|---|---|---|
| `test_status_go_nogo_viability.py` | status 시계열 | `results/go_nogo/status_viability_latest.md` |
| `test_utic_incident_go_nogo_viability.py` | UTIC 돌발 | `results/go_nogo/utic_viability_latest.md` |
| `analyze_status_panel.py` | D2 시계열 패널 분석 | `results/status_panel_analysis/` |
| `../processing/db/load_status_panel_to_pg.py` | D2→Postgres (DBeaver) | `docs/data/API/DBeaver_테스트DB.md` |
| `run_all_viability.py` | GO/NO-GO 전부 | `results/go_nogo/viability_all_latest.md` |

```bash
# 하나씩
python apps/data-pipeline/evaluation/viability_tests/test_status_go_nogo_viability.py
python apps/data-pipeline/evaluation/viability_tests/test_utic_incident_go_nogo_viability.py

# 전부
python apps/data-pipeline/evaluation/viability_tests/run_all_viability.py
```

exit **2** = 해당 트랙 재료 실패(status면 프로젝트 kill 검토, UTIC면 돌발 트랙 실패).

기존 `evaluation/tests/test_status_go_nogo_viability.py`는 여기로 **리다이렉트**만 남김.
