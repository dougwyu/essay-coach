# tests/test_export_utils.py
import csv
import io
import json
import pytest
from export_utils import format_question_export, format_class_export


# ── format_question_export ──────────────────────────────────────────────

def test_question_export_csv_headers():
    content, media_type = format_question_export([], "csv")
    assert media_type == "text/csv"
    reader = csv.DictReader(io.StringIO(content))
    assert reader.fieldnames == [
        "session_id", "attempt_number", "student_answer",
        "feedback", "score_awarded", "max_score",
    ]


def test_question_export_csv_empty_body():
    content, _ = format_question_export([], "csv")
    lines = content.strip().splitlines()
    assert len(lines) == 1  # header only


def test_question_export_csv_scored_rows():
    sessions = [
        {
            "session_id": "aaaa-bbbb-cccc-dddd-eeee",
            "attempts": [
                {
                    "attempt_number": 1,
                    "student_answer": "ans1",
                    "feedback": "fb1",
                    "score_data": {"total_awarded": 5, "total_max": 10},
                },
                {
                    "attempt_number": 2,
                    "student_answer": "ans2",
                    "feedback": "fb2",
                    "score_data": {"total_awarded": 8, "total_max": 10},
                },
            ],
        }
    ]
    content, _ = format_question_export(sessions, "csv")
    rows = list(csv.DictReader(io.StringIO(content)))
    assert len(rows) == 2
    assert rows[0]["score_awarded"] == "5"
    assert rows[0]["max_score"] == "10"
    assert rows[1]["score_awarded"] == "8"


def test_question_export_csv_unscored_rows():
    sessions = [
        {
            "session_id": "xxxx-0000",
            "attempts": [
                {
                    "attempt_number": 1,
                    "student_answer": "ans",
                    "feedback": None,
                    "score_data": None,
                }
            ],
        }
    ]
    content, _ = format_question_export(sessions, "csv")
    rows = list(csv.DictReader(io.StringIO(content)))
    assert rows[0]["score_awarded"] == ""
    assert rows[0]["max_score"] == ""
    assert rows[0]["feedback"] == ""


def test_question_export_json_structure():
    sessions = [
        {
            "session_id": "sid-1",
            "attempts": [
                {
                    "attempt_number": 1,
                    "student_answer": "a",
                    "feedback": "f",
                    "score_data": {"total_awarded": 3, "total_max": 5},
                }
            ],
        }
    ]
    content, media_type = format_question_export(sessions, "json")
    assert media_type == "application/json"
    data = json.loads(content)
    assert isinstance(data, list)
    assert len(data) == 1
    row = data[0]
    assert set(row.keys()) == {
        "session_id", "attempt_number", "student_answer",
        "feedback", "score_awarded", "max_score",
    }
    assert row["score_awarded"] == 3
    assert row["max_score"] == 5


def test_question_export_json_empty():
    content, _ = format_question_export([], "json")
    assert json.loads(content) == []


def test_question_export_json_unscored_uses_empty_string():
    sessions = [
        {
            "session_id": "s",
            "attempts": [
                {
                    "attempt_number": 1,
                    "student_answer": "a",
                    "feedback": None,
                    "score_data": None,
                }
            ],
        }
    ]
    content, _ = format_question_export(sessions, "json")
    row = json.loads(content)[0]
    assert row["score_awarded"] == ""
    assert row["max_score"] == ""


def test_question_export_unknown_format_defaults_to_csv():
    content, media_type = format_question_export([], "xlsx")
    assert media_type == "text/csv"


# ── format_class_export ─────────────────────────────────────────────────

def test_class_export_csv_headers():
    content, media_type = format_class_export([], "csv")
    assert media_type == "text/csv"
    reader = csv.DictReader(io.StringIO(content))
    assert reader.fieldnames == [
        "question_title", "session_id", "attempt_count", "final_score", "max_score",
    ]


def test_class_export_csv_empty_body():
    content, _ = format_class_export([], "csv")
    lines = content.strip().splitlines()
    assert len(lines) == 1  # header only


def test_class_export_csv_rows():
    rows = [
        {
            "question_title": "Q1",
            "session_id": "s1",
            "attempt_count": 2,
            "final_score": 7,
            "max_score": 10,
        },
        {
            "question_title": "Q2",
            "session_id": "s2",
            "attempt_count": 1,
            "final_score": "",
            "max_score": "",
        },
    ]
    content, _ = format_class_export(rows, "csv")
    data = list(csv.DictReader(io.StringIO(content)))
    assert len(data) == 2
    assert data[0]["question_title"] == "Q1"
    assert data[1]["final_score"] == ""


def test_class_export_json_structure():
    rows = [
        {
            "question_title": "Q1",
            "session_id": "s1",
            "attempt_count": 1,
            "final_score": 5,
            "max_score": 10,
        }
    ]
    content, media_type = format_class_export(rows, "json")
    assert media_type == "application/json"
    data = json.loads(content)
    assert len(data) == 1
    assert set(data[0].keys()) == {
        "question_title", "session_id", "attempt_count", "final_score", "max_score",
    }


def test_class_export_json_empty():
    content, _ = format_class_export([], "json")
    assert json.loads(content) == []


def test_class_export_unknown_format_defaults_to_csv():
    content, media_type = format_class_export([], "anything")
    assert media_type == "text/csv"
