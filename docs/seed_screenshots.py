#!/usr/bin/env python3
"""Seed the Essay Coach database with demo data for screenshots.

Run against a freshly started server:
    python docs/seed_screenshots.py

The script prints the instructor password and class codes so you can log in.
"""
import requests
import sqlite3
import uuid
import json

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


def seed_attempts(question_id, session_id, attempts):
    """Seed attempts directly into the DB (bypasses LLM)."""
    db = sqlite3.connect("essay_coach.db")
    for i, (answer, feedback, score_data) in enumerate(attempts, 1):
        score_json = json.dumps(score_data) if score_data else None
        db.execute(
            "INSERT INTO attempts "
            "(question_id, session_id, student_answer, feedback, attempt_number, score_data) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (question_id, session_id, answer, feedback, i, score_json),
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

    # ── Question 1: Photosynthesis (scored) ──────────────────────────────
    q1 = create_question(
        title="Photosynthesis",
        prompt=(
            "Explain the process of photosynthesis, including the light-dependent "
            "and light-independent reactions. Where does each stage occur, and what "
            "are the key inputs and outputs?"
        ),
        model_answer=(
            "Photosynthesis occurs in two stages. "
            "The light-dependent reactions in the thylakoid membranes use sunlight "
            "to split water molecules, releasing oxygen and producing ATP and NADPH. [4] "
            "The Calvin cycle (light-independent reactions) takes place in the stroma "
            "and uses the ATP and NADPH to fix CO₂ into glucose via the enzyme RuBisCO. [4] "
            "The net equation is: 6CO₂ + 6H₂O + light energy → C₆H₁₂O₆ + 6O₂. [2]"
        ),
        rubric=(
            "- Must distinguish light-dependent vs. light-independent reactions\n"
            "- Must name thylakoid membranes and stroma as locations\n"
            "- Must include the overall equation or equivalent\n"
            "- Must mention ATP and NADPH as products of light reactions"
        ),
        class_id=class_id,
    )

    # Session 1: 3 attempts, strong improvement arc
    sid1 = str(uuid.uuid4())
    seed_attempts(q1, sid1, [
        (
            "Photosynthesis uses sunlight to make food. Plants absorb light and produce oxygen.",
            (
                "**Coverage:** You've identified that sunlight is involved and that oxygen is produced, "
                "but the two distinct stages (light-dependent and light-independent reactions) are missing entirely.\n\n"
                "**Depth:** There's no mention of where photosynthesis occurs within the cell, "
                "what molecules are produced beyond oxygen, or how CO₂ is incorporated.\n\n"
                "**Structure:** The answer reads as a single general statement rather than an organized explanation.\n\n"
                "**Score:** 2/10 — Captures the basic idea but lacks almost all specific content."
            ),
            {"total_awarded": 2, "total_max": 10},
        ),
        (
            "Photosynthesis has two stages: the light reactions and the Calvin cycle. "
            "The light reactions happen in the thylakoids and produce ATP. "
            "The Calvin cycle uses ATP to make glucose from CO₂.",
            (
                "**Coverage:** Good — you now identify both stages and their locations. "
                "NADPH is missing from the products of the light reactions.\n\n"
                "**Depth:** The light reactions need more detail: water is split to release oxygen, "
                "and both ATP and NADPH are produced. The Calvin cycle explanation is brief but correct.\n\n"
                "**Progress:** Strong improvement from attempt 1 — you've added the two-stage structure "
                "and named the thylakoid correctly.\n\n"
                "**Score:** 7/10 — Core structure is right; missing NADPH and the overall equation."
            ),
            {"total_awarded": 7, "total_max": 10},
        ),
        (
            "The light-dependent reactions occur in the thylakoid membranes. Sunlight splits water, "
            "releasing O₂ and producing ATP and NADPH. The Calvin cycle in the stroma uses ATP and NADPH "
            "to fix CO₂ into glucose via RuBisCO. Net equation: 6CO₂ + 6H₂O + light → C₆H₁₂O₆ + 6O₂.",
            (
                "**Coverage:** Excellent — both stages, both locations, key molecules, enzyme name, "
                "and the overall equation are all present.\n\n"
                "**Depth:** The explanation correctly traces the energy flow from light → ATP/NADPH → glucose.\n\n"
                "**Progress:** Major improvement from attempt 2 — you added NADPH, RuBisCO, and the net equation.\n\n"
                "**Score:** 9/10 — Very strong answer. Minor point: the role of water splitting in "
                "releasing electrons for the electron transport chain could be made explicit."
            ),
            {"total_awarded": 9, "total_max": 10},
        ),
    ])

    # Session 2: 2 attempts, moderate improvement
    sid2 = str(uuid.uuid4())
    seed_attempts(q1, sid2, [
        (
            "Plants absorb sunlight and convert CO2 and water into sugar and oxygen. "
            "This happens in the chloroplasts.",
            (
                "**Coverage:** You mention chloroplasts (correct) and the basic inputs/outputs, "
                "but the two-stage structure is absent.\n\n"
                "**Depth:** No distinction between thylakoid and stroma, no ATP or NADPH, "
                "no Calvin cycle.\n\n"
                "**Score:** 3/10 — Basic inputs and outputs plus chloroplast location is a reasonable start."
            ),
            {"total_awarded": 3, "total_max": 10},
        ),
        (
            "The light reactions happen in the thylakoid membranes and use light to produce ATP and NADPH, "
            "releasing oxygen from water. The Calvin cycle in the stroma uses this ATP and NADPH to make "
            "glucose from CO₂.",
            (
                "**Coverage:** Both stages and locations covered. ATP and NADPH correctly identified.\n\n"
                "**Depth:** Good explanation of energy transfer between the two stages. "
                "The overall equation is missing.\n\n"
                "**Progress:** Big jump from attempt 1 — you've added the two-stage structure, "
                "thylakoid/stroma locations, and the key intermediate molecules.\n\n"
                "**Score:** 7/10 — Solid answer; add the net equation to round it out."
            ),
            {"total_awarded": 7, "total_max": 10},
        ),
    ])

    # ── Question 2: Cell Division (scored) ───────────────────────────────
    q2 = create_question(
        title="Cell Division",
        prompt=(
            "Describe the key differences between mitosis and meiosis. "
            "Include the number and type of daughter cells produced, "
            "and explain the biological purpose of each process."
        ),
        model_answer=(
            "Mitosis produces two genetically identical diploid daughter cells "
            "and is used for growth, tissue repair, and asexual reproduction. [3] "
            "Meiosis produces four genetically unique haploid cells (gametes) "
            "and is used for sexual reproduction. [3] "
            "Key differences: meiosis involves two rounds of cell division, "
            "crossing-over between homologous chromosomes in prophase I (creating genetic variation), "
            "and separation of homologous pairs in meiosis I. [4]"
        ),
        rubric=(
            "- Must contrast ploidy (diploid vs. haploid)\n"
            "- Must state the number of daughter cells (2 vs. 4)\n"
            "- Must describe the biological purpose of each\n"
            "- Must mention genetic variation / crossing-over for meiosis"
        ),
        class_id=class_id,
    )

    # Session 3: 2 attempts
    sid3 = str(uuid.uuid4())
    seed_attempts(q2, sid3, [
        (
            "Mitosis makes copies of cells for growth. Meiosis makes sex cells with half the chromosomes.",
            (
                "**Coverage:** You've captured the core distinction (growth vs. reproduction, "
                "diploid vs. haploid) but the number of daughter cells and genetic variation are missing.\n\n"
                "**Depth:** No mention of crossing-over, the two-round structure of meiosis, "
                "or the term 'gametes'.\n\n"
                "**Score:** 4/10 — Core idea is correct; needs more specifics."
            ),
            {"total_awarded": 4, "total_max": 10},
        ),
        (
            "Mitosis produces 2 genetically identical diploid cells for growth and tissue repair. "
            "Meiosis produces 4 haploid gametes for sexual reproduction. "
            "Meiosis involves two rounds of division and crossing-over in prophase I, "
            "which creates genetic variation.",
            (
                "**Coverage:** Excellent — number of cells, ploidy, purpose, two rounds of division, "
                "and crossing-over are all present.\n\n"
                "**Depth:** The answer correctly connects crossing-over to genetic variation. "
                "Could mention homologous chromosome separation in meiosis I for completeness.\n\n"
                "**Progress:** Strong improvement — you added ploidy, gamete count, and the mechanism "
                "of genetic variation.\n\n"
                "**Score:** 8/10 — Very complete answer."
            ),
            {"total_awarded": 8, "total_max": 10},
        ),
    ])

    print("\n─── Seeding complete ───────────────────────────────────────")
    print(f"Log in at:        {BASE}/login")
    print(f"Credentials:      {username} / {password}")
    print(f"Class analytics:  {BASE}/instructor/classes/{class_id}/analytics")
    print()
    print("Next: capture screenshots per docs/superpowers/plans/2026-03-25-screenshots.md")


if __name__ == "__main__":
    main()
