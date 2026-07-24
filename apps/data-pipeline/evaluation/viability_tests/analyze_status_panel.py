"""Analyze D2 status timeseries panel (gap-safe forward-fill).

Does not train models or score stations — DA➀ materials only.

  python apps/data-pipeline/evaluation/viability_tests/analyze_status_panel.py

Inputs (prefer newest parquet under results/datasets/):
  station_feature_panel_*.parquet
  or rebuild via SANDBOX .../build_d2_panel.py

Outputs:
  evaluation/results/status_panel_analysis/
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib.pyplot as plt
import pandas as pd

HERE = Path(__file__).resolve().parent


def _repo_root() -> Path:
    for p in [HERE, *HERE.parents]:
        if (p / "AGENTS.md").exists() and (p / "apps" / "data-pipeline").exists():
            return p
    raise RuntimeError("repo root not found")


REPO = _repo_root()
DATASETS = REPO / "apps/data-pipeline/evaluation/results/datasets"
OUT = REPO / "apps/data-pipeline/evaluation/results/status_panel_analysis"
STATUS_SRC = (
    REPO
    / "apps/data-pipeline/evaluation/personal/experiments"
    / "SANDBOX_20260717_status_periodic_collection"
    / "src"
)
KST = ZoneInfo("Asia/Seoul")


def _latest_panel() -> Path:
    cands = sorted(DATASETS.glob("station_feature_panel_20*.parquet"))
    if not cands:
        cands = sorted(DATASETS.glob("station_feature_panel_20*.csv"))
    if not cands:
        raise FileNotFoundError("no station_feature_panel_* — run build_d2_panel.py first")
    return cands[-1]


def _point_latest(src: Path) -> None:
    for ext in (".parquet", ".csv"):
        if src.suffix == ext:
            dest = DATASETS / f"station_feature_panel_latest{ext}"
            dest.write_bytes(src.read_bytes())
            # also copy sibling if exists
            sib = src.with_suffix(".csv" if ext == ".parquet" else ".parquet")
            if sib.exists():
                (DATASETS / f"station_feature_panel_latest{sib.suffix}").write_bytes(
                    sib.read_bytes()
                )


def _fleet_from_station_panel(panel: pd.DataFrame) -> pd.DataFrame:
    """Aggregate station×time → fleet timeseries (equal weight per station with known usable)."""
    df = panel.copy()
    df["panel_ts"] = pd.to_datetime(df["panel_ts"])
    df["available_count"] = pd.to_numeric(df["available_count"], errors="coerce")
    df["usable_known"] = pd.to_numeric(df["usable_known"], errors="coerce")
    g = df.groupby("panel_ts", sort=True)
    out = g.agg(
        stations=("statId", "nunique"),
        available_sum=("available_count", "sum"),
        usable_sum=("usable_known", "sum"),
        confirmed_stations=("has_confirmed_available", "sum"),
    ).reset_index()
    out["fleet_avail_pct"] = out["available_sum"] / out["usable_sum"] * 100
    out["confirmed_station_pct"] = out["confirmed_stations"] / out["stations"] * 100
    out["hour"] = out["panel_ts"].dt.hour
    out["date"] = out["panel_ts"].dt.date
    out["dow"] = out["panel_ts"].dt.dayofweek
    # segments from 25m gaps
    out["segment_id"] = (
        out["panel_ts"].diff().gt(pd.Timedelta(minutes=25)).cumsum()
    )
    return out


def _bias_compare() -> dict:
    sys.path.insert(0, str(STATUS_SRC))
    from build_panel import bias_summary  # noqa: E402

    return bias_summary()


def _plots(fleet: pd.DataFrame, hourly: pd.Series, by_day: pd.DataFrame) -> list[str]:
    OUT.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []

    fig, ax = plt.subplots(figsize=(11, 4))
    ax.plot(fleet["panel_ts"], fleet["fleet_avail_pct"], lw=1.2, color="#1f4e79")
    ax.set_title("Fleet availability % (panel, usable known)")
    ax.set_ylabel("%")
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    p1 = OUT / "fleet_availability_timeseries.png"
    fig.tight_layout()
    fig.savefig(p1, dpi=120)
    plt.close(fig)
    paths.append(str(p1.relative_to(REPO)).replace("\\", "/"))

    fig, ax = plt.subplots(figsize=(8, 4))
    hourly.plot(kind="bar", ax=ax, color="#2e75b6")
    ax.set_title("Mean availability % by hour (KST)")
    ax.set_xlabel("hour")
    ax.set_ylabel("%")
    ax.grid(True, axis="y", alpha=0.3)
    p2 = OUT / "availability_by_hour.png"
    fig.tight_layout()
    fig.savefig(p2, dpi=120)
    plt.close(fig)
    paths.append(str(p2.relative_to(REPO)).replace("\\", "/"))

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(by_day["date"].astype(str), by_day["fleet_avail_pct"], color="#548235")
    ax.set_title("Mean availability % by day")
    ax.set_ylabel("%")
    ax.tick_params(axis="x", rotation=30)
    ax.grid(True, axis="y", alpha=0.3)
    p3 = OUT / "availability_by_day.png"
    fig.tight_layout()
    fig.savefig(p3, dpi=120)
    plt.close(fig)
    paths.append(str(p3.relative_to(REPO)).replace("\\", "/"))

    fig, ax = plt.subplots(figsize=(11, 3.5))
    ax.plot(fleet["panel_ts"], fleet["stations"], lw=1.0, color="#833c0c")
    ax.set_title("Stations present in panel over time")
    ax.set_ylabel("n stations")
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    p4 = OUT / "stations_in_panel_over_time.png"
    fig.tight_layout()
    fig.savefig(p4, dpi=120)
    plt.close(fig)
    paths.append(str(p4.relative_to(REPO)).replace("\\", "/"))

    return paths


def main() -> int:
    panel_path = _latest_panel()
    print(f"loading {panel_path.name}…", flush=True)
    if panel_path.suffix == ".parquet":
        panel = pd.read_parquet(panel_path)
    else:
        panel = pd.read_csv(panel_path)

    _point_latest(panel_path)

    fleet = _fleet_from_station_panel(panel)
    hourly = fleet.groupby("hour")["fleet_avail_pct"].mean()
    by_day = (
        fleet.groupby("date", as_index=False)["fleet_avail_pct"]
        .mean()
        .sort_values("date")
    )
    n_seg = int(fleet["segment_id"].nunique())

    print("bias_summary (row vs panel)…", flush=True)
    try:
        bias = _bias_compare()
    except Exception as exc:  # noqa: BLE001
        bias = {"error": str(exc)}

    # station-level: how often confirmed available
    st = panel.copy()
    st["has_confirmed_available"] = st["has_confirmed_available"].astype(bool)
    st_rate = st.groupby("statId")["has_confirmed_available"].mean()
    station_summary = {
        "stations": int(panel["statId"].nunique()),
        "panel_timestamps": int(panel["panel_ts"].nunique()),
        "rows": int(len(panel)),
        "mean_confirmed_rate_across_stations": round(float(st_rate.mean()), 3),
        "stations_confirmed_gt_50pct_of_ticks": int((st_rate > 0.5).sum()),
        "stations_confirmed_lt_10pct_of_ticks": int((st_rate < 0.1).sum()),
    }

    charts = _plots(fleet, hourly, by_day)
    fleet.to_csv(OUT / "fleet_timeseries.csv", index=False, encoding="utf-8-sig")
    hourly.to_csv(OUT / "availability_by_hour.csv", header=["fleet_avail_pct"])
    by_day.to_csv(OUT / "availability_by_day.csv", index=False, encoding="utf-8-sig")

    meta = {
        "generated_at": datetime.now(tz=KST).isoformat(),
        "panel_file": str(panel_path.relative_to(REPO)).replace("\\", "/"),
        "latest_pointer": "apps/data-pipeline/evaluation/results/datasets/station_feature_panel_latest.parquet",
        "segments_25m": n_seg,
        "fleet": {
            "ticks": int(len(fleet)),
            "avail_pct_mean": round(float(fleet["fleet_avail_pct"].mean()), 2),
            "avail_pct_median": round(float(fleet["fleet_avail_pct"].median()), 2),
            "avail_pct_min": round(float(fleet["fleet_avail_pct"].min()), 2),
            "avail_pct_max": round(float(fleet["fleet_avail_pct"].max()), 2),
            "first_ts": str(fleet["panel_ts"].iloc[0]),
            "last_ts": str(fleet["panel_ts"].iloc[-1]),
        },
        "hourly_mean": {str(int(k)): round(float(v), 2) for k, v in hourly.items()},
        "by_day": [
            {"date": str(r.date), "fleet_avail_pct": round(float(r.fleet_avail_pct), 2)}
            for r in by_day.itertuples(index=False)
        ],
        "station_summary": station_summary,
        "bias_row_vs_panel": bias,
        "charts": charts,
        "note": (
            "Panel forward-fills within ≤25m gaps so quiet chargers are not under-weighted. "
            "Night PC-off starts new segments — do not treat as continuous overnight series."
        ),
    }
    (OUT / "analysis_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )

    md = [
        "# Status 시계열 패널 분석 (D2)",
        "",
        f"| 생성 | `{meta['generated_at']}` |",
        f"| 패널 | `{meta['panel_file']}` |",
        f"| 세그먼트(25분 gap) | **{n_seg}** |",
        "",
        "## 한 줄",
        "",
        f"패널 통합 후 플릿 가용률 mean **{meta['fleet']['avail_pct_mean']}%** "
        f"(median {meta['fleet']['avail_pct_median']}%). "
        f"충전소 {station_summary['stations']} · 시각 {station_summary['panel_timestamps']}틱 · 행 {station_summary['rows']:,}.",
        "",
        "## 왜 패널인가",
        "",
        "status API는 **변경분**만 준다. 원본 행을 그냥 평균하면 바쁜 충전기가 과대 반영된다. "
        "패널은 연속 구간(≤25분) 안에서 마지막 상태를 forward-fill해 **충전기/소를 균등**하게 본다.",
        "",
        "## 플릿 가용률",
        "",
        f"- 기간: {meta['fleet']['first_ts']} → {meta['fleet']['last_ts']}",
        f"- mean/median/min/max %: "
        f"**{meta['fleet']['avail_pct_mean']}** / {meta['fleet']['avail_pct_median']} / "
        f"{meta['fleet']['avail_pct_min']} / {meta['fleet']['avail_pct_max']}",
        "",
        "### 요일별(일자)",
        "",
        "| date | avail % |",
        "|---|---:|",
    ]
    for row in meta["by_day"]:
        md.append(f"| {row['date']} | {row['fleet_avail_pct']} |")
    md += [
        "",
        "### 시간대 mean %",
        "",
        "| hour | avail % |",
        "|---:|---:|",
    ]
    for h, v in sorted(meta["hourly_mean"].items(), key=lambda x: int(x[0])):
        md.append(f"| {h} | {v} |")

    md += [
        "",
        "## 충전소 단위",
        "",
        f"- 틱 중 확정가용 비율 평균: **{station_summary['mean_confirmed_rate_across_stations']}**",
        f"- 틱의 50% 이상에서 확정가용: **{station_summary['stations_confirmed_gt_50pct_of_ticks']}**소",
        f"- 틱의 10% 미만에서만 확정가용: **{station_summary['stations_confirmed_lt_10pct_of_ticks']}**소",
        "",
        "## 편향 비교 (원본 행 vs 패널)",
        "",
        "```json",
        json.dumps(bias, ensure_ascii=False, indent=2, default=str),
        "```",
        "",
        "## 차트",
        "",
    ]
    for c in charts:
        md.append(f"- `{c}`")
    md += [
        "",
        "## 해석 (MVP)",
        "",
        "- **실시간 추천 재료**: D1 스냅샷 + 이 패널의 시간대 패턴(참고) — OK",
        "- **야간 연속 시계열**: 세그먼트가 끊김 → 밤새 패턴 단정 금지",
        "- **예측 ML**: 여전히 일수·밀도 부족 (viability 테스트 참고)",
        "",
        "재실행:",
        "```bash",
        "python apps/data-pipeline/evaluation/personal/experiments/SANDBOX_20260717_status_periodic_collection/src/build_d2_panel.py",
        "python apps/data-pipeline/evaluation/viability_tests/analyze_status_panel.py",
        "```",
        "",
        "```",
        "DA➀ | status panel analysis | auto",
        "```",
        "",
    ]
    report = OUT / "README.md"
    report.write_text("\n".join(md), encoding="utf-8")
    # also copy friendly name
    (OUT / "패널_분석_보고서.md").write_text("\n".join(md), encoding="utf-8")

    print(
        json.dumps(
            {
                "ok": True,
                "report": str(report.relative_to(REPO)).replace("\\", "/"),
                "fleet_avail_pct_mean": meta["fleet"]["avail_pct_mean"],
                "stations": station_summary["stations"],
                "segments": n_seg,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
