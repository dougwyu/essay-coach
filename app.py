import json
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Optional
from db import (
    init_db,
    create_question,
    get_question,
    list_questions,
    update_question,
    delete_question,
    create_attempt,
    get_attempts,
    get_attempt_count,
)
from feedback import generate_feedback_stream

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.on_event("startup")
def startup():
    init_db()


# --- HTML routes ---


@app.get("/", response_class=RedirectResponse)
def root():
    return RedirectResponse(url="/student")


@app.get("/student", response_class=HTMLResponse)
def student_list(request: Request):
    questions = list_questions()
    # SECURITY: model_answer is server-side only, never sent to client
    safe_questions = [
        {"id": q["id"], "title": q["title"], "prompt": q["prompt"]} for q in questions
    ]
    return templates.TemplateResponse(
        "student.html", {"request": request, "questions": safe_questions, "question": None}
    )


@app.get("/student/{question_id}", response_class=HTMLResponse)
def student_workspace(request: Request, question_id: str):
    q = get_question(question_id)
    if not q:
        return RedirectResponse(url="/student")
    # SECURITY: model_answer is server-side only, never sent to client
    safe_question = {"id": q["id"], "title": q["title"], "prompt": q["prompt"]}
    return templates.TemplateResponse(
        "student.html", {"request": request, "questions": None, "question": safe_question}
    )


@app.get("/instructor", response_class=HTMLResponse)
def instructor_dashboard(request: Request):
    questions = list_questions()
    for q in questions:
        q["attempt_count"] = get_attempt_count(q["id"])
    return templates.TemplateResponse(
        "instructor.html", {"request": request, "questions": questions}
    )


# --- API routes ---


class QuestionCreate(BaseModel):
    title: str
    prompt: str
    model_answer: str
    rubric: Optional[str] = ""


class QuestionUpdate(BaseModel):
    title: Optional[str] = None
    prompt: Optional[str] = None
    model_answer: Optional[str] = None
    rubric: Optional[str] = None


class FeedbackRequest(BaseModel):
    question_id: str
    student_answer: str
    session_id: str


@app.post("/api/questions")
def api_create_question(data: QuestionCreate):
    qid = create_question(data.title, data.prompt, data.model_answer, data.rubric)
    return {"id": qid}


@app.get("/api/questions/detail/{question_id}")
def api_get_question_detail(question_id: str):
    """Instructor-only endpoint that returns full question data including model answer."""
    q = get_question(question_id)
    if not q:
        return {"error": "Not found"}
    return q


@app.put("/api/questions/{question_id}")
def api_update_question(question_id: str, data: QuestionUpdate):
    kwargs = {k: v for k, v in data.model_dump().items() if v is not None}
    update_question(question_id, **kwargs)
    return {"ok": True}


@app.delete("/api/questions/{question_id}")
def api_delete_question(question_id: str):
    delete_question(question_id)
    return {"ok": True}


@app.get("/api/attempts/{question_id}")
def api_get_attempts(question_id: str, session_id: str):
    attempts = get_attempts(question_id, session_id)
    # SECURITY: model_answer is server-side only, never sent to client
    return {"attempts": attempts}


@app.post("/api/feedback")
async def api_feedback(data: FeedbackRequest):
    question = get_question(data.question_id)
    if not question:
        return {"error": "Question not found"}

    # SECURITY: model_answer is server-side only, never sent to client
    attempts = get_attempts(data.question_id, data.session_id)
    attempt_number = len(attempts) + 1
    previous_feedback = attempts[0]["feedback"] if attempts else None

    collected_feedback = []

    async def event_stream():
        async for chunk in generate_feedback_stream(
            question_prompt=question["prompt"],
            model_answer=question["model_answer"],
            rubric=question["rubric"],
            student_answer=data.student_answer,
            attempt_number=attempt_number,
            previous_feedback=previous_feedback,
        ):
            collected_feedback.append(chunk)
            yield f"data: {json.dumps({'text': chunk})}\n\n"

        full_feedback = "".join(collected_feedback)
        create_attempt(
            data.question_id,
            data.session_id,
            data.student_answer,
            full_feedback,
            attempt_number,
        )
        yield f"data: {json.dumps({'done': True, 'attempt_number': attempt_number})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
