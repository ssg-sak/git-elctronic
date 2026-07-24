"""Traffic linkspeed + incident mock cleaning."""
from __future__ import annotations

import pandas as pd

from .utils import parse_kst_datetime


CONG_MAP = {"1": "원활", "2": "지체", "3": "정체"}


def clean_traffic_link(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    meta: dict = {"steps": []}
    out = df.copy()
    out["linkId"] = out["linkId"].astype("string")
    meta["pk_duplicates"] = int(out["linkId"].duplicated().sum())
    out["distanceM_num"] = pd.to_numeric(out.get("distanceM"), errors="coerce")
    out["speedKph_num"] = pd.to_numeric(out.get("speedKph"), errors="coerce")
    out["travelTimeSec_num"] = pd.to_numeric(out.get("travelTimeSec"), errors="coerce")
    out["negative_metric"] = (
        (out["distanceM_num"] < 0) | (out["speedKph_num"] < 0) | (out["travelTimeSec_num"] < 0)
    )
    # expected travel time seconds = distance_m / (speed_kmh * 1000/3600) = distance_m * 3.6 / speed
    expected = out["distanceM_num"] * 3.6 / out["speedKph_num"]
    out["travel_time_expected"] = expected
    out["travel_time_inconsistent"] = (
        out["travelTimeSec_num"].notna()
        & expected.notna()
        & ((out["travelTimeSec_num"] - expected).abs() > 30)
    )
    out["congGrade"] = out["congGrade"].astype("string")
    expected_nm = out["congGrade"].map(CONG_MAP)
    out["cong_name_inconsistent"] = (
        out["congGradeNm"].notna()
        & expected_nm.notna()
        & (out["congGradeNm"].astype("string") != expected_nm)
    )
    if "isMock" in out.columns:
        out["isMock"] = out["isMock"].astype("string").str.lower().isin(["true", "1", "y"])
    else:
        out["isMock"] = True
    out["lat_num"] = pd.to_numeric(out.get("lat"), errors="coerce")
    out["lng_num"] = pd.to_numeric(out.get("lng"), errors="coerce")
    out["crs"] = "EPSG:4326"
    meta["travel_time_inconsistent_rows"] = int(out["travel_time_inconsistent"].fillna(False).sum())
    return out, meta


def clean_traffic_incident(df: pd.DataFrame, links: pd.DataFrame, as_of: pd.Timestamp | None = None) -> tuple[pd.DataFrame, dict]:
    meta: dict = {"steps": []}
    out = df.copy()
    out["incidentId"] = out["incidentId"].astype("string")
    meta["pk_duplicates"] = int(out["incidentId"].duplicated().sum())
    out["startDt_dt"], out["startDt_parse_failed"] = parse_kst_datetime(out["startDt"])
    out["endDt_dt"], out["endDt_parse_failed"] = parse_kst_datetime(out["endDt"])
    out["start_after_end"] = out["startDt_dt"] > out["endDt_dt"]

    as_of = as_of or pd.Timestamp.now()
    out["is_active_at_asof"] = (out["startDt_dt"] <= as_of) & (out["endDt_dt"] >= as_of)
    # status consistency soft check
    out["status"] = out["status"].astype("string")
    out["affectLinkId"] = out["affectLinkId"].astype("string")
    link_ids = set(links["linkId"].astype("string"))
    out["affect_link_fk_ok"] = out["affectLinkId"].isna() | out["affectLinkId"].isin(link_ids)
    meta["fk_fail_count"] = int((~out["affect_link_fk_ok"]).sum())
    if "isMock" in out.columns:
        out["isMock"] = out["isMock"].astype("string").str.lower().isin(["true", "1", "y"])
    else:
        out["isMock"] = True
    # note missing is optional/structural
    out["note_optional_missing"] = out.get("note", pd.Series([pd.NA] * len(out))).isna()
    out["lat_num"] = pd.to_numeric(out.get("lat"), errors="coerce")
    out["lng_num"] = pd.to_numeric(out.get("lng"), errors="coerce")
    out["crs"] = "EPSG:4326"
    return out, meta
