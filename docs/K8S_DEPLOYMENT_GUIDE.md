# Kubeastra — Kubernetes Deployment Guide

This guide covers everything needed to build Docker images, push them to your local Artifactory registry, and deploy the full Kubeastra stack onto a Kubernetes cluster using the Helm chart at `helm/kubeastra/`.

> **Workspace root:** All paths in this guide are relative to `kubeastra/` unless stated otherwise.

---

## Architecture deployed

```
Artifactory (your registry)
  ├── kubeastra-backend:1.0.0    ← FastAPI + mcp (one image)
  └── kubeastra-frontend:1.0.0  ← Next.js standalone

Kubernetes namespace: kubeastra
  ├── Deployment/backend         (1 pod — FastAPI on :8800 + MCP on :8001)
  ├── Deployment/frontend        (1 pod — Next.js on :3300)
  ├── Service/backend            (ClusterIP :8800 — internal, frontend proxies to it)
  ├── Service/frontend           (LoadBalancer :3300 — browser access)
  ├── Service/mcp                (ILB :8001 — IDE access for Cursor/Claude Desktop)
  ├── ConfigMap/app-config       (env vars — timeouts, namespaces, model names)
  ├── Secret/app-secrets         (GEMINI_API_KEY + kubeconfig file + MCP auth token)
  ├── ServiceAccount             (pod identity)
  ├── ClusterRole + Binding      (kubectl read/write permissions)
  ├── PersistentVolumeClaim      (SQLite chat_history.db — optional but recommended)
  └── Ingress                    (optional — disabled by default)
```

### Key features in the deployed stack

| Feature | How it works in K8s |
|---|---|
| Chat UI | Next.js frontend proxies `/api/*` → FastAPI backend |
| Gemini AI analysis | Needs `GEMINI_API_KEY` in the secrets |
| Local kubectl | kubeconfig Secret mounted at `/app/kubeconfig/config` |
| SSH remote cluster | Users provide SSH creds in the UI at runtime — no extra config needed |
| SQLite persistence | `chat_history.db` at `/app/data/` — mount a PVC to survive pod restarts |
| HTTP MCP server | Internal LoadBalancer on `:8001` — IDE clients connect via ILB IP |

---

## Prerequisites

| Tool | Minimum version | Check |
|---|---|---|
| Docker | 20.x+ | `docker --version` |
| kubectl | 1.26+ | `kubectl version --client` |
| Helm | 3.12+ | `helm version` |
| Access to Artifactory | — | `docker login your-artifactory.example.com` |
| Access to target K8s cluster | — | `kubectl cluster-info` |

---

## Step 1 — Build the backend Docker image

The backend image bundles both `ui/backend` and `mcp` into a single image. The build context **must be `kubeastra/`** so Docker can COPY both subdirectories.

```bash
# Navigate to the repo root (kubeastra/)
cd /path/to/kubeastra

# Build the backend image
# Replace 'your-artifactory.example.com' with your actual Artifactory hostname
docker build \
  -f ui/backend/Dockerfile \
  -t your-artifactory.example.com/kubeastra-backend:1.0.0 \
  .
```

**What this image contains:**
- Python 3.11-slim base
- `kubectl` binary (downloaded at build time)
- All Python dependencies from both `mcp/requirements.txt` and `ui/backend/requirements.txt` (including `paramiko` for SSH)
- `mcp/` source at `/app/mcp/`
- `ui/backend/` source at `/app/`
- `KUBECONFIG=/app/kubeconfig/config` (the kubeconfig is mounted as a Secret at runtime)
- SQLite database written to `/app/data/chat_history.db` at runtime

**Verify the build:**
```bash
docker run --rm your-artifactory.example.com/kubeastra-backend:1.0.0 python -c "import fastapi, paramiko; print('OK')"
```

---

## Step 2 — Build the frontend Docker image

The frontend includes a **server-side proxy** at `app/api/[...path]/route.ts`.

- the browser talks to the frontend at `/api/*`
- the Next.js server proxies those requests to the backend
- the backend target is configured at runtime with `API_BASE_URL`
- you do **not** need to rebuild the frontend image just to change the backend URL

```bash
# Navigate to the frontend directory
cd /path/to/kubeastra/ui/frontend

# Build the frontend image
docker build \
  -t your-artifactory.example.com/kubeastra-frontend:1.0.0 \
  .
```

At runtime, the frontend container reads:

```bash
API_BASE_URL=http://<backend-host>:8800
```

from its environment.

**Verify the build:**
```bash
docker run --rm -p 3300:3300 your-artifactory.example.com/kubeastra-frontend:1.0.0
# Open http://localhost:3300 — you should see the chat UI
```

---

## Step 3 — Push images to Artifactory

```bash
# Login to Artifactory (if not already logged in)
docker login your-artifactory.example.com

# Push backend image
docker push your-artifactory.example.com/kubeastra-backend:1.0.0

# Push frontend image
docker push your-artifactory.example.com/kubeastra-frontend:1.0.0
```

If your cluster needs an image pull secret to access Artifactory:

```bash
kubectl create secret docker-registry artifactory-pull-secret \
  --namespace kubeastra \
  --docker-server=your-artifactory.example.com \
  --docker-username=YOUR_USERNAME \
  --docker-password=YOUR_PASSWORD \
  --docker-email=YOUR_EMAIL
```

Then add to `values.yaml`:
```yaml
imagePullSecrets:
  - name: artifactory-pull-secret
```

---

## Step 4 — Prepare the kubeconfig Secret

The backend pod runs `kubectl` as a subprocess and needs a kubeconfig to authenticate to your cluster. You provide this via a Kubernetes Secret that is volume-mounted into the pod at `/app/kubeconfig/config`.

### Option A — Use your local kubeconfig (simplest)

```bash
# Base64-encode your kubeconfig (single line, no newlines)
cat ~/.kube/config | base64 | tr -d '\n'
```

Copy the output — you will pass it to Helm in Step 5.

### Option B — Create a dedicated service account kubeconfig (recommended for production)

This creates a minimal kubeconfig with only the permissions the app needs:

```bash
# 1. Create a service account in the TARGET cluster the app will query
kubectl create serviceaccount kubeastra-app -n kube-system

# 2. Create a ClusterRoleBinding for it (reuse the role from the Helm chart)
kubectl create clusterrolebinding kubeastra-app \
  --clusterrole=cluster-reader \
  --serviceaccount=kube-system:kubeastra-app

# 3. Create a long-lived token (K8s 1.24+)
kubectl create token kubeastra-app -n kube-system --duration=8760h > /tmp/kubeastra-token.txt

# 4. Build a minimal kubeconfig using the token
CLUSTER_SERVER=$(kubectl config view --minify -o jsonpath='{.clusters[0].cluster.server}')
CLUSTER_CA=$(kubectl config view --raw --minify -o jsonpath='{.clusters[0].cluster.certificate-authority-data}')
TOKEN=$(cat /tmp/kubeastra-token.txt)

cat > /tmp/kubeastra-kubeconfig.yaml << EOF
apiVersion: v1
kind: Config
clusters:
- cluster:
    server: ${CLUSTER_SERVER}
    certificate-authority-data: ${CLUSTER_CA}
  name: target-cluster
contexts:
- context:
    cluster: target-cluster
    user: kubeastra-app
  name: kubeastra
current-context: kubeastra
users:
- name: kubeastra-app
  user:
    token: ${TOKEN}
EOF

# 5. Base64-encode it
cat /tmp/kubeastra-kubeconfig.yaml | base64 | tr -d '\n'
```

---

## Step 5 — Create the namespace and install the Helm chart

```bash
# Navigate to the Helm chart directory
cd /path/to/kubeastra/helm/kubeastra

# Dry-run first to check everything renders correctly
helm install kubeastra . \
  --namespace kubeastra \
  --create-namespace \
  --dry-run \
  --set backend.image.repository=your-artifactory.example.com/kubeastra-backend \
  --set backend.image.tag=1.0.0 \
  --set frontend.image.repository=your-artifactory.example.com/kubeastra-frontend \
  --set frontend.image.tag=1.0.0 \
  --set secrets.geminiApiKey="YOUR_GEMINI_API_KEY" \
  --set secrets.kubeconfig="PASTE_BASE64_KUBECONFIG_HERE"
```

If the dry-run output looks correct, install for real:

```bash
helm install kubeastra . \
  --namespace kubeastra \
  --create-namespace \
  --set backend.image.repository=your-artifactory.example.com/kubeastra-backend \
  --set backend.image.tag=1.0.0 \
  --set frontend.image.repository=your-artifactory.example.com/kubeastra-frontend \
  --set frontend.image.tag=1.0.0 \
  --set secrets.geminiApiKey="YOUR_GEMINI_API_KEY" \
  --set secrets.kubeconfig="PASTE_BASE64_KUBECONFIG_HERE"
```

### Alternative — use a values override file (recommended, keeps secrets out of shell history)

Create `my-values.yaml` (do not commit this file):

```yaml
backend:
  image:
    repository: your-artifactory.example.com/kubeastra-backend
    tag: "1.0.0"

frontend:
  image:
    repository: your-artifactory.example.com/kubeastra-frontend
    tag: "1.0.0"

secrets:
  geminiApiKey: "YOUR_GEMINI_API_KEY"
  kubeconfig: "PASTE_BASE64_KUBECONFIG_HERE"
```

Then install with:

```bash
helm install kubeastra . \
  --namespace kubeastra \
  -f my-values.yaml
```

---

## Step 6 — Verify the deployment

```bash
# Check all pods are Running
kubectl get pods -n kubeastra

# Expected output:
# NAME                                         READY   STATUS    RESTARTS   AGE
# kubeastra-backend-...  1/1     Running   0          60s
# kubeastra-frontend-... 1/1     Running   0          60s

# Check services
kubectl get services -n kubeastra

# Check backend logs
kubectl logs -n kubeastra deployment/kubeastra-backend --follow

# Verify kubectl works inside the backend pod
kubectl exec -n kubeastra \
  deployment/kubeastra-backend \
  -- kubectl get nodes
```

---

## Step 7 — Access the UI

### Option A — Port-forward (quickest, no Ingress needed)

Open two terminal windows:

```bash
# Terminal 1 — backend
kubectl port-forward -n kubeastra service/kubeastra-backend 8800:8800

# Terminal 2 — frontend
kubectl port-forward -n kubeastra service/kubeastra-frontend 3300:3300
```

Open `http://localhost:3300` in your browser.

The browser talks to the frontend on port `3300`, and the frontend server proxies `/api/*` to the backend on port `8800`.

### Option B — Ingress (for team access)

Enable Ingress in your values and upgrade:

```bash
helm upgrade kubeastra . \
  --namespace kubeastra \
  -f my-values.yaml \
  --set ingress.enabled=true \
  --set ingress.frontendHost=kubeastra.your-company.com \
  --set ingress.backendHost=kubeastra-api.your-company.com \
  --set ingress.className=nginx
```

> **Runtime config note:** With the new proxy model, switching backend targets is usually a frontend runtime env change (`API_BASE_URL`), not a frontend rebuild.

---

## Connecting IDEs via MCP (Cursor, Claude Desktop, VS Code)

The MCP service is exposed as an Internal Load Balancer by default. After deploying, get the ILB IP:

```bash
kubectl get service kubeastra-mcp -n kubeastra
# NAME             TYPE           CLUSTER-IP     EXTERNAL-IP    PORT(S)
# kubeastra-mcp    LoadBalancer   10.x.x.x       10.y.y.y       8001:xxxxx/TCP
```

Use the `EXTERNAL-IP` in your IDE's MCP config.

### Cursor / Claude Desktop / VS Code — `.mcp.json`

```json
{
  "mcpServers": {
    "kubeastra": {
      "type": "http",
      "url": "http://<EXTERNAL-IP>:8001/mcp/",
      "headers": {
        "Authorization": "Bearer <your-mcp-auth-token>"
      }
    }
  }
}
```

Replace `<EXTERNAL-IP>` with the ILB IP from `kubectl get service` above, and `<your-mcp-auth-token>` with the value you set in `secrets.mcpAuthToken`.

### Cloud provider ILB annotations

The default annotation targets GKE. Override for your provider in `my-values.yaml`:

```yaml
# AWS
mcp:
  service:
    annotations:
      service.beta.kubernetes.io/aws-load-balancer-internal: "true"

# Azure
mcp:
  service:
    annotations:
      service.beta.kubernetes.io/azure-load-balancer-internal: "true"

# GKE (default)
mcp:
  service:
    annotations:
      networking.gke.io/load-balancer-type: "Internal"
```

### Securing MCP access

Set `secrets.mcpAuthToken` during install so all MCP requests require a bearer token:

```bash
helm install kubeastra . \
  --namespace kubeastra \
  -f my-values.yaml \
  --set secrets.mcpAuthToken="your-secure-token-here"
```

Without this token, the MCP server accepts unauthenticated requests.

---

## Step 8 — Upgrading after a code change

```bash
# Run from kubeastra/
# 1. Rebuild and push images with a new tag
docker build -f ui/backend/Dockerfile -t your-artifactory.example.com/kubeastra-backend:1.0.1 .
docker push your-artifactory.example.com/kubeastra-backend:1.0.1

# 2. Upgrade the Helm release with the new image tag
cd helm/kubeastra
helm upgrade kubeastra . \
  --namespace kubeastra \
  -f my-values.yaml \
  --set backend.image.tag=1.0.1
```

---

## Local development — start.sh

For local development, use the provided `start.sh` script (no Docker or Helm needed):

```bash
cd kubeastra/ui
./start.sh
```

This starts:
- **Backend** — `uvicorn main:app --port 8800` (with `MCP_PATH` and `PYTHONPATH` set to `mcp/`)
- **Frontend** — `npm run dev` on port 3300 with `API_BASE_URL=http://localhost:8800`

Press `Ctrl+C` to stop both.

> **Note:** The backend writes `chat_history.db` to `ui/backend/` locally. This file is git-ignored.

---

## SQLite persistence in Kubernetes

The backend automatically creates `chat_history.db` at startup (path: `/app/data/chat_history.db` inside the container). Without a persistent volume this file is lost when the pod restarts — all chat histories are cleared.

**To persist chat history across pod restarts**, add a PVC to your `my-values.yaml`:

```yaml
backend:
  persistence:
    enabled: true
    storageClass: "standard"   # use your cluster's storage class
    size: 1Gi
    mountPath: /app/data
```

If `persistence.enabled` is false (default), the backend still works — users just lose history on pod restart.

---

## Complete file structure

```
kubeastra/
├── docs/
│   └── K8S_DEPLOYMENT_GUIDE.md         ← This file
├── ui/
│   ├── start.sh                         ← Local dev launcher (backend + frontend)
│   ├── backend/
│   │   ├── Dockerfile                   ← Bundles mcp + backend
│   │   ├── main.py                      ← FastAPI app + SQLite init
│   │   ├── routers/
│   │   │   ├── chat.py                  ← Gemini router + tool dispatcher + SSH
│   │   │   └── sessions.py              ← Chat history + SSH target REST API
│   │   └── db.py                        ← SQLite schema + CRUD
│   └── frontend/
│       ├── Dockerfile                   ← Next.js standalone build
│       ├── next.config.ts               ← output: 'standalone'
│       └── app/api/[...path]/route.ts   ← Server-side proxy → backend
├── mcp/
│   ├── k8s/
│   │   ├── kubectl_runner.py            ← Local kubectl (kubeconfig)
│   │   └── ssh_runner.py                ← Remote kubectl via SSH (paramiko)
│   ├── ai_tools/                        ← Gemini-powered tools
│   └── services/llm_service.py          ← Gemini API client + SYSTEM_PROMPT
└── helm/
    └── kubeastra/
        ├── Chart.yaml
        ├── values.yaml                  ← All configurable parameters
        └── templates/
            ├── _helpers.tpl             ← Name helpers, label helpers
            ├── configmap.yaml           ← Non-secret env vars
            ├── secret.yaml              ← GEMINI_API_KEY + kubeconfig
            ├── serviceaccount.yaml      ← Pod identity
            ├── rbac.yaml                ← ClusterRole + ClusterRoleBinding
            ├── backend-deployment.yaml  ← Mounts kubeconfig Secret, reads ConfigMap
            ├── backend-service.yaml     ← ClusterIP :8800
            ├── frontend-deployment.yaml ← Passes API_BASE_URL at runtime
            ├── frontend-service.yaml    ← ClusterIP :3300
            └── ingress.yaml             ← Optional, disabled by default
```

---

## Troubleshooting

### Backend pod is stuck in Init state

The init container runs `kubectl config view` to verify the kubeconfig is readable. If it fails:

```bash
# Check init container logs
kubectl logs -n kubeastra \
  $(kubectl get pod -n kubeastra -l app.kubernetes.io/component=backend -o name) \
  -c kubeconfig-check

# Verify the Secret was created with the kubeconfig key
kubectl get secret -n kubeastra kubeastra-secrets -o yaml
```

Common causes:
- Base64 encoding has newlines — re-encode with `| tr -d '\n'`
- kubeconfig references a cluster unreachable from inside the pod (e.g., `localhost`)
- Kubeconfig uses exec-based auth (GKE workload identity) that doesn't work in a container — use token-based auth (Option B in Step 4)

### Backend pod starts but kubectl commands fail

```bash
# Shell into the backend pod
kubectl exec -it -n kubeastra \
  deployment/kubeastra-backend \
  -- bash

# Inside the pod:
echo $KUBECONFIG          # Should be /app/kubeconfig/config
cat $KUBECONFIG           # Should show your kubeconfig YAML
kubectl get nodes         # Test connectivity
kubectl get pods -A       # Test namespace access
```

### Gemini AI features not working (kubectl tools still work)

```bash
# Check the secret is set
kubectl exec -n kubeastra \
  deployment/kubeastra-backend \
  -- env | grep GEMINI

# If empty, update the secret
kubectl patch secret kubeastra-secrets \
  -n kubeastra \
  --type='json' \
  -p='[{"op":"replace","path":"/data/GEMINI_API_KEY","value":"'$(echo -n "YOUR_KEY" | base64)'"}]'

# Restart the backend pod to pick up the new secret
kubectl rollout restart deployment/kubeastra-backend -n kubeastra
```

### SSH cluster connection fails

SSH remote cluster support uses `paramiko` (already in `backend/requirements.txt`). No extra K8s config is needed — users provide hostname/username/password through the UI at runtime. If SSH fails:

```bash
# Verify paramiko is installed inside the backend pod
kubectl exec -n kubeastra \
  deployment/kubeastra-backend \
  -- python -c "import paramiko; print(paramiko.__version__)"

# Check backend logs for SSH errors
kubectl logs -n kubeastra deployment/kubeastra-backend | grep -i ssh
```

Common causes:
- Target host not reachable from inside the K8s cluster (firewall/VPN rules)
- Wrong SSH port (default 22)
- Username has no `kubectl` access on the remote node

---

### Frontend shows "Failed to fetch" or blank results

This means the frontend server cannot reach the backend target or the browser cannot reach the frontend.

```bash
# Check the runtime backend target inside the frontend container
kubectl exec -n kubeastra \
  deployment/kubeastra-frontend \
  -- env | grep API_BASE_URL

# Check frontend logs
kubectl logs -n kubeastra deployment/kubeastra-frontend --follow
```

Common causes:
- `API_BASE_URL` points to the wrong backend service or host
- backend Service name or port is wrong
- frontend is reachable but backend pod is failing readiness/liveness
- Ingress or port-forward only exposes frontend, while backend is unavailable behind the proxy

### Checking the Helm release status

```bash
helm status kubeastra -n kubeastra
helm get values kubeastra -n kubeastra
```

### Uninstalling

```bash
helm uninstall kubeastra -n kubeastra
kubectl delete namespace kubeastra
```

---

## Optional: Enable Weaviate RAG

Weaviate is not included in the Helm chart by default (it requires persistent storage and a separate deployment). If you want RAG (similar past errors in `analyze_error`):

```bash
# Apply a minimal Weaviate deployment
kubectl apply -n kubeastra -f - <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: weaviate
  namespace: kubeastra
spec:
  replicas: 1
  selector:
    matchLabels:
      app: weaviate
  template:
    metadata:
      labels:
        app: weaviate
    spec:
      containers:
        - name: weaviate
          image: semitechnologies/weaviate:1.28.4
          ports:
            - containerPort: 8080
          env:
            - name: QUERY_DEFAULTS_LIMIT
              value: "20"
            - name: AUTHENTICATION_ANONYMOUS_ACCESS_ENABLED
              value: "true"
            - name: DEFAULT_VECTORIZER_MODULE
              value: "none"
          resources:
            requests:
              memory: "512Mi"
            limits:
              memory: "1Gi"
---
apiVersion: v1
kind: Service
metadata:
  name: weaviate
  namespace: kubeastra
spec:
  selector:
    app: weaviate
  ports:
    - port: 8080
      targetPort: 8080
EOF

# Then upgrade Helm to point the backend at in-cluster Weaviate
helm upgrade kubeastra helm/kubeastra \
  --namespace kubeastra \
  -f my-values.yaml \
  --set backend.config.weaviateUrl=http://weaviate:8080
```
