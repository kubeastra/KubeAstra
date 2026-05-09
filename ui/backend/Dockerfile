# ── Build context: kubeastra/ ───────────────────────────────────
# Build command (run from kubeastra/):
#   docker build -f ui/backend/Dockerfile -t <registry>/kubeastra-backend:latest .

FROM python:3.11-slim

# Install kubectl + git (DEBIAN_FRONTEND suppresses debconf TTY warnings in CI)
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends curl git && \
    curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" && \
    chmod +x kubectl && mv kubectl /usr/local/bin/ && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Create UID 1000 in /etc/passwd so PyTorch's getpass.getuser() doesn't crash
# when Kubernetes runs the container with runAsUser: 1000 (a non-root security context).
RUN useradd -u 1000 -m -s /bin/bash appuser

WORKDIR /app

# ── Install Python dependencies (cached layers) ───────────────────────────────
# MCP dependencies first (larger, changes less often).
# Install CPU-only torch FIRST so sentence-transformers doesn't pull the CUDA build
# (which is 5GB+ and causes nodes to run out of ephemeral storage on pull).
COPY mcp/requirements.txt /tmp/mcp-requirements.txt
RUN pip install --no-cache-dir \
      torch>=2.0.0 --extra-index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r /tmp/mcp-requirements.txt

# Backend dependencies
COPY ui/backend/requirements.txt /tmp/backend-requirements.txt
RUN pip install --no-cache-dir -r /tmp/backend-requirements.txt

# ── Copy source code ──────────────────────────────────────────────────────────
# Copy mcp source (the backend imports from here)
COPY mcp/ /app/mcp/

# Copy backend source (includes entrypoint.sh)
COPY ui/backend/ /app/
RUN chmod +x /app/entrypoint.sh

# ── Runtime environment ───────────────────────────────────────────────────────
ENV MCP_PATH=/app/mcp
ENV PYTHONPATH=/app/mcp
# Give torch a writable cache dir — avoids getpwuid/HOME lookup issues in restricted containers
ENV TORCHINDUCTOR_CACHE_DIR=/tmp/torch_cache
ENV HOME=/home/appuser

# kubeconfig is mounted via K8s Secret at /app/kubeconfig/config
ENV KUBECONFIG=/app/kubeconfig/config

# Non-secret defaults (overridden by ConfigMap in K8s)
ENV ALLOWED_NAMESPACES=*
ENV KUBECTL_TIMEOUT_SECONDS=15
ENV MAX_LOG_TAIL_LINES=200
ENV ENABLE_RECOVERY_OPERATIONS=false

# Port 8800 — FastAPI chat backend (web UI)
# Port 8001 — HTTP MCP server (Cursor / Claude Desktop / any MCP client)
EXPOSE 8800 8001

# Starts both services; set MCP_AUTH_TOKEN env var to protect port 8001
CMD ["/app/entrypoint.sh"]
