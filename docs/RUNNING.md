# Running the App

Two ways to run this: with **Docker** (one command, everything containerized -
recommended), or **manually** (install Python/Node/Ollama yourself and run
each piece directly). Both end up with the same app at `http://localhost:3000`.

---

## Option A: Docker (recommended)

### 1. Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed
  and running (includes Docker Compose).
- ~5 GB free disk space for the images and models on first run.

### 2. (Optional) configure

The app runs with sane defaults out of the box. To customize the model,
ports, or temperature, copy the example env file and edit it:

```bash
cp .env.example .env
```

### 3. Start everything

From the project root:

```bash
docker compose up -d --build
```

This builds and starts four services:

| Service | What it does |
|---|---|
| `ollama` | Runs the local LLM engine. |
| `ollama-pull` | One-shot: downloads the chat model (`llama3.2:3b`) and embedding model (`nomic-embed-text`), then exits. |
| `backend` | FastAPI app - the API, RAG pipeline, and knowledge base. |
| `frontend` | The React chat UI (Vite dev server). |

**First run only:** `ollama-pull` downloads ~2.3 GB of models, which can take
a few minutes depending on your connection. Watch its progress with:

```bash
docker compose logs -f ollama-pull
```

Once it exits with `success`, the backend starts automatically (it waits for
the pull to finish).

### 4. Open the app

```
Frontend: http://localhost:3000
Backend:  http://localhost:8000/docs   (interactive API docs)
```

The knowledge base seeds itself from `backend/university_faq.md` on first
startup, so there's sample content to chat about immediately.

### 5. GPU acceleration (optional)

If you have an NVIDIA GPU, check it's visible to Docker first:

```bash
docker info | grep -i runtime   # should list "nvidia"
nvidia-smi                      # should show your GPU
```

If both work, start the stack with the GPU override layered on top instead:

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build
```

Ollama detects and uses the GPU automatically once it can see it - no other
change needed. Verify it's actually being used:

```bash
docker exec ai-assignment-ollama nvidia-smi   # shows GPU memory in use
docker exec ai-assignment-ollama ollama ps    # PROCESSOR column should say "100% GPU"
```

### 6. Everyday commands

```bash
docker compose down                    # stop everything
docker compose up -d                   # start again (no rebuild)
docker compose up -d --build           # rebuild after changing Dockerfiles/dependencies
docker compose logs -f backend         # tail backend logs
docker compose logs -f frontend        # tail frontend logs
docker compose restart backend         # restart one service
```

If you added the GPU override, include both `-f` flags every time you bring
the stack up or down, or Compose falls back to the CPU-only config.

### 7. Troubleshooting

- **Frontend shows stale code after editing source files** - Vite's file
  watcher doesn't always pick up changes through Docker Desktop's bind mount.
  Restart the frontend service: `docker compose restart frontend`.
- **Frontend won't pick up a new npm dependency** - the `frontend_node_modules`
  Docker volume can go stale after editing `package.json`. Reset it:
  ```bash
  docker compose stop frontend
  docker compose rm -f frontend
  docker volume rm ai_assignment-_frontend_node_modules
  docker compose up -d --build frontend
  ```
- **First chat message seems slow** - the backend warms the model up on
  startup, but the very first Ollama inference in a fresh container can still
  take up to a minute (CUDA/CPU kernel compilation, one-time per container
  lifetime). Subsequent messages are fast.
- **Port already in use** - something else on your machine is using 3000,
  8000, or 11434. Stop it, or change the port mapping in `docker-compose.yml`.
- **Editing `docker-compose.yml` or a Dockerfile and nothing changes** - use
  `docker compose up -d --build`, not `restart` - `restart` reuses the old
  container config (including old port mappings) instead of recreating it.

---

## Option B: Run without Docker (manual)

Useful for development, or if you'd rather not use Docker at all.

### 1. Prerequisites

- Python 3.10+ (tested on 3.12).
- Node.js 18+ and npm.
- [Ollama](https://ollama.ai/download) installed.

### 2. Install Ollama and pull the models

```bash
ollama pull llama3.2:3b
ollama pull nomic-embed-text
```

Ollama runs as a background service after installation - confirm it's up:

```bash
curl http://localhost:11434
```

### 3. Backend

```bash
python -m venv .venv
source .venv/bin/activate       # macOS / Linux
# .venv\Scripts\activate        # Windows

pip install -r requirements.txt
cp .env.example .env            # optional, edit as needed

cd backend
uvicorn main:app --reload
```

Leave this running. The API is now at `http://localhost:8000` (docs at
`/docs`). The knowledge base seeds itself from `university_faq.md` the first
time it starts.

### 4. Frontend

In a **second terminal**, from the project root:

```bash
cd frontend
npm install
npm run dev
```

The UI is now at `http://localhost:3000`.

### 5. Troubleshooting

- **Backend can't reach Ollama** - make sure `ollama serve` is running (it
  usually auto-starts after installing Ollama) and that `OLLAMA_BASE_URL` in
  `.env` points to it (default `http://localhost:11434` is correct for a
  local install).
- **`ModuleNotFoundError` on backend start** - the virtual environment isn't
  activated, or `pip install -r requirements.txt` needs a re-run after
  pulling new changes.
- **Frontend can't reach the backend** - check `VITE_API_BASE_URL` in
  `frontend/.env` (or the project root `.env`) matches where the backend is
  actually running.

---

## Verifying it's working

Either way you started it, a quick sanity check:

```bash
curl http://localhost:8000/health
# {"status":"ok","model":"llama3.2:3b","ollama_reachable":true,"model_installed":true}
```

Then open `http://localhost:3000` and ask something like *"What are the
library opening hours?"* - it should come back with a grounded answer and a
"Used knowledge base" chip.
