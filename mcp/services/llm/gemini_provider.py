"""Google Gemini LLM provider."""

import logging
from typing import Any, Optional

from .base import LLMProvider, LLMProviderError

logger = logging.getLogger(__name__)


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, api_key: str, model: str):
        self._api_key = api_key
        self._model = model
        self._client: Optional[Any] = None

    @property
    def enabled(self) -> bool:
        return bool(self._api_key)

    def _get_client(self) -> Optional[Any]:
        if self._client is not None:
            return self._client
        if not self._api_key:
            return None
        try:
            from google import genai
        except ImportError as exc:
            logger.error("google-genai is not installed — run 'pip install google-genai'")
            raise LLMProviderError("google-genai SDK is not installed") from exc
        self._client = genai.Client(api_key=self._api_key)
        return self._client

    def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
    ) -> str:
        client = self._get_client()
        if client is None:
            raise LLMProviderError("Gemini API key is not configured")

        try:
            from google.genai import types
        except ImportError as exc:
            raise LLMProviderError("google-genai SDK is not installed") from exc

        kwargs: dict = {"temperature": temperature}
        if system:
            kwargs["system_instruction"] = system
        if max_tokens:
            kwargs["max_output_tokens"] = max_tokens
        config = types.GenerateContentConfig(**kwargs)

        try:
            response = client.models.generate_content(
                model=self._model,
                contents=prompt,
                config=config,
            )
        except Exception as exc:
            logger.error(f"Gemini request failed: {exc}")
            raise LLMProviderError(str(exc)) from exc

        return response.text or ""
