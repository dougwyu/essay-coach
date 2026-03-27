# SECURITY: model_answer is server-side only, never sent to client
import json
import re

import anthropic
import httpx
from config import ANTHROPIC_API_KEY, MODEL_NAME, LLM_BACKEND, OLLAMA_BASE_URL, OLLAMA_MODEL


def parse_scored_paragraphs(model_answer: str) -> list[dict]:
    """Split model_answer into paragraphs, extracting trailing [N] point values.
    Returns list of {"text": str, "points": int | None}.
    """
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', model_answer.strip()) if p.strip()]
    pattern = re.compile(r'^(.*?)\s*\[([1-9]\d*)\]\s*$', re.DOTALL)
    result = []
    for p in paragraphs:
        m = pattern.match(p)
        if m:
            result.append({"text": m.group(1).strip(), "points": int(m.group(2))})
        else:
            result.append({"text": p, "points": None})
    return result


def total_points(paragraphs: list[dict]) -> int:
    return sum(p["points"] for p in paragraphs if p["points"] is not None)


def validate_score(data: dict, paragraphs: list[dict]) -> bool:
    scored = [p for p in paragraphs if p["points"] is not None]
    if len(data.get("breakdown", [])) != len(scored):
        return False
    for item, para in zip(data["breakdown"], scored):
        if not (0 <= item["awarded"] <= item["max"]):
            return False
        if item["max"] != para["points"]:
            return False
    expected_total_max = sum(p["points"] for p in scored)
    expected_total_awarded = sum(item["awarded"] for item in data["breakdown"])
    if data.get("total_max") != expected_total_max:
        return False
    if data.get("total_awarded") != expected_total_awarded:
        return False
    return True


SYSTEM_PROMPT = """You are an essay coach helping a university student improve their answer. You have access to the instructor's model answer and rubric, but you must NEVER reveal the model answer's content directly. Your job is to give the student directional feedback so they can discover the shape of a good answer through revision.

Rules:
1. NEVER quote, paraphrase, or closely mirror the model answer. Do not say "the answer should state that X is Y." Instead say "consider whether your discussion of X is complete."
2. Structure feedback as:
   - COVERAGE: Which key concepts/arguments are present, partially present, or missing? Use vague directional hints, not the actual content.
   - DEPTH: Where does the student's reasoning need to go deeper?
   - STRUCTURE: How could the argument's organization improve?
   - ACCURACY: Flag any factual errors or misconceptions.
   - PROGRESS (attempt 2+): What improved since last attempt, what still needs work.
3. Be encouraging but honest. Scale specificity with attempt number: early attempts get broad strokes, later attempts get more targeted nudges.
4. If the answer is very close to the model answer, say so and suggest minor polish rather than new directions.
5. Never assign a grade or numeric score. Use qualitative language only.
6. If the model answer contains point values in square brackets (e.g. [3]) at the end of sections, acknowledge at the very end of your feedback in one brief sentence that a numerical score will follow. If no point values are present, add one sentence: 'No point values were set for this question — feedback is qualitative only.'"""


def build_messages(question_prompt, model_answer, rubric, student_answer, attempt_number, previous_feedback=None):
    content = f"""The student is answering this question: {question_prompt}

<model_answer>{model_answer}</model_answer>
<rubric>{rubric or "No specific rubric provided."}</rubric>
<student_answer attempt="{attempt_number}">{student_answer}</student_answer>"""

    if previous_feedback:
        content += f"\n<previous_feedback>{previous_feedback}</previous_feedback>"

    return [{"role": "user", "content": content}]


async def _ollama_feedback_stream(messages, system_prompt):
    """Stream feedback from Ollama's OpenAI-compatible endpoint."""
    payload = {
        "model": OLLAMA_MODEL,
        "stream": True,
        "max_tokens": 2048,
        "messages": [{"role": "system", "content": system_prompt}] + messages,
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream(
            "POST",
            f"{OLLAMA_BASE_URL}/v1/chat/completions",
            json=payload,
            headers={"Authorization": "Bearer ollama"},
        ) as response:
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                payload_str = line[6:]
                if payload_str.strip() == "[DONE]":
                    break
                chunk = json.loads(payload_str)
                delta = chunk["choices"][0]["delta"].get("content", "")
                if delta:
                    yield delta


async def _ollama_score(user_message, system_prompt):
    """Request a JSON score from Ollama (non-streaming)."""
    payload = {
        "model": OLLAMA_MODEL,
        "stream": False,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{OLLAMA_BASE_URL}/v1/chat/completions",
            json=payload,
            headers={"Authorization": "Bearer ollama"},
        )
    return response.json()["choices"][0]["message"]["content"].strip()


async def generate_feedback_stream(question_prompt, model_answer, rubric, student_answer, attempt_number, previous_feedback=None):
    messages = build_messages(question_prompt, model_answer, rubric, student_answer, attempt_number, previous_feedback)
    if LLM_BACKEND == "ollama":
        async for chunk in _ollama_feedback_stream(messages, SYSTEM_PROMPT):
            yield chunk
        return

    # Anthropic path (default)
    client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    async with client.messages.stream(
        model=MODEL_NAME,
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=messages,
    ) as stream:
        async for text in stream.text_stream:
            yield text


SCORING_SYSTEM_PROMPT = """You are a strict but fair examiner scoring a student's essay answer.
You will be given the model answer split into numbered sections, each with a maximum point value.
The student's answer will not follow the same order as the model answer sections.
For each section, judge how many points the student has earned based on the conceptual
coverage and accuracy of their answer as a whole.

Rules:
1. awarded must be an integer between 0 and max (inclusive).
2. Generate a label (3–7 words) summarising the core concept of each section.
   - attempt_number 1: use broad topic labels (e.g. "Light-dependent reactions").
   - attempt_number 2+: use progressively more specific labels that give the student
     clearer signal about what is missing (e.g. "Role of ATP and NADPH in light reactions").
   Labels should orient the student to the relevant part of their answer without
   quoting or closely paraphrasing the model answer text.
3. Return ONLY valid JSON matching the schema below. No prose, no markdown.

Schema:
{
  "breakdown": [
    {"label": "<string>", "awarded": <int>, "max": <int>},
    ...
  ],
  "total_awarded": <int>,
  "total_max": <int>
}"""


async def generate_score(paragraphs: list[dict], student_answer: str, attempt_number: int) -> dict | None:
    """Score a student answer against scored paragraphs. Returns score dict or None on failure."""
    scored = [p for p in paragraphs if p["points"] is not None]
    if not scored:
        return None

    sections_xml = "\n".join(
        f'  <section index="{i + 1}" max="{p["points"]}">{p["text"]}</section>'
        for i, p in enumerate(scored)
    )
    user_message = (
        f"<sections>\n{sections_xml}\n</sections>\n"
        f'<student_answer attempt="{attempt_number}">{student_answer}</student_answer>'
    )

    try:
        if LLM_BACKEND == "ollama":
            raw = await _ollama_score(user_message, SCORING_SYSTEM_PROMPT)
        else:
            # Anthropic path (default)
            client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
            response = await client.messages.create(
                model=MODEL_NAME,
                max_tokens=1024,
                system=SCORING_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            )
            raw = response.content[0].text.strip()

        data = json.loads(raw)
        if validate_score(data, paragraphs):
            return data
        return None
    except Exception:
        return None
