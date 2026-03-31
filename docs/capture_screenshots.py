"""
Screenshot capture script for Essay Coach tutorial.
Run from the essay-coach directory with the server running on port 8000.
Usage: python docs/capture_screenshots.py
"""

import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright

BASE = "http://localhost:8000"
OUT  = Path(__file__).parent / "images"

CLASS_ID   = "3eadff64-6bf0-4157-ac53-697e1c4dbee6"
CLASS_CODE = "148D0E8Z"
INST_CODE  = "E2I147ZN"
Q_PHOTOSYN = "6e39218b-0c3c-4b60-a5cc-d0537870e0d2"
Q_CELLDIV  = "5046cb75-717f-4b98-bee1-d072726f0317"
INST_USER  = "screenshot_user"
INST_PASS  = "screenshotpass1"
INVITE     = "L5OUPWZ1"

VIEWPORT = {"width": 1440, "height": 900}


async def save(page, name: str):
    path = OUT / name
    await page.screenshot(path=str(path), full_page=False)
    print(f"  saved {name}")


async def run():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()

        # ── INSTRUCTOR SCREENSHOTS ────────────────────────────────
        print("Instructor pages...")
        ctx = await browser.new_context(viewport=VIEWPORT)
        page = await ctx.new_page()

        # 1. Login page
        await page.goto(f"{BASE}/login")
        await page.wait_for_load_state("networkidle")
        await save(page, "instructor-login.png")

        # Register + join class + log in
        await page.request.post(f"{BASE}/api/auth/register",
            data=json.dumps({"username": INST_USER, "password": INST_PASS, "invite_code": INVITE}),
            headers={"Content-Type": "application/json"})
        res = await page.request.post(f"{BASE}/api/auth/login",
            data=json.dumps({"username": INST_USER, "password": INST_PASS}),
            headers={"Content-Type": "application/json"})
        assert res.ok, f"Login failed: {await res.text()}"
        await page.request.post(f"{BASE}/api/classes/join",
            data=json.dumps({"instructor_code": INST_CODE}),
            headers={"Content-Type": "application/json"})

        # 2. Instructor dashboard
        await page.goto(f"{BASE}/instructor")
        await page.wait_for_load_state("networkidle")
        await save(page, "instructor-dashboard.png")

        # 3. Edit mode (click Edit on first question)
        edit_btn = page.locator(".question-card").first.locator("button", has_text="Edit")
        if await edit_btn.count():
            await edit_btn.click()
            await page.wait_for_timeout(500)
            await save(page, "instructor-edit.png")

        # 4. Manage Classes
        await page.goto(f"{BASE}/instructor/classes")
        await page.wait_for_load_state("networkidle")
        await save(page, "instructor-classes.png")

        # 5. Class analytics
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

        # ── STUDENT SCREENSHOTS ───────────────────────────────────
        # Reuse the same context (new page) — avoids connection resets
        print("Student pages...")
        sp = await ctx.new_page()

        # 9. Student landing — show class code panel
        await sp.goto(f"{BASE}/student")
        await sp.wait_for_load_state("networkidle")
        await sp.wait_for_timeout(400)
        anon = sp.locator("a", has_text="Continue anonymously")
        if await anon.count():
            await anon.click()
            await sp.wait_for_timeout(300)
        await save(sp, "student-landing.png")

        # 10. Question list — navigate directly to class question list
        await sp.goto(f"{BASE}/student/{CLASS_ID}")
        await sp.wait_for_load_state("networkidle")
        await save(sp, "student-question-list.png")

        # 11. Student workspace (blank)
        await sp.goto(f"{BASE}/student/{CLASS_ID}/{Q_CELLDIV}")
        await sp.wait_for_load_state("networkidle")
        await sp.wait_for_timeout(500)
        await save(sp, "student-workspace.png")

        # Fill answer text
        textarea = sp.locator("#student-answer")
        await textarea.fill(
            "Mitosis produces two genetically identical diploid daughter cells and is used "
            "for growth and tissue repair. Meiosis produces four genetically unique haploid "
            "cells and is used for sexual reproduction. Mitosis involves one division; meiosis "
            "involves two divisions (meiosis I separates homologous chromosomes, meiosis II "
            "separates sister chromatids). Crossing over during meiosis I generates genetic "
            "variation."
        )

        # 12. Feedback (mock)
        await sp.evaluate("""() => {
            const fb = document.getElementById('feedback-section');
            const fc = document.getElementById('feedback-content');
            if (fb && fc) {
                fb.style.display = 'block';
                fc.textContent = 'COVERAGE: You have correctly identified the main outcomes '
                    + 'of both processes and noted the number of divisions involved in meiosis. '
                    + 'Consider whether your answer fully addresses why the chromosome number '
                    + 'changes during meiosis and what biological purpose this serves.\\n\\n'
                    + 'DEPTH: Your explanation of the two meiotic divisions is on the right '
                    + 'track. Think about whether you have described the specific chromosomal '
                    + 'events that generate genetic variation, and at what stage these occur.\\n\\n'
                    + 'ACCURACY: No factual errors. A numerical score will follow.';
            }
            const ss = document.getElementById('score-section');
            if (ss) ss.style.display = 'none';
        }""")
        await save(sp, "student-feedback.png")

        # 13. Feedback with score
        await sp.evaluate("""() => {
            const ss = document.getElementById('score-section');
            const sc = document.getElementById('score-content');
            if (ss && sc) {
                ss.style.display = 'block';
                sc.innerHTML = `
                  <div class="score-total">9 / 12</div>
                  <div class="score-breakdown">
                    <div class="score-item">
                      <span class="score-item-label">Section 1</span>
                      <span class="score-item-value score-high">3 / 3</span>
                    </div>
                    <div class="score-item">
                      <span class="score-item-label">Section 2</span>
                      <span class="score-item-value score-high">3 / 3</span>
                    </div>
                    <div class="score-item">
                      <span class="score-item-label">Section 3</span>
                      <span class="score-item-value score-mid">2 / 3</span>
                    </div>
                    <div class="score-item">
                      <span class="score-item-label">Section 4</span>
                      <span class="score-item-value score-mid">1 / 3</span>
                    </div>
                  </div>`;
            }
        }""")
        await save(sp, "student-feedback-scored.png")

        # 14. Revision (previous attempt shown)
        await sp.evaluate("""() => {
            const fc = document.getElementById('feedback-content');
            if (fc) {
                fc.textContent = 'PROGRESS: Improved from your previous attempt (5/12 → 9/12)! '
                    + 'You now address genetic variation more specifically. '
                    + 'Still to develop: consider whether your answer fully explains '
                    + 'the significance of the chromosome number change and why it matters '
                    + 'for the next stage of the life cycle.';
            }
        }""")
        await save(sp, "student-revision.png")

        # 15. Session history (mock)
        await sp.evaluate("""() => {
            const hs = document.getElementById('history-sidebar');
            const hc = document.getElementById('history-content');
            const ht = document.getElementById('history-toggle-text');
            if (hs && hc && ht) {
                ht.textContent = 'Hide Revision History';
                hc.style.display = 'block';
                hc.innerHTML = `
                  <div class="history-attempt">
                    <div class="history-attempt-label">Attempt 1</div>
                    <div style="font-size:0.82rem;color:var(--text-muted);margin-top:0.15rem;">
                      Score: 5 / 12</div>
                  </div>
                  <div class="history-attempt">
                    <div class="history-attempt-label">Attempt 2 — current</div>
                    <div style="font-size:0.82rem;color:var(--teal-dark);font-weight:600;margin-top:0.15rem;">
                      Score: 9 / 12</div>
                  </div>`;
            }
        }""")
        await save(sp, "student-session-history.png")

        await browser.close()
        print(f"\nAll done — screenshots saved to {OUT}")


if __name__ == "__main__":
    asyncio.run(run())
