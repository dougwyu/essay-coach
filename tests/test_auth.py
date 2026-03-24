import pytest
from datetime import datetime, timedelta, timezone

import db as db_module
from db import (
    init_db,
    create_user,
    get_user_by_username,
    get_user_by_id,
    create_session,
    get_session,
    update_session_expiry,
    delete_session,
    delete_sessions_for_user,
    get_setting,
    set_setting,
)


@pytest.fixture(autouse=True)
def test_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DATABASE_PATH", db_path)
    init_db()
    yield db_path


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _future(days: int = 7) -> str:
    return (_now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")


def _past(days: int = 1) -> str:
    return (_now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")


# --- users ---

def test_create_and_get_user_by_username():
    uid = create_user("alice", "hashed_pw")
    user = get_user_by_username("alice")
    assert user is not None
    assert user["id"] == uid
    assert user["username"] == "alice"
    assert user["password_hash"] == "hashed_pw"


def test_get_user_by_id():
    uid = create_user("bob", "hashed_pw")
    user = get_user_by_id(uid)
    assert user is not None
    assert user["username"] == "bob"


def test_get_user_by_username_missing_returns_none():
    assert get_user_by_username("nobody") is None


def test_get_user_by_id_missing_returns_none():
    assert get_user_by_id("no-such-id") is None


def test_create_user_duplicate_username_raises():
    create_user("alice", "pw1")
    with pytest.raises(Exception):
        create_user("alice", "pw2")


# --- sessions ---

def test_create_and_get_session():
    uid = create_user("alice", "pw")
    create_session("tok123", uid, _future())
    session = get_session("tok123")
    assert session is not None
    assert session["user_id"] == uid


def test_get_session_expired_returns_none():
    uid = create_user("alice", "pw")
    create_session("old_tok", uid, _past())
    assert get_session("old_tok") is None


def test_get_session_missing_returns_none():
    assert get_session("no_such_token") is None


def test_update_session_expiry():
    uid = create_user("alice", "pw")
    create_session("tok", uid, _past())
    assert get_session("tok") is None  # expired
    update_session_expiry("tok", _future())
    assert get_session("tok") is not None  # renewed


def test_delete_session():
    uid = create_user("alice", "pw")
    create_session("tok", uid, _future())
    delete_session("tok")
    assert get_session("tok") is None


def test_delete_sessions_for_user_removes_all():
    uid = create_user("alice", "pw")
    create_session("tok1", uid, _future())
    create_session("tok2", uid, _future())
    delete_sessions_for_user(uid)
    assert get_session("tok1") is None
    assert get_session("tok2") is None


# --- settings ---

def test_invite_code_seeded_on_init():
    code = get_setting("invite_code")
    assert code is not None
    assert len(code) == 8
    valid = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")
    assert all(c in valid for c in code)


def test_set_and_get_setting():
    set_setting("invite_code", "NEWCODE1")
    assert get_setting("invite_code") == "NEWCODE1"


def test_get_setting_missing_returns_none():
    assert get_setting("no_such_key") is None
