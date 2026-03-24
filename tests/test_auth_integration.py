import pytest
from fastapi.testclient import TestClient

import db as db_module
from app import app
from db import init_db, get_setting, get_session


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DATABASE_PATH", db_path)
    init_db()
    yield


@pytest.fixture
def client():
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# ---- helpers ----

def _register(client, username="alice", password="password123", invite_code=None):
    if invite_code is None:
        invite_code = get_setting("invite_code")
    return client.post("/api/auth/register", json={
        "username": username,
        "password": password,
        "invite_code": invite_code,
    })


def _login(client, username="alice", password="password123"):
    return client.post("/api/auth/login", json={
        "username": username,
        "password": password,
    })


def _make_class(client):
    """Create a class and return its class_id. Client must already be authenticated."""
    res = client.post("/api/classes", json={"name": "Test Class"})
    return res.json()["class_id"]


# ---- register ----

def test_register_happy_path(client):
    res = _register(client)
    assert res.status_code == 200
    assert res.json() == {"ok": True}
    assert "session_token" in res.cookies


def test_register_wrong_invite_code(client):
    res = _register(client, invite_code="WRONGCOD")
    assert res.status_code == 400


def test_register_duplicate_username(client):
    _register(client)
    res = _register(client)
    assert res.status_code == 400


def test_register_password_too_short(client):
    res = _register(client, password="short")
    assert res.status_code == 400


def test_register_password_too_long(client):
    res = _register(client, password="x" * 73)
    assert res.status_code == 400


# ---- login ----

def test_login_happy_path(client):
    _register(client)
    client.cookies.clear()
    res = _login(client)
    assert res.status_code == 200
    assert "session_token" in res.cookies


def test_login_wrong_password(client):
    _register(client)
    res = _login(client, password="wrongpassword")
    assert res.status_code == 401


def test_login_unknown_user(client):
    res = _login(client, username="nobody")
    assert res.status_code == 401


def test_login_invalidates_previous_session(client):
    _register(client)
    res1 = _login(client)
    old_token = res1.cookies["session_token"]
    _login(client)  # second login replaces all sessions
    assert get_session(old_token) is None


# ---- me ----

def test_me_returns_username(client):
    _register(client)  # client now has session cookie
    res = client.get("/api/auth/me")
    assert res.status_code == 200
    assert res.json()["username"] == "alice"


def test_me_without_session_returns_401(client):
    res = client.get("/api/auth/me")
    assert res.status_code == 401


# ---- protected HTML route ----

def test_instructor_page_without_session_redirects(client):
    res = client.get("/instructor", follow_redirects=False)
    assert res.status_code == 302
    assert "/login" in res.headers["location"]


def test_instructor_page_with_session_returns_200(client):
    _register(client)
    res = client.get("/instructor")
    assert res.status_code == 200


# ---- protected API routes ----

def test_create_question_without_session_returns_401(client):
    res = client.post("/api/questions", json={
        "title": "T", "prompt": "P", "model_answer": "A", "rubric": "", "class_id": "dummy-id"
    })
    assert res.status_code == 401


def test_delete_question_without_session_returns_401(client):
    res = client.delete("/api/questions/some-id")
    assert res.status_code == 401


def test_update_question_without_session_returns_401(client):
    res = client.put("/api/questions/some-id", json={"title": "New"})
    assert res.status_code == 401


def test_get_question_detail_without_session_returns_401(client):
    res = client.get("/api/questions/detail/some-id")
    assert res.status_code == 401


def test_get_question_detail_missing_question_returns_404(client):
    _register(client)
    res = client.get("/api/questions/detail/no-such-id")
    assert res.status_code == 404


# ---- session sliding window ----

def test_session_expiry_is_renewed_on_authenticated_request(client):
    """Hitting a protected endpoint slides the 7-day expiry window."""
    from datetime import datetime, timedelta, timezone
    from db import get_session as db_get_session, get_user_by_username, update_session_expiry

    _register(client)
    token = client.cookies["session_token"]
    # Shorten expiry to 1 hour from now
    now = datetime.now(timezone.utc)
    short_expiry = (now + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    update_session_expiry(token, short_expiry)

    # Hit a protected endpoint
    client.get("/api/auth/me")

    # Expiry should now be approximately 7 days from now
    session = db_get_session(token)
    assert session is not None
    renewed = datetime.strptime(session["expires_at"], "%Y-%m-%d %H:%M:%S")
    assert renewed > datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=6)


# ---- logout ----

def test_logout_clears_session(client):
    _register(client)
    client.post("/logout", follow_redirects=False)
    res = client.get("/instructor", follow_redirects=False)
    assert res.status_code == 302


# ---- settings ----

def test_get_invite_code_without_auth(client):
    res = client.get("/api/settings/invite-code")
    assert res.status_code == 401


def test_get_invite_code_with_auth(client):
    _register(client)
    res = client.get("/api/settings/invite-code")
    assert res.status_code == 200
    data = res.json()
    assert "invite_code" in data
    assert len(data["invite_code"]) == 8


def test_put_invite_code_without_auth(client):
    res = client.put("/api/settings/invite-code", json={"code": "NEWCODE1"})
    assert res.status_code == 401


def test_put_invite_code_with_explicit_code(client):
    _register(client)
    res = client.put("/api/settings/invite-code", json={"code": "NEWCODE1"})
    assert res.status_code == 200
    assert res.json()["invite_code"] == "NEWCODE1"


def test_put_invite_code_auto_generates(client):
    _register(client)
    res = client.put("/api/settings/invite-code", json={})
    assert res.status_code == 200
    new_code = res.json()["invite_code"]
    assert len(new_code) == 8
