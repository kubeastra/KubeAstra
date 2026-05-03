"""Chat endpoint with Gemini-powered intent router.

POST /api/chat
  Input:  { message: str, history?: list, ssh?: SSHCredentials }
  Output: { reply: str, tool_used: str, result: dict | None,
            timestamp: float, suggested_actions: list }

The router asks Gemini to classify the user's intent and extract
parameters, then calls the appropriate tool function automatically.
No tool selection required from the user.

When the request includes ssh credentials, all kubectl calls for the
duration of that request are transparently routed via SSH to the remote
cluster master node — no other code changes required.
"""

import json
import logging
import os
import re
import time
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

import db

logger = logging.getLogger(__name__)
router = APIRouter()


_cached_llm_provider = None


def _llm_provider():
    """Lazily resolve and cache the configured LLM provider.

    Imported from `services.llm` in mcp (added to sys.path in main.py).
    Returns None on any import / config failure so callers can fall back cleanly.
    """
    global _cached_llm_provider
    if _cached_llm_provider is not None:
        return _cached_llm_provider
    try:
        from services.llm import get_provider
        _cached_llm_provider = get_provider()
        return _cached_llm_provider
    except Exception as e:
        logger.warning(f"LLM provider unavailable: {e}")
        return None


def _short_session_id(session_id: Optional[str]) -> str:
    if not session_id:
        return "-"
    return session_id[:8]

# ── Request / response models ─────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str        # "user" | "assistant"
    content: str


class SSHCredentials(BaseModel):
    host: str
    username: str
    password: str
    port: int = 22


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []
    ssh: Optional[SSHCredentials] = None
    session_id: Optional[str] = None   # from browser localStorage


class ChatResponse(BaseModel):
    reply: str
    tool_used: str
    result: Optional[dict] = None
    error: Optional[str] = None
    timestamp: float = 0.0
    suggested_actions: list = []


class ExecuteRequest(BaseModel):
    command: str
    ssh: Optional[SSHCredentials] = None


class ExecuteResponse(BaseModel):
    success: bool
    output: str = ""
    error: str = ""


# ── Intent routing prompt ─────────────────────────────────────────────────────

ROUTER_SYSTEM = """You are a Kubernetes/Ansible DevOps assistant intent router.

Given a user message, identify EXACTLY which tool to call and what parameters to pass.

Available tools and when to use them:

1. analyze_error      — user pastes an error message or log snippet, wants diagnosis + fix
2. investigate_pod    — user asks to investigate, debug, or triage a specific pod by name
3. get_pods           — user wants to list/see pods in a namespace; also use when user asks "are there any X pods?" or "show me pods with status Y"
4. get_pod_logs       — user wants logs from a specific pod
5. get_events         — user wants events from a namespace; also use when user asks "are there any X errors/warnings?" or "any OOM/crash/pending issues?" — these are live cluster checks, NOT runbook requests
6. get_deployment     — user asks about a specific deployment AND explicitly states the namespace
7. get_service        — user asks about a specific service AND explicitly states the namespace
8. get_endpoints      — user wants to check endpoints AND explicitly states the namespace
9. get_fix_commands   — user wants specific kubectl commands to fix an error category
10. generate_runbook  — user EXPLICITLY asks for a runbook, documentation, or step-by-step guide (keywords: "generate runbook", "write a runbook", "create documentation")
11. cluster_report    — user pastes kubectl events output and wants a health report
12. error_summary     — user provides multiple errors and wants a summary
13. list_contexts     — user wants to know what clusters/contexts are configured
14. switch_context    — user wants to switch to a different cluster
15. find_workload     — user wants to find a service/pod/deployment across namespaces
16. get_rollout_status — user asks about deployment rollout or if a deployment is ready
17. get_namespaces           — user asks what namespaces exist in the cluster, or wants to list/see all namespaces
18. list_namespace_resources — user asks for "all resources", "everything", "what's running" in a namespace
19. list_services            — user asks to list/show services in a namespace (no specific service name given)
20. get_resource_graph       — user wants to visualize / draw / map / see the topology of a namespace
                               (Ingress → Service → Deployment → Pod relationships)
21. investigate_workload     — user asks to investigate, debug, or triage a specific deployment, statefulset, or daemonset
22. analyze_namespace        — user asks for a holistic health check, analysis, or systemic issue check of a namespace
23. get_nodes                — user asks about nodes in the cluster (e.g. "how many nodes", "list nodes")

CRITICAL ROUTING RULES:

RULE 0 — "all resources" / "everything in namespace X" always uses list_namespace_resources:
  "get all resources in namespace X"    → list_namespace_resources
  "what's running in namespace X"       → list_namespace_resources
  "show everything in X namespace"      → list_namespace_resources
  "list services in namespace X"        → list_services  (no specific name given)
  "services?" or "show services"        → list_services  (use namespace from context)
  "get service <name> in namespace X"   → get_service    (specific name given)
  "visualize the X namespace"           → get_resource_graph (namespace="X")
  "show me the resource graph for X"    → get_resource_graph (namespace="X")
  "map the X namespace"                 → get_resource_graph (namespace="X")
  "draw the topology of X"              → get_resource_graph (namespace="X")

RULE 1 — "Are there any X?" questions check the LIVE cluster, they do NOT generate runbooks:
  When NO namespace is mentioned, ALWAYS use namespace="*" (all namespaces):
  "are there any OOM errors?"           → get_events (namespace="*", field_selector="type=Warning")
  "any CrashLoopBackOff pods?"          → get_pods (namespace="*", status_filter="CrashLoopBackOff")
  "are there any warnings?"             → get_events (namespace="*", field_selector="type=Warning")
  "are there any recent events?"        → get_events (namespace="*")
  "any issues in namespace X?"          → get_events (namespace="X")
  "do we have any failing pods?"        → get_pods (namespace="*")
  When user specifies a namespace, use that namespace instead of "*".

RULE 2 — Only use generate_runbook when the user EXPLICITLY requests one:
  "generate a runbook for OOMKilled"    → generate_runbook
  "write me a runbook"                  → generate_runbook
  "create documentation for X"         → generate_runbook
  (anything else mentioning OOM, crash, etc. without "runbook" = get_events or get_pods)

RULE 3 — If the user mentions a named workload (app, service, deployment) but does NOT
  specify a namespace, ALWAYS use find_workload instead of get_deployment/get_service.
  This avoids "not found in default" errors because the workload may be in any namespace.

RULE 4 — namespace="*" means all namespaces (equivalent to kubectl -A).
  Use it whenever the user does not specify a namespace for event or pod queries.

RULE 5 — For get_pod_logs and investigate_pod: if the user does NOT explicitly state a namespace,
  OMIT the namespace field from params entirely. Do NOT default to "default".
  The backend auto-discovers the correct namespace by searching all namespaces.
  ✗ Wrong: "get logs for sym-shw-app pod"  → { "namespace": "default", "pod_name": "sym-shw-app" }
  ✓ Right: "get logs for sym-shw-app pod"  → { "pod_name": "sym-shw-app" }
  If the user says "one of the X pods" or gives only a name prefix, still emit just the pod name —
  the dispatcher will resolve the first matching pod automatically.

RULE 6 — Port / service detail questions ALWAYS use get_service (not find_workload):
  "what port does grafana use?"              → get_service (service_name="grafana-operator-grafana-service")
  "what's the port for grafana-operator?"   → get_service (service_name="grafana-operator")
  "ports of grafana-operator"               → get_service (service_name="grafana-operator")
  "i need the ports of X"                   → get_service (service_name="X")
  "how do i connect to X?"                  → get_service (service_name="X")
  If the namespace is NOT explicitly stated, OMIT the namespace field — the backend will
  auto-discover it. Do NOT default to "default" for get_service when namespace is unknown.
  ✗ Wrong: { "namespace": "default", "service_name": "grafana-operator" }
  ✓ Right: { "service_name": "grafana-operator" }

Respond ONLY with valid JSON in this exact format:
{
  "tool": "<tool_name>",
  "params": { <tool parameters as key-value pairs> },
  "explanation": "<one sentence: what you understood and what you will do>"
}

Parameter extraction rules:
- For analyze_error: params = { "error_text": "<the full pasted error>" }
- For investigate_pod: params = { "namespace": "<ns if explicitly stated>", "pod_name": "<name>", "use_ai": true }
  - ONLY include namespace if the user explicitly states it. If not stated, omit it entirely.
  - If pod name not given but service/app name is, use it as pod_name
- For get_pods: params = { "namespace": "<ns>", "status_filter": "<optional status to filter by, e.g. CrashLoopBackOff, Error. If user says 'crashloop', use 'CrashLoopBackOff'>" }
- For get_pod_logs: params = { "namespace": "<ns if explicitly stated>", "pod_name": "<name>", "previous": false }
  - ONLY include namespace if the user explicitly states it. If not stated, omit it entirely.
  - Set previous=true if user says "previous", "crashed", "last crash"
- For get_events: params = { "namespace": "<ns or * for all namespaces>" }
  Use namespace="*" when user does not mention a specific namespace.
- For get_deployment: params = { "namespace": "<ns>", "deployment_name": "<name>" }
- For get_service: params = { "namespace": "<ns>", "service_name": "<name>" }
- For get_endpoints: params = { "namespace": "<ns>", "service_name": "<name>" }
- For get_fix_commands: params = { "error_text": "<error or description>" }
- For generate_runbook: params = { "error_text": "<error or category>" }
- For cluster_report: params = { "events_text": "<pasted kubectl events>" }
- For error_summary: params = { "errors": ["<error1>", "<error2>"] }
- For list_contexts: params = {}
- For switch_context: params = { "context_name": "<name>" }
- For find_workload: params = { "name": "<service or app name>" }
  USE THIS when: user says "check status of X", "is X running", "find X", "where is X",
  "status of X" without mentioning a namespace. Examples: "check argocd", "is nginx running",
  "find my-api", "status of prometheus"
- For get_rollout_status: params = { "namespace": "<ns>", "deployment_name": "<name>" }
- For get_namespaces: params = {}
- For list_namespace_resources: params = { "namespace": "<ns>" }
- For list_services: params = { "namespace": "<ns>" }
- For get_resource_graph: params = { "namespace": "<ns>" }
- For investigate_workload: params = { "namespace": "<ns if stated>", "workload_name": "<name>", "workload_type": "deployment", "use_ai": true }
- For analyze_namespace: params = { "namespace": "<ns>" }
- For get_nodes: params = {}

If the message is a general question or greeting that doesn't map to a tool,
respond with: { "tool": "none", "params": {}, "explanation": "<friendly response to the user>" }"""


# ── Tool dispatcher ───────────────────────────────────────────────────────────

def _dispatch(tool: str, params: dict) -> dict:
    """Call the appropriate tool function and return its result as a dict.

    KubectlErrors (e.g. resource not found) are caught here and converted into
    a structured dict so the chat endpoint can give the user a helpful message
    rather than a raw exception.
    """
    import json as _json
    try:
        return _dispatch_inner(tool, params)
    except Exception as e:
        err_msg = str(e)
        # Detect "not found" errors and suggest alternatives
        not_found = ("not found" in err_msg.lower() or
                     "notfound" in err_msg.lower() or
                     "no resources found" in err_msg.lower())
        if not_found:
            name = (params.get("deployment_name") or params.get("service_name") or
                    params.get("pod_name") or params.get("name") or "")
            ns = params.get("namespace", "default")
            # Auto-retry with find_workload across namespaces if we have a name
            if name:
                try:
                    from k8s.wrappers import find_workload
                    fw_result = find_workload(name)
                    fw_result["_not_found_hint"] = (
                        f"'{name}' was not found in namespace '{ns}'. "
                        f"Searched across all namespaces instead:"
                    )
                    return fw_result
                except Exception:
                    pass
            return {
                "error": err_msg,
                "suggestion": (
                    f"The resource was not found in namespace '{ns}'. "
                    "Try specifying the namespace explicitly, e.g. "
                    "'check argocd in the argocd namespace'."
                ),
            }
        # Generic kubectl / other error → return as structured error
        return {"error": err_msg}


def _resolve_pod_ns(params: dict, pod_name: str) -> str:
    """Return the best namespace for a pod-specific tool call (investigate_pod).

    If the router explicitly provided a non-default namespace, use it directly.
    Otherwise run find_workload to auto-discover which namespace the pod lives in.
    Falls back to "default" if discovery fails or returns no results.
    """
    explicit_ns = params.get("namespace")
    if explicit_ns and explicit_ns not in ("default",):
        return explicit_ns
    if not pod_name:
        return explicit_ns or "default"
    try:
        from k8s.wrappers import find_workload
        fw = find_workload(pod_name)
        # find_workload returns {"pods": [...], "deployments": [...], "services": [...]}
        for pod in fw.get("pods", []):
            if pod.get("namespace"):
                return pod["namespace"]
        for dep in fw.get("deployments", []):
            if dep.get("namespace"):
                return dep["namespace"]
    except Exception:
        pass
    return explicit_ns or "default"


def _candidate_workload_names(raw_name: str) -> list[str]:
    """Generate likely Kubernetes resource names from a natural-language phrase."""
    if not raw_name:
        return []

    cleaned = re.sub(r"[^a-z0-9\s._-]", " ", raw_name.lower()).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned:
        return []

    tokens = [t for t in cleaned.split(" ") if t]
    generic_suffixes = {"pod", "deployment", "service", "app", "application", "workload"}

    candidates = []

    def _push(name: str) -> None:
        name = re.sub(r"[-_.]{2,}", "-", name.strip("-._"))
        if name and name not in candidates:
            candidates.append(name)

    _push(cleaned.replace(" ", "-"))
    _push(cleaned.replace(" ", ""))

    if len(tokens) > 1 and tokens[-1] in generic_suffixes:
        trimmed = tokens[:-1]
        if trimmed:
            _push("-".join(trimmed))
            _push("".join(trimmed))

    return candidates


def _resolve_pod_ns_and_name(params: dict, pod_name: str) -> tuple[str, str]:
    """Return (namespace, exact_pod_name) for pod-specific tool calls.

    Always runs find_workload to resolve partial/prefix pod names to the first
    real running pod name (pods have suffixes like -10, -7d4f9b-xkj2p that
    users never type). When namespace is explicitly given, results are filtered
    to that namespace. Falls back to the original values if discovery fails.
    """
    explicit_ns = params.get("namespace")
    if not pod_name:
        return explicit_ns or "default", pod_name

    for candidate in _candidate_workload_names(pod_name) or [pod_name]:
        try:
            from k8s.wrappers import find_workload
            fw = find_workload(candidate)
            # find_workload returns {"pods": [...], "deployments": [...], "services": [...]}
            pods = fw.get("pods", [])
            deps = fw.get("deployments", [])

            # When namespace was explicitly given, prefer matches from that namespace
            if explicit_ns:
                ns_pods = [p for p in pods if p.get("namespace") == explicit_ns]
                ns_deps = [d for d in deps if d.get("namespace") == explicit_ns]
                # Fall back to any match if none in the specified namespace
                pods = ns_pods or pods
                deps = ns_deps or deps

            # Prefer an exact pod match (gives us the full name with ordinal / hash suffix)
            if pods:
                first = pods[0]
                return first.get("namespace") or explicit_ns or "default", first.get("name", candidate)

            # Fall back to deployment namespace (pod name stays normalized for later matching)
            if deps:
                return deps[0].get("namespace") or explicit_ns or "default", candidate
        except Exception:
            pass

    return explicit_ns or "default", pod_name


def _dispatch_inner(tool: str, params: dict) -> dict:
    """Inner dispatcher — raises on errors; called by _dispatch which handles them."""
    import json as _json

    # Helper: namespace falls back to "default" if Gemini omits it.
    # "*" is a valid value meaning all-namespaces (passed as-is to get_events/get_pods).
    ns = params.get("namespace") or "default"

    if tool == "analyze_error":
        from ai_tools.analyze import run
        raw = run(params.get("error_text", ""), params.get("tool", "kubernetes"))
        return _json.loads(raw)

    elif tool == "investigate_pod":
        from k8s.wrappers import investigate_pod
        pod_name = params.get("pod_name", "")
        effective_ns, pod_name = _resolve_pod_ns_and_name(params, pod_name)
        return investigate_pod(
            effective_ns,
            pod_name,
            tail=params.get("tail", 200),
            use_ai=params.get("use_ai", True),
        )

    elif tool == "investigate_workload":
        from k8s.wrappers import investigate_workload
        return investigate_workload(
            ns,
            params.get("workload_name", ""),
            params.get("workload_type", "deployment"),
            use_ai=params.get("use_ai", True)
        )

    elif tool == "analyze_namespace":
        from k8s.wrappers import analyze_namespace
        return analyze_namespace(ns)

    elif tool == "get_pods":
        from k8s.wrappers import get_pods
        return get_pods(ns, params.get("label_selector"), params.get("status_filter"))

    elif tool == "get_pod_logs":
        from k8s.wrappers import get_pod_logs
        pod_name = params.get("pod_name", "")
        effective_ns, pod_name = _resolve_pod_ns_and_name(params, pod_name)
        return get_pod_logs(
            effective_ns,
            pod_name,
            previous=params.get("previous", False),
            tail=params.get("tail", 200),
        )

    elif tool == "get_events":
        from k8s.wrappers import get_events
        return get_events(ns, params.get("field_selector"))

    elif tool == "get_deployment":
        from k8s.wrappers import get_deployment
        return get_deployment(ns, params.get("deployment_name", ""))

    elif tool == "get_service":
        from k8s.wrappers import get_service
        svc_name = params.get("service_name", "")
        # If namespace not explicitly stated, auto-discover via find_workload
        if not params.get("namespace") and svc_name:
            try:
                from k8s.wrappers import find_workload
                fw = find_workload(svc_name)
                svcs = fw.get("services", [])
                if svcs:
                    ns = svcs[0].get("namespace") or ns
                    # Use the exact service name returned (handles prefix matches)
                    svc_name = svcs[0].get("name") or svc_name
            except Exception:
                pass
        return get_service(ns, svc_name)

    elif tool == "get_endpoints":
        from k8s.wrappers import get_endpoints
        return get_endpoints(ns, params.get("service_name", ""))

    elif tool == "get_fix_commands":
        from ai_tools.fix import get_fix_commands
        raw = get_fix_commands(error_text=params.get("error_text"), category=params.get("category"))
        return _json.loads(raw)

    elif tool == "generate_runbook":
        from ai_tools.runbook import generate_runbook
        raw = generate_runbook(error_text=params.get("error_text"), category=params.get("category"))
        return _json.loads(raw)

    elif tool == "cluster_report":
        from ai_tools.report import cluster_report
        raw = cluster_report(params["events_text"])
        return _json.loads(raw)

    elif tool == "error_summary":
        from ai_tools.report import error_summary
        raw = error_summary(params.get("errors", []))
        return _json.loads(raw)

    elif tool == "list_contexts":
        from k8s.wrappers import list_kubeconfig_contexts
        return list_kubeconfig_contexts()

    elif tool == "switch_context":
        from k8s.wrappers import switch_kubeconfig_context
        return switch_kubeconfig_context(params["context_name"])

    elif tool == "find_workload":
        from k8s.wrappers import find_workload
        return find_workload(params["name"], params.get("environment"))

    elif tool == "get_rollout_status":
        from k8s.wrappers import get_rollout_status
        return get_rollout_status(ns, params.get("deployment_name", ""))

    elif tool == "get_namespaces":
        from k8s.wrappers import get_namespaces
        return get_namespaces()

    elif tool == "get_nodes":
        from k8s.wrappers import get_nodes
        return get_nodes()

    elif tool == "list_namespace_resources":
        from k8s.wrappers import list_namespace_resources
        return list_namespace_resources(ns)

    elif tool == "list_services":
        from k8s.wrappers import list_services
        return list_services(ns)

    elif tool == "get_resource_graph":
        from k8s.wrappers import get_resource_graph
        return get_resource_graph(ns)

    else:
        return {}


def _gemini_route(message: str, history: list[ChatMessage]) -> dict:
    """Use the configured LLM (Gemini or Ollama) to classify intent and extract params.

    Name kept for backwards compatibility; actual provider is whatever
    LLM_PROVIDER resolves to. Falls back to keyword routing on any failure.
    """
    provider = _llm_provider()
    if provider is None or not provider.enabled:
        return _keyword_route(message, history)

    # Build conversation context (last 4 messages for context)
    context = ""
    if history:
        recent = history[-4:]
        context = "\n".join(f"{m.role}: {m.content[:200]}" for m in recent)
        context = f"\n\nRecent conversation:\n{context}\n"

    prompt = f"{context}\nUser message:\n{message}"

    try:
        text = provider.generate(prompt, system=ROUTER_SYSTEM, temperature=0.1)
    except Exception as e:
        err_str = str(e)
        logger.warning(f"{provider.name} routing failed, falling back to keyword routing: {err_str}")
        res = _keyword_route(message, history)
        if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "503" in err_str or "UNAVAILABLE" in err_str:
            res["_router_error"] = f"AI Service Unavailable (Quota/Rate Limit): {err_str}"
        return res

    text = (text or "").strip()
    # Strip markdown code fences if present
    if "```" in text:
        for part in text.split("```"):
            part = part.strip().lstrip("json").strip()
            if part.startswith("{"):
                text = part
                break

    try:
        routed = json.loads(text)
        return _normalize_route(message, routed)
    except json.JSONDecodeError as e:
        logger.warning(f"{provider.name} returned non-JSON routing output: {e}")
        return _keyword_route(message, history)


def _normalize_route(message: str, routing: dict) -> dict:
    """Correct known bad routing decisions for targeted failure questions.

    Questions like "why is payment-service crashing?" should trigger a focused
    investigation, not a namespace-wide events dump.
    """
    tool = routing.get("tool")
    msg = message.lower().strip()

    targeted_failure = re.search(
        r"^(?:why is|why are|why isn't|why isnt|what is wrong with|what's wrong with|whats wrong with)\s+"
        r"(?:the\s+)?([a-z0-9][a-z0-9\s\-\.]{0,80}?)\s+"
        r"(crashing|failing|restarting|pending|unhealthy|down|not starting|not running)\b",
        msg,
    )

    if tool == "get_events" and targeted_failure:
        resource_name = _candidate_workload_names(targeted_failure.group(1).strip("?. "))[0]
        ns_match = re.search(
            r"(?:namespace[:\s]+(\S+)|in\s+(?:the\s+)?([a-z0-9][a-z0-9\-]+)\s+namespace)",
            msg,
        )
        params = {"pod_name": resource_name, "use_ai": True}
        if ns_match:
            params["namespace"] = ns_match.group(1) or ns_match.group(2)
        return {
            "tool": "investigate_pod",
            "params": params,
            "explanation": f"Investigating why '{resource_name}' is failing",
        }

    return routing


def _keyword_route(message: str, history: list = None) -> dict:
    """Simple keyword-based fallback router when Gemini is unavailable."""
    msg = message.lower().strip()
    history = history or []

    # ── Short follow-up questions (< 40 chars, no obvious entity) ─────────────
    # Repeat the last tool with the same params rather than misrouting
    SHORT_FOLLOWUPS = [
        "any warnings", "any errors", "any issues", "what about warnings",
        "show warnings", "show errors", "show issues", "any critical",
        "what happened", "why", "more details", "tell me more",
    ]
    if len(msg) < 50 and history:
        for phrase in SHORT_FOLLOWUPS:
            if phrase in msg:
                # Try to pick up namespace from last assistant turn; default to "*" (all)
                ns = "*"
                for m in reversed(history):
                    if m.role == "assistant":
                        ns_hit = re.search(r'"namespace"\s*:\s*"([^"]+)"', m.content)
                        if ns_hit and ns_hit.group(1) not in ("*", "all"):
                            ns = ns_hit.group(1)
                        break
                field = None
                if any(w in msg for w in ["warning", "warn"]):
                    field = "type=Warning"
                ns_label = "all namespaces" if ns == "*" else f"namespace {ns}"
                return {
                    "tool": "get_events",
                    "params": {"namespace": ns, "field_selector": field},
                    "explanation": f"Getting {'warning ' if field else ''}events across {ns_label}",
                }

    # ── "Are there any X?" → check live cluster (events or pods) ──────────────
    # These are cluster-status questions, NOT error analysis requests.
    # Pattern: short question asking if something exists in the cluster.
    cluster_check = re.search(
        r"^(are there|any|do (we|i|you) have|show me|check for|is there).{0,60}"
        r"(oom|crash|crashloop|evict|pending|imagepull|error|warning|fail|issue|problem)",
        msg,
    )
    if cluster_check and len(message) < 120 and "runbook" not in msg:
        ns_match = re.search(r"namespace[:\s]+(\S+)|in\s+([a-z0-9-]+)(?:\s+namespace)?", msg)
        # Default to "*" (all namespaces) when none specified
        ns = (ns_match.group(1) or ns_match.group(2)) if ns_match else "*"
        ns_label = "all namespaces" if ns == "*" else f"namespace '{ns}'"
        if re.search(r"oom|evict|crash|imagepull|warning|error|fail|issue|problem", msg):
            return {"tool": "get_events",
                    "params": {"namespace": ns, "field_selector": "type=Warning"},
                    "explanation": f"Checking live cluster events across {ns_label} for issues"}
        return {"tool": "get_pods",
                "params": {"namespace": ns},
                "explanation": f"Checking pod status across {ns_label}"}

    # ── Error pasted → analyze ─────────────────────────────────────────────
    error_keywords = ["crashloopbackoff", "oomkilled", "imagepullbackoff", "error:", "exception:",
                      "failed:", "traceback", "panic:", "fatal:", "evicted", "pending",
                      "backoff", "oomkill", "exitcode", "exit code", "connection refused",
                      "timeout", "permission denied", "forbidden"]
    if any(k in msg for k in error_keywords) and len(message) > 60:
        return {"tool": "analyze_error", "params": {"error_text": message},
                "explanation": "Detected a pasted error — analyzing with AI"}

    # ── Namespace Analysis ──────────────────────────────────────────────────
    if re.search(r"analyze|health|holistic", msg) and re.search(r"namespace", msg):
        ns_match = re.search(r"namespace[:\s]+(\S+)|(of|health\s+of)\s+([a-z0-9-]+)", msg)
        ns = (ns_match.group(1) or ns_match.group(3)) if ns_match else "default"
        # Avoid matching "analyze error" which is handled earlier
        if "error" not in msg:
            return {"tool": "analyze_namespace", "params": {"namespace": ns},
                    "explanation": f"Analyzing health of namespace '{ns}'"}

    # ── Workload investigation ──────────────────────────────────────────────
    if re.search(r"investigate|triage|debug|diagnose", msg) and not re.search(r"pod", msg):
        ns_match = re.search(r"(?:namespace[:\s]+(\S+)|in\s+([a-z0-9-]+)\s+namespace)", msg)
        wl_match = re.search(r"(?:deployment|statefulset|daemonset|workload|app|application)[:\s]+(\S+)|investigate\s+(\S+)", msg)
        wl = (wl_match.group(1) or wl_match.group(2)) if wl_match else ""
        if wl and wl not in ["pod", "namespace"]:
            ns = (ns_match.group(1) or ns_match.group(2)) if ns_match else "default"
            return {"tool": "investigate_workload", 
                    "params": {"namespace": ns, "workload_name": wl, "workload_type": "deployment", "use_ai": True},
                    "explanation": f"Investigating workload '{wl}' in '{ns}'"}

    # ── Pod investigation ───────────────────────────────────────────────────
    targeted_failure = re.search(
        r"^(?:why is|why are|why isn't|why isnt|what is wrong with|what's wrong with|whats wrong with)\s+"
        r"(?:the\s+)?([a-z0-9][a-z0-9\s\-\.]{0,80}?)\s+"
        r"(crashing|failing|restarting|pending|unhealthy|down|not starting|not running)\b",
        msg,
    )
    if targeted_failure:
        ns_match = re.search(
            r"(?:namespace[:\s]+(\S+)|in\s+(?:the\s+)?([a-z0-9][a-z0-9\-]+)\s+namespace)",
            msg,
        )
        pod = _candidate_workload_names(targeted_failure.group(1).strip("?. "))[0]
        params_inv: dict = {"pod_name": pod, "use_ai": True}
        if ns_match:
            params_inv["namespace"] = ns_match.group(1) or ns_match.group(2)
        return {
            "tool": "investigate_pod",
            "params": params_inv,
            "explanation": f"Investigating why '{pod}' is failing",
        }

    if re.search(r"investigate|triage|debug|diagnose", msg):
        ns_match = re.search(r"(?:namespace[:\s]+(\S+)|in\s+([a-z0-9-]+)\s+namespace)", msg)
        pod_match = re.search(r"pod[:\s]+(\S+)|pod\s+named?\s+(\S+)", msg)
        pod = (pod_match.group(1) or pod_match.group(2)) if pod_match else ""
        # Omit namespace when not stated so _dispatch_inner can auto-discover it
        params_inv: dict = {"pod_name": pod, "use_ai": True}
        if ns_match:
            params_inv["namespace"] = ns_match.group(1) or ns_match.group(2)
        return {"tool": "investigate_pod", "params": params_inv,
                "explanation": f"Investigating pod '{pod}'"}

    # ── Logs ───────────────────────────────────────────────────────────────
    if re.search(r"\blog\b|logs\b", msg):
        # Extract namespace only when the user explicitly names it
        ns_match = re.search(
            r"(?:namespace[:\s]+(\S+)|in\s+(?:the\s+)?([a-z0-9][a-z0-9\-]+)\s+namespace)",
            msg,
        )
        # Extract pod/workload name: handle "for one of the X pods", "for pod X", "for the X pod"
        pod_match = re.search(
            r"(?:pod[:\s]+(\S+)|"
            r"(?:for|of|from)\s+(?:one\s+of\s+the\s+|the\s+)?([a-z0-9][a-z0-9\-\.]+)\s*pods?\b)",
            msg,
        )
        ns = (ns_match.group(1) or ns_match.group(2)) if ns_match else None
        pod = (pod_match.group(1) or pod_match.group(2)) if pod_match else ""
        # Omit namespace when not explicitly stated — _dispatch_inner will auto-discover it
        params_log: dict = {"pod_name": pod, "previous": "previous" in msg or "crash" in msg}
        if ns:
            params_log["namespace"] = ns
        return {"tool": "get_pod_logs", "params": params_log, "explanation": "Fetching pod logs"}

    # ── Pods list ──────────────────────────────────────────────────────────
    if "pod" in msg and re.search(r"list|show|get|all|running|status", msg):
        ns_match = re.search(r"namespace[:\s]+(\S+)|in\s+([a-z0-9-]+)", msg)
        ns = (ns_match.group(1) or ns_match.group(2)) if ns_match else "default"
        return {"tool": "get_pods", "params": {"namespace": ns},
                "explanation": f"Listing pods in namespace {ns}"}

    # ── Events (warnings, errors, recent activity) ─────────────────────────
    if re.search(r"event|warning|warn|recent|what.s happening|happening", msg):
        ns_match = re.search(r"namespace[:\s]+(\S+)|in\s+([a-z0-9-]+)", msg)
        ns = (ns_match.group(1) or ns_match.group(2)) if ns_match else "*"
        field = "type=Warning" if re.search(r"warning|warn|error|issue", msg) else None
        ns_label = "all namespaces" if ns == "*" else f"namespace {ns}"
        return {"tool": "get_events",
                "params": {"namespace": ns, "field_selector": field},
                "explanation": f"Getting {'warning ' if field else ''}events across {ns_label}"}

    # ── All resources in a namespace ───────────────────────────────────────
    if re.search(r"all resources|everything|all (the\s+)?things|what.s running|what is running", msg):
        ns_match = re.search(r"namespace[:\s]+(\S+)|in\s+[\"']?([a-z0-9_\-]+)[\"']?\s*(ns|namespace)?", msg)
        ns = (ns_match.group(1) or ns_match.group(2)) if ns_match else "default"
        return {"tool": "list_namespace_resources", "params": {"namespace": ns},
                "explanation": f"Listing all resources in namespace '{ns}'"}

    # ── Resource graph / topology visualization ─────────────────────────────
    if re.search(r"visualize|visualise|resource graph|topology|draw.*(namespace|cluster)|map the (namespace|cluster)", msg):
        ns_match = re.search(r"namespace[:\s]+(\S+)|(?:in|of|for)\s+[\"']?([a-z0-9_\-]+)[\"']?\s*(ns|namespace)?", msg)
        ns = (ns_match.group(1) or ns_match.group(2)) if ns_match else "default"
        return {"tool": "get_resource_graph", "params": {"namespace": ns},
                "explanation": f"Building resource graph for namespace '{ns}'"}

    # ── List services (no specific name) ────────────────────────────────────
    if re.search(r"^services\??$|list services|show services|get services|what services", msg):
        ns_match = re.search(r"namespace[:\s]+(\S+)|in\s+([a-z0-9_\-]+)", msg)
        # Try to pick up namespace from recent history context
        ns = (ns_match.group(1) or ns_match.group(2)) if ns_match else "default"
        return {"tool": "list_services", "params": {"namespace": ns},
                "explanation": f"Listing all services in namespace '{ns}'"}

    # ── Namespaces ─────────────────────────────────────────────────────────
    if re.search(r"namespace|namespaces", msg) and re.search(r"list|show|get|what|which|all|have|do i", msg):
        return {"tool": "get_namespaces", "params": {},
                "explanation": "Listing all namespaces in the cluster"}

    # ── Contexts / clusters ────────────────────────────────────────────────
    if any(k in msg for k in ["context", "cluster", "kubeconfig", "which cluster", "what cluster"]):
        return {"tool": "list_contexts", "params": {},
                "explanation": "Listing available cluster contexts"}

    # ── Runbook — only when explicitly requested ────────────────────────────
    if "runbook" in msg or re.search(r"(generate|write|create)\s+(a\s+)?(doc|guide|documentation)", msg):
        return {"tool": "generate_runbook", "params": {"error_text": message},
                "explanation": "Generating runbook"}

    # ── Fix commands ───────────────────────────────────────────────────────
    if re.search(r"fix|how (to|do i|can i) (fix|resolve|solve)|command", msg):
        return {"tool": "get_fix_commands", "params": {"error_text": message},
                "explanation": "Getting fix commands"}

    # ── Port / service detail query ────────────────────────────────────────────
    # "what port does grafana use?", "ports of grafana-operator", "i need the ports of X"
    port_query = re.search(r"\bport\b", msg)
    if port_query:
        # Try to extract a service/app name from the message
        svc_match = re.search(
            r"(?:port(?:s)?\s+(?:of|for)\s+|connect\s+to\s+|of\s+service\s+)"
            r"([a-z0-9][a-z0-9\-\.]{1,60})",
            msg,
        ) or re.search(
            r"([a-z0-9][a-z0-9\-\.]{2,60})\s+(?:port|ports|service)",
            msg,
        )
        svc_name = svc_match.group(1).strip("?. ") if svc_match else ""
        stopwords = {"the", "a", "an", "my", "our", "all", "any", "this", "that", "what", "which"}
        if svc_name and svc_name not in stopwords:
            ns_match = re.search(r"namespace[:\s]+(\S+)|in\s+([a-z0-9-]+)\s+namespace", msg)
            params_svc: dict = {"service_name": svc_name}
            if ns_match:
                params_svc["namespace"] = ns_match.group(1) or ns_match.group(2)
            return {"tool": "get_service", "params": params_svc,
                    "explanation": f"Getting port details for service '{svc_name}'"}

    # ── Named workload lookup without namespace → search all ──────────────────
    # "check status of argocd", "is nginx running", "where is prometheus"
    workload_match = re.search(
        r"(?:status of|check|find|where is|is .+? running)\s+([a-z0-9][a-z0-9\-\.]{1,40})",
        msg,
    )
    if workload_match and not re.search(r"namespace[:\s]|in\s+\w+\s+namespace", msg):
        name = workload_match.group(1).strip("?. ")
        stopwords = {"the", "a", "an", "my", "our", "all", "any", "pods", "events", "logs"}
        if name not in stopwords:
            return {"tool": "find_workload", "params": {"name": name},
                    "explanation": f"Searching for '{name}' across all namespaces"}

    # ── Deployment status (namespace explicitly given) ─────────────────────────
    if re.search(r"deployment|deploy|rollout|replica", msg):
        ns_match = re.search(r"namespace[:\s]+(\S+)|in\s+the\s+([a-z0-9-]+)\s+namespace", msg)
        dep_match = re.search(r"deployment[:\s]+(\S+)|deploy[:\s]+(\S+)", msg)
        ns = (ns_match.group(1) or ns_match.group(2)) if ns_match else None
        dep = (dep_match.group(1) or dep_match.group(2)) if dep_match else ""
        if dep and ns:
            return {"tool": "get_deployment",
                    "params": {"namespace": ns, "deployment_name": dep},
                    "explanation": f"Checking deployment {dep} in {ns}"}
        elif dep:
            return {"tool": "find_workload", "params": {"name": dep},
                    "explanation": f"Searching for '{dep}' across all namespaces"}

    # ── Default: if message looks like a short question, ask for more detail ───
    if re.search(r"^(what|how|why|when|is|are|can|does|do|any|show|list|tell)", msg) and len(msg) < 60:
        return {"tool": "none", "params": {},
                "explanation": (
                    "I need a bit more detail to help you. Try asking something like:\n"
                    "- \"List all pods in the production namespace\"\n"
                    "- \"Are there any warnings in the default namespace?\"\n"
                    "- \"Investigate pod my-app-xyz in namespace staging\"\n"
                    "- Or paste an error message directly."
                )}

    # ── Default → analyze ──────────────────────────────────────────────────
    return {"tool": "analyze_error", "params": {"error_text": message},
            "explanation": "Analyzing your message as an error/question"}


def _friendly_summary(tool: str, result: dict, explanation: str) -> str:
    """Fallback static summary used when synthesis is unavailable."""
    if tool in {"investigate_pod", "investigate_workload", "analyze_namespace"} and isinstance(result, dict):
        ai = result.get("ai", {})
        ai_analysis = ai.get("ai_analysis", {}) if isinstance(ai, dict) else {}
        if isinstance(ai_analysis, dict) and ai_analysis.get("root_cause"):
            root = str(ai_analysis.get("root_cause", "")).strip()
            solution = str(ai_analysis.get("solution", "")).strip()
            if solution:
                return f"{root}\n\nSuggested fix: {solution}"
            return root

        if tool == "investigate_pod":
            pod_name = result.get("pod_name") or "This pod"
            classification = result.get("classification", {})
            mode = classification.get("mode") if isinstance(classification, dict) else None
            if mode == "CrashLoopBackOff":
                return f"`{pod_name}` is in **CrashLoopBackOff**. I collected describe output, logs, and events to help pinpoint the root cause."
            if mode == "ImagePullBackOff":
                return f"`{pod_name}` is failing because the image cannot be pulled. I collected describe output and events for the exact pull failure."
            if mode == "Pending":
                return f"`{pod_name}` is stuck in **Pending**. I collected describe output and scheduling events to show why it is not starting."

    summaries = {
        "analyze_error": "Here's the AI diagnosis for your error:",
        "investigate_pod": "I investigated the pod and collected the most relevant diagnostics.",
        "get_pods": "Here are the pods I found:",
        "get_pod_logs": "Here are the pod logs:",
        "get_events": "Here are the recent events:",
        "get_deployment": "Here's the deployment status:",
        "get_service": "Here's the service details:",
        "get_endpoints": "Here are the endpoints:",
        "get_fix_commands": "Here are the fix commands:",
        "generate_runbook": "Here's the generated runbook:",
        "cluster_report": "Here's the cluster health report:",
        "error_summary": "Here's the error summary:",
        "list_contexts": "Here are your configured clusters:",
        "switch_context": "Context switched:",
        "find_workload": "Here's what I found across all namespaces:",
        "get_rollout_status": "Here's the rollout status:",
        "get_namespaces": "Here are the namespaces in this cluster:",
        "list_namespace_resources": "Here are all resources in the namespace:",
        "list_services": "Here are the services in the namespace:",
        "get_resource_graph": "Here is the resource graph for the namespace:",
        "investigate_workload": "I investigated the workload and summarized the main issue.",
        "analyze_namespace": "I analyzed the namespace health and summarized the main issues.",
    }
    return summaries.get(tool, explanation)


# Tools whose output Gemini should synthesise into a direct answer.
# AI tools (analyze_error, generate_runbook, etc.) already produce natural
# language — a second Gemini pass on those would be wasteful.
_SYNTHESIZE_TOOLS = {
    "get_pods", "get_events", "get_deployment", "get_service",
    "get_endpoints", "get_rollout_status", "find_workload",
    "list_namespace_resources", "list_services", "get_namespaces",
    "get_pod_logs", "list_contexts", "investigate_pod",
    "investigate_workload", "analyze_namespace",
}


def _synthesize_answer(question: str, tool: str, result: dict) -> tuple[Optional[str], Optional[str]]:
    """Use the configured LLM to write a concise direct answer to the user's question.

    Takes the original question and the tool result, asks the LLM for a
    1-2 sentence summary that directly answers what was asked rather than
    just saying "here are the pods".

    Returns (answer, error) where both can be None.
    """
    if tool not in _SYNTHESIZE_TOOLS:
        return None, None

    provider = _llm_provider()
    if provider is None or not provider.enabled:
        return None, None

    import json as _json

    # For investigate_pod, pull out the AI analysis + classification to keep
    # the prompt focused on the diagnosis rather than raw kubectl output.
    if tool == "investigate_pod":
        focused = {
            "pod": result.get("pod_name") or result.get("pod"),
            "namespace": result.get("namespace"),
            "classification": result.get("classification"),
            "ai_analysis": (result.get("ai") or {}).get("ai_analysis"),
            "steps_run": result.get("steps_run"),
        }
        result_text = _json.dumps(focused, default=str)[:3000]
    elif tool == "get_pods":
        # For pod listings, always send the health summary first so the LLM
        # sees unhealthy pods even when the full list is 170+ entries.
        health = result.get("health_summary", {})
        focused = {
            "namespace": result.get("namespace"),
            "pod_count": result.get("pod_count"),
            "health_summary": health,
        }
        # If there are few enough pods, include the full list
        full_json = _json.dumps(result, default=str)
        if len(full_json) <= 3000:
            result_text = full_json
        else:
            # Health summary + first/last pods for context
            result_text = _json.dumps(focused, default=str)[:3000]
    else:
        # Compact the result to avoid inflating the prompt — 3000 chars is
        # enough to understand pod counts, statuses, restart counts etc.
        result_text = _json.dumps(result, default=str)[:3000]

    # Scale max_tokens based on tool complexity
    _COMPLEX_TOOLS = {
        "investigate_pod", "investigate_workload", "analyze_namespace",
        "list_namespace_resources", "get_pods", "get_events",
    }
    max_tok = 800 if tool in _COMPLEX_TOOLS else 400

    system = (
        "You are a Kubernetes DevOps assistant. "
        "Answer the user's question directly and concisely in 2-4 sentences using the data provided. "
        "Be specific: mention pod names, image names, counts, or error reasons where relevant. "
        "Apply semantic reasoning — do not rely on exact keyword matches: "
        "  • BackOff events on pods that are pulling images = ImagePullBackOff-related issue. "
        "  • OOMKilled in pod status or events = OOM error. "
        "  • CrashLoopBackOff in pod status = crash loop issue. "
        "Only say 'none found' if the data genuinely shows no related activity whatsoever. "
        "Do not list every event — summarise the pattern (e.g. which pods, which image, how many). "
        "Use markdown formatting: **bold** for emphasis, `inline code` for pod/resource names, "
        "and bullet points for lists of 3+ items. Keep the response concise."
    )

    try:
        answer = provider.generate(
            f"User question: {question}\n\nData returned: {result_text}",
            system=system,
            temperature=0.1,
            max_tokens=max_tok,
        )
    except Exception as e:
        err_str = str(e)
        logger.warning(f"Answer synthesis failed, using static summary: {err_str}")
        if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "503" in err_str or "UNAVAILABLE" in err_str:
            return None, f"AI Service Unavailable (Quota/Rate Limit): {err_str}"
        return None, None

    answer = (answer or "").strip()
    return answer if answer else None, None

# ── Suggested actions extraction ──────────────────────────────────────────────

def _extract_suggested_actions(tool: str, result: dict) -> list:
    """Extract actionable commands from tool results for the frontend.

    Looks for kubectl commands in AI analysis results, fix playbooks, and
    error analysis that the user might want to execute directly.
    Returns a list of action dicts: [{type, label, command, namespace?, confirm?}]
    """
    actions = []
    if not isinstance(result, dict):
        return actions

    # From investigate_pod AI analysis
    ai = result.get("ai", {})
    if isinstance(ai, dict):
        ai_analysis = ai.get("ai_analysis", {})
        if isinstance(ai_analysis, dict):
            for cmd in ai_analysis.get("commands", []):
                c = cmd if isinstance(cmd, str) else (cmd.get("command") or cmd.get("cmd") or "")
                desc = "" if isinstance(cmd, str) else cmd.get("description", "")
                if c and c.strip().startswith("kubectl"):
                    is_write = any(w in c for w in ["delete", "apply", "patch", "scale", "rollout restart"])
                    actions.append({
                        "type": "apply" if is_write else "run",
                        "label": desc or c[:60],
                        "command": c,
                        "confirm": is_write,
                    })

    # From analyze_error / get_fix_commands
    for cmd in result.get("commands", []):
        c = cmd if isinstance(cmd, str) else (cmd.get("command") or cmd.get("cmd") or "")
        desc = "" if isinstance(cmd, str) else cmd.get("description", "")
        if c and c.strip().startswith("kubectl"):
            is_write = any(w in c for w in ["delete", "apply", "patch", "scale", "rollout restart"])
            actions.append({
                "type": "apply" if is_write else "run",
                "label": desc or c[:60],
                "command": c,
                "confirm": is_write,
            })

    # Deduplicate by command
    seen = set()
    deduped = []
    for a in actions:
        if a["command"] not in seen:
            seen.add(a["command"])
            deduped.append(a)
    return deduped[:5]  # Cap at 5 actions


# ── Chat endpoint ─────────────────────────────────────────────────────────────

@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    """Handle a chat turn.

    If the request includes SSH credentials, all kubectl calls in this turn
    are executed on the remote master node via SSH.  The runner is reset to
    the local default after the turn completes (success or error).

    If session_id is provided, both the user message and assistant reply are
    persisted to SQLite so history survives page reloads.
    """
    ssh_runner = None
    ctx_token = None
    sid = req.session_id  # may be None for clients that don't send it
    session_tag = _short_session_id(sid)

    def _persist(role: str, content: str, tool_used: str = None,
                 result: dict = None, error: str = None):
        """Save a message to DB, silently ignoring errors so DB issues never
        break the chat response."""
        if not sid:
            return
        try:
            db.save_message(sid, role, content, tool_used=tool_used,
                            result=result, error=error)
        except Exception as db_err:
            logger.warning(f"DB save failed: {db_err}")

    try:
        # ── Set up SSH runner if credentials were provided ───────────────────
        if req.ssh:
            from k8s.ssh_runner import SSHKubectlRunner, SSHConnectionError
            from k8s.kubectl_runner import set_runner, runner_ctx

            try:
                ssh_runner = SSHKubectlRunner(
                    host=req.ssh.host,
                    username=req.ssh.username,
                    password=req.ssh.password,
                    port=req.ssh.port,
                )
                ssh_runner.connect()
                ctx_token = set_runner(ssh_runner)
                logger.info(f"SSH runner active for {req.ssh.username}@{req.ssh.host}")
            except SSHConnectionError as e:
                logger.warning(
                    "chat_ssh_connect_failed session=%s host=%s port=%s error=%s",
                    session_tag,
                    req.ssh.host,
                    req.ssh.port,
                    str(e),
                )
                return ChatResponse(
                    reply=f"Could not connect to {req.ssh.host} via SSH: {e}",
                    tool_used="error",
                    result=None,
                    error=str(e),
                )

        # 1. Persist the user message
        _persist("user", req.message)

        # 2. Route the message
        routing = _gemini_route(req.message, req.history)
        tool = routing.get("tool", "none")
        params = routing.get("params", {})
        explanation = routing.get("explanation", "")
        router_error = routing.get("_router_error")
        logger.info(
            "chat_routed session=%s tool=%s ssh=%s",
            session_tag,
            tool,
            bool(req.ssh),
        )

        # 3. No tool needed (greeting / general question)
        if tool == "none":
            _persist("assistant", explanation, tool_used="none")
            return ChatResponse(
                reply=explanation,
                tool_used="none",
                result=None,
                timestamp=time.time(),
            )

        # 4. Dispatch to tool
        dispatch_started_at = time.perf_counter()
        result = _dispatch(tool, params)
        dispatch_elapsed_ms = (time.perf_counter() - dispatch_started_at) * 1000
        logger.info(
            "chat_dispatched session=%s tool=%s ssh=%s elapsed_ms=%.1f",
            session_tag,
            tool,
            bool(req.ssh),
            dispatch_elapsed_ms,
        )

        # 5. Check if the result itself is an error (KubectlError caught in _dispatch)
        if isinstance(result, dict) and (
            ("error" in result and len(result) <= 2) or
            (result.get("success") is False and result.get("error"))
        ):
            hint = result.get("suggestion", "")
            err = result.get("error", "Unknown error")
            reply = hint or f"I ran into an issue: {err}"
            _persist("assistant", reply, tool_used=tool, result=result, error=err)
            return ChatResponse(reply=reply, tool_used=tool, result=result, error=err, timestamp=time.time())

        # 6. Build reply — try Gemini synthesis first, fall back to static summary
        not_found_hint = result.pop("_not_found_hint", None) if isinstance(result, dict) else None
        
        synth_ans, synth_err = _synthesize_answer(req.message, tool, result)
        
        reply = (
            not_found_hint
            or synth_ans
            or _friendly_summary(tool, result, explanation)
        )

        # 7. Extract suggested actions from AI analysis results
        actions = _extract_suggested_actions(tool, result)

        final_err = router_error or synth_err
        
        _persist("assistant", reply, tool_used=tool, result=result, error=final_err)
        return ChatResponse(
            reply=reply,
            tool_used=tool,
            result=result,
            error=final_err,
            timestamp=time.time(),
            suggested_actions=actions,
        )

    except Exception as e:
        logger.exception("Chat error")
        err_reply = f"Something went wrong: {e}"
        _persist("assistant", err_reply, tool_used="error", error=str(e))
        return ChatResponse(
            reply=err_reply,
            tool_used="error",
            result=None,
            error=str(e),
        )

    finally:
        # Always close SSH and restore the runner context
        if ssh_runner is not None:
            ssh_runner.close()
        if ctx_token is not None:
            from k8s.kubectl_runner import runner_ctx
            runner_ctx.reset(ctx_token)


# ── Execute endpoint ──────────────────────────────────────────────────────────

# Only these kubectl sub-commands are allowed via the execute endpoint.
_SAFE_KUBECTL_PREFIXES = [
    "kubectl patch ",
    "kubectl apply ",
    "kubectl scale ",
    "kubectl rollout restart ",
    "kubectl delete pod ",
    "kubectl set image ",
    "kubectl set resources ",
    "kubectl label ",
    "kubectl annotate ",
    "kubectl cordon ",
    "kubectl uncordon ",
    "kubectl drain ",
]


@router.post("/execute", response_model=ExecuteResponse)
def execute_command(req: ExecuteRequest):
    """Execute a kubectl command suggested by AI analysis.

    Safety guards:
    - Only kubectl commands are allowed (no shell injection).
    - Only specific kubectl sub-commands from a whitelist are permitted.
    - SSH credentials are supported for remote cluster execution.
    """
    cmd = req.command.strip()
    logger.info("execute_request command=%s ssh=%s", cmd[:80], bool(req.ssh))

    # Safety check 1: Must start with "kubectl"
    if not cmd.startswith("kubectl"):
        return ExecuteResponse(success=False, error="Only kubectl commands are allowed.")

    # Safety check 2: Must match a safe prefix
    if not any(cmd.startswith(prefix) for prefix in _SAFE_KUBECTL_PREFIXES):
        return ExecuteResponse(
            success=False,
            error=f"Command not in allowed list. Allowed: {', '.join(p.strip() for p in _SAFE_KUBECTL_PREFIXES)}",
        )

    # Safety check 3: No shell metacharacters
    dangerous = set(";|&$`()")
    if any(c in cmd for c in dangerous):
        return ExecuteResponse(success=False, error="Command contains disallowed shell characters.")

    # Execute
    ssh_runner = None
    ctx_token = None
    try:
        if req.ssh:
            from k8s.kubectl_runner import SSHKubectlRunner, runner_ctx
            ssh_runner = SSHKubectlRunner(
                host=req.ssh.host,
                username=req.ssh.username,
                password=req.ssh.password or None,
                key_path=req.ssh.key_path or None,
                port=req.ssh.port,
            )
            ctx_token = runner_ctx.set(ssh_runner)

        from k8s.kubectl_runner import run_kubectl
        result = run_kubectl(cmd.replace("kubectl ", "", 1))
        return ExecuteResponse(success=True, output=result)

    except Exception as e:
        logger.exception("Execute error")
        return ExecuteResponse(success=False, error=str(e))

    finally:
        if ssh_runner is not None:
            ssh_runner.close()
        if ctx_token is not None:
            from k8s.kubectl_runner import runner_ctx
            runner_ctx.reset(ctx_token)
