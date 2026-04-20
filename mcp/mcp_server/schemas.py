"""Pydantic schemas for MCP tool inputs.

Covers all 33 tools:
- 27 live kubectl tools (pod/deployment/service inspection, events, recovery,
  resource-graph topology, SSH-aware kubeconfig management)
- 1 enhanced investigate_pod with use_ai flag (counted above)
- 6 AI analysis tools (error analysis, fix playbooks, runbooks, reports)
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class FindWorkloadInput(BaseModel):
    """Input schema for find_workload tool."""
    
    name: str = Field(
        description="Workload name or partial name to search for"
    )
    environment: Optional[str] = Field(
        default=None,
        description="Environment hint (e.g., 'prod', 'staging', 'dev') to prioritize namespace search"
    )


class GetPodsInput(BaseModel):
    """Input schema for get_pods tool."""
    
    namespace: str = Field(
        description="Namespace to query for pods"
    )
    label_selector: Optional[str] = Field(
        default=None,
        description="Optional label selector (e.g., 'app=myapp,env=prod')"
    )


class GetNamespacesInput(BaseModel):
    """Input schema for get_namespaces tool."""

    pass


class ListNamespaceResourcesInput(BaseModel):
    """Input schema for list_namespace_resources tool."""

    namespace: str = Field(
        description="Namespace to inspect for aggregate resources"
    )


class ListServicesInput(BaseModel):
    """Input schema for list_services tool."""

    namespace: str = Field(
        description="Namespace to list services from"
    )


class GetResourceGraphInput(BaseModel):
    """Input schema for get_resource_graph tool."""

    namespace: str = Field(
        description="Namespace to build the visual resource graph for"
    )


class DescribePodInput(BaseModel):
    """Input schema for describe_pod tool."""
    
    namespace: str = Field(
        description="Namespace containing the pod"
    )
    pod_name: str = Field(
        description="Name of the pod to describe"
    )


class GetPodLogsInput(BaseModel):
    """Input schema for get_pod_logs tool."""
    
    namespace: str = Field(
        description="Namespace containing the pod"
    )
    pod_name: str = Field(
        description="Name of the pod"
    )
    previous: bool = Field(
        default=False,
        description="Get logs from previous container instance (useful for CrashLoopBackOff)"
    )
    tail: int = Field(
        default=200,
        description="Number of log lines to retrieve (will be capped by server settings)"
    )
    container: Optional[str] = Field(
        default=None,
        description="Container name for multi-container pods"
    )


class GetEventsInput(BaseModel):
    """Input schema for get_events tool."""
    
    namespace: str = Field(
        description="Namespace to query for events"
    )
    field_selector: Optional[str] = Field(
        default=None,
        description="Optional field selector for filtering events"
    )


class GetDeploymentInput(BaseModel):
    """Input schema for get_deployment tool."""
    
    namespace: str = Field(
        description="Namespace containing the deployment"
    )
    deployment_name: str = Field(
        description="Name of the deployment"
    )


class GetServiceInput(BaseModel):
    """Input schema for get_service tool."""
    
    namespace: str = Field(
        description="Namespace containing the service"
    )
    service_name: str = Field(
        description="Name of the service"
    )


class GetEndpointsInput(BaseModel):
    """Input schema for get_endpoints tool."""
    
    namespace: str = Field(
        description="Namespace containing the service"
    )
    service_name: str = Field(
        description="Name of the service to check endpoints for"
    )


class GetRolloutStatusInput(BaseModel):
    """Input schema for get_rollout_status tool."""
    
    namespace: str = Field(
        description="Namespace containing the deployment"
    )
    deployment_name: str = Field(
        description="Name of the deployment"
    )


class K8sgptAnalyzeInput(BaseModel):
    """Input schema for k8sgpt_analyze tool."""
    
    namespace: Optional[str] = Field(
        default=None,
        description="Optional namespace to analyze (analyzes all if not specified)"
    )
    filter_text: Optional[str] = Field(
        default=None,
        description="Optional filter for k8sgpt analysis"
    )


class AddKubeconfigContextInput(BaseModel):
    """Input schema for add_kubeconfig_context tool."""
    
    ssh_connection: str = Field(
        description="SSH connection string (e.g., 'user@hostname' or 'ansible@k8s-master.example.com')"
    )
    password: Optional[str] = Field(
        default=None,
        description="Optional SSH password (if not using key-based auth). WARNING: Use with caution."
    )
    context_name: Optional[str] = Field(
        default=None,
        description="Optional custom name for the context (defaults to hostname)"
    )
    port: int = Field(
        default=22,
        description="SSH port (default: 22)"
    )


class ListKubeconfigContextsInput(BaseModel):
    """Input schema for list_kubeconfig_contexts tool."""
    pass


class SwitchKubeconfigContextInput(BaseModel):
    """Input schema for switch_kubeconfig_context tool."""
    
    context_name: str = Field(
        description="Name of the context to switch to"
    )


class GetCurrentContextInput(BaseModel):
    """Input schema for get_current_context tool."""
    pass


class SearchDeploymentRepoInput(BaseModel):
    """Input schema for search_deployment_repo tool."""
    
    query: str = Field(
        description="Search query (e.g., 'ansible playbook', 'helm chart', 'deployment config')"
    )
    path_filter: Optional[str] = Field(
        default=None,
        description="Optional path filter (e.g., 'ansible/', 'helm/', 'infra/')"
    )
    file_extension: Optional[str] = Field(
        default=None,
        description="Optional file extension filter (e.g., '.yaml', '.yml', '.sh')"
    )


class GetDeploymentRepoFileInput(BaseModel):
    """Input schema for get_deployment_repo_file tool."""
    
    file_path: str = Field(
        description="Relative path to file in deployment-provisioning repo"
    )


class ListDeploymentRepoPathInput(BaseModel):
    """Input schema for list_deployment_repo_path tool."""
    
    path: str = Field(
        default="",
        description="Relative path in deployment-provisioning repo (default: root)"
    )


class InvestigatePodInput(BaseModel):
    """Input schema for investigate_pod tool."""

    namespace: str = Field(
        description="Namespace containing the pod"
    )
    pod_name: str = Field(
        description="Name of the pod to investigate end-to-end"
    )
    tail: int = Field(
        default=200,
        description="Log tail lines for log steps (capped by server settings)"
    )
    use_ai: bool = Field(
        default=True,
        description="Run Gemini AI analysis on the collected kubectl data (requires GEMINI_API_KEY)"
    )


class ExecPodCommandInput(BaseModel):
    """Input schema for exec_pod_command tool."""

    namespace: str = Field(
        description="Namespace containing the pod"
    )
    pod_name: str = Field(
        description="Name of the pod to execute command in"
    )
    command: str = Field(
        description="Command to execute (e.g., 'ls -lh /var/lib/postgresql/pg_wal/')"
    )
    container: Optional[str] = Field(
        default=None,
        description="Container name for multi-container pods"
    )
    confirm: bool = Field(
        default=False,
        description="REQUIRED: Must be set to true to confirm execution. This is a write operation."
    )


class DeletePodInput(BaseModel):
    """Input schema for delete_pod tool."""

    namespace: str = Field(
        description="Namespace containing the pod"
    )
    pod_name: str = Field(
        description="Name of the pod to delete"
    )
    grace_period: int = Field(
        default=30,
        description="Grace period in seconds for pod termination (default: 30)"
    )
    confirm: bool = Field(
        default=False,
        description="REQUIRED: Must be set to true to confirm deletion. This is a destructive operation."
    )


class RolloutRestartInput(BaseModel):
    """Input schema for rollout_restart tool."""

    namespace: str = Field(
        description="Namespace containing the deployment"
    )
    deployment_name: str = Field(
        description="Name of the deployment to restart"
    )
    confirm: bool = Field(
        default=False,
        description="REQUIRED: Must be set to true to confirm restart. This will restart all pods."
    )


class ScaleDeploymentInput(BaseModel):
    """Input schema for scale_deployment tool."""

    namespace: str = Field(
        description="Namespace containing the deployment"
    )
    deployment_name: str = Field(
        description="Name of the deployment to scale"
    )
    replicas: int = Field(
        description="Target number of replicas",
        ge=0
    )
    confirm: bool = Field(
        default=False,
        description="REQUIRED: Must be set to true to confirm scaling. This will change replica count."
    )


class ApplyPatchInput(BaseModel):
    """Input schema for apply_patch tool."""

    namespace: str = Field(
        description="Namespace containing the resource"
    )
    resource_type: str = Field(
        description="Resource type (e.g., 'deployment', 'statefulset', 'pod')"
    )
    resource_name: str = Field(
        description="Name of the resource to patch"
    )
    patch: str = Field(
        description="JSON patch to apply (e.g., '{\"spec\":{\"template\":{\"spec\":{\"containers\":[{\"name\":\"app\",\"resources\":{\"limits\":{\"memory\":\"1Gi\"}}}]}}}}')"
    )
    patch_type: str = Field(
        default="strategic",
        description="Patch type: 'strategic', 'merge', or 'json' (default: strategic)"
    )
    confirm: bool = Field(
        default=False,
        description="REQUIRED: Must be set to true to confirm patch. This will modify the resource."
    )


# ── AI Analysis Tool Schemas ──────────────────────────────────────────────────

class AnalyzeErrorInput(BaseModel):
    """Input schema for analyze_error tool."""

    error_text: str = Field(
        description="Raw error text to analyze (paste from logs, terminal, CI/CD pipeline, etc.)"
    )
    tool: str = Field(
        default="kubernetes",
        description="Tool type: 'kubernetes', 'ansible', or 'helm'"
    )
    environment: str = Field(
        default="production",
        description="Environment context (e.g., 'production', 'staging', 'dev')"
    )


class GetFixCommandsInput(BaseModel):
    """Input schema for get_fix_commands tool."""

    error_text: Optional[str] = Field(
        default=None,
        description="Raw error text (will auto-classify). Provide this OR category."
    )
    category: Optional[str] = Field(
        default=None,
        description="Known error category (e.g., 'pod_crashloop', 'pod_oom', 'rbac'). Provide this OR error_text."
    )
    tool: str = Field(
        default="kubernetes",
        description="Tool type: 'kubernetes' or 'ansible'"
    )
    namespace: str = Field(
        default="<namespace>",
        description="Kubernetes namespace to substitute into commands"
    )
    resource_name: str = Field(
        default="<name>",
        description="Resource name (pod/deployment) to substitute into commands"
    )


class ListErrorCategoriesInput(BaseModel):
    """Input schema for list_error_categories tool (no parameters required)."""
    pass


class ClusterReportInput(BaseModel):
    """Input schema for cluster_report tool."""

    events_text: str = Field(
        description="Paste the output of: kubectl get events --all-namespaces --sort-by='.lastTimestamp'"
    )
    namespace: str = Field(
        default="all",
        description="Namespace context for the report (informational)"
    )


class ErrorSummaryInput(BaseModel):
    """Input schema for error_summary tool."""

    errors: List[str] = Field(
        description="List of error strings to summarize (e.g., from a CI/CD pipeline run)"
    )
    tool: str = Field(
        default="kubernetes",
        description="Tool type: 'kubernetes' or 'ansible'"
    )


class GenerateRunbookInput(BaseModel):
    """Input schema for generate_runbook tool."""

    category: Optional[str] = Field(
        default=None,
        description="Error category name (e.g., 'pod_crashloop'). Provide this OR error_text."
    )
    error_text: Optional[str] = Field(
        default=None,
        description="Raw error text (will auto-classify to a category)"
    )
    error_examples: Optional[List[str]] = Field(
        default=None,
        description="Optional list of example error strings for richer runbook context"
    )
    tool: str = Field(
        default="kubernetes",
        description="Tool type: 'kubernetes' or 'ansible'"
    )
