"""E3: availability / unobserved by station charger-count bucket.

Uses D1 (master total_chargers) + optional D2 station mean availability.
Does not score stations (AI·data ②).
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


def bucket_chargers(n: int) -> str:
    if n <= 1:
        return "1"
    if n <= 3:
        return "2-3"
    if n <= 6:
        return "4-6"
    return "7+"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    d1_path = DATASETS / "station_feature_snapshot_latest.csv"
    d1 = pd.read_csv(d1_path)
    d1["total_chargers"] = pd.to_numeric(d1["total_chargers"], errors="coerce").fillna(0).astype(int)
    d1["bucket"] = d1["total_chargers"].map(bucket_chargers)
    d1["avail"] = pd.to_numeric(d1["availability_ratio_observed"], errors="coerce")
    d1["unobs"] = pd.to_numeric(d1["unobserved_rate"], errors="coerce")
    d1["confirmed"] = d1["has_confirmed_available"].astype(str).str.lower().isin(["true", "1"])

    # D2 station-level mean avail (time average)
    d2_path = DATASETS / "station_feature_panel_latest.parquet"
    d2_station = None
    if d2_path.exists():
        d2 = pd.read_parquet(d2_path, columns=["statId", "availability_ratio_observed"])
        d2["avail"] = pd.to_numeric(d2["availability_ratio_observed"], errors="coerce")
        d2_station = (
            d2.groupby("statId", as_index=False)["avail"]
            .mean()
            .rename(columns={"avail": "d2_avail_mean"})
        )
        d1 = d1.merge(d2_station, on="statId", how="left")

    order = ["1", "2-3", "4-6", "7+"]
    rows = []
    for b in order:
        part = d1[d1["bucket"] == b]
        a = part["avail"].dropna()
        rows.append(
            {
                "bucket": b,
                "stations": len(part),
                "total_chargers_mean": round(float(part["total_chargers"].mean()), 2),
                "unobserved_rate_mean": round(float(part["unobs"].mean()), 4),
                "confirmed_rate": round(float(part["confirmed"].mean()), 4),
                "d1_avail_mean_observed": round(float(a.mean()), 4) if len(a) else None,
                "d1_avail_n": int(len(a)),
                "d2_avail_mean": round(float(part["d2_avail_mean"].mean()), 4)
                if "d2_avail_mean" in part.columns and part["d2_avail_mean"].notna().any()
                else None,
                "d2_stations_with_panel": int(part["d2_avail_mean"].notna().sum())
                if "d2_avail_mean" in part.columns
                else 0,
            }
        )
    out = pd.DataFrame(rows)
    csv_path = OUT / "e3_availability_by_charger_count.csv"
    out.to_csv(csv_path, index=False, encoding="utf-8-sig")

    meta = {
        "analysis": "E3_charger_count_x_availability",
        "generated_at": datetime.now(KST).isoformat(),
        "d1_source": str(d1_path.resolve().relative_to(REPO_ROOT)).replace("\\", "/"),
        "d2_source": str(d2_path.resolve().relative_to(REPO_ROOT)).replace("\\", "/")
        if d2_path.exists()
        else None,
        "buckets": "1 / 2-3 / 4-6 / 7+ (master total_chargers)",
        "stations_total": int(len(d1)),
        "csv": str(csv_path.resolve().relative_to(REPO_ROOT)).replace("\\", "/"),
        "note": (
            "d1_avail_mean_observed ignores stations with no observed chargers (null F01). "
            "unobserved_rate uses full master denominator."
        ),
    }
    (OUT / "e3_availability_by_charger_count_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    print(out.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
