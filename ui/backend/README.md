# Backend

FastAPI backend for the Kubeastra Web UI.

This service exposes the REST API used by the Next.js frontend and imports logic directly from `mcp` so there is no duplicated Kubernetes or AI execution layer.

## What Changed

- Health checks now work on both `/health` and `/api/health`
- Added request logging middleware with request IDs and latency
- Added chat/tool dispatch logs in `routers/chat.py`
- Frontend integration now assumes same-origin `/api/*` calls from the browser, with the Next.js server proxying requests here

## Responsibilities

- serve chat requests at `POST /api/chat`
- persist chat history and SSH target metadata in SQLite
- expose health, session, kubectl, AI, and recovery endpoints
- route natural-language chat requests into `mcp` wrapper/tool calls
- switch to SSH-backed kubectl execution when per-request SSH credentials are supplied

## Runtime Flow

```text
Browser
  -> Next.js frontend on :3000
  -> frontend /api/* proxy
  -> FastAPI backend on :8000
  -> mcp shared logic
  -> kubectl / SSH / Gemini / Weaviate
```

## Key Files

- [main.py](/path/to/kubeastra/ui/backend/main.py)
  App setup, middleware, request logging, lifespan init
- [db.py](/path/to/kubeastra/ui/backend/db.py)
  SQLite persistence
- [routers/chat.py](/path/to/kubeastra/ui/backend/routers/chat.py)
  Main chat router and dispatcher
- [routers/health.py](/path/to/kubeastra/ui/backend/routers/health.py)
  Health endpoints
- [routers/sessions.py](/path/to/kubeastra/ui/backend/routers/sessions.py)
  Chat history and SSH target endpoints

## Local Run

```bash
cd ui/backend
MCP_PATH=../../mcp PYTHONPATH=../../mcp venv/bin/uvicorn main:app --reload --port 8000
```

## Health Endpoints

- `GET /health`
- `GET /api/health`

These return:

- backend status
- whether `kubectl` is available
- current kubectl context when available
- whether Gemini is enabled
- configured Weaviate URL

## Logging

The backend now logs:

- request ID
- HTTP method
- request path
- response status
- elapsed time in milliseconds
- selected chat tool
- tool dispatch duration
- SSH connection failures

This makes local debugging and container operations much easier.

## Environment Variables

```bash
MCP_PATH=../../mcp
PYTHONPATH=../../mcp
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-2.5-flash
ALLOWED_NAMESPACES=prod,staging,dev,default
KUBECTL_TIMEOUT_SECONDS=15
MAX_LOG_TAIL_LINES=200
ENABLE_RECOVERY_OPERATIONS=false
DB_PATH=./chat_history.db
WEAVIATE_URL=http://localhost:8080
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
```

## Verification

```bash
python3 -m py_compile main.py routers/chat.py routers/health.py
```

Manual checks:

- `curl http://localhost:8000/health`
- `curl http://localhost:8000/api/health`
- open `http://localhost:3000/chat`
- submit a chat request and inspect backend logs for request IDs and tool timing
