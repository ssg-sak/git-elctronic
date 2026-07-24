"""Gap-safe panel reconstruction (DATA_PART_WORK_GUIDE §4.5).

Forward-fills last known status per charger within continuous collection
segments. Gaps longer than max_gap_minutes start a new segment.
"""
from __future__ import annotations

import pandas as pd

import sys
from pathlib import Path
_PROCESSING = Path(__file__).resolve().parents[1]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))
from _bootstrap import ensure_paths

ensure_paths()

from features.status_standard import OFFICIAL_STATUSES, to_official_status

AVAILABLE = "AVAILABLE"
CHARGING = "CHARGING"
OUT_OF_SERVICE = "OUT_OF_SERVICE"


def _normalize_events(events: pd.DataFrame) -> pd.DataFrame:
    df = events.copy()
    rename = {}
    if "statId" in df.columns and "stationId" not in df.columns:
        rename["statId"] = "stationId"
    if "chgerId" in df.columns and "chargerId" not in df.columns:
        rename["chgerId"] = "chargerId"
    if "fetchedAt" in df.columns and "observedAt" not in df.columns:
        rename["fetchedAt"] = "observedAt"
    df = df.rename(columns=rename)

    if "observedAt" not in df.columns and "snapshotId" in df.columns:
        df["observedAt"] = pd.to_datetime(
            df["snapshotId"], format="%Y%m%d_%H%M%S", errors="coerce"
        ).dt.tz_localize("Asia/Seoul")

    df["observedAt"] = pd.to_datetime(df["observedAt"], utc=True).dt.tz_convert(
        "Asia/Seoul"
    )
    df["status"] = df["status"].map(to_official_status)
    df["charger_key"] = (
        df["stationId"].astype(str) + "|" + df["chargerId"].astype(str)
    )
    return df.sort_values(["charger_key", "observedAt"])


def build_gap_safe_panel(
    events: pd.DataFrame,
    max_gap_minutes: int = 25,
) -> pd.DataFrame:
    """Return long panel: one row per (panel_ts, stationId, chargerId).

    Columns: panel_ts, stationId, chargerId, status, segment_id
    """
    df = _normalize_events(events)
    if df.empty:
        return pd.DataFrame(
            columns=["panel_ts", "stationId", "chargerId", "status", "segment_id"]
        )

    panel_times = pd.DatetimeIndex(sorted(df["observedAt"].unique()))
    gap = panel_times.to_series().diff().gt(pd.Timedelta(minutes=max_gap_minutes))
    time_segment = gap.cumsum()
    time_to_segment = dict(zip(panel_times, time_segment.values, strict=True))

    rows: list[dict] = []
    for charger_key, grp in df.groupby("charger_key", sort=False):
        station_id, charger_id = charger_key.split("|", 1)
        grp = grp.sort_values("observedAt")
        obs_segments = (
            grp["observedAt"].diff().gt(pd.Timedelta(minutes=max_gap_minutes)).cumsum()
        )
        for seg_id, seg in grp.groupby(obs_segments):
            seg = seg.sort_values("observedAt")
            last_status = None
            seg_start = seg["observedAt"].iloc[0]
            seg_end = seg["observedAt"].iloc[-1]
            seg_panel_times = panel_times[
                (panel_times >= seg_start) & (panel_times <= seg_end)
            ]
            event_idx = 0
            events_list = list(seg.itertuples(index=False))
            for ts in seg_panel_times:
                while event_idx < len(events_list) and events_list[event_idx].observedAt <= ts:
                    last_status = events_list[event_idx].status
                    event_idx += 1
                if last_status is None:
                    continue
                rows.append(
                    {
                        "panel_ts": ts,
                        "stationId": station_id,
                        "chargerId": charger_id,
                        "status": last_status,
                        "segment_id": int(time_to_segment.get(ts, seg_id)),
                    }
                )

    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values(["panel_ts", "stationId", "chargerId"]).reset_index(drop=True)


def aggregate_station_features(panel: pd.DataFrame, as_of_ts=None) -> pd.DataFrame:
    """Station-level counts/ratios at each panel_ts (guide §4.6)."""
    if panel.empty:
        return pd.DataFrame()

    df = panel.copy()
    if as_of_ts is not None:
        ts = pd.Timestamp(as_of_ts)
        if ts.tzinfo is None:
            ts = ts.tz_localize("Asia/Seoul")
        df = df[df["panel_ts"] <= ts]
        if df.empty:
            return pd.DataFrame()
        last_ts = df["panel_ts"].max()
        df = df[df["panel_ts"] == last_ts]

    usable = df["status"].isin([AVAILABLE, CHARGING])
    g = df.groupby(["panel_ts", "stationId"], dropna=False)
    out = pd.DataFrame(
        {
            "total_chargers": g.size(),
            "available_count": df.loc[df["status"] == AVAILABLE]
            .groupby(["panel_ts", "stationId"])
            .size()
            .reindex(g.size().index, fill_value=0),
            "charging_count": df.loc[df["status"] == CHARGING]
            .groupby(["panel_ts", "stationId"])
            .size()
            .reindex(g.size().index, fill_value=0),
            "out_of_service_count": df.loc[df["status"] == OUT_OF_SERVICE]
            .groupby(["panel_ts", "stationId"])
            .size()
            .reindex(g.size().index, fill_value=0),
        }
    ).reset_index()

    out["available_ratio"] = out["available_count"] / out["total_chargers"].clip(lower=1)
    out["charging_ratio"] = out["charging_count"] / out["total_chargers"].clip(lower=1)
    out["out_of_service_ratio"] = out["out_of_service_count"] / out[
        "total_chargers"
    ].clip(lower=1)
    out["hour"] = out["panel_ts"].dt.hour
    out["day_of_week"] = out["panel_ts"].dt.dayofweek
    out["is_weekend"] = out["day_of_week"].isin([5, 6]).astype(int)
    return out
