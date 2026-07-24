"""Load EvCharger info CSV into local Postgres for DBeaver (TEST ONLY).

  set ALLOW_TEST_DB_LOAD=1
  python apps/data-pipeline/processing/db/load_charger_info_to_pg.py
"""
from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import pandas as pd
from dotenv import load_dotenv

_PROCESSING = Path(__file__).resolve().parents[1]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))
from _bootstrap import ensure_paths

REPO = ensure_paths()
from loop_paths import EXTRACTED_CHARGER_INFO, EXTRACTED_DAILY, charger_info_csvs

KST = ZoneInfo("Asia/Seoul")
TABLE = "ev_charger_info"


def _database_url() -> str:
    load_dotenv(REPO / ".env")
    url = os.environ.get("DATABASE_URL", "").strip()
    if url:
        return url
    user = os.environ.get("POSTGRES_USER", "postgres")
    password = os.environ.get("POSTGRES_PASSWORD", "")
    db = os.environ.get("POSTGRES_DB", "ev_safecharge")
    port = os.environ.get("POSTGRES_PORT", "5432")
    if not password:
        raise RuntimeError("DATABASE_URL or POSTGRES_PASSWORD missing in .env")
    return f"postgresql://{user}:{password}@localhost:{port}/{db}"


def _connect(url: str):
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("pip install 'psycopg[binary]' required") from exc
    return psycopg.connect(url)


def _ensure_database(url: str) -> None:
    import psycopg

    parsed = urlparse(url)
    dbname = (parsed.path or "/ev_safecharge").lstrip("/") or "ev_safecharge"
    admin = parsed._replace(path="/postgres").geturl()
    try:
        with psycopg.connect(admin, connect_timeout=5, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM pg_database WHERE datname=%s", (dbname,))
                if cur.fetchone() is None:
                    cur.execute(f'CREATE DATABASE "{dbname}"')
                    print(f"created database {dbname}", flush=True)
    except Exception as exc:
        print(f"ensure_database skipped: {type(exc).__name__}", flush=True)


def _pick_info_csv() -> Path:
    # prefer explicit env, else service-ready (coord_ok + delYn≠Y), else newest
    override = os.environ.get("CHARGER_INFO_CSV", "").strip()
    if override:
        p = Path(override)
        if not p.is_absolute():
            p = REPO / p
        if not p.exists():
            raise FileNotFoundError(p)
        return p

    service = EXTRACTED_CHARGER_INFO / "daegu_charger_info_service_latest.csv"
    if service.is_file():
        return service

    daily_latest = sorted(EXTRACTED_DAILY.glob("**/daegu_charger_info_*latest.csv"))
    if daily_latest:
        return daily_latest[-1]
    stamped = sorted(EXTRACTED_CHARGER_INFO.glob("daegu_charger_info_*.csv"))
    # avoid picking quarantine/flagged as "latest" by name sort — prefer *_20260723_latest raw
    preferred = EXTRACTED_CHARGER_INFO / "daegu_charger_info_20260723_latest.csv"
    if preferred.is_file():
        return preferred
    if stamped:
        return stamped[-1]
    all_c = charger_info_csvs()
    if not all_c:
        raise FileNotFoundError("no daegu_charger_info_*.csv found")
    return all_c[-1]


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    # keep API column names as text; add load meta
    out = df.copy()
    for c in out.columns:
        out[c] = out[c].astype(str).where(out[c].notna(), None)
        out[c] = out[c].replace({"nan": None, "None": None, "": None})
    # numeric helpers when present
    for col in ("lat", "lng"):
        if col in out.columns:
            out[col] = pd.to_numeric(df[col], errors="coerce")
    return out


def _create_and_load(conn, df: pd.DataFrame, source: Path) -> int:
    cols = list(df.columns)
    # quote identifiers
    col_defs = []
    for c in cols:
        if c in ("lat", "lng"):
            col_defs.append(f'"{c}" DOUBLE PRECISION')
        else:
            col_defs.append(f'"{c}" TEXT')
    col_defs.append('"loaded_at" TIMESTAMPTZ NOT NULL DEFAULT NOW()')
    col_defs.append('"source_file" TEXT')

    with conn.cursor() as cur:
        cur.execute(f'DROP TABLE IF EXISTS "{TABLE}"')
        cur.execute(
            f'CREATE TABLE "{TABLE}" (\n  '
            + ",\n  ".join(col_defs)
            + "\n)"
        )
        cur.execute(
            f'CREATE INDEX IF NOT EXISTS idx_{TABLE}_stat ON "{TABLE}" ("statId")'
        )
        if "chgerId" in cols:
            cur.execute(
                f'CREATE INDEX IF NOT EXISTS idx_{TABLE}_chger ON "{TABLE}" ("statId", "chgerId")'
            )

        insert_cols = cols + ["source_file"]
        placeholders = ", ".join(["%s"] * len(insert_cols))
        quoted = ", ".join(f'"{c}"' for c in insert_cols)
        sql = f'INSERT INTO "{TABLE}" ({quoted}) VALUES ({placeholders})'

        src_name = str(source.relative_to(REPO)).replace("\\", "/") if source.is_relative_to(REPO) else str(source)
        rows = []
        for rec in df.to_dict(orient="records"):
            rows.append(tuple(rec.get(c) for c in cols) + (src_name,))

        # batch
        batch = 1000
        n = 0
        for i in range(0, len(rows), batch):
            cur.executemany(sql, rows[i : i + batch])
            n += len(rows[i : i + batch])
        cur.execute(
            f"COMMENT ON TABLE \"{TABLE}\" IS 'EvCharger getChargerInfo dump for DBeaver (test)'"
        )
    conn.commit()
    return n


def main() -> int:
    if os.environ.get("ALLOW_TEST_DB_LOAD", "").strip() != "1":
        print("REFUSED: set ALLOW_TEST_DB_LOAD=1 to load test DB", flush=True)
        return 2

    csv_path = _pick_info_csv()
    print(f"source={csv_path}", flush=True)
    raw = pd.read_csv(csv_path, dtype=str)
    df = _normalize(raw)
    print(f"rows={len(df)} cols={list(df.columns)[:12]}...", flush=True)

    url = _database_url()
    _ensure_database(url)
    with _connect(url) as conn:
        n = _create_and_load(conn, df, csv_path)
        with conn.cursor() as cur:
            cur.execute(f'SELECT COUNT(*) FROM "{TABLE}"')
            cnt = cur.fetchone()[0]
            cur.execute(
                f'SELECT COUNT(DISTINCT "statId") FROM "{TABLE}"'
                if "statId" in df.columns
                else "SELECT 0"
            )
            stations = cur.fetchone()[0]

    print(
        {
            "ok": True,
            "table": TABLE,
            "inserted": n,
            "count": cnt,
            "stations": stations,
            "source": str(csv_path),
            "loaded_at": datetime.now(KST).isoformat(),
            "dbeaver": {
                "host": "localhost",
                "port": 5432,
                "database": "ev_safecharge",
                "table": TABLE,
            },
        },
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
