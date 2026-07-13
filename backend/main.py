"""
FastAPI backend for the University Student Support Assistant.

Pipeline:  frontend  ->  this API (/chat)  ->  llm_client  ->  local Ollama
model, which can call the search_knowledge_base tool  ->  vector_store (FAISS).

Every route except the /auth/* ones requires a logged-in user (a signed JWT
in an httpOnly "access_token" cookie, set by /auth/signup and /auth/login).
Chat history is owned by the server, one row per session/message in
backend/data/app.db (db.py) - not the browser's localStorage.

Endpoints:
    GET    /                     - service info and endpoint list
    GET    /health                - liveness + whether the local model is reachable/installed
    POST   /auth/signup           - create an account, logs in
    POST   /auth/login            - log in
    POST   /auth/logout           - clear the session cookie
    GET    /auth/me                - current user, or 401
    POST   /chat                  - send a message, get an answer (the main endpoint)
    GET    /chat/sessions          - list the caller's chat sessions
    GET    /chat/sessions/{id}     - one session's full message history
    DELETE /chat/sessions/{id}     - delete a chat session
    POST   /feedback               - record a Good/Average/Poor rating
    POST   /rag/documents/text     - ingest pasted text into the knowledge base
    POST   /rag/documents/file     - ingest an uploaded .txt/.md/.pdf file
    GET    /rag/documents          - list ingested documents and chunk counts
    DELETE /rag/documents/{src}    - remove a document from the knowledge base
    POST   /rag/search             - search the knowledge base directly (no LLM)
    GET    /rag/status             - knowledge base size and embedding model

Run:  uvicorn main:app --reload      (from the backend/ folder)
  or: python main.py
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

import auth
import db
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

# How many recent messages to send back to the model, so follow-up questions
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


def _make_title(content: str) -> str:
    flat = re.sub(r"\s+", " ", content).strip()
    return f"{flat[:40]}…" if len(flat) > 40 else flat


# ── Auth models + cookie helper ──────────────────────────────────────────────
_COOKIE_NAME = "access_token"


class SignupRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    email: str = Field(..., min_length=3, max_length=254)
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def _valid_email(cls, value: str) -> str:
        value = value.strip().lower()
        if "@" not in value or "." not in value.split("@")[-1]:
            raise ValueError("Enter a valid email address.")
        return value


class LoginRequest(BaseModel):
    email: str
    password: str


class UserResponse(BaseModel):
    id: str
    name: str
    email: str


def _set_auth_cookie(response: Response, user_id: str) -> None:
    response.set_cookie(
        key=_COOKIE_NAME,
        value=auth.create_access_token(user_id),
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        max_age=settings.JWT_EXPIRE_DAYS * 24 * 60 * 60,
    )


# ── Request/response models ─────────────────────────────────────────────────
class ChatRequest(BaseModel):
    session_id: str | None = None
    message: str
    temperature: float = Field(
        default=settings.DEFAULT_TEMPERATURE, ge=0.0, le=1.0,
        description="Sampling temperature (0 = focused, 1 = creative).",
    )

    @field_validator("message")
    @classmethod
    def _valid_message(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Message must not be empty.")
        if len(stripped) > settings.MAX_QUESTION_CHARS:
            raise ValueError(
                f"Message is too long (max {settings.MAX_QUESTION_CHARS} characters)."
            )
        return stripped


class SearchResult(BaseModel):
    text: str
    source: str
    heading: str
    score: float


class ChatResponse(BaseModel):
    session_id: str
    title: str
    answer: str
    tokens_used: int
    generation_time: float
    timestamp: str
    model: str
    used_kb: bool
    sources: list[SearchResult] = []


class StoredMessage(BaseModel):
    role: str
    content: str
    used_kb: bool = False
    sources: list[SearchResult] = []
    model: str | None = None
    tokens_used: int | None = None
    generation_time: float | None = None
    is_error: bool = False


class SessionSummary(BaseModel):
    id: str
    title: str
    updated_at: str


class SessionDetail(BaseModel):
    id: str
    title: str
    updated_at: str
    messages: list[StoredMessage]


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
    version="3.0.0",
)

# allow_origins must be an explicit list (not "*") when allow_credentials is
# True - the auth cookie only round-trips if the browser trusts the origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_ORIGIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _init_database() -> None:
    db.init_db()


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
            "auth": "POST /auth/signup, POST /auth/login, POST /auth/logout, GET /auth/me",
            "chat": "POST /chat",
            "chat_sessions": "GET /chat/sessions, GET/DELETE /chat/sessions/{id}",
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


# ── Auth ─────────────────────────────────────────────────────────────────────
@app.post("/auth/signup", response_model=UserResponse)
def signup(request: SignupRequest, response: Response) -> UserResponse:
    try:
        user = db.create_user(request.email, request.name.strip(), auth.hash_password(request.password))
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="An account with that email already exists.")
    _set_auth_cookie(response, user["id"])
    logger.info("New user signed up: %s", user["email"])
    return UserResponse(**user)


@app.post("/auth/login", response_model=UserResponse)
def login(request: LoginRequest, response: Response) -> UserResponse:
    user = db.get_user_by_email(request.email.strip().lower())
    if not user or not auth.verify_password(request.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    _set_auth_cookie(response, user["id"])
    return UserResponse(id=user["id"], name=user["name"], email=user["email"])


@app.post("/auth/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(_COOKIE_NAME)
    return {"status": "logged_out"}


@app.get("/auth/me", response_model=UserResponse)
def me(user: sqlite3.Row = Depends(auth.get_current_user)) -> UserResponse:
    return UserResponse(id=user["id"], name=user["name"], email=user["email"])


# ── Chat ─────────────────────────────────────────────────────────────────────
@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest, user: sqlite3.Row = Depends(auth.get_current_user)) -> ChatResponse:
    """Answer a student's message, using the knowledge base as a tool when useful."""
    if request.session_id:
        session = db.get_session(request.session_id, user["id"])
        if not session:
            raise HTTPException(status_code=404, detail="Chat session not found.")
        title = session["title"]
        history = db.list_messages(request.session_id)[-MAX_HISTORY_MESSAGES:]
        session_id: str | None = session["id"]
    else:
        title = _make_title(request.message)
        history = []
        session_id = None  # created only after a successful answer, below

    logger.info("Chat message received (session=%s): %s", session_id, request.message)

    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages += [{"role": m["role"], "content": m["content"]} for m in history]
    messages.append({"role": "user", "content": request.message})

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
                # Small models occasionally call the tool with a blank query for
                # greeting-shaped messages that don't need a real search. Ollama's
                # embedding endpoint returns an empty vector for an empty string
                # (a 200, not an error), so skip the call entirely rather than
                # let that surface as a failed answer.
                if not query.strip():
                    hits: list[dict] = []
                else:
                    # A single best-matching chunk per search, not several - this
                    # is what keeps answers focused. Returning the top few
                    # "loosely related" chunks made the model dutifully report
                    # on all of them, padding answers with facts the student
                    # didn't ask about.
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
                "content": f"Using the information above, answer this question: {request.message}",
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
    sources = [SearchResult(**hit) for hit in source_refs]

    # Only persist a session once we actually have an answer for it - a
    # failed first message shouldn't leave an empty chat behind.
    if session_id is None:
        session_id = db.create_session(user["id"], title)["id"]

    db.add_message(session_id, "user", request.message)
    db.add_message(
        session_id, "assistant", answer,
        used_kb=used_kb, sources=[s.model_dump() for s in sources],
        model=result["model"], tokens_used=result["tokens_used"],
        generation_time=result["generation_time"],
    )
    db.touch_session(session_id, title=title)

    response = ChatResponse(
        session_id=session_id,
        title=title,
        answer=answer,
        tokens_used=result["tokens_used"],
        generation_time=result["generation_time"],
        timestamp=datetime.now(timezone.utc).isoformat(),
        model=result["model"],
        used_kb=used_kb,
        sources=sources,
    )
    logger.info(
        "Chat answer generated (session=%s, model=%s, tokens=%s, %.2fs, used_kb=%s, sources=%d): %s",
        session_id, response.model, response.tokens_used, response.generation_time,
        used_kb, len(response.sources), response.answer[:120].replace("\n", " "),
    )
    return response


@app.get("/chat/sessions", response_model=list[SessionSummary])
def list_chat_sessions(user: sqlite3.Row = Depends(auth.get_current_user)) -> list[SessionSummary]:
    return [SessionSummary(**s) for s in db.list_sessions(user["id"])]


@app.get("/chat/sessions/{session_id}", response_model=SessionDetail)
def get_chat_session(session_id: str, user: sqlite3.Row = Depends(auth.get_current_user)) -> SessionDetail:
    session = db.get_session(session_id, user["id"])
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found.")
    return SessionDetail(
        id=session["id"],
        title=session["title"],
        updated_at=session["updated_at"],
        messages=db.list_messages(session_id),
    )


@app.delete("/chat/sessions/{session_id}")
def delete_chat_session(session_id: str, user: sqlite3.Row = Depends(auth.get_current_user)) -> dict:
    if not db.delete_session(session_id, user["id"]):
        raise HTTPException(status_code=404, detail="Chat session not found.")
    return {"status": "deleted", "session_id": session_id}


@app.post("/feedback")
def feedback(request: FeedbackRequest, _user: sqlite3.Row = Depends(auth.get_current_user)) -> dict:
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
def ingest_text_document(
    payload: IngestTextRequest, _user: sqlite3.Row = Depends(auth.get_current_user)
) -> RagDocument:
    if not payload.text.strip():
        raise HTTPException(status_code=400, detail="Text must not be empty.")
    count = ingestion.ingest_text(payload.source, payload.text)
    if count == 0:
        raise HTTPException(status_code=400, detail="No content could be extracted from the text.")
    logger.info("Ingested %d chunks from pasted text (source=%s)", count, payload.source)
    return RagDocument(source=payload.source, chunks=count)


@app.post("/rag/documents/file", response_model=RagDocument)
async def ingest_file_document(
    file: UploadFile = File(...), _user: sqlite3.Row = Depends(auth.get_current_user)
) -> RagDocument:
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
def list_documents(_user: sqlite3.Row = Depends(auth.get_current_user)) -> list[RagDocument]:
    return [RagDocument(**d) for d in vector_store.list_sources()]


@app.delete("/rag/documents/{source}")
def delete_document(source: str, _user: sqlite3.Row = Depends(auth.get_current_user)) -> dict:
    removed = vector_store.delete_source(source)
    if removed == 0:
        raise HTTPException(status_code=404, detail=f"No document found for source '{source}'.")
    logger.info("Deleted %d chunks for source %s", removed, source)
    return {"status": "deleted", "source": source, "chunks_removed": removed}


@app.post("/rag/search", response_model=list[SearchResult])
def search_knowledge_base(
    payload: SearchRequest, _user: sqlite3.Row = Depends(auth.get_current_user)
) -> list[SearchResult]:
    if not payload.query.strip():
        raise HTTPException(status_code=400, detail="Query must not be empty.")
    return [SearchResult(**hit) for hit in vector_store.search(payload.query, k=payload.k)]


@app.get("/rag/status", response_model=RagStatus)
def rag_status(_user: sqlite3.Row = Depends(auth.get_current_user)) -> RagStatus:
    return RagStatus(**vector_store.status())


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=True,
    )
