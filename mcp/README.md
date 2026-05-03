# mcp — Unified Kubernetes DevOps MCP Server

A single, unified MCP (Model Context Protocol) server that merges the best of two projects:

| Source | What it brought |
|--------|----------------|
| `mcp-k8s-investigation-agent` | Live kubectl tools, multi-cluster support, recovery operations, deployment repo search |
| `k8s-ansible-mcp` | Gemini AI error analysis, RAG similarity search, fix playbooks, runbook generation |

**Result: 33 tools in one server**, covering the full DevOps loop — investigate → diagnose → fix → document.

The same toolset is available through two MCP transports:
- `stdio` for local IDE integration
- `streamable-http` for remote IDE or cross-workspace testing

---

## What's New vs. the Individual Projects

1. **`investigate_pod` now includes Gemini AI** — after running the kubectl playbook, it automatically calls Gemini to produce a root-cause analysis and copy-paste fix commands from the live data.
2. **SSH remote cluster support** — query any remote kubeadm cluster by passing SSH credentials (host/username/password). No kubeconfig copy needed on the central server.
3. **All-namespace queries** — `get_events` and `get_pods` accept `namespace="*"` to search across all namespaces (equivalent to `kubectl -A`).
4. **Single Cursor config entry** — one `kubeastra` entry in `~/.cursor/mcp.json` replaces two.
5. **Unified settings** — one `.env` file covers both kubectl tuning and AI API keys.

---

## Quick Start

```bash
cd kubeastra/mcp
./setup.sh
```

Then edit `.env`:
```bash
GEMINI_API_KEY=your_key_here
ALLOWED_NAMESPACES=prod,staging,dev,default
```

Restart Cursor — the `kubeastra` MCP server will be active with all 33 tools.

To expose the server over localhost HTTP for another IDE:
```bash
make run-http
```
Then point the IDE at:
```text
http://127.0.0.1:8001/mcp/
```

---

## Project Structure

```
mcp/
├── mcp_server/
│   ├── server.py       # MCP entry point (stdio server)
│   ├── runtime.py      # Shared MCP bootstrap helpers
│   ├── tools.py        # All 33 tool registrations
│   └── schemas.py      # Pydantic input schemas for all tools
├── http_mcp/
│   ├── http_server.py  # Streamable HTTP MCP endpoint at /mcp
│   ├── http_client.py  # Example HTTP MCP test client
│   └── README.md       # HTTP transport setup and usage
├── k8s/
│   ├── wrappers.py     # kubectl wrappers + AI-enhanced investigate_pod
│   ├── kubectl_runner.py  # Local kubectl runner + ContextVar for SSH routing
│   ├── ssh_runner.py   # SSH-based kubectl runner (paramiko) for remote clusters
│   ├── parsers.py
│   └── validators.py
├── services/
│   ├── llm_service.py  # Gemini AI (analyze, summarize, live investigation, runbook)
│   ├── vector_db.py    # Weaviate RAG
│   ├── embeddings.py   # sentence-transformers
│   └── error_parser.py # K8s + Ansible error classification (regex patterns)
├── ai_tools/
│   ├── analyze.py      # analyze_error tool
│   ├── fix.py          # get_fix_commands + list_error_categories
│   ├── report.py       # cluster_report + error_summary
│   └── runbook.py      # generate_runbook
├── config/
│   └── settings.py     # Merged Pydantic settings (kubectl + AI + RAG)
├── data/
│   └── seed.py         # Seed Weaviate with sample K8s/Ansible errors
├── docker-compose.yml  # Weaviate only (for RAG features)
├── requirements.txt    # All dependencies
├── .env.example        # Template environment config
├── setup.sh            # One-shot setup
└── Makefile            # Common tasks
```

---

## All 33 Tools

### Live kubectl Tools (26)

| Tool | What it does |
|------|-------------|
| `find_workload` | Search for pods/deployments/services by name across namespaces |
| `get_pods` | List pods in a namespace (or all namespaces with `namespace="*"`) |
| `get_namespaces` | List all namespaces in the cluster |
| `list_namespace_resources` | Aggregate view of all major resource types in a namespace |
| `list_services` | List all services in a namespace |
| `describe_pod` | Full pod description with parsed highlights |
| `get_pod_logs` | Fetch current or previous container logs |
| `get_events` | Namespace events sorted by timestamp; use `namespace="*"` for all namespaces |
| `get_deployment` | Deployment status and replica counts |
| `get_service` | Service details and port config |
| `get_endpoints` | Check which pods back a service |
| `get_rollout_status` | Monitor deployment rollout progress |
| `k8sgpt_analyze` | Run k8sgpt CLI analysis (optional) |
| `add_kubeconfig_context` | Add a cluster via SSH |
| `list_kubeconfig_contexts` | List available cluster contexts |
| `switch_kubeconfig_context` | Switch active cluster |
| `get_current_context` | Show active cluster |
| `search_deployment_repo` | Search Ansible/Helm repo for configs |
| `get_deployment_repo_file` | Read a file from the deployment repo |
| `list_deployment_repo_path` | Browse the deployment repo structure |
| `investigate_pod` ⭐ | Full triage: kubectl playbook **+ Gemini AI diagnosis** |
| `exec_pod_command` | Run a command inside a pod (requires confirm) |
| `delete_pod` | Force restart a pod (requires confirm) |
| `rollout_restart` | Rolling restart a deployment (requires confirm) |
| `scale_deployment` | Scale replicas up/down (requires confirm) |
| `apply_patch` | Patch a K8s resource (requires confirm) |

### AI Analysis Tools (6)

| Tool | What it does |
|------|-------------|
| `analyze_error` | Paste any K8s/Ansible error → Gemini root cause + fix commands |
| `get_fix_commands` | Get curated copy-paste fix commands for an error category |
| `list_error_categories` | List all 20+ supported error categories |
| `cluster_report` | Paste kubectl events → AI cluster health report |
| `error_summary` | Summarize a batch of errors from CI/CD logs |
| `generate_runbook` | Generate a full markdown runbook for a recurring error |

---

## SSH Remote Cluster Support

The MCP server can query remote kubeadm clusters without a local kubeconfig by using SSH:

```python
# The kubectl_runner uses a ContextVar to switch between local and SSH runners.
# When SSH credentials are provided (via ui chat), all kubectl calls
# for that request are transparently routed over SSH to the remote master node.
```

This allows one central deployment to debug multiple `qa`/`dev`/`staging` clusters without
copying kubeconfig files onto the central server.

---

## Cursor Usage

Once set up, use natural language in Cursor chat:

```
investigate the pod payment-service-7d4f9b in namespace prod
```
→ Runs kubectl playbook + Gemini AI diagnosis in one shot.

```
I'm seeing this error in my CI/CD pipeline: [paste error]
```
→ Uses `analyze_error` for AI root cause + fix commands.

```
generate a runbook for pod_crashloop errors
```
→ Produces a Confluence-ready markdown runbook.

```
switch to the staging cluster and get events for the default namespace
```
→ Uses `switch_kubeconfig_context` then `get_events`.

---

## Configuration

All config lives in `.env`. Key variables:

```bash
# Required
ALLOWED_NAMESPACES=prod,staging,dev,default
GEMINI_API_KEY=your_key_here

# Kubectl tuning
KUBECTL_TIMEOUT_SECONDS=15
MAX_LOG_TAIL_LINES=200
ENABLE_RECOVERY_OPERATIONS=false   # set true to enable write operations

# RAG (optional — requires `make docker-up && make seed`)
WEAVIATE_URL=http://localhost:8080
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
```

---

## Cursor MCP Config (`~/.cursor/mcp.json`)

```json
{
  "mcpServers": {
    "kubeastra": {
      "command": "<absolute-path>/kubeastra/mcp/venv/bin/python",
      "args": ["<absolute-path>/kubeastra/mcp/mcp_server/server.py"],
      "env": {
        "PYTHONPATH": "<absolute-path>/kubeastra/mcp",
        "ALLOWED_NAMESPACES": "prod,staging,dev,default"
      }
    }
  }
}
```

Replace `<absolute-path>` with the output of `pwd` run from inside `kubeastra/`.

## HTTP MCP Config (`~/.cursor/mcp.json` or another IDE)

Run the HTTP transport locally:

```bash
cd kubeastra/mcp
make run-http
```

Then use this remote MCP config:

```json
{
  "mcpServers": {
    "kubeastra-http": {
      "url": "http://127.0.0.1:8001/mcp/"
    }
  }
}
```

Optional auth:

```bash
export MCP_HTTP_AUTH_TOKEN=dev-local-token
make run-http
```

```json
{
  "mcpServers": {
    "kubeastra-http": {
      "url": "http://127.0.0.1:8001/mcp/",
      "headers": {
        "Authorization": "Bearer dev-local-token"
      }
    }
  }
}
```

---

## Optional: Enable RAG (Weaviate)

The AI tools work without Weaviate — Gemini analyzes errors without past history.
With Weaviate enabled, `analyze_error` also returns similar past cases ranked by semantic similarity.

```bash
make docker-up   # starts Weaviate at http://localhost:8080
make seed        # loads ~60 sample K8s/Ansible errors
```

---

## Makefile Commands

```bash
make setup            # First-time setup
make install          # Install/update dependencies
make docker-up        # Start Weaviate
make seed             # Seed vector DB
make run              # Start MCP server via stdio (for Cursor)
make run-http         # Start HTTP MCP server on 127.0.0.1:8001 (local IDE testing)
make run-http-external  # Start HTTP MCP server on 0.0.0.0:8001 (network-accessible)
make test             # Run tests
make clean            # Remove venv and caches
```
