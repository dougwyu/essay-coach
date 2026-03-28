import json
import uuid
import secrets
import string
from collections import defaultdict
from datetime import datetime, timezone
from db_connection import get_conn, IS_POSTGRES


def _connect():
    return get_conn()


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
    # Seed invite code
    row = conn.execute(
        "SELECT value FROM settings WHERE key = 'invite_code'"
    ).fetchone()
    if not row:
        alphabet = string.ascii_uppercase + string.digits
        code = "".join(secrets.choice(alphabet) for _ in range(8))
        conn.execute(
            "INSERT INTO settings (key, value) VALUES ('invite_code', %s)", (code,)
        )
    conn.commit()


def _init_db_sqlite(conn):
    """SQLite schema creation and incremental migrations."""
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
        CREATE TABLE IF NOT EXISTS student_users (
            id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS student_sessions (
            token TEXT PRIMARY KEY,
            student_id TEXT NOT NULL REFERENCES student_users(id) ON DELETE CASCADE,
            expires_at TIMESTAMP NOT NULL
        );
        CREATE TABLE IF NOT EXISTS student_question_sessions (
            id TEXT PRIMARY KEY,
            student_id TEXT NOT NULL REFERENCES student_users(id) ON DELETE CASCADE,
            question_id TEXT NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
            session_number INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(student_id, question_id, session_number)
        );
        DELETE FROM sessions WHERE expires_at < datetime('now');
    """)

    # Migration: add session_number to student_question_sessions (table rebuild required for SQLite)
    sq_cols = [r[1] for r in conn.execute_raw("PRAGMA table_info(student_question_sessions)").fetchall()]
    if "session_number" not in sq_cols:
        conn.execute_raw("PRAGMA foreign_keys = OFF")
        conn.execute("""
            CREATE TABLE student_question_sessions_new (
                id TEXT PRIMARY KEY,
                student_id TEXT NOT NULL REFERENCES student_users(id) ON DELETE CASCADE,
                question_id TEXT NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
                session_number INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(student_id, question_id, session_number)
            )
        """)
        conn.execute("""
            INSERT INTO student_question_sessions_new (id, student_id, question_id, session_number, created_at)
                SELECT id, student_id, question_id, 1, created_at FROM student_question_sessions
        """)
        conn.execute("DROP TABLE student_question_sessions")
        conn.execute("ALTER TABLE student_question_sessions_new RENAME TO student_question_sessions")
        conn.execute_raw("PRAGMA foreign_keys = ON")
        conn.commit()

    # Add class_id column to questions if it doesn't exist yet (migration for pre-Phase-3 DBs)
    existing_cols = [
        r[1] for r in conn.execute_raw("PRAGMA table_info(questions)").fetchall()
    ]
    if "class_id" not in existing_cols:
        conn.execute(
            "ALTER TABLE questions ADD COLUMN class_id TEXT REFERENCES classes(id) ON DELETE CASCADE"
        )
        conn.commit()

    # Migration: assign orphaned questions to a Default class
    orphan_count = conn.execute(
        "SELECT COUNT(*) AS cnt FROM questions WHERE class_id IS NULL"
    ).fetchone()["cnt"]
    if orphan_count > 0:
        s_code = "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
        i_code = "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
        default_id = str(uuid.uuid4())
        # Use first user (by created_at) as creator if any exist
        first_user = conn.execute(
            "SELECT id FROM users ORDER BY created_at ASC LIMIT 1"
        ).fetchone()
        created_by = first_user["id"] if first_user else None
        conn.execute(
            "INSERT INTO classes (id, name, student_code, instructor_code, created_by) VALUES (%s, %s, %s, %s, %s)",
            (default_id, "Default", s_code, i_code, created_by),
        )
        conn.execute(
            "UPDATE questions SET class_id = %s WHERE class_id IS NULL", (default_id,)
        )
        if created_by:
            conn.execute(
                "INSERT INTO class_members (class_id, user_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (default_id, created_by),
            )
        conn.commit()

    # Add score_data column to attempts if not present (migration for pre-scoring DBs)
    attempt_cols = [
        r[1] for r in conn.execute_raw("PRAGMA table_info(attempts)").fetchall()
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
            "INSERT INTO settings (key, value) VALUES ('invite_code', %s)", (code,)
        )
    conn.commit()


def init_db():
    conn = _connect()
    if IS_POSTGRES:
        _init_db_postgres(conn)
    else:
        _init_db_sqlite(conn)
    conn.close()


def create_question(title, prompt, model_answer, rubric, class_id):
    qid = str(uuid.uuid4())
    conn = _connect()
    conn.execute(
        "INSERT INTO questions (id, title, prompt, model_answer, rubric, class_id) VALUES (%s, %s, %s, %s, %s, %s)",
        (qid, title, prompt, model_answer, rubric, class_id),
    )
    conn.commit()
    conn.close()
    return qid


def get_question(question_id):
    conn = _connect()
    row = conn.execute("SELECT * FROM questions WHERE id = %s", (question_id,)).fetchone()
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
    set_clause = ", ".join(f"{k} = %s" for k in fields)
    values = list(fields.values()) + [question_id]
    conn = _connect()
    conn.execute(f"UPDATE questions SET {set_clause} WHERE id = %s", values)
    conn.commit()
    conn.close()


def delete_question(question_id):
    conn = _connect()
    conn.execute("DELETE FROM questions WHERE id = %s", (question_id,))
    conn.commit()
    conn.close()


def create_attempt(question_id, session_id, student_answer, feedback, attempt_number, score_data=None):
    aid = str(uuid.uuid4())
    score_json = json.dumps(score_data) if score_data is not None else None
    conn = _connect()
    conn.execute(
        "INSERT INTO attempts (id, question_id, session_id, student_answer, feedback, attempt_number, score_data)"
        " VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (aid, question_id, session_id, student_answer, feedback, attempt_number, score_json),
    )
    conn.commit()
    conn.close()
    return aid


def update_attempt_score(attempt_id: str, score_data: dict) -> None:
    score_json = json.dumps(score_data)
    conn = _connect()
    conn.execute(
        "UPDATE attempts SET score_data = %s WHERE id = %s",
        (score_json, attempt_id),
    )
    conn.commit()
    conn.close()


def get_attempts(question_id, session_id):
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM attempts WHERE question_id = %s AND session_id = %s ORDER BY attempt_number DESC",
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
        "SELECT COUNT(*) as cnt FROM attempts WHERE question_id = %s", (question_id,)
    ).fetchone()
    conn.close()
    return row["cnt"]


def delete_attempts_for_question(question_id):
    conn = _connect()
    conn.execute("DELETE FROM attempts WHERE question_id = %s", (question_id,))
    conn.commit()
    conn.close()


# --- users ---

def create_user(username: str, password_hash: str) -> str:
    uid = str(uuid.uuid4())
    conn = _connect()
    conn.execute(
        "INSERT INTO users (id, username, password_hash) VALUES (%s, %s, %s)",
        (uid, username, password_hash),
    )
    conn.commit()
    conn.close()
    return uid


def get_user_by_username(username: str) -> dict | None:
    conn = _connect()
    row = conn.execute(
        "SELECT * FROM users WHERE username = %s", (username,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_id(user_id: str) -> dict | None:
    conn = _connect()
    row = conn.execute(
        "SELECT * FROM users WHERE id = %s", (user_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


# --- sessions ---

def create_session(token: str, user_id: str, expires_at: str) -> None:
    conn = _connect()
    conn.execute(
        "INSERT INTO sessions (token, user_id, expires_at) VALUES (%s, %s, %s)",
        (token, user_id, expires_at),
    )
    conn.commit()
    conn.close()


def get_session(token: str) -> dict | None:
    """Return session if it exists and has not expired; None otherwise."""
    conn = _connect()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    row = conn.execute(
        "SELECT * FROM sessions WHERE token = %s AND expires_at > %s",
        (token, now),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def update_session_expiry(token: str, expires_at: str) -> None:
    conn = _connect()
    conn.execute(
        "UPDATE sessions SET expires_at = %s WHERE token = %s",
        (expires_at, token),
    )
    conn.commit()
    conn.close()


def delete_session(token: str) -> None:
    conn = _connect()
    conn.execute("DELETE FROM sessions WHERE token = %s", (token,))
    conn.commit()
    conn.close()


def delete_sessions_for_user(user_id: str) -> None:
    conn = _connect()
    conn.execute("DELETE FROM sessions WHERE user_id = %s", (user_id,))
    conn.commit()
    conn.close()


# --- settings ---

def get_setting(key: str) -> str | None:
    conn = _connect()
    row = conn.execute(
        "SELECT value FROM settings WHERE key = %s", (key,)
    ).fetchone()
    conn.close()
    return row["value"] if row else None


def set_setting(key: str, value: str) -> None:
    conn = _connect()
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (%s, %s)"
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
        "INSERT INTO classes (id, name, student_code, instructor_code, created_by) VALUES (%s, %s, %s, %s, %s)",
        (cid, name, student_code, instructor_code, created_by),
    )
    conn.commit()
    conn.close()
    return cid


def get_class(class_id: str) -> dict | None:
    conn = _connect()
    row = conn.execute("SELECT * FROM classes WHERE id = %s", (class_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_class_by_student_code(code: str) -> dict | None:
    conn = _connect()
    row = conn.execute("SELECT * FROM classes WHERE student_code = %s", (code,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_class_by_instructor_code(code: str) -> dict | None:
    conn = _connect()
    row = conn.execute("SELECT * FROM classes WHERE instructor_code = %s", (code,)).fetchone()
    conn.close()
    return dict(row) if row else None


def list_classes_for_user(user_id: str) -> list[dict]:
    conn = _connect()
    rows = conn.execute(
        """SELECT c.* FROM classes c
           JOIN class_members m ON c.id = m.class_id
           WHERE m.user_id = %s
           ORDER BY c.created_at ASC""",
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_class_member(class_id: str, user_id: str) -> None:
    conn = _connect()
    conn.execute(
        "INSERT INTO class_members (class_id, user_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
        (class_id, user_id),
    )
    conn.commit()
    conn.close()


def is_class_member(class_id: str, user_id: str) -> bool:
    conn = _connect()
    row = conn.execute(
        "SELECT 1 FROM class_members WHERE class_id = %s AND user_id = %s",
        (class_id, user_id),
    ).fetchone()
    conn.close()
    return row is not None


def get_class_question_count(class_id: str) -> int:
    conn = _connect()
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM questions WHERE class_id = %s", (class_id,)
    ).fetchone()
    conn.close()
    return row["cnt"]


def update_class_student_code(class_id: str, new_code: str) -> None:
    conn = _connect()
    conn.execute(
        "UPDATE classes SET student_code = %s WHERE id = %s", (new_code, class_id)
    )
    conn.commit()
    conn.close()


def update_class_instructor_code(class_id: str, new_code: str) -> None:
    conn = _connect()
    conn.execute(
        "UPDATE classes SET instructor_code = %s WHERE id = %s", (new_code, class_id)
    )
    conn.commit()
    conn.close()


def list_questions_for_class(class_id: str) -> list[dict]:
    """Return all questions belonging to a class, newest first."""
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM questions WHERE class_id = %s ORDER BY created_at DESC", (class_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def list_questions_for_user(user_id: str) -> list[dict]:
    """Return all questions in classes this user is a member of."""
    conn = _connect()
    rows = conn.execute(
        """SELECT q.* FROM questions q
           JOIN class_members m ON q.class_id = m.class_id
           WHERE m.user_id = %s
           ORDER BY q.created_at ASC""",
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_class_question_stats(class_id: str) -> list[dict]:
    conn = _connect()
    questions = conn.execute(
        "SELECT id, title FROM questions WHERE class_id = %s ORDER BY created_at ASC",
        (class_id,),
    ).fetchall()
    if not questions:
        conn.close()
        return []

    q_ids = [q["id"] for q in questions]
    placeholders = ",".join(["%s"] * len(q_ids))
    rows = conn.execute(
        f"SELECT * FROM attempts WHERE question_id IN ({placeholders}) ORDER BY question_id, session_id, attempt_number",
        q_ids,
    ).fetchall()
    conn.close()

    # group attempts by question_id then by session_id
    q_sessions: dict = defaultdict(lambda: defaultdict(list))
    for row in rows:
        d = dict(row)
        if d.get("score_data"):
            d["score_data"] = json.loads(d["score_data"])
        q_sessions[d["question_id"]][d["session_id"]].append(d)

    result = []
    for q in questions:
        qid = q["id"]
        sessions = q_sessions.get(qid, {})
        total_sessions = len(sessions)

        if total_sessions == 0:
            result.append({
                "question_id": qid,
                "title": q["title"],
                "total_sessions": 0,
                "avg_attempts": 0.0,
                "avg_final_score": None,
                "max_total": None,
                "score_buckets": None,
            })
            continue

        attempt_counts = []
        final_scores = []
        max_total = None
        buckets = {"low": 0, "mid": 0, "high": 0}

        for session_id, atts in sessions.items():
            attempt_counts.append(len(atts))
            last = atts[-1]
            sd = last.get("score_data")
            if sd:
                score = sd["total_awarded"]
                mt = sd["total_max"]
                final_scores.append(score)
                if max_total is None:
                    max_total = mt
                pct = score / mt
                if pct >= 0.70:
                    buckets["high"] += 1
                elif pct >= 0.40:
                    buckets["mid"] += 1
                else:
                    buckets["low"] += 1

        avg_attempts = sum(attempt_counts) / total_sessions
        avg_final_score = sum(final_scores) / len(final_scores) if final_scores else None
        score_buckets = buckets if final_scores else None

        result.append({
            "question_id": qid,
            "title": q["title"],
            "total_sessions": total_sessions,
            "avg_attempts": avg_attempts,
            "avg_final_score": avg_final_score,
            "max_total": max_total,
            "score_buckets": score_buckets,
        })

    return result


def get_question_session_stats(question_id: str) -> list[dict]:
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM attempts WHERE question_id = %s ORDER BY session_id, attempt_number",
        (question_id,),
    ).fetchall()
    conn.close()

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


# --- student users ---

def create_student_user(username: str, email: str, password_hash: str) -> str:
    uid = str(uuid.uuid4())
    conn = _connect()
    conn.execute(
        "INSERT INTO student_users (id, username, email, password_hash) VALUES (%s, %s, %s, %s)",
        (uid, username, email, password_hash),
    )
    conn.commit()
    conn.close()
    return uid


def get_student_by_username(username: str) -> dict | None:
    conn = _connect()
    row = conn.execute(
        "SELECT * FROM student_users WHERE username = %s", (username,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_student_by_email(email: str) -> dict | None:
    conn = _connect()
    row = conn.execute(
        "SELECT * FROM student_users WHERE email = %s", (email,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_student_by_id(student_id: str) -> dict | None:
    conn = _connect()
    row = conn.execute(
        "SELECT * FROM student_users WHERE id = %s", (student_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def create_student_session(token: str, student_id: str, expires_at: str) -> None:
    conn = _connect()
    conn.execute(
        "INSERT INTO student_sessions (token, student_id, expires_at) VALUES (%s, %s, %s)",
        (token, student_id, expires_at),
    )
    conn.commit()
    conn.close()


def get_student_session(token: str) -> dict | None:
    """Return session if it exists and has not expired; None otherwise."""
    conn = _connect()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    row = conn.execute(
        "SELECT * FROM student_sessions WHERE token = %s AND expires_at > %s",
        (token, now),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def update_student_session_expiry(token: str, expires_at: str) -> None:
    conn = _connect()
    conn.execute(
        "UPDATE student_sessions SET expires_at = %s WHERE token = %s",
        (expires_at, token),
    )
    conn.commit()
    conn.close()


def delete_student_session(token: str) -> None:
    conn = _connect()
    conn.execute("DELETE FROM student_sessions WHERE token = %s", (token,))
    conn.commit()
    conn.close()


def get_or_create_question_session(student_id: str, question_id: str) -> str:
    """Return the active (latest) session UUID for (student_id, question_id), creating session_number=1 if none exists.
    SQLite serialises all writes so SELECT-then-INSERT is safe within a single connection."""
    conn = _connect()
    row = conn.execute(
        "SELECT id FROM student_question_sessions WHERE student_id = %s AND question_id = %s"
        " ORDER BY session_number DESC LIMIT 1",
        (student_id, question_id),
    ).fetchone()
    if row:
        conn.close()
        return row["id"]
    sid = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO student_question_sessions (id, student_id, question_id, session_number)"
        " VALUES (%s, %s, %s, %s)",
        (sid, student_id, question_id, 1),
    )
    conn.commit()
    conn.close()
    return sid


def start_new_question_session(student_id: str, question_id: str) -> tuple[str, int]:
    """Create the next session for (student_id, question_id) and return (session_id, session_number).
    Assumes at least one session already exists for the pair; if none exists, session_number will be 1."""
    sid = str(uuid.uuid4())
    conn = _connect()
    row = conn.execute(
        "SELECT MAX(session_number) as max_num FROM student_question_sessions"
        " WHERE student_id = %s AND question_id = %s",
        (student_id, question_id),
    ).fetchone()
    next_num = (row["max_num"] or 0) + 1
    conn.execute(
        "INSERT INTO student_question_sessions (id, student_id, question_id, session_number)"
        " VALUES (%s, %s, %s, %s)",
        (sid, student_id, question_id, next_num),
    )
    conn.commit()
    conn.close()
    return sid, next_num


def list_question_sessions(student_id: str, question_id: str) -> list[dict]:
    """Return all sessions for (student_id, question_id) ordered oldest-first."""
    conn = _connect()
    rows = conn.execute(
        "SELECT id, session_number FROM student_question_sessions"
        " WHERE student_id = %s AND question_id = %s ORDER BY session_number ASC",
        (student_id, question_id),
    ).fetchall()
    conn.close()
    return [{"session_id": row["id"], "session_number": row["session_number"]} for row in rows]
