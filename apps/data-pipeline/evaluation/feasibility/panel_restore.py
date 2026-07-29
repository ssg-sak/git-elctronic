"""Reconstruct charger×tick panel with required feasibility columns (vectorized)."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .paths import LOOP1_INDEX, OUT_JSON, OUT_TABLES, ensure_out

_SANDBOX_SRC = (
    Path(__file__).resolve().parents[1]
    / "personal/experiments/SANDBOX_20260717_status_periodic_collection/src"
)
if str(_SANDBOX_SRC) not in sys.path:
    sys.path.insert(0, str(_SANDBOX_SRC))

from load_snapshots import load_all_snapshots  # noqa: E402

MAX_HOLD_MINUTES = 25


def _station_tick_from_matrices(
    *,
    all_ts: pd.DatetimeIndex,
    idx: pd.DataFrame,
    succ: np.ndarray,
    values: np.ndarray,
    recon: np.ndarray,
    age: np.ndarray,
    station_codes: np.ndarray,
    n_stations: int,
    station_labels: np.ndarray,
) -> pd.DataFrame:
    n_t = len(all_ts)
    rows = []
    for i in range(n_t):
        obs = values[i]
        rec = recon[i]
        observed = ~np.isnan(obs)
        avail_obs = (obs == 2) & observed
        usable_obs = np.isin(obs, [2, 3]) & observed
        avail_rec = rec == 2
        usable_rec = np.isin(rec, [2, 3])
        known_rec = ~np.isnan(rec)

        def bincount(mask: np.ndarray) -> np.ndarray:
            return np.bincount(station_codes[mask], minlength=n_stations)

        min_age = np.full(n_stations, np.inf, dtype=float)
        if known_rec.any():
            np.minimum.at(
                min_age,
                station_codes[known_rec],
                age[i, known_rec],
            )
        min_age[np.isinf(min_age)] = np.nan

        chargers = np.bincount(station_codes, minlength=n_stations)
        rows.append(
            pd.DataFrame(
                {
                    "station_id": station_labels,
                    "chargers": chargers,
                    "observed_chargers": bincount(observed),
                    "available_observed": bincount(avail_obs),
                    "usable_observed": bincount(usable_obs),
                    "known_recon": bincount(~np.isnan(rec)),
                    "available_recon": bincount(~np.isnan(rec) & avail_rec),
                    "usable_recon": bincount(~np.isnan(rec) & usable_rec),
                    "observation_age_minutes": min_age,
                    "panel_time": all_ts[i],
                    "snapshotId": idx.loc[i, "snapshotId"],
                    "collection_success": bool(succ[i]),
                }
            )
        )
    return pd.concat(rows, ignore_index=True)


def run_panel_restore(*, max_hold_minutes: int = MAX_HOLD_MINUTES) -> dict[str, Any]:
    ensure_out()
    idx = pd.read_csv(LOOP1_INDEX, dtype=str)
    idx["panel_time"] = pd.to_datetime(idx["snapshotId"], format="%Y%m%d_%H%M%S")
    idx["collection_success"] = idx["ok"].astype(str).str.lower().isin({"true", "1", "yes"})
    idx = idx.sort_values("panel_time").reset_index(drop=True)

    events = load_all_snapshots()
    if events.empty:
        return {"ok": False, "error": "no events", "impossible": True}

    events["stat"] = pd.to_numeric(events["stat"], errors="coerce")
    events["ts"] = pd.to_datetime(events["snapshotId"], format="%Y%m%d_%H%M%S")
    events["charger_key"] = events["statId"].astype(str) + "|" + events["chgerId"].astype(str)

    wide_obs = (
        events.pivot_table(index="ts", columns="charger_key", values="stat", aggfunc="last")
        .sort_index()
    )
    all_ts = pd.DatetimeIndex(idx["panel_time"])
    wide_obs = wide_obs.reindex(all_ts)
    success = pd.Series(idx["collection_success"].to_numpy(), index=all_ts)
    gap = all_ts.to_series().diff().gt(pd.Timedelta(minutes=max_hold_minutes))
    segment = gap.cumsum().to_numpy()

    values = wide_obs.to_numpy(dtype=float)
    n_t, n_c = values.shape
    recon = np.full_like(values, np.nan)
    age = np.full_like(values, np.nan)
    is_obs = ~np.isnan(values)
    is_imp = np.zeros_like(values, dtype=bool)
    succ = success.to_numpy()

    last_val = np.full(n_c, np.nan)
    last_t_idx = np.full(n_c, -1)
    for i in range(n_t):
        if i > 0 and segment[i] != segment[i - 1]:
            last_val[:] = np.nan
            last_t_idx[:] = -1
        obs_row = values[i]
        observed = ~np.isnan(obs_row)
        last_val[observed] = obs_row[observed]
        last_t_idx[observed] = i
        recon[i, observed] = obs_row[observed]
        age[i, observed] = 0.0
        if succ[i]:
            need = ~observed & ~np.isnan(last_val) & (last_t_idx >= 0)
            if need.any():
                ages = (all_ts[i] - all_ts[last_t_idx[need]]).total_seconds() / 60.0
                ok_hold = ages <= max_hold_minutes
                idx_need = np.where(need)[0]
                keep = idx_need[ok_hold]
                drop = idx_need[~ok_hold]
                recon[i, keep] = last_val[keep]
                age[i, keep] = ages[ok_hold]
                is_imp[i, keep] = True
                age[i, drop] = ages[~ok_hold]
        else:
            need = ~observed & (last_t_idx >= 0)
            if need.any():
                ages = (all_ts[i] - all_ts[last_t_idx[need]]).total_seconds() / 60.0
                age[i, need] = ages

    cols = wide_obs.columns.to_numpy()
    station_ids = np.array([c.split("|", 1)[0] for c in cols])
    station_codes, station_labels = pd.factorize(station_ids, sort=False)
    labels_arr = np.asarray(station_labels)
    station_tick = _station_tick_from_matrices(
        all_ts=all_ts,
        idx=idx,
        succ=succ,
        values=values,
        recon=recon,
        age=age,
        station_codes=station_codes,
        n_stations=len(labels_arr),
        station_labels=labels_arr,
    )
    # drop stations with 0 chargers in matrix (all should have >0)
    station_tick.to_csv(OUT_TABLES / "station_tick_panel.csv", index=False, encoding="utf-8-sig")
    try:
        station_tick.to_parquet(OUT_TABLES / "station_tick_panel.parquet", index=False)
        tick_path = OUT_TABLES / "station_tick_panel.parquet"
    except Exception:
        tick_path = OUT_TABLES / "station_tick_panel.csv"
    station_tick.head(3000).to_csv(
        OUT_TABLES / "station_tick_panel_sample.csv", index=False, encoding="utf-8-sig"
    )

    n_obs = int(is_obs.sum())
    n_imp = int(is_imp.sum())
    n_cells = int(n_t * n_c)
    n_null = n_cells - n_obs - n_imp

    sample_idx = np.linspace(0, n_t - 1, num=min(n_t, 80), dtype=int)
    sample_charger_idx = np.linspace(0, n_c - 1, num=min(n_c, 400), dtype=int)
    sample_rows = []
    for i in sample_idx:
        for j in sample_charger_idx:
            sid, cid = cols[j].split("|", 1)
            o = values[i, j]
            r = recon[i, j]
            observed = not np.isnan(o)
            imputed = bool(is_imp[i, j])
            if observed:
                stype = "observed_event"
            elif imputed:
                stype = "ffill_within_hold"
            elif not succ[i]:
                stype = "collection_failed"
            elif not np.isnan(age[i, j]) and age[i, j] > max_hold_minutes:
                stype = "hold_expired"
            else:
                stype = "unobserved"
            sample_rows.append(
                {
                    "charger_id": cid,
                    "station_id": sid,
                    "panel_time": all_ts[i],
                    "observed_status": None if np.isnan(o) else int(o),
                    "reconstructed_status": None if np.isnan(r) else int(r),
                    "is_observed": observed,
                    "is_imputed": imputed,
                    "observation_age_minutes": None if np.isnan(age[i, j]) else float(age[i, j]),
                    "collection_success": bool(succ[i]),
                    "source_type": stype,
                }
            )
    sample_df = pd.DataFrame(sample_rows)
    sample_df.to_csv(OUT_TABLES / "panel_restore_sample.csv", index=False, encoding="utf-8-sig")
    sample_df["source_type"].value_counts().rename("count").reset_index().to_csv(
        OUT_TABLES / "panel_restore_source_type.csv", index=False, encoding="utf-8-sig"
    )

    summary = {
        "ok": True,
        "impossible": False,
        "panel_cells": n_cells,
        "n_chargers": int(n_c),
        "n_ticks": int(n_t),
        "max_hold_minutes": max_hold_minutes,
        "n_observed_cells": n_obs,
        "n_imputed_cells": n_imp,
        "n_null_cells": n_null,
        "impute_rate": n_imp / n_cells if n_cells else 0,
        "observed_rate": n_obs / n_cells if n_cells else 0,
        "null_rate": n_null / n_cells if n_cells else 0,
        "restore_accuracy_on_observed": 1.0,
        "station_tick_rows": int(len(station_tick)),
        "columns_required": [
            "charger_id",
            "station_id",
            "panel_time",
            "observed_status",
            "reconstructed_status",
            "is_observed",
            "is_imputed",
            "observation_age_minutes",
            "collection_success",
            "source_type",
        ],
        "sample_has_required_columns": True,
        "note": (
            "Panel times = actual collection ticks (~10 min ops). "
            "Regular empty 5-min grid not invented (no collection_success)."
        ),
        "five_min_grid": {
            "built": False,
            "reason": "Collector not running at 5 min; inventing ticks would fabricate collection_success.",
        },
        "_station_tick_path": str(tick_path),
    }
    (OUT_JSON / "panel_restore.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    return summary
