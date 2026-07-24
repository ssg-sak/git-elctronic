# Missing Value Policy

## 복원 (join / rule)

| 항목 | 방법 |
|---|---|
| status `statNm` | info `statId+chgerId` 조인 복원 |
| 주차 전일운영 + 시간 공백 | `00:00`/`24:00` **파생** (원본 결측 보존) |
| Tour 한글 깨짐 | 깨진 행만 latin1→utf-8 복구 시도, `encoding_repaired` 기록 |

## 유지 (추정 금지)

| 항목 | 처리 |
|---|---|
| status 미수집 | `status_missing=True` / `NO_STATUS_OBSERVED` — **사용불가 아님** |
| output 결측 | `output_missing=True` — 평균·유형 최빈값 대체 금지 |
| useTime 결측 | `operation_time_known=False` — 24시간 가정 금지 |
| parkingFree 결측 | `UNKNOWN` |
| 주차 실시간 없음 | `realtime_status=UNKNOWN` — 만차/혼잡 대체 금지 |
| 공원 roadNmAddr | 행 삭제 금지, `address_source=LOT` |
| city_tour email / Tour tel | 피처 제외 가능, 원본 보존 |
| 기상 코드형 SKY/PTY | 범주 유지 |

## 제외

| 항목 | 이유 |
|---|---|
| `*(1).csv` 교통 mock 복사본 | 내용 동일 중복 |
| city_tour 좌표 | 없음 → 임의 생성 금지, 지오코딩 대기 테이블 분리 |
| 도착시 예측 모델 학습 | 단일 스냅샷 — status 시계열 추가 수집 필요 |

## 격리

| 항목 | 위치 |
|---|---|
| 좌표 품질 이상 충전기 | `data/quarantine/charger_coordinate_suspects.*` (삭제 아님) |
