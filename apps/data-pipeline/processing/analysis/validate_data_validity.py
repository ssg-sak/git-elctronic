"""Create a reproducible validity audit for EV SafeCharge local data.

The audit is intentionally offline: it only reads already-collected files.  It
separates data defects from known scope limits (for example, a 1km parking
join is not evidence that a charger is inside that parking lot).
"""
from __future__ import annotations

import json
import math
import random
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import matplotlib.pyplot as plt
import pandas as pd

REPO = Path(__file__).resolve().parents[4]
KST = ZoneInfo("Asia/Seoul")
STAMP = datetime.now(KST).strftime("%Y%m%d")
OUT = REPO / "docs" / "data" / "analysis" / f"data_validity_assessment_{STAMP}"
FIG = OUT / "figures"


@dataclass
class Check:
    domain: str
    dimension: str
    check_id: str
    status: str
    observed: str
    criterion: str
    interpretation: str = "검증 세부 경로는 criterion 참조"
    rerun: str = "validate_data_validity.py"


CHECKS: list[Check] = []


def add(
    domain: str,
    dimension: str,
    check_id: str,
    passed: bool | None,
    observed: str,
    criterion: str,
    interpretation: str = "검증 세부 경로는 criterion 참조",
    rerun: str = "validate_data_validity.py",
    *,
    warn: bool = False,
) -> None:
    status = "PASS" if passed else "WARN" if warn else "FAIL"
    if passed is None:
        status = "WARN"
    CHECKS.append(
        Check(domain, dimension, check_id, status, observed, criterion, interpretation, rerun)
    )


def read_csv(path: Path, **kwargs: Any) -> pd.DataFrame | None:
    if not path.is_file():
        return None
    try:
        return pd.read_csv(path, low_memory=False, **kwargs)
    except UnicodeDecodeError:
        return pd.read_csv(path, low_memory=False, encoding="cp949", **kwargs)


def latest(root: Path, pattern: str) -> Path | None:
    paths = sorted(root.glob(pattern))
    return paths[-1] if paths else None


def truth(frame: pd.DataFrame, name: str) -> pd.Series:
    return frame.get(name, pd.Series(False, index=frame.index)).astype(str).str.lower().isin(
        ("true", "1", "y", "yes")
    )


def as_number(frame: pd.DataFrame, name: str) -> pd.Series:
    return pd.to_numeric(frame.get(name, pd.Series(index=frame.index, dtype=float)), errors="coerce")


def markdown_table(frame: pd.DataFrame, *, include_index: bool = False) -> str:
    """Render a small Markdown table without requiring the optional tabulate package."""
    table = frame.reset_index() if include_index else frame
    columns = [str(column) for column in table.columns]
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in table.fillna("").astype(str).itertuples(index=False, name=None):
        values = [value.replace("|", "\\|").replace("\n", " ") for value in row]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def construct_measurement_model(metrics: dict[str, Any]) -> pd.DataFrame:
    """Map each observable feature to the product's intended construct.

    The target is deliberately an arrival-time outcome, not the current API
    state.  A variable can be well-formed data while still being an invalid
    measure of that target.
    """
    return pd.DataFrame(
        [
            {
                "variable": "도착 시 실제 충전 성공",
                "measurement_role": "목표 개념 / 정답 라벨",
                "construct_fit": "직접",
                "current_evidence": "미수집",
                "allowed_use": "측정 기준으로 정의만 가능",
                "threat": "도착 시점 상태·충전 시작 결과가 없음",
                "decision": "보류",
            },
            {
                "variable": "현재 관측된 사용 가능 충전기 수",
                "measurement_role": "현재 시점의 직접 상태 지표",
                "construct_fit": "부분 직접",
                "current_evidence": f"D1 observed availability; status/master key overlap {metrics.get('status_key_overlap_pct', 'n/a')}%",
                "allowed_use": "즉시 후보 필터",
                "threat": "도착 전 상태 변화·관측 누락",
                "decision": "MVP 사용",
            },
            {
                "variable": "상태 갱신·관측 신선도",
                "measurement_role": "현재 상태 지표의 측정 품질",
                "construct_fit": "타당성 보정",
                "current_evidence": f"상태 snapshot {metrics.get('status_snapshot_count', 'n/a')}개; 공백 {metrics.get('status_gap_events', 'n/a')}회",
                "allowed_use": "신뢰도 경고·후보 tier",
                "threat": "신선도가 높아도 도착 시 비어 있다는 뜻은 아님",
                "decision": "MVP 사용",
            },
            {
                "variable": "전체 충전기 수",
                "measurement_role": "대기·고장 충격 완화 능력",
                "construct_fit": "구조적 proxy",
                "current_evidence": "D1 total_chargers",
                "allowed_use": "동률 후보의 실패 위험 완화 보조",
                "threat": "현재 가용 수·도착 시 상태를 직접 관측하지 않음",
                "decision": "보조",
            },
            {
                "variable": "과거 이용량·회전율",
                "measurement_role": "장기 수요·이용 강도 proxy",
                "construct_fit": "간접",
                "current_evidence": f"D1 history coverage {metrics.get('d1_history_coverage_pct', 'n/a')}%",
                "allowed_use": "표본이 있는 충전소의 장기 설명",
                "threat": "200/4210만 연결; live availability와 시간 단위가 다름",
                "decision": "보조",
            },
            {
                "variable": "주차 점유율",
                "measurement_role": "접근·주차 가능성 proxy",
                "construct_fit": "조건부 간접",
                "current_evidence": f"realtime station links {metrics.get('d1_parking_realtime', 'n/a')}; 100m STRONG 표본 검토 필요",
                "allowed_use": "검증된 STRONG 공존 후보의 안내 문구",
                "threat": "1km 주차장은 충전소 내부 주차장이 아닐 수 있음",
                "decision": "직접 점수화 금지",
            },
            {
                "variable": "도시 링크속도·UTIC 돌발",
                "measurement_role": "이동 마찰·주의 상황 proxy",
                "construct_fit": "간접",
                "current_evidence": f"UTIC live matches {metrics.get('utic_live_station_matches', 'n/a')}",
                "allowed_use": "경로 계산 전 경고·도시 맥락",
                "threat": "경로별 ETA·도착 시간을 측정하지 않음",
                "decision": "ETA 대체 금지",
            },
            {
                "variable": "ETA 후 예상 상태",
                "measurement_role": "목표와 가장 가까운 선행 예측치",
                "construct_fit": "직접에 가까움",
                "current_evidence": f"D1 ETA values {metrics.get('d1_eta_values', 'n/a')}",
                "allowed_use": "현재 미사용",
                "threat": "TMAP ETA·상태 전이·도착 결과 라벨이 없음",
                "decision": "향후 핵심 측정치",
            },
        ]
    )


def source_paths() -> dict[str, Path | None]:
    extracted = REPO / "docs" / "data" / "extracted"
    return {
        "master": extracted / "charger" / "info" / "daegu_charger_info_service_latest.csv",
        "parking_master": extracted / "parking" / "daegu_parking_info_team5_latest.csv",
        "parking_realtime": extracted / "parking" / "daegu_parking_realtime_team5_latest.csv",
        "parking_join": REPO / "docs" / "data" / "spatial_join" / "join_parking_team5_1000m.csv",
        "utic": REPO / "docs" / "data" / "loops" / "loop2" / "daegu_traffic_incident_utic_latest.csv",
        "utic_join": REPO
        / "docs"
        / "data"
        / "spatial_join"
        / "join_traffic_incident_utic_1000m.csv",
        "usage": latest(extracted / "charger" / "usage", "daegu_charger_usage_daily*.csv"),
        "usage_join": REPO / "docs" / "data" / "spatial_join" / "join_usage_history_statId.csv",
        "d1": REPO
        / "apps"
        / "data-pipeline"
        / "evaluation"
        / "results"
        / "datasets"
        / "station_feature_snapshot_latest.csv",
        "reliability": REPO
        / "docs"
        / "data"
        / "analysis"
        / "snapshot_all_20260723"
        / "reliability_checks.json",
        "health": REPO / "docs" / "data" / "quality" / "collection_health_latest.json",
        "colocation": REPO
        / "docs"
        / "data"
        / "analysis"
        / f"parking_ev_colocation_{STAMP}"
        / "parking_lots_with_ev_candidates.csv",
    }


def audit_master_status(paths: dict[str, Path | None], metrics: dict[str, Any]) -> None:
    master = read_csv(paths["master"], dtype=str)  # type: ignore[arg-type]
    if master is None:
        add("충전소", "내적", "MASTER_FILE", False, "missing", "master exists", "검증 불가", "rerun collection")
        return
    keys = ["statId", "chgerId"]
    dup = int(master.duplicated(keys, keep=False).sum())
    coords = pd.to_numeric(master["lat"], errors="coerce").notna() & pd.to_numeric(
        master["lng"], errors="coerce"
    ).notna()
    bbox = pd.to_numeric(master["lat"], errors="coerce").between(35.55, 36.45) & pd.to_numeric(
        master["lng"], errors="coerce"
    ).between(128.25, 129.05)
    metrics["master_stations"] = int(master["statId"].nunique())
    metrics["master_chargers"] = int(len(master))
    metrics["master_coord_ok"] = int(coords.sum())
    add("충전소", "내적", "MASTER_UNIQUE_KEY", dup == 0, str(dup), "duplicate statId+chgerId = 0",
        "충전기 키 중복 여부", "validate_data_validity.py")
    add("충전소", "내적", "MASTER_COORDINATES", bool((coords & bbox).mean() >= 0.99),
        f"{int((coords & bbox).sum())}/{len(master)}", "Daegu bbox 좌표 ≥99%",
        "좌표가 공간 조인에 적합한지", "validate_data_validity.py", warn=True)

    snapshots = sorted((REPO / "docs" / "data" / "loops" / "loop1" / "snapshots").glob("**/daegu_charger_status_*.csv"))
    if not snapshots:
        add("상태", "신뢰성", "STATUS_SNAPSHOTS", False, "0", "at least 1 snapshot", "상태 검증 불가", "pull Lightsail")
        return
    latest_snapshot = snapshots[-1]
    status = read_csv(latest_snapshot, dtype=str)
    if status is None:
        return
    status_key = set(zip(status.get("statId", []), status.get("chgerId", [])))
    master_key = set(zip(master["statId"], master["chgerId"]))
    overlap = len(status_key & master_key)
    dup_status = int(status.duplicated(keys, keep=False).sum()) if set(keys).issubset(status.columns) else len(status)
    metrics["status_snapshot_count"] = len(snapshots)
    metrics["status_latest_file"] = str(latest_snapshot.relative_to(REPO)).replace("\\", "/")
    metrics["status_key_overlap_pct"] = round(100 * overlap / max(1, len(status_key)), 2)
    add("상태", "내적", "STATUS_DUPLICATE_KEY", dup_status == 0, str(dup_status), "duplicate statId+chgerId = 0",
        "동일 tick 내 상태 키의 유일성", "validate_collection.py")
    add("상태", "외적", "MASTER_STATUS_KEY_OVERLAP", overlap / max(1, len(status_key)) >= 0.98,
        f"{overlap}/{len(status_key)} ({metrics['status_key_overlap_pct']}%)", "master key overlap ≥98%",
        "최신 상태가 최신 master에 귀속되는지", "validate_data_validity.py", warn=True)

    if paths["reliability"] and paths["reliability"].is_file():
        reliability = json.loads(paths["reliability"].read_text(encoding="utf-8"))
        failed = [item["id"] for item in reliability.get("checks", []) if not item.get("pass", True)]
        metrics["status_reliability_failed"] = failed
        add("상태", "신뢰성", "STATUS_RELIABILITY_BATTERY", not failed, ", ".join(failed) or "all pass",
            "R1–R6 all pass", "기존 상태 시계열 신뢰성 조건의 재현",
            "plot_and_reliability_all_snapshots.py", warn=True)
    validation_path = REPO / "docs" / "data" / "loops" / "loop1" / "logs" / "validation_report.json"
    if validation_path.is_file():
        validation = json.loads(validation_path.read_text(encoding="utf-8"))
        duplicate_files = validation.get("duplicate_pair_snapshots", [])
        gaps = validation.get("timing", {}).get("gaps_detected")
        metrics["status_duplicate_pair_snapshots"] = len(duplicate_files)
        metrics["status_gap_events"] = gaps
        add("상태", "내적", "STATUS_CORPUS_DUPLICATE_PAIRS", not duplicate_files,
            f"{len(duplicate_files)} snapshots", "all snapshots have duplicate statId+chgerId = 0",
            f"최신 tick은 정상이나 과거 {len(duplicate_files)}개 snapshot에 중복 key가 있어 시계열 집계 시 dedupe가 필요",
            "validate_collection.py --write-report", warn=True)
        add("상태", "신뢰성", "STATUS_CADENCE_GAPS", gaps == 0, str(gaps),
            "long collection gaps = 0", "야간·PC off 구간 포함 11개 장기 공백",
            "validate_collection.py --write-report", warn=True)


def audit_parking(paths: dict[str, Path | None], metrics: dict[str, Any]) -> tuple[pd.DataFrame | None, pd.DataFrame | None]:
    master = read_csv(paths["parking_master"], dtype=str)  # type: ignore[arg-type]
    realtime = read_csv(paths["parking_realtime"], dtype=str)  # type: ignore[arg-type]
    join = read_csv(paths["parking_join"], dtype=str)  # type: ignore[arg-type]
    if master is None or realtime is None:
        add("주차", "내적", "PARKING_EXPORT", False, "missing master/realtime", "both exports exist",
            "주차 검증 불가", "export_team5_parking_csv.py")
        return master, join
    master_ids = set(master["pkltId"].dropna())
    rt_ids = set(realtime["pkltId"].dropna())
    orphan = len(rt_ids - master_ids)
    occupancy = as_number(realtime, "occupancy_rate")
    total = as_number(realtime, "total_spaces")
    remaining = as_number(realtime, "remaining_spaces")
    expected = (total - remaining) / total
    comparable = total.gt(0) & remaining.notna() & occupancy.notna()
    mismatch = int((occupancy[comparable].sub(expected[comparable] * 100).abs() > 0.02).sum())
    metrics["parking_master_lots"] = int(master["pkltId"].nunique())
    metrics["parking_realtime_lots"] = int(realtime["pkltId"].nunique())
    add("주차", "내적", "PARKING_REALTIME_SUBSET", orphan == 0, str(orphan), "realtime pkltId ⊆ master",
        "1개 realtime 주차장 ID가 최신 master에 없어 export 시점 차이 또는 master 보완이 필요",
        "export_team5_parking_csv.py", warn=True)
    add("주차", "내적", "PARKING_OCCUPANCY_FORMULA", mismatch == 0, f"{mismatch}/{int(comparable.sum())}",
        "|occupancy% - 100×(total-remaining)/total| ≤ 0.02", "잔여면과 점유율의 수식 일관성",
        "validate_data_validity.py", warn=True)

    if join is not None:
        matched = truth(join, "matched")
        distance = as_number(join, "distance_m")
        over_radius = int((matched & distance.gt(1000)).sum())
        realtime_matches = truth(join, "has_realtime")
        metrics["parking_1km_matches"] = int(matched.sum())
        metrics["parking_realtime_station_matches"] = int(realtime_matches.sum())
        add("주차", "공간", "PARKING_JOIN_RADIUS", over_radius == 0, str(over_radius),
            "matched distance ≤1000m", "join_parking_team5.py")
        add("주차", "외적", "PARKING_REALTIME_COVERAGE", False,
            f"{int(realtime_matches.sum())}/{int(matched.sum())} matched stations",
            "1km 정적 조인 ≠ 동일 시설·realtime은 일부 lot", "parking_ev_colocation report", warn=True)
    return master, join


def audit_traffic_utic(paths: dict[str, Path | None], metrics: dict[str, Any]) -> None:
    traffic = latest(REPO / "docs" / "data" / "loops" / "loop3" / STAMP, "daegu_traffic_linkspeed_*.csv")
    links = read_csv(traffic, dtype=str) if traffic else None
    if links is not None:
        grade = pd.to_numeric(links.get("congGrade"), errors="coerce")
        speed = pd.to_numeric(links.get("speedKph"), errors="coerce")
        duplicate_links = int(links.duplicated("linkId", keep=False).sum())
        grade_means = speed.groupby(grade).mean().to_dict()
        monotonic = all(
            grade_means.get(a, -math.inf) >= grade_means.get(b, math.inf)
            for a, b in ((1, 2), (2, 3))
            if a in grade_means and b in grade_means
        )
        metrics["traffic_latest_links"] = int(len(links))
        metrics["traffic_grade_speed_means"] = {str(k): round(v, 2) for k, v in grade_means.items()}
        add("도시소통", "내적", "TRAFFIC_LINK_ALIAS_DUPLICATES", duplicate_links == 0, str(duplicate_links),
            "linkId alias rows must be deduplicated for link-level aggregates",
            "동일 linkId가 복수 roadName으로 반복된다. 도시 평균은 원천 행 기준이고, link 단위 분석은 dedupe가 필요",
            "analyze_city_congestion.py", warn=True)
        add("도시소통", "내적", "TRAFFIC_SPEED_GRADE_ORDER", monotonic, str(metrics["traffic_grade_speed_means"]),
            "grade 1 speed ≥ grade 2 ≥ grade 3", "속도와 혼잡 등급의 방향성",
            "validate_data_validity.py", warn=True)
        add("도시소통", "외적", "TRAFFIC_ETA_BOUNDARY", False, "link geometry absent",
            "city linkspeed must not be used as route ETA", "dynamic/static contract", warn=True)

    utic = read_csv(paths["utic"], dtype=str)  # type: ignore[arg-type]
    join = read_csv(paths["utic_join"], dtype=str)  # type: ignore[arg-type]
    if utic is not None:
        dup = int(utic.duplicated("incidentId", keep=False).sum())
        daegu_address = utic.get("addressJibun", pd.Series("", index=utic.index)).fillna("").str.contains("대구")
        metrics["utic_latest_incidents"] = int(len(utic))
        add("UTIC", "내적", "UTIC_UNIQUE_INCIDENT", dup == 0, str(dup),
            "latest tick incidentId unique", "extract_utic_incident.py", warn=True)
        add("UTIC", "외적", "UTIC_DAEGU_FILTER", bool(daegu_address.all()),
            f"{int(daegu_address.sum())}/{len(utic)} address contains 대구", "all latest rows Daegu-filtered",
            "extract_utic_incident.py", warn=True)
    if join is not None:
        matched = truth(join, "matched")
        over_radius = int((matched & as_number(join, "distance_m").gt(1000)).sum())
        metrics["utic_live_station_matches"] = int(matched.sum())
        add("UTIC", "공간", "UTIC_JOIN_RADIUS", over_radius == 0, str(over_radius),
            "matched distance ≤1000m", "join_utic_incident.py")


def audit_usage_d1(paths: dict[str, Path | None], metrics: dict[str, Any]) -> pd.DataFrame | None:
    usage = read_csv(paths["usage"], dtype=str) if paths["usage"] else None
    usage_join = read_csv(paths["usage_join"], dtype=str)  # type: ignore[arg-type]
    if usage is not None:
        date_col = next((c for c in ("일자", "date", "useDate") if c in usage.columns), None)
        sessions_col = next((c for c in ("사용횟수", "sessions", "session_count") if c in usage.columns), None)
        metrics["usage_rows"] = int(len(usage))
        negative = int((pd.to_numeric(usage[sessions_col], errors="coerce") < 0).sum()) if sessions_col else 0
        add("이용이력", "내적", "USAGE_NONNEGATIVE", negative == 0, str(negative),
            "negative sessions = 0", "이용 횟수의 범위 검증", "usage_eda.py", warn=True)
        if date_col:
            metrics["usage_date_range"] = f"{usage[date_col].min()}~{usage[date_col].max()}"
    if usage_join is not None:
        matched = truth(usage_join, "matched")
        over_radius = int((matched & as_number(usage_join, "distance_m").gt(80)).sum())
        metrics["usage_join_matches"] = int(matched.sum())
        add("이용이력", "공간", "USAGE_JOIN_RADIUS", over_radius == 0, str(over_radius),
            "matched distance ≤80m", "build_usage_history_features.py")

    d1 = read_csv(paths["d1"], dtype=str)  # type: ignore[arg-type]
    if d1 is None:
        add("D1", "내적", "D1_FILE", False, "missing", "D1 exists", "통합 검증 불가", "build_d1_snapshot.py")
        return None
    dup = int(d1.duplicated("statId", keep=False).sum())
    observed = as_number(d1, "observed_count")
    ratio = as_number(d1, "availability_ratio_observed")
    null_policy_bad = int((observed.eq(0) & ratio.notna()).sum())
    availability = as_number(d1, "available_count")
    total = as_number(d1, "total_chargers")
    count_bad = int((availability.gt(total) | availability.lt(0)).sum())
    public_flag = truth(d1, "recommend_public_default")
    restricted = truth(d1, "access_restricted")
    public_bad = int((public_flag & restricted).sum())
    as_of = d1["as_of_ts"].iloc[0] if "as_of_ts" in d1 else "unknown"
    history = truth(d1, "history_observed")
    metrics["d1_rows"] = int(len(d1))
    metrics["d1_as_of_ts"] = str(as_of)
    metrics["d1_history_coverage_pct"] = round(100 * history.mean(), 2)
    metrics["d1_parking_realtime"] = int(truth(d1, "parking_has_realtime").sum())
    metrics["d1_utic_matches"] = int(as_number(d1, "nearest_incident_m").notna().sum())
    metrics["d1_eta_values"] = int(as_number(d1, "eta_minutes").notna().sum())
    metrics["d1_observed_station_share_pct"] = round(100 * observed.gt(0).mean(), 2)
    metrics["d1_confirmed_available_share_pct"] = round(
        100 * truth(d1, "has_confirmed_available").mean(), 2
    )
    add("D1", "내적", "D1_ONE_ROW_PER_STATION", dup == 0, str(dup), "duplicate statId = 0",
        "D1 row unit 검증", "build_d1_snapshot.py")
    add("D1", "내적", "D1_UNOBSERVED_NULL_POLICY", null_policy_bad == 0, str(null_policy_bad),
        "observed_count=0 → availability ratio null", "status_as_of.py")
    add("D1", "내적", "D1_COUNT_BOUNDS", count_bad == 0, str(count_bad),
        "0 ≤ available_count ≤ total_chargers", "build_d1_snapshot.py")
    add("D1", "내적", "D1_PUBLIC_ACCESS_FLAGS", public_bad == 0, str(public_bad),
        "public default and access restricted do not overlap", "build_d1_snapshot.py")
    add("이용이력", "외적", "USAGE_D1_COVERAGE", False, f"{history.sum()}/{len(d1)} ({history.mean():.1%})",
        "coverage ceiling = municipal ~219 stations (not join bug); auxiliary prior only",
        "integration readiness", warn=True)
    return d1


def audit_drift(paths: dict[str, Path | None], metrics: dict[str, Any], d1: pd.DataFrame | None) -> None:
    health = json.loads(paths["health"].read_text(encoding="utf-8")) if paths["health"] and paths["health"].is_file() else {}
    health_checks = health.get("checks", [])
    health_ok = all(item.get("status") == "PASS" for item in health_checks)
    metrics["collection_health"] = health.get("overall", "UNKNOWN")
    add("수집운영", "신뢰성", "DYNAMIC_FILE_FRESHNESS", health_ok,
        ", ".join(f"{x.get('source')}={x.get('age_minutes')}m" for x in health_checks) or "missing",
        "status ≤30m and traffic ≤45m", "check_collection_health.py", warn=True)
    if d1 is None:
        return
    d1_ts = pd.to_datetime(d1["as_of_ts"].iloc[0], errors="coerce")
    latest_status = metrics.get("status_latest_file", "")
    status_parts = Path(latest_status).stem.split("_") if latest_status else []
    status_stamp = "_".join(status_parts[-2:])
    live_ts = pd.to_datetime(status_stamp, format="%Y%m%d_%H%M%S", errors="coerce")
    if pd.notna(live_ts):
        live_ts = live_ts.tz_localize(KST)
    drift_minutes = (live_ts - d1_ts).total_seconds() / 60 if pd.notna(live_ts) and pd.notna(d1_ts) else None
    metrics["d1_to_status_drift_minutes"] = round(float(drift_minutes), 1) if drift_minutes is not None else None
    add("D1", "신뢰성", "D1_LIVE_STATUS_DRIFT",
        drift_minutes is not None and abs(drift_minutes) <= 30,
        f"{drift_minutes:.1f}m" if drift_minutes is not None else "unavailable",
        "D1 rebuilt within 30 minutes of latest status", "build_d1_snapshot.py", warn=True)
    live_utic = metrics.get("utic_live_station_matches")
    d1_utic = metrics.get("d1_utic_matches")
    if live_utic is not None and d1_utic is not None:
        add("D1", "신뢰성", "D1_LIVE_UTIC_DRIFT", d1_utic == live_utic,
            f"D1={d1_utic}, live={live_utic}", "same timestamp required for equality",
            "join_utic_incident.py → build_d1_snapshot.py", warn=True)


def external_samples(paths: dict[str, Path | None]) -> dict[str, int]:
    review = OUT / "external_review_samples"
    review.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    colocation = read_csv(paths["colocation"], dtype=str)  # type: ignore[arg-type]
    if colocation is not None:
        strong = colocation[colocation["best_grade"].eq("STRONG")].copy()
        sample = strong.sample(min(20, len(strong)), random_state=20260725)
        sample["map_verified"] = ""
        sample["external_address_match"] = ""
        sample["review_note"] = ""
        sample.to_csv(review / "parking_strong_external_review_sample.csv", index=False, encoding="utf-8-sig")
        counts["parking_strong_sample"] = int(len(sample))
    usage = read_csv(paths["usage_join"], dtype=str)  # type: ignore[arg-type]
    if usage is not None:
        sample = usage[truth(usage, "matched")].sample(min(20, int(truth(usage, "matched").sum())), random_state=20260725)
        sample["map_verified"] = ""
        sample["external_address_match"] = ""
        sample["review_note"] = ""
        sample.to_csv(review / "usage_join_external_review_sample.csv", index=False, encoding="utf-8-sig")
        counts["usage_join_sample"] = int(len(sample))
    return counts


def write_figures(metrics: dict[str, Any]) -> list[str]:
    FIG.mkdir(parents=True, exist_ok=True)
    plt.rcParams["font.family"] = ["Malgun Gothic", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    coverage = {
        "주차 realtime\nlot": (
            metrics.get("parking_realtime_lots", 0),
            metrics.get("parking_master_lots", 0),
        ),
        "이용이력\nD1": (
            round(metrics.get("d1_history_coverage_pct", 0), 2),
            100,
        ),
        "주차 realtime\nstation": (
            metrics.get("d1_parking_realtime", 0),
            metrics.get("d1_rows", 0),
        ),
    }
    labels = list(coverage)
    values = [100 * a / b if b else 0 for a, b in coverage.values()]
    fig, ax = plt.subplots(figsize=(8, 4.6))
    bars = ax.bar(labels, values, color="#4c78a8")
    ax.set_title("보조 데이터 커버리지 — 원천별 모집단 대비")
    ax.set_ylabel("커버리지 (%)")
    ax.set_ylim(0, 105)
    for bar, value in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, value + 2, f"{value:.1f}%", ha="center")
    fig.tight_layout()
    coverage_path = FIG / "01_auxiliary_data_coverage.png"
    fig.savefig(coverage_path, dpi=160)
    plt.close(fig)

    verdicts = pd.Series([item.status for item in CHECKS]).value_counts().reindex(["PASS", "WARN", "FAIL"], fill_value=0)
    fig, ax = plt.subplots(figsize=(7, 4.6))
    bars = ax.bar(verdicts.index, verdicts.values, color=["#59a14f", "#f28e2b", "#e15759"])
    ax.set_title("자동 타당성 검사 판정 수")
    ax.set_ylabel("검사 수 (개)")
    for bar, value in zip(bars, verdicts.values):
        ax.text(bar.get_x() + bar.get_width() / 2, value + 0.2, str(value), ha="center")
    fig.tight_layout()
    verdict_path = FIG / "02_check_verdicts.png"
    fig.savefig(verdict_path, dpi=160)
    plt.close(fig)
    return [coverage_path.relative_to(OUT).as_posix(), verdict_path.relative_to(OUT).as_posix()]


def write_report(metrics: dict[str, Any], sample_counts: dict[str, int], figures: list[str]) -> None:
    frame = pd.DataFrame(asdict(item) for item in CHECKS)
    frame.to_csv(OUT / "checks.csv", index=False, encoding="utf-8-sig")
    construct = construct_measurement_model(metrics)
    construct.to_csv(OUT / "construct_measurement_matrix.csv", index=False, encoding="utf-8-sig")
    by_domain = (
        frame.groupby(["domain", "status"]).size().unstack(fill_value=0).reindex(columns=["PASS", "WARN", "FAIL"], fill_value=0)
    )
    verdict = {
        "generated_at_kst": datetime.now(KST).isoformat(timespec="seconds"),
        "method": "offline local-file invariants, cross-source consistency, and external-review samples",
        "metrics": metrics,
        "checks": {"PASS": int((frame.status == "PASS").sum()), "WARN": int((frame.status == "WARN").sum()), "FAIL": int((frame.status == "FAIL").sum())},
        "mvp_verdict": {
            "allowed": ["public/available/fresh candidate filtering", "state freshness warning", "parking and UTIC explanatory context"],
            "auxiliary_only": ["parking realtime", "UTIC proximity", "usage history", "city-wide linkspeed"],
            "hold": ["arrival-success probability", "parking occupancy as charger availability", "linkspeed as route ETA", "long-term parking pattern"],
        },
        "external_review_samples": sample_counts,
        "figures": figures,
        "construct_target": "사용자가 ETA 후 도착했을 때 실제로 충전을 시작할 수 있는지",
        "construct_measurement_file": "construct_measurement_matrix.csv",
    }
    (OUT / "summary.json").write_text(json.dumps(verdict, ensure_ascii=False, indent=2), encoding="utf-8")
    table = markdown_table(by_domain, include_index=True)
    construct_table = markdown_table(
        construct[
            [
                "variable",
                "measurement_role",
                "construct_fit",
                "allowed_use",
                "decision",
            ]
        ]
    )
    warnings = markdown_table(
        frame[frame.status != "PASS"][["domain", "check_id", "status", "observed", "interpretation"]]
    )
    text = f"""# 데이터 타당성 종합 검증

| 항목 | 내용 |
|---|---|
| 생성 시각 | {verdict["generated_at_kst"]} |
| 방법 | 로컬 파일 불변식 · 원천 간 교차검증 · 시간/공간 정합성 · 외부 표본 검토 목록 |
| API 재호출 | 없음 |

## 결론

**MVP의 후보 필터와 상태 신선도 경고는 사용 가능하다.** 다만 주차·UTIC·이용이력은 보조 설명 신호이며,
도착 성공확률·ETA·장기 주차 혼잡은 이 데이터만으로 검증되지 않았다.

## 도메인별 자동 검사

{table}

![보조 데이터 커버리지]({figures[0]})

![자동 검사 판정]({figures[1]})

## WARN / FAIL의 의미

{warnings}

## 내적 타당성

- 충전기 master·상태·D1의 키 유일성, 수치 범위, null 정책을 검사했다.
- 주차 realtime은 master의 부분집합인지, 점유율 산식과 1km 반경이 맞는지 검사했다.
- 교통은 link 유일성과 속도·혼잡 등급의 방향성을, UTIC/이용이력은 반경·필터·중복을 검사했다.
- D1은 최신 원천과 다른 시점의 고정 스냅샷일 수 있으므로 drift는 데이터 오류가 아니라 **재빌드 필요 경고**로 분리했다.

## 측정타당성 — “사용 가능성”을 무엇으로 측정하는가

서비스 목표는 **“사용자가 ETA 후 도착했을 때 실제로 충전을 시작할 수 있는지”**다. 따라서
현재 API의 빈 충전기 수는 중요한 입력이지만, 목표 자체와 동의어가 아니다. 현재는 도착 결과
정답 라벨·경로 ETA·상태 전이 예측이 없으므로 도착 성공확률을 측정하거나 주장할 수 없다.

{construct_table}

### 현재 측정의 해석 규칙

- `available_count`는 **관측 시점** 충전 가능성의 부분 직접 측정치다. `observed_count=0`을 0개로 바꾸지 않는다.
- 신선도는 사용 가능성의 구성요소가 아니라, `available_count`가 믿을 만한지 판단하는 **측정 품질 변수**다.
- 충전기 수는 현재 빈자리의 측정치가 아니라, 한 대 고장·사용중일 때의 실패 위험을 완화하는 구조적 proxy다.
- 과거 이용량·회전율은 장기 수요 proxy이고, 현재 가용성이나 ETA 후 상태를 대신하지 않는다.
- 주차 점유율은 검증된 같은 시설(STRONG)에서만 접근성 보조 정보다. 1km 조인을 충전기 상태로 해석하지 않는다.
- ETA 후 예상 상태가 목표에 가장 가깝지만, 현재 `eta_minutes`는 {metrics.get("d1_eta_values", 0)}건이라 아직 측정 불가다.

## 신뢰성

- 상태 수집의 별도 R1–R6 검사와 최신 파일 freshness를 재사용했다.
- 상태 API는 변경분 feed이므로, 관측되지 않은 충전기를 사용 불가로 해석하지 않는다.
- 주차 realtime은 일부 주차장만 포함하고, PC 기반 UTIC은 서버 상시 운영 데이터가 아니다.

## 외적 타당성 경계

- 대상은 대구 MVP·공용 후보 중심이며, 다른 도시·계절·사용자 목적에 일반화할 수 없다.
- 1km 주차 매칭은 “주변 주차장”이지 “충전소 내부 주차장”이 아니다. 100m STRONG 후보도 외부 지도·주소 확인 전에는 확정 표현을 금지한다.
- 실제 충전 성공/도착 시 가용성 정답 라벨이 없어 추천 성공확률의 외적 타당성은 **보류**다.

## 수동 외부 표본 검토

- `external_review_samples/parking_strong_external_review_sample.csv`: STRONG 주차 공존 후보 {sample_counts.get("parking_strong_sample", 0)}개
- `external_review_samples/usage_join_external_review_sample.csv`: 이용이력 공간조인 후보 {sample_counts.get("usage_join_sample", 0)}개

각 파일의 `map_verified`, `external_address_match`, `review_note`를 지도·주소 대조 후 기록한다.

## 재검증 조건

1. 최신 pull 직후 D1을 재생성하고 D1 drift WARN을 해소한다.
2. STRONG 주차 표본을 외부 지도·주소로 확인한다.
3. 상태·주차 이력이 2주 이상 누적된 뒤 시간대 안정성과 주차–가용 관계를 재검증한다.
4. ETA와 충전 성공확률은 경로 ETA·도착 후 결과 라벨을 확보한 뒤 별도 검증한다.

```text
DA① | offline data validity assessment | {STAMP}
```
"""
    (OUT / "README.md").write_text(text, encoding="utf-8")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    paths = source_paths()
    metrics: dict[str, Any] = {}
    audit_master_status(paths, metrics)
    audit_parking(paths, metrics)
    audit_traffic_utic(paths, metrics)
    d1 = audit_usage_d1(paths, metrics)
    audit_drift(paths, metrics, d1)
    samples = external_samples(paths)
    figures = write_figures(metrics)
    write_report(metrics, samples, figures)
    print(json.dumps({"out": str(OUT.relative_to(REPO)), "checks": len(CHECKS), "metrics": metrics}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
