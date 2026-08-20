"""Univariate significance of lat/lng vs target_available (HGB training set)."""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

_ANALYSIS = Path(__file__).resolve().parent
if str(_ANALYSIS) not in sys.path:
    sys.path.insert(0, str(_ANALYSIS))
_PROCESSING = Path(__file__).resolve().parents[1]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))

from _bootstrap import ensure_paths
from build_station_horizon_training import _association_row

REPO = ensure_paths()
KST = ZoneInfo("Asia/Seoul")
CENTER_LAT, CENTER_LNG = 35.8714, 128.6014  # Daegu city-hall approx


def hav_km(lat: np.ndarray, lng: np.ndarray) -> np.ndarray:
    r = 6371.0
    lat1 = np.radians(CENTER_LAT)
    lon1 = np.radians(CENTER_LNG)
    lat2 = np.radians(lat)
    lon2 = np.radians(lng)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def decide(feature: str, row: dict, baseline: set[str]) -> tuple[float | None, str]:
    da = row.get("directional_auc")
    ba = row.get("blocked_auc")
    ci = row.get("auc_ci_low")
    practical = None
    if da is not None and ba is not None:
        practical = min(float(da), float(ba))
    elif da is not None:
        practical = float(da)

    if feature in baseline:
        return practical, "BASELINE_REF"
    if practical is None:
        return practical, "INCONCLUSIVE"
    if practical >= 0.60 and ci is not None and float(ci) > 0.5:
        return practical, "CANDIDATE"
    if practical >= 0.55 and ci is not None and float(ci) > 0.5:
        return practical, "WEAK_CANDIDATE"
    return practical, "DROP_LIKELY"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    train_path = (
        REPO
        / "apps/data-pipeline/evaluation/results/datasets/station_horizon_training_v1.parquet"
    )
    d1_path = (
        REPO
        / "apps/data-pipeline/evaluation/results/datasets/station_feature_snapshot_latest.csv"
    )
    stamp = datetime.now(KST).strftime("%Y%m%d")
    out = REPO / "docs/data/analysis" / f"coord_feature_significance_{stamp}"
    out.mkdir(parents=True, exist_ok=True)

    train = pd.read_parquet(train_path)
    d1 = pd.read_csv(d1_path, dtype=str, usecols=["statId", "lat", "lng", "coord_ok"])
    d1["lat"] = pd.to_numeric(d1["lat"], errors="coerce")
    d1["lng"] = pd.to_numeric(d1["lng"], errors="coerce")
    coords = d1.rename(columns={"statId": "station_id"})[
        ["station_id", "lat", "lng", "coord_ok"]
    ]
    merged = train.merge(coords, on="station_id", how="left")
    merged["dist_from_daegu_center_km"] = hav_km(
        merged["lat"].to_numpy(dtype=float),
        merged["lng"].to_numpy(dtype=float),
    )
    if "feature_date" not in merged.columns:
        merged["feature_date"] = pd.to_datetime(merged["feature_as_of"]).dt.date.astype(
            str
        )

    features = ["lat", "lng", "dist_from_daegu_center_km"]
    baseline = {"available_count", "observation_age_minutes", "horizon_minutes"}
    all_feats = features + [f for f in baseline if f in merged.columns]

    train_df = merged[merged["split"] == "train"].copy()
    rows = []
    for feature in all_feats:
        row = _association_row(
            train_df,
            feature,
            block_column="feature_date",
            bootstrap_iterations=40,
        )
        practical, decision = decide(feature, row, baseline)
        row["practical_auc"] = practical
        row["decision"] = decision
        rows.append(row)
        print(
            feature,
            "dir",
            row.get("directional_auc"),
            "blocked",
            row.get("blocked_auc"),
            "ci_low",
            row.get("auc_ci_low"),
            "pb",
            row.get("point_biserial"),
            decision,
        )

    assoc = pd.DataFrame(rows)
    assoc.to_csv(out / "coord_vs_target_association.csv", index=False, encoding="utf-8-sig")

    by_h = []
    for horizon, part in train_df.groupby("horizon_minutes"):
        for feature in features:
            row = _association_row(
                part,
                feature,
                block_column="feature_date",
                bootstrap_iterations=20,
            )
            row["horizon_minutes"] = int(horizon)
            by_h.append(row)
    pd.DataFrame(by_h).to_csv(
        out / "coord_association_by_horizon.csv", index=False, encoding="utf-8-sig"
    )

    coord_rows = [r for r in rows if r["feature"] in features]
    keep_any = any(
        (r.get("practical_auc") or 0) >= 0.55 and (r.get("auc_ci_low") or 0) > 0.5
        for r in coord_rows
    )
    recommend = (
        "INCLUDE_FOR_ABLATION"
        if keep_any
        else "DO_NOT_ADD — univariate signal too weak; keep lat/lng for map/join only"
    )

    summary = {
        "generated_at": datetime.now(KST).isoformat(),
        "training_rows": int(len(merged)),
        "train_rows": int(len(train_df)),
        "stations": int(merged["station_id"].nunique()),
        "lat_null_rate": float(merged["lat"].isna().mean()),
        "center_ref": {"lat": CENTER_LAT, "lng": CENTER_LNG},
        "thresholds": {
            "practical_auc_candidate": 0.55,
            "blocked_ci_lower_gt": 0.5,
        },
        "results": rows,
        "recommend_include_lat_lng": keep_any,
        "recommend_text": recommend,
    }
    (out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    lines = [
        f"# 위도·경도 피처 유의성 점검 ({stamp})",
        "",
        "| 항목 | 내용 |",
        "|---|---|",
        "| **데이터** | `station_horizon_training_v1` + D1 lat/lng |",
        "| **타겟** | `target_available` (도착 시 가용≥1) |",
        f"| **한 줄** | {recommend} |",
        "",
        "## 결과 (train split)",
        "",
        "| feature | directional_auc | blocked_auc | auc_ci_low | point_biserial | decision |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for r in rows:
        lines.append(
            "| `{feature}` | {directional_auc} | {blocked_auc} | {auc_ci_low} | {point_biserial} | {decision} |".format(
                feature=r["feature"],
                directional_auc=r.get("directional_auc"),
                blocked_auc=r.get("blocked_auc"),
                auc_ci_low=r.get("auc_ci_low"),
                point_biserial=r.get("point_biserial"),
                decision=r.get("decision"),
            )
        )
    lines += [
        "",
        "## 해석",
        "",
        "- AUC≈0.5면 위치만으로 도착 가용을 거의 구분 못 함.",
        "- `available_count` baseline보다 훨씬 약하면 **모델 피처로 불필요**.",
        "- 위·경도는 **지도·거리·조인**용으로만 유지.",
        "",
        f"상세: `docs/data/analysis/coord_feature_significance_{stamp}/`",
        "",
        "```",
        f"DA① | lat/lng significance vs target_available | {stamp}",
        "```",
        "",
    ]
    text = "\n".join(lines)
    (out / "README.md").write_text(text, encoding="utf-8")
    share = REPO / "docs" / "팀공유" / f"위경도_피처유의성_{stamp}.md"
    share.write_text(text, encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
