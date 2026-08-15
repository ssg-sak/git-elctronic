"""Charger info quality flags — coords, delYn, service target.

Used by `analysis/fix_dq_artifacts.py` to write quarantine + service CSVs.
"""
from __future__ import annotations

import pandas as pd

# Daegu-ish bbox (same spirit as SANDBOX preprocess; Gunwi fringe included)
DAEGU_LAT_MIN, DAEGU_LAT_MAX = 35.55, 36.45
DAEGU_LNG_MIN, DAEGU_LNG_MAX = 128.25, 129.05


def annotate_charger_info(df: pd.DataFrame) -> pd.DataFrame:
    """Add quality columns. Does not drop rows."""
    out = df.copy()
    out["statId"] = out["statId"].astype("string")
    out["chgerId"] = out["chgerId"].astype("string")

    out["lat_num"] = pd.to_numeric(out.get("lat"), errors="coerce")
    out["lng_num"] = pd.to_numeric(out.get("lng"), errors="coerce")

    if "delYn" in out.columns:
        del_y = out["delYn"].astype("string").str.upper().eq("Y")
    else:
        del_y = pd.Series(False, index=out.index)
    out["is_service_target"] = (~del_y).astype(bool)

    addr = out["addr"].astype("string") if "addr" in out.columns else pd.Series(pd.NA, index=out.index)
    out["addr_is_daegu"] = addr.str.contains("대구", na=False)
    out["coord_in_bbox"] = (
        out["lat_num"].between(DAEGU_LAT_MIN, DAEGU_LAT_MAX)
        & out["lng_num"].between(DAEGU_LNG_MIN, DAEGU_LNG_MAX)
    )
    # classic placeholder / null-island style
    out["coord_placeholder"] = (
        out["lat_num"].notna()
        & out["lng_num"].notna()
        & (out["lat_num"].round(3).isin([35.0, 0.0]))
        & (out["lng_num"].round(3).isin([128.0, 0.0]))
    )

    # same lat/lng shared by many stations (Everon-style) — flag at station level later
    xy = (
        out["lat_num"].round(6).astype("string")
        + ","
        + out["lng_num"].round(6).astype("string")
    )
    n_stat_at_xy = out.assign(_xy=xy).groupby("_xy")["statId"].transform("nunique")
    out["shared_coord_station_n"] = n_stat_at_xy
    out["shared_coord_cluster"] = n_stat_at_xy >= 10

    flags: list[str] = []
    for _, row in out.iterrows():
        f: list[str] = []
        if pd.isna(row["lat_num"]) or pd.isna(row["lng_num"]):
            f.append("MISSING_COORD")
        else:
            if row["coord_placeholder"]:
                f.append("PLACEHOLDER_COORD")
            if not row["coord_in_bbox"]:
                f.append("OUT_OF_BBOX")
            if bool(row["addr_is_daegu"]) and not bool(row["coord_in_bbox"]):
                f.append("ADDR_DAEGU_COORD_SUSPECT")
            if (
                pd.notna(row.get("addr"))
                and not bool(row["addr_is_daegu"])
                and bool(row["coord_in_bbox"])
            ):
                f.append("ADDR_NOT_DAEGU")
        flags.append("|".join(f) if f else "OK")
    out["coordinate_quality_flag"] = flags
    out["coord_ok"] = out["coordinate_quality_flag"].eq("OK")

    # info.stat is a fetch-time snapshot — never treat as live loop status
    if "stat" in out.columns:
        out["stat_at_info_fetch"] = out["stat"]
        out["stat_is_live"] = False

    return out


def service_chargers(df: pd.DataFrame) -> pd.DataFrame:
    """Rows safe for distance / map / ETA candidate pools."""
    return df[df["is_service_target"] & df["coord_ok"]].copy()


def quarantine_chargers(df: pd.DataFrame) -> pd.DataFrame:
    return df[~df["coord_ok"]].copy()
