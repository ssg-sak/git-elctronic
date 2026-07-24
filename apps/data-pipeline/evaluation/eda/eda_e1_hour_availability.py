"""E1: hour-of-day availability from D2 panel (analyzable hours only).

Does not compute recommendation scores (AI·data ②).
Plan: docs/보고/EDA_계획_상태패널.md
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[4]
EVAL = Path(__file__).resolve().parents[1]
DATASETS = EVAL / "results" / "datasets"
OUT = EVAL / "results" / "eda"
KST = ZoneInfo("Asia/Seoul")

# Minimum support to call an hour "analyzable"
MIN_TIMESTAMPS = 2
MIN_PANEL_ROWS = 5000


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    panel_path = DATASETS / "station_feature_panel_latest.parquet"
    if not panel_path.exists():
        panel_path = DATASETS / "station_feature_panel_latest.csv"
    df = pd.read_parquet(panel_path) if panel_path.suffix == ".parquet" else pd.read_csv(panel_path)
    df["panel_ts"] = pd.to_datetime(df["panel_ts"])
    df["hour"] = df["panel_ts"].dt.hour
    df["avail"] = pd.to_numeric(df["availability_ratio_observed"], errors="coerce")
    df["confirmed"] = df["has_confirmed_available"].astype(str).str.lower().isin(["true", "1"])
    usable = pd.to_numeric(df["usable_known"], errors="coerce")
    in_use = pd.to_numeric(df["in_use_count"], errors="coerce")
    df["in_use_rate"] = in_use / usable.replace(0, pd.NA)

    rows = []
    for hour, part in df.groupby("hour", sort=True):
        a = part["avail"].dropna()
        n_ts = int(part["panel_ts"].nunique())
        n_rows = len(part)
        analyzable = n_ts >= MIN_TIMESTAMPS and n_rows >= MIN_PANEL_ROWS
        rows.append(
            {
                "hour": int(hour),
                "analyzable": analyzable,
                "panel_rows": n_rows,
                "n_timestamps": n_ts,
                "n_stations": int(part["statId"].nunique()),
                "avail_mean": round(float(a.mean()), 4) if len(a) else None,
                "avail_median": round(float(a.median()), 4) if len(a) else None,
                "confirmed_rate": round(float(part["confirmed"].mean()), 4),
                "in_use_rate_mean": round(float(part["in_use_rate"].mean()), 4)
                if part["in_use_rate"].notna().any()
                else None,
                "exclude_reason": ""
                if analyzable
                else f"thin: timestamps<{MIN_TIMESTAMPS} or rows<{MIN_PANEL_ROWS}",
            }
        )
    out = pd.DataFrame(rows)
    csv_path = OUT / "e1_availability_by_hour.csv"
    out.to_csv(csv_path, index=False, encoding="utf-8-sig")

    ok = out[out["analyzable"]].copy()
    meta = {
        "analysis": "E1_hour_availability",
        "generated_at": datetime.now(KST).isoformat(),
        "source": str(panel_path.resolve().relative_to(REPO_ROOT)).replace("\\", "/"),
        "panel_ts_min": str(df["panel_ts"].min()),
        "panel_ts_max": str(df["panel_ts"].max()),
        "segments": int(df["segment_id"].nunique()) if "segment_id" in df.columns else None,
        "hours_present": sorted(df["hour"].unique().tolist()),
        "hours_analyzable": ok["hour"].tolist(),
        "hours_excluded": out.loc[~out["analyzable"], "hour"].tolist(),
        "filter": {"min_timestamps": MIN_TIMESTAMPS, "min_panel_rows": MIN_PANEL_ROWS},
        "peak_avail_hour": int(ok.loc[ok["avail_mean"].idxmax(), "hour"]) if len(ok) else None,
        "trough_avail_hour": int(ok.loc[ok["avail_mean"].idxmin(), "hour"]) if len(ok) else None,
        "avail_mean_morning_8_11": round(float(ok.loc[ok["hour"].between(8, 11), "avail_mean"].mean()), 4)
        if ok["hour"].between(8, 11).any()
        else None,
        "avail_mean_evening_18_21": round(
            float(ok.loc[ok["hour"].between(18, 21), "avail_mean"].mean()), 4
        )
        if ok["hour"].between(18, 21).any()
        else None,
        "csv": str(csv_path.resolve().relative_to(REPO_ROOT)).replace("\\", "/"),
        "note": "Mean availability among usable known (stat 2/3). Night hours 0–6,23 absent in collection window.",
    }
    (OUT / "e1_availability_by_hour_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    print(ok.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
