"""Team5 parking realtime → short-horizon volatility features for D1 (additive).

Uses latest `daegu_parking_realtime_history_team5_*.csv` + `join_parking_team5_1000m.csv`.
Outputs station-level:
  - parking_remaining_std_1h
  - parking_remaining_delta_1h  (last - first in window)
  - parking_realtime_ticks_1h

Not a usual congestion profile — short-window auxiliary only.
Does not overwrite live parking join CSVs.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

_PROCESSING = Path(__file__).resolve().parents[1]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))
from _bootstrap import ensure_paths

REPO = ensure_paths()
from loop_paths import EXTRACTED_PARKING  # noqa: E402

JOIN = REPO / "docs/data/spatial_join/join_parking_team5_1000m.csv"
OUT_CSV = REPO / "docs/data/spatial_join/parking_realtime_1h_features.csv"
OUT_META = REPO / "docs/data/spatial_join/parking_realtime_1h_features_meta.json"
WINDOW = pd.Timedelta(hours=1)


def _latest_history() -> Path:
    files = sorted(EXTRACTED_PARKING.glob("daegu_parking_realtime_history_team5_*.csv"))
    if not files:
        raise FileNotFoundError(f"No history CSV under {EXTRACTED_PARKING}")
    return files[-1]


def main() -> int:
    hist_path = _latest_history()
    hist = pd.read_csv(hist_path, low_memory=False)
    id_col = "pkltId" if "pkltId" in hist.columns else "pklt_id"
    ts_col = "fetchedAt" if "fetchedAt" in hist.columns else "collected_at"
    hist["pklt_id"] = hist[id_col].astype(str)
    hist["ts"] = pd.to_datetime(hist[ts_col], errors="coerce")
    hist["remaining_spaces"] = pd.to_numeric(hist["remaining_spaces"], errors="coerce")
    hist = hist.dropna(subset=["pklt_id", "ts", "remaining_spaces"]).copy()

    as_of = hist["ts"].max()
    window_start = as_of - WINDOW
    recent = hist[hist["ts"] >= window_start].copy()

    g = recent.groupby("pklt_id", sort=False)["remaining_spaces"]
    lot = pd.DataFrame(
        {
            "pklt_id": g.mean().index.astype(str),
            "parking_remaining_std_1h": g.std(ddof=0).values,
            "parking_remaining_delta_1h": (
                g.last().values - g.first().values
            ),
            "parking_realtime_ticks_1h": g.size().values.astype(int),
        }
    )

    join = pd.read_csv(JOIN, dtype=str, low_memory=False)
    join["matched"] = join.get("matched", "False").astype(str).str.lower().isin(
        ["true", "1"]
    )
    join = join[join["matched"] & join["matched_id"].notna() & (join["matched_id"] != "")]
    join = join[["statId", "matched_id"]].drop_duplicates("statId")
    join["matched_id"] = join["matched_id"].astype(str)

    out = join.merge(lot, left_on="matched_id", right_on="pklt_id", how="left")
    out = out.drop(columns=["pklt_id"], errors="ignore")
    out = out.rename(columns={"matched_id": "parking_matched_id"})

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")

    with_feat = int(out["parking_remaining_std_1h"].notna().sum())
    meta = {
        "as_of_kst": str(as_of),
        "window_hours": 1,
        "history_file": str(hist_path.relative_to(REPO)).replace("\\", "/"),
        "history_rows": int(len(hist)),
        "window_rows": int(len(recent)),
        "lots_in_window": int(lot.shape[0]),
        "stations_joined": int(len(out)),
        "stations_with_1h_features": with_feat,
        "note": "short-horizon auxiliary only; not usual congestion profile",
        "output": str(OUT_CSV.relative_to(REPO)).replace("\\", "/"),
    }
    OUT_META.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
