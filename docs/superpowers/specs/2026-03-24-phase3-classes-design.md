# Essay Coach Phase 3 — Classes Design

## Goal

Add a classes layer so multiple instructors can run separate courses on the same Essay Coach instance. Each class has its own questions, its own student access code, and its own instructor invite code. Students see only their class's questions. Instructors see all their questions across all classes in a single unified dashboard, with class labels and a filter.

## Stack additions

None — no new libraries. Classes are built on existing FastAPI + SQLite patterns.

---

## Data Model

### New table: `classes`

| column | type | notes |
|---|---|---|
| id | TEXT PK | UUID |
| name | TEXT NOT NULL | e.g. "BIO101 Spring 2026" |
| student_code | TEXT UNIQUE NOT NULL | 8-char alphanumeric; students enter this to access the class |
| instructor_code | TEXT UNIQUE NOT NULL | 8-char alphanumeric; existing instructors enter this to join the class |
| created_by | TEXT FK → users(id) | SET NULL on delete; NULL is valid (default class or deleted user) |
| created_at | TIMESTAMP | default CURRENT_TIMESTAMP |

Generate `student_code` and `instructor_code` with `auth.generate_invite_code()` at creation time. Both must be unique across all classes.

### New table: `class_members`

| column | type | notes |
|---|---|---|
| class_id | TEXT FK → classes(id) ON DELETE CASCADE | |
| user_id | TEXT FK → users(id) ON DELETE CASCADE | |
| joined_at | TIMESTAMP | default CURRENT_TIMESTAMP |
| PRIMARY KEY | (class_id, user_id) | |

Add an index on `class_members(user_id)` to support efficient lookup of all classes for a given instructor.

### Modified table: `questions`

Add column: `class_id TEXT NOT NULL REFERENCES classes(id) ON DELETE CASCADE`

Attempts are already implicitly scoped to a class through `question_id → class_id`; no change to `attempts`.

### Migration

`init_db()` handles existing data automatically on first startup after this change:

1. If any questions exist without a `class_id`, create a class named `"Default"` with auto-generated codes.
2. Assign all such questions to the Default class.
3. Add the first user in `users` (by `created_at`) as a member of the Default class. If no users exist, `created_by` is NULL and the class has no members yet.

The migration is idempotent: it only runs if unassigned questions exist.

---

## Routes

### New HTML routes

| route | method | description |
|---|---|---|
| `/instructor/classes` | GET | Class management page: list of instructor's classes with codes and question counts |

### Modified HTML routes

| route | change |
|---|---|
| `GET /instructor` | Passes all classes the instructor belongs to into the template (for the question filter and the class selector in the create/edit form) |
| `GET /student` | Renders class code entry form instead of question list; skips to `/student/{class_id}` if localStorage has a stored class. If the stored class_id is stale (server returns 404), clears localStorage and renders the code entry form. |
| `GET /student/{class_id}` | New route — question list scoped to class (was `GET /student`) |
| `GET /student/{class_id}/{question_id}` | New route — workspace (was `GET /student/{question_id}`) |

The old `GET /student/{question_id}` route is removed. Existing student bookmarks to `/student/{question_id}` will break; this is acceptable for a local tool.

### New API routes

| route | method | auth | description |
|---|---|---|---|
| `/api/classes` | POST | instructor | Create a new class; creator is automatically added as a member |
| `/api/classes/join` | POST | instructor | Join a class via instructor code |
| `/api/classes/by-student-code/{code}` | GET | none | Resolve student code → `{class_id, name}`. Used by student landing page |
| `/api/classes/{class_id}/settings` | GET | instructor + member | Returns `{name, student_code, instructor_code}` |
| `/api/classes/{class_id}/student-code` | PUT | instructor + member | Rotate student code; returns `{student_code}` |
| `/api/classes/{class_id}/instructor-code` | PUT | instructor + member | Rotate instructor code; returns `{instructor_code}` |

### Modified API routes

| route | change |
|---|---|
| `POST /api/questions` | Body gains required `class_id` field; server validates instructor is a member of that class |
| `PUT /api/questions/{id}` | Body may include `class_id` to reassign the question; server validates membership on both old and new class |

All other existing question and feedback routes are unchanged. The question routes remain at `/api/questions/...` — class is a property of the question, not a URL namespace.

---

## Auth and Permissions

### New dependency: `require_class_member`

A FastAPI dependency used on class-scoped operations:

1. Extract `class_id` from the path parameter.
2. Call `require_instructor_api` to get the authenticated user.
3. Look up membership in `class_members`; if not a member, raise HTTP 403 Forbidden.
4. Return `(user, class_id)`.

Used on: `GET /api/classes/{class_id}/settings`, both code-rotation routes, and any future class-scoped routes. Question creation/update validates membership inline (the class is in the request body, not the path).

### Class creation

1. Instructor POSTs `{name}` to `POST /api/classes`.
2. Server generates `student_code` and `instructor_code` (unique across all classes — retry if collision).
3. Inserts into `classes` and `class_members` (creator is automatically a member).
4. Returns `{class_id, name, student_code, instructor_code}`.

### Joining a class

1. Instructor POSTs `{instructor_code}` to `POST /api/classes/join`.
2. Server looks up the class by `instructor_code` using constant-time comparison (`hmac.compare_digest`).
3. If already a member, return HTTP 400. Otherwise insert into `class_members`.
4. Returns `{class_id, name}`.

### Student class access

1. Student's browser calls `GET /api/classes/by-student-code/{code}` with the code in the URL path.
2. Server looks up class by `student_code`. No auth required.
3. Returns `{class_id, name}` or HTTP 404.
4. Browser stores `class_id` in localStorage and redirects to `/student/{class_id}`.

---

## Frontend Changes

### `templates/instructor.html`

- **Question form**: add a required `<select>` for class, populated with the instructor's classes (passed from the route). Disabled with a placeholder if the instructor has no classes yet.
- **Question cards**: add a class badge (e.g. `<span class="class-badge">BIO101</span>`) to each card.
- **Filter control**: add a `<select>` above the question list to filter by class (client-side filtering, no page reload).
- **Header**: add a link to `/instructor/classes` (e.g. "Manage Classes").

### New `templates/instructor-classes.html`

Class management page. Shows a card per class:
- Class name
- Student code (with Rotate button)
- Instructor invite code (with Rotate button)
- Question count

Two buttons at top of page: **Create Class** (inline form: name field) and **Join a Class** (inline form: instructor code field). Both submit via `fetch`.

### `templates/student.html`

- New mode: class code entry. When no `class_id` is available, render a single input form asking for the class code. On success, redirect to `/student/{class_id}` and store in localStorage.
- In question-list mode, show the class name in the page heading.
- Add a small "Switch class" link that clears localStorage and reloads `/student`.

### `static/app.js`

Instructor section:
- Class filter: filter `currentQuestions` by `class_id` on the selected filter value.
- Class badge: render class name on each question card.
- Class selector: populate the create/edit form's class dropdown.
- `createClass(name)`: POST to `/api/classes`, reload class list.
- `joinClass(code)`: POST to `/api/classes/join`, reload class list.
- `rotateStudentCode(classId)` and `rotateInstructorCode(classId)`: PUT to respective endpoints, update display.

Student section:
- `resolveClassCode(code)`: GET `/api/classes/by-student-code/{code}`, store class_id in localStorage, redirect.
- `getStoredClassId()`: returns stored class_id or null.
- `clearClass()`: clears localStorage class_id, reloads `/student`.

### `static/style.css`

- `.class-badge`: coloured pill label on question cards.
- `.class-filter`: styling for the filter dropdown.
- Styles for the class management page cards.

---

## DB additions to `db.py`

```
create_class(name, student_code, instructor_code, created_by) -> str  # returns class_id
get_class(class_id) -> dict | None
get_class_by_student_code(code) -> dict | None
get_class_by_instructor_code(code) -> dict | None
list_classes_for_user(user_id) -> list[dict]
add_class_member(class_id, user_id)
is_class_member(class_id, user_id) -> bool
get_class_question_count(class_id) -> int
update_class_student_code(class_id, new_code)
update_class_instructor_code(class_id, new_code)
```

---

## Testing

### `tests/test_classes.py` — unit tests for new db.py functions

- `create_class` / `get_class` round-trip
- `get_class_by_student_code` and `get_class_by_instructor_code` lookups
- `list_classes_for_user` returns correct classes
- `add_class_member` / `is_class_member` round-trip
- `get_class_question_count` returns correct count
- Code rotation functions update correctly

### `tests/test_classes_integration.py` — FastAPI TestClient integration tests

- `POST /api/classes` happy path → 200, creator is a member
- `POST /api/classes/join` happy path → 200
- `POST /api/classes/join` wrong code → 404
- `POST /api/classes/join` already a member → 400
- `GET /api/classes/by-student-code/{code}` happy path → returns class_id + name
- `GET /api/classes/by-student-code/{code}` wrong code → 404
- `GET /api/classes/{class_id}/settings` without auth → 401
- `GET /api/classes/{class_id}/settings` non-member → 403
- `GET /api/classes/{class_id}/settings` member → 200
- `PUT /api/classes/{class_id}/student-code` non-member → 403
- `PUT /api/classes/{class_id}/student-code` member → 200, new code returned
- `PUT /api/classes/{class_id}/instructor-code` member → 200
- `POST /api/questions` with valid class_id → 200
- `POST /api/questions` with class_id the instructor is not a member of → 403
- `GET /instructor` returns classes list in template context
- `GET /student/{class_id}` returns only questions for that class
- Migration: existing questions assigned to Default class on init

### Existing tests

`test_db.py`, `test_feedback.py`, `test_auth_utils.py`, `test_auth.py`, and `test_auth_integration.py` are unaffected.
