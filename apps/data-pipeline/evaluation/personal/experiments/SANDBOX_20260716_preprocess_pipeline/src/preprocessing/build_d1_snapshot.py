"""Build D1 station_feature_snapshot (docs/data/스키마/데이터셋_명세.md).

Inputs:
  - charger_master (station/charger inventory + useTime/coords)
  - status SANDBOX snapshots → latest per charger with statUpdDt ≤ as_of_ts
  - spatial_join CSVs

Output: evaluation/results/datasets/station_feature_snapshot_*.parquet|csv
        + station_feature_snapshot_latest.* + handoff sample

Does not compute scores or train models.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO = Path(__file__).resolve().parents[8]
PROCESSING = REPO / "apps" / "data-pipeline" / "processing"
_DATA_PIPELINE = REPO / "apps" / "data-pipeline"
sys.path.insert(0, str(PROCESSING))
sys.path.insert(0, str(_DATA_PIPELINE))

from loop_paths import iter_status_csvs, status_snapshots_dir  # noqa: E402

from features.station_features import (  # noqa: E402
    aggregate_availability_features,
    aggregate_reliability_combined,
    observation_state,
    series_operating_now,
)
from features.status_as_of import join_master_with_status, load_latest_status_as_of  # noqa: E402

KST = ZoneInfo("Asia/Seoul")
SCHEMA_VERSION = "station_feature_v1"

SANDBOX = (
    REPO
    / "apps/data-pipeline/evaluation/personal/experiments"
    / "SANDBOX_20260716_preprocess_pipeline"
)
MASTER = SANDBOX / "data" / "processed" / "charger_master.csv"
STATUS_SNAP_DIR = status_snapshots_dir()
_SNAP_STAMP = re.compile(r"_(\d{8})_(\d{6})")


def latest_status_snapshot_as_of(snap_dir: Path | None = None) -> datetime | None:
    """Wall time of the newest status CSV filename (…_YYYYMMDD_HHMMSS.csv)."""
    directory = snap_dir or STATUS_SNAP_DIR
    files = iter_status_csvs(directory)
    if not files:
        return None
    best: datetime | None = None
    for fp in files:
        m = _SNAP_STAMP.search(fp.name)
        if not m:
            continue
        try:
            ts = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S").replace(
                tzinfo=KST
            )
        except ValueError:
            continue
        if best is None or ts > best:
            best = ts
    return best


def resolve_as_of(mode: str = "latest-snap") -> datetime:
    """Default latest-snap so observation_state reflects collection freshness, not rebuild lag.

    - latest-snap: newest status snapshot stamp (offline handoff / after Lightsail pull)
    - now: wall clock (live serving style; may be STALE if pull is old)
    """
    if mode == "now":
        return datetime.now(KST)
    snap_ts = latest_status_snapshot_as_of()
    if snap_ts is None:
        print("WARN: no status snapshots — falling back to now()", file=sys.stderr)
        return datetime.now(KST)
    return snap_ts
SPATIAL = REPO / "docs" / "data" / "spatial_join"
OUT_DIR = REPO / "apps" / "data-pipeline" / "evaluation" / "results" / "datasets"
HANDOFF_DIR = OUT_DIR / "handoff_to_model"


def _load_nearest(path: Path, value_col: str = "distance_m") -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=["statId", value_col])
    df = pd.read_csv(path, dtype=str)
    df["matched"] = df.get("matched", "False").astype(str).str.lower().isin(["true", "1"])
    df[value_col] = pd.to_numeric(df.get(value_col), errors="coerce")
    ok = df[df["matched"]].copy()
    return ok[["statId", value_col]].drop_duplicates(subset=["statId"])


def _poi_count_1km() -> pd.DataFrame:
    frames = []
    for name in ("join_tour_api_1000m.csv", "join_walk_parks_1000m.csv"):
        p = SPATIAL / name
        if not p.exists():
            continue
        df = pd.read_csv(p, dtype=str)
        df["matched"] = df.get("matched", "False").astype(str).str.lower().isin(["true", "1"])
        frames.append(df.loc[df["matched"], ["statId"]])
    if not frames:
        return pd.DataFrame(columns=["statId", "poi_count_1km"])
    allm = pd.concat(frames, ignore_index=True)
    return allm.groupby("statId").size().rename("poi_count_1km").reset_index()


def _load_usage_history_station_features() -> pd.DataFrame:
    """Collapse charger_type rows → one row per statId (highest intensity)."""
    path = (
        REPO
        / "apps/data-pipeline/evaluation/results/datasets/station_history_features_latest.csv"
    )
    empty = pd.DataFrame(
        columns=[
            "statId",
            "usage_level",
            "sessions_per_charger",
            "usage_weekday_avg",
            "usage_weekend_avg",
            "usage_charger_type",
            "history_observed",
        ]
    )
    if not path.exists():
        return empty
    feat = pd.read_csv(path, dtype=str)
    if feat.empty or "statId" not in feat.columns:
        return empty
    feat["sessions_per_charger"] = pd.to_numeric(
        feat.get("sessions_per_charger"), errors="coerce"
    )
    feat["usage_weekday_avg"] = pd.to_numeric(
        feat.get("weekday_avg_sessions"), errors="coerce"
    )
    feat["usage_weekend_avg"] = pd.to_numeric(
        feat.get("weekend_avg_sessions"), errors="coerce"
    )
    feat = feat.sort_values("sessions_per_charger", ascending=False, na_position="last")
    feat = feat.drop_duplicates(subset=["statId"], keep="first")
    out = feat.rename(columns={"charger_type": "usage_charger_type"})[
        [
            "statId",
            "usage_level",
            "sessions_per_charger",
            "usage_weekday_avg",
            "usage_weekend_avg",
            "usage_charger_type",
        ]
    ].copy()
    out["history_observed"] = True
    return out


def build_snapshot(as_of_ts: datetime | None = None) -> tuple[pd.DataFrame, dict]:
    as_of = as_of_ts or datetime.now(KST)
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=KST)
    else:
        as_of = as_of.astimezone(KST)

    master = pd.read_csv(MASTER, dtype=str, low_memory=False)
    if "pk" not in master.columns:
        master["pk"] = master["statId"].astype(str) + "|" + master["chgerId"].astype(str)

    status = load_latest_status_as_of(STATUS_SNAP_DIR, as_of)
    raw = join_master_with_status(master, status)

    avail = aggregate_availability_features(raw)
    reli = aggregate_reliability_combined(raw)

    meta_cols = [
        c
        for c in [
            "statId",
            "statNm",
            "addr",
            "lat_num",
            "lng_num",
            "lat",
            "lng",
            "coordinate_quality_flag",
            "useTime",
            "limitYn",
        ]
        if c in raw.columns
    ]
    meta = raw[meta_cols].drop_duplicates(subset=["statId"], keep="first")
    lat = pd.to_numeric(meta.get("lat_num", meta.get("lat")), errors="coerce")
    lng = pd.to_numeric(meta.get("lng_num", meta.get("lng")), errors="coerce")
    meta = meta.assign(lat=lat, lng=lng)
    meta["coord_ok"] = meta.get("coordinate_quality_flag", "OK") == "OK"

    # Access: station restricted if ANY charger has limitYn=Y (EvCharger).
    # Name heuristic is advisory only — do not hard-delete on name alone.
    if "limitYn" in master.columns:
        lim_any = (
            master.assign(_lim=master["limitYn"].astype(str).str.upper().eq("Y"))
            .groupby("statId")["_lim"]
            .any()
        )
        meta = meta.merge(lim_any.rename("access_restricted"), on="statId", how="left")
        meta["access_restricted"] = meta["access_restricted"].fillna(False)
    else:
        meta["access_restricted"] = False
    name_blob = (
        meta.get("statNm", pd.Series("", index=meta.index)).fillna("").astype(str)
        + " "
        + meta.get("addr", pd.Series("", index=meta.index)).fillna("").astype(str)
    )
    meta["name_suggests_residential"] = name_blob.str.contains(
        r"아파트|단지|\bAPT\b|거주자", case=False, na=False, regex=True
    )
    meta["limitYn"] = meta.get("limitYn", pd.Series("N", index=meta.index)).fillna("N")
    # Default public recommend pool: not access-restricted (limitYn-driven)
    meta["recommend_public_default"] = ~meta["access_restricted"].astype(bool)

    if "useTime" in meta.columns:
        meta["is_operating_now"] = series_operating_now(meta["useTime"], as_of)
    else:
        meta["is_operating_now"] = "UNKNOWN"

    # Parking: team_5 PIS real join (mock removed 2026-07-23).
    park_join = SPATIAL / "join_parking_team5_1000m.csv"
    if park_join.exists():
        parking = pd.read_csv(park_join, dtype=str, low_memory=False)
        rename = {
            "distance_m": "nearest_parking_m",
            "remaining_spaces": "parking_remaining_spaces",
            "total_spaces": "parking_total_spaces",
            "occupancy_rate": "parking_occupancy_rate",
            "congestion_status": "parking_congestion_status",
            "matched_id": "parking_matched_id",
            "has_realtime": "parking_has_realtime",
        }
        keep = ["statId"] + [c for c in rename if c in parking.columns]
        parking = parking[keep].rename(columns=rename)
        parking["nearest_parking_m"] = pd.to_numeric(
            parking["nearest_parking_m"], errors="coerce"
        )
        for c in (
            "parking_remaining_spaces",
            "parking_total_spaces",
            "parking_occupancy_rate",
        ):
            if c in parking.columns:
                parking[c] = pd.to_numeric(parking[c], errors="coerce")
        if "parking_has_realtime" in parking.columns:
            parking["parking_has_realtime"] = (
                parking["parking_has_realtime"]
                .astype(str)
                .str.lower()
                .isin(("1", "true", "yes"))
            )
        parking_source = "team5_pis"
        parking_is_mock = False
    else:
        parking = pd.DataFrame(columns=["statId", "nearest_parking_m"])
        parking_source = "none"
        parking_is_mock = False  # mock files deleted — do not claim mock
        print(
            "WARN: join_parking_team5_1000m.csv missing — nearest_parking_m null",
            file=sys.stderr,
        )

    utic_join = SPATIAL / "join_traffic_incident_utic_1000m.csv"
    if utic_join.exists():
        incident = _load_nearest(utic_join).rename(
            columns={"distance_m": "nearest_incident_m"}
        )
        traffic_is_mock = False
        traffic_source = "utic"
    else:
        # No mock fallback — fake incident distances are stripped from D1.
        incident = pd.DataFrame(columns=["statId", "nearest_incident_m"])
        traffic_is_mock = True
        traffic_source = "none"
        print(
            "WARN: join_traffic_incident_utic_1000m.csv missing — "
            "nearest_incident_m null (mock traffic join not used)",
            file=sys.stderr,
        )
    poi = _poi_count_1km()

    # Past usage intensity (Daegu municipal history) — station grain, optional.
    # Does not override realtime availability. Scoring weight = DA➁ agreement.
    usage_feat = _load_usage_history_station_features()

    # Parking short-horizon volatility (Team5 history) — additive, optional.
    park_1h_path = SPATIAL / "parking_realtime_1h_features.csv"
    if park_1h_path.exists():
        park_1h = pd.read_csv(park_1h_path, dtype=str, low_memory=False)
        for c in (
            "parking_remaining_std_1h",
            "parking_remaining_delta_1h",
            "parking_realtime_ticks_1h",
        ):
            if c in park_1h.columns:
                park_1h[c] = pd.to_numeric(park_1h[c], errors="coerce")
        keep_1h = ["statId"] + [
            c
            for c in (
                "parking_remaining_std_1h",
                "parking_remaining_delta_1h",
                "parking_realtime_ticks_1h",
            )
            if c in park_1h.columns
        ]
        park_1h = park_1h[keep_1h].drop_duplicates("statId")
    else:
        park_1h = pd.DataFrame(columns=["statId"])

    # Nearest linkspeed (TMAP node-midpoint interim geom) — additive, not ETA.
    link_join_path = SPATIAL / "join_linkspeed_nearest.csv"
    if link_join_path.exists():
        link_feat = pd.read_csv(link_join_path, dtype=str, low_memory=False)
        for c in ("nearest_link_m", "link_speed_kph", "link_cong_grade"):
            if c in link_feat.columns:
                link_feat[c] = pd.to_numeric(link_feat[c], errors="coerce")
        keep_link = ["statId"] + [
            c
            for c in (
                "nearest_link_id",
                "nearest_link_m",
                "link_speed_kph",
                "link_cong_grade",
                "link_cong_grade_nm",
            )
            if c in link_feat.columns
        ]
        link_feat = link_feat[keep_link].drop_duplicates("statId")
    else:
        link_feat = pd.DataFrame(columns=["statId"])

    out = (
        meta[
            [
                "statId",
                "statNm",
                "addr",
                "lat",
                "lng",
                "coord_ok",
                "is_operating_now",
                "limitYn",
                "access_restricted",
                "name_suggests_residential",
                "recommend_public_default",
            ]
        ]
        .merge(avail, on="statId", how="left")
        .merge(reli, on="statId", how="left")
        .merge(parking, on="statId", how="left")
        .merge(park_1h, on="statId", how="left")
        .merge(incident, on="statId", how="left")
        .merge(link_feat, on="statId", how="left")
        .merge(poi, on="statId", how="left")
        .merge(usage_feat, on="statId", how="left")
    )
    out["poi_count_1km"] = out["poi_count_1km"].fillna(0).astype(int)
    if "history_observed" in out.columns:
        out["history_observed"] = out["history_observed"].fillna(False).astype(bool)
    else:
        out["history_observed"] = False
    out["parking_is_mock"] = parking_is_mock
    out["parking_source"] = parking_source
    out["traffic_is_mock"] = traffic_is_mock
    out["traffic_source"] = traffic_source
    out["eta_minutes"] = pd.NA
    out["as_of_ts"] = as_of.isoformat()
    out["source_status"] = "sandbox_series"
    out["schema_version"] = SCHEMA_VERSION
    out["observation_state"] = observation_state(
        out.get("observed_count", pd.Series(0, index=out.index)),
        out.get(
            "reliability_grade_effective",
            pd.Series("CHECK_REQUIRED", index=out.index),
        ),
    )

    ordered = [
        "statId",
        "as_of_ts",
        "statNm",
        "addr",
        "lat",
        "lng",
        "coord_ok",
        "total_chargers",
        "available_count",
        "observed_count",
        "unobserved_count",
        "availability_ratio_observed",
        "unobserved_rate",
        "has_confirmed_available",
        "status_age_minutes",
        "reliability_grade",
        "observation_age_minutes",
        "observation_grade",
        "reliability_grade_effective",
        "observation_state",
        "is_operating_now",
        "limitYn",
        "access_restricted",
        "name_suggests_residential",
        "recommend_public_default",
        "usage_level",
        "sessions_per_charger",
        "usage_weekday_avg",
        "usage_weekend_avg",
        "usage_charger_type",
        "history_observed",
        "eta_minutes",
        "poi_count_1km",
        "nearest_parking_m",
        "parking_remaining_spaces",
        "parking_total_spaces",
        "parking_occupancy_rate",
        "parking_congestion_status",
        "parking_matched_id",
        "parking_has_realtime",
        "parking_remaining_std_1h",
        "parking_remaining_delta_1h",
        "parking_realtime_ticks_1h",
        "parking_is_mock",
        "parking_source",
        "nearest_incident_m",
        "nearest_link_id",
        "nearest_link_m",
        "link_speed_kph",
        "link_cong_grade",
        "link_cong_grade_nm",
        "traffic_is_mock",
        "traffic_source",
        "source_status",
        "schema_version",
    ]
    for c in ordered:
        if c not in out.columns:
            out[c] = pd.NA

    build_meta = {
        "as_of_ts": as_of.isoformat(),
        "master_chargers": int(len(master)),
        "status_chargers_as_of": int(len(status)),
        "status_snapshot_files": len(iter_status_csvs(STATUS_SNAP_DIR)),
        "stations": int(out["statId"].nunique()),
        "observed_chargers": int(raw["status_missing"].eq(False).sum()) if len(raw) else 0,
        "parking_is_mock": parking_is_mock,
        "parking_source": parking_source,
        "nearest_parking_policy": "team5_pis 1km join; unmatched null (no mock fill)",
        "parking_matched_stations": int(out["nearest_parking_m"].notna().sum()),
        "parking_with_realtime_stations": int(
            out["parking_has_realtime"].fillna(False).astype(bool).sum()
        )
        if "parking_has_realtime" in out.columns
        else 0,
        "parking_1h_feature_stations": int(
            out["parking_remaining_std_1h"].notna().sum()
        )
        if "parking_remaining_std_1h" in out.columns
        else 0,
        "traffic_is_mock": traffic_is_mock,
        "traffic_source": traffic_source,
        "incident_matched_stations": int(out["nearest_incident_m"].notna().sum()),
        "linkspeed_matched_stations": int(out["nearest_link_id"].notna().sum())
        if "nearest_link_id" in out.columns
        else 0,
        "linkspeed_join_policy": "MOCT_LINK SHP midpoint ≤400m (fallback TMAP nodes); not route ETA",
        "access_restricted_stations": int(out["access_restricted"].astype(bool).sum()),
        "recommend_public_default_stations": int(
            out["recommend_public_default"].astype(bool).sum()
        ),
        "name_suggests_residential_stations": int(
            out["name_suggests_residential"].astype(bool).sum()
        ),
        "history_observed_stations": int(out["history_observed"].astype(bool).sum()),
        "usage_level_attached": True,
        "observation_state_counts": out["observation_state"].value_counts(dropna=False).to_dict(),
    }
    return out[ordered], build_meta


def main() -> int:
    parser = argparse.ArgumentParser(description="Build D1 station_feature_snapshot")
    parser.add_argument(
        "--as-of",
        choices=("latest-snap", "now"),
        default="latest-snap",
        help="latest-snap=최신 status 파일 시각(기본). now=현재시각(라이브).",
    )
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    HANDOFF_DIR.mkdir(parents=True, exist_ok=True)

    as_of = resolve_as_of(args.as_of)
    print(f"D1 as_of mode={args.as_of} -> {as_of.isoformat()}", flush=True)
    snap, build_meta = build_snapshot(as_of_ts=as_of)
    build_meta["as_of_mode"] = args.as_of
    stamp = datetime.now(KST).strftime("%Y%m%d_%H%M%S")
    base = f"station_feature_snapshot_{stamp}"
    csv_path = OUT_DIR / f"{base}.csv"
    latest_csv = OUT_DIR / "station_feature_snapshot_latest.csv"
    snap.to_csv(csv_path, index=False, encoding="utf-8-sig")
    snap.to_csv(latest_csv, index=False, encoding="utf-8-sig")

    parquet_path = OUT_DIR / f"{base}.parquet"
    latest_pq = OUT_DIR / "station_feature_snapshot_latest.parquet"
    try:
        snap.to_parquet(parquet_path, index=False)
        snap.to_parquet(latest_pq, index=False)
        pq = str(parquet_path.relative_to(REPO)).replace("\\", "/")
        pq_latest = str(latest_pq.relative_to(REPO)).replace("\\", "/")
    except Exception as exc:  # noqa: BLE001
        pq = f"(parquet skipped: {exc})"
        pq_latest = pq

    sample = snap.head(30)
    sample_path = HANDOFF_DIR / "station_feature_snapshot_sample_30.csv"
    sample.to_csv(sample_path, index=False, encoding="utf-8-sig")

    meta = {
        "schema_version": SCHEMA_VERSION,
        "dataset": "D1_station_feature_snapshot",
        "row_unit": "statId",
        "as_of_ts": snap["as_of_ts"].iloc[0] if len(snap) else None,
        "rows": int(len(snap)),
        "coord_ok_rows": int(snap["coord_ok"].sum()),
        "has_confirmed_available_rows": int(
            snap["has_confirmed_available"].fillna(False).sum()
        ),
        "observed_ratio_mean": float(
            pd.to_numeric(1 - snap["unobserved_rate"], errors="coerce").mean()
        ),
        "status_refresh": build_meta,
        "parking_is_mock": build_meta.get("parking_is_mock", False),
        "parking_source": build_meta.get("parking_source", "none"),
        "nearest_parking_policy": build_meta.get("nearest_parking_policy"),
        "parking_matched_stations": build_meta.get("parking_matched_stations"),
        "parking_with_realtime_stations": build_meta.get(
            "parking_with_realtime_stations"
        ),
        "traffic_is_mock": build_meta.get("traffic_is_mock", True),
        "traffic_source": build_meta.get("traffic_source", "none"),
        "incident_matched_stations": build_meta.get("incident_matched_stations"),
        "access_restricted_stations": build_meta.get("access_restricted_stations"),
        "recommend_public_default_stations": build_meta.get(
            "recommend_public_default_stations"
        ),
        "name_suggests_residential_stations": build_meta.get(
            "name_suggests_residential_stations"
        ),
        "access_policy": "access_restricted=any limitYn=Y; recommend_public_default=~restricted; name heuristic advisory only",
        "eta_minutes": "null — filled by backend/TMAP (AI·data ② / API)",
        "unobserved_policy": "unobserved ≠ unavailable; availability_ratio_observed null if observed_count=0",
        "status_policy": "per charger: newest statUpdDt ≤ as_of_ts; observation_age from last_seen_at (max fetchedAt/snapshotId)",
        "spec": "docs/data/스키마/데이터셋_명세.md",
        "features": "docs/data/스키마/피처_카탈로그.md",
        "files": {
            "full_csv": str(csv_path.relative_to(REPO)).replace("\\", "/"),
            "full_parquet": pq,
            "latest_csv": str(latest_csv.relative_to(REPO)).replace("\\", "/"),
            "latest_parquet": pq_latest,
            "sample_csv": str(sample_path.relative_to(REPO)).replace("\\", "/"),
        },
        "owner": "AI·data ①",
        "consumer": "AI·data ②",
    }
    (HANDOFF_DIR / "HANDOFF_META.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )

    (HANDOFF_DIR / "README.md").write_text(
        f"""# ① → ② 핸드오프 패키지

| 항목 | 내용 |
|---|---|
| **제공** | AI·데이터 ① |
| **수신** | AI·데이터 ② (모델·평가·서빙) |
| **스키마** | `{SCHEMA_VERSION}` |
| **명세** | `docs/data/스키마/데이터셋_명세.md` · `피처_카탈로그.md` |
| **status** | SANDBOX 시계열 as-of 갱신 (`source_status=sandbox_series`) |

## 포함 파일

- `station_feature_snapshot_sample_30.csv` — 샘플 30행
- `HANDOFF_META.json` — 행수·정책·경로
- 전체: `{csv_path.name}`
- 항상 최신 포인터: `station_feature_snapshot_latest.csv`

## 반드시 읽을 정책

1. **미관측 ≠ 사용 불가** — `unobserved_rate`, `availability_ratio_observed`(관측 0이면 null)
2. **mock / 소스 플래그** — `parking_is_mock=false` · `parking_source=team5_pis` (1km 조인; 미매칭 null) · `traffic_is_mock`/`traffic_source` (UTIC면 `utic`)
3. **`eta_minutes`** — ①은 null 예약, TMAP/백엔드 채움
4. **점수·위험도·추천 이유** — ② 영역 (이 테이블에 없음)
5. **status** — 충전기별 `statUpdDt ≤ as_of_ts` 최신 관측 + `observation_age`/`reliability_grade_effective` (이중 신선도)
6. **가짜 거리 금지** — parking mock 폐기; team5 실조인만 D1에 반영

생성 시각: {meta["as_of_ts"]}
관측 충전기: {build_meta.get("status_chargers_as_of")} / 마스터 {build_meta.get("master_chargers")}
""",
        encoding="utf-8",
    )

    print(json.dumps(meta, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
