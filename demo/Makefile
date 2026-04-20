.PHONY: help up down clean status workloads cluster ui logs

CLUSTER_NAME := k8s-devops-demo
KIND_CONFIG  := kind-config.yaml
WORKLOADS    := broken-workloads/
UI_DIR       := ../ui

help:
	@echo "k8s-devops-ai-assistant — demo"
	@echo ""
	@echo "  make up         Full demo: kind cluster + broken workloads + web UI"
	@echo "  make cluster    Create the kind cluster only"
	@echo "  make workloads  Apply the broken workloads to an existing cluster"
	@echo "  make ui         Start the web UI via docker-compose"
	@echo "  make status     Show pod status in the demo namespace"
	@echo "  make logs       Tail the web UI backend logs"
	@echo "  make down       Remove broken workloads (keep cluster)"
	@echo "  make clean      Delete the kind cluster entirely"

up: cluster workloads ui
	@echo ""
	@echo "Demo ready."
	@echo "  Web UI:     http://localhost:3000"
	@echo "  Backend:    http://localhost:8000"
	@echo "  Namespace:  demo"
	@echo ""
	@echo "Try asking: 'what's broken in the demo namespace?'"

cluster:
	@command -v kind >/dev/null 2>&1 || { echo "kind is required: https://kind.sigs.k8s.io/"; exit 1; }
	@command -v kubectl >/dev/null 2>&1 || { echo "kubectl is required"; exit 1; }
	@if kind get clusters 2>/dev/null | grep -q '^$(CLUSTER_NAME)$$'; then \
		echo "Cluster '$(CLUSTER_NAME)' already exists — reusing"; \
	else \
		echo "Creating kind cluster '$(CLUSTER_NAME)'..."; \
		kind create cluster --name $(CLUSTER_NAME) --config $(KIND_CONFIG); \
	fi
	@kubectl cluster-info --context kind-$(CLUSTER_NAME)

workloads:
	@echo "Applying broken workloads to namespace 'demo'..."
	kubectl --context kind-$(CLUSTER_NAME) apply -f $(WORKLOADS)
	@echo ""
	@echo "Waiting for the broken states to manifest..."
	@sleep 20
	@$(MAKE) --no-print-directory status

ui:
	@command -v docker >/dev/null 2>&1 || { echo "docker is required"; exit 1; }
	@if [ ! -f $(UI_DIR)/backend/.env ]; then \
		if [ -f $(UI_DIR)/backend/.env.example ]; then \
			echo "Creating $(UI_DIR)/backend/.env from .env.example"; \
			cp $(UI_DIR)/backend/.env.example $(UI_DIR)/backend/.env; \
			echo ""; \
			echo "Edit $(UI_DIR)/backend/.env to set GEMINI_API_KEY (or LLM_PROVIDER=ollama) before chatting."; \
		else \
			echo "No .env or .env.example in $(UI_DIR)/backend — the UI will start but the LLM won't be configured."; \
		fi; \
	fi
	@echo "Starting web UI (backend + frontend)..."
	cd $(UI_DIR) && docker compose up -d --build

status:
	@kubectl --context kind-$(CLUSTER_NAME) get pods,pvc -n demo -o wide 2>/dev/null || \
		echo "Cluster '$(CLUSTER_NAME)' not reachable — run 'make cluster' first"

logs:
	cd $(UI_DIR) && docker compose logs -f backend

down:
	@echo "Removing demo workloads (cluster kept)..."
	-kubectl --context kind-$(CLUSTER_NAME) delete -f $(WORKLOADS) --ignore-not-found
	@echo "Stopping web UI..."
	-cd $(UI_DIR) && docker compose down

clean: down
	@echo "Deleting kind cluster '$(CLUSTER_NAME)'..."
	-kind delete cluster --name $(CLUSTER_NAME)
