# Essay Coach

A local web application that helps university students iteratively improve essay answers through structured AI feedback. Instructors provide model answers that students never see; the AI compares student work against these hidden answers and returns directional feedback.

## Setup

This version assumes that you have a Claude API key, which is available for purchase at [Claude Dashboard](https://platform.claude.com/dashboard). Future versions will allow substitution with a locally running LLM like ollama or deepseek.

```bash
pip install -r requirements.txt
cp .env.example .env  # add your ANTHROPIC_API_KEY
python app.py         # runs on localhost:8000
```

## Usage

- **Instructor view** (`/instructor`): Create and manage essay questions with model answers and rubrics.
- **Student view** (`/student`): Select a question, write an answer, and receive structured AI feedback. Revise and resubmit to improve.

## How Feedback Works

The AI compares student answers against the instructor's model answer but **never reveals** the model answer directly. Feedback is structured as:

- **Coverage**: Which key concepts are present, partially present, or missing
- **Depth**: Where reasoning needs to go deeper
- **Structure**: How the argument's organization could improve
- **Accuracy**: Any factual errors or misconceptions
- **Progress** (attempt 2+): What improved since last attempt

Feedback becomes more specific with each attempt, guiding students toward discovering the shape of a good answer through revision.

For a full walkthrough (user guide + developer guide), see [docs/tutorial.md](docs/tutorial.md).

## License

Copyright (C) 2026 Douglas Yu

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, version 3. See [LICENSE](LICENSE) for details.

## Built With

This application was built entirely by [Claude Code](https://claude.ai/claude-code), Anthropic's agentic coding tool. Claude Code generated the full stack — backend, frontend, database schema, AI feedback engine, tests, and documentation — from a single architectural prompt.
