"""Panel reconstruction for unbiased fleet statistics.

Why this exists
---------------
The collector uses the API `period` parameter, so each snapshot returns only
chargers whose status *changed* recently. Busy chargers (frequent state
changes) therefore appear in far more rows than quiet ones. Averaging raw
observation rows over-weights busy chargers and inflates availability.

Fix: reconstruct a per-charger panel by carrying each charger's last known
state forward in time (forward-fill) *within a continuous collection segment*.
At every snapshot time each known charger contributes exactly one state, so
fleet statistics weight every charger equally. "Not returned" is interpreted
as "state unchanged" only while polling remains continuous.

States are never carried across a long collection gap. Changes during a gap
cannot be recovered because the API only returns the recent period window.

Everything is read-only over the immutable snapshots.
"""
from __future__ import annotations

import pandas as pd

from load_snapshots import load_all_snapshots

USABLE_STATES = (2, 3)  # available, in_use
MAX_CONTINUOUS_GAP_MINUTES = 25


def build_state_panel(
    source_df: pd.DataFrame | None = None,
    *,
    max_continuous_gap_minutes: int = MAX_CONTINUOUS_GAP_MINUTES,
) -> pd.DataFrame:
    """Return a wide panel: rows = snapshot time, cols = charger, value = ffilled state.

    A cell is NaN until the charger's first observation in each continuous
    collection segment, then holds the last known state within that segment.
    A gap longer than ``max_continuous_gap_minutes`` starts a fresh segment.

    ``source_df`` is accepted for deterministic tests and isolated analysis.
    When omitted, immutable snapshots are loaded through ``load_snapshots``.
    """
    df = load_all_snapshots() if source_df is None else source_df.copy()
    df["stat"] = pd.to_numeric(df["stat"], errors="coerce")
    df["ts"] = pd.to_datetime(df["snapshotId"], format="%Y%m%d_%H%M%S")
    df["charger"] = df["statId"].astype(str) + "|" + df["chgerId"].astype(str)

    wide = df.pivot_table(
        index="ts", columns="charger", values="stat", aggfunc="last"
    ).sort_index()
    segment = (
        wide.index.to_series()
        .diff()
        .gt(pd.Timedelta(minutes=max_continuous_gap_minutes))
        .cumsum()
    )
    return wide.groupby(segment).ffill()


def availability_timeseries(panel: pd.DataFrame | None = None) -> pd.DataFrame:
    """Per-snapshot, charger-weighted fleet availability.

    availability = available / (available + in_use), each charger counted once
    using its forward-filled state.
    """
    if panel is None:
        panel = build_state_panel()
    avail = (panel == 2).sum(axis=1)
    in_use = (panel == 3).sum(axis=1)
    known = (panel.isin(USABLE_STATES)).sum(axis=1)
    out = pd.DataFrame(
        {
            "ts": panel.index,
            "available": avail.to_numpy(),
            "in_use": in_use.to_numpy(),
            "usable_known": known.to_numpy(),
        }
    )
    out["availability_pct"] = out["available"] / out["usable_known"] * 100
    out["hour"] = out["ts"].dt.hour
    out["date"] = out["ts"].dt.date
    out["segment_id"] = (
        out["ts"]
        .diff()
        .gt(pd.Timedelta(minutes=MAX_CONTINUOUS_GAP_MINUTES))
        .cumsum()
    )
    return out


def hourly_availability(panel: pd.DataFrame | None = None) -> pd.Series:
    ts = availability_timeseries(panel)
    return ts.groupby("hour")["availability_pct"].mean()


def bias_summary() -> dict:
    """Compare row-weighted vs charger-weighted vs panel availability."""
    df = load_all_snapshots()
    df["stat"] = pd.to_numeric(df["stat"], errors="coerce")
    sub = df[df["stat"].isin(USABLE_STATES)]

    row_weighted = (sub["stat"] == 2).mean() * 100
    per_charger = sub.groupby(["statId", "chgerId"])["stat"].apply(
        lambda s: (s == 2).mean()
    )
    charger_weighted = per_charger.mean() * 100

    panel = build_state_panel()
    ts = availability_timeseries(panel)
    panel_weighted = ts["availability_pct"].mean()

    return {
        "row_weighted_pct": round(float(row_weighted), 1),
        "charger_weighted_pct": round(float(charger_weighted), 1),
        "panel_weighted_pct": round(float(panel_weighted), 1),
        "observed_once_pct": round(float((sub.groupby(["statId", "chgerId"]).size() == 1).mean() * 100), 1),
    }


if __name__ == "__main__":
    import json

    print(json.dumps(bias_summary(), ensure_ascii=False, indent=2))
