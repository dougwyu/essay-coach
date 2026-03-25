# Multiple Student Sessions — Design Spec

**Date:** 2026-03-25
**Status:** Approved

---

## Goal

Allow logged-in students to explicitly start a new attempt session for a question, creating a separate revision chain. Each session is auto-numbered ("Session 1", "Session 2", etc.). All past sessions remain visible in the history sidebar. Anonymous users are unaffected.

---

## Database

### Schema changes to `student_question_sessions`

**Remove:** `UNIQUE(student_id, question_id)`
**Add:** `session_number INTEGER NOT NULL DEFAULT 1`
**Add:** `UNIQUE(student_id, question_id, session_number)`

The active session for a (student_id, question_id) pair is the row with the highest `session_number`. No `is_active` flag — active is always latest.

The `attempts` table is unchanged. Each attempt already links to a `session_id`, so separate chains are naturally isolated.

### Migration

Existing rows get `session_number = 1` via `ALTER TABLE … ADD COLUMN session_number INTEGER NOT NULL DEFAULT 1`. The UNIQUE(student_id, question_id) constraint must be dropped; SQLite requires recreating the table to drop a constraint (handled via `CREATE TABLE … AS SELECT` pattern in `init_db()`).

### New / updated DB functions

| Function | Description |
|---|---|
| `get_or_create_question_session(student_id, question_id)` | **Updated.** Uses `MAX(session_number)` to find the active session; creates session_number=1 if none exists. |
| `start_new_question_session(student_id, question_id)` | **New.** Inserts a new row with `session_number = MAX(session_number) + 1`. Returns the new session `id`. |
| `list_question_sessions(student_id, question_id)` | **New.** Returns all sessions for this student+question ordered by `session_number` ASC. Each row: `{id, session_number}`. |

---

## API

### Existing route (internal update only)

`GET /api/student/session/{question_id}` — no signature change. Internally calls the updated `get_or_create_question_session`. Returns `{"session_id": "..."}` as before.

### New routes

**`POST /api/student/session/{question_id}/new`**
- Requires: valid `student_session_token` cookie
- Action: calls `start_new_question_session(student_id, question_id)`
- Returns: `{"session_id": "...", "session_number": 2}`
- Errors: 401 if not authenticated, 404 if question not found

**`GET /api/student/sessions/{question_id}`**
- Requires: valid `student_session_token` cookie
- Action: calls `list_question_sessions(student_id, question_id)`
- Returns: `[{"session_id": "...", "session_number": 1}, ...]` ordered oldest-first
- Errors: 401 if not authenticated, 404 if question not found

---

## Frontend

### `templates/student.html`

A "Start new session" button is added to the workspace block, next to the identity indicator. It is only rendered for logged-in students (controlled via JS after `initStudent()` resolves auth state — button starts hidden, shown if `_resolvedSessionId` came from the API rather than the anonymous fallback).

### `static/app.js`

**`initStudent()` update:** After resolving `_resolvedSessionId` from the API, also fetch `GET /api/student/sessions/{question_id}` and store the full session list for use by the history sidebar.

**`startNewSession()` (new):** Calls `POST /api/student/session/{question_id}/new`, updates `_resolvedSessionId` and `_allSessions`, clears the answer textarea and feedback/score panels, reloads attempt history for the new empty session.

**`loadAttemptHistory()` update (logged-in path):** Instead of a flat list, renders collapsible session groups:
- Fetches `GET /api/attempts/{question_id}?session_id=...` for each session in `_allSessions`
- Renders each as a group header: "Session N (active)" or "Session N — M attempts"
- Active session (highest session_number) is expanded by default; others are collapsed
- Within each group, attempts are rendered exactly as today

**Anonymous path:** `loadAttemptHistory()` is unchanged — flat list, no session groups.

---

## Testing

New tests added to `tests/test_student_auth.py`:

| Test | Description |
|---|---|
| `test_start_new_session_returns_new_id` | POST new session returns a different session_id than the first |
| `test_start_new_session_increments_number` | session_number increments to 2 |
| `test_list_sessions_returns_all` | After two sessions, list returns both in order |
| `test_active_session_is_latest` | GET /api/student/session returns the newest session_id |
| `test_attempts_isolated_between_sessions` | Attempts from session 1 don't appear in session 2's history |
| `test_new_session_unauthenticated` | POST new session returns 401 without cookie |
| `test_list_sessions_unauthenticated` | GET sessions returns 401 without cookie |

---

## Out of scope

- Students cannot rename sessions
- Students cannot delete sessions
- Instructors have no visibility into individual student sessions (only aggregate stats as today)
- Anonymous users cannot start new sessions
