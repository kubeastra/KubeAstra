# Backend

FastAPI backend for the Kubeastra Web UI.

This service exposes the REST API consumed by the Next.js frontend and imports logic directly from `mcp/` — there is no duplicated Kubernetes or AI execution layer.

## What It Does

- **ReAct agent orchestration** — multi-step investigations that chain kubectl tools, analyze results, and produce root cause diagnoses with fix suggestions
- **Cluster connection management** — autodetect local kubeconfig, accept uploaded kubeconfigs, verify connectivity, manage temp files securely
- **Safe command execution** — reviewed kubectl write commands (rollout restart, scale, delete pod, patch) executed through an allowlisted endpoint
- **Intent routing** — classifies natural-language questions and routes them to the appropriate tool or triggers a full ReAct investigation
- **Session persistence** — chat history, cluster connections, and SSH targets stored in SQLite
- **Security hardening** — session ID sanitization, path traversal prevention, unknown tool rejection, temp file cleanup on shutdown

## Runtime Flow

```text
Browser
  -> Next.js frontend on :3300
  -> frontend /api/* proxy
  -> FastAPI backend on :8800
     |-- routers/chat.py      (intent classification + ReAct dispatch)
     |-- react.py             (multi-step investigation loop)
     |-- routers/cluster.py   (cluster connection lifecycle)
     +-- routers/sessions.py  (history + SSH targets)
  -> mcp shared logic
  -> kubectl / SSH / Gemini / Weaviate
```

## Key Files

- **main.py** — App setup, middleware, request logging, lifespan init
- **react.py** — ReAct loop engine: think/act/observe cycle, tool descriptions, observation truncation, 90s wall-clock timeout, fix extraction
- **db.py** — SQLite persistence (chat history, cluster connections, SSH targets, post-mortems)
- **routers/chat.py** — Main chat router: intent classification, tool dispatch, ReAct trigger, `/api/chat/execute` for safe write ops
- **routers/cluster.py** — Cluster connection: autodetect, kubeconfig upload/parse, context select, connectivity check, disconnect + cleanup
- **routers/sessions.py** — Chat history and SSH target CRUD
- **routers/health.py** — Health endpoints (`/health`, `/api/health`)
- **routers/recovery.py** — Legacy write operation endpoints (exec, delete-pod, restart, scale, patch)

## Local Run

```bash
cd ui/backend
MCP_PATH=../../mcp PYTHONPATH=../../mcp venv/bin/uvicorn main:app --reload --port 8800
```

## API Endpoints

### Chat & Investigation

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/chat` | Main chat — classifies intent, dispatches tools or triggers ReAct investigation |
| `POST` | `/api/chat/execute` | Execute a reviewed kubectl write command (allowlisted prefixes only) |

### Cluster Connection

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/cluster/autodetect` | Detect local kubeconfig contexts (or in-cluster SA) |
| `POST` | `/api/cluster/connect/kubeconfig` | Upload kubeconfig content, parse and return contexts |
| `POST` | `/api/cluster/connect/context` | Select context, verify connectivity via `kubectl cluster-info` |
| `POST` | `/api/cluster/disconnect` | Disconnect and delete temp kubeconfig |
| `GET` | `/api/cluster/status/{session_id}` | Current connection status for a session |

### Sessions

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/sessions/{id}/history` | Load chat history |
| `DELETE` | `/api/sessions/{id}/history` | Clear chat history (New Chat) |
| `GET/POST/DELETE` | `/api/sessions/{id}/ssh-target` | SSH target CRUD |

### Health

| Method | Path | Returns |
|--------|------|---------|
| `GET` | `/health` | Backend status, kubectl availability, Gemini status, Weaviate URL |
| `GET` | `/api/health` | Same (probe-friendly alias) |

## Logging

The backend emits structured logs:

- **Request level** — request ID, HTTP method, path, status, elapsed ms
- **ReAct iterations** — tool called, observation size, iteration count, wall-clock elapsed
- **Chat routing** — selected tool, SSH/cluster connection mode
- **Security events** — sanitized session IDs, rejected unknown tools, temp file operations
- **Connection events** — SSH failures, cluster connectivity checks

## Environment Variables

```bash
MCP_PATH=../../mcp
PYTHONPATH=../../mcp
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-2.5-flash
ALLOWED_NAMESPACES=*
KUBECTL_TIMEOUT_SECONDS=15
MAX_LOG_TAIL_LINES=200
ENABLE_RECOVERY_OPERATIONS=false
DB_PATH=./chat_history.db
WEAVIATE_URL=http://localhost:8080
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
```

## Verification

```bash
# Syntax check all key files
python3 -m py_compile main.py react.py routers/chat.py routers/cluster.py routers/health.py
```

Manual checks:

- `curl http://localhost:8800/health` — verify backend, kubectl, Gemini status
- `curl http://localhost:8800/api/cluster/autodetect` — should return local contexts
- Open `http://localhost:3300/chat` — connect a cluster, run an investigation
- Check backend logs for request IDs, ReAct iteration traces, and tool timing
