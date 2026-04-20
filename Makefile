.PHONY: help demo demo-down demo-clean demo-status

help:
	@echo "k8s-devops-ai-assistant"
	@echo ""
	@echo "  make demo         Spin up kind cluster + broken workloads + web UI"
	@echo "  make demo-status  Show pod status in the demo namespace"
	@echo "  make demo-down    Remove demo workloads + stop UI (keep cluster)"
	@echo "  make demo-clean   Delete the kind cluster entirely"
	@echo ""
	@echo "See demo/README.md for details."

demo:
	$(MAKE) -C demo up

demo-status:
	$(MAKE) -C demo status

demo-down:
	$(MAKE) -C demo down

demo-clean:
	$(MAKE) -C demo clean
