# Phase 3 Classes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a classes layer so multiple instructors can run separate courses, each with its own questions, student access code, and instructor invite code, all visible in a single unified instructor dashboard with class labels and a filter.

**Architecture:** Two new DB tables (`classes`, `class_members`) scope questions to a class; students enter a class code on a new landing page; instructors see a unified dashboard with a class filter and manage classes at `/instructor/classes`. A new `require_class_member` dependency gates class-scoped operations. The student workspace URL changes from `/student/{question_id}` to `/student/{class_id}/{question_id}`.

**Tech Stack:** FastAPI, SQLite (via existing `db.py` pattern), Jinja2 templates, vanilla JS, existing `auth.generate_invite_code()` for code generation.

**Spec:** `docs/superpowers/specs/2026-03-24-phase3-classes-design.md`

---

## File Structure

**Modify:**
- `db.py` — add `classes`/`class_members` tables + migration in `init_db()`; add 10 new functions; modify `create_question` and `update_question` to handle `class_id`
- `dependencies.py` — add `require_class_member` dependency
- `app.py` — add class API routes; add `GET /instructor/classes`; modify `GET /instructor`; replace student routes; modify `POST /api/questions` and `PUT /api/questions/{id}`
- `templates/instructor.html` — class `<select>` in form, class badge on cards, filter dropdown, Manage Classes link in nav
- `templates/student.html` — class code entry mode; question-list mode shows class name and Switch class link; workspace back-link goes to `/student/{class_id}`
- `static/app.js` — class functions for instructor and student sections
- `static/style.css` — `.class-badge`, `.class-filter`, class management card styles

**Create:**
- `templates/instructor-classes.html` — class management page
- `tests/test_classes.py` — unit tests for new `db.py` functions
- `tests/test_classes_integration.py` — FastAPI TestClient integration tests

**Update (due to `create_question` signature change):**
- `tests/test_db.py` — pass `class_id` to `create_question` calls
- `tests/test_auth_integration.py` — pass `class_id` when creating questions via API

---

## Task 1: DB Schema — classes and class_members tables + migration

Adds the two new tables and migration logic to `init_db()`. Also modifies `create_question` and `update_question` to handle `class_id`. Updates existing tests that call `create_question`.

**Files:**
- Modify: `db.py`
- Modify: `tests/test_db.py`
- Create: `tests/test_classes.py`

- [ ] **Step 1: Write failing tests for the new schema**

Create `tests/test_classes.py`:

```python
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
    """Calling init_db() twice does not create a second Default class."""
    db_path = str(tmp_path / "idem.db")
    monkeypatch.setattr(db_module, "DATABASE_PATH", db_path)
    init_db()
    init_db()  # second call

    import sqlite3
    conn = sqlite3.connect(db_path)
    count = conn.execute("SELECT COUNT(*) FROM classes WHERE name = 'Default'").fetchone()[0]
    conn.close()
    assert count <= 1
```

- [ ] **Step 2: Run tests — expect failures**

```bash
cd /Users/douglasyu/src/Cowork/essay-coach
pytest tests/test_classes.py -v 2>&1 | head -40
```

Expected: 5 failures (tables don't exist yet).

- [ ] **Step 3: Add classes + class_members tables and migration to `db.py`**

In `db.py`, replace the `init_db()` function with this expanded version (keep everything below it unchanged):

```python
def init_db():
    conn = _connect()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS classes (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            student_code TEXT UNIQUE NOT NULL,
            instructor_code TEXT UNIQUE NOT NULL,
            created_by TEXT REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS class_members (
            class_id TEXT NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (class_id, user_id)
        );
        CREATE INDEX IF NOT EXISTS idx_class_members_user_id ON class_members(user_id);
        CREATE TABLE IF NOT EXISTS questions (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            prompt TEXT NOT NULL,
            model_answer TEXT NOT NULL,
            rubric TEXT,
            class_id TEXT REFERENCES classes(id) ON DELETE CASCADE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS attempts (
            id TEXT PRIMARY KEY,
            question_id TEXT REFERENCES questions(id) ON DELETE CASCADE,
            session_id TEXT NOT NULL,
            student_answer TEXT NOT NULL,
            feedback TEXT,
            attempt_number INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            expires_at TIMESTAMP NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        DELETE FROM sessions WHERE expires_at < datetime('now');
    """)

    # Add class_id column to questions if it doesn't exist yet (migration for pre-Phase-3 DBs)
    existing_cols = [
        r[1] for r in conn.execute("PRAGMA table_info(questions)").fetchall()
    ]
    if "class_id" not in existing_cols:
        conn.execute(
            "ALTER TABLE questions ADD COLUMN class_id TEXT REFERENCES classes(id) ON DELETE CASCADE"
        )
        conn.commit()

    # Migration: assign orphaned questions to a Default class
    orphan_count = conn.execute(
        "SELECT COUNT(*) FROM questions WHERE class_id IS NULL"
    ).fetchone()[0]
    if orphan_count > 0:
        import string as _string
        alphabet = _string.ascii_uppercase + string.digits
        s_code = "".join(secrets.choice(alphabet) for _ in range(8))
        i_code = "".join(secrets.choice(alphabet) for _ in range(8))
        default_id = str(uuid.uuid4())
        # Use first user (by created_at) as creator if any exist
        first_user = conn.execute(
            "SELECT id FROM users ORDER BY created_at ASC LIMIT 1"
        ).fetchone()
        created_by = first_user[0] if first_user else None
        conn.execute(
            "INSERT INTO classes (id, name, student_code, instructor_code, created_by) VALUES (?, ?, ?, ?, ?)",
            (default_id, "Default", s_code, i_code, created_by),
        )
        conn.execute(
            "UPDATE questions SET class_id = ? WHERE class_id IS NULL", (default_id,)
        )
        if created_by:
            conn.execute(
                "INSERT OR IGNORE INTO class_members (class_id, user_id) VALUES (?, ?)",
                (default_id, created_by),
            )
        conn.commit()

    # Seed invite code
    row = conn.execute(
        "SELECT value FROM settings WHERE key = 'invite_code'"
    ).fetchone()
    if not row:
        alphabet = string.ascii_uppercase + string.digits
        code = "".join(secrets.choice(alphabet) for _ in range(8))
        conn.execute(
            "INSERT INTO settings (key, value) VALUES ('invite_code', ?)", (code,)
        )
    conn.commit()
    conn.close()
```

Note the `import string as _string` inside the if-block is a workaround for the local alias — actually remove it and use `string` directly (it's already imported at the top of `db.py`). The snippet above has a minor naming issue; use the corrected version:

```python
        s_code = "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
        i_code = "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
```

- [ ] **Step 4: Also modify `create_question` to accept `class_id`**

In `db.py`, replace the `create_question` function:

```python
def create_question(title, prompt, model_answer, rubric, class_id):
    qid = str(uuid.uuid4())
    conn = _connect()
    conn.execute(
        "INSERT INTO questions (id, title, prompt, model_answer, rubric, class_id) VALUES (?, ?, ?, ?, ?, ?)",
        (qid, title, prompt, model_answer, rubric, class_id),
    )
    conn.commit()
    conn.close()
    return qid
```

Also update `update_question` to allow `class_id`:

```python
def update_question(question_id, **kwargs):
    allowed = {"title", "prompt", "model_answer", "rubric", "class_id"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [question_id]
    conn = _connect()
    conn.execute(f"UPDATE questions SET {set_clause} WHERE id = ?", values)
    conn.commit()
    conn.close()
```

- [ ] **Step 5: Update `tests/test_db.py` to pass `class_id`**

All `create_question` calls need a `class_id`. Since the DB unit tests don't have a class, use a placeholder UUID. Replace the file:

```python
import pytest
import db as db_module
from db import (
    init_db,
    create_question,
    get_question,
    list_questions,
    update_question,
    delete_question,
    create_attempt,
    get_attempts,
    get_attempt_count,
)

DUMMY_CLASS_ID = "00000000-0000-0000-0000-000000000001"


@pytest.fixture(autouse=True)
def test_db(tmp_path, monkeypatch):
    import sqlite3
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DATABASE_PATH", db_path)
    init_db()
    # Insert a dummy class so FK constraint is satisfied
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO classes (id, name, student_code, instructor_code) VALUES (?, ?, ?, ?)",
        (DUMMY_CLASS_ID, "Test", "STUD0001", "INST0001"),
    )
    conn.commit()
    conn.close()
    yield db_path


def test_create_and_get_question():
    qid = create_question("Test Title", "Write about X", "X is Y because Z", "Point 1\nPoint 2", DUMMY_CLASS_ID)
    q = get_question(qid)
    assert q["title"] == "Test Title"
    assert q["prompt"] == "Write about X"
    assert q["model_answer"] == "X is Y because Z"
    assert q["rubric"] == "Point 1\nPoint 2"
    assert q["class_id"] == DUMMY_CLASS_ID


def test_list_questions():
    create_question("Q1", "Prompt 1", "Answer 1", "", DUMMY_CLASS_ID)
    create_question("Q2", "Prompt 2", "Answer 2", "", DUMMY_CLASS_ID)
    qs = list_questions()
    assert len(qs) == 2


def test_update_question():
    qid = create_question("Old", "Old prompt", "Old answer", "", DUMMY_CLASS_ID)
    update_question(qid, title="New", prompt="New prompt", model_answer="New answer", rubric="New rubric")
    q = get_question(qid)
    assert q["title"] == "New"


def test_delete_question():
    qid = create_question("Del", "P", "A", "", DUMMY_CLASS_ID)
    delete_question(qid)
    assert get_question(qid) is None


def test_create_and_get_attempts():
    qid = create_question("Q", "P", "A", "", DUMMY_CLASS_ID)
    create_attempt(qid, "session1", "My answer", "Good job", 1)
    create_attempt(qid, "session1", "Better answer", "Even better", 2)
    attempts = get_attempts(qid, "session1")
    assert len(attempts) == 2
    assert attempts[0]["attempt_number"] == 2  # newest first


def test_get_attempt_count():
    qid = create_question("Q", "P", "A", "", DUMMY_CLASS_ID)
    create_attempt(qid, "s1", "ans", "fb", 1)
    create_attempt(qid, "s2", "ans", "fb", 1)
    assert get_attempt_count(qid) == 2
```

- [ ] **Step 6: Run all schema tests — expect pass**

```bash
pytest tests/test_classes.py tests/test_db.py -v
```

Expected: all pass.

- [ ] **Step 7: Run existing test suite to check nothing is broken**

```bash
pytest tests/ -v --ignore=tests/test_auth_integration.py 2>&1 | tail -20
```

Note: `test_auth_integration.py` will fail because it creates questions without `class_id` — that's fixed in Task 4.

- [ ] **Step 8: Commit**

```bash
git add db.py tests/test_db.py tests/test_classes.py
git commit -m "feat: add classes/class_members tables, migration, update create_question"
```

---

## Task 2: DB Class CRUD Functions

Adds all 10 new class-related functions to `db.py`. Tests live in `tests/test_classes.py`.

**Files:**
- Modify: `db.py`
- Modify: `tests/test_classes.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_classes.py`:

```python
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
    create_question,
)


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
    from db import hash_password
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
    uid = create_user("eve", "hash")
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
```

Also add this import at the top of `tests/test_classes.py` (after existing imports):
```python
from auth import hash_password
```

And in the test file, replace `from db import hash_password` with the auth import — `hash_password` lives in `auth.py`, not `db.py`. The `create_user` call just needs any string as `password_hash`.

- [ ] **Step 2: Run tests — expect failures**

```bash
pytest tests/test_classes.py -k "test_create_class" -v 2>&1 | head -20
```

Expected: ImportError (functions don't exist yet).

- [ ] **Step 3: Add 10 new DB functions to `db.py`**

Add a new section `# --- classes ---` at the end of `db.py`:

```python
# --- classes ---

def create_class(name: str, student_code: str, instructor_code: str, created_by: str | None) -> str:
    cid = str(uuid.uuid4())
    conn = _connect()
    conn.execute(
        "INSERT INTO classes (id, name, student_code, instructor_code, created_by) VALUES (?, ?, ?, ?, ?)",
        (cid, name, student_code, instructor_code, created_by),
    )
    conn.commit()
    conn.close()
    return cid


def get_class(class_id: str) -> dict | None:
    conn = _connect()
    row = conn.execute("SELECT * FROM classes WHERE id = ?", (class_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_class_by_student_code(code: str) -> dict | None:
    conn = _connect()
    row = conn.execute("SELECT * FROM classes WHERE student_code = ?", (code,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_class_by_instructor_code(code: str) -> dict | None:
    conn = _connect()
    row = conn.execute("SELECT * FROM classes WHERE instructor_code = ?", (code,)).fetchone()
    conn.close()
    return dict(row) if row else None


def list_classes_for_user(user_id: str) -> list[dict]:
    conn = _connect()
    rows = conn.execute(
        """SELECT c.* FROM classes c
           JOIN class_members m ON c.id = m.class_id
           WHERE m.user_id = ?
           ORDER BY c.created_at ASC""",
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_class_member(class_id: str, user_id: str) -> None:
    conn = _connect()
    conn.execute(
        "INSERT OR IGNORE INTO class_members (class_id, user_id) VALUES (?, ?)",
        (class_id, user_id),
    )
    conn.commit()
    conn.close()


def is_class_member(class_id: str, user_id: str) -> bool:
    conn = _connect()
    row = conn.execute(
        "SELECT 1 FROM class_members WHERE class_id = ? AND user_id = ?",
        (class_id, user_id),
    ).fetchone()
    conn.close()
    return row is not None


def get_class_question_count(class_id: str) -> int:
    conn = _connect()
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM questions WHERE class_id = ?", (class_id,)
    ).fetchone()
    conn.close()
    return row["cnt"]


def update_class_student_code(class_id: str, new_code: str) -> None:
    conn = _connect()
    conn.execute(
        "UPDATE classes SET student_code = ? WHERE id = ?", (new_code, class_id)
    )
    conn.commit()
    conn.close()


def update_class_instructor_code(class_id: str, new_code: str) -> None:
    conn = _connect()
    conn.execute(
        "UPDATE classes SET instructor_code = ? WHERE id = ?", (new_code, class_id)
    )
    conn.commit()
    conn.close()


def list_questions_for_class(class_id: str) -> list[dict]:
    """Return all questions belonging to a class, newest first."""
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM questions WHERE class_id = ? ORDER BY created_at DESC", (class_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
```

Note: `list_questions_for_class` is added here because Task 6 (student routes) will need it.

- [ ] **Step 4: Run tests — expect pass**

```bash
pytest tests/test_classes.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add db.py tests/test_classes.py
git commit -m "feat: add class CRUD functions to db.py"
```

---

## Task 3: `require_class_member` Dependency

Adds the `require_class_member` FastAPI dependency to `dependencies.py`.

**Files:**
- Modify: `dependencies.py`

- [ ] **Step 1: Add `require_class_member` to `dependencies.py`**

Append to `dependencies.py`:

```python
from fastapi import Depends, Path


async def require_class_member(
    class_id: str = Path(...),
    user: dict = Depends(require_instructor_api),
) -> tuple[dict, str]:
    """FastAPI dependency for class-scoped routes. Raises 403 if user is not a member."""
    if not db.is_class_member(class_id, user["id"]):
        raise HTTPException(status_code=403, detail="Not a member of this class")
    return user, class_id
```

Also add `Path` to the existing import from fastapi at the top of `dependencies.py`. The full updated imports section:

```python
from datetime import datetime, timedelta, timezone

from fastapi import Cookie, Depends, HTTPException, Path

import db
```

- [ ] **Step 2: Verify existing tests still pass**

```bash
pytest tests/test_auth_utils.py tests/test_auth.py -v
```

Expected: all pass (dependencies.py isn't imported by these tests directly).

- [ ] **Step 3: Commit**

```bash
git add dependencies.py
git commit -m "feat: add require_class_member dependency"
```

---

## Task 4: Class API Routes

Adds 6 new API endpoints for class management and modifies question creation/update to require `class_id`. Updates `test_auth_integration.py`.

**Files:**
- Modify: `app.py`
- Modify: `tests/test_auth_integration.py`
- Create: `tests/test_classes_integration.py`

- [ ] **Step 1: Write failing integration tests**

Create `tests/test_classes_integration.py`:

```python
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


def _login(client, username="alice", password="password123"):
    res = client.post("/api/auth/login", json={"username": username, "password": password})
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
    from db import create_class
    cid = create_class("X", "STUD0001", "INST0001", None)
    res = client.get(f"/api/classes/{cid}/settings")
    assert res.status_code == 401


def test_get_class_settings_non_member_gets_403(client):
    _auth_client(client)
    from db import create_class
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
    from db import create_class
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
    from db import create_class
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
```

- [ ] **Step 2: Run tests — expect failures**

```bash
pytest tests/test_classes_integration.py -v 2>&1 | head -30
```

Expected: import errors and 404s (routes don't exist yet).

- [ ] **Step 3: Add class API routes to `app.py`**

Add new imports at the top of `app.py` (update existing db import block and dependencies import):

```python
from db import (
    init_db,
    create_question,
    get_question,
    list_questions,
    list_questions_for_class,
    update_question,
    delete_question,
    create_attempt,
    get_attempts,
    get_attempt_count,
    create_user,
    get_user_by_username,
    create_session,
    delete_session,
    delete_sessions_for_user,
    get_setting,
    set_setting,
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
)
from dependencies import _validate_session, require_instructor_api, require_class_member
```

Add new Pydantic models (after existing models):

```python
class ClassCreate(BaseModel):
    name: str


class ClassJoin(BaseModel):
    instructor_code: str
```

Add class API routes (add before the `# ---- Questions API routes` section):

```python
# ---- Classes API routes ----

def _unique_class_code() -> str:
    """Generate an 8-char code guaranteed unique across all classes (student and instructor codes)."""
    while True:
        code = generate_invite_code()
        if not get_class_by_student_code(code) and not get_class_by_instructor_code(code):
            return code


@app.post("/api/classes")
def api_create_class(data: ClassCreate, user: dict = Depends(require_instructor_api)):
    s_code = _unique_class_code()
    i_code = _unique_class_code()
    class_id = create_class(data.name, s_code, i_code, user["id"])
    add_class_member(class_id, user["id"])
    return {"class_id": class_id, "name": data.name, "student_code": s_code, "instructor_code": i_code}


@app.post("/api/classes/join")
def api_join_class(data: ClassJoin, user: dict = Depends(require_instructor_api)):
    cls = get_class_by_instructor_code(data.instructor_code)
    if not cls:
        raise HTTPException(status_code=404, detail="Class not found")
    if is_class_member(cls["id"], user["id"]):
        raise HTTPException(status_code=400, detail="Already a member")
    add_class_member(cls["id"], user["id"])
    return {"class_id": cls["id"], "name": cls["name"]}


@app.get("/api/classes/by-student-code/{code}")
def api_by_student_code(code: str):
    cls = get_class_by_student_code(code)
    if not cls:
        raise HTTPException(status_code=404, detail="Class not found")
    return {"class_id": cls["id"], "name": cls["name"]}


@app.get("/api/classes/{class_id}/settings")
def api_class_settings(user_and_class: tuple = Depends(require_class_member)):
    user, class_id = user_and_class
    cls = get_class(class_id)
    return {"name": cls["name"], "student_code": cls["student_code"], "instructor_code": cls["instructor_code"]}


@app.put("/api/classes/{class_id}/student-code")
def api_rotate_student_code(user_and_class: tuple = Depends(require_class_member)):
    user, class_id = user_and_class
    new_code = _unique_class_code()
    update_class_student_code(class_id, new_code)
    return {"student_code": new_code}


@app.put("/api/classes/{class_id}/instructor-code")
def api_rotate_instructor_code(user_and_class: tuple = Depends(require_class_member)):
    user, class_id = user_and_class
    new_code = _unique_class_code()
    update_class_instructor_code(class_id, new_code)
    return {"instructor_code": new_code}
```

- [ ] **Step 4: Modify question API routes for `class_id`**

Update the `QuestionCreate` Pydantic model in `app.py`:

```python
class QuestionCreate(BaseModel):
    title: str
    prompt: str
    model_answer: str
    rubric: Optional[str] = ""
    class_id: str
```

Update `api_create_question`:

```python
@app.post("/api/questions")
def api_create_question(
    data: QuestionCreate,
    user: dict = Depends(require_instructor_api),
):
    if not is_class_member(data.class_id, user["id"]):
        raise HTTPException(status_code=403, detail="Not a member of this class")
    qid = create_question(data.title, data.prompt, data.model_answer, data.rubric, data.class_id)
    return {"id": qid}
```

Update `QuestionUpdate` to allow `class_id`:

```python
class QuestionUpdate(BaseModel):
    title: Optional[str] = None
    prompt: Optional[str] = None
    model_answer: Optional[str] = None
    rubric: Optional[str] = None
    class_id: Optional[str] = None
```

Update `api_update_question` to validate membership on class change:

```python
@app.put("/api/questions/{question_id}")
def api_update_question(
    question_id: str,
    data: QuestionUpdate,
    user: dict = Depends(require_instructor_api),
):
    q = get_question(question_id)
    if not q:
        raise HTTPException(status_code=404, detail="Not found")
    if not is_class_member(q["class_id"], user["id"]):
        raise HTTPException(status_code=403, detail="Not a member of this class")
    kwargs = {k: v for k, v in data.model_dump().items() if v is not None}
    if "class_id" in kwargs and not is_class_member(kwargs["class_id"], user["id"]):
        raise HTTPException(status_code=403, detail="Not a member of target class")
    update_question(question_id, **kwargs)
    return {"ok": True}
```

- [ ] **Step 5: Update `test_auth_integration.py` — fix `create_question` calls**

In `tests/test_auth_integration.py`, every place a question is created via POST `/api/questions` needs a `class_id`. Add a helper at the top of the test file:

```python
def _make_class(client):
    """Create a class and return its class_id. Client must already be authenticated."""
    res = client.post("/api/classes", json={"name": "Test Class"})
    return res.json()["class_id"]
```

Then in each test that calls `client.post("/api/questions", ...)`, first call `_make_class(client)` and add `"class_id": class_id` to the JSON payload.

Search for all occurrences in `test_auth_integration.py`:

```bash
grep -n "api/questions" tests/test_auth_integration.py
```

Update each question-creation POST to include `class_id`. For example:

```python
# Before
res = client.post("/api/questions", json={"title": "Q", "prompt": "P", "model_answer": "A", "rubric": ""})

# After
class_id = _make_class(client)
res = client.post("/api/questions", json={"title": "Q", "prompt": "P", "model_answer": "A", "rubric": "", "class_id": class_id})
```

- [ ] **Step 6: Run all tests**

```bash
pytest tests/ -v 2>&1 | tail -30
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add app.py dependencies.py tests/test_classes_integration.py tests/test_auth_integration.py
git commit -m "feat: add class API routes, scope question creation to class"
```

---

## Task 5: Instructor HTML Routes

Modifies `GET /instructor` to pass classes and adds `GET /instructor/classes`.

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Update `GET /instructor` route**

In `app.py`, replace the `instructor_dashboard` function:

```python
@app.get("/instructor", response_class=HTMLResponse)
def instructor_dashboard(
    request: Request,
    session_token: str | None = Cookie(default=None),
):
    user = _validate_session(session_token)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    questions = list_questions()
    classes = list_classes_for_user(user["id"])
    for q in questions:
        q["attempt_count"] = get_attempt_count(q["id"])
    return templates.TemplateResponse(
        "instructor.html",
        {"request": request, "questions": questions, "username": user["username"], "classes": classes},
    )
```

- [ ] **Step 2: Add `GET /instructor/classes` route**

Add this route to `app.py` (after the instructor_dashboard route):

```python
@app.get("/instructor/classes", response_class=HTMLResponse)
def instructor_classes_page(
    request: Request,
    session_token: str | None = Cookie(default=None),
):
    user = _validate_session(session_token)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    classes = list_classes_for_user(user["id"])
    for cls in classes:
        cls["question_count"] = get_class_question_count(cls["id"])
    return templates.TemplateResponse(
        "instructor-classes.html",
        {"request": request, "classes": classes, "username": user["username"]},
    )
```

- [ ] **Step 3: Update student routes — replace old `/student` and `/student/{question_id}`**

Replace the existing `student_list` and `student_workspace` routes with these new ones:

```python
@app.get("/student", response_class=HTMLResponse)
def student_landing(request: Request):
    """Class code entry page. JS checks localStorage and may redirect to /student/{class_id}."""
    return templates.TemplateResponse("student.html", {"request": request, "mode": "landing"})


@app.get("/student/{class_id}", response_class=HTMLResponse)
def student_class_list(request: Request, class_id: str):
    cls = get_class(class_id)
    if not cls:
        return RedirectResponse(url="/student")
    questions = list_questions_for_class(class_id)
    safe_questions = [
        {"id": q["id"], "title": q["title"], "prompt": q["prompt"]} for q in questions
    ]
    return templates.TemplateResponse(
        "student.html",
        {"request": request, "mode": "list", "class_id": class_id, "class_name": cls["name"], "questions": safe_questions},
    )


@app.get("/student/{class_id}/{question_id}", response_class=HTMLResponse)
def student_workspace(request: Request, class_id: str, question_id: str):
    cls = get_class(class_id)
    if not cls:
        return RedirectResponse(url="/student")
    q = get_question(question_id)
    if not q or q.get("class_id") != class_id:
        return RedirectResponse(url=f"/student/{class_id}")
    safe_question = {"id": q["id"], "title": q["title"], "prompt": q["prompt"]}
    return templates.TemplateResponse(
        "student.html",
        {"request": request, "mode": "workspace", "class_id": class_id, "class_name": cls["name"], "question": safe_question},
    )
```

- [ ] **Step 4: Run integration tests**

```bash
pytest tests/test_classes_integration.py -v
```

Expected: all pass (including `test_instructor_page_includes_classes` and `test_student_class_page_shows_only_class_questions`).

- [ ] **Step 5: Run full suite**

```bash
pytest tests/ -v 2>&1 | tail -20
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add app.py
git commit -m "feat: update instructor/student HTML routes for classes"
```

---

## Task 6: `templates/instructor.html` — Class Support

Adds class select in form, class badge on cards, filter dropdown, and Manage Classes nav link.

**Files:**
- Modify: `templates/instructor.html`

- [ ] **Step 1: Add Manage Classes link to nav**

In `instructor.html`, in the `<nav>` section, add a link before "To Student View":

```html
<nav>
    <span class="username-display">{{ username }}</span>
    <a href="/instructor/classes">Manage Classes</a>
    <a href="/student">To Student View</a>
    <form method="POST" action="/logout" style="display:inline; margin-left:0.75rem;">
        <button type="submit" class="btn btn-small">Sign Out</button>
    </form>
</nav>
```

- [ ] **Step 2: Add class filter above question list**

In the `<section class="questions-section">`, add filter before the questions list:

```html
<section class="questions-section">
    <div class="questions-section-header">
        <h2>Existing Questions</h2>
        <select id="class-filter" class="class-filter" onchange="applyClassFilter()">
            <option value="">All Classes</option>
            {% for cls in classes %}
            <option value="{{ cls.id }}">{{ cls.name }}</option>
            {% endfor %}
        </select>
    </div>
    <div id="questions-list">
        ...existing question cards...
    </div>
</section>
```

- [ ] **Step 3: Add class badge to each question card and `data-class-id`**

Update each question card in the `{% for q in questions %}` loop:

```html
<div class="question-card" data-id="{{ q.id }}" data-class-id="{{ q.class_id }}">
    <div class="question-header">
        <h3>{{ q.title }}</h3>
        <div class="question-meta">
            {% for cls in classes %}{% if cls.id == q.class_id %}<span class="class-badge">{{ cls.name }}</span>{% endif %}{% endfor %}
            <span class="attempt-badge">{{ q.attempt_count }} attempt{{ 's' if q.attempt_count != 1 else '' }}</span>
        </div>
    </div>
    <p class="question-prompt">{{ q.prompt[:150] }}{{ '...' if q.prompt|length > 150 else '' }}</p>
    <div class="question-actions">
        <button class="btn btn-small" onclick="editQuestion('{{ q.id }}')">Edit</button>
        <button class="btn btn-small btn-danger" onclick="deleteQuestion('{{ q.id }}')">Delete</button>
    </div>
</div>
```

- [ ] **Step 4: Add class `<select>` to question form**

In the `<form id="question-form">`, add a class select field after the rubric field (before `form-actions`):

```html
<div class="field">
    <label for="q-class">Class</label>
    {% if classes %}
    <select id="q-class" required>
        <option value="" disabled selected>Select a class...</option>
        {% for cls in classes %}
        <option value="{{ cls.id }}">{{ cls.name }}</option>
        {% endfor %}
    </select>
    {% else %}
    <select id="q-class" disabled>
        <option value="">No classes yet — create one at Manage Classes</option>
    </select>
    {% endif %}
</div>
```

- [ ] **Step 5: Verify the page renders**

```bash
pytest tests/test_classes_integration.py::test_instructor_page_includes_classes -v
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add templates/instructor.html
git commit -m "feat: add class badge, filter, and class select to instructor dashboard"
```

---

## Task 7: `templates/instructor-classes.html` — Class Management Page

Creates the new class management template.

**Files:**
- Create: `templates/instructor-classes.html`

- [ ] **Step 1: Create the template**

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Essay Coach — Manage Classes</title>
    <link rel="stylesheet" href="/static/style.css">
</head>
<body>
    <header>
        <h1>Essay Coach <span class="badge">Instructor</span></h1>
        <nav>
            <span class="username-display">{{ username }}</span>
            <a href="/instructor">&larr; Dashboard</a>
            <form method="POST" action="/logout" style="display:inline; margin-left:0.75rem;">
                <button type="submit" class="btn btn-small">Sign Out</button>
            </form>
        </nav>
    </header>

    <main class="classes-page">
        <div class="classes-actions">
            <div class="class-action-form">
                <h2>Create Class</h2>
                <div class="field">
                    <input type="text" id="new-class-name" placeholder="e.g. BIO101 Spring 2026">
                </div>
                <button class="btn btn-primary" onclick="createClass()">Create</button>
            </div>
            <div class="class-action-form">
                <h2>Join a Class</h2>
                <div class="field">
                    <input type="text" id="join-instructor-code" placeholder="Instructor code">
                </div>
                <button class="btn btn-primary" onclick="joinClass()">Join</button>
            </div>
        </div>

        <div id="classes-list">
            {% for cls in classes %}
            <div class="class-card" id="class-card-{{ cls.id }}">
                <div class="class-card-header">
                    <h3>{{ cls.name }}</h3>
                    <span class="attempt-badge">{{ cls.question_count }} question{{ 's' if cls.question_count != 1 else '' }}</span>
                </div>
                <div class="field">
                    <label>Student Code</label>
                    <div class="invite-code-row">
                        <code id="student-code-{{ cls.id }}">{{ cls.student_code }}</code>
                        <button class="btn btn-small" onclick="rotateStudentCode('{{ cls.id }}')">Rotate</button>
                    </div>
                </div>
                <div class="field">
                    <label>Instructor Invite Code</label>
                    <div class="invite-code-row">
                        <code id="instructor-code-{{ cls.id }}">{{ cls.instructor_code }}</code>
                        <button class="btn btn-small" onclick="rotateInstructorCode('{{ cls.id }}')">Rotate</button>
                    </div>
                </div>
            </div>
            {% endfor %}
            {% if not classes %}
            <p class="empty-state">No classes yet. Create one above.</p>
            {% endif %}
        </div>
    </main>

    <script src="/static/app.js"></script>
    <script>initClasses();</script>
</body>
</html>
```

- [ ] **Step 2: Verify the page loads**

```bash
python -c "
import db as db_module
db_module.DATABASE_PATH = '/tmp/test_classes_page.db'
from db import init_db; init_db()
from fastapi.testclient import TestClient
from app import app
client = TestClient(app)
# register
from db import get_setting
code = get_setting('invite_code')
client.post('/api/auth/register', json={'username': 'a', 'password': 'password1', 'invite_code': code})
res = client.get('/instructor/classes')
assert res.status_code == 200, f'Got {res.status_code}'
print('OK')
"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add templates/instructor-classes.html
git commit -m "feat: add instructor-classes.html template"
```

---

## Task 8: `templates/student.html` — Class Code Entry

Rewrites student.html to support three modes: `landing` (class code entry), `list` (question list), `workspace`.

**Files:**
- Modify: `templates/student.html`

- [ ] **Step 1: Rewrite student.html**

Replace the entire file:

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Essay Coach</title>
    <link rel="stylesheet" href="/static/style.css">
</head>
<body>

{% if mode == "landing" %}
<!-- Landing: class code entry (or auto-redirect if class stored in localStorage) -->
<header>
    <h1>Essay Coach</h1>
</header>
<main class="question-list-view">
    <h2>Enter Your Class Code</h2>
    <div class="class-entry-form">
        <div class="field">
            <input type="text" id="class-code-input" placeholder="e.g. ABC12345" maxlength="8"
                   style="text-transform:uppercase; max-width:200px;">
        </div>
        <button class="btn btn-primary" onclick="resolveClassCode()">Continue</button>
        <p id="class-code-error" class="error" style="margin-top:0.5rem; display:none;">Class not found. Check your code and try again.</p>
    </div>
</main>
<script src="/static/app.js"></script>
<script>initStudentLanding();</script>

{% elif mode == "list" %}
<!-- Question list for a class -->
<header>
    <h1>Essay Coach</h1>
    <nav>
        <span style="font-size:0.9rem; color:var(--text-muted);">{{ class_name }}</span>
        <a href="#" onclick="clearClass(); return false;" style="margin-left:1rem; font-size:0.85rem;">Switch class</a>
    </nav>
</header>
<main class="question-list-view">
    <h2>Select a Question</h2>
    <div class="question-grid">
        {% for q in questions %}
        <a href="/student/{{ class_id }}/{{ q.id }}" class="question-link-card">
            <h3>{{ q.title }}</h3>
            <p>{{ q.prompt[:200] }}{{ '...' if q.prompt|length > 200 else '' }}</p>
        </a>
        {% endfor %}
        {% if not questions %}
        <p class="empty-state">No questions available yet. Ask your instructor to create some.</p>
        {% endif %}
    </div>
</main>
<script src="/static/app.js"></script>
<script>
    const CLASS_ID = "{{ class_id }}";
</script>

{% else %}
<!-- Workspace -->
<header>
    <h1>Essay Coach</h1>
    <nav><a href="/student/{{ class_id }}">&larr; All Questions</a></nav>
</header>
<main class="workspace">
    <div class="workspace-left">
        <div class="prompt-section">
            <h2>{{ question.title }}</h2>
            <div class="essay-prompt">{{ question.prompt }}</div>
        </div>
        <div class="answer-section">
            <label for="student-answer">Your Answer</label>
            <textarea id="student-answer" rows="16" placeholder="Type or paste your essay answer here..."></textarea>
            <div class="answer-actions">
                <button id="submit-btn" class="btn btn-primary" onclick="submitForFeedback()">Submit for Feedback</button>
                <span id="attempt-counter" class="attempt-counter"></span>
            </div>
        </div>
    </div>
    <div class="workspace-right">
        <div id="feedback-section" class="feedback-section" style="display:none">
            <h3>Feedback</h3>
            <div id="feedback-content" class="feedback-content"></div>
        </div>
        <div id="streaming-indicator" class="streaming-indicator" style="display:none">
            <div class="dot-pulse"></div>
            <span>Analyzing your answer...</span>
        </div>
    </div>
</main>

<aside id="history-sidebar" class="history-sidebar">
    <button class="history-toggle" onclick="toggleHistory()">
        <span id="history-toggle-text">Show Revision History</span>
    </button>
    <div id="history-content" class="history-content" style="display:none"></div>
</aside>

<script>
    const QUESTION_ID = "{{ question.id }}";
    const CLASS_ID = "{{ class_id }}";
</script>
<script src="/static/app.js"></script>
<script>initStudent();</script>
{% endif %}

</body>
</html>
```

- [ ] **Step 2: Verify student routes**

```bash
pytest tests/test_classes_integration.py::test_student_class_page_shows_only_class_questions -v
```

Expected: pass.

- [ ] **Step 3: Commit**

```bash
git add templates/student.html
git commit -m "feat: rewrite student.html for landing/list/workspace modes"
```

---

## Task 9: `static/app.js` — Class Functions

Adds client-side class management for instructor and student.

**Files:**
- Modify: `static/app.js`

- [ ] **Step 1: Update `handleQuestionSubmit` to include class_id**

In `app.js`, update `handleQuestionSubmit` to read class_id from the form:

```javascript
async function handleQuestionSubmit(e) {
    e.preventDefault();

    const editId = document.getElementById('edit-id').value;
    const payload = {
        title: document.getElementById('q-title').value,
        prompt: document.getElementById('q-prompt').value,
        model_answer: document.getElementById('q-model-answer').value,
        rubric: document.getElementById('q-rubric').value,
        class_id: document.getElementById('q-class').value,
    };

    let res;
    if (editId) {
        res = await fetch(`/api/questions/${editId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
    } else {
        res = await fetch('/api/questions', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
    }
    if (handleAuthError(res)) return;
    window.location.reload();
}
```

- [ ] **Step 2: Update `editQuestion` to restore class select**

In `editQuestion`, add one line to populate the class select:

```javascript
async function editQuestion(id) {
    const dataRes = await fetch(`/api/questions/detail/${id}`);
    if (handleAuthError(dataRes)) return;
    if (!dataRes.ok) return;
    const q = await dataRes.json();
    document.getElementById('edit-id').value = id;
    document.getElementById('q-title').value = q.title;
    document.getElementById('q-prompt').value = q.prompt;
    document.getElementById('q-model-answer').value = q.model_answer;
    document.getElementById('q-rubric').value = q.rubric || '';
    document.getElementById('q-class').value = q.class_id || '';
    document.getElementById('form-title').textContent = 'Edit Question';
    document.getElementById('submit-btn').textContent = 'Update Question';
    document.getElementById('cancel-btn').style.display = 'inline-block';
    window.scrollTo({ top: 0, behavior: 'smooth' });
}
```

- [ ] **Step 3: Add class filter function**

In `app.js`, add `applyClassFilter` after `initInstructor`:

```javascript
function applyClassFilter() {
    const filterVal = document.getElementById('class-filter').value;
    document.querySelectorAll('.question-card').forEach(card => {
        if (!filterVal || card.dataset.classId === filterVal) {
            card.style.display = '';
        } else {
            card.style.display = 'none';
        }
    });
}
```

- [ ] **Step 4: Add class management functions**

Add these functions to the `// INSTRUCTOR` section of `app.js`:

```javascript
// ---- Classes (instructor-classes.html) ----

function initClasses() {
    // no setup needed currently
}

async function createClass() {
    const name = document.getElementById('new-class-name').value.trim();
    if (!name) { alert('Enter a class name.'); return; }
    const res = await fetch('/api/classes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
    });
    if (handleAuthError(res)) return;
    window.location.reload();
}

async function joinClass() {
    const code = document.getElementById('join-instructor-code').value.trim().toUpperCase();
    if (!code) { alert('Enter an instructor code.'); return; }
    const res = await fetch('/api/classes/join', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ instructor_code: code }),
    });
    if (handleAuthError(res)) return;
    if (res.status === 400) { alert('You are already a member of this class.'); return; }
    if (res.status === 404) { alert('Class not found. Check the code.'); return; }
    window.location.reload();
}

async function rotateStudentCode(classId) {
    if (!confirm('Rotate the student code? Students using the old code will need the new one.')) return;
    const res = await fetch(`/api/classes/${classId}/student-code`, { method: 'PUT' });
    if (handleAuthError(res)) return;
    if (!res.ok) return;
    const data = await res.json();
    document.getElementById(`student-code-${classId}`).textContent = data.student_code;
}

async function rotateInstructorCode(classId) {
    if (!confirm('Rotate the instructor invite code? The old code will stop working.')) return;
    const res = await fetch(`/api/classes/${classId}/instructor-code`, { method: 'PUT' });
    if (handleAuthError(res)) return;
    if (!res.ok) return;
    const data = await res.json();
    document.getElementById(`instructor-code-${classId}`).textContent = data.instructor_code;
}
```

- [ ] **Step 5: Add student class functions**

Add these functions to the `// STUDENT` section of `app.js`:

```javascript
// ---- Student class helpers ----

// When landing on /student?clear=1 (stale class_id redirect from server), clear localStorage.
// When a valid class_id is in localStorage, auto-redirect to /student/{class_id}.
// Server redirects /student/{invalid_class_id} → /student?clear=1 to break the loop.
function initStudentLanding() {
    const params = new URLSearchParams(window.location.search);
    if (params.get('clear')) {
        localStorage.removeItem('essay_coach_class_id');
        return;
    }
    const stored = localStorage.getItem('essay_coach_class_id');
    if (stored) {
        window.location.href = `/student/${stored}`;
    }
}

async function resolveClassCode() {
    const code = document.getElementById('class-code-input').value.trim().toUpperCase();
    if (!code) return;
    const errorEl = document.getElementById('class-code-error');
    errorEl.style.display = 'none';
    const res = await fetch(`/api/classes/by-student-code/${code}`);
    if (!res.ok) {
        errorEl.style.display = 'block';
        return;
    }
    const data = await res.json();
    localStorage.setItem('essay_coach_class_id', data.class_id);
    window.location.href = `/student/${data.class_id}`;
}

function clearClass() {
    localStorage.removeItem('essay_coach_class_id');
    window.location.href = '/student';
}
```

The server must redirect invalid class_ids to `/student?clear=1` (not just `/student`) to avoid a redirect loop. This is handled in Step 6 below.

- [ ] **Step 6: Update `app.py` student routes for `?clear=1`**

In `student_class_list` and `student_workspace` in `app.py`, change:
```python
return RedirectResponse(url="/student")
```
to:
```python
return RedirectResponse(url="/student?clear=1")
```

- [ ] **Step 7: Commit**

```bash
git add static/app.js app.py
git commit -m "feat: add class JS functions (instructor + student)"
```

---

## Task 10: `static/style.css` — Class Styles

Adds styles for class badges, filter dropdown, class cards, and the class entry form.

**Files:**
- Modify: `static/style.css`

- [ ] **Step 1: Append class styles to `style.css`**

Append to the end of `style.css`:

```css
/* Class badge on question cards */
.class-badge {
    display: inline-block;
    background: #dbeafe;
    color: #1d4ed8;
    font-size: 0.7rem;
    font-weight: 600;
    padding: 2px 8px;
    border-radius: 10px;
    letter-spacing: 0.03em;
    margin-right: 0.4rem;
}

/* Question meta row (class badge + attempt badge) */
.question-meta {
    display: flex;
    align-items: center;
    gap: 0.25rem;
}

/* Questions section header with filter */
.questions-section-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 1rem;
}

.questions-section-header h2 {
    margin-bottom: 0;
}

/* Class filter dropdown */
.class-filter {
    padding: 0.3rem 0.6rem;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    font-family: inherit;
    font-size: 0.85rem;
    background: var(--bg);
    color: var(--text);
    cursor: pointer;
}

/* Class management page */
.classes-page {
    max-width: 900px;
    margin: 2rem auto;
    padding: 0 2rem;
}

.classes-actions {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1.5rem;
    margin-bottom: 2rem;
}

.class-action-form {
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 1.25rem;
}

.class-action-form h2 {
    font-size: 1rem;
    margin-bottom: 1rem;
}

.class-card {
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 1.25rem;
    margin-bottom: 1rem;
}

.class-card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1rem;
}

.class-card-header h3 {
    font-size: 1.1rem;
}

/* Student class code entry */
.class-entry-form {
    max-width: 400px;
    margin-top: 1.5rem;
}

/* Responsive: classes-actions */
@media (max-width: 600px) {
    .classes-actions {
        grid-template-columns: 1fr;
    }
}
```

- [ ] **Step 2: Run full test suite**

```bash
pytest tests/ -v
```

Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add static/style.css
git commit -m "feat: add CSS styles for class badges, filter, and management page"
```

---

## Final Verification

- [ ] **Run full test suite one more time**

```bash
pytest tests/ -v 2>&1 | tail -30
```

Expected: all pass, zero failures.

- [ ] **Smoke test the app manually**

```bash
python app.py
```

1. Visit `http://localhost:8000/instructor` — should redirect to `/login`
2. Log in → see "Manage Classes" link in nav
3. Go to Manage Classes → create a class → get student + instructor codes
4. See class select in Create Question form
5. Create a question in the class
6. Visit `http://localhost:8000/student` → enter student code → redirected to class question list
7. Click a question → workspace loads at `/student/{class_id}/{question_id}`
8. "Switch class" link returns to landing page

