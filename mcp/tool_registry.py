"""Unified tool registry — single source of truth for all Kubeastra tools.

Every tool across all surfaces (MCP stdio, HTTP MCP, REST chat, ReAct loop)
is defined here with its metadata, schema, and handler adapter. Entry points
import from this module instead of maintaining their own tool lists.

Phase 2 of the routing architecture refactoring.
See internal_docs/ROUTING_ARCHITECTURE_PROPOSAL_FIXES.md for context.

Usage:
    from tool_registry import resolve_tool, tools_for_surface, dispatch, DispatchContext
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Literal, Optional

logger = logging.getLogger(__name__)

# ── Types ────────────────────────────────────────────────────────────────────

ToolSurface = Literal["mcp", "chat", "react", "rest"]


# ── Core data structures ────────────────────────────────────────────────────

@dataclass(frozen=True)
class ToolDef:
    """Metadata and execution adapter for a single tool."""
    name: str                                            # Canonical name (e.g. "list_kubeconfig_contexts")
    handler: Callable[[dict, DispatchContext], dict]      # Adapter wrapping the raw implementation
    schema: type                                         # Pydantic BaseModel input class
    description: str                                     # Human-readable, used by all prompts
    category: str                                        # Grouping key: investigation, discovery, pod, etc.
    surfaces: frozenset[ToolSurface]                      # Where this tool is available
    aliases: tuple[str, ...] = ()                        # Short names that resolve to this tool
    write_op: bool = False                               # Is this a write/destructive operation?
    requires_confirm: bool = False                       # Does it need confirm=True to execute?
    react_enabled: bool = True                           # Should the ReAct agent see this tool?
    returns_json_string: bool = False                    # AI tools return str, not dict
    notes: str = ""                                      # Implementation notes (not user-facing)


@dataclass
class DispatchContext:
    """Execution context passed to every handler adapter."""
    surface: ToolSurface
    session_id: Optional[str] = None
    history: Optional[list] = None
    allow_write: bool = False


# ── Name resolution helpers ─────────────────────────────────────────────────
# Copied from chat.py _resolve_pod_ns_and_name / _candidate_workload_names.
# chat.py keeps its copies until Phase 5 wires up the shared dispatcher.

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

    candidates: list[str] = []

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

    Runs find_workload to resolve partial/prefix pod names to the first
    matching running pod. When namespace is explicitly given, results are
    filtered to that namespace.
    """
    explicit_ns = params.get("namespace")
    if not pod_name:
        return explicit_ns or "default", pod_name

    for candidate in _candidate_workload_names(pod_name) or [pod_name]:
        try:
            from k8s.wrappers import find_workload
            fw = find_workload(candidate)
            pods = fw.get("pods", [])
            deps = fw.get("deployments", [])

            if explicit_ns:
                ns_pods = [p for p in pods if p.get("namespace") == explicit_ns]
                ns_deps = [d for d in deps if d.get("namespace") == explicit_ns]
                pods = ns_pods or pods
                deps = ns_deps or deps

            if pods:
                first = pods[0]
                return first.get("namespace") or explicit_ns or "default", first.get("name", candidate)

            if deps:
                return deps[0].get("namespace") or explicit_ns or "default", candidate
        except Exception:
            pass

    return explicit_ns or "default", pod_name


# ── Handler adapters ────────────────────────────────────────────────────────
# Each handler wraps the raw implementation function with the exact behavior
# currently in _dispatch_inner (namespace resolution, auto-discovery, JSON
# parsing for AI tools). Signatures: (params: dict, ctx: DispatchContext) -> dict

# -- Investigation tools --

def _handle_investigate_pod(params: dict, ctx: DispatchContext) -> dict:
    from k8s.wrappers import investigate_pod
    pod_name = params.get("pod_name", "")
    if ctx.surface in ("chat", "react"):
        ns, pod_name = _resolve_pod_ns_and_name(params, pod_name)
    else:
        ns = params.get("namespace") or "default"
    return investigate_pod(
        ns, pod_name,
        tail=params.get("tail", 200),
        use_ai=params.get("use_ai", True),
    )


def _handle_investigate_workload(params: dict, ctx: DispatchContext) -> dict:
    from k8s.wrappers import investigate_workload
    ns = params.get("namespace") or "default"
    return investigate_workload(
        ns,
        params.get("workload_name", ""),
        params.get("workload_type", "deployment"),
        use_ai=params.get("use_ai", True),
    )


def _handle_analyze_namespace(params: dict, ctx: DispatchContext) -> dict:
    from k8s.wrappers import analyze_namespace
    return analyze_namespace(params.get("namespace") or "default")


# -- Discovery tools --

def _handle_find_workload(params: dict, ctx: DispatchContext) -> dict:
    from k8s.wrappers import find_workload
    return find_workload(params["name"], params.get("environment"))


def _handle_get_namespaces(params: dict, ctx: DispatchContext) -> dict:
    from k8s.wrappers import get_namespaces
    return get_namespaces()


def _handle_get_nodes(params: dict, ctx: DispatchContext) -> dict:
    from k8s.wrappers import get_nodes
    return get_nodes()


def _handle_list_namespace_resources(params: dict, ctx: DispatchContext) -> dict:
    from k8s.wrappers import list_namespace_resources
    return list_namespace_resources(params.get("namespace") or "default")


# -- Pod tools --

def _handle_get_pods(params: dict, ctx: DispatchContext) -> dict:
    from k8s.wrappers import get_pods
    ns = params.get("namespace") or "default"
    return get_pods(ns, params.get("label_selector"), params.get("status_filter"))


def _handle_get_pod_logs(params: dict, ctx: DispatchContext) -> dict:
    from k8s.wrappers import get_pod_logs
    pod_name = params.get("pod_name", "")
    if ctx.surface in ("chat", "react"):
        ns, pod_name = _resolve_pod_ns_and_name(params, pod_name)
    else:
        ns = params.get("namespace") or "default"
    return get_pod_logs(
        ns, pod_name,
        previous=params.get("previous", False),
        tail=params.get("tail", 200),
        container=params.get("container"),
    )


def _handle_describe_pod(params: dict, ctx: DispatchContext) -> dict:
    from k8s.wrappers import describe_pod
    return describe_pod(params.get("namespace") or "default", params.get("pod_name", ""))


# -- Cluster state tools --

def _handle_get_events(params: dict, ctx: DispatchContext) -> dict:
    from k8s.wrappers import get_events
    return get_events(params.get("namespace") or "default", params.get("field_selector"))


def _handle_get_deployment(params: dict, ctx: DispatchContext) -> dict:
    from k8s.wrappers import get_deployment
    return get_deployment(params.get("namespace") or "default", params.get("deployment_name", ""))


def _handle_get_service(params: dict, ctx: DispatchContext) -> dict:
    from k8s.wrappers import get_service
    ns = params.get("namespace") or "default"
    svc_name = params.get("service_name", "")
    # Auto-discover namespace via find_workload for chat/react when not stated
    if ctx.surface in ("chat", "react") and not params.get("namespace") and svc_name:
        try:
            from k8s.wrappers import find_workload
            fw = find_workload(svc_name)
            svcs = fw.get("services", [])
            if svcs:
                ns = svcs[0].get("namespace") or ns
                svc_name = svcs[0].get("name") or svc_name
        except Exception:
            pass
    return get_service(ns, svc_name)


def _handle_get_endpoints(params: dict, ctx: DispatchContext) -> dict:
    from k8s.wrappers import get_endpoints
    return get_endpoints(params.get("namespace") or "default", params.get("service_name", ""))


def _handle_get_rollout_status(params: dict, ctx: DispatchContext) -> dict:
    from k8s.wrappers import get_rollout_status
    return get_rollout_status(params.get("namespace") or "default", params.get("deployment_name", ""))


def _handle_list_services(params: dict, ctx: DispatchContext) -> dict:
    from k8s.wrappers import list_services
    return list_services(params.get("namespace") or "default")


def _handle_get_resource_graph(params: dict, ctx: DispatchContext) -> dict:
    from k8s.wrappers import get_resource_graph
    return get_resource_graph(params.get("namespace") or "default")


def _handle_list_kubeconfig_contexts(params: dict, ctx: DispatchContext) -> dict:
    from k8s.wrappers import list_kubeconfig_contexts
    return list_kubeconfig_contexts()


def _handle_switch_kubeconfig_context(params: dict, ctx: DispatchContext) -> dict:
    from k8s.wrappers import switch_kubeconfig_context
    return switch_kubeconfig_context(params["context_name"])


def _handle_get_current_context(params: dict, ctx: DispatchContext) -> dict:
    from k8s.wrappers import get_current_context
    return get_current_context()


def _handle_k8sgpt_analyze(params: dict, ctx: DispatchContext) -> dict:
    from k8s.wrappers import k8sgpt_analyze
    return k8sgpt_analyze(params.get("namespace"), params.get("filter_text"))


# -- Kubeconfig management --

def _handle_add_kubeconfig_context(params: dict, ctx: DispatchContext) -> dict:
    from k8s.wrappers import add_kubeconfig_context
    return add_kubeconfig_context(
        params["ssh_connection"],
        params.get("password"),
        params.get("context_name"),
        params.get("port", 22),
    )


# -- Deployment repo tools --

def _handle_search_deployment_repo(params: dict, ctx: DispatchContext) -> dict:
    from k8s.wrappers import search_deployment_repo
    return search_deployment_repo(
        params["query"], params.get("path_filter"), params.get("file_extension"),
    )


def _handle_get_deployment_repo_file(params: dict, ctx: DispatchContext) -> dict:
    from k8s.wrappers import get_deployment_repo_file
    return get_deployment_repo_file(params["file_path"])


def _handle_list_deployment_repo_path(params: dict, ctx: DispatchContext) -> dict:
    from k8s.wrappers import list_deployment_repo_path
    return list_deployment_repo_path(params.get("path", ""))


# -- Write operations --

def _handle_exec_pod_command(params: dict, ctx: DispatchContext) -> dict:
    from k8s.wrappers import exec_pod_command
    return exec_pod_command(
        params.get("namespace") or "default",
        params.get("pod_name", ""),
        params.get("command", ""),
        params.get("container"),
        params.get("confirm", False),
    )


def _handle_delete_pod(params: dict, ctx: DispatchContext) -> dict:
    from k8s.wrappers import delete_pod
    return delete_pod(
        params.get("namespace") or "default",
        params.get("pod_name", ""),
        params.get("grace_period", 30),
        params.get("confirm", False),
    )


def _handle_rollout_restart(params: dict, ctx: DispatchContext) -> dict:
    from k8s.wrappers import rollout_restart
    return rollout_restart(
        params.get("namespace") or "default",
        params.get("deployment_name", ""),
        params.get("confirm", False),
    )


def _handle_scale_deployment(params: dict, ctx: DispatchContext) -> dict:
    from k8s.wrappers import scale_deployment
    return scale_deployment(
        params.get("namespace") or "default",
        params.get("deployment_name", ""),
        params.get("replicas", 1),
        params.get("confirm", False),
    )


def _handle_apply_patch(params: dict, ctx: DispatchContext) -> dict:
    from k8s.wrappers import apply_patch
    return apply_patch(
        params.get("namespace") or "default",
        params.get("resource_type", ""),
        params.get("resource_name", ""),
        params.get("patch", ""),
        params.get("patch_type", "strategic"),
        params.get("confirm", False),
    )


# -- AI analysis tools (return JSON strings; handler parses for chat/react) --

def _handle_analyze_error(params: dict, ctx: DispatchContext) -> dict:
    from ai_tools.analyze import run
    raw = run(params.get("error_text", ""), params.get("tool", "kubernetes"))
    if ctx.surface == "mcp":
        return {"_raw_text": raw}
    return json.loads(raw)


def _handle_get_fix_commands(params: dict, ctx: DispatchContext) -> dict:
    from ai_tools.fix import get_fix_commands
    raw = get_fix_commands(
        error_text=params.get("error_text"),
        category=params.get("category"),
    )
    if ctx.surface == "mcp":
        return {"_raw_text": raw}
    return json.loads(raw)


def _handle_list_error_categories(params: dict, ctx: DispatchContext) -> dict:
    from ai_tools.fix import list_categories
    raw = list_categories()
    if ctx.surface == "mcp":
        return {"_raw_text": raw}
    return json.loads(raw)


def _handle_cluster_report(params: dict, ctx: DispatchContext) -> dict:
    from ai_tools.report import cluster_report
    raw = cluster_report(params["events_text"])
    if ctx.surface == "mcp":
        return {"_raw_text": raw}
    return json.loads(raw)


def _handle_error_summary(params: dict, ctx: DispatchContext) -> dict:
    from ai_tools.report import error_summary
    raw = error_summary(params.get("errors", []))
    if ctx.surface == "mcp":
        return {"_raw_text": raw}
    return json.loads(raw)


def _handle_generate_runbook(params: dict, ctx: DispatchContext) -> dict:
    from ai_tools.runbook import generate_runbook
    raw = generate_runbook(
        error_text=params.get("error_text"),
        category=params.get("category"),
    )
    if ctx.surface == "mcp":
        return {"_raw_text": raw}
    return json.loads(raw)


# ── Schema imports ──────────────────────────────────────────────────────────

from mcp_server.schemas import (
    FindWorkloadInput, GetPodsInput, GetNodesInput, GetNamespacesInput,
    ListNamespaceResourcesInput, ListServicesInput, GetResourceGraphInput,
    DescribePodInput, GetPodLogsInput, GetEventsInput,
    GetDeploymentInput, GetServiceInput, GetEndpointsInput,
    GetRolloutStatusInput, K8sgptAnalyzeInput,
    AddKubeconfigContextInput, ListKubeconfigContextsInput,
    SwitchKubeconfigContextInput, GetCurrentContextInput,
    SearchDeploymentRepoInput, GetDeploymentRepoFileInput,
    ListDeploymentRepoPathInput,
    InvestigatePodInput, InvestigateWorkloadInput, AnalyzeNamespaceInput,
    ExecPodCommandInput, DeletePodInput, RolloutRestartInput,
    ScaleDeploymentInput, ApplyPatchInput,
    AnalyzeErrorInput, GetFixCommandsInput, ListErrorCategoriesInput,
    ClusterReportInput, ErrorSummaryInput, GenerateRunbookInput,
)


# ── Convenience sets ────────────────────────────────────────────────────────

_ALL = frozenset({"mcp", "chat", "react"})
_MCP_ONLY = frozenset({"mcp"})
_MCP_CHAT_REACT = _ALL


# ── Tool registry ───────────────────────────────────────────────────────────

TOOLS: dict[str, ToolDef] = {}


def _reg(tool: ToolDef) -> None:
    """Register a tool (internal helper)."""
    TOOLS[tool.name] = tool


# -- Investigation tools --

_reg(ToolDef(
    name="investigate_pod",
    handler=_handle_investigate_pod,
    schema=InvestigatePodInput,
    description=(
        "Deep investigation of a specific pod: collects status, describe, logs, "
        "events, and AI analysis. Best first tool for 'why is X crashing?'"
    ),
    category="investigation",
    surfaces=_ALL,
))

_reg(ToolDef(
    name="investigate_workload",
    handler=_handle_investigate_workload,
    schema=InvestigateWorkloadInput,
    description=(
        "Investigate a deployment/statefulset/daemonset: replica status, pod health, "
        "rollout history, events, AI analysis."
    ),
    category="investigation",
    surfaces=_ALL,
))

_reg(ToolDef(
    name="analyze_namespace",
    handler=_handle_analyze_namespace,
    schema=AnalyzeNamespaceInput,
    description="Holistic health check of an entire namespace: all pods, events, services, issues.",
    category="investigation",
    surfaces=_ALL,
))

# -- Discovery tools --

_reg(ToolDef(
    name="find_workload",
    handler=_handle_find_workload,
    schema=FindWorkloadInput,
    description=(
        "Search for matching workloads (deployments, pods, services) across all namespaces. "
        "Use when you know the name but not the namespace."
    ),
    category="discovery",
    surfaces=_ALL,
))

_reg(ToolDef(
    name="get_namespaces",
    handler=_handle_get_namespaces,
    schema=GetNamespacesInput,
    description="List all namespaces in the current cluster with status and labels.",
    category="discovery",
    surfaces=_ALL,
))

_reg(ToolDef(
    name="get_nodes",
    handler=_handle_get_nodes,
    schema=GetNodesInput,
    description="List all nodes in the cluster with status, roles, capacity, and resource usage.",
    category="discovery",
    surfaces=_ALL,
))

_reg(ToolDef(
    name="list_namespace_resources",
    handler=_handle_list_namespace_resources,
    schema=ListNamespaceResourcesInput,
    description=(
        "Get an aggregate view of everything running in a namespace: pods, services, "
        "deployments, statefulsets, daemonsets, configmaps, and ingresses."
    ),
    category="discovery",
    surfaces=_ALL,
))

# -- Pod tools --

_reg(ToolDef(
    name="get_pods",
    handler=_handle_get_pods,
    schema=GetPodsInput,
    description=(
        "List pods in a namespace with optional label selector and status filter. "
        "Use namespace='*' for all namespaces."
    ),
    category="pod",
    surfaces=_ALL,
))

_reg(ToolDef(
    name="get_pod_logs",
    handler=_handle_get_pod_logs,
    schema=GetPodLogsInput,
    description=(
        "Get logs from a specific pod. Set previous=true for crashed container logs."
    ),
    category="pod",
    surfaces=_ALL,
))

_reg(ToolDef(
    name="describe_pod",
    handler=_handle_describe_pod,
    schema=DescribePodInput,
    description="Get full kubectl describe output for a pod.",
    category="pod",
    surfaces=_MCP_ONLY,
    react_enabled=False,
    notes="Used internally by investigate_pod; not exposed to chat/react directly.",
))

# -- Cluster state tools --

_reg(ToolDef(
    name="get_events",
    handler=_handle_get_events,
    schema=GetEventsInput,
    description=(
        "Get events in a namespace. Use namespace='*' for all. "
        "Use field_selector='type=Warning' for warnings only."
    ),
    category="cluster",
    surfaces=_ALL,
))

_reg(ToolDef(
    name="get_deployment",
    handler=_handle_get_deployment,
    schema=GetDeploymentInput,
    description="Get details of a specific deployment.",
    category="cluster",
    surfaces=_ALL,
))

_reg(ToolDef(
    name="get_service",
    handler=_handle_get_service,
    schema=GetServiceInput,
    description="Get details of a specific service including ports and selectors.",
    category="cluster",
    surfaces=_ALL,
))

_reg(ToolDef(
    name="get_endpoints",
    handler=_handle_get_endpoints,
    schema=GetEndpointsInput,
    description="Check endpoints for a service.",
    category="cluster",
    surfaces=_ALL,
))

_reg(ToolDef(
    name="get_rollout_status",
    handler=_handle_get_rollout_status,
    schema=GetRolloutStatusInput,
    description="Check if a deployment rollout is progressing.",
    category="cluster",
    surfaces=_ALL,
))

_reg(ToolDef(
    name="list_services",
    handler=_handle_list_services,
    schema=ListServicesInput,
    description="List all services in a namespace with type, cluster IP, ports, and selectors.",
    category="cluster",
    surfaces=_ALL,
))

_reg(ToolDef(
    name="get_resource_graph",
    handler=_handle_get_resource_graph,
    schema=GetResourceGraphInput,
    description=(
        "Build a visual resource graph for a namespace. Returns nodes "
        "(ingresses, services, deployments, pods with status) and edges."
    ),
    category="cluster",
    surfaces=_ALL,
))

_reg(ToolDef(
    name="list_kubeconfig_contexts",
    handler=_handle_list_kubeconfig_contexts,
    schema=ListKubeconfigContextsInput,
    description="List available kubeconfig contexts and show the active context.",
    category="cluster",
    surfaces=_ALL,
    aliases=("list_contexts",),
))

_reg(ToolDef(
    name="switch_kubeconfig_context",
    handler=_handle_switch_kubeconfig_context,
    schema=SwitchKubeconfigContextInput,
    description="Switch to a different cluster context.",
    category="cluster",
    surfaces=_ALL,
    aliases=("switch_context",),
))

_reg(ToolDef(
    name="get_current_context",
    handler=_handle_get_current_context,
    schema=GetCurrentContextInput,
    description="Get the currently active kubeconfig context.",
    category="cluster",
    surfaces=_MCP_ONLY,
    react_enabled=False,
    notes="Available in MCP; chat/react use list_contexts instead.",
))

_reg(ToolDef(
    name="k8sgpt_analyze",
    handler=_handle_k8sgpt_analyze,
    schema=K8sgptAnalyzeInput,
    description="Run k8sgpt analysis on the cluster or a specific namespace.",
    category="cluster",
    surfaces=_MCP_ONLY,
    react_enabled=False,
    notes="Requires k8sgpt binary. MCP-only for now.",
))

# -- Kubeconfig management --

_reg(ToolDef(
    name="add_kubeconfig_context",
    handler=_handle_add_kubeconfig_context,
    schema=AddKubeconfigContextInput,
    description="Add a new kubeconfig context via SSH connection.",
    category="cluster",
    surfaces=_MCP_ONLY,
    react_enabled=False,
))

# -- Deployment repo tools --

_reg(ToolDef(
    name="search_deployment_repo",
    handler=_handle_search_deployment_repo,
    schema=SearchDeploymentRepoInput,
    description="Search the deployment-provisioning repo for files matching a query.",
    category="repo",
    surfaces=_MCP_ONLY,
    react_enabled=False,
))

_reg(ToolDef(
    name="get_deployment_repo_file",
    handler=_handle_get_deployment_repo_file,
    schema=GetDeploymentRepoFileInput,
    description="Read a file from the deployment-provisioning repo.",
    category="repo",
    surfaces=_MCP_ONLY,
    react_enabled=False,
))

_reg(ToolDef(
    name="list_deployment_repo_path",
    handler=_handle_list_deployment_repo_path,
    schema=ListDeploymentRepoPathInput,
    description="List files in a directory of the deployment-provisioning repo.",
    category="repo",
    surfaces=_MCP_ONLY,
    react_enabled=False,
))

# -- Write operations --

_reg(ToolDef(
    name="exec_pod_command",
    handler=_handle_exec_pod_command,
    schema=ExecPodCommandInput,
    description="Execute a command inside a running pod.",
    category="write",
    surfaces=_MCP_ONLY,
    write_op=True,
    requires_confirm=True,
    react_enabled=False,
))

_reg(ToolDef(
    name="delete_pod",
    handler=_handle_delete_pod,
    schema=DeletePodInput,
    description="Delete a pod (it will be recreated by its controller).",
    category="write",
    surfaces=_MCP_ONLY,
    write_op=True,
    requires_confirm=True,
    react_enabled=False,
))

_reg(ToolDef(
    name="rollout_restart",
    handler=_handle_rollout_restart,
    schema=RolloutRestartInput,
    description="Perform a rolling restart of a deployment.",
    category="write",
    surfaces=_MCP_ONLY,
    write_op=True,
    requires_confirm=True,
    react_enabled=False,
))

_reg(ToolDef(
    name="scale_deployment",
    handler=_handle_scale_deployment,
    schema=ScaleDeploymentInput,
    description="Scale a deployment to a target replica count.",
    category="write",
    surfaces=_MCP_ONLY,
    write_op=True,
    requires_confirm=True,
    react_enabled=False,
))

_reg(ToolDef(
    name="apply_patch",
    handler=_handle_apply_patch,
    schema=ApplyPatchInput,
    description="Apply a JSON patch to a Kubernetes resource.",
    category="write",
    surfaces=_MCP_ONLY,
    write_op=True,
    requires_confirm=True,
    react_enabled=False,
))

# -- AI analysis tools --

_reg(ToolDef(
    name="analyze_error",
    handler=_handle_analyze_error,
    schema=AnalyzeErrorInput,
    description="AI diagnosis of a pasted error message or log snippet.",
    category="ai",
    surfaces=_ALL,
    returns_json_string=True,
))

_reg(ToolDef(
    name="get_fix_commands",
    handler=_handle_get_fix_commands,
    schema=GetFixCommandsInput,
    description="Get specific kubectl fix commands for an error.",
    category="ai",
    surfaces=_ALL,
    returns_json_string=True,
))

_reg(ToolDef(
    name="list_error_categories",
    handler=_handle_list_error_categories,
    schema=ListErrorCategoriesInput,
    description="List all known error categories with descriptions.",
    category="ai",
    surfaces=_MCP_ONLY,
    returns_json_string=True,
    react_enabled=False,
))

_reg(ToolDef(
    name="cluster_report",
    handler=_handle_cluster_report,
    schema=ClusterReportInput,
    description="Generate a cluster health report from events data.",
    category="ai",
    surfaces=_ALL,
    returns_json_string=True,
))

_reg(ToolDef(
    name="error_summary",
    handler=_handle_error_summary,
    schema=ErrorSummaryInput,
    description="Summarize multiple errors into a concise report.",
    category="ai",
    surfaces=_ALL,
    returns_json_string=True,
))

_reg(ToolDef(
    name="generate_runbook",
    handler=_handle_generate_runbook,
    schema=GenerateRunbookInput,
    description=(
        "Generate a step-by-step runbook for a recurring error. "
        "Only use when the user explicitly asks for a runbook."
    ),
    category="ai",
    surfaces=_ALL,
    returns_json_string=True,
))


# ── Public API ──────────────────────────────────────────────────────────────

def resolve_tool(name: str) -> Optional[ToolDef]:
    """Look up a tool by canonical name or alias."""
    tool = TOOLS.get(name)
    if tool:
        return tool
    for t in TOOLS.values():
        if name in t.aliases:
            return t
    return None


def tools_for_surface(surface: ToolSurface) -> list[ToolDef]:
    """Return all tools available on a given surface, sorted by name."""
    return sorted(
        (t for t in TOOLS.values() if surface in t.surfaces),
        key=lambda t: t.name,
    )


def build_react_tool_descriptions() -> str:
    """Generate the TOOL_DESCRIPTIONS string from registry entries.

    Groups tools by category, filters to react-enabled tools on the
    'react' surface. Output format matches the existing freeform text
    in react.py so ReAct prompt behavior is preserved.
    """
    react_tools = [
        t for t in tools_for_surface("react")
        if t.react_enabled
    ]

    # Group by category, preserving a stable order
    category_order = [
        "investigation", "discovery", "pod", "cluster", "ai",
    ]
    groups: dict[str, list[ToolDef]] = {}
    for t in react_tools:
        groups.setdefault(t.category, []).append(t)

    category_labels = {
        "investigation": "INVESTIGATION TOOLS (start here for debugging questions)",
        "discovery": "DISCOVERY TOOLS (use when you need to find things)",
        "pod": "POD TOOLS",
        "cluster": "CLUSTER STATE TOOLS",
        "ai": "AI ANALYSIS TOOLS (use after gathering data, or for specific requests)",
    }

    lines = ["Available tools (call exactly one per step):\n"]
    for cat in category_order:
        tools_in_cat = groups.get(cat, [])
        if not tools_in_cat:
            continue
        label = category_labels.get(cat, cat.upper())
        lines.append(f"{label}:")
        for t in tools_in_cat:
            # Use alias if it exists (shorter name preferred in ReAct prompts)
            display_name = t.aliases[0] if t.aliases else t.name
            lines.append(f"- {display_name} -- {t.description}")
        lines.append("")

    return "\n".join(lines)


def dispatch(tool_name: str, params: dict, ctx: DispatchContext) -> dict:
    """Shared dispatcher: resolve tool, validate surface, call handler.

    This preserves the error handling behavior from chat.py _dispatch:
    - Not-found errors trigger cross-namespace search via find_workload
    - Generic errors are returned as structured dicts
    """
    tool = resolve_tool(tool_name)
    if tool is None:
        return {"error": f"Unknown tool: {tool_name}", "tool": tool_name}

    if ctx.surface not in tool.surfaces:
        return {
            "error": f"Tool '{tool.name}' is not available on {ctx.surface}",
            "tool": tool.name,
        }

    try:
        return tool.handler(params, ctx)
    except Exception as exc:
        err_msg = str(exc)
        logger.exception("dispatch error for %s", tool.name)

        # Not-found fallback: search across namespaces
        not_found = (
            "not found" in err_msg.lower()
            or "notfound" in err_msg.lower()
            or "no resources found" in err_msg.lower()
        )
        if not_found:
            name = (
                params.get("deployment_name")
                or params.get("service_name")
                or params.get("pod_name")
                or params.get("name")
                or ""
            )
            ns = params.get("namespace", "default")
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
                    "Try specifying the namespace explicitly."
                ),
            }

        return {"error": err_msg, "tool": tool.name}
