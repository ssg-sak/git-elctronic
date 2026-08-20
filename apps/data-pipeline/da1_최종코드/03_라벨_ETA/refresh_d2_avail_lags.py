"""Recompute D2 avail_rate_lag_15m/60m on latest panel (no full snapshot rebuild).

Default: parquet + sample only (CSV of ~4M rows is optional via --with-csv).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

REPO = Path(__file__).resolve().parents[4]
STATUS_SRC = (
    REPO
    / "apps/data-pipeline/evaluation/personal/experiments"
    / "SANDBOX_20260717_status_periodic_collection"
    / "src"
)
sys.path.insert(0, str(STATUS_SRC))
from build_d2_panel import add_avail_rate_time_lags  # noqa: E402

KST = ZoneInfo("Asia/Seoul")
OUT_DIR = REPO / "apps/data-pipeline/evaluation/results/datasets"
HANDOFF = OUT_DIR / "handoff_to_model"
REPORT = REPO / "docs/data/analysis/d2_lag_align_20260731"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--with-csv",
        action="store_true",
        help="Also rewrite latest/stamped CSV (slow on full panel)",
    )
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    src = OUT_DIR / "station_feature_panel_latest.parquet"
    if not src.exists():
        raise FileNotFoundError(src)
    print(f"loading {src}...")
    panel = pd.read_parquet(src)
    before_15 = (
        float(panel["avail_rate_lag_15m"].isna().mean())
        if "avail_rate_lag_15m" in panel
        else None
    )
    before_60 = (
        float(panel["avail_rate_lag_60m"].isna().mean())
        if "avail_rate_lag_60m" in panel
        else None
    )

    s = panel.sort_values(["statId", "panel_ts"]).copy()
    s["prev_ts"] = s.groupby("statId")["panel_ts"].shift(1)
    s["prev_seg"] = s.groupby("statId")["segment_id"].shift(1)
    s["dt"] = (s["panel_ts"] - s["prev_ts"]).dt.total_seconds() / 60.0
    cross_seg = s["segment_id"].ne(s["prev_seg"]) & s["prev_seg"].notna()
    leak_before = (
        int((s["avail_rate_lag_15m"].notna() & s["dt"].gt(25) & cross_seg).sum())
        if "avail_rate_lag_15m" in s.columns
        else None
    )

    print("recomputing time-based lags...")
    panel = add_avail_rate_time_lags(panel)

    stamp = datetime.now(KST).strftime("%Y%m%d_%H%M%S")
    pq = OUT_DIR / f"station_feature_panel_{stamp}.parquet"
    latest_pq = OUT_DIR / "station_feature_panel_latest.parquet"
    print(f"writing {pq.name} + latest parquet...")
    panel.to_parquet(pq, index=False)
    panel.to_parquet(latest_pq, index=False)

    csv = None
    latest_csv = OUT_DIR / "station_feature_panel_latest.csv"
    if args.with_csv:
        csv = OUT_DIR / f"station_feature_panel_{stamp}.csv"
        print("writing csv (slow)...")
        panel.to_csv(latest_csv, index=False, encoding="utf-8-sig")
        panel.to_csv(csv, index=False, encoding="utf-8-sig")

    HANDOFF.mkdir(parents=True, exist_ok=True)
    panel.head(50).to_csv(
        HANDOFF / "station_feature_panel_sample_50.csv",
        index=False,
        encoding="utf-8-sig",
    )

    after_15 = float(panel["avail_rate_lag_15m"].isna().mean())
    after_60 = float(panel["avail_rate_lag_60m"].isna().mean())

    new_lags = panel[
        ["statId", "panel_ts", "segment_id", "avail_rate_lag_15m", "avail_rate_lag_60m"]
    ]
    # cross-segment first ticks after long gap must not carry lag from old segment
    long_gap = s.loc[s["dt"].gt(25) & cross_seg, ["statId", "panel_ts", "segment_id", "dt"]]
    chk = long_gap.merge(new_lags, on=["statId", "panel_ts", "segment_id"], how="left")
    leak_after = int(chk["avail_rate_lag_15m"].notna().sum()) if len(chk) else 0
    gap_null15 = float(chk["avail_rate_lag_15m"].isna().mean()) if len(chk) else None

    REPORT.mkdir(parents=True, exist_ok=True)
    summary = {
        "generated_at": datetime.now(KST).isoformat(),
        "rows": int(len(panel)),
        "stations": int(panel["statId"].nunique()),
        "panel_ts_min": str(panel["panel_ts"].min()),
        "panel_ts_max": str(panel["panel_ts"].max()),
        "null_rate_before": {"lag_15m": before_15, "lag_60m": before_60},
        "null_rate_after": {"lag_15m": after_15, "lag_60m": after_60},
        "cross_segment_long_gap_rows": int(len(chk)),
        "cross_segment_lag15_filled_before": leak_before,
        "cross_segment_lag15_filled_after": leak_after,
        "cross_segment_lag15_null_rate_after": gap_null15,
        "definition": {
            "avail_rate_lag_15m": "availability_ratio_observed at latest same-segment tick in [t-27m, t-15m]",
            "avail_rate_lag_60m": "availability_ratio_observed at latest same-segment tick in [t-75m, t-60m]",
            "no_cross_segment": True,
        },
        "files": {
            "latest_parquet": str(latest_pq.relative_to(REPO)).replace("\\", "/"),
            "stamped_parquet": str(pq.relative_to(REPO)).replace("\\", "/"),
            "csv_rewritten": bool(args.with_csv),
        },
        "easy_doc": "docs/팀공유/D2_lag정합_쉬운설명_20260731.md",
    }
    (REPORT / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    meta_path = HANDOFF / "HANDOFF_META_D2.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    files = dict(meta.get("files") or {})
    files["full_parquet"] = str(pq.relative_to(REPO)).replace("\\", "/")
    files["latest_parquet"] = str(latest_pq.relative_to(REPO)).replace("\\", "/")
    if csv is not None:
        files["full_csv"] = str(csv.relative_to(REPO)).replace("\\", "/")
        files["latest_csv"] = str(latest_csv.relative_to(REPO)).replace("\\", "/")
    meta.update(
        {
            "rows": int(len(panel)),
            "stations": int(panel["statId"].nunique()),
            "panel_timestamps": int(panel["panel_ts"].nunique()),
            "lag_policy": summary["definition"],
            "lag_refreshed_at": summary["generated_at"],
            "files": files,
        }
    )
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
