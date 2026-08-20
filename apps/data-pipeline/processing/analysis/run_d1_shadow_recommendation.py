"""Run a transparent D1 integration test without a recommendation score.

This is a QA/shadow output, not the AI·data ② ranking model:
- filters to public, coordinate-valid, confirmed-available stations;
- groups fresh/operating candidates ahead of candidates needing confirmation;
- orders only by straight-line distance from the supplied test point.

Usage (repo root):
  python apps/data-pipeline/processing/analysis/run_d1_shadow_recommendation.py
  python apps/data-pipeline/processing/analysis/run_d1_shadow_recommendation.py \
    --lat 35.8714 --lng 128.6014 --label "대구시청"
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib.pyplot as plt
import pandas as pd

import sys

_PROCESSING = Path(__file__).resolve().parents[1]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))
from _bootstrap import ensure_paths

REPO = ensure_paths()
KST = ZoneInfo("Asia/Seoul")
D1 = REPO / "apps/data-pipeline/evaluation/results/datasets/station_feature_snapshot_latest.csv"
plt.rcParams["font.family"] = ["Malgun Gothic", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False


def truth(df: pd.DataFrame, column: str) -> pd.Series:
    return df[column].astype(str).str.lower().isin(("true", "1", "yes"))


def distance_m(lat: pd.Series, lng: pd.Series, origin_lat: float, origin_lng: float) -> pd.Series:
    r = 6_371_000
    lat1, lng1 = math.radians(origin_lat), math.radians(origin_lng)
    lat2, lng2 = lat.astype(float).map(math.radians), lng.astype(float).map(math.radians)
    a = (
        (lat2 - lat1).map(lambda value: math.sin(value / 2) ** 2)
        + math.cos(lat1)
        * lat2.map(math.cos)
        * (lng2 - lng1).map(lambda value: math.sin(value / 2) ** 2)
    )
    return a.clip(0, 1).map(lambda value: 2 * r * math.asin(math.sqrt(value)))


def reason(row: pd.Series) -> str:
    reasons = [
        f"공용 후보(limitYn 제한 없음)",
        f"확정 사용 가능 {int(row['available_count'])}/{int(row['total_chargers'])}대",
        f"상태 신뢰도 {row['reliability_grade_effective']}",
        f"운영 여부 {row['is_operating_now']}",
    ]
    if pd.notna(row["nearest_parking_m"]):
        reasons.append(f"Team5 주차장 {row['nearest_parking_m']:.0f}m")
    if pd.notna(row["parking_remaining_spaces"]):
        reasons.append(f"주차 잔여 {row['parking_remaining_spaces']:.0f}면")
    if pd.notna(row["nearest_incident_m"]):
        reasons.append(f"UTIC 돌발 {row['nearest_incident_m']:.0f}m")
    if pd.notna(row["usage_level"]):
        reasons.append(f"과거 이용강도 {row['usage_level']}")
    if row["total_chargers"] <= 1:
        reasons.append("충전기 1대: 대기·실패 위험 주의")
    if row["is_operating_now"] == "UNKNOWN":
        reasons.append("운영시간 미확인")
    if row["reliability_grade_effective"] == "CHECK_REQUIRED":
        reasons.append("상태 재확인 필요")
    if pd.notna(row["parking_remaining_spaces"]) and row["parking_remaining_spaces"] <= 0:
        reasons.append("인근 주차장 만차")
    return " · ".join(reasons)


def style(ax) -> None:
    ax.set_facecolor("#ffffff")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=0.2)


def plot_funnel(counts: list[tuple[str, int]], fig_dir: Path) -> Path:
    labels, values = zip(*counts, strict=True)
    fig, ax = plt.subplots(figsize=(10, 4.8), facecolor="#f7f8fa")
    style(ax)
    bars = ax.bar(labels, values, color=["#9aa5b1", "#4c78a8", "#54a24b", "#f58518", "#18794e"])
    ax.set_title("D1 → Shadow 후보 추출 흐름", loc="left", fontweight="bold")
    ax.set_ylabel("충전소 수")
    ax.tick_params(axis="x", labelrotation=12)
    for bar, value in zip(bars, values, strict=True):
        ax.text(bar.get_x() + bar.get_width() / 2, value + max(values) * 0.02, f"{value:,}", ha="center")
    out = fig_dir / "01_candidate_funnel.png"
    fig.savefig(out, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_top_candidates(shown: pd.DataFrame, fig_dir: Path) -> Path:
    top = shown.sort_values("distance_from_test_m", ascending=False)
    labels = [f"{row.shadow_display_rank}. {row.statNm}" for row in top.itertuples()]
    colors = ["#18794e" if row.shadow_tier.startswith("A") else "#f58518" for row in top.itertuples()]
    fig, ax = plt.subplots(figsize=(11, 6), facecolor="#f7f8fa")
    style(ax)
    bars = ax.barh(labels, top["distance_from_test_m"], color=colors)
    ax.set_title("표시 후보 Top10 — 테스트 위치 직선거리", loc="left", fontweight="bold")
    ax.set_xlabel("거리 (m) · ETA 아님")
    for bar, row in zip(bars, top.itertuples(), strict=True):
        ax.text(
            bar.get_width() + max(top["distance_from_test_m"]) * 0.01,
            bar.get_y() + bar.get_height() / 2,
            f"{row.available_count:.0f}/{row.total_chargers:.0f}대 · {row.reliability_grade_effective}",
            va="center",
            fontsize=8,
        )
    ax.set_xlim(0, max(top["distance_from_test_m"]) * 1.35)
    out = fig_dir / "02_top_candidates_distance.png"
    fig.savefig(out, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_evidence_coverage(eligible: pd.DataFrame, fig_dir: Path) -> Path:
    coverage = [
        ("상태·가용", len(eligible)),
        ("Team5 거리", int(eligible["nearest_parking_m"].notna().sum())),
        ("Team5 realtime", int(eligible["parking_remaining_spaces"].notna().sum())),
        ("UTIC 1km", int(eligible["nearest_incident_m"].notna().sum())),
        ("이용이력", int(eligible["usage_level"].notna().sum())),
    ]
    labels, values = zip(*coverage, strict=True)
    fig, ax = plt.subplots(figsize=(9, 4.8), facecolor="#f7f8fa")
    style(ax)
    bars = ax.bar(labels, values, color=["#4c78a8", "#54a24b", "#72b7b2", "#e45756", "#f58518"])
    ax.set_title("Shadow 후보에 붙은 통합 근거 커버리지", loc="left", fontweight="bold")
    ax.set_ylabel("후보 수")
    for bar, value in zip(bars, values, strict=True):
        ax.text(bar.get_x() + bar.get_width() / 2, value + len(eligible) * 0.02, f"{value:,}", ha="center")
    out = fig_dir / "03_evidence_coverage.png"
    fig.savefig(out, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="D1 transparent shadow recommendation test")
    parser.add_argument("--lat", type=float, default=35.8714, help="Test origin latitude")
    parser.add_argument("--lng", type=float, default=128.6014, help="Test origin longitude")
    parser.add_argument("--label", default="대구시청", help="Human-readable test origin")
    parser.add_argument("--limit", type=int, default=10, help="Displayed candidates")
    args = parser.parse_args()

    d1 = pd.read_csv(D1, low_memory=False)
    d1["lat"] = pd.to_numeric(d1["lat"], errors="coerce")
    d1["lng"] = pd.to_numeric(d1["lng"], errors="coerce")
    for column in (
        "available_count",
        "total_chargers",
        "nearest_parking_m",
        "parking_remaining_spaces",
        "nearest_incident_m",
    ):
        d1[column] = pd.to_numeric(d1[column], errors="coerce")

    public = truth(d1, "recommend_public_default")
    coord = truth(d1, "coord_ok") & d1["lat"].notna() & d1["lng"].notna()
    available = truth(d1, "has_confirmed_available")
    operating = d1["is_operating_now"].fillna("UNKNOWN").ne("N")
    eligible = d1[public & coord & available & operating].copy()
    eligible["distance_from_test_m"] = distance_m(
        eligible["lat"], eligible["lng"], args.lat, args.lng
    )
    fresh = eligible["reliability_grade_effective"].isin(("HIGH", "NORMAL"))
    operating_yes = eligible["is_operating_now"].eq("Y")
    eligible["shadow_tier"] = (fresh & operating_yes).map(
        {True: "A: 즉시 후보", False: "B: 확인 후 후보"}
    )
    eligible["evidence"] = eligible.apply(reason, axis=1)
    eligible = eligible.sort_values(
        ["shadow_tier", "distance_from_test_m", "available_count"],
        ascending=[True, True, False],
    ).reset_index(drop=True)
    eligible.insert(0, "shadow_display_rank", eligible.index + 1)

    rejected = {
        "access_restricted": int((~public).sum()),
        "invalid_or_missing_coordinate": int((public & ~coord).sum()),
        "no_confirmed_available_charger": int((public & coord & ~available).sum()),
        "known_closed_now": int((public & coord & available & ~operating).sum()),
    }
    now = datetime.now(KST)
    out = REPO / "docs/data/analysis" / f"shadow_recommendation_{now:%Y%m%d}"
    out.mkdir(parents=True, exist_ok=True)
    fig_dir = out / "figures"
    fig_dir.mkdir(exist_ok=True)
    shown = eligible.head(max(args.limit, 1)).copy()
    columns = [
        "shadow_display_rank",
        "shadow_tier",
        "statId",
        "statNm",
        "addr",
        "distance_from_test_m",
        "available_count",
        "total_chargers",
        "reliability_grade_effective",
        "is_operating_now",
        "nearest_parking_m",
        "parking_remaining_spaces",
        "nearest_incident_m",
        "usage_level",
        "evidence",
    ]
    shown[columns].to_csv(out / "top_candidates.csv", index=False, encoding="utf-8-sig")
    funnel = [
        ("전체 D1", len(d1)),
        ("공용 후보", int(public.sum())),
        ("좌표 정상", int((public & coord).sum())),
        ("확정 가용", int((public & coord & available).sum())),
        ("출력 후보", len(eligible)),
    ]
    figures = [
        plot_funnel(funnel, fig_dir),
        plot_top_candidates(shown, fig_dir),
        plot_evidence_coverage(eligible, fig_dir),
    ]
    summary = {
        "generated_at_kst": now.isoformat(timespec="seconds"),
        "test_origin": {"label": args.label, "lat": args.lat, "lng": args.lng},
        "d1_as_of_ts": str(d1["as_of_ts"].iloc[0]),
        "pipeline": "D1 → public/coordinate/available/operating filter → freshness tier → distance display order",
        "not_a_model_score": True,
        "input_rows": int(len(d1)),
        "eligible_rows": int(len(eligible)),
        "tier_counts": {
            str(key): int(value) for key, value in eligible["shadow_tier"].value_counts().items()
        },
        "rejected": rejected,
        "files": {
            "top_candidates": "top_candidates.csv",
            "figures": [str(path.relative_to(out)).replace("\\", "/") for path in figures],
        },
        "limitations": [
            "No ETA: distance is only a display-order tie-breaker.",
            "No final score or weight is calculated.",
            "D1 must be rebuilt after source updates before current-use claims.",
        ],
    }
    (out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    rows = "\n".join(
        f"| {r.shadow_display_rank} | {r.shadow_tier} | {r.statNm} | "
        f"{r.distance_from_test_m:.0f}m | {r.available_count:.0f}/{r.total_chargers:.0f} | "
        f"{r.reliability_grade_effective} | {r.is_operating_now} |"
        for r in shown.itertuples()
    )
    report = f"""# D1 Shadow 추천 테스트 — {args.label}

| 항목 | 값 |
|---|---|
| 테스트 위치 | {args.label} ({args.lat}, {args.lng}) |
| D1 기준시각 | {summary["d1_as_of_ts"]} |
| 전체 D1 | {summary["input_rows"]:,} |
| 출력 가능 후보 | {summary["eligible_rows"]:,} |
| A: 즉시 후보 | {summary["tier_counts"].get("A: 즉시 후보", 0):,} |
| B: 확인 후 후보 | {summary["tier_counts"].get("B: 확인 후 후보", 0):,} |

## 출력 흐름

`D1 → 공용 후보 → 좌표 정상 → 확정 가용 ≥1 → 운영 중/미확인 → 신선도 tier → 직선거리 표시 순서`

이는 **통합 데이터 흐름 QA**다. 최종 점수·가중치·ETA·실패 위험도는 계산하지 않았으며,
AI·데이터 ②/백엔드 구현 전에는 이 결과를 실제 순위나 도착 성공 확률로 표현하지 않는다.

## 표시 후보 Top {len(shown)}

| 표시 순서 | tier | 충전소 | 테스트 위치 직선거리 | 사용 가능/전체 | 신뢰도 | 운영 |
|---:|---|---|---:|---:|---|---|
{rows}

각 후보의 모든 근거는 [`top_candidates.csv`](./top_candidates.csv)의 `evidence` 열에 기록했다.

## 시각자료

![후보 추출 흐름](figures/01_candidate_funnel.png)

![Top 후보 거리](figures/02_top_candidates_distance.png)

![통합 근거 커버리지](figures/03_evidence_coverage.png)

## 제외 근거

| 제외 사유 | 충전소 수 |
|---|---:|
| 이용 제한 | {rejected["access_restricted"]:,} |
| 공용이나 좌표 없음/비정상 | {rejected["invalid_or_missing_coordinate"]:,} |
| 공용·좌표 정상이나 확정 가용 없음 | {rejected["no_confirmed_available_charger"]:,} |
| 현재 운영 중지로 표시 | {rejected["known_closed_now"]:,} |

```
DA① | D1 shadow integration test | {now:%Y%m%d}
```
"""
    (out / "README.md").write_text(report, encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"OUT {out.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
