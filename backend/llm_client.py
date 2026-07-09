"""
Thin client for the locally hosted LLM (Ollama).

The rest of the application talks to the model only through this module, so
swapping the model or even the provider is a configuration change, not a code
change. The client uses Ollama's native HTTP API:

    GET  /api/tags   - list installed models (used for the health check)
    POST /api/chat   - conversational completion, optionally with tools

All network failures are converted into a small set of explicit exceptions so
the API layer can return clear, user-facing error messages (Task 7).
"""

from __future__ import annotations

import time
from typing import Any

import requests

from config import settings


class LLMError(Exception):
    """Base class for all LLM client failures."""


class LLMUnavailableError(LLMError):
    """The model server could not be reached (Ollama not running, wrong URL)."""


class LLMTimeoutError(LLMError):
    """The model took too long to respond."""


def check_health() -> dict[str, Any]:
    """Return the health of the LLM service.

    Reports whether Ollama is reachable and whether the configured model is
    installed. Never raises; returns a structured dict the /health route uses.
    """
    try:
        response = requests.get(
            f"{settings.OLLAMA_BASE_URL}/api/tags",
            timeout=5,
        )
        response.raise_for_status()
        payload = response.json()
        installed = [m.get("name", "") for m in payload.get("models", [])]
        model_ready = any(
            name == settings.OLLAMA_MODEL_NAME
            or name.startswith(settings.OLLAMA_MODEL_NAME.split(":")[0])
            for name in installed
        )
        return {
            "ollama_reachable": True,
            "model": settings.OLLAMA_MODEL_NAME,
            "model_installed": model_ready,
            "installed_models": installed,
        }
    except requests.RequestException as exc:
        return {
            "ollama_reachable": False,
            "model": settings.OLLAMA_MODEL_NAME,
            "model_installed": False,
            "error": str(exc),
        }


def chat(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    temperature: float | None = None,
) -> dict[str, Any]:
    """Send a conversation (optionally with tool definitions) to the local model.

    Args:
        messages:    Chat history, each a {"role", "content"} dict (roles:
                     system, user, assistant, tool).
        tools:       Optional OpenAI-style tool definitions the model may call.
        temperature: Sampling temperature; falls back to the configured default.

    Returns:
        dict with keys: message (the raw assistant message, which may contain
        "tool_calls" instead of/alongside "content"), tokens_used (int),
        generation_time (float seconds), model (str).

    Raises:
        LLMUnavailableError: the Ollama server is unreachable.
        LLMTimeoutError:     the request exceeded REQUEST_TIMEOUT_SECONDS.
        LLMError:            any other model-side failure.
    """
    if temperature is None:
        temperature = settings.DEFAULT_TEMPERATURE

    body: dict[str, Any] = {
        "model": settings.OLLAMA_MODEL_NAME,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature},
    }
    if tools:
        body["tools"] = tools

    start = time.perf_counter()
    try:
        response = requests.post(
            f"{settings.OLLAMA_BASE_URL}/api/chat",
            json=body,
            timeout=settings.REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.ConnectionError as exc:
        raise LLMUnavailableError(
            "Cannot reach the local LLM server. Is Ollama running "
            f"at {settings.OLLAMA_BASE_URL}?"
        ) from exc
    except requests.Timeout as exc:
        raise LLMTimeoutError(
            "The model took too long to respond. Try a shorter question "
            "or a lighter model."
        ) from exc
    except requests.HTTPError as exc:
        raise LLMError(f"The model returned an error: {exc}") from exc

    elapsed = time.perf_counter() - start
    data = response.json()
    message = data.get("message") or {}
    if not message.get("content") and not message.get("tool_calls"):
        raise LLMError("The model returned an empty response.")

    return {
        "message": message,
        # Ollama reports prompt + completion token counts when available.
        "tokens_used": int(data.get("eval_count", 0) or 0)
        + int(data.get("prompt_eval_count", 0) or 0),
        "generation_time": round(elapsed, 3),
        "model": settings.OLLAMA_MODEL_NAME,
    }
