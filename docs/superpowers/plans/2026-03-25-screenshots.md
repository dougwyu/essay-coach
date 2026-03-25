# Screenshots Implementation Plan

> **For agentic workers:** This plan requires a running Essay Coach server with seeded test data. Screenshots must be taken manually in a browser (or via an automated tool like Playwright). Steps marked `[manual]` cannot be automated without browser access.

**Goal:** Capture a complete set of screenshots covering every major UI state and embed them throughout the tutorial, replacing the placeholder references where they exist and adding new ones where the tutorial currently has none.

**Architecture:** All screenshots live in `docs/images/`. Tutorial references them as `![caption](images/filename.png)`. The seeding script (`docs/seed_screenshots.py`) creates a consistent, realistic dataset so screenshots look meaningful rather than empty.

**Tech Stack:** Python (seed script), browser (manual capture or Playwright), Markdown image embeds

---

## Current Screenshot Inventory

Already referenced in `docs/tutorial.md` (files may or may not exist yet):

| File | Tutorial location |
|------|------------------|
| `images/instructor-dashboard.png` | Before the Create Question form table |
| `images/instructor-edit.png` | In the Editing/Deleting section |
| `images/student-question-list.png` | In the Selecting a Question section |
| `images/student-workspace.png` | In the Writing section |
| `images/student-feedback.png` | In the Writing section, after submit |

---

## Planned Screenshots

### New screenshots to capture and embed

| File | Page / state | Tutorial section |
|------|-------------|-----------------|
| `images/student-landing.png` | `/student` — class code entry form (empty) | Entering Your Class Code |
| `images/instructor-login.png` | `/login` — login form | Signing In |
| `images/instructor-classes.png` | `/instructor/classes` — class list with student/instructor codes visible | Managing Classes |
| `images/instructor-analytics-class.png` | `/instructor/classes/{id}/analytics` — class summary table with score bars | Class Analytics Summary |
| `images/instructor-analytics-question.png` | `/instructor/analytics/{id}` — session detail table, answers collapsed | Per-Question Session Detail |
| `images/instructor-analytics-answers.png` | Same page — one row with answers expanded | Per-Question Session Detail (Show Answers) |
| `images/instructor-analytics-export.png` | Either analytics page — header with Download CSV · JSON links visible | Exporting Data |
| `images/student-feedback-scored.png` | Student workspace after submit — feedback with numeric score visible | Reading Your Feedback |
| `images/student-revision.png` | Student workspace after second submit — Progress section visible in feedback | Revising Your Answer |

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `docs/seed_screenshots.py` | Seed script: creates instructor account, class, questions, student attempts |
| Modify | `docs/tutorial.md` | Insert `![caption](images/filename.png)` at appropriate locations |
| Create | `docs/images/*.png` | Actual screenshot files (captured manually or via Playwright) |

---

## Tasks

### Task 1: Write the seed script

**File:** `docs/seed_screenshots.py`

This script runs against a live server to create realistic demo data. Run it once after starting the server with a fresh database.

- [ ] **Step 1: Write `docs/seed_screenshots.py`**

```python
#!/usr/bin/env python3
"""Seed the Essay Coach database with demo data for screenshots.

Run against a freshly started server:
    python docs/seed_screenshots.py

The script prints the instructor password and class codes so you can log in.
"""
import requests
import sqlite3
import sys

BASE = "http://localhost:8000"
session = requests.Session()


def get_invite_code():
    db = sqlite3.connect("essay_coach.db")
    row = db.execute("SELECT value FROM settings WHERE key='invite_code'").fetchone()
    db.close()
    return row[0]


def register(username, password, invite_code):
    r = session.post(f"{BASE}/api/auth/register", json={
        "username": username,
        "password": password,
        "invite_code": invite_code,
    })
    r.raise_for_status()
    print(f"Registered instructor: {username} / {password}")


def create_class(name):
    r = session.post(f"{BASE}/api/classes", json={"name": name})
    r.raise_for_status()
    data = r.json()
    print(f"Created class '{name}': student code={data['student_code']}, id={data['class_id']}")
    return data["class_id"]


def create_question(title, prompt, model_answer, rubric, class_id):
    r = session.post(f"{BASE}/api/questions", json={
        "title": title,
        "prompt": prompt,
        "model_answer": model_answer,
        "rubric": rubric,
        "class_id": class_id,
    })
    r.raise_for_status()
    qid = r.json()["id"]
    print(f"Created question '{title}': id={qid}")
    return qid


def seed_attempts(question_id, session_id, answers_and_scores):
    """Seed attempts directly into the DB (bypasses LLM)."""
    db = sqlite3.connect("essay_coach.db")
    for i, (answer, score_data) in enumerate(answers_and_scores, 1):
        import json
        score_json = json.dumps(score_data) if score_data else None
        db.execute(
            "INSERT INTO attempts (question_id, session_id, student_answer, feedback, attempt_number, score_data) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (question_id, session_id, answer,
             "Good attempt. Try expanding your explanation of the mechanism.",
             i, score_json),
        )
    db.commit()
    db.close()


def main():
    invite = get_invite_code()

    # Instructor account
    username, password = "demo_instructor", "demo_password"
    register(username, password, invite)

    # Class: Biology 101
    class_id = create_class("Biology 101")

    # Question 1: scored
    q1 = create_question(
        title="Photosynthesis",
        prompt="Explain the process of photosynthesis, including the light-dependent and light-independent reactions.",
        model_answer=(
            "Photosynthesis occurs in two stages. "
            "The light-dependent reactions in the thylakoid membranes use sunlight to split water and produce ATP and NADPH. [4] "
            "The Calvin cycle (light-independent reactions) in the stroma uses that ATP and NADPH to fix CO₂ into glucose. [4] "
            "The net equation is: 6CO₂ + 6H₂O + light → C₆H₁₂O₆ + 6O₂. [2]"
        ),
        rubric="- Light-dependent vs. light-independent reactions must be distinct\n- Must name thylakoid and stroma\n- Must include overall equation",
        class_id=class_id,
    )

    # Question 2: scored
    q2 = create_question(
        title="Cell Division",
        prompt="Describe the key differences between mitosis and meiosis.",
        model_answer=(
            "Mitosis produces two genetically identical daughter cells and is used for growth and repair. [3] "
            "Meiosis produces four genetically unique haploid cells and is used for sexual reproduction. [3] "
            "Key differences: meiosis involves two rounds of division, crossing-over in prophase I, and homologous chromosome separation. [4]"
        ),
        rubric="- Must contrast ploidy (diploid vs. haploid)\n- Must mention genetic variation in meiosis",
        class_id=class_id,
    )

    # Seed attempts for question 1 (two sessions)
    import uuid
    sid1 = str(uuid.uuid4())
    seed_attempts(q1, sid1, [
        ("Photosynthesis uses sunlight to make food. Plants absorb light and produce oxygen.",
         {"total_awarded": 2, "total_max": 10}),
        ("Photosynthesis has two stages: light reactions in thylakoids produce ATP, and the Calvin cycle uses ATP to make glucose.",
         {"total_awarded": 7, "total_max": 10}),
        ("The light-dependent reactions split water in the thylakoid membranes, producing ATP and NADPH. The Calvin cycle in the stroma fixes CO₂ into glucose. Net: 6CO₂ + 6H₂O → C₆H₁₂O₆ + 6O₂.",
         {"total_awarded": 9, "total_max": 10}),
    ])

    sid2 = str(uuid.uuid4())
    seed_attempts(q1, sid2, [
        ("Plants absorb sunlight and convert CO2 and water into sugar and oxygen.",
         {"total_awarded": 3, "total_max": 10}),
        ("The light reactions happen in the thylakoid and produce ATP. The Calvin cycle uses this to make glucose from CO2.",
         {"total_awarded": 7, "total_max": 10}),
    ])

    # Seed attempts for question 2 (one session)
    sid3 = str(uuid.uuid4())
    seed_attempts(q2, sid3, [
        ("Mitosis makes copies of cells. Meiosis makes sex cells with half the chromosomes.",
         {"total_awarded": 4, "total_max": 10}),
        ("Mitosis produces 2 diploid cells for growth and repair. Meiosis produces 4 haploid cells for reproduction, and includes crossing-over for genetic variation.",
         {"total_awarded": 8, "total_max": 10}),
    ])

    print("\n--- Done ---")
    print(f"Log in at {BASE}/login as: {username} / {password}")
    print(f"Class analytics: {BASE}/instructor/classes/{class_id}/analytics")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify the script runs**

```bash
# Start a fresh server first, then:
python docs/seed_screenshots.py
```

Expected: Prints class ID, question IDs, and login URL. No errors.

- [ ] **Step 3: Commit**

```bash
git add docs/seed_screenshots.py
git commit -m "docs: add screenshot seed script"
```

---

### Task 2: Capture screenshots `[manual]`

With the server running after seeding, capture each screenshot below. Use 1280×800 browser window. Save as PNG to `docs/images/`.

**Before capturing:** Log in to the instructor account created by the seed script.

#### Screenshots to capture (in order)

1. **`student-landing.png`** — Navigate to `http://localhost:8000/student` while logged out. Capture the class code entry form before entering anything.

2. **`instructor-login.png`** — Navigate to `http://localhost:8000/login`. Capture the login form (empty).

3. **`instructor-dashboard.png`** *(re-capture to show seeded questions)* — Navigate to `http://localhost:8000/instructor`. Capture the full dashboard showing the question cards with attempt counts and the class filter.

4. **`instructor-edit.png`** *(re-capture if needed)* — Click **Edit** on a question card to load it into the form. Capture the left-side form with data filled in.

5. **`instructor-classes.png`** — Navigate to `http://localhost:8000/instructor/classes`. Capture the class list showing the Biology 101 class with its student and instructor codes.

6. **`instructor-analytics-class.png`** — Navigate to the class analytics page (URL printed by the seed script). Capture the full table showing both questions with score distribution bars.

7. **`instructor-analytics-question.png`** — Click **View →** on the Photosynthesis row. Capture the session detail page showing both sessions with score progression, answers collapsed.

8. **`instructor-analytics-answers.png`** — On the same page, click **▶ Show answers** on the first session row. Capture the expanded answer panel.

9. **`instructor-analytics-export.png`** — Capture the analytics header area (crop tightly) showing the "Download: CSV · JSON" links in the top-right corner. Either analytics page works.

10. **`student-question-list.png`** *(re-capture to show seeded questions)* — Open a private/incognito window, navigate to `http://localhost:8000/student`, enter the student code for Biology 101, and capture the question list.

11. **`student-workspace.png`** *(re-capture)* — Click on the Photosynthesis question. Capture the empty workspace (prompt visible, answer area empty, no feedback yet).

12. **`student-feedback.png`** *(re-capture or use existing if good)* — Submit an answer and capture the workspace with AI feedback streaming or complete. Should show the Coverage/Depth/Structure sections.

13. **`student-feedback-scored.png`** — After submitting with the seeded question (which has `[4]` markers), capture the feedback panel showing the numeric score breakdown at the bottom.

14. **`student-revision.png`** — Submit a second attempt on the same question. Capture the feedback panel showing the **Progress** section ("What improved since your last attempt").

- [ ] **Step 4: Confirm all 14 files exist in `docs/images/`**

```bash
ls docs/images/
```

- [ ] **Step 5: Commit screenshots**

```bash
git add docs/images/
git commit -m "docs: add/update tutorial screenshots"
```

---

### Task 3: Insert image references in tutorial

Embed the new screenshots at the appropriate locations in `docs/tutorial.md`.

#### Insertions needed

**Signing In section** — After "Navigate to `http://localhost:8000/login`..." text:
```markdown
![Instructor login page](images/instructor-login.png)
```

**Entering Your Class Code section** — After the first paragraph explaining how to enter a code:
```markdown
![Student class code entry](images/student-landing.png)
```

**Managing Classes section** — After the paragraph describing how to view class codes:
```markdown
![Class management page](images/instructor-classes.png)
```

**Class Analytics Summary section** — After the table describing the columns:
```markdown
![Class analytics summary](images/instructor-analytics-class.png)
```

**Per-Question Session Detail section** — After the description of score progression:
```markdown
![Per-question session detail](images/instructor-analytics-question.png)
```

After the "Show answers" paragraph:
```markdown
![Session with answers expanded](images/instructor-analytics-answers.png)
```

**Exporting Data section** — After the two bullet points:
```markdown
![Export download links](images/instructor-analytics-export.png)
```

**Reading Your Feedback section** — After the scored feedback description:
```markdown
![AI feedback with score](images/student-feedback-scored.png)
```

**Revising Your Answer section** — After describing the Progress section:
```markdown
![Feedback showing progress from previous attempt](images/student-revision.png)
```

- [ ] **Step 6: Read each target location and insert image references**

Use the Edit tool to add each `![caption](images/filename.png)` line at the location described above. Read the relevant section first to find the exact insertion point.

- [ ] **Step 7: Run a quick sanity check**

```bash
# Verify all referenced image files exist
grep -o 'images/[^)]*' docs/tutorial.md | sort -u | while read f; do
  [ -f "docs/$f" ] && echo "OK: $f" || echo "MISSING: $f"
done
```

Expected: all lines print "OK".

- [ ] **Step 8: Commit**

```bash
git add docs/tutorial.md
git commit -m "docs: embed screenshots throughout tutorial"
```

---

## After All Tasks

The tutorial will have 14 screenshots covering every major UI state. Run a final check:

```bash
grep -c '!\[' docs/tutorial.md
```

Expected: 14 (or more if the existing 5 were already correct and are counted).
