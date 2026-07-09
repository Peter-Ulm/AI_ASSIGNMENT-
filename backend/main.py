"""
FastAPI backend for the University Student Support Assistant.

Pipeline:  frontend  ->  this API (/chat)  ->  llm_client  ->  local Ollama
model, which can call the search_knowledge_base tool  ->  vector_store (FAISS).

Endpoints:
    GET    /                     - service info and endpoint list
    GET    /health               - liveness + whether the local model is reachable/installed
    POST   /chat                 - send a conversation, get an answer (the main endpoint)
    POST   /feedback             - record a Good/Average/Poor rating
    POST   /rag/documents/text   - ingest pasted text into the knowledge base
    POST   /rag/documents/file   - ingest an uploaded .txt/.md/.pdf file
    GET    /rag/documents        - list ingested documents and chunk counts
    DELETE /rag/documents/{src}  - remove a document from the knowledge base
    POST   /rag/search           - search the knowledge base directly (no LLM)
    GET    /rag/status           - knowledge base size and embedding model

Run:  uvicorn main:app --reload      (from the backend/ folder)
  or: python main.py
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

import ingestion
import llm_client
import vector_store
from config import settings

# ── Logging ──────────────────────────────────────────────────────────────────
settings.LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(settings.LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("student-support")


# ── Prompt + tool design ─────────────────────────────────────────────────────
# The model decides whether a question needs the knowledge base rather than
# every prompt being force-fed FAQ text, regardless of relevance.
SYSTEM_PROMPT = (
    "You are a knowledgeable university student services officer, answering "
    "questions about course registration, examination rules, library services, "
    "ICT support, hostel applications, fee payment, the academic calendar, and "
    "student conduct.\n\n"
    "When you call search_knowledge_base, your answer must report the actual "
    "facts and steps the tool returned, in your own words - do not summarize "
    "them away into a vague referral, and do not invent any office name, "
    "policy, date, or amount that wasn't in what the tool gave you. Only tell "
    "the student to contact an office if the tool genuinely found nothing "
    "relevant to their question.\n\n"
    "Write like a confident, direct staff member: answer first, skip small "
    "talk and restating the question, and don't mention that you searched "
    "anything. For greetings or questions unrelated to university services, "
    "respond naturally and briefly without searching."
)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge_base",
            "description": (
                "Search the university's knowledge base for information relevant "
                "to a student's question (course registration, exams, library, "
                "ICT, hostels, fees, academic calendar, conduct, and any other "
                "ingested documents). Skip it for greetings or questions unrelated "
                "to the university."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query, derived from the student's question.",
                    }
                },
                "required": ["query"],
            },
        },
    }
]

# How many recent turns to send back to the model, so follow-up questions
# ("what about the second one?") work without unbounded prompt growth.
MAX_HISTORY_MESSAGES = 12

# Below this cosine-similarity score a retrieved chunk is treated as noise
# (tangentially related rather than actually relevant) and dropped before the
# model sees it - otherwise the model tends to dutifully report on every
# retrieved chunk, even ones the student didn't ask about. The single best
# hit is always kept so a weak match still beats no answer at all.
MIN_SOURCE_SCORE = 0.6


def _filter_relevant(hits: list[dict]) -> list[dict]:
    relevant = [h for h in hits if h["score"] >= MIN_SOURCE_SCORE]
    return relevant or hits[:1]


# Small models occasionally emit a stub instead of a real natural-language
# answer: an empty "{}", or - after a tool round-trip - a tool-call-shaped
# JSON blob left over from the model's own template habits even with no
# tools bound. Both are template quirks at this model size, not real answers.
_EMPTY_STUB = re.compile(r"^\{?\s*\}?$")


def _is_degenerate(content: str) -> bool:
    stripped = content.strip()
    if _EMPTY_STUB.fullmatch(stripped):
        return True
    return stripped.startswith("{") and '"name"' in stripped and (
        '"parameters"' in stripped or '"arguments"' in stripped
    )


# Occasionally a stray chat-template role label ("assistant") leaks in as the
# first line of the content. Harmless to strip if present, no-op otherwise.
_LEADING_ROLE_TAG = re.compile(r"^(assistant|system|user)\s*\n+", re.IGNORECASE)


# ── Request/response models ─────────────────────────────────────────────────
class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    temperature: float = Field(
        default=settings.DEFAULT_TEMPERATURE, ge=0.0, le=1.0,
        description="Sampling temperature (0 = focused, 1 = creative).",
    )

    @field_validator("messages")
    @classmethod
    def _valid_history(cls, value: list[ChatMessage]) -> list[ChatMessage]:
        if not value:
            raise ValueError("messages must not be empty.")
        latest = value[-1].content.strip()
        if not latest:
            raise ValueError("The latest message must not be empty.")
        if len(latest) > settings.MAX_QUESTION_CHARS:
            raise ValueError(
                f"Message is too long (max {settings.MAX_QUESTION_CHARS} characters)."
            )
        return value


class SearchResult(BaseModel):
    text: str
    source: str
    heading: str
    score: float


class ChatResponse(BaseModel):
    answer: str
    tokens_used: int
    generation_time: float
    timestamp: str
    model: str
    used_kb: bool
    sources: list[SearchResult] = []


class HealthResponse(BaseModel):
    status: str
    model: str
    ollama_reachable: bool
    model_installed: bool


class FeedbackRequest(BaseModel):
    question: str
    answer: str
    rating: str = Field(..., description="One of: Good, Average, Poor.")

    @field_validator("rating")
    @classmethod
    def _valid_rating(cls, value: str) -> str:
        allowed = {"Good", "Average", "Poor"}
        if value not in allowed:
            raise ValueError(f"rating must be one of {sorted(allowed)}.")
        return value


class RagDocument(BaseModel):
    source: str
    chunks: int


class IngestTextRequest(BaseModel):
    source: str
    text: str


class SearchRequest(BaseModel):
    query: str
    k: int = Field(default=5, ge=1, le=20)


class RagStatus(BaseModel):
    chunk_count: int
    source_count: int
    embedding_model: str


# ── Application ─────────────────────────────────────────────────────────────
app = FastAPI(
    title="University Student Support Assistant",
    description="A self-hosted LLM chat app with FAISS-backed RAG (IS 365 assignment).",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _seed_knowledge_base() -> None:
    ingestion.seed_if_empty(settings.FAQ_FILE)


@app.on_event("startup")
def _warm_up_model() -> None:
    """Send a throwaway prompt so the first real chat isn't the one paying for
    Ollama's cold-start cost (model load + CUDA kernel compilation, which can
    take a minute or more on first inference but is a one-time cost per
    container lifetime)."""
    try:
        llm_client.chat([{"role": "user", "content": "hi"}])
        logger.info("Model warm-up complete.")
    except llm_client.LLMError as exc:
        logger.warning("Model warm-up skipped: %s", exc)


@app.get("/")
def root() -> dict:
    return {
        "service": "University Student Support Assistant",
        "model": settings.OLLAMA_MODEL_NAME,
        "endpoints": {
            "health": "GET /health",
            "chat": "POST /chat",
            "feedback": "POST /feedback",
            "rag_documents": "GET/POST /rag/documents, DELETE /rag/documents/{source}",
            "rag_search": "POST /rag/search",
            "rag_status": "GET /rag/status",
            "docs": "GET /docs",
        },
    }


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Report whether the API is up and the local model is reachable."""
    info = llm_client.check_health()
    reachable = bool(info.get("ollama_reachable"))
    installed = bool(info.get("model_installed"))
    status = "ok" if reachable and installed else "degraded"
    return HealthResponse(
        status=status,
        model=settings.OLLAMA_MODEL_NAME,
        ollama_reachable=reachable,
        model_installed=installed,
    )


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    """Answer a student's message, using the knowledge base as a tool when useful."""
    history = request.messages[-MAX_HISTORY_MESSAGES:]
    logger.info("Chat message received: %s", history[-1].content)

    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages += [{"role": m.role, "content": m.content} for m in history]

    tools = TOOLS if settings.USE_RAG else None
    used_kb = False
    hits_by_key: dict[tuple[str, str], dict] = {}

    try:
        result = llm_client.chat(messages, tools=tools, temperature=request.temperature)

        tool_calls = result["message"].get("tool_calls") or []
        if tool_calls:
            used_kb = True
            messages.append(result["message"])
            for call in tool_calls:
                query = call.get("function", {}).get("arguments", {}).get("query", "")
                # A single best-matching chunk per search, not several - this is
                # what keeps answers focused. Returning the top few "loosely
                # related" chunks made the model dutifully report on all of
                # them, padding answers with facts the student didn't ask about.
                hits = _filter_relevant(vector_store.search(query, k=1))
                for hit in hits:
                    key = (hit["source"], hit["heading"])
                    if key not in hits_by_key or hit["score"] > hits_by_key[key]["score"]:
                        hits_by_key[key] = hit
                tool_text = "\n\n".join(h["text"] for h in hits) or "No relevant information found."
                messages.append({"role": "tool", "content": tool_text})

            # Re-ask the original question explicitly right before the final
            # generation call. Without this, the model reliably falls back to
            # a generic "contact the office" deflection instead of actually
            # using the tool result - a measured quirk at this model size,
            # not a hypothetical one. A plain system reminder does not fix
            # it; restating the question in a user turn does.
            messages.append({
                "role": "user",
                "content": f"Using the information above, answer this question: {history[-1].content}",
            })

            # One follow-up call to let the model answer using the tool results.
            # Tools are omitted here by design - a single round-trip is enough
            # for this assistant and avoids open-ended tool-call loops.
            result = llm_client.chat(messages, temperature=request.temperature)

        if _is_degenerate(result["message"].get("content") or ""):
            result = llm_client.chat(messages, temperature=request.temperature)

    except llm_client.LLMUnavailableError as exc:
        logger.error("LLM unavailable: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc))
    except llm_client.LLMTimeoutError as exc:
        logger.error("LLM timeout: %s", exc)
        raise HTTPException(status_code=504, detail=str(exc))
    except llm_client.LLMError as exc:
        logger.error("LLM error: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc))

    answer = (result["message"].get("content") or "").strip()
    answer = _LEADING_ROLE_TAG.sub("", answer).strip()
    if not answer:
        raise HTTPException(status_code=502, detail="The model returned an empty answer.")

    source_refs = sorted(hits_by_key.values(), key=lambda h: h["score"], reverse=True)

    response = ChatResponse(
        answer=answer,
        tokens_used=result["tokens_used"],
        generation_time=result["generation_time"],
        timestamp=datetime.now(timezone.utc).isoformat(),
        model=result["model"],
        used_kb=used_kb,
        sources=[SearchResult(**hit) for hit in source_refs],
    )
    logger.info(
        "Chat answer generated (model=%s, tokens=%s, %.2fs, used_kb=%s, sources=%d): %s",
        response.model, response.tokens_used, response.generation_time,
        used_kb, len(response.sources), response.answer[:120].replace("\n", " "),
    )
    return response


@app.post("/feedback")
def feedback(request: FeedbackRequest) -> dict:
    """Record a user rating of an answer."""
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "rating": request.rating,
        "question": request.question,
        "answer": request.answer,
    }
    with settings.FEEDBACK_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    logger.info("Feedback recorded: %s for question: %s", request.rating, request.question)
    return {"status": "saved", "rating": request.rating}


# ── RAG management ───────────────────────────────────────────────────────────
_ALLOWED_EXTENSIONS = {".txt", ".md", ".pdf"}


@app.post("/rag/documents/text", response_model=RagDocument)
def ingest_text_document(payload: IngestTextRequest) -> RagDocument:
    if not payload.text.strip():
        raise HTTPException(status_code=400, detail="Text must not be empty.")
    count = ingestion.ingest_text(payload.source, payload.text)
    if count == 0:
        raise HTTPException(status_code=400, detail="No content could be extracted from the text.")
    logger.info("Ingested %d chunks from pasted text (source=%s)", count, payload.source)
    return RagDocument(source=payload.source, chunks=count)


@app.post("/rag/documents/file", response_model=RagDocument)
async def ingest_file_document(file: UploadFile = File(...)) -> RagDocument:
    extension = Path(file.filename or "").suffix.lower()
    if extension not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {extension or 'unknown'}. Allowed: .txt, .md, .pdf",
        )
    raw_bytes = await file.read()
    count = ingestion.ingest_file(file.filename, raw_bytes)
    if count == 0:
        raise HTTPException(status_code=400, detail="No content could be extracted from the file.")
    logger.info("Ingested %d chunks from file %s", count, file.filename)
    return RagDocument(source=file.filename, chunks=count)


@app.get("/rag/documents", response_model=list[RagDocument])
def list_documents() -> list[RagDocument]:
    return [RagDocument(**d) for d in vector_store.list_sources()]


@app.delete("/rag/documents/{source}")
def delete_document(source: str) -> dict:
    removed = vector_store.delete_source(source)
    if removed == 0:
        raise HTTPException(status_code=404, detail=f"No document found for source '{source}'.")
    logger.info("Deleted %d chunks for source %s", removed, source)
    return {"status": "deleted", "source": source, "chunks_removed": removed}


@app.post("/rag/search", response_model=list[SearchResult])
def search_knowledge_base(payload: SearchRequest) -> list[SearchResult]:
    if not payload.query.strip():
        raise HTTPException(status_code=400, detail="Query must not be empty.")
    return [SearchResult(**hit) for hit in vector_store.search(payload.query, k=payload.k)]


@app.get("/rag/status", response_model=RagStatus)
def rag_status() -> RagStatus:
    return RagStatus(**vector_store.status())


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=True,
    )
