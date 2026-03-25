import json
import pytest
from db import (
    init_db,
    create_class,
    create_question,
    create_attempt,
    get_class_question_stats,
    get_question_session_stats,
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


# --- DB unit tests for get_question_session_stats ---

def test_session_stats_single_attempt():
    cid = _make_class()
    qid = _make_question(cid)
    sid = str(uuid.uuid4())
    _make_attempt(qid, sid, 1, {"breakdown": [], "total_awarded": 5, "total_max": 10})
    result = get_question_session_stats(qid)
    assert len(result) == 1
    s = result[0]
    assert s["attempt_count"] == 1
    assert len(s["score_progression"]) == 1
    assert s["score_progression"][0] == 5
    assert s["final_score"] == 5


def test_session_stats_multi_attempt_score_improvement():
    cid = _make_class()
    qid = _make_question(cid)
    sid = str(uuid.uuid4())
    _make_attempt(qid, sid, 1, {"breakdown": [], "total_awarded": 3, "total_max": 10})
    _make_attempt(qid, sid, 2, {"breakdown": [], "total_awarded": 7, "total_max": 10})
    _make_attempt(qid, sid, 3, {"breakdown": [], "total_awarded": 9, "total_max": 10})
    result = get_question_session_stats(qid)
    assert len(result) == 1
    s = result[0]
    assert s["attempt_count"] == 3
    assert s["score_progression"] == [3, 7, 9]
    assert s["final_score"] == 9


def test_session_stats_no_score_data():
    cid = _make_class()
    qid = _make_question(cid)
    sid = str(uuid.uuid4())
    _make_attempt(qid, sid, 1)
    _make_attempt(qid, sid, 2)
    result = get_question_session_stats(qid)
    s = result[0]
    assert all(v is None for v in s["score_progression"])
    assert s["final_score"] is None
    assert s["max_total"] is None


def test_session_stats_sort_order():
    """Session with more attempts appears first."""
    cid = _make_class()
    qid = _make_question(cid)
    sid1 = str(uuid.uuid4())
    sid2 = str(uuid.uuid4())
    _make_attempt(qid, sid1, 1)
    _make_attempt(qid, sid2, 1)
    _make_attempt(qid, sid2, 2)
    _make_attempt(qid, sid2, 3)
    result = get_question_session_stats(qid)
    assert result[0]["attempt_count"] == 3
    assert result[1]["attempt_count"] == 1


def test_session_stats_attempts_ascending_order():
    """attempts list within a session is in ascending attempt_number order."""
    cid = _make_class()
    qid = _make_question(cid)
    sid = str(uuid.uuid4())
    _make_attempt(qid, sid, 1, {"breakdown": [], "total_awarded": 3, "total_max": 10})
    _make_attempt(qid, sid, 2, {"breakdown": [], "total_awarded": 7, "total_max": 10})
    result = get_question_session_stats(qid)
    atts = result[0]["attempts"]
    assert atts[0]["attempt_number"] == 1
    assert atts[1]["attempt_number"] == 2


def test_session_stats_no_sessions():
    """Question with no attempts returns empty list."""
    cid = _make_class()
    qid = _make_question(cid)
    result = get_question_session_stats(qid)
    assert result == []
