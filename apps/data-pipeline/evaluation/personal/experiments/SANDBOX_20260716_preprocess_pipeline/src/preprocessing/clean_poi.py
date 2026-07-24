"""Tour / city tour / walk parks cleaning."""
from __future__ import annotations

import re

import pandas as pd

from .utils import repair_mojibake_column, normalize_str_series


ATTR_ALIASES = {
    "외국어안내서비스": "외국어 안내서비스",
    "외국어 안내서비스": "외국어 안내서비스",
    "이용시간": "이용시간",
    "이용요금": "이용요금",
    "주차시설": "주차시설",
    "장애인 편의시설": "장애인 편의시설",
    "한국어 안내서비스": "한국어 안내서비스",
}


def clean_tour_attractions(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    meta: dict = {"encoding_repaired_cells": 0, "steps": []}
    out = df.copy()
    out["contentid"] = out["contentid"].astype("string")
    repaired_any = pd.Series(False, index=out.index)
    for col in ("title", "addr1", "addr2"):
        if col not in out.columns:
            continue
        fixed, flags = repair_mojibake_column(out[col])
        out[f"{col}_raw"] = out[col]
        out[col] = fixed
        repaired_any = repaired_any | flags
        meta["encoding_repaired_cells"] += int(flags.sum())
    out["encoding_repaired"] = repaired_any
    meta["encoding_repaired_rows"] = int(repaired_any.sum())

    out["lng"] = pd.to_numeric(out.get("mapx"), errors="coerce")
    out["lat"] = pd.to_numeric(out.get("mapy"), errors="coerce")
    out["crs"] = "EPSG:4326"
    a1 = out.get("addr1", pd.Series([pd.NA] * len(out))).astype("string")
    a2 = out.get("addr2", pd.Series([pd.NA] * len(out))).astype("string")
    out["addr2_structural_missing"] = a1.notna() & a2.isna()
    out["address_std"] = (a1.fillna("") + " " + a2.fillna("")).str.strip().replace("", pd.NA)
    out["has_image"] = out.get("firstimage", pd.Series([pd.NA] * len(out))).notna()
    out["isMock"] = False
    out["poi_type"] = "TOUR_API"
    out["source"] = "TourAPI_KorService2"
    meta["steps"].append(f"mojibake_repaired_rows={meta['encoding_repaired_rows']}")
    return out, meta


def _split_attr(cell) -> tuple[str | None, str | None]:
    if cell is None or (isinstance(cell, float) and pd.isna(cell)):
        return None, None
    s = str(cell).strip()
    if not s or "|" not in s:
        return None, None
    name, _, val = s.partition("|")
    name = ATTR_ALIASES.get(name.strip().replace(" ", ""), name.strip())
    # also normalize spaces in name
    name_norm = re.sub(r"\s+", " ", name.strip())
    name_norm = ATTR_ALIASES.get(name_norm.replace(" ", ""), ATTR_ALIASES.get(name_norm, name_norm))
    val = val.strip()
    if val == "":
        return name_norm, None
    return name_norm, val


def clean_city_tour(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    """Returns (wide_base, long_attrs, wide_attrs, meta). No fake coordinates."""
    meta: dict = {"steps": [], "needs_geocoding": True}
    base = df.copy()
    base["poi_id"] = [f"CITYTOUR-{i:04d}" for i in range(1, len(base) + 1)]
    base["name"] = base.get("attractname")
    base["address"] = normalize_str_series(base["address"]) if "address" in base.columns else pd.NA
    base["isMock"] = False
    base["source"] = "Daegu_CityTour"
    base["has_coords"] = False
    base["lat"] = pd.NA
    base["lng"] = pd.NA
    meta["steps"].append("city_tour has no coordinates; geocoding required later")

    long_rows = []
    for _, row in base.iterrows():
        for col in ("attr01", "attr02", "attr03", "attr04", "attr05"):
            if col not in base.columns:
                continue
            aname, aval = _split_attr(row.get(col))
            if aname is None:
                continue
            long_rows.append({
                "poi_id": row["poi_id"],
                "attractname": row.get("attractname"),
                "attr_col": col,
                "attr_name": aname,
                "attr_value": aval if aval is not None else pd.NA,
                "attr_missing": aval is None,
            })
    long_df = pd.DataFrame(long_rows)

    # wide pivot of known attrs
    if len(long_df):
        piv = long_df.pivot_table(
            index="poi_id", columns="attr_name", values="attr_value", aggfunc="first"
        ).reset_index()
    else:
        piv = pd.DataFrame({"poi_id": base["poi_id"]})

    return base, long_df, piv, meta


def clean_walk_parks(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    meta: dict = {"steps": []}
    out = df.copy()
    out["mngNo"] = out["mngNo"].astype("string")
    dup = int(out["mngNo"].duplicated().sum())
    meta["mngNo_duplicates"] = dup

    road = out.get("roadNmAddr")
    lot = out.get("lotNoAddr")
    out["address_source"] = "UNKNOWN"
    out["representative_address"] = pd.NA
    has_road = road.notna() if road is not None else pd.Series([False] * len(out))
    has_lot = lot.notna() if lot is not None else pd.Series([False] * len(out))
    out.loc[has_road, "representative_address"] = road[has_road]
    out.loc[has_road, "address_source"] = "ROAD"
    out.loc[~has_road & has_lot, "representative_address"] = lot[~has_road & has_lot]
    out.loc[~has_road & has_lot, "address_source"] = "LOT"
    out.loc[~has_road & ~has_lot, "representative_address"] = "UNKNOWN"

    out["lat_num"] = pd.to_numeric(out.get("lat"), errors="coerce")
    out["lng"] = pd.to_numeric(out.get("lot"), errors="coerce")  # lot column = lng
    out["crs"] = "EPSG:4326"
    out["coord_valid"] = out["lat_num"].between(33, 39) & out["lng"].between(124, 132)
    out["isMock"] = False
    out["poi_type"] = "PARK_WALK"
    out["source"] = "Daegu_WalkParks"
    meta["roadNmAddr_missing_rate"] = float(road.isna().mean()) if road is not None else None
    meta["steps"].append("high roadNmAddr missing -> keep rows; use lot/coords")
    return out, meta


def match_tour_candidates(tour: pd.DataFrame, city: pd.DataFrame) -> pd.DataFrame:
    """Fuzzy-ish candidate matching — NOT auto-confirmed."""
    rows = []
    t = tour[["contentid", "title", "address_std", "lat", "lng"]].copy()
    c = city[["poi_id", "attractname", "address"]].copy()
    for _, tr in t.iterrows():
        title = str(tr["title"]) if pd.notna(tr["title"]) else ""
        for _, cr in c.iterrows():
            cname = str(cr["attractname"]) if pd.notna(cr["attractname"]) else ""
            if not title or not cname:
                continue
            # simple containment / equality score
            score = 0.0
            if title.replace(" ", "") == cname.replace(" ", ""):
                score = 1.0
            elif title.replace(" ", "") in cname.replace(" ", "") or cname.replace(" ", "") in title.replace(" ", ""):
                score = 0.8
            else:
                continue
            rows.append({
                "tour_contentid": tr["contentid"],
                "tour_title": title,
                "city_poi_id": cr["poi_id"],
                "city_name": cname,
                "match_score": score,
                "needs_review": score < 1.0,
                "auto_confirmed": False,
            })
    return pd.DataFrame(rows)
