"""Ollama local LLM provider.

Uses the Ollama HTTP API (`/api/chat`). Expects an Ollama server to be reachable
at `OLLAMA_BASE_URL` with the model specified by `OLLAMA_MODEL` already pulled
(e.g. `ollama pull llama3.1`). No data leaves the local network.
"""

import logging
from typing import Optional

import httpx

from .base import LLMProvider, LLMProviderError

logger = logging.getLogger(__name__)


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(self, base_url: str, model: str, timeout: float = 120.0):
        self._base_url = (base_url or "").rstrip("/")
        self._model = model
        self._timeout = timeout

    @property
    def enabled(self) -> bool:
        return bool(self._base_url and self._model)

    def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
    ) -> str:
        if not self.enabled:
            raise LLMProviderError("Ollama base URL or model is not configured")

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        options: dict = {"temperature": temperature}
        if max_tokens:
            options["num_predict"] = max_tokens

        payload = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            "options": options,
        }

        url = f"{self._base_url}/api/chat"
        try:
            response = httpx.post(url, json=payload, timeout=self._timeout)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error(f"Ollama request to {url} failed: {exc}")
            raise LLMProviderError(f"Ollama request failed: {exc}") from exc

        data = response.json()
        message = data.get("message") or {}
        content = message.get("content", "")
        if not content:
            raise LLMProviderError(
                "Ollama returned an empty response — verify the model is pulled "
                f"('ollama pull {self._model}')"
            )
        return content
