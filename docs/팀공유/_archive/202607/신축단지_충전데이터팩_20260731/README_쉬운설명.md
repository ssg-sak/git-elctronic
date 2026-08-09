# 신축단지 충전 데이터 팩 (20260731)

## 이게 다니? (2025)
- **공식 전수 명단은 아님.** 부동산 입주 정리 블로그 표(약 9,291세대)에 맞춘 **모니터링 시드**.
- 출처마다 단지가 조금씩 다름 (일정 변경·오피스텔 포함 여부).
- 이번 시드 2025: **22개 단지** (죽전행복주택·영대 오피스텔 포함해 이전 20개보다 보강).

## 2026도 넣어야 하나?
- **넣어야 함 (모니터링용).** 입주 전이라도 충전기가 먼저 등록될 수 있고, 입주 직후 등록 지연도 볼 수 있음.
- 다만 지금은 **MISSING이 정상인 구간**이 많을 수 있음. ‘미반영=버그’로 단정하지 말 것.
- 이번 시드 2026: **9개 단지** (범어자이·대명자이 등).

## 이름 매칭 결과
- FOUND_NAME: 0
- POSSIBLE_RELATED: 0
- MISSING_IN_INFO: 31

## 단지별 요약 (발췌)
| 단지 | 입주 | 판정 | 500m내 충전소 |
|---|---|---|---:|
| 두류역서한포레스트 | 2025-01 | MISSING_IN_INFO | 14 |
| 수성포레스트스위첸 | 2025-01 | MISSING_IN_INFO | 4 |
| 더센트럴화성파크드림 | 2025-01 | MISSING_IN_INFO | 27 |
| 이안엑소디움에이펙스 | 2025-02 | MISSING_IN_INFO | 18 |
| 화성파크드림구수산공원 | 2025-02 | MISSING_IN_INFO | 20 |
| 빌리브루센트 | 2025-03 | MISSING_IN_INFO | 17 |
| 대구역자이더스타 | 2025-04 | MISSING_IN_INFO | 17 |
| 힐스테이트대구역퍼스트 | 2025-05 | MISSING_IN_INFO | 20 |
| 힐스테이트대구역퍼스트2차 | 2025-05 | MISSING_IN_INFO | 20 |
| 힐스테이트동인 | 2025-05 | MISSING_IN_INFO | 15 |
| 빌리브라디체 | 2025-06 | MISSING_IN_INFO | 21 |
| 해링턴플레이스감삼3차 | 2025-07 | MISSING_IN_INFO | 18 |
| 태왕디아너스오페라 | 2025-07 | MISSING_IN_INFO | 29 |
| 힐스테이트서대구역센트럴 | 2025-07 | MISSING_IN_INFO | 5 |
| 두류스타힐스 | 2025-07 | MISSING_IN_INFO | 11 |
| 두류역자이 | 2025-08 | MISSING_IN_INFO | 11 |
| 대구죽전행복주택 | 2025-09 | MISSING_IN_INFO | 17 |
| 더팰리스트데시앙 | 2025-10 | MISSING_IN_INFO | 27 |
| e편한세상동대구역센텀스퀘어 | 2025-11 | MISSING_IN_INFO | 27 |
| 더샵동성로센트리엘 | 2025-11 | MISSING_IN_INFO | 22 |
| 영대병원역골드클래스센트럴오피스텔 | 2025-11 | MISSING_IN_INFO | 14 |
| 달서롯데캐슬센트럴스카이 | 2025-12 | MISSING_IN_INFO | 21 |
| 범어자이 | 2026-02 | MISSING_IN_INFO | 27 |
| 힐스테이트대명센트럴2차 | 2026-02 | MISSING_IN_INFO | 14 |
| 힐스테이트칠성더오페라 | 2026-02 | MISSING_IN_INFO | 17 |
| 달서푸르지오시그니처 | 2026-03 | MISSING_IN_INFO | 37 |
| 대구역센트레빌더오페라 | 2026-04 | MISSING_IN_INFO | 24 |
| 대명자이그랜드시티 | 2026-04 | MISSING_IN_INFO | 14 |
| 힐스테이트동대구센트럴 | 2026-04 | MISSING_IN_INFO | 27 |
| 벤처밸리푸르지오 | 2026-04 | MISSING_IN_INFO | 27 |
| 더샵달서센트엘로 | 2026-06 | MISSING_IN_INFO | 21 |

## 폴더
- `complex_charger_summary.csv` — 한눈에
- `per_complex/<id>/` — 단지별 info매칭·인근·D1
- `all_nearby_stations_500m.csv` — 인근 통합
- `daegu_movein_seed_2025_2026.csv` — 시드

## 해석
- 이름 MISSING ≠ 인근에 충전기 없음 (반경 검색으로 보완).
- 반경 충전소 ≠ 단지 내부 충전기.
- MVP는 관측 가능 EvCharger 기준 유지.
