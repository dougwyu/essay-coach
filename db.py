import json
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
        CREATE TABLE IF NOT EXISTS classes (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            student_code TEXT UNIQUE NOT NULL,
            instructor_code TEXT UNIQUE NOT NULL,
            created_by TEXT REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS class_members (
            class_id TEXT NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
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

    # Add class_id column to questions if it doesn't exist yet (migration for pre-Phase-3 DBs)
    existing_cols = [
        r[1] for r in conn.execute("PRAGMA table_info(questions)").fetchall()
    ]
    if "class_id" not in existing_cols:
        conn.execute(
            "ALTER TABLE questions ADD COLUMN class_id TEXT REFERENCES classes(id) ON DELETE CASCADE"
        )
        conn.commit()

    # Migration: assign orphaned questions to a Default class
    orphan_count = conn.execute(
        "SELECT COUNT(*) FROM questions WHERE class_id IS NULL"
    ).fetchone()[0]
    if orphan_count > 0:
        s_code = "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
        i_code = "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
        default_id = str(uuid.uuid4())
        # Use first user (by created_at) as creator if any exist
        first_user = conn.execute(
            "SELECT id FROM users ORDER BY created_at ASC LIMIT 1"
        ).fetchone()
        created_by = first_user[0] if first_user else None
        conn.execute(
            "INSERT INTO classes (id, name, student_code, instructor_code, created_by) VALUES (?, ?, ?, ?, ?)",
            (default_id, "Default", s_code, i_code, created_by),
        )
        conn.execute(
            "UPDATE questions SET class_id = ? WHERE class_id IS NULL", (default_id,)
        )
        if created_by:
            conn.execute(
                "INSERT OR IGNORE INTO class_members (class_id, user_id) VALUES (?, ?)",
                (default_id, created_by),
            )
        conn.commit()

    # Add score_data column to attempts if not present (migration for pre-scoring DBs)
    attempt_cols = [
        r[1] for r in conn.execute("PRAGMA table_info(attempts)").fetchall()
    ]
    if "score_data" not in attempt_cols:
        conn.execute("ALTER TABLE attempts ADD COLUMN score_data TEXT")
        conn.commit()

    # Seed invite code
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


def create_question(title, prompt, model_answer, rubric, class_id):
    qid = str(uuid.uuid4())
    conn = _connect()
    conn.execute(
        "INSERT INTO questions (id, title, prompt, model_answer, rubric, class_id) VALUES (?, ?, ?, ?, ?, ?)",
        (qid, title, prompt, model_answer, rubric, class_id),
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
    allowed = {"title", "prompt", "model_answer", "rubric", "class_id"}
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


def create_attempt(question_id, session_id, student_answer, feedback, attempt_number, score_data=None):
    aid = str(uuid.uuid4())
    score_json = json.dumps(score_data) if score_data is not None else None
    conn = _connect()
    conn.execute(
        "INSERT INTO attempts (id, question_id, session_id, student_answer, feedback, attempt_number, score_data)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (aid, question_id, session_id, student_answer, feedback, attempt_number, score_json),
    )
    conn.commit()
    conn.close()
    return aid


def update_attempt_score(attempt_id: str, score_data: dict) -> None:
    score_json = json.dumps(score_data)
    conn = _connect()
    conn.execute(
        "UPDATE attempts SET score_data = ? WHERE id = ?",
        (score_json, attempt_id),
    )
    conn.commit()
    conn.close()


def get_attempts(question_id, session_id):
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM attempts WHERE question_id = ? AND session_id = ? ORDER BY attempt_number DESC",
        (question_id, session_id),
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        if d.get("score_data"):
            d["score_data"] = json.loads(d["score_data"])
        result.append(d)
    return result


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


# --- classes ---

def create_class(name: str, student_code: str, instructor_code: str, created_by: str | None) -> str:
    cid = str(uuid.uuid4())
    conn = _connect()
    conn.execute(
        "INSERT INTO classes (id, name, student_code, instructor_code, created_by) VALUES (?, ?, ?, ?, ?)",
        (cid, name, student_code, instructor_code, created_by),
    )
    conn.commit()
    conn.close()
    return cid


def get_class(class_id: str) -> dict | None:
    conn = _connect()
    row = conn.execute("SELECT * FROM classes WHERE id = ?", (class_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_class_by_student_code(code: str) -> dict | None:
    conn = _connect()
    row = conn.execute("SELECT * FROM classes WHERE student_code = ?", (code,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_class_by_instructor_code(code: str) -> dict | None:
    conn = _connect()
    row = conn.execute("SELECT * FROM classes WHERE instructor_code = ?", (code,)).fetchone()
    conn.close()
    return dict(row) if row else None


def list_classes_for_user(user_id: str) -> list[dict]:
    conn = _connect()
    rows = conn.execute(
        """SELECT c.* FROM classes c
           JOIN class_members m ON c.id = m.class_id
           WHERE m.user_id = ?
           ORDER BY c.created_at ASC""",
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_class_member(class_id: str, user_id: str) -> None:
    conn = _connect()
    conn.execute(
        "INSERT OR IGNORE INTO class_members (class_id, user_id) VALUES (?, ?)",
        (class_id, user_id),
    )
    conn.commit()
    conn.close()


def is_class_member(class_id: str, user_id: str) -> bool:
    conn = _connect()
    row = conn.execute(
        "SELECT 1 FROM class_members WHERE class_id = ? AND user_id = ?",
        (class_id, user_id),
    ).fetchone()
    conn.close()
    return row is not None


def get_class_question_count(class_id: str) -> int:
    conn = _connect()
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM questions WHERE class_id = ?", (class_id,)
    ).fetchone()
    conn.close()
    return row["cnt"]


def update_class_student_code(class_id: str, new_code: str) -> None:
    conn = _connect()
    conn.execute(
        "UPDATE classes SET student_code = ? WHERE id = ?", (new_code, class_id)
    )
    conn.commit()
    conn.close()


def update_class_instructor_code(class_id: str, new_code: str) -> None:
    conn = _connect()
    conn.execute(
        "UPDATE classes SET instructor_code = ? WHERE id = ?", (new_code, class_id)
    )
    conn.commit()
    conn.close()


def list_questions_for_class(class_id: str) -> list[dict]:
    """Return all questions belonging to a class, newest first."""
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM questions WHERE class_id = ? ORDER BY created_at DESC", (class_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def list_questions_for_user(user_id: str) -> list[dict]:
    """Return all questions in classes this user is a member of."""
    conn = _connect()
    rows = conn.execute(
        """SELECT q.* FROM questions q
           JOIN class_members m ON q.class_id = m.class_id
           WHERE m.user_id = ?
           ORDER BY q.created_at ASC""",
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
