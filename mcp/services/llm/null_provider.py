"""Fallback LLM provider used when no model backend is configured."""

import json
from typing import Optional

from .base import LLMProvider

NOT_CONFIGURED_MESSAGE = (
    "No LLM configured. Set GEMINI_API_KEY in .env, or set LLM_PROVIDER=ollama "
    "with a running Ollama server."
)


class NullProvider(LLMProvider):
    """Provider marker for degraded mode when kubectl tools still work."""

    name = "null"

    @property
    def enabled(self) -> bool:
        return False

    def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
    ) -> str:
        return json.dumps(
            {
                "type": "llm_not_configured",
                "message": NOT_CONFIGURED_MESSAGE,
                "setup_options": [
                    {
                        "label": "Set up Gemini",
                        "url": "https://aistudio.google.com/",
                        "env": "GEMINI_API_KEY",
                    },
                    {
                        "label": "Run Ollama locally",
                        "url": "https://ollama.com/",
                        "env": "LLM_PROVIDER=ollama",
                    },
                ],
            }
        )
