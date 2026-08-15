"""Build station-level t0 → t0+ETA availability replay data.

The replay uses the conservative 25-minute reconstructed station panel.
It evaluates fixed arrival horizons because historical per-request TMAP routes
do not exist. TMAP remains the production ETA source.

Outputs:
  docs/data/analysis/arrival_availability_replay_YYYYMMDD/
    arrival_availability_replay.csv
    arrival_availability_replay.parquet (when parquet support is available)
    arrival_availability_replay_sample.csv
    arrival_availability_summary.json

Usage from repository root:
  python apps/data-pipeline/processing/analysis/build_arrival_availability_replay.py
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_PROCESSING = Path(__file__).resolve().parents[1]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))

from _bootstrap import ensure_paths

REPO = ensure_paths()
DEFAULT_PANEL = (
    REPO
    / "apps"
    / "data-pipeline"
    / "reports"
    / "timeseries_feasibility"
    / "tables"
    / "station_tick_panel.parquet"
)
DEFAULT_D1 = (
    REPO
    / "apps"
    / "data-pipeline"
    / "evaluation"
    / "results"
    / "datasets"
    / "station_feature_snapshot_latest.csv"
)
DEFAULT_HORIZONS = (5, 10, 15, 30)
TARGET_TOLERANCE_MINUTES = 7.5
SEGMENT_GAP_MINUTES = 25
FALLBACK_NEIGHBORS = 5


def truth(series: pd.Series) -> pd.Series:
    return series.astype(str).str.lower().isin({"true", "1", "yes"})


def future_tick_map(
    times: pd.DatetimeIndex,
    horizon_minutes: int,
    *,
    tolerance_minutes: float = TARGET_TOLERANCE_MINUTES,
    segment_gap_minutes: float = SEGMENT_GAP_MINUTES,
) -> np.ndarray:
    """Map each tick to the first tick at/after t+h within tolerance and segment."""
    if len(times) == 0:
        return np.array([], dtype=int)
    # Normalize explicitly because pandas may preserve microsecond resolution.
    values = times.astype("datetime64[ns]").view("int64")
    target_values = values + pd.Timedelta(minutes=horizon_minutes).value
    candidates = np.searchsorted(values, target_values, side="left")
    mapping = np.full(len(times), -1, dtype=int)

    segment = (
        times.to_series()
        .diff()
        .gt(pd.Timedelta(minutes=segment_gap_minutes))
        .cumsum()
        .to_numpy()
    )
    tolerance_ns = pd.Timedelta(minutes=tolerance_minutes).value
    for index, candidate in enumerate(candidates):
        if candidate >= len(times) or candidate <= index:
            continue
        if segment[candidate] != segment[index]:
            continue
        if abs(values[candidate] - target_values[index]) > tolerance_ns:
            continue
        mapping[index] = int(candidate)
    return mapping


def nearest_neighbor_indices(
    latitudes: np.ndarray,
    longitudes: np.ndarray,
    *,
    k: int = FALLBACK_NEIGHBORS,
) -> np.ndarray:
    """Return nearest station indices by haversine distance, excluding self."""
    n = len(latitudes)
    if n <= 1:
        return np.empty((n, 0), dtype=int)
    k = min(k, n - 1)
    lat = np.radians(latitudes.astype(float))
    lng = np.radians(longitudes.astype(float))
    dlat = lat[:, None] - lat[None, :]
    dlng = lng[:, None] - lng[None, :]
    a = (
        np.sin(dlat / 2) ** 2
        + np.cos(lat[:, None]) * np.cos(lat[None, :]) * np.sin(dlng / 2) ** 2
    )
    distance = 2 * 6_371_000 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))
    np.fill_diagonal(distance, np.inf)
    partition = np.argpartition(distance, kth=k - 1, axis=1)[:, :k]
    row = np.arange(n)[:, None]
    order = np.argsort(distance[row, partition], axis=1)
    return partition[row, order]


def _read_panel(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path)
    return pd.read_csv(path, low_memory=False)


def _build_matrices(
    panel: pd.DataFrame,
    d1: pd.DataFrame,
) -> tuple[pd.DatetimeIndex, np.ndarray, np.ndarray, pd.DataFrame]:
    panel = panel.copy()
    panel["panel_time"] = pd.to_datetime(panel["panel_time"])
    required_panel = {
        "station_id",
        "panel_time",
        "known_recon",
        "available_recon",
    }
    missing = required_panel - set(panel.columns)
    if missing:
        raise ValueError(f"panel missing columns: {sorted(missing)}")

    d1 = d1.copy()
    d1["statId"] = d1["statId"].astype(str)
    d1["lat"] = pd.to_numeric(d1["lat"], errors="coerce")
    d1["lng"] = pd.to_numeric(d1["lng"], errors="coerce")
    eligible = (
        truth(d1["recommend_public_default"])
        & truth(d1["coord_ok"])
        & d1["lat"].notna()
        & d1["lng"].notna()
        & d1["is_operating_now"].fillna("UNKNOWN").ne("N")
    )
    meta = (
        d1.loc[
            eligible,
            [
                "statId",
                "statNm",
                "lat",
                "lng",
                "total_chargers",
                "recommend_public_default",
                "coord_ok",
            ],
        ]
        .drop_duplicates(subset=["statId"])
        .rename(columns={"statId": "station_id"})
    )
    present = set(panel["station_id"].astype(str).unique())
    meta = meta[meta["station_id"].isin(present)].sort_values("station_id")
    station_ids = meta["station_id"].tolist()
    panel = panel[panel["station_id"].isin(station_ids)].copy()

    known = (
        panel.pivot(index="panel_time", columns="station_id", values="known_recon")
        .reindex(columns=station_ids)
        .sort_index()
        .fillna(0)
    )
    available = (
        panel.pivot(
            index="panel_time",
            columns="station_id",
            values="available_recon",
        )
        .reindex(index=known.index, columns=station_ids)
        .fillna(0)
    )
    return (
        pd.DatetimeIndex(known.index),
        known.to_numpy(dtype=np.int16),
        available.to_numpy(dtype=np.int16),
        meta.reset_index(drop=True),
    )


def _horizon_frame(
    *,
    times: pd.DatetimeIndex,
    known: np.ndarray,
    available: np.ndarray,
    meta: pd.DataFrame,
    neighbors: np.ndarray,
    horizon: int,
) -> tuple[pd.DataFrame, dict[str, object]]:
    target_index = future_tick_map(times, horizon)
    mapped_ticks = np.where(target_index >= 0)[0]
    if not len(mapped_ticks):
        return pd.DataFrame(), {
            "horizon_minutes": horizon,
            "labeled_rows": 0,
            "reason": "no future tick mapping",
        }

    current_known = known[mapped_ticks]
    current_available = available[mapped_ticks]
    future_known = known[target_index[mapped_ticks]]
    future_available = available[target_index[mapped_ticks]]

    candidate = (current_known > 0) & (current_available > 0)
    labelable = candidate & (future_known > 0)

    fallback_count = np.zeros_like(current_available, dtype=np.int16)
    if neighbors.shape[1]:
        for row_index in range(len(mapped_ticks)):
            survives = (
                (current_known[row_index] > 0)
                & (current_available[row_index] > 0)
                & (future_known[row_index] > 0)
                & (future_available[row_index] > 0)
            )
            fallback_count[row_index] = survives[neighbors].sum(axis=1)

    row_idx, station_idx = np.where(labelable)
    if not len(row_idx):
        return pd.DataFrame(), {
            "horizon_minutes": horizon,
            "labeled_rows": 0,
            "reason": "no labelable candidate rows",
        }

    source_tick_idx = mapped_ticks[row_idx]
    future_tick_idx = target_index[source_tick_idx]
    current_count = current_available[row_idx, station_idx]
    arrival_count = future_available[row_idx, station_idx]
    fallback_counts = fallback_count[row_idx, station_idx]
    arrival_available = arrival_count > 0
    became_unavailable = ~arrival_available
    count_changed = current_count != arrival_count
    fallback_covered = became_unavailable & (fallback_counts > 0)

    frame = pd.DataFrame(
        {
            "station_id": meta.iloc[station_idx]["station_id"].to_numpy(),
            "station_name": meta.iloc[station_idx]["statNm"].to_numpy(),
            "t0": times[source_tick_idx],
            "target_time": times[source_tick_idx]
            + pd.to_timedelta(horizon, unit="m"),
            "matched_arrival_time": times[future_tick_idx],
            "horizon_minutes": horizon,
            "match_delta_minutes": (
                (
                    times[future_tick_idx]
                    - (
                        times[source_tick_idx]
                        + pd.to_timedelta(horizon, unit="m")
                    )
                ).total_seconds()
                / 60
            ),
            "current_known_chargers": current_known[row_idx, station_idx],
            "current_available_count": current_count,
            "arrival_known_chargers": future_known[row_idx, station_idx],
            "arrival_available_count": arrival_count,
            "arrival_available": arrival_available,
            "became_unavailable": became_unavailable,
            "available_count_changed": count_changed,
            "fallback_candidate_count_nearest5": fallback_counts,
            "fallback_covered_if_failed": fallback_covered,
            "label_source": "25m_hold_reconstructed_status",
            "eta_source": "fixed_horizon_replay_not_tmap",
        }
    )

    failed = frame["became_unavailable"]
    multi = frame["current_available_count"] >= 2
    one = frame["current_available_count"] == 1
    stats = {
        "horizon_minutes": horizon,
        "mapped_ticks": int(len(mapped_ticks)),
        "labeled_rows": int(len(frame)),
        "stations": int(frame["station_id"].nunique()),
        "arrival_available_rate": float(frame["arrival_available"].mean()),
        "became_unavailable_rate": float(frame["became_unavailable"].mean()),
        "recommendation_change_rate": float(
            frame["available_count_changed"].mean()
        ),
        "failed_rows": int(failed.sum()),
        "fallback_candidate_coverage": (
            float(frame.loc[failed, "fallback_covered_if_failed"].mean())
            if failed.any()
            else None
        ),
        "single_available_arrival_rate": (
            float(frame.loc[one, "arrival_available"].mean()) if one.any() else None
        ),
        "multi_available_arrival_rate": (
            float(frame.loc[multi, "arrival_available"].mean())
            if multi.any()
            else None
        ),
    }
    return frame, stats


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--panel", type=Path, default=DEFAULT_PANEL)
    parser.add_argument("--d1", type=Path, default=DEFAULT_D1)
    parser.add_argument(
        "--horizons",
        type=int,
        nargs="+",
        default=list(DEFAULT_HORIZONS),
    )
    parser.add_argument("--sample-rows", type=int, default=50_000)
    args = parser.parse_args()

    panel_path = args.panel if args.panel.is_absolute() else REPO / args.panel
    d1_path = args.d1 if args.d1.is_absolute() else REPO / args.d1
    if not panel_path.exists():
        raise FileNotFoundError(f"missing panel: {panel_path}")
    if not d1_path.exists():
        raise FileNotFoundError(f"missing D1: {d1_path}")

    panel = _read_panel(panel_path)
    d1 = pd.read_csv(d1_path, low_memory=False)
    times, known, available, meta = _build_matrices(panel, d1)
    neighbors = nearest_neighbor_indices(
        meta["lat"].to_numpy(),
        meta["lng"].to_numpy(),
    )

    frames: list[pd.DataFrame] = []
    horizon_stats: dict[str, object] = {}
    for horizon in args.horizons:
        frame, stats = _horizon_frame(
            times=times,
            known=known,
            available=available,
            meta=meta,
            neighbors=neighbors,
            horizon=horizon,
        )
        horizon_stats[str(horizon)] = stats
        if not frame.empty:
            frames.append(frame)

    replay = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    latest_day = times[-1].strftime("%Y%m%d") if len(times) else "unknown"
    out = (
        REPO
        / "docs"
        / "data"
        / "analysis"
        / f"arrival_availability_replay_{latest_day}"
    )
    out.mkdir(parents=True, exist_ok=True)

    csv_path = out / "arrival_availability_replay.csv"
    replay.to_csv(csv_path, index=False, encoding="utf-8-sig")
    parquet_path = out / "arrival_availability_replay.parquet"
    try:
        replay.to_parquet(parquet_path, index=False)
        canonical_path = parquet_path
    except Exception:
        canonical_path = csv_path

    sample = (
        replay.sample(
            n=min(args.sample_rows, len(replay)),
            random_state=42,
        )
        .sort_values(["t0", "horizon_minutes", "station_id"])
        if len(replay)
        else replay
    )
    sample.to_csv(
        out / "arrival_availability_replay_sample.csv",
        index=False,
        encoding="utf-8-sig",
    )

    overall_failed = replay["became_unavailable"] if len(replay) else pd.Series(dtype=bool)
    summary = {
        "generated_from_latest_tick": (
            times[-1].isoformat() if len(times) else None
        ),
        "source_panel": str(panel_path.relative_to(REPO)).replace("\\", "/"),
        "source_d1": str(d1_path.relative_to(REPO)).replace("\\", "/"),
        "grain": "station × t0 × fixed arrival horizon",
        "eligible_public_coordinate_stations": int(len(meta)),
        "replay_rows": int(len(replay)),
        "horizons": horizon_stats,
        "overall": {
            "arrival_available_rate": (
                float(replay["arrival_available"].mean()) if len(replay) else None
            ),
            "recommendation_change_rate": (
                float(replay["available_count_changed"].mean())
                if len(replay)
                else None
            ),
            "failed_rows": int(overall_failed.sum()) if len(replay) else 0,
            "fallback_candidate_coverage": (
                float(
                    replay.loc[
                        overall_failed,
                        "fallback_covered_if_failed",
                    ].mean()
                )
                if len(replay) and overall_failed.any()
                else None
            ),
        },
        "quality_rules": {
            "raw_page_duplicates": "latest statUpdDt wins",
            "state_hold_minutes": 25,
            "target_tick_tolerance_minutes": TARGET_TOLERANCE_MINUTES,
            "fallback_definition": (
                "among the five stations nearest to the primary station, "
                "candidate was available at t0 and remains available at arrival"
            ),
        },
        "limitations": [
            "Fixed horizons are used because historical request-level TMAP ETA is unavailable.",
            "Fallback proximity is straight-line station-to-station distance, not route time.",
            "State is reconstructed only within a continuous segment and 25-minute hold.",
            "Availability means API status=2, not a reservation or charging guarantee.",
        ],
        "files": {
            "canonical": str(canonical_path.relative_to(out)).replace("\\", "/"),
            "csv": csv_path.name,
            "sample": "arrival_availability_replay_sample.csv",
        },
    }
    (out / "arrival_availability_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"OUT {out.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
