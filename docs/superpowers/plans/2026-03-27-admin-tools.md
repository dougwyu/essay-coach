# Admin Tools Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a super-admin role with an admin dashboard (user list, invite code management, class overview), email field on instructor accounts, and an admin-initiated password reset flow (no SMTP required).

**Architecture:** The first instructor to register is auto-promoted to admin (`is_admin=1` in `users`). Any admin can promote/demote other instructors and generate one-time password-reset links they share manually. No email-sending infrastructure is required — the reset URL is displayed in the admin dashboard for the admin to copy and share. A new `require_admin_api` dependency guards all `/api/admin/*` routes. The admin dashboard (`/admin`) is a JS-driven single-page view matching the existing instructor UI pattern.

**Tech Stack:** Python/FastAPI, SQLite + PostgreSQL (via db_connection abstraction), Jinja2 templates, vanilla JS, bcrypt (passlib), existing `auth.py` helpers.

---

## File Map

| File | Change |
|------|--------|
| `db.py` | Add `email` + `is_admin` columns to `users`; add `password_reset_tokens` table; add/update functions: `create_user`, `list_users`, `delete_user`, `get_user_by_email`, `set_user_admin`, `create_password_reset_token`, `get_password_reset_token`, `consume_password_reset_token` |
| `dependencies.py` | Add `require_admin_api` |
| `app.py` | Update `/api/auth/register` to accept `email`; add admin page route; add `/api/admin/*` routes |
| `templates/register.html` | Add email field |
| `templates/admin.html` | New: admin dashboard (user list, invite code, class overview) |
| `templates/reset-password.html` | New: password-reset form (token in URL, new password input) |
| `tests/test_admin.py` | New: integration tests for all admin API routes |
| `tests/test_db.py` | Update `create_user` calls to pass `email` |
| `tests/test_auth.py` | Update `create_user` calls to pass `email` |
| `tests/test_auth_integration.py` | Update register payload to include `email` |
| `tests/test_classes_integration.py` | Update any `create_user` calls |

---

### Task 1: Schema — add email, is_admin, password_reset_tokens

**Files:**
- Modify: `db.py`

- [ ] **Step 1: Write failing tests for new schema columns**

```python
# tests/test_db.py  — add inside the existing test file
def test_create_user_stores_email(tmp_db):
    uid = create_user("alice", "hash", "alice@uni.ac.uk")
    user = get_user_by_username("alice")
    assert user["email"] == "alice@uni.ac.uk"

def test_first_user_is_admin(tmp_db):
    uid = create_user("alice", "hash", "alice@uni.ac.uk")
    user = get_user_by_username("alice")
    assert user["is_admin"] == 1

def test_second_user_is_not_admin(tmp_db):
    create_user("alice", "hash", "alice@uni.ac.uk")
    create_user("bob", "hash", "bob@uni.ac.uk")
    bob = get_user_by_username("bob")
    assert bob["is_admin"] == 0

def test_get_user_by_email(tmp_db):
    create_user("alice", "hash", "alice@uni.ac.uk")
    user = get_user_by_email("alice@uni.ac.uk")
    assert user["username"] == "alice"

def test_list_users(tmp_db):
    create_user("alice", "hash", "alice@uni.ac.uk")
    create_user("bob", "hash", "bob@uni.ac.uk")
    users = list_users()
    assert len(users) == 2

def test_delete_user(tmp_db):
    uid = create_user("alice", "hash", "alice@uni.ac.uk")
    delete_user(uid)
    assert get_user_by_username("alice") is None

def test_set_user_admin(tmp_db):
    create_user("alice", "hash", "alice@uni.ac.uk")
    uid2 = create_user("bob", "hash", "bob@uni.ac.uk")
    set_user_admin(uid2, True)
    bob = get_user_by_username("bob")
    assert bob["is_admin"] == 1
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /Users/douglasyu/src/Cowork/essay-coach
pytest tests/test_db.py::test_create_user_stores_email tests/test_db.py::test_first_user_is_admin -v
```
Expected: FAIL — `create_user` doesn't accept `email` argument.

- [ ] **Step 3: Update `_init_db_sqlite` — add columns to `users` and new table**

In `db.py`, update the `CREATE TABLE IF NOT EXISTS users` statement inside `_init_db_sqlite`:

```python
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE,
            password_hash TEXT NOT NULL,
            is_admin INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
```

Add the `password_reset_tokens` table to `_init_db_sqlite` (before the `DELETE FROM sessions` line):

```python
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            token TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            expires_at TIMESTAMP NOT NULL,
            used INTEGER NOT NULL DEFAULT 0
        );
```

Add SQLite migration block (after the existing migration blocks, before the invite-code seed):

```python
    # Migration: add email + is_admin to users
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
    if "email" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN email TEXT")
        conn.commit()
    if "is_admin" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0")
        # promote first user
        first_user = conn.execute(
            "SELECT id FROM users ORDER BY created_at ASC LIMIT 1"
        ).fetchone()
        if first_user:
            conn.execute(
                "UPDATE users SET is_admin=1 WHERE id=%s", (first_user["id"],)
            )
        conn.commit()

    # Migration: add password_reset_tokens table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            token TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            expires_at TIMESTAMP NOT NULL,
            used INTEGER NOT NULL DEFAULT 0
        )
    """)
    conn.commit()
```

- [ ] **Step 4: Update `_init_db_postgres` — add columns to `users` and new table**

In `_init_db_postgres`, update the `users` CREATE TABLE:

```python
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE,
            password_hash TEXT NOT NULL,
            is_admin INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW()
        );
```

Add to the executescript (before `DELETE FROM sessions WHERE expires_at < NOW()`):

```python
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            token TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            expires_at TIMESTAMP NOT NULL,
            used INTEGER NOT NULL DEFAULT 0
        );
```

- [ ] **Step 5: Update `create_user` to accept `email`, auto-promote first user**

Replace the existing `create_user` function in `db.py`:

```python
def create_user(username: str, password_hash: str, email: str = "") -> str:
    uid = str(uuid.uuid4())
    conn = _connect()
    # First registered user becomes admin
    row = conn.execute("SELECT COUNT(*) AS cnt FROM users").fetchone()
    is_admin = 1 if row["cnt"] == 0 else 0
    conn.execute(
        "INSERT INTO users (id, username, email, password_hash, is_admin) VALUES (%s, %s, %s, %s, %s)",
        (uid, username, email, password_hash, is_admin),
    )
    conn.commit()
    conn.close()
    return uid
```

- [ ] **Step 6: Add new db functions after `get_user_by_id`**

```python
def get_user_by_email(email: str) -> dict | None:
    conn = _connect()
    row = conn.execute(
        "SELECT * FROM users WHERE email = %s", (email,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def list_users() -> list[dict]:
    conn = _connect()
    rows = conn.execute(
        "SELECT id, username, email, is_admin, created_at FROM users ORDER BY created_at ASC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_user(user_id: str) -> None:
    conn = _connect()
    conn.execute("DELETE FROM users WHERE id = %s", (user_id,))
    conn.commit()
    conn.close()


def set_user_admin(user_id: str, is_admin: bool) -> None:
    conn = _connect()
    conn.execute(
        "UPDATE users SET is_admin = %s WHERE id = %s",
        (1 if is_admin else 0, user_id),
    )
    conn.commit()
    conn.close()


def create_password_reset_token(user_id: str) -> str:
    """Create a single-use 24-hour password reset token. Returns the token string."""
    import secrets as _secrets
    from datetime import datetime, timezone, timedelta
    token = _secrets.token_hex(32)
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=24)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    conn = _connect()
    # Delete any existing unused tokens for this user
    conn.execute(
        "DELETE FROM password_reset_tokens WHERE user_id = %s", (user_id,)
    )
    conn.execute(
        "INSERT INTO password_reset_tokens (token, user_id, expires_at, used) VALUES (%s, %s, %s, 0)",
        (token, user_id, expires_at),
    )
    conn.commit()
    conn.close()
    return token


def get_password_reset_token(token: str) -> dict | None:
    """Return token row if it exists, is unused, and has not expired."""
    from datetime import datetime, timezone
    conn = _connect()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    row = conn.execute(
        "SELECT * FROM password_reset_tokens WHERE token = %s AND used = 0 AND expires_at > %s",
        (token, now),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def consume_password_reset_token(token: str, new_password_hash: str) -> bool:
    """Mark token used and update the user's password. Returns True on success."""
    row = get_password_reset_token(token)
    if not row:
        return False
    conn = _connect()
    conn.execute(
        "UPDATE password_reset_tokens SET used = 1 WHERE token = %s", (token,)
    )
    conn.execute(
        "UPDATE users SET password_hash = %s WHERE id = %s",
        (new_password_hash, row["user_id"]),
    )
    conn.commit()
    conn.close()
    return True
```

- [ ] **Step 7: Run failing tests**

```bash
pytest tests/test_db.py::test_create_user_stores_email tests/test_db.py::test_first_user_is_admin tests/test_db.py::test_second_user_is_not_admin tests/test_db.py::test_get_user_by_email tests/test_db.py::test_list_users tests/test_db.py::test_delete_user tests/test_db.py::test_set_user_admin -v
```
Expected: all PASS.

- [ ] **Step 8: Update existing tests that call `create_user` without email**

In `tests/test_db.py` and `tests/test_auth.py`, find any existing calls to `create_user("alice", "hash")` and add a dummy email argument: `create_user("alice", "hash", "alice@test.com")`.

Run:
```bash
pytest tests/test_db.py tests/test_auth.py -v
```
Expected: all PASS.

- [ ] **Step 9: Add password reset token tests**

```python
# tests/test_db.py — add these tests
from db import create_password_reset_token, get_password_reset_token, consume_password_reset_token

def test_password_reset_token_roundtrip(tmp_db):
    uid = create_user("alice", "newhash", "alice@uni.ac.uk")
    token = create_password_reset_token(uid)
    row = get_password_reset_token(token)
    assert row is not None
    assert row["user_id"] == uid

def test_consume_password_reset_token(tmp_db):
    uid = create_user("alice", "oldhash", "alice@uni.ac.uk")
    token = create_password_reset_token(uid)
    result = consume_password_reset_token(token, "newhash")
    assert result is True
    user = get_user_by_username("alice")
    assert user["password_hash"] == "newhash"

def test_consume_used_token_fails(tmp_db):
    uid = create_user("alice", "oldhash", "alice@uni.ac.uk")
    token = create_password_reset_token(uid)
    consume_password_reset_token(token, "newhash")
    result = consume_password_reset_token(token, "anotherhash")
    assert result is False
```

Run:
```bash
pytest tests/test_db.py -v -k "reset"
```
Expected: all PASS.

- [ ] **Step 10: Commit**

```bash
git add db.py tests/test_db.py tests/test_auth.py
git commit -m "feat: add email, is_admin, password_reset_tokens to users schema"
```

---

### Task 2: require_admin_api dependency

**Files:**
- Modify: `dependencies.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_admin.py — new file
import pytest
from fastapi.testclient import TestClient
import config as config_module
from app import app
from auth import hash_password
from db import init_db, create_user

client = TestClient(app, raise_server_exceptions=False)

@pytest.fixture
def tmp_db(monkeypatch, tmp_path):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(config_module, "DATABASE_PATH", db_path)
    init_db()
    yield db_path

def _register_and_login(username, email, password, invite_code=None):
    """Helper: register instructor and return session cookie."""
    if invite_code is None:
        import sqlite3
        conn = sqlite3.connect(config_module.DATABASE_PATH)
        row = conn.execute("SELECT value FROM settings WHERE key='invite_code'").fetchone()
        conn.close()
        invite_code = row[0]
    res = client.post("/api/auth/register", json={
        "username": username,
        "email": email,
        "password": password,
        "invite_code": invite_code,
    })
    assert res.status_code == 200, res.text
    return res.cookies

def test_admin_route_requires_auth(tmp_db):
    res = client.get("/admin", follow_redirects=False)
    assert res.status_code == 303

def test_admin_api_requires_admin(tmp_db):
    # Register first user (auto-admin), then register second (non-admin) and try admin API
    cookies1 = _register_and_login("alice", "alice@uni.ac.uk", "password123")
    # rotate invite code so bob can register
    res = client.post("/api/auth/invite-code", json={"code": "NEWCODE1"}, cookies=cookies1)
    assert res.status_code == 200
    cookies2 = _register_and_login("bob", "bob@uni.ac.uk", "password123", invite_code="NEWCODE1")
    res = client.get("/api/admin/users", cookies=cookies2)
    assert res.status_code == 403

def test_admin_api_allows_admin(tmp_db):
    cookies = _register_and_login("alice", "alice@uni.ac.uk", "password123")
    res = client.get("/api/admin/users", cookies=cookies)
    assert res.status_code == 200
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
pytest tests/test_admin.py::test_admin_api_requires_admin -v
```
Expected: FAIL — `/api/admin/users` route does not exist yet.

- [ ] **Step 3: Add `require_admin_api` to `dependencies.py`**

Read the existing `require_instructor_api` in `dependencies.py` and add after it:

```python
async def require_admin_api(
    request: Request,
    session_token: Optional[str] = Cookie(default=None),
) -> dict:
    """Like require_instructor_api but also checks is_admin == 1."""
    user = await _validate_session(session_token)
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user
```

Add `require_admin_api` to the imports in `app.py`:

```python
from dependencies import _validate_session, require_instructor_api, require_class_member, require_admin_api
```

- [ ] **Step 4: Add placeholder `/api/admin/users` route to `app.py`** (just enough for the test to pass — will be fleshed out in Task 4)

```python
@app.get("/api/admin/users")
def api_admin_list_users(user: dict = Depends(require_admin_api)):
    from db import list_users
    return list_users()
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_admin.py -v
```
Expected: all 3 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add dependencies.py app.py tests/test_admin.py
git commit -m "feat: add require_admin_api dependency and stub admin users endpoint"
```

---

### Task 3: Update registration to accept email

**Files:**
- Modify: `app.py` (register endpoint)
- Modify: `templates/register.html`
- Modify: `tests/test_auth_integration.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_auth_integration.py — add this test
def test_register_stores_email(tmp_db):
    from db import get_user_by_email
    import sqlite3
    conn = sqlite3.connect(config_module.DATABASE_PATH)
    code = conn.execute("SELECT value FROM settings WHERE key='invite_code'").fetchone()[0]
    conn.close()
    res = client.post("/api/auth/register", json={
        "username": "carol",
        "email": "carol@uni.ac.uk",
        "password": "password123",
        "invite_code": code,
    })
    assert res.status_code == 200
    user = get_user_by_email("carol@uni.ac.uk")
    assert user is not None
    assert user["username"] == "carol"
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
pytest tests/test_auth_integration.py::test_register_stores_email -v
```
Expected: FAIL — `RegisterRequest` model lacks `email` field.

- [ ] **Step 3: Update the `RegisterRequest` model and register endpoint in `app.py`**

Find the `RegisterRequest` Pydantic model (near the `/api/auth/register` route):

```python
class RegisterRequest(BaseModel):
    username: str
    email: str = ""
    password: str
    invite_code: str
```

Find the `api_register` function and update the `create_user` call:

```python
user_id = create_user(data.username, hash_password(data.password), data.email)
```

- [ ] **Step 4: Add `get_user_by_email` and `create_user` (with email) to the `app.py` imports from `db`**

```python
from db import (
    ...
    get_user_by_email,
    ...
)
```

- [ ] **Step 5: Update `register.html` to add email field**

Add after the username field and before the password field:

```html
<div class="field">
    <label for="email">Email</label>
    <input type="email" id="email" required autocomplete="email" placeholder="you@university.ac.uk">
</div>
```

Update the `fetch` body in the `<script>` block to include `email`:

```javascript
body: JSON.stringify({
    username: document.getElementById('username').value,
    email: document.getElementById('email').value,
    password: document.getElementById('password').value,
    invite_code: document.getElementById('invite-code').value,
})
```

- [ ] **Step 6: Update existing register tests that omit email**

In `tests/test_auth_integration.py`, find all `client.post("/api/auth/register", json={...})` calls that lack `"email"` and add `"email": "user@test.com"` (or use unique emails per test). Run all auth integration tests:

```bash
pytest tests/test_auth_integration.py -v
```
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add app.py templates/register.html tests/test_auth_integration.py
git commit -m "feat: add email field to instructor registration"
```

---

### Task 4: Admin API routes

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_admin.py — add these tests

def test_admin_delete_user(tmp_db):
    cookies1 = _register_and_login("alice", "alice@uni.ac.uk", "password123")
    client.post("/api/auth/invite-code", json={"code": "NEWCODE1"}, cookies=cookies1)
    _register_and_login("bob", "bob@uni.ac.uk", "password123", invite_code="NEWCODE1")
    from db import get_user_by_username
    bob = get_user_by_username("bob")
    res = client.delete(f"/api/admin/users/{bob['id']}", cookies=cookies1)
    assert res.status_code == 200
    assert get_user_by_username("bob") is None

def test_admin_cannot_delete_self(tmp_db):
    cookies = _register_and_login("alice", "alice@uni.ac.uk", "password123")
    from db import get_user_by_username
    alice = get_user_by_username("alice")
    res = client.delete(f"/api/admin/users/{alice['id']}", cookies=cookies)
    assert res.status_code == 400

def test_admin_promote_user(tmp_db):
    cookies1 = _register_and_login("alice", "alice@uni.ac.uk", "password123")
    client.post("/api/auth/invite-code", json={"code": "NEWCODE1"}, cookies=cookies1)
    _register_and_login("bob", "bob@uni.ac.uk", "password123", invite_code="NEWCODE1")
    from db import get_user_by_username
    bob = get_user_by_username("bob")
    res = client.post(f"/api/admin/users/{bob['id']}/promote", cookies=cookies1)
    assert res.status_code == 200
    assert get_user_by_username("bob")["is_admin"] == 1

def test_admin_generate_reset_link(tmp_db):
    cookies1 = _register_and_login("alice", "alice@uni.ac.uk", "password123")
    client.post("/api/auth/invite-code", json={"code": "NEWCODE1"}, cookies=cookies1)
    _register_and_login("bob", "bob@uni.ac.uk", "password123", invite_code="NEWCODE1")
    from db import get_user_by_username
    bob = get_user_by_username("bob")
    res = client.post(f"/api/admin/users/{bob['id']}/reset-password", cookies=cookies1)
    assert res.status_code == 200
    data = res.json()
    assert "reset_url" in data
    assert data["reset_url"].startswith("http")

def test_admin_class_overview(tmp_db):
    cookies = _register_and_login("alice", "alice@uni.ac.uk", "password123")
    res = client.get("/api/admin/classes", cookies=cookies)
    assert res.status_code == 200
    assert isinstance(res.json(), list)
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_admin.py -v
```
Expected: 5 new tests FAIL, 3 old tests PASS.

- [ ] **Step 3: Add admin routes to `app.py`**

Add the following imports at the top of `app.py` (merge with existing `db` imports):
```python
from db import (
    ...
    list_users,
    delete_user,
    get_user_by_email,
    set_user_admin,
    create_password_reset_token,
    list_all_classes,
)
```

Add after the existing `/api/admin/users` GET route:

```python
@app.delete("/api/admin/users/{user_id}")
def api_admin_delete_user(user_id: str, user: dict = Depends(require_admin_api)):
    if user_id == user["id"]:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    delete_user(user_id)
    return {"ok": True}


@app.post("/api/admin/users/{user_id}/promote")
def api_admin_promote_user(user_id: str, user: dict = Depends(require_admin_api)):
    set_user_admin(user_id, True)
    return {"ok": True}


@app.post("/api/admin/users/{user_id}/demote")
def api_admin_demote_user(user_id: str, user: dict = Depends(require_admin_api)):
    if user_id == user["id"]:
        raise HTTPException(status_code=400, detail="Cannot demote yourself")
    set_user_admin(user_id, False)
    return {"ok": True}


@app.post("/api/admin/users/{user_id}/reset-password")
def api_admin_reset_password(user_id: str, request: Request, user: dict = Depends(require_admin_api)):
    token = create_password_reset_token(user_id)
    base_url = str(request.base_url).rstrip("/")
    return {"reset_url": f"{base_url}/reset-password?token={token}"}


@app.get("/api/admin/classes")
def api_admin_classes(user: dict = Depends(require_admin_api)):
    from db import list_all_classes
    return list_all_classes()
```

- [ ] **Step 4: Add `list_all_classes` to `db.py`**

```python
def list_all_classes() -> list[dict]:
    """Return all classes with instructor username and question count."""
    conn = _connect()
    rows = conn.execute(
        """SELECT c.id, c.name, c.student_code, c.created_at,
                  u.username AS instructor,
                  (SELECT COUNT(*) FROM questions q WHERE q.class_id = c.id) AS question_count
           FROM classes c
           LEFT JOIN users u ON c.created_by = u.id
           ORDER BY c.created_at ASC"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_admin.py -v
```
Expected: all 8 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add app.py db.py tests/test_admin.py
git commit -m "feat: add admin API routes (users, classes, reset-password)"
```

---

### Task 5: Admin dashboard template

**Files:**
- Create: `templates/admin.html`
- Modify: `app.py` (add `/admin` page route)

- [ ] **Step 1: Add `/admin` page route to `app.py`**

Find the `/instructor` page route for reference. Add:

```python
@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request, session_token: Optional[str] = Cookie(default=None)):
    user = await _validate_session(session_token)
    if not user:
        return RedirectResponse("/login?next=/admin", status_code=303)
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return templates.TemplateResponse("admin.html", {"request": request, "username": user["username"]})
```

- [ ] **Step 2: Create `templates/admin.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Essay Coach — Admin</title>
    <link rel="stylesheet" href="/static/style.css">
</head>
<body>
    <header>
        <h1>Essay Coach <span class="badge">Admin</span></h1>
        <nav>
            <span class="username-display">{{ username }}</span>
            <a href="/instructor" class="btn btn-small">Instructor View</a>
            <form method="POST" action="/logout" style="display:inline; margin-left:0.75rem;">
                <button type="submit" class="btn btn-small">Sign Out</button>
            </form>
        </nav>
    </header>
    <main>

        <section class="admin-section">
            <h2>Instructors</h2>
            <div id="invite-code-row" style="margin-bottom:1rem;">
                Invite code: <strong id="invite-code-val">—</strong>
                <button class="btn btn-small" onclick="rotateInviteCode()">Rotate</button>
            </div>
            <table id="users-table" class="data-table">
                <thead>
                    <tr>
                        <th>Username</th>
                        <th>Email</th>
                        <th>Role</th>
                        <th>Registered</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody id="users-tbody"></tbody>
            </table>
        </section>

        <section class="admin-section" style="margin-top:2rem;">
            <h2>Classes</h2>
            <table id="classes-table" class="data-table">
                <thead>
                    <tr>
                        <th>Class</th>
                        <th>Instructor</th>
                        <th>Questions</th>
                        <th>Student code</th>
                        <th>Created</th>
                    </tr>
                </thead>
                <tbody id="classes-tbody"></tbody>
            </table>
        </section>

        <div id="reset-link-box" class="info-box" style="display:none; margin-top:1.5rem;">
            <strong>Password reset link (share with instructor):</strong><br>
            <a id="reset-link-val" href="#" target="_blank"></a>
            <button class="btn btn-small" onclick="copyResetLink()">Copy</button>
        </div>

    </main>
    <script>
        const ME_USERNAME = "{{ username }}";

        async function loadInviteCode() {
            const res = await fetch('/api/auth/invite-code');
            if (res.ok) {
                const d = await res.json();
                document.getElementById('invite-code-val').textContent = d.invite_code;
            }
        }

        async function rotateInviteCode() {
            if (!confirm('Rotate invite code? The current code will stop working.')) return;
            const res = await fetch('/api/auth/invite-code', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({}) });
            if (res.ok) loadInviteCode();
        }

        async function loadUsers() {
            const res = await fetch('/api/admin/users');
            if (!res.ok) return;
            const users = await res.json();
            const tbody = document.getElementById('users-tbody');
            tbody.innerHTML = '';
            for (const u of users) {
                const isSelf = u.username === ME_USERNAME;
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td>${esc(u.username)}</td>
                    <td>${esc(u.email || '—')}</td>
                    <td>${u.is_admin ? '<span class="badge">Admin</span>' : 'Instructor'}</td>
                    <td>${u.created_at ? u.created_at.slice(0,10) : '—'}</td>
                    <td>
                        ${!isSelf && !u.is_admin ? `<button class="btn btn-small" onclick="promoteUser('${u.id}')">Make Admin</button>` : ''}
                        ${!isSelf && u.is_admin ? `<button class="btn btn-small" onclick="demoteUser('${u.id}')">Remove Admin</button>` : ''}
                        <button class="btn btn-small" onclick="generateResetLink('${u.id}')">Reset Password</button>
                        ${!isSelf ? `<button class="btn btn-small btn-danger" onclick="deleteUser('${u.id}', '${esc(u.username)}')">Delete</button>` : ''}
                    </td>
                `;
                tbody.appendChild(tr);
            }
        }

        async function loadClasses() {
            const res = await fetch('/api/admin/classes');
            if (!res.ok) return;
            const classes = await res.json();
            const tbody = document.getElementById('classes-tbody');
            tbody.innerHTML = '';
            for (const c of classes) {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td>${esc(c.name)}</td>
                    <td>${esc(c.instructor || '—')}</td>
                    <td>${c.question_count}</td>
                    <td><code>${esc(c.student_code)}</code></td>
                    <td>${c.created_at ? c.created_at.slice(0,10) : '—'}</td>
                `;
                tbody.appendChild(tr);
            }
        }

        async function promoteUser(userId) {
            await fetch(`/api/admin/users/${userId}/promote`, { method: 'POST' });
            loadUsers();
        }

        async function demoteUser(userId) {
            await fetch(`/api/admin/users/${userId}/demote`, { method: 'POST' });
            loadUsers();
        }

        async function deleteUser(userId, username) {
            if (!confirm(`Delete instructor "${username}"? This cannot be undone.`)) return;
            await fetch(`/api/admin/users/${userId}`, { method: 'DELETE' });
            loadUsers();
        }

        async function generateResetLink(userId) {
            const res = await fetch(`/api/admin/users/${userId}/reset-password`, { method: 'POST' });
            if (!res.ok) return;
            const data = await res.json();
            const box = document.getElementById('reset-link-box');
            const link = document.getElementById('reset-link-val');
            link.textContent = data.reset_url;
            link.href = data.reset_url;
            box.style.display = 'block';
            box.scrollIntoView({ behavior: 'smooth' });
        }

        function copyResetLink() {
            const url = document.getElementById('reset-link-val').textContent;
            navigator.clipboard.writeText(url).then(() => alert('Copied to clipboard.'));
        }

        function esc(s) {
            if (!s) return '';
            return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
        }

        loadInviteCode();
        loadUsers();
        loadClasses();
    </script>
</body>
</html>
```

- [ ] **Step 3: Verify the admin page loads**

```bash
cd /Users/douglasyu/src/Cowork/essay-coach
python app.py &
sleep 2
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/admin
# Expected: 303 (redirect to login — not logged in)
kill %1
```

- [ ] **Step 4: Run full test suite**

```bash
pytest -v --tb=short
```
Expected: all existing tests PASS, new admin tests PASS.

- [ ] **Step 5: Commit**

```bash
git add templates/admin.html app.py
git commit -m "feat: add admin dashboard template and /admin page route"
```

---

### Task 6: Password reset flow (user-facing)

**Files:**
- Create: `templates/reset-password.html`
- Modify: `app.py` (add `/reset-password` page route and `/api/auth/reset-password` API)

- [ ] **Step 1: Write failing tests**

```python
# tests/test_admin.py — add these tests
def test_reset_password_flow(tmp_db):
    """Full flow: admin generates token → user POSTs new password → can log in."""
    cookies1 = _register_and_login("alice", "alice@uni.ac.uk", "password123")
    client.post("/api/auth/invite-code", json={"code": "NEWCODE1"}, cookies=cookies1)
    _register_and_login("bob", "bob@uni.ac.uk", "password123", invite_code="NEWCODE1")
    from db import get_user_by_username
    bob = get_user_by_username("bob")
    # Admin generates reset link
    res = client.post(f"/api/admin/users/{bob['id']}/reset-password", cookies=cookies1)
    reset_url = res.json()["reset_url"]
    token = reset_url.split("token=")[1]
    # Bob uses the token to set new password
    res2 = client.post("/api/auth/reset-password", json={"token": token, "password": "newpass456"})
    assert res2.status_code == 200
    # Bob can now log in with new password
    res3 = client.post("/api/auth/login", json={"username": "bob", "password": "newpass456"})
    assert res3.status_code == 200

def test_reset_password_bad_token(tmp_db):
    res = client.post("/api/auth/reset-password", json={"token": "badtoken", "password": "newpass456"})
    assert res.status_code == 400

def test_reset_password_token_single_use(tmp_db):
    cookies1 = _register_and_login("alice", "alice@uni.ac.uk", "password123")
    client.post("/api/auth/invite-code", json={"code": "NEWCODE1"}, cookies=cookies1)
    _register_and_login("bob", "bob@uni.ac.uk", "password123", invite_code="NEWCODE1")
    from db import get_user_by_username
    bob = get_user_by_username("bob")
    res = client.post(f"/api/admin/users/{bob['id']}/reset-password", cookies=cookies1)
    token = res.json()["reset_url"].split("token=")[1]
    client.post("/api/auth/reset-password", json={"token": token, "password": "newpass456"})
    # Second use of same token must fail
    res2 = client.post("/api/auth/reset-password", json={"token": token, "password": "anotherpass"})
    assert res2.status_code == 400
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_admin.py::test_reset_password_flow tests/test_admin.py::test_reset_password_bad_token -v
```
Expected: FAIL — `/api/auth/reset-password` does not exist.

- [ ] **Step 3: Add reset password API endpoint to `app.py`**

Add imports to db import block: `consume_password_reset_token`

```python
class ResetPasswordRequest(BaseModel):
    token: str
    password: str


@app.post("/api/auth/reset-password")
def api_reset_password(data: ResetPasswordRequest):
    if len(data.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    ok = consume_password_reset_token(data.token, hash_password(data.password))
    if not ok:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    return {"ok": True}
```

Add page route (serves the HTML form):

```python
@app.get("/reset-password", response_class=HTMLResponse)
async def reset_password_page(request: Request, token: str = ""):
    return templates.TemplateResponse("reset-password.html", {"request": request, "token": token})
```

- [ ] **Step 4: Create `templates/reset-password.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Essay Coach — Reset Password</title>
    <link rel="stylesheet" href="/static/style.css">
</head>
<body>
    <header>
        <h1>Essay Coach <span class="badge">Instructor</span></h1>
    </header>
    <main class="auth-layout">
        <section class="auth-form">
            <h2>Set New Password</h2>
            <div id="error-msg" class="error" style="display:none"></div>
            <div id="success-msg" class="success" style="display:none"></div>
            <form id="reset-form">
                <div class="field">
                    <label for="password">New Password <span class="optional">(8–72 characters)</span></label>
                    <input type="password" id="password" required autocomplete="new-password" minlength="8" maxlength="72">
                </div>
                <div class="field">
                    <label for="password2">Confirm Password</label>
                    <input type="password" id="password2" required autocomplete="new-password" minlength="8" maxlength="72">
                </div>
                <div class="form-actions">
                    <button type="submit" class="btn btn-primary">Set Password</button>
                </div>
            </form>
            <p class="auth-link"><a href="/login">Back to Sign In</a></p>
        </section>
    </main>
    <script>
        const TOKEN = new URLSearchParams(window.location.search).get('token') || '';

        document.getElementById('reset-form').addEventListener('submit', async function(e) {
            e.preventDefault();
            const errEl = document.getElementById('error-msg');
            const okEl = document.getElementById('success-msg');
            errEl.style.display = 'none';
            okEl.style.display = 'none';
            const pw = document.getElementById('password').value;
            const pw2 = document.getElementById('password2').value;
            if (pw !== pw2) {
                errEl.textContent = 'Passwords do not match.';
                errEl.style.display = 'block';
                return;
            }
            try {
                const res = await fetch('/api/auth/reset-password', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ token: TOKEN, password: pw }),
                });
                if (res.ok) {
                    okEl.textContent = 'Password updated. You can now sign in.';
                    okEl.style.display = 'block';
                    document.getElementById('reset-form').style.display = 'none';
                } else {
                    const data = await res.json().catch(() => ({}));
                    errEl.textContent = data.detail || 'Reset failed. The link may have expired.';
                    errEl.style.display = 'block';
                }
            } catch (_) {
                errEl.textContent = 'Network error. Please try again.';
                errEl.style.display = 'block';
            }
        });
    </script>
</body>
</html>
```

- [ ] **Step 5: Run all admin tests**

```bash
pytest tests/test_admin.py -v
```
Expected: all 11 tests PASS.

- [ ] **Step 6: Run full test suite**

```bash
pytest -v --tb=short
```
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add templates/reset-password.html app.py tests/test_admin.py
git commit -m "feat: add password reset flow (admin-generated one-time link)"
```

---

### Task 7: Add admin link to instructor dashboard + CSS polish

**Files:**
- Modify: `templates/instructor.html`
- Modify: `static/style.css`

- [ ] **Step 1: Add "Admin" nav link to `instructor.html` (conditionally rendered)**

The `instructor.html` template already receives `username` from the route. We need `is_admin` too. Update the `/instructor` page route in `app.py`:

```python
@app.get("/instructor", response_class=HTMLResponse)
async def instructor_page(request: Request, session_token: Optional[str] = Cookie(default=None)):
    user = await _validate_session(session_token)
    if not user:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse("instructor.html", {
        "request": request,
        "username": user["username"],
        "is_admin": bool(user.get("is_admin")),
    })
```

In `templates/instructor.html`, add the Admin link in the `<nav>` block after the username display:

```html
{% if is_admin %}
<a href="/admin" class="btn btn-small">Admin</a>
{% endif %}
```

- [ ] **Step 2: Add CSS for `.admin-section`, `.data-table`, `.info-box`, `.btn-danger` to `static/style.css`**

Read `static/style.css` to find a good insertion point (after existing table styles if any, otherwise at end). Add:

```css
/* Admin dashboard */
.admin-section { margin-bottom: 2rem; }

.data-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.9rem;
}
.data-table th,
.data-table td {
    text-align: left;
    padding: 0.5rem 0.75rem;
    border-bottom: 1px solid var(--border, #e0e0e0);
}
.data-table th { font-weight: 600; background: var(--surface-alt, #f5f5f5); }
.data-table tr:last-child td { border-bottom: none; }

.info-box {
    background: #fff8e1;
    border: 1px solid #ffe082;
    border-radius: 4px;
    padding: 1rem;
    word-break: break-all;
}

.btn-danger {
    background: #c62828;
    color: #fff;
    border-color: #c62828;
}
.btn-danger:hover { background: #b71c1c; border-color: #b71c1c; }

.success {
    color: #2e7d32;
    background: #e8f5e9;
    border: 1px solid #a5d6a7;
    border-radius: 4px;
    padding: 0.5rem 0.75rem;
    margin-bottom: 1rem;
}
```

- [ ] **Step 3: Run full test suite**

```bash
pytest -v --tb=short
```
Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add templates/instructor.html app.py static/style.css
git commit -m "feat: show Admin nav link for admin users, add admin CSS"
```

---

### Task 8: Update tutorial.md

**Files:**
- Modify: `docs/tutorial.md`

- [ ] **Step 1: Update the Table of Contents**

Add under `### Part 1: User Guide` → `For Instructors`:
```
  - [Admin Tools](#admin-tools)
    - [Accessing the Admin Dashboard](#accessing-the-admin-dashboard)
    - [Managing Instructors](#managing-instructors)
    - [Password Reset](#password-reset)
```

Add to `### Part 3: Development History`:
```
- [Phase 10 — Admin Tools](#phase-10--admin-tools)
```

- [ ] **Step 2: Add Admin Tools user-guide section**

Add after the `### Signing Out` section (end of the instructor guide):

```markdown
### Admin Tools

The first instructor to register is automatically promoted to **admin**. Admins have access to the Admin Dashboard at `/admin`, reachable via the **Admin** button in the instructor nav bar.

#### Accessing the Admin Dashboard

1. Sign in as an instructor with admin privileges.
2. Click **Admin** in the top navigation bar.

#### Managing Instructors

The Instructors table lists every registered instructor with their email, role, and registration date. Admins can:

- **Make Admin** — promotes an instructor to admin; they will see the Admin button on their next page load.
- **Remove Admin** — revokes admin privileges (cannot demote yourself).
- **Delete** — permanently removes an instructor account and all their classes (cannot delete yourself).

The **Invite code** is shown at the top of the section. Click **Rotate** to generate a new code; the old code stops working immediately.

#### Password Reset

There is no self-service "forgot password" email flow. Instead:

1. In the Admin Dashboard, click **Reset Password** next to the instructor's name.
2. A one-time reset link appears at the bottom of the page — copy it and share it with the instructor (e.g. by email or message).
3. The instructor opens the link and sets a new password. The link expires after 24 hours and can only be used once.
```

- [ ] **Step 3: Update the Troubleshooting section**

Replace:
```markdown
### Forgot my password
- There is no password reset flow. An admin with database access can delete the user row and re-register:
  ```bash
  sqlite3 essay_coach.db "DELETE FROM users WHERE username='alice';"
  ```
  Then register again at `/register` with the current invite code.
```

With:
```markdown
### Forgot my password
Ask your admin to open the Admin Dashboard (`/admin`), click **Reset Password** next to your name, and share the one-time link with you. The link expires after 24 hours.

If you *are* the only admin (or the first user) and there is no one to reset for you, a user with database access can generate a token directly:
```bash
sqlite3 essay_coach.db "SELECT value FROM settings WHERE key='invite_code';"
# Then delete the user and re-register:
sqlite3 essay_coach.db "DELETE FROM users WHERE username='alice';"
```
Then register again at `/register` with the current invite code.
```

- [ ] **Step 4: Remove Admin tools from the "Extending the App" list and update description**

Find:
```
- **Admin tools** — invite code management, user list, and class overview for a super-admin role; currently all managed via CLI or direct database access
```
Replace with:
```
- **Email-based password reset** — the current admin-generated reset link requires the admin to share the URL manually; a future "forgot password" form could send it via SMTP (see `SMTP_*` env vars in `.env.example`)
```

- [ ] **Step 5: Add Phase 10 to Development History**

Add after the Phase 9 section:

```markdown
## Phase 10 — Admin Tools

**Goal:** Give the first instructor an admin role with a dashboard to manage other instructors, the invite code, classes, and password resets — without requiring SMTP or email infrastructure.

**What was built:**
- `email` and `is_admin` columns on the `users` table; SQLite migration and PostgreSQL schema update.
- The first registered instructor is automatically promoted to admin.
- New db functions: `list_users`, `delete_user`, `set_user_admin`, `create_password_reset_token`, `get_password_reset_token`, `consume_password_reset_token`, `list_all_classes`.
- `require_admin_api` dependency in `dependencies.py`.
- Admin API routes: `GET /api/admin/users`, `DELETE /api/admin/users/{id}`, `POST /api/admin/users/{id}/promote`, `POST /api/admin/users/{id}/demote`, `POST /api/admin/users/{id}/reset-password`, `GET /api/admin/classes`.
- `templates/admin.html` — admin dashboard (instructors, invite code, class overview).
- `templates/reset-password.html` — password reset form.
- Registration updated to capture instructor email.
- Admin nav link on instructor dashboard (visible to admins only).
- New test file: `tests/test_admin.py` (11 tests).
```

- [ ] **Step 6: Commit**

```bash
git add docs/tutorial.md
git commit -m "docs: update tutorial for Phase 10 admin tools"
```

---

## Self-Review

**Spec coverage check:**
- ✅ Admin dashboard at `/admin` — Tasks 4, 5
- ✅ Instructor user list with email — Tasks 1, 3, 5
- ✅ Email field on instructor accounts — Tasks 1, 3
- ✅ Password reset (admin-generated link, no SMTP) — Tasks 1, 4, 6
- ✅ Invite code management in admin dashboard — Task 5
- ✅ Class overview in admin dashboard — Tasks 4, 5
- ✅ First user auto-promoted to admin — Task 1
- ✅ Admin/non-admin access control — Task 2
- ✅ CSS for new UI elements — Task 7
- ✅ Tutorial updated — Task 8

**Placeholder scan:** No TBDs or "implement later" present.

**Type consistency:** `user_id: str` used consistently across `create_password_reset_token`, `get_password_reset_token`, `consume_password_reset_token`, and all admin route handlers. `list_users()` returns `list[dict]` and is consumed as such in the template JS.
