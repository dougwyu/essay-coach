# Per-Student Analytics Design

## Goal

Give instructors two new read-only pages: a class-level summary showing aggregate performance per question, and a per-question detail page showing each anonymous student session's attempt count, score progression, and answer text.

## Context

Students are identified only by a browser-generated UUID (`session_id`) stored in `localStorage`. There is no student login. "Per-student" analytics therefore means "per session." All the data needed already exists in the `attempts` table (`session_id`, `attempt_number`, `student_answer`, `feedback`, `score_data`, `created_at`).

**`score_data` structure:** When present, `score_data` is stored as a JSON text string in SQLite and must be deserialized via `json.loads` before use. The deserialized dict has this shape:

```json
{
  "breakdown": [
    {"label": "<string>", "awarded": <int>, "max": <int>},
    ...
  ],
  "total_awarded": <int>,
  "total_max": <int>
}
```

`total_awarded` is the student's score for that attempt. `total_max` is the maximum possible score (constant across all attempts for the same question). Score data is optional — questions without `[N]` point markers in the model answer have `NULL` `score_data` on all attempts. The analytics UI handles both scored and unscored questions gracefully.

---

## Architecture

### New Routes

Both routes require instructor authentication and class membership. They are HTML routes (not API routes), so they use `_validate_session` directly and redirect to `/login` on failure — the same pattern as `/instructor` and `/instructor/classes`.

| Method | Route | Template | Description |
|--------|-------|----------|-------------|
| `GET` | `/instructor/classes/{class_id}/analytics` | `instructor-analytics-class.html` | Class summary: one row per question |
| `GET` | `/instructor/analytics/{question_id}` | `instructor-analytics-question.html` | Question detail: one row per session |

**Class summary route:** After session validation, calls `get_class(class_id)` to fetch the class. Returns 404 if the class does not exist. Then checks `is_class_member(class_id, user_id)` — returns 403 if not a member. Passes `class_name` from the class record to the template.

**Question detail route:** After session validation, fetches the question by `question_id`. Returns 404 if the question does not exist. Derives `class_id` from `question.class_id`, then checks `is_class_member(class_id, user_id)`. Returns 403 if not a member. Passes `class_id` as a template context variable so the breadcrumb back-link is correct.

Register these routes in `app.py` after the existing `/instructor/classes` routes. Register `/instructor/classes/{class_id}/analytics` before any future parameterized `/instructor/classes/{class_id}` catch-all HTML route to ensure correct FastAPI route matching order.

### Entry Points

In `instructor.html`, the existing class filter section shows a dropdown and class badges. A new **Analytics** link is added beside each class badge (or in the class filter section header), one per class, linking to `/instructor/classes/{class_id}/analytics` for that class. Each question card also gets a small **Analytics** link that goes directly to `/instructor/analytics/{question_id}`.

---

## Data Layer

### New DB Functions (`db.py`)

**`get_class_question_stats(class_id: str) -> list[dict]`**

Returns one dict per question in the class. When there are no sessions for a question, `total_sessions=0`, `avg_attempts=0.0`, `avg_final_score=None`, `max_total=None`, `score_buckets=None`.

```python
{
    "question_id": str,
    "title": str,
    "total_sessions": int,         # distinct session_ids with at least one attempt
    "avg_attempts": float,         # mean attempts per session; 0.0 if no sessions
    "avg_final_score": float | None,  # mean of each session's final total_awarded; None if unscored or no sessions
    "max_total": int | None,       # total_max from score_data; None if unscored
    "score_buckets": {             # None if question is unscored or has no sessions
        "low": int,    # sessions where final score / max_total < 0.40
        "mid": int,    # sessions where 0.40 <= final score / max_total < 0.70
        "high": int,   # sessions where final score / max_total >= 0.70
    }
}
```

If the class has no questions, return `[]` immediately without executing the attempts query (avoids an empty `IN ()` clause which is a SQLite syntax error).

Implementation: fetch all attempts for all questions in the class (`SELECT * FROM attempts WHERE question_id IN (...) ORDER BY question_id, session_id, attempt_number`), deserialize `score_data` using `if row["score_data"]: json.loads(row["score_data"])` (truthy guard, not `is not None`, to match the existing `get_attempts` pattern — the column may be an empty string rather than NULL on some migration paths), then group and aggregate in Python.

**`get_question_session_stats(question_id: str) -> list[dict]`**

Returns one dict per session, sorted by `attempt_count` descending (most attempts first). `score_progression` is the list of `total_awarded` values per attempt in ascending attempt order; `None` entries for attempts with no score data.

```python
{
    "session_id": str,                       # full UUID
    "attempt_count": int,
    "score_progression": list[int | None],   # total_awarded per attempt, ascending; all None if unscored
    "final_score": int | None,               # total_awarded of the last attempt; None if unscored
    "max_total": int | None,                 # total_max; None if unscored
    "attempts": [                            # all attempts, ascending attempt_number order
        {
            "attempt_number": int,
            "student_answer": str,
            "feedback": str | None,          # LLM qualitative feedback; included for all attempts, displayed only for the final one
            "score_data": dict | None,       # deserialized; None if not scored
        }
    ]
}
```

Implementation: `SELECT * FROM attempts WHERE question_id = ? ORDER BY session_id, attempt_number`, deserialize `score_data` using `if row["score_data"]: json.loads(row["score_data"])` (same truthy guard as above), group by `session_id` in Python. `None` entries in `score_progression` are displayed as `—` in the `→`-joined sequence in the template.

---

## Score Bucketing

Thresholds are based on `total_awarded / total_max`. Applied consistently in both the Python bucketing logic and the Jinja2 template color-coding:

| Bucket | Condition | Color |
|--------|-----------|-------|
| low (red) | `total_awarded / total_max < 0.40` | red |
| mid (yellow) | `0.40 <= total_awarded / total_max < 0.70` | yellow |
| high (green) | `total_awarded / total_max >= 0.70` | green |

Sessions without score data are excluded from bucketing and the avg score calculation, but counted in `total_sessions` and `avg_attempts`.

---

## Templates

### `instructor-analytics-class.html`

Full-width single-column layout (no form/list split). Context from server: `class_name`, `class_id`, `question_stats`.

- Top nav: site name + Sign Out (same pattern as `instructor-classes.html`)
- Breadcrumb: `← Back to Dashboard` (links to `/instructor`)
- Page heading: `{class_name} — Analytics`
- Table columns: Question · Sessions · Avg attempts · Avg score · Score distribution · (link)
- Avg score display format: `{avg_final_score:.1f} / {max_total}` (e.g., `7.1 / 10`). Unscored questions show `—`.
- Score distribution: a `<div>` bar split into red/yellow/green segments proportional to `score_buckets` counts. Unscored questions show `—` in score columns and "No scoring" in distribution column.
- Each row's "View →" links to `/instructor/analytics/{question_id}`

### `instructor-analytics-question.html`

Context from server: `question` (id, title, prompt), `class_id`, `sessions`.

- Top nav: same pattern
- Breadcrumb: `← Back to Class Analytics` (links to `/instructor/classes/{class_id}/analytics`)
- Page heading: `{question.title} — Session Detail`
- Three stat tiles: Sessions · Avg attempts · Avg final score (or "—" if unscored)
- Table columns: Session · Attempts · Score progression · Final score · (toggle)
  - Session: truncated UUID (`{first4}…{last4}`)
  - Score progression: `total_awarded` values joined with `→`, final value bolded. "—" if unscored.
  - Final score: color-coded per bucketing thresholds above. "—" if unscored.
  - Toggle: "▶ Show answers" / "▼ Hide answers" — expands an inline row showing each attempt's answer text (labelled "Attempt N"). Under the final attempt's answer, the LLM's qualitative feedback is shown in full.
- Sorted by `attempt_count` descending

"Show answers" toggle: small inline `<script>` in the template, no changes to `app.js`.

---

## Security

- Both routes use `_validate_session` + redirect to `/login` on failure (HTML routes — same pattern as `/instructor` and `/instructor/classes`).
- Class summary: `is_class_member(class_id, user_id)` — 403 if not a member.
- Question detail: fetch question → 404 if not found → `is_class_member(question.class_id, user_id)` → 403 if not a member.
- Neither route exposes model answers or rubrics.

---

## Testing (`tests/test_analytics_integration.py`)

**DB unit tests for `get_class_question_stats`:**
- Class with no questions → returns `[]` (no DB query for attempts)
- Empty question (no sessions) → `total_sessions=0`, `avg_attempts=0.0`, `avg_final_score=None`, `score_buckets=None`
- Single session, unscored → correct counts, `None` score fields
- Multiple sessions with scores → correct averages and bucket counts
- Score bucket boundary: `total_awarded / total_max == 0.40` → `mid` bucket
- Score bucket boundary: `total_awarded / total_max == 0.70` → `high` bucket (threshold is `>=`)
- Score bucket boundary: `total_awarded / total_max == 0.699` → `mid` bucket

**DB unit tests for `get_question_session_stats`:**
- Single attempt session → `attempt_count=1`, `score_progression` length 1
- Multi-attempt session with score improvement → `score_progression` in ascending attempt order, `final_score` from last attempt
- Session with no score data → all `None` in `score_progression`, `final_score=None`
- Sort order: session with more attempts appears before session with fewer

**Integration tests (FastAPI routes):**
- `GET /instructor/classes/{id}/analytics` → 302 redirect to `/login` if unauthenticated
- `GET /instructor/classes/{id}/analytics` → 404 if `class_id` does not exist
- `GET /instructor/classes/{id}/analytics` → 403 if authenticated but not a class member
- `GET /instructor/classes/{id}/analytics` → 200 with correct `question_stats` shape for authenticated member
- `GET /instructor/analytics/{question_id}` → 302 redirect to `/login` if unauthenticated
- `GET /instructor/analytics/{question_id}` → 404 if `question_id` does not exist
- `GET /instructor/analytics/{question_id}` → 403 if question exists but instructor is not a member of its class
- `GET /instructor/analytics/{question_id}` → 200 with correct `sessions` shape for authenticated member of the question's class
