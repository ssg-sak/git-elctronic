# 실데이터 확장 (대기) — AI·데이터 ①

| 항목 | 내용 |
|---|---|
| **상태** | ⏸ **대기** — 지금 파이프라인 전환하지 않음 |
| **예정 ID** | EXP-017 |
| **범위** | 전처리·공간결합·품질 (점수·ETA 서빙은 ②) |

## 원천만 보관 (이미 있음)

파이프라인에 **연결하지 않은** 원천 CSV:

| 파일 | 비고 |
|---|---|
| `docs/data/extracted/daegu_traffic_incident_stats_20260717_194546.csv` | odcloud 돌발 · 좌표 O · 과거 이력 |
| `docs/data/extracted/daegu_traffic_link_hourly_stats_20260717_194730.csv` | odcloud 링크 속도 · **좌표 없음** |
| `docs/data/extracted/daegu_traffic_control_20260717_194730.csv` | odcloud 통제 |
| (미확보) 주차 실API | `.env` pis 키 + IP 화이트리스트 후 추출 |

## 할 일 (체크리스트 — 실행은 나중)

- [ ] 링크 지오코딩 → lat/lng
- [ ] odcloud → 전처리 스키마 어댑터 (mock과 분리)
- [ ] 주차 실추출 → 조인·품질 보고
- [ ] 매칭 성공률·실패 목록 기록
- [ ] EXP-017 보고서 → [`../compare_1vs2/`](../compare_1vs2/)

## 하지 말 것

- `docs/data/extracted/` 덮어쓰기
- 점수·Top-N·추천 이유·ML 실험 (②)
- 지금 당장 운영 전처리 경로를 실데이터로 강제 전환
