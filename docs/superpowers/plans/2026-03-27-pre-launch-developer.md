# Pre-Launch Developer Tasks — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prepare Essay Coach for production deployment on a university-managed Docker host with PostgreSQL and a switchable LLM backend (Anthropic API or local Ollama).

**Architecture:** A new `db_connection.py` module abstracts the database driver so `db.py` works with both SQLite (dev/test) and PostgreSQL (production) via an environment variable. A `LLM_BACKEND` env var in `config.py` routes `feedback.py` calls to either the Anthropic API or an Ollama-hosted open-source model. Docker Compose wires the app, database, Nginx, and optional Ollama together.

**Tech Stack:** Python 3.12, FastAPI, psycopg2-binary, httpx, Ollama (OpenAI-compatible API), Docker Compose v2, Nginx, PostgreSQL 16.

---

## File Map

| Action | File | Responsibility |
|---|---|---|
| Modify | `config.py` | Add `LLM_BACKEND`, `OLLAMA_*`, `DATABASE_URL` |
| Create | `.env.example` | Document all env vars for the server operator |
| Create | `db_connection.py` | Driver abstraction: SQLite compat wrapper + psycopg2 path |
| Modify | `db.py` | Use `db_connection.py`; add PostgreSQL `init_db` path; replace `?` → `%s` |
| Modify | `feedback.py` | Add Ollama streaming and scoring paths |
| Modify | `requirements.txt` | Add `psycopg2-binary`, `httpx` |
| Create | `Dockerfile` | Build the app image |
| Create | `docker-compose.yml` | Orchestrate app, db, nginx, optional ollama |
| Create | `nginx.conf` | Reverse proxy + TLS + SSE + rate limiting |
| Create | `scripts/migrate_to_postgres.py` | One-time SQLite → PostgreSQL data transfer |
| Create | `tests/test_ollama_feedback.py` | Unit tests for Ollama LLM path |

---

## Task 1: Extend config.py and create .env.example

**Files:**
- Modify: `config.py`
- Create: `.env.example`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
import importlib, os, sys

def _reload_config(env):
    for mod in list(sys.modules.keys()):
        if "config" in mod:
            del sys.modules[mod]
    os.environ.update(env)
    import config
    return config

def test_defaults(monkeypatch):
    monkeypatch.delenv("LLM_BACKEND", raising=False)
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    cfg = _reload_config({})
    assert cfg.LLM_BACKEND == "anthropic"
    assert cfg.OLLAMA_BASE_URL == "http://ollama:11434"
    assert cfg.OLLAMA_MODEL == "llama3.3:70b"
    assert cfg.DATABASE_URL == ""

def test_ollama_env(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "ollama")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "phi4:14b")
    cfg = _reload_config({})
    assert cfg.LLM_BACKEND == "ollama"
    assert cfg.OLLAMA_MODEL == "phi4:14b"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/douglasyu/src/Cowork/essay-coach
pytest tests/test_config.py -v
```

Expected: `AttributeError: module 'config' has no attribute 'LLM_BACKEND'`

- [ ] **Step 3: Update config.py**

Replace the entire file:

```python
import os
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
DATABASE_PATH = os.getenv("DATABASE_PATH", "essay_coach.db")   # dev/test only
DATABASE_URL = os.getenv("DATABASE_URL", "")                   # production PostgreSQL
MODEL_NAME = "claude-sonnet-4-20250514"

# LLM backend: "anthropic" (default) or "ollama"
LLM_BACKEND = os.getenv("LLM_BACKEND", "anthropic")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.3:70b")
```

- [ ] **Step 4: Create .env.example**

```bash
cat > .env.example << 'EOF'
# ── LLM Backend ─────────────────────────────────────────────────────────────
# "anthropic" (default) or "ollama"
LLM_BACKEND=anthropic

# Required when LLM_BACKEND=anthropic
ANTHROPIC_API_KEY=sk-ant-...

# Required when LLM_BACKEND=ollama
OLLAMA_BASE_URL=http://ollama:11434
OLLAMA_MODEL=llama3.3:70b

# ── Database ─────────────────────────────────────────────────────────────────
# Production: PostgreSQL connection URL
DATABASE_URL=postgresql://essay_coach:CHANGE_ME@db:5432/essay_coach

# PostgreSQL credentials (used by the docker-compose db service)
POSTGRES_USER=essay_coach
POSTGRES_PASSWORD=CHANGE_ME

# Development / testing only (ignored when DATABASE_URL is set)
# DATABASE_PATH=essay_coach.db
EOF
```

- [ ] **Step 5: Run test to verify it passes**

```bash
pytest tests/test_config.py -v
```

Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add config.py .env.example tests/test_config.py
git commit -m "feat: add LLM_BACKEND and DATABASE_URL env vars to config"
```

---

## Task 2: Add psycopg2-binary and httpx to requirements.txt

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add the two packages**

Open `requirements.txt` and add after the existing lines:

```
psycopg2-binary==2.9.10
httpx>=0.27.0
```

- [ ] **Step 2: Install them**

```bash
pip install psycopg2-binary==2.9.10 "httpx>=0.27.0"
```

Expected: both packages install without errors.

- [ ] **Step 3: Verify existing tests still pass**

```bash
pytest --tb=short -q
```

Expected: same pass count as before, no new failures.

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "chore: add psycopg2-binary and httpx to requirements"
```

---

## Task 3: Create db_connection.py — database driver abstraction

**Files:**
- Create: `db_connection.py`
- Create: `tests/test_db_connection.py`

This module provides a single `get_conn()` factory that returns a connection object compatible with the `conn.execute(sql, params)` pattern already used throughout `db.py`. The SQLite path wraps the standard `sqlite3` connection so it accepts `%s` placeholders (PostgreSQL style). The PostgreSQL path uses `psycopg2` with `RealDictCursor` so rows come back as plain dicts in both cases.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_db_connection.py
import os
import pytest


def _get_module(monkeypatch, database_url=""):
    import sys
    for key in list(sys.modules):
        if key in ("db_connection", "config"):
            del sys.modules[key]
    monkeypatch.setenv("DATABASE_URL", database_url)
    import db_connection
    return db_connection


def test_sqlite_placeholder(monkeypatch, tmp_path):
    mod = _get_module(monkeypatch, "")
    monkeypatch.setattr("config.DATABASE_PATH", str(tmp_path / "t.db"))
    conn = mod.get_conn()
    conn.execute("CREATE TABLE t (x TEXT)")
    conn.execute("INSERT INTO t VALUES (%s)", ("hello",))
    conn.commit()
    row = conn.execute("SELECT x FROM t").fetchone()
    conn.close()
    assert row["x"] == "hello"


def test_sqlite_fetchall(monkeypatch, tmp_path):
    mod = _get_module(monkeypatch, "")
    monkeypatch.setattr("config.DATABASE_PATH", str(tmp_path / "t2.db"))
    conn = mod.get_conn()
    conn.execute("CREATE TABLE t (x TEXT)")
    conn.execute("INSERT INTO t VALUES (%s)", ("a",))
    conn.execute("INSERT INTO t VALUES (%s)", ("b",))
    conn.commit()
    rows = conn.execute("SELECT x FROM t ORDER BY x").fetchall()
    conn.close()
    assert [r["x"] for r in rows] == ["a", "b"]


def test_sqlite_fetchone_none(monkeypatch, tmp_path):
    mod = _get_module(monkeypatch, "")
    monkeypatch.setattr("config.DATABASE_PATH", str(tmp_path / "t3.db"))
    conn = mod.get_conn()
    conn.execute("CREATE TABLE t (x TEXT)")
    conn.commit()
    row = conn.execute("SELECT x FROM t").fetchone()
    conn.close()
    assert row is None


def test_is_postgres_false_by_default(monkeypatch):
    mod = _get_module(monkeypatch, "")
    assert mod.IS_POSTGRES is False


def test_is_postgres_true_for_pg_url(monkeypatch):
    mod = _get_module(monkeypatch, "postgresql://u:p@localhost/db")
    assert mod.IS_POSTGRES is True
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_db_connection.py -v
```

Expected: `ModuleNotFoundError: No module named 'db_connection'`

- [ ] **Step 3: Create db_connection.py**

```python
# db_connection.py
"""
Database driver abstraction.

Provides get_conn() returning a connection that:
  - accepts %s placeholders in all execute() calls
  - returns rows as plain dicts from fetchone() / fetchall()
  - works with both SQLite (development/test) and PostgreSQL (production)

Set DATABASE_URL to a postgresql:// URI to use PostgreSQL.
Leave it blank (or set DATABASE_PATH) for SQLite.
"""
import sqlite3
from config import DATABASE_PATH, DATABASE_URL

IS_POSTGRES = DATABASE_URL.startswith("postgresql") or DATABASE_URL.startswith("postgres")


# ── SQLite compat layer ───────────────────────────────────────────────────────

class _SQLiteCursor:
    """Wraps sqlite3.Cursor; converts %s → ? and returns rows as dicts."""

    def __init__(self, raw):
        self._raw = raw

    def fetchone(self):
        row = self._raw.fetchone()
        return dict(row) if row is not None else None

    def fetchall(self):
        return [dict(r) for r in self._raw.fetchall()]

    @property
    def lastrowid(self):
        return self._raw.lastrowid

    @property
    def rowcount(self):
        return self._raw.rowcount


class _SQLiteConn:
    """Wraps sqlite3.Connection; accepts %s placeholders."""

    def __init__(self, path):
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")

    def execute(self, sql, params=()):
        return _SQLiteCursor(self._conn.execute(sql.replace("%s", "?"), params))

    def executemany(self, sql, seq):
        self._conn.executemany(sql.replace("%s", "?"), seq)

    def executescript(self, script):
        return self._conn.executescript(script)

    # sqlite3-specific: used by init_db() migrations only
    def execute_raw(self, sql, params=()):
        """Execute without placeholder conversion — for PRAGMA statements."""
        return self._conn.execute(sql, params)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


# ── PostgreSQL layer ──────────────────────────────────────────────────────────

class _PGConn:
    """Wraps psycopg2 connection; rows returned as dicts via RealDictCursor."""

    def __init__(self, url):
        import psycopg2
        import psycopg2.extras
        self._psycopg2 = psycopg2
        self._extras = psycopg2.extras
        self._conn = psycopg2.connect(url)
        self._conn.autocommit = False

    def execute(self, sql, params=()):
        cur = self._conn.cursor(cursor_factory=self._extras.RealDictCursor)
        cur.execute(sql, params if params else None)
        return cur

    def executemany(self, sql, seq):
        cur = self._conn.cursor()
        cur.executemany(sql, seq)

    def executescript(self, script):
        """Split on ; and execute each statement individually."""
        cur = self._conn.cursor()
        for stmt in script.split(";"):
            stmt = stmt.strip()
            if stmt:
                cur.execute(stmt)

    def execute_raw(self, sql, params=()):
        """Same as execute() — exists for SQLite API compatibility."""
        return self.execute(sql, params)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


# ── Public factory ────────────────────────────────────────────────────────────

def get_conn():
    if IS_POSTGRES:
        return _PGConn(DATABASE_URL)
    return _SQLiteConn(DATABASE_PATH)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_db_connection.py -v
```

Expected: PASS (5 tests)

- [ ] **Step 5: Verify no regressions**

```bash
pytest --tb=short -q
```

Expected: same pass count as before.

- [ ] **Step 6: Commit**

```bash
git add db_connection.py tests/test_db_connection.py
git commit -m "feat: add db_connection abstraction for SQLite/PostgreSQL"
```

---

## Task 4: Update db.py to use db_connection.py

**Files:**
- Modify: `db.py`

This task has three mechanical changes:
1. Replace `import sqlite3` and `_connect()` with imports from `db_connection`.
2. Replace `?` with `%s` throughout (the compat wrapper converts back for SQLite).
3. Split `init_db()` so the SQLite-specific PRAGMA migrations run only on SQLite; PostgreSQL gets a clean CREATE TABLE path.

- [ ] **Step 1: Run the existing test suite to record the baseline**

```bash
pytest --tb=short -q 2>&1 | tail -5
```

Note the pass/fail count. Every test must still pass after this task.

- [ ] **Step 2: Replace the import block and _connect() at the top of db.py**

Find:
```python
import json
import sqlite3
import uuid
import secrets
import string
from collections import defaultdict
from config import DATABASE_PATH


def _connect():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
```

Replace with:
```python
import json
import uuid
import secrets
import string
from collections import defaultdict
from db_connection import get_conn, IS_POSTGRES


def _connect():
    return get_conn()
```

- [ ] **Step 3: Replace all `?` placeholders with `%s` in db.py**

```bash
cd /Users/douglasyu/src/Cowork/essay-coach
# Preview the count first
grep -c '"?' db.py || grep -c "'?" db.py
# Replace
sed -i '' "s/\", ?/\", %s/g; s/', ?/', %s/g; s/(?)/(%%s)/g" db.py
```

That sed approach is fragile. Do it properly with Python:

```bash
python3 - << 'EOF'
import re

with open("db.py") as f:
    src = f.read()

# Replace ? placeholders in SQL strings.
# Strategy: replace ?, ) and ?, with %s), %s, etc. - covers all parameter patterns.
# We only want to replace ? that are SQL placeholders, not in comments.
# A safe heuristic: replace ?, and ?) and ? at end of string literal.
result = src.replace(", ?)", ", %s)") \
            .replace(", ?,", ", %s,") \
            .replace("(?)", "(%s)") \
            .replace("(?, ", "(%s, ") \
            .replace(", ?, ", ", %s, ") \
            .replace("= ?", "= %s") \
            .replace("= ?,", "= %s,") \
            .replace("= ?)", "= %s)")

with open("db.py", "w") as f:
    f.write(result)
print("Done")
EOF
```

Then manually verify with:
```bash
grep -n "\b?\b" db.py | grep -v "^#" | grep -v "sqlite"
```

Any remaining `?` that are SQL placeholders should be changed to `%s` manually.

- [ ] **Step 4: Split init_db() for PostgreSQL vs SQLite**

In `db.py`, find the `init_db()` function. After the `executescript(...)` block and before the SQLite migration code (the PRAGMA table_info blocks), add a guard:

```python
def init_db():
    conn = _connect()
    if IS_POSTGRES:
        _init_db_postgres(conn)
    else:
        _init_db_sqlite(conn)
    conn.close()
```

Extract the existing `init_db()` body into `_init_db_sqlite(conn)` (unchanged).

Add a new `_init_db_postgres(conn)` function immediately above `init_db()`:

```python
def _init_db_postgres(conn):
    """Fresh PostgreSQL schema — no PRAGMA, no migration guards needed."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            expires_at TIMESTAMP NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
        CREATE TABLE IF NOT EXISTS student_users (
            id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS student_sessions (
            token TEXT PRIMARY KEY,
            student_id TEXT NOT NULL REFERENCES student_users(id) ON DELETE CASCADE,
            expires_at TIMESTAMP NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_student_sessions_student_id ON student_sessions(student_id);
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS classes (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            student_code TEXT UNIQUE NOT NULL,
            instructor_code TEXT UNIQUE NOT NULL,
            created_by TEXT REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMP DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS class_members (
            class_id TEXT NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            joined_at TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY (class_id, user_id)
        );
        CREATE INDEX IF NOT EXISTS idx_class_members_user_id ON class_members(user_id);
        CREATE TABLE IF NOT EXISTS questions (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            prompt TEXT NOT NULL,
            model_answer TEXT NOT NULL,
            rubric TEXT,
            class_id TEXT NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
            created_at TIMESTAMP DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS student_question_sessions (
            id TEXT PRIMARY KEY,
            student_id TEXT NOT NULL REFERENCES student_users(id) ON DELETE CASCADE,
            question_id TEXT NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
            session_number INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(student_id, question_id, session_number)
        );
        CREATE TABLE IF NOT EXISTS attempts (
            id TEXT PRIMARY KEY,
            question_id TEXT REFERENCES questions(id) ON DELETE CASCADE,
            session_id TEXT NOT NULL,
            student_answer TEXT NOT NULL,
            feedback TEXT,
            attempt_number INTEGER NOT NULL,
            score_data TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        );
        DELETE FROM sessions WHERE expires_at < NOW()
    """)
    conn.commit()
```

- [ ] **Step 5: Run the existing test suite**

```bash
pytest --tb=short -q
```

Expected: same pass count as the baseline recorded in Step 1. Fix any failures before proceeding.

- [ ] **Step 6: Commit**

```bash
git add db.py
git commit -m "feat: update db.py to use db_connection abstraction (PostgreSQL-compatible)"
```

---

## Task 5: Add Ollama backend to feedback.py

**Files:**
- Modify: `feedback.py`
- Create: `tests/test_ollama_feedback.py`

Ollama exposes an OpenAI-compatible `/v1/chat/completions` endpoint. We use `httpx` to call it directly, keeping the same async streaming interface as the Anthropic path.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_ollama_feedback.py
import json
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sse_lines(text_chunks):
    """Build the raw SSE bytes that Ollama streams back."""
    lines = []
    for chunk in text_chunks:
        payload = {"choices": [{"delta": {"content": chunk}, "finish_reason": None}]}
        lines.append(f"data: {json.dumps(payload)}\n\n")
    lines.append("data: [DONE]\n\n")
    return "".join(lines).encode()


def _score_response(score_dict):
    return {
        "choices": [{"message": {"content": json.dumps(score_dict)}}]
    }


# ── generate_feedback_stream (ollama path) ────────────────────────────────────

@pytest.mark.asyncio
async def test_ollama_feedback_stream_yields_text(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "ollama")

    import sys
    for k in list(sys.modules):
        if k in ("feedback", "config"):
            del sys.modules[k]
    from feedback import generate_feedback_stream

    sse_bytes = _sse_lines(["Hello", " world"])

    async def mock_aiter_lines():
        for line in sse_bytes.decode().splitlines():
            if line:
                yield line

    mock_response = MagicMock()
    mock_response.aiter_lines = mock_aiter_lines
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)

    mock_client = MagicMock()
    mock_client.stream = MagicMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_client):
        chunks = []
        async for chunk in generate_feedback_stream("Q", "A", None, "S", 1):
            chunks.append(chunk)

    assert chunks == ["Hello", " world"]


@pytest.mark.asyncio
async def test_ollama_feedback_stream_skips_done(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "ollama")

    import sys
    for k in list(sys.modules):
        if k in ("feedback", "config"):
            del sys.modules[k]
    from feedback import generate_feedback_stream

    sse_bytes = _sse_lines(["only chunk"])

    async def mock_aiter_lines():
        for line in sse_bytes.decode().splitlines():
            if line:
                yield line

    mock_response = MagicMock()
    mock_response.aiter_lines = mock_aiter_lines
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)
    mock_client = MagicMock()
    mock_client.stream = MagicMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_client):
        chunks = []
        async for chunk in generate_feedback_stream("Q", "A", None, "S", 1):
            chunks.append(chunk)

    assert "[DONE]" not in "".join(chunks)
    assert chunks == ["only chunk"]


# ── generate_score (ollama path) ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ollama_score_returns_valid_score(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "ollama")

    import sys
    for k in list(sys.modules):
        if k in ("feedback", "config"):
            del sys.modules[k]
    from feedback import generate_score, parse_scored_paragraphs

    score = {
        "breakdown": [{"label": "Topic A", "awarded": 2, "max": 3}],
        "total_awarded": 2,
        "total_max": 3,
    }
    paragraphs = parse_scored_paragraphs("Key concept [3]")

    mock_response = MagicMock()
    mock_response.json = MagicMock(return_value=_score_response(score))
    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await generate_score(paragraphs, "student answer", 1)

    assert result == score


@pytest.mark.asyncio
async def test_ollama_score_returns_none_on_invalid_json(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "ollama")

    import sys
    for k in list(sys.modules):
        if k in ("feedback", "config"):
            del sys.modules[k]
    from feedback import generate_score, parse_scored_paragraphs

    paragraphs = parse_scored_paragraphs("Key concept [3]")

    mock_response = MagicMock()
    mock_response.json = MagicMock(return_value={"choices": [{"message": {"content": "not json"}}]})
    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await generate_score(paragraphs, "student answer", 1)

    assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_ollama_feedback.py -v
```

Expected: failures because `generate_feedback_stream` and `generate_score` don't have an Ollama path yet.

- [ ] **Step 3: Add the Ollama path to feedback.py**

At the top of `feedback.py`, add the import:

```python
import httpx
from config import ANTHROPIC_API_KEY, MODEL_NAME, LLM_BACKEND, OLLAMA_BASE_URL, OLLAMA_MODEL
```

(Replace the existing `from config import ANTHROPIC_API_KEY, MODEL_NAME` line.)

Add these two private functions before `generate_feedback_stream`:

```python
async def _ollama_feedback_stream(messages, system_prompt):
    """Stream feedback from Ollama's OpenAI-compatible endpoint."""
    payload = {
        "model": OLLAMA_MODEL,
        "stream": True,
        "max_tokens": 2048,
        "messages": [{"role": "system", "content": system_prompt}] + messages,
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream(
            "POST",
            f"{OLLAMA_BASE_URL}/v1/chat/completions",
            json=payload,
            headers={"Authorization": "Bearer ollama"},
        ) as response:
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                payload_str = line[6:]
                if payload_str.strip() == "[DONE]":
                    break
                chunk = json.loads(payload_str)
                delta = chunk["choices"][0]["delta"].get("content", "")
                if delta:
                    yield delta


async def _ollama_score(user_message, system_prompt):
    """Request a JSON score from Ollama (non-streaming)."""
    payload = {
        "model": OLLAMA_MODEL,
        "stream": False,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{OLLAMA_BASE_URL}/v1/chat/completions",
            json=payload,
            headers={"Authorization": "Bearer ollama"},
        )
    return response.json()["choices"][0]["message"]["content"].strip()
```

Replace the body of `generate_feedback_stream` so it dispatches on `LLM_BACKEND`:

```python
async def generate_feedback_stream(
    question_prompt, model_answer, rubric, student_answer, attempt_number, previous_feedback=None
):
    messages = build_messages(
        question_prompt, model_answer, rubric, student_answer, attempt_number, previous_feedback
    )
    if LLM_BACKEND == "ollama":
        async for chunk in _ollama_feedback_stream(messages, SYSTEM_PROMPT):
            yield chunk
        return

    # Anthropic path (default)
    client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    async with client.messages.stream(
        model=MODEL_NAME,
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=messages,
    ) as stream:
        async for text in stream.text_stream:
            yield text
```

Replace the body of `generate_score` so it dispatches on `LLM_BACKEND`:

```python
async def generate_score(paragraphs: list[dict], student_answer: str, attempt_number: int) -> dict | None:
    """Score a student answer against scored paragraphs. Returns score dict or None on failure."""
    scored = [p for p in paragraphs if p["points"] is not None]
    if not scored:
        return None

    sections_xml = "\n".join(
        f'  <section index="{i + 1}" max="{p["points"]}">{p["text"]}</section>'
        for i, p in enumerate(scored)
    )
    user_message = (
        f"<sections>\n{sections_xml}\n</sections>\n"
        f'<student_answer attempt="{attempt_number}">{student_answer}</student_answer>'
    )

    try:
        if LLM_BACKEND == "ollama":
            raw = await _ollama_score(user_message, SCORING_SYSTEM_PROMPT)
        else:
            # Anthropic path (default)
            client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
            response = await client.messages.create(
                model=MODEL_NAME,
                max_tokens=1024,
                system=SCORING_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            )
            raw = response.content[0].text.strip()

        data = json.loads(raw)
        if validate_score(data, paragraphs):
            return data
        return None
    except Exception:
        return None
```

- [ ] **Step 4: Run the new Ollama tests**

```bash
pytest tests/test_ollama_feedback.py -v
```

Expected: PASS (4 tests)

- [ ] **Step 5: Run the full test suite**

```bash
pytest --tb=short -q
```

Expected: no regressions. All previously passing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add feedback.py tests/test_ollama_feedback.py
git commit -m "feat: add Ollama LLM backend to feedback.py (switchable via LLM_BACKEND)"
```

---

## Task 6: Create the Docker files

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `nginx.conf`

No automated tests for this task — correctness is verified in Task 8.

- [ ] **Step 1: Create Dockerfile**

```dockerfile
# Dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for psycopg2-binary
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Create docker-compose.yml**

```yaml
# docker-compose.yml
services:

  app:
    build: .
    env_file: .env
    depends_on:
      db:
        condition: service_healthy
    restart: unless-stopped
    # Port not exposed directly — nginx proxies to it
    expose:
      - "8000"

  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: essay_coach
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d essay_coach"]
      interval: 5s
      timeout: 5s
      retries: 10
    restart: unless-stopped

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro
      # IT team mounts the university TLS cert here:
      - /etc/ssl/essay-coach:/etc/ssl/essay-coach:ro
    depends_on:
      - app
    restart: unless-stopped

  # Ollama — only started when the "ollama" profile is active:
  #   docker compose --profile ollama up -d
  ollama:
    image: ollama/ollama
    profiles:
      - ollama
    volumes:
      - ollama_data:/root/.ollama
    restart: unless-stopped
    # Add GPU access if available on the host:
    # deploy:
    #   resources:
    #     reservations:
    #       devices:
    #         - driver: nvidia
    #           count: all
    #           capabilities: [gpu]

volumes:
  pgdata:
  ollama_data:
```

- [ ] **Step 3: Create nginx.conf**

```nginx
# nginx.conf
# Rate-limiting zone — defined at http level via this include file.
# Limits /api/feedback to 20 requests/minute per IP.
limit_req_zone $binary_remote_addr zone=feedback:10m rate=20r/m;

server {
    listen 80;
    server_name _;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name _;

    ssl_certificate     /etc/ssl/essay-coach/cert.pem;
    ssl_certificate_key /etc/ssl/essay-coach/key.pem;

    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;

    # Serve static files directly from the container's filesystem.
    # Mount the static directory, or let nginx proxy these too (simpler for now).
    location /static/ {
        proxy_pass http://app:8000/static/;
    }

    # Rate-limited feedback endpoint (SSE — requires buffering off).
    location /api/feedback {
        limit_req zone=feedback burst=5 nodelay;

        proxy_pass         http://app:8000;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;

        # SSE requires these:
        proxy_buffering    off;
        proxy_cache        off;
        proxy_read_timeout 300s;
    }

    # All other routes.
    location / {
        proxy_pass         http://app:8000;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }
}
```

- [ ] **Step 4: Add .dockerignore**

```bash
cat > .dockerignore << 'EOF'
.env
*.db
__pycache__
.pytest_cache
.git
docs/
*.md
EOF
```

- [ ] **Step 5: Commit**

```bash
git add Dockerfile docker-compose.yml nginx.conf .dockerignore
git commit -m "feat: add Dockerfile, docker-compose.yml, and nginx.conf"
```

---

## Task 7: Create the SQLite → PostgreSQL migration script

**Files:**
- Create: `scripts/migrate_to_postgres.py`

This is a one-time script run on the server before go-live. It reads all rows from the existing SQLite database and inserts them into the freshly initialised PostgreSQL database (already created by `init_db()` on first app startup).

- [ ] **Step 1: Create the scripts directory**

```bash
mkdir -p scripts
```

- [ ] **Step 2: Create scripts/migrate_to_postgres.py**

```python
#!/usr/bin/env python3
"""
One-time migration: SQLite → PostgreSQL

Usage:
    SQLITE_PATH=/path/to/essay_coach.db \
    DATABASE_URL=postgresql://essay_coach:password@localhost:5432/essay_coach \
    python scripts/migrate_to_postgres.py

Run AFTER `docker compose up -d` has started the app once
(so that init_db() has already created the PostgreSQL schema).
"""
import os
import sqlite3
import json
import sys

import psycopg2

SQLITE_PATH = os.environ.get("SQLITE_PATH")
DATABASE_URL = os.environ.get("DATABASE_URL")

if not SQLITE_PATH or not DATABASE_URL:
    print("ERROR: Set SQLITE_PATH and DATABASE_URL environment variables.")
    sys.exit(1)

# Tables must be inserted in this order to satisfy foreign key constraints.
TABLES = [
    "users",
    "sessions",
    "settings",
    "student_users",
    "student_sessions",
    "classes",
    "class_members",
    "questions",
    "student_question_sessions",
    "attempts",
]


def migrate():
    src = sqlite3.connect(SQLITE_PATH)
    src.row_factory = sqlite3.Row
    dst = psycopg2.connect(DATABASE_URL)
    dst.autocommit = False

    try:
        cur = dst.cursor()
        for table in TABLES:
            rows = src.execute(f"SELECT * FROM {table}").fetchall()
            if not rows:
                print(f"  {table}: 0 rows — skipped")
                continue

            row_dicts = [dict(r) for r in rows]
            cols = list(row_dicts[0].keys())
            col_names = ", ".join(cols)
            placeholders = ", ".join(["%s"] * len(cols))
            values = [tuple(r[c] for c in cols) for r in row_dicts]

            cur.executemany(
                f"INSERT INTO {table} ({col_names}) VALUES ({placeholders}) ON CONFLICT DO NOTHING",
                values,
            )
            print(f"  {table}: {len(values)} rows migrated")

        dst.commit()
        print("\nMigration complete.")
    except Exception as exc:
        dst.rollback()
        print(f"\nMigration FAILED: {exc}")
        raise
    finally:
        src.close()
        dst.close()


if __name__ == "__main__":
    migrate()
```

- [ ] **Step 3: Make it executable**

```bash
chmod +x scripts/migrate_to_postgres.py
```

- [ ] **Step 4: Dry-run against a local PostgreSQL (if available)**

```bash
# Start a throwaway postgres to test the script
docker run --rm -d \
  --name pg_test \
  -e POSTGRES_USER=essay_coach \
  -e POSTGRES_PASSWORD=testpass \
  -e POSTGRES_DB=essay_coach \
  -p 5433:5432 \
  postgres:16-alpine

# Wait for it to be ready
sleep 3

# Run the app briefly to create the schema, then stop it
DATABASE_URL=postgresql://essay_coach:testpass@localhost:5433/essay_coach \
  python -c "import db; db.init_db(); print('Schema created')"

# Run the migration against the existing SQLite file
SQLITE_PATH=essay_coach.db \
DATABASE_URL=postgresql://essay_coach:testpass@localhost:5433/essay_coach \
  python scripts/migrate_to_postgres.py

# Verify row counts match
docker exec pg_test psql -U essay_coach -d essay_coach -c "\dt"

# Clean up
docker stop pg_test
```

Expected: all tables listed, row counts matching your SQLite database.

- [ ] **Step 5: Commit**

```bash
git add scripts/migrate_to_postgres.py
git commit -m "feat: add SQLite to PostgreSQL one-time migration script"
```

---

## Task 8: Run the full test suite against PostgreSQL

**Files:**
- No new files — this is a verification task.

- [ ] **Step 1: Start a local PostgreSQL container**

```bash
docker run --rm -d \
  --name pg_ci \
  -e POSTGRES_USER=essay_coach \
  -e POSTGRES_PASSWORD=testpass \
  -e POSTGRES_DB=essay_coach \
  -p 5433:5432 \
  postgres:16-alpine

# Wait for readiness
until docker exec pg_ci pg_isready -U essay_coach -d essay_coach; do sleep 1; done
```

- [ ] **Step 2: Run the test suite with DATABASE_URL set**

```bash
DATABASE_URL=postgresql://essay_coach:testpass@localhost:5433/essay_coach \
  pytest --tb=short -q
```

Expected: same pass count as the SQLite run. Any failures indicate a SQL compatibility issue introduced in Task 4 — fix in `db.py` before proceeding.

- [ ] **Step 3: Run the test suite with SQLite to confirm no regression**

```bash
pytest --tb=short -q
```

Expected: same pass count as PostgreSQL run.

- [ ] **Step 4: Smoke-test the Docker Compose stack locally**

```bash
# Copy .env.example to .env and fill in values
cp .env.example .env
# Edit .env: set POSTGRES_USER=essay_coach, POSTGRES_PASSWORD=testpass,
#            DATABASE_URL=postgresql://essay_coach:testpass@db:5432/essay_coach
#            LLM_BACKEND=anthropic, ANTHROPIC_API_KEY=<your key>

docker compose up -d --build
sleep 5

# Check all containers are healthy
docker compose ps

# Hit the app
curl -s http://localhost/  # Should return HTML (nginx proxies to app on :80 → :443 redirect)
# Or if no TLS cert locally, test on port 8000 directly:
docker compose exec app curl -s http://localhost:8000/ | head -5

docker compose logs app | tail -20
```

Expected: no error logs, app returns HTML.

- [ ] **Step 5: Stop the test containers**

```bash
docker compose down
docker stop pg_ci
```

- [ ] **Step 6: Commit the final state**

```bash
git add -A
git status   # confirm only expected files staged
git commit -m "chore: verify full test suite passes against PostgreSQL — pre-launch ready"
```

---

## Summary

| Task | Outcome |
|---|---|
| 1 | `config.py` exposes `LLM_BACKEND`, `OLLAMA_*`, `DATABASE_URL`; `.env.example` documents every variable |
| 2 | `psycopg2-binary` and `httpx` in `requirements.txt` |
| 3 | `db_connection.py` — driver abstraction; SQLite and PostgreSQL interchangeable |
| 4 | `db.py` uses `db_connection`; PostgreSQL `init_db` path added; `?` → `%s` throughout |
| 5 | `feedback.py` routes to Anthropic or Ollama via `LLM_BACKEND`; 4 new unit tests |
| 6 | `Dockerfile`, `docker-compose.yml`, `nginx.conf`, `.dockerignore` |
| 7 | `scripts/migrate_to_postgres.py` — one-time SQLite → PostgreSQL data transfer |
| 8 | Full test suite green on both SQLite and PostgreSQL; Docker Compose stack smoke-tested |
