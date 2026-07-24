"""Station-level feature aggregation (F01–F03, F08 + counts).

Canonical definitions: docs/data/스키마/피처_카탈로그.md · 상태코드_매핑.md
Does not compute recommendation scores (AI·data ②).
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd

import sys
from pathlib import Path
_PROCESSING = Path(__file__).resolve().parents[1]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))
from _bootstrap import ensure_paths

ensure_paths()

from features.use_time import is_operating_now, series_is_operating_now

AVAILABLE = "AVAILABLE"
CHARGING = "CHARGING"
OUT_OF_ORDER = "OUT_OF_ORDER"
UNDER_INSPECTION = "UNDER_INSPECTION"
UNKNOWN = "UNKNOWN"

OBSERVED_STATUSES = {AVAILABLE, CHARGING, OUT_OF_ORDER, UNDER_INSPECTION}


def _col(df: pd.DataFrame, *names: str) -> str:
    for n in names:
        if n in df.columns:
            return n
    raise KeyError(f"None of {names} in columns: {list(df.columns)}")


def resolve_stat_series(df: pd.DataFrame) -> pd.Series:
    """Prefer mapped status; fall back to raw `stat` if already standard."""
    if "stat_mapped" in df.columns:
        s = df["stat_mapped"].astype("string")
    elif "stat" in df.columns:
        s = df["stat"].astype("string")
    else:
        raise KeyError("need stat_mapped or stat")
    return s


def is_unobserved_mask(df: pd.DataFrame, stat: pd.Series) -> pd.Series:
    """Unobserved = explicit missing flag OR unknown/null status."""
    if "status_missing" in df.columns:
        sm = df["status_missing"]
        if sm.dtype == bool:
            missing = sm.fillna(False)
        else:
            missing = sm.astype(str).str.lower().isin(["true", "1", "yes"])
    else:
        missing = pd.Series(False, index=df.index)

    unk = stat.isna() | (stat.str.upper() == UNKNOWN) | (stat.str.upper() == "STATUS_UNKNOWN")
    note = pd.Series(False, index=df.index)
    if "availability_note" in df.columns:
        note = df["availability_note"].astype("string") == "NO_STATUS_OBSERVED"
    return missing | unk | note


def aggregate_availability_features(df_chargers: pd.DataFrame) -> pd.DataFrame:
    """F01 availability_ratio_observed, F02 unobserved_rate, F03 has_confirmed_available.

    Also returns F06 total_chargers, F07 available_count.

    Row key: statId or stat_id.
    Unobserved chargers never increment available_count.
    If observed_count==0 → availability_ratio_observed is NA (not 0).
    """
    if df_chargers.empty:
        return pd.DataFrame(
            columns=[
                "statId",
                "total_chargers",
                "available_count",
                "observed_count",
                "unobserved_count",
                "availability_ratio_observed",
                "unobserved_rate",
                "has_confirmed_available",
            ]
        )

    df = df_chargers.copy()
    id_col = _col(df, "statId", "stat_id")
    stat = resolve_stat_series(df).str.upper()
    # sandbox may keep CHARGING; map aliases
    stat = stat.replace({"IN_USE": CHARGING, "MAINTENANCE": UNDER_INSPECTION})

    unobs = is_unobserved_mask(df, stat)
    available = (~unobs) & (stat == AVAILABLE)
    observed = ~unobs

    g = df.groupby(id_col, dropna=False)
    out = pd.DataFrame(
        {
            "total_chargers": g.size(),
            "available_count": available.groupby(df[id_col]).sum().astype(int),
            "observed_count": observed.groupby(df[id_col]).sum().astype(int),
            "unobserved_count": unobs.groupby(df[id_col]).sum().astype(int),
        }
    ).fillna(0)
    out["total_chargers"] = out["total_chargers"].astype(int)
    out["available_count"] = out["available_count"].astype(int)
    out["observed_count"] = out["observed_count"].astype(int)
    out["unobserved_count"] = out["unobserved_count"].astype(int)

    out["availability_ratio_observed"] = out.apply(
        lambda r: (r["available_count"] / r["observed_count"])
        if r["observed_count"] > 0
        else pd.NA,
        axis=1,
    )
    out["unobserved_rate"] = out.apply(
        lambda r: (r["unobserved_count"] / r["total_chargers"])
        if r["total_chargers"] > 0
        else pd.NA,
        axis=1,
    )
    out["has_confirmed_available"] = out["available_count"] >= 1

    out = out.reset_index().rename(columns={id_col: "statId"})
    return out


def grade_from_age_minutes(minutes: float) -> str:
    if minutes != minutes or minutes == float("inf"):  # NaN or inf
        return "CHECK_REQUIRED"
    if minutes <= 5.0:
        return "HIGH"
    if minutes <= 15.0:
        return "NORMAL"
    return "CHECK_REQUIRED"


_GRADE_RANK = {"HIGH": 3, "NORMAL": 2, "CHECK_REQUIRED": 1}


def effective_grade(status_grade: str, observation_grade: str) -> str:
    """Pick the better (fresher) grade when dual freshness is available."""
    return (
        status_grade
        if _GRADE_RANK.get(status_grade, 0) >= _GRADE_RANK.get(observation_grade, 0)
        else observation_grade
    )


def aggregate_reliability_from_age(
    df_chargers: pd.DataFrame,
    age_col: str = "status_age_seconds",
) -> pd.DataFrame:
    """Station-level F04/F05 from per-charger age (min age among observed)."""
    if df_chargers.empty:
        return pd.DataFrame(columns=["statId", "status_age_minutes", "reliability_grade"])

    df = df_chargers.copy()
    id_col = _col(df, "statId", "stat_id")
    if age_col not in df.columns:
        # fall back via reliability module style column
        return pd.DataFrame(
            {
                "statId": df[id_col].drop_duplicates().values,
                "status_age_minutes": float("inf"),
                "reliability_grade": "CHECK_REQUIRED",
            }
        )

    age_sec = pd.to_numeric(df[age_col], errors="coerce")
    age_min = age_sec / 60.0
    stat = resolve_stat_series(df).str.upper()
    unobs = is_unobserved_mask(df, stat)
    age_min = age_min.where(~unobs, other=pd.NA)

    g = age_min.groupby(df[id_col])
    mins = g.min()
    out = mins.reset_index()
    out.columns = ["statId", "status_age_minutes"]
    out["reliability_grade"] = out["status_age_minutes"].apply(
        lambda m: grade_from_age_minutes(float(m) if pd.notna(m) else float("inf"))
    )
    return out


def aggregate_observation_freshness(
    df_chargers: pd.DataFrame,
    age_col: str = "observation_age_seconds",
) -> pd.DataFrame:
    """Station-level F04b/F05b from per-charger last poll time (min age among observed)."""
    if df_chargers.empty:
        return pd.DataFrame(
            columns=[
                "statId",
                "observation_age_minutes",
                "observation_grade",
                "reliability_grade_effective",
            ]
        )

    df = df_chargers.copy()
    id_col = _col(df, "statId", "stat_id")
    stat = resolve_stat_series(df).str.upper()
    unobs = is_unobserved_mask(df, stat)

    status_min = pd.to_numeric(df.get("status_age_seconds"), errors="coerce") / 60.0
    status_min = status_min.where(~unobs, other=pd.NA)

    if age_col not in df.columns:
        obs_min = pd.Series(float("inf"), index=df.index)
    else:
        obs_min = pd.to_numeric(df[age_col], errors="coerce") / 60.0
        obs_min = obs_min.where(~unobs, other=pd.NA)

    status_station = status_min.groupby(df[id_col]).min()
    obs_station = obs_min.groupby(df[id_col]).min()

    out = pd.DataFrame({"statId": status_station.index})
    out["observation_age_minutes"] = obs_station.values
    out["observation_grade"] = out["observation_age_minutes"].apply(
        lambda m: grade_from_age_minutes(float(m) if pd.notna(m) else float("inf"))
    )
    status_grade = status_station.apply(
        lambda m: grade_from_age_minutes(float(m) if pd.notna(m) else float("inf"))
    )
    out["reliability_grade_effective"] = [
        effective_grade(sg, og)
        for sg, og in zip(status_grade.values, out["observation_grade"].values, strict=True)
    ]
    return out.reset_index(drop=True)


def aggregate_reliability_combined(
    df_chargers: pd.DataFrame,
) -> pd.DataFrame:
    """F04/F05 + F04b/F05b in one station-level table."""
    status = aggregate_reliability_from_age(df_chargers)
    if status.empty:
        return aggregate_observation_freshness(df_chargers)
    obs = aggregate_observation_freshness(df_chargers)
    return status.merge(obs, on="statId", how="left")


def operating_now_from_use_time(
    use_time: str | float | None,
    when: datetime | None = None,
) -> str:
    """F08 wrapper — see `use_time.is_operating_now`."""
    return is_operating_now(use_time, when)


def series_operating_now(
    use_times: pd.Series,
    when: datetime | None = None,
) -> pd.Series:
    """F08 vectorized — Y / N / UNKNOWN."""
    return series_is_operating_now(use_times, when)
