# Export Design

## Goal

Give instructors two CSV/JSON download links: one on the per-question session detail page (full attempt text) and one on the class analytics summary page (metadata only). Both are triggered by plain `<a href>` links — no JavaScript required.

---

## Architecture

### New Routes

Both routes require instructor authentication and class membership. They follow the same pattern as the existing analytics HTML routes: `_validate_session` → redirect to `/login` on failure, 404 if resource not found, 403 if not a member. They return a `Response` with `Content-Disposition: attachment` to trigger a browser download.

| Method | Route | Description |
|--------|-------|-------------|
| `GET` | `/instructor/analytics/{question_id}/export` | Per-question export |
| `GET` | `/instructor/classes/{class_id}/analytics/export` | Per-class export |

Both accept a `format` query parameter: `csv` (default) or `json`.

**Per-question route:** Fetch the question → 404 if not found → `is_class_member(q["class_id"], user_id)` → 403 if not a member. Call `get_question_session_stats(question_id)` to get session data. Flatten to one row per attempt and format.

**Per-class route:** `get_class(class_id)` → 404 if not found → `is_class_member(class_id, user_id)` → 403 if not a member. Call `get_class_question_stats(class_id)` to get per-question aggregate data, then call `get_question_session_stats` for each question to get the per-session rows. Format as metadata-only rows.

Register both routes in `app.py` immediately after the existing analytics routes.

### No New DB Functions

Both routes reuse `get_question_session_stats` and `get_class_question_stats` from `db.py`.

### Formatting Helpers (`export_utils.py`)

A new module `export_utils.py` with two pure functions:

**`format_question_export(sessions: list[dict], fmt: str) -> tuple[str, str]`**

Returns `(content, media_type)`. Flattens sessions to one row per attempt:

```python
# Per attempt row:
{
    "session_id": str,         # full UUID
    "attempt_number": int,
    "student_answer": str,
    "feedback": str | None,    # empty string in CSV if None
    "score_awarded": int | "",  # total_awarded, or "" if unscored
    "max_score": int | "",      # total_max, or "" if unscored
}
```

CSV column order: `session_id, attempt_number, student_answer, feedback, score_awarded, max_score`

JSON: list of objects with the same keys.

**`format_class_export(question_stats: list[dict], fmt: str) -> tuple[str, str]`**

Accepts the output of `get_class_question_stats` (which already has `total_sessions`, `avg_attempts`, etc.) but the per-class export needs per-session rows — not aggregates. So the route passes a different structure: a list of `{question_title, session_id, attempt_count, final_score, max_score}` dicts built in the route handler by calling `get_question_session_stats` for each question.

```python
# Per session row:
{
    "question_title": str,
    "session_id": str,          # full UUID
    "attempt_count": int,
    "final_score": int | "",    # or "" if unscored
    "max_score": int | "",      # or "" if unscored
}
```

CSV column order: `question_title, session_id, attempt_count, final_score, max_score`

JSON: list of objects with the same keys.

**`make_response(content: str, media_type: str, filename: str) -> Response`**

Returns a FastAPI `Response` with `Content-Disposition: attachment; filename="{filename}"`.

---

## Filenames

| Export | CSV filename | JSON filename |
|--------|-------------|---------------|
| Per-question | `question-{question_id[:8]}.csv` | `question-{question_id[:8]}.json` |
| Per-class | `class-{class_id[:8]}.csv` | `class-{class_id[:8]}.json` |

---

## UI

Two pairs of download links added to existing analytics templates. No new templates.

**`instructor-analytics-question.html`** — in `.analytics-header`, alongside the breadcrumb:

```html
<div class="export-links">
  Download:
  <a href="/instructor/analytics/{{ question.id }}/export?format=csv">CSV</a>
  &middot;
  <a href="/instructor/analytics/{{ question.id }}/export?format=json">JSON</a>
</div>
```

Hidden when `sessions` is empty.

**`instructor-analytics-class.html`** — same placement:

```html
<div class="export-links">
  Download:
  <a href="/instructor/classes/{{ class_id }}/analytics/export?format=csv">CSV</a>
  &middot;
  <a href="/instructor/classes/{{ class_id }}/analytics/export?format=json">JSON</a>
</div>
```

Hidden when `question_stats` is empty.

**CSS** — one small addition to `static/style.css`:

```css
.export-links {
    font-size: 0.85rem;
    color: var(--text-muted);
    margin-left: auto;
}

.export-links a {
    color: var(--primary);
    text-decoration: none;
}

.export-links a:hover {
    text-decoration: underline;
}
```

The `.analytics-header` div already uses `display: flex` (from the analytics CSS), so `margin-left: auto` on `.export-links` pushes it to the right.

---

## Testing (`tests/test_analytics_integration.py`)

13 new tests appended to the existing file.

**Per-question export:**
1. Unauthenticated → 302 to `/login`
2. Question not found → 404
3. Not a class member → 403
4. CSV: 200, `text/csv` content-type, correct `Content-Disposition` filename, header row + data rows match seeded attempts including score columns
5. JSON: 200, `application/json`, list of objects with expected keys
6. No attempts → CSV has header row only; JSON is `[]`
7. Unscored question → `score_awarded` and `max_score` are empty string in CSV, `""` in JSON

**Per-class export:**
8. Unauthenticated → 302 to `/login`
9. Class not found → 404
10. Not a class member → 403
11. CSV: 200, correct content-type, correct filename, header row + data rows
12. JSON: 200, list of objects with expected keys
13. Class with no questions → CSV has header row only; JSON is `[]`
