"""Weaviate vector DB service for RAG-based similar error lookup."""

import logging
from typing import Optional

import weaviate
from weaviate.classes.config import Configure, Property, DataType
from weaviate.classes.query import MetadataQuery

from config.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class VectorDB:
    def __init__(self):
        self._client: Optional[weaviate.WeaviateClient] = None
        self.collection = settings.weaviate_collection

    def connect(self):
        host, port = self._parse_url(settings.weaviate_url)
        self._client = weaviate.connect_to_local(host=host, port=port)
        self._ensure_collection()
        logger.info("VectorDB connected")

    def _parse_url(self, url: str):
        url = url.replace("http://", "").replace("https://", "")
        parts = url.split(":")
        host = parts[0]
        port = int(parts[1]) if len(parts) > 1 else 8080
        return host, port

    def _ensure_collection(self):
        if not self._client.collections.exists(self.collection):
            self._client.collections.create(
                name=self.collection,
                vectorizer_config=Configure.Vectorizer.none(),
                properties=[
                    Property(name="error_text",    data_type=DataType.TEXT),
                    Property(name="tool",           data_type=DataType.TEXT),
                    Property(name="category",       data_type=DataType.TEXT),
                    Property(name="solution_text",  data_type=DataType.TEXT),
                    Property(name="commands",       data_type=DataType.TEXT),
                    Property(name="success_rate",   data_type=DataType.NUMBER),
                    Property(name="severity",       data_type=DataType.TEXT),
                ],
            )
            logger.info(f"Created collection: {self.collection}")

    def add(self, error_text: str, tool: str, category: str, solution_text: str,
            commands: str, success_rate: float, severity: str, vector: list[float]):
        col = self._client.collections.get(self.collection)
        col.data.insert(
            properties={
                "error_text":    error_text,
                "tool":          tool,
                "category":      category,
                "solution_text": solution_text,
                "commands":      commands,
                "success_rate":  success_rate,
                "severity":      severity,
            },
            vector=vector,
        )

    def search(self, query_vector: list[float], tool: str = None, limit: int = 5) -> list[dict]:
        if not self._client:
            return []
        try:
            col = self._client.collections.get(self.collection)
            results = col.query.near_vector(
                near_vector=query_vector,
                limit=limit,
                return_metadata=MetadataQuery(distance=True),
            )
            matches = []
            for obj in results.objects:
                p = obj.properties
                if tool and p.get("tool") not in (tool, "both"):
                    continue
                matches.append({
                    "error_text":    p.get("error_text", ""),
                    "tool":          p.get("tool", ""),
                    "category":      p.get("category", ""),
                    "solution_text": p.get("solution_text", ""),
                    "commands":      p.get("commands", ""),
                    "success_rate":  p.get("success_rate", 0),
                    "severity":      p.get("severity", "medium"),
                    "similarity":    round(1 - obj.metadata.distance, 3),
                })
            return matches
        except Exception as e:
            logger.warning(f"Vector search failed: {e}")
            return []

    def disconnect(self):
        if self._client:
            self._client.close()


vector_db = VectorDB()
