"""The RAG service — the orchestrator that ties retrieval and generation together.

This is the single object the API layer talks to. It owns the embedding provider, the
vector store, and the LLM, and exposes the two operations that matter:

* ``ingest`` — chunk a document, embed the chunks, and add them to the index.
* ``query`` / ``stream`` — retrieve the most relevant chunks and have the LLM answer
  the question grounded in (and citing) them.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

from app.config import Settings
from app.core.chunking import chunk_text
from app.core.embeddings import EmbeddingProvider, build_embedding_provider
from app.core.ingest import extract_text
from app.core.llm import SYSTEM_PROMPT, LLMProvider, build_llm_provider
from app.core.vectorstore import NumpyVectorStore, Record, SearchResult, VectorStore
from app.schemas import Citation


class RAGService:
    def __init__(
        self,
        settings: Settings,
        embeddings: EmbeddingProvider,
        store: VectorStore,
        llm: LLMProvider,
    ) -> None:
        self.settings = settings
        self.embeddings = embeddings
        self.store = store
        self.llm = llm

    # --- ingestion -----------------------------------------------------------
    def ingest(self, filename: str, data: bytes, collection: str = "") -> int:
        """Chunk, embed, and index a document. Returns the number of chunks added.

        ``collection`` scopes the document to a single chat, so uploads only affect
        the conversation they were added to.
        """
        text = extract_text(filename, data)
        chunks = chunk_text(
            text,
            chunk_size=self.settings.chunk_size,
            overlap=self.settings.chunk_overlap,
        )
        if not chunks:
            return 0

        vectors = self.embeddings.embed_documents(chunks)
        records = [
            Record(
                id=str(uuid.uuid4()),
                text=chunk,
                source=filename,
                chunk_index=i,
                collection=collection,
            )
            for i, chunk in enumerate(chunks)
        ]
        # Re-ingesting the same filename in a chat replaces its previous chunks.
        self.store.remove_document(filename, collection=collection)
        self.store.add(records, vectors)
        return len(records)

    def documents(self, collection: str | None = None) -> dict[str, int]:
        return self.store.documents(collection=collection)

    def remove_document(self, source: str, collection: str | None = None) -> int:
        return self.store.remove_document(source, collection=collection)

    def remove_collection(self, collection: str) -> int:
        return self.store.remove_collection(collection)

    # --- retrieval + generation ---------------------------------------------
    def retrieve(
        self, question: str, top_k: int | None = None, collection: str | None = None
    ) -> list[SearchResult]:
        k = top_k or self.settings.top_k
        query_vec = self.embeddings.embed_query(question)
        return self.store.search(query_vec, k, collection=collection)

    def query(
        self, question: str, top_k: int | None = None, collection: str | None = None
    ) -> tuple[str, list[Citation]]:
        """Non-streaming answer + citations."""
        results = self.retrieve(question, top_k, collection=collection)
        citations = _to_citations(results)
        if not results:
            return (
                "I don't have any documents in this chat that address your question. "
                "Attach a PDF, TXT, or Markdown file to this chat first.",
                citations,
            )
        prompt = _build_prompt(question, results)
        answer = self.llm.complete(SYSTEM_PROMPT, prompt)
        return answer, citations

    def stream(
        self, question: str, top_k: int | None = None, collection: str | None = None
    ) -> tuple[Iterator[str], list[Citation]]:
        """Streaming answer generator + citations (citations resolved up front)."""
        results = self.retrieve(question, top_k, collection=collection)
        citations = _to_citations(results)
        if not results:
            def _empty() -> Iterator[str]:
                yield (
                    "I don't have any documents in this chat that address your question. "
                    "Attach a PDF, TXT, or Markdown file to this chat first."
                )

            return _empty(), citations
        prompt = _build_prompt(question, results)
        return self.llm.stream(SYSTEM_PROMPT, prompt), citations


# --- prompt + citation helpers ----------------------------------------------
def _build_prompt(question: str, results: list[SearchResult]) -> str:
    blocks = []
    for i, result in enumerate(results, start=1):
        source = result.record.source
        blocks.append(f"[{i}] (source: {source})\n{result.record.text}")
    context = "\n\n".join(blocks)
    return (
        f"Context passages:\n\n{context}\n\n"
        f"Question: {question}\n\n"
        "Answer using only the context above and cite passages with [n]."
    )


def _to_citations(results: list[SearchResult]) -> list[Citation]:
    citations = []
    for i, result in enumerate(results, start=1):
        snippet = result.record.text.strip().replace("\n", " ")
        if len(snippet) > 240:
            snippet = snippet[:237] + "..."
        citations.append(
            Citation(
                marker=i,
                source=result.record.source,
                chunk_index=result.record.chunk_index,
                score=round(result.score, 4),
                snippet=snippet,
            )
        )
    return citations


def build_service(settings: Settings) -> RAGService:
    """Construct a fully wired ``RAGService`` from settings."""
    embeddings = build_embedding_provider(settings)
    store = NumpyVectorStore(settings.index_dir)
    llm = build_llm_provider(settings)
    return RAGService(settings, embeddings, store, llm)
