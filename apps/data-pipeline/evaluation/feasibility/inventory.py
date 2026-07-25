"""Data inventory for feasibility gate — real files only, no guesses."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from .paths import (
    D1_LATEST,
    EXTRACTED_DIR,
    HISTORY_FEAT,
    LOOP1_DIR,
    LOOP1_INDEX,
    LOOP1_SNAPSHOTS,
    OUT_JSON,
    OUT_TABLES,
    USAGE_CSV,
    USAGE_JOIN,
    charger_info_csvs,
    charger_status_oneshot_csvs,
    ensure_out,
    iter_status_csvs,
    parking_team5_csvs,
    status_snapshots_dirs,
)


def _count_rows_fast(path: Path) -> int:
    n = 0
    with path.open("rb") as f:
        for _ in f:
            n += 1
    return max(n - 1, 0)


def _peek_csv(path: Path, encodings: tuple[str, ...] = ("utf-8-sig", "utf-8", "cp949")) -> dict[str, Any]:
    last_err: Exception | None = None
    for enc in encodings:
        try:
            df = pd.read_csv(path, nrows=5, dtype=str, encoding=enc)
            rows = _count_rows_fast(path)
            return {
                "path": str(path).replace("\\", "/"),
                "exists": True,
                "encoding": enc,
                "rows": rows,
                "cols": int(df.shape[1]),
                "columns": list(df.columns),
                "sample_head": df.head(2).to_dict(orient="records"),
            }
        except Exception as exc:  # noqa: BLE001
            last_err = exc
    return {
        "path": str(path).replace("\\", "/"),
        "exists": path.exists(),
        "error": str(last_err),
    }


def _classify(path: Path, name: str) -> str:
    low = name.lower()
    if "mock" in low or "fixture" in low:
        return "mock"
    if not path.exists():
        return "missing"
    return "real"


def run_inventory() -> dict[str, Any]:
    ensure_out()
    rows: list[dict[str, Any]] = []

    # --- charger info ---
    info_files = charger_info_csvs()
    seen: set[Path] = set()
    for p in info_files:
        rp = p.resolve()
        if rp in seen:
            continue
        seen.add(rp)
        peek = _peek_csv(p)
        peek.update(
            {
                "category": "charger_info",
                "kind": _classify(p, p.name),
                "grain": "charger (statId+chgerId)",
                "time_columns": [c for c in peek.get("columns", []) if c.lower() in {"fetchedat", "statupddt", "usetime"}],
                "has_station_id": "statId" in peek.get("columns", []),
                "has_charger_id": "chgerId" in peek.get("columns", []),
                "eta_target_role": "none — static master",
                "feature_role": "join key / static attrs",
            }
        )
        rows.append(peek)

    # --- status one-shot ---
    for p in charger_status_oneshot_csvs():
        peek = _peek_csv(p)
        peek.update(
            {
                "category": "status_oneshot",
                "kind": "real",
                "grain": "charger change event (period window)",
                "time_columns": [c for c in peek.get("columns", []) if c in {"statUpdDt", "fetchedAt"}],
                "has_station_id": "statId" in peek.get("columns", []),
                "has_charger_id": "chgerId" in peek.get("columns", []),
                "eta_target_role": "insufficient alone (single tick)",
                "feature_role": "current state only",
            }
        )
        rows.append(peek)

    # --- loop1 series ---
    snap_dirs = status_snapshots_dirs()
    snap_files: list[Path] = []
    for d in snap_dirs:
        snap_files.extend(iter_status_csvs(d))
    n_snaps = len(snap_files)
    first = snap_files[0] if snap_files else None
    last = snap_files[-1] if snap_files else None
    peek0 = _peek_csv(first) if first else {}
    idx_rows = _count_rows_fast(LOOP1_INDEX) if LOOP1_INDEX.exists() else 0
    rows.append(
        {
            "category": "status_loop1_series",
            "kind": "real",
            "path": str(LOOP1_SNAPSHOTS).replace("\\", "/"),
            "exists": LOOP1_SNAPSHOTS.is_dir(),
            "snapshot_files": n_snaps,
            "index_rows": idx_rows,
            "first_snapshot": first.name if first else None,
            "last_snapshot": last.name if last else None,
            "columns": peek0.get("columns"),
            "cols": peek0.get("cols"),
            "sample_rows_per_snap": peek0.get("rows"),
            "grain": "charger × change-event within period; tick = snapshotId",
            "time_columns": ["statUpdDt", "fetchedAt", "snapshotId"],
            "has_station_id": True,
            "has_charger_id": True,
            "timezone": "Asia/Seoul (filename / fetchedAt local)",
            "eta_target_role": "direct candidate IF t and t+horizon both observed",
            "feature_role": "primary realtime state / reliability",
            "note": "API period=change feed — absence in tick ≠ unavailable",
        }
    )

    # --- usage daily ---
    if USAGE_CSV.exists():
        peek = _peek_csv(USAGE_CSV)
        # date range via chunk
        dates = []
        for chunk in pd.read_csv(USAGE_CSV, encoding=peek.get("encoding", "cp949"), usecols=["일자"], chunksize=50000):
            dates.append(chunk["일자"].astype(str))
        ser = pd.concat(dates, ignore_index=True)
        dt = pd.to_datetime(ser, errors="coerce")
        n_2025 = int(((dt >= "2025-01-01") & (dt < "2026-01-01")).sum())
        peek.update(
            {
                "category": "usage_daily",
                "kind": "real",
                "grain": "municipal_charger × day",
                "time_columns": ["일자"],
                "time_min": str(dt.min().date()) if dt.notna().any() else None,
                "time_max": str(dt.max().date()) if dt.notna().any() else None,
                "rows_2025": n_2025,
                "has_station_id": "충전소아이디" in peek.get("columns", []),
                "has_charger_id": "충전기아이디" in peek.get("columns", []),
                "eta_target_role": "NOT a direct ETA availability target (daily grain)",
                "feature_role": "auxiliary historical congestion features",
            }
        )
        rows.append(peek)
    else:
        rows.append({"category": "usage_daily", "kind": "missing", "path": str(USAGE_CSV)})

    if USAGE_JOIN.exists():
        peek = _peek_csv(USAGE_JOIN)
        peek.update(
            {
                "category": "usage_statId_join",
                "kind": "derived_real",
                "grain": "municipal_station → EvCharger statId",
                "eta_target_role": "none",
                "feature_role": "ID bridge for usage features",
            }
        )
        rows.append(peek)

    if HISTORY_FEAT.exists():
        peek = _peek_csv(HISTORY_FEAT)
        peek.update(
            {
                "category": "usage_history_features",
                "kind": "derived_real",
                "grain": "statId × charger_type",
                "eta_target_role": "none",
                "feature_role": "rolling/weekday usage auxiliaries",
            }
        )
        rows.append(peek)

    if D1_LATEST.exists():
        peek = _peek_csv(D1_LATEST)
        peek.update(
            {
                "category": "d1_station_snapshot",
                "kind": "derived_real",
                "grain": "station × as_of_ts",
                "eta_target_role": "current state features only — not future target",
                "feature_role": "MVP rule inputs",
            }
        )
        rows.append(peek)

    # parking team5 real
    for p in parking_team5_csvs():
        if "latest" not in p.name:
            continue
        peek = _peek_csv(p)
        peek.update(
            {
                "category": "parking",
                "kind": "real_team5_pis",
                "eta_target_role": "auxiliary occupancy feature after spatial join",
                "feature_role": "D1 parking fields (DA①)",
            }
        )
        rows.append(peek)

    summary = {
        "loop1_dir": str(LOOP1_DIR).replace("\\", "/"),
        "n_inventory_rows": len(rows),
        "status_snapshots": n_snaps,
        "categories": sorted({r.get("category") for r in rows}),
    }
    out = {"summary": summary, "items": rows}
    (OUT_JSON / "inventory.json").write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    flat = []
    for r in rows:
        flat.append(
            {
                "category": r.get("category"),
                "kind": r.get("kind"),
                "path": r.get("path"),
                "rows": r.get("rows") or r.get("snapshot_files"),
                "cols": r.get("cols"),
                "time_min": r.get("time_min") or r.get("first_snapshot"),
                "time_max": r.get("time_max") or r.get("last_snapshot"),
                "grain": r.get("grain"),
                "eta_target_role": r.get("eta_target_role"),
                "feature_role": r.get("feature_role"),
            }
        )
    pd.DataFrame(flat).to_csv(OUT_TABLES / "inventory_overview.csv", index=False, encoding="utf-8-sig")
    return out
