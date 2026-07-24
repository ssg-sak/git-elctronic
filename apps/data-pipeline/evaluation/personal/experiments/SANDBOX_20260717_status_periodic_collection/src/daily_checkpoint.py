"""Generate one immutable daily health checkpoint (JSON, Markdown, PNG).

The previous day is checked automatically by ``run_loop.py`` after the first
successful collection of a new day. This script performs no API calls and does
not modify raw snapshots.
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import matplotlib.pyplot as plt
import pandas as pd

from build_panel import availability_timeseries, build_state_panel
from daily_export import export_daily_status_csv
from load_snapshots import load_all_snapshots

_SRC = Path(__file__).resolve().parent
_REPO = Path(__file__).resolve().parents[7]
import sys

_DATA_PIPELINE = _REPO / "apps" / "data-pipeline"
if str(_DATA_PIPELINE) not in sys.path:
    sys.path.insert(0, str(_DATA_PIPELINE))

from loop_paths import LOOP1_INDEX

EVALUATION_ROOT = _SRC.parents[2]
INDEX_CSV = LOOP1_INDEX
REPORTS_ROOT = EVALUATION_ROOT / "results" / "status_daily"
KST = ZoneInfo("Asia/Seoul")
EXPECTED_INTERVAL_MINUTES = 5
MAX_CONTINUOUS_GAP_MINUTES = 25
DAILY_API_LIMIT = 1000


def _json_value(value: Any) -> Any:
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    return value


def _status_counts(df: pd.DataFrame) -> dict[str, int]:
    labels = {
        1: "communication_error",
        2: "available",
        3: "in_use",
        4: "operation_stopped",
        5: "under_inspection",
        9: "status_unknown",
    }
    stat = pd.to_numeric(df["stat"], errors="coerce")
    return {
        labels.get(int(code), f"unknown_{int(code)}"): int(count)
        for code, count in stat.value_counts().sort_index().items()
        if pd.notna(code)
    }


def _timing_metrics(times: pd.Series) -> dict[str, Any]:
    times = times.sort_values().drop_duplicates().reset_index(drop=True)
    if times.empty:
        return {}
    deltas = times.diff().dropna().dt.total_seconds() / 60
    gaps = []
    for index, minutes in deltas.items():
        if minutes > MAX_CONTINUOUS_GAP_MINUTES:
            gaps.append(
                {
                    "from": times.iloc[index - 1],
                    "to": times.iloc[index],
                    "minutes": round(float(minutes), 1),
                    "approx_missed": max(
                        int(round(minutes / EXPECTED_INTERVAL_MINUTES)) - 1, 1
                    ),
                }
            )
    span_minutes = (times.iloc[-1] - times.iloc[0]).total_seconds() / 60
    expected = int(round(span_minutes / EXPECTED_INTERVAL_MINUTES)) + 1
    return {
        "first": times.iloc[0],
        "last": times.iloc[-1],
        "active_span_hours": round(span_minutes / 60, 1),
        "interval_median_minutes": (
            round(float(deltas.median()), 1) if not deltas.empty else None
        ),
        "interval_max_minutes": (
            round(float(deltas.max()), 1) if not deltas.empty else None
        ),
        "expected_rounds_within_active_span": expected,
        "continuity_pct_within_active_span": round(
            min(len(times) / expected * 100, 100.0), 1
        ),
        "gap_count": len(gaps),
        "gaps": gaps,
    }


def calculate_checkpoint(report_date: date) -> dict[str, Any]:
    if not INDEX_CSV.exists():
        raise FileNotFoundError(f"missing index: {INDEX_CSV}")

    idx = pd.read_csv(INDEX_CSV)
    idx["fetchedAt"] = pd.to_datetime(idx["fetchedAt"], errors="coerce")
    daily_idx = idx[idx["fetchedAt"].dt.date == report_date].copy()
    if daily_idx.empty:
        return {
            "generated": False,
            "report_date": report_date.isoformat(),
            "reason": "no_snapshots_for_date",
        }

    all_df = load_all_snapshots()
    all_df["snapshot_ts"] = pd.to_datetime(
        all_df["snapshotId"], format="%Y%m%d_%H%M%S", errors="coerce"
    )
    all_df["stat"] = pd.to_numeric(all_df["stat"], errors="coerce")
    daily_df = all_df[all_df["snapshot_ts"].dt.date == report_date].copy()
    cumulative = all_df[all_df["snapshot_ts"].dt.date <= report_date].copy()

    raw_rows = int(daily_idx["rows"].sum())
    dedup_rows = int(len(daily_df))
    charger_counts = cumulative.groupby(["statId", "chgerId"]).size()

    panel = build_state_panel(cumulative)
    panel_ts = availability_timeseries(panel)
    daily_panel_ts = panel_ts[panel_ts["ts"].dt.date == report_date].copy()

    timing = _timing_metrics(daily_idx["fetchedAt"])
    quality = {
        "null_statId": int(daily_df["statId"].isna().sum()),
        "null_chgerId": int(daily_df["chgerId"].isna().sum()),
        "null_stat": int(daily_df["stat"].isna().sum()),
        "duplicate_rows_removed_at_read": raw_rows - dedup_rows,
        "invalid_status_rows": int(
            (~daily_df["stat"].isin([1, 2, 3, 4, 5, 9])).sum()
        ),
    }
    panel_metrics = {
        "availability_mean_pct": round(
            float(daily_panel_ts["availability_pct"].mean()), 1
        ),
        "availability_min_pct": round(
            float(daily_panel_ts["availability_pct"].min()), 1
        ),
        "availability_max_pct": round(
            float(daily_panel_ts["availability_pct"].max()), 1
        ),
        "known_chargers_median": int(daily_panel_ts["usable_known"].median()),
        "known_chargers_last": int(daily_panel_ts["usable_known"].iloc[-1]),
        "segments": int(daily_panel_ts["segment_id"].nunique()),
    }

    healthy = (
        quality["null_statId"] == 0
        and quality["null_chgerId"] == 0
        and quality["null_stat"] == 0
        and quality["invalid_status_rows"] == 0
        and timing["interval_median_minutes"] is not None
        and timing["interval_median_minutes"] <= MAX_CONTINUOUS_GAP_MINUTES
    )

    return {
        "generated": True,
        "report_date": report_date.isoformat(),
        "health": "healthy" if healthy else "check_required",
        "daily": {
            "snapshots": int(len(daily_idx)),
            "raw_rows": raw_rows,
            "dedup_rows": dedup_rows,
            "api_calls": int(daily_idx["api_calls"].sum()),
            "api_limit_usage_pct": round(
                float(daily_idx["api_calls"].sum()) / DAILY_API_LIMIT * 100, 1
            ),
            "rows_mean": round(float(daily_idx["rows"].mean()), 1),
            "rows_min": int(daily_idx["rows"].min()),
            "rows_max": int(daily_idx["rows"].max()),
            "status_counts": _status_counts(daily_df),
        },
        "timing": timing,
        "quality": quality,
        "cumulative_through_date": {
            "unique_chargers": int(len(charger_counts)),
            "observed_at_least_2": int((charger_counts >= 2).sum()),
            "observed_at_least_5": int((charger_counts >= 5).sum()),
            "observed_at_least_10": int((charger_counts >= 10).sum()),
            "observations_median": float(charger_counts.median()),
            "observations_mean": round(float(charger_counts.mean()), 1),
        },
        "gap_safe_panel": panel_metrics,
    }


def _write_markdown(report: dict[str, Any], path: Path) -> None:
    daily = report["daily"]
    timing = report["timing"]
    quality = report["quality"]
    cumulative = report["cumulative_through_date"]
    panel = report["gap_safe_panel"]
    gap_lines = (
        "\n".join(
            f"- {gap['from']} → {gap['to']}: {gap['minutes']}분 "
            f"(약 {gap['approx_missed']}회 누락)"
            for gap in timing["gaps"]
        )
        if timing["gaps"]
        else "- 없음"
    )
    text = f"""# status 일일 자동 점검 | {report['report_date']}

| 항목 | 결과 |
|---|---|
| 상태 | **{report['health']}** |
| 수집 회차 | {daily['snapshots']}회 |
| 수집 시간 | {timing['first']} ~ {timing['last']} |
| 중앙 수집 간격 | {timing['interval_median_minutes']}분 |
| 활성 구간 연속성 | {timing['continuity_pct_within_active_span']}% |
| API 호출 | {daily['api_calls']} / {DAILY_API_LIMIT} ({daily['api_limit_usage_pct']}%) |
| 행 수 | raw {daily['raw_rows']:,} / dedup {daily['dedup_rows']:,} |
| 패널 가용률 | 평균 {panel['availability_mean_pct']}% |
| 패널 알려진 충전기 | 마지막 {panel['known_chargers_last']:,}대 |

## 수집 공백

{gap_lines}

## 데이터 품질

- statId 결측: {quality['null_statId']}
- chgerId 결측: {quality['null_chgerId']}
- stat 결측: {quality['null_stat']}
- 유효하지 않은 상태코드: {quality['invalid_status_rows']}
- 읽기 단계 제거 중복행: {quality['duplicate_rows_removed_at_read']}

## 누적 현황 ({report['report_date']} 종료 기준)

- 고유 충전기: {cumulative['unique_chargers']:,}대
- 2회 이상 관측: {cumulative['observed_at_least_2']:,}대
- 5회 이상 관측: {cumulative['observed_at_least_5']:,}대
- 10회 이상 관측: {cumulative['observed_at_least_10']:,}대
- 충전기당 관측: 중앙값 {cumulative['observations_median']:.0f}회 / 평균 {cumulative['observations_mean']:.1f}회

## 집계 원칙

- 원본 스냅샷은 수정하지 않는다.
- 중복은 읽기 단계에서만 제거한다.
- 가용률은 충전기 1대=1표인 패널 재구성 기준이다.
- 25분을 넘는 수집 공백 뒤에는 이전 상태를 이어 쓰지 않는다.

![일일 점검 차트](./daily_checkpoint.png)
"""
    path.write_text(text, encoding="utf-8")


def _write_png(report: dict[str, Any], report_date: date, path: Path) -> None:
    idx = pd.read_csv(INDEX_CSV)
    idx["fetchedAt"] = pd.to_datetime(idx["fetchedAt"], errors="coerce")
    day_idx = idx[idx["fetchedAt"].dt.date == report_date].sort_values("fetchedAt")

    all_df = load_all_snapshots()
    all_df["snapshot_ts"] = pd.to_datetime(
        all_df["snapshotId"], format="%Y%m%d_%H%M%S", errors="coerce"
    )
    all_df["stat"] = pd.to_numeric(all_df["stat"], errors="coerce")
    cumulative = all_df[all_df["snapshot_ts"].dt.date <= report_date].copy()
    panel_ts = availability_timeseries(build_state_panel(cumulative))
    day_panel = panel_ts[panel_ts["ts"].dt.date == report_date]
    counts = cumulative.groupby(["statId", "chgerId"]).size()

    plt.rcParams["font.family"] = ["Malgun Gothic", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    fig, axes = plt.subplots(2, 2, figsize=(13, 8), facecolor="#f7f8fa")
    fig.suptitle(
        f"EV SafeCharge | status 일일 점검 · {report_date}",
        fontsize=17,
        fontweight="bold",
        x=0.06,
        ha="left",
    )

    ax = axes[0, 0]
    ax.plot(day_idx["fetchedAt"], day_idx["rows"], marker="o", markersize=3)
    ax.set_title("회차별 수집 행 수", loc="left", fontweight="bold")
    ax.set_ylabel("건")
    ax.tick_params(axis="x", labelrotation=20, labelsize=8)

    ax = axes[0, 1]
    ax.plot(
        day_panel["ts"],
        day_panel["availability_pct"],
        color="#18794e",
        linewidth=2,
    )
    ax.set_title("공백 안전 패널 가용률", loc="left", fontweight="bold")
    ax.set_ylabel("% · 충전기 1대=1표")
    ax.set_ylim(0, 100)
    ax.tick_params(axis="x", labelrotation=20, labelsize=8)

    ax = axes[1, 0]
    levels = [1, 2, 5, 10]
    values = [int((counts >= level).sum()) for level in levels]
    ax.bar([f"{level}회+" for level in levels], values, color="#4c78a8")
    ax.set_title("누적 반복 관측 깊이", loc="left", fontweight="bold")
    ax.set_ylabel("충전기 수 (대)")

    ax = axes[1, 1]
    metrics = report["daily"]
    quality = report["quality"]
    timing = report["timing"]
    panel = report["gap_safe_panel"]
    ax.axis("off")
    ax.set_title("일일 판정", loc="left", fontweight="bold")
    ax.text(
        0,
        0.93,
        f"상태: {report['health']}\n\n"
        f"수집 {metrics['snapshots']}회 · API {metrics['api_calls']}회\n"
        f"활성 구간 연속성 {timing['continuity_pct_within_active_span']}%\n"
        f"공백 {timing['gap_count']}건 · 읽기 중복 {quality['duplicate_rows_removed_at_read']}행\n"
        f"패널 평균 가용률 {panel['availability_mean_pct']}%\n"
        f"마지막 알려진 충전기 {panel['known_chargers_last']:,}대",
        va="top",
        fontsize=11,
        linespacing=1.6,
        bbox={
            "boxstyle": "round,pad=0.8",
            "facecolor": "#ffffff",
            "edgecolor": "#c8d0d8",
        },
    )

    for ax in axes.flat[:3]:
        ax.grid(axis="y", alpha=0.25)
        ax.set_facecolor("#ffffff")
        ax.spines[["top", "right"]].set_visible(False)
    fig.text(
        0.06,
        0.02,
        "Source: immutable status snapshots · read-time dedup · gap-safe panel",
        fontsize=8.5,
        color="#68737d",
    )
    fig.savefig(path, dpi=170, bbox_inches="tight")
    plt.close(fig)


def generate_daily_checkpoint(
    report_date: date, *, force: bool = False
) -> dict[str, Any]:
    output_dir = REPORTS_ROOT / report_date.isoformat()
    json_path = output_dir / "daily_checkpoint.json"
    if json_path.exists() and not force:
        return {
            "generated": False,
            "report_date": report_date.isoformat(),
            "reason": "already_exists",
            "path": str(output_dir),
        }

    report = calculate_checkpoint(report_date)
    if not report.get("generated"):
        return report

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=_json_value),
        encoding="utf-8",
    )
    _write_markdown(report, output_dir / "daily_checkpoint.md")
    _write_png(report, report_date, output_dir / "daily_checkpoint.png")
    try:
        daily_csv = export_daily_status_csv(report_date, force=force)
        report["daily_csv"] = daily_csv
    except Exception as exc:  # export must never block checkpoint
        report["daily_csv"] = {"generated": False, "reason": "export_error", "error": str(exc)}
    report["path"] = str(output_dir)
    return report


def ensure_previous_day_checkpoint() -> dict[str, Any]:
    yesterday = datetime.now(tz=KST).date() - timedelta(days=1)
    return generate_daily_checkpoint(yesterday)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate daily collection checkpoint")
    parser.add_argument(
        "--date",
        help="target date (YYYY-MM-DD); default is yesterday in Asia/Seoul",
    )
    parser.add_argument("--force", action="store_true", help="overwrite existing report")
    args = parser.parse_args()
    target = (
        date.fromisoformat(args.date)
        if args.date
        else datetime.now(tz=KST).date() - timedelta(days=1)
    )
    result = generate_daily_checkpoint(target, force=args.force)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=_json_value))
    return 0 if result.get("generated") or result.get("reason") == "already_exists" else 1


if __name__ == "__main__":
    raise SystemExit(main())
