# -*- coding: utf-8 -*-
"""Inspect team_5 (HeidiSQL shared) for parking tables. No password printed."""
from __future__ import annotations

import os
import sys
import winreg
from pathlib import Path

from dotenv import load_dotenv

REPO = Path(__file__).resolve().parents[4]
load_dotenv(REPO / ".env")

SESSION = r"Software\HeidiSQL\Servers\Unnamed-1"
DB = "team_5"


def heidi_conn() -> tuple[str, int, str, str]:
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, SESSION)
    host = winreg.QueryValueEx(key, "Host")[0]
    port = int(winreg.QueryValueEx(key, "Port")[0])
    user = winreg.QueryValueEx(key, "User")[0]
    pwd = winreg.QueryValueEx(key, "Password")[0]
    return host, port, user, str(pwd)


def password_candidates(heidi_pwd: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for k in (
        "TEAM5_DB_PASSWORD",
        "TEAM_5_DB_PASSWORD",
        "MYSQL_PASSWORD",
        "TEAM5_PASSWORD",
        "EV_MODEL_READER_PASSWORD",
        "DB_PASSWORD",
        "TEAM_DB_PASSWORD",
    ):
        v = os.getenv(k)
        if v:
            out.append((f"env:{k}", v))
    if heidi_pwd:
        out.append(("heidi_reg", heidi_pwd))
    out.append(("empty", ""))
    return out


def main() -> int:
    try:
        import pymysql
    except ImportError:
        import subprocess

        subprocess.check_call([sys.executable, "-m", "pip", "install", "pymysql", "-q"])
        import pymysql

    host, port, user, heidi_pwd = heidi_conn()
    print(f"target host={host} port={port} user={user} db={DB}")

    conn = None
    used = None
    last = None
    for label, pwd in password_candidates(heidi_pwd):
        try:
            conn = pymysql.connect(
                host=host,
                port=port,
                user=user,
                password=pwd,
                database=DB,
                connect_timeout=10,
                read_timeout=60,
                charset="utf8mb4",
            )
            used = label
            break
        except Exception as exc:  # noqa: BLE001
            last = f"{label}:{type(exc).__name__}"
            print("auth_fail", last)

    if conn is None:
        print("CONNECT_FAILED", last)
        print("HINT: set TEAM5_DB_PASSWORD in .env (HeidiSQL password for ev_model_reader)")
        return 2

    print("CONNECTED via", used)
    cur = conn.cursor()
    cur.execute("SHOW TABLES")
    tables = [r[0] for r in cur.fetchall()]
    print("TABLE_COUNT", len(tables))
    for t in sorted(tables):
        print("TABLE", t)

    park = [
        t
        for t in tables
        if any(x in t.lower() for x in ("park", "prk", "pis", "kotsa", "주차"))
    ]
    print("PARKING_LIKE_TABLES", park)

    cur.execute(
        """
        SELECT TABLE_NAME, COLUMN_NAME
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA=%s
          AND (
            LOWER(TABLE_NAME) LIKE %s OR LOWER(TABLE_NAME) LIKE %s
            OR LOWER(COLUMN_NAME) LIKE %s OR LOWER(COLUMN_NAME) LIKE %s
            OR LOWER(COLUMN_NAME) LIKE %s
          )
        ORDER BY TABLE_NAME, ORDINAL_POSITION
        """,
        (DB, "%park%", "%prk%", "%park%", "%prk%", "%remain%"),
    )
    hits = cur.fetchall()
    print("SCHEMA_HITS", len(hits))
    for tn, cn in hits[:80]:
        print(f"COL {tn}.{cn}")

    for t in park:
        cur.execute(f"SELECT COUNT(*) FROM `{t}`")
        n = cur.fetchone()[0]
        cur.execute(f"SHOW COLUMNS FROM `{t}`")
        cols = [r[0] for r in cur.fetchall()]
        print(f"STATS {t} rows={n} ncols={len(cols)}")
        print("COLS", ",".join(cols[:30]))
        cur.execute(f"SELECT * FROM `{t}` LIMIT 2")
        rows = cur.fetchall()
        print("SAMPLE_N", len(rows))

    # if no park table name, still summarize any table with parking-ish columns
    if not park and hits:
        names = sorted({t for t, _ in hits})
        for t in names:
            cur.execute(f"SELECT COUNT(*) FROM `{t}`")
            print(f"RELATED {t} rows={cur.fetchone()[0]}")

    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
