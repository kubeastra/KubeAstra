#!/usr/bin/env python3
"""
Seed the vector DB with known Kubernetes and Ansible errors + solutions.
Run: python data/seed.py
"""

import sys, os, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.vector_db import vector_db
from services.embeddings import embeddings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SEED_DATA = [
    # ── Kubernetes ──────────────────────────────────────────────────────────
    {
        "error_text": "Back-off restarting failed container myapp in pod myapp-abc123",
        "tool": "kubernetes", "category": "pod_crashloop", "severity": "high",
        "solution_text": "Container is crash-looping. Check logs with kubectl logs --previous to find the startup error. Common causes: missing env vars, bad config, failed DB connection.",
        "commands": "kubectl logs myapp-abc123 --previous\nkubectl describe pod myapp-abc123",
        "success_rate": 90.0,
    },
    {
        "error_text": "OOMKilled - container myapp exceeded memory limit 512Mi",
        "tool": "kubernetes", "category": "pod_oom", "severity": "high",
        "solution_text": "Container killed by OOMKiller. Increase memory limit in the deployment spec or investigate memory leak.",
        "commands": "kubectl top pod myapp-abc123\nkubectl edit deployment myapp  # increase resources.limits.memory",
        "success_rate": 95.0,
    },
    {
        "error_text": "Failed to pull image registry.example.com/myapp:v1.2.3: rpc error: code = Unknown: failed to pull",
        "tool": "kubernetes", "category": "pod_image", "severity": "high",
        "solution_text": "Image pull failed. Verify the image tag exists and the imagePullSecret is configured for the registry.",
        "commands": "kubectl get secret regcred -n default\nkubectl describe pod myapp-abc123 | grep -A5 Events",
        "success_rate": 88.0,
    },
    {
        "error_text": "0/3 nodes are available: 3 Insufficient memory. preemption: 0/3 nodes are available",
        "tool": "kubernetes", "category": "pod_pending", "severity": "medium",
        "solution_text": "No nodes have enough memory to schedule the pod. Reduce resource requests or add more nodes to the cluster.",
        "commands": "kubectl describe pod <pending-pod>\nkubectl top nodes\nkubectl get nodes -o json | jq '.items[].status.allocatable'",
        "success_rate": 85.0,
    },
    {
        "error_text": "The node was low on resource: ephemeral-storage. Threshold quantity: 10%, available: 8%.",
        "tool": "kubernetes", "category": "pod_evicted", "severity": "critical",
        "solution_text": "Node running out of disk space caused pod eviction. Free up disk space and clean up unused images.",
        "commands": "kubectl describe node <node-name> | grep -A10 Conditions\ncrictl rmi --prune\ndocker system prune -af",
        "success_rate": 92.0,
    },
    {
        "error_text": "User system:serviceaccount:myapp:default is forbidden: unable to create resource pods in API group",
        "tool": "kubernetes", "category": "rbac", "severity": "high",
        "solution_text": "Service account lacks RBAC permissions. Create a Role with the required verbs and bind it to the service account.",
        "commands": "kubectl auth can-i create pods --as=system:serviceaccount:myapp:default -n myapp\nkubectl create rolebinding myapp-pod-creator --clusterrole=edit --serviceaccount=myapp:default -n myapp",
        "success_rate": 98.0,
    },
    {
        "error_text": "dial tcp 10.96.0.1:443: connect: connection refused - unable to reach kubernetes API",
        "tool": "kubernetes", "category": "networking", "severity": "critical",
        "solution_text": "Cannot connect to Kubernetes API server. Check cluster health, apiserver pod status, and network policies.",
        "commands": "kubectl cluster-info\nkubectl get pods -n kube-system | grep apiserver\njournalctl -u kubelet -n 50",
        "success_rate": 80.0,
    },
    {
        "error_text": "persistentvolumeclaim myapp-pvc not found / FailedMount Unable to mount volumes",
        "tool": "kubernetes", "category": "storage", "severity": "high",
        "solution_text": "PVC cannot be found or mounted. Check if PVC exists and is bound to a PV. Verify storage class is available.",
        "commands": "kubectl get pvc -n myapp\nkubectl describe pvc myapp-pvc -n myapp\nkubectl get storageclass",
        "success_rate": 87.0,
    },
    {
        "error_text": "Deployment does not have minimum availability. Replicas: 3 desired | 0 available | ProgressDeadlineExceeded",
        "tool": "kubernetes", "category": "deployment_stuck", "severity": "critical",
        "solution_text": "Deployment is stuck. New pods are not becoming ready. Check pod logs and readiness probes.",
        "commands": "kubectl rollout status deployment/myapp -n myapp\nkubectl get pods -n myapp -l app=myapp\nkubectl logs -l app=myapp --tail=50 -n myapp\nkubectl rollout undo deployment/myapp -n myapp",
        "success_rate": 83.0,
    },
    {
        "error_text": "node myworker01 NotReady - kubelet stopped posting node status",
        "tool": "kubernetes", "category": "node", "severity": "critical",
        "solution_text": "Node is not ready. SSH to the node and check/restart the kubelet service.",
        "commands": "kubectl describe node myworker01\nkubectl cordon myworker01\nssh myworker01 'systemctl status kubelet && systemctl restart kubelet'",
        "success_rate": 78.0,
    },
    {
        "error_text": "Error from server: secrets myapp-secret not found",
        "tool": "kubernetes", "category": "configmap_secret", "severity": "high",
        "solution_text": "Referenced Secret does not exist in the namespace. Create it before deploying the application.",
        "commands": "kubectl get secrets -n myapp\nkubectl create secret generic myapp-secret --from-literal=DB_PASSWORD=<REDACTED> -n myapp",
        "success_rate": 99.0,
    },
    {
        "error_text": "exceeded quota: resource quota myapp-quota, requested: pods=1, used: pods=10, limited: pods=10",
        "tool": "kubernetes", "category": "resource_quota", "severity": "medium",
        "solution_text": "Namespace has hit its ResourceQuota limit. Delete unused pods or increase the quota.",
        "commands": "kubectl describe resourcequota -n myapp\nkubectl get pods -n myapp --sort-by=.metadata.creationTimestamp\nkubectl delete pods <old-pods> -n myapp",
        "success_rate": 91.0,
    },
    # ── Ansible ────────────────────────────────────────────────────────────
    {
        "error_text": "fatal: [web01]: UNREACHABLE! => Failed to connect to the host via ssh: Connection timed out",
        "tool": "ansible", "category": "connection", "severity": "high",
        "solution_text": "Cannot reach host via SSH. Check security groups allow port 22, the host is running, and the SSH key is valid.",
        "commands": "ssh -vvv -i ~/.ssh/id_rsa user@web01\nansible web01 -m ping -vvv\nssh-add ~/.ssh/id_rsa",
        "success_rate": 88.0,
    },
    {
        "error_text": "fatal: [host]: FAILED! => msg: Timeout (12s) waiting for privilege escalation prompt",
        "tool": "ansible", "category": "sudo", "severity": "medium",
        "solution_text": "Sudo password required but not provided. Use -K flag or set ansible_become_pass in inventory.",
        "commands": "ansible-playbook playbook.yml -K\nansible-playbook playbook.yml -e 'ansible_become_pass=<REDACTED>'",
        "success_rate": 97.0,
    },
    {
        "error_text": "ERROR! Syntax Error while loading YAML. found character that cannot start any token",
        "tool": "ansible", "category": "syntax", "severity": "medium",
        "solution_text": "YAML syntax error in playbook. Common causes: wrong indentation, tabs instead of spaces, special characters.",
        "commands": "yamllint playbook.yml\nansible-playbook playbook.yml --syntax-check",
        "success_rate": 100.0,
    },
    {
        "error_text": "fatal: FAILED! => msg: Failure when executing Helm command. Exited 1. json: cannot unmarshal bool into Go struct field EnvVar",
        "tool": "ansible", "category": "helm_type_error", "severity": "high",
        "solution_text": "Boolean value passed to Kubernetes env var (must be string). Quote all boolean/numeric values in Helm values.",
        "commands": "helm template release chart -f values.yaml | kubectl apply --dry-run=client -f -\nhelm lint chart -f values.yaml",
        "success_rate": 93.0,
    },
    {
        "error_text": "The authenticity of host '10.0.1.50' can't be established. RSA key fingerprint is...",
        "tool": "ansible", "category": "ssh_verification", "severity": "low",
        "solution_text": "Host not in known_hosts. Scan and add the host key, or disable host key checking for automation.",
        "commands": "ssh-keyscan -H 10.0.1.50 >> ~/.ssh/known_hosts\n# Or in ansible.cfg: host_key_checking = False",
        "success_rate": 100.0,
    },
]


def main():
    logger.info("Connecting to vector DB...")
    vector_db.connect()

    logger.info(f"Generating embeddings for {len(SEED_DATA)} entries...")
    texts = [d["error_text"] for d in SEED_DATA]
    vecs = embeddings.embed_many(texts)

    for i, (data, vec) in enumerate(zip(SEED_DATA, vecs)):
        vector_db.add(
            error_text=data["error_text"],
            tool=data["tool"],
            category=data["category"],
            solution_text=data["solution_text"],
            commands=data["commands"],
            success_rate=data["success_rate"],
            severity=data["severity"],
            vector=vec,
        )
        logger.info(f"  [{i+1}/{len(SEED_DATA)}] {data['category']}: {data['error_text'][:60]}...")

    vector_db.disconnect()
    logger.info("Seeding complete!")


if __name__ == "__main__":
    main()
