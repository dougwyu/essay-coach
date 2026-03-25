from feedback import (
    build_messages,
    parse_scored_paragraphs,
    total_points,
    validate_score,
)


def test_build_messages_first_attempt():
    messages = build_messages(
        question_prompt="Explain X",
        model_answer="X is Y",
        rubric="Cover Y",
        student_answer="I think X might be Y",
        attempt_number=1,
        previous_feedback=None,
    )
    assert messages[0]["role"] == "user"
    content = messages[0]["content"]
    assert "<model_answer>" in content
    assert "<student_answer" in content
    assert 'attempt="1"' in content
    assert "<previous_feedback>" not in content


def test_build_messages_with_previous_feedback():
    messages = build_messages(
        question_prompt="Explain X",
        model_answer="X is Y",
        rubric="Cover Y",
        student_answer="Better answer",
        attempt_number=2,
        previous_feedback="You missed Z",
    )
    content = messages[0]["content"]
    assert "<previous_feedback>" in content
    assert 'attempt="2"' in content


def test_build_messages_no_rubric():
    messages = build_messages(
        question_prompt="Explain X",
        model_answer="X is Y",
        rubric="",
        student_answer="My answer",
        attempt_number=1,
    )
    content = messages[0]["content"]
    assert "No specific rubric provided." in content


def test_parse_extracts_point_values():
    result = parse_scored_paragraphs("First paragraph text. [3]\n\nSecond paragraph text. [4]")
    assert len(result) == 2
    assert result[0]["text"] == "First paragraph text."
    assert result[0]["points"] == 3
    assert result[1]["text"] == "Second paragraph text."
    assert result[1]["points"] == 4


def test_parse_unscored_paragraph_has_none():
    result = parse_scored_paragraphs("Context paragraph.\n\nScored paragraph. [2]")
    assert result[0]["points"] is None
    assert result[0]["text"] == "Context paragraph."
    assert result[1]["points"] == 2


def test_parse_no_scored_paragraphs():
    result = parse_scored_paragraphs("Just a plain paragraph.\n\nAnother one.")
    assert all(p["points"] is None for p in result)


def test_parse_strips_bracket_from_text():
    result = parse_scored_paragraphs("Some text here. [5]")
    assert "[5]" not in result[0]["text"]
    assert result[0]["text"] == "Some text here."


def test_total_points_sums_scored():
    paras = [{"text": "a", "points": 3}, {"text": "b", "points": None}, {"text": "c", "points": 4}]
    assert total_points(paras) == 7


def test_total_points_zero_when_no_scored():
    paras = [{"text": "a", "points": None}]
    assert total_points(paras) == 0


def test_validate_score_passes_on_correct_response():
    paras = [
        {"text": "a", "points": 3},
        {"text": "b", "points": None},
        {"text": "c", "points": 4},
    ]
    data = {
        "breakdown": [
            {"label": "Topic A", "awarded": 2, "max": 3},
            {"label": "Topic C", "awarded": 4, "max": 4},
        ],
        "total_awarded": 6,
        "total_max": 7,
    }
    assert validate_score(data, paras) is True


def test_validate_score_fails_awarded_exceeds_max():
    paras = [{"text": "a", "points": 3}]
    data = {
        "breakdown": [{"label": "Topic A", "awarded": 4, "max": 3}],
        "total_awarded": 4,
        "total_max": 3,
    }
    assert validate_score(data, paras) is False


def test_validate_score_fails_wrong_total_awarded():
    paras = [{"text": "a", "points": 3}]
    data = {
        "breakdown": [{"label": "Topic A", "awarded": 2, "max": 3}],
        "total_awarded": 99,
        "total_max": 3,
    }
    assert validate_score(data, paras) is False


def test_validate_score_fails_breakdown_length_mismatch():
    paras = [{"text": "a", "points": 3}, {"text": "b", "points": 4}]
    data = {
        "breakdown": [{"label": "Topic A", "awarded": 2, "max": 3}],
        "total_awarded": 2,
        "total_max": 3,
    }
    assert validate_score(data, paras) is False


def test_validate_score_fails_max_mismatch():
    paras = [{"text": "a", "points": 3}]
    data = {
        "breakdown": [{"label": "Topic A", "awarded": 2, "max": 99}],
        "total_awarded": 2,
        "total_max": 99,
    }
    assert validate_score(data, paras) is False
