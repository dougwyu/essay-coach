# Student Accounts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add optional student accounts (username + email + password) with 30-day sliding sessions so students can preserve submission history across browsers and devices, while anonymous usage remains fully supported.

**Architecture:** Three new DB tables (`student_users`, `student_sessions`, `student_question_sessions`) added to `init_db()`. Five new API routes registered in `app.py` before `# ---- Auth API routes ----`. The landing page (`/student`) gains an auth-first two-step flow via JS; the workspace resolves session_id from the new `/api/student/session/{question_id}` endpoint and shows an "Already signed in as" identity indicator.

**Tech Stack:** FastAPI, SQLite (via existing `_connect()` helper), Pydantic BaseModel, `bcrypt` (via `hash_password`/`verify_password`/`generate_token` from `auth.py`), vanilla JS.

**Spec:** `docs/superpowers/specs/2026-03-25-student-accounts-design.md`

---

## File Map

| File | Change |
|------|--------|
| `db.py` | Add 3 tables to `init_db()`, add 9 new functions |
| `app.py` | Add 9 db imports, add `_validate_student_session` helper, add 2 Pydantic models, add 5 routes |
| `templates/student.html` | Add auth panel (Step 1) and class-code panel identity bar (Step 2) to `mode == "landing"` block; add identity indicator to workspace block |
| `static/app.js` | Rewrite `initStudentLanding()` to call `/api/student/auth/me` first; add auth panel JS (register/login/logout/anonymous); update `initStudent()` to call `/api/student/session/{QUESTION_ID}` |
| `tests/test_student_auth.py` | New file — 17 integration tests |

---

## Task 1: DB tables and functions

**Files:**
- Modify: `db.py`
- Test: `tests/test_student_auth.py` (create file)

- [ ] **Step 1: Create the test file with fresh_db fixture and first DB test**

```python
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
```

- [ ] **Step 2: Run the test to confirm it fails (functions not defined yet)**

```bash
cd /Users/douglasyu/src/Cowork/essay-coach && pytest tests/test_student_auth.py::test_create_and_get_student_user -v
```

Expected: `ImportError` or `FAILED` — `create_student_user` does not exist yet.

- [ ] **Step 3: Add the three new tables to `init_db()` in `db.py`**

In `db.py`, inside the `conn.executescript("""...""")` block in `init_db()`, add these three `CREATE TABLE IF NOT EXISTS` statements immediately before the final `DELETE FROM sessions WHERE expires_at < datetime('now');` line:

```sql
        CREATE TABLE IF NOT EXISTS student_users (
            id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS student_sessions (
            token TEXT PRIMARY KEY,
            student_id TEXT NOT NULL REFERENCES student_users(id) ON DELETE CASCADE,
            expires_at TIMESTAMP NOT NULL
        );
        CREATE TABLE IF NOT EXISTS student_question_sessions (
            id TEXT PRIMARY KEY,
            student_id TEXT NOT NULL REFERENCES student_users(id) ON DELETE CASCADE,
            question_id TEXT NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(student_id, question_id)
        );
```

- [ ] **Step 4: Add the 9 new db functions at the bottom of `db.py`**

Add a `# --- student users ---` section at the end of `db.py`:

```python
# --- student users ---

def create_student_user(username: str, email: str, password_hash: str) -> str:
    uid = str(uuid.uuid4())
    conn = _connect()
    conn.execute(
        "INSERT INTO student_users (id, username, email, password_hash) VALUES (?, ?, ?, ?)",
        (uid, username, email, password_hash),
    )
    conn.commit()
    conn.close()
    return uid


def get_student_by_username(username: str) -> dict | None:
    conn = _connect()
    row = conn.execute(
        "SELECT * FROM student_users WHERE username = ?", (username,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_student_by_email(email: str) -> dict | None:
    conn = _connect()
    row = conn.execute(
        "SELECT * FROM student_users WHERE email = ?", (email,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_student_by_id(student_id: str) -> dict | None:
    conn = _connect()
    row = conn.execute(
        "SELECT * FROM student_users WHERE id = ?", (student_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def create_student_session(token: str, student_id: str, expires_at: str) -> None:
    conn = _connect()
    conn.execute(
        "INSERT INTO student_sessions (token, student_id, expires_at) VALUES (?, ?, ?)",
        (token, student_id, expires_at),
    )
    conn.commit()
    conn.close()


def get_student_session(token: str) -> dict | None:
    """Return session if it exists and has not expired; None otherwise."""
    conn = _connect()
    row = conn.execute(
        "SELECT * FROM student_sessions WHERE token = ? AND expires_at > datetime('now')",
        (token,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def update_student_session_expiry(token: str, expires_at: str) -> None:
    conn = _connect()
    conn.execute(
        "UPDATE student_sessions SET expires_at = ? WHERE token = ?",
        (expires_at, token),
    )
    conn.commit()
    conn.close()


def delete_student_session(token: str) -> None:
    conn = _connect()
    conn.execute("DELETE FROM student_sessions WHERE token = ?", (token,))
    conn.commit()
    conn.close()


def get_or_create_question_session(student_id: str, question_id: str) -> str:
    """Return the session UUID for (student_id, question_id), creating it if needed.
    Uses INSERT OR IGNORE + SELECT to be idempotent and race-safe."""
    sid = str(uuid.uuid4())
    conn = _connect()
    conn.execute(
        "INSERT OR IGNORE INTO student_question_sessions (id, student_id, question_id)"
        " VALUES (?, ?, ?)",
        (sid, student_id, question_id),
    )
    conn.commit()
    row = conn.execute(
        "SELECT id FROM student_question_sessions WHERE student_id = ? AND question_id = ?",
        (student_id, question_id),
    ).fetchone()
    conn.close()
    return row["id"]
```

- [ ] **Step 5: Run the DB test to confirm it passes**

```bash
cd /Users/douglasyu/src/Cowork/essay-coach && pytest tests/test_student_auth.py::test_create_and_get_student_user -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
cd /Users/douglasyu/src/Cowork/essay-coach && git add db.py tests/test_student_auth.py
git commit -m "feat: add student_users, student_sessions, student_question_sessions tables and db functions"
```

---

## Task 2: API routes (`app.py`)

**Files:**
- Modify: `app.py`
- Test: `tests/test_student_auth.py`

- [ ] **Step 1: Add the remaining 16 HTTP tests to `tests/test_student_auth.py`**

Append to `tests/test_student_auth.py` after the existing DB test:

```python
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
```

- [ ] **Step 2: Run all tests to confirm they fail (routes not yet added)**

```bash
cd /Users/douglasyu/src/Cowork/essay-coach && pytest tests/test_student_auth.py -v --tb=no -q
```

Expected: The new HTTP tests fail with 404 or errors; the DB test still passes.

- [ ] **Step 3: Add the 9 new db imports to `app.py`**

In `app.py`, find the `from db import (` block (lines 19-51). Add the 9 new functions to it:

```python
    create_student_user,
    get_student_by_username,
    get_student_by_email,
    get_student_by_id,
    create_student_session,
    get_student_session,
    update_student_session_expiry,
    delete_student_session,
    get_or_create_question_session,
```

Place them after the existing `update_class_instructor_code,` line, just before the closing `)`.

- [ ] **Step 4: Add `_validate_student_session` helper and student route Pydantic models to `app.py`**

After the `_set_session_cookie` function (around line 84) and before `# ---- HTML routes ----`, add:

```python
def _validate_student_session(student_session_token: str | None) -> dict | None:
    """Return student dict if session is valid and not expired, None otherwise.
    Slides the 30-day expiry window on each valid access."""
    if not student_session_token:
        return None
    session = get_student_session(student_session_token)
    if not session:
        return None
    new_expiry = (datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
    update_student_session_expiry(student_session_token, new_expiry)
    return get_student_by_id(session["student_id"])
```

- [ ] **Step 5: Add Pydantic models for student auth routes**

Just before `# ---- Auth API routes ----` (around line 309), add:

```python
# ---- Student Auth API routes ----

class StudentRegisterRequest(BaseModel):
    username: str
    email: str
    password: str


class StudentLoginRequest(BaseModel):
    username_or_email: str
    password: str
```

- [ ] **Step 6: Add the 5 student auth routes**

Immediately after the Pydantic models, add:

```python
@app.post("/api/student/auth/register")
def api_student_register(data: StudentRegisterRequest):
    if len(data.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    if get_student_by_username(data.username):
        raise HTTPException(status_code=400, detail="Username already taken")
    if get_student_by_email(data.email):
        raise HTTPException(status_code=400, detail="Email already registered")
    student_id = create_student_user(data.username, data.email, hash_password(data.password))
    token = generate_token()
    expires_at = (datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
    create_student_session(token, student_id, expires_at)
    response = JSONResponse({"id": student_id, "username": data.username})
    response.set_cookie(
        key="student_session_token",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=30 * 24 * 3600,
    )
    return response


@app.post("/api/student/auth/login")
def api_student_login(data: StudentLoginRequest):
    student = get_student_by_username(data.username_or_email)
    if not student:
        student = get_student_by_email(data.username_or_email)
    if not student or not verify_password(data.password, student["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = generate_token()
    expires_at = (datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
    create_student_session(token, student["id"], expires_at)
    response = JSONResponse({"id": student["id"], "username": student["username"]})
    response.set_cookie(
        key="student_session_token",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=30 * 24 * 3600,
    )
    return response


@app.post("/api/student/auth/logout")
def api_student_logout(student_session_token: str | None = Cookie(default=None)):
    if student_session_token:
        delete_student_session(student_session_token)
    response = JSONResponse({"ok": True})
    response.delete_cookie("student_session_token", httponly=True, samesite="lax")
    return response


@app.get("/api/student/auth/me")
def api_student_me(student_session_token: str | None = Cookie(default=None)):
    student = _validate_student_session(student_session_token)
    if not student:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {"id": student["id"], "username": student["username"]}


@app.get("/api/student/session/{question_id}")
def api_student_session(
    question_id: str,
    student_session_token: str | None = Cookie(default=None),
):
    student = _validate_student_session(student_session_token)
    if not student:
        raise HTTPException(status_code=401, detail="Not authenticated")
    question = get_question(question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    session_id = get_or_create_question_session(student["id"], question_id)
    return {"session_id": session_id}
```

- [ ] **Step 7: Run all student auth tests**

```bash
cd /Users/douglasyu/src/Cowork/essay-coach && pytest tests/test_student_auth.py -v
```

Expected: All 17 tests pass. (The `test_valid_session_slides_window` test has a 1-second sleep — this is acceptable for correctness.)

- [ ] **Step 8: Run the full test suite to confirm no regressions**

```bash
cd /Users/douglasyu/src/Cowork/essay-coach && pytest -v --tb=short
```

Expected: All existing tests still pass.

- [ ] **Step 9: Commit**

```bash
cd /Users/douglasyu/src/Cowork/essay-coach && git add app.py tests/test_student_auth.py
git commit -m "feat: add student auth API routes (register, login, logout, me, session)"
```

---

## Task 3: Landing page UI — auth-first two-step flow

**Files:**
- Modify: `templates/student.html`
- Modify: `static/app.js`

No new tests — this is pure UI logic. The API routes tested in Task 2 are the source of truth.

- [ ] **Step 1: Replace the `mode == "landing"` block in `templates/student.html`**

Replace the entire `{% if mode == "landing" %}` block (lines 11–28 in `student.html`) with:

```html
{% if mode == "landing" %}
<!-- Step 1: Auth panel (shown when not logged in) -->
<header>
    <h1>Essay Coach</h1>
</header>
<main class="question-list-view">
    <div id="auth-panel">
        <h2>Sign in or create account</h2>
        <div class="class-entry-form">
            <div class="field">
                <input type="text" id="auth-username" placeholder="Username"
                       style="display:block; width:100%; margin-bottom:0.5rem;">
            </div>
            <div class="field" id="auth-email-field" style="display:none">
                <input type="email" id="auth-email" placeholder="Email"
                       style="display:block; width:100%; margin-bottom:0.5rem;">
            </div>
            <div class="field">
                <input type="password" id="auth-password" placeholder="Password"
                       style="display:block; width:100%; margin-bottom:0.5rem;">
            </div>
            <button class="btn btn-primary" style="width:100%; margin-bottom:0.4rem;"
                    onclick="studentSignIn()">Sign in</button>
            <button class="btn btn-secondary" style="width:100%; margin-bottom:0.75rem;"
                    onclick="studentRegister()">Create account</button>
            <p id="auth-error" class="error" style="display:none; margin-bottom:0.5rem;"></p>
            <p style="font-size:0.85rem; color:var(--text-muted);">
                No account?
                <a href="#" onclick="showClassCodePanel(false); return false;">Continue anonymously</a>
                — then enter your class code on the next panel.
            </p>
        </div>
    </div>

    <!-- Step 2: Class code panel (shown after auth or anonymous) -->
    <div id="class-code-panel" style="display:none">
        <div id="student-identity" style="font-size:0.85rem; color:var(--text-muted); margin-bottom:0.75rem;"></div>
        <h2>Enter Your Class Code</h2>
        <div class="class-entry-form">
            <div class="field">
                <input type="text" id="class-code-input" placeholder="e.g. ABC12345" maxlength="8"
                       style="text-transform:uppercase; max-width:200px;">
            </div>
            <button class="btn btn-primary" onclick="resolveClassCode()">Continue</button>
            <p id="class-code-error" class="error" style="margin-top:0.5rem; display:none;">Class not found. Check your code and try again.</p>
        </div>
    </div>
</main>
<script src="/static/app.js"></script>
<script>initStudentLanding();</script>
```

- [ ] **Step 2: Add identity indicator to the workspace block in `templates/student.html`**

In the `{% else %}` (workspace) block, find the `<div class="prompt-section">` line. Add this `<div id="student-identity">` line immediately before it:

```html
        <div id="student-identity" style="font-size:0.85rem; color:var(--text-muted); margin-bottom:0.5rem;"></div>
        <div class="prompt-section">
```

- [ ] **Step 3: Rewrite `initStudentLanding()` and add student auth JS functions in `static/app.js`**

Replace the existing `initStudentLanding()` function (lines 370–380 in `app.js`) with:

```javascript
async function initStudentLanding() {
    const params = new URLSearchParams(window.location.search);
    if (params.get('clear')) {
        localStorage.removeItem('essay_coach_class_id');
    }

    // Check if already authenticated
    const res = await fetch('/api/student/auth/me');
    if (res.ok) {
        const student = await res.json();
        const stored = localStorage.getItem('essay_coach_class_id');
        if (stored) {
            window.location.href = `/student/${stored}`;
            return;
        }
        showClassCodePanel(true, student.username);
    } else {
        // Not logged in — check for stored class_id (anonymous fast-path)
        const stored = localStorage.getItem('essay_coach_class_id');
        if (stored) {
            window.location.href = `/student/${stored}`;
            return;
        }
        // Show auth panel (Step 1)
        document.getElementById('auth-panel').style.display = 'block';
        document.getElementById('class-code-panel').style.display = 'none';
    }
}

function showClassCodePanel(loggedIn, username) {
    document.getElementById('auth-panel').style.display = 'none';
    document.getElementById('class-code-panel').style.display = 'block';
    const identityEl = document.getElementById('student-identity');
    if (loggedIn && username) {
        identityEl.innerHTML =
            `Already signed in as <strong>${escapeHtml(username)}</strong> &nbsp;·&nbsp; ` +
            `<a href="#" onclick="studentSignOut(); return false;">Sign out</a>`;
    } else {
        identityEl.innerHTML =
            `Browsing anonymously &nbsp;·&nbsp; ` +
            `<a href="#" onclick="showAuthPanel(); return false;">Sign in</a>`;
    }
}

function showAuthPanel() {
    document.getElementById('auth-panel').style.display = 'block';
    document.getElementById('class-code-panel').style.display = 'none';
}

async function studentSignIn() {
    const username = document.getElementById('auth-username').value.trim();
    const password = document.getElementById('auth-password').value;
    const errorEl = document.getElementById('auth-error');
    errorEl.style.display = 'none';
    // Hide the email field (used only for registration)
    document.getElementById('auth-email-field').style.display = 'none';
    const res = await fetch('/api/student/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username_or_email: username, password })
    });
    if (!res.ok) {
        errorEl.textContent = 'Invalid username or password.';
        errorEl.style.display = 'block';
        return;
    }
    const data = await res.json();
    showClassCodePanel(true, data.username);
}

async function studentRegister() {
    const errorEl = document.getElementById('auth-error');
    errorEl.style.display = 'none';
    // Show the email field if not already visible
    const emailField = document.getElementById('auth-email-field');
    if (emailField.style.display === 'none') {
        // First click: reveal email field and prompt user to fill it in
        emailField.style.display = 'block';
        document.getElementById('auth-email').focus();
        errorEl.textContent = 'Enter your email above, then click Create account again.';
        errorEl.style.display = 'block';
        return;
    }
    const username = document.getElementById('auth-username').value.trim();
    const email = document.getElementById('auth-email').value.trim();
    const password = document.getElementById('auth-password').value;
    const res = await fetch('/api/student/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, email, password })
    });
    if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        errorEl.textContent = data.detail || 'Registration failed. Check your details and try again.';
        errorEl.style.display = 'block';
        return;
    }
    const data = await res.json();
    showClassCodePanel(true, data.username);
}

async function studentSignOut() {
    await fetch('/api/student/auth/logout', { method: 'POST' });
    window.location.href = '/student';
}
```

- [ ] **Step 4: Update `initStudent()` in `static/app.js` to resolve session_id from the API**

Replace the existing `initStudent()` function (lines 15–17 in `app.js`):

```javascript
// Module-level resolved session ID for this page load
let _resolvedSessionId = null;

async function initStudent() {
    // Try to get a server-managed session_id for logged-in students
    const res = await fetch(`/api/student/session/${QUESTION_ID}`);
    if (res.ok) {
        const data = await res.json();
        _resolvedSessionId = data.session_id;
        // Show identity indicator
        const meRes = await fetch('/api/student/auth/me');
        if (meRes.ok) {
            const student = await meRes.json();
            const identityEl = document.getElementById('student-identity');
            if (identityEl) {
                identityEl.innerHTML =
                    `Already signed in as <strong>${escapeHtml(student.username)}</strong> &nbsp;·&nbsp; ` +
                    `<a href="#" onclick="studentSignOut(); return false;">Sign out</a>`;
            }
        }
    } else {
        // Anonymous fallback
        _resolvedSessionId = getSessionId();
    }
    loadAttemptHistory();
}
```

- [ ] **Step 5: Update all places in `app.js` that call `getSessionId()` within student flows to use `_resolvedSessionId`**

Find every call to `getSessionId()` in the student-facing functions (`submitForFeedback`, `loadAttemptHistory`). Replace them with `_resolvedSessionId`:

In `submitForFeedback()` (around line 48), change:
```javascript
                session_id: getSessionId()
```
to:
```javascript
                session_id: _resolvedSessionId
```

In `loadAttemptHistory()` (around line 116), change:
```javascript
    const res = await fetch(`/api/attempts/${QUESTION_ID}?session_id=${getSessionId()}`);
```
to:
```javascript
    const res = await fetch(`/api/attempts/${QUESTION_ID}?session_id=${_resolvedSessionId}`);
```

- [ ] **Step 6: Add `studentSignOut` function for the workspace**

The `studentSignOut` function was added in Step 3 for the landing page. It is also used in the workspace identity indicator. No additional code needed — the function is already defined globally.

- [ ] **Step 7: Smoke-test the app manually**

```bash
cd /Users/douglasyu/src/Cowork/essay-coach && uvicorn app:app --reload
```

1. Open `http://localhost:8000/student`
2. Confirm Step 1 (auth panel) appears
3. Click "Continue anonymously" → confirm Step 2 (class code panel) appears with "Browsing anonymously · Sign in"
4. Click "Create account" → enter test credentials → confirm Step 2 appears with "Already signed in as [username]"
5. Navigate to a question workspace → confirm "Already signed in as" indicator appears above the prompt
6. Click "Sign out" → confirm redirect to landing page with auth panel

- [ ] **Step 8: Run the full test suite**

```bash
cd /Users/douglasyu/src/Cowork/essay-coach && pytest -v --tb=short
```

Expected: All tests pass.

- [ ] **Step 9: Commit**

```bash
cd /Users/douglasyu/src/Cowork/essay-coach && git add templates/student.html static/app.js
git commit -m "feat: add auth-first two-step landing page and workspace identity indicator"
```

---

## Final verification

- [ ] **Run the full test suite one last time**

```bash
cd /Users/douglasyu/src/Cowork/essay-coach && pytest -v
```

Expected: All tests pass with no failures.
