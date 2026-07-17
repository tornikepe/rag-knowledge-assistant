"""Embedding providers.

Embeddings turn text into vectors so we can measure semantic similarity. The provider
is pluggable behind a small interface, which keeps the rest of the app agnostic to
*how* vectors are produced:

* ``GeminiEmbeddings`` — Google Gemini (``gemini-embedding-001``); the recommended
  provider for real retrieval, and free on Gemini's free tier.
* ``OpenAIEmbeddings`` — ``text-embedding-3-small``.
* ``HashingEmbeddings`` — a deterministic, dependency-free, offline embedder used for
  demos and CI. It is a hashing bag-of-words model: not semantically strong, but it
  needs no API key and makes the whole pipeline runnable and testable anywhere.
"""

from __future__ import annotations

import hashlib
import re
import time
from abc import ABC, abstractmethod

import numpy as np

from app.config import Settings

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Transient Gemini statuses (overloaded / rate-limited / internal) worth retrying.
_GEMINI_RETRYABLE_STATUS = frozenset({429, 500, 503})


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


class GeminiEmbeddings(EmbeddingProvider):
    """Google Gemini embeddings via the google-genai SDK (free-tier friendly).

    Task-type aware: documents are embedded with ``RETRIEVAL_DOCUMENT`` and queries
    with ``RETRIEVAL_QUERY``, which sharpens retrieval versus one symmetric embedding.
    One ``GEMINI_API_KEY`` powers this and ``app.core.llm.GeminiLLM``.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-embedding-001",
        dim: int = 768,
        batch_size: int = 100,
        max_retries: int = 3,
    ) -> None:
        from google import genai  # lazy import so `hash` mode needs no google-genai dep
        from google.genai import errors, types

        self._types = types
        self._errors = errors
        self._client = genai.Client(api_key=api_key)
        self.model = model
        self.dim = dim
        self.batch_size = batch_size
        self.max_retries = max_retries

    def _embed_batch(self, batch: list[str], task_type: str) -> list[list[float]]:
        """Embed one batch, retrying transient Gemini errors with backoff."""
        for attempt in range(self.max_retries + 1):
            try:
                resp = self._client.models.embed_content(
                    model=self.model,
                    contents=batch,
                    config=self._types.EmbedContentConfig(
                        task_type=task_type,
                        output_dimensionality=self.dim,
                    ),
                )
                return [e.values for e in resp.embeddings]
            except self._errors.APIError as exc:
                status = getattr(exc, "code", None)
                if status not in _GEMINI_RETRYABLE_STATUS or attempt == self.max_retries:
                    raise
                time.sleep(0.6 * (2 ** attempt))
        return []  # unreachable; the loop returns or raises

    def _embed(self, texts: list[str], task_type: str) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        vectors: list[list[float]] = []
        # Gemini accepts batches; 100 stays within the embedding request limit.
        for start in range(0, len(texts), self.batch_size):
            vectors.extend(self._embed_batch(texts[start : start + self.batch_size], task_type))
        # A truncated output dimension (dim < the model's native size) needs
        # re-normalizing for cosine similarity — which is what _l2_normalize does.
        return _l2_normalize(np.array(vectors, dtype=np.float32))

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        return self._embed(texts, "RETRIEVAL_DOCUMENT")

    def embed_query(self, text: str) -> np.ndarray:
        return self._embed([text], "RETRIEVAL_QUERY")[0]


class OpenAIEmbeddings(EmbeddingProvider):
    """OpenAI embeddings (``text-embedding-3-small`` by default)."""

    _DIMS = {
        "text-embedding-3-small": 1536,
        "text-embedding-3-large": 3072,
        "text-embedding-ada-002": 1536,
    }

    def __init__(self, api_key: str, model: str = "text-embedding-3-small") -> None:
        try:
            from openai import OpenAI  # lazy import: only needed for EMBEDDING_PROVIDER=openai
        except ModuleNotFoundError as exc:  # pragma: no cover - optional dependency
            raise ModuleNotFoundError(
                "EMBEDDING_PROVIDER=openai needs the OpenAI SDK. Install it with "
                "`pip install openai`. The default free provider is Gemini "
                "(EMBEDDING_PROVIDER=gemini), which needs no extra install."
            ) from exc

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
    if provider == "gemini":
        if not settings.gemini_api_key:
            raise ValueError(
                "EMBEDDING_PROVIDER=gemini requires GEMINI_API_KEY. "
                "Set it in .env, or use EMBEDDING_PROVIDER=hash for offline mode."
            )
        return GeminiEmbeddings(
            settings.gemini_api_key,
            settings.gemini_embedding_model,
            settings.gemini_embedding_dim,
            max_retries=settings.gemini_max_retries,
        )
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
