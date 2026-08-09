"""Keep only latest stamp per analysis series under docs/data/analysis/.

Moves older dated folders into docs/data/analysis/_archive/YYYYMM/.
Does NOT delete.
"""
from __future__ import annotations

import json
import re
import shutil
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[5]
ROOT = REPO / "docs" / "data" / "analysis"
ARCHIVE = ROOT / "_archive"
KST = ZoneInfo("Asia/Seoul")
STAMP_RE = re.compile(r"(20\d{6})")

SERIES_PREFIXES = [
    "arrival_availability_replay_",
    "arrival_labels_tmap_eta_",
    "city_congestion_",
    "coord_feature_significance_",
    "d1_explain_",
    "data_validity_assessment_",
    "derived_v0_",
    "hgb_training_pipeline_",
    "integration_readiness_",
    "parking_score_validation_",
    "shadow_recommendation_",
    "station_tmap_eta_",
    "team5_parking_eda_",
    "utic_incidents_",
]

# Keep at root even if old / unique (final reference or still used).
KEEP_EXACT = {
    "_archive",
    "hgb_arrival_eta_fitness_20260808",
    "hgb_overfit_risk_20260808",
    "eta_calibration_20260806",
    "iqr_outlier_scan_20260806",
    "anomaly_scan_20260806",
    "chart_type_gallery_20260806",
    "parking_fee_20260803",
    "me_history_hourly_profile",
    "missingness_20260731",
    "new_apt_coverage",
    "parking",
    "trip_charger_usage",
    "d2_lag_align_20260731",
    "historical_incidents_20260728",
    "usage_history_qa_20260730",
    "snapshot_all_latest.json",
}

# One-off old probes → archive (superseded or unused for handoff).
FORCE_ARCHIVE_PREFIXES = (
    "comprehensive_eda_quality_",
    "dq_check_",
    "fee_mapping_probe_",
    "fee_operator_evorkr_probe_",
    "parking_ev_colocation_",
    "recommendation_handoff_",
    "snapshot_all_2026",
    "soc_route_scenarios_",
    "tmap_eta_sample_",
)


def _stamp(name: str) -> str | None:
    m = STAMP_RE.search(name)
    return m.group(1) if m else None


def _dest_for(name: str) -> Path:
    st = _stamp(name)
    if st:
        return ARCHIVE / st[:6] / name
    return ARCHIVE / "misc" / name


def _move(src: Path, moved: list[dict]) -> None:
    dest = _dest_for(src.name)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        shutil.rmtree(dest) if dest.is_dir() else dest.unlink()
    shutil.move(str(src), str(dest))
    moved.append({"from": src.name, "to": str(dest.relative_to(ROOT)).replace("\\", "/")})


def main() -> None:
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    moved: list[dict] = []
    kept_latest: dict[str, str] = {}

    by_series: dict[str, list[Path]] = defaultdict(list)
    for p in ROOT.iterdir():
        if p.name in KEEP_EXACT or p.name == "_archive":
            continue
        if not p.is_dir() and p.suffix == ".log":
            continue  # leave run logs; optional later
        for pref in SERIES_PREFIXES:
            if p.name.startswith(pref) and _stamp(p.name):
                by_series[pref].append(p)
                break

    for pref, paths in by_series.items():
        paths = sorted(paths, key=lambda x: _stamp(x.name) or "")
        latest = paths[-1]
        kept_latest[pref] = latest.name
        for p in paths[:-1]:
            _move(p, moved)

    for p in list(ROOT.iterdir()):
        if p.name in KEEP_EXACT or p.name == "_archive":
            continue
        if any(p.name.startswith(pref) for pref in SERIES_PREFIXES):
            continue
        if any(p.name.startswith(pref) for pref in FORCE_ARCHIVE_PREFIXES):
            _move(p, moved)

    # Move stale run logs that are not 20260808 final suite (optional: keep all logs)
    # Keep *.log at root for now.

    (ARCHIVE / "README.md").write_text(
        "\n".join(
            [
                "# analysis 아카이브",
                "",
                "`docs/data/analysis/` 루트에는 **시리즈별 최신 stamp + 최종 HGB/ETA**만 둡니다.",
                "과거 날짜 폴더는 여기로 이동. **삭제하지 않음.**",
                "",
                f"- 정리 시각: {datetime.now(KST).isoformat(timespec='seconds')}",
                f"- 이번 이동: {len(moved)}건",
                "",
            ]
        ),
        encoding="utf-8",
    )

    meta = {
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "moved": len(moved),
        "kept_latest": kept_latest,
        "moves": moved,
    }
    (ARCHIVE / "last_archive_run.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({"ok": True, "moved": len(moved), "kept_latest": kept_latest}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
