"""MCP tool registrations for the unified K8s DevOps MCP server.

Registers 33 tools split across two categories:
  • 27 live kubectl tools  — real-time cluster investigation & recovery
  •  6 AI analysis tools  — LLM-powered error analysis, fix playbooks, runbooks

Live tools (kubectl-based):
  find_workload, get_pods, get_namespaces, list_namespace_resources, list_services,
  get_resource_graph, describe_pod, get_pod_logs, get_events, get_deployment,
  get_service, get_endpoints, get_rollout_status, k8sgpt_analyze,
  add_kubeconfig_context, list_kubeconfig_contexts, switch_kubeconfig_context,
  get_current_context, search_deployment_repo, get_deployment_repo_file,
  list_deployment_repo_path, investigate_pod (+ AI analysis),
  exec_pod_command, delete_pod, rollout_restart, scale_deployment, apply_patch

AI tools (LLM + RAG):
  analyze_error, get_fix_commands, list_error_categories,
  cluster_report, error_summary, generate_runbook
"""

import logging
from typing import Any, Dict

from mcp.server import Server
from mcp.types import Tool, TextContent

from k8s.wrappers import (
    find_workload, get_pods, get_namespaces, list_namespace_resources, list_services,
    describe_pod, get_pod_logs, get_events,
    get_deployment, get_service, get_endpoints, get_rollout_status,
    k8sgpt_analyze, add_kubeconfig_context, list_kubeconfig_contexts,
    switch_kubeconfig_context, get_current_context, search_deployment_repo,
    get_deployment_repo_file, list_deployment_repo_path, investigate_pod,
    exec_pod_command, delete_pod, rollout_restart, scale_deployment, apply_patch,
    get_resource_graph, investigate_workload, analyze_namespace,
)
from k8s.validators import ValidationError
from k8s.kubectl_runner import KubectlError

import ai_tools.analyze as _analyze_tool
import ai_tools.fix as _fix_tool
import ai_tools.report as _report_tool
import ai_tools.runbook as _runbook_tool

from mcp_server.schemas import (
    # Live kubectl schemas
    FindWorkloadInput, GetPodsInput, GetNamespacesInput, ListNamespaceResourcesInput,
    ListServicesInput, GetResourceGraphInput, DescribePodInput, GetPodLogsInput,
    GetEventsInput, GetDeploymentInput, GetServiceInput, GetEndpointsInput,
    GetRolloutStatusInput, K8sgptAnalyzeInput, AddKubeconfigContextInput,
    ListKubeconfigContextsInput, SwitchKubeconfigContextInput, GetCurrentContextInput,
    SearchDeploymentRepoInput, GetDeploymentRepoFileInput, ListDeploymentRepoPathInput,
    InvestigatePodInput, ExecPodCommandInput, DeletePodInput, RolloutRestartInput,
    ScaleDeploymentInput, ApplyPatchInput, InvestigateWorkloadInput, AnalyzeNamespaceInput,
    # AI tool schemas
    AnalyzeErrorInput, GetFixCommandsInput, ListErrorCategoriesInput,
    ClusterReportInput, ErrorSummaryInput, GenerateRunbookInput,
)

logger = logging.getLogger(__name__)


def register_tools(server: Server) -> None:
    """Register all tools with the MCP server."""

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            # ── Live Kubectl Tools ──────────────────────────────────────────────
            Tool(
                name="find_workload",
                description=(
                    "Search for matching workloads (deployments, pods, services) across allowed namespaces. "
                    "Use when you know the service/workload name but not the namespace. "
                    "Optionally provide an environment hint (prod, staging, dev) to prioritize search."
                ),
                inputSchema=FindWorkloadInput.model_json_schema()
            ),
            Tool(
                name="get_pods",
                description=(
                    "List pods in a namespace with optional label selector. "
                    "Use as a first step to understand pod health and identify unhealthy pods. "
                    "Returns pod summaries including phase, ready status, restart count, and node placement."
                ),
                inputSchema=GetPodsInput.model_json_schema()
            ),
            Tool(
                name="get_namespaces",
                description=(
                    "List all namespaces in the current cluster with status and labels. "
                    "Use this when you need to discover the available namespaces before drilling deeper."
                ),
                inputSchema=GetNamespacesInput.model_json_schema()
            ),
            Tool(
                name="list_namespace_resources",
                description=(
                    "Get an aggregate view of everything running in a namespace. "
                    "Returns pods, services, deployments, statefulsets, daemonsets, configmaps, and ingresses."
                ),
                inputSchema=ListNamespaceResourcesInput.model_json_schema()
            ),
            Tool(
                name="list_services",
                description=(
                    "List all services in a namespace with type, cluster IP, ports, and selectors. "
                    "Use when the user wants all services rather than details for a single one."
                ),
                inputSchema=ListServicesInput.model_json_schema()
            ),
            Tool(
                name="get_resource_graph",
                description=(
                    "Build a visual resource graph for a namespace. Returns nodes "
                    "(ingresses, services, deployments, pods with status) and edges "
                    "(ingress→service, service→pod via selector, deployment→pod via labels). "
                    "Use when the user wants to visualize, map, or 'see' the namespace topology."
                ),
                inputSchema=GetResourceGraphInput.model_json_schema()
            ),
            Tool(
                name="describe_pod",
                description=(
                    "Get detailed pod description with parsed highlights. "
                    "Use after identifying a failing pod to understand its state, conditions, and recent events. "
                    "Returns restart count, current state, last state, and readiness information."
                ),
                inputSchema=DescribePodInput.model_json_schema()
            ),
            Tool(
                name="get_pod_logs",
                description=(
                    "Get pod logs with size limits. "
                    "Use previous=True for CrashLoopBackOff investigations to see logs from the crashed container. "
                    "Logs are automatically truncated to prevent memory issues."
                ),
                inputSchema=GetPodLogsInput.model_json_schema()
            ),
            Tool(
                name="get_events",
                description=(
                    "Get recent events in a namespace sorted by timestamp. "
                    "Use for scheduling issues, image pull errors, probe failures, and other cluster events."
                ),
                inputSchema=GetEventsInput.model_json_schema()
            ),
            Tool(
                name="get_deployment",
                description=(
                    "Get deployment status and details including replica counts and conditions. "
                    "Use to understand deployment health, rollout status, and scaling issues."
                ),
                inputSchema=GetDeploymentInput.model_json_schema()
            ),
            Tool(
                name="get_service",
                description=(
                    "Get service details including selector, ports, and type. "
                    "Use to understand how traffic is routed to pods and verify service configuration."
                ),
                inputSchema=GetServiceInput.model_json_schema()
            ),
            Tool(
                name="get_endpoints",
                description=(
                    "Get service endpoints to check if pods are backing the service. "
                    "Use when a service has no endpoints or when investigating connectivity issues."
                ),
                inputSchema=GetEndpointsInput.model_json_schema()
            ),
            Tool(
                name="get_rollout_status",
                description=(
                    "Get rollout status for a deployment. "
                    "Use when investigating stuck rollouts or deployment updates."
                ),
                inputSchema=GetRolloutStatusInput.model_json_schema()
            ),
            Tool(
                name="k8sgpt_analyze",
                description=(
                    "Run k8sgpt analysis for broader cluster insights (requires k8sgpt CLI). "
                    "Use only as a supporting step when targeted checks are insufficient."
                ),
                inputSchema=K8sgptAnalyzeInput.model_json_schema()
            ),
            Tool(
                name="add_kubeconfig_context",
                description=(
                    "Add a new Kubernetes cluster context via SSH. "
                    "Use to dynamically add cluster contexts without restarting the server. "
                    "Supports key-based and password-based SSH auth. "
                    "Example: ssh_connection='ansible@hostname.example.com'"
                ),
                inputSchema=AddKubeconfigContextInput.model_json_schema()
            ),
            Tool(
                name="list_kubeconfig_contexts",
                description=(
                    "List all available kubeconfig contexts and show which one is currently active."
                ),
                inputSchema=ListKubeconfigContextsInput.model_json_schema()
            ),
            Tool(
                name="switch_kubeconfig_context",
                description=(
                    "Switch to a different kubeconfig context. "
                    "All subsequent kubectl commands will target the selected cluster."
                ),
                inputSchema=SwitchKubeconfigContextInput.model_json_schema()
            ),
            Tool(
                name="get_current_context",
                description="Get the current active kubeconfig context (which cluster is active).",
                inputSchema=GetCurrentContextInput.model_json_schema()
            ),
            Tool(
                name="search_deployment_repo",
                description=(
                    "Search the deployment-provisioning repository for Ansible playbooks, Helm charts, "
                    "and infrastructure configurations. Supports content search and filename matching."
                ),
                inputSchema=SearchDeploymentRepoInput.model_json_schema()
            ),
            Tool(
                name="get_deployment_repo_file",
                description=(
                    "Get the full contents of a specific file from the deployment-provisioning repository. "
                    "Use after finding relevant files with search_deployment_repo."
                ),
                inputSchema=GetDeploymentRepoFileInput.model_json_schema()
            ),
            Tool(
                name="list_deployment_repo_path",
                description=(
                    "List files and directories in the deployment-provisioning repository. "
                    "Use to explore Ansible playbooks, Helm charts, and infrastructure configurations."
                ),
                inputSchema=ListDeploymentRepoPathInput.model_json_schema()
            ),
            Tool(
                name="investigate_pod",
                description=(
                    "End-to-end investigation for a pod using failure-mode playbooks + optional AI diagnosis. "
                    "Automatically classifies Pending, ImagePullBackOff, or CrashLoopBackOff and runs "
                    "the right kubectl tool chain. If use_ai=True (default) and GEMINI_API_KEY is set, "
                    "appends a Gemini AI root-cause analysis and fix commands to the kubectl findings. "
                    "Use this as your primary triage tool."
                ),
                inputSchema=InvestigatePodInput.model_json_schema()
            ),
            Tool(
                name="investigate_workload",
                description=(
                    "Investigate a Deployment or StatefulSet workload directly. "
                    "Checks for scale-up issues, quota limitations, and controller-level events before checking pods. "
                    "Use when a user asks to investigate a deployment, statefulset, or application as a whole."
                ),
                inputSchema=InvestigateWorkloadInput.model_json_schema()
            ),
            Tool(
                name="analyze_namespace",
                description=(
                    "Perform a holistic health check on an entire namespace. "
                    "Gathers all resources and recent warnings to identify cascading or systemic failures. "
                    "Use when the user asks to check the health of a namespace or environment."
                ),
                inputSchema=AnalyzeNamespaceInput.model_json_schema()
            ),
            Tool(
                name="exec_pod_command",
                description=(
                    "Execute a command inside a pod container. WRITE OPERATION requiring user approval. "
                    "Requires confirm=True to execute. Returns command output."
                ),
                inputSchema=ExecPodCommandInput.model_json_schema()
            ),
            Tool(
                name="delete_pod",
                description=(
                    "Delete a pod to force restart. DESTRUCTIVE OPERATION requiring user approval. "
                    "If managed by a controller the pod will be recreated. Requires confirm=True."
                ),
                inputSchema=DeletePodInput.model_json_schema()
            ),
            Tool(
                name="rollout_restart",
                description=(
                    "Perform a rolling restart of a deployment. WRITE OPERATION requiring user approval. "
                    "Triggers a rolling update that recreates pods one by one. Requires confirm=True."
                ),
                inputSchema=RolloutRestartInput.model_json_schema()
            ),
            Tool(
                name="scale_deployment",
                description=(
                    "Scale a deployment to a specific number of replicas. WRITE OPERATION requiring user approval. "
                    "Scale to 0 to stop all pods. Requires confirm=True."
                ),
                inputSchema=ScaleDeploymentInput.model_json_schema()
            ),
            Tool(
                name="apply_patch",
                description=(
                    "Apply a JSON patch to a Kubernetes resource. WRITE OPERATION requiring user approval. "
                    "Use to modify memory limits, env vars, or image tags. Requires confirm=True."
                ),
                inputSchema=ApplyPatchInput.model_json_schema()
            ),

            # ── AI Analysis Tools ───────────────────────────────────────────────
            Tool(
                name="analyze_error",
                description=(
                    "Analyze a pasted Kubernetes or Ansible error with Gemini AI + RAG similarity search. "
                    "No live cluster access needed — paste the error text from any log, terminal, or CI/CD pipeline. "
                    "Returns root cause, fix steps, kubectl commands, and similar past cases."
                ),
                inputSchema=AnalyzeErrorInput.model_json_schema()
            ),
            Tool(
                name="get_fix_commands",
                description=(
                    "Get curated fix commands and playbooks for a specific Kubernetes error category. "
                    "Provide either raw error_text (auto-classifies) or a known category name. "
                    "Returns copy-paste ready kubectl commands with explanations."
                ),
                inputSchema=GetFixCommandsInput.model_json_schema()
            ),
            Tool(
                name="list_error_categories",
                description=(
                    "List all supported Kubernetes error categories with descriptions. "
                    "Use this to discover what categories are available for get_fix_commands or generate_runbook."
                ),
                inputSchema=ListErrorCategoriesInput.model_json_schema()
            ),
            Tool(
                name="cluster_report",
                description=(
                    "Analyze pasted kubectl events output and produce an AI-powered cluster health report. "
                    "Paste the output of: kubectl get events --all-namespaces --sort-by='.lastTimestamp' "
                    "Returns event statistics, top issue categories, and an AI executive summary."
                ),
                inputSchema=ClusterReportInput.model_json_schema()
            ),
            Tool(
                name="error_summary",
                description=(
                    "Summarize a batch of error strings (e.g., from a CI/CD pipeline run or log file). "
                    "Pass a list of error strings and get back category breakdown + AI executive summary. "
                    "Useful for post-incident reports and sprint retrospectives."
                ),
                inputSchema=ErrorSummaryInput.model_json_schema()
            ),
            Tool(
                name="generate_runbook",
                description=(
                    "Generate a markdown runbook for a recurring Kubernetes or Ansible error category. "
                    "Provide a category name or raw error text. Output is ready to paste into Confluence or Notion. "
                    "Includes overview, symptoms, diagnosis steps, fix procedures, prevention, and escalation path."
                ),
                inputSchema=GenerateRunbookInput.model_json_schema()
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: Any) -> list[TextContent]:
        """Handle tool execution requests from Cursor."""
        try:
            # ── Live Kubectl Tools ────────────────────────────────────────────
            if name == "find_workload":
                inp = FindWorkloadInput(**arguments)
                return [TextContent(type="text", text=_fmt(find_workload(inp.name, inp.environment)))]

            elif name == "get_pods":
                inp = GetPodsInput(**arguments)
                return [TextContent(type="text", text=_fmt(get_pods(inp.namespace, inp.label_selector)))]

            elif name == "get_namespaces":
                return [TextContent(type="text", text=_fmt(get_namespaces()))]

            elif name == "list_namespace_resources":
                inp = ListNamespaceResourcesInput(**arguments)
                return [TextContent(type="text", text=_fmt(list_namespace_resources(inp.namespace)))]

            elif name == "list_services":
                inp = ListServicesInput(**arguments)
                return [TextContent(type="text", text=_fmt(list_services(inp.namespace)))]

            elif name == "get_resource_graph":
                inp = GetResourceGraphInput(**arguments)
                return [TextContent(type="text", text=_fmt(get_resource_graph(inp.namespace)))]

            elif name == "describe_pod":
                inp = DescribePodInput(**arguments)
                return [TextContent(type="text", text=_fmt(describe_pod(inp.namespace, inp.pod_name)))]

            elif name == "get_pod_logs":
                inp = GetPodLogsInput(**arguments)
                return [TextContent(type="text", text=_fmt(get_pod_logs(
                    inp.namespace, inp.pod_name, inp.previous, inp.tail, inp.container
                )))]

            elif name == "get_events":
                inp = GetEventsInput(**arguments)
                return [TextContent(type="text", text=_fmt(get_events(inp.namespace, inp.field_selector)))]

            elif name == "get_deployment":
                inp = GetDeploymentInput(**arguments)
                return [TextContent(type="text", text=_fmt(get_deployment(inp.namespace, inp.deployment_name)))]

            elif name == "get_service":
                inp = GetServiceInput(**arguments)
                return [TextContent(type="text", text=_fmt(get_service(inp.namespace, inp.service_name)))]

            elif name == "get_endpoints":
                inp = GetEndpointsInput(**arguments)
                return [TextContent(type="text", text=_fmt(get_endpoints(inp.namespace, inp.service_name)))]

            elif name == "get_rollout_status":
                inp = GetRolloutStatusInput(**arguments)
                return [TextContent(type="text", text=_fmt(get_rollout_status(inp.namespace, inp.deployment_name)))]

            elif name == "k8sgpt_analyze":
                inp = K8sgptAnalyzeInput(**arguments)
                return [TextContent(type="text", text=_fmt(k8sgpt_analyze(inp.namespace, inp.filter_text)))]

            elif name == "add_kubeconfig_context":
                inp = AddKubeconfigContextInput(**arguments)
                return [TextContent(type="text", text=_fmt(add_kubeconfig_context(
                    inp.ssh_connection, inp.password, inp.context_name, inp.port
                )))]

            elif name == "list_kubeconfig_contexts":
                return [TextContent(type="text", text=_fmt(list_kubeconfig_contexts()))]

            elif name == "switch_kubeconfig_context":
                inp = SwitchKubeconfigContextInput(**arguments)
                return [TextContent(type="text", text=_fmt(switch_kubeconfig_context(inp.context_name)))]

            elif name == "get_current_context":
                return [TextContent(type="text", text=_fmt(get_current_context()))]

            elif name == "search_deployment_repo":
                inp = SearchDeploymentRepoInput(**arguments)
                return [TextContent(type="text", text=_fmt(search_deployment_repo(
                    inp.query, inp.path_filter, inp.file_extension
                )))]

            elif name == "get_deployment_repo_file":
                inp = GetDeploymentRepoFileInput(**arguments)
                return [TextContent(type="text", text=_fmt(get_deployment_repo_file(inp.file_path)))]

            elif name == "list_deployment_repo_path":
                inp = ListDeploymentRepoPathInput(**arguments)
                return [TextContent(type="text", text=_fmt(list_deployment_repo_path(inp.path)))]

            elif name == "investigate_pod":
                inp = InvestigatePodInput(**arguments)
                return [TextContent(type="text", text=_fmt(investigate_pod(
                    inp.namespace, inp.pod_name, inp.tail, inp.use_ai
                )))]

            elif name == "investigate_workload":
                inp = InvestigateWorkloadInput(**arguments)
                return [TextContent(type="text", text=_fmt(investigate_workload(
                    inp.namespace, inp.workload_name, inp.workload_type, inp.use_ai
                )))]

            elif name == "analyze_namespace":
                inp = AnalyzeNamespaceInput(**arguments)
                return [TextContent(type="text", text=_fmt(analyze_namespace(inp.namespace)))]

            elif name == "exec_pod_command":
                inp = ExecPodCommandInput(**arguments)
                return [TextContent(type="text", text=_fmt(exec_pod_command(
                    inp.namespace, inp.pod_name, inp.command, inp.container, inp.confirm
                )))]

            elif name == "delete_pod":
                inp = DeletePodInput(**arguments)
                return [TextContent(type="text", text=_fmt(delete_pod(
                    inp.namespace, inp.pod_name, inp.grace_period, inp.confirm
                )))]

            elif name == "rollout_restart":
                inp = RolloutRestartInput(**arguments)
                return [TextContent(type="text", text=_fmt(rollout_restart(
                    inp.namespace, inp.deployment_name, inp.confirm
                )))]

            elif name == "scale_deployment":
                inp = ScaleDeploymentInput(**arguments)
                return [TextContent(type="text", text=_fmt(scale_deployment(
                    inp.namespace, inp.deployment_name, inp.replicas, inp.confirm
                )))]

            elif name == "apply_patch":
                inp = ApplyPatchInput(**arguments)
                return [TextContent(type="text", text=_fmt(apply_patch(
                    inp.namespace, inp.resource_type, inp.resource_name,
                    inp.patch, inp.patch_type, inp.confirm
                )))]

            # ── AI Analysis Tools ─────────────────────────────────────────────
            elif name == "analyze_error":
                inp = AnalyzeErrorInput(**arguments)
                return [TextContent(type="text", text=_analyze_tool.run(
                    inp.error_text, inp.tool, inp.environment
                ))]

            elif name == "get_fix_commands":
                inp = GetFixCommandsInput(**arguments)
                return [TextContent(type="text", text=_fix_tool.get_fix_commands(
                    inp.error_text, inp.category, inp.tool, inp.namespace, inp.resource_name
                ))]

            elif name == "list_error_categories":
                return [TextContent(type="text", text=_fix_tool.list_categories())]

            elif name == "cluster_report":
                inp = ClusterReportInput(**arguments)
                return [TextContent(type="text", text=_report_tool.cluster_report(
                    inp.events_text, inp.namespace
                ))]

            elif name == "error_summary":
                inp = ErrorSummaryInput(**arguments)
                return [TextContent(type="text", text=_report_tool.error_summary(
                    inp.errors, inp.tool
                ))]

            elif name == "generate_runbook":
                inp = GenerateRunbookInput(**arguments)
                return [TextContent(type="text", text=_runbook_tool.generate_runbook(
                    inp.category, inp.error_examples, inp.error_text, inp.tool
                ))]

            else:
                return [TextContent(type="text", text=f"Unknown tool: {name}")]

        except ValidationError as e:
            logger.error(f"Validation error in {name}: {e}")
            return [TextContent(type="text", text=f"Validation error: {str(e)}")]

        except KubectlError as e:
            logger.error(f"Kubectl error in {name}: {e}")
            return [TextContent(type="text", text=f"Kubectl error: {str(e)}\nStderr: {e.stderr}")]

        except Exception as e:
            logger.exception(f"Unexpected error in {name}")
            return [TextContent(type="text", text=f"Unexpected error: {str(e)}")]


def _fmt(result: Dict[str, Any]) -> str:
    """Format a dict result as indented JSON."""
    import json
    return json.dumps(result, indent=2, default=str)
