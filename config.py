import os
from dotenv import load_dotenv

load_dotenv(override=True)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
DATABASE_PATH = os.getenv("DATABASE_PATH", "essay_coach.db")   # dev/test only
DATABASE_URL = os.getenv("DATABASE_URL", "")                   # production PostgreSQL
MODEL_NAME = "claude-sonnet-4-20250514"

# LLM backend: "anthropic" (default) or "ollama"
LLM_BACKEND = os.getenv("LLM_BACKEND", "anthropic")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.3:70b")
