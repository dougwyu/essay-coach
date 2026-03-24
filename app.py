# app.py
import json
from datetime import datetime, timedelta

from fastapi import Cookie, Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Optional

from auth import (
    compare_codes,
    generate_invite_code,
    generate_token,
    hash_password,
    verify_password,
)
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
    create_user,
    get_user_by_username,
    create_session,
    delete_session,
    delete_sessions_for_user,
    get_setting,
    set_setting,
)
from dependencies import _validate_session, require_instructor_api
from feedback import generate_feedback_stream

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.on_event("startup")
def startup():
    init_db()


# ---- internal helpers ----

def _new_session(user_id: str) -> str:
    """Create a DB session and return the token."""
    token = generate_token()
    expires_at = (datetime.utcnow() + timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    create_session(token, user_id, expires_at)
    return token


def _set_session_cookie(response: JSONResponse, token: str) -> None:
    response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=7 * 24 * 3600,
    )


# ---- HTML routes ----

@app.get("/", response_class=RedirectResponse)
def root():
    return RedirectResponse(url="/student")


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})


@app.post("/logout")
def logout(session_token: str | None = Cookie(default=None)):
    response = RedirectResponse(url="/login", status_code=302)
    if session_token:
        delete_session(session_token)
    response.delete_cookie("session_token")
    return response


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
def instructor_dashboard(
    request: Request,
    session_token: str | None = Cookie(default=None),
):
    # HTML route: redirect to /login on auth failure instead of raising 401
    user = _validate_session(session_token)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    questions = list_questions()
    for q in questions:
        q["attempt_count"] = get_attempt_count(q["id"])
    return templates.TemplateResponse(
        "instructor.html",
        {"request": request, "questions": questions, "username": user["username"]},
    )


# ---- Auth API routes ----

class RegisterRequest(BaseModel):
    username: str
    password: str
    invite_code: str


class LoginRequest(BaseModel):
    username: str
    password: str


@app.post("/api/auth/register")
def api_register(data: RegisterRequest):
    if len(data.password) < 8 or len(data.password) > 72:
        raise HTTPException(status_code=400, detail="Password must be 8-72 characters")
    stored_code = get_setting("invite_code")
    if not stored_code or not compare_codes(data.invite_code, stored_code):
        raise HTTPException(status_code=400, detail="Invalid invite code")
    if get_user_by_username(data.username):
        raise HTTPException(status_code=400, detail="Username already taken")
    user_id = create_user(data.username, hash_password(data.password))
    token = _new_session(user_id)
    response = JSONResponse({"ok": True})
    _set_session_cookie(response, token)
    return response


@app.post("/api/auth/login")
def api_login(data: LoginRequest):
    user = get_user_by_username(data.username)
    if not user or not verify_password(data.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    delete_sessions_for_user(user["id"])
    token = _new_session(user["id"])
    response = JSONResponse({"ok": True})
    _set_session_cookie(response, token)
    return response


@app.get("/api/auth/me")
def api_me(user: dict = Depends(require_instructor_api)):
    return {"username": user["username"]}


# ---- Settings API routes (instructor-protected) ----

class InviteCodeUpdate(BaseModel):
    code: Optional[str] = None


@app.get("/api/settings/invite-code")
def api_get_invite_code(user: dict = Depends(require_instructor_api)):
    return {"invite_code": get_setting("invite_code")}


@app.put("/api/settings/invite-code")
def api_update_invite_code(
    data: InviteCodeUpdate,
    user: dict = Depends(require_instructor_api),
):
    new_code = data.code if data.code else generate_invite_code()
    set_setting("invite_code", new_code)
    return {"invite_code": new_code}


# ---- Questions API routes (instructor-protected) ----

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


@app.post("/api/questions")
def api_create_question(
    data: QuestionCreate,
    user: dict = Depends(require_instructor_api),
):
    qid = create_question(data.title, data.prompt, data.model_answer, data.rubric)
    return {"id": qid}


@app.get("/api/questions/detail/{question_id}")
def api_get_question_detail(
    question_id: str,
    user: dict = Depends(require_instructor_api),
):
    """Instructor-only endpoint that returns full question data including model answer."""
    q = get_question(question_id)
    if not q:
        return {"error": "Not found"}
    return q


@app.put("/api/questions/{question_id}")
def api_update_question(
    question_id: str,
    data: QuestionUpdate,
    user: dict = Depends(require_instructor_api),
):
    kwargs = {k: v for k, v in data.model_dump().items() if v is not None}
    update_question(question_id, **kwargs)
    return {"ok": True}


@app.delete("/api/questions/{question_id}")
def api_delete_question(
    question_id: str,
    user: dict = Depends(require_instructor_api),
):
    delete_question(question_id)
    return {"ok": True}


# ---- Student API routes (unprotected) ----

class FeedbackRequest(BaseModel):
    question_id: str
    student_answer: str
    session_id: str


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
