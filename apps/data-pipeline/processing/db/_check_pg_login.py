from __future__ import annotations

import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

import sys
from pathlib import Path
_PROCESSING = Path(__file__).resolve().parents[1]
if str(_PROCESSING) not in sys.path:
    sys.path.insert(0, str(_PROCESSING))
from _bootstrap import ensure_paths

ROOT = ensure_paths()
load_dotenv(ROOT / ".env")


def try_login(user: str, password: str, db: str) -> str:
    url = f"postgresql://{user}:{password}@localhost:5432/{db}"
    try:
        with psycopg.connect(url, connect_timeout=5) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT current_user, current_database()")
                u, d = cur.fetchone()
                cur.execute(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_schema='public'"
                )
                n = cur.fetchone()[0]
        return f"OK user={u} db={d} public_tables={n}"
    except Exception as exc:
        return f"FAIL {type(exc).__name__}: {str(exc)[:160]}"


def main() -> None:
    pw = os.environ.get("POSTGRES_PASSWORD", "")
    user = os.environ.get("POSTGRES_USER", "postgres")
    print("env_user", user)
    print("env_pw_set", bool(pw), "len", len(pw))
    print("postgres/ev_safecharge", try_login(user, pw, "ev_safecharge"))
    print("test/ev_safecharge", try_login("test", pw, "ev_safecharge"))
    print("test/test", try_login("test", "test", "ev_safecharge"))


if __name__ == "__main__":
    main()
