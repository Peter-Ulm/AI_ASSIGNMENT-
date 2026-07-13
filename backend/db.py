"""
Tiny SQLite persistence layer for user accounts and chat history.

Each function opens its own short-lived connection - this workload is a
handful of small, fast queries per request, not a place where connection
pooling would matter, and it sidesteps sqlite3's thread-safety caveats
entirely (FastAPI's sync routes run across a threadpool).
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from config import settings

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chat_sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    used_kb INTEGER,
    sources_json TEXT,
    model TEXT,
    tokens_used INTEGER,
    generation_time REAL,
    is_error INTEGER,
    created_at TEXT NOT NULL
);
"""


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    settings.DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(_SCHEMA)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Users ────────────────────────────────────────────────────────────────

def create_user(email: str, name: str, password_hash: str) -> dict[str, Any]:
    """Raises sqlite3.IntegrityError if the email is already registered."""
    user_id = str(uuid.uuid4())
    with _connect() as conn:
        conn.execute(
            "INSERT INTO users (id, email, name, password_hash, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, email, name, password_hash, _now()),
        )
    return {"id": user_id, "email": email, "name": name}


def get_user_by_email(email: str) -> sqlite3.Row | None:
    with _connect() as conn:
        return conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()


def get_user_by_id(user_id: str) -> sqlite3.Row | None:
    with _connect() as conn:
        return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


# ── Chat sessions ────────────────────────────────────────────────────────

def create_session(user_id: str, title: str) -> dict[str, Any]:
    session_id = str(uuid.uuid4())
    now = _now()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO chat_sessions (id, user_id, title, updated_at) VALUES (?, ?, ?, ?)",
            (session_id, user_id, title, now),
        )
    return {"id": session_id, "title": title, "updated_at": now}


def list_sessions(user_id: str) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, title, updated_at FROM chat_sessions WHERE user_id = ? ORDER BY updated_at DESC",
            (user_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_session(session_id: str, user_id: str) -> sqlite3.Row | None:
    """Ownership-checked: returns None if the session isn't the caller's."""
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM chat_sessions WHERE id = ? AND user_id = ?",
            (session_id, user_id),
        ).fetchone()


def touch_session(session_id: str, title: str | None = None) -> None:
    with _connect() as conn:
        if title is not None:
            conn.execute(
                "UPDATE chat_sessions SET updated_at = ?, title = ? WHERE id = ?",
                (_now(), title, session_id),
            )
        else:
            conn.execute(
                "UPDATE chat_sessions SET updated_at = ? WHERE id = ?",
                (_now(), session_id),
            )


def delete_session(session_id: str, user_id: str) -> bool:
    with _connect() as conn:
        cursor = conn.execute(
            "DELETE FROM chat_sessions WHERE id = ? AND user_id = ?",
            (session_id, user_id),
        )
    return cursor.rowcount > 0


# ── Chat messages ────────────────────────────────────────────────────────

def add_message(
    session_id: str,
    role: str,
    content: str,
    *,
    used_kb: bool = False,
    sources: list[dict[str, Any]] | None = None,
    model: str | None = None,
    tokens_used: int | None = None,
    generation_time: float | None = None,
    is_error: bool = False,
) -> None:
    with _connect() as conn:
        conn.execute(
            """INSERT INTO chat_messages
               (id, session_id, role, content, used_kb, sources_json, model,
                tokens_used, generation_time, is_error, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(uuid.uuid4()), session_id, role, content,
                int(used_kb), json.dumps(sources or []),
                model, tokens_used, generation_time, int(is_error), _now(),
            ),
        )


def list_messages(session_id: str) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM chat_messages WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,),
        ).fetchall()

    messages = []
    for row in rows:
        messages.append({
            "role": row["role"],
            "content": row["content"],
            "used_kb": bool(row["used_kb"]),
            "sources": json.loads(row["sources_json"] or "[]"),
            "model": row["model"],
            "tokens_used": row["tokens_used"],
            "generation_time": row["generation_time"],
            "is_error": bool(row["is_error"]),
        })
    return messages
