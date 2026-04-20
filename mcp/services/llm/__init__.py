"""Pluggable LLM provider abstraction.

Each provider implements the `LLMProvider` interface in `base.py`. Add a new
provider by creating a module in this package, implementing `LLMProvider`,
and registering it in `get_provider()` below.
"""

from .base import LLMProvider


def get_provider() -> LLMProvider:
    """Return the configured LLM provider instance.

    Selected by the `LLM_PROVIDER` env var. Defaults to `gemini` so existing
    deployments that only set `GEMINI_API_KEY` keep working.
    """
    from config.settings import get_settings

    settings = get_settings()
    name = (settings.llm_provider or "gemini").lower()

    if name == "ollama":
        from .ollama_provider import OllamaProvider
        return OllamaProvider(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
        )

    if name == "gemini":
        from .gemini_provider import GeminiProvider
        return GeminiProvider(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
        )

    raise ValueError(
        f"Unknown LLM_PROVIDER '{settings.llm_provider}'. "
        f"Supported: 'gemini', 'ollama'."
    )


__all__ = ["LLMProvider", "get_provider"]
