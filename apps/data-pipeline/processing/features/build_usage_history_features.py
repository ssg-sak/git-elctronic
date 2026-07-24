"""Build station history usage features from Daegu municipal daily usage CSV.

Steps:
  1. Load docs/data/extracted/charger/usage/daegu_charger_usage_daily_*.csv (cp949 or utf-8-sig)
  2. Nearest-join municipal station coords → EvCharger charger_master (≤80m)
  3. Aggregate per matched statId (+ charger type) → usage intensity / usage_level

Outputs:
  - docs/data/spatial_join/join_usage_history_statId.csv
  - docs/data/spatial_join/join_usage_history_meta.json
  - apps/data-pipeline/evaluation/results/datasets/station_history_features_latest.csv
  - .../station_history_features_meta.json

Does NOT merge into D1 (quality review first). Does NOT compute recommendation scores.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd

import sys
from pathlib import Path
_PROCESSING = Path(__file__).resolve().parents[1]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))
from _bootstrap import ensure_paths

REPO = ensure_paths()
from loop_paths import EXTRACTED_CHARGER_USAGE

USAGE_GLOB = EXTRACTED_CHARGER_USAGE
MASTER = (
    REPO
    / "apps/data-pipeline/evaluation/personal/experiments"
    / "SANDBOX_20260716_preprocess_pipeline"
    / "data/processed/charger_master.csv"
)
OUT_JOIN = REPO / "docs" / "data" / "spatial_join"
OUT_FEAT = REPO / "apps" / "data-pipeline" / "evaluation" / "results" / "datasets"
RADIUS_M = 80.0


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def find_usage_csv() -> Path:
    files = sorted(USAGE_GLOB.glob("daegu_charger_usage_daily_*.csv"))
    if not files:
        raise FileNotFoundError(f"No usage CSV under {USAGE_GLOB}")
    return files[-1]


def load_usage(path: Path) -> pd.DataFrame:
    last_err: Exception | None = None
    for enc in ("cp949", "utf-8-sig", "utf-8"):
        try:
            df = pd.read_csv(path, encoding=enc, dtype=str)
            break
        except Exception as e:  # noqa: BLE001
            last_err = e
            df = None
    if df is None:
        raise RuntimeError(f"Cannot read {path}: {last_err}")

    rename = {
        "일자": "date",
        "충전소아이디": "station_id_daegu",
        "충전소명칭": "station_name_daegu",
        "위도": "lat",
        "경도": "lng",
        "충전기아이디": "charger_id_daegu",
        "충전기타입": "charger_type",
        "사용횟수": "sessions",
        "충전량": "kwh",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
    need = ["date", "station_id_daegu", "lat", "lng", "charger_id_daegu", "charger_type", "sessions"]
    missing = [c for c in need if c not in df.columns]
    if missing:
        raise ValueError(f"usage CSV missing columns: {missing}")

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    df["lng"] = pd.to_numeric(df["lng"], errors="coerce")
    df["sessions"] = pd.to_numeric(df["sessions"], errors="coerce").fillna(0)
    if "kwh" in df.columns:
        df["kwh"] = pd.to_numeric(df["kwh"], errors="coerce")
    if "station_name_daegu" not in df.columns:
        df["station_name_daegu"] = ""
    return df.dropna(subset=["date", "lat", "lng", "station_id_daegu"]).reset_index(drop=True)


def load_stations() -> pd.DataFrame:
    df = pd.read_csv(MASTER, dtype=str, low_memory=False)
    for c in ("lat_num", "lng_num", "lat", "lng"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    lat = df["lat_num"] if "lat_num" in df.columns else df["lat"]
    lng = df["lng_num"] if "lng_num" in df.columns else df["lng"]
    df = df.assign(lat_f=lat, lng_f=lng)
    if "coordinate_quality_flag" in df.columns:
        df = df[df["coordinate_quality_flag"] == "OK"]
    return (
        df.dropna(subset=["lat_f", "lng_f"])
        .drop_duplicates(subset=["statId"])
        [["statId", "statNm", "addr", "lat_f", "lng_f"]]
        .reset_index(drop=True)
    )


def join_usage_stations(usage: pd.DataFrame, stations: pd.DataFrame, radius_m: float) -> pd.DataFrame:
    """Map each municipal station_id → nearest EvCharger statId within radius_m."""
    uniq = (
        usage.groupby("station_id_daegu", as_index=False)
        .agg(
            station_name_daegu=("station_name_daegu", "first"),
            lat=("lat", "first"),
            lng=("lng", "first"),
        )
    )
    st_coords = list(
        zip(
            stations["statId"].astype(str),
            stations["statNm"].astype(str),
            stations["lat_f"].astype(float),
            stations["lng_f"].astype(float),
            strict=True,
        )
    )
    rows = []
    for _, u in uniq.iterrows():
        best_id = best_name = None
        best_d = None
        ulat, ulng = float(u["lat"]), float(u["lng"])
        for sid, snm, slat, slng in st_coords:
            d = haversine_m(ulat, ulng, slat, slng)
            if d <= radius_m and (best_d is None or d < best_d):
                best_d = d
                best_id = sid
                best_name = snm
        rows.append(
            {
                "station_id_daegu": u["station_id_daegu"],
                "station_name_daegu": u["station_name_daegu"],
                "lat": ulat,
                "lng": ulng,
                "statId": best_id or "",
                "statNm": best_name or "",
                "distance_m": round(best_d, 1) if best_d is not None else "",
                "radius_m": radius_m,
                "matched": best_d is not None,
            }
        )
    return pd.DataFrame(rows)


def build_features(usage: pd.DataFrame, join_map: pd.DataFrame) -> pd.DataFrame:
    matched = join_map[join_map["matched"]].copy()
    if matched.empty:
        return pd.DataFrame()

    u = usage.merge(
        matched[["station_id_daegu", "statId", "statNm", "distance_m"]],
        on="station_id_daegu",
        how="inner",
    )
    u["dow"] = u["date"].dt.dayofweek  # 0=Mon
    u["is_weekend"] = u["dow"] >= 5

    # charger count per station × type (unique charger ids in history)
    n_ch = (
        u.groupby(["statId", "charger_type"])["charger_id_daegu"]
        .nunique()
        .rename("n_chargers")
        .reset_index()
    )

    # daily totals per station × type
    if "kwh" in u.columns:
        daily = u.groupby(
            ["statId", "statNm", "charger_type", "date", "dow", "is_weekend"], as_index=False
        ).agg(sessions=("sessions", "sum"), kwh=("kwh", "sum"))
    else:
        daily = u.groupby(
            ["statId", "statNm", "charger_type", "date", "dow", "is_weekend"], as_index=False
        ).agg(sessions=("sessions", "sum"))
        daily["kwh"] = float("nan")

    same_dow = (
        daily.groupby(["statId", "charger_type", "dow"], as_index=False)
        .agg(same_dow_avg_sessions=("sessions", "mean"))
    )

    weekday = (
        daily[~daily["is_weekend"]]
        .groupby(["statId", "charger_type"], as_index=False)
        .agg(weekday_avg_sessions=("sessions", "mean"))
    )
    weekend = (
        daily[daily["is_weekend"]]
        .groupby(["statId", "charger_type"], as_index=False)
        .agg(weekend_avg_sessions=("sessions", "mean"))
    )

    max_date = daily["date"].max()
    cut_28 = max_date - pd.Timedelta(days=27)
    cut_7 = max_date - pd.Timedelta(days=6)
    d28 = daily[daily["date"] >= cut_28]
    d7 = daily[daily["date"] >= cut_7]

    avg28 = d28.groupby(["statId", "charger_type"], as_index=False).agg(
        avg_sessions_28d=("sessions", "mean"),
        avg_kwh_28d=("kwh", "mean"),
    )
    avg7 = d7.groupby(["statId", "charger_type"], as_index=False).agg(
        avg_sessions_7d=("sessions", "mean"),
    )

    # overall mean for usage_level (station × type)
    overall = daily.groupby(["statId", "statNm", "charger_type"], as_index=False).agg(
        avg_sessions_all=("sessions", "mean"),
        avg_kwh_all=("kwh", "mean"),
        n_days=("date", "nunique"),
    )

    feat = overall.merge(n_ch, on=["statId", "charger_type"], how="left")
    feat = feat.merge(weekday, on=["statId", "charger_type"], how="left")
    feat = feat.merge(weekend, on=["statId", "charger_type"], how="left")
    feat = feat.merge(avg28, on=["statId", "charger_type"], how="left")
    feat = feat.merge(avg7, on=["statId", "charger_type"], how="left")

    # attach same-dow as wide-ish: keep long table keyed by dow separately? Plan wants
    # station_same_dow — export long rows with weekday column for same_dow.
    # Primary table: one row per statId × charger_type (no dow), plus same_dow columns Mon..Sun optional.
    for dow in range(7):
        col = f"same_dow_{dow}_avg_sessions"
        sub = same_dow[same_dow["dow"] == dow][["statId", "charger_type", "same_dow_avg_sessions"]]
        sub = sub.rename(columns={"same_dow_avg_sessions": col})
        feat = feat.merge(sub, on=["statId", "charger_type"], how="left")

    feat["n_chargers"] = feat["n_chargers"].fillna(1).clip(lower=1)
    feat["sessions_per_charger"] = feat["avg_sessions_all"] / feat["n_chargers"]
    feat["sessions_per_charger_28d"] = feat["avg_sessions_28d"] / feat["n_chargers"]
    feat["kwh_per_session"] = feat["avg_kwh_all"] / feat["avg_sessions_all"].replace(0, pd.NA)

    # usage_level tertiles within charger_type (by sessions_per_charger)
    def _level(s: pd.Series) -> pd.Series:
        try:
            return pd.qcut(s.rank(method="first"), 3, labels=["적음", "보통", "많음"])
        except ValueError:
            return pd.Series(["보통"] * len(s), index=s.index)

    feat["usage_level"] = (
        feat.groupby("charger_type", group_keys=False)["sessions_per_charger"].transform(_level).astype(str)
    )
    feat["usage_percentile"] = feat.groupby("charger_type")["sessions_per_charger"].rank(pct=True)
    feat["history_observed"] = True
    feat["history_source"] = "daegu_city_usage_daily"
    feat["match_radius_m"] = RADIUS_M

    # station-level ALL type rollup (optional second grain)
    # Keep charger_type rows only as specified.

    cols = [
        "statId",
        "statNm",
        "charger_type",
        "n_chargers",
        "n_days",
        "avg_sessions_all",
        "weekday_avg_sessions",
        "weekend_avg_sessions",
        "avg_sessions_7d",
        "avg_sessions_28d",
        "avg_kwh_28d",
        "sessions_per_charger",
        "sessions_per_charger_28d",
        "kwh_per_session",
        "usage_percentile",
        "usage_level",
        "history_observed",
        "history_source",
        "match_radius_m",
    ] + [f"same_dow_{d}_avg_sessions" for d in range(7)]
    return feat[[c for c in cols if c in feat.columns]].sort_values(["charger_type", "sessions_per_charger"], ascending=[True, False])


def main() -> int:
    usage_path = find_usage_csv()
    usage = load_usage(usage_path)
    stations = load_stations()
    join_map = join_usage_stations(usage, stations, RADIUS_M)

    OUT_JOIN.mkdir(parents=True, exist_ok=True)
    OUT_FEAT.mkdir(parents=True, exist_ok=True)

    join_csv = OUT_JOIN / "join_usage_history_statId.csv"
    join_map.to_csv(join_csv, index=False, encoding="utf-8-sig")

    matched_n = int(join_map["matched"].sum())
    join_meta = {
        "layer": "usage_history_statId",
        "radius_m": RADIUS_M,
        "usage_file": str(usage_path.relative_to(REPO)).replace("\\", "/"),
        "usage_rows": int(len(usage)),
        "usage_stations": int(join_map.shape[0]),
        "evcharger_stations": int(len(stations)),
        "matched": matched_n,
        "match_rate": round(matched_n / len(join_map), 4) if len(join_map) else 0,
        "date_min": str(usage["date"].min().date()),
        "date_max": str(usage["date"].max().date()),
        "output": str(join_csv.relative_to(REPO)).replace("\\", "/"),
        "note": "municipal station_id ≠ EvCharger statId; matched by coordinates",
    }
    (OUT_JOIN / "join_usage_history_meta.json").write_text(
        json.dumps(join_meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    feat = build_features(usage, join_map)
    feat_csv = OUT_FEAT / "station_history_features_latest.csv"
    feat.to_csv(feat_csv, index=False, encoding="utf-8-sig")

    feat_meta = {
        **join_meta,
        "feature_rows": int(len(feat)),
        "feature_file": str(feat_csv.relative_to(REPO)).replace("\\", "/"),
        "usage_level": "tertile of sessions_per_charger within charger_type",
        "d1_merged": False,
        "owner": "AI·data ①",
        "consumer": "AI·data ② (optional prior for stale/unobserved)",
    }
    (OUT_FEAT / "station_history_features_meta.json").write_text(
        json.dumps(feat_meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(json.dumps(feat_meta, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
