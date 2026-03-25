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

Both accept a `format` query parameter: `csv` (default) or `json`. Any value other than `json` is treated as `csv` — no 400 is raised for unknown values.

**Per-question route:** Fetch the question → 404 if not found → `is_class_member(q["class_id"], user_id)` → 403 if not a member. Call `get_question_session_stats(question_id)` to get session data. Flatten to one row per attempt and format.

**Per-class route:** `get_class(class_id)` → 404 if not found → `is_class_member(class_id, user_id)` → 403 if not a member. Build the flat session-row list (see `format_class_export` below), then format.

Register both routes in `app.py` immediately after the existing analytics routes.

### No New DB Functions

Both routes reuse `get_question_session_stats` and `get_class_question_stats` from `db.py`.

### Formatting Helpers (`export_utils.py`)

A new module `export_utils.py` with two formatting functions. `make_response` lives in `app.py` as a route-level helper (not in `export_utils.py`) to keep the module free of FastAPI imports and trivially unit-testable.

**`format_question_export(sessions: list[dict], fmt: str) -> tuple[str, str]`**

Returns `(content, media_type)`. `sessions` is the direct output of `get_question_session_stats`. The function flattens sessions to one row per attempt:

```python
# Per attempt row (fields in this CSV column order):
# session_id, attempt_number, student_answer, feedback, score_awarded, max_score
{
    "session_id": str,          # full UUID (36 chars; slicing is safe)
    "attempt_number": int,
    "student_answer": str,
    "feedback": str,            # empty string if None
    "score_awarded": int | str, # attempt["score_data"]["total_awarded"], or "" if score_data is None
    "max_score": int | str,     # attempt["score_data"]["total_max"], or "" if score_data is None
}
```

CSV column order: `session_id, attempt_number, student_answer, feedback, score_awarded, max_score`

JSON: list of objects with the same keys. Unscored fields use `""` (empty string) rather than `null` so that CSV and JSON rows are structurally symmetric and spreadsheet tools do not encounter mixed types in the same column.

**`format_class_export(session_rows: list[dict], fmt: str) -> tuple[str, str]`**

Returns `(content, media_type)`. `session_rows` is a flat list built by the route handler — NOT the direct output of `get_class_question_stats`. The route handler builds it as follows:

```python
# Route handler pseudocode:
q_stats = get_class_question_stats(class_id)
session_rows = []
for q in q_stats:
    for s in get_question_session_stats(q["question_id"]):
        session_rows.append({
            "question_title": q["title"],
            "session_id": s["session_id"],
            "attempt_count": s["attempt_count"],
            "final_score": s["final_score"] if s["final_score"] is not None else "",
            "max_score": s["max_total"] if s["max_total"] is not None else "",
            # Note: source key is "max_total"; export key is "max_score"
        })
```

```python
# Per session row (fields in this CSV column order):
# question_title, session_id, attempt_count, final_score, max_score
{
    "question_title": str,
    "session_id": str,
    "attempt_count": int,
    "final_score": int | str,  # or "" if unscored
    "max_score": int | str,    # or "" if unscored (sourced from s["max_total"])
}
```

CSV column order: `question_title, session_id, attempt_count, final_score, max_score`

JSON: list of objects with the same keys. Unscored fields use `""` for the same reason as above.

**`make_response` (in `app.py`)**

A small helper used by both export routes:

```python
def _make_export_response(content: str, media_type: str, filename: str) -> Response:
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
```

---

## Filenames

| Export | CSV filename | JSON filename |
|--------|-------------|---------------|
| Per-question | `question-{question_id[:8]}.csv` | `question-{question_id[:8]}.json` |
| Per-class | `class-{class_id[:8]}.csv` | `class-{class_id[:8]}.json` |

IDs are `str(uuid.uuid4())` — always 36 characters — so `[:8]` is safe with no length check needed.

---

## UI

Two pairs of download links added to existing analytics templates. No new templates.

**`instructor-analytics-question.html`** — in `.analytics-header`, alongside the breadcrumb. Also add `display: flex; align-items: baseline;` to the `.analytics-header` CSS rule (it does not currently have `display: flex`):

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

**CSS** — update `.analytics-header` to add flex, and add `.export-links` styles to `static/style.css`:

```css
/* Update existing rule: */
.analytics-header {
    margin-bottom: 1.5rem;
    display: flex;
    align-items: baseline;
    gap: 1rem;
}

/* New rule: */
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

`margin-left: auto` on `.export-links` pushes it to the right within the flex row containing the breadcrumb and heading.

---

## Testing (`tests/test_analytics_integration.py`)

13 new tests appended to the existing file.

**Per-question export:**

1. Unauthenticated → 302 to `/login`
2. Question not found → 404
3. Not a class member → 403
4. CSV happy path: seed one class + question + one session with two scored attempts (attempt 1: score 5/10, attempt 2: score 8/10). `GET ?format=csv` → 200, `Content-Type: text/csv`, `Content-Disposition` contains `question-`, body has header row + 2 data rows, first data row has `score_awarded=5`, second has `score_awarded=8`.
5. JSON happy path: same seed as test 4. `GET ?format=json` → 200, `Content-Type: application/json`, response is a list of 2 objects each with keys `session_id, attempt_number, student_answer, feedback, score_awarded, max_score`. First object has `score_awarded=5, max_score=10`; second has `score_awarded=8, max_score=10`.
6. No attempts → `?format=csv` returns 200 with header row only (1 line); `?format=json` returns `[]`.
7. Unscored question: seed one attempt with no `score_data`. CSV row has empty `score_awarded` and `max_score` columns. JSON object has `score_awarded=""` and `max_score=""`.

**Per-class export:**

8. Unauthenticated → 302 to `/login`
9. Class not found → 404
10. Not a class member → 403
11. CSV happy path: seed one class + two questions, each with one session and one scored attempt. `GET ?format=csv` → 200, `Content-Type: text/csv`, `Content-Disposition` contains `class-`, body has header row + 2 data rows (one per session), each row contains the correct `question_title`.
12. JSON happy path: same seed as test 11. `GET ?format=json` → 200, list of 2 objects each with keys `question_title, session_id, attempt_count, final_score, max_score`. Each object has the correct `question_title` matching the seeded question and `attempt_count=1`.
13. Class with no questions → `?format=csv` returns header row only; `?format=json` returns `[]`.
