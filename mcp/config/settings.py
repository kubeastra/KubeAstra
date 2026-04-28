"""Merged configuration for Kubeastra MCP Server.

Combines settings from both:
- mcp-k8s-investigation-agent (kubectl, cluster access, recovery ops)
- k8s-ansible-mcp (Gemini AI, Weaviate vector DB, embeddings)
"""

from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

_CONFIG_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _CONFIG_DIR.parent
_ENV_FILE = _PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Kubernetes / kubectl settings ─────────────────────────────────────────
    kubeconfig_path: Optional[str] = None
    allowed_namespaces: str = "default"
    kubectl_timeout_seconds: int = 15
    max_log_tail_lines: int = 200
    max_output_bytes: int = 102400  # 100 KB — enough for logs/describe; run_json uses 10 MB
    enable_k8sgpt: bool = False
    enable_audit_log: bool = True
    audit_log_path: str = "./audit.log"

    # Recovery operations (disabled by default for safety)
    enable_recovery_operations: bool = False
    max_scale_replicas: int = 100
    max_grace_period_seconds: int = 300

    # ── Deployment repository settings ────────────────────────────────────────
    deployment_repo_url: str = "git@github.com:your-org/deployment-provisioning.git"
    github_token: Optional[str] = None

    # ── LLM provider selection ────────────────────────────────────────────────
    # "gemini" (default) or "ollama". Add more providers by implementing
    # services/llm/<name>_provider.py and registering in services/llm/__init__.py.
    llm_provider: str = "gemini"

    # ── AI / Gemini settings ──────────────────────────────────────────────────
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"

    # ── Ollama settings (local / self-hosted LLM) ─────────────────────────────
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"

    # ── Vector DB / RAG settings ──────────────────────────────────────────────
    weaviate_url: str = "http://localhost:8080"
    weaviate_collection: str = "K8sAnsibleError"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    # ── Database (optional, inherited from devops-ai-assistant) ───────────────
    database_url: str = "postgresql://devops_ai:devops_ai_password@localhost:5432/devops_ai_db"

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def allowed_namespaces_list(self) -> List[str]:
        return [ns.strip() for ns in self.allowed_namespaces.split(",") if ns.strip()]

    @property
    def kubeconfig_path_resolved(self) -> Optional[Path]:
        if not self.kubeconfig_path:
            return None
        return Path(self.kubeconfig_path).expanduser().resolve()

    @property
    def ai_enabled(self) -> bool:
        provider = (self.llm_provider or "").lower()
        if provider == "ollama":
            return bool(self.ollama_base_url and self.ollama_model)
        return bool(self.gemini_api_key)

    def validate_settings(self) -> None:
        if not self.allowed_namespaces_list:
            raise ValueError("ALLOWED_NAMESPACES must contain at least one namespace")
        if self.kubectl_timeout_seconds <= 0:
            raise ValueError("KUBECTL_TIMEOUT_SECONDS must be positive")
        if self.max_log_tail_lines <= 0 or self.max_log_tail_lines > 1000:
            raise ValueError("MAX_LOG_TAIL_LINES must be between 1 and 1000")
        if self.max_output_bytes <= 0:
            raise ValueError("MAX_OUTPUT_BYTES must be positive")


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
