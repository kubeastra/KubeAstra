import os
import subprocess
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    kubectl_available: bool
    kubectl_context: str | None
    ai_enabled: bool
    weaviate_url: str


def _health_status() -> HealthResponse:
    # Check kubectl
    kubectl_ok = False
    current_context = None
    try:
        result = subprocess.run(
            ["kubectl", "config", "current-context"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            kubectl_ok = True
            current_context = result.stdout.strip()
    except Exception:
        pass

    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    provider = os.environ.get("LLM_PROVIDER", "gemini").lower()
    ollama_base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model = os.environ.get("OLLAMA_MODEL", "llama3.1")
    weaviate_url = os.environ.get("WEAVIATE_URL", "http://localhost:8080")
    ai_enabled = bool(
        (provider == "ollama" and ollama_base_url and ollama_model)
        or (provider in {"", "gemini"} and gemini_key)
    )

    return HealthResponse(
        status="ok",
        kubectl_available=kubectl_ok,
        kubectl_context=current_context,
        ai_enabled=ai_enabled,
        weaviate_url=weaviate_url,
    )


@router.get("/health", response_model=HealthResponse)
@router.get("/api/health", response_model=HealthResponse)
def health_check():
    return _health_status()
