"""Run full timeseries feasibility gate and write reports."""
from __future__ import annotations

import json
import sys
import traceback
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .backtest import run_backtest
from .eta_targets import run_eta_targets
from .inventory import run_inventory
from .panel_restore import run_panel_restore
from .paths import EXP_DIR, OUT_JSON, OUT_ROOT, ensure_out
from .status_quality import run_status_quality
from .usage_eda import run_usage_eda
from .verdict import run_verdict

KST = ZoneInfo("Asia/Seoul")


def _write_exps(bundle: dict, verdict: dict) -> list[str]:
    ensure_out()
    EXP_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now(tz=KST).strftime("%Y-%m-%d")
    sq = bundle.get("status_quality") or {}
    panel = bundle.get("panel_restore") or {}
    eta = bundle.get("eta_targets") or {}
    usage = bundle.get("usage_eda") or {}
    bt = bundle.get("backtest") or {}
    inv = bundle.get("inventory") or {}

    files: list[str] = []

    def dump(name: str, body: str) -> None:
        path = EXP_DIR / name
        path.write_text(body, encoding="utf-8")
        files.append(str(path).replace("\\", "/"))

    dump(
        "EXP-011_20260722_5분상태수집_연속성품질검증.md",
        f"""# EXP-011 | 5분 상태 수집 연속성·품질 검증

```
SSG-SAK  |  이현석  |  EXP-011  |  {today}
```

## 실험 정보

| 항목 | 내용 |
|---|---|
| 실험 ID | EXP-011 |
| 날짜 | {today} |
| 목적 | 상태 수집이 5분 설계를 만족하는지, 공백·중복·시각 이상·성공/실패 구분이 되는지 검증 |
| 가설 | loop1 변경분 피드 + call_log로 수집 성공은 구분 가능하나, 5분 준수율은 낮고 충전기 단위 unchanged 확인 행은 없다 |
| 데이터 범위 | loop1 snapshots + index + call_log (실데이터) |

## 입력 (전 소스)

| 데이터 | 구분 | 경로/건수 | 본 실험에서 |
|---|---|---|---|
| status loop1 | 실 | snapshots={sq.get('n_snapshots')} · events={sq.get('event_rows')} | 사용 |
| call_log/index | 실 | loop1/logs, index.csv | 사용 |
| 일별 이용 | 실 | N/A | N/A |
| 주차 | mock | extracted | N/A |

## 방법

```bash
python -m apps.data-pipeline.evaluation.feasibility.run_all
# or: python apps/data-pipeline/evaluation/feasibility/run_all.py
```

## 결과

| 지표 | 값 |
|---|---|
| 기간 | {sq.get('first_ts')} → {sq.get('last_ts')} |
| 캘린더 일수 | {sq.get('n_calendar_days')} |
| gap median (분) | {(sq.get('gap_distribution') or {}).get('median_min')} |
| ≤5.5분 준수율 | {(sq.get('gap_distribution') or {}).get('pct_le_5_5min')} |
| ≤10.5분 준수율 | {(sq.get('gap_distribution') or {}).get('pct_le_10_5min')} |
| ≥30분 공백 비율 | {(sq.get('gap_distribution') or {}).get('pct_ge_30min')} |
| API 성공률 | {sq.get('api_success_rate')} |
| 최대 연속 실패 | {sq.get('max_consecutive_failures')} |
| 관측 충전기 수 | {sq.get('unique_chargers_observed')} |
| 스냅샷 내 중복률 | {sq.get('within_snapshot_dup_rate')} |
| 시간 역전 건수 | {sq.get('time_reversal_count')} |

### 설계 판정

- 수집 성공/실패: **구분 가능** (`index.ok`, `call_log.jsonl`)
- 상태 유지 vs 미관측: **충전기 단위로는 부분적** — 성공 틱에서 미반환은 period 변경분 의미이지 전수 스냅샷이 아님
- lastSeenAt-only serving: 이력 소실 위험 **있음** (현재는 틱별 CSV로 변경 이력 보존)

## 해석

- 운영 간격은 설계 5분이 아니라 **약 10분** 중심이다.
- 미관측을 사용불가로 채우면 안 된다 (본 검증도 채우지 않음).
- 치명적 설계 공백: unchanged 확인 행 없음 → `collection_log + event + serving` 분리 유지 필요.

## 산출물

| 파일 | 경로 |
|---|---|
| JSON | `apps/data-pipeline/reports/timeseries_feasibility/json/status_quality.json` |
| 표 | `.../tables/status_tick_gaps.csv` 등 |
| 그림 | `.../figures/status_gap_hist.png` |

```
SSG-SAK  |  EXP-011  |  {today}
```
""",
    )

    dump(
        "EXP-012_20260722_일별이용데이터_시계열EDA.md",
        f"""# EXP-012 | 일별 이용 데이터 시계열 EDA (보조 피처)

```
SSG-SAK  |  이현석  |  EXP-012  |  {today}
```

> 참고: 기존 `EXP-012_20260717_status주기수집_시작.md`와 ID가 겹친다. 본 파일은 **일별 이용 EDA** 전용(2026-07-22 게이트).

## 실험 정보

| 항목 | 내용 |
|---|---|
| 목적 | 2025 전후 일별 이용량이 ETA 타깃이 될 수 없는지 확인하고, 혼잡 보조 피처 가치만 검증 |
| 가설 | 일별 grain이라 ETA 가용 타깃 불가. 요일/이동평균 등 보조 피처는 가능 |

## 결과

| 지표 | 값 |
|---|---|
| 행 수 | {usage.get('rows')} |
| 2025 행 | {usage.get('rows_2025')} |
| 기간 | {usage.get('date_min')} → {usage.get('date_max')} |
| 충전소 수 | {usage.get('n_stations')} |
| 일평균 세션(플릿) | {usage.get('daily_avg_sessions_fleet')} |
| 세션-충전량 상관 | {usage.get('corr_sessions_kwh')} |
| 1회당 kWh median | {usage.get('avg_kwh_per_session_median')} |
| 무이용 vs 결측 구분 | {(usage.get('missing_vs_zero') or {}).get('can_distinguish')} |
| ETA 타깃 사용 | **금지** ({usage.get('eta_target_forbidden')}) |

## 해석

{usage.get('role_verdict')}

## 산출물

- `json/usage_eda.json`
- `tables/usage_daily_fleet.csv`, `usage_by_weekday.csv`
- `figures/usage_daily_sessions.png`

```
SSG-SAK  |  EXP-012-usage  |  {today}
```
""",
    )

    dump(
        "EXP-013_20260722_상태이벤트_5분패널복원.md",
        f"""# EXP-013 | 상태 이벤트 → 패널 복원

```
SSG-SAK  |  이현석  |  EXP-013  |  {today}
```

## 방법 요약

- 패널 시각 = **실제 수집 틱** (약 10분). 빈 5분 격자 생성 안 함.
- ffill 조건: 직전 관측 존재 ∧ `collection_success` ∧ age≤{panel.get('max_hold_minutes')}분
- 미관측/수집실패는 null (사용불가 아님)

## 결과

| 지표 | 값 |
|---|---|
| ticks | {panel.get('n_ticks')} |
| chargers | {panel.get('n_chargers')} |
| cells | {panel.get('panel_cells')} |
| observed_rate | {panel.get('observed_rate')} |
| impute_rate | {panel.get('impute_rate')} |
| null_rate | {panel.get('null_rate')} |
| restore_acc (observed) | {panel.get('restore_accuracy_on_observed')} |
| 5분 격자 | {panel.get('five_min_grid')} |

필수 컬럼 샘플: `tables/panel_restore_sample.csv`

```
SSG-SAK  |  EXP-013  |  {today}
```
""",
    )

    e15 = eta.get("eta15") or {}
    dump(
        "EXP-014_20260722_ETA15분_예측타당성검증.md",
        f"""# EXP-014 | ETA 15분 예측 타당성

```
SSG-SAK  |  이현석  |  EXP-014  |  {today}
```

## 타깃 정의

- 1: t+15 근처에서 **실제 관측** available≥1
- 0: t+15 근처 관측됐고 usable 관측 중 available=0
- null: 신뢰 관측 없음 (**0으로 변환 금지**)

## 결과 (주 판정 15분)

| 지표 | 값 |
|---|---|
| 후보 행 | {e15.get('candidate_rows')} |
| 라벨 행 | {e15.get('labeled_rows')} |
| 커버리지 | {e15.get('coverage')} |
| 양성/음성 | {e15.get('positive')} / {e15.get('negative')} |
| 양성 비율 | {e15.get('positive_rate')} |
| 라벨 일수 | {e15.get('dates_with_label')} |
| 시간순 분할 가능 | {eta.get('temporal_split_feasible')} |
| 백테스트 | skipped={bt.get('skipped')} ok={bt.get('ok')} · {bt.get('reason')} |

## 최종 게이트 연동

판정은 `reports/timeseries_feasibility/timeseries_feasibility_summary.md` 및 `json/verdict.json`.

```
SSG-SAK  |  EXP-014  |  {today}
```
""",
    )

    # summary md
    summary_path = OUT_ROOT / "timeseries_feasibility_summary.md"
    summary_path.write_text(
        f"""# Timeseries Feasibility Summary — EV SafeCharge

| 생성 | `{datetime.now(tz=KST).isoformat()}` |
| 판정 | **{verdict.get('grade_label')}** (`{verdict.get('grade')}`) |

## 핵심 목표

예상 도착시각(ETA)에 **실제로 사용 가능한** 충전소 추천이 데이터로 성립하는가.

## 판정

**{verdict.get('grade_label')}**

### 핵심 근거 5개

{chr(10).join(f"- {e}" for e in (verdict.get("core_evidence") or []))}

### 치명적 문제

{chr(10).join(f"- {e}" for e in (verdict.get("critical_issues") or ["(없음)"])) or "- (없음)"}

### 수정 가능한 문제

{chr(10).join(f"- {e}" for e in (verdict.get("fixable_issues") or []))}

### 필요 최소 수집 기간

**{verdict.get('min_collection_period_days')}일** (현재 라벨 생산속도 기준 추정)

### 일정 내 해결 가능

{verdict.get('solvable_in_project_schedule')}

### 핵심 목표 유지

{verdict.get('core_goal_retainable')}

### 목표 축소 시 대체 문구

{verdict.get('goal_rewrite_if_needed')}

### 권고

{verdict.get('recommendation')}

## 데이터 인벤토리 요약

- inventory items: {(inv.get('summary') or {}).get('n_inventory_rows')}
- status snapshots: {(inv.get('summary') or {}).get('status_snapshots')}
- 표: `tables/inventory_overview.csv`

## 재실행

```bash
cd git-elctronic
python apps/data-pipeline/evaluation/feasibility/run_all.py
```

원본 데이터는 수정하지 않음. mock 주차는 평가에서 제외.
""",
        encoding="utf-8",
    )
    files.append(str(summary_path).replace("\\", "/"))
    return files


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    ensure_out()
    bundle: dict = {"started_at": datetime.now(tz=KST).isoformat()}
    steps = [
        ("inventory", run_inventory),
        ("status_quality", run_status_quality),
        ("panel_restore", run_panel_restore),
        ("usage_eda", run_usage_eda),
    ]
    for name, fn in steps:
        print(f"=== {name} ===", flush=True)
        try:
            bundle[name] = fn()
            print(json.dumps({k: bundle[name].get(k) for k in list(bundle[name])[:8] if k != "items"}, ensure_ascii=False, default=str)[:500], flush=True)
        except Exception as exc:
            bundle[name] = {"ok": False, "error": str(exc), "trace": traceback.format_exc()}
            print(f"FAIL {name}: {exc}", flush=True)

    print("=== eta_targets ===", flush=True)
    try:
        st_path = (bundle.get("panel_restore") or {}).get("_station_tick_path")
        bundle["eta_targets"] = run_eta_targets(st_path)
    except Exception as exc:
        bundle["eta_targets"] = {"ok": False, "error": str(exc), "trace": traceback.format_exc()}
        print(f"FAIL eta: {exc}", flush=True)

    print("=== backtest ===", flush=True)
    try:
        bundle["backtest"] = run_backtest()
    except Exception as exc:
        bundle["backtest"] = {"ok": False, "error": str(exc), "trace": traceback.format_exc()}

    verdict = run_verdict(bundle)
    bundle["verdict"] = verdict
    (OUT_JSON / "bundle_meta.json").write_text(
        json.dumps({k: (v if k != "inventory" else v.get("summary")) for k, v in bundle.items()}, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    files = _write_exps(bundle, verdict)
    print(json.dumps({"verdict": verdict.get("grade_label"), "files": files}, ensure_ascii=False, indent=2), flush=True)
    return 0 if verdict.get("grade") != "C_NO_GO" else 2


if __name__ == "__main__":
    raise SystemExit(main())
