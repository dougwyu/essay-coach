import pytest
import config as config_module
from db import (
    init_db,
    create_question,
    get_question,
    list_questions,
    update_question,
    delete_question,
    create_attempt,
    get_attempts,
    get_attempt_count,
)

DUMMY_CLASS_ID = "00000000-0000-0000-0000-000000000001"


@pytest.fixture(autouse=True)
def test_db(tmp_path, monkeypatch):
    from db_connection import IS_POSTGRES, get_conn
    if not IS_POSTGRES:
        db_path = str(tmp_path / "test.db")
        monkeypatch.setattr(config_module, "DATABASE_PATH", db_path)
    else:
        db_path = None
    init_db()
    # Insert a dummy class so FK constraint is satisfied
    conn = get_conn()
    conn.execute(
        "INSERT INTO classes (id, name, student_code, instructor_code) VALUES (%s, %s, %s, %s)",
        (DUMMY_CLASS_ID, "Test", "STUD0001", "INST0001"),
    )
    conn.commit()
    conn.close()
    yield db_path


def test_create_and_get_question():
    qid = create_question("Test Title", "Write about X", "X is Y because Z", "Point 1\nPoint 2", DUMMY_CLASS_ID)
    q = get_question(qid)
    assert q["title"] == "Test Title"
    assert q["prompt"] == "Write about X"
    assert q["model_answer"] == "X is Y because Z"
    assert q["rubric"] == "Point 1\nPoint 2"
    assert q["class_id"] == DUMMY_CLASS_ID


def test_list_questions():
    create_question("Q1", "Prompt 1", "Answer 1", "", DUMMY_CLASS_ID)
    create_question("Q2", "Prompt 2", "Answer 2", "", DUMMY_CLASS_ID)
    qs = list_questions()
    assert len(qs) == 2


def test_update_question():
    qid = create_question("Old", "Old prompt", "Old answer", "", DUMMY_CLASS_ID)
    update_question(qid, title="New", prompt="New prompt", model_answer="New answer", rubric="New rubric")
    q = get_question(qid)
    assert q["title"] == "New"


def test_delete_question():
    qid = create_question("Del", "P", "A", "", DUMMY_CLASS_ID)
    delete_question(qid)
    assert get_question(qid) is None


def test_create_and_get_attempts():
    qid = create_question("Q", "P", "A", "", DUMMY_CLASS_ID)
    create_attempt(qid, "session1", "My answer", "Good job", 1)
    create_attempt(qid, "session1", "Better answer", "Even better", 2)
    attempts = get_attempts(qid, "session1")
    assert len(attempts) == 2
    assert attempts[0]["attempt_number"] == 2  # newest first


def test_get_attempt_count():
    qid = create_question("Q", "P", "A", "", DUMMY_CLASS_ID)
    create_attempt(qid, "s1", "ans", "fb", 1)
    create_attempt(qid, "s2", "ans", "fb", 1)
    assert get_attempt_count(qid) == 2
