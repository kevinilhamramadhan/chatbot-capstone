"""Ollama-backed embedding function compatible with ChromaDB.

Wraps the `qwen3-embedding:0.6b` model served by Ollama.
"""

import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


class OllamaEmbeddingFunction:
    """ChromaDB EmbeddingFunction protocol: __call__(input) -> embeddings."""

    def __init__(self) -> None:
        from langchain_ollama import OllamaEmbeddings  # lazy: heavy import

        self._emb = OllamaEmbeddings(
            base_url=settings.ollama_base_url,
            model=settings.embedding_model,
            keep_alive=settings.llm_keep_alive,  # keep resident alongside the LLM
        )

    def __call__(self, input) -> list[list[float]]:  # noqa: A002
        # ChromaDB passes a list of documents (indexing path).
        return self._emb.embed_documents(list(input))

    def embed_query(self, input):  # noqa: A002
        # ChromaDB 1.x query path calls this with keyword `input` (str or list).
        if isinstance(input, str):
            return self._emb.embed_query(input)
        return self._emb.embed_documents(list(input))

    def embed_one(self, text: str) -> list[float]:
        """Single query vector — used directly by retrieval (version-agnostic)."""
        return self._emb.embed_query(text)

    # ChromaDB calls this for validation/telemetry.
    def name(self) -> str:
        return f"ollama:{settings.embedding_model}"


_ef: OllamaEmbeddingFunction | None = None


def get_embedding_function() -> OllamaEmbeddingFunction:
    global _ef
    if _ef is None:
        _ef = OllamaEmbeddingFunction()
    return _ef
