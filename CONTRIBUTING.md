# Contributing

Thanks for your interest in contributing! Whether you're fixing a bug, adding a new Kubernetes investigation tool, improving documentation, or proposing a feature — your contributions help the entire DevOps community debug smarter.

---

## Getting Started

### 1. Fork and Clone

```bash
git clone https://github.com/YOUR_USERNAME/kubeastra.git
cd kubeastra
```

### 2. Set Up Your Development Environment

**Core engine (`mcp`):**

```bash
cd mcp
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**Web UI backend:**

```bash
cd ui/backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env       # then fill in GEMINI_API_KEY or LLM_PROVIDER=ollama
```

**Web UI frontend:**

```bash
cd ui/frontend
npm install
```

### 3. Verify Everything Works

```bash
# Run tests
cd mcp && pytest

# Start the backend (from ui/backend/)
uvicorn main:app --reload

# Start the frontend (from ui/frontend/)
npm run dev
```

You'll need a running Kubernetes cluster (local clusters like kind, minikube, or k3d work fine) and either a Gemini API key or a running Ollama instance. The fastest path is `make demo` from the repo root, which spins up a kind cluster with pre-broken workloads.

---

## How to Contribute

### Reporting Bugs

Open an issue with:
- What you expected to happen
- What actually happened
- Steps to reproduce
- Your environment (K8s version, Python version, OS)
- Relevant logs or screenshots

### Suggesting Features

Open an issue with the `feature-request` label. Include:
- The problem you're trying to solve
- Your proposed approach (if you have one)
- How it would benefit other users

### Submitting Code

1. **Check existing issues** — look for `good-first-issue` or `help-wanted` labels
2. **Open an issue first** for significant changes — let's align on the approach before you invest time
3. **Create a feature branch** from `main`
4. **Write tests** for new tools or logic changes
5. **Submit a pull request** with a clear description of what and why

---

## Project Structure

Understanding where things live will help you contribute to the right place:

```
kubeastra/
├── mcp/              # Core engine — all K8s tools and AI logic
│   ├── k8s/
│   │   ├── wrappers.py          # High-level kubectl workflows (the main API)
│   │   ├── kubectl_runner.py    # Safe local kubectl execution
│   │   ├── ssh_runner.py        # SSH-backed kubectl for remote nodes
│   │   ├── validators.py        # Safety checks (namespace, name, selectors)
│   │   └── parsers.py           # Structured output parsing
│   ├── ai_tools/                # AI analysis, fix playbooks, runbooks, reports
│   ├── services/                # LLM providers, Weaviate RAG, embeddings, error parsing
│   ├── mcp_server/              # MCP protocol server (stdio + HTTP transports)
│   ├── http_mcp/                # HTTP MCP transport client + server
│   └── config/settings.py       # Pydantic settings
├── ui/
│   ├── backend/                 # FastAPI — chat routing + tool orchestration
│   │   ├── main.py              # App entrypoint
│   │   ├── routers/chat.py      # Main chat flow + intent classification
│   │   ├── routers/sessions.py  # Session history + SSH target APIs
│   │   └── db.py                # SQLite persistence
│   └── frontend/                # Next.js chat interface
├── helm/kubeastra/   # Helm chart
├── demo/                        # kind config + broken workloads for `make demo`
└── docs/                        # Architecture, deployment guide, runbooks
```

### Where to Make Changes

| I want to... | Look here |
|---|---|
| Add a new kubectl investigation tool | `mcp/k8s/wrappers.py` + register in `mcp_server/tools.py` |
| Improve AI analysis or prompts | `mcp/ai_tools/` + `mcp/services/llm_service.py` |
| Add a new LLM provider | `mcp/services/llm/` (see `base.py` for the interface) |
| Fix chat routing or intent classification | `ui/backend/routers/chat.py` |
| Update the web interface | `ui/frontend/` (Next.js + TypeScript) |
| Modify the Helm deployment | `helm/kubeastra/` |
| Add broken workloads to the demo | `demo/broken-workloads/` |

---

## Adding a New Kubernetes Tool

This is the most common type of contribution. Here's the pattern:

1. Add the wrapper function in `mcp/k8s/wrappers.py`
2. Use `KubectlRunner` (or `get_runner()` for SSH transparency) for all cluster interactions
3. Add a Pydantic input schema in `mcp/mcp_server/schemas.py`
4. Register the tool in `mcp/mcp_server/tools.py`
5. Teach the chat router about it in `ui/backend/routers/chat.py` (the `ROUTER_SYSTEM` prompt)
6. Add tests in `mcp/tests/`
7. Update the README tool count if applicable

```python
# Example: a new tool to check ingress health
async def check_ingress_health(namespace: str = "default") -> dict:
    """Check the health and configuration of ingress resources."""
    runner = get_runner()
    result = await runner.run_json(["get", "ingress", "-n", namespace, "-o", "json"])
    # ... parse and return structured results
    return {"ingresses": parsed, "issues": issues_found}
```

**Safety rules for write operations:**
- Write tools (delete/scale/restart/patch) must require an explicit `confirm: bool = False` argument
- Write tools must also be gated by `settings.enable_recovery_operations`
- Every command must be audit-logged (the runner handles this automatically)

---

## Adding a New LLM Provider

LLM providers live in `mcp/services/llm/`. Each provider implements a common `LLMProvider` interface defined in `base.py`. To add a new provider (e.g. Anthropic Claude):

1. Create `services/llm/anthropic.py` implementing `LLMProvider`
2. Register it in `services/llm/__init__.py` → `get_provider()`
3. Add provider-specific settings to `config/settings.py` (e.g. `anthropic_api_key`)
4. Add the optional SDK dependency to `requirements.txt` (use try-import in the adapter so users who don't need it don't have to install it)
5. Update the `LLM_PROVIDER` docs in the README

---

## Code Standards

- **Python**: Follow PEP 8. Use type hints. Run `ruff check` before submitting.
- **TypeScript/React**: Follow the existing ESLint config (`npm run lint`). Use functional components with hooks.
- **Commits**: Use clear, descriptive commit messages. One logical change per commit.
- **Tests**: New tools and logic changes should include tests. We use `pytest` for Python.

---

## Pull Request Checklist

Before submitting your PR, make sure:

- [ ] Code follows the project's style guidelines
- [ ] Tests pass locally (`pytest` for Python, `npm test` for frontend)
- [ ] New tools are registered in both `mcp_server/tools.py` and the chat router
- [ ] No hardcoded credentials, internal URLs, or sensitive config
- [ ] PR description explains what changed and why
- [ ] Read-only safety is preserved (write operations require explicit `confirm=True`)
- [ ] `.env.example` is updated if you added new config variables

---

## Good First Issues

New to the project? Look for issues labeled `good-first-issue`. These are scoped, well-defined tasks that are a great way to get familiar with the codebase. Examples:

- Adding a new kubectl wrapper tool
- Improving error messages in `ai_tools/analyze.py`
- Expanding test coverage in `mcp/tests/`
- Adding broken workload examples to `demo/broken-workloads/`
- Documentation improvements

---

## Community

- **Issues**: For bugs, features, and discussions
- **Pull Requests**: For code contributions
- **Discussions**: For questions, ideas, and general conversation

---

## License

By contributing, you agree that your contributions will be licensed under the [Apache 2.0 License](LICENSE).
