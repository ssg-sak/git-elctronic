# -*- coding: utf-8 -*-
"""Export team_5 parking tables → docs/data/extracted/parking/ CSVs."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
from dotenv import load_dotenv

_PROCESSING = Path(__file__).resolve().parents[1]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))
from _bootstrap import ensure_paths

REPO = ensure_paths()
from loop_paths import EXTRACTED_PARKING

KST = ZoneInfo("Asia/Seoul")


def connect():
    load_dotenv(REPO / ".env")
    pwd = os.environ.get("TEAM5_DB_PASSWORD", "").strip()
    if not pwd:
        raise RuntimeError("TEAM5_DB_PASSWORD missing in .env")
    import pymysql

    return pymysql.connect(
        host=os.environ.get("TEAM5_DB_HOST", "3.39.251.72"),
        port=int(os.environ.get("TEAM5_DB_PORT", "3306")),
        user=os.environ.get("TEAM5_DB_USER", "ev_model_reader"),
        password=pwd,
        database=os.environ.get("TEAM5_DB_NAME", "team_5"),
        charset="utf8mb4",
        connect_timeout=15,
        read_timeout=120,
    )


def _first_list(obj):
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for v in obj.values():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                return v
            if isinstance(v, dict):
                found = _first_list(v)
                if found:
                    return found
    return []


def export_from_raw(conn) -> tuple[pd.DataFrame, pd.DataFrame]:
    cur = conn.cursor()
    cur.execute(
        "SELECT api_type, collected_at, http_status, payload FROM parking_api_raw ORDER BY id"
    )
    info_rows: list[dict] = []
    rt_from_raw: list[dict] = []
    for api_type, collected_at, http_status, payload in cur.fetchall():
        d = json.loads(payload)
        items = d.get("data") if isinstance(d.get("data"), list) else _first_list(d.get("data", d))
        print(f"raw {api_type}: http={http_status} items={len(items)} at={collected_at}")
        if not items:
            continue
        if api_type == "parking_info":
            for it in items:
                info = it.get("prkInfo") or {}
                fclt = it.get("prkFcltInfo") or {}
                oper = it.get("prkOperInfo") or {}
                info_rows.append(
                    {
                        "pkltId": info.get("pkltId"),
                        "pkltNm": info.get("pkltNm"),
                        "sggCd": info.get("sggCd"),
                        "useYn": info.get("useYn"),
                        "sysgrpyYn": info.get("sysgrpyYn"),
                        "pkltSeCd": fclt.get("pkltSeCd"),
                        "pkltTypeCd": fclt.get("pkltTypeCd"),
                        "roadNmAddr": fclt.get("roadNmAddr"),
                        "lotnoAddr": fclt.get("lotnoAddr"),
                        "addr": fclt.get("roadNmAddr") or fclt.get("lotnoAddr"),
                        "lat": fclt.get("lat"),
                        "lng": fclt.get("lot"),  # PIS uses 'lot' for longitude
                        "prkNocmprt": fclt.get("prkNocmprt"),
                        "mngInstNm": fclt.get("mngInstNm"),
                        "telno": fclt.get("telno"),
                        "wkdayOperBgngHr": oper.get("wkdayOperBgngHr"),
                        "wkdayOperEndHr": oper.get("wkdayOperEndHr"),
                        "parking_source": "team5_pis",
                        "isMock": False,
                        "fetchedAt": str(collected_at),
                    }
                )
        elif api_type == "parking_realtime":
            for it in items:
                r = it.get("rltmPrkInfo") or {}
                tot = r.get("totPrkNocmprt")
                rem = r.get("totRmndPrkNocmprt")
                occ = None
                if tot not in (None, 0, "0") and rem is not None:
                    try:
                        tot_f, rem_f = float(tot), float(rem)
                        occ = round((tot_f - rem_f) / tot_f * 100, 2) if tot_f else None
                    except (TypeError, ValueError):
                        occ = None
                rt_from_raw.append(
                    {
                        "pkltId": r.get("pkltId"),
                        "pkltSeCd": r.get("pkltSeCd"),
                        "pkltTypeCd": r.get("pkltTypeCd"),
                        "congestion_status": r.get("prkCnfSttsCd"),
                        "flrCnt": r.get("flrCnt"),
                        "total_spaces": tot,
                        "remaining_spaces": rem,
                        "occupancy_rate": occ,
                        "parking_source": "team5_pis",
                        "isMock": False,
                        "fetchedAt": str(collected_at),
                    }
                )
    return pd.DataFrame(info_rows), pd.DataFrame(rt_from_raw)


def export_realtime_table(conn) -> pd.DataFrame:
    return pd.read_sql(
        """
        SELECT
          id, source_raw_id, pklt_id AS pkltId, collected_at AS fetchedAt,
          pklt_se_cd AS pkltSeCd, pklt_type_cd AS pkltTypeCd,
          congestion_status, floor_count AS flrCnt,
          total_spaces, remaining_spaces, occupied_spaces, occupancy_rate
        FROM parking_realtime_status
        ORDER BY pklt_id
        """,
        conn,
    )


def main() -> int:
    as_of = datetime.now(KST)
    EXTRACTED_PARKING.mkdir(parents=True, exist_ok=True)
    stamp = as_of.strftime("%Y%m%d_%H%M%S")

    with connect() as conn:
        info_df, rt_raw_df = export_from_raw(conn)
        rt_tbl = export_realtime_table(conn)

    paths = {}
    # prefer structured realtime table
    rt = rt_tbl.copy()
    rt["parking_source"] = "team5_pis"
    rt["isMock"] = False
    if rt.empty and len(rt_raw_df):
        rt = rt_raw_df

    if len(info_df):
        p = EXTRACTED_PARKING / f"daegu_parking_info_team5_{stamp}.csv"
        latest = EXTRACTED_PARKING / "daegu_parking_info_team5_latest.csv"
        info_df.to_csv(p, index=False, encoding="utf-8-sig")
        info_df.to_csv(latest, index=False, encoding="utf-8-sig")
        paths["info"] = str(latest.relative_to(REPO)).replace("\\", "/")
        lat_ok = pd.to_numeric(info_df.get("lat"), errors="coerce").notna().sum()
        print("info rows", len(info_df), "with_lat", int(lat_ok))
    else:
        print("WARN: no parking_info parsed from raw")

    p_rt = EXTRACTED_PARKING / f"daegu_parking_realtime_team5_{stamp}.csv"
    latest_rt = EXTRACTED_PARKING / "daegu_parking_realtime_team5_latest.csv"
    rt.to_csv(p_rt, index=False, encoding="utf-8-sig")
    rt.to_csv(latest_rt, index=False, encoding="utf-8-sig")
    paths["realtime"] = str(latest_rt.relative_to(REPO)).replace("\\", "/")
    print("realtime rows", len(rt))

    # joined view: realtime + info coords (for charger distance join)
    if len(info_df) and len(rt):
        join = rt.merge(
            info_df[
                [
                    c
                    for c in ["pkltId", "pkltNm", "addr", "lat", "lng", "roadNmAddr"]
                    if c in info_df.columns
                ]
            ],
            on="pkltId",
            how="left",
            suffixes=("", "_info"),
        )
        jpath = EXTRACTED_PARKING / "daegu_parking_realtime_with_coords_team5_latest.csv"
        join.to_csv(jpath, index=False, encoding="utf-8-sig")
        paths["realtime_with_coords"] = str(jpath.relative_to(REPO)).replace("\\", "/")
        print(
            "joined realtime+coords",
            len(join),
            "matched_lat",
            int(pd.to_numeric(join.get("lat"), errors="coerce").notna().sum()),
        )

    # short pointer — canonical plan lives under docs/data/
    # README is maintained separately; only stamp export meta sidecar
    meta_path = EXTRACTED_PARKING / "team5_export_meta.json"
    meta_path.write_text(
        json.dumps(
            {
                "as_of_kst": as_of.isoformat(timespec="seconds"),
                "paths": paths,
                "plan": "docs/data/주차/주차_실데이터_계획_team5_20260723.md",
                "role": "DA① export only — scoring is ② / runtime query is BE",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print("wrote", meta_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
