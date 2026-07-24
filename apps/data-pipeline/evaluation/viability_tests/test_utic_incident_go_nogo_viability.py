"""GO / NO-GO: UTIC 돌발 데이터의 MVP 실효성.

돌발은 “충전소 옆 도로가 막히면 도착·대기 위험이 커진다”는 재료.
건수 절대값이 아니라 **루프·조인·D1 반영**이 되는지 본다.

판정 축
  A) MVP 운영 — 수집·신선도·대구 필터·mock 제거
  B) 공간조인 — 1km 매칭·D1 traffic_source
  C) 시계열/예측 — 돌발 예측은 범위 밖 (관측 피드)

실행 (repo root):
  python apps/data-pipeline/evaluation/viability_tests/test_utic_incident_go_nogo_viability.py

산출:
  apps/data-pipeline/evaluation/results/go_nogo/utic_viability_latest.{json,md}

exit: 0 = 유지, 2 = MVP NO (돌발 재료로 쓰기 어려움)
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

REPO_CANDIDATE = Path(__file__).resolve().parents[4]


def _repo_root() -> Path:
    here = Path(__file__).resolve().parent
    for p in [here, *here.parents]:
        if (p / "AGENTS.md").exists() and (p / "apps" / "data-pipeline").exists():
            return p
    return REPO_CANDIDATE


REPO = _repo_root()
UTIC_DIR = REPO / "docs" / "data" / "loops" / "utic"
JOIN_META = REPO / "docs" / "data" / "spatial_join" / "join_traffic_incident_utic_meta.json"
JOIN_CSV = REPO / "docs" / "data" / "spatial_join" / "join_traffic_incident_utic_1000m.csv"
D1_CSV = REPO / "apps/data-pipeline/evaluation/results/datasets/station_feature_snapshot_latest.csv"
OUT_DIR = REPO / "apps/data-pipeline/evaluation/results" / "go_nogo"
KST = ZoneInfo("Asia/Seoul")

MVP = {
    "max_age_minutes": 60,
    "min_calendar_days": 2,
    "min_extracts": 10,
    "min_daegu_when_national_ok": 0,  # 0도 허용(그날 돌발 없을 수 있음) — soft
    "require_daegu_or_national": True,
}
JOIN = {
    "min_matched": 1,
    "min_match_rate": 0.01,  # soft: 돌발 0이면 rate 의미 없음
    "radius_m": 1000,
}
D1 = {
    "require_traffic_source_utic": True,
    "require_not_mock": True,
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
    verdict: str
    score: str
    checks: list[Check] = field(default_factory=list)
    summary: str = ""


def _verdict(checks: list[Check], soft_ids: set[str] | None = None) -> str:
    soft_ids = soft_ids or set()
    if any(not c.ok and c.id not in soft_ids for c in checks):
        return "NO"
    if any(not c.ok for c in checks):
        return "CONDITIONAL"
    return "GO"


def _parse_stamp(name: str) -> datetime | None:
    m = re.search(r"(\d{8}_\d{6})", name)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y%m%d_%H%M%S").replace(tzinfo=KST)
    except ValueError:
        return None


def _inventory() -> dict[str, Any]:
    metas = sorted(UTIC_DIR.glob("utic_incident_meta_20*.json"))
    csvs = sorted(
        p
        for p in UTIC_DIR.glob("daegu_traffic_incident_utic_20*.csv")
        if "latest" not in p.name
    )
    days: set[str] = set()
    stamps: list[datetime] = []
    daegu_counts: list[int] = []
    for mp in metas:
        try:
            meta = json.loads(mp.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        ts = _parse_stamp(mp.name)
        if ts:
            stamps.append(ts)
            days.add(ts.strftime("%Y-%m-%d"))
        if meta.get("daegu_records") is not None:
            daegu_counts.append(int(meta["daegu_records"]))

    gaps: list[float] = []
    stamps_s = sorted(stamps)
    for a, b in zip(stamps_s, stamps_s[1:]):
        # daytime-ish gaps only for median ops
        if 8 <= a.hour < 22 and 8 <= b.hour < 22:
            gaps.append((b - a).total_seconds() / 60.0)

    latest_meta: dict[str, Any] = {}
    latest_path = UTIC_DIR / "utic_incident_meta_latest.json"
    if latest_path.exists():
        latest_meta = json.loads(latest_path.read_text(encoding="utf-8"))

    age = None
    if latest_meta.get("fetched_at"):
        try:
            ft = datetime.fromisoformat(str(latest_meta["fetched_at"]))
            if ft.tzinfo is None:
                ft = ft.replace(tzinfo=KST)
            age = round((datetime.now(tz=KST) - ft).total_seconds() / 60.0, 1)
        except ValueError:
            pass

    return {
        "meta_files": len(metas),
        "csv_files": len(csvs),
        "calendar_days": sorted(days),
        "n_days": len(days),
        "first_ts": str(stamps_s[0]) if stamps_s else None,
        "last_ts": str(stamps_s[-1]) if stamps_s else None,
        "daytime_median_gap_min": float(median(gaps)) if gaps else None,
        "daegu_records_latest": latest_meta.get("daegu_records"),
        "national_records_latest": latest_meta.get("national_records"),
        "fetched_at": latest_meta.get("fetched_at"),
        "age_minutes": age,
        "traffic_is_mock_meta": latest_meta.get("traffic_is_mock"),
        "traffic_source_meta": latest_meta.get("traffic_source"),
        "daegu_records_history_median": float(median(daegu_counts)) if daegu_counts else None,
        "daegu_zero_ticks": int(sum(1 for x in daegu_counts if x == 0)),
        "daegu_positive_ticks": int(sum(1 for x in daegu_counts if x > 0)),
    }


def _join_info() -> dict[str, Any]:
    out: dict[str, Any] = {"ok": JOIN_META.exists()}
    if JOIN_META.exists():
        out.update(json.loads(JOIN_META.read_text(encoding="utf-8")))
    out["join_csv_exists"] = JOIN_CSV.exists()
    if JOIN_CSV.exists():
        df = pd.read_csv(JOIN_CSV, nrows=5)
        out["join_csv_cols"] = list(df.columns)
    return out


def _d1_traffic() -> dict[str, Any]:
    if not D1_CSV.exists():
        return {"ok": False, "error": "D1 missing"}
    df = pd.read_csv(D1_CSV, usecols=lambda c: c in {
        "traffic_is_mock", "traffic_source", "nearest_incident_m", "statId"
    })
    out: dict[str, Any] = {"ok": True, "rows": int(len(df))}
    if "traffic_source" in df.columns:
        out["traffic_source"] = str(df["traffic_source"].iloc[0])
    if "traffic_is_mock" in df.columns:
        # bool-ish
        v = df["traffic_is_mock"].astype(str).str.lower().isin(["true", "1", "yes"])
        out["traffic_is_mock"] = bool(v.iloc[0]) if len(v) else None
        out["traffic_is_mock_any"] = bool(v.any())
    if "nearest_incident_m" in df.columns:
        dist = pd.to_numeric(df["nearest_incident_m"], errors="coerce")
        out["stations_with_incident_within_1km"] = int((dist <= 1000).sum())
        out["nearest_incident_notnull"] = int(dist.notna().sum())
    return out


def evaluate() -> dict[str, Any]:
    now = datetime.now(tz=KST)
    inv = _inventory()
    join = _join_info()
    d1 = _d1_traffic()

    # A) MVP ops
    a_checks = [
        Check(
            "utic_files",
            "돌발 extract 파일 존재",
            inv["meta_files"] >= MVP["min_extracts"] and inv["csv_files"] >= MVP["min_extracts"],
            {"meta": inv["meta_files"], "csv": inv["csv_files"]},
            f">={MVP['min_extracts']} each",
        ),
        Check(
            "utic_days",
            "수집 캘린더 일수",
            inv["n_days"] >= MVP["min_calendar_days"],
            inv["n_days"],
            f">={MVP['min_calendar_days']}",
        ),
        Check(
            "utic_fresh",
            "latest 신선도",
            inv["age_minutes"] is not None and inv["age_minutes"] <= MVP["max_age_minutes"],
            inv["age_minutes"],
            f"<={MVP['max_age_minutes']}분",
        ),
        Check(
            "utic_national",
            "전국 피드 수신 (national_records)",
            (inv.get("national_records_latest") or 0) > 0,
            inv.get("national_records_latest"),
            ">0 (API/키/IP 정상 신호)",
        ),
        Check(
            "utic_not_mock_meta",
            "meta traffic_is_mock=false",
            inv.get("traffic_is_mock_meta") is False,
            inv.get("traffic_is_mock_meta"),
            "False",
        ),
        Check(
            "utic_daegu_sometimes",
            "대구 돌발 >0 인 틱이 한 번이라도",
            inv.get("daegu_positive_ticks", 0) >= 1,
            inv.get("daegu_positive_ticks"),
            ">=1",
            note="어떤 날은 대구 0건일 수 있음 — 히스토리에 양수 틱 필요",
        ),
        Check(
            "utic_gap_soft",
            "주간 extract 간격 median ≈15분",
            inv.get("daytime_median_gap_min") is not None
            and 10 <= float(inv["daytime_median_gap_min"]) <= 20,
            inv.get("daytime_median_gap_min"),
            "10~20분",
            note="미달·초과는 CONDITIONAL",
        ),
    ]
    a = AxisVerdict(
        axis="A_MVP_ops",
        verdict=_verdict(a_checks, soft_ids={"utic_gap_soft", "utic_daegu_sometimes"}),
        score=f"{sum(c.ok for c in a_checks)}/{len(a_checks)}",
        checks=a_checks,
        summary="돌발 루프가 돌고, mock이 아니며, 최근 피드가 살아 있는가.",
    )

    # B) Join / D1
    matched = join.get("matched") or 0
    match_rate = join.get("match_rate")
    daegu_now = inv.get("daegu_records_latest") or 0
    # if daegu=0, matched=0 is OK (soft)
    join_needed = daegu_now > 0
    b_checks = [
        Check(
            "join_meta",
            "조인 meta 존재",
            bool(join.get("ok")),
            join.get("ok"),
            "join_traffic_incident_utic_meta.json",
        ),
        Check(
            "join_matched",
            "1km 매칭 충전소 수",
            (not join_needed) or (int(matched) >= JOIN["min_matched"]),
            matched,
            f">={JOIN['min_matched']} (대구 돌발 {daegu_now}건일 때)",
            note="대구 0건이면 매칭 0도 정상",
        ),
        Check(
            "join_rate_soft",
            "매칭률",
            (not join_needed)
            or (match_rate is not None and float(match_rate) >= JOIN["min_match_rate"]),
            match_rate,
            f">={JOIN['min_match_rate']}",
        ),
        Check(
            "d1_exists",
            "D1 존재",
            bool(d1.get("ok")),
            d1.get("ok"),
            "station_feature_snapshot_latest.csv",
        ),
        Check(
            "d1_source",
            "D1 traffic_source=utic",
            str(d1.get("traffic_source", "")).lower() == "utic",
            d1.get("traffic_source"),
            "utic",
        ),
        Check(
            "d1_not_mock",
            "D1 traffic_is_mock=false",
            d1.get("traffic_is_mock") is False,
            d1.get("traffic_is_mock"),
            "False",
        ),
    ]
    b = AxisVerdict(
        axis="B_spatial_join_D1",
        verdict=_verdict(b_checks, soft_ids={"join_rate_soft"}),
        score=f"{sum(c.ok for c in b_checks)}/{len(b_checks)}",
        checks=b_checks,
        summary="돌발이 충전소 1km 조인·D1 플래그로 MVP 재료에 붙었는가.",
    )

    # C) Forecast — out of scope for MVP
    c_checks = [
        Check(
            "forecast_scope",
            "돌발 발생 예측 모델",
            False,
            "out_of_scope",
            "MVP 비대상 (관측 피드만)",
            note="돌발은 실시간 관측·조인이 목표. 예측 ML은 폐기 기준 아님",
        ),
    ]
    c = AxisVerdict(
        axis="C_incident_forecast_ML",
        verdict="NO",
        score="0/1",
        checks=c_checks,
        summary="돌발 **예측**은 MVP 범위 밖. NO여도 프로젝트 kill 아님.",
    )

    kill = a.verdict == "NO" or b.verdict == "NO"
    if not kill and a.verdict == "GO" and b.verdict == "GO":
        overall = "KEEP_UTIC_FOR_MVP"
    elif not kill:
        overall = "KEEP_BUT_FIX_UTIC_GAPS"
    else:
        overall = "UTIC_MATERIAL_FAIL"

    plain = (
        f"운영(A): {a.verdict} · 조인/D1(B): {b.verdict} · 예측(C): {c.verdict}. "
        + (
            "→ 돌발 재료로 MVP 보조 가능. 예측은 안 함."
            if not kill
            else "→ 돌발 루프/조인부터 고쳐야 함 (폐기 전체가 아니라 돌발 트랙)."
        )
    )

    return {
        "generated_at": now.isoformat(),
        "goal_reminder": (
            "돌발=도착 지연·실패 위험 보조 신호. "
            "KPI는 루프·조인 동작이지 대구 건수 절대값이 아님."
        ),
        "inventory": inv,
        "join": join,
        "d1_traffic": d1,
        "axes": [
            {
                "axis": a.axis,
                "verdict": a.verdict,
                "score": a.score,
                "summary": a.summary,
                "checks": [asdict(x) for x in a.checks],
            },
            {
                "axis": b.axis,
                "verdict": b.verdict,
                "score": b.score,
                "summary": b.summary,
                "checks": [asdict(x) for x in b.checks],
            },
            {
                "axis": c.axis,
                "verdict": c.verdict,
                "score": c.score,
                "summary": c.summary,
                "checks": [asdict(x) for x in c.checks],
            },
        ],
        "overall": overall,
        "project_keep_utic_track": not kill,
        "kill_utic_track": kill,
        "plain_korean": plain,
    }


def _to_md(report: dict[str, Any]) -> str:
    lines = [
        "# UTIC 돌발 타당성 GO/NO-GO",
        "",
        f"| 생성 | `{report['generated_at']}` |",
        f"| 종합 | **{report['overall']}** |",
        f"| 돌발 트랙 유지 | **{report['project_keep_utic_track']}** |",
        f"| 돌발 트랙 실패 | **{report['kill_utic_track']}** |",
        "",
        report.get("plain_korean", ""),
        "",
        "## 목표 리마인드",
        "",
        report.get("goal_reminder", ""),
        "",
        "## 인벤토리",
        "",
    ]
    inv = report.get("inventory", {})
    lines += [
        f"- extract: meta={inv.get('meta_files')} · csv={inv.get('csv_files')} · {inv.get('n_days')}일",
        f"- 기간: {inv.get('first_ts')} → {inv.get('last_ts')}",
        f"- latest age: {inv.get('age_minutes')}분 · 대구 {inv.get('daegu_records_latest')} / 전국 {inv.get('national_records_latest')}",
        f"- 주간 median gap: {inv.get('daytime_median_gap_min')}분",
        f"- 대구>0 틱: {inv.get('daegu_positive_ticks')} · 대구=0 틱: {inv.get('daegu_zero_ticks')}",
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
        "재실행:",
        "```bash",
        "python apps/data-pipeline/evaluation/viability_tests/test_utic_incident_go_nogo_viability.py",
        "```",
        "",
        "```",
        "DA➀ | go-nogo utic viability | auto",
        "```",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    report = evaluate()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "utic_viability_latest.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    md = OUT_DIR / "utic_viability_latest.md"
    md.write_text(_to_md(report), encoding="utf-8")
    print(
        json.dumps(
            {
                "overall": report["overall"],
                "project_keep_utic_track": report["project_keep_utic_track"],
                "kill_utic_track": report["kill_utic_track"],
                "md": str(md),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    print("\n" + report.get("plain_korean", ""))
    return 2 if report.get("kill_utic_track") else 0


if __name__ == "__main__":
    sys.exit(main())
