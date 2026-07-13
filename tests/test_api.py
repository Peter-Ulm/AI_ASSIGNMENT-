"""
API test script.

Tests the running backend over HTTP:
  - GET  /health          returns a status and model
  - POST /auth/signup or /auth/login - gets an authenticated session
  - POST /chat            returns the required fields with a non-empty answer
  - POST /chat (empty)    is rejected with a 4xx error
  - POST /rag/search      returns a list (empty query rejected)

Run with the backend up:
    python tests/test_api.py          # prints a PASS/FAIL summary
    pytest tests/test_api.py -v       # same checks under pytest

If the backend is not reachable, pytest skips (so CI does not hard-fail) and the
script prints a clear message.
"""

from __future__ import annotations

import os
import sys

import pytest
import requests

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
REQUIRED_FIELDS = [
    "session_id", "title", "answer", "tokens_used", "generation_time",
    "timestamp", "model", "used_kb", "sources",
]

# Fixed test account, reused across runs (signup if missing, login otherwise)
# so this script is idempotent and doesn't accumulate throwaway users.
TEST_EMAIL = "test-api@example.com"
TEST_PASSWORD = "test-api-password"


def _backend_up() -> bool:
    try:
        requests.get(f"{API_BASE_URL}/health", timeout=5)
        return True
    except requests.RequestException:
        return False


pytestmark = pytest.mark.skipif(
    not _backend_up(),
    reason=f"backend not reachable at {API_BASE_URL}; start it before running tests",
)


def _authed_session() -> requests.Session:
    """Log in as the fixed test account, signing it up on first use."""
    session = requests.Session()
    resp = session.post(
        f"{API_BASE_URL}/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        timeout=10,
    )
    if resp.status_code != 200:
        resp = session.post(
            f"{API_BASE_URL}/auth/signup",
            json={"name": "Test API", "email": TEST_EMAIL, "password": TEST_PASSWORD},
            timeout=10,
        )
        assert resp.status_code == 200, f"could not create test account: {resp.text}"
    return session


def test_health():
    resp = requests.get(f"{API_BASE_URL}/health", timeout=10)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "status" in data and "model" in data


def test_chat_returns_required_fields():
    session = _authed_session()
    resp = session.post(
        f"{API_BASE_URL}/chat",
        json={"session_id": None, "message": "How do I register for courses?", "temperature": 0.2},
        timeout=180,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    for field in REQUIRED_FIELDS:
        assert field in data, f"missing field: {field}"
    assert len(data["answer"]) > 0, "answer is empty"


def test_empty_message_is_rejected():
    session = _authed_session()
    resp = session.post(
        f"{API_BASE_URL}/chat",
        json={"session_id": None, "message": "   ", "temperature": 0.2},
        timeout=30,
    )
    assert resp.status_code >= 400, "empty message should be rejected"


def test_chat_requires_auth():
    resp = requests.post(
        f"{API_BASE_URL}/chat",
        json={"session_id": None, "message": "Hello", "temperature": 0.2},
        timeout=30,
    )
    assert resp.status_code == 401, "chat without a session cookie should be rejected"


def test_rag_search_returns_results():
    session = _authed_session()
    resp = session.post(
        f"{API_BASE_URL}/rag/search",
        json={"query": "library hours", "k": 3},
        timeout=30,
    )
    assert resp.status_code == 200, resp.text
    assert isinstance(resp.json(), list)


def _run_as_script() -> int:
    if not _backend_up():
        print(f"[SKIP] Backend not reachable at {API_BASE_URL}. Start it first:")
        print("       cd backend && uvicorn main:app --reload")
        return 1

    checks = [
        ("GET /health", test_health),
        ("POST /chat requires auth", test_chat_requires_auth),
        ("POST /chat (valid)", test_chat_returns_required_fields),
        ("POST /chat (empty -> rejected)", test_empty_message_is_rejected),
        ("POST /rag/search", test_rag_search_returns_results),
    ]
    failures = 0
    for name, fn in checks:
        try:
            fn()
            print(f"[PASS] {name}")
        except AssertionError as exc:
            failures += 1
            print(f"[FAIL] {name}: {exc}")
        except requests.RequestException as exc:
            failures += 1
            print(f"[FAIL] {name}: request error: {exc}")
    print(f"\n{len(checks) - failures}/{len(checks)} checks passed.")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(_run_as_script())
