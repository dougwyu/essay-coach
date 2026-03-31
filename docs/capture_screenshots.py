"""
Screenshot capture script for Essay Coach tutorial.
Run from the essay-coach directory with the server running on port 8000.
Usage: python docs/capture_screenshots.py

The script creates a fresh class and questions on every run so it works
against any database — no hardcoded UUIDs or codes required.
"""

import asyncio
import json
import os
import sqlite3
import time
import httpx
from pathlib import Path
from playwright.async_api import async_playwright

BASE = "http://localhost:8000"
OUT  = Path(__file__).parent / "images"

INST_USER = "screenshot_user"
INST_PASS = "screenshotpass1"

# Fresh student account per run — ensures attempt 1 is truly attempt 1
_SUFFIX   = str(int(time.time()))[-6:]
STU_USER  = f"screenshot_student_{_SUFFIX}"
STU_EMAIL = f"screenshot_student_{_SUFFIX}@example.com"
STU_PASS  = "screenshotstu1"

VIEWPORT = {"width": 1440, "height": 900}

# Student answers for Cell Division (attempt 1 = weaker, attempt 2 = stronger)
ANSWER_1 = (
    "Mitosis makes two cells that are the same as the parent cell. It is used for growth. "
    "Meiosis makes four cells and is used for reproduction. Meiosis has two divisions."
)
ANSWER_2 = (
    "Mitosis produces two genetically identical diploid daughter cells and is used "
    "for growth and tissue repair. Meiosis produces four genetically unique haploid "
    "cells and is used for sexual reproduction. Mitosis involves one division; meiosis "
    "involves two divisions (meiosis I separates homologous chromosomes, meiosis II "
    "separates sister chromatids). Crossing over during meiosis I generates genetic variation."
)

CELLDIV_QUESTION = {
    "title": "Cell Division",
    "prompt": (
        "Describe the key differences between mitosis and meiosis. "
        "Include the number and type of daughter cells produced, "
        "and explain the biological purpose of each process."
    ),
    "model_answer": (
        "Mitosis produces two genetically identical diploid daughter cells "
        "and is used for growth, tissue repair, and asexual reproduction. [3]\n\n"
        "Meiosis produces four genetically unique haploid cells (gametes) "
        "and is used for sexual reproduction. [3]\n\n"
        "Key differences: meiosis involves two rounds of cell division, "
        "crossing-over between homologous chromosomes in prophase I (creating genetic variation), "
        "and separation of homologous pairs in meiosis I. [4]"
    ),
    "rubric": (
        "- Must contrast ploidy (diploid vs. haploid)\n"
        "- Must state the number of daughter cells (2 vs. 4)\n"
        "- Must describe the biological purpose of each\n"
        "- Must mention genetic variation / crossing-over for meiosis"
    ),
}

PHOTOSYN_QUESTION = {
    "title": "Photosynthesis",
    "prompt": (
        "Explain the process of photosynthesis, including the light-dependent "
        "and light-independent reactions. Where does each stage occur, and what "
        "are the key inputs and outputs?"
    ),
    "model_answer": (
        "The light-dependent reactions in the thylakoid membranes use sunlight "
        "to split water molecules, releasing oxygen and producing ATP and NADPH. [4]\n\n"
        "The Calvin cycle (light-independent reactions) takes place in the stroma "
        "and uses the ATP and NADPH to fix CO\u2082 into glucose via the enzyme RuBisCO. [4]\n\n"
        "The net equation is: 6CO\u2082 + 6H\u2082O + light energy \u2192 C\u2086H\u2081\u2082O\u2086 + 6O\u2082. [2]"
    ),
    "rubric": (
        "- Must distinguish light-dependent vs. light-independent reactions\n"
        "- Must name thylakoid membranes and stroma as locations\n"
        "- Must include the overall equation or equivalent\n"
        "- Must mention ATP and NADPH as products of light reactions"
    ),
}


def get_invite_code() -> str:
    """Read the invite code from the local SQLite DB."""
    db_path = os.getenv("DATABASE_PATH", "essay_coach.db")
    db = sqlite3.connect(db_path)
    row = db.execute("SELECT value FROM settings WHERE key='invite_code'").fetchone()
    db.close()
    if not row:
        raise RuntimeError("invite_code not found in settings table. Is the server running and DB initialised?")
    return row[0]


def cleanup_screenshot_classes() -> None:
    """Delete all classes created by screenshot_user and remove any other memberships."""
    db_path = os.getenv("DATABASE_PATH", "essay_coach.db")
    db = sqlite3.connect(db_path)
    db.execute("PRAGMA foreign_keys = ON")
    row = db.execute("SELECT id FROM users WHERE username = ?", (INST_USER,)).fetchone()
    if row:
        uid = row[0]
        deleted = db.execute("DELETE FROM classes WHERE created_by = ?", (uid,)).rowcount
        db.execute("DELETE FROM class_members WHERE user_id = ?", (uid,))
        db.commit()
        if deleted:
            print(f"  cleaned up {deleted} previous screenshot class(es)")
    db.close()


async def save(page, name: str):
    path = OUT / name
    await page.screenshot(path=str(path), full_page=False)
    print(f"  saved {name}")


async def get_student_cookies() -> dict:
    """Register a fresh student account and return session cookies."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(f"{BASE}/api/student/auth/register",
            json={"username": STU_USER, "email": STU_EMAIL, "password": STU_PASS})
        r.raise_for_status()
        return dict(r.cookies)


async def get_real_feedback(cookies: dict, question_id: str, answer: str, attempt: int) -> tuple[str, dict | None]:
    """Create a student session, submit answer to SSE endpoint, collect full response."""
    feedback_text = []
    score_data = None

    async with httpx.AsyncClient(timeout=120.0, cookies=cookies) as client:
        if attempt == 1:
            r = await client.post(f"{BASE}/api/student/session/{question_id}/new")
        else:
            r = await client.get(f"{BASE}/api/student/session/{question_id}")
        assert r.status_code == 200, f"Session failed ({r.status_code}): {r.text}"
        session_id = r.json()["session_id"]

        async with client.stream(
            "POST",
            f"{BASE}/api/feedback",
            json={"question_id": question_id, "student_answer": answer,
                  "attempt_number": attempt, "session_id": session_id},
            headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        ) as resp:
            assert resp.status_code == 200, f"Feedback failed ({resp.status_code}): {resp.text[:200]}"
            try:
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    raw = line[6:].strip()
                    if raw == "[DONE]":
                        break
                    try:
                        data = json.loads(raw)
                        if "text" in data:
                            feedback_text.append(data["text"])
                        elif "score" in data:
                            score_data = data["score"]
                    except json.JSONDecodeError:
                        pass
            except Exception:
                pass  # SSE stream closed by server — normal for chunked transfer

    return "".join(feedback_text), score_data


def render_score_html(score: dict) -> str:
    """Build the score HTML that app.js normally builds."""
    total = f"{score['total_awarded']} / {score['total_max']}"
    items = []
    for item in score.get("breakdown", []):
        pct = item["awarded"] / item["max"] if item["max"] else 0
        cls = "score-high" if pct >= 0.75 else ("score-mid" if pct >= 0.4 else "score-low")
        items.append(
            f'<div class="score-item">'
            f'<span class="score-item-label">{item.get("label", "Section")}</span>'
            f'<span class="score-item-value {cls}">{item["awarded"]} / {item["max"]}</span>'
            f'</div>'
        )
    return (
        f'<div class="score-total">{total}</div>'
        f'<div class="score-breakdown">{"".join(items)}</div>'
    )


async def inject_feedback(page, feedback: str, score: dict | None, show_score: bool = True):
    """Inject real feedback and score into the student workspace DOM."""
    fb_js = feedback.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")
    score_html = render_score_html(score).replace("`", "\\`") if score else ""

    await page.evaluate(f"""() => {{
        const fb = document.getElementById('feedback-section');
        const fc = document.getElementById('feedback-content');
        if (fb && fc) {{
            fb.style.display = 'block';
            fc.textContent = `{fb_js}`;
        }}
        const ss = document.getElementById('score-section');
        const sc = document.getElementById('score-content');
        if (ss && sc) {{
            if ({str(show_score and score is not None).lower()} && `{score_html}`) {{
                ss.style.display = 'block';
                sc.innerHTML = `{score_html}`;
            }} else {{
                ss.style.display = 'none';
            }}
        }}
        const ind = document.getElementById('streaming-indicator');
        if (ind) ind.style.display = 'none';
    }}""")


async def run():
    invite = get_invite_code()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        ctx = await browser.new_context(viewport=VIEWPORT)
        page = await ctx.new_page()

        # ── SETUP: register/login instructor, create class + questions ────
        print("Setting up...")

        cleanup_screenshot_classes()

        await page.request.post(f"{BASE}/api/auth/register",
            data=json.dumps({"username": INST_USER, "password": INST_PASS, "invite_code": invite}),
            headers={"Content-Type": "application/json"})
        res = await page.request.post(f"{BASE}/api/auth/login",
            data=json.dumps({"username": INST_USER, "password": INST_PASS}),
            headers={"Content-Type": "application/json"})
        assert res.ok, f"Login failed: {await res.text()}"

        cls_res = await page.request.post(f"{BASE}/api/classes",
            data=json.dumps({"name": "Biology 101"}),
            headers={"Content-Type": "application/json"})
        assert cls_res.ok, f"Create class failed: {await cls_res.text()}"
        cls_data = await cls_res.json()
        CLASS_ID = cls_data["class_id"]

        cd_res = await page.request.post(f"{BASE}/api/questions",
            data=json.dumps({**CELLDIV_QUESTION, "class_id": CLASS_ID}),
            headers={"Content-Type": "application/json"})
        assert cd_res.ok, f"Create Cell Division question failed: {await cd_res.text()}"
        Q_CELLDIV = (await cd_res.json())["id"]

        ph_res = await page.request.post(f"{BASE}/api/questions",
            data=json.dumps({**PHOTOSYN_QUESTION, "class_id": CLASS_ID}),
            headers={"Content-Type": "application/json"})
        assert ph_res.ok, f"Create Photosynthesis question failed: {await ph_res.text()}"

        print(f"  class={CLASS_ID}  Q_CELLDIV={Q_CELLDIV}")

        # ── STUDENT AI CALLS (done early so analytics pages show real data) ─
        print("Student AI calls...")
        student_cookies = await get_student_cookies()

        print("  calling AI for attempt 1 feedback...")
        fb1, score1 = await get_real_feedback(student_cookies, Q_CELLDIV, ANSWER_1, attempt=1)
        print(f"  attempt 1 done — score: {score1.get('total_awarded') if score1 else 'N/A'}/{score1.get('total_max') if score1 else 'N/A'}")

        print("  calling AI for attempt 2 feedback...")
        fb2, score2 = await get_real_feedback(student_cookies, Q_CELLDIV, ANSWER_2, attempt=2)
        print(f"  attempt 2 done — score: {score2.get('total_awarded') if score2 else 'N/A'}/{score2.get('total_max') if score2 else 'N/A'}")

        # ── INSTRUCTOR SCREENSHOTS ────────────────────────────────────────
        print("Instructor pages...")

        # 1. Login page
        await page.goto(f"{BASE}/login")
        await page.wait_for_load_state("networkidle")
        await save(page, "instructor-login.png")

        # 2. Instructor dashboard
        await page.goto(f"{BASE}/instructor")
        await page.wait_for_load_state("networkidle")
        await save(page, "instructor-dashboard.png")

        # 3. Edit mode
        edit_btn = page.locator(".question-card").first.locator("button", has_text="Edit")
        if await edit_btn.count():
            await edit_btn.click()
            await page.wait_for_timeout(500)
            await save(page, "instructor-edit.png")

        # 4. Manage Classes
        await page.goto(f"{BASE}/instructor/classes")
        await page.wait_for_load_state("networkidle")
        await save(page, "instructor-classes.png")

        # 5. Class analytics (attempt data already in DB from student AI calls above)
        await page.goto(f"{BASE}/instructor/classes/{CLASS_ID}/analytics")
        await page.wait_for_load_state("networkidle")
        await save(page, "instructor-analytics-class.png")

        # 6. Question analytics
        await page.goto(f"{BASE}/instructor/analytics/{Q_CELLDIV}")
        await page.wait_for_load_state("networkidle")
        await save(page, "instructor-analytics-question.png")

        # 7. Answers expanded
        expand_btn = page.locator("button", has_text="Show answers").first
        if await expand_btn.count():
            await expand_btn.click()
            await page.wait_for_timeout(400)
        await save(page, "instructor-analytics-answers.png")

        # 8. Export links
        await page.goto(f"{BASE}/instructor/classes/{CLASS_ID}/analytics")
        await page.wait_for_load_state("networkidle")
        export = page.locator(".export-links")
        if await export.count():
            await export.scroll_into_view_if_needed()
        await save(page, "instructor-analytics-export.png")

        # ── STUDENT SCREENSHOTS ───────────────────────────────────────────
        print("Student pages...")
        sp = await ctx.new_page()

        # 9. Student landing
        await sp.goto(f"{BASE}/student")
        await sp.wait_for_load_state("networkidle")
        await sp.wait_for_timeout(400)
        anon = sp.locator("a", has_text="Continue anonymously")
        if await anon.count():
            await anon.click()
            await sp.wait_for_timeout(300)
        await save(sp, "student-landing.png")

        # 10. Question list
        await sp.goto(f"{BASE}/student/{CLASS_ID}")
        await sp.wait_for_load_state("networkidle")
        await save(sp, "student-question-list.png")

        # 11. Student workspace (blank)
        await sp.goto(f"{BASE}/student/{CLASS_ID}/{Q_CELLDIV}")
        await sp.wait_for_load_state("networkidle")
        await sp.wait_for_timeout(500)
        await save(sp, "student-workspace.png")

        # 12. First attempt feedback (text only, no score yet)
        await sp.locator("#student-answer").fill(ANSWER_1)
        await inject_feedback(sp, fb1, score1, show_score=False)
        await save(sp, "student-feedback.png")

        # 13. First attempt feedback with score
        await inject_feedback(sp, fb1, score1, show_score=True)
        await save(sp, "student-feedback-scored.png")

        # 14. Revision — attempt 2 answer + feedback (includes PROGRESS section)
        await sp.locator("#student-answer").fill(ANSWER_2)
        await inject_feedback(sp, fb2, score2, show_score=True)
        await save(sp, "student-revision.png")

        # 15. Session history
        s1_total = f"{score1['total_awarded']} / {score1['total_max']}" if score1 else "—"
        s2_total = f"{score2['total_awarded']} / {score2['total_max']}" if score2 else "—"
        await sp.evaluate(f"""() => {{
            const hc = document.getElementById('history-content');
            const ht = document.getElementById('history-toggle-text');
            if (hc && ht) {{
                ht.textContent = 'Hide Revision History';
                hc.style.display = 'block';
                hc.innerHTML = `
                  <div class="history-attempt">
                    <div class="history-attempt-label">Attempt 1</div>
                    <div style="font-size:0.82rem;color:var(--text-muted);margin-top:0.15rem;">
                      Score: {s1_total}</div>
                  </div>
                  <div class="history-attempt">
                    <div class="history-attempt-label">Attempt 2 — current</div>
                    <div style="font-size:0.82rem;color:var(--teal-dark);font-weight:600;margin-top:0.15rem;">
                      Score: {s2_total}</div>
                  </div>`;
            }}
        }}""")
        await save(sp, "student-session-history.png")

        await browser.close()
        print(f"\nAll done — screenshots saved to {OUT}")


if __name__ == "__main__":
    asyncio.run(run())
