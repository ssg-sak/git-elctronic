"""Daily CSV exports for charger info (and index tracking).

Info CSVs land under docs/data/extracted/daily/YYYY-MM-DD/ — never overwrite
flat extracted/*.csv files from one-off pulls.
"""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import config
import db

KST = ZoneInfo("Asia/Seoul")
DAILY_ROOT = config.ROOT_DIR / "docs" / "data" / "extracted" / "daily"
DAILY_INDEX = DAILY_ROOT / "index.csv"

INFO_FIELDS = [
    "statId",
    "statNm",
    "addr",
    "lat",
    "lng",
    "chgerId",
    "chgerType",
    "output",
    "useTime",
    "busiNm",
    "parkingFree",
    "delYn",
    "fetchedAt",
]

INDEX_FIELDS = [
    "exportDate",
    "kind",
    "path",
    "rows",
    "fetchedAt",
    "source",
]


def _now_kst() -> datetime:
    return datetime.now(tz=KST)


def _stamp(dt: datetime | None = None) -> str:
    value = dt or _now_kst()
    return value.strftime("%Y%m%d_%H%M%S")


def _append_index(
    *,
    export_date: str,
    kind: str,
    path: Path,
    rows: int,
    fetched_at: str,
    source: str,
) -> None:
    DAILY_ROOT.mkdir(parents=True, exist_ok=True)
    exists = DAILY_INDEX.exists()
    with DAILY_INDEX.open("a", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=INDEX_FIELDS)
        if not exists:
            writer.writeheader()
        writer.writerow(
            {
                "exportDate": export_date,
                "kind": kind,
                "path": str(path.relative_to(config.ROOT_DIR)).replace("\\", "/"),
                "rows": rows,
                "fetchedAt": fetched_at,
                "source": source,
            }
        )


def _load_info_rows() -> list[dict[str, str | float | None]]:
    query = """
        SELECT
            s.stat_id AS statId,
            s.stat_nm AS statNm,
            s.addr AS addr,
            s.lat AS lat,
            s.lng AS lng,
            c.chger_id AS chgerId,
            c.chger_type AS chgerType,
            c.output AS output,
            s.use_time AS useTime,
            s.busi_nm AS busiNm,
            s.parking_free AS parkingFree,
            s.del_yn AS delYn,
            c.fetched_at AS fetchedAt
        FROM chargers c
        JOIN charging_stations s ON s.stat_id = c.stat_id
        ORDER BY s.stat_id, c.chger_id
    """
    with db.get_connection() as conn:
        rows = conn.execute(query).fetchall()
    return [dict(row) for row in rows]


def export_charger_info_csv(*, fetched_at: str | None = None) -> Path:
    """Write today's charger info CSV from the collection DB."""
    rows = _load_info_rows()
    if not rows:
        raise RuntimeError("charger info export failed: DB has no rows")

    now = _now_kst()
    export_date = now.date().isoformat()
    day_dir = DAILY_ROOT / export_date
    day_dir.mkdir(parents=True, exist_ok=True)

    stamp = _stamp(now)
    out_path = day_dir / f"daegu_charger_info_{stamp}.csv"
    latest_path = day_dir / f"daegu_charger_info_{export_date.replace('-', '')}_latest.csv"

    fetched_value = fetched_at or str(rows[0].get("fetchedAt") or now.strftime("%Y-%m-%d %H:%M:%S"))
    for row in rows:
        row["fetchedAt"] = fetched_value

    with out_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=INFO_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    latest_path.write_bytes(out_path.read_bytes())
    _append_index(
        export_date=export_date,
        kind="charger_info",
        path=out_path,
        rows=len(rows),
        fetched_at=fetched_value,
        source="collection.db",
    )
    return out_path


def info_export_exists_for_today() -> bool:
    export_date = _now_kst().date().isoformat()
    day_dir = DAILY_ROOT / export_date
    if not day_dir.exists():
        return False
    return any(day_dir.glob("daegu_charger_info_*.csv"))


def backfill_info_from_extracted() -> list[dict[str, str | int]]:
    """Organize existing flat extracted/info CSVs into daily/ folders."""
    extracted = config.ROOT_DIR / "docs" / "data" / "extracted"
    results: list[dict[str, str | int]] = []
    for source in sorted(extracted.glob("daegu_charger_info_*.csv")):
        parts = source.stem.split("_")
        if len(parts) < 5:
            continue
        ymd = parts[3]
        if len(ymd) != 8 or not ymd.isdigit():
            continue
        export_date = f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:8]}"
        day_dir = DAILY_ROOT / export_date
        day_dir.mkdir(parents=True, exist_ok=True)
        dest = day_dir / source.name
        latest = day_dir / f"daegu_charger_info_{ymd}_latest.csv"
        if not dest.exists():
            dest.write_bytes(source.read_bytes())
        latest.write_bytes(dest.read_bytes())
        row_count = sum(1 for _ in dest.open(encoding="utf-8-sig")) - 1
        _append_index(
            export_date=export_date,
            kind="charger_info",
            path=dest,
            rows=row_count,
            fetched_at=parts[4] if len(parts) > 4 else "",
            source="extracted_backfill",
        )
        results.append(
            {
                "export_date": export_date,
                "path": str(dest),
                "rows": row_count,
            }
        )
    return results


if __name__ == "__main__":
    import json

    print(json.dumps(backfill_info_from_extracted(), ensure_ascii=False, indent=2))
