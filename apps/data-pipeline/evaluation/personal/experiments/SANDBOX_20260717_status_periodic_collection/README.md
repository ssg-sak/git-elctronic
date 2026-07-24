# SANDBOX_20260717_status_periodic_collection

**격리된 status 주기 수집 샌드박스.**  
메인 `collection/` · `docs/data/extracted/` 와 분리한다.

**소유**: AI·데이터 ① 파이프라인 (학습·EDA·특성용 시계열).  
**비소유**: 공식 수집기(`apps/data-pipeline/collection/`) — 이 SANDBOX가 대체하거나 덮어쓰지 않는다.

## ⚠ 주의사항 (필수)

1. **`docs/data/extracted/` 덮어쓰기 금지** — 타임스탬프 스냅샷만 적재  
2. **본 SANDBOX 경로만 사용** — `collection/` 코드·경로 수정 금지  
3. **일 호출 한도(1000) + 마진** — 공식 수집과 키·한도를 공유하므로 근접 시 회차 스킵  
4. **서비스 이관 시** — `collection/` 담당과 합의 후 이전

상세: [`../EXP-012_20260717_status주기수집_시작.md`](../EXP-012_20260717_status주기수집_시작.md)  
**학습서 (왜 중요한지):** [`LEARNING_GUIDE_status주기수집.md`](./LEARNING_GUIDE_status주기수집.md)

## 왜 하는가

단일 시점 status(커버리지 ~2.34%)만으로는 LightGBM 라벨·시계열 피처를 만들 수 없다.  
공식 수집을 대체하는 것이 아니라, **파이프라인용 시계열 재료**를 SANDBOX에만 쌓는다.

## interval vs period (다른 개념)

| | interval | period |
|---|---|---|
| **누가** | 우리 `run_loop.py` | EvCharger API |
| **의미** | 몇 분마다 호출·저장 | 최근 N분 **상태 변경분**만 응답 |
| **초기값** | 15 | 20 |

`period=20` ≠ 20분마다 수집. **15분마다 호출하고, 매번 최근 20분 변경분을 받는다.**

## API 한도

1회 실측 ≈ 5 calls. 5분×5 = 일 1,440 → 한도(1000) 초과 위험.  
**24h 운영(Lightsail): 10분 간격** (≈720 calls/day). PC에서는 돌리지 말 것.

## 실행

```bash
cd git-elctronic
python apps/data-pipeline/evaluation/personal/experiments/SANDBOX_20260717_status_periodic_collection/src/collect_once.py
python apps/data-pipeline/evaluation/personal/experiments/SANDBOX_20260717_status_periodic_collection/src/run_loop.py --interval-minutes 15 --period-minutes 20

# 가동 현황 요약
python apps/data-pipeline/evaluation/personal/experiments/SANDBOX_20260717_status_periodic_collection/src/summarize_run.py

# 전날 일일 점검 수동 재생성 (평소에는 다음 날 첫 수집 때 자동 생성)
python apps/data-pipeline/evaluation/personal/experiments/SANDBOX_20260717_status_periodic_collection/src/daily_checkpoint.py --date 2026-07-18 --force
```

출력: `data/snapshots/daegu_charger_status_YYYYMMDD_HHMMSS.csv`

## 일일 자동 점검

다음 날 첫 수집이 성공하면 전날 데이터를 자동 점검한다. 점검 실패가 발생해도
수집 루프는 중단하지 않고 오류만 출력한다.

출력(샌드박스 밖 자동 산출물 전용 폴더):
`apps/data-pipeline/evaluation/results/status_daily/YYYY-MM-DD/`

- `daily_checkpoint.json` — 자동 처리용 지표
- `daily_checkpoint.md` — 읽기용 보고서
- `daily_checkpoint.png` — 공유용 시각자료

점검 내용: 수집 회차·공백·API 사용량·결측·중복·누적 반복 관측 깊이·
공백 안전 패널 가용률.
