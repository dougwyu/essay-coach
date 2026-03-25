# Multiple Student Sessions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let logged-in students start a new revision chain ("session") for the same question, with all past sessions visible as collapsible groups in the history sidebar.

**Architecture:** Add `session_number` to `student_question_sessions` (removing the old `UNIQUE(student_id, question_id)` constraint via a SQLite table-rebuild migration). Update `get_or_create_question_session` to return the latest session by `session_number DESC`. Add two new DB functions (`start_new_question_session`, `list_question_sessions`), two new API routes (`POST /api/student/session/{question_id}/new`, `GET /api/student/session/{question_id}/list`), a "Start new session" button in the workspace, and a grouped history sidebar in `app.js`.

**Tech Stack:** FastAPI, SQLite (via existing `_connect()` helper), vanilla JS.

**Spec:** `docs/superpowers/specs/2026-03-25-multiple-sessions-design.md`

---

## File Map

| File | Change |
|------|--------|
| `db.py` | Update `student_question_sessions` DDL in `executescript`, add migration block, update `get_or_create_question_session`, add `start_new_question_session` and `list_question_sessions` |
| `app.py` | Add 2 db imports, add 2 new routes before the existing `GET /api/student/session/{question_id}` route |
| `templates/student.html` | Add hidden "Start new session" button after `<div id="student-identity">` in workspace block |
| `static/app.js` | Add `_allSessions` module var, update `initStudent()`, add `startNewSession()`, rewrite `loadAttemptHistory()` |
| `static/style.css` | Add `.session-group`, `.session-group-header`, `.session-group-body` styles |
| `tests/test_student_auth.py` | Add migration test (custom fixture) + 8 new HTTP tests |

---

## Task 1: DB schema, migration, and functions

**Files:**
- Modify: `db.py`
- Modify: `tests/test_student_auth.py`

- [ ] **Step 1: Add the migration test and `old_schema_db` fixture to `tests/test_student_auth.py`**

Append at the end of `tests/test_student_auth.py`:

```python
# --- Migration test (does NOT use fresh_db autouse fixture) ---

@pytest.fixture
def old_schema_db(tmp_path, monkeypatch):
    """Creates a database with the old student_question_sessions schema (no session_number)."""
    db_path = str(tmp_path / "old.db")
    monkeypatch.setattr("config.DATABASE_PATH", db_path)
    monkeypatch.setattr("db.DATABASE_PATH", db_path)
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
```

Note: `fresh_db` is `autouse=True` and will still run for this test — but `old_schema_db` calls `monkeypatch.setattr("db.DATABASE_PATH", ...)` after `fresh_db` does, so `old_schema_db`'s path wins. The test calls `init_db()` against the old-schema path. This is the intended behaviour.

- [ ] **Step 2: Run the migration test to confirm it fails**

```bash
cd /Users/douglasyu/src/Cowork/essay-coach && pytest tests/test_student_auth.py::test_migration_adds_session_number -v
```

Expected: FAIL — `session_number` column does not exist yet.

- [ ] **Step 3: Add DB function tests for the new functions**

Append to `tests/test_student_auth.py` (after the migration test):

```python
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
```

Also add the new imports to the top of the file — add `start_new_question_session` and `list_question_sessions` to the `from db import (...)` block:

```python
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
```

- [ ] **Step 4: Run the new DB tests to confirm they fail**

```bash
cd /Users/douglasyu/src/Cowork/essay-coach && pytest tests/test_student_auth.py::test_start_new_session_returns_different_id tests/test_student_auth.py::test_list_question_sessions_returns_all tests/test_student_auth.py::test_get_or_create_returns_latest_after_new -v --tb=no
```

Expected: ImportError or FAILED — functions not defined yet.

- [ ] **Step 5: Update the `student_question_sessions` DDL inside `conn.executescript()` in `init_db()` in `db.py`**

In `db.py`, inside the `conn.executescript("""...""")` block in `init_db()`, replace:

```sql
        CREATE TABLE IF NOT EXISTS student_question_sessions (
            id TEXT PRIMARY KEY,
            student_id TEXT NOT NULL REFERENCES student_users(id) ON DELETE CASCADE,
            question_id TEXT NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(student_id, question_id)
        );
```

with:

```sql
        CREATE TABLE IF NOT EXISTS student_question_sessions (
            id TEXT PRIMARY KEY,
            student_id TEXT NOT NULL REFERENCES student_users(id) ON DELETE CASCADE,
            question_id TEXT NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
            session_number INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(student_id, question_id, session_number)
        );
```

- [ ] **Step 6: Add the migration block to `init_db()` in `db.py`**

In `db.py`, in `init_db()`, add the new migration block immediately after the closing `conn.executescript("""...""")` call and before the `# Add class_id column to questions if it doesn't exist yet` comment:

```python
    # Migration: add session_number to student_question_sessions (table rebuild required for SQLite)
    sq_cols = [r[1] for r in conn.execute("PRAGMA table_info(student_question_sessions)").fetchall()]
    if "session_number" not in sq_cols:
        conn.execute("""
            CREATE TABLE student_question_sessions_new (
                id TEXT PRIMARY KEY,
                student_id TEXT NOT NULL REFERENCES student_users(id) ON DELETE CASCADE,
                question_id TEXT NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
                session_number INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(student_id, question_id, session_number)
            )
        """)
        conn.execute("""
            INSERT INTO student_question_sessions_new (id, student_id, question_id, session_number, created_at)
                SELECT id, student_id, question_id, 1, created_at FROM student_question_sessions
        """)
        conn.execute("DROP TABLE student_question_sessions")
        conn.execute("ALTER TABLE student_question_sessions_new RENAME TO student_question_sessions")
        conn.commit()
```

- [ ] **Step 7: Update `get_or_create_question_session` and add `start_new_question_session` and `list_question_sessions` in `db.py`**

Replace the existing `get_or_create_question_session` function:

```python
def get_or_create_question_session(student_id: str, question_id: str) -> str:
    """Return the active (latest) session UUID for (student_id, question_id), creating session_number=1 if none exists.
    SQLite serialises all writes so SELECT-then-INSERT is safe within a single connection."""
    conn = _connect()
    row = conn.execute(
        "SELECT id FROM student_question_sessions WHERE student_id = ? AND question_id = ?"
        " ORDER BY session_number DESC LIMIT 1",
        (student_id, question_id),
    ).fetchone()
    if row:
        conn.close()
        return row["id"]
    sid = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO student_question_sessions (id, student_id, question_id, session_number)"
        " VALUES (?, ?, ?, ?)",
        (sid, student_id, question_id, 1),
    )
    conn.commit()
    conn.close()
    return sid
```

Then add the two new functions immediately after it:

```python
def start_new_question_session(student_id: str, question_id: str) -> tuple[str, int]:
    """Create the next session for (student_id, question_id) and return (session_id, session_number)."""
    sid = str(uuid.uuid4())
    conn = _connect()
    row = conn.execute(
        "SELECT MAX(session_number) as max_num FROM student_question_sessions"
        " WHERE student_id = ? AND question_id = ?",
        (student_id, question_id),
    ).fetchone()
    next_num = (row["max_num"] or 0) + 1
    conn.execute(
        "INSERT INTO student_question_sessions (id, student_id, question_id, session_number)"
        " VALUES (?, ?, ?, ?)",
        (sid, student_id, question_id, next_num),
    )
    conn.commit()
    conn.close()
    return sid, next_num


def list_question_sessions(student_id: str, question_id: str) -> list[dict]:
    """Return all sessions for (student_id, question_id) ordered oldest-first."""
    conn = _connect()
    rows = conn.execute(
        "SELECT id, session_number FROM student_question_sessions"
        " WHERE student_id = ? AND question_id = ? ORDER BY session_number ASC",
        (student_id, question_id),
    ).fetchall()
    conn.close()
    return [{"session_id": row["id"], "session_number": row["session_number"]} for row in rows]
```

- [ ] **Step 8: Run the migration test and DB function tests**

```bash
cd /Users/douglasyu/src/Cowork/essay-coach && pytest tests/test_student_auth.py::test_migration_adds_session_number tests/test_student_auth.py::test_start_new_session_returns_different_id tests/test_student_auth.py::test_list_question_sessions_returns_all tests/test_student_auth.py::test_get_or_create_returns_latest_after_new -v
```

Expected: All 4 PASS.

- [ ] **Step 9: Commit**

```bash
cd /Users/douglasyu/src/Cowork/essay-coach && git add db.py tests/test_student_auth.py && git commit -m "feat: add session_number to student_question_sessions and multi-session db functions"
```

---

## Task 2: API routes

**Files:**
- Modify: `app.py`
- Modify: `tests/test_student_auth.py`

- [ ] **Step 1: Add the 8 new HTTP tests to `tests/test_student_auth.py`**

Append to `tests/test_student_auth.py`:

```python
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
    # Create session 1 and submit an attempt via the feedback API would require LLM — skip.
    # Instead test isolation at DB level: create two sessions, verify list returns both
    # and that /api/attempts for session2 returns empty when only session1 has attempts.
    sid1 = client.get(f"/api/student/session/{qid}").json()["session_id"]
    sid2 = client.post(f"/api/student/session/{qid}/new").json()["session_id"]
    # Fetch attempts for session2 — must be empty (no submissions yet)
    res = client.get(f"/api/attempts/{qid}?session_id={sid2}")
    assert res.status_code == 200
    assert res.json()["attempts"] == []
    # Fetch attempts for session1 — also empty, but crucially returns its own list
    res1 = client.get(f"/api/attempts/{qid}?session_id={sid1}")
    assert res1.status_code == 200
    assert res1.json()["attempts"] == []


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
```

- [ ] **Step 2: Run the new HTTP tests to confirm they fail**

```bash
cd /Users/douglasyu/src/Cowork/essay-coach && pytest tests/test_student_auth.py -k "api_start_new or api_list or api_active or api_attempts_isolated or api_new_session_unauth or api_list_sessions_unauth" -v --tb=no -q
```

Expected: All 8 FAIL with 404 or assertion errors — routes not yet added.

- [ ] **Step 3: Add 2 new db imports to `app.py`**

In `app.py`, in the `from db import (...)` block, add after `get_or_create_question_session,`:

```python
    start_new_question_session,
    list_question_sessions,
```

- [ ] **Step 4: Add the 2 new routes to `app.py`**

The new routes must be registered **before** the existing `GET /api/student/session/{question_id}` route to ensure FastAPI matches the specific `/new` and `/list` paths first. Find the existing route:

```python
@app.get("/api/student/session/{question_id}")
def api_student_session(
```

Insert the two new routes immediately before it:

```python
@app.post("/api/student/session/{question_id}/new")
def api_student_session_new(
    question_id: str,
    student_session_token: str | None = Cookie(default=None),
):
    student = _validate_student_session(student_session_token)
    if not student:
        raise HTTPException(status_code=401, detail="Not authenticated")
    question = get_question(question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    session_id, session_number = start_new_question_session(student["id"], question_id)
    return {"session_id": session_id, "session_number": session_number}


@app.get("/api/student/session/{question_id}/list")
def api_student_session_list(
    question_id: str,
    student_session_token: str | None = Cookie(default=None),
):
    student = _validate_student_session(student_session_token)
    if not student:
        raise HTTPException(status_code=401, detail="Not authenticated")
    question = get_question(question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    return list_question_sessions(student["id"], question_id)


```

- [ ] **Step 5: Run all student auth tests**

```bash
cd /Users/douglasyu/src/Cowork/essay-coach && pytest tests/test_student_auth.py -v --tb=short
```

Expected: All tests pass (original 18 + migration test + 3 DB tests + 8 HTTP tests = 30 total).

- [ ] **Step 6: Run the full test suite to confirm no regressions**

```bash
cd /Users/douglasyu/src/Cowork/essay-coach && pytest -v --tb=short
```

Expected: All tests pass.

- [ ] **Step 7: Commit**

```bash
cd /Users/douglasyu/src/Cowork/essay-coach && git add app.py tests/test_student_auth.py && git commit -m "feat: add POST /new and GET /list routes for student question sessions"
```

---

## Task 3: Frontend

**Files:**
- Modify: `templates/student.html`
- Modify: `static/app.js`
- Modify: `static/style.css`

No new automated tests — this is UI logic. The API routes tested in Task 2 are the source of truth.

- [ ] **Step 1: Add the "Start new session" button to `templates/student.html`**

In the workspace `{% else %}` block, find:

```html
        <div id="student-identity" style="font-size:0.85rem; color:var(--text-muted); margin-bottom:0.5rem;"></div>
        <div class="prompt-section">
```

Replace with:

```html
        <div id="student-identity" style="font-size:0.85rem; color:var(--text-muted); margin-bottom:0.5rem;"></div>
        <button id="new-session-btn" class="btn btn-secondary"
                style="font-size:0.8rem; margin-bottom:0.5rem; display:none;"
                onclick="startNewSession()">Start new session</button>
        <div class="prompt-section">
```

- [ ] **Step 2: Add session group CSS to `static/style.css`**

At the end of `static/style.css`, append:

```css
/* Session groups (multi-session history) */
.session-group {
    border: 1px solid var(--border);
    border-radius: var(--radius);
    margin-bottom: 0.75rem;
    overflow: hidden;
}

.session-group-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.6rem 0.75rem;
    cursor: pointer;
    background: var(--bg-subtle);
    font-size: 0.85rem;
}

.session-group-header:hover {
    background: var(--border);
}

.session-group-body {
    display: none;
    padding: 0.75rem;
}

.session-group.expanded .session-group-body {
    display: block;
}
```

- [ ] **Step 3: Add `_allSessions` module-level variable in `static/app.js`**

Find:

```javascript
// Module-level resolved session ID for this page load
let _resolvedSessionId = null;
```

Replace with:

```javascript
// Module-level resolved session ID for this page load
let _resolvedSessionId = null;
// Module-level session list for logged-in students (null = anonymous/not fetched)
let _allSessions = null;
```

- [ ] **Step 4: Update `initStudent()` in `static/app.js`**

Replace the existing `initStudent()` function:

```javascript
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
            // Load all sessions for grouped history
            const listRes = await fetch(`/api/student/session/${QUESTION_ID}/list`);
            if (listRes.ok) {
                _allSessions = await listRes.json();
            } else {
                _allSessions = [];
            }
            document.getElementById('new-session-btn').style.display = '';
        }
    } else {
        // Anonymous fallback
        _resolvedSessionId = getSessionId();
    }
    loadAttemptHistory();
}
```

- [ ] **Step 5: Add `startNewSession()` to `static/app.js`**

Add immediately after `initStudent()`:

```javascript
async function startNewSession() {
    const btn = document.getElementById('new-session-btn');
    btn.disabled = true;
    try {
        const res = await fetch(`/api/student/session/${QUESTION_ID}/new`, { method: 'POST' });
        if (!res.ok) return;
        const data = await res.json();
        _resolvedSessionId = data.session_id;
        if (_allSessions !== null) {
            _allSessions.push({ session_id: data.session_id, session_number: data.session_number });
        }
        // Clear workspace for fresh start
        document.getElementById('student-answer').value = '';
        const feedbackSection = document.getElementById('feedback-section');
        if (feedbackSection) feedbackSection.style.display = 'none';
        const scoreSection = document.getElementById('score-section');
        if (scoreSection) scoreSection.style.display = 'none';
        document.getElementById('attempt-counter').textContent = '';
        loadAttemptHistory();
    } finally {
        btn.disabled = false;
    }
}
```

- [ ] **Step 6: Rewrite `loadAttemptHistory()` in `static/app.js`**

Replace the existing `loadAttemptHistory()` function with:

```javascript
async function loadAttemptHistory() {
    if (typeof QUESTION_ID === 'undefined') return;
    const container = document.getElementById('history-content');
    if (!container) return;

    if (_allSessions !== null) {
        // Authenticated path: render grouped by session
        if (_allSessions.length === 0) {
            container.innerHTML = '<p class="empty-state">No previous attempts yet.</p>';
            document.getElementById('attempt-counter').textContent = '';
            return;
        }
        const sessionsCopy = [..._allSessions].reverse(); // newest first
        const groups = await Promise.all(sessionsCopy.map(async (s) => {
            const r = await fetch(`/api/attempts/${QUESTION_ID}?session_id=${s.session_id}`);
            const d = await r.json();
            return { ...s, attempts: d.attempts };
        }));
        container.innerHTML = groups.map(g => {
            const isActive = g.session_id === _resolvedSessionId;
            const label = isActive
                ? `Session ${g.session_number} (active)`
                : `Session ${g.session_number} \u2014 ${g.attempts.length} attempt${g.attempts.length !== 1 ? 's' : ''}`;
            const attemptsHtml = g.attempts.length === 0
                ? '<p class="empty-state" style="margin:0.5rem 0 0 0;">No attempts yet.</p>'
                : g.attempts.map(a => `
                    <div class="history-item">
                        <div class="history-item-header" onclick="this.parentElement.classList.toggle('expanded')">
                            <strong>Attempt ${a.attempt_number}</strong>
                            <span class="history-date">${new Date(a.created_at).toLocaleString()}</span>
                        </div>
                        <div class="history-item-body">
                            <div class="history-answer"><h4>Your Answer</h4><p>${escapeHtml(a.student_answer)}</p></div>
                            <div class="history-feedback"><h4>Feedback</h4><div>${formatFeedback(a.feedback || '')}</div></div>
                            <div class="score-section" style="display:none"><div class="score-content"></div></div>
                        </div>
                    </div>`).join('');
            return `<div class="session-group${isActive ? ' expanded' : ''}">
                <div class="session-group-header" onclick="this.parentElement.classList.toggle('expanded')">
                    <strong>${label}</strong>
                </div>
                <div class="session-group-body">${attemptsHtml}</div>
            </div>`;
        }).join('');
        // Render scores inside each session group
        groups.forEach((g, gi) => {
            const groupEl = container.querySelectorAll('.session-group')[gi];
            g.attempts.forEach((a, ai) => {
                if (a.score_data) {
                    const card = groupEl.querySelectorAll('.history-item')[ai];
                    if (card) renderScore(a.score_data, card);
                }
            });
        });
        // Update attempt counter for active session
        const activeGroup = groups.find(g => g.session_id === _resolvedSessionId);
        const counter = document.getElementById('attempt-counter');
        if (counter && activeGroup) {
            const n = activeGroup.attempts.length;
            counter.textContent = n > 0 ? `${n} previous attempt${n !== 1 ? 's' : ''}` : '';
        }
    } else {
        // Anonymous path: flat list (unchanged behaviour)
        const res = await fetch(`/api/attempts/${QUESTION_ID}?session_id=${_resolvedSessionId}`);
        const data = await res.json();
        if (data.attempts.length === 0) {
            container.innerHTML = '<p class="empty-state">No previous attempts yet.</p>';
            return;
        }
        container.innerHTML = data.attempts.map((a, i) => `
            <div class="history-item">
                <div class="history-item-header" onclick="this.parentElement.classList.toggle('expanded')">
                    <strong>Attempt ${a.attempt_number}</strong>
                    <span class="history-date">${new Date(a.created_at).toLocaleString()}</span>
                </div>
                <div class="history-item-body">
                    <div class="history-answer">
                        <h4>Your Answer</h4>
                        <p>${escapeHtml(a.student_answer)}</p>
                    </div>
                    <div class="history-feedback">
                        <h4>Feedback</h4>
                        <div>${formatFeedback(a.feedback || '')}</div>
                    </div>
                    <div class="score-section" style="display:none"><div class="score-content"></div></div>
                </div>
            </div>
        `).join('');
        data.attempts.forEach((a, i) => {
            if (a.score_data) {
                const card = container.querySelectorAll('.history-item')[i];
                renderScore(a.score_data, card);
            }
        });
        const counter = document.getElementById('attempt-counter');
        if (counter) {
            counter.textContent = `${data.attempts.length} previous attempt${data.attempts.length !== 1 ? 's' : ''}`;
        }
    }
}
```

- [ ] **Step 7: Run the full test suite**

```bash
cd /Users/douglasyu/src/Cowork/essay-coach && pytest -v --tb=short
```

Expected: All tests pass.

- [ ] **Step 8: Smoke test the app manually**

```bash
cd /Users/douglasyu/src/Cowork/essay-coach && uvicorn app:app --reload
```

1. Open `http://localhost:8000/student`, register/log in, enter a class code, open a question
2. Confirm the "Start new session" button appears above the prompt
3. Submit an answer; verify it shows in the history sidebar as "Session 1 (active)"
4. Click "Start new session"; confirm the textarea clears and history shows "Session 2 (active)" expanded and "Session 1 — 1 attempt" collapsed
5. Open a question as an anonymous user; confirm the flat history list still works (no session groups)

- [ ] **Step 9: Commit**

```bash
cd /Users/douglasyu/src/Cowork/essay-coach && git add templates/student.html static/app.js static/style.css && git commit -m "feat: add grouped session history and Start new session button"
```

---

## Final verification

- [ ] **Run the full test suite one last time**

```bash
cd /Users/douglasyu/src/Cowork/essay-coach && pytest -v
```

Expected: All tests pass with no failures.
