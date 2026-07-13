"""
Password hashing and JWT session tokens.

Passwords are hashed with bcrypt; sessions are a signed JWT stored in an
httpOnly cookie (set by main.py), so the token never touches client-side
JavaScript or localStorage.
"""

from __future__ import annotations

import datetime as dt
import sqlite3

import bcrypt
import jwt
from fastapi import Cookie, HTTPException

import db
from config import settings

_ALGORITHM = "HS256"
# bcrypt ignores/rejects bytes beyond 72; truncate defensively rather than
# let an unusually long password raise inside the library.
_MAX_PASSWORD_BYTES = 72


def hash_password(password: str) -> str:
    truncated = password.encode("utf-8")[:_MAX_PASSWORD_BYTES]
    return bcrypt.hashpw(truncated, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    truncated = password.encode("utf-8")[:_MAX_PASSWORD_BYTES]
    return bcrypt.checkpw(truncated, password_hash.encode("utf-8"))


def create_access_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=settings.JWT_EXPIRE_DAYS),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=_ALGORITHM)


def decode_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[_ALGORITHM])
        return payload.get("sub")
    except jwt.PyJWTError:
        return None


def get_current_user(access_token: str | None = Cookie(default=None)) -> sqlite3.Row:
    """FastAPI dependency: resolves the caller's user row from the auth cookie."""
    user_id = decode_token(access_token) if access_token else None
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    user = db.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    return user
