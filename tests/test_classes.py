import pytest
import db as db_module
from db import init_db, create_question, get_question, list_questions


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DATABASE_PATH", db_path)
    init_db()
    yield


def test_classes_table_exists():
    """init_db creates the classes table."""
    import sqlite3
    conn = sqlite3.connect(db_module.DATABASE_PATH)
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='classes'"
    ).fetchone()
    conn.close()
    assert row is not None


def test_class_members_table_exists():
    import sqlite3
    conn = sqlite3.connect(db_module.DATABASE_PATH)
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='class_members'"
    ).fetchone()
    conn.close()
    assert row is not None


def test_questions_has_class_id_column():
    import sqlite3
    conn = sqlite3.connect(db_module.DATABASE_PATH)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(questions)").fetchall()]
    conn.close()
    assert "class_id" in cols


def test_migration_assigns_default_class_to_existing_questions(tmp_path, monkeypatch):
    """Simulates a pre-Phase-3 DB: questions without class_id get assigned to Default class."""
    import sqlite3
    db_path = str(tmp_path / "migrate.db")
    monkeypatch.setattr(db_module, "DATABASE_PATH", db_path)

    # Create old schema (no class_id on questions, no classes table)
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE questions (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            prompt TEXT NOT NULL,
            model_answer TEXT NOT NULL,
            rubric TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE users (
            id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE sessions (
            token TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            expires_at TIMESTAMP NOT NULL
        );
        CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT INTO questions (id, title, prompt, model_answer) VALUES
            ('q1', 'Q1', 'P1', 'A1'),
            ('q2', 'Q2', 'P2', 'A2');
        INSERT INTO users (id, username, password_hash) VALUES
            ('u1', 'alice', 'hash');
    """)
    conn.commit()
    conn.close()

    init_db()  # should run migration

    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT class_id FROM questions").fetchall()
    conn.close()
    assert all(r[0] is not None for r in rows), "All questions should have a class_id after migration"
    assert len(set(r[0] for r in rows)) == 1, "All questions should share one Default class"


def test_migration_idempotent(tmp_path, monkeypatch):
    """Running init_db() twice after a migration creates exactly one Default class, not two."""
    import sqlite3
    db_path = str(tmp_path / "idem.db")
    monkeypatch.setattr(db_module, "DATABASE_PATH", db_path)

    # Build old-schema DB with orphan questions (same as migration test)
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE questions (
            id TEXT PRIMARY KEY, title TEXT NOT NULL, prompt TEXT NOT NULL,
            model_answer TEXT NOT NULL, rubric TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE users (id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE sessions (token TEXT PRIMARY KEY, user_id TEXT NOT NULL, expires_at TIMESTAMP NOT NULL);
        CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT INTO questions (id, title, prompt, model_answer) VALUES ('q1', 'Q', 'P', 'A');
    """)
    conn.commit()
    conn.close()

    init_db()  # first call — triggers migration, creates Default class
    init_db()  # second call — should NOT create another Default class

    conn = sqlite3.connect(db_path)
    count = conn.execute("SELECT COUNT(*) FROM classes WHERE name = 'Default'").fetchone()[0]
    conn.close()
    assert count == 1, f"Expected exactly 1 Default class, got {count}"
