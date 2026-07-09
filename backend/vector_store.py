"""
Minimal FAISS-backed vector store for the RAG knowledge base.

One flat inner-product index (cosine similarity, since embeddings are
normalized before insertion) plus a parallel JSONL file holding the text and
metadata for each vector, keyed by insertion position. Deliberately simple:
this corpus is small (assignment-scale), so a flat index and a rebuild-on-
delete are fast enough - no need for IVF/HNSW or a WAL-style vector database.
"""

from __future__ import annotations

import json
import threading
from typing import Any

import faiss
import numpy as np

from config import settings
from embeddings import embed

_INDEX_FILE = settings.VECTOR_STORE_DIR / "faiss.index"
_CHUNKS_FILE = settings.VECTOR_STORE_DIR / "chunks.jsonl"

_lock = threading.Lock()
_index: faiss.Index | None = None
_chunks: list[dict[str, str]] = []


def _normalize(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vectors / norms


def _load() -> None:
    global _index, _chunks
    settings.VECTOR_STORE_DIR.mkdir(parents=True, exist_ok=True)
    if _INDEX_FILE.exists() and _CHUNKS_FILE.exists():
        _index = faiss.read_index(str(_INDEX_FILE))
        _chunks = [
            json.loads(line)
            for line in _CHUNKS_FILE.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    else:
        _index = None
        _chunks = []


def _save() -> None:
    settings.VECTOR_STORE_DIR.mkdir(parents=True, exist_ok=True)
    if _index is not None:
        faiss.write_index(_index, str(_INDEX_FILE))
    with _CHUNKS_FILE.open("w", encoding="utf-8") as fh:
        for chunk in _chunks:
            fh.write(json.dumps(chunk, ensure_ascii=False) + "\n")


_load()


def is_empty() -> bool:
    return len(_chunks) == 0


def add(chunks: list[dict[str, str]]) -> int:
    """Embed and append chunks ({"text", "source", "heading"}). Returns count added."""
    global _index
    if not chunks:
        return 0

    with _lock:
        vectors = _normalize(np.array(embed([c["text"] for c in chunks]), dtype="float32"))

        if _index is None:
            _index = faiss.IndexFlatIP(vectors.shape[1])

        _index.add(vectors)
        _chunks.extend(chunks)
        _save()
        return len(chunks)


def search(query: str, k: int = 3) -> list[dict[str, Any]]:
    """Return up to k chunks most similar to the query, each with a similarity score."""
    with _lock:
        if _index is None or _index.ntotal == 0:
            return []
        query_vector = _normalize(np.array(embed([query]), dtype="float32"))
        scores, indices = _index.search(query_vector, min(k, _index.ntotal))

    results = []
    for score, idx in zip(scores[0], indices[0]):
        if idx < 0:
            continue
        results.append({**_chunks[idx], "score": float(score)})
    return results


def list_sources() -> list[dict[str, Any]]:
    """Distinct sources with their chunk counts, most recently added first."""
    counts: dict[str, int] = {}
    order: list[str] = []
    for chunk in _chunks:
        source = chunk["source"]
        if source not in counts:
            order.append(source)
        counts[source] = counts.get(source, 0) + 1
    return [{"source": source, "chunks": counts[source]} for source in reversed(order)]


def delete_source(source: str) -> int:
    """Remove all chunks for a source, rebuilding the index in place. Returns count removed."""
    global _index
    with _lock:
        if _index is None:
            return 0

        keep_positions = [i for i, c in enumerate(_chunks) if c["source"] != source]
        removed = len(_chunks) - len(keep_positions)
        if removed == 0:
            return 0

        if keep_positions:
            # Pull vectors straight back out of the flat index - no re-embedding needed.
            all_vectors = _index.reconstruct_n(0, _index.ntotal)
            kept_vectors = all_vectors[keep_positions]
            new_index = faiss.IndexFlatIP(kept_vectors.shape[1])
            new_index.add(kept_vectors)
            _index = new_index
            _chunks[:] = [_chunks[i] for i in keep_positions]
        else:
            _index = None
            _chunks.clear()

        _save()
        return removed


def status() -> dict[str, Any]:
    return {
        "chunk_count": len(_chunks),
        "source_count": len(list_sources()),
        "embedding_model": settings.EMBEDDING_MODEL_NAME,
    }
