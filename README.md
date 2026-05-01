# Kubeastra

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Next.js 16](https://img.shields.io/badge/Next.js-16-black.svg)](https://nextjs.org/)
[![MCP compatible](https://img.shields.io/badge/MCP-compatible-green.svg)](https://modelcontextprotocol.io)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

**Your clusters are talking. This assistant helps you listen.**

An AI-powered Kubernetes troubleshooting assistant that lets teams investigate, diagnose, and resolve cluster issues through natural language — via a **chat-based web UI** or directly inside your **IDE (Cursor / Claude Desktop / VS Code via MCP)**.

Combines live `kubectl` access with pluggable LLM providers (Gemini, Ollama/local, more coming) for root-cause analysis that turns cryptic Kubernetes failures into clear answers and actionable fix commands.

## See it in action

<!--
  GitHub renders this <video> tag inline on the rendered README page.
  The file lives in docs/kubeastra-demo.webm and is served via raw.githubusercontent.
  If the embed ever fails, the link below is the fallback.
-->
<video src="https://github.com/user-attachments/assets/5a75787b-fa5f-4fe8-a4ad-4abef4ff0f1b" controls width="100%"></video>

▶ [Watch the 90-second demo](docs/kubeastra-demo.webm) — Kubeastra walking through 7 real Kubernetes failures (CrashLoopBackOff, OOMKilled, ImagePullBackOff, stuck PVC, unschedulable pod, namespace-wide health, runbook generation).

> Want to reproduce it locally? `make demo` spins up a kind cluster pre-seeded with six broken workloads. See [`demo/README.md`](demo/README.md).

---

## Why this exists

Every DevOps engineer has been here: a pod is crashlooping at 2 AM, and you're mentally chaining together `kubectl get`, `kubectl describe`, `kubectl logs`, cross-referencing events, checking resource limits, and Googling error messages — all while half asleep.

This tool handles that investigation loop for you:

- **Ask in plain English** — *"Why is payment-service crashing in production?"*
- **Get root-cause analysis** — not just logs, but AI-synthesized explanations of what's wrong and why
- **Receive fix commands** — ready to run, with safety confirmations for write operations
- **Generate runbooks** — so your team doesn't debug the same issue twice
- **Stay on your own infra** — run entirely locally with Ollama, no data leaves your cluster

---

## Key Features

### 🔍 33 Built-in Kubernetes Tools

**Live cluster tools (27)** — pod/deployment/service inspection, event streams, multi-namespace discovery, rollout status, kubeconfig context switching, log retrieval with previous-container support, resource-graph topology, and safe write operations (delete, scale, restart, patch — all gated behind `confirm=true`).

**AI analysis tools (6)** — error analysis with RAG-backed similarity search, curated fix playbooks for 11 error categories, AI-generated runbooks, cluster health reports, post-incident summarization.

### 💬 Two Ways to Use It

| Web UI | IDE / MCP Integration |
|---|---|
| Chat-based Next.js interface for team-wide troubleshooting | Direct integration into Cursor, Claude Desktop, or any MCP client |
| Shareable sessions with persistent chat history (SQLite) | Debug without leaving your editor |
| SSH panel to attach to any remote kubeadm cluster | 33 tools available via stdio or HTTP MCP transport |

### 🔌 Pluggable LLM Providers

Pick your LLM — **Google Gemini** (default, free tier available) or **Ollama** (fully local — your cluster data never leaves your network). OpenAI and Anthropic Claude adapters coming next.

### 🛡️ Safety First

- **Read-only by default** — all `kubectl` commands are validated before execution
- **Explicit confirmation required** for write operations (`delete`, `scale`, `restart`, `patch`)
- **Full audit logging** of every command executed
- **RBAC-aware** — respects your existing Kubernetes permissions
- **Input validation** — namespace/name/label selector safety checks prevent injection

### 🚀 Deploy Anywhere

- **Local dev** — docker-compose one-liner
- **Kind demo cluster** — `make demo` spins up a broken cluster so you can see the tool work in 60 seconds
- **Production Helm chart** — deploy into the same clusters it monitors
- **SSH multi-cluster** — query any remote kubeadm cluster without copying kubeconfigs

---

## Quick Start

### Prerequisites

- A running Kubernetes cluster with `kubectl` access (or use `make demo`)
- An LLM: either a [Google Gemini API key](https://aistudio.google.com/) (free tier works) **or** [Ollama](https://ollama.com/) running locally

### Option 1: Try the demo (60 seconds, no cluster needed)

```bash
git clone https://github.com/AskKube/kubeastra.git
cd kubeastra
make demo
```

Spins up a local kind cluster with pre-broken workloads (CrashLoop, OOM, ImagePull, stuck PVC) and launches the web UI. Open http://localhost:3000 and ask *"what's broken in the demo namespace?"*.

### Option 2: Run locally against your own cluster

```bash
# 1. Configure the backend
cp ui/backend/.env.example ui/backend/.env
#    → set GEMINI_API_KEY (or LLM_PROVIDER=ollama) in .env

# 2. Start via docker-compose (kubeconfig mounted read-only)
cd ui
docker compose up --build

# 3. Open http://localhost:3000
```

### Option 3: Use via MCP (Cursor / Claude Desktop)

```bash
cd mcp
./setup.sh        # creates venv, installs deps, writes MCP config entry
```

Edit `mcp/.env`:
```env
GEMINI_API_KEY=your-key-here          # or LLM_PROVIDER=ollama
ALLOWED_NAMESPACES=prod,staging,default
```

Restart your IDE — all 33 tools appear as MCP tools.

### Option 4: Deploy to Kubernetes via Helm

```bash
helm upgrade --install kubeastra helm/kubeastra \
  --namespace kubeastra --create-namespace \
  --set backend.image.repository=ghcr.io/your-org/kubeastra-backend \
  --set frontend.image.repository=ghcr.io/your-org/kubeastra-frontend \
  --set secrets.geminiApiKey="YOUR_KEY" \
  --set secrets.kubeconfig="$(cat ~/.kube/config | base64 | tr -d '\n')"
```

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                    Frontends                          │
│  ┌──────────────────┐   ┌──────────────────────────┐  │
│  │  Web Chat UI     │   │  MCP Server              │  │
│  │  (Next.js)       │   │  (stdio + HTTP transport)│  │
│  └────────┬─────────┘   └──────────┬───────────────┘  │
│           │                        │                  │
│  ┌────────▼────────────────────────▼───────────────┐  │
│  │         mcp (Core Engine)            │  │
│  │                                                 │  │
│  │  ┌──────────────┐     ┌──────────────────────┐  │  │
│  │  │ kubectl      │     │ LLM Providers        │  │  │
│  │  │ wrappers     │     │ (Gemini / Ollama)    │  │  │
│  │  │ (27 tools)   │     │ + AI tools (6 tools) │  │  │
│  │  └──────┬───────┘     └──────────┬───────────┘  │  │
│  │         │                        │              │  │
│  │  ┌──────▼──────┐      ┌──────────▼───────────┐  │  │
│  │  │ Local or    │      │ Weaviate (optional)  │  │  │
│  │  │ SSH runner  │      │ RAG similarity       │  │  │
│  │  └──────┬──────┘      └──────────────────────┘  │  │
│  └─────────┼──────────────────────────────────────┘  │
│            │                                          │
│   ┌────────▼────────┐                                 │
│   │  Kubernetes     │                                 │
│   │  Cluster(s)     │                                 │
│   └─────────────────┘                                 │
└──────────────────────────────────────────────────────┘
```

**Core design principle:** a single shared library (`mcp`) provides all investigation logic and AI tools, consumed by two independent frontends. Every tool works identically whether you're in the web UI, Cursor, or Claude Desktop.

Full architecture deep-dive: [`docs/ARCHITECTURE_DIAGRAM.md`](docs/ARCHITECTURE_DIAGRAM.md)

---

## How It Works

1. **You ask a question** — *"Why are pods in checkout-service not starting?"*
2. **Intent classification** — LLM (Gemini or local Ollama) picks the right tool + extracts params. Falls back to a 30+ pattern regex router if no LLM key is set.
3. **Auto-discovery** — if you don't specify a namespace, `find_workload` searches across all namespaces.
4. **Live investigation** — executes read-only `kubectl` commands against your cluster (or over SSH if you've connected a remote node).
5. **AI synthesis** — instead of dumping raw JSON, returns a clear 2–3 sentence diagnosis with root cause and next steps.
6. **Persistence** — every message, tool call, and result saved to SQLite so you can pick up where you left off.

---

## Example Interaction

```
You: Why is my-app crashing in the dev namespace?Assistant: my-app-7d4f9b-xkj2p is in CrashLoopBackOff. The container is failing
with exit code 1 during startup — the application logs show a connection
refused error to redis-master:6379. The Redis pod in this namespace is in
Pending state due to an unbound PVC.

Suggested fix:
  kubectl get pvc -n dev                   # Check PVC status
  kubectl describe pvc redis-data -n dev   # Check binding issue

Would you like me to generate a runbook for Redis PVC recovery?
```

---

## Configuration

All settings are read from environment variables (or `.env`):

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `gemini` | `gemini` or `ollama` |
| `GEMINI_API_KEY` | — | Required when `LLM_PROVIDER=gemini`. [Get one free](https://aistudio.google.com/) |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model to use |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `llama3.1` | Ollama model name (must be pulled first) |
| `ALLOWED_NAMESPACES` | `*` | Comma-separated list, or `*` for all |
| `KUBECTL_TIMEOUT_SECONDS` | `15` | Per-command timeout |
| `MAX_LOG_TAIL_LINES` | `200` | Max log lines per request |
| `ENABLE_RECOVERY_OPERATIONS` | `false` | Enables `delete_pod`, `rollout_restart`, `scale`, `apply_patch` |
| `WEAVIATE_URL` | `http://localhost:8080` | Optional RAG vector DB |

---

## Repository Layout

```
kubeastra/
├── ui/
│   ├── frontend/          # Next.js chat UI
│   ├── backend/           # FastAPI app + SQLite persistence
│   └── docker-compose.yml
├── mcp/
│   ├── mcp_server/        # MCP server (stdio + HTTP transports)
│   ├── k8s/               # kubectl wrappers, SSH runner, validators
│   ├── ai_tools/          # Error analysis, runbooks, error summary
│   ├── services/          # LLM providers, Weaviate, embeddings
│   └── config/settings.py
├── helm/kubeastra/   # Helm chart
├── demo/                        # Kind + broken workloads for `make demo`
└── docs/                        # Architecture diagrams, deployment guide
```

---

## Roadmap

- [x] Gemini + Ollama (local) LLM support
- [x] Demo mode with kind cluster
- [x] Visual resource graph (Ingress → Service → Deployment → Pod)
- [ ] OpenAI + Anthropic Claude adapters
- [ ] Slack bot integration (alert-driven investigation)
- [ ] "What changed?" view — recent deployments, configmap/secret mutations
- [ ] Agentic investigation loop (multi-step ReAct)
- [ ] Prometheus/Grafana metrics integration
- [ ] Shareable session URLs
- [ ] CLI tool (`kubeastra investigate <pod>`)
- [ ] VS Code extension (beyond MCP)
- [ ] Post-mortem generator
- [ ] CNCF Sandbox submission

---

## Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for local setup, project layout, and how to add a new tool.

---

## License

Apache 2.0 — see [LICENSE](LICENSE) for details.
