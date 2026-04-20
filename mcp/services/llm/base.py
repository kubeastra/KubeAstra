"""LLM provider interface.

All providers return plain text. The caller (`LLMService`) handles JSON parsing,
prompt construction, and error fallbacks — keeping providers thin and swappable.
"""

from abc import ABC, abstractmethod
from typing import Optional


class LLMProviderError(RuntimeError):
    """Raised when a provider cannot fulfill a generation request."""


class LLMProvider(ABC):
    """Abstract base class for pluggable LLM backends."""

    name: str = "base"

    @property
    @abstractmethod
    def enabled(self) -> bool:
        """Whether the provider is configured and can serve requests."""

    @abstractmethod
    def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Generate a single completion and return its text.

        Raises `LLMProviderError` on failure so callers can render a friendly
        fallback instead of leaking transport exceptions.
        """
