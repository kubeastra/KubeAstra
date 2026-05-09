# Kubeastra Web UI

A self-hosted web application that gives your entire team access to 32+ investigation tools through a **conversational chat interface** — no Cursor or AI IDE required.

Ask natural-language questions like *"are there any pods crashing?"* and Kubeastra's **ReAct agent** autonomously runs multi-step investigations — chaining kubectl calls, analyzing logs, identifying root causes, and suggesting one-click fixes — all in one conversation turn.

### Highlights

- **Multi-step ReAct investigations** — the AI agent chains tools automatically (get pods, describe, logs, events) to diagnose issues end-to-end
- **One-click fix execution** — review suggested kubectl commands and execute them directly from the UI
- **Connect any cluster** — autodetect local kubeconfig, paste a kubeconfig, or SSH into remote nodes
- **Shareable sessions** — send a link to share an investigation with your team (read-only)
- **Rich result cards** — structured pod tables, event timelines, log viewers, and resource graphs instead of raw text

---

## Architecture

```
Browser (port 3300)
    |  same-origin /api/* calls
Next.js frontend server (port 3300)
    |-- app/api/[...path]/route.ts  -- runtime proxy to backend
    |-- app/chat/page.tsx           -- primary chat UI
    |-- app/chat/[sessionId]        -- shareable session routes
    +-- lib/api.ts                  -- typed API client
    |  REST JSON
FastAPI backend (port 8800)
    |-- routers/chat.py      -- intent router + ReAct orchestrator
    |-- routers/cluster.py   -- cluster connection management
    |-- routers/sessions.py  -- chat history + SSH target API
    |-- routers/health.py    -- /health and /api/health
    |-- react.py             -- ReAct loop engine (multi-step investigations)
    |-- db.py                -- SQLite persistence (chat_history.db)
    +-- request logging      -- request_id + latency + tool dispatch logs
    |  Python imports (sys.path)
mcp/
    |-- ai_tools/    -- Gemini AI analysis
    |-- services/    -- Gemini, Weaviate, embeddings
    +-- k8s/         -- kubectl live cluster access
         |-- wrappers.py        -- high-level tool functions
         |-- kubectl_runner.py  -- local cluster (kubeconfig)
         +-- ssh_runner.py      -- remote cluster (SSH + paramiko)
    |  kubectl (local) or SSH (remote)
Kubernetes cluster
```

The backend reuses `mcp` code directly — there is no duplication.

The frontend proxies all backend calls through its own `/api/*` route, so browser requests never depend on a baked-in backend URL.

---

## Key Features

- **ReAct agent** — multi-step reasoning loop chains kubectl calls, log analysis, and AI diagnosis automatically; includes a 90-second wall-clock safety timeout
- **One-click fix execution** — after investigation, the AI suggests safe kubectl write commands (rollout restart, scale, delete pod, patch) that you can review and execute in one click
- **Manual steps fallback** — when no automated fix exists (e.g. ImagePullBackOff), the UI shows step-by-step remediation guidance
- **4-mode cluster connection** — autodetect local kubeconfig, paste/upload kubeconfig, select a specific context, or SSH into remote nodes
- **Rich result cards** — structured tables for pods, events, logs, and deployments replace raw text output
- **Shareable investigations** — every session gets a unique URL you can send to teammates for read-only viewing
- **Large cluster support** — all-namespace pod queries use text-format parsing (~100 bytes/pod) instead of JSON (~2KB/pod), handling 5000+ pod clusters
- **Runtime backend proxying** — the frontend server proxies `/api/*` to the backend at runtime via `API_BASE_URL`, avoiding rebuilds just to change backend URLs
- **SSH remote cluster support** — enter host/username/password in the SSH panel to query any remote kubeadm cluster without copying kubeconfig files
- **SQLite session persistence** — chat history, cluster connections, and SSH details survive browser reloads
- **Security hardened** — session ID sanitization, path traversal prevention, unknown tool rejection, strong entropy for session URLs

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
bash start.sh          # starts backend (8800) + frontend (3300)
```

Open **http://localhost:3300/chat**

The frontend uses:

```bash
API_BASE_URL=http://localhost:8800
```

behind the scenes and proxies browser requests through `http://localhost:3300/api/*`.

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

Open **http://localhost:3300/chat**

The `~/.kube` config is mounted read-only into the backend container, giving it kubectl access to all your local clusters.

The frontend container proxies requests to the backend container using:

```bash
API_BASE_URL=http://backend:8800
```

---

## Project Structure

```
ui/
├── backend/
│   ├── main.py              # FastAPI app — lifespan calls db.init_db()
│   ├── react.py             # ReAct loop engine — multi-step tool-calling orchestrator
│   ├── db.py                # SQLite layer (chat_history.db, sessions, cluster connections)
│   ├── routers/
│   │   ├── chat.py          # POST /api/chat — intent router + ReAct dispatcher
│   │   │                    # POST /api/chat/execute — safe kubectl write execution
│   │   ├── cluster.py       # Cluster connection — autodetect, kubeconfig upload, context select
│   │   ├── sessions.py      # GET/DELETE /api/sessions/{id}/history
│   │   │                    # GET/POST/DELETE /api/sessions/{id}/ssh-target
│   │   ├── ai_tools.py      # Legacy REST endpoints: /api/analyze, /fix, /runbook, ...
│   │   ├── kubectl.py       # Legacy REST endpoints: /api/pods, /events, /logs, ...
│   │   ├── recovery.py      # POST /api/exec, /delete-pod, /restart, /scale, /patch
│   │   └── health.py        # GET /health and /api/health
│   ├── requirements.txt
│   ├── .env.example
│   └── Dockerfile
├── frontend/
│   ├── app/
│   │   ├── api/[...path]    # Server-side proxy to backend runtime API base
│   │   ├── chat/page.tsx    # Main chat interface (primary UI)
│   │   ├── chat/[sessionId] # Shareable session routes (read-only viewing)
│   │   ├── tools/page.tsx   # Legacy form-based tool dashboard
│   │   ├── layout.tsx
│   │   └── page.tsx         # Redirects to /chat
│   ├── components/astra/    # UI components — ResultCard, RootCauseCard, IntentBar, etc.
│   ├── lib/
│   │   └── api.ts           # Typed API client (same-origin /api proxy)
│   └── Dockerfile
├── docker-compose.yml
├── setup.sh                 # One-shot local setup
└── start.sh                 # Generated by setup.sh — starts both services
```

---

## Chat Interface (`/chat`)

The primary interface. Type any Kubernetes question and the AI agent investigates automatically — often chaining multiple tools in a single response.

### Example queries

| What you type | What happens |
|---|---|
| `are there any pods crashing?` | ReAct agent scans all namespaces, identifies unhealthy pods, pulls logs, diagnoses root cause, suggests fixes |
| `list pods in the jenkins namespace` | `get_pods -n jenkins` with structured table card |
| `investigate pod my-app-xyz in prod` | Multi-step: describe pod, get logs, check events, analyze root cause |
| `what namespaces do I have?` | `kubectl get namespaces` |
| `get all resources in the platform namespace` | Aggregates pods, services, deployments, etc. |
| `any recent events that need attention?` | `get_events --all-namespaces type=Warning` |
| *(paste a raw error log)* | `analyze_error` with root cause card + fix suggestions |

### Cluster connection

Click the cluster icon in the top bar. Four connection modes:

| Mode | How it works |
|---|---|
| **Autodetect** | Reads `~/.kube/config` — select from detected contexts |
| **Paste kubeconfig** | Paste raw YAML, pick a context, connect |
| **SSH** | Enter host/username/password to tunnel kubectl to a remote node |
| **In-cluster** | Auto-detected when running inside a Kubernetes pod |

Connection state is persisted per session in SQLite. Temp kubeconfig files are written with `0600` permissions and cleaned up on disconnect or process exit.

### Shareable sessions

Every session has a unique URL like `/chat/abc123-def456`. Send it to a teammate and they see the full investigation read-only. If the session doesn't exist, a clean "not found" page is shown instead of a broken UI.

### Session persistence

Each browser tab generates a unique session ID (using `crypto.randomUUID()` for strong entropy) stored in `localStorage`. The backend saves every chat message to SQLite, so history survives page reloads. Clicking **New Chat** clears the current session's messages.

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
# The browser still calls http://localhost:3300/api/*.
API_BASE_URL=http://localhost:8800
```

---

## API Reference

The FastAPI backend auto-generates interactive docs at:
- **Swagger UI**: http://localhost:8800/docs
- **ReDoc**: http://localhost:8800/redoc

### Key endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/chat` | Main chat — intent routing, ReAct investigation, tool dispatch |
| `POST` | `/api/chat/execute` | Execute a reviewed kubectl write command |
| `GET` | `/api/cluster/autodetect` | Detect local kubeconfig contexts |
| `POST` | `/api/cluster/connect/kubeconfig` | Upload kubeconfig, get available contexts |
| `POST` | `/api/cluster/connect/context` | Select a context and verify connectivity |
| `POST` | `/api/cluster/disconnect` | Disconnect and clean up temp files |
| `GET` | `/api/cluster/status/{id}` | Current connection status for a session |
| `GET` | `/api/sessions/{id}/history` | Load chat history for a session |
| `DELETE` | `/api/sessions/{id}/history` | Clear chat history (New Chat) |
| `GET` | `/api/sessions/{id}/ssh-target` | Get saved SSH target for a session |
| `POST` | `/api/sessions/{id}/ssh-target` | Save SSH target (host/user/port — no password) |
| `DELETE` | `/api/sessions/{id}/ssh-target` | Remove saved SSH target |
| `GET` | `/health` | Health check (probe-friendly path) |
| `GET` | `/api/health` | Health check |

### Logging

The backend emits structured logs including:

- request-level logs with request ID, method, path, status, and elapsed time
- ReAct iteration logs with tool calls, observation sizes, and wall-clock timing
- chat routing logs with selected tool and SSH/cluster connection usage
- tool dispatch timing logs
- security events (sanitized session IDs, rejected unknown tools)

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
