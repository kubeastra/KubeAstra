.PHONY: help up down clean status workloads cluster ui logs kubeconfig

CLUSTER_NAME := kubeastra-demo
KIND_CONFIG  := kind-config.yaml
WORKLOADS    := broken-workloads/
UI_DIR       := ../ui
DEMO_KUBECONFIG := $(UI_DIR)/backend/.demo-kubeconfig
DEMO_COMPOSE_ENV := $(UI_DIR)/.env.demo
LEGACY_COMPOSE_ENV := $(UI_DIR)/.env
LEGACY_COMPOSE_ENV_BACKUP := $(UI_DIR)/.env.kubeastra-demo.bak

help:
	@echo "kubeastra — demo"
	@echo ""
	@echo "  make up         Full demo: kind cluster + broken workloads + web UI"
	@echo "  make cluster    Create the kind cluster only"
	@echo "  make workloads  Apply the broken workloads to an existing cluster"
	@echo "  make ui         Start the web UI via docker-compose"
	@echo "  make status     Show pod status in the demo namespace"
	@echo "  make logs       Tail the web UI backend logs"
	@echo "  make down       Remove broken workloads (keep cluster)"
	@echo "  make clean      Delete the kind cluster entirely"

up: cluster kubeconfig workloads ui
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

kubeconfig:
	@echo "Preparing demo kubeconfig for the Dockerized backend..."
	@if [ -f $(LEGACY_COMPOSE_ENV_BACKUP) ]; then \
		mv $(LEGACY_COMPOSE_ENV_BACKUP) $(LEGACY_COMPOSE_ENV); \
	elif [ -f $(LEGACY_COMPOSE_ENV) ]; then \
		grep -v '^KUBEASTRA_KUBECONFIG_FILE=' $(LEGACY_COMPOSE_ENV) > $(LEGACY_COMPOSE_ENV).tmp || true; \
		mv $(LEGACY_COMPOSE_ENV).tmp $(LEGACY_COMPOSE_ENV); \
		[ -s $(LEGACY_COMPOSE_ENV) ] || rm -f $(LEGACY_COMPOSE_ENV); \
	fi
	@mkdir -p $(dir $(DEMO_KUBECONFIG))
	@kind get kubeconfig --name $(CLUSTER_NAME) > $(DEMO_KUBECONFIG)
	@SERVER=$$(kubectl config view --kubeconfig $(DEMO_KUBECONFIG) --minify -o jsonpath='{.clusters[0].cluster.server}'); \
	DOCKER_SERVER=$$(printf '%s' "$$SERVER" | sed 's#127\.0\.0\.1#host.docker.internal#; s#localhost#host.docker.internal#'); \
	kubectl config set-cluster kind-$(CLUSTER_NAME) --server="$$DOCKER_SERVER" --kubeconfig $(DEMO_KUBECONFIG) >/dev/null; \
	kubectl config set-cluster kind-$(CLUSTER_NAME) --tls-server-name=localhost --kubeconfig $(DEMO_KUBECONFIG) >/dev/null; \
	echo "  Demo backend will use $$DOCKER_SERVER"; \
	grep -q 'host.docker.internal' $(DEMO_KUBECONFIG) || { echo "Failed to rewrite demo kubeconfig for Docker access"; exit 1; }; \
	grep -q 'tls-server-name: localhost' $(DEMO_KUBECONFIG) || { echo "Failed to set TLS server name for demo kubeconfig"; exit 1; }
	@printf 'KUBEASTRA_KUBECONFIG_FILE=%s\n' "$(abspath $(DEMO_KUBECONFIG))" > $(DEMO_COMPOSE_ENV)

workloads:
	@echo "Applying broken workloads to namespace 'demo'..."
	kubectl --context kind-$(CLUSTER_NAME) apply -f $(WORKLOADS)
	@echo ""
	@echo "Waiting for the broken states to manifest..."
	@sleep 20
	@$(MAKE) --no-print-directory status

ui: kubeconfig
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
	cd $(UI_DIR) && docker compose --env-file .env.demo up -d --build --force-recreate

status:
	@kubectl --context kind-$(CLUSTER_NAME) get pods,pvc -n demo -o wide 2>/dev/null || \
		echo "Cluster '$(CLUSTER_NAME)' not reachable — run 'make cluster' first"

logs:
	cd $(UI_DIR) && docker compose logs -f backend

down:
	@echo "Removing demo workloads (cluster kept)..."
	-kubectl --context kind-$(CLUSTER_NAME) delete -f $(WORKLOADS) --ignore-not-found
	@echo "Stopping web UI..."
	-if [ -f $(DEMO_COMPOSE_ENV) ]; then cd $(UI_DIR) && docker compose --env-file .env.demo down; else cd $(UI_DIR) && docker compose down; fi
	@if [ -f $(LEGACY_COMPOSE_ENV_BACKUP) ]; then \
		mv $(LEGACY_COMPOSE_ENV_BACKUP) $(LEGACY_COMPOSE_ENV); \
	elif [ -f $(LEGACY_COMPOSE_ENV) ]; then \
		grep -v '^KUBEASTRA_KUBECONFIG_FILE=' $(LEGACY_COMPOSE_ENV) > $(LEGACY_COMPOSE_ENV).tmp || true; \
		mv $(LEGACY_COMPOSE_ENV).tmp $(LEGACY_COMPOSE_ENV); \
		[ -s $(LEGACY_COMPOSE_ENV) ] || rm -f $(LEGACY_COMPOSE_ENV); \
	fi
	-rm -f $(DEMO_COMPOSE_ENV)
	-rm -f $(DEMO_KUBECONFIG)

clean: down
	@echo "Deleting kind cluster '$(CLUSTER_NAME)'..."
	-kind delete cluster --name $(CLUSTER_NAME)
