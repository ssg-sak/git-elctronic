"""Parking mock cleaning."""
from __future__ import annotations

import pandas as pd

from .utils import parse_kst_datetime


def clean_parking(info: pd.DataFrame, realtime: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    meta: dict = {"steps": []}
    base = info.copy()
    rt = realtime.copy()

    for df in (base, rt):
        df["pkltId"] = df["pkltId"].astype("string")
        if "isMock" in df.columns:
            df["isMock"] = df["isMock"].astype("string").str.lower().isin(["true", "1", "y"])
        else:
            df["isMock"] = True

    # operating hours: only if 전일운영 and empty times -> derived 00:00-24:00
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

    base["lat_num"] = pd.to_numeric(base["lat"], errors="coerce")
    base["lng_num"] = pd.to_numeric(base["lot"], errors="coerce")  # lot = lng in this schema
    base["crs"] = "EPSG:4326"

    joined = base.merge(rt, on="pkltId", how="left", suffixes=("", "_rt"))
    joined["realtime_parking_missing"] = joined["totRmndPrkNocmprt"].isna() if "totRmndPrkNocmprt" in joined.columns else True
    joined["realtime_status"] = "UNKNOWN"
    if "prkCnfSttsCd" in joined.columns:
        joined.loc[~joined["realtime_parking_missing"], "realtime_status"] = joined.loc[
            ~joined["realtime_parking_missing"], "prkCnfSttsCd"
        ].astype("string")
    # missing realtime is NOT 만차
    joined.loc[joined["realtime_parking_missing"], "realtime_status"] = "UNKNOWN"

    # validations on rows with realtime
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

    only_rt = set(rt["pkltId"]) - set(base["pkltId"])
    only_base = set(base["pkltId"]) - set(rt["pkltId"])
    meta["realtime_only_ids"] = sorted(only_rt)
    meta["info_without_realtime"] = sorted(only_base)
    meta["steps"].append(f"info_without_realtime={sorted(only_base)}")

    if "fetchedAt" in joined.columns:
        joined["fetchedAt_dt"], joined["fetchedAt_parse_failed"] = parse_kst_datetime(joined["fetchedAt"])

    return joined, meta
