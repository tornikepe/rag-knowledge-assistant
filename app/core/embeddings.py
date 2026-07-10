"""Embedding providers.

Embeddings turn text into vectors so we can measure semantic similarity. The provider
is pluggable behind a small interface, which keeps the rest of the app agnostic to
*how* vectors are produced:

* ``OpenAIEmbeddings`` — ``text-embedding-3-small``; the production default.
* ``HashingEmbeddings`` — a deterministic, dependency-free, offline embedder used for
  demos and CI. It is a hashing bag-of-words model: not semantically strong, but it
  needs no API key and makes the whole pipeline runnable and testable anywhere.
"""

from __future__ import annotations

import hashlib
import re
from abc import ABC, abstractmethod

import numpy as np

from app.config import Settings

_TOKEN_RE = re.compile(r"[a-z0-9]+")


class EmbeddingProvider(ABC):
    """Turns text into unit-length vectors."""

    dim: int

    @abstractmethod
    def embed_documents(self, texts: list[str]) -> np.ndarray:
        """Embed a batch of documents -> array of shape (len(texts), dim)."""

    def embed_query(self, text: str) -> np.ndarray:
        """Embed a single query -> array of shape (dim,)."""
        return self.embed_documents([text])[0]


def _l2_normalize(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


class HashingEmbeddings(EmbeddingProvider):
    """Deterministic offline embeddings via feature hashing.

    Each token is hashed into one of ``dim`` buckets; the resulting count vector is
    L2-normalized. Cosine similarity then behaves like normalized term overlap — enough
    to demonstrate retrieval end-to-end without any external service.
    """

    def __init__(self, dim: int = 256) -> None:
        self.dim = dim

    def _embed_one(self, text: str) -> np.ndarray:
        vec = np.zeros(self.dim, dtype=np.float32)
        for token in _TOKEN_RE.findall(text.lower()):
            h = int(hashlib.md5(token.encode()).hexdigest(), 16)
            vec[h % self.dim] += 1.0
        return vec

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        return _l2_normalize(np.vstack([self._embed_one(t) for t in texts]))


class OpenAIEmbeddings(EmbeddingProvider):
    """OpenAI embeddings (``text-embedding-3-small`` by default)."""

    _DIMS = {
        "text-embedding-3-small": 1536,
        "text-embedding-3-large": 3072,
        "text-embedding-ada-002": 1536,
    }

    def __init__(self, api_key: str, model: str = "text-embedding-3-small") -> None:
        from openai import OpenAI  # imported lazily so `hash` mode needs no openai dep

        self._client = OpenAI(api_key=api_key)
        self.model = model
        self.dim = self._DIMS.get(model, 1536)

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        vectors: list[list[float]] = []
        # OpenAI accepts batches; 128 keeps requests comfortably under limits.
        for start in range(0, len(texts), 128):
            batch = texts[start : start + 128]
            resp = self._client.embeddings.create(model=self.model, input=batch)
            vectors.extend(item.embedding for item in resp.data)
        return _l2_normalize(np.array(vectors, dtype=np.float32))


def build_embedding_provider(settings: Settings) -> EmbeddingProvider:
    """Factory: choose an embedding provider from settings."""
    provider = settings.embedding_provider.lower()
    if provider == "openai":
        if not settings.openai_api_key:
            raise ValueError(
                "EMBEDDING_PROVIDER=openai requires OPENAI_API_KEY. "
                "Set it in .env, or use EMBEDDING_PROVIDER=hash for offline mode."
            )
        return OpenAIEmbeddings(settings.openai_api_key, settings.embedding_model)
    if provider == "hash":
        return HashingEmbeddings(settings.embedding_dim)
    raise ValueError(f"Unknown EMBEDDING_PROVIDER: {settings.embedding_provider!r}")
