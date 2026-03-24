# Essay Coach Tutorial

A complete guide to using and understanding Essay Coach — the local web app that helps university students improve essay answers through structured AI feedback.

---

## Table of Contents

### Part 1: User Guide
- [Quick Setup](#quick-setup)
- [For Instructors](#for-instructors)
  - [First-Time Setup: Creating Your Account](#first-time-setup-creating-your-account)
  - [Signing In](#signing-in)
  - [Creating a Question](#creating-a-question)
  - [Writing a Good Model Answer](#writing-a-good-model-answer)
  - [Writing an Effective Rubric](#writing-an-effective-rubric)
  - [Editing and Deleting Questions](#editing-and-deleting-questions)
  - [Viewing Analytics](#viewing-analytics)
  - [Managing the Invite Code](#managing-the-invite-code)
  - [Signing Out](#signing-out)
- [For Students](#for-students)
  - [Selecting a Question](#selecting-a-question)
  - [Writing and Submitting Your Answer](#writing-and-submitting-your-answer)
  - [Reading Your Feedback](#reading-your-feedback)
  - [Revising Your Answer](#revising-your-answer)
  - [Using Revision History](#using-revision-history)

### Part 2: Developer Guide
- [Architecture Overview](#architecture-overview)
- [Project Structure](#project-structure)
- [File-by-File Breakdown](#file-by-file-breakdown)
- [The Feedback Engine](#the-feedback-engine)
- [Security Model](#security-model)
- [Database Schema](#database-schema)
- [API Reference](#api-reference)
- [Frontend Architecture](#frontend-architecture)
- [Extending the App](#extending-the-app)

---

# Part 1: User Guide

## Quick Setup

You need Python 3.9+ and an Anthropic API key.

```bash
# Clone or navigate to the project
cd essay-coach

# Install dependencies
pip install -r requirements.txt

# Configure your API key
cp .env.example .env
```

Open `.env` in any text editor and replace the placeholder with your actual key:

```
ANTHROPIC_API_KEY=sk-ant-api03-your-key-here
```

You can get an API key at [console.anthropic.com](https://console.anthropic.com). The Anthropic API has its own billing — it is separate from a Claude Pro subscription.

Start the server:

```bash
python app.py
```

The app runs at **http://localhost:8000**. Open it in your browser.

- **Students** go to: `http://localhost:8000/student`
- **Instructors** go to: `http://localhost:8000/instructor` (login required)

---

## For Instructors

The instructor dashboard is protected by login. Instructors must create an account before they can access it.

### First-Time Setup: Creating Your Account

1. Start the server (`python app.py`).
2. Get the invite code the server generated on first startup:

   ```bash
   sqlite3 essay_coach.db "SELECT value FROM settings WHERE key='invite_code';"
   ```

3. Navigate to `http://localhost:8000/register`.
4. Enter a username, a password (8–72 characters), and the invite code from step 2.
5. Click **Create Account**. You'll be redirected to the instructor dashboard.

The invite code prevents unauthorized registrations. You can view and rotate it any time from the Settings section of the dashboard (see [Managing the Invite Code](#managing-the-invite-code)).

Additional instructors can register using the same invite code. Share it with anyone who should have instructor access.

### Signing In

Navigate to `http://localhost:8000/instructor`. If you're not logged in, you'll be redirected to `/login` automatically. Enter your username and password and click **Sign In**.

### Creating a Question

1. Navigate to `http://localhost:8000/instructor`.

![Instructor dashboard](images/instructor-dashboard.png)

2. On the left side, you'll see the **Create New Question** form with four fields:

| Field | Required | Description |
|-------|----------|-------------|
| **Title** | Yes | A short name for the question (e.g., "Photosynthesis"). Students see this when picking a question. |
| **Essay Prompt** | Yes | The full question text students will read and respond to. Be specific about what you want them to cover. |
| **Model Answer** | Yes | Your ideal answer. Students **never** see this — it is used only by the AI to judge how close the student's answer is. |
| **Rubric** | No | Optional grading criteria, one bullet point per line. Helps the AI focus its feedback on what matters most to you. |

3. Click **Create Question**. The question appears immediately in the "Existing Questions" list on the right.

### Writing a Good Model Answer

The model answer is the most important field. It directly shapes the quality of AI feedback. Tips:

- **Be comprehensive.** Include every concept, argument, and detail you'd expect in an A-grade answer. The AI uses this as the benchmark — anything missing from the model answer won't be flagged as missing from the student's answer.
- **Be specific.** Vague model answers produce vague feedback. If you want students to mention a particular mechanism, study, or relationship, include it.
- **Write in prose.** The AI compares the student's essay against your answer, so writing in full sentences (rather than bullet points) helps it assess depth and structure more accurately.
- **Don't worry about perfection.** The AI never quotes or paraphrases the model answer to students. It uses it as a reference, not a script.

**Example model answer for a Photosynthesis question:**

> Photosynthesis is the process by which plants, algae, and some bacteria convert light energy into chemical energy stored in glucose. It occurs in two stages: light-dependent reactions in the thylakoid membranes and the Calvin cycle in the stroma. In the light reactions, water is split, oxygen is released, and ATP and NADPH are produced. The Calvin cycle uses CO2, ATP, and NADPH to synthesize glucose through carbon fixation. Chlorophyll absorbs light primarily in the blue and red wavelengths, reflecting green. Photosynthesis is fundamental to life as it produces oxygen and is the basis for most food chains and aerobic life.

### Writing an Effective Rubric

The rubric is optional but recommended. It tells the AI which aspects of the answer matter most. Format it as one bullet point per line:

```
- Describes both light-dependent and light-independent reactions
- Mentions the role of chlorophyll in light absorption
- Explains oxygen as a byproduct
- Discusses significance for food chains and aerobic life
```

Tips:
- Keep each bullet focused on one concept or skill.
- Use action verbs: "Describes...", "Explains...", "Compares...", "Evaluates..."
- You don't need to cover everything — the AI also uses the model answer. The rubric just emphasizes your priorities.
- If you skip the rubric entirely, the AI still works fine — it just relies entirely on the model answer.

### Editing and Deleting Questions

Each question card in the "Existing Questions" list has two buttons:

- **Edit**: Loads the question's data (including the model answer and rubric) back into the form on the left. Make your changes and click **Update Question**. Click **Cancel** to discard changes.

![Instructor editing a question](images/instructor-edit.png)

- **Delete**: Permanently removes the question and all associated student attempts. You'll get a confirmation dialog first.

### Viewing Analytics

Each question card shows an **attempt count** badge (e.g., "5 attempts") — the total number of student submissions across all sessions. This gives you a rough sense of engagement.

### Managing the Invite Code

The Settings section at the bottom of the instructor dashboard shows the current invite code. Share this code with anyone who should be able to register as an instructor.

To generate a new code, click **Rotate**. The old code stops working immediately — any registration links or notes sharing the old code will need to be updated.

You can also view the current code from the command line:

```bash
sqlite3 essay_coach.db "SELECT value FROM settings WHERE key='invite_code';"
```

### Signing Out

Click **Sign Out** in the top-right of the instructor dashboard. Your session is ended and you'll be redirected to the login page.

---

## For Students

### Selecting a Question

1. Go to `http://localhost:8000` (or `/student`). You'll see a list of available questions.
2. Each card shows the question title and a preview of the essay prompt.
3. Click a question to open the writing workspace.

![Student question list](images/student-question-list.png)

### Writing and Submitting Your Answer

The workspace is a split-screen layout:

- **Left pane**: The essay prompt at the top, and a large text area below for your answer.
- **Right pane**: Where feedback appears after you submit.

![Student workspace](images/student-workspace.png)

Write or paste your answer into the text area, then click **Submit for Feedback**.

While the AI analyzes your answer, you'll see a pulsing dot with "Analyzing your answer..." The feedback streams in word-by-word in real time — you can start reading before it finishes.

![Student workspace with AI feedback](images/student-feedback.png)

### Reading Your Feedback

Feedback is structured into sections:

| Section | What It Tells You |
|---------|-------------------|
| **Coverage** | Which key concepts or arguments are present, partially addressed, or missing. The AI gives directional hints ("consider whether your discussion of X is complete") rather than revealing what the answer should say. |
| **Depth** | Where your reasoning could go deeper — areas where you've stated a fact but haven't explained the mechanism, significance, or connection. |
| **Structure** | How to improve the organization of your argument — paragraph ordering, transitions, logical flow. |
| **Accuracy** | Any factual errors or misconceptions the AI detected. |
| **Progress** | (Attempt 2 and later) What improved since your last attempt and what still needs work. |

The AI **never** gives you a grade or numeric score. It uses qualitative language only. It also **never** reveals the instructor's model answer — it's designed to guide you toward discovering the shape of a good answer through your own thinking.

### Revising Your Answer

After reading the feedback:

1. Edit your answer in the text area (your previous text is still there).
2. Click **Submit for Feedback** again.
3. The attempt counter increments. The AI sees your revision history and adjusts its feedback:
   - **Early attempts** get broad guidance.
   - **Later attempts** get more targeted, specific nudges.
   - If your answer is very close to the model answer, the AI will say so and suggest minor polish.

There is no limit on how many times you can revise and resubmit.

### Using Revision History

Below the workspace, there's a **Show Revision History** toggle. Click it to expand a collapsible list of all your previous attempts, newest first. Each entry shows:

- Your submitted answer text
- The feedback you received

Click any attempt's header to expand or collapse it. This helps you track your progress and see how your answer has evolved across revisions.

**Note:** Your attempts are tracked by a session ID stored in your browser's local storage. If you clear your browser data or switch browsers, you'll start fresh with no history.

---

# Part 2: Developer Guide

## Architecture Overview

Essay Coach is a deliberately simple stack:

```
Browser (vanilla JS) ←→ FastAPI (Python) ←→ SQLite + Anthropic API
```

- **Backend**: FastAPI serves both HTML pages (via Jinja2 templates) and a JSON/SSE API.
- **Frontend**: Plain HTML, CSS, and JavaScript — no framework, no build step.
- **Database**: SQLite, stored as a single file (`essay_coach.db`).
- **AI**: Anthropic Python SDK, calling `claude-sonnet-4-20250514` with streaming.
- **Auth**: Server-side sessions stored in SQLite. Passwords hashed with bcrypt via passlib. Instructor registration gated by invite code.

## Project Structure

```
essay-coach/
├── app.py              # FastAPI app — all routes (HTML + API)
├── auth.py             # Pure crypto: password hashing, token/code generation
├── dependencies.py     # FastAPI auth dependency (require_instructor_api)
├── feedback.py         # LLM prompt construction and streaming API call
├── db.py               # SQLite schema, connection, and query functions
├── config.py           # Environment variables and settings
├── static/
│   ├── style.css       # All styles (CSS custom properties, responsive grid)
│   └── app.js          # All client-side logic (student + instructor)
├── templates/
│   ├── student.html    # Student question list + workspace (Jinja2)
│   ├── instructor.html # Instructor dashboard (Jinja2)
│   ├── login.html      # Instructor login form
│   └── register.html   # Instructor registration form
├── tests/              # Test suite
├── requirements.txt    # Python dependencies
├── .env.example        # API key placeholder
└── docs/
    └── tutorial.md     # This file
```

## File-by-File Breakdown

### `config.py`

Loads environment variables from `.env` using `python-dotenv`. Exposes three settings:

- `ANTHROPIC_API_KEY` — required for the AI feedback to work.
- `DATABASE_PATH` — defaults to `essay_coach.db` in the project root.
- `MODEL_NAME` — hardcoded to `claude-sonnet-4-20250514`.

### `auth.py`

Pure cryptographic utilities with no project imports — only stdlib and passlib. This keeps it independently testable and free of circular imports.

| Function | Purpose |
|----------|---------|
| `hash_password(plain)` | Returns a bcrypt hash of the password. |
| `verify_password(plain, hashed)` | Constant-time bcrypt verification. |
| `generate_token()` | Returns a 64-character cryptographically random hex session token. |
| `generate_invite_code()` | Returns a random 8-character uppercase alphanumeric code. |
| `compare_codes(a, b)` | Constant-time string comparison via `hmac.compare_digest` — prevents timing attacks on invite code checks. |

### `dependencies.py`

FastAPI auth dependency used by all instructor API routes.

- **`_validate_session(token)`**: Looks up the session in the DB, returns `None` if missing or expired, and slides the 7-day expiry window on each valid access.
- **`require_instructor_api`**: An async FastAPI dependency that reads `session_token` from the cookie and raises HTTP 401 if the session is invalid. Used with `Depends()` on protected routes.

The `GET /instructor` HTML route imports `_validate_session` directly to redirect to `/login` on failure instead of returning a 401.

### `db.py`

Manages all SQLite interactions. Key design decisions:

- Uses `sqlite3.Row` as the row factory so query results behave like dictionaries.
- Enables foreign keys with `PRAGMA foreign_keys = ON`.
- Questions and users use UUID primary keys (generated in Python, not by SQLite).
- `ON DELETE CASCADE` on attempts (via questions) and sessions (via users).
- Every function opens and closes its own connection. This is simple but not suitable for high concurrency — fine for a local tool.
- On startup, `init_db()` deletes expired sessions and seeds the invite code if absent.

Functions — questions and attempts:

| Function | Purpose |
|----------|---------|
| `init_db()` | Creates all tables, cleans expired sessions, seeds invite code. Called on app startup. |
| `create_question(...)` | Inserts a new question, returns its UUID. |
| `get_question(id)` | Returns a single question as a dict, or `None`. |
| `list_questions()` | Returns all questions, newest first. |
| `update_question(id, **kwargs)` | Updates only the fields you pass. |
| `delete_question(id)` | Deletes a question and cascades to its attempts. |
| `create_attempt(...)` | Records a student submission and its feedback. |
| `get_attempts(question_id, session_id)` | Returns a student's attempts, newest first. |
| `get_attempt_count(question_id)` | Total submissions across all students. |

Functions — auth:

| Function | Purpose |
|----------|---------|
| `create_user(username, password_hash)` | Inserts a new instructor user, returns UUID. |
| `get_user_by_username(username)` | Returns user dict or `None`. |
| `get_user_by_id(user_id)` | Returns user dict or `None`. |
| `create_session(token, user_id, expires_at)` | Inserts a session row. |
| `get_session(token)` | Returns session if valid and not expired, else `None`. |
| `update_session_expiry(token, expires_at)` | Slides the session window. |
| `delete_session(token)` | Removes a single session (used on logout). |
| `delete_sessions_for_user(user_id)` | Removes all sessions for a user (used on login). |
| `get_setting(key)` | Returns a settings value or `None`. |
| `set_setting(key, value)` | Upserts a settings value. |

### `feedback.py`

The core of the app. Two functions:

**`build_messages(...)`** constructs the user message sent to Claude. The model answer and rubric are embedded in XML-delimited blocks that the LLM can reference:

```xml
<model_answer>...</model_answer>
<rubric>...</rubric>
<student_answer attempt="2">...</student_answer>
<previous_feedback>...</previous_feedback>
```

**`generate_feedback_stream(...)`** creates an async Anthropic client and streams the response. It yields text chunks as they arrive, which the API endpoint forwards to the browser via SSE.

The system prompt is embedded as a constant at the top of the file. It instructs the LLM to:
1. Never reveal the model answer's content directly.
2. Structure feedback into Coverage, Depth, Structure, Accuracy, and Progress sections.
3. Scale specificity with attempt number (broad early, targeted later).
4. Use qualitative language only — no grades or scores.

### `app.py`

The FastAPI application. Routes are organized into four groups:

**HTML routes** (serve pages):
- `GET /` → redirects to `/student`
- `GET /login` → login form
- `GET /register` → registration form
- `POST /logout` → ends session, redirects to `/login`
- `GET /student` → renders question list
- `GET /student/{id}` → renders writing workspace
- `GET /instructor` → renders instructor dashboard (redirects to `/login` if not authenticated)

**Auth API routes**:
- `POST /api/auth/register` → validates invite code, creates user and session
- `POST /api/auth/login` → validates credentials, creates session
- `GET /api/auth/me` → returns `{username}` for the logged-in instructor

**Settings API routes** (instructor-protected):
- `GET /api/settings/invite-code` → returns current invite code
- `PUT /api/settings/invite-code` → rotates invite code (generates one if no body supplied)

**Questions API routes** (instructor-protected):
- `POST /api/questions` → create question
- `GET /api/questions/detail/{id}` → full question data including model answer
- `PUT /api/questions/{id}` → update question
- `DELETE /api/questions/{id}` → delete question

**Student API routes** (unprotected):
- `POST /api/feedback` → stream AI feedback via SSE
- `GET /api/attempts/{id}?session_id=...` → attempt history

### `static/app.js`

A single JS file handling both the student and instructor interfaces. Key patterns:

- **Session management**: `getSessionId()` creates a UUID in `localStorage` on first visit. This tracks a student's attempts without requiring login.
- **Auth error handling**: `handleAuthError(res)` checks for HTTP 401 responses on instructor fetch calls and redirects to `/login` if found.
- **Invite code**: `loadInviteCode()` and `rotateInviteCode()` manage the invite code display in the Settings section.
- **SSE consumption**: `submitForFeedback()` uses `fetch()` with a `ReadableStream` reader to process Server-Sent Events manually (no EventSource API — this allows POST requests).
- **Markdown rendering**: `formatFeedback()` does lightweight Markdown-to-HTML conversion (bold, headers, lists) for the streamed feedback text.
- **History loading**: `loadAttemptHistory()` fetches past attempts from the API and renders collapsible cards.

### `static/style.css`

Vanilla CSS using custom properties (CSS variables) for theming. Key layout decisions:

- The student workspace uses `CSS Grid` with two equal columns (left: writing, right: feedback).
- The instructor page uses the same two-column grid (left: form, right: question list).
- Auth pages (login, register) use a centered card layout (`max-width: 420px`).
- Mobile breakpoint at 768px collapses both layouts to single-column.
- Feedback background uses `--bg-subtle` (#f7f7f8) to visually distinguish it from the writing area.
- System font stack — no external fonts or CSS frameworks.

## The Feedback Engine

This is how a student submission turns into feedback:

```
Student clicks "Submit"
    → Browser POSTs to /api/feedback
        → Server looks up question (model_answer, rubric)
        → Server calls build_messages() to construct the prompt
        → Server opens streaming connection to Anthropic API
        → Each text chunk is forwarded to browser via SSE
        → Browser renders chunks in real-time
        → When stream ends, server saves attempt to SQLite
        → Browser receives "done" event, reloads history
```

The system prompt is critical. It tells Claude to act as an essay coach with strict rules about never revealing the model answer. The key constraint is **directional feedback**: instead of saying "you should mention X," the AI says "consider whether your discussion of X is complete."

The prompt also instructs Claude to **scale specificity with attempt number**. On attempt 1, feedback is broad ("you're missing some key concepts in area X"). By attempt 4, it's much more targeted ("your discussion of X is solid but doesn't address the relationship between X and Y").

## Security Model

### Model answer protection

The central security constraint: **the model answer must never reach the student's browser**.

This is enforced at multiple layers:

1. **HTML routes**: When rendering student pages, the server strips `model_answer` and `rubric` from the question data before passing it to the template. Only `id`, `title`, and `prompt` are sent.

2. **API responses**: The `/api/feedback` endpoint returns only the feedback text via SSE — never the model answer or rubric. The `/api/attempts` endpoint returns only `student_answer` and `feedback`.

3. **Server-side only**: The model answer is passed to the LLM via the Anthropic API call. It exists only in server memory during the request. The LLM's system prompt forbids it from quoting or paraphrasing the model answer.

4. **Protected endpoint**: `GET /api/questions/detail/{id}` returns the full question including model answer, but requires an authenticated instructor session.

5. **Code annotations**: Security-critical lines are marked with `# SECURITY: model_answer is server-side only, never sent to client`.

### Instructor authentication

- Passwords are hashed with bcrypt (via passlib). The raw password is never stored.
- Sessions use a 64-character cryptographically random token stored in an `HttpOnly`, `SameSite=Lax` cookie. The token cannot be read by JavaScript.
- Sessions have a 7-day sliding expiry window — each authenticated request extends the session.
- On login, all existing sessions for the user are deleted, preventing session accumulation.
- Invite codes are compared using `hmac.compare_digest` (constant-time) to prevent timing attacks.
- Password length is validated server-side to 8–72 characters (bcrypt silently truncates at 72 bytes).
- The `POST /logout` route prevents CSRF-via-GET (an `<img src="/logout">` tag cannot log out an instructor).

**Note on HTTPS:** The session cookie does not set the `Secure` flag, which is intentional for local HTTP development. If you deploy this app over HTTPS, add `secure=True` to the `set_cookie` call in `app.py`'s `_set_session_cookie` helper.

## Database Schema

Five tables:

```sql
CREATE TABLE questions (
    id TEXT PRIMARY KEY,          -- UUID generated in Python
    title TEXT NOT NULL,
    prompt TEXT NOT NULL,
    model_answer TEXT NOT NULL,
    rubric TEXT,                  -- Optional, one bullet per line
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE attempts (
    id TEXT PRIMARY KEY,          -- UUID generated in Python
    question_id TEXT REFERENCES questions(id) ON DELETE CASCADE,
    session_id TEXT NOT NULL,     -- Browser-generated UUID
    student_answer TEXT NOT NULL,
    feedback TEXT,
    attempt_number INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE users (
    id TEXT PRIMARY KEY,          -- UUID generated in Python
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,  -- bcrypt via passlib
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE sessions (
    token TEXT PRIMARY KEY,       -- 64-char hex (secrets.token_hex(32))
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at TIMESTAMP NOT NULL -- 7-day sliding window
);

CREATE INDEX idx_sessions_user_id ON sessions(user_id);

CREATE TABLE settings (
    key TEXT PRIMARY KEY,         -- e.g. "invite_code"
    value TEXT NOT NULL
);
```

The `session_id` on attempts is how the app tracks which submissions belong to which student browser session, without requiring login. Each browser gets a random UUID stored in `localStorage`.

## API Reference

### Auth

| Method | Endpoint | Body | Returns | Auth required |
|--------|----------|------|---------|---------------|
| `POST` | `/api/auth/register` | `{username, password, invite_code}` | `{ok: true}` + cookie | No |
| `POST` | `/api/auth/login` | `{username, password}` | `{ok: true}` + cookie | No |
| `GET` | `/api/auth/me` | — | `{username}` | Yes |

### Settings

| Method | Endpoint | Body | Returns | Auth required |
|--------|----------|------|---------|---------------|
| `GET` | `/api/settings/invite-code` | — | `{invite_code}` | Yes |
| `PUT` | `/api/settings/invite-code` | `{code?}` | `{invite_code}` | Yes |

If `code` is omitted or empty on PUT, a random 8-character code is generated.

### Questions

| Method | Endpoint | Body | Returns | Auth required |
|--------|----------|------|---------|---------------|
| `POST` | `/api/questions` | `{title, prompt, model_answer, rubric?}` | `{id}` | Yes |
| `GET` | `/api/questions/detail/{id}` | — | Full question object | Yes |
| `PUT` | `/api/questions/{id}` | `{title?, prompt?, model_answer?, rubric?}` | `{ok: true}` | Yes |
| `DELETE` | `/api/questions/{id}` | — | `{ok: true}` | Yes |

### Feedback

| Method | Endpoint | Body | Returns | Auth required |
|--------|----------|------|---------|---------------|
| `POST` | `/api/feedback` | `{question_id, student_answer, session_id}` | SSE stream | No |

The SSE stream emits two types of events:
- `data: {"text": "chunk of feedback"}` — one per streaming token
- `data: {"done": true, "attempt_number": 3}` — signals completion

### Attempts

| Method | Endpoint | Query Params | Returns | Auth required |
|--------|----------|--------------|---------|---------------|
| `GET` | `/api/attempts/{question_id}` | `session_id` (required) | `{attempts: [...]}` | No |

Each attempt object contains: `id`, `question_id`, `session_id`, `student_answer`, `feedback`, `attempt_number`, `created_at`.

## Frontend Architecture

The frontend is intentionally simple — no framework, no build tools, no npm.

**Templates** (`templates/`): Jinja2 templates that the server renders with context data. The student template has two modes controlled by a Jinja `{% if %}` block:
- Question list mode (when `questions` is set)
- Workspace mode (when `question` is set)

The instructor template receives a `username` variable from the route, used to display the logged-in user's name in the header.

**JavaScript** (`static/app.js`): A single file with two sections separated by comments. `initStudent()` and `initInstructor()` are called from their respective templates. The code uses only modern browser APIs (`fetch`, `crypto.randomUUID`, `ReadableStream`).

**CSS** (`static/style.css`): All styles in one file. Uses CSS custom properties for colors and spacing, CSS Grid for layout, and a single `@media` breakpoint for mobile.

**No build step.** Edit the files and refresh the browser.

## Extending the App

### Per-Student Analytics
- Add an instructor view that lists individual student sessions per question.
- Show attempt-over-attempt improvement.
- Allow instructors to read student answers and feedback (read-only).

### Multiple Student Sessions
- Let students explicitly start a "new attempt session" for the same question.
- Track separate revision chains.

### Other Ideas
- **Export**: Download attempt history as CSV or PDF.
- **File upload**: Accept essay uploads (`.txt`, `.docx`) in addition to paste.
- **Custom LLM settings**: Let instructors adjust feedback tone, max tokens, or model.
- **Plagiarism detection**: Compare submissions across students.
- **Rubric scoring**: Optional numeric rubric scoring alongside qualitative feedback.

---

## Troubleshooting

### "Failed to get feedback" error
- Check that your `.env` file has a valid `ANTHROPIC_API_KEY`.
- Make sure the API key has available credits at [console.anthropic.com](https://console.anthropic.com).
- Check the terminal running `python app.py` for error messages.

### Server won't start
- Ensure all dependencies are installed: `pip install -r requirements.txt`
- Check you're using Python 3.9 or later: `python --version`

### Feedback is generic or unhelpful
- Improve your model answer — the more detailed it is, the better the AI can assess gaps.
- Add a rubric to focus the AI on the criteria you care about most.

### Lost my revision history
- History is tied to a browser session ID stored in `localStorage`. Clearing browser data or switching browsers resets it.
- The data still exists in the SQLite database. You can query it directly:
  ```bash
  sqlite3 essay_coach.db "SELECT * FROM attempts ORDER BY created_at DESC;"
  ```

### Forgot the invite code
- Retrieve it from the database:
  ```bash
  sqlite3 essay_coach.db "SELECT value FROM settings WHERE key='invite_code';"
  ```
- Or log in to the instructor dashboard — it's displayed in the Settings section.

### Forgot my password
- There is no password reset flow. An admin with database access can delete the user row and re-register:
  ```bash
  sqlite3 essay_coach.db "DELETE FROM users WHERE username='alice';"
  ```
  Then register again at `/register` with the current invite code.
