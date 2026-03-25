import json
import pytest
import db as db_module
from db import init_db, create_attempt, get_attempts


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(db_module, "DATABASE_PATH", db_path)
    init_db()
    yield


def _make_question():
    from db import create_class, create_question
    cid = create_class("C", "SCODE001", "ICODE001", None)
    return create_question("Q", "Prompt", "Model answer [3]", None, cid)


# --- DB unit tests ---

def test_create_attempt_without_score():
    qid = _make_question()
    create_attempt(qid, "sess1", "my answer", "feedback text", 1)
    attempts = get_attempts(qid, "sess1")
    assert len(attempts) == 1
    assert attempts[0]["score_data"] is None


def test_create_attempt_with_score():
    qid = _make_question()
    score = {
        "breakdown": [{"label": "Topic A", "awarded": 2, "max": 3}],
        "total_awarded": 2,
        "total_max": 3,
    }
    create_attempt(qid, "sess1", "my answer", "feedback text", 1, score_data=score)
    attempts = get_attempts(qid, "sess1")
    assert attempts[0]["score_data"] == score


def test_update_attempt_score():
    from db import update_attempt_score
    qid = _make_question()
    aid = create_attempt(qid, "sess1", "my answer", "feedback", 1)
    score = {
        "breakdown": [{"label": "T", "awarded": 1, "max": 3}],
        "total_awarded": 1,
        "total_max": 3,
    }
    update_attempt_score(aid, score)
    attempts = get_attempts(qid, "sess1")
    assert attempts[0]["score_data"] == score
