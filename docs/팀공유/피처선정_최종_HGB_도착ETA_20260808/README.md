# 최종 피처 선정 — HGB × 도착 ETA 라벨

| 항목 | 내용 |
|---|---|
| **모델** | HistGradientBoosting (확정 기준) |
| **타겟** | `target_available_at_arrival` |
| **파생변수 추가** | **불필요** |
| **최종 피처 수** | 9 |
| **신뢰도 종합** | **WARN** (valid/test·seed는 PASS · 시간블록 CV만 경계) |
| **타당도 종합** | **PASS** |

> **신뢰도 WARN이 뭔지 쉽게:** [`신뢰도WARN_의미_쉽게읽기.md`](./신뢰도WARN_의미_쉽게읽기.md)  
> → 카드 WARN 원인(시간 블록 B1) · 타당성 WARN과의 차이 · 30초 멘트 · ② 인수인계 한 줄

## 1. 파생변수 필요 여부

| 파생 | 필요? | 근거(수치) |
|---|---|---|
| `single_charger` | **아니오** | LOO ΔPR-AUC = +0.000000 (사실상 0) · `total_chargers`가 흡수 |
| `eta_bucket` | **아니오** | 연속 `tmap_eta_min` 사용 · 구간화 이득 없음 |
| `avail_ratio_t0` | **아니오** | A+ vs A ΔPR-AUC ≈ +0.000007 |
| horizon+tmap+거리 동시 | **아니오** | D−B ΔPR-AUC = +0.0019 · 택1 계약 |

## 2. 최종 RETAIN 피처

```
available_count
total_chargers
known_charger_count
observation_coverage
hour
weekday
avail_rate_lag_15m
avail_rate_lag_60m
tmap_eta_min
```

- ETA family 확정: **`tmap_eta_min`** (실측 1848/1848 · horizon/haversine과 택1)
- 캘린더: `hour` + `weekday` (`is_weekend` 제외)
- 패널 래그: `avail_rate_lag_15m`, `avail_rate_lag_60m` 유지

## 3. 신뢰도 (reliability) 수치

| 지표 | 값 | 기준 | 판정 |
|---|---:|---|:---:|
| valid→test ΔPR-AUC | -0.0008 | \|Δ\|≤0.02 | PASS |
| valid→test Δneg-recall | -0.0068 | \|Δ\|≤0.05 | PASS |
| valid→test ΔBrier | +0.0071 | \|Δ\|≤0.03 | PASS |
| seed std PR-AUC | 0.00007 | <0.005 | PASS |
| seed std neg-recall | 0.00033 | <0.02 | PASS |
| block CV std PR-AUC | 0.02007 | <0.02 | WARN |
| eta_is_proxy rate | 0.0 | 0 권장 | PASS |

> 시간블록 WARN 원인: 초반 블록(7/17~7/24) PR-AUC 0.944 vs 후반 0.98대. 수집 초기 불안정이지 피처 세트 붕괴는 아님. valid↔test·seed는 모두 PASS.

최종셋 valid: PR-AUC **0.9821** · neg-recall **0.8405** · Brier **0.1532**  
최종셋 test: PR-AUC **0.9813** · neg-recall **0.8337** · Brier **0.1603**

## 4. 타당도 (validity) 수치

| 종류 | 수치/증거 | 판정 |
|---|---|:---:|
| 기준 타당도 (test) | PR-AUC 0.9813 · neg-recall 0.8337 · Brier 0.1603 | PASS |
| 구성 타당도 | 타겟=도착가용 · 충전성공 아님을 명시 | PASS(한계고지) |
| 수렴 타당도 | horizon 0.9807 / tmap 0.9821 / hav 0.9823 | PASS |
| 변별 타당도 | proxy·usage·주차점수·avail_ratio 제외 | PASS |
| 증분 타당도(파생) | single_charger·ratio·ETA스택 증분≈0 | **파생 불필요** |

## 5. 넣지 말 것

- `eta_is_proxy`, `eta_bucket`, `single_charger`, `is_weekend`, `avail_ratio_t0`
- usage / 주차 점수 / horizon+tmap+haversine 동시 투입
- accuracy로 모델 비교

## 보기용 BI

- **[`BI_대시보드.md`](./BI_대시보드.md)** ← 그림 모음
- 그림: `figures/`
- D: `D:/EV_SafeCharge_DA1/BI_피처선정_HGB_도착ETA_20260808/`

## 산출 경로

- `docs/data/analysis/hgb_arrival_eta_fitness_20260808/final_feature_selection.json`
- `docs/팀공유/피처선정_최종_HGB_도착ETA_20260808/`

```
DA① | final HGB feature selection | 20260808
```
