"""Build D2 station_feature_panel from status SANDBOX timeseries.

Row unit: statId × panel_ts (docs/data/스키마/데이터셋_명세.md).
Uses gap-safe forward-fill (25 min) from build_panel.py.

Does not train models or compute recommendation scores.
"""
from __future__ import annotations

import json
import os
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
    """Aggregate charger-level ffilled panel → station × time features.

    Avoids a full melt/stack (which OOMs/thrashes on ~3k×20k panels).
    Aggregates per-station column groups with vectorized counts.
    """
    from collections import defaultdict

    groups: dict[str, list[str]] = defaultdict(list)
    for col in wide.columns:
        groups[str(col).split("|", 1)[0]].append(col)

    parts: list[pd.DataFrame] = []
    n_stations = len(groups)
    for i, (sid, cols) in enumerate(groups.items(), start=1):
        if i == 1 or i % 500 == 0 or i == n_stations:
            print(f"  aggregating stations {i}/{n_stations}…", flush=True)
        sub = wide[cols]
        known = sub.notna().sum(axis=1)
        available = (sub == STAT_AVAILABLE).sum(axis=1)
        in_use = (sub == STAT_IN_USE).sum(axis=1)
        usable = available + in_use
        part = pd.DataFrame(
            {
                "statId": sid,
                "panel_ts": wide.index,
                "known_chargers": known.astype("int32"),
                "available_count": available.astype("int32"),
                "in_use_count": in_use.astype("int32"),
                "usable_known": usable.astype("int32"),
            }
        )
        # keep only ticks where at least one charger is known (matches prior melt dropna)
        part = part.loc[part["known_chargers"].gt(0)]
        parts.append(part)

    out = pd.concat(parts, ignore_index=True)
    out["availability_ratio_observed"] = (
        out["available_count"].div(out["usable_known"]).where(out["usable_known"].gt(0))
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

    # True calendar lags (not row-shift): same station + same segment only.
    print("  attaching avail_rate lags…", flush=True)
    out = add_avail_rate_time_lags(out)

    out["schema_version"] = SCHEMA_VERSION
    out["source_status"] = "sandbox_series"
    return out


def add_avail_rate_time_lags(panel: pd.DataFrame) -> pd.DataFrame:
    """Attach avail_rate_lag_15m / avail_rate_lag_60m.

    Definition (aligned with docs/data/스키마):
      value of availability_ratio_observed at the latest tick T' where
      - same statId and segment_id
      - T' <= panel_ts - lag_minutes
      - T' >= panel_ts - lag_minutes - tolerance_minutes
    If none → null (do not cross gap-safe segment boundaries).
    """
    out = panel.copy()
    out["panel_ts"] = pd.to_datetime(out["panel_ts"])
    for col in ("avail_rate_lag_15m", "avail_rate_lag_60m"):
        if col in out.columns:
            out = out.drop(columns=[col])

    specs = (
        ("avail_rate_lag_15m", 15, 12),
        ("avail_rate_lag_60m", 60, 15),
    )
    base = out[
        ["statId", "segment_id", "panel_ts", "availability_ratio_observed"]
    ].sort_values(["statId", "segment_id", "panel_ts"])

    for col, lag_min, tol_min in specs:
        left = base[["statId", "segment_id", "panel_ts"]].copy()
        left["asof_ts"] = left["panel_ts"] - pd.Timedelta(minutes=lag_min)
        right = base.rename(
            columns={
                "panel_ts": "lag_ts",
                "availability_ratio_observed": col,
            }
        )[["statId", "segment_id", "lag_ts", col]]
        left = left.sort_values("asof_ts")
        right = right.sort_values("lag_ts")
        hit = pd.merge_asof(
            left,
            right,
            left_on="asof_ts",
            right_on="lag_ts",
            by=["statId", "segment_id"],
            direction="backward",
            tolerance=pd.Timedelta(minutes=tol_min),
        )
        out = out.merge(
            hit[["statId", "segment_id", "panel_ts", col]],
            on=["statId", "segment_id", "panel_ts"],
            how="left",
        )
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
    # Parquet is the daily contract. Full CSV is optional — writing ~GB CSVs
    # twice routinely stalls evening rebuilds (RAM/disk).
    write_csv = os.environ.get("D2_WRITE_CSV", "").strip() in {"1", "true", "TRUE", "yes"}
    panel.to_parquet(pq_path, index=False)
    if write_csv:
        panel.to_csv(csv_path, index=False, encoding="utf-8-sig")
    # keep stable latest pointers for EDA / KPI consumers
    latest_csv = OUT_DIR / "station_feature_panel_latest.csv"
    latest_pq = OUT_DIR / "station_feature_panel_latest.parquet"
    panel.to_parquet(latest_pq, index=False)
    if write_csv:
        panel.to_csv(latest_csv, index=False, encoding="utf-8-sig")

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
            "full_csv": str(csv_path.relative_to(REPO)).replace("\\", "/") if write_csv else None,
            "full_parquet": str(pq_path.relative_to(REPO)).replace("\\", "/"),
            "latest_csv": str(latest_csv.relative_to(REPO)).replace("\\", "/") if write_csv else None,
            "latest_parquet": str(latest_pq.relative_to(REPO)).replace("\\", "/"),
            "sample_csv": str(sample_path.relative_to(REPO)).replace("\\", "/"),
        },
        "spec": "docs/data/스키마/데이터셋_명세.md",
        "owner": "AI·data ①",
        "consumer": "AI·data ②",
        "write_csv": write_csv,
        "note": "availability among usable known (stat 2/3); other codes counted in known_chargers but not in usable_known denominator; set D2_WRITE_CSV=1 for full CSV",
    }
    (HANDOFF / "HANDOFF_META_D2.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    print(json.dumps(meta, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
