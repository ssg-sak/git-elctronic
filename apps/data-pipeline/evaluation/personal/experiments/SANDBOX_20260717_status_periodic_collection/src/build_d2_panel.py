"""Build D2 station_feature_panel from status SANDBOX timeseries.

Row unit: statId × panel_ts (docs/data/스키마/데이터셋_명세.md).
Uses gap-safe forward-fill (25 min) from build_panel.py.

Does not train models or compute recommendation scores.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

REPO = Path(__file__).resolve().parents[7]
STATUS_SRC = (
    REPO
    / "apps/data-pipeline/evaluation/personal/experiments"
    / "SANDBOX_20260717_status_periodic_collection"
    / "src"
)
sys.path.insert(0, str(STATUS_SRC))

from build_panel import (  # noqa: E402
    MAX_CONTINUOUS_GAP_MINUTES,
    build_state_panel,
)
from load_snapshots import load_all_snapshots  # noqa: E402

KST = ZoneInfo("Asia/Seoul")
SCHEMA_VERSION = "station_feature_panel_v1"
OUT_DIR = REPO / "apps" / "data-pipeline" / "evaluation" / "results" / "datasets"
HANDOFF = OUT_DIR / "handoff_to_model"

# EvCharger raw codes
STAT_AVAILABLE = 2
STAT_IN_USE = 3


def station_panel_from_charger_panel(wide: pd.DataFrame) -> pd.DataFrame:
    """Aggregate charger-level ffilled panel → station × time features."""
    # columns are "statId|chgerId"
    stations = pd.Index([c.split("|", 1)[0] for c in wide.columns])
    # melt for groupby
    long = wide.stack(future_stack=True).rename("stat").reset_index()
    long.columns = ["panel_ts", "charger", "stat"]
    long["statId"] = long["charger"].str.split("|", n=1).str[0]
    long = long.dropna(subset=["stat"])

    long["is_available"] = long["stat"] == STAT_AVAILABLE
    long["is_in_use"] = long["stat"] == STAT_IN_USE
    long["is_usable"] = long["stat"].isin([STAT_AVAILABLE, STAT_IN_USE])

    g = long.groupby(["statId", "panel_ts"], sort=False)
    out = g.agg(
        known_chargers=("charger", "count"),
        available_count=("is_available", "sum"),
        in_use_count=("is_in_use", "sum"),
        usable_known=("is_usable", "sum"),
    ).reset_index()
    out["available_count"] = out["available_count"].astype(int)
    out["in_use_count"] = out["in_use_count"].astype(int)
    out["usable_known"] = out["usable_known"].astype(int)
    out["known_chargers"] = out["known_chargers"].astype(int)

    # F01-style among usable known (avail / (avail+in_use)); null if none usable
    out["availability_ratio_observed"] = out.apply(
        lambda r: (r["available_count"] / r["usable_known"])
        if r["usable_known"] > 0
        else pd.NA,
        axis=1,
    )
    out["has_confirmed_available"] = out["available_count"] >= 1

    # segment id from time gaps
    ts_order = out[["panel_ts"]].drop_duplicates().sort_values("panel_ts")
    seg = (
        ts_order["panel_ts"]
        .diff()
        .gt(pd.Timedelta(minutes=MAX_CONTINUOUS_GAP_MINUTES))
        .cumsum()
    )
    ts_order = ts_order.assign(segment_id=seg.values)
    out = out.merge(ts_order, on="panel_ts", how="left")

    # lags per station
    out = out.sort_values(["statId", "panel_ts"])
    out["avail_rate_lag_15m"] = out.groupby("statId")["availability_ratio_observed"].shift(1)
    # ~4 * 15m steps ≈ 60m if interval is 15m
    out["avail_rate_lag_60m"] = out.groupby("statId")["availability_ratio_observed"].shift(4)

    out["schema_version"] = SCHEMA_VERSION
    out["source_status"] = "sandbox_series"
    return out


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    HANDOFF.mkdir(parents=True, exist_ok=True)

    print("loading snapshots…")
    raw = load_all_snapshots()
    if raw.empty:
        print("no snapshots")
        return 1

    print("building charger panel…")
    wide = build_state_panel(raw)
    print(f"panel shape={wide.shape}")

    print("aggregating to stations…")
    panel = station_panel_from_charger_panel(wide)

    stamp = datetime.now(KST).strftime("%Y%m%d_%H%M%S")
    base = f"station_feature_panel_{stamp}"
    csv_path = OUT_DIR / f"{base}.csv"
    pq_path = OUT_DIR / f"{base}.parquet"
    panel.to_csv(csv_path, index=False, encoding="utf-8-sig")
    panel.to_parquet(pq_path, index=False)

    sample = panel.head(50)
    sample_path = HANDOFF / "station_feature_panel_sample_50.csv"
    sample.to_csv(sample_path, index=False, encoding="utf-8-sig")

    meta = {
        "schema_version": SCHEMA_VERSION,
        "dataset": "D2_station_feature_panel",
        "row_unit": "statId × panel_ts",
        "rows": int(len(panel)),
        "stations": int(panel["statId"].nunique()),
        "panel_timestamps": int(panel["panel_ts"].nunique()),
        "gap_safe_minutes": MAX_CONTINUOUS_GAP_MINUTES,
        "source_snapshots": int(raw["snapshotId"].nunique()),
        "source_rows_deduped": int(len(raw)),
        "files": {
            "full_csv": str(csv_path.relative_to(REPO)).replace("\\", "/"),
            "full_parquet": str(pq_path.relative_to(REPO)).replace("\\", "/"),
            "sample_csv": str(sample_path.relative_to(REPO)).replace("\\", "/"),
        },
        "spec": "docs/data/스키마/데이터셋_명세.md",
        "owner": "AI·data ①",
        "consumer": "AI·data ②",
        "note": "availability among usable known (stat 2/3); other codes counted in known_chargers but not in usable_known denominator",
    }
    (HANDOFF / "HANDOFF_META_D2.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    print(json.dumps(meta, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
