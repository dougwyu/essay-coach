import sqlite3
import uuid
import secrets
import string
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
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            expires_at TIMESTAMP NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        DELETE FROM sessions WHERE expires_at < datetime('now');
    """)
    row = conn.execute(
        "SELECT value FROM settings WHERE key = 'invite_code'"
    ).fetchone()
    if not row:
        alphabet = string.ascii_uppercase + string.digits
        code = "".join(secrets.choice(alphabet) for _ in range(8))
        conn.execute(
            "INSERT INTO settings (key, value) VALUES ('invite_code', ?)", (code,)
        )
    conn.commit()
    conn.close()


def create_question(title, prompt, model_answer, rubric):
    qid = str(uuid.uuid4())
    conn = _connect()
    conn.execute(
        "INSERT INTO questions (id, title, prompt, model_answer, rubric) VALUES (?, ?, ?, ?, ?)",
        (qid, title, prompt, model_answer, rubric),
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
        (aid, question_id, session_id, student_answer, feedback, attempt_number),
    )
    conn.commit()
    conn.close()
    return aid


def get_attempts(question_id, session_id):
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM attempts WHERE question_id = ? AND session_id = ? ORDER BY attempt_number DESC",
        (question_id, session_id),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_attempt_count(question_id):
    conn = _connect()
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM attempts WHERE question_id = ?", (question_id,)
    ).fetchone()
    conn.close()
    return row["cnt"]


# --- users ---

def create_user(username: str, password_hash: str) -> str:
    uid = str(uuid.uuid4())
    conn = _connect()
    conn.execute(
        "INSERT INTO users (id, username, password_hash) VALUES (?, ?, ?)",
        (uid, username, password_hash),
    )
    conn.commit()
    conn.close()
    return uid


def get_user_by_username(username: str) -> dict | None:
    conn = _connect()
    row = conn.execute(
        "SELECT * FROM users WHERE username = ?", (username,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_id(user_id: str) -> dict | None:
    conn = _connect()
    row = conn.execute(
        "SELECT * FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


# --- sessions ---

def create_session(token: str, user_id: str, expires_at: str) -> None:
    conn = _connect()
    conn.execute(
        "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
        (token, user_id, expires_at),
    )
    conn.commit()
    conn.close()


def get_session(token: str) -> dict | None:
    """Return session if it exists and has not expired; None otherwise."""
    conn = _connect()
    row = conn.execute(
        "SELECT * FROM sessions WHERE token = ? AND expires_at > datetime('now')",
        (token,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def update_session_expiry(token: str, expires_at: str) -> None:
    conn = _connect()
    conn.execute(
        "UPDATE sessions SET expires_at = ? WHERE token = ?",
        (expires_at, token),
    )
    conn.commit()
    conn.close()


def delete_session(token: str) -> None:
    conn = _connect()
    conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
    conn.commit()
    conn.close()


def delete_sessions_for_user(user_id: str) -> None:
    conn = _connect()
    conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


# --- settings ---

def get_setting(key: str) -> str | None:
    conn = _connect()
    row = conn.execute(
        "SELECT value FROM settings WHERE key = ?", (key,)
    ).fetchone()
    conn.close()
    return row["value"] if row else None


def set_setting(key: str, value: str) -> None:
    conn = _connect()
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?)"
        " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()
    conn.close()
