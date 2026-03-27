# tests/test_student_auth.py
import sqlite3
import pytest
import uuid
import config as config_module
from db import (
    init_db,
    create_student_user,
    get_student_by_username,
    get_student_by_email,
    get_student_by_id,
    create_student_session,
    get_student_session,
    update_student_session_expiry,
    delete_student_session,
    get_or_create_question_session,
    start_new_question_session,
    list_question_sessions,
    create_class,
    create_question,
)
from auth import hash_password
from fastapi.testclient import TestClient
from app import app as fastapi_app


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(config_module, "DATABASE_PATH", db_path)
    init_db()
    yield


@pytest.fixture
def client():
    with TestClient(fastapi_app, raise_server_exceptions=True) as c:
        yield c


def _make_class():
    return create_class("BIO101", str(uuid.uuid4())[:8], str(uuid.uuid4())[:8], None)


def _make_question(class_id):
    return create_question("Q1", "Prompt", "Model answer.", None, class_id)


def _register(client, username="alice", email="alice@example.com", password="password1"):
    return client.post("/api/student/auth/register", json={
        "username": username, "email": email, "password": password
    })


# --- DB-layer tests (no HTTP) ---

def test_create_and_get_student_user():
    uid = create_student_user("alice", "alice@example.com", hash_password("password1"))
    user = get_student_by_username("alice")
    assert user is not None
    assert user["username"] == "alice"
    assert user["email"] == "alice@example.com"
    user2 = get_student_by_email("alice@example.com")
    assert user2["id"] == user["id"]
    user3 = get_student_by_id(user["id"])
    assert user3["id"] == user["id"]


# --- Register tests ---

def test_register_success(client):
    res = _register(client)
    assert res.status_code == 200
    data = res.json()
    assert "id" in data
    assert data["username"] == "alice"
    assert "student_session_token" in res.cookies


def test_register_duplicate_username(client):
    _register(client)
    res = _register(client, email="other@example.com")
    assert res.status_code == 400


def test_register_duplicate_email(client):
    _register(client)
    res = _register(client, username="bob")
    assert res.status_code == 400


def test_register_short_password(client):
    res = _register(client, password="short")
    assert res.status_code == 400


# --- Login tests ---

def test_login_by_username(client):
    _register(client)
    res = client.post("/api/student/auth/login", json={
        "username_or_email": "alice", "password": "password1"
    })
    assert res.status_code == 200
    assert "student_session_token" in res.cookies


def test_login_by_email(client):
    _register(client)
    res = client.post("/api/student/auth/login", json={
        "username_or_email": "alice@example.com", "password": "password1"
    })
    assert res.status_code == 200
    assert "student_session_token" in res.cookies


def test_login_wrong_password(client):
    _register(client)
    res = client.post("/api/student/auth/login", json={
        "username_or_email": "alice", "password": "wrongpass"
    })
    assert res.status_code == 401


def test_login_unknown_user(client):
    res = client.post("/api/student/auth/login", json={
        "username_or_email": "nobody", "password": "password1"
    })
    assert res.status_code == 401


# --- Me tests ---

def test_me_authenticated(client):
    _register(client)
    res = client.get("/api/student/auth/me")
    assert res.status_code == 200
    assert res.json()["username"] == "alice"


def test_me_unauthenticated(client):
    res = client.get("/api/student/auth/me")
    assert res.status_code == 401


# --- Logout test ---

def test_logout_clears_session(client):
    _register(client)
    assert client.get("/api/student/auth/me").status_code == 200
    client.post("/api/student/auth/logout")
    assert client.get("/api/student/auth/me").status_code == 401


# --- Session endpoint tests ---

def test_session_endpoint_returns_uuid(client):
    _register(client)
    cid = _make_class()
    qid = _make_question(cid)
    res = client.get(f"/api/student/session/{qid}")
    assert res.status_code == 200
    data = res.json()
    assert "session_id" in data
    # Verify it looks like a UUID
    assert len(data["session_id"]) == 36


def test_session_endpoint_idempotent(client):
    _register(client)
    cid = _make_class()
    qid = _make_question(cid)
    first = client.get(f"/api/student/session/{qid}").json()["session_id"]
    second = client.get(f"/api/student/session/{qid}").json()["session_id"]
    assert first == second


def test_session_endpoint_question_not_found(client):
    _register(client)
    res = client.get("/api/student/session/nonexistent-id")
    assert res.status_code == 404


def test_session_endpoint_unauthenticated(client):
    cid = _make_class()
    qid = _make_question(cid)
    res = client.get(f"/api/student/session/{qid}")
    assert res.status_code == 401


# --- Session expiry and sliding window tests ---

def test_expired_session_returns_401(client, tmp_path):
    # Register to get a student_id, then manually insert an expired session
    reg = _register(client)
    student_id = reg.json()["id"]
    expired_token = "expired-token-123"
    create_student_session(expired_token, student_id, "2000-01-01 00:00:00")
    # Use a separate client (no cookie) with the expired token manually set
    with TestClient(fastapi_app, raise_server_exceptions=True) as c2:
        c2.cookies.set("student_session_token", expired_token)
        res = c2.get("/api/student/auth/me")
    assert res.status_code == 401
    # Verify expires_at was NOT updated (must query DB directly using tmp_path)
    db_path = str(tmp_path / "test.db")
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT expires_at FROM student_sessions WHERE token = ?", (expired_token,)
    ).fetchone()
    conn.close()
    assert row is not None
    assert row[0] == "2000-01-01 00:00:00"


def test_valid_session_slides_window(client, tmp_path):
    _register(client)
    db_path = str(tmp_path / "test.db")
    # Read expires_at before the /me call
    conn = sqlite3.connect(db_path)
    row_before = conn.execute(
        "SELECT expires_at FROM student_sessions ORDER BY rowid DESC LIMIT 1"
    ).fetchone()
    conn.close()
    before = row_before[0]
    # Small delay to ensure the new timestamp is strictly greater
    import time; time.sleep(1)
    res = client.get("/api/student/auth/me")
    assert res.status_code == 200
    conn = sqlite3.connect(db_path)
    row_after = conn.execute(
        "SELECT expires_at FROM student_sessions ORDER BY rowid DESC LIMIT 1"
    ).fetchone()
    conn.close()
    after = row_after[0]
    assert after > before


# --- Migration test (does NOT use fresh_db autouse fixture) ---

@pytest.fixture
def old_schema_db(tmp_path, monkeypatch):
    """Creates a database with the old student_question_sessions schema (no session_number)."""
    db_path = str(tmp_path / "old.db")
    monkeypatch.setattr(config_module, "DATABASE_PATH", db_path)
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE student_users (
            id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE questions (
            id TEXT PRIMARY KEY, title TEXT NOT NULL, prompt TEXT NOT NULL,
            model_answer TEXT NOT NULL, rubric TEXT, class_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE student_question_sessions (
            id TEXT PRIMARY KEY,
            student_id TEXT NOT NULL, question_id TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(student_id, question_id)
        );
        INSERT INTO student_question_sessions (id, student_id, question_id)
            VALUES ('old-session-id', 'student-1', 'question-1');
    """)
    conn.close()
    yield db_path


def test_migration_adds_session_number(old_schema_db):
    init_db()
    conn = sqlite3.connect(old_schema_db)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(student_question_sessions)").fetchall()]
    assert "session_number" in cols
    row = conn.execute(
        "SELECT session_number FROM student_question_sessions WHERE id = 'old-session-id'"
    ).fetchone()
    assert row[0] == 1
    conn.close()


# --- Multi-session DB tests ---

def test_start_new_session_returns_different_id():
    cid = _make_class()
    qid = _make_question(cid)
    uid = create_student_user("alice", "alice@example.com", hash_password("p"))
    sid1 = get_or_create_question_session(uid, qid)
    sid2, num = start_new_question_session(uid, qid)
    assert sid1 != sid2
    assert num == 2


def test_list_question_sessions_returns_all():
    cid = _make_class()
    qid = _make_question(cid)
    uid = create_student_user("alice", "alice@example.com", hash_password("p"))
    get_or_create_question_session(uid, qid)
    start_new_question_session(uid, qid)
    sessions = list_question_sessions(uid, qid)
    assert len(sessions) == 2
    assert sessions[0]["session_number"] == 1
    assert sessions[1]["session_number"] == 2


def test_get_or_create_returns_latest_after_new():
    cid = _make_class()
    qid = _make_question(cid)
    uid = create_student_user("alice", "alice@example.com", hash_password("p"))
    get_or_create_question_session(uid, qid)
    sid2, _ = start_new_question_session(uid, qid)
    active = get_or_create_question_session(uid, qid)
    assert active == sid2


# --- Multi-session HTTP tests ---

def test_api_start_new_session_returns_different_id(client):
    _register(client)
    cid = _make_class()
    qid = _make_question(cid)
    first = client.get(f"/api/student/session/{qid}").json()["session_id"]
    res = client.post(f"/api/student/session/{qid}/new")
    assert res.status_code == 200
    data = res.json()
    assert "session_id" in data
    assert data["session_id"] != first


def test_api_start_new_session_increments_number(client):
    _register(client)
    cid = _make_class()
    qid = _make_question(cid)
    client.get(f"/api/student/session/{qid}")  # creates session_number=1
    res = client.post(f"/api/student/session/{qid}/new")
    assert res.json()["session_number"] == 2


def test_api_list_sessions_returns_all_in_order(client):
    _register(client)
    cid = _make_class()
    qid = _make_question(cid)
    client.get(f"/api/student/session/{qid}")       # session 1
    client.post(f"/api/student/session/{qid}/new")  # session 2
    res = client.get(f"/api/student/session/{qid}/list")
    assert res.status_code == 200
    sessions = res.json()
    assert len(sessions) == 2
    assert sessions[0]["session_number"] == 1
    assert sessions[1]["session_number"] == 2


def test_api_active_session_is_latest(client):
    _register(client)
    cid = _make_class()
    qid = _make_question(cid)
    client.get(f"/api/student/session/{qid}")           # session 1
    new_data = client.post(f"/api/student/session/{qid}/new").json()  # session 2
    active = client.get(f"/api/student/session/{qid}").json()["session_id"]
    assert active == new_data["session_id"]


def test_api_attempts_isolated_between_sessions(client):
    _register(client)
    cid = _make_class()
    qid = _make_question(cid)
    sid1 = client.get(f"/api/student/session/{qid}").json()["session_id"]
    sid2 = client.post(f"/api/student/session/{qid}/new").json()["session_id"]
    # Insert a real attempt directly into the DB for session 1
    from db import _connect
    conn = _connect()
    import uuid as _uuid
    conn.execute(
        "INSERT INTO attempts (id, question_id, session_id, student_answer, feedback, attempt_number)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (str(_uuid.uuid4()), qid, sid1, "My answer", "Some feedback", 1),
    )
    conn.commit()
    conn.close()
    # Session 1 should show the attempt
    res1 = client.get(f"/api/attempts/{qid}?session_id={sid1}")
    assert res1.status_code == 200
    assert len(res1.json()["attempts"]) == 1
    # Session 2 must NOT show session 1's attempt
    res2 = client.get(f"/api/attempts/{qid}?session_id={sid2}")
    assert res2.status_code == 200
    assert res2.json()["attempts"] == []


def test_api_list_sessions_empty_returns_200(client):
    _register(client)
    cid = _make_class()
    qid = _make_question(cid)
    # Do NOT call GET /api/student/session/{qid} — that would create a session
    res = client.get(f"/api/student/session/{qid}/list")
    assert res.status_code == 200
    assert res.json() == []


def test_api_new_session_unauthenticated_returns_401(client):
    cid = _make_class()
    qid = _make_question(cid)
    res = client.post(f"/api/student/session/{qid}/new")
    assert res.status_code == 401


def test_api_list_sessions_unauthenticated_returns_401(client):
    cid = _make_class()
    qid = _make_question(cid)
    res = client.get(f"/api/student/session/{qid}/list")
    assert res.status_code == 401


def test_api_new_session_unknown_question_returns_404(client):
    _register(client)
    res = client.post("/api/student/session/nonexistent-id/new")
    assert res.status_code == 404


def test_api_list_sessions_unknown_question_returns_404(client):
    _register(client)
    res = client.get("/api/student/session/nonexistent-id/list")
    assert res.status_code == 404
