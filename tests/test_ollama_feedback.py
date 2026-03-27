import json
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sse_lines(text_chunks):
    """Build the raw SSE bytes that Ollama streams back."""
    lines = []
    for chunk in text_chunks:
        payload = {"choices": [{"delta": {"content": chunk}, "finish_reason": None}]}
        lines.append(f"data: {json.dumps(payload)}\n\n")
    lines.append("data: [DONE]\n\n")
    return "".join(lines).encode()


def _score_response(score_dict):
    return {
        "choices": [{"message": {"content": json.dumps(score_dict)}}]
    }


# ── generate_feedback_stream (ollama path) ────────────────────────────────────

@pytest.mark.asyncio
async def test_ollama_feedback_stream_yields_text(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "ollama")

    import sys
    for k in list(sys.modules):
        if k in ("feedback", "config"):
            del sys.modules[k]
    from feedback import generate_feedback_stream

    sse_bytes = _sse_lines(["Hello", " world"])

    async def mock_aiter_lines():
        for line in sse_bytes.decode().splitlines():
            if line:
                yield line

    mock_response = MagicMock()
    mock_response.aiter_lines = mock_aiter_lines
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)

    mock_client = MagicMock()
    mock_client.stream = MagicMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_client):
        chunks = []
        async for chunk in generate_feedback_stream("Q", "A", None, "S", 1):
            chunks.append(chunk)

    assert chunks == ["Hello", " world"]


@pytest.mark.asyncio
async def test_ollama_feedback_stream_skips_done(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "ollama")

    import sys
    for k in list(sys.modules):
        if k in ("feedback", "config"):
            del sys.modules[k]
    from feedback import generate_feedback_stream

    sse_bytes = _sse_lines(["only chunk"])

    async def mock_aiter_lines():
        for line in sse_bytes.decode().splitlines():
            if line:
                yield line

    mock_response = MagicMock()
    mock_response.aiter_lines = mock_aiter_lines
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)
    mock_client = MagicMock()
    mock_client.stream = MagicMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_client):
        chunks = []
        async for chunk in generate_feedback_stream("Q", "A", None, "S", 1):
            chunks.append(chunk)

    assert "[DONE]" not in "".join(chunks)
    assert chunks == ["only chunk"]


# ── generate_score (ollama path) ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ollama_score_returns_valid_score(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "ollama")

    import sys
    for k in list(sys.modules):
        if k in ("feedback", "config"):
            del sys.modules[k]
    from feedback import generate_score, parse_scored_paragraphs

    score = {
        "breakdown": [{"label": "Topic A", "awarded": 2, "max": 3}],
        "total_awarded": 2,
        "total_max": 3,
    }
    paragraphs = parse_scored_paragraphs("Key concept [3]")

    mock_response = MagicMock()
    mock_response.json = MagicMock(return_value=_score_response(score))
    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await generate_score(paragraphs, "student answer", 1)

    assert result == score


@pytest.mark.asyncio
async def test_ollama_score_returns_none_on_invalid_json(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "ollama")

    import sys
    for k in list(sys.modules):
        if k in ("feedback", "config"):
            del sys.modules[k]
    from feedback import generate_score, parse_scored_paragraphs

    paragraphs = parse_scored_paragraphs("Key concept [3]")

    mock_response = MagicMock()
    mock_response.json = MagicMock(return_value={"choices": [{"message": {"content": "not json"}}]})
    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await generate_score(paragraphs, "student answer", 1)

    assert result is None
