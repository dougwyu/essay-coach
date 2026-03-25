import json
import pytest
from db import (
    init_db,
    create_class,
    create_question,
    create_attempt,
    get_class_question_stats,
)
from auth import hash_password
import uuid


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr("config.DATABASE_PATH", db_path)
    monkeypatch.setattr("db.DATABASE_PATH", db_path)
    init_db()
    yield


def _make_class(name="BIO101"):
    return create_class(name, str(uuid.uuid4())[:8], str(uuid.uuid4())[:8], None)


def _make_question(class_id, title="Q1"):
    return create_question(title, "Prompt", "Model answer.", None, class_id)


def _make_attempt(question_id, session_id, attempt_number, score_data=None):
    score_json = json.dumps(score_data) if score_data else None
    return create_attempt(question_id, session_id, "student answer", "feedback", attempt_number, score_data)


# --- DB unit tests for get_class_question_stats ---

def test_class_stats_no_questions():
    cid = _make_class()
    result = get_class_question_stats(cid)
    assert result == []


def test_class_stats_empty_question():
    cid = _make_class()
    qid = _make_question(cid)
    result = get_class_question_stats(cid)
    assert len(result) == 1
    r = result[0]
    assert r["total_sessions"] == 0
    assert r["avg_attempts"] == 0.0
    assert r["avg_final_score"] is None
    assert r["score_buckets"] is None


def test_class_stats_single_session_unscored():
    cid = _make_class()
    qid = _make_question(cid)
    sid = str(uuid.uuid4())
    _make_attempt(qid, sid, 1)
    result = get_class_question_stats(cid)
    r = result[0]
    assert r["total_sessions"] == 1
    assert r["avg_attempts"] == 1.0
    assert r["avg_final_score"] is None
    assert r["score_buckets"] is None


def test_class_stats_multiple_sessions_with_scores():
    cid = _make_class()
    qid = _make_question(cid)
    sid1 = str(uuid.uuid4())
    sid2 = str(uuid.uuid4())
    _make_attempt(qid, sid1, 1, {"breakdown": [], "total_awarded": 8, "total_max": 10})
    _make_attempt(qid, sid2, 1, {"breakdown": [], "total_awarded": 4, "total_max": 10})
    result = get_class_question_stats(cid)
    r = result[0]
    assert r["total_sessions"] == 2
    assert r["avg_attempts"] == 1.0
    assert r["avg_final_score"] == 6.0
    assert r["max_total"] == 10
    assert r["score_buckets"]["high"] == 1  # 8/10 >= 0.70
    assert r["score_buckets"]["mid"] == 1   # 4/10 == 0.40, boundary is mid


def test_class_stats_bucket_boundary_low_mid():
    """total_awarded / total_max == 0.40 -> mid bucket"""
    cid = _make_class()
    qid = _make_question(cid)
    sid = str(uuid.uuid4())
    _make_attempt(qid, sid, 1, {"breakdown": [], "total_awarded": 4, "total_max": 10})
    result = get_class_question_stats(cid)
    r = result[0]
    assert r["score_buckets"]["mid"] == 1
    assert r["score_buckets"]["low"] == 0


def test_class_stats_bucket_boundary_mid_high():
    """total_awarded / total_max == 0.70 -> high bucket"""
    cid = _make_class()
    qid = _make_question(cid)
    sid = str(uuid.uuid4())
    _make_attempt(qid, sid, 1, {"breakdown": [], "total_awarded": 7, "total_max": 10})
    result = get_class_question_stats(cid)
    r = result[0]
    assert r["score_buckets"]["high"] == 1
    assert r["score_buckets"]["mid"] == 0


def test_class_stats_bucket_boundary_699():
    """total_awarded / total_max == 0.699 -> mid bucket"""
    cid = _make_class()
    qid = _make_question(cid)
    sid = str(uuid.uuid4())
    # Use 699/1000 to get 0.699
    _make_attempt(qid, sid, 1, {"breakdown": [], "total_awarded": 699, "total_max": 1000})
    result = get_class_question_stats(cid)
    r = result[0]
    assert r["score_buckets"]["mid"] == 1
    assert r["score_buckets"]["high"] == 0
