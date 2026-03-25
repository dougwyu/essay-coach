# Per-Student Analytics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two read-only instructor pages — a class-level summary of question performance and a per-question session detail view — giving instructors visibility into attempt counts, score progressions, and student answer text.

**Architecture:** Two new DB query functions aggregate attempt data per class/question; two new FastAPI HTML routes render Jinja2 templates; analytics entry points are wired into the existing instructor dashboard. All analytics are read-only with no new tables.

**Tech Stack:** Python/FastAPI, SQLite via `db.py`, Jinja2 templates, vanilla CSS appended to `static/style.css`. Tests use pytest + FastAPI TestClient.

---

## File Structure

| File | Change |
|------|--------|
| `db.py` | Add `get_class_question_stats` and `get_question_session_stats` after `get_attempt_count` (~line 223) |
| `app.py` | Add 2 imports from `db`; add 2 new HTML routes after `instructor_classes_page` (~line 178) |
| `templates/instructor-analytics-class.html` | Create new — class summary table |
| `templates/instructor-analytics-question.html` | Create new — session detail table with answer expand |
| `static/style.css` | Append analytics CSS classes |
| `templates/instructor.html` | Add analytics links to question cards and class filter section |
| `tests/test_analytics_integration.py` | Create new — DB unit tests + FastAPI integration tests |

---

### Task 1: `get_class_question_stats` DB function

**Files:**
- Modify: `db.py` (after `get_attempt_count`, ~line 223)
- Test: `tests/test_analytics_integration.py` (create)

- [ ] **Step 1: Create the test file and write failing DB unit tests for `get_class_question_stats`**

```python
# tests/test_analytics_integration.py
import json
import pytest
import db as db_module
from db import (
    init_db, get_setting,
    create_class, create_question, create_attempt,
    get_class_question_stats,
)


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DATABASE_PATH", db_path)
    init_db()
    yield


def _make_class(name="BIO101"):
    return create_class(name, f"S{name[:6].upper()}", f"I{name[:6].upper()}", None)


def _make_question(class_id, title="Q1"):
    return create_question(title, "Prompt", "Model answer", None, class_id)


SCORE_7_10 = {"breakdown": [{"label": "A", "awarded": 7, "max": 10}], "total_awarded": 7, "total_max": 10}
SCORE_4_10 = {"breakdown": [{"label": "A", "awarded": 4, "max": 10}], "total_awarded": 4, "total_max": 10}
SCORE_3_10 = {"breakdown": [{"label": "A", "awarded": 3, "max": 10}], "total_awarded": 3, "total_max": 10}


# ---- get_class_question_stats ----

def test_stats_class_with_no_questions():
    cid = _make_class()
    result = get_class_question_stats(cid)
    assert result == []


def test_stats_question_no_sessions():
    cid = _make_class()
    qid = _make_question(cid)
    result = get_class_question_stats(cid)
    assert len(result) == 1
    r = result[0]
    assert r["question_id"] == qid
    assert r["total_sessions"] == 0
    assert r["avg_attempts"] == 0.0
    assert r["avg_final_score"] is None
    assert r["max_total"] is None
    assert r["score_buckets"] is None


def test_stats_single_session_unscored():
    cid = _make_class()
    qid = _make_question(cid)
    create_attempt(qid, "sess1", "answer", "feedback", 1)
    result = get_class_question_stats(cid)
    r = result[0]
    assert r["total_sessions"] == 1
    assert r["avg_attempts"] == 1.0
    assert r["avg_final_score"] is None
    assert r["score_buckets"] is None


def test_stats_multiple_sessions_with_scores():
    cid = _make_class()
    qid = _make_question(cid)
    # session A: 1 attempt, score 7/10 (high bucket)
    create_attempt(qid, "sessA", "ans", "fb", 1, score_data=SCORE_7_10)
    # session B: 2 attempts, final score 4/10 (mid bucket)
    create_attempt(qid, "sessB", "ans1", "fb1", 1, score_data=SCORE_3_10)
    create_attempt(qid, "sessB", "ans2", "fb2", 2, score_data=SCORE_4_10)
    result = get_class_question_stats(cid)
    r = result[0]
    assert r["total_sessions"] == 2
    assert r["avg_attempts"] == 1.5   # (1+2)/2
    assert abs(r["avg_final_score"] - 5.5) < 0.01  # (7+4)/2
    assert r["max_total"] == 10
    assert r["score_buckets"]["high"] == 1
    assert r["score_buckets"]["mid"] == 1
    assert r["score_buckets"]["low"] == 0


def test_stats_bucket_boundary_40_pct_is_mid():
    cid = _make_class()
    qid = _make_question(cid)
    # 4/10 = 0.40, boundary: should be mid (>= 0.40 and < 0.70)
    create_attempt(qid, "s1", "a", "f", 1, score_data=SCORE_4_10)
    result = get_class_question_stats(cid)
    buckets = result[0]["score_buckets"]
    assert buckets["mid"] == 1
    assert buckets["low"] == 0
    assert buckets["high"] == 0


def test_stats_bucket_boundary_70_pct_is_high():
    cid = _make_class()
    qid = _make_question(cid)
    # 7/10 = 0.70, boundary: should be high (>= 0.70)
    create_attempt(qid, "s1", "a", "f", 1, score_data=SCORE_7_10)
    result = get_class_question_stats(cid)
    buckets = result[0]["score_buckets"]
    assert buckets["high"] == 1
    assert buckets["mid"] == 0


def test_stats_bucket_boundary_699_pct_is_mid():
    cid = _make_class()
    qid = _make_question(cid)
    # 6.99/10 ≈ 0.699, should be mid (< 0.70)
    score_699 = {"breakdown": [{"label": "A", "awarded": 699, "max": 1000}], "total_awarded": 699, "total_max": 1000}
    create_attempt(qid, "s1", "a", "f", 1, score_data=score_699)
    result = get_class_question_stats(cid)
    buckets = result[0]["score_buckets"]
    assert buckets["mid"] == 1
    assert buckets["high"] == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_analytics_integration.py -v -k "stats_class"
```

Expected: ImportError or AttributeError (`get_class_question_stats` not found)

- [ ] **Step 3: Implement `get_class_question_stats` in `db.py`**

Add after `get_attempt_count` (~line 223):

```python
def get_class_question_stats(class_id: str) -> list[dict]:
    """Return per-question aggregate stats for all questions in a class."""
    conn = _connect()
    questions = conn.execute(
        "SELECT id, title FROM questions WHERE class_id = ? ORDER BY created_at",
        (class_id,),
    ).fetchall()
    conn.close()

    if not questions:
        return []

    question_ids = [q["id"] for q in questions]
    question_map = {q["id"]: q["title"] for q in questions}

    placeholders = ",".join("?" * len(question_ids))
    conn = _connect()
    rows = conn.execute(
        f"SELECT * FROM attempts WHERE question_id IN ({placeholders})"
        f" ORDER BY question_id, session_id, attempt_number",
        question_ids,
    ).fetchall()
    conn.close()

    # Group: q_sessions[question_id][session_id] = [attempts in order]
    from collections import defaultdict
    q_sessions: dict = defaultdict(lambda: defaultdict(list))
    for row in rows:
        d = dict(row)
        if d.get("score_data"):
            d["score_data"] = json.loads(d["score_data"])
        q_sessions[d["question_id"]][d["session_id"]].append(d)

    result = []
    for qid in question_ids:
        title = question_map[qid]
        sessions = q_sessions.get(qid, {})

        if not sessions:
            result.append({
                "question_id": qid,
                "title": title,
                "total_sessions": 0,
                "avg_attempts": 0.0,
                "avg_final_score": None,
                "max_total": None,
                "score_buckets": None,
            })
            continue

        total_sessions = len(sessions)
        total_attempts = sum(len(atts) for atts in sessions.values())
        avg_attempts = total_attempts / total_sessions

        final_scores = []
        max_total = None
        for atts in sessions.values():
            last = atts[-1]  # already ordered by attempt_number
            sd = last.get("score_data")
            if sd:
                final_scores.append(sd["total_awarded"])
                if max_total is None:
                    max_total = sd["total_max"]

        avg_final_score = sum(final_scores) / len(final_scores) if final_scores else None

        score_buckets = None
        if final_scores and max_total:
            buckets = {"low": 0, "mid": 0, "high": 0}
            for score in final_scores:
                pct = score / max_total
                if pct < 0.40:
                    buckets["low"] += 1
                elif pct < 0.70:
                    buckets["mid"] += 1
                else:
                    buckets["high"] += 1
            score_buckets = buckets

        result.append({
            "question_id": qid,
            "title": title,
            "total_sessions": total_sessions,
            "avg_attempts": avg_attempts,
            "avg_final_score": avg_final_score,
            "max_total": max_total,
            "score_buckets": score_buckets,
        })

    return result
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_analytics_integration.py -v -k "stats_class"
```

Expected: all 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add db.py tests/test_analytics_integration.py
git commit -m "feat: add get_class_question_stats DB function"
```

---

### Task 2: `get_question_session_stats` DB function

**Files:**
- Modify: `db.py` (after `get_class_question_stats`)
- Modify: `tests/test_analytics_integration.py` (add tests)

- [ ] **Step 1: Add failing DB unit tests for `get_question_session_stats`**

Append to `tests/test_analytics_integration.py` (after the existing imports, add `get_question_session_stats` to the import line, then append these tests):

Update the import at the top of the file:
```python
from db import (
    init_db, get_setting,
    create_class, create_question, create_attempt,
    get_class_question_stats, get_question_session_stats,
)
```

Append these tests:

```python
# ---- get_question_session_stats ----

def test_session_stats_no_sessions():
    cid = _make_class()
    qid = _make_question(cid)
    result = get_question_session_stats(qid)
    assert result == []


def test_session_stats_no_sessions():
    cid = _make_class()
    qid = _make_question(cid)
    result = get_question_session_stats(qid)
    assert result == []


def test_session_stats_single_attempt():
    cid = _make_class()
    qid = _make_question(cid)
    create_attempt(qid, "sessA", "my answer", "feedback text", 1)
    result = get_question_session_stats(qid)
    assert len(result) == 1
    s = result[0]
    assert s["session_id"] == "sessA"
    assert s["attempt_count"] == 1
    assert len(s["score_progression"]) == 1
    assert s["score_progression"][0] is None
    assert s["final_score"] is None
    assert s["max_total"] is None
    assert len(s["attempts"]) == 1
    assert s["attempts"][0]["attempt_number"] == 1
    assert s["attempts"][0]["student_answer"] == "my answer"
    assert s["attempts"][0]["feedback"] == "feedback text"


def test_session_stats_multi_attempt_score_improvement():
    cid = _make_class()
    qid = _make_question(cid)
    create_attempt(qid, "s1", "ans1", "fb1", 1, score_data=SCORE_3_10)
    create_attempt(qid, "s1", "ans2", "fb2", 2, score_data=SCORE_7_10)
    result = get_question_session_stats(qid)
    assert len(result) == 1
    s = result[0]
    assert s["attempt_count"] == 2
    assert s["score_progression"] == [3, 7]   # ascending attempt order
    assert s["final_score"] == 7
    assert s["max_total"] == 10
    assert s["attempts"][0]["attempt_number"] == 1
    assert s["attempts"][1]["attempt_number"] == 2
    # feedback only returned for final attempt display (data available for all)
    assert s["attempts"][1]["feedback"] == "fb2"


def test_session_stats_unscored_progression_all_none():
    cid = _make_class()
    qid = _make_question(cid)
    create_attempt(qid, "s1", "a1", "f1", 1)
    create_attempt(qid, "s1", "a2", "f2", 2)
    result = get_question_session_stats(qid)
    s = result[0]
    assert s["score_progression"] == [None, None]
    assert s["final_score"] is None


def test_session_stats_sorted_by_attempt_count_desc():
    cid = _make_class()
    qid = _make_question(cid)
    # sessA: 1 attempt, sessB: 3 attempts
    create_attempt(qid, "sessA", "a", "f", 1)
    create_attempt(qid, "sessB", "b1", "f1", 1)
    create_attempt(qid, "sessB", "b2", "f2", 2)
    create_attempt(qid, "sessB", "b3", "f3", 3)
    result = get_question_session_stats(qid)
    assert result[0]["session_id"] == "sessB"
    assert result[1]["session_id"] == "sessA"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_analytics_integration.py -v -k "session_stats"
```

Expected: ImportError (`get_question_session_stats` not found)

- [ ] **Step 3: Implement `get_question_session_stats` in `db.py`**

Add after `get_class_question_stats`:

```python
def get_question_session_stats(question_id: str) -> list[dict]:
    """Return per-session stats for a question, sorted by attempt count descending."""
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM attempts WHERE question_id = ? ORDER BY session_id, attempt_number",
        (question_id,),
    ).fetchall()
    conn.close()

    from collections import defaultdict
    sessions: dict = defaultdict(list)
    for row in rows:
        d = dict(row)
        if d.get("score_data"):
            d["score_data"] = json.loads(d["score_data"])
        sessions[d["session_id"]].append(d)

    result = []
    for session_id, atts in sessions.items():
        score_progression = []
        max_total = None
        for a in atts:
            sd = a.get("score_data")
            if sd:
                score_progression.append(sd["total_awarded"])
                if max_total is None:
                    max_total = sd["total_max"]
            else:
                score_progression.append(None)

        last = atts[-1]
        last_sd = last.get("score_data")
        final_score = last_sd["total_awarded"] if last_sd else None

        result.append({
            "session_id": session_id,
            "attempt_count": len(atts),
            "score_progression": score_progression,
            "final_score": final_score,
            "max_total": max_total,
            "attempts": [
                {
                    "attempt_number": a["attempt_number"],
                    "student_answer": a["student_answer"],
                    "feedback": a.get("feedback"),
                    "score_data": a.get("score_data"),
                }
                for a in atts
            ],
        })

    result.sort(key=lambda s: s["attempt_count"], reverse=True)
    return result
```

- [ ] **Step 4: Run all analytics DB tests to verify they pass**

```bash
pytest tests/test_analytics_integration.py -v -k "stats or session_stats"
```

Expected: all 13 tests PASS (7 from Task 1 + 5 new session_stats tests + 1 no_sessions test)

- [ ] **Step 5: Commit**

```bash
git add db.py tests/test_analytics_integration.py
git commit -m "feat: add get_question_session_stats DB function"
```

---

### Task 3: Analytics routes + integration tests + stub templates

**Files:**
- Modify: `app.py` (add imports + 2 routes after `instructor_classes_page`)
- Create: `templates/instructor-analytics-class.html` (stub)
- Create: `templates/instructor-analytics-question.html` (stub)
- Modify: `tests/test_analytics_integration.py` (add integration tests)

- [ ] **Step 1: Add integration tests**

Append to `tests/test_analytics_integration.py`. First update the top-level imports to add FastAPI client fixtures:

```python
# Add these imports near the top of the file (after existing imports):
from fastapi.testclient import TestClient
from app import app


@pytest.fixture
def client():
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def _register_and_login(client, username="alice"):
    invite = get_setting("invite_code")
    client.post("/api/auth/register", json={
        "username": username, "password": "password123", "invite_code": invite,
    })


def _make_class_via_api(client, name="BIO101"):
    res = client.post("/api/classes", json={"name": name})
    return res.json()["class_id"]


def _make_question_via_api(client, class_id):
    res = client.post("/api/questions", json={
        "title": "Photosynthesis", "prompt": "Explain it.",
        "model_answer": "Plants make food. [5]", "rubric": "", "class_id": class_id,
    })
    return res.json()["id"]
```

Then append the integration tests:

```python
# ---- Route integration tests ----

def test_class_analytics_redirects_if_unauthenticated(client):
    cid = "some-class-id"
    res = client.get(f"/instructor/classes/{cid}/analytics", follow_redirects=False)
    assert res.status_code == 302
    assert "/login" in res.headers["location"]


def test_class_analytics_404_if_class_not_found(client):
    _register_and_login(client)
    res = client.get("/instructor/classes/nonexistent-id/analytics")
    assert res.status_code == 404


def test_class_analytics_403_if_not_member(client):
    _register_and_login(client, "alice")
    # bob creates a class; alice is not a member
    _register_and_login(client, "bob")  # re-register won't work — use direct DB
    from db import create_class, create_user, add_class_member
    from auth import hash_password
    bob_id = create_user("bob2", hash_password("password123"))
    cid = create_class("Bob class", "SBOB0001", "IBOB0001", bob_id)
    add_class_member(cid, bob_id)
    # alice is logged in; she is not a member of bob's class
    res = client.get(f"/instructor/classes/{cid}/analytics")
    assert res.status_code == 403


def test_class_analytics_200_for_member(client):
    _register_and_login(client)
    cid = _make_class_via_api(client)
    res = client.get(f"/instructor/classes/{cid}/analytics")
    assert res.status_code == 200


def test_question_analytics_redirects_if_unauthenticated(client):
    res = client.get("/instructor/analytics/some-question-id", follow_redirects=False)
    assert res.status_code == 302
    assert "/login" in res.headers["location"]


def test_question_analytics_404_if_question_not_found(client):
    _register_and_login(client)
    res = client.get("/instructor/analytics/nonexistent-id")
    assert res.status_code == 404


def test_question_analytics_403_if_not_member(client):
    _register_and_login(client, "alice")
    from db import create_class, create_question, create_user, add_class_member
    from auth import hash_password
    bob_id = create_user("bob2", hash_password("password123"))
    cid = create_class("Bob class", "SBOB0002", "IBOB0002", bob_id)
    add_class_member(cid, bob_id)
    qid = create_question("Q", "P", "A", None, cid)
    res = client.get(f"/instructor/analytics/{qid}")
    assert res.status_code == 403


def test_question_analytics_200_for_member(client):
    _register_and_login(client)
    cid = _make_class_via_api(client)
    qid = _make_question_via_api(client, cid)
    res = client.get(f"/instructor/analytics/{qid}")
    assert res.status_code == 200
```

- [ ] **Step 2: Run integration tests to verify they fail**

```bash
pytest tests/test_analytics_integration.py -v -k "analytics_redirect or analytics_404 or analytics_403 or analytics_200"
```

Expected: 404 (routes not registered yet)

- [ ] **Step 3: Create stub templates**

`templates/instructor-analytics-class.html`:
```html
<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>Analytics</title></head>
<body><p>Class analytics stub</p></body>
</html>
```

`templates/instructor-analytics-question.html`:
```html
<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>Session Detail</title></head>
<body><p>Question analytics stub</p></body>
</html>
```

- [ ] **Step 4: Add imports and routes to `app.py`**

In `app.py`, add `get_class_question_stats` and `get_question_session_stats` to the `from db import (...)` block. Find the line `get_class_question_count,` and add after it:

```python
    get_class_question_stats,
    get_question_session_stats,
```

After `instructor_classes_page` (~line 178), add:

```python
@app.get("/instructor/classes/{class_id}/analytics", response_class=HTMLResponse)
def instructor_class_analytics(
    request: Request,
    class_id: str,
    session_token: str | None = Cookie(default=None),
):
    user = _validate_session(session_token)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    cls = get_class(class_id)
    if not cls:
        raise HTTPException(status_code=404, detail="Class not found")
    if not is_class_member(class_id, user["id"]):
        raise HTTPException(status_code=403, detail="Not a member of this class")
    question_stats = get_class_question_stats(class_id)
    return templates.TemplateResponse(
        "instructor-analytics-class.html",
        {
            "request": request,
            "class_name": cls["name"],
            "class_id": class_id,
            "question_stats": question_stats,
            "username": user["username"],
        },
    )


@app.get("/instructor/analytics/{question_id}", response_class=HTMLResponse)
def instructor_question_analytics(
    request: Request,
    question_id: str,
    session_token: str | None = Cookie(default=None),
):
    user = _validate_session(session_token)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    q = get_question(question_id)
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")
    if not is_class_member(q["class_id"], user["id"]):
        raise HTTPException(status_code=403, detail="Not a member of this class")
    sessions = get_question_session_stats(question_id)
    total_sessions = len(sessions)
    avg_attempts = (
        sum(s["attempt_count"] for s in sessions) / total_sessions
        if sessions else 0.0
    )
    scored = [s for s in sessions if s["final_score"] is not None]
    avg_final_score = sum(s["final_score"] for s in scored) / len(scored) if scored else None
    max_total = scored[0]["max_total"] if scored else None
    return templates.TemplateResponse(
        "instructor-analytics-question.html",
        {
            "request": request,
            "question": q,
            "class_id": q["class_id"],
            "sessions": sessions,
            "total_sessions": total_sessions,
            "avg_attempts": avg_attempts,
            "avg_final_score": avg_final_score,
            "max_total": max_total,
            "username": user["username"],
        },
    )
```

- [ ] **Step 5: Run all integration tests to verify they pass**

```bash
pytest tests/test_analytics_integration.py -v
```

Expected: all 20 tests PASS

- [ ] **Step 6: Commit**

```bash
git add app.py templates/instructor-analytics-class.html templates/instructor-analytics-question.html tests/test_analytics_integration.py
git commit -m "feat: add analytics routes and integration tests"
```

---

### Task 4: Class analytics template + CSS

**Files:**
- Modify: `templates/instructor-analytics-class.html` (replace stub)
- Modify: `static/style.css` (append analytics CSS)

- [ ] **Step 1: Replace `instructor-analytics-class.html` with full template**

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Essay Coach — Analytics</title>
    <link rel="stylesheet" href="/static/style.css">
</head>
<body>
    <header>
        <h1>Essay Coach <span class="badge">Instructor</span></h1>
        <nav>
            <span class="username-display">{{ username }}</span>
            <a href="/instructor">&larr; Dashboard</a>
            <form method="POST" action="/logout" style="display:inline; margin-left:0.75rem;">
                <button type="submit" class="btn btn-small">Sign Out</button>
            </form>
        </nav>
    </header>

    <main class="analytics-page">
        <div class="analytics-header">
            <a href="/instructor" class="breadcrumb">&larr; Back to Dashboard</a>
            <h2>{{ class_name }} — Analytics</h2>
        </div>

        {% if question_stats %}
        <table class="analytics-table">
            <thead>
                <tr>
                    <th>Question</th>
                    <th class="col-center">Sessions</th>
                    <th class="col-center">Avg attempts</th>
                    <th class="col-center">Avg score</th>
                    <th>Score distribution</th>
                    <th></th>
                </tr>
            </thead>
            <tbody>
                {% for q in question_stats %}
                <tr>
                    <td class="analytics-question-title">{{ q.title }}</td>
                    <td class="col-center">{{ q.total_sessions }}</td>
                    <td class="col-center">{{ "%.1f"|format(q.avg_attempts) }}</td>
                    <td class="col-center">
                        {% if q.avg_final_score is not none %}
                            {{ "%.1f"|format(q.avg_final_score) }} / {{ q.max_total }}
                        {% else %}
                            <span class="analytics-muted">—</span>
                        {% endif %}
                    </td>
                    <td>
                        {% if q.score_buckets %}
                            <div class="score-dist-bar">
                                {% if q.score_buckets.low > 0 %}
                                <div class="score-dist-seg score-dist-low" style="flex:{{ q.score_buckets.low }}"></div>
                                {% endif %}
                                {% if q.score_buckets.mid > 0 %}
                                <div class="score-dist-seg score-dist-mid" style="flex:{{ q.score_buckets.mid }}"></div>
                                {% endif %}
                                {% if q.score_buckets.high > 0 %}
                                <div class="score-dist-seg score-dist-high" style="flex:{{ q.score_buckets.high }}"></div>
                                {% endif %}
                            </div>
                            <div class="score-dist-label">
                                {{ q.score_buckets.low }} low &middot;
                                {{ q.score_buckets.mid }} mid &middot;
                                {{ q.score_buckets.high }} high
                            </div>
                        {% else %}
                            <span class="analytics-muted">No scoring</span>
                        {% endif %}
                    </td>
                    <td>
                        <a href="/instructor/analytics/{{ q.question_id }}" class="analytics-link">View &rarr;</a>
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        {% else %}
        <p class="empty-state">No questions in this class yet.</p>
        {% endif %}
    </main>
</body>
</html>
```

- [ ] **Step 2: Append analytics CSS to `static/style.css`**

```css
/* ---- Analytics pages ---- */

.analytics-page {
    max-width: 960px;
    margin: 2rem auto;
    padding: 0 1.5rem;
}

.analytics-header {
    margin-bottom: 1.5rem;
}

.analytics-header h2 {
    margin: 0.25rem 0 0;
    font-size: 1.4rem;
}

.breadcrumb {
    font-size: 0.85rem;
    color: var(--text-muted);
    text-decoration: none;
}

.breadcrumb:hover {
    text-decoration: underline;
}

.analytics-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.9rem;
}

.analytics-table th {
    padding: 0.5rem 0.75rem;
    color: var(--text-muted);
    font-weight: 600;
    text-align: left;
    border-bottom: 2px solid var(--border);
}

.analytics-table td {
    padding: 0.6rem 0.75rem;
    border-bottom: 1px solid var(--bg-subtle);
    vertical-align: top;
}

.col-center {
    text-align: center;
}

.analytics-question-title {
    font-weight: 500;
}

.analytics-muted {
    color: var(--text-muted);
    font-style: italic;
}

.analytics-link {
    color: var(--primary);
    font-size: 0.85rem;
    text-decoration: none;
    white-space: nowrap;
}

.analytics-link:hover {
    text-decoration: underline;
}

.score-dist-bar {
    display: flex;
    height: 12px;
    border-radius: 3px;
    overflow: hidden;
    width: 120px;
    gap: 1px;
}

.score-dist-seg {
    min-width: 2px;
}

.score-dist-low  { background: #ef4444; }
.score-dist-mid  { background: #f59e0b; }
.score-dist-high { background: #22c55e; }

.score-dist-label {
    font-size: 0.72rem;
    color: var(--text-muted);
    margin-top: 3px;
}

/* ---- Analytics tiles ---- */

.analytics-tiles {
    display: flex;
    gap: 1rem;
    margin-bottom: 1.5rem;
}

.analytics-tile {
    background: var(--bg-subtle);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 0.75rem 1.25rem;
    text-align: center;
    min-width: 120px;
}

.tile-value {
    font-size: 1.5rem;
    font-weight: 700;
    color: var(--text);
}

.tile-label {
    font-size: 0.8rem;
    color: var(--text-muted);
    margin-top: 2px;
}

/* ---- Session detail ---- */

.session-id-cell {
    font-family: monospace;
    font-size: 0.82rem;
    color: var(--text-muted);
}

.score-high { color: #16a34a; font-weight: 600; }
.score-mid  { color: #d97706; font-weight: 600; }
.score-low  { color: #dc2626; font-weight: 600; }

.answers-cell {
    background: var(--bg-subtle);
    padding: 0.75rem 1.5rem;
}

.attempt-block {
    margin-bottom: 1rem;
    padding-bottom: 1rem;
    border-bottom: 1px solid var(--border);
}

.attempt-block:last-child {
    margin-bottom: 0;
    padding-bottom: 0;
    border-bottom: none;
}

.attempt-label {
    font-size: 0.75rem;
    font-weight: 600;
    color: var(--text-muted);
    text-transform: uppercase;
    margin-bottom: 0.35rem;
}

.attempt-answer {
    background: white;
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 0.6rem 0.75rem;
    font-size: 0.85rem;
    line-height: 1.5;
    white-space: pre-wrap;
}

.attempt-feedback-label {
    font-size: 0.75rem;
    font-weight: 600;
    color: var(--text-muted);
    text-transform: uppercase;
    margin: 0.75rem 0 0.35rem;
}

.attempt-feedback {
    background: white;
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 0.6rem 0.75rem;
    font-size: 0.85rem;
    line-height: 1.6;
    white-space: pre-wrap;
}
```

- [ ] **Step 3: Run the full test suite to confirm nothing broke**

```bash
pytest --tb=short -q
```

Expected: all tests PASS

- [ ] **Step 4: Commit**

```bash
git add templates/instructor-analytics-class.html static/style.css
git commit -m "feat: full class analytics template and analytics CSS"
```

---

### Task 5: Question analytics template

**Files:**
- Modify: `templates/instructor-analytics-question.html` (replace stub)

- [ ] **Step 1: Replace `instructor-analytics-question.html` with full template**

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Essay Coach — Session Detail</title>
    <link rel="stylesheet" href="/static/style.css">
</head>
<body>
    <header>
        <h1>Essay Coach <span class="badge">Instructor</span></h1>
        <nav>
            <span class="username-display">{{ username }}</span>
            <a href="/instructor">&larr; Dashboard</a>
            <form method="POST" action="/logout" style="display:inline; margin-left:0.75rem;">
                <button type="submit" class="btn btn-small">Sign Out</button>
            </form>
        </nav>
    </header>

    <main class="analytics-page">
        <div class="analytics-header">
            <a href="/instructor/classes/{{ class_id }}/analytics" class="breadcrumb">&larr; Back to Class Analytics</a>
            <h2>{{ question.title }} — Session Detail</h2>
        </div>

        <div class="analytics-tiles">
            <div class="analytics-tile">
                <div class="tile-value">{{ total_sessions }}</div>
                <div class="tile-label">Sessions</div>
            </div>
            <div class="analytics-tile">
                <div class="tile-value">{{ "%.1f"|format(avg_attempts) }}</div>
                <div class="tile-label">Avg attempts</div>
            </div>
            <div class="analytics-tile">
                <div class="tile-value">
                    {% if avg_final_score is not none %}
                        {{ "%.1f"|format(avg_final_score) }} / {{ max_total }}
                    {% else %}
                        &mdash;
                    {% endif %}
                </div>
                <div class="tile-label">Avg final score</div>
            </div>
        </div>

        {% if sessions %}
        <table class="analytics-table">
            <thead>
                <tr>
                    <th>Session</th>
                    <th class="col-center">Attempts</th>
                    <th>Score progression</th>
                    <th class="col-center">Final score</th>
                    <th></th>
                </tr>
            </thead>
            <tbody>
                {% for s in sessions %}
                <tr id="session-row-{{ loop.index }}">
                    <td class="session-id-cell">{{ s.session_id[:4] }}&hellip;{{ s.session_id[-4:] }}</td>
                    <td class="col-center">{{ s.attempt_count }}</td>
                    <td>
                        {% set has_any_score = s.score_progression | select | list | length > 0 %}
                        {% if has_any_score %}
                            {% for score in s.score_progression %}
                                {% if loop.last %}<strong>{{ score if score is not none else '&mdash;' }}</strong>{% else %}{{ score if score is not none else '&mdash;' }} &rarr; {% endif %}
                            {% endfor %}
                        {% else %}
                            <span class="analytics-muted">&mdash;</span>
                        {% endif %}
                    </td>
                    <td class="col-center">
                        {% if s.final_score is not none %}
                            {% set pct = s.final_score / s.max_total %}
                            {% if pct >= 0.70 %}
                                <span class="score-high">{{ s.final_score }} / {{ s.max_total }}</span>
                            {% elif pct >= 0.40 %}
                                <span class="score-mid">{{ s.final_score }} / {{ s.max_total }}</span>
                            {% else %}
                                <span class="score-low">{{ s.final_score }} / {{ s.max_total }}</span>
                            {% endif %}
                        {% else %}
                            <span class="analytics-muted">&mdash;</span>
                        {% endif %}
                    </td>
                    <td>
                        <button class="btn btn-small" onclick="toggleAnswers({{ loop.index }})">
                            &#9654; Show answers
                        </button>
                    </td>
                </tr>
                <tr id="answers-row-{{ loop.index }}" style="display:none">
                    <td colspan="5" class="answers-cell">
                        {% for attempt in s.attempts %}
                        <div class="attempt-block">
                            <div class="attempt-label">Attempt {{ attempt.attempt_number }}</div>
                            <div class="attempt-answer">{{ attempt.student_answer }}</div>
                            {% if loop.last and attempt.feedback %}
                            <div class="attempt-feedback-label">AI Feedback</div>
                            <div class="attempt-feedback">{{ attempt.feedback }}</div>
                            {% endif %}
                        </div>
                        {% endfor %}
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        {% else %}
        <p class="empty-state">No student submissions yet.</p>
        {% endif %}
    </main>

    <script>
    function toggleAnswers(idx) {
        var row = document.getElementById('answers-row-' + idx);
        var btn = document.querySelector('#session-row-' + idx + ' button');
        if (row.style.display === 'none') {
            row.style.display = '';
            btn.textContent = '\u25BE Hide answers';
        } else {
            row.style.display = 'none';
            btn.textContent = '\u25B6 Show answers';
        }
    }
    </script>
</body>
</html>
```

- [ ] **Step 2: Run the full test suite**

```bash
pytest --tb=short -q
```

Expected: all tests PASS

- [ ] **Step 3: Commit**

```bash
git add templates/instructor-analytics-question.html
git commit -m "feat: full question analytics template with answer/feedback expand"
```

---

### Task 6: Analytics entry points in `instructor.html`

**Files:**
- Modify: `templates/instructor.html`

- [ ] **Step 1: Add Analytics link to the class filter section header**

In `instructor.html`, find the `<div class="questions-section-header">` block (around line 66). After the `</select>` closing tag and before the closing `</div>`, add the class analytics links:

```html
            <div class="analytics-class-links">
                {% for cls in classes %}
                <a href="/instructor/classes/{{ cls.id }}/analytics" class="analytics-class-link">{{ cls.name }}</a>
                {% endfor %}
            </div>
```

The full updated block becomes:

```html
            <div class="questions-section-header">
                <h2>Existing Questions</h2>
                <select id="class-filter" class="class-filter" onchange="applyClassFilter()">
                    <option value="">All Classes</option>
                    {% for cls in classes %}
                    <option value="{{ cls.id }}">{{ cls.name }}</option>
                    {% endfor %}
                </select>
                <div class="analytics-class-links">
                    {% for cls in classes %}
                    <a href="/instructor/classes/{{ cls.id }}/analytics" class="analytics-class-link">{{ cls.name }}</a>
                    {% endfor %}
                </div>
            </div>
```

- [ ] **Step 2: Add Analytics link to each question card**

In `instructor.html`, find the `<div class="question-actions">` block (around line 86). Add an analytics link alongside Edit and Delete:

```html
                    <div class="question-actions">
                        <button class="btn btn-small" onclick="editQuestion('{{ q.id }}')">Edit</button>
                        <button class="btn btn-small btn-danger" onclick="deleteQuestion('{{ q.id }}')">Delete</button>
                        <a href="/instructor/analytics/{{ q.id }}" class="btn btn-small">Analytics</a>
                    </div>
```

- [ ] **Step 3: Append CSS for the class analytics links to `static/style.css`**

```css
/* ---- Dashboard analytics entry points ---- */

.analytics-class-links {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
    margin-top: 0.5rem;
}

.analytics-class-link {
    font-size: 0.78rem;
    color: var(--primary);
    text-decoration: none;
    background: var(--bg-subtle);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 0.2rem 0.5rem;
}

.analytics-class-link::after {
    content: " Analytics";
    color: var(--text-muted);
}

.analytics-class-link:hover {
    background: #dbeafe;
    border-color: #93c5fd;
}
```

- [ ] **Step 4: Run the full test suite one final time**

```bash
pytest --tb=short -q
```

Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add templates/instructor.html static/style.css
git commit -m "feat: add analytics entry points to instructor dashboard"
```
