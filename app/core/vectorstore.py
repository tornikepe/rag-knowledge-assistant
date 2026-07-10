"""A small, persistent vector store.

This is a from-scratch cosine-similarity index over a dense NumPy matrix. It is
deliberately simple and dependency-light — the point is to show the mechanics of
retrieval clearly. Everything sits behind the ``VectorStore`` interface, so swapping in
Chroma, pgvector, Pinecone, etc. is a single-class change with no impact on the rest of
the app.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np


@dataclass
class Record:
    """One indexed chunk plus provenance."""

    id: str
    text: str
    source: str
    chunk_index: int


@dataclass
class SearchResult:
    record: Record
    score: float


class VectorStore(ABC):
    @abstractmethod
    def add(self, records: list[Record], embeddings: np.ndarray) -> None: ...

    @abstractmethod
    def search(self, query_embedding: np.ndarray, k: int) -> list[SearchResult]: ...

    @abstractmethod
    def count(self) -> int: ...

    @abstractmethod
    def documents(self) -> dict[str, int]:
        """Map of source filename -> number of chunks."""

    @abstractmethod
    def remove_document(self, source: str) -> int:
        """Remove every chunk belonging to ``source``. Returns how many were removed."""

    @abstractmethod
    def clear(self) -> None: ...


class NumpyVectorStore(VectorStore):
    """In-memory index backed by a NumPy matrix, persisted to disk as .npy + .json."""

    def __init__(self, index_dir: Path) -> None:
        self.index_dir = Path(index_dir)
        self._records: list[Record] = []
        self._matrix: np.ndarray | None = None  # shape (N, dim), rows L2-normalized
        self._load()

    # --- persistence ---------------------------------------------------------
    @property
    def _vectors_path(self) -> Path:
        return self.index_dir / "vectors.npy"

    @property
    def _records_path(self) -> Path:
        return self.index_dir / "records.json"

    def _load(self) -> None:
        if self._vectors_path.exists() and self._records_path.exists():
            self._matrix = np.load(self._vectors_path)
            raw = json.loads(self._records_path.read_text(encoding="utf-8"))
            self._records = [Record(**r) for r in raw]

    def _persist(self) -> None:
        self.index_dir.mkdir(parents=True, exist_ok=True)
        matrix = self._matrix if self._matrix is not None else np.zeros((0, 0))
        np.save(self._vectors_path, matrix)
        self._records_path.write_text(
            json.dumps([asdict(r) for r in self._records], ensure_ascii=False),
            encoding="utf-8",
        )

    # --- interface -----------------------------------------------------------
    def add(self, records: list[Record], embeddings: np.ndarray) -> None:
        if not records:
            return
        if len(records) != embeddings.shape[0]:
            raise ValueError("records and embeddings length mismatch")
        embeddings = embeddings.astype(np.float32)
        if self._matrix is None or self._matrix.size == 0:
            self._matrix = embeddings
        else:
            if embeddings.shape[1] != self._matrix.shape[1]:
                raise ValueError(
                    "Embedding dimension changed — clear the index before switching "
                    "embedding providers."
                )
            self._matrix = np.vstack([self._matrix, embeddings])
        self._records.extend(records)
        self._persist()

    def search(self, query_embedding: np.ndarray, k: int) -> list[SearchResult]:
        if self._matrix is None or self._matrix.size == 0:
            return []
        query = query_embedding.astype(np.float32).reshape(-1)
        # Rows and query are unit-normalized, so the dot product is cosine similarity.
        scores = self._matrix @ query
        k = min(k, len(self._records))
        top = np.argpartition(-scores, k - 1)[:k]
        top = top[np.argsort(-scores[top])]
        return [SearchResult(self._records[i], float(scores[i])) for i in top]

    def count(self) -> int:
        return len(self._records)

    def documents(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for record in self._records:
            counts[record.source] = counts.get(record.source, 0) + 1
        return counts

    def remove_document(self, source: str) -> int:
        if not self._records:
            return 0
        keep = [i for i, r in enumerate(self._records) if r.source != source]
        removed = len(self._records) - len(keep)
        if removed == 0:
            return 0
        self._records = [self._records[i] for i in keep]
        self._matrix = self._matrix[keep] if (keep and self._matrix is not None) else None
        self._persist()
        return removed

    def clear(self) -> None:
        self._records = []
        self._matrix = None
        for path in (self._vectors_path, self._records_path):
            path.unlink(missing_ok=True)
