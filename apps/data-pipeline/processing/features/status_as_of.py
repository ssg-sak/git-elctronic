"""Latest charger status as-of a reference time (D1 refresh).

For each (statId, chgerId) keeps the newest row with statUpdDt <= as_of_ts.
Does not score or rank (AI·data ②).
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

import sys
from pathlib import Path
_PROCESSING = Path(__file__).resolve().parents[1]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))
from _bootstrap import ensure_paths

ensure_paths()

from core.cleansing import STAT_MAP

KST = ZoneInfo("Asia/Seoul")


def _observation_ts(row: pd.Series) -> pd.Timestamp | pd.NaT:
    """When we last polled and saw this row (fetchedAt preferred, else snapshotId)."""
    fetched = pd.to_datetime(row.get("fetchedAt"), errors="coerce")
    if pd.notna(fetched):
        if getattr(fetched, "tzinfo", None) is None:
            return fetched.tz_localize(KST, ambiguous="NaT", nonexistent="NaT")
        return fetched.tz_convert(KST)
    snap = row.get("snapshotId")
    if snap is not None and not (isinstance(snap, float) and pd.isna(snap)):
        parsed = pd.to_datetime(str(snap), format="%Y%m%d_%H%M%S", errors="coerce")
        if pd.notna(parsed):
            return parsed.tz_localize(KST, ambiguous="NaT", nonexistent="NaT")
    return pd.NaT


def _map_stat(raw) -> str:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return "UNKNOWN"
    s = str(raw).strip()
    if not s:
        return "UNKNOWN"
    return STAT_MAP.get(s) or STAT_MAP.get(s.zfill(2), "UNKNOWN")


def load_latest_status_as_of(
    snap_dir: str | Path,
    as_of: datetime,
) -> pd.DataFrame:
    """Return one row per charger: latest observed status at/before `as_of`.

    Columns: statId, chgerId, pk, stat, stat_mapped, statUpdDt_dt,
             status_age_seconds, last_seen_at_dt, observation_age_seconds,
             snapshotId (source of winning row).
    """
    snap_dir = Path(snap_dir)
    # Live loop data is partitioned by date:
    # snapshots/YYYYMMDD/daegu_charger_status_YYYYMMDD_HHMMSS.csv.
    # Keep the flat glob too for legacy/archive inputs.
    files_by_name: dict[str, Path] = {}
    for pattern in ("daegu_charger_status_*.csv", "*/daegu_charger_status_*.csv"):
        for path in snap_dir.glob(pattern):
            if not path.is_file():
                continue
            current = files_by_name.get(path.name)
            if current is None or len(path.parts) >= len(current.parts):
                files_by_name[path.name] = path
    files = sorted(files_by_name.values(), key=lambda path: path.name)
    empty_cols = [
        "statId",
        "chgerId",
        "pk",
        "stat",
        "stat_mapped",
        "statUpdDt_dt",
        "status_age_seconds",
        "last_seen_at_dt",
        "observation_age_seconds",
        "snapshotId",
    ]
    if not files:
        return pd.DataFrame(columns=empty_cols)

    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=KST)
    else:
        as_of = as_of.astimezone(KST)

    frames = [pd.read_csv(fp, dtype={"statId": str, "chgerId": str}) for fp in files]
    df = pd.concat(frames, ignore_index=True)
    df = df.drop_duplicates(subset=["snapshotId", "statId", "chgerId"], keep="first")

    upd = pd.to_datetime(df["statUpdDt"], format="%Y%m%d%H%M%S", errors="coerce")
    # naive → KST
    if getattr(upd.dt, "tz", None) is None:
        upd = upd.dt.tz_localize(KST, ambiguous="NaT", nonexistent="NaT")
    else:
        upd = upd.dt.tz_convert(KST)
    df = df.assign(statUpdDt_dt=upd)
    df = df.assign(observation_ts=df.apply(_observation_ts, axis=1))
    df = df[df["statUpdDt_dt"].notna() & (df["statUpdDt_dt"] <= as_of)]
    df = df[df["observation_ts"].notna() & (df["observation_ts"] <= as_of)]
    if df.empty:
        return pd.DataFrame(columns=empty_cols)

    last_seen = (
        df.groupby(["statId", "chgerId"], as_index=False)["observation_ts"]
        .max()
        .rename(columns={"observation_ts": "last_seen_at_dt"})
    )

    df = df.sort_values(["statId", "chgerId", "statUpdDt_dt", "observation_ts"])
    latest = df.groupby(["statId", "chgerId"], as_index=False, sort=False).tail(1).copy()
    latest = latest.merge(last_seen, on=["statId", "chgerId"], how="left")
    latest["stat_mapped"] = latest["stat"].map(_map_stat)
    latest["status_age_seconds"] = (as_of - latest["statUpdDt_dt"]).dt.total_seconds()
    latest["observation_age_seconds"] = (
        as_of - latest["last_seen_at_dt"]
    ).dt.total_seconds()
    latest["pk"] = latest["statId"].astype(str) + "|" + latest["chgerId"].astype(str)
    return latest[empty_cols].reset_index(drop=True)


def join_master_with_status(
    master: pd.DataFrame,
    status_latest: pd.DataFrame,
) -> pd.DataFrame:
    """Left-join master chargers with as-of status. Missing status ≠ unavailable."""
    m = master.copy()
    if "pk" not in m.columns:
        m["pk"] = m["statId"].astype(str) + "|" + m["chgerId"].astype(str)

    cols = [
        c
        for c in [
            "pk",
            "stat",
            "stat_mapped",
            "statUpdDt_dt",
            "status_age_seconds",
            "last_seen_at_dt",
            "observation_age_seconds",
            "snapshotId",
        ]
        if c in status_latest.columns
    ]
    view = m.merge(status_latest[cols], on="pk", how="left", suffixes=("", "_st"))
    view["status_missing"] = view["stat_mapped"].isna() if "stat_mapped" in view.columns else True
    # ensure unobserved mask works
    if "stat_mapped" in view.columns:
        view.loc[view["status_missing"], "stat_mapped"] = pd.NA
    view["availability_note"] = view["status_missing"].map(
        lambda x: "NO_STATUS_OBSERVED" if x else "STATUS_OBSERVED"
    )
    return view
