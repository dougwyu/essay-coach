# Per-Student Analytics Design

## Goal

Give instructors two new read-only pages: a class-level summary showing aggregate performance per question, and a per-question detail page showing each anonymous student session's attempt count, score progression, and answer text.

## Context

Students are identified only by a browser-generated UUID (`session_id`) stored in `localStorage`. There is no student login. "Per-student" analytics therefore means "per session." All the data needed already exists in the `attempts` table (`session_id`, `attempt_number`, `student_answer`, `feedback`, `score_data`).

Score data is optional — questions without `[N]` point markers in the model answer produce no `score_data`. The analytics UI handles both scored and unscored questions gracefully.

---

## Architecture

### New Routes

Both routes require instructor authentication and class membership (same checks as existing class-scoped routes).

| Method | Route | Template | Description |
|--------|-------|----------|-------------|
| `GET` | `/instructor/classes/{class_id}/analytics` | `instructor-analytics-class.html` | Class summary: one row per question |
| `GET` | `/instructor/analytics/{question_id}` | `instructor-analytics-question.html` | Question detail: one row per session |

The question detail route additionally verifies the question belongs to a class the instructor is a member of (same membership check, via the question's `class_id`).

### Entry Points

- A new **Analytics** link is added to the class header area on the existing instructor dashboard (`instructor.html`), linking to `/instructor/classes/{class_id}/analytics` for each class the filter is set to.
- Each row in the class summary links to `/instructor/analytics/{question_id}`.

---

## Data Layer

### New DB Functions (`db.py`)

**`get_class_question_stats(class_id: str) -> list[dict]`**

Returns one dict per question in the class:

```python
{
    "question_id": str,
    "title": str,
    "total_sessions": int,        # distinct session_ids that submitted
    "avg_attempts": float,        # mean attempts per session
    "avg_final_score": float | None,   # mean of each session's highest-attempt score
    "max_total": int | None,      # max_total from score_data (same for all attempts)
    "score_buckets": {            # None if question is unscored
        "low": int,   # sessions where final score < 40% of max_total
        "mid": int,   # sessions where final score 40–70% of max_total
        "high": int,  # sessions where final score > 70% of max_total
    }
}
```

Implementation: single SQL query fetching all attempts for all questions in the class, grouped in Python. Sessions with no `score_data` on any attempt are counted but have `None` scores.

**`get_question_session_stats(question_id: str) -> list[dict]`**

Returns one dict per session, sorted by `attempt_count` descending (most engaged first):

```python
{
    "session_id": str,            # full UUID
    "attempt_count": int,
    "score_progression": list[int | None],  # scores in attempt order; None if unscored
    "final_score": int | None,    # score from the last attempt
    "max_total": int | None,
    "attempts": [                 # all attempts, ascending order
        {
            "attempt_number": int,
            "student_answer": str,
            "score_data": dict | None,
        }
    ]
}
```

Implementation: `SELECT * FROM attempts WHERE question_id = ? ORDER BY session_id, attempt_number`, then group by `session_id` in Python.

---

## Templates

### `instructor-analytics-class.html`

Full-width single-column layout (no form/list split). Context from server: `class_name`, `class_id`, `question_stats`.

- Top nav: site name + Sign Out (same pattern as `instructor-classes.html`)
- Breadcrumb: `← Back to Dashboard`
- Page heading: `{class_name} — Analytics`
- Table with columns: Question · Sessions · Avg attempts · Avg score · Score distribution · (link)
- Score distribution: a `<div>` bar split into red/yellow/green segments proportional to `score_buckets` counts. Unscored questions show `—` in score columns and "No scoring" in distribution column.
- Each row's "View →" links to `/instructor/analytics/{question_id}`

### `instructor-analytics-question.html`

Context from server: `question` (id, title, prompt), `class_id`, `sessions`.

- Top nav: same pattern
- Breadcrumb: `← Back to Class Analytics` (links to `/instructor/classes/{class_id}/analytics`)
- Page heading: `{question.title} — Session Detail`
- Three stat tiles: Sessions · Avg attempts · Avg final score (or "—" if unscored)
- Table with columns: Session · Attempts · Score progression · Final score · (toggle)
  - Session: truncated UUID (`{first4}…{last4}`)
  - Score progression: attempt scores joined with `→`, final score bolded (e.g., `5 → 7 → **9**`). "—" if unscored.
  - Final score: color-coded — green ≥70%, yellow 40–69%, red <40% of max. "—" if unscored.
  - Toggle: "▶ Show answers" / "▼ Hide answers" — expands an inline row showing each attempt's answer text
- Sorted by `attempt_count` descending

"Show answers" toggle: small inline `<script>` in the template, no changes to `app.js`.

---

## Score Bucketing

Thresholds are based on percentage of `max_total`:

| Bucket | Condition |
|--------|-----------|
| low (red) | final score / max_total < 0.40 |
| mid (yellow) | 0.40 ≤ final score / max_total ≤ 0.70 |
| high (green) | final score / max_total > 0.70 |

Sessions without score data are excluded from bucketing and the avg score calculation, but counted in `total_sessions` and `avg_attempts`.

---

## Security

- Both routes use `_validate_session` + redirect to `/login` on failure (HTML routes, not API routes — same pattern as `/instructor` and `/instructor/classes`).
- Class membership check: `is_class_member(class_id, user_id)` — same as `/instructor/classes/{class_id}/settings`.
- Question detail route: fetches question, checks `is_class_member(question.class_id, user_id)`.
- Neither route exposes model answers or rubrics.

---

## Testing (`tests/test_analytics_integration.py`)

**DB unit tests for `get_class_question_stats`:**
- Empty question (no sessions) → `total_sessions=0`, `avg_attempts=0`, `avg_final_score=None`
- Single session, unscored → correct counts, `None` score fields
- Multiple sessions with scores → correct averages and bucket counts
- Score bucket boundary values: exactly 40% → mid, exactly 70% → mid, 70.1% → high

**DB unit tests for `get_question_session_stats`:**
- Single attempt session → `attempt_count=1`, progression list length 1
- Multi-attempt session with score improvement → progression in correct order
- Session with no score data → `None` in progression, `None` final score
- Sort order: session with more attempts appears first

**Integration tests (FastAPI routes):**
- `GET /instructor/classes/{id}/analytics` → 302 redirect if unauthenticated
- `GET /instructor/classes/{id}/analytics` → 403 if authenticated but not a member
- `GET /instructor/classes/{id}/analytics` → 200 with correct `question_stats` shape for authenticated member
- `GET /instructor/analytics/{question_id}` → 302 redirect if unauthenticated
- `GET /instructor/analytics/{question_id}` → 403 if not a member of the question's class
- `GET /instructor/analytics/{question_id}` → 200 with correct `sessions` shape for authenticated member
