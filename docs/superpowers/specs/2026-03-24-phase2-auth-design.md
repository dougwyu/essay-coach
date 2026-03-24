# Essay Coach Phase 2 — Instructor Authentication Design

## Goal

Add multi-account authentication for instructors. Students remain anonymous (localStorage session ID unchanged). Only the instructor view and its write APIs are protected.

## Stack additions

- `passlib[bcrypt]` for password hashing (one new dependency)
- No other new libraries — auth is built on existing FastAPI + SQLite patterns

---

## Data Model

Three new tables added to SQLite via `init_db()`.

### `users`

| column | type | notes |
|---|---|---|
| id | TEXT PK | UUID |
| username | TEXT UNIQUE NOT NULL | instructor's chosen name |
| password_hash | TEXT NOT NULL | bcrypt via passlib |
| created_at | TIMESTAMP | default CURRENT_TIMESTAMP |

### `sessions`

| column | type | notes |
|---|---|---|
| token | TEXT PK | random 32-byte hex |
| user_id | TEXT FK → users(id) | ON DELETE CASCADE |
| expires_at | TIMESTAMP NOT NULL | 7-day sliding window |

Add an index on `sessions(user_id)` to support efficient per-user session invalidation.

**Session cleanup:** Expired sessions are not actively purged in Phase 2. `init_db()` deletes sessions where `expires_at < now()` on startup as a lightweight cleanup. Active purge is deferred.

### `settings`

| column | type | notes |
|---|---|---|
| key | TEXT PK | e.g. `"invite_code"` |
| value | TEXT NOT NULL | current value |

On first startup, if `settings` has no `invite_code` row, seed it with a random 8-character alphanumeric string (uppercase + digits).

---

## Routes

### New HTML routes

| route | method | description |
|---|---|---|
| `/login` | GET | Login form with link to `/register` |
| `/register` | GET | Registration form (username, password, invite code) |
| `/logout` | POST | Deletes session, clears cookie, redirects to `/login` |

Note: logout is `POST` to prevent CSRF-via-GET (e.g. a stray `<img src="/logout">` logging out the instructor).

### New API routes

| route | method | description |
|---|---|---|
| `/api/auth/login` | POST | Validates credentials, sets session cookie |
| `/api/auth/register` | POST | Validates invite code, creates user, sets session cookie |
| `/api/auth/me` | GET | Returns `{"username": "..."}` for logged-in instructor |
| `/api/settings/invite-code` | GET | Returns current invite code `{"invite_code": "..."}` (auth required) |
| `/api/settings/invite-code` | PUT | Rotates invite code (auth required) |

### Protected routes (require valid session cookie)

- `GET /instructor`
- `POST /api/questions`
- `PUT /api/questions/{id}`
- `DELETE /api/questions/{id}`
- `GET /api/questions/detail/{id}`

### Unprotected routes (no change)

- `GET /student`, `GET /student/{question_id}`
- `GET /api/attempts/{question_id}`
- `POST /api/feedback`

---

## Auth Implementation

### FastAPI dependency: `require_instructor`

Use **two separate dependencies** to handle the HTML vs API distinction cleanly:

- `require_instructor_api` — used on all `/api/...` protected routes. On failure raises `HTTP 401 Unauthorized`.
- `require_instructor_html` — used on HTML routes (`GET /instructor`). On failure returns `RedirectResponse("/login", status_code=302)`.

Both dependencies share the same session validation logic:
1. Read `session_token` cookie from the request
2. Look up token in `sessions` table
3. Check `expires_at > now()`
4. If valid: update `expires_at` to `now() + 7 days` (sliding window), return user dict
5. If invalid or missing: apply the appropriate failure response (401 or redirect)

### Registration flow

1. Instructor submits username + password + invite code to `POST /api/auth/register`
2. Validate password: minimum 8 characters, maximum 72 characters (bcrypt silently truncates at 72 bytes — enforce this server-side)
3. Verify invite code using `hmac.compare_digest` against `settings` where `key = "invite_code"` (constant-time comparison to prevent timing attacks)
4. Check username is not already taken; if taken return HTTP 400
5. Hash password with bcrypt via passlib
6. Insert into `users`
7. Create session token (32-byte `secrets.token_hex(32)`), insert into `sessions` with `expires_at = now() + 7 days`
8. Set `HttpOnly`, `SameSite=Lax` cookie named `session_token` (`Secure` flag omitted for local dev)
9. Return `{"ok": True}`; frontend redirects to `/instructor`

### Login flow

1. Instructor submits username + password to `POST /api/auth/login`
2. Look up user by username; if not found return HTTP 401 (do not reveal whether the username exists)
3. Verify bcrypt hash; if wrong return HTTP 401
4. Delete all existing sessions for this user (prevents session accumulation; multi-session is not supported)
5. Create new session token, insert into `sessions`
6. Set `HttpOnly`, `SameSite=Lax` cookie named `session_token`
7. Return `{"ok": True}`; frontend redirects to `/instructor`

### Logout flow

1. `POST /logout` reads `session_token` cookie
2. Deletes matching row from `sessions`
3. Clears cookie (set max-age=0)
4. Redirects to `/login`

### Invite code rotation

1. Logged-in instructor calls `PUT /api/settings/invite-code`
2. Optional JSON body: `{"code": "newcode"}` — if omitted or empty, server generates a random 8-char alphanumeric code using `secrets`
3. Updates `settings` where `key = "invite_code"`
4. Returns `{"invite_code": "newvalue"}`

---

## Frontend Changes

### New templates

- `templates/login.html` — username/password form, link to `/register`, error message display area
- `templates/register.html` — username/password/invite-code form, link to `/login`, error message display area

Both forms submit via JS `fetch` to the API endpoints and handle error responses inline.

### Changes to `templates/instructor.html`

- Add logout button in the header (a standard HTML `<form method="POST" action="/logout">` — not a fetch call; the session is read from the cookie, not the request body)
- Add a Settings section: shows current invite code (fetched via `GET /api/auth/me` on load — invite code fetched via separate call to `GET /api/settings/invite-code`), with a "Rotate" button

### Changes to `static/app.js`

- All instructor API calls check for 401 response → redirect to `/login`
- Add invite code fetch and rotation handler

### No changes to student templates or student JS

---

## New modules and functions

### `auth.py` (new module — auth logic only, no DB access)

```
hash_password(plain: str) -> str
verify_password(plain: str, hashed: str) -> bool
generate_token() -> str          # secrets.token_hex(32)
generate_invite_code() -> str    # 8-char alphanumeric via secrets
compare_codes(a: str, b: str) -> bool  # hmac.compare_digest wrapper
```

### DB additions to `db.py`

```
create_user(username: str, password_hash: str) -> str         # returns user_id
get_user_by_username(username: str) -> dict | None
create_session(token: str, user_id: str, expires_at: str)
get_session(token: str) -> dict | None
update_session_expiry(token: str, expires_at: str)
delete_session(token: str)
delete_sessions_for_user(user_id: str)                        # used on login
get_setting(key: str) -> str | None
set_setting(key: str, value: str)
```

---

## Testing

### `tests/test_auth.py` — unit tests

**Fixture:** same pattern as `test_db.py` — `monkeypatch` sets `db.DATABASE_PATH` to a `tmp_path` SQLite file, `init_db()` is called in the fixture.

Tests:
- `create_user` / `get_user_by_username` round-trip
- `create_session` / `get_session` / `delete_session` round-trip
- `update_session_expiry` updates correctly
- `delete_sessions_for_user` removes all sessions for that user
- `get_setting` / `set_setting` round-trip
- `hash_password` + `verify_password`: correct password passes, wrong password fails
- `compare_codes`: matching codes pass, non-matching fail
- `get_session` returns `None` for an expired session (set `expires_at` in the past)

### `tests/test_auth_integration.py` — FastAPI TestClient integration tests

**Fixture:** uses `TestClient` with the FastAPI app. Overrides `db.DATABASE_PATH` via `monkeypatch` to a `tmp_path` file. Calls `init_db()` before each test (via autouse fixture). The seeded invite code is retrieved via `db.get_setting("invite_code")` in each test that needs it.

Tests:
- `POST /api/auth/register` happy path → 200, cookie set
- `POST /api/auth/register` wrong invite code → 400
- `POST /api/auth/register` duplicate username → 400
- `POST /api/auth/register` password too short (< 8 chars) → 400
- `POST /api/auth/register` password too long (> 72 chars) → 400
- `POST /api/auth/login` happy path → 200, cookie set
- `POST /api/auth/login` wrong password → 401
- `POST /api/auth/login` unknown user → 401
- `POST /api/auth/login` invalidates previous session (old token no longer works)
- `GET /instructor` without session → redirect to `/login`
- `GET /instructor` with valid session → 200
- `DELETE /api/questions/{id}` without session → 401
- `POST /logout` clears session; subsequent `GET /instructor` redirects to `/login`
- `GET /api/settings/invite-code` without auth → 401
- `GET /api/settings/invite-code` with auth → returns `{"invite_code": "..."}` with current code
- `PUT /api/settings/invite-code` without auth → 401
- `PUT /api/settings/invite-code` with auth, explicit code → returns new code
- `PUT /api/settings/invite-code` with auth, no body → returns auto-generated code

### Existing tests

`tests/test_db.py` and `tests/test_feedback.py` are unaffected.
