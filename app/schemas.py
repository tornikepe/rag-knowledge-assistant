"""Pydantic request/response models — the public API contract."""

from __future__ import annotations

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str
    embedding_provider: str
    llm_provider: str
    model: str
    documents: int
    chunks: int


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)
    top_k: int | None = Field(default=None, ge=1, le=20)
    collection: str | None = Field(
        default=None, max_length=128, description="Chat id to scope retrieval to"
    )


class Citation(BaseModel):
    marker: int = Field(..., description="Inline citation number, e.g. [1]")
    source: str
    chunk_index: int
    score: float = Field(..., description="Cosine similarity of the chunk to the query")
    snippet: str


class QueryResponse(BaseModel):
    answer: str
    citations: list[Citation]
    model: str


class DocumentInfo(BaseModel):
    source: str
    chunks: int


class DocumentsResponse(BaseModel):
    documents: list[DocumentInfo]
    total_chunks: int


class IngestResponse(BaseModel):
    source: str
    chunks_added: int
    total_chunks: int
    message: str
