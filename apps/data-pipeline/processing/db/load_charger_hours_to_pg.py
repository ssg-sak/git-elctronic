"""Load charger hours CSV into local Postgres (TEST). Requires ALLOW_TEST_DB_LOAD=1."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

_PROCESSING = Path(__file__).resolve().parents[1]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))
from _bootstrap import ensure_paths

REPO = ensure_paths()


def main() -> int:
    if os.environ.get("ALLOW_TEST_DB_LOAD", "").strip() != "1":
        print("REFUSED: set ALLOW_TEST_DB_LOAD=1")
        return 2
    load_dotenv(REPO / ".env")
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL missing")
    import psycopg

    csv_path = REPO / "docs/data/extracted/charger/hours/daegu_charger_hours_full_latest.csv"
    if not csv_path.is_file():
        csv_path = REPO / "docs/data/extracted/charger/hours/daegu_charger_hours_annotated_latest.csv"
    df = pd.read_csv(csv_path, dtype=str, encoding="utf-8-sig")
    # optional: service targets only
    if "is_service_target" in df.columns:
        before = len(df)
        df = df[df["is_service_target"].astype(str).str.upper().isin(["TRUE", "1", "Y", "YES"])]
        print(f"service filter hours {before} -> {len(df)}", flush=True)
    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS ev_charger_hours")
            cur.execute(
                """
                CREATE TABLE ev_charger_hours (
                    "statId" TEXT PRIMARY KEY,
                    "statNm" TEXT,
                    "useTime" TEXT,
                    is_operating_now TEXT,
                    is_service_target TEXT,
                    loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            has_svc = "is_service_target" in df.columns
            rows = []
            for r in df.itertuples(index=False):
                svc = getattr(r, "is_service_target", None) if has_svc else None
                rows.append((r.statId, r.statNm, r.useTime, r.is_operating_now, str(svc) if svc is not None else None))
            cur.executemany(
                'INSERT INTO ev_charger_hours ("statId","statNm","useTime",is_operating_now,is_service_target) '
                "VALUES (%s,%s,%s,%s,%s)",
                rows,
            )
            cur.execute(
                """
                SELECT COUNT(*),
                       COUNT(*) FILTER (WHERE is_operating_now = 'Y'),
                       COUNT(*) FILTER (WHERE is_operating_now = 'N'),
                       COUNT(*) FILTER (WHERE is_operating_now = 'UNKNOWN')
                FROM ev_charger_hours
                """
            )
            print({"counts_total_Y_N_U": cur.fetchone(), "table": "ev_charger_hours"})
        conn.commit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
