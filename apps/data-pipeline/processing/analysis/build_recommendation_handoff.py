"""Export DA① recommendation-ready static inputs and refresh policy.

Request-time values (SOC, vehicle, TMAP ETA, route distance) intentionally
remain null. The backend must bind them for every recommendation request.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

_PROCESSING = Path(__file__).resolve().parents[1]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))

from _bootstrap import ensure_paths

REPO = ensure_paths()
DEFAULT_D1 = (
    REPO
    / "apps"
    / "data-pipeline"
    / "evaluation"
    / "results"
    / "datasets"
    / "station_feature_snapshot_latest.csv"
)


def truth(series: pd.Series) -> pd.Series:
    return series.astype(str).str.lower().isin({"true", "1", "yes"})


def freshness_flag(status_age_minutes: float | None) -> str:
    if status_age_minutes is None or pd.isna(status_age_minutes):
        return "UNOBSERVED"
    if status_age_minutes <= 5:
        return "FRESH"
    if status_age_minutes <= 15:
        return "AGING"
    return "CHECK_REQUIRED"


def build_quality_flags(row: pd.Series) -> str:
    flags = [freshness_flag(row["status_age_minutes"])]
    if float(row.get("observed_count", 0) or 0) <= 0:
        flags.append("UNOBSERVED")
    if not bool(row["coord_ok_bool"]):
        flags.append("COORDINATE_EXCLUDED")
    if not bool(row["public_bool"]):
        flags.append("ACCESS_RESTRICTED")
    if bool(row.get("status_missing_bool", False)):
        flags.append("STATUS_MISSING")
    return "|".join(dict.fromkeys(flags))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--d1", type=Path, default=DEFAULT_D1)
    args = parser.parse_args()
    d1_path = args.d1 if args.d1.is_absolute() else REPO / args.d1
    if not d1_path.exists():
        raise FileNotFoundError(f"missing D1: {d1_path}")

    d1 = pd.read_csv(d1_path, low_memory=False)
    required = {
        "statId",
        "as_of_ts",
        "lat",
        "lng",
        "coord_ok",
        "total_chargers",
        "available_count",
        "observed_count",
        "has_confirmed_available",
        "status_age_minutes",
        "observation_age_minutes",
        "recommend_public_default",
        "is_operating_now",
    }
    missing = required - set(d1.columns)
    if missing:
        raise ValueError(f"D1 missing columns: {sorted(missing)}")

    numeric = [
        "lat",
        "lng",
        "total_chargers",
        "available_count",
        "observed_count",
        "status_age_minutes",
        "observation_age_minutes",
    ]
    for column in numeric:
        d1[column] = pd.to_numeric(d1[column], errors="coerce")

    d1["coord_ok_bool"] = truth(d1["coord_ok"])
    d1["public_bool"] = truth(d1["recommend_public_default"])
    d1["confirmed_available_bool"] = truth(d1["has_confirmed_available"])
    d1["status_missing_bool"] = d1["observed_count"].fillna(0).le(0)
    as_of = pd.to_datetime(d1["as_of_ts"], errors="coerce", utc=True)
    d1["status_updated_at"] = as_of - pd.to_timedelta(
        d1["status_age_minutes"],
        unit="m",
    )
    d1["status_observed_at"] = as_of - pd.to_timedelta(
        d1["observation_age_minutes"],
        unit="m",
    )
    d1["observation_coverage"] = (
        d1["observed_count"] / d1["total_chargers"].replace(0, pd.NA)
    )
    d1["freshness_flag"] = d1["status_age_minutes"].map(freshness_flag)
    d1["data_quality_flags"] = d1.apply(build_quality_flags, axis=1)
    d1["recheck_required"] = (
        d1["freshness_flag"].isin({"CHECK_REQUIRED", "UNOBSERVED"})
        | d1["available_count"].fillna(0).le(1)
    )
    d1["static_candidate_ready"] = (
        d1["coord_ok_bool"]
        & d1["public_bool"]
        & d1["is_operating_now"].fillna("UNKNOWN").ne("N")
        & d1["observed_count"].fillna(0).gt(0)
    )
    d1["availability_guaranteed"] = False

    # Request-time fields are deliberately unbound in the DA① export.
    for column in [
        "request_vehicle_model",
        "request_current_soc_percent",
        "request_eta_minutes",
        "request_route_distance_km",
        "arrival_soc_percent",
        "soc_risk_level",
    ]:
        d1[column] = pd.NA

    columns = [
        "statId",
        "statNm",
        "as_of_ts",
        "status_updated_at",
        "status_observed_at",
        "status_age_minutes",
        "observation_age_minutes",
        "freshness_flag",
        "lat",
        "lng",
        "total_chargers",
        "available_count",
        "observed_count",
        "observation_coverage",
        "confirmed_available_bool",
        "static_candidate_ready",
        "recheck_required",
        "availability_guaranteed",
        "data_quality_flags",
        "request_vehicle_model",
        "request_current_soc_percent",
        "request_eta_minutes",
        "request_route_distance_km",
        "arrival_soc_percent",
        "soc_risk_level",
        "is_operating_now",
        "schema_version",
    ]
    columns = [column for column in columns if column in d1.columns]
    export = d1[columns].copy()
    export = export.rename(
        columns={
            "statId": "station_id",
            "statNm": "station_name",
            "as_of_ts": "as_of",
            "confirmed_available_bool": "observed_available",
        }
    )

    latest_as_of = pd.to_datetime(d1["as_of_ts"], errors="coerce").max()
    day = latest_as_of.strftime("%Y%m%d") if pd.notna(latest_as_of) else "unknown"
    out = (
        REPO
        / "docs"
        / "data"
        / "analysis"
        / f"recommendation_handoff_{day}"
    )
    out.mkdir(parents=True, exist_ok=True)
    export.to_csv(
        out / "recommendation_input_snapshot.csv",
        index=False,
        encoding="utf-8-sig",
    )
    try:
        export.to_parquet(
            out / "recommendation_input_snapshot.parquet",
            index=False,
        )
    except Exception:
        pass

    policy = {
        "version": "recommendation_refresh_policy_v1_proposed",
        "status": "PROPOSED_PENDING_DA2_BACKEND_APPROVAL",
        "source": "DA① data handoff",
        "principles": [
            "Never claim availability_guaranteed=true without a reservation/lock API.",
            "Use cached AWS loop data; do not trigger public API calls per client refresh.",
            "Bind vehicle SOC and TMAP route values at request time.",
        ],
        "triggers": [
            {
                "code": "PRIMARY_NO_LONGER_AVAILABLE",
                "condition": "available_count <= 0",
                "action": "IMMEDIATE_RERANK",
            },
            {
                "code": "PRIMARY_SINGLE_CHARGER_LEFT",
                "condition": "available_count == 1",
                "action": "RECHECK_AND_PREPARE_FALLBACK",
            },
            {
                "code": "STATUS_STALE",
                "condition": "status_age_minutes > 15 or status missing",
                "action": "RECHECK_REQUIRED",
            },
            {
                "code": "SOC_DANGER",
                "condition": "arrival_soc_percent <= 10",
                "action": "HARD_FILTER_AND_RERANK",
            },
            {
                "code": "SOC_WARNING",
                "condition": "10 < arrival_soc_percent <= 15",
                "action": "PREFER_NEARER_MULTI_CHARGER_FALLBACK",
            },
            {
                "code": "ETA_DRIFT",
                "condition": "abs(new_eta_minutes - old_eta_minutes) >= 5",
                "action": "RECOMPUTE_SOC_AND_RERANK",
            },
            {
                "code": "NEW_AWS_SNAPSHOT",
                "condition": "source snapshotId changes during navigation",
                "action": "COMPARE_PRIMARY_AND_RERANK_IF_TRIGGERED",
            },
        ],
        "backend_flow": [
            "bind request vehicle/current SOC/current location",
            "fetch TMAP ETA and route distance for shortlist",
            "compute arrival SOC",
            "apply hard filters",
            "rank in DA② recommendation core",
            "return primary plus fallback candidates",
            "on new cached snapshot or ETA drift, evaluate triggers",
        ],
    }
    (out / "recommendation_refresh_policy_v1.json").write_text(
        json.dumps(policy, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    summary = {
        "generated_from_d1_as_of": (
            latest_as_of.isoformat() if pd.notna(latest_as_of) else None
        ),
        "rows": int(len(export)),
        "static_candidate_ready": int(d1["static_candidate_ready"].sum()),
        "observed_available": int(d1["confirmed_available_bool"].sum()),
        "recheck_required": int(d1["recheck_required"].sum()),
        "freshness_counts": {
            str(key): int(value)
            for key, value in d1["freshness_flag"].value_counts().items()
        },
        "request_time_fields_unbound": [
            "request_vehicle_model",
            "request_current_soc_percent",
            "request_eta_minutes",
            "request_route_distance_km",
            "arrival_soc_percent",
            "soc_risk_level",
        ],
        "contract_status": "PROPOSED_PENDING_DA2_BACKEND_APPROVAL",
        "files": {
            "snapshot": "recommendation_input_snapshot.csv",
            "policy": "recommendation_refresh_policy_v1.json",
        },
    }
    (out / "recommendation_handoff_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"OUT {out.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
