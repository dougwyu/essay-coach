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

### `settings`

| column | type | notes |
|---|---|---|
| key | TEXT PK | e.g. `"invite_code"` |
| value | TEXT NOT NULL | current value |

On first startup, if `settings` is empty, seed `invite_code` with a random 8-character alphanumeric string.

---

## Routes

### New HTML routes

| route | description |
|---|---|
| `GET /login` | Login form with link to `/register` |
| `GET /register` | Registration form (username, password, invite code) |
| `GET /logout` | Deletes session, clears cookie, redirects to `/login` |

### New API routes

| route | description |
|---|---|
| `POST /api/auth/login` | Validates credentials, sets session cookie |
| `POST /api/auth/register` | Validates invite code, creates user, sets session cookie |
| `GET /api/auth/me` | Returns `{"username": "..."}` for logged-in instructor |
| `PUT /api/settings/invite-code` | Rotates invite code (auth required) |

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

A reusable dependency injected into all protected routes:

1. Reads `session_token` cookie from the request
2. Looks up token in `sessions` table, checks `expires_at > now()`
3. If valid: updates `expires_at` to `now() + 7 days` (sliding window), returns user dict
4. If invalid or missing:
   - HTML routes: redirect to `/login`
   - API routes: raise `HTTP 401`

### Registration flow

1. Instructor submits username + password + invite code to `POST /api/auth/register`
2. Server verifies invite code matches `settings` where `key = "invite_code"`
3. Checks username not already taken
4. Hashes password with bcrypt
5. Inserts into `users`
6. Creates session token, inserts into `sessions`
7. Sets `HttpOnly` session cookie, returns `{"ok": True}`
8. Frontend redirects to `/instructor`

### Login flow

1. Instructor submits username + password to `POST /api/auth/login`
2. Server fetches user by username, verifies bcrypt hash
3. Creates session token, inserts into `sessions`
4. Sets `HttpOnly` session cookie, returns `{"ok": True}`
5. Frontend redirects to `/instructor`

### Logout flow

1. `GET /logout` reads session cookie
2. Deletes session row from `sessions`
3. Clears cookie
4. Redirects to `/login`

### Invite code rotation

1. Logged-in instructor hits `PUT /api/settings/invite-code`
2. Optional body: `{"code": "newcode"}` — if omitted, server generates a random 8-char alphanumeric code
3. Updates `settings` where `key = "invite_code"`
4. Returns `{"invite_code": "newvalue"}`

---

## Frontend Changes

### New templates

- `templates/login.html` — username/password form, link to `/register`, error display
- `templates/register.html` — username/password/invite-code form, link to `/login`, error display

### Changes to `templates/instructor.html`

- Add logout link in the header (calls `GET /logout`)
- Add a Settings section: shows current invite code, "Rotate" button that calls `PUT /api/settings/invite-code` and updates the displayed code

### Changes to `static/app.js`

- All instructor API calls check for 401 response → redirect to `/login`
- Add invite code rotation handler

### No changes to student templates or student JS

---

## New DB functions (`db.py` additions)

- `create_user(username, password_hash) → user_id`
- `get_user_by_username(username) → dict | None`
- `create_session(user_id, token, expires_at)`
- `get_session(token) → dict | None`
- `update_session_expiry(token, expires_at)`
- `delete_session(token)`
- `get_setting(key) → str | None`
- `set_setting(key, value)`

Auth logic (hashing, verification, token generation) lives in a new `auth.py` module, keeping `db.py` as pure data access.

---

## Testing

### `tests/test_auth.py` — unit tests

- `create_user` / `get_user_by_username` round-trip
- `create_session` / `get_session` / `delete_session` round-trip
- `get_setting` / `set_setting` round-trip
- Password hash + verify (correct password passes, wrong password fails)
- Invite code validation (correct code passes, wrong code fails)
- Expired session is rejected

### `tests/test_auth_integration.py` — FastAPI TestClient integration tests

- `POST /api/auth/register` happy path
- `POST /api/auth/register` wrong invite code → 400
- `POST /api/auth/register` duplicate username → 400
- `POST /api/auth/login` happy path
- `POST /api/auth/login` wrong password → 401
- `POST /api/auth/login` unknown user → 401
- `GET /instructor` without session → redirect to `/login`
- `GET /instructor` with valid session → 200
- `DELETE /api/questions/{id}` without session → 401
- `GET /logout` clears session; subsequent `GET /instructor` redirects to `/login`
- `PUT /api/settings/invite-code` without auth → 401
- `PUT /api/settings/invite-code` with auth → returns new code

### Existing tests

`tests/test_db.py` and `tests/test_feedback.py` are unaffected.
