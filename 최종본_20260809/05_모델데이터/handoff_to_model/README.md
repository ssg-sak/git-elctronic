# ① → ② 핸드오프 패키지

| 항목 | 내용 |
|---|---|
| **제공** | AI·데이터 ① |
| **수신** | AI·데이터 ② (모델·평가·서빙) |
| **스키마** | `station_feature_v1` |
| **명세** | `docs/data/스키마/데이터셋_명세.md` · `피처_카탈로그.md` |
| **status** | SANDBOX 시계열 as-of 갱신 (`source_status=sandbox_series`) |

## 포함 파일

- `station_feature_snapshot_sample_30.csv` — 샘플 30행
- `HANDOFF_META.json` — 행수·정책·경로
- 전체: `station_feature_snapshot_20260809_080127.csv`
- 항상 최신 포인터: `station_feature_snapshot_latest.csv`

## 반드시 읽을 정책

1. **미관측 ≠ 사용 불가** — `unobserved_rate`, `availability_ratio_observed`(관측 0이면 null)
2. **mock / 소스 플래그** — `parking_is_mock=false` · `parking_source=team5_pis` (1km 조인; 미매칭 null) · `traffic_is_mock`/`traffic_source` (UTIC면 `utic`)
3. **`eta_minutes`** — ①은 null 예약, TMAP/백엔드 채움
4. **점수·위험도·추천 이유** — ② 영역 (이 테이블에 없음)
5. **status** — 충전기별 `statUpdDt ≤ as_of_ts` 최신 관측 + `observation_age`/`reliability_grade_effective` (이중 신선도)
6. **가짜 거리 금지** — parking mock 폐기; team5 실조인만 D1에 반영

생성 시각: 2026-08-09T07:23:21+09:00
관측 충전기: 21368 / 마스터 25368
