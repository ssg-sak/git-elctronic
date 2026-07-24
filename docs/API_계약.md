# 추천 API 계약 (DA➁ · 백엔드)

| | |
|---|---|
| **정본 가이드** | [`데이터파트_작업가이드.md`](./데이터파트_작업가이드.md) |
| **타입** | [`packages/shared-types/src/index.ts`](../packages/shared-types/src/index.ts) |
| **목 출력 샘플** | [`json/recommendations.json`](../json/recommendations.json) |
| **점수 가중치** | [`packages/recommendation-core/src/index.ts`](../packages/recommendation-core/src/index.ts) · 루트 `AGENTS.md` |

---

## 1. 추천 요청 (개요)

| 필드 | 타입 | 설명 |
|---|---|---|
| `userLat` | number | 사용자 위도 |
| `userLng` | number | 사용자 경도 |
| `asOf` | ISO8601 | 기준시각 (KST) |
| `topN` | number | 반환 개수 (기본 5) |

> 상세 HTTP 경로·인증은 백엔드(`apps/api/`)와 합의 후 본 문서에 추가.

---

## 2. 추천 응답 (개요)

`StationRecommendation[]` — [`shared-types`](../packages/shared-types/src/index.ts)

| 필드 | 설명 |
|---|---|
| `station` | 충전소·충전기 목록 |
| `score` | 0~100 종합 점수 (DA➁ 산출) |
| `failureRisk` | `낮음` / `보통` / `높음` |
| `reliability` | `높음` / `보통` / `확인필요` — **DA➀ `reliability_grade_effective` 권장** |
| `travelTimeSec` | TMAP 등 ETA |
| `reason` | 추천 이유 문장 (DA➁) |

---

## 3. DA➀ 입력 (특성 스냅샷)

행 단위: **충전소 1행 × as_of_ts**

| 파일 | 설명 |
|---|---|
| `station_feature_snapshot_latest.csv` | D1 — [`데이터셋_명세.md`](./data/스키마/데이터셋_명세.md) |
| `station_feature_panel_*.parquet` | D2 시계열 |

DA➁은 D1/D2를 읽어 점수·추천을 생성하고, 출력은 `recommendations.json` 규격에 맞춘다.

---

## 4. 변경 절차

스키마·타입 변경 시 **DA➀ ↔ DA➁ ↔ 백엔드** 3자 합의 후:

1. `데이터셋_명세.md` / `피처_카탈로그.md`
2. `packages/shared-types`
3. 본 문서
