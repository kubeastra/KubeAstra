"""
MCP Tool: get_fix_commands
Given an error category or raw error, returns the exact kubectl/ansible commands to fix it.
"""

import json
from services.error_parser import classify_error, extract_context
from services.llm_service import llm_service

# Curated fix playbooks for common K8s/Ansible issues
FIX_PLAYBOOKS: dict[str, dict] = {
    "pod_crashloop": {
        "description": "Pod is crash-looping — container keeps restarting",
        "commands": [
            {"cmd": "kubectl logs <pod-name> -n <namespace> --previous", "description": "Get logs from the crashed container"},
            {"cmd": "kubectl describe pod <pod-name> -n <namespace>",    "description": "Check events and resource limits"},
            {"cmd": "kubectl get events -n <namespace> --sort-by='.lastTimestamp'", "description": "Recent namespace events"},
        ],
        "common_fixes": [
            "Check app logs for startup errors (missing env vars, config files, or DB connection failures)",
            "Verify liveness/readiness probe paths are correct",
            "Ensure resource limits (CPU/memory) are not too low for startup",
        ],
    },
    "pod_oom": {
        "description": "Pod killed by OOMKiller — out of memory",
        "commands": [
            {"cmd": "kubectl top pod <pod-name> -n <namespace>", "description": "Current memory usage"},
            {"cmd": "kubectl get pod <pod-name> -n <namespace> -o jsonpath='{.spec.containers[*].resources}'", "description": "Current resource limits"},
        ],
        "common_fixes": [
            "Increase memory limit in deployment spec: resources.limits.memory",
            "Profile the app for memory leaks",
            "Add memory requests to help the scheduler place the pod on a node with enough RAM",
        ],
    },
    "pod_image": {
        "description": "Container image cannot be pulled",
        "commands": [
            {"cmd": "kubectl describe pod <pod-name> -n <namespace>",         "description": "Check the exact pull error"},
            {"cmd": "kubectl get secret -n <namespace>",                       "description": "List image pull secrets"},
            {"cmd": "kubectl create secret docker-registry regcred --docker-server=<registry> --docker-username=<user> --docker-password=<REDACTED> -n <namespace>", "description": "Create image pull secret"},
        ],
        "common_fixes": [
            "Verify image tag exists in the registry",
            "Check imagePullSecrets is set on the pod/serviceaccount",
            "Ensure the registry is accessible from the cluster nodes",
        ],
    },
    "pod_pending": {
        "description": "Pod is stuck in Pending — cannot be scheduled",
        "commands": [
            {"cmd": "kubectl describe pod <pod-name> -n <namespace>",                   "description": "Check scheduling failure reason"},
            {"cmd": "kubectl get nodes -o wide",                                         "description": "List nodes and status"},
            {"cmd": "kubectl describe nodes | grep -A5 'Allocated resources'",           "description": "Node resource usage"},
            {"cmd": "kubectl get nodes -o json | jq '.items[].spec.taints'",             "description": "Check node taints"},
        ],
        "common_fixes": [
            "If 'Insufficient cpu/memory': scale up nodes or reduce resource requests",
            "If 'node(s) had taints': add tolerations to the pod spec or remove the taint",
            "If nodeSelector/affinity: ensure matching nodes exist with the required labels",
        ],
    },
    "pod_evicted": {
        "description": "Pod evicted due to node resource pressure",
        "commands": [
            {"cmd": "kubectl get nodes",                                               "description": "Check node status"},
            {"cmd": "kubectl describe node <node-name> | grep -A10 'Conditions'",     "description": "Check pressure conditions"},
            {"cmd": "kubectl get pods --all-namespaces --field-selector=status.phase=Failed", "description": "All evicted pods"},
            {"cmd": "kubectl delete pods --field-selector=status.phase=Failed -n <namespace>", "description": "WARNING: Clean up evicted pods"},
        ],
        "common_fixes": [
            "Free up disk space on nodes (clean up unused images: crictl rmi --prune)",
            "Set proper resource requests so scheduler avoids overpacking nodes",
            "Configure PodDisruptionBudgets to control eviction behavior",
        ],
    },
    "rbac": {
        "description": "RBAC permission denied",
        "commands": [
            {"cmd": "kubectl auth can-i <verb> <resource> --as=<user> -n <namespace>", "description": "Test specific permission"},
            {"cmd": "kubectl get rolebindings,clusterrolebindings -n <namespace> -o wide", "description": "List role bindings"},
            {"cmd": "kubectl describe clusterrole <role-name>",                         "description": "Inspect role permissions"},
        ],
        "common_fixes": [
            "Create or update a Role/ClusterRole with the required permissions",
            "Bind the role to the service account with a RoleBinding/ClusterRoleBinding",
            "Use 'kubectl auth can-i' to test permissions before deploying",
        ],
    },
    "networking": {
        "description": "Network connectivity failure inside the cluster",
        "commands": [
            {"cmd": "kubectl run debug --image=busybox --rm -it -- /bin/sh",        "description": "Launch debug pod"},
            {"cmd": "kubectl exec -it <pod> -- curl -v http://<service>.<namespace>.svc.cluster.local", "description": "Test service DNS"},
            {"cmd": "kubectl get svc -n <namespace>",                               "description": "List services and ports"},
            {"cmd": "kubectl get networkpolicies -n <namespace>",                    "description": "Check network policies"},
        ],
        "common_fixes": [
            "Verify service selector matches pod labels",
            "Check NetworkPolicy is not blocking the traffic",
            "Test DNS resolution: nslookup <service>.<namespace>.svc.cluster.local",
        ],
    },
    "storage": {
        "description": "Persistent volume or storage mount failure",
        "commands": [
            {"cmd": "kubectl get pvc -n <namespace>",            "description": "List PVCs and their status"},
            {"cmd": "kubectl describe pvc <pvc-name> -n <namespace>", "description": "Check binding status"},
            {"cmd": "kubectl get pv",                             "description": "List cluster-wide persistent volumes"},
            {"cmd": "kubectl get storageclass",                   "description": "List available storage classes"},
        ],
        "common_fixes": [
            "If PVC is Pending: check if a matching PV exists or if the StorageClass can provision dynamically",
            "If FailedMount: check node has access to the storage backend (NFS, EBS, etc.)",
            "Ensure storage class name in PVC matches available storage classes",
        ],
    },
    "helm_type_error": {
        "description": "Helm values have wrong types (boolean/number instead of string)",
        "commands": [
            {"cmd": "helm template <release> <chart> -f values.yaml | kubectl apply --dry-run=client -f -", "description": "Validate chart rendering locally"},
            {"cmd": "helm show values <chart>", "description": "View expected values structure"},
            {"cmd": "helm lint <chart-path> -f values.yaml", "description": "Lint chart values"},
        ],
        "common_fixes": [
            "Quote boolean values in values.yaml: change 'true' to '\"true\"'",
            "Quote numeric values used as env vars: change '8080' to '\"8080\"'",
            "In Ansible, use the Jinja2 string filter: {{ my_var | string }}",
        ],
    },
    "deployment_stuck": {
        "description": "Deployment rollout is stuck or failing",
        "commands": [
            {"cmd": "kubectl rollout status deployment/<name> -n <namespace>",     "description": "Check rollout status"},
            {"cmd": "kubectl rollout history deployment/<name> -n <namespace>",    "description": "View rollout history"},
            {"cmd": "kubectl describe deployment <name> -n <namespace>",           "description": "Check deployment events"},
            {"cmd": "kubectl rollout undo deployment/<name> -n <namespace>",       "description": "WARNING: Rollback to previous version"},
        ],
        "common_fixes": [
            "Check if new pods are crashing (kubectl logs on new ReplicaSet pods)",
            "Verify readiness probe is passing within the progressDeadlineSeconds",
            "Roll back if the new version is broken: kubectl rollout undo",
        ],
    },
    "node": {
        "description": "Node is NotReady or under pressure",
        "commands": [
            {"cmd": "kubectl describe node <node-name>",          "description": "Full node status"},
            {"cmd": "kubectl get events --field-selector=involvedObject.name=<node-name>", "description": "Node events"},
            {"cmd": "kubectl cordon <node-name>",                 "description": "Prevent new pods from scheduling on node"},
            {"cmd": "kubectl drain <node-name> --ignore-daemonsets --delete-emptydir-data", "description": "WARNING: Drain node for maintenance"},
        ],
        "common_fixes": [
            "SSH to the node and check: systemctl status kubelet, journalctl -u kubelet",
            "Free up disk space: docker system prune or crictl rmi --prune",
            "Restart kubelet if it is unresponsive: systemctl restart kubelet",
        ],
    },
}


def get_fix_commands(error_text: str = None, category: str = None, tool: str = "kubernetes",
                     namespace: str = "<namespace>", resource_name: str = "<name>") -> str:
    """
    Get exact fix commands for an error.
    Either provide raw error_text OR a known category name.
    """
    if not category and error_text:
        category = classify_error(error_text, tool)

    playbook = FIX_PLAYBOOKS.get(category)

    if not playbook and error_text:
        context = extract_context(error_text, tool)
        ai_result = llm_service.analyze(error_text, context)
        output = {
            "category":    context["category"],
            "description": ai_result.get("root_cause", ""),
            "commands":    ai_result.get("commands", []),
            "steps":       ai_result.get("steps", []),
            "common_fixes": [],
            "source":      "ai_generated",
        }
        return json.dumps(output, indent=2)

    if playbook:
        commands = []
        for cmd_entry in playbook["commands"]:
            cmd = cmd_entry["cmd"].replace("<namespace>", namespace).replace("<name>", resource_name).replace("<pod-name>", resource_name)
            commands.append({"cmd": cmd, "description": cmd_entry["description"]})

        output = {
            "category":    category,
            "description": playbook["description"],
            "commands":    commands,
            "common_fixes": playbook["common_fixes"],
            "source":      "curated_playbook",
        }
        return json.dumps(output, indent=2)

    return json.dumps({
        "category": category or "unknown",
        "message":  f"No playbook found for category '{category}'. Provide error_text for AI analysis.",
        "available_categories": list(FIX_PLAYBOOKS.keys()),
    }, indent=2)


def list_categories() -> str:
    """List all supported error categories with descriptions."""
    cats = {k: v["description"] for k, v in FIX_PLAYBOOKS.items()}
    return json.dumps(cats, indent=2)
