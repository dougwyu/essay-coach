# Essay Coach

A local web application that helps university students iteratively improve essay answers through structured AI feedback. Instructors create classes, set questions with model answers, and share a class code with students. The AI compares student work against the hidden model answers and returns directional feedback. The student never sees the model answer. Multiple instructors can run separate classes on a single instance. 

The goal of Essay Coach is to help students 'learn the shape' of a good answer to an exam essay question. Essay Coach is not designed to be used for real exams, nor is it for teaching how to write well. It automates formative feedback, not summative feedback. 

The approach is to give the students access to last year's exam questions (or mock questions) at the beginning of term so that the students can practice answering questions during the term. I hypothesise that this will help the students 'learn how to learn' the material, ultimately helping them do better on the exam. I also hypothesise that Essay Coach will need to be introduced in a workshop, so that the students who need it the most are at least exposed to it. You can lead a horse to water... 

![Essay Coach Infographic](essaycoachinfographic_notebookLM_20270327.png)

## Setup

This version assumes that you have a Claude API key, which is available for purchase at [Claude Dashboard](https://platform.claude.com/dashboard). Future versions will allow substitution with a locally running LLM like ollama or deepseek.

```bash
pip install -r requirements.txt
cp .env.example .env  # add your ANTHROPIC_API_KEY
python app.py         # runs on localhost:8000
```

## Usage

- **Instructor view** (`/instructor`): Create and manage classes and essay questions. Requires login — register at `/register` using the invite code printed in the terminal on first startup. Go to **Manage Classes** to create a class and get its student access code.
- **Student view** (`/student`): Optionally sign in or create an account, enter your class code, select a question, write an answer, and receive structured AI feedback. Revise and resubmit to improve. Login is optional — anonymous use is supported, but a student account preserves history across browsers and devices.
- **Analytics** (`/instructor/classes/{id}/analytics`): Per-class summary showing sessions, average attempts, average score, and a score distribution bar for each question. Drill into any question for per-session detail — attempt counts, score progression, and expandable student answers. Download links on each analytics page export session data as CSV or JSON.

## How Feedback Works

The AI compares student answers against the instructor's model answer but **never reveals** the model answer directly. Feedback is structured as:

- **Coverage**: Which key concepts are present, partially present, or missing
- **Depth**: Where reasoning needs to go deeper
- **Structure**: How the argument's organization could improve
- **Accuracy**: Any factual errors or misconceptions
- **Progress** (attempt 2+): What improved since last attempt
- **Score** (optional): If the instructor annotated their model answer with point values (e.g. `[3]` at the end of a paragraph), students receive a numeric score after each submission showing points earned per section

Feedback becomes more specific with each attempt, guiding students toward discovering the shape of a good answer through revision.

For a full walkthrough (user guide + developer guide), see [docs/tutorial.md](docs/tutorial.md).

## License

Copyright (C) 2026 Douglas Yu

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, version 3. See [LICENSE](LICENSE) for details.

## Built With

This application was built by [Claude Code](https://claude.ai/claude-code), Anthropic's agentic coding tool. Claude Code generated the full stack — backend, frontend, database schema, AI feedback engine, tests, and documentation — from a single architectural prompt.

The development workflow was powered by the **[Superpowers](https://github.com/obra/superpowers)** plugin for Claude Code. Superpowers adds structured, skill-based workflows on top of Claude Code: brainstorming sessions that turn ideas into reviewed design specs, plan documents with bite-sized TDD steps, and subagent-driven execution where a fresh Claude subagent handles each task and two-stage review (spec compliance, then code quality) gates every merge. The result is a disciplined, reviewable process that produces better code with fewer regressions than ad-hoc prompting.

**Install Superpowers** (run this in your terminal, not inside Claude Code):

```bash
claude plugin install superpowers@claude-plugins-official
```

Superpowers is described in the [Claude plugin store](https://claude.com/plugins/superpowers).
