"""
Turns raw text, markdown, or PDF bytes into chunks and adds them to the
vector store. Two chunking strategies:
  - "## heading" sections, when the text has them (keeps a meaningful
    heading per chunk, useful for citing the source in the chat UI)
  - fixed-size windows with overlap, as a fallback for plain prose that has
    no headings

No other document types are supported by design - this stays a small,
readable ingestion path rather than a general-purpose document loader.
"""

from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader

import vector_store

_CHUNK_SIZE = 800
_CHUNK_OVERLAP = 100


def _split_by_headings(text: str) -> list[tuple[str, str]]:
    """Split on '## ' headings. Returns (heading, body) pairs, or [] if none found."""
    sections: list[tuple[str, str]] = []
    heading: str | None = None
    body: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if heading is not None:
                sections.append((heading, " ".join(body).strip()))
            heading = line[3:].strip()
            body = []
        elif heading is not None:
            body.append(line)
    if heading is not None:
        sections.append((heading, " ".join(body).strip()))
    return sections


def _split_fixed_window(text: str) -> list[str]:
    """Fallback chunker for text with no headings: fixed-size windows with overlap."""
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = start + _CHUNK_SIZE
        chunks.append(text[start:end].strip())
        start = end - _CHUNK_OVERLAP
    return [c for c in chunks if c]


def _chunk(text: str) -> list[dict[str, str]]:
    sections = _split_by_headings(text)
    if sections:
        return [{"heading": heading, "text": body} for heading, body in sections if body]
    return [{"heading": "", "text": chunk} for chunk in _split_fixed_window(text)]


def ingest_text(source: str, text: str) -> int:
    """Chunk and add plain text/markdown under the given source name."""
    chunks = [{"source": source, **c} for c in _chunk(text)]
    return vector_store.add(chunks)


def _extract_pdf_text(raw_bytes: bytes) -> str:
    reader = PdfReader(BytesIO(raw_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def ingest_file(filename: str, raw_bytes: bytes) -> int:
    """Chunk and add an uploaded .txt/.md/.pdf file under its filename as source."""
    if filename.lower().endswith(".pdf"):
        text = _extract_pdf_text(raw_bytes)
    else:
        text = raw_bytes.decode("utf-8", errors="ignore")
    return ingest_text(filename, text)


def seed_if_empty(faq_path: Path) -> None:
    """On a fresh install, ingest the bundled FAQ so the knowledge base isn't empty."""
    if vector_store.is_empty() and faq_path.exists():
        ingest_text(faq_path.name, faq_path.read_text(encoding="utf-8"))
