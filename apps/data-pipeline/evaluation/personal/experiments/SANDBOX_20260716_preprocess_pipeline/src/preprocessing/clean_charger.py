"""Charger info + status cleaning."""
from __future__ import annotations

import pandas as pd

from . import paths
from .utils import (
    load_stat_code_map,
    normalize_busi_name,
    parse_kst_datetime,
    save_table,
)


def clean_charger_info(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    meta: dict = {"steps": []}
    out = df.copy()
    out["statId"] = out["statId"].astype("string")
    out["chgerId"] = out["chgerId"].astype("string")
    out["pk"] = out["statId"] + "|" + out["chgerId"]

    dup = int(out["pk"].duplicated().sum())
    meta["pk_duplicates"] = dup
    meta["steps"].append(f"pk_duplicates={dup}")

    out["lat_num"] = pd.to_numeric(out["lat"], errors="coerce")
    out["lng_num"] = pd.to_numeric(out["lng"], errors="coerce")
    out["output_num"] = pd.to_numeric(out["output"], errors="coerce")
    out["output_missing"] = out["output_num"].isna()

    for col in ("parkingFree", "limitYn", "delYn"):
        if col in out.columns:
            out[f"{col}_raw"] = out[col]
            mapped = out[col].astype("string").str.upper()
            out[col] = mapped

    # parkingFree missing -> UNKNOWN (do not infer free/paid)
    if "parkingFree" in out.columns:
        pf = out["parkingFree"].astype("string").str.upper()
        out["parkingFree"] = pf.where(pf.isin(["Y", "N"]), "UNKNOWN")

    out["busiNm_raw"] = out.get("busiNm")
    out["busiNm_norm"] = out["busiNm"].map(normalize_busi_name) if "busiNm" in out.columns else pd.NA

    out["useTime_raw"] = out.get("useTime")
    out["operation_time_known"] = out["useTime"].notna() if "useTime" in out.columns else False
    ut = out["useTime"].astype("string") if "useTime" in out.columns else pd.Series([pd.NA] * len(out))
    out["is_24h"] = ut.str.contains("24", na=False) | ut.str.contains("종일", na=False)

    del_y = out["delYn"].astype("string").str.upper().eq("Y") if "delYn" in out.columns else False
    out["is_service_target"] = ~del_y

    # address / coordinate quality
    addr = out["addr"].astype("string") if "addr" in out.columns else pd.Series([pd.NA] * len(out))
    out["addr_is_daegu"] = addr.str.contains("대구", na=False)
    out["coord_in_bbox"] = (
        out["lat_num"].between(paths.DAEGU_LAT_MIN, paths.DAEGU_LAT_MAX)
        & out["lng_num"].between(paths.DAEGU_LNG_MIN, paths.DAEGU_LNG_MAX)
    )
    # same statId conflicting coords
    g = out.groupby("statId")["lat_num"].transform("nunique", dropna=True)
    out["statid_coord_conflict"] = g.fillna(0).astype(int) > 1

    flags = []
    for i, row in out.iterrows():
        f = []
        if pd.isna(row["lat_num"]) or pd.isna(row["lng_num"]):
            f.append("MISSING_COORD")
        elif not row["coord_in_bbox"]:
            f.append("OUT_OF_BBOX")
        if row.get("addr_is_daegu") and row.get("coord_in_bbox") is False and pd.notna(row["lat_num"]):
            f.append("ADDR_DAEGU_COORD_SUSPECT")
        if not row.get("addr_is_daegu") and pd.notna(row.get("addr")) and row.get("coord_in_bbox"):
            f.append("ADDR_NOT_DAEGU")
        if row.get("statid_coord_conflict"):
            f.append("STATID_COORD_CONFLICT")
        flags.append("|".join(f) if f else "OK")
    out["coordinate_quality_flag"] = flags

    quarantine = out[out["coordinate_quality_flag"] != "OK"].copy()
    meta["quarantine_rows"] = len(quarantine)
    meta["steps"].append(f"quarantine_coord_rows={len(quarantine)}")

    # keep all rows (no auto delete) — quarantine is separate copy
    save_table(quarantine, paths.QUARANTINE_DIR / "charger_coordinate_suspects")
    return out, quarantine, meta


def clean_charger_status(status: pd.DataFrame, info: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    meta: dict = {"steps": []}
    st = status.copy()
    st["statId"] = st["statId"].astype("string")
    st["chgerId"] = st["chgerId"].astype("string")
    st["pk"] = st["statId"] + "|" + st["chgerId"]

    # restore statNm from info
    info_key = info[["statId", "chgerId", "statNm"]].drop_duplicates(subset=["statId", "chgerId"])
    info_key = info_key.rename(columns={"statNm": "statNm_from_info"})
    st = st.merge(info_key, on=["statId", "chgerId"], how="left")
    st["statNm_raw"] = st.get("statNm")
    st["statNm"] = st["statNm_from_info"].combine_first(st["statNm_raw"])
    restored = int(st["statNm_raw"].isna().sum() & st["statNm"].notna().sum())  # rough
    meta["statNm_restored_via_join"] = int(st["statNm_from_info"].notna().sum())
    meta["steps"].append("statNm restored via info join where possible")

    st["statUpdDt_dt"], st["statUpdDt_parse_failed"] = parse_kst_datetime(st["statUpdDt"], fmt="%Y%m%d%H%M%S")
    st["fetchedAt_dt"], st["fetchedAt_parse_failed"] = parse_kst_datetime(st["fetchedAt"])
    age = (st["fetchedAt_dt"] - st["statUpdDt_dt"]).dt.total_seconds()
    st["status_age_seconds"] = age
    st["is_status_stale"] = age > paths.STATUS_STALE_SECONDS

    code_map = load_stat_code_map(paths.CONFIG_DIR / "stat_code_map.json")
    st["stat_raw"] = st["stat"].astype("string")
    st["stat_mapped"] = st["stat_raw"].map(lambda x: code_map.get(str(x), "UNKNOWN_CODE") if pd.notna(x) else pd.NA)

    # coverage vs info
    info_pks = set(info["pk"])
    status_pks = set(st["pk"])
    meta["status_rows"] = len(st)
    meta["info_rows"] = len(info)
    meta["coverage_charger_pct"] = round(100.0 * len(status_pks & info_pks) / max(len(info_pks), 1), 4)
    info_stations = set(info["statId"])
    status_stations = set(st["statId"])
    meta["coverage_station_pct"] = round(100.0 * len(status_stations & info_stations) / max(len(info_stations), 1), 4)

    # by busi / type
    tmp = info.merge(st[["pk"]].assign(has_status=True), on="pk", how="left")
    tmp["has_status"] = tmp["has_status"].fillna(False)
    if "busiNm_norm" in tmp.columns:
        meta["coverage_by_busi"] = (
            tmp.groupby(tmp["busiNm_norm"].fillna("UNKNOWN"))["has_status"].mean().mul(100).round(2).to_dict()
        )
    if "chgerType" in tmp.columns:
        meta["coverage_by_type"] = (
            tmp.groupby(tmp["chgerType"].fillna("UNKNOWN"))["has_status"].mean().mul(100).round(2).to_dict()
        )

    return st, meta


def build_charger_tables(info_clean: pd.DataFrame, status_clean: pd.DataFrame) -> dict[str, pd.DataFrame]:
    master = info_clean.copy()
    status_cur = status_clean.copy()

    view = master.merge(
        status_cur[
            [
                "pk", "stat", "stat_mapped", "statNm", "statUpdDt_dt", "fetchedAt_dt",
                "status_age_seconds", "is_status_stale", "statUpdDt_parse_failed",
            ]
        ],
        on="pk",
        how="left",
        suffixes=("", "_st"),
    )
    view["status_missing"] = view["stat"].isna()
    # NEVER convert missing status to unavailable
    view["availability_note"] = view["status_missing"].map(
        lambda x: "NO_STATUS_OBSERVED" if x else "STATUS_OBSERVED"
    )

    return {
        "charger_master": master,
        "charger_status_current": status_cur,
        "charger_current_view": view,
    }
