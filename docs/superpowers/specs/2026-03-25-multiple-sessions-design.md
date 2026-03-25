# Multiple Student Sessions — Design Spec

**Date:** 2026-03-25
**Status:** Approved

---

## Goal

Allow logged-in students to explicitly start a new attempt session for a question, creating a separate revision chain. Each session is auto-numbered ("Session 1", "Session 2", etc.). All past sessions remain visible in the history sidebar. Anonymous users are unaffected.

---

## Database

### Schema changes to `student_question_sessions`

The current schema is:
```sql
CREATE TABLE IF NOT EXISTS student_question_sessions (
    id TEXT PRIMARY KEY,
    student_id TEXT NOT NULL REFERENCES student_users(id) ON DELETE CASCADE,
    question_id TEXT NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(student_id, question_id)
);
```

The new schema is:
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

Changes:
- `UNIQUE(student_id, question_id)` removed
- `session_number INTEGER NOT NULL DEFAULT 1` added
- `UNIQUE(student_id, question_id, session_number)` added

The `CREATE TABLE IF NOT EXISTS` DDL inside the `conn.executescript()` block in `init_db()` must be updated to include `session_number` and the new `UNIQUE(student_id, question_id, session_number)` constraint. This ensures new databases get the correct schema from `executescript()`. The separate migration guard (below) uses `if "session_number" not in cols` to handle existing databases where the table already exists without the column — it will not fire on a newly created database.

The `attempts` table is unchanged — it already links to `session_id` and isolation between chains is already enforced by the existing `GET /api/attempts/{question_id}?session_id=...` endpoint.

The existing `get_class_question_stats` and `get_question_session_stats` functions group attempts by `session_id` and do not reference `student_question_sessions` at all — they are unaffected by this change.

### SQLite migration for existing databases

SQLite cannot drop constraints directly; a full table-rebuild migration is required. This must be implemented using individual `conn.execute()` calls (not `conn.executescript()`), consistent with the migration patterns already in `init_db()`. (`executescript()` issues an implicit COMMIT and does not inherit the `PRAGMA foreign_keys = ON` set by `_connect()`.)

```python
# In init_db(), after the CREATE TABLE block:
cols = [r[1] for r in conn.execute("PRAGMA table_info(student_question_sessions)").fetchall()]
if "session_number" not in cols:
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

This guard runs only when `session_number` is absent (existing databases). New databases get the correct schema from `CREATE TABLE IF NOT EXISTS`.

### New and updated DB functions

**`get_or_create_question_session(student_id, question_id)` — updated**

The current implementation uses `INSERT OR IGNORE` which relied on the now-removed `UNIQUE(student_id, question_id)` constraint. Replace with a SELECT-then-INSERT pattern. Because SQLite serialises all writes through a single write lock, the SELECT-then-INSERT within a single connection is safe: no two writes to the same database can interleave at the SQLite layer.

```python
def get_or_create_question_session(student_id: str, question_id: str) -> str:
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

This function returns the active (latest) session by `ORDER BY session_number DESC LIMIT 1`. After `start_new_question_session` creates a new row, subsequent calls to `get_or_create_question_session` will return that new session's id.

**`start_new_question_session(student_id, question_id)` — new**

```python
def start_new_question_session(student_id: str, question_id: str) -> tuple[str, int]:
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
```

Returns `(session_id, session_number)`. The MAX + INSERT is safe within a single connection for the same reason as above (SQLite write serialisation).

**`list_question_sessions(student_id, question_id)` — new**

```python
def list_question_sessions(student_id: str, question_id: str) -> list[dict]:
    conn = _connect()
    rows = conn.execute(
        "SELECT id, session_number FROM student_question_sessions"
        " WHERE student_id = ? AND question_id = ? ORDER BY session_number ASC",
        (student_id, question_id),
    ).fetchall()
    conn.close()
    return [{"session_id": row["id"], "session_number": row["session_number"]} for row in rows]
```

Returns `[{"session_id": "...", "session_number": 1}, ...]` ordered oldest-first.

---

## API

All routes require a valid `student_session_token` cookie (401 if absent or expired).

### Existing route (internal update only)

**`GET /api/student/session/{question_id}`**
- No signature change. Internally calls the updated `get_or_create_question_session`.
- After `start_new_question_session` has run, this endpoint returns the new (latest) session's id, because `get_or_create_question_session` uses `ORDER BY session_number DESC LIMIT 1`.
- Returns `{"session_id": "..."}` as before.
- Errors: 401 (not authenticated), 404 (question not found).

### New routes

Both new routes are prefixed `/api/student/session/` (singular, consistent with the existing route). `question_id` values are UUIDs (hex + hyphens only) so the suffixes `/new` and `/list` cannot collide with a real question_id.

**`POST /api/student/session/{question_id}/new`**
- Calls `start_new_question_session(student_id, question_id)`
- Returns: `{"session_id": "<uuid>", "session_number": <N>}` where N is the newly created session number
- Errors: 401 (not authenticated), 404 (question not found)

**`GET /api/student/session/{question_id}/list`**
- Calls `list_question_sessions(student_id, question_id)`
- Returns: `[{"session_id": "...", "session_number": 1}, ...]` ordered oldest-first
- If the student has no sessions yet, returns `[]` (200, not 404). The question existence check still runs; if the question does not exist, returns 404.
- Errors: 401 (not authenticated), 404 (question not found)

---

## Frontend

### `templates/student.html`

A "Start new session" button is added to the workspace block, immediately after the `<div id="student-identity">` element. It starts hidden and is shown by `initStudent()` only when the student is authenticated:

```html
<button id="new-session-btn" class="btn btn-secondary"
        style="font-size:0.8rem; margin-bottom:0.5rem; display:none;"
        onclick="startNewSession()">Start new session</button>
```

### `static/app.js`

**Module-level addition:**
```javascript
let _allSessions = null;  // null = not yet fetched; [] = fetched, no sessions; [...] = fetched sessions
```

Using `null` as the "not yet fetched" sentinel distinguishes "authenticated but has no prior sessions" (empty array) from "not authenticated / not fetched" (null). `loadAttemptHistory()` uses `_allSessions !== null` to decide whether to render session groups.

**`initStudent()` update:**

The two new steps are added inside the existing `if (res.ok) { ... if (meRes.ok) { ... } }` nesting — not as new outer conditions. Specifically, after the identity indicator is set inside `if (meRes.ok)`:
1. Show the "Start new session" button
2. Fetch `GET /api/student/session/${QUESTION_ID}/list` and store the result in `_allSessions`

```javascript
// Inside the existing if (meRes.ok) block, after the identity indicator:
const listRes = await fetch(`/api/student/session/${QUESTION_ID}/list`);
if (listRes.ok) {
    _allSessions = await listRes.json();
} else {
    _allSessions = [];  // fetch failed — treat as authenticated with no sessions
}
document.getElementById('new-session-btn').style.display = '';
```

The button is shown only after `_allSessions` is set (either to the fetched array or to `[]` on failure). This ensures `_allSessions !== null` is always true when the button is visible, so `loadAttemptHistory()` always takes the authenticated path and `startNewSession()` always pushes to `_allSessions`.

**`startNewSession()` — new:**

The button is disabled immediately to prevent double-click creating duplicate sessions, and re-enabled on completion or error:

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

**`loadAttemptHistory()` update:**

Branch on `_allSessions !== null` (not `_allSessions.length > 0`) to distinguish authenticated from anonymous:

- **Authenticated path** (`_allSessions !== null`): render grouped session history. For each session in `_allSessions` (newest first), fetch `GET /api/attempts/${QUESTION_ID}?session_id=<id>` and render a collapsible group. The active session (matching `_resolvedSessionId`) is labeled "(active)" and expanded by default; others are collapsed. If `_allSessions` is empty, renders "No previous attempts yet." This is an N-fetch-per-load pattern; acceptable for the initial implementation since students are unlikely to have more than a handful of sessions per question.

- **Anonymous path** (`_allSessions === null`): existing flat list using `_resolvedSessionId` directly, unchanged.

---

## Testing

### Migration test

The migration test must NOT use the `fresh_db` autouse fixture (which calls `init_db()` and creates the correct new schema, making the migration branch unreachable). It uses a separate fixture that manually creates the old schema:

```python
@pytest.fixture
def old_schema_db(tmp_path, monkeypatch):
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
```

```python
def test_migration_adds_session_number(old_schema_db):
    init_db()
    conn = sqlite3.connect(old_schema_db)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(student_question_sessions)").fetchall()]
    assert "session_number" in cols
    row = conn.execute("SELECT session_number FROM student_question_sessions WHERE id = 'old-session-id'").fetchone()
    assert row[0] == 1
    conn.close()
```

### HTTP tests

Added to `tests/test_student_auth.py` (use existing `fresh_db` autouse + `client` fixtures):

| Test | Description |
|---|---|
| `test_start_new_session_returns_different_id` | POST new session after initial GET returns a different session_id |
| `test_start_new_session_increments_number` | First session has session_number=1, new session has session_number=2 |
| `test_list_sessions_returns_all_in_order` | After two sessions, list returns both ordered by session_number ASC |
| `test_active_session_is_latest` | Call GET /api/student/session to create the initial session (session_number=1), then POST /new once to create session_number=2, then assert GET /api/student/session returns the second session's id. |
| `test_attempts_isolated_between_sessions` | Submit an attempt under session 1 (using `session_id` from GET); call GET /api/attempts with `session_id=<session2_id>` from POST new session; assert response contains zero attempts |
| `test_list_sessions_empty_returns_200` | Register, create a question, call GET /list WITHOUT calling GET /api/student/session first (to avoid creating a session); assert 200 and `[]`. |
| `test_new_session_unauthenticated_returns_401` | POST new session without cookie returns 401 |
| `test_list_sessions_unauthenticated_returns_401` | GET list without cookie returns 401 |

---

## Out of scope

- Students cannot rename sessions
- Students cannot delete sessions
- Instructors have no visibility into individual student sessions (only aggregate stats as today)
- Anonymous users cannot start new sessions
