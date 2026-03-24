from feedback import build_messages


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
