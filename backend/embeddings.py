"""
Thin client for turning text into vectors via Ollama's embeddings API.

Mirrors llm_client.py: one small function, network failures converted to the
same LLMError hierarchy so callers handle both the same way.
"""

from __future__ import annotations

import requests

from config import settings
from llm_client import LLMError, LLMUnavailableError


def embed(texts: list[str]) -> list[list[float]]:
    """Embed a batch of strings. Returns one vector per input string, in order."""
    vectors: list[list[float]] = []
    for text in texts:
        try:
            response = requests.post(
                f"{settings.OLLAMA_BASE_URL}/api/embeddings",
                json={"model": settings.EMBEDDING_MODEL_NAME, "prompt": text},
                timeout=settings.REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
        except requests.ConnectionError as exc:
            raise LLMUnavailableError(
                "Cannot reach the local LLM server for embeddings. Is Ollama "
                f"running at {settings.OLLAMA_BASE_URL}?"
            ) from exc
        except requests.RequestException as exc:
            raise LLMError(f"Embedding request failed: {exc}") from exc

        vector = response.json().get("embedding")
        if not vector:
            raise LLMError("The embedding model returned an empty vector.")
        vectors.append(vector)
    return vectors
