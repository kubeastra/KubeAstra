# Kubeastra Web UI

A self-hosted web application that gives your entire team access to the 32 `mcp` tools through a **conversational chat interface** — no Cursor or AI IDE required.

Users can ask natural language questions like *"are there any warnings in the cluster?"* or *"investigate pod my-app in the jenkins namespace"*, and the backend automatically routes to the right kubectl tool and returns a concise Gemini-powered summary.

---

## Architecture

```
Browser (port 3000)
    ↓  same-origin /api/* calls
Next.js frontend server (port 3000)
    ├── app/api/[...path]/route.ts  → runtime proxy to backend
    ├── app/chat/page.tsx           → primary chat UI
    └── lib/api.ts                  → typed API client using same-origin /api
    ↓  REST JSON
FastAPI backend (port 8000)
    ├── routers/chat.py      → Gemini intent router + tool dispatcher
    ├── routers/sessions.py  → Chat history + SSH target API
    ├── routers/health.py    → /health and /api/health
    ├── db.py                → SQLite persistence (chat_history.db)
    └── request logging      → request_id + latency + tool dispatch logs
    ↓  Python imports (sys.path)
mcp/
    ├── ai_tools/    → Gemini AI analysis
    ├── services/    → Gemini, Weaviate, embeddings
    └── k8s/         → kubectl live cluster access
         ├── kubectl_runner.py   → local cluster (kubeconfig)
         └── ssh_runner.py       → remote cluster (SSH + paramiko)
    ↓  kubectl (local) or SSH (remote)
Kubernetes cluster
```

The backend reuses `mcp` code directly — there is no duplication.

The frontend now proxies backend calls through its own `/api/*` route, so browser requests no longer depend on a baked-in backend URL.

---

## Key Features

- **Chat interface** — natural language questions routed to the right kubectl tool automatically
- **Gemini-powered summaries** — results are synthesized into direct 1-2 sentence answers
- **Runtime backend proxying** — the frontend server proxies `/api/*` to the backend at runtime via `API_BASE_URL`, avoiding rebuilds just to change backend URLs
- **SSH remote cluster support** — enter host/username/password in the SSH panel to query any remote kubeadm cluster without copying kubeconfig files
- **SQLite session persistence** — chat history and SSH connection details survive browser reloads
- **All-namespace queries** — "are there any warnings?" searches across all namespaces automatically
- **SSH reconnect banner** — if you reload the browser mid-session, a banner prompts for just the password to reconnect instantly
- **Request and tool logging** — backend logs now include request IDs, request latency, tool routing, tool dispatch timing, and SSH connection failures

---

## Quick Start (Local, No Docker)

### 1. Run setup

```bash
cd kubeastra/ui
bash setup.sh
```

### 2. Edit backend `.env`

```bash
# backend/.env
GEMINI_API_KEY=your_key_here          # required for AI features
ALLOWED_NAMESPACES=*
ENABLE_RECOVERY_OPERATIONS=false      # set true for write ops
```

### 3. Start both services

```bash
bash start.sh          # starts backend (8000) + frontend (3000)
```

Open **http://localhost:3000/chat**

The frontend uses:

```bash
API_BASE_URL=http://localhost:8000
```

behind the scenes and proxies browser requests through `http://localhost:3000/api/*`.

For `make demo`, the backend still reads `ui/backend/.env`, but the demo flow injects a generated kubeconfig and a temporary Compose env override so the container talks to the `kind-kubeastra-demo` cluster instead of relying on your host's current kubectl context or modifying `ui/.env`.

---

## Quick Start (Docker Compose)

Requires Docker Desktop running.

```bash
cd kubeastra/ui

# Copy and edit .env
cp backend/.env.example backend/.env
# edit backend/.env → set GEMINI_API_KEY

# Start backend + frontend
docker compose up --build
```

Open **http://localhost:3000/chat**

The `~/.kube` config is mounted read-only into the backend container, giving it kubectl access to all your local clusters.

The frontend container proxies requests to the backend container using:

```bash
API_BASE_URL=http://backend:8000
```

---

## Project Structure

```
ui/
├── backend/
│   ├── main.py              # FastAPI app — lifespan calls db.init_db()
│   ├── db.py                # SQLite layer (chat_history.db, sessions, ssh_targets)
│   ├── routers/
│   │   ├── chat.py          # POST /api/chat — Gemini router + tool dispatcher
│   │   ├── sessions.py      # GET/DELETE /api/sessions/{id}/history
│   │   │                    # GET/POST/DELETE /api/sessions/{id}/ssh-target
│   │   ├── ai_tools.py      # Legacy REST endpoints: /api/analyze, /fix, /runbook, ...
│   │   ├── kubectl.py       # Legacy REST endpoints: /api/pods, /events, /logs, ...
│   │   ├── recovery.py      # POST /api/exec, /delete-pod, /restart, /scale, /patch
│   │   └── health.py        # GET /health and /api/health
│   ├── requirements.txt     # Includes fastapi, uvicorn, google-genai, paramiko
│   ├── .env.example
│   └── Dockerfile
├── frontend/
│   ├── app/
│   │   ├── api/[...path]    # Server-side proxy to backend runtime API base
│   │   ├── chat/page.tsx    # ★ Main chat interface (primary UI)
│   │   ├── tools/page.tsx   # Legacy form-based tool dashboard
│   │   ├── layout.tsx
│   │   └── page.tsx         # Redirects to /chat
│   ├── lib/
│   │   └── api.ts           # Typed API client (same-origin /api proxy + legacy form helpers)
│   └── Dockerfile
├── docker-compose.yml
├── setup.sh                 # One-shot local setup
└── start.sh                 # Generated by setup.sh — starts both services
```

---

## Chat Interface (`/chat`)

The primary interface. Type any Kubernetes question and the AI routes it to the right tool automatically.

### Example queries

| What you type | What happens |
|---|---|
| `are there any warnings?` | `get_events --all-namespaces type=Warning` |
| `list pods in the jenkins namespace` | `get_pods -n jenkins` |
| `investigate pod my-app-xyz in prod` | Full kubectl playbook + Gemini diagnosis |
| `what namespaces do I have?` | `kubectl get namespaces` |
| `get all resources in the platform namespace` | Aggregates pods, services, deployments, etc. |
| `any recent events that need attention?` | `get_events --all-namespaces` |
| *(paste a raw error log)* | `analyze_error` → Gemini root cause + fix commands |

### SSH panel

Click the SSH icon in the top bar to connect to a remote kubeadm cluster. Enter:
- **Host** — IP or hostname of the master node
- **Username** — SSH user (e.g. `ubuntu`, `root`)
- **Password** — SSH password
- **Port** — defaults to `22`

All kubectl queries for that session are then routed over SSH to the remote cluster. Host, username, and port are saved to SQLite so a reconnect banner appears on page reload (password is never stored).

### Session persistence

Each browser tab generates a unique session ID stored in `localStorage`. The backend saves every chat message to `chat_history.db` (SQLite), so history survives page reloads. Clicking **New Chat** clears the current session's messages.

---

## Environment Variables

```bash
# backend/.env

# Path to mcp (only needed for local/non-Docker runs)
MCP_PATH=../../mcp

# Gemini
GEMINI_API_KEY=...                 # required for AI intent routing and answer synthesis
GEMINI_MODEL=gemini-2.5-flash

# kubectl tuning
ALLOWED_NAMESPACES=*
KUBECTL_TIMEOUT_SECONDS=15
MAX_LOG_TAIL_LINES=200
ENABLE_RECOVERY_OPERATIONS=false   # set true to allow write ops (scale, delete, exec)

# SQLite persistence
DB_PATH=./chat_history.db          # path to SQLite file (default: next to main.py)

# RAG (optional — requires Weaviate)
WEAVIATE_URL=http://localhost:8080
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
```

```bash
# frontend runtime env

# Server-side proxy target used by app/api/[...path]/route.ts.
# The browser still calls http://localhost:3000/api/*.
API_BASE_URL=http://localhost:8000
```

---

## API Reference

The FastAPI backend auto-generates interactive docs at:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Key endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/chat` | Main chat endpoint — routes message and returns reply + tool result |
| `GET` | `/api/sessions/{id}/history` | Load chat history for a session |
| `DELETE` | `/api/sessions/{id}/history` | Clear chat history (New Chat) |
| `GET` | `/api/sessions/{id}/ssh-target` | Get saved SSH target for a session |
| `POST` | `/api/sessions/{id}/ssh-target` | Save SSH target (host/user/port — no password) |
| `DELETE` | `/api/sessions/{id}/ssh-target` | Remove saved SSH target |
| `GET` | `/health` | Health check (probe-friendly path) |
| `GET` | `/api/health` | Health check |

### Logging

The backend now emits:

- request-level logs with request ID, method, path, status, and elapsed time
- chat routing logs with selected tool and SSH usage
- tool dispatch timing logs
- SSH connection failure logs

---

## Deploying to a Team Server

Deploy on any Linux server with Docker and kubectl access:

```bash
# 1. Clone the repo on the server
git clone <your-repo> /opt/kubeastra
cd /opt/kubeastra/ui

# 2. For local cluster access — copy kubeconfig to server
scp ~/.kube/config server:/root/.kube/config

# 3. Create .env
cp backend/.env.example backend/.env
# edit backend/.env → set GEMINI_API_KEY

# 4. Build and start
docker compose up -d --build
```

For team access, point a DNS record at the server and put nginx or Traefik in front with HTTPS.

> **Tip:** If users access remote clusters via SSH, no kubeconfig needs to be on the central server at all — users provide SSH credentials through the chat UI per session.

> **Runtime config note:** The frontend no longer needs a rebuild just to point at a different backend URL. Set the frontend container's `API_BASE_URL` at runtime instead.
