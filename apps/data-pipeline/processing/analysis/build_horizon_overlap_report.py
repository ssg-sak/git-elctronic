"""Build pairwise overlap and label-similarity report across horizons."""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from itertools import combinations
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

import pandas as pd

_PROCESSING = Path(__file__).resolve().parents[1]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))

from _bootstrap import ensure_paths

REPO = ensure_paths()
KST = ZoneInfo("Asia/Seoul")
DEFAULT_INPUT = REPO / "apps" / "data-pipeline" / "evaluation" / "results" / "datasets" / "station_horizon_training_v1.parquet"
DEFAULT_OUT = REPO / "docs" / "data" / "quality"
HORIZONS = (5, 10, 15, 30)
KEYS = ["station_id", "feature_as_of"]


def build_report(path: Path) -> tuple[pd.DataFrame, dict]:
    data = pd.read_parquet(path)
    data = data[data["horizon_minutes"].isin(HORIZONS)].copy()
    duplicate_grain = int(data.duplicated(KEYS + ["horizon_minutes"]).sum())
    per_horizon = []
    by_horizon = {int(h): data[data["horizon_minutes"] == h].copy() for h in HORIZONS}
    for horizon, frame in by_horizon.items():
        unique_keys = frame[KEYS].drop_duplicates()
        per_horizon.append(
            {
                "horizon_minutes": horizon,
                "rows": int(len(frame)),
                "unique_station_asof": int(len(unique_keys)),
                "duplicate_grain_rows": int(frame.duplicated(KEYS).sum()),
                "positive_rate": round(float(frame["target_available"].mean()), 6),
            }
        )

    pairwise = []
    for left, right in combinations(HORIZONS, 2):
        lhs = by_horizon[left].set_index(KEYS)[["target_available", "target_time"]].rename(
            columns={"target_available": "target_left", "target_time": "target_time_left"}
        )
        rhs = by_horizon[right].set_index(KEYS)[["target_available", "target_time"]].rename(
            columns={"target_available": "target_right", "target_time": "target_time_right"}
        )
        joined = lhs.join(rhs, how="inner")
        same = joined["target_left"] == joined["target_right"]
        denominator = min(len(lhs), len(rhs))
        pairwise.append(
            {
                "left_horizon_minutes": left,
                "right_horizon_minutes": right,
                "left_rows": int(len(lhs)),
                "right_rows": int(len(rhs)),
                "overlap_rows": int(len(joined)),
                "overlap_rate_vs_smaller_horizon": round(float(len(joined) / denominator), 6) if denominator else None,
                "same_label_rows": int(same.sum()),
                "same_label_rate_within_overlap": round(float(same.mean()), 6) if len(joined) else None,
                "different_label_rows": int((~same).sum()),
                "same_target_time_rows": int((joined["target_time_left"] == joined["target_time_right"]).sum()),
            }
        )
    table = pd.DataFrame(pairwise)
    summary = {
        "input": str(path.relative_to(REPO)).replace("\\", "/"),
        "horizons": list(HORIZONS),
        "rows": int(len(data)),
        "duplicate_grain_rows": duplicate_grain,
        "grain": "station_id × feature_as_of × horizon_minutes",
        "interpretation": "overlap is measured on station_id × feature_as_of; same-label rate measures how redundant two horizons are within their overlap.",
        "per_horizon": per_horizon,
        "pairwise": pairwise,
    }
    return table, summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    input_path = args.input if args.input.is_absolute() else REPO / args.input
    out = args.output_dir if args.output_dir.is_absolute() else REPO / args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    table, summary = build_report(input_path)
    stamp = datetime.now(KST).strftime("%Y%m%d")
    csv_path = out / f"horizon_overlap_{stamp}.csv"
    json_path = out / f"horizon_overlap_{stamp}_summary.json"
    table.to_csv(csv_path, index=False, encoding="utf-8-sig")
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(table.to_string(index=False))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"OUT {csv_path.relative_to(REPO)}")
    print(f"OUT {json_path.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
