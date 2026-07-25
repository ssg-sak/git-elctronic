"""Parking cleaning (team5 PIS / legacy mock schemas)."""
from __future__ import annotations

import pandas as pd

from .utils import parse_kst_datetime


def clean_parking(info: pd.DataFrame, realtime: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    meta: dict = {"steps": []}
    base = info.copy()
    rt = realtime.copy()

    if base.empty:
        meta["steps"].append("parking_info_empty")
        return base, meta

    for df in (base, rt):
        if "pkltId" not in df.columns:
            continue
        df["pkltId"] = df["pkltId"].astype("string")
        if "isMock" in df.columns:
            df["isMock"] = df["isMock"].astype("string").str.lower().isin(["true", "1", "y"])
        else:
            df["isMock"] = False

    # operating hours: only if 전일운영 and empty times -> derived 00:00-24:00
    if "wkdayOperBgngHr" in base.columns:
        base["wkdayOperBgngHr_raw"] = base.get("wkdayOperBgngHr")
        base["wkdayOperEndHr_raw"] = base.get("wkdayOperEndHr")
        base["oper_hours_derived"] = False
        se = base.get("operHrWkdaySeCd", pd.Series([pd.NA] * len(base))).astype("string")
        bg = base["wkdayOperBgngHr"]
        ed = base["wkdayOperEndHr"]
        mask = se.str.contains("전일", na=False) & bg.isna() & ed.isna()
        base.loc[mask, "wkdayOperBgngHr_derived"] = "0000"
        base.loc[mask, "wkdayOperEndHr_derived"] = "2400"
        base.loc[mask, "oper_hours_derived"] = True
        meta["oper_hours_derived_rows"] = int(mask.sum())
    else:
        meta["oper_hours_derived_rows"] = 0

    # coords: team5 uses lng; legacy mock used lot
    base["lat_num"] = pd.to_numeric(base["lat"], errors="coerce") if "lat" in base.columns else pd.NA
    lng_col = "lng" if "lng" in base.columns else ("lot" if "lot" in base.columns else None)
    if lng_col is None:
        base["lng_num"] = pd.NA
        meta["steps"].append("WARN: no lng/lot column")
    else:
        base["lng_num"] = pd.to_numeric(base[lng_col], errors="coerce")
    base["crs"] = "EPSG:4326"

    # normalize realtime column aliases (team5 vs legacy)
    rt_alias = {
        "remaining_spaces": "totRmndPrkNocmprt",
        "total_spaces": "totPrkNocmprt",
        "occupancy_rate": "occupancyRate",
        "congestion_status": "prkCnfSttsCd",
        "prkNocmprt": "totPrkNocmprt",
    }
    for src, dst in rt_alias.items():
        if src in rt.columns and dst not in rt.columns:
            rt[dst] = rt[src]
    if "prkNocmprt" in base.columns and "totPrkNocmprt" not in base.columns:
        base["totPrkNocmprt"] = base["prkNocmprt"]

    if rt.empty or "pkltId" not in rt.columns:
        joined = base.copy()
        joined["realtime_parking_missing"] = True
        joined["realtime_status"] = "UNKNOWN"
        meta["steps"].append("realtime_empty_or_no_pkltId")
        meta["info_without_realtime"] = sorted(
            base["pkltId"].dropna().astype(str).unique().tolist()
        )
        meta["realtime_only_ids"] = []
        return joined, meta

    joined = base.merge(rt, on="pkltId", how="left", suffixes=("", "_rt"))
    joined["realtime_parking_missing"] = (
        joined["totRmndPrkNocmprt"].isna() if "totRmndPrkNocmprt" in joined.columns else True
    )
    joined["realtime_status"] = "UNKNOWN"
    if "prkCnfSttsCd" in joined.columns:
        joined.loc[~joined["realtime_parking_missing"], "realtime_status"] = joined.loc[
            ~joined["realtime_parking_missing"], "prkCnfSttsCd"
        ].astype("string")
    joined.loc[joined["realtime_parking_missing"], "realtime_status"] = "UNKNOWN"

    joined["totPrkNocmprt_num"] = pd.to_numeric(joined.get("totPrkNocmprt"), errors="coerce")
    joined["totRmnd_num"] = pd.to_numeric(joined.get("totRmndPrkNocmprt"), errors="coerce")
    joined["occupancy_num"] = pd.to_numeric(joined.get("occupancyRate"), errors="coerce")
    joined["rmnd_negative"] = joined["totRmnd_num"] < 0
    joined["rmnd_gt_total"] = joined["totRmnd_num"] > joined["totPrkNocmprt_num"]
    expected = 1 - (joined["totRmnd_num"] / joined["totPrkNocmprt_num"])
    joined["occupancy_inconsistent"] = (
        joined["occupancy_num"].notna()
        & expected.notna()
        & ((joined["occupancy_num"] - expected).abs() > 0.05)
    )

    only_rt = set(rt["pkltId"].dropna().astype(str)) - set(base["pkltId"].dropna().astype(str))
    only_base = set(base["pkltId"].dropna().astype(str)) - set(rt["pkltId"].dropna().astype(str))
    meta["realtime_only_ids"] = sorted(only_rt)
    meta["info_without_realtime"] = sorted(only_base)
    meta["steps"].append(f"info_without_realtime_n={len(only_base)}")
    meta["parking_source"] = "team5_pis"

    if "fetchedAt" in joined.columns:
        joined["fetchedAt_dt"], joined["fetchedAt_parse_failed"] = parse_kst_datetime(
            joined["fetchedAt"]
        )

    return joined, meta
