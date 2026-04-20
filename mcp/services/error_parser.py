import re
import hashlib

# ── Kubernetes error categories ───────────────────────────────────────────────
K8S_PATTERNS = {
    "pod_crashloop": [
        r"CrashLoopBackOff",
        r"Back-off restarting failed container",
        r"container.*crash",
    ],
    "pod_oom": [
        r"OOMKilled",
        r"OutOfMemory",
        r"memory limit exceeded",
        r"Killed.*memory",
    ],
    "pod_image": [
        r"ImagePullBackOff",
        r"ErrImagePull",
        r"Failed to pull image",
        r"manifest.*not found",
        r"unauthorized.*repository",
        r"image.*not found",
    ],
    "pod_pending": [
        r"Pending.*Unschedulable",
        r"0/\d+ nodes are available",
        r"Insufficient (cpu|memory|pods)",
        r"No nodes.*match.*node ?[Ss]elector",
        r"node\(s\) didn't match",
        r"Unschedulable",
    ],
    "pod_evicted": [
        r"Evicted",
        r"The node was low on resource",
        r"eviction.*threshold",
        r"disk.*pressure",
        r"memory.*pressure",
    ],
    "pod_init_error": [
        r"Init:Error",
        r"Init:CrashLoopBackOff",
        r"init container.*failed",
        r"initContainers.*Error",
    ],
    "container_config": [
        r"invalid.*environment variable",
        r"cannot unmarshal.*into Go struct",
        r"json:.*cannot unmarshal",
        r"unknown field",
        r"spec.*invalid",
    ],
    "rbac": [
        r"forbidden.*User.*cannot",
        r"RBAC.*denied",
        r"is forbidden",
        r"does not have.*permission",
        r"Unauthorized",
        r"no.*RBAC policy",
    ],
    "networking": [
        r"connection refused",
        r"dial.*timeout",
        r"i/o timeout",
        r"no route to host",
        r"EOF.*connection",
        r"network.*unreachable",
        r"failed to connect",
        r"Service.*ClusterIP.*unreachable",
    ],
    "storage": [
        r"persistentvolumeclaim.*not found",
        r"no persistent volumes available",
        r"FailedMount",
        r"Unable to mount",
        r"volume.*not found",
        r"storageclass.*not found",
        r"ReadOnlyFileSystem",
    ],
    "resource_quota": [
        r"exceeded quota",
        r"resource quota",
        r"LimitRange",
        r"maximum allowed.*exceeded",
        r"pods.*exceeded.*quota",
    ],
    "deployment_stuck": [
        r"Deployment.*does not have minimum availability",
        r"Rollout.*stalled",
        r"ProgressDeadlineExceeded",
        r"ReplicaSet.*failed",
        r"unavailable replicas",
    ],
    "statefulset": [
        r"StatefulSet.*cannot be handled",
        r"statefulset.*invalid",
        r"StatefulSet.*failed",
        r"pod.*StatefulSet.*not ready",
    ],
    "ingress": [
        r"ingress.*not.*found",
        r"failed to create.*ingress",
        r"backend.*not.*available",
        r"TLS.*certificate.*error",
        r"ingress controller.*error",
    ],
    "api_server": [
        r"Unable to connect to the server",
        r"connection refused.*6443",
        r"the server is currently unable",
        r"etcd.*cluster.*unhealthy",
        r"apiserver.*not ready",
    ],
    "helm_error": [
        r"Failure when executing Helm command",
        r"UPGRADE FAILED",
        r"helm.*Exited [1-9]",
        r"Error:.*errors? occurred",
        r"coalesce.*Not a table",
        r"Release.*does not exist",
    ],
    "configmap_secret": [
        r"configmap.*not found",
        r"secret.*not found",
        r"failed to fetch.*configmap",
        r"referenced.*secret.*not exist",
    ],
    "node": [
        r"node.*NotReady",
        r"node.*taint",
        r"node.*cordoned",
        r"kubelet.*not.*running",
        r"node.*unreachable",
    ],
}

# ── Ansible error categories ──────────────────────────────────────────────────
ANSIBLE_PATTERNS = {
    "connection": [
        r"Failed to connect.*ssh",
        r"UNREACHABLE",
        r"Connection refused",
        r"Connection timed out",
        r"ssh.*timed out",
    ],
    "variables": [
        r"undefined variable",
        r"AnsibleUndefinedVariable",
        r"is not defined",
        r"variable.*not found",
    ],
    "syntax": [
        r"Syntax Error.*YAML",
        r"YAML.*error",
        r"parsing error",
        r"is not a valid attribute",
    ],
    "dependencies": [
        r"Failed to import",
        r"No module named",
        r"ModuleNotFoundError",
        r"could not import",
    ],
    "ssh_verification": [
        r"authenticity of host.*can't be established",
        r"Host key verification",
        r"REMOTE HOST IDENTIFICATION HAS CHANGED",
    ],
    "sudo": [
        r"privilege escalation",
        r"sudo.*password",
        r"become.*failed",
        r"Timeout.*privilege escalation",
    ],
    "permissions": [r"Permission denied", r"access denied", r"not permitted"],
    "helm_type_error": [
        r"cannot unmarshal \w+ into Go struct field",
        r"json:.*cannot unmarshal",
    ],
    "helm_install": [
        r"Failure when executing Helm command",
        r"helm.*Exited [1-9]",
    ],
    "task_failure": [r"fatal:.*FAILED", r"FAILED!", r"failed=[1-9]"],
}


def classify_error(error_text: str, tool: str) -> str:
    patterns = K8S_PATTERNS if tool == "kubernetes" else ANSIBLE_PATTERNS
    for category, regexes in patterns.items():
        for pattern in regexes:
            if re.search(pattern, error_text, re.IGNORECASE):
                return category
    return "general_failure"


def extract_context(error_text: str, tool: str) -> dict:
    ctx: dict = {
        "tool": tool,
        "category": classify_error(error_text, tool),
        "error_hash": _hash(error_text),
    }

    # Kubernetes context extraction
    pod_match = re.search(r"pod[/ ]+([a-z0-9][a-z0-9\-\.]+)", error_text, re.I)
    if pod_match:
        ctx["pod"] = pod_match.group(1)

    ns_match = re.search(r"namespace[/ ]+([a-z0-9][a-z0-9\-]+)", error_text, re.I)
    if ns_match:
        ctx["namespace"] = ns_match.group(1)

    deploy_match = re.search(r"deployment[/ ]+([a-z0-9][a-z0-9\-]+)", error_text, re.I)
    if deploy_match:
        ctx["deployment"] = deploy_match.group(1)

    node_match = re.search(r"node[/ ]+([a-z0-9][a-z0-9\-\.]+)", error_text, re.I)
    if node_match:
        ctx["node"] = node_match.group(1)

    # Ansible context extraction
    task_match = re.search(r"TASK\s+\[(.+?)\]", error_text)
    if task_match:
        ctx["task"] = task_match.group(1)

    host_match = re.search(r"fatal:\s+\[(.+?)\]", error_text)
    if host_match:
        ctx["host"] = host_match.group(1)

    helm_match = re.search(r"chart_ref:\s*(\S+)", error_text)
    if helm_match:
        ctx["helm_chart"] = helm_match.group(1)

    return ctx


def _hash(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text.strip().lower())
    normalized = re.sub(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", "<IP>", normalized)
    normalized = re.sub(r"[a-f0-9-]{36}", "<UUID>", normalized)
    normalized = re.sub(r"/[\w/.\-]+", "<PATH>", normalized)
    return hashlib.sha256(normalized.encode()).hexdigest()
