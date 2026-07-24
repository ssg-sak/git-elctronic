# Phase 구조 (실험 로드맵) — AI·데이터 ①

① 범위: 전처리·품질·EDA·특성·데이터셋·status 시계열 수집.  
점수·규칙 추천·ML·평가는 **AI·데이터 ②** (이 로드맵에 포함하지 않음).

```text
[전처리·품질 baseline] ──→ [status 시계열 누적] ──→ [특성·데이터셋]
```

| 단계 | 폴더 | 상태 | 지금 할 일 |
|---|---|---|---|
| **전처리** | [`SANDBOX_20260716_preprocess_pipeline/`](./SANDBOX_20260716_preprocess_pipeline/) | ✅ | 전처리·품질만 유지 |
| **status** | [`SANDBOX_20260717_status_periodic_collection/`](./SANDBOX_20260717_status_periodic_collection/) | 🚀 가동 | 15분 수집·일일 점검 |
| **실데이터 확장** | [`phase2_realdata/`](./phase2_realdata/) | ⏸ 대기 | 주차·교통 실데이터 등 (파이프라인 연결 시) |
| **비교** | [`compare_1vs2/`](./compare_1vs2/) | ⏸ 대기 | 데이터 품질·커버리지 비교 (모델 비교 아님) |

## 데이터 역할

| 위치 | 역할 |
|---|---|
| `docs/data/extracted/*_mock.csv` | 스키마·조인 검증용 mock |
| `docs/data/extracted/daegu_traffic_*_20260717_*.csv` | 원천 보관, 파이프라인 미연결 |
| `docs/data/extracted/daegu_charger_*` 등 실추출 | 전처리·EDA 입력 |
| status SANDBOX snapshots | 특성·학습용 시계열 재료 (②에 넘길 입력) |

## 예약 EXP

| ID | 제목 | 시점 |
|---|---|---|
| EXP-017 | 실데이터 전처리·공간결합 확장 | phase2 시작 시 |
| EXP-018 | 데이터 품질·커버리지 비교 | 확장 완료 후 |
