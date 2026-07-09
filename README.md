# University Student Support Assistant

A self-hosted Large Language Model (LLM) chat application that answers student
questions about university services: course registration, examination rules,
library services, ICT support, hostel application, fee payment, the academic
calendar, and student conduct.

Built for **IS 365 - Full-Stack Pipeline for Deploying a Self-Hosted LLM
Application**. The whole pipeline runs locally, with retrieval-augmented
generation (RAG) exposed to the model as a tool it decides whether to use:

```
User -> React chat UI -> FastAPI backend -> local Ollama model
                              |                    |
                              |                    +-> search_knowledge_base tool
                              |                            |
                              +-> logging                  +-> FAISS vector store
                                  (backend/logs/app.log)        (backend/data/)
```

## Features

- **Claude-style chat UI**: sidebar + conversation view, dark/light mode,
  multi-turn memory, markdown rendering, per-answer feedback.
- **Tool-calling RAG**: the model is given a `search_knowledge_base` tool and
  decides for itself whether a question needs it - university-services
  questions get grounded, searched answers with cited sources; greetings and
  off-topic questions are answered directly, without a wasted search.
- **FAISS-backed knowledge base** with a full ingestion/management flow: paste
  text, or upload `.txt`/`.md`/`.pdf` files, list documents, delete them, or
  search the knowledge base directly without going through the LLM at all.
- **GPU-accelerated Ollama** (optional): if the host has an NVIDIA GPU and the
  NVIDIA Container Toolkit, Ollama runs inference and embeddings on it - see
  [GPU support](#gpu-support) below. Falls back to CPU everywhere else.
- FastAPI backend with `/health`, `/chat`, `/rag/*`, and auto-generated
  Swagger docs at `/docs`.
- Configuration via environment variables (`.env`), so the model/host/port are
  swappable without touching code.
- Logging of every chat turn, error, and timestamp.
- Good/Average/Poor answer rating saved to a file.

## Project structure

```
.
├── backend/
│   ├── main.py              # FastAPI app: /health, /chat, /feedback, /rag/*
│   ├── llm_client.py        # talks to the local Ollama model (chat + tool calling)
│   ├── embeddings.py        # talks to Ollama's embedding model
│   ├── vector_store.py      # FAISS index + persistence + CRUD
│   ├── ingestion.py         # chunking for pasted text / .txt / .md / .pdf
│   ├── config.py            # env-driven settings
│   ├── university_faq.md    # seed knowledge base content (edit with your own info)
│   └── data/                # FAISS index + chunk metadata, created at runtime
├── frontend/
│   ├── src/
│   │   ├── App.tsx                    # top-level chat state + persistence
│   │   ├── components/
│   │   │   ├── ChatLayout.tsx         # sidebar + chat pane shell
│   │   │   ├── Sidebar.tsx            # new chat, knowledge base, status, theme
│   │   │   ├── KnowledgeBasePanel.tsx # ingestion, document list, direct search
│   │   │   ├── ChatPane.tsx           # message list + composer
│   │   │   ├── MessageBubble.tsx      # markdown rendering, KB citation chip
│   │   │   ├── Composer.tsx           # input box, send, temperature
│   │   │   └── FeedbackButtons.tsx    # Good/Average/Poor rating
│   │   ├── context/ThemeContext.tsx   # dark/light mode context
│   │   ├── services/api.ts            # API calls to backend
│   │   └── types/index.ts             # TypeScript type definitions
│   ├── index.html
│   ├── package.json
│   └── vite.config.ts
├── tests/
│   └── test_api.py
├── docs/
│   ├── report.md
│   ├── SCREENSHOTS.md
│   └── screenshots/
├── docker-compose.yml        # CPU-only by default
├── docker-compose.gpu.yml    # GPU override, see below
├── requirements.txt
├── .env.example
└── README.md
```

## Prerequisites

- Python 3.10+ (tested on 3.12).
- [Ollama](https://ollama.ai/download) installed and running.
- A pulled chat model (`llama3.2:3b` by default) and embedding model
  (`nomic-embed-text` by default) - see setup below.
- Node.js 18+ and npm (for the React frontend).
- Docker + Docker Compose, if running via containers (recommended).

## Setup

For a full, step-by-step walkthrough (including troubleshooting), see
**[docs/RUNNING.md](docs/RUNNING.md)**. Quick version below.

### Docker Compose (recommended)

```bash
# CPU everywhere
docker compose up -d --build

# With GPU acceleration for Ollama (requires NVIDIA Container Toolkit)
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build
```

This starts four services: `ollama`, a one-shot `ollama-pull` that pulls both
the chat and embedding models, `backend`, and `frontend`. The backend seeds
the knowledge base from `backend/university_faq.md` on first startup if it's
empty.

Then open:

```
Frontend: http://localhost:3000
Backend:  http://localhost:8000  (docs at /docs)
Ollama:   http://localhost:11434
```

### GPU support

Check whether Docker has GPU support available:

```bash
docker info | grep -i runtime   # should list "nvidia" among the runtimes
nvidia-smi                      # should show your GPU
```

If both work, use the GPU compose override shown above. `docker-compose.yml`
stays CPU-only by default so it runs on any machine; `docker-compose.gpu.yml`
only adds an NVIDIA device reservation on top when you explicitly include it.
Ollama detects and uses the GPU automatically once it can see it - no extra
flags needed.

### Manual setup (without Docker)

```bash
# Backend
python -m venv .venv
source .venv/bin/activate     # macOS / Linux
# .venv\Scripts\activate      # Windows
pip install -r requirements.txt
cp .env.example .env          # edit as needed
ollama pull llama3.2:3b
ollama pull nomic-embed-text
cd backend && uvicorn main:app --reload
# API:     http://localhost:8000
# Swagger: http://localhost:8000/docs

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
# UI: http://localhost:3000
```

## Using the app

- **Chat**: ask a question in the composer. The model decides on its own
  whether to search the knowledge base - grounded answers show a "Used
  knowledge base" chip with the source sections it cited.
- **Knowledge base**: in the sidebar, paste text or upload a `.txt`/`.md`/
  `.pdf` file to add it to the knowledge base; delete documents you no longer
  want; or search the knowledge base directly (no LLM involved) to see raw
  matches and their similarity scores.

## Testing

With the backend running:

```bash
python tests/test_api.py        # prints a PASS/FAIL summary
# or
pytest tests/test_api.py -v
```

## Configuration (.env)

All settings live in `.env` (see `.env.example`). The most useful ones:

| Variable | Default | Purpose |
|---|---|---|
| `OLLAMA_MODEL_NAME` | `llama3.2:3b` | Chat model. |
| `EMBEDDING_MODEL_NAME` | `nomic-embed-text` | Embedding model for the knowledge base. |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Where Ollama is served. |
| `DEFAULT_TEMPERATURE` | `0.7` | Default sampling temperature. |
| `API_PORT` | `8000` | Backend port. |
| `USE_RAG` | `true` | Whether the chat model is given the search tool at all. |
| `VITE_API_BASE_URL` | `http://localhost:8000` | Backend URL used by the frontend. |

## Error handling

| Situation | Behaviour |
|---|---|
| Backend not running | Frontend status indicator shows offline. |
| Model not running | Backend returns a 503 with a clear message; the frontend surfaces it. |
| Empty message | Composer blocks the send; backend also rejects it (422). |
| Slow response | Frontend shows a typing indicator. |

## Notes

This project was built independently as a class assignment. The application
pipeline is self-contained in this repository.
