"""
Database driver abstraction.

Provides get_conn() returning a connection that:
  - accepts %s placeholders in all execute() calls
  - returns rows as plain dicts from fetchone() / fetchall()
  - works with both SQLite (development/test) and PostgreSQL (production)

Set DATABASE_URL to a postgresql:// URI to use PostgreSQL.
Leave it blank (or set DATABASE_PATH) for SQLite.
"""
import sqlite3
from config import DATABASE_PATH, DATABASE_URL

IS_POSTGRES = DATABASE_URL.startswith("postgresql") or DATABASE_URL.startswith("postgres")


# ── SQLite compat layer ───────────────────────────────────────────────────────

class _SQLiteCursor:
    """Wraps sqlite3.Cursor; converts %s → ? and returns rows as dicts."""

    def __init__(self, raw):
        self._raw = raw

    def fetchone(self):
        row = self._raw.fetchone()
        return dict(row) if row is not None else None

    def fetchall(self):
        return [dict(r) for r in self._raw.fetchall()]

    @property
    def lastrowid(self):
        return self._raw.lastrowid

    @property
    def rowcount(self):
        return self._raw.rowcount


class _SQLiteConn:
    """Wraps sqlite3.Connection; accepts %s placeholders."""

    def __init__(self, path):
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")

    def execute(self, sql, params=()):
        return _SQLiteCursor(self._conn.execute(sql.replace("%s", "?"), params))

    def executemany(self, sql, seq):
        self._conn.executemany(sql.replace("%s", "?"), seq)

    def executescript(self, script):
        return self._conn.executescript(script)

    # sqlite3-specific: used by init_db() migrations only
    def execute_raw(self, sql, params=()):
        """Execute without placeholder conversion — for PRAGMA statements."""
        return self._conn.execute(sql, params)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


# ── PostgreSQL layer ──────────────────────────────────────────────────────────

class _PGConn:
    """Wraps psycopg2 connection; rows returned as dicts via RealDictCursor."""

    def __init__(self, url):
        import psycopg2
        import psycopg2.extras
        self._psycopg2 = psycopg2
        self._extras = psycopg2.extras
        self._conn = psycopg2.connect(url)
        self._conn.autocommit = False

    def execute(self, sql, params=()):
        cur = self._conn.cursor(cursor_factory=self._extras.RealDictCursor)
        cur.execute(sql, params if params else None)
        return cur

    def executemany(self, sql, seq):
        cur = self._conn.cursor()
        cur.executemany(sql, seq)

    def executescript(self, script):
        """Split on ; and execute each statement individually."""
        cur = self._conn.cursor()
        for stmt in script.split(";"):
            stmt = stmt.strip()
            if stmt:
                cur.execute(stmt)

    def execute_raw(self, sql, params=()):
        """Same as execute() — exists for SQLite API compatibility."""
        return self.execute(sql, params)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


# ── Public factory ────────────────────────────────────────────────────────────

def get_conn():
    if IS_POSTGRES:
        return _PGConn(DATABASE_URL)
    import config
    return _SQLiteConn(config.DATABASE_PATH)
