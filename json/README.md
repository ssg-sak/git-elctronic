# json/ — 실험용 목데이터 (공식 가이드)

| 파일 | 용도 |
|---|---|
| `stations.json` | 충전소 단위 특성 (DA➀·DA➁) |
| `charger-status-history.json` | 상태 이력 이벤트 (DA➀ 전처리 입력) |
| `station-detail-MOCK-ST001.json` | 충전기 단위 구조 샘플 |
| `recommendations.json` | 추천 출력 규격 샘플 (DA➁) |

**트랙:** 실험(목) — 실진행 D1과 분리.  
분류표: [`docs/data/운영/실데이터_목데이터_트랙.md`](../docs/data/운영/실데이터_목데이터_트랙.md)  
정본: [`docs/데이터파트_작업가이드.md`](../docs/데이터파트_작업가이드.md)

실수집 연결: `python apps/data-pipeline/processing/export_history_json.py` → 동일 스키마로 덮어쓰기.
