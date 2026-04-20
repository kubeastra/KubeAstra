"""High-level kubectl wrappers for investigation operations."""

import logging
import subprocess
import re
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from k8s.kubectl_runner import get_runner, KubectlError
from k8s.parsers import (
    parse_deployment,
    parse_endpoints,
    parse_events,
    parse_pod_describe_highlights,
    parse_pod_list,
    parse_service,
    truncate_logs,
)
from k8s.validators import (
    validate_environment_hint,
    validate_label_selector,
    validate_namespace,
    validate_resource_name,
    validate_tail_lines,
    get_allowed_namespaces,
)
from config.settings import settings

logger = logging.getLogger(__name__)

_ai_service_available = True
try:
    from services.llm_service import llm_service as _llm_service
except ImportError:
    _ai_service_available = False
    _llm_service = None

# Store deployment repo in workspace to avoid permission issues
DEPLOYMENT_REPO_PATH = Path(__file__).parent.parent / ".deployment-provisioning-cache"


def find_workload(
    name: str,
    environment: Optional[str] = None
) -> Dict[str, Any]:
    """
    Search for matching workloads across allowed namespaces.

    When ALLOWED_NAMESPACES=* (wildcard), uses a single --all-namespaces
    kubectl call per resource type (3 calls total) instead of N calls per
    namespace, which avoids multi-minute hangs on large clusters.

    Args:
        name: Workload name or partial name to search for
        environment: Optional environment hint (prod, staging, dev)

    Returns:
        Dict with matches grouped by namespace and resource type
    """
    validate_resource_name(name, "workload")
    environment = validate_environment_hint(environment)

    allowed_namespaces = get_allowed_namespaces()
    wildcard = "*" in allowed_namespaces

    matches: Dict[str, Any] = {
        "query": name,
        "environment_hint": environment,
        "deployments": [],
        "pods": [],
        "services": [],
    }

    def _search_all_namespaces(resource: str) -> list:
        """Single --all-namespaces call — fast even on large clusters."""
        try:
            result = get_runner().run_json(["get", resource, "--all-namespaces", "-o", "json"])
            return result.get("items", [])
        except Exception as e:
            logger.warning(f"Error fetching {resource} across all namespaces: {e}")
            return []

    def _search_per_namespace(resource: str, namespaces: list) -> list:
        """Per-namespace calls — used when a specific namespace list is given."""
        items = []
        for ns in namespaces:
            try:
                result = get_runner().run_json(["get", resource, "-o", "json"], namespace=ns)
                for item in result.get("items", []):
                    item["_searched_ns"] = ns
                items.extend(result.get("items", []))
            except KubectlError as e:
                logger.warning(f"Error searching {resource} in {ns}: {e}")
        return items

    if wildcard:
        all_deployments = _search_all_namespaces("deployments")
        all_pods = _search_all_namespaces("pods")
        all_services = _search_all_namespaces("services")
        namespaces_searched = "all"
    else:
        if environment:
            prioritized = [ns for ns in allowed_namespaces if environment in ns.lower()]
            rest = [ns for ns in allowed_namespaces if environment not in ns.lower()]
            search_namespaces = prioritized + rest
        else:
            search_namespaces = allowed_namespaces
        all_deployments = _search_per_namespace("deployments", search_namespaces)
        all_pods = _search_per_namespace("pods", search_namespaces)
        all_services = _search_per_namespace("services", search_namespaces)
        namespaces_searched = len(search_namespaces)

    # Filter by name match
    for item in all_deployments:
        item_name = item.get("metadata", {}).get("name", "")
        if name.lower() in item_name.lower():
            matches["deployments"].append({
                "namespace": item.get("metadata", {}).get("namespace", ""),
                "name": item_name,
                "replicas": item.get("spec", {}).get("replicas"),
                "ready": item.get("status", {}).get("readyReplicas", 0),
            })

    for item in all_pods:
        item_name = item.get("metadata", {}).get("name", "")
        if name.lower() in item_name.lower():
            matches["pods"].append({
                "namespace": item.get("metadata", {}).get("namespace", ""),
                "name": item_name,
                "phase": item.get("status", {}).get("phase", "Unknown"),
            })

    for item in all_services:
        item_name = item.get("metadata", {}).get("name", "")
        if name.lower() in item_name.lower():
            matches["services"].append({
                "namespace": item.get("metadata", {}).get("namespace", ""),
                "name": item_name,
                "type": item.get("spec", {}).get("type", ""),
            })

    matches["summary"] = {
        "total_deployments": len(matches["deployments"]),
        "total_pods": len(matches["pods"]),
        "total_services": len(matches["services"]),
        "namespaces_searched": namespaces_searched,
    }

    return matches


def get_namespaces() -> Dict[str, Any]:
    """List all namespaces in the cluster with their status."""
    result = get_runner().run_json(["get", "namespaces", "-o", "json"])
    items = result.get("items", [])
    namespaces = []
    for ns in items:
        name = ns.get("metadata", {}).get("name", "")
        phase = ns.get("status", {}).get("phase", "Unknown")
        labels = ns.get("metadata", {}).get("labels", {})
        namespaces.append({"name": name, "status": phase, "labels": labels})
    namespaces.sort(key=lambda n: n["name"])
    return {
        "namespace_count": len(namespaces),
        "namespaces": namespaces,
    }


def list_namespace_resources(namespace: str) -> Dict[str, Any]:
    """List all key resource types in a namespace in one call.

    Returns pods, services, deployments, statefulsets, daemonsets,
    configmaps, and ingresses — giving a full picture of what is
    running in the namespace without needing multiple queries.
    """
    namespace = validate_namespace(namespace)

    def _fetch(resource: str) -> List[dict]:
        try:
            data = get_runner().run_json(["get", resource, "-o", "json"], namespace=namespace)
            return data.get("items", [])
        except Exception:
            return []

    def _meta(item: dict) -> dict:
        m = item.get("metadata", {})
        return {"name": m.get("name", ""), "namespace": m.get("namespace", namespace)}

    # Pods
    raw_pods = _fetch("pods")
    pods = []
    for p in raw_pods:
        meta = _meta(p)
        status_obj = p.get("status", {})
        phase = status_obj.get("phase", "Unknown")
        conditions = {c["type"]: c["status"] for c in status_obj.get("conditions", [])}
        ready = conditions.get("Ready", "False") == "True"
        restarts = sum(
            cs.get("restartCount", 0)
            for cs in status_obj.get("containerStatuses", [])
        )
        pods.append({**meta, "status": phase, "ready": ready, "restarts": restarts})

    # Services
    raw_svcs = _fetch("services")
    services = []
    for s in raw_svcs:
        meta = _meta(s)
        spec = s.get("spec", {})
        services.append({
            **meta,
            "type": spec.get("type", "ClusterIP"),
            "cluster_ip": spec.get("clusterIP", ""),
            "ports": [
                f"{p.get('port')}/{p.get('protocol', 'TCP')}"
                for p in spec.get("ports", [])
            ],
        })

    # Deployments
    raw_deps = _fetch("deployments")
    deployments = []
    for d in raw_deps:
        meta = _meta(d)
        spec = d.get("spec", {})
        status = d.get("status", {})
        deployments.append({
            **meta,
            "replicas": spec.get("replicas", 0),
            "ready": status.get("readyReplicas", 0),
            "available": status.get("availableReplicas", 0),
        })

    # StatefulSets
    raw_sts = _fetch("statefulsets")
    statefulsets = []
    for s in raw_sts:
        meta = _meta(s)
        spec = s.get("spec", {})
        status = s.get("status", {})
        statefulsets.append({
            **meta,
            "replicas": spec.get("replicas", 0),
            "ready": status.get("readyReplicas", 0),
        })

    # DaemonSets
    raw_ds = _fetch("daemonsets")
    daemonsets = []
    for d in raw_ds:
        meta = _meta(d)
        status = d.get("status", {})
        daemonsets.append({
            **meta,
            "desired": status.get("desiredNumberScheduled", 0),
            "ready": status.get("numberReady", 0),
        })

    # ConfigMaps (exclude system ones)
    raw_cms = _fetch("configmaps")
    configmaps = [
        _meta(c)["name"] for c in raw_cms
        if _meta(c)["name"] not in ("kube-root-ca.crt",)
    ]

    # Ingresses
    raw_ing = _fetch("ingresses")
    ingresses = []
    for i in raw_ing:
        meta = _meta(i)
        rules = i.get("spec", {}).get("rules", [])
        hosts = [r.get("host", "") for r in rules if r.get("host")]
        ingresses.append({**meta, "hosts": hosts})

    return {
        "namespace": namespace,
        "pods": pods,
        "services": services,
        "deployments": deployments,
        "statefulsets": statefulsets,
        "daemonsets": daemonsets,
        "configmaps": configmaps,
        "ingresses": ingresses,
        "summary": {
            "pods": len(pods),
            "services": len(services),
            "deployments": len(deployments),
            "statefulsets": len(statefulsets),
            "daemonsets": len(daemonsets),
            "configmaps": len(configmaps),
            "ingresses": len(ingresses),
        },
    }


def list_services(namespace: str) -> Dict[str, Any]:
    """List all services in a namespace."""
    namespace = validate_namespace(namespace)
    data = get_runner().run_json(["get", "services", "-o", "json"], namespace=namespace)
    items = data.get("items", [])
    services = []
    for s in items:
        m = s.get("metadata", {})
        spec = s.get("spec", {})
        services.append({
            "name": m.get("name", ""),
            "type": spec.get("type", "ClusterIP"),
            "cluster_ip": spec.get("clusterIP", ""),
            "ports": [
                f"{p.get('port')}/{p.get('protocol', 'TCP')}"
                for p in spec.get("ports", [])
            ],
            "selector": spec.get("selector", {}),
        })
    return {"namespace": namespace, "service_count": len(services), "services": services}


def get_pods(
    namespace: str,
    label_selector: Optional[str] = None
) -> Dict[str, Any]:
    """
    List pods in namespace with optional label selector.

    Args:
        namespace: Namespace to query. Pass "*" or "all" to list pods across
                   all namespaces (equivalent to kubectl get pods -A).
        label_selector: Optional label selector (e.g., "app=myapp")

    Returns:
        Dict with pod summaries
    """
    all_namespaces = namespace in ("*", "all", "all-namespaces")

    if not all_namespaces:
        namespace = validate_namespace(namespace)

    args = ["get", "pods", "-o", "json"]

    if all_namespaces:
        args.append("--all-namespaces")

    if label_selector:
        label_selector = validate_label_selector(label_selector)
        args.extend(["-l", label_selector])

    result = get_runner().run_json(args, namespace=None if all_namespaces else namespace)
    pods = parse_pod_list(result)

    return {
        "namespace": "*" if all_namespaces else namespace,
        "label_selector": label_selector,
        "pod_count": len(pods),
        "pods": pods,
    }


def describe_pod(namespace: str, pod_name: str) -> Dict[str, Any]:
    """
    Get detailed pod description with parsed highlights.
    
    Args:
        namespace: Namespace containing the pod
        pod_name: Name of the pod
        
    Returns:
        Dict with pod description and highlights
    """
    namespace = validate_namespace(namespace)
    pod_name = validate_resource_name(pod_name, "pod")
    
    # Get describe output
    result = get_runner().run(
        ["describe", "pod", pod_name],
        namespace=namespace
    )
    result.raise_for_status()
    
    # Parse highlights
    highlights = parse_pod_describe_highlights(result.stdout)
    
    return {
        "namespace": namespace,
        "pod_name": pod_name,
        "highlights": highlights,
        "raw_output": result.stdout,
        "truncated": result.truncated,
    }


def get_pod_logs(
    namespace: str,
    pod_name: str,
    previous: bool = False,
    tail: int = 200,
    container: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get pod logs with size limits.
    
    Args:
        namespace: Namespace containing the pod
        pod_name: Name of the pod
        previous: Get logs from previous container instance
        tail: Number of lines to retrieve (capped by settings)
        container: Optional container name for multi-container pods
        
    Returns:
        Dict with log content
    """
    namespace = validate_namespace(namespace)
    pod_name = validate_resource_name(pod_name, "pod")
    tail = validate_tail_lines(tail)
    
    args = ["logs", pod_name, f"--tail={tail}"]
    
    if previous:
        args.append("--previous")
    
    if container:
        # VALIDATION: Container names can have dots and underscores
        if not container or len(container) > 253:
            raise ValueError(f"Invalid container name: {container}")
        # Allow more characters for container names (dots, underscores)
        if not all(c.isalnum() or c in '-_.' for c in container):
            raise ValueError(
                f"Invalid container name: '{container}'. "
                "Container names must contain only alphanumeric characters, hyphens, dots, and underscores."
            )
        args.extend(["-c", container])
    
    try:
        result = get_runner().run(args, namespace=namespace)
        
        # Additional truncation if needed
        log_text, was_truncated = truncate_logs(
            result.stdout,
            settings.max_log_tail_lines
        )
        
        return {
            "namespace": namespace,
            "pod_name": pod_name,
            "container": container,
            "previous": previous,
            "tail_lines": tail,
            "logs": log_text,
            "truncated": was_truncated or result.truncated,
            "success": True,
        }
        
    except KubectlError as e:
        return {
            "namespace": namespace,
            "pod_name": pod_name,
            "container": container,
            "previous": previous,
            "tail_lines": tail,
            "logs": "",
            "error": str(e),
            "stderr": e.stderr,
            "success": False,
        }


def _classify_pod_failure_mode(pod_item: Dict[str, Any]) -> Dict[str, Any]:
    """
    Classify pod state for automated investigation playbooks.

    Returns mode: Pending | ImagePullBackOff | CrashLoopBackOff | other

    Container waiting reasons are checked before phase=Pending so that
    ImagePullBackOff/CrashLoopBackOff on a not-yet-Running pod match the right playbook.
    """
    status = pod_item.get("status", {})
    phase = status.get("phase", "")

    image_reasons = ("ImagePullBackOff", "ErrImagePull", "InvalidImageName")
    crash_reasons = ("CrashLoopBackOff",)

    for cs in status.get("initContainerStatuses", []) or []:
        waiting = cs.get("state", {}).get("waiting", {})
        r = waiting.get("reason", "")
        if r in image_reasons:
            return {
                "mode": "ImagePullBackOff",
                "container": cs.get("name"),
                "reason": r,
                "message": waiting.get("message", ""),
            }
        if r in crash_reasons:
            return {
                "mode": "CrashLoopBackOff",
                "container": cs.get("name"),
                "reason": r,
                "message": waiting.get("message", ""),
            }

    for cs in status.get("containerStatuses", []) or []:
        waiting = cs.get("state", {}).get("waiting", {})
        r = waiting.get("reason", "")
        if r in image_reasons:
            return {
                "mode": "ImagePullBackOff",
                "container": cs.get("name"),
                "reason": r,
                "message": waiting.get("message", ""),
            }
        if r in crash_reasons:
            return {
                "mode": "CrashLoopBackOff",
                "container": cs.get("name"),
                "reason": r,
                "message": waiting.get("message", ""),
            }

    if phase == "Pending":
        return {
            "mode": "Pending",
            "container": None,
            "reason": status.get("reason", ""),
            "message": status.get("message", ""),
        }

    return {
        "mode": "other",
        "container": None,
        "reason": "",
        "message": "",
    }


def _pod_events_field_selector(pod_name: str) -> str:
    """Field selector for events involving this Pod (read-only)."""
    return f"involvedObject.name={pod_name},involvedObject.kind=Pod"


def investigate_pod(
    namespace: str,
    pod_name: str,
    tail: int = 200,
    use_ai: bool = True,
) -> Dict[str, Any]:
    """
    Run a read-only investigation playbook for one pod based on failure mode.

    Branches (automatic):
    - CrashLoopBackOff: describe → logs (current) → logs (previous) → events
    - ImagePullBackOff: describe → events
    - Pending: describe → events
    - other: describe → events (minimal)

    After gathering kubectl data, optionally calls Gemini AI for diagnosis and fix commands.

    Args:
        namespace: Namespace containing the pod
        pod_name: Pod name
        tail: Log tail lines (capped by settings)
        use_ai: Call Gemini AI for diagnosis after gathering kubectl data (default: True)

    Returns:
        Aggregated dict with classification, step outputs, and optional AI analysis
    """
    namespace = validate_namespace(namespace)
    pod_name = validate_resource_name(pod_name, "pod")
    tail = validate_tail_lines(tail)

    try:
        pod_json = get_runner().run_json(
            ["get", "pod", pod_name, "-o", "json"],
            namespace=namespace
        )
    except KubectlError as e:
        return {
            "success": False,
            "error": str(e),
            "stderr": e.stderr,
            "namespace": namespace,
            "pod_name": pod_name,
        }

    classification = _classify_pod_failure_mode(pod_json)
    mode = classification["mode"]

    spec_containers = pod_json.get("spec", {}).get("containers", [])
    default_container = spec_containers[0].get("name") if spec_containers else None
    log_container = classification.get("container") or default_container

    result: Dict[str, Any] = {
        "success": True,
        "namespace": namespace,
        "pod_name": pod_name,
        "classification": classification,
        "playbook": mode,
        "steps_run": [],
    }

    describe = describe_pod(namespace, pod_name)
    result["describe"] = describe
    result["steps_run"].append("describe_pod")

    event_fs = _pod_events_field_selector(pod_name)

    if mode == "CrashLoopBackOff":
        result["logs_current"] = get_pod_logs(
            namespace, pod_name, previous=False, tail=tail, container=log_container
        )
        result["steps_run"].append("get_pod_logs")
        result["logs_previous"] = get_pod_logs(
            namespace, pod_name, previous=True, tail=tail, container=log_container
        )
        result["steps_run"].append("get_pod_logs_previous")
        result["events"] = get_events(namespace, field_selector=event_fs)
        result["steps_run"].append("get_events")
    elif mode == "ImagePullBackOff":
        result["events"] = get_events(namespace, field_selector=event_fs)
        result["steps_run"].append("get_events")
    elif mode == "Pending":
        result["events"] = get_events(namespace, field_selector=event_fs)
        result["steps_run"].append("get_events")
    else:
        result["note"] = (
            "Pod did not match Pending, ImagePullBackOff, or CrashLoopBackOff. "
            "Included describe and filtered events only."
        )
        result["events"] = get_events(namespace, field_selector=event_fs)
        result["steps_run"].append("get_events")

    # ── Gemini AI analysis (optional) ──────────────────────────────────────────
    if use_ai and _ai_service_available and _llm_service:
        try:
            ai_result = _llm_service.analyze_live_investigation(pod_name, namespace, result)
            result["ai"] = ai_result
            result["steps_run"].append("ai_analysis")
        except Exception as e:
            logger.warning(f"AI analysis failed (non-fatal): {e}")
            result["ai"] = {"ai_enabled": False, "error": str(e)}
    elif use_ai:
        result["ai"] = {"ai_enabled": False, "message": "AI service not available"}

    return result


def get_events(namespace: str, field_selector: Optional[str] = None) -> Dict[str, Any]:
    """
    Get recent events in a namespace, or across all namespaces.

    Args:
        namespace: Namespace to query. Pass "*" or "all" to search all namespaces
                   (equivalent to kubectl get events -A).
        field_selector: Optional field selector for filtering (e.g. "type=Warning")

    Returns:
        Dict with parsed events (limited to most recent 50)
    """
    all_namespaces = namespace in ("*", "all", "all-namespaces")

    if not all_namespaces:
        namespace = validate_namespace(namespace)

    args = ["get", "events", "-o", "json", "--sort-by=.lastTimestamp"]

    if all_namespaces:
        args.append("--all-namespaces")

    if field_selector:
        if not all(c.isalnum() or c in '-_.,=!' for c in field_selector):
            raise ValueError(
                f"Invalid field selector: '{field_selector}'. "
                "Field selectors must contain only alphanumeric characters and -_.=!,"
            )
        if any(dangerous in field_selector for dangerous in [";", "&", "|", "`", "$", "(", ")"]):
            raise ValueError("Field selector contains forbidden characters")
        args.extend(["--field-selector", field_selector])

    try:
        # When using --all-namespaces don't pass a -n flag
        result = get_runner().run_json(args, namespace=None if all_namespaces else namespace)
        events = parse_events(result)
    except Exception as e:
        logger.error(f"Failed to get events: {e}")
        return {
            "namespace": "*" if all_namespaces else namespace,
            "event_count": 0,
            "events": [],
            "error": str(e),
            "truncated": False,
        }

    # SAFETY: Limit number of events returned to prevent huge outputs
    max_events = 50
    original_count = len(events)
    if len(events) > max_events:
        events = events[:max_events]
        truncated = True
    else:
        truncated = False

    return {
        "namespace": "*" if all_namespaces else namespace,
        "event_count": len(events),
        "original_count": original_count,
        "events": events,
        "truncated": truncated,
    }


def get_deployment(namespace: str, deployment_name: str) -> Dict[str, Any]:
    """
    Get deployment status and details.
    
    Args:
        namespace: Namespace containing the deployment
        deployment_name: Name of the deployment
        
    Returns:
        Dict with deployment details
    """
    namespace = validate_namespace(namespace)
    deployment_name = validate_resource_name(deployment_name, "deployment")
    
    result = get_runner().run_json(
        ["get", "deployment", deployment_name, "-o", "json"],
        namespace=namespace
    )
    
    deployment = parse_deployment(result)
    
    return deployment


def get_service(namespace: str, service_name: str) -> Dict[str, Any]:
    """
    Get service details.
    
    Args:
        namespace: Namespace containing the service
        service_name: Name of the service
        
    Returns:
        Dict with service details
    """
    namespace = validate_namespace(namespace)
    service_name = validate_resource_name(service_name, "service")
    
    result = get_runner().run_json(
        ["get", "service", service_name, "-o", "json"],
        namespace=namespace
    )
    
    service = parse_service(result)
    
    return service


def get_endpoints(namespace: str, service_name: str) -> Dict[str, Any]:
    """
    Get service endpoints to check if pods are backing the service.
    
    Args:
        namespace: Namespace containing the service
        service_name: Name of the service
        
    Returns:
        Dict with endpoint details
    """
    namespace = validate_namespace(namespace)
    service_name = validate_resource_name(service_name, "service")
    
    result = get_runner().run_json(
        ["get", "endpoints", service_name, "-o", "json"],
        namespace=namespace
    )
    
    endpoints = parse_endpoints(result)
    
    return endpoints


def get_rollout_status(namespace: str, deployment_name: str) -> Dict[str, Any]:
    """
    Get rollout status for deployment.
    
    Args:
        namespace: Namespace containing the deployment
        deployment_name: Name of the deployment
        
    Returns:
        Dict with rollout status
    """
    namespace = validate_namespace(namespace)
    deployment_name = validate_resource_name(deployment_name, "deployment")
    
    result = get_runner().run(
        ["rollout", "status", f"deployment/{deployment_name}"],
        namespace=namespace
    )
    
    return {
        "namespace": namespace,
        "deployment_name": deployment_name,
        "status": result.stdout.strip(),
        "success": result.success,
    }


def k8sgpt_analyze(
    namespace: Optional[str] = None,
    filter_text: Optional[str] = None
) -> Dict[str, Any]:
    """
    Run k8sgpt analysis if available.
    
    Args:
        namespace: Optional namespace to analyze
        filter_text: Optional filter for analysis
        
    Returns:
        Dict with k8sgpt output or error message
    """
    if not settings.enable_k8sgpt:
        return {
            "enabled": False,
            "message": "k8sgpt is not enabled. Set ENABLE_K8SGPT=true in .env",
        }
    
    if namespace:
        namespace = validate_namespace(namespace)
    
    # Build k8sgpt command - use array for safety
    cmd = ["k8sgpt", "analyze", "--output", "json"]
    
    if namespace:
        cmd.extend(["--namespace", namespace])
    
    if filter_text:
        # SECURITY: Strict validation for filter text
        if not filter_text.replace("-", "").replace("_", "").isalnum():
            raise ValueError(
                f"Invalid filter text: '{filter_text}'. "
                "Filter must contain only alphanumeric characters, hyphens, and underscores."
            )
        cmd.extend(["--filter", filter_text])
    
    try:
        # SAFETY: Run k8sgpt with proper subprocess safety
        import subprocess
        import json
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=settings.kubectl_timeout_seconds,
            check=False,
            # SECURITY: Never use shell=True
            shell=False
        )
        
        # SAFETY: Truncate output if too large
        stdout = result.stdout
        stderr = result.stderr
        truncated = False
        
        if len(stdout) > settings.max_output_bytes:
            stdout = stdout[:settings.max_output_bytes]
            truncated = True
        
        if len(stderr) > settings.max_output_bytes:
            stderr = stderr[:settings.max_output_bytes]
        
        if result.returncode == 0:
            try:
                analysis = json.loads(stdout)
                return {
                    "enabled": True,
                    "success": True,
                    "namespace": namespace,
                    "analysis": analysis,
                    "truncated": truncated,
                }
            except json.JSONDecodeError as e:
                return {
                    "enabled": True,
                    "success": False,
                    "error": f"Failed to parse k8sgpt output: {e}",
                    "raw_output": stdout[:1000] if stdout else "",
                }
        else:
            return {
                "enabled": True,
                "success": False,
                "error": stderr or "k8sgpt command failed",
            }
            
    except FileNotFoundError:
        return {
            "enabled": True,
            "success": False,
            "error": "k8sgpt CLI not found. Please install k8sgpt: https://k8sgpt.ai/",
        }
    except subprocess.TimeoutExpired:
        return {
            "enabled": True,
            "success": False,
            "error": f"k8sgpt command timed out after {settings.kubectl_timeout_seconds}s",
        }
    except Exception as e:
        logger.exception("Unexpected error running k8sgpt")
        return {
            "enabled": True,
            "success": False,
            "error": f"Unexpected error: {str(e)}",
        }


def add_kubeconfig_context(
    ssh_connection: str,
    password: Optional[str] = None,
    context_name: Optional[str] = None,
    port: int = 22
) -> Dict[str, Any]:
    """
    Add a new kubeconfig context via SSH.
    
    This function connects to a remote Kubernetes master node via SSH
    and adds its kubeconfig to the local configuration.
    
    Supports both key-based and password-based authentication.
    
    Args:
        ssh_connection: SSH connection string (e.g., 'user@hostname')
        password: Optional SSH password (if not using key-based auth)
        context_name: Optional custom context name (defaults to hostname)
        port: SSH port (default: 22)
        
    Returns:
        Dict with operation result
    """
    # Validate SSH connection format
    if not re.match(r'^[\w\-\.]+@[\w\-\.]+$', ssh_connection):
        return {
            "success": False,
            "error": "Invalid SSH connection format. Expected: user@hostname"
        }
    
    # Extract user and hostname
    username, hostname = ssh_connection.split('@')
    
    if not context_name:
        context_name = hostname.split('.')[0]
    
    # Validate context name
    if not re.match(r'^[\w\-]+$', context_name):
        return {
            "success": False,
            "error": "Invalid context name. Must contain only alphanumeric characters and hyphens."
        }
    
    try:
        import paramiko
        from io import StringIO
        
        logger.info(f"Connecting to {hostname}:{port} as {username}")
        
        # Create SSH client
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        # Connect with password or key-based auth
        try:
            if password:
                # Password-based authentication
                logger.info("Using password authentication")
                ssh.connect(
                    hostname=hostname,
                    port=port,
                    username=username,
                    password=password,
                    timeout=30,
                    look_for_keys=False,
                    allow_agent=False
                )
            else:
                # Key-based authentication (default)
                logger.info("Using key-based authentication")
                ssh.connect(
                    hostname=hostname,
                    port=port,
                    username=username,
                    timeout=30
                )
        except paramiko.AuthenticationException:
            return {
                "success": False,
                "error": "Authentication failed. Check username/password or SSH keys.",
                "ssh_connection": ssh_connection
            }
        except paramiko.SSHException as e:
            return {
                "success": False,
                "error": f"SSH connection failed: {str(e)}",
                "ssh_connection": ssh_connection
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Connection error: {str(e)}",
                "ssh_connection": ssh_connection
            }
        
        # Fetch remote kubeconfig
        logger.info("Fetching remote kubeconfig")
        stdin, stdout, stderr = ssh.exec_command("cat ~/.kube/config")
        
        remote_config = stdout.read().decode('utf-8')
        error_output = stderr.read().decode('utf-8')
        
        ssh.close()
        
        if not remote_config or "apiVersion" not in remote_config:
            return {
                "success": False,
                "error": f"Invalid kubeconfig received from remote host. Error: {error_output}",
                "ssh_connection": ssh_connection
            }
        
        # Get local kubeconfig path
        kubeconfig_path = settings.kubeconfig_path_resolved or Path.home() / ".kube" / "config"
        
        # Ensure .kube directory exists
        kubeconfig_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Create backup
        backup_path = kubeconfig_path.parent / f"config.backup.{context_name}"
        if kubeconfig_path.exists():
            import shutil
            shutil.copy(kubeconfig_path, backup_path)
            logger.info(f"Created backup at {backup_path}")
        
        # Write remote config to a temporary file
        temp_config = kubeconfig_path.parent / f"config.{context_name}.tmp"
        temp_config.write_text(remote_config)
        
        # Merge configs using kubectl
        merge_cmd = [
            "kubectl", "config", "view", "--flatten"
        ]
        
        # Set KUBECONFIG to merge both configs
        env = {
            "KUBECONFIG": f"{kubeconfig_path}:{temp_config}"
        }
        
        merge_result = subprocess.run(
            merge_cmd,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            env={**subprocess.os.environ, **env}
        )
        
        if merge_result.returncode != 0:
            temp_config.unlink()
            return {
                "success": False,
                "error": f"Failed to merge kubeconfig: {merge_result.stderr}",
                "ssh_connection": ssh_connection
            }
        
        # Write merged config
        kubeconfig_path.write_text(merge_result.stdout)
        
        # Clean up temp file
        temp_config.unlink()
        
        # Rename context if needed
        if context_name != hostname:
            rename_cmd = [
                "kubectl", "config", "rename-context",
                hostname, context_name
            ]
            subprocess.run(rename_cmd, capture_output=True, timeout=5)
        
        logger.info(f"Successfully added context: {context_name}")
        
        return {
            "success": True,
            "context_name": context_name,
            "ssh_connection": ssh_connection,
            "auth_method": "password" if password else "key",
            "message": f"Successfully added kubeconfig context '{context_name}'",
            "backup_created": str(backup_path) if backup_path.exists() else None
        }
        
    except ImportError:
        return {
            "success": False,
            "error": "paramiko library not installed. Run: pip install paramiko",
            "ssh_connection": ssh_connection
        }
    except Exception as e:
        logger.exception(f"Error adding kubeconfig context: {e}")
        return {
            "success": False,
            "error": f"Unexpected error: {str(e)}",
            "ssh_connection": ssh_connection
        }


def list_kubeconfig_contexts() -> Dict[str, Any]:
    """
    List all available kubeconfig contexts.
    
    Returns:
        Dict with list of contexts and current context
    """
    try:
        # Get all contexts
        result = subprocess.run(
            ["kubectl", "config", "get-contexts", "-o", "name"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False
        )
        
        if result.returncode != 0:
            return {
                "success": False,
                "error": f"Failed to list contexts: {result.stderr}"
            }
        
        contexts = [ctx.strip() for ctx in result.stdout.strip().split('\n') if ctx.strip()]
        
        # Get current context
        current_result = subprocess.run(
            ["kubectl", "config", "current-context"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False
        )
        
        current_context = current_result.stdout.strip() if current_result.returncode == 0 else None
        
        return {
            "success": True,
            "contexts": contexts,
            "current_context": current_context,
            "total_contexts": len(contexts)
        }
        
    except Exception as e:
        logger.exception(f"Error listing contexts: {e}")
        return {
            "success": False,
            "error": f"Unexpected error: {str(e)}"
        }


def switch_kubeconfig_context(context_name: str) -> Dict[str, Any]:
    """
    Switch to a different kubeconfig context.
    
    Args:
        context_name: Name of the context to switch to
        
    Returns:
        Dict with operation result
    """
    # Validate context name (allow alphanumeric, hyphens, dots, underscores, and @ symbol)
    if not re.match(r'^[\w\-\.@]+$', context_name):
        return {
            "success": False,
            "error": "Invalid context name format"
        }
    
    try:
        # Switch context
        result = subprocess.run(
            ["kubectl", "config", "use-context", context_name],
            capture_output=True,
            text=True,
            timeout=5,
            check=False
        )
        
        if result.returncode != 0:
            return {
                "success": False,
                "error": f"Failed to switch context: {result.stderr}",
                "context_name": context_name
            }
        
        logger.info(f"Switched to context: {context_name}")
        
        return {
            "success": True,
            "context_name": context_name,
            "message": f"Switched to context '{context_name}'"
        }
        
    except Exception as e:
        logger.exception(f"Error switching context: {e}")
        return {
            "success": False,
            "error": f"Unexpected error: {str(e)}",
            "context_name": context_name
        }


def get_current_context() -> Dict[str, Any]:
    """
    Get the current active kubeconfig context.
    
    Returns:
        Dict with current context information
    """
    try:
        # Get current context
        result = subprocess.run(
            ["kubectl", "config", "current-context"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False
        )
        
        if result.returncode != 0:
            return {
                "success": False,
                "error": "No active context or kubectl config error",
                "current_context": None
            }
        
        current_context = result.stdout.strip()
        
        # Get context details
        details_result = subprocess.run(
            ["kubectl", "config", "get-contexts", current_context],
            capture_output=True,
            text=True,
            timeout=5,
            check=False
        )
        
        # Get namespace for current context
        namespace_result = subprocess.run(
            ["kubectl", "config", "view", "--minify", "--output", "jsonpath={.contexts[0].context.namespace}"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False
        )
        
        namespace = namespace_result.stdout.strip() if namespace_result.returncode == 0 else None
        
        # Get cluster and user info
        cluster_result = subprocess.run(
            ["kubectl", "config", "view", "--minify", "--output", "jsonpath={.contexts[0].context.cluster}"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False
        )
        
        user_result = subprocess.run(
            ["kubectl", "config", "view", "--minify", "--output", "jsonpath={.contexts[0].context.user}"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False
        )
        
        cluster = cluster_result.stdout.strip() if cluster_result.returncode == 0 else None
        user = user_result.stdout.strip() if user_result.returncode == 0 else None
        
        return {
            "success": True,
            "current_context": current_context,
            "namespace": namespace or "default",
            "cluster": cluster,
            "user": user,
            "details": details_result.stdout if details_result.returncode == 0 else None
        }
        
    except Exception as e:
        logger.exception(f"Error getting current context: {e}")
        return {
            "success": False,
            "error": f"Unexpected error: {str(e)}",
            "current_context": None
        }


def _ensure_deployment_repo() -> Dict[str, Any]:
    """
    Ensure the deployment-provisioning repository is cloned and up to date.
    
    Returns:
        Dict with success status and repo path or error message
    """
    try:
        repo_url = settings.deployment_repo_url
        
        # Check if repo exists
        if DEPLOYMENT_REPO_PATH.exists():
            logger.info(f"Deployment repo exists at {DEPLOYMENT_REPO_PATH}, pulling latest changes")
            
            # Pull latest changes
            result = subprocess.run(
                ["git", "pull"],
                cwd=DEPLOYMENT_REPO_PATH,
                capture_output=True,
                text=True,
                timeout=30,
                check=False
            )
            
            if result.returncode != 0:
                logger.warning(f"Failed to pull latest changes: {result.stderr}")
                # Continue anyway - existing repo is better than nothing
            
            return {
                "success": True,
                "repo_path": str(DEPLOYMENT_REPO_PATH),
                "action": "updated"
            }
        else:
            logger.info(f"Cloning deployment repo to {DEPLOYMENT_REPO_PATH}")
            
            # Create parent directory
            DEPLOYMENT_REPO_PATH.parent.mkdir(parents=True, exist_ok=True)
            
            # Prepare git clone command
            clone_cmd = ["git", "clone"]
            
            # Add authentication if using HTTPS with token
            if repo_url.startswith("https://") and settings.github_token:
                # Insert token into URL
                repo_url_with_token = repo_url.replace(
                    "https://",
                    f"https://{settings.github_token}@"
                )
                clone_cmd.extend([repo_url_with_token, str(DEPLOYMENT_REPO_PATH)])
            else:
                # Use SSH or public HTTPS
                clone_cmd.extend([repo_url, str(DEPLOYMENT_REPO_PATH)])
            
            # Clone repository
            result = subprocess.run(
                clone_cmd,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
                env={**os.environ, "GIT_TERMINAL_PROMPT": "0"}  # Disable interactive prompts
            )
            
            if result.returncode != 0:
                error_msg = result.stderr
                
                # Provide helpful error messages
                if "Repository not found" in error_msg or "not found" in error_msg:
                    error_msg = (
                        f"Repository not found or access denied. "
                        f"Please ensure:\n"
                        f"1. The repository URL is correct: {settings.deployment_repo_url}\n"
                        f"2. You have access to the repository\n"
                        f"3. For private repos:\n"
                        f"   - SSH: Your SSH keys are configured (~/.ssh/id_rsa or ~/.ssh/id_ed25519)\n"
                        f"   - HTTPS: Set GITHUB_TOKEN in .env file\n"
                        f"Original error: {error_msg}"
                    )
                
                return {
                    "success": False,
                    "error": error_msg,
                    "repo_url": settings.deployment_repo_url
                }
            
            logger.info(f"Successfully cloned deployment repo")
            
            return {
                "success": True,
                "repo_path": str(DEPLOYMENT_REPO_PATH),
                "action": "cloned"
            }
            
    except Exception as e:
        logger.exception(f"Error ensuring deployment repo: {e}")
        return {
            "success": False,
            "error": f"Unexpected error: {str(e)}"
        }


def search_deployment_repo(
    query: str,
    path_filter: Optional[str] = None,
    file_extension: Optional[str] = None
) -> Dict[str, Any]:
    """
    Search for files and content in the deployment-provisioning repository.
    
    Args:
        query: Search query (e.g., 'ansible playbook', 'helm chart')
        path_filter: Optional path filter (e.g., 'ansible/', 'helm/')
        file_extension: Optional file extension filter (e.g., '.yaml', '.yml')
        
    Returns:
        Dict with search results
    """
    # Validate query
    if not query or len(query) > 200:
        return {
            "success": False,
            "error": "Invalid query. Must be between 1 and 200 characters."
        }
    
    # Ensure repo is available
    repo_status = _ensure_deployment_repo()
    if not repo_status["success"]:
        return repo_status
    
    try:
        # Build grep command for content search
        grep_cmd = ["grep", "-r", "-i", "-n", query, str(DEPLOYMENT_REPO_PATH)]
        
        # Add file extension filter if provided
        if file_extension:
            if not file_extension.startswith('.'):
                file_extension = f'.{file_extension}'
            grep_cmd.extend(["--include", f"*{file_extension}"])
        
        # Run grep
        result = subprocess.run(
            grep_cmd,
            capture_output=True,
            text=True,
            timeout=15,
            check=False
        )
        
        # Parse results
        matches = []
        if result.stdout:
            for line in result.stdout.split('\n')[:100]:  # Limit to 100 matches
                if ':' in line:
                    parts = line.split(':', 2)
                    if len(parts) >= 3:
                        file_path = parts[0].replace(str(DEPLOYMENT_REPO_PATH) + '/', '')
                        line_num = parts[1]
                        content = parts[2].strip()
                        
                        # Apply path filter if provided
                        if path_filter and not file_path.startswith(path_filter):
                            continue
                        
                        matches.append({
                            "file": file_path,
                            "line": line_num,
                            "content": content[:200]  # Truncate long lines
                        })
        
        # Also search for matching file names
        find_cmd = ["find", str(DEPLOYMENT_REPO_PATH), "-type", "f", "-iname", f"*{query}*"]
        
        if file_extension:
            find_cmd.extend(["-name", f"*{file_extension}"])
        
        find_result = subprocess.run(
            find_cmd,
            capture_output=True,
            text=True,
            timeout=10,
            check=False
        )
        
        matching_files = []
        if find_result.stdout:
            for file_path in find_result.stdout.split('\n')[:50]:  # Limit to 50 files
                if file_path:
                    rel_path = file_path.replace(str(DEPLOYMENT_REPO_PATH) + '/', '')
                    
                    # Apply path filter if provided
                    if path_filter and not rel_path.startswith(path_filter):
                        continue
                    
                    matching_files.append(rel_path)
        
        return {
            "success": True,
            "query": query,
            "path_filter": path_filter,
            "file_extension": file_extension,
            "content_matches": matches,
            "matching_files": matching_files,
            "total_content_matches": len(matches),
            "total_matching_files": len(matching_files),
            "repo_path": str(DEPLOYMENT_REPO_PATH)
        }
        
    except Exception as e:
        logger.exception(f"Error searching deployment repo: {e}")
        return {
            "success": False,
            "error": f"Unexpected error: {str(e)}",
            "query": query
        }


def get_deployment_repo_file(file_path: str) -> Dict[str, Any]:
    """
    Get the contents of a file from the deployment-provisioning repository.
    
    Args:
        file_path: Relative path to file in the repository
        
    Returns:
        Dict with file contents
    """
    # Validate file path (security check)
    if not file_path or '..' in file_path or file_path.startswith('/'):
        return {
            "success": False,
            "error": "Invalid file path. Must be a relative path without '..' or leading '/'."
        }
    
    # Ensure repo is available
    repo_status = _ensure_deployment_repo()
    if not repo_status["success"]:
        return repo_status
    
    try:
        full_path = DEPLOYMENT_REPO_PATH / file_path
        
        # Security check - ensure path is within repo
        if not str(full_path.resolve()).startswith(str(DEPLOYMENT_REPO_PATH.resolve())):
            return {
                "success": False,
                "error": "Invalid file path. Path must be within the repository."
            }
        
        # Check if file exists
        if not full_path.exists():
            return {
                "success": False,
                "error": f"File not found: {file_path}"
            }
        
        # Check if it's a file (not a directory)
        if not full_path.is_file():
            return {
                "success": False,
                "error": f"Path is not a file: {file_path}"
            }
        
        # Read file content
        content = full_path.read_text()
        
        # Truncate if too large
        max_size = 50000  # 50KB
        truncated = False
        if len(content) > max_size:
            content = content[:max_size]
            truncated = True
        
        return {
            "success": True,
            "file_path": file_path,
            "content": content,
            "size_bytes": full_path.stat().st_size,
            "truncated": truncated,
            "repo_path": str(DEPLOYMENT_REPO_PATH)
        }
        
    except Exception as e:
        logger.exception(f"Error reading file from deployment repo: {e}")
        return {
            "success": False,
            "error": f"Unexpected error: {str(e)}",
            "file_path": file_path
        }


def list_deployment_repo_path(path: str = "") -> Dict[str, Any]:
    """
    List files and directories in a path within the deployment-provisioning repository.
    
    Args:
        path: Relative path in the repository (default: root)
        
    Returns:
        Dict with directory listing
    """
    # Validate path (security check)
    if '..' in path or (path and path.startswith('/')):
        return {
            "success": False,
            "error": "Invalid path. Must be a relative path without '..' or leading '/'."
        }
    
    # Ensure repo is available
    repo_status = _ensure_deployment_repo()
    if not repo_status["success"]:
        return repo_status
    
    try:
        full_path = DEPLOYMENT_REPO_PATH / path if path else DEPLOYMENT_REPO_PATH
        
        # Security check - ensure path is within repo
        if not str(full_path.resolve()).startswith(str(DEPLOYMENT_REPO_PATH.resolve())):
            return {
                "success": False,
                "error": "Invalid path. Path must be within the repository."
            }
        
        # Check if path exists
        if not full_path.exists():
            return {
                "success": False,
                "error": f"Path not found: {path}"
            }
        
        # Check if it's a directory
        if not full_path.is_dir():
            return {
                "success": False,
                "error": f"Path is not a directory: {path}"
            }
        
        # List directory contents
        directories = []
        files = []
        
        for item in sorted(full_path.iterdir()):
            rel_path = str(item.relative_to(DEPLOYMENT_REPO_PATH))
            
            if item.is_dir():
                directories.append({
                    "name": item.name,
                    "path": rel_path,
                    "type": "directory"
                })
            else:
                files.append({
                    "name": item.name,
                    "path": rel_path,
                    "type": "file",
                    "size_bytes": item.stat().st_size
                })
        
        return {
            "success": True,
            "path": path or "/",
            "directories": directories,
            "files": files,
            "total_directories": len(directories),
            "total_files": len(files),
            "repo_path": str(DEPLOYMENT_REPO_PATH)
        }
        
    except Exception as e:
        logger.exception(f"Error listing deployment repo path: {e}")
        return {
            "success": False,
            "error": f"Unexpected error: {str(e)}",
            "path": path
        }


def exec_pod_command(
    namespace: str,
    pod_name: str,
    command: str,
    container: Optional[str] = None,
    confirm: bool = False
) -> Dict[str, Any]:
    """
    Execute a command in a pod container.
    
    WRITE OPERATION: Requires confirm=True to execute.
    
    Args:
        namespace: Namespace containing the pod
        pod_name: Name of the pod
        command: Command to execute
        container: Optional container name for multi-container pods
        confirm: Must be True to execute (safety guard)
        
    Returns:
        Dict with command output or error
    """
    # Check if recovery operations are enabled
    if not settings.enable_recovery_operations:
        return {
            "success": False,
            "error": "Recovery operations are disabled. Set ENABLE_RECOVERY_OPERATIONS=true in .env to enable.",
            "operation": "exec_pod_command"
        }
    
    namespace = validate_namespace(namespace)
    pod_name = validate_resource_name(pod_name, "pod")
    
    # SAFETY: Require explicit confirmation
    if not confirm:
        return {
            "success": False,
            "error": "Confirmation required. Set confirm=True to execute this command.",
            "namespace": namespace,
            "pod_name": pod_name,
            "command": command,
            "requires_approval": True,
            "operation": "exec_pod_command"
        }
    
    # SECURITY: Validate command (basic sanity check)
    if not command or len(command) > 1000:
        return {
            "success": False,
            "error": "Invalid command. Must be between 1 and 1000 characters."
        }
    
    # Build kubectl exec command
    args = ["exec", pod_name, "--"]
    
    if container:
        # Validate container name
        if not container or len(container) > 253:
            return {
                "success": False,
                "error": f"Invalid container name: {container}"
            }
        if not all(c.isalnum() or c in '-_.' for c in container):
            return {
                "success": False,
                "error": f"Invalid container name: '{container}'. Must contain only alphanumeric characters, hyphens, dots, and underscores."
            }
        args.insert(2, "-c")
        args.insert(3, container)
    
    # Add command (split by spaces for safety)
    args.extend(command.split())
    
    try:
        result = get_runner().run(args, namespace=namespace)
        
        return {
            "success": True,
            "namespace": namespace,
            "pod_name": pod_name,
            "container": container,
            "command": command,
            "output": result.stdout,
            "stderr": result.stderr if result.stderr else None,
            "truncated": result.truncated,
            "operation": "exec_pod_command"
        }
        
    except KubectlError as e:
        return {
            "success": False,
            "namespace": namespace,
            "pod_name": pod_name,
            "command": command,
            "error": str(e),
            "stderr": e.stderr,
            "operation": "exec_pod_command"
        }


def delete_pod(
    namespace: str,
    pod_name: str,
    grace_period: int = 30,
    confirm: bool = False
) -> Dict[str, Any]:
    """
    Delete a pod (forces restart for pods managed by controllers).
    
    DESTRUCTIVE OPERATION: Requires confirm=True to execute.
    
    Args:
        namespace: Namespace containing the pod
        pod_name: Name of the pod to delete
        grace_period: Grace period in seconds (default: 30)
        confirm: Must be True to execute (safety guard)
        
    Returns:
        Dict with operation result
    """
    # Check if recovery operations are enabled
    if not settings.enable_recovery_operations:
        return {
            "success": False,
            "error": "Recovery operations are disabled. Set ENABLE_RECOVERY_OPERATIONS=true in .env to enable.",
            "operation": "delete_pod"
        }
    
    namespace = validate_namespace(namespace)
    pod_name = validate_resource_name(pod_name, "pod")
    
    # SAFETY: Require explicit confirmation
    if not confirm:
        return {
            "success": False,
            "error": "Confirmation required. Set confirm=True to delete this pod.",
            "namespace": namespace,
            "pod_name": pod_name,
            "requires_approval": True,
            "operation": "delete_pod",
            "warning": "This will delete the pod. If managed by a controller (Deployment, StatefulSet), it will be recreated."
        }
    
    # Validate grace period
    if grace_period < 0 or grace_period > settings.max_grace_period_seconds:
        return {
            "success": False,
            "error": f"Grace period must be between 0 and {settings.max_grace_period_seconds} seconds."
        }
    
    # Build kubectl delete command
    args = ["delete", "pod", pod_name, f"--grace-period={grace_period}"]
    
    try:
        result = get_runner().run(args, namespace=namespace)
        
        return {
            "success": True,
            "namespace": namespace,
            "pod_name": pod_name,
            "grace_period": grace_period,
            "message": result.stdout.strip(),
            "operation": "delete_pod"
        }
        
    except KubectlError as e:
        return {
            "success": False,
            "namespace": namespace,
            "pod_name": pod_name,
            "error": str(e),
            "stderr": e.stderr,
            "operation": "delete_pod"
        }


def rollout_restart(
    namespace: str,
    deployment_name: str,
    confirm: bool = False
) -> Dict[str, Any]:
    """
    Restart a deployment (rolling restart of all pods).
    
    WRITE OPERATION: Requires confirm=True to execute.
    
    Args:
        namespace: Namespace containing the deployment
        deployment_name: Name of the deployment to restart
        confirm: Must be True to execute (safety guard)
        
    Returns:
        Dict with operation result
    """
    # Check if recovery operations are enabled
    if not settings.enable_recovery_operations:
        return {
            "success": False,
            "error": "Recovery operations are disabled. Set ENABLE_RECOVERY_OPERATIONS=true in .env to enable.",
            "operation": "rollout_restart"
        }
    
    namespace = validate_namespace(namespace)
    deployment_name = validate_resource_name(deployment_name, "deployment")
    
    # SAFETY: Require explicit confirmation
    if not confirm:
        return {
            "success": False,
            "error": "Confirmation required. Set confirm=True to restart this deployment.",
            "namespace": namespace,
            "deployment_name": deployment_name,
            "requires_approval": True,
            "operation": "rollout_restart",
            "warning": "This will perform a rolling restart of all pods in the deployment."
        }
    
    # Build kubectl rollout restart command
    args = ["rollout", "restart", f"deployment/{deployment_name}"]
    
    try:
        result = get_runner().run(args, namespace=namespace)
        
        return {
            "success": True,
            "namespace": namespace,
            "deployment_name": deployment_name,
            "message": result.stdout.strip(),
            "operation": "rollout_restart",
            "next_step": "Use get_rollout_status to monitor the restart progress"
        }
        
    except KubectlError as e:
        return {
            "success": False,
            "namespace": namespace,
            "deployment_name": deployment_name,
            "error": str(e),
            "stderr": e.stderr,
            "operation": "rollout_restart"
        }


def scale_deployment(
    namespace: str,
    deployment_name: str,
    replicas: int,
    confirm: bool = False
) -> Dict[str, Any]:
    """
    Scale a deployment to a specific number of replicas.
    
    WRITE OPERATION: Requires confirm=True to execute.
    
    Args:
        namespace: Namespace containing the deployment
        deployment_name: Name of the deployment to scale
        replicas: Target number of replicas
        confirm: Must be True to execute (safety guard)
        
    Returns:
        Dict with operation result
    """
    # Check if recovery operations are enabled
    if not settings.enable_recovery_operations:
        return {
            "success": False,
            "error": "Recovery operations are disabled. Set ENABLE_RECOVERY_OPERATIONS=true in .env to enable.",
            "operation": "scale_deployment"
        }
    
    namespace = validate_namespace(namespace)
    deployment_name = validate_resource_name(deployment_name, "deployment")
    
    # Validate replicas
    if replicas < 0 or replicas > settings.max_scale_replicas:
        return {
            "success": False,
            "error": f"Replicas must be between 0 and {settings.max_scale_replicas}."
        }
    
    # SAFETY: Require explicit confirmation
    if not confirm:
        return {
            "success": False,
            "error": "Confirmation required. Set confirm=True to scale this deployment.",
            "namespace": namespace,
            "deployment_name": deployment_name,
            "target_replicas": replicas,
            "requires_approval": True,
            "operation": "scale_deployment",
            "warning": f"This will scale the deployment to {replicas} replicas."
        }
    
    # Build kubectl scale command
    args = ["scale", f"deployment/{deployment_name}", f"--replicas={replicas}"]
    
    try:
        result = get_runner().run(args, namespace=namespace)
        
        return {
            "success": True,
            "namespace": namespace,
            "deployment_name": deployment_name,
            "target_replicas": replicas,
            "message": result.stdout.strip(),
            "operation": "scale_deployment",
            "next_step": "Use get_deployment to verify the scaling operation"
        }
        
    except KubectlError as e:
        return {
            "success": False,
            "namespace": namespace,
            "deployment_name": deployment_name,
            "target_replicas": replicas,
            "error": str(e),
            "stderr": e.stderr,
            "operation": "scale_deployment"
        }


def apply_patch(
    namespace: str,
    resource_type: str,
    resource_name: str,
    patch: str,
    patch_type: str = "strategic",
    confirm: bool = False
) -> Dict[str, Any]:
    """
    Apply a patch to a Kubernetes resource.
    
    WRITE OPERATION: Requires confirm=True to execute.
    
    Args:
        namespace: Namespace containing the resource
        resource_type: Resource type (e.g., 'deployment', 'statefulset')
        resource_name: Name of the resource
        patch: JSON patch to apply
        patch_type: Patch type ('strategic', 'merge', or 'json')
        confirm: Must be True to execute (safety guard)
        
    Returns:
        Dict with operation result
    """
    # Check if recovery operations are enabled
    if not settings.enable_recovery_operations:
        return {
            "success": False,
            "error": "Recovery operations are disabled. Set ENABLE_RECOVERY_OPERATIONS=true in .env to enable.",
            "operation": "apply_patch"
        }
    
    namespace = validate_namespace(namespace)
    resource_name = validate_resource_name(resource_name, resource_type)
    
    # Validate resource type
    allowed_resource_types = [
        "deployment", "statefulset", "daemonset", "pod",
        "service", "configmap", "secret"
    ]
    if resource_type.lower() not in allowed_resource_types:
        return {
            "success": False,
            "error": f"Invalid resource type. Allowed: {', '.join(allowed_resource_types)}"
        }
    
    # Validate patch type
    if patch_type not in ["strategic", "merge", "json"]:
        return {
            "success": False,
            "error": "Invalid patch type. Must be 'strategic', 'merge', or 'json'."
        }
    
    # Validate patch is valid JSON
    import json
    try:
        json.loads(patch)
    except json.JSONDecodeError as e:
        return {
            "success": False,
            "error": f"Invalid JSON patch: {str(e)}"
        }
    
    # SAFETY: Require explicit confirmation
    if not confirm:
        return {
            "success": False,
            "error": "Confirmation required. Set confirm=True to apply this patch.",
            "namespace": namespace,
            "resource_type": resource_type,
            "resource_name": resource_name,
            "patch": patch,
            "patch_type": patch_type,
            "requires_approval": True,
            "operation": "apply_patch",
            "warning": "This will modify the resource configuration."
        }
    
    # Build kubectl patch command
    args = [
        "patch",
        resource_type,
        resource_name,
        "--type", patch_type,
        "--patch", patch
    ]
    
    try:
        result = get_runner().run(args, namespace=namespace)
        
        return {
            "success": True,
            "namespace": namespace,
            "resource_type": resource_type,
            "resource_name": resource_name,
            "patch": patch,
            "patch_type": patch_type,
            "message": result.stdout.strip(),
            "operation": "apply_patch",
            "next_step": f"Use get_{resource_type} to verify the patch was applied"
        }
        
    except KubectlError as e:
        return {
            "success": False,
            "namespace": namespace,
            "resource_type": resource_type,
            "resource_name": resource_name,
            "patch": patch,
            "error": str(e),
            "stderr": e.stderr,
            "operation": "apply_patch"
        }


def get_resource_graph(namespace: str) -> Dict[str, Any]:
    """Build a visual resource graph for a namespace.

    Returns `nodes` and `edges` that a frontend (React Flow, D3, etc.) can
    render directly. Relationships computed:

      - Ingress   → Service   via `spec.rules[*].http.paths[*].backend.service.name`
      - Service   → Pod       via selector-vs-label matching
      - Deployment → Pod      via `spec.selector.matchLabels` vs pod labels

    Node shape:
      { "id": str, "label": str, "type": "ingress|service|deployment|pod",
        "status": "healthy|degraded|unknown", "meta": {...} }

    Edge shape:
      { "source": str, "target": str, "kind": "ingress->service|..." }
    """
    namespace = validate_namespace(namespace)
    runner = get_runner()

    def _fetch(resource: str) -> List[dict]:
        try:
            data = runner.run_json(["get", resource, "-o", "json"], namespace=namespace)
            return data.get("items", [])
        except Exception as exc:
            logger.warning(f"get_resource_graph: failed to fetch {resource} in {namespace}: {exc}")
            return []

    def _labels_match(selector: Dict[str, str], labels: Dict[str, str]) -> bool:
        if not selector:
            return False
        return all(labels.get(k) == v for k, v in selector.items())

    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []

    # ── Pods ──────────────────────────────────────────────────────────────
    raw_pods = _fetch("pods")
    pods: List[Dict[str, Any]] = []
    for p in raw_pods:
        meta = p.get("metadata", {})
        status = p.get("status", {})
        phase = status.get("phase", "Unknown")
        conditions = {c.get("type"): c.get("status") for c in status.get("conditions", [])}
        ready = conditions.get("Ready") == "True"
        cs_list = status.get("containerStatuses", []) or []
        restarts = sum(cs.get("restartCount", 0) for cs in cs_list)
        waiting_reasons = [
            (cs.get("state", {}).get("waiting") or {}).get("reason")
            for cs in cs_list
        ]
        waiting_reasons = [r for r in waiting_reasons if r]
        reason = waiting_reasons[0] if waiting_reasons else status.get("reason", "")

        health = "healthy"
        if phase in ("Failed", "Unknown"):
            health = "degraded"
        elif phase == "Pending":
            health = "degraded"
        elif not ready:
            health = "degraded"
        elif restarts > 5:
            health = "degraded"

        node_id = f"pod/{meta.get('name','')}"
        pods.append({
            "id": node_id,
            "name": meta.get("name", ""),
            "labels": meta.get("labels", {}) or {},
            "owner_refs": meta.get("ownerReferences", []) or [],
        })
        nodes.append({
            "id": node_id,
            "label": meta.get("name", ""),
            "type": "pod",
            "status": health,
            "meta": {
                "phase": phase,
                "ready": ready,
                "restarts": restarts,
                "reason": reason,
            },
        })

    # ── Services ──────────────────────────────────────────────────────────
    raw_services = _fetch("services")
    services: List[Dict[str, Any]] = []
    for s in raw_services:
        meta = s.get("metadata", {})
        spec = s.get("spec", {})
        selector = spec.get("selector") or {}
        node_id = f"service/{meta.get('name','')}"
        services.append({
            "id": node_id,
            "name": meta.get("name", ""),
            "selector": selector,
        })
        nodes.append({
            "id": node_id,
            "label": meta.get("name", ""),
            "type": "service",
            "status": "healthy" if selector else "unknown",
            "meta": {
                "cluster_ip": spec.get("clusterIP", ""),
                "service_type": spec.get("type", "ClusterIP"),
                "ports": [
                    {"port": p.get("port"), "target_port": p.get("targetPort"),
                     "protocol": p.get("protocol", "TCP")}
                    for p in spec.get("ports", [])
                ],
                "selector": selector,
            },
        })

        # Service → Pod edges (by selector match)
        if selector:
            for pod in pods:
                if _labels_match(selector, pod["labels"]):
                    edges.append({
                        "source": node_id,
                        "target": pod["id"],
                        "kind": "service->pod",
                    })

    # ── Deployments ───────────────────────────────────────────────────────
    raw_deps = _fetch("deployments")
    for d in raw_deps:
        meta = d.get("metadata", {})
        spec = d.get("spec", {})
        status_obj = d.get("status", {})
        selector = (spec.get("selector") or {}).get("matchLabels") or {}
        replicas = spec.get("replicas", 0) or 0
        ready_replicas = status_obj.get("readyReplicas", 0) or 0

        node_id = f"deployment/{meta.get('name','')}"
        health = "healthy" if replicas > 0 and ready_replicas == replicas else "degraded"
        nodes.append({
            "id": node_id,
            "label": meta.get("name", ""),
            "type": "deployment",
            "status": health,
            "meta": {
                "replicas": replicas,
                "ready_replicas": ready_replicas,
                "selector": selector,
            },
        })

        # Deployment → Pod edges (label-selector match)
        if selector:
            for pod in pods:
                if _labels_match(selector, pod["labels"]):
                    edges.append({
                        "source": node_id,
                        "target": pod["id"],
                        "kind": "deployment->pod",
                    })

    # ── Ingresses ─────────────────────────────────────────────────────────
    raw_ings = _fetch("ingresses")
    service_names = {s["name"] for s in services}
    for ing in raw_ings:
        meta = ing.get("metadata", {})
        spec = ing.get("spec", {})
        node_id = f"ingress/{meta.get('name','')}"
        rules = spec.get("rules", []) or []
        hosts = sorted({r.get("host", "") for r in rules if r.get("host")})

        nodes.append({
            "id": node_id,
            "label": meta.get("name", ""),
            "type": "ingress",
            "status": "healthy",
            "meta": {
                "hosts": hosts,
                "ingress_class": spec.get("ingressClassName", ""),
            },
        })

        for rule in rules:
            http = rule.get("http") or {}
            for path in http.get("paths", []) or []:
                backend = path.get("backend", {}) or {}
                svc = backend.get("service") or {}
                target_name = svc.get("name")
                if target_name and target_name in service_names:
                    edges.append({
                        "source": node_id,
                        "target": f"service/{target_name}",
                        "kind": "ingress->service",
                    })

    return {
        "namespace": namespace,
        "nodes": nodes,
        "edges": edges,
        "summary": {
            "ingresses": sum(1 for n in nodes if n["type"] == "ingress"),
            "services": sum(1 for n in nodes if n["type"] == "service"),
            "deployments": sum(1 for n in nodes if n["type"] == "deployment"),
            "pods": sum(1 for n in nodes if n["type"] == "pod"),
            "edges": len(edges),
        },
    }
