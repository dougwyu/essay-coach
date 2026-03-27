import os
import pytest


def _get_module(monkeypatch, database_url=""):
    import sys
    for key in list(sys.modules):
        if key in ("db_connection", "config"):
            del sys.modules[key]
    monkeypatch.setenv("DATABASE_URL", database_url)
    import db_connection
    return db_connection


def test_sqlite_placeholder(monkeypatch, tmp_path):
    mod = _get_module(monkeypatch, "")
    monkeypatch.setattr("config.DATABASE_PATH", str(tmp_path / "t.db"))
    conn = mod.get_conn()
    conn.execute("CREATE TABLE t (x TEXT)")
    conn.execute("INSERT INTO t VALUES (%s)", ("hello",))
    conn.commit()
    row = conn.execute("SELECT x FROM t").fetchone()
    conn.close()
    assert row["x"] == "hello"


def test_sqlite_fetchall(monkeypatch, tmp_path):
    mod = _get_module(monkeypatch, "")
    monkeypatch.setattr("config.DATABASE_PATH", str(tmp_path / "t2.db"))
    conn = mod.get_conn()
    conn.execute("CREATE TABLE t (x TEXT)")
    conn.execute("INSERT INTO t VALUES (%s)", ("a",))
    conn.execute("INSERT INTO t VALUES (%s)", ("b",))
    conn.commit()
    rows = conn.execute("SELECT x FROM t ORDER BY x").fetchall()
    conn.close()
    assert [r["x"] for r in rows] == ["a", "b"]


def test_sqlite_fetchone_none(monkeypatch, tmp_path):
    mod = _get_module(monkeypatch, "")
    monkeypatch.setattr("config.DATABASE_PATH", str(tmp_path / "t3.db"))
    conn = mod.get_conn()
    conn.execute("CREATE TABLE t (x TEXT)")
    conn.commit()
    row = conn.execute("SELECT x FROM t").fetchone()
    conn.close()
    assert row is None


def test_is_postgres_false_by_default(monkeypatch):
    mod = _get_module(monkeypatch, "")
    assert mod.IS_POSTGRES is False


def test_is_postgres_true_for_pg_url(monkeypatch):
    mod = _get_module(monkeypatch, "postgresql://u:p@localhost/db")
    assert mod.IS_POSTGRES is True
