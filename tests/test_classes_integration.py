import pytest
from fastapi.testclient import TestClient

import db as db_module
from app import app
from db import init_db, get_setting, create_class, add_class_member


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
    res = client.post("/api/auth/register", json={
        "username": username, "password": password, "invite_code": invite_code,
    })
    assert res.status_code == 200
    return res


def _auth_client(client, username="alice"):
    _register(client, username=username)
    return client  # cookies are set on the TestClient


# ---- POST /api/classes ----

def test_create_class_happy_path(client):
    _auth_client(client)
    res = client.post("/api/classes", json={"name": "BIO101"})
    assert res.status_code == 200
    data = res.json()
    assert "class_id" in data
    assert data["name"] == "BIO101"
    assert len(data["student_code"]) == 8
    assert len(data["instructor_code"]) == 8


def test_create_class_creator_is_member(client):
    _auth_client(client)
    res = client.post("/api/classes", json={"name": "BIO101"})
    class_id = res.json()["class_id"]
    from db import get_user_by_username, is_class_member
    user = get_user_by_username("alice")
    assert is_class_member(class_id, user["id"])


def test_create_class_requires_auth(client):
    res = client.post("/api/classes", json={"name": "BIO101"})
    assert res.status_code == 401


# ---- POST /api/classes/join ----

def test_join_class_happy_path(client):
    _register(client, username="alice")
    res_create = client.post("/api/classes", json={"name": "BIO101"})
    instructor_code = res_create.json()["instructor_code"]
    class_id = res_create.json()["class_id"]

    _register(client, username="bob")
    res_join = client.post("/api/classes/join", json={"instructor_code": instructor_code})
    assert res_join.status_code == 200
    assert res_join.json()["class_id"] == class_id


def test_join_class_wrong_code(client):
    _auth_client(client)
    res = client.post("/api/classes/join", json={"instructor_code": "WRONGCOD"})
    assert res.status_code == 404


def test_join_class_already_member(client):
    _auth_client(client)
    res_create = client.post("/api/classes", json={"name": "BIO101"})
    instructor_code = res_create.json()["instructor_code"]
    res = client.post("/api/classes/join", json={"instructor_code": instructor_code})
    assert res.status_code == 400


# ---- GET /api/classes/by-student-code/{code} ----

def test_by_student_code_happy_path(client):
    _auth_client(client)
    res_create = client.post("/api/classes", json={"name": "BIO101"})
    student_code = res_create.json()["student_code"]
    class_id = res_create.json()["class_id"]

    res = client.get(f"/api/classes/by-student-code/{student_code}")
    assert res.status_code == 200
    assert res.json()["class_id"] == class_id
    assert res.json()["name"] == "BIO101"


def test_by_student_code_wrong_code(client):
    res = client.get("/api/classes/by-student-code/XXXXXXXX")
    assert res.status_code == 404


# ---- GET /api/classes/{class_id}/settings ----

def test_get_class_settings_requires_auth(client):
    cid = create_class("X", "STUD0001", "INST0001", None)
    res = client.get(f"/api/classes/{cid}/settings")
    assert res.status_code == 401


def test_get_class_settings_non_member_gets_403(client):
    _auth_client(client)
    cid = create_class("X", "STUD0001", "INST0001", None)
    res = client.get(f"/api/classes/{cid}/settings")
    assert res.status_code == 403


def test_get_class_settings_member_gets_200(client):
    _auth_client(client)
    res_create = client.post("/api/classes", json={"name": "BIO101"})
    class_id = res_create.json()["class_id"]
    res = client.get(f"/api/classes/{class_id}/settings")
    assert res.status_code == 200
    data = res.json()
    assert "name" in data and "student_code" in data and "instructor_code" in data


# ---- PUT /api/classes/{class_id}/student-code ----

def test_rotate_student_code_non_member_gets_403(client):
    _auth_client(client)
    cid = create_class("X", "STUD0001", "INST0001", None)
    res = client.put(f"/api/classes/{cid}/student-code")
    assert res.status_code == 403


def test_rotate_student_code_member_gets_200(client):
    _auth_client(client)
    res_create = client.post("/api/classes", json={"name": "BIO101"})
    class_id = res_create.json()["class_id"]
    old_code = res_create.json()["student_code"]
    res = client.put(f"/api/classes/{class_id}/student-code")
    assert res.status_code == 200
    assert "student_code" in res.json()
    assert res.json()["student_code"] != old_code


# ---- PUT /api/classes/{class_id}/instructor-code ----

def test_rotate_instructor_code_member_gets_200(client):
    _auth_client(client)
    res_create = client.post("/api/classes", json={"name": "BIO101"})
    class_id = res_create.json()["class_id"]
    res = client.put(f"/api/classes/{class_id}/instructor-code")
    assert res.status_code == 200
    assert "instructor_code" in res.json()


# ---- POST /api/questions with class_id ----

def test_create_question_with_valid_class_id(client):
    _auth_client(client)
    res_create = client.post("/api/classes", json={"name": "BIO101"})
    class_id = res_create.json()["class_id"]
    res = client.post("/api/questions", json={
        "title": "Q1", "prompt": "P", "model_answer": "A", "rubric": "",
        "class_id": class_id,
    })
    assert res.status_code == 200
    assert "id" in res.json()


def test_create_question_non_member_class_gets_403(client):
    _auth_client(client)
    other_class_id = create_class("Other", "STUD0002", "INST0002", None)
    res = client.post("/api/questions", json={
        "title": "Q1", "prompt": "P", "model_answer": "A", "rubric": "",
        "class_id": other_class_id,
    })
    assert res.status_code == 403


# ---- GET /instructor returns classes ----

def test_instructor_page_includes_classes(client):
    _auth_client(client)
    client.post("/api/classes", json={"name": "BIO101"})
    res = client.get("/instructor")
    assert res.status_code == 200
    assert "BIO101" in res.text


# ---- Migration: existing questions assigned to Default class ----

def test_migration_assigns_default_class(tmp_path, monkeypatch):
    import sqlite3
    db_path = str(tmp_path / "migrate.db")
    monkeypatch.setattr(db_module, "DATABASE_PATH", db_path)

    # Build old-schema DB
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE questions (
            id TEXT PRIMARY KEY, title TEXT NOT NULL, prompt TEXT NOT NULL,
            model_answer TEXT NOT NULL, rubric TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE users (
            id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE sessions (token TEXT PRIMARY KEY, user_id TEXT NOT NULL, expires_at TIMESTAMP NOT NULL);
        CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT INTO questions (id, title, prompt, model_answer) VALUES ('q1', 'Old Q', 'P', 'A');
    """)
    conn.commit()
    conn.close()

    init_db()

    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT class_id FROM questions WHERE id='q1'").fetchone()
    conn.close()
    assert row[0] is not None


# ---- GET /student/{class_id} scoped questions ----

def test_student_class_page_shows_only_class_questions(client):
    _auth_client(client)
    res1 = client.post("/api/classes", json={"name": "ClassA"})
    cid1 = res1.json()["class_id"]
    res2 = client.post("/api/classes", json={"name": "ClassB"})
    cid2 = res2.json()["class_id"]
    client.post("/api/questions", json={
        "title": "ClassA Q", "prompt": "P", "model_answer": "A", "rubric": "",
        "class_id": cid1,
    })
    client.post("/api/questions", json={
        "title": "ClassB Q", "prompt": "P", "model_answer": "A", "rubric": "",
        "class_id": cid2,
    })
    res = client.get(f"/student/{cid1}")
    assert res.status_code == 200
    assert "ClassA Q" in res.text
    assert "ClassB Q" not in res.text
