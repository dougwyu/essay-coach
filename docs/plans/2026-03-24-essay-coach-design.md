# Essay Coach Design

**Goal:** A local web app where instructors create essay questions with hidden model answers, and students iteratively improve essays via structured AI feedback that never reveals the model answer.

**Stack:** FastAPI, vanilla HTML/CSS/JS, SQLite, Anthropic Python SDK

**Key decisions:**
- No auth (Phase 1) — instructor at `/instructor`, student at `/student`
- Session tracking via browser `localStorage` UUID
- SSE streaming for feedback
- Model answers never leave the server
- Feedback: Coverage, Depth, Structure, Accuracy, Progress
- Model: claude-sonnet-4-20250514
