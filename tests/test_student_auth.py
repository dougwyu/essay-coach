# tests/test_student_auth.py
import sqlite3
import pytest
import uuid
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
    create_class,
    create_question,
)
from auth import hash_password
from fastapi.testclient import TestClient
from app import app as fastapi_app


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr("config.DATABASE_PATH", db_path)
    monkeypatch.setattr("db.DATABASE_PATH", db_path)
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
