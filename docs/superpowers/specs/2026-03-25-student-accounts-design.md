# Student Accounts Design

## Goal

Add optional student accounts so students can preserve their submission history across browsers and devices. Anonymous usage remains fully supported and is the fallback for students who skip registration.

---

## Key Decisions

- **Account fields:** username, email, password (min 8 chars). No email verification. No password reset (no email-sending capability).
- **Anonymous history:** fresh start on account creation — existing anonymous attempts are not linked to the new account.
- **Analytics:** unchanged — instructors still see session IDs, not usernames. Accounts are purely for the student's benefit.
- **Landing page flow:** auth-first, two-step on the same page (`/student`). Step 1 shows login/register. Step 2 (after auth or "continue anonymously") shows the class code form.
- **Session window:** 30-day sliding, stored in an httponly `student_session_token` cookie.

---

## Architecture

### New DB Tables (in `db.py`)

All three tables are created with `CREATE TABLE IF NOT EXISTS` in `init_db()`. No changes to existing tables.

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

`student_question_sessions.id` is a UUID that becomes the `session_id` stored in the `attempts` table — the glue between accounts and the existing analytics model. The `UNIQUE(student_id, question_id)` constraint will be relaxed when "multiple sessions" is implemented.

### New `db.py` Functions

```python
create_student_user(username, email, password_hash) -> str          # returns id
get_student_by_username(username) -> dict | None
get_student_by_email(email) -> dict | None
get_student_by_id(student_id) -> dict | None
create_student_session(token, student_id, expires_at) -> None
get_student_session(token) -> dict | None                           # checks expires_at > now()
update_student_session_expiry(token, expires_at) -> None
delete_student_session(token) -> None
get_or_create_question_session(student_id, question_id) -> str      # returns session UUID
```

`get_or_create_question_session` uses `INSERT OR IGNORE` followed by `SELECT id` to be idempotent and race-safe.

### New Routes (in `app.py`)

All five routes are registered before `# ---- Auth API routes ----`.

#### `POST /api/student/auth/register`

Request: `{ username: str, email: str, password: str }`

- 400 if password < 8 chars
- 400 if username already taken (check `get_student_by_username`)
- 400 if email already taken (check `get_student_by_email`)
- Hash password with `hash_password` (same bcrypt helper used for instructors)
- Create user, create session token, set `student_session_token` cookie (httponly, samesite=lax, max_age=30×24×3600)
- Return `{ id, username }`

#### `POST /api/student/auth/login`

Request: `{ username_or_email: str, password: str }`

- Look up by username first (`get_student_by_username`), then by email (`get_student_by_email`) if not found
- 401 if not found or password mismatch (`verify_password`)
- Create session token, set cookie (same as register)
- Return `{ id, username }`

#### `POST /api/student/auth/logout`

- Delete session from DB (`delete_student_session`)
- Clear `student_session_token` cookie
- Return `{ ok: true }`

#### `GET /api/student/auth/me`

- Read `student_session_token` cookie
- Validate via `get_student_session` (checks expiry, slides window with `update_student_session_expiry`)
- 401 if missing or invalid
- Return `{ id, username }`

#### `GET /api/student/session/{question_id}`

- Validate student session cookie (same as `/me`); 401 if invalid
- `get_question(question_id)` → 404 if not found
- `get_or_create_question_session(student_id, question_id)` → returns UUID
- Return `{ session_id: UUID }`

### Student session validation helper

A module-level helper in `app.py`, analogous to `_validate_session`:

```python
def _validate_student_session(student_session_token: str | None) -> dict | None:
    if not student_session_token:
        return None
    session = get_student_session(student_session_token)
    if not session:
        return None
    new_expiry = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=30)
    update_student_session_expiry(student_session_token, new_expiry)
    return get_student_by_id(session["student_id"])
```

---

## UI Changes

### Landing page (`templates/student.html`, `static/app.js`)

**New Step 1 — auth panel** (shown when `mode == "landing"` and student is not logged in):

```
Sign in or create account
[Username or email         ]
[Password                  ]
[        Sign in           ]
[      Create account      ]

No account? Continue anonymously — then enter your class code on the next panel.
```

**Step 2 — class code panel** (shown after successful auth, or after "continue anonymously"):

If logged in:
```
Already signed in as alice · Sign out

Enter your class code
[BIO101    ] [ Continue → ]
```

If anonymous (skipped auth):
```
Browsing anonymously · Sign in

Enter your class code
[BIO101    ] [ Continue → ]
```

**Implementation:** `initStudentLanding()` in `app.js` calls `GET /api/student/auth/me` on load. If 200 → skip the auth panel, go directly to Step 2 with the logged-in state. If 401 → show the auth panel (Step 1). After successful register/login or clicking "Continue anonymously," transition to Step 2 (hide Step 1, show Step 2) without a page reload.

The existing `essay_coach_class_id` localStorage check (auto-redirect to question list) is preserved — it runs after the auth check, so a logged-in student with a saved class_id goes straight to the question list.

### Workspace (`static/app.js`)

**Session resolution** — `initStudent()` calls `GET /api/student/session/{QUESTION_ID}` before loading attempt history. If 200, use the returned `session_id`. If 401 (anonymous), fall back to `getSessionId()` (localStorage). The resolved session_id is stored in a module-level variable and used for all subsequent API calls in that page load.

**Identity indicator** — a small line above the question prompt (rendered by JS after session resolution):
- Logged in: `Already signed in as alice · Sign out`
- Anonymous: *(nothing — no indicator in the workspace for anonymous users)*

"Sign out" calls `POST /api/student/auth/logout` then reloads the page (returning to Step 1 of the landing page).

---

## No Changes To

- `attempts` table schema
- `/api/feedback` route
- `/api/attempts/{question_id}` route
- All analytics routes and templates
- All instructor routes and templates

---

## Testing (`tests/test_student_auth.py`)

16 integration tests using the same `client` fixture and `fresh_db` autouse fixture pattern as `tests/test_analytics_integration.py`.

**Register (4 tests):**
1. Success → 200, `student_session_token` cookie set, returns `{ id, username }`
2. Duplicate username → 400
3. Duplicate email → 400
4. Password under 8 chars → 400

**Login (4 tests):**
5. Success by username → 200, cookie set
6. Success by email → 200, cookie set
7. Wrong password → 401
8. Unknown user → 401

**Me (2 tests):**
9. Authenticated → 200, returns `{ id, username }`
10. Unauthenticated → 401

**Logout (1 test):**
11. Clears session — subsequent `GET /api/student/auth/me` returns 401

**Session endpoint (4 tests):**
12. Authenticated, question exists → 200, returns UUID
13. Authenticated, same question second call → same UUID (idempotent)
14. Authenticated, question not found → 404
15. Unauthenticated → 401

**Landing page flow (1 test):**
16. Authenticated student (valid cookie) calling `GET /api/student/auth/me` → 200 with username (verifies the JS-side "skip auth panel" logic has correct data to work with)
