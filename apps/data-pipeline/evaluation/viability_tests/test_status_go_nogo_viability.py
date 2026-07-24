"""GO / NO-GO: status 시계열로 MVP·분석이 가능한가?

프로젝트 폐기 여부를 가르는 **재료 타당성** 테스트.
점수·추천 성공률은 DA➁ — 여기서는 ① 재료만 본다.

판정 축
  A) MVP (규칙 기반 추천 재료) — 관측/가용/신선도/확정가용
  B) 시계열 EDA (시간대 패턴·패널) — 일수·주간 gap·충전기당 관측 횟수
  C) 시계열 ML 예측 (도착 시 가용 예측 등) — 더 긴 시계열 필요

실행 (repo root):
  python apps/data-pipeline/evaluation/viability_tests/test_status_go_nogo_viability.py

산출:
  apps/data-pipeline/evaluation/results/go_nogo/status_viability_latest.{json,md}

exit code: 0 = 프로젝트 유지(MVP GO 또는 CONDITIONAL), 2 = MVP NO (폐기 검토)
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd


def _repo_root() -> Path:
    here = Path(__file__).resolve().parent
    for p in [here, *here.parents]:
        if (p / "AGENTS.md").exists() and (p / "apps" / "data-pipeline").exists():
            return p
    return Path(__file__).resolve().parents[4]


REPO = _repo_root()
SANDBOX = (
    REPO
    / "apps/data-pipeline/evaluation/personal/experiments"
    / "SANDBOX_20260717_status_periodic_collection"
)
SNAP_DIR = SANDBOX / "data" / "snapshots"
INDEX_CSV = SANDBOX / "data" / "index.csv"
D1_CSV = REPO / "apps/data-pipeline/evaluation/results/datasets/station_feature_snapshot_latest.csv"
MASTER_GLOB = list(
    (REPO / "docs/data/extracted").glob("daegu_charger_info_*.csv")
)
OUT_DIR = REPO / "apps/data-pipeline/evaluation/results" / "go_nogo"
KST = ZoneInfo("Asia/Seoul")

# --- thresholds (MVP vs analysis) ---
MVP = {
    "min_calendar_days": 3,
    "min_snapshots": 50,
    "min_cum_chargers": 5_000,
    "min_cum_charger_ratio": 0.35,  # vs master if available
    "min_confirmed_available_rate": 0.50,
    "max_unobserved_rate_mean": 0.50,
    # hard: allow legacy 10~15m history in same series (kill만 막는 선)
    "max_daytime_median_gap_min_hard": 16.0,
    # soft (CONDITIONAL): target 5-min ops
    "max_daytime_median_gap_min_soft": 6.0,
}
TS_EDA = {
    "min_calendar_days": 5,
    # change-feed: same charger need not appear every tick — count across ALL snaps
    "min_chargers_with_5_obs": 3_000,
    "min_chargers_with_10_obs": 1_000,
    "max_night_gap_share": 0.55,  # of total span that is night/off gaps
}
TS_ML = {
    "min_calendar_days": 14,
    "min_chargers_with_30_obs": 2_000,
}


@dataclass
class Check:
    id: str
    name: str
    ok: bool
    value: Any
    threshold: Any
    note: str = ""


@dataclass
class AxisVerdict:
    axis: str
    verdict: str  # GO | CONDITIONAL | NO
    score: str
    checks: list[Check] = field(default_factory=list)
    summary: str = ""


def _latest_master() -> Path | None:
    if not MASTER_GLOB:
        return None
    return max(MASTER_GLOB, key=lambda p: p.stat().st_mtime)


def _load_index() -> pd.DataFrame:
    if not INDEX_CSV.exists():
        return pd.DataFrame()
    idx = pd.read_csv(INDEX_CSV, dtype=str)
    idx["snapshotId"] = idx["snapshotId"].astype(str)
    idx["ts"] = pd.to_datetime(idx["snapshotId"], format="%Y%m%d_%H%M%S", errors="coerce")
    idx["day"] = idx["ts"].dt.strftime("%Y-%m-%d")
    idx["rows"] = pd.to_numeric(idx.get("rows"), errors="coerce")
    return idx.dropna(subset=["ts"]).sort_values("ts")


def _daytime_gaps_minutes(ts: pd.Series) -> list[float]:
    """Gaps between consecutive ticks that both fall in 08–22 KST."""
    gaps: list[float] = []
    t = ts.sort_values().tolist()
    for a, b in zip(t, t[1:]):
        if a.hour >= 8 and a.hour < 22 and b.hour >= 8 and b.hour < 22:
            gaps.append((b - a).total_seconds() / 60.0)
    return gaps


def _night_or_off_gaps(ts: pd.Series) -> tuple[float, float]:
    """Return (sum of gaps > 30min in minutes, total span minutes)."""
    t = ts.sort_values()
    if len(t) < 2:
        return 0.0, 0.0
    span = (t.iloc[-1] - t.iloc[0]).total_seconds() / 60.0
    big = 0.0
    for a, b in zip(t.iloc[:-1], t.iloc[1:]):
        d = (b - a).total_seconds() / 60.0
        if d > 30:
            big += d
    return big, span


def _full_observation_counts() -> dict[str, Any]:
    """Count how often each charger appears across ALL snapshots (one pass)."""
    files = sorted(SNAP_DIR.glob("daegu_charger_status_*.csv"))
    if not files:
        return {"ok": False, "error": "no snapshots"}
    counts: dict[tuple[str, str], int] = {}
    for fp in files:
        df = pd.read_csv(fp, dtype={"statId": str, "chgerId": str}, usecols=["statId", "chgerId"])
        df = df.drop_duplicates(["statId", "chgerId"])
        for sid, cid in zip(df["statId"], df["chgerId"]):
            key = (sid, cid)
            counts[key] = counts.get(key, 0) + 1
    vals = list(counts.values()) if counts else [0]
    return {
        "ok": True,
        "snapshots_scanned": len(files),
        "unique_chargers": len(counts),
        "obs_ge_5": int(sum(1 for v in vals if v >= 5)),
        "obs_ge_10": int(sum(1 for v in vals if v >= 10)),
        "obs_ge_20": int(sum(1 for v in vals if v >= 20)),
        "obs_ge_30": int(sum(1 for v in vals if v >= 30)),
        "obs_median": float(median(vals)),
        "obs_mean": float(sum(vals) / len(vals)) if vals else 0.0,
    }


def _d1_metrics() -> dict[str, Any]:
    if not D1_CSV.exists():
        return {"ok": False, "error": "D1 missing"}
    df = pd.read_csv(D1_CSV)
    out: dict[str, Any] = {"ok": True, "rows": int(len(df))}
    if "has_confirmed_available" in df.columns:
        out["confirmed_available_rate"] = float(df["has_confirmed_available"].astype(bool).mean())
    if "unobserved_rate" in df.columns:
        out["unobserved_rate_mean"] = float(pd.to_numeric(df["unobserved_rate"], errors="coerce").mean())
    if "availability_ratio_observed" in df.columns:
        out["availability_ratio_observed_mean"] = float(
            pd.to_numeric(df["availability_ratio_observed"], errors="coerce").mean()
        )
    if "recommend_public_default" in df.columns:
        pub = df[df["recommend_public_default"].astype(bool)]
        out["public_stations"] = int(len(pub))
        if "has_confirmed_available" in pub.columns:
            out["public_confirmed_available_rate"] = float(pub["has_confirmed_available"].astype(bool).mean())
    if "reliability_grade" in df.columns:
        out["reliability_dist"] = df["reliability_grade"].value_counts().to_dict()
    return out


def _master_charger_count() -> int | None:
    path = _latest_master()
    if path is None:
        return None
    df = pd.read_csv(path, dtype={"statId": str, "chgerId": str}, usecols=["statId", "chgerId"])
    return int(df.drop_duplicates(["statId", "chgerId"]).shape[0])


def _verdict_from_checks(checks: list[Check], *, soft_ids: set[str] | None = None) -> str:
    soft_ids = soft_ids or set()
    hard_fail = [c for c in checks if not c.ok and c.id not in soft_ids]
    soft_fail = [c for c in checks if not c.ok and c.id in soft_ids]
    if hard_fail:
        return "NO"
    if soft_fail:
        return "CONDITIONAL"
    return "GO"


def evaluate() -> dict[str, Any]:
    idx = _load_index()
    disk_n = len(list(SNAP_DIR.glob("daegu_charger_status_*.csv")))
    now = datetime.now(tz=KST)

    if idx.empty or disk_n == 0:
        return {
            "generated_at": now.isoformat(),
            "project_keep": False,
            "overall": "NO",
            "kill_project": True,
            "reason": "status snapshots / index missing",
            "axes": [],
        }

    days = sorted(idx["day"].unique().tolist())
    n_days = len(days)
    n_snap = int(len(idx))
    day_gaps = _daytime_gaps_minutes(idx["ts"])
    day_med = float(median(day_gaps)) if day_gaps else None
    big_gap_min, span_min = _night_or_off_gaps(idx["ts"])
    night_share = (big_gap_min / span_min) if span_min > 0 else 1.0

    print("scanning all snapshots for coverage + obs counts…", flush=True)
    obs = _full_observation_counts()
    cum = int(obs.get("unique_chargers") or 0)
    master_n = _master_charger_count()
    cum_ratio = (cum / master_n) if master_n else None
    d1 = _d1_metrics()

    # ----- A) MVP -----
    gap_hard_ok = day_med is not None and day_med <= MVP["max_daytime_median_gap_min_hard"]
    gap_soft_ok = day_med is not None and day_med <= MVP["max_daytime_median_gap_min_soft"]
    mvp_checks = [
        Check("mvp_days", "수집 캘린더 일수", n_days >= MVP["min_calendar_days"], n_days, f">={MVP['min_calendar_days']}"),
        Check("mvp_snaps", "스냅샷 회차", n_snap >= MVP["min_snapshots"], n_snap, f">={MVP['min_snapshots']}"),
        Check("mvp_cum", "누적 관측 충전기", cum >= MVP["min_cum_chargers"], cum, f">={MVP['min_cum_chargers']}"),
        Check(
            "mvp_ratio",
            "누적/마스터 비율",
            cum_ratio is None or cum_ratio >= MVP["min_cum_charger_ratio"],
            None if cum_ratio is None else round(cum_ratio, 3),
            f">={MVP['min_cum_charger_ratio']}" if master_n else "master missing → skip",
            note="getChargerStatus는 변경분이라 100% 불가·누적 커버로 판단",
        ),
        Check(
            "mvp_gap_hard",
            "주간 틱 간격 median (하드)",
            gap_hard_ok,
            None if day_med is None else round(day_med, 2),
            f"<={MVP['max_daytime_median_gap_min_hard']}분 (레거시 15분 구간 허용)",
        ),
        Check(
            "mvp_gap_soft",
            "주간 틱 간격 median (목표 5분)",
            gap_soft_ok,
            None if day_med is None else round(day_med, 2),
            f"<={MVP['max_daytime_median_gap_min_soft']}분",
            note="미달이면 CONDITIONAL — 폐기 사유 아님 · 5분 루프 재시작 후 개선",
        ),
    ]
    if d1.get("ok"):
        mvp_checks.append(
            Check(
                "mvp_confirmed",
                "D1 확정가용 소 비율",
                d1.get("confirmed_available_rate", 0) >= MVP["min_confirmed_available_rate"],
                round(float(d1["confirmed_available_rate"]), 3),
                f">={MVP['min_confirmed_available_rate']}",
            )
        )
        mvp_checks.append(
            Check(
                "mvp_unobs",
                "D1 미관측률 mean",
                d1.get("unobserved_rate_mean", 1) <= MVP["max_unobserved_rate_mean"],
                round(float(d1["unobserved_rate_mean"]), 3),
                f"<={MVP['max_unobserved_rate_mean']}",
            )
        )
    else:
        mvp_checks.append(Check("mvp_d1", "D1 존재", False, "missing", "station_feature_snapshot_latest.csv"))

    mvp_verdict = _verdict_from_checks(mvp_checks, soft_ids={"mvp_ratio", "mvp_gap_soft"})
    mvp = AxisVerdict(
        axis="A_MVP_rule_based",
        verdict=mvp_verdict,
        score=f"{sum(c.ok for c in mvp_checks)}/{len(mvp_checks)}",
        checks=mvp_checks,
        summary=(
            "실시간 관측·가용·신선도 재료로 **규칙 기반 추천(MVP)** 가능한가. "
            "프로젝트 핵심 목표의 최소선. 미달 시에만 폐기 검토."
        ),
    )

    # ----- B) Timeseries EDA -----
    eda_checks = [
        Check("eda_days", "캘린더 일수", n_days >= TS_EDA["min_calendar_days"], n_days, f">={TS_EDA['min_calendar_days']}"),
        Check(
            "eda_obs5",
            "전체 스냅샷 기준 ≥5회 관측 충전기",
            obs.get("ok") and obs.get("obs_ge_5", 0) >= TS_EDA["min_chargers_with_5_obs"],
            obs.get("obs_ge_5"),
            f">={TS_EDA['min_chargers_with_5_obs']} / {obs.get('snapshots_scanned')} snaps",
        ),
        Check(
            "eda_obs10",
            "전체 스냅샷 기준 ≥10회 관측 충전기",
            obs.get("ok") and obs.get("obs_ge_10", 0) >= TS_EDA["min_chargers_with_10_obs"],
            obs.get("obs_ge_10"),
            f">={TS_EDA['min_chargers_with_10_obs']}",
            note="변경분 API라 ‘매 틱 등장’은 기대하지 않음",
        ),
        Check(
            "eda_night",
            "큰 gap(>30분)이 전체 span에서 차지 비율",
            night_share <= TS_EDA["max_night_gap_share"],
            round(night_share, 3),
            f"<={TS_EDA['max_night_gap_share']} (야간 PC off 반영)",
            note="야간 공백이 크면 ‘연속 시계열’ 해석은 주간만 타당",
        ),
    ]
    eda_verdict = _verdict_from_checks(eda_checks, soft_ids={"eda_night", "eda_obs10"})
    eda = AxisVerdict(
        axis="B_timeseries_EDA",
        verdict=eda_verdict,
        score=f"{sum(c.ok for c in eda_checks)}/{len(eda_checks)}",
        checks=eda_checks,
        summary="시간대 패턴·공백 안전 패널 등 **탐색적 시계열**이 타당한가.",
    )

    # ----- C) ML forecast -----
    ml_checks = [
        Check("ml_days", "캘린더 일수", n_days >= TS_ML["min_calendar_days"], n_days, f">={TS_ML['min_calendar_days']}"),
        Check(
            "ml_obs30",
            "≥30회 관측 충전기",
            obs.get("ok") and obs.get("obs_ge_30", 0) >= TS_ML["min_chargers_with_30_obs"],
            obs.get("obs_ge_30"),
            f">={TS_ML['min_chargers_with_30_obs']}",
            note="도착시점 가용 예측 ML은 보통 2주+·조밀 관측 필요 · MVP 필수 아님",
        ),
    ]
    ml_verdict = _verdict_from_checks(ml_checks)
    ml = AxisVerdict(
        axis="C_timeseries_ML_forecast",
        verdict=ml_verdict,
        score=f"{sum(c.ok for c in ml_checks)}/{len(ml_checks)}",
        checks=ml_checks,
        summary="도착 시 가용 **예측 모델**까지 가려면. MVP 필수가 아님 (README 확장).",
    )

    # Project keep rule: kill only if MVP is NO
    kill = mvp.verdict == "NO"
    if mvp.verdict == "GO" and eda.verdict in ("GO", "CONDITIONAL"):
        overall = "KEEP_BUILD_MVP"
    elif mvp.verdict == "CONDITIONAL":
        overall = "KEEP_BUT_FIX_GAPS"
    elif mvp.verdict == "GO" and eda.verdict == "NO":
        overall = "KEEP_MVP_ONLY_NO_DEEP_TS"
    else:
        overall = "CONSIDER_KILL"

    return {
        "generated_at": now.isoformat(),
        "goal_reminder": (
            "가까운 곳이 아니라 가서 충전할 확률이 높은 소를 추천. "
            "MVP=규칙 점수 재료(관측·가용·신뢰도). 예측 ML은 확장."
        ),
        "inventory": {
            "snapshots_on_disk": disk_n,
            "index_rows": n_snap,
            "calendar_days": days,
            "n_days": n_days,
            "first_ts": str(idx["ts"].iloc[0]),
            "last_ts": str(idx["ts"].iloc[-1]),
            "daytime_median_gap_min": day_med,
            "large_gap_share_of_span": round(night_share, 3),
            "cumulative_unique_chargers": cum,
            "master_chargers": master_n,
            "cumulative_ratio": None if cum_ratio is None else round(cum_ratio, 4),
            "observation_counts": obs,
            "d1": d1,
        },
        "axes": [
            {
                "axis": mvp.axis,
                "verdict": mvp.verdict,
                "score": mvp.score,
                "summary": mvp.summary,
                "checks": [asdict(c) for c in mvp.checks],
            },
            {
                "axis": eda.axis,
                "verdict": eda.verdict,
                "score": eda.score,
                "summary": eda.summary,
                "checks": [asdict(c) for c in eda.checks],
            },
            {
                "axis": ml.axis,
                "verdict": ml.verdict,
                "score": ml.score,
                "summary": ml.summary,
                "checks": [asdict(c) for c in ml.checks],
            },
        ],
        "overall": overall,
        "project_keep": not kill,
        "kill_project": kill,
        "plain_korean": _plain_korean(mvp.verdict, eda.verdict, ml.verdict, kill),
    }


def _plain_korean(mvp: str, eda: str, ml: str, kill: bool) -> str:
    if kill:
        return (
            "MVP 재료조차 기준 미달 → 실시간 추천 프로젝트를 이 데이터로 밀어붙이기 어렵다. "
            "수집·D1부터 고치거나 폐기 검토."
        )
    parts = [
        f"MVP(규칙 추천 재료): {mvp}",
        f"시계열 EDA: {eda}",
        f"시계열 ML 예측: {ml}",
    ]
    if mvp == "GO" and ml == "NO":
        parts.append(
            "→ 지금 쌓인 양으로 **실시간 현황·규칙 추천은 가능**. "
            "깊은 시계열 예측은 아직 타당하지 않음. 프로젝트 폐기는 아님."
        )
    elif mvp in ("GO", "CONDITIONAL"):
        parts.append("→ 프로젝트는 유지하고, 부족한 축만 보완.")
    return " ".join(parts)


def _to_md(report: dict[str, Any]) -> str:
    lines = [
        "# Status 타당성 GO/NO-GO",
        "",
        f"| 생성 | `{report['generated_at']}` |",
        f"| 종합 | **{report['overall']}** |",
        f"| 프로젝트 유지 | **{report['project_keep']}** |",
        f"| 폐기 검토(kill) | **{report['kill_project']}** |",
        "",
        report.get("plain_korean", ""),
        "",
        "## 목표 리마인드",
        "",
        report.get("goal_reminder", ""),
        "",
        "## 인벤토리 요약",
        "",
    ]
    inv = report.get("inventory", {})
    lines += [
        f"- 스냅샷: disk={inv.get('snapshots_on_disk')} · index={inv.get('index_rows')}",
        f"- 기간: {inv.get('first_ts')} → {inv.get('last_ts')} ({inv.get('n_days')}일)",
        f"- 주간 median gap: {inv.get('daytime_median_gap_min')}분",
        f"- 큰 gap 비율(span): {inv.get('large_gap_share_of_span')}",
        f"- 누적 관측 충전기: {inv.get('cumulative_unique_chargers')} / master {inv.get('master_chargers')} (ratio={inv.get('cumulative_ratio')})",
        "",
        "## 축별 판정",
        "",
    ]
    for ax in report.get("axes", []):
        lines.append(f"### {ax['axis']} → **{ax['verdict']}** ({ax['score']})")
        lines.append("")
        lines.append(ax.get("summary", ""))
        lines.append("")
        lines.append("| ID | 항목 | OK | 값 | 기준 |")
        lines.append("|---|---|---|---|---|")
        for c in ax.get("checks", []):
            lines.append(
                f"| `{c['id']}` | {c['name']} | {c['ok']} | {c['value']} | {c['threshold']} |"
            )
        lines.append("")
    lines += [
        "## 해석 가이드",
        "",
        "- **GO (MVP)** = 실시간 현황 + 규칙 점수 재료로 목표에 접근 가능",
        "- **CONDITIONAL** = 쓸 수 있으나 gap·커버 보완 필요",
        "- **NO (ML)** = 예측 모델은 지금 데이터로 타당하지 않음 (MVP와 별개)",
        "- **kill_project=true** 일 때만 ‘이 API/수집으로는 MVP 불가 → 폐기 검토’",
        "",
        "재실행:",
        "```bash",
        "python apps/data-pipeline/evaluation/tests/test_status_go_nogo_viability.py",
        "```",
        "",
        "```",
        "DA➀ | go-nogo status viability | auto",
        "```",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    report = evaluate()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUT_DIR / "status_viability_latest.json"
    md_path = OUT_DIR / "status_viability_latest.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    md_path.write_text(_to_md(report), encoding="utf-8")
    print(json.dumps({"overall": report["overall"], "project_keep": report["project_keep"], "kill_project": report["kill_project"], "md": str(md_path)}, ensure_ascii=False, indent=2))
    print("\n" + report.get("plain_korean", ""))
    return 2 if report.get("kill_project") else 0


if __name__ == "__main__":
    sys.exit(main())
