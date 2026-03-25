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


from unittest.mock import patch
from fastapi.testclient import TestClient
from app import app
from db import get_setting


@pytest.fixture
def client():
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def _register_and_login(client):
    invite = get_setting("invite_code")
    client.post("/api/auth/register", json={
        "username": "alice", "password": "password123", "invite_code": invite
    })
    client.post("/api/auth/login", json={"username": "alice", "password": "password123"})


def _create_class_and_question(client, model_answer="Section one text. [3]\n\nSection two text. [4]"):
    res = client.post("/api/classes", json={"name": "Test Class"})
    class_id = res.json()["class_id"]
    res = client.post("/api/questions", json={
        "title": "Q1", "prompt": "Explain X",
        "model_answer": model_answer, "rubric": "", "class_id": class_id,
    })
    return res.json()["id"]


MOCK_SCORE = {
    "breakdown": [
        {"label": "Topic A", "awarded": 2, "max": 3},
        {"label": "Topic B", "awarded": 3, "max": 4},
    ],
    "total_awarded": 5,
    "total_max": 7,
}


def _mock_stream(text="Good feedback."):
    async def _gen(*args, **kwargs):
        yield text
    return _gen


def _mock_score(return_value=MOCK_SCORE):
    async def _score(*args, **kwargs):
        return return_value
    return _score


def _parse_sse(response_text):
    """Parse SSE response text into list of event data dicts."""
    events = []
    for line in response_text.splitlines():
        if line.startswith("data: "):
            try:
                events.append(json.loads(line[6:]))
            except Exception:
                pass
    return events


# --- Integration tests ---

def test_feedback_scored_question_emits_score_event(client):
    _register_and_login(client)
    qid = _create_class_and_question(client)

    with patch("app.generate_feedback_stream", _mock_stream()), \
         patch("app.generate_score", _mock_score()):
        res = client.post("/api/feedback", json={
            "question_id": qid, "student_answer": "My answer", "session_id": "s1"
        })
    events = _parse_sse(res.text)
    score_events = [e for e in events if "score" in e]
    assert len(score_events) == 1
    assert score_events[0]["score"]["total_max"] == 7


def test_feedback_unscored_question_no_score_event(client):
    _register_and_login(client)
    qid = _create_class_and_question(client, model_answer="Plain model answer without points.")

    with patch("app.generate_feedback_stream", _mock_stream()):
        res = client.post("/api/feedback", json={
            "question_id": qid, "student_answer": "My answer", "session_id": "s2"
        })
    events = _parse_sse(res.text)
    score_events = [e for e in events if "score" in e]
    assert len(score_events) == 0


def test_feedback_score_total_max_matches_model_answer(client):
    _register_and_login(client)
    # [3] + [4] = 7 total
    qid = _create_class_and_question(client, model_answer="Section one. [3]\n\nSection two. [4]")
    score_7 = {
        "breakdown": [
            {"label": "A", "awarded": 2, "max": 3},
            {"label": "B", "awarded": 3, "max": 4},
        ],
        "total_awarded": 5,
        "total_max": 7,
    }

    with patch("app.generate_feedback_stream", _mock_stream()), \
         patch("app.generate_score", _mock_score(score_7)):
        res = client.post("/api/feedback", json={
            "question_id": qid, "student_answer": "Answer", "session_id": "s3"
        })
    events = _parse_sse(res.text)
    score_event = next(e for e in events if "score" in e)
    assert score_event["score"]["total_max"] == 7


def test_get_attempts_returns_score_data_as_object(client):
    _register_and_login(client)
    qid = _create_class_and_question(client)

    with patch("app.generate_feedback_stream", _mock_stream()), \
         patch("app.generate_score", _mock_score()):
        client.post("/api/feedback", json={
            "question_id": qid, "student_answer": "Answer", "session_id": "s4"
        })

    res = client.get(f"/api/attempts/{qid}?session_id=s4")
    attempts = res.json()["attempts"]
    assert len(attempts) == 1
    assert attempts[0]["score_data"] is not None
    assert isinstance(attempts[0]["score_data"], dict)
    assert attempts[0]["score_data"]["total_max"] == 7


def test_get_attempts_score_data_null_when_no_scoring(client):
    _register_and_login(client)
    qid = _create_class_and_question(client, model_answer="No points here.")

    with patch("app.generate_feedback_stream", _mock_stream()):
        client.post("/api/feedback", json={
            "question_id": qid, "student_answer": "Answer", "session_id": "s5"
        })

    res = client.get(f"/api/attempts/{qid}?session_id=s5")
    attempts = res.json()["attempts"]
    assert attempts[0]["score_data"] is None


def test_scoring_failure_done_still_emitted_no_score_event(client):
    _register_and_login(client)
    qid = _create_class_and_question(client)

    with patch("app.generate_feedback_stream", _mock_stream()), \
         patch("app.generate_score", _mock_score(None)):
        res = client.post("/api/feedback", json={
            "question_id": qid, "student_answer": "Answer", "session_id": "s6"
        })
    events = _parse_sse(res.text)
    done_events = [e for e in events if "done" in e]
    score_events = [e for e in events if "score" in e]
    assert len(done_events) == 1
    assert len(score_events) == 0


def test_scoring_failure_attempt_saved_without_score(client):
    _register_and_login(client)
    qid = _create_class_and_question(client)

    with patch("app.generate_feedback_stream", _mock_stream()), \
         patch("app.generate_score", _mock_score(None)):
        client.post("/api/feedback", json={
            "question_id": qid, "student_answer": "Answer", "session_id": "s7"
        })

    res = client.get(f"/api/attempts/{qid}?session_id=s7")
    attempts = res.json()["attempts"]
    assert len(attempts) == 1
    assert attempts[0]["score_data"] is None
