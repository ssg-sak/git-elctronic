"""Load SANDBOX status index + D2 panel into local Postgres (DBeaver).

**TEST ONLY.** Not part of ops / server / status loop.
Refuses to run unless ALLOW_TEST_DB_LOAD=1.

  set ALLOW_TEST_DB_LOAD=1
  python apps/data-pipeline/processing/db/load_status_panel_to_pg.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import pandas as pd
from dotenv import load_dotenv

import sys
from pathlib import Path
_PROCESSING = Path(__file__).resolve().parents[1]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))
from _bootstrap import ensure_paths

REPO = ensure_paths()
from loop_paths import LOOP1_INDEX

SQL_PATH = Path(__file__).resolve().parent / "sql" / "init_status_test_schema.sql"
DATASETS = REPO / "apps/data-pipeline/evaluation/results/datasets"
INDEX_CSV = LOOP1_INDEX
KST = ZoneInfo("Asia/Seoul")


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
    """Create target DB if missing (local Postgres)."""
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
        # may lack CREATEDB privilege — load will surface the real error
        print(f"ensure_database skipped: {type(exc).__name__}", flush=True)


def _apply_schema(conn) -> None:
    sql = SQL_PATH.read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()


def _load_schedule(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM meta_collection_schedule")
        cur.executemany(
            """
            INSERT INTO meta_collection_schedule
              (source, interval_minutes, period_minutes, note)
            VALUES (%s, %s, %s, %s)
            """,
            [
                (
                    "sandbox_loop",
                    5,
                    10,
                    "run_loop.py defaults; do not run with collection scheduler same day",
                ),
                (
                    "collection_scheduler",
                    5,
                    10,
                    "collection/scheduler.py IntervalTrigger",
                ),
            ],
        )
    conn.commit()


def _load_ticks(conn) -> int:
    if not INDEX_CSV.exists():
        return 0
    idx = pd.read_csv(INDEX_CSV, dtype=str)
    rows = []
    for r in idx.itertuples(index=False):
        sid = str(getattr(r, "snapshotId", "") or "")
        if not sid:
            continue
        fetched = getattr(r, "fetchedAt", None)
        try:
            ft = pd.to_datetime(fetched) if fetched and str(fetched) != "nan" else None
        except Exception:
            ft = None
        rows.append(
            (
                sid,
                ft.to_pydatetime() if ft is not None and not pd.isna(ft) else None,
                int(float(getattr(r, "rows", 0) or 0)) if str(getattr(r, "rows", "")).strip() else None,
                int(float(getattr(r, "api_calls", 0) or 0))
                if str(getattr(r, "api_calls", "")).strip() not in ("", "nan")
                else None,
                int(float(getattr(r, "period_minutes", 0) or 0))
                if str(getattr(r, "period_minutes", "")).strip() not in ("", "nan")
                else None,
                str(getattr(r, "ok", "True")).lower() in ("true", "1", "yes"),
                str(getattr(r, "path", "") or ""),
            )
        )
    with conn.cursor() as cur:
        cur.execute("DELETE FROM charger_status_tick")
        cur.executemany(
            """
            INSERT INTO charger_status_tick
              (snapshot_id, fetched_at, rows_n, api_calls, period_minutes, ok, path)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            rows,
        )
    conn.commit()
    return len(rows)


def _latest_panel() -> Path:
    pq = DATASETS / "station_feature_panel_latest.parquet"
    if pq.exists():
        return pq
    cands = sorted(DATASETS.glob("station_feature_panel_20*.parquet"))
    if not cands:
        raise FileNotFoundError("no station_feature_panel_*.parquet — run build_d2_panel.py")
    return cands[-1]


def _load_panel(conn, path: Path) -> int:
    df = pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path)
    # normalize columns
    rename = {
        "statId": "stat_id",
        "panel_ts": "panel_ts",
        "known_chargers": "known_chargers",
        "available_count": "available_count",
        "in_use_count": "in_use_count",
        "usable_known": "usable_known",
        "availability_ratio_observed": "availability_ratio_observed",
        "has_confirmed_available": "has_confirmed_available",
        "segment_id": "segment_id",
        "avail_rate_lag_15m": "avail_rate_lag_15m",
        "avail_rate_lag_60m": "avail_rate_lag_60m",
        "schema_version": "schema_version",
        "source_status": "source_status",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
    df["panel_ts"] = pd.to_datetime(df["panel_ts"])
    for c in ("availability_ratio_observed", "avail_rate_lag_15m", "avail_rate_lag_60m"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    if "has_confirmed_available" in df.columns:
        df["has_confirmed_available"] = df["has_confirmed_available"].astype(bool)

    cols = [
        "stat_id",
        "panel_ts",
        "known_chargers",
        "available_count",
        "in_use_count",
        "usable_known",
        "availability_ratio_observed",
        "has_confirmed_available",
        "segment_id",
        "avail_rate_lag_15m",
        "avail_rate_lag_60m",
        "schema_version",
        "source_status",
    ]
    for c in cols:
        if c not in df.columns:
            df[c] = None
    # chunked insert
    with conn.cursor() as cur:
        cur.execute("DELETE FROM station_feature_panel")
    conn.commit()

    batch: list[tuple] = []
    n = 0

    def flush() -> None:
        nonlocal batch, n
        if not batch:
            return
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO station_feature_panel (
                  stat_id, panel_ts, known_chargers, available_count, in_use_count,
                  usable_known, availability_ratio_observed, has_confirmed_available,
                  segment_id, avail_rate_lag_15m, avail_rate_lag_60m,
                  schema_version, source_status
                ) VALUES (
                  %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
                )
                """,
                batch,
            )
        conn.commit()
        n += len(batch)
        batch = []

    for row in df[cols].itertuples(index=False, name=None):
        # convert NaN → None
        clean = []
        for v in row:
            if v is None or (isinstance(v, float) and pd.isna(v)):
                clean.append(None)
            elif hasattr(v, "to_pydatetime"):
                clean.append(v.to_pydatetime())
            else:
                clean.append(v)
        batch.append(tuple(clean))
        if len(batch) >= 5000:
            flush()
    flush()
    return n


def main() -> int:
    if os.environ.get("ALLOW_TEST_DB_LOAD", "").strip() != "1":
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "refused: test DB only",
                    "hint": "완전 테스트용. 운영/루프에 쓰지 않음. 정말 넣을 때만 ALLOW_TEST_DB_LOAD=1",
                },
                ensure_ascii=False,
            )
        )
        return 2

    url = _database_url()
    # redact password in logs
    parsed = urlparse(url)
    safe = f"{parsed.scheme}://{parsed.username}:***@{parsed.hostname}:{parsed.port}{parsed.path}"
    print(f"connecting {safe}", flush=True)
    _ensure_database(url)

    try:
        conn = _connect(url)
    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": str(exc),
                    "hint": "docker compose up -d 후 .env DATABASE_URL 확인. 기존 볼륨이면 비밀번호 불일치 시 docker volume rm 필요할 수 있음",
                },
                ensure_ascii=False,
            )
        )
        return 1

    try:
        _apply_schema(conn)
        _load_schedule(conn)
        n_ticks = _load_ticks(conn)
        panel_path = _latest_panel()
        print(f"loading panel {panel_path.name}…", flush=True)
        n_panel = _load_panel(conn, panel_path)
        meta = {
            "ok": True,
            "loaded_at": datetime.now(tz=KST).isoformat(),
            "ticks": n_ticks,
            "panel_rows": n_panel,
            "panel_file": str(panel_path.relative_to(REPO)).replace("\\", "/"),
            "dbeaver": {
                "host": "localhost",
                "port": 5432,
                "database": "ev_safecharge",
                "user": "postgres",
                "password": "(root .env POSTGRES_PASSWORD)",
                "tables": [
                    "meta_collection_schedule",
                    "charger_status_tick",
                    "station_feature_panel",
                ],
            },
        }
        out = REPO / "apps/data-pipeline/evaluation/results/go_nogo/pg_load_latest.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(meta, ensure_ascii=False, indent=2))
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
