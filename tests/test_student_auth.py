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
