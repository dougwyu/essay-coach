"""
Shared pytest fixtures.

PostgreSQL isolation: with SQLite each test gets a fresh temp file via monkeypatching
DATABASE_PATH. With PostgreSQL all tests share one database, so we truncate all tables
before each test to achieve the same isolation.

We hold a reference to the original db_connection module object rather than importing
from it inside _truncate_all(), because test_db_connection.py reloads db_connection
(replacing sys.modules['db_connection']) and a bare `from db_connection import get_conn`
inside the function would pick up the reloaded SQLite-mode module.
"""
import pytest
import db_connection as _db_connection

IS_POSTGRES = _db_connection.IS_POSTGRES

_PG_TABLES = [
    # reverse FK dependency order so CASCADE isn't strictly required, but we add it anyway
    "student_question_sessions",
    "student_sessions",
    "student_users",
    "attempts",
    "questions",
    "class_members",
    "classes",
    "sessions",
    "users",
    "settings",
]


@pytest.fixture(autouse=True)
def _pg_reset():
    """Truncate all tables before each test when running against PostgreSQL."""
    if not IS_POSTGRES:
        yield
        return
    _truncate_all()
    yield


def _truncate_all():
    conn = _db_connection.get_conn()
    for table in _PG_TABLES:
        conn.execute(f"TRUNCATE {table} CASCADE")
    conn.commit()
    conn.close()
