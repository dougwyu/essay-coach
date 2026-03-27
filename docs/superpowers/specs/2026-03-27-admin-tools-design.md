# Admin Tools Design

## Goal

Add a super-admin role so one designated instructor can manage the system through a web dashboard rather than the terminal or direct database access. The admin can view all instructors, rotate the invite code, see a class overview, and generate password-reset links for any instructor. No email-sending infrastructure is required.

---

## Key Decisions

- **Who is admin?** The first instructor to register is automatically promoted to admin (`is_admin = 1`). Any admin can promote or demote other instructors; they cannot demote themselves.
- **Password reset — no SMTP.** The admin generates a one-time reset URL in the dashboard and shares it manually (email, Teams, etc.). No `SMTP_*` config needed. The link is single-use and expires after 24 hours.
- **Email on instructor accounts.** Email is captured at registration (required). It is used to identify instructors in the admin view and will be the address the admin shares the reset link to — but the app does not send email itself.
- **Admin dashboard is a separate page** at `/admin`, not a tab on the instructor dashboard. Only users with `is_admin = 1` can reach it. Regular instructors see a 403.
- **No self-service "forgot password".** The reset flow is strictly admin-initiated. Students are unaffected (they already have email on their accounts but no password-reset flow is added here).
- **Invite code management stays in the admin dashboard** (already exists at `/api/auth/invite-code` — the admin UI just surfaces it).

---

## Roles

| Role | Can access |
|------|-----------|
| Instructor | `/instructor`, all class/question/analytics routes |
| Admin | Everything above + `/admin`, all `/api/admin/*` routes |

An instructor can hold both roles simultaneously. The `is_admin` flag is a boolean column on the `users` table — no separate roles table.

---

## Database Changes

### `users` table — two new columns

```sql
email    TEXT UNIQUE          -- instructor email; NULL allowed for legacy rows (migration sets NULL)
is_admin INTEGER NOT NULL DEFAULT 0
```

**SQLite migration:** `ALTER TABLE users ADD COLUMN` guards (check `PRAGMA table_info`). Existing first user is promoted to `is_admin = 1` automatically on first startup after migration.

**PostgreSQL:** Clean `CREATE TABLE` in `_init_db_postgres` — no migration needed (always fresh on first deploy).

### New table: `password_reset_tokens`

```sql
CREATE TABLE IF NOT EXISTS password_reset_tokens (
    token      TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at TIMESTAMP NOT NULL,
    used       INTEGER NOT NULL DEFAULT 0
);
```

One active token per user — generating a new token for a user deletes the previous one.

---

## New DB Functions

```python
# users
create_user(username, password_hash, email="") -> str   # updated signature; first user gets is_admin=1
get_user_by_email(email) -> dict | None
list_users() -> list[dict]                               # id, username, email, is_admin, created_at
delete_user(user_id) -> None
set_user_admin(user_id, is_admin: bool) -> None

# admin class overview
list_all_classes() -> list[dict]   # id, name, student_code, created_at, instructor (username), question_count

# password reset
create_password_reset_token(user_id) -> str             # returns token; deletes prior unused token
get_password_reset_token(token) -> dict | None          # None if used or expired
consume_password_reset_token(token, new_password_hash) -> bool
```

---

## API Routes

All `/api/admin/*` routes require `require_admin_api` (403 if not admin, 401 if not authenticated).

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/admin/users` | List all instructors |
| `DELETE` | `/api/admin/users/{id}` | Delete instructor (400 if self) |
| `POST` | `/api/admin/users/{id}/promote` | Set `is_admin = 1` |
| `POST` | `/api/admin/users/{id}/demote` | Set `is_admin = 0` (400 if self) |
| `POST` | `/api/admin/users/{id}/reset-password` | Generate reset token; return `{reset_url}` |
| `GET` | `/api/admin/classes` | List all classes with instructor + question count |

Existing routes reused:
- `GET /api/auth/invite-code` — already requires instructor auth; also used in admin dashboard
- `POST /api/auth/invite-code` — same

New public route:
- `POST /api/auth/reset-password` — `{token, password}` → consumes token, updates password hash

---

## Page Routes

| Path | Auth required | Template |
|------|--------------|----------|
| `GET /admin` | is_admin | `admin.html` |
| `GET /reset-password?token=…` | none | `reset-password.html` |

`/instructor` page route updated to pass `is_admin` to the template so the Admin nav button appears conditionally.

---

## Admin Dashboard (`/admin`)

Three sections on a single page, loaded via JS fetch on page load:

### 1 — Instructors
- Invite code display + Rotate button (calls existing `/api/auth/invite-code`)
- Table: Username | Email | Role (Admin badge or "Instructor") | Registered | Actions
- Actions per row:
  - **Make Admin** (non-admin only, not self)
  - **Remove Admin** (admin only, not self)
  - **Reset Password** (all users) — generates link, displays at bottom of page
  - **Delete** (not self) — confirm dialog

### 2 — Classes
- Table: Class name | Instructor | Questions | Student code | Created

### 3 — Reset link panel (hidden until generated)
- Displays the one-time URL
- Copy-to-clipboard button

---

## Password Reset Flow

```
Admin dashboard → "Reset Password" button
    → POST /api/admin/users/{id}/reset-password
    → server creates token, returns reset_url = baseURL + /reset-password?token=…
    → admin copies URL, shares with instructor

Instructor opens URL → /reset-password?token=…
    → types new password (+ confirm)
    → POST /api/auth/reset-password {token, password}
    → server calls consume_password_reset_token → updates password, marks token used
    → success message; instructor goes to /login
```

Failure cases handled:
- Token not found / already used → 400 "Invalid or expired reset token"
- Token expired (> 24h) → 400 same message
- Password < 8 chars → 400 "Password must be at least 8 characters"

---

## Registration Changes

`POST /api/auth/register` body gains `email: str` (optional for backwards compat — defaults to `""`).

`register.html` adds an email input field between username and password.

---

## Instructor Dashboard Change

`/instructor` page passes `is_admin` boolean to template. The **Admin** nav button appears only when `is_admin` is true.

---

## Security Notes

- `require_admin_api` checks both `is_authenticated` and `is_admin == 1`; returns 403 (not 404) for non-admin instructors.
- Reset tokens are `secrets.token_hex(32)` (256-bit entropy).
- Tokens are single-use (`used = 1` after consumption) and server-enforced expiry (checked at consumption time, not just generation).
- Admin cannot delete or demote themselves (prevents lockout).
- Generating a new reset token for a user replaces any prior unused token (prevents token accumulation).

---

## Out of Scope

- SMTP / email sending — the admin shares the reset URL manually
- Student password reset — no change to student auth in this phase
- Self-service "forgot password" form — future work
- Audit log — future work
- Rate limiting on reset endpoint — handled by the existing Nginx `limit_req` on `/api/`

---

## Testing

New file `tests/test_admin.py` with integration tests covering:
- Unauthenticated access → 303 redirect (page) or 401 (API)
- Non-admin instructor → 403 on all `/api/admin/*`
- Admin user → 200 on all `/api/admin/*`
- Delete user, promote, demote
- Cannot delete self, cannot demote self
- Password reset roundtrip (generate → consume → login with new password)
- Token single-use enforcement
- Invalid token → 400

Existing tests updated: `create_user` calls gain `email` argument.
