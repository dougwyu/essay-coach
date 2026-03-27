#!/usr/bin/env python3
"""
One-time migration: SQLite → PostgreSQL

Usage:
    SQLITE_PATH=/path/to/essay_coach.db \
    DATABASE_URL=postgresql://essay_coach:password@localhost:5432/essay_coach \
    python scripts/migrate_to_postgres.py

Run AFTER `docker compose up -d` has started the app once
(so that init_db() has already created the PostgreSQL schema).
"""
import os
import sqlite3
import sys

import psycopg2

SQLITE_PATH = os.environ.get("SQLITE_PATH")
DATABASE_URL = os.environ.get("DATABASE_URL")

if not SQLITE_PATH or not DATABASE_URL:
    print("ERROR: Set SQLITE_PATH and DATABASE_URL environment variables.")
    sys.exit(1)

# Tables must be inserted in this order to satisfy foreign key constraints.
TABLES = [
    "users",
    "sessions",
    "settings",
    "student_users",
    "student_sessions",
    "classes",
    "class_members",
    "questions",
    "student_question_sessions",
    "attempts",
]


def migrate():
    src = sqlite3.connect(SQLITE_PATH)
    src.row_factory = sqlite3.Row
    dst = psycopg2.connect(DATABASE_URL)
    dst.autocommit = False

    try:
        cur = dst.cursor()
        for table in TABLES:
            rows = src.execute(f"SELECT * FROM {table}").fetchall()
            if not rows:
                print(f"  {table}: 0 rows — skipped")
                continue

            row_dicts = [dict(r) for r in rows]
            cols = list(row_dicts[0].keys())
            col_names = ", ".join(cols)
            placeholders = ", ".join(["%s"] * len(cols))
            values = [tuple(r[c] for c in cols) for r in row_dicts]

            cur.executemany(
                f"INSERT INTO {table} ({col_names}) VALUES ({placeholders}) ON CONFLICT DO NOTHING",
                values,
            )
            print(f"  {table}: {len(values)} rows migrated")

        dst.commit()
        print("\nMigration complete.")
    except Exception as exc:
        dst.rollback()
        print(f"\nMigration FAILED: {exc}")
        raise
    finally:
        src.close()
        dst.close()


if __name__ == "__main__":
    migrate()
