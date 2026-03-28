# app.py
import json
from datetime import datetime, timedelta, timezone

from fastapi import Cookie, Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
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
    update_attempt_score,
    delete_attempts_for_question,
    create_user,
    get_user_by_username,
    create_session,
    delete_session,
    delete_sessions_for_user,
    get_setting,
    set_setting,
    list_questions_for_class,
    list_questions_for_user,
    create_class,
    get_class,
    get_class_by_student_code,
    get_class_by_instructor_code,
    list_classes_for_user,
    add_class_member,
    is_class_member,
    get_class_question_count,
    get_class_question_stats,
    get_question_session_stats,
    update_class_student_code,
    update_class_instructor_code,
    create_student_user,
    get_student_by_username,
    get_student_by_email,
    get_student_by_id,
    create_student_session,
    get_student_session,
    update_student_session_expiry,
    delete_student_session,
    get_or_create_question_session,
    start_new_question_session,
    list_question_sessions,
)
from dependencies import _validate_session, require_instructor_api, require_class_member
from export_utils import format_question_export, format_class_export
from feedback import generate_feedback_stream, parse_scored_paragraphs, total_points, generate_score

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
    expires_at = (datetime.now(timezone.utc) + timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
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


def _validate_student_session(student_session_token: str | None) -> dict | None:
    """Return student dict if session is valid and not expired, None otherwise.
    Slides the 30-day expiry window on each valid access."""
    if not student_session_token:
        return None
    session = get_student_session(student_session_token)
    if not session:
        return None
    new_expiry = (datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
    update_student_session_expiry(student_session_token, new_expiry)
    return get_student_by_id(session["student_id"])


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
def student_landing(request: Request):
    """Class code entry page. JS checks localStorage and may redirect to /student/{class_id}."""
    return templates.TemplateResponse("student.html", {"request": request, "mode": "landing"})


@app.get("/student/{class_id}", response_class=HTMLResponse)
def student_class_list(request: Request, class_id: str):
    cls = get_class(class_id)
    if not cls:
        return RedirectResponse(url="/student?clear=1", status_code=302)
    questions = list_questions_for_class(class_id)
    safe_questions = [
        {"id": q["id"], "title": q["title"], "prompt": q["prompt"]} for q in questions
    ]
    return templates.TemplateResponse(
        "student.html",
        {"request": request, "mode": "list", "class_id": class_id, "class_name": cls["name"], "questions": safe_questions},
    )


@app.get("/student/{class_id}/{question_id}", response_class=HTMLResponse)
def student_workspace(request: Request, class_id: str, question_id: str):
    cls = get_class(class_id)
    if not cls:
        return RedirectResponse(url="/student?clear=1", status_code=302)
    q = get_question(question_id)
    if not q or q.get("class_id") != class_id:
        return RedirectResponse(url=f"/student/{class_id}", status_code=302)
    safe_question = {"id": q["id"], "title": q["title"], "prompt": q["prompt"]}
    return templates.TemplateResponse(
        "student.html",
        {"request": request, "mode": "workspace", "class_id": class_id, "class_name": cls["name"], "question": safe_question},
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
    questions = list_questions_for_user(user["id"])
    classes = list_classes_for_user(user["id"])
    for q in questions:
        q["attempt_count"] = get_attempt_count(q["id"])
    return templates.TemplateResponse(
        "instructor.html",
        {"request": request, "questions": questions, "username": user["username"], "classes": classes},
    )


@app.get("/instructor/classes", response_class=HTMLResponse)
def instructor_classes_page(
    request: Request,
    session_token: str | None = Cookie(default=None),
):
    user = _validate_session(session_token)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    classes = list_classes_for_user(user["id"])
    for cls in classes:
        cls["question_count"] = get_class_question_count(cls["id"])
    return templates.TemplateResponse(
        "instructor-classes.html",
        {"request": request, "classes": classes, "username": user["username"]},
    )


@app.get("/instructor/classes/{class_id}/analytics", response_class=HTMLResponse)
def instructor_class_analytics(
    request: Request,
    class_id: str,
    session_token: str | None = Cookie(default=None),
):
    user = _validate_session(session_token)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    cls = get_class(class_id)
    if not cls:
        raise HTTPException(status_code=404, detail="Class not found")
    if not is_class_member(class_id, user["id"]):
        raise HTTPException(status_code=403, detail="Not a member of this class")
    question_stats = get_class_question_stats(class_id)
    return templates.TemplateResponse(
        "instructor-analytics-class.html",
        {
            "request": request,
            "class_name": cls["name"],
            "class_id": class_id,
            "question_stats": question_stats,
            "username": user["username"],
        },
    )


@app.get("/instructor/analytics/{question_id}", response_class=HTMLResponse)
def instructor_question_analytics(
    request: Request,
    question_id: str,
    session_token: str | None = Cookie(default=None),
):
    user = _validate_session(session_token)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    q = get_question(question_id)
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")
    if not is_class_member(q["class_id"], user["id"]):
        raise HTTPException(status_code=403, detail="Not a member of this class")
    sessions = get_question_session_stats(question_id)
    total_sessions = len(sessions)
    avg_attempts = (
        sum(s["attempt_count"] for s in sessions) / total_sessions
        if sessions else 0.0
    )
    scored = [s for s in sessions if s["final_score"] is not None]
    avg_final_score = sum(s["final_score"] for s in scored) / len(scored) if scored else None
    max_total = scored[0]["max_total"] if scored else None
    return templates.TemplateResponse(
        "instructor-analytics-question.html",
        {
            "request": request,
            "question": q,
            "class_id": q["class_id"],
            "sessions": sessions,
            "total_sessions": total_sessions,
            "avg_attempts": avg_attempts,
            "avg_final_score": avg_final_score,
            "max_total": max_total,
            "username": user["username"],
        },
    )


def _make_export_response(content: str, media_type: str, basename: str):
    ext = "json" if media_type == "application/json" else "csv"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{basename}.{ext}"'},
    )


@app.get("/instructor/analytics/{question_id}/export")
def export_question(
    question_id: str,
    format: str = Query(default="csv"),
    session_token: str | None = Cookie(default=None),
):
    user = _validate_session(session_token)
    if not user:
        return RedirectResponse("/login", status_code=302)
    q = get_question(question_id)
    if not q:
        raise HTTPException(status_code=404)
    if not is_class_member(q["class_id"], user["id"]):
        raise HTTPException(status_code=403)
    sessions = get_question_session_stats(question_id)
    content, media_type = format_question_export(sessions, format)
    return _make_export_response(content, media_type, f"question-{question_id[:8]}")


@app.get("/instructor/classes/{class_id}/analytics/export")
def export_class(
    class_id: str,
    format: str = Query(default="csv"),
    session_token: str | None = Cookie(default=None),
):
    user = _validate_session(session_token)
    if not user:
        return RedirectResponse("/login", status_code=302)
    cls = get_class(class_id)
    if not cls:
        raise HTTPException(status_code=404)
    if not is_class_member(class_id, user["id"]):
        raise HTTPException(status_code=403)
    q_stats = get_class_question_stats(class_id)
    session_rows = []
    for q in q_stats:
        for s in get_question_session_stats(q["question_id"]):
            session_rows.append(
                {
                    "question_title": q["title"],
                    "session_id": s["session_id"],
                    "attempt_count": s["attempt_count"],
                    "final_score": s["final_score"] if s["final_score"] is not None else "",
                    "max_score": s["max_total"] if s["max_total"] is not None else "",
                }
            )
    content, media_type = format_class_export(session_rows, format)
    return _make_export_response(content, media_type, f"class-{class_id[:8]}")


# ---- Student Auth API routes ----

class StudentRegisterRequest(BaseModel):
    username: str
    email: str
    password: str


class StudentLoginRequest(BaseModel):
    username_or_email: str
    password: str


@app.post("/api/student/auth/register")
def api_student_register(data: StudentRegisterRequest):
    if len(data.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    if get_student_by_username(data.username):
        raise HTTPException(status_code=400, detail="Username already taken")
    if get_student_by_email(data.email):
        raise HTTPException(status_code=400, detail="Email already registered")
    student_id = create_student_user(data.username, data.email, hash_password(data.password))
    token = generate_token()
    expires_at = (datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
    create_student_session(token, student_id, expires_at)
    response = JSONResponse({"id": student_id, "username": data.username})
    response.set_cookie(
        key="student_session_token",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=30 * 24 * 3600,
    )
    return response


@app.post("/api/student/auth/login")
def api_student_login(data: StudentLoginRequest):
    student = get_student_by_username(data.username_or_email)
    if not student:
        student = get_student_by_email(data.username_or_email)
    if not student or not verify_password(data.password, student["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = generate_token()
    expires_at = (datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
    create_student_session(token, student["id"], expires_at)
    response = JSONResponse({"id": student["id"], "username": student["username"]})
    response.set_cookie(
        key="student_session_token",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=30 * 24 * 3600,
    )
    return response


@app.post("/api/student/auth/logout")
def api_student_logout(student_session_token: str | None = Cookie(default=None)):
    if student_session_token:
        delete_student_session(student_session_token)
    response = JSONResponse({"ok": True})
    response.delete_cookie("student_session_token", httponly=True, samesite="lax")
    return response


@app.get("/api/student/auth/me")
def api_student_me(student_session_token: str | None = Cookie(default=None)):
    student = _validate_student_session(student_session_token)
    if not student:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {"id": student["id"], "username": student["username"]}


@app.post("/api/student/session/{question_id}/new")
def api_student_session_new(
    question_id: str,
    student_session_token: str | None = Cookie(default=None),
):
    student = _validate_student_session(student_session_token)
    if not student:
        raise HTTPException(status_code=401, detail="Not authenticated")
    question = get_question(question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    session_id, session_number = start_new_question_session(student["id"], question_id)
    return {"session_id": session_id, "session_number": session_number}


@app.get("/api/student/session/{question_id}/list")
def api_student_session_list(
    question_id: str,
    student_session_token: str | None = Cookie(default=None),
):
    student = _validate_student_session(student_session_token)
    if not student:
        raise HTTPException(status_code=401, detail="Not authenticated")
    question = get_question(question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    return list_question_sessions(student["id"], question_id)


@app.get("/api/student/session/{question_id}")
def api_student_session(
    question_id: str,
    student_session_token: str | None = Cookie(default=None),
):
    student = _validate_student_session(student_session_token)
    if not student:
        raise HTTPException(status_code=401, detail="Not authenticated")
    question = get_question(question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    session_id = get_or_create_question_session(student["id"], question_id)
    return {"session_id": session_id}


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
    class_id: str


class QuestionUpdate(BaseModel):
    title: Optional[str] = None
    prompt: Optional[str] = None
    model_answer: Optional[str] = None
    rubric: Optional[str] = None
    class_id: Optional[str] = None


class ClassCreate(BaseModel):
    name: str


class ClassJoin(BaseModel):
    instructor_code: str


# ---- Classes API routes ----

def _unique_class_code() -> str:
    """Generate an 8-char code guaranteed unique across all classes (student and instructor codes)."""
    for _ in range(10):
        code = generate_invite_code()
        if not get_class_by_student_code(code) and not get_class_by_instructor_code(code):
            return code
    raise RuntimeError("Failed to generate unique class code after 10 attempts")


@app.post("/api/classes")
def api_create_class(data: ClassCreate, user: dict = Depends(require_instructor_api)):
    s_code = _unique_class_code()
    i_code = _unique_class_code()
    class_id = create_class(data.name, s_code, i_code, user["id"])
    add_class_member(class_id, user["id"])
    return {"class_id": class_id, "name": data.name, "student_code": s_code, "instructor_code": i_code}


@app.post("/api/classes/join")
def api_join_class(data: ClassJoin, user: dict = Depends(require_instructor_api)):
    cls = get_class_by_instructor_code(data.instructor_code)
    if not cls or not compare_codes(data.instructor_code, cls["instructor_code"]):
        raise HTTPException(status_code=404, detail="Class not found")
    if is_class_member(cls["id"], user["id"]):
        raise HTTPException(status_code=400, detail="Already a member")
    add_class_member(cls["id"], user["id"])
    return {"class_id": cls["id"], "name": cls["name"]}


@app.get("/api/classes/by-student-code/{code}")
def api_by_student_code(code: str):
    cls = get_class_by_student_code(code)
    if not cls:
        raise HTTPException(status_code=404, detail="Class not found")
    return {"class_id": cls["id"], "name": cls["name"]}


@app.get("/api/classes/{class_id}/settings")
def api_class_settings(user_and_class: tuple = Depends(require_class_member)):
    user, class_id = user_and_class
    cls = get_class(class_id)
    return {"name": cls["name"], "student_code": cls["student_code"], "instructor_code": cls["instructor_code"]}


@app.put("/api/classes/{class_id}/student-code")
def api_rotate_student_code(user_and_class: tuple = Depends(require_class_member)):
    user, class_id = user_and_class
    new_code = _unique_class_code()
    update_class_student_code(class_id, new_code)
    return {"student_code": new_code}


@app.put("/api/classes/{class_id}/instructor-code")
def api_rotate_instructor_code(user_and_class: tuple = Depends(require_class_member)):
    user, class_id = user_and_class
    new_code = _unique_class_code()
    update_class_instructor_code(class_id, new_code)
    return {"instructor_code": new_code}


# ---- Questions API routes (continued) ----

@app.post("/api/questions")
def api_create_question(
    data: QuestionCreate,
    user: dict = Depends(require_instructor_api),
):
    if not is_class_member(data.class_id, user["id"]):
        raise HTTPException(status_code=403, detail="Not a member of this class")
    qid = create_question(data.title, data.prompt, data.model_answer, data.rubric, data.class_id)
    return {"id": qid}


@app.get("/api/questions/detail/{question_id}")
def api_get_question_detail(
    question_id: str,
    user: dict = Depends(require_instructor_api),
):
    """Instructor-only endpoint that returns full question data including model answer."""
    q = get_question(question_id)
    if not q:
        raise HTTPException(status_code=404, detail="Not found")
    return q


@app.put("/api/questions/{question_id}")
def api_update_question(
    question_id: str,
    data: QuestionUpdate,
    user: dict = Depends(require_instructor_api),
):
    q = get_question(question_id)
    if not q:
        raise HTTPException(status_code=404, detail="Not found")
    if not is_class_member(q["class_id"], user["id"]):
        raise HTTPException(status_code=403, detail="Not a member of this class")
    kwargs = {k: v for k, v in data.model_dump().items() if v is not None}
    if "class_id" in kwargs and not is_class_member(kwargs["class_id"], user["id"]):
        raise HTTPException(status_code=403, detail="Not a member of target class")
    update_question(question_id, **kwargs)
    return {"ok": True}


@app.delete("/api/questions/{question_id}/attempts")
def api_clear_attempts(
    question_id: str,
    user: dict = Depends(require_instructor_api),
):
    q = get_question(question_id)
    if not q:
        raise HTTPException(status_code=404, detail="Not found")
    if not is_class_member(q["class_id"], user["id"]):
        raise HTTPException(status_code=403, detail="Not a member of this class")
    delete_attempts_for_question(question_id)
    return {"ok": True}


@app.delete("/api/questions/{question_id}")
def api_delete_question(
    question_id: str,
    user: dict = Depends(require_instructor_api),
):
    q = get_question(question_id)
    if not q:
        raise HTTPException(status_code=404, detail="Not found")
    if not is_class_member(q["class_id"], user["id"]):
        raise HTTPException(status_code=403, detail="Not a member of this class")
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
    for a in attempts:
        if a.get("score_data") and "breakdown" in a["score_data"]:
            a["score_data"]["breakdown"] = [
                {"awarded": b["awarded"], "max": b["max"]}
                for b in a["score_data"]["breakdown"]
            ]
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

    paragraphs = parse_scored_paragraphs(question["model_answer"])
    has_scoring = total_points(paragraphs) > 0

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
        attempt_id = create_attempt(
            data.question_id,
            data.session_id,
            data.student_answer,
            full_feedback,
            attempt_number,
        )
        yield f"data: {json.dumps({'done': True, 'attempt_number': attempt_number})}\n\n"

        if has_scoring:
            score = await generate_score(paragraphs, data.student_answer, attempt_number)
            if score is not None:
                update_attempt_score(attempt_id, score)
                client_score = {**score, "breakdown": [{"awarded": b["awarded"], "max": b["max"]} for b in score["breakdown"]]}
                yield f"data: {json.dumps({'score': client_score})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn

    print("App is running on \033[1mhttp://localhost:8000/instructor\033[0m")
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
