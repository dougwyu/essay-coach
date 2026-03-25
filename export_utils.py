# export_utils.py
import csv
import io
import json

_FMT_JSON = "json"
_MEDIA_JSON = "application/json"
_MEDIA_CSV = "text/csv"


def format_question_export(sessions: list[dict], fmt: str) -> tuple[str, str]:
    """Flatten sessions to one row per attempt and format as CSV or JSON.

    `sessions` is the direct output of ``get_question_session_stats()``.
    Each attempt dict must have keys: ``attempt_number``, ``student_answer``,
    ``feedback`` (may be None), and optionally ``score_data`` (may be None).

    Any `fmt` value other than ``"json"`` is treated as CSV.

    Returns (content, media_type).
    """
    rows = []
    for s in sessions:
        for attempt in s.get("attempts", []):
            score_data = attempt.get("score_data")
            rows.append(
                {
                    "session_id": s["session_id"],
                    "attempt_number": attempt["attempt_number"],
                    "student_answer": attempt["student_answer"],
                    "feedback": attempt["feedback"] or "",
                    "score_awarded": score_data["total_awarded"] if score_data else "",
                    "max_score": score_data["total_max"] if score_data else "",
                }
            )

    if fmt == _FMT_JSON:
        return json.dumps(rows), _MEDIA_JSON

    # CSV (default for any non-json value)
    fieldnames = [
        "session_id",
        "attempt_number",
        "student_answer",
        "feedback",
        "score_awarded",
        "max_score",
    ]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue(), _MEDIA_CSV


def format_class_export(session_rows: list[dict], fmt: str) -> tuple[str, str]:
    """Format pre-built session rows as CSV or JSON.

    Any `fmt` value other than ``"json"`` is treated as CSV.

    Returns (content, media_type).
    """
    if fmt == _FMT_JSON:
        return json.dumps(session_rows), _MEDIA_JSON

    fieldnames = [
        "question_title",
        "session_id",
        "attempt_count",
        "final_score",
        "max_score",
    ]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(session_rows)
    return buf.getvalue(), _MEDIA_CSV
