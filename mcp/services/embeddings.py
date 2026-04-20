"""Sentence-transformer embeddings for semantic error similarity search.

SentenceTransformer (and transitively torch) is imported lazily at first use,
not at module load time. This prevents startup crashes in environments where:
  - UID is not present in /etc/passwd (torch.getpwuid fails)
  - Weaviate/RAG is not configured and embeddings are never called
"""

import logging
from typing import TYPE_CHECKING, Optional

from config.settings import get_settings

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer as _ST

logger = logging.getLogger(__name__)
settings = get_settings()


class EmbeddingService:
    def __init__(self):
        self._model: Optional["_ST"] = None

    def _load(self):
        if not self._model:
            # Lazy import — only triggered when RAG/Weaviate actually calls embed()
            from sentence_transformers import SentenceTransformer
            logger.info(f"Loading embedding model: {settings.embedding_model}")
            self._model = SentenceTransformer(settings.embedding_model)

    def embed(self, text: str) -> list[float]:
        self._load()
        return self._model.encode(text, normalize_embeddings=True).tolist()

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        self._load()
        return self._model.encode(texts, normalize_embeddings=True, batch_size=32).tolist()


embeddings = EmbeddingService()
