"""Apply DQ fixes: quarantine coords, service CSV, full hours, sync archive snaps.

Usage (repo root):
  python apps/data-pipeline/processing/analysis/fix_dq_artifacts.py
"""
from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

_PROCESSING = Path(__file__).resolve().parents[1]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))
from _bootstrap import ensure_paths

REPO = ensure_paths()
from core.charger_quality import (  # noqa: E402
    annotate_charger_info,
    quarantine_chargers,
    service_chargers,
)
from features.use_time import is_operating_now  # noqa: E402
from loop_paths import (  # noqa: E402
    EXTRACTED_CHARGER_HOURS,
    EXTRACTED_CHARGER_INFO,
    LOOP1_SNAPSHOTS,
    LOOPS_ARCHIVE,
    iter_status_csvs,
    loop1_day_dir,
    status_snapshots_dirs,
    ymd_from_filename,
)

KST = ZoneInfo("Asia/Seoul")


def _latest_info() -> Path:
    preferred = EXTRACTED_CHARGER_INFO / "daegu_charger_info_20260723_latest.csv"
    if preferred.is_file():
        return preferred
    files = sorted(EXTRACTED_CHARGER_INFO.glob("daegu_charger_info_*.csv"))
    if not files:
        raise FileNotFoundError("no charger info CSV")
    return files[-1]


def _build_info_artifacts(info_path: Path, as_of: datetime) -> dict:
    raw = pd.read_csv(info_path, dtype=str)
    ann = annotate_charger_info(raw)
    q = quarantine_chargers(ann)
    svc = service_chargers(ann)

    out_dir = EXTRACTED_CHARGER_INFO
    q_path = out_dir / "daegu_charger_info_quarantine_coords_latest.csv"
    svc_path = out_dir / "daegu_charger_info_service_latest.csv"
    flagged_path = out_dir / "daegu_charger_info_flagged_latest.csv"

    # compact quarantine for review
    q_cols = [
        c
        for c in [
            "statId",
            "chgerId",
            "statNm",
            "addr",
            "lat",
            "lng",
            "delYn",
            "coordinate_quality_flag",
            "busiNm",
        ]
        if c in q.columns
    ]
    q[q_cols].to_csv(q_path, index=False, encoding="utf-8-sig")

    # service: drop misleading live-looking `stat` name — keep as stat_at_info_fetch only
    svc_out = svc.copy()
    if "stat" in svc_out.columns:
        svc_out = svc_out.drop(columns=["stat"])
    keep = [
        c
        for c in svc_out.columns
        if c
        not in {
            "lat_num",
            "lng_num",
            "addr_is_daegu",
            "coord_in_bbox",
            "coord_placeholder",
            "_xy",
        }
    ]
    svc_out[keep].to_csv(svc_path, index=False, encoding="utf-8-sig")

    # full flagged master (all rows)
    ann.to_csv(flagged_path, index=False, encoding="utf-8-sig")

    # also under analysis for DQ pack
    dq_dir = REPO / "docs/data/analysis/dq_check_20260723"
    dq_dir.mkdir(parents=True, exist_ok=True)
    q[q_cols].to_csv(dq_dir / "quarantine_coords.csv", index=False, encoding="utf-8-sig")

    return {
        "info_source": str(info_path.relative_to(REPO)).replace("\\", "/"),
        "rows_raw": int(len(ann)),
        "stations_raw": int(ann["statId"].nunique()),
        "quarantine_rows": int(len(q)),
        "quarantine_stations": int(q["statId"].nunique()) if len(q) else 0,
        "service_rows": int(len(svc)),
        "service_stations": int(svc["statId"].nunique()) if len(svc) else 0,
        "delYn_Y_rows": int((~ann["is_service_target"]).sum()),
        "shared_coord_cluster_rows": int(ann["shared_coord_cluster"].sum()),
        "outputs": {
            "quarantine": str(q_path.relative_to(REPO)).replace("\\", "/"),
            "service": str(svc_path.relative_to(REPO)).replace("\\", "/"),
            "flagged": str(flagged_path.relative_to(REPO)).replace("\\", "/"),
        },
    }


def _build_full_hours(info_path: Path, as_of: datetime) -> dict:
    info = pd.read_csv(info_path, dtype=str)
    # station-level: prefer service targets; still include delYn=Y with flag
    if "delYn" in info.columns:
        info["_del"] = info["delYn"].astype(str).str.upper().eq("Y")
    else:
        info["_del"] = False
    stations = (
        info.sort_values(["statId", "chgerId"])
        .drop_duplicates(subset=["statId"], keep="first")
        .copy()
    )
    stations["is_service_target"] = ~stations["_del"]
    stations["is_operating_now"] = stations["useTime"].map(
        lambda x: is_operating_now(x, as_of)
    )
    cols = ["statId", "statNm", "useTime", "is_operating_now", "is_service_target"]
    out = stations[cols]

    EXTRACTED_CHARGER_HOURS.mkdir(parents=True, exist_ok=True)
    full_path = EXTRACTED_CHARGER_HOURS / "daegu_charger_hours_full_latest.csv"
    anno_path = EXTRACTED_CHARGER_HOURS / "daegu_charger_hours_annotated_latest.csv"
    # keep legacy 496 file name meaning "annotated full" going forward
    out.to_csv(full_path, index=False, encoding="utf-8-sig")
    out.to_csv(anno_path, index=False, encoding="utf-8-sig")

    # retain old partial extract under archive name if present
    old_partial = EXTRACTED_CHARGER_HOURS / "daegu_charger_hours_latest.csv"
    if old_partial.is_file():
        bak = EXTRACTED_CHARGER_HOURS / "daegu_charger_hours_partial496_20260723.csv"
        if not bak.is_file():
            shutil.copy2(old_partial, bak)
        # point latest → full (overwrite with full station universe)
        out.to_csv(old_partial, index=False, encoding="utf-8-sig")

    note = EXTRACTED_CHARGER_HOURS / "README.md"
    note.write_text(
        "\n".join(
            [
                "# charger hours",
                "",
                "- **`daegu_charger_hours_latest.csv` / `_full_latest.csv` / `_annotated_latest.csv`**",
                "  = **전체 충전소** useTime (info 정본, station 1행).",
                "- `daegu_charger_hours_partial496_20260723.csv` = 예전 496 부분셋 백업.",
                "- 라이브 가용은 loop status · info.`stat` 쓰지 말 것.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return {
        "stations": int(len(out)),
        "service_stations": int(out["is_service_target"].sum()),
        "operating_Y_N_U": out["is_operating_now"].value_counts().to_dict(),
        "full_csv": str(full_path.relative_to(REPO)).replace("\\", "/"),
    }


def _sync_archive_snapshots_into_live() -> dict:
    """Copy archive-only snapshot CSVs into loop1/snapshots/YYYYMMDD/."""
    LOOP1_SNAPSHOTS.mkdir(parents=True, exist_ok=True)
    live_names = {p.name for p in iter_status_csvs(LOOP1_SNAPSHOTS)}
    archive_roots = sorted(LOOPS_ARCHIVE.glob("from_lightsail_*/loop1/snapshots"))
    copied = []
    skipped = 0
    for root in archive_roots:
        for src in iter_status_csvs(root):
            if src.name in live_names:
                skipped += 1
                continue
            ymd = ymd_from_filename(src.name) or "unknown"
            dest = loop1_day_dir(ymd) / src.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            live_names.add(src.name)
            copied.append(src.name)
    return {
        "archive_dirs": [str(p.relative_to(REPO)).replace("\\", "/") for p in archive_roots],
        "copied_into_live": len(copied),
        "already_in_live": skipped,
        "live_total_after": len(iter_status_csvs(LOOP1_SNAPSHOTS)),
        "sample_copied": copied[:5] + (["…"] if len(copied) > 5 else []),
    }


def _parking_guard_note() -> dict:
    path = REPO / "docs/data/extracted/parking/PARKING_MOCK_DO_NOT_SCORE.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "# 주차 데이터 — 점수에 넣지 말 것",
                "",
                "- 2026-07-23 프로브: 공공 주차 API **키 미등록** / mock.",
                "- `parking_occupancy`·잔여면수로 **추천 감점 금지**.",
                "- 키 승인·실수집 후 이 파일 삭제/갱신.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return {"note": str(path.relative_to(REPO)).replace("\\", "/")}


def main() -> int:
    as_of = datetime.now(KST)
    info_path = _latest_info()
    print("info:", info_path)

    info_meta = _build_info_artifacts(info_path, as_of)
    print("info artifacts:", json.dumps(info_meta, ensure_ascii=False))

    hours_meta = _build_full_hours(info_path, as_of)
    print("hours:", json.dumps(hours_meta, ensure_ascii=False))

    sync_meta = _sync_archive_snapshots_into_live()
    print("snapshot sync:", json.dumps(sync_meta, ensure_ascii=False))

    park_meta = _parking_guard_note()
    print("parking guard:", park_meta)

    dirs = status_snapshots_dirs()
    print("status_snapshots_dirs:", [str(d) for d in dirs])

    meta = {
        "as_of_kst": as_of.isoformat(timespec="seconds"),
        "info": info_meta,
        "hours": hours_meta,
        "snapshot_sync": sync_meta,
        "parking": park_meta,
        "status_snapshots_dirs": [str(d.relative_to(REPO)).replace("\\", "/") for d in dirs],
    }
    out = REPO / "docs/data/analysis/dq_check_20260723/fix_applied.json"
    out.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
