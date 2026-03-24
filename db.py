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
