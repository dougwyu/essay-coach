# Essay Coach Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a local web app where instructors create essay questions with hidden model answers, and students get structured AI feedback to iteratively improve their essays.

**Architecture:** FastAPI serves HTML templates and JSON/SSE API endpoints. SQLite for persistence via raw queries. Anthropic SDK streams feedback. Two views: instructor CRUD and student writing workspace.

**Tech Stack:** Python 3.10+, FastAPI, uvicorn, Jinja2, sqlite3, anthropic SDK, python-dotenv

---

### Task 1: Project scaffolding and dependencies

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `config.py`
- Create: `.gitignore`

**Step 1: Create requirements.txt**

```
fastapi==0.115.6
uvicorn[standard]==0.34.0
jinja2==3.1.5
python-dotenv==1.0.1
anthropic==0.52.0
python-multipart==0.0.20
```

**Step 2: Create .env.example**

```
ANTHROPIC_API_KEY=your-api-key-here
```

**Step 3: Create .gitignore**

```
__pycache__/
*.pyc
.env
*.db
.venv/
```

**Step 4: Create config.py**

```python
import os
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
DATABASE_PATH = os.getenv("DATABASE_PATH", "essay_coach.db")
MODEL_NAME = "claude-sonnet-4-20250514"
```

**Step 5: Install dependencies and commit**

```bash
pip install -r requirements.txt
git add requirements.txt .env.example .gitignore config.py
git commit -m "feat: project scaffolding and dependencies"
```

---

### Task 2: Database layer

**Files:**
- Create: `db.py`
- Create: `tests/test_db.py`

**Step 1: Write failing tests for db functions**

```python
# tests/test_db.py
import os
import pytest
from db import init_db, create_question, get_question, list_questions, update_question, delete_question, create_attempt, get_attempts, get_attempt_count

@pytest.fixture(autouse=True)
def test_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr("db.DATABASE_PATH", db_path)
    init_db()
    yield db_path

def test_create_and_get_question():
    qid = create_question("Test Title", "Write about X", "X is Y because Z", "Point 1\nPoint 2")
    q = get_question(qid)
    assert q["title"] == "Test Title"
    assert q["prompt"] == "Write about X"
    assert q["model_answer"] == "X is Y because Z"
    assert q["rubric"] == "Point 1\nPoint 2"

def test_list_questions():
    create_question("Q1", "Prompt 1", "Answer 1", "")
    create_question("Q2", "Prompt 2", "Answer 2", "")
    qs = list_questions()
    assert len(qs) == 2

def test_update_question():
    qid = create_question("Old", "Old prompt", "Old answer", "")
    update_question(qid, title="New", prompt="New prompt", model_answer="New answer", rubric="New rubric")
    q = get_question(qid)
    assert q["title"] == "New"

def test_delete_question():
    qid = create_question("Del", "P", "A", "")
    delete_question(qid)
    assert get_question(qid) is None

def test_create_and_get_attempts():
    qid = create_question("Q", "P", "A", "")
    aid1 = create_attempt(qid, "session1", "My answer", "Good job", 1)
    aid2 = create_attempt(qid, "session1", "Better answer", "Even better", 2)
    attempts = get_attempts(qid, "session1")
    assert len(attempts) == 2
    assert attempts[0]["attempt_number"] == 2  # newest first

def test_get_attempt_count():
    qid = create_question("Q", "P", "A", "")
    create_attempt(qid, "s1", "ans", "fb", 1)
    create_attempt(qid, "s2", "ans", "fb", 1)
    assert get_attempt_count(qid) == 2
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_db.py -v
```
Expected: FAIL — `db` module not found.

**Step 3: Implement db.py**

```python
# db.py
import sqlite3
import uuid
from config import DATABASE_PATH

def _connect():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = _connect()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS questions (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            prompt TEXT NOT NULL,
            model_answer TEXT NOT NULL,
            rubric TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS attempts (
            id TEXT PRIMARY KEY,
            question_id TEXT REFERENCES questions(id) ON DELETE CASCADE,
            session_id TEXT NOT NULL,
            student_answer TEXT NOT NULL,
            feedback TEXT,
            attempt_number INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    conn.close()

def create_question(title, prompt, model_answer, rubric):
    qid = str(uuid.uuid4())
    conn = _connect()
    conn.execute(
        "INSERT INTO questions (id, title, prompt, model_answer, rubric) VALUES (?, ?, ?, ?, ?)",
        (qid, title, prompt, model_answer, rubric)
    )
    conn.commit()
    conn.close()
    return qid

def get_question(question_id):
    conn = _connect()
    row = conn.execute("SELECT * FROM questions WHERE id = ?", (question_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def list_questions():
    conn = _connect()
    rows = conn.execute("SELECT * FROM questions ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def update_question(question_id, **kwargs):
    allowed = {"title", "prompt", "model_answer", "rubric"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [question_id]
    conn = _connect()
    conn.execute(f"UPDATE questions SET {set_clause} WHERE id = ?", values)
    conn.commit()
    conn.close()

def delete_question(question_id):
    conn = _connect()
    conn.execute("DELETE FROM questions WHERE id = ?", (question_id,))
    conn.commit()
    conn.close()

def create_attempt(question_id, session_id, student_answer, feedback, attempt_number):
    aid = str(uuid.uuid4())
    conn = _connect()
    conn.execute(
        "INSERT INTO attempts (id, question_id, session_id, student_answer, feedback, attempt_number) VALUES (?, ?, ?, ?, ?, ?)",
        (aid, question_id, session_id, student_answer, feedback, attempt_number)
    )
    conn.commit()
    conn.close()
    return aid

def get_attempts(question_id, session_id):
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM attempts WHERE question_id = ? AND session_id = ? ORDER BY attempt_number DESC",
        (question_id, session_id)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_attempt_count(question_id):
    conn = _connect()
    row = conn.execute("SELECT COUNT(*) as cnt FROM attempts WHERE question_id = ?", (question_id,)).fetchone()
    conn.close()
    return row["cnt"]
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/test_db.py -v
```
Expected: ALL PASS

**Step 5: Commit**

```bash
git add db.py tests/test_db.py
git commit -m "feat: database layer with SQLite schema and queries"
```

---

### Task 3: Feedback engine

**Files:**
- Create: `feedback.py`
- Create: `tests/test_feedback.py`

**Step 1: Write test for prompt construction**

```python
# tests/test_feedback.py
from feedback import build_messages

def test_build_messages_first_attempt():
    messages = build_messages(
        question_prompt="Explain X",
        model_answer="X is Y",
        rubric="Cover Y",
        student_answer="I think X might be Y",
        attempt_number=1,
        previous_feedback=None
    )
    assert messages[0]["role"] == "user"
    content = messages[0]["content"]
    assert "<model_answer>" in content
    assert "<student_answer" in content
    assert "attempt=\"1\"" in content
    assert "<previous_feedback>" not in content

def test_build_messages_with_previous_feedback():
    messages = build_messages(
        question_prompt="Explain X",
        model_answer="X is Y",
        rubric="Cover Y",
        student_answer="Better answer",
        attempt_number=2,
        previous_feedback="You missed Z"
    )
    content = messages[0]["content"]
    assert "<previous_feedback>" in content
    assert "attempt=\"2\"" in content
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/test_feedback.py -v
```

**Step 3: Implement feedback.py**

```python
# feedback.py
import anthropic
from config import ANTHROPIC_API_KEY, MODEL_NAME

SYSTEM_PROMPT = """You are an essay coach helping a university student improve their answer. You have access to the instructor's model answer and rubric, but you must NEVER reveal the model answer's content directly. Your job is to give the student directional feedback so they can discover the shape of a good answer through revision.

Rules:
1. NEVER quote, paraphrase, or closely mirror the model answer. Do not say "the answer should state that X is Y." Instead say "consider whether your discussion of X is complete."
2. Structure feedback as:
   - COVERAGE: Which key concepts/arguments are present, partially present, or missing? Use vague directional hints, not the actual content.
   - DEPTH: Where does the student's reasoning need to go deeper?
   - STRUCTURE: How could the argument's organization improve?
   - ACCURACY: Flag any factual errors or misconceptions.
   - PROGRESS (attempt 2+): What improved since last attempt, what still needs work.
3. Be encouraging but honest. Scale specificity with attempt number: early attempts get broad strokes, later attempts get more targeted nudges.
4. If the answer is very close to the model answer, say so and suggest minor polish rather than new directions.
5. Never assign a grade or numeric score. Use qualitative language only."""


def build_messages(question_prompt, model_answer, rubric, student_answer, attempt_number, previous_feedback=None):
    # SECURITY: model_answer is server-side only, never sent to client
    content = f"""The student is answering this question: {question_prompt}

<model_answer>{model_answer}</model_answer>
<rubric>{rubric or "No specific rubric provided."}</rubric>
<student_answer attempt="{attempt_number}">{student_answer}</student_answer>"""

    if previous_feedback:
        content += f"\n<previous_feedback>{previous_feedback}</previous_feedback>"

    return [{"role": "user", "content": content}]


async def generate_feedback_stream(question_prompt, model_answer, rubric, student_answer, attempt_number, previous_feedback=None):
    client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    messages = build_messages(question_prompt, model_answer, rubric, student_answer, attempt_number, previous_feedback)

    async with client.messages.stream(
        model=MODEL_NAME,
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=messages,
    ) as stream:
        async for text in stream.text_stream:
            yield text
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/test_feedback.py -v
```

**Step 5: Commit**

```bash
git add feedback.py tests/test_feedback.py
git commit -m "feat: feedback engine with LLM prompt construction and streaming"
```

---

### Task 4: FastAPI app with all routes

**Files:**
- Create: `app.py`

**Step 1: Implement app.py with all API endpoints and HTML serving**

```python
# app.py
import json
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Optional
from db import init_db, create_question, get_question, list_questions, update_question, delete_question, create_attempt, get_attempts, get_attempt_count
from feedback import generate_feedback_stream

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

@app.on_event("startup")
def startup():
    init_db()

# --- HTML routes ---

@app.get("/", response_class=RedirectResponse)
def root():
    return RedirectResponse(url="/student")

@app.get("/student", response_class=HTMLResponse)
def student_list(request: Request):
    questions = list_questions()
    # SECURITY: model_answer is server-side only, never sent to client
    safe_questions = [{"id": q["id"], "title": q["title"], "prompt": q["prompt"]} for q in questions]
    return templates.TemplateResponse("student.html", {"request": request, "questions": safe_questions, "question": None})

@app.get("/student/{question_id}", response_class=HTMLResponse)
def student_workspace(request: Request, question_id: str):
    q = get_question(question_id)
    if not q:
        return RedirectResponse(url="/student")
    # SECURITY: model_answer is server-side only, never sent to client
    safe_question = {"id": q["id"], "title": q["title"], "prompt": q["prompt"]}
    return templates.TemplateResponse("student.html", {"request": request, "questions": None, "question": safe_question})

@app.get("/instructor", response_class=HTMLResponse)
def instructor_dashboard(request: Request):
    questions = list_questions()
    for q in questions:
        q["attempt_count"] = get_attempt_count(q["id"])
    return templates.TemplateResponse("instructor.html", {"request": request, "questions": questions})

# --- API routes ---

class QuestionCreate(BaseModel):
    title: str
    prompt: str
    model_answer: str
    rubric: Optional[str] = ""

class QuestionUpdate(BaseModel):
    title: Optional[str] = None
    prompt: Optional[str] = None
    model_answer: Optional[str] = None
    rubric: Optional[str] = None

class FeedbackRequest(BaseModel):
    question_id: str
    student_answer: str
    session_id: str

@app.post("/api/questions")
def api_create_question(data: QuestionCreate):
    qid = create_question(data.title, data.prompt, data.model_answer, data.rubric)
    return {"id": qid}

@app.put("/api/questions/{question_id}")
def api_update_question(question_id: str, data: QuestionUpdate):
    kwargs = {k: v for k, v in data.model_dump().items() if v is not None}
    update_question(question_id, **kwargs)
    return {"ok": True}

@app.delete("/api/questions/{question_id}")
def api_delete_question(question_id: str):
    delete_question(question_id)
    return {"ok": True}

@app.get("/api/attempts/{question_id}")
def api_get_attempts(question_id: str, session_id: str):
    attempts = get_attempts(question_id, session_id)
    return {"attempts": attempts}

@app.post("/api/feedback")
async def api_feedback(data: FeedbackRequest):
    question = get_question(data.question_id)
    if not question:
        return {"error": "Question not found"}

    # SECURITY: model_answer is server-side only, never sent to client
    attempts = get_attempts(data.question_id, data.session_id)
    attempt_number = len(attempts) + 1
    previous_feedback = attempts[0]["feedback"] if attempts else None

    collected_feedback = []

    async def event_stream():
        async for chunk in generate_feedback_stream(
            question_prompt=question["prompt"],
            model_answer=question["model_answer"],
            rubric=question["rubric"],
            student_answer=data.student_answer,
            attempt_number=attempt_number,
            previous_feedback=previous_feedback,
        ):
            collected_feedback.append(chunk)
            yield f"data: {json.dumps({'text': chunk})}\n\n"

        full_feedback = "".join(collected_feedback)
        create_attempt(data.question_id, data.session_id, data.student_answer, full_feedback, attempt_number)
        yield f"data: {json.dumps({'done': True, 'attempt_number': attempt_number})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
```

**Step 2: Commit**

```bash
git add app.py
git commit -m "feat: FastAPI app with all routes and SSE streaming"
```

---

### Task 5: Instructor HTML template

**Files:**
- Create: `templates/instructor.html`

**Step 1: Create instructor.html** — full CRUD form, question list with attempt counts, edit/delete.

**Step 2: Commit**

```bash
git add templates/instructor.html
git commit -m "feat: instructor dashboard template"
```

---

### Task 6: Student HTML template

**Files:**
- Create: `templates/student.html`

**Step 1: Create student.html** — question list view, writing workspace with left/right panes, SSE feedback display, collapsible revision history sidebar.

**Step 2: Commit**

```bash
git add templates/student.html
git commit -m "feat: student workspace template"
```

---

### Task 7: Frontend JavaScript

**Files:**
- Create: `static/app.js`

**Step 1: Implement app.js** — handles SSE feedback streaming, attempt history loading, session ID management via localStorage, form submissions for instructor CRUD.

**Step 2: Commit**

```bash
git add static/app.js
git commit -m "feat: frontend JavaScript for SSE and CRUD"
```

---

### Task 8: CSS styling

**Files:**
- Create: `static/style.css`

**Step 1: Implement style.css** — minimal clean UI, system font stack, white bg, dark text, generous whitespace, feedback section with subtle background, responsive layout, collapsible sidebar styles.

**Step 2: Commit**

```bash
git add static/style.css
git commit -m "feat: clean minimal CSS styling"
```

---

### Task 9: README and final integration test

**Files:**
- Create: `README.md`

**Step 1: Create README.md** with setup instructions.

**Step 2: Run all tests**

```bash
pytest tests/ -v
```

**Step 3: Manual smoke test** — start server, create question via instructor page, submit answer via student page, verify feedback streams and model answer never appears in network responses.

**Step 4: Final commit**

```bash
git add README.md
git commit -m "docs: README with setup instructions"
```
