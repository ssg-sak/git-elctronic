# loops/ — 주기 수집(루프) 데이터

단발 추출(`../extracted/`)과 **섞지 않는다.**

| 루프 | 폴더 | 별칭 | 내용 | 주기 | 스크립트 |
|---|---|---|---|---|---|
| **loop1** | `loop1/` | **status** | EvCharger **status** 스냅샷 | 5분 | `SANDBOX_.../src/run_loop.py` |
| **loop2** | `loop2/` | **utic** | UTIC **돌발** | 15분 | `processing/loops/run_utic_loop.py` |
| **loop3** | `loop3/` | **daegu_traffic** | 대구 ITS **소통·돌발** | 15분 | `processing/loops/run_daegu_traffic_loop.py` |

경로 정본: `apps/data-pipeline/loop_paths.py`

서버 풀·테스트 복사본: [`_archive/`](_archive/) (라이브 `loop1`~`3` 과 분리)

조인 결과(충전소↔돌발)는 `../spatial_join/` 에 둔다.

쉬운 설명: [`../수집루프_쉬운설명.md`](../운영/수집루프_쉬운설명.md)
