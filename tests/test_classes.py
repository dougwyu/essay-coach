import pytest
import config as config_module
from db import init_db, create_question, get_question, list_questions
from db_connection import IS_POSTGRES
from db import (
    create_class,
    get_class,
    get_class_by_student_code,
    get_class_by_instructor_code,
    list_classes_for_user,
    add_class_member,
    is_class_member,
    get_class_question_count,
    update_class_student_code,
    update_class_instructor_code,
    create_user,
)


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(config_module, "DATABASE_PATH", db_path)
    init_db()
    yield


@pytest.mark.skipif(IS_POSTGRES, reason="SQLite schema introspection only")
def test_classes_table_exists():
    """init_db creates the classes table."""
    import sqlite3
    conn = sqlite3.connect(config_module.DATABASE_PATH)
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='classes'"
    ).fetchone()
    conn.close()
    assert row is not None


@pytest.mark.skipif(IS_POSTGRES, reason="SQLite schema introspection only")
def test_class_members_table_exists():
    import sqlite3
    conn = sqlite3.connect(config_module.DATABASE_PATH)
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='class_members'"
    ).fetchone()
    conn.close()
    assert row is not None


@pytest.mark.skipif(IS_POSTGRES, reason="SQLite schema introspection only")
def test_questions_has_class_id_column():
    import sqlite3
    conn = sqlite3.connect(config_module.DATABASE_PATH)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(questions)").fetchall()]
    conn.close()
    assert "class_id" in cols


@pytest.mark.skipif(IS_POSTGRES, reason="SQLite-only migration test")
def test_migration_assigns_default_class_to_existing_questions(tmp_path, monkeypatch):
    """Simulates a pre-Phase-3 DB: questions without class_id get assigned to Default class."""
    import sqlite3
    db_path = str(tmp_path / "migrate.db")
    monkeypatch.setattr(config_module, "DATABASE_PATH", db_path)

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


@pytest.mark.skipif(IS_POSTGRES, reason="SQLite-only migration test")
def test_migration_idempotent(tmp_path, monkeypatch):
    """Running init_db() twice after a migration creates exactly one Default class, not two."""
    import sqlite3
    db_path = str(tmp_path / "idem.db")
    monkeypatch.setattr(config_module, "DATABASE_PATH", db_path)

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


def _make_class(name="BIO101", s="STUD0001", i="INST0001", created_by=None):
    return create_class(name, s, i, created_by)


def test_create_class_and_get():
    cid = _make_class()
    c = get_class(cid)
    assert c["name"] == "BIO101"
    assert c["student_code"] == "STUD0001"
    assert c["instructor_code"] == "INST0001"


def test_get_class_returns_none_for_missing():
    assert get_class("nonexistent") is None


def test_get_class_by_student_code():
    cid = _make_class()
    c = get_class_by_student_code("STUD0001")
    assert c["id"] == cid


def test_get_class_by_student_code_missing():
    assert get_class_by_student_code("XXXXXXXX") is None


def test_get_class_by_instructor_code():
    cid = _make_class()
    c = get_class_by_instructor_code("INST0001")
    assert c["id"] == cid


def test_get_class_by_instructor_code_missing():
    assert get_class_by_instructor_code("XXXXXXXX") is None


def test_add_class_member_and_is_member():
    uid = create_user("bob", "hash")
    cid = _make_class()
    assert not is_class_member(cid, uid)
    add_class_member(cid, uid)
    assert is_class_member(cid, uid)


def test_list_classes_for_user():
    uid = create_user("carol", "hash")
    cid1 = create_class("Math", "STUD0002", "INST0002", uid)
    cid2 = create_class("Sci", "STUD0003", "INST0003", uid)
    add_class_member(cid1, uid)
    add_class_member(cid2, uid)
    classes = list_classes_for_user(uid)
    ids = {c["id"] for c in classes}
    assert cid1 in ids and cid2 in ids


def test_list_classes_for_user_empty():
    uid = create_user("dave", "hash")
    assert list_classes_for_user(uid) == []


def test_get_class_question_count():
    cid = _make_class("Physics", "STUD0004", "INST0004")
    assert get_class_question_count(cid) == 0
    create_question("Q1", "P", "A", "", cid)
    create_question("Q2", "P", "A", "", cid)
    assert get_class_question_count(cid) == 2


def test_update_class_student_code():
    cid = _make_class("X", "STUD0005", "INST0005")
    update_class_student_code(cid, "NEWSTUD1")
    c = get_class(cid)
    assert c["student_code"] == "NEWSTUD1"


def test_update_class_instructor_code():
    cid = _make_class("Y", "STUD0006", "INST0006")
    update_class_instructor_code(cid, "NEWINST1")
    c = get_class(cid)
    assert c["instructor_code"] == "NEWINST1"
