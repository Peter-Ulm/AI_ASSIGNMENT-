"""
Central configuration for the Student Support Assistant backend.

Every setting is read from an environment variable with a sensible default, so
the application can be retargeted (different model, host, port) by editing the
.env file alone, without touching code. Copy .env.example to .env to override.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the project root (one level above this backend/ folder).
PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

BACKEND_DIR = Path(__file__).resolve().parent


def _get_bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    """Application settings, all overridable via environment variables."""

    # ── LLM provider ────────────────────────────────────────────────────────
    # Only "ollama" is implemented, but the indirection mirrors the FYP so a
    # second provider (e.g. OpenAI) could be slotted in without changing callers.
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "ollama")

    # ── Ollama (local LLM) ──────────────────────────────────────────────────
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    # Default to a model already pulled on the dev machine; change in .env to
    # llama3.2:1b or phi3 for a lighter footprint.
    OLLAMA_MODEL_NAME: str = os.getenv("OLLAMA_MODEL_NAME", "llama3.2:3b")
    # Small model dedicated to embeddings (RAG). Pulled alongside the chat model.
    EMBEDDING_MODEL_NAME: str = os.getenv("EMBEDDING_MODEL_NAME", "nomic-embed-text")

    # ── Generation defaults ─────────────────────────────────────────────────
    DEFAULT_TEMPERATURE: float = float(os.getenv("DEFAULT_TEMPERATURE", "0.7"))
    REQUEST_TIMEOUT_SECONDS: int = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "120"))
    MAX_QUESTION_CHARS: int = int(os.getenv("MAX_QUESTION_CHARS", "1000"))

    # ── API server ──────────────────────────────────────────────────────────
    API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
    API_PORT: int = int(os.getenv("API_PORT", "8000"))

    # ── Logging ─────────────────────────────────────────────────────────────
    LOG_FILE: Path = BACKEND_DIR / "logs" / "app.log"
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # ── Bonus features (toggleable) ─────────────────────────────────────────
    # Simple FAQ retrieval (RAG): inject the most relevant FAQ section into the
    # prompt before calling the model.
    USE_RAG: bool = _get_bool("USE_RAG", True)
    FAQ_FILE: Path = BACKEND_DIR / "university_faq.md"
    # Where user ratings (Good/Average/Poor) are appended.
    FEEDBACK_FILE: Path = BACKEND_DIR / "feedback.jsonl"

    # ── Vector store (FAISS) ─────────────────────────────────────────────────
    VECTOR_STORE_DIR: Path = BACKEND_DIR / "data"

    # ── Auth ─────────────────────────────────────────────────────────────────
    DB_FILE: Path = BACKEND_DIR / "data" / "app.db"
    # Change this for any real deployment - the default is only safe for local use.
    JWT_SECRET: str = os.getenv("JWT_SECRET", "dev-secret-change-me")
    JWT_EXPIRE_DAYS: int = int(os.getenv("JWT_EXPIRE_DAYS", "7"))
    FRONTEND_ORIGIN: str = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")
    # Cookies require HTTPS when Secure is set - keep False for local http, flip
    # to True once the app is served over HTTPS.
    COOKIE_SECURE: bool = _get_bool("COOKIE_SECURE", False)


settings = Settings()
