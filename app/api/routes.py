"""HTTP API routes."""

from __future__ import annotations

import json

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from app import __version__
from app.core.ingest import UnsupportedFileType
from app.core.service import RAGService
from app.schemas import (
    DocumentInfo,
    DocumentsResponse,
    HealthResponse,
    IngestResponse,
    QueryRequest,
    QueryResponse,
)

router = APIRouter(prefix="/api")


def _service(request: Request) -> RAGService:
    return request.app.state.service


@router.get("/health", response_model=HealthResponse, tags=["system"])
def health(request: Request) -> HealthResponse:
    service = _service(request)
    return HealthResponse(
        version=__version__,
        embedding_provider=service.settings.embedding_provider,
        llm_provider=service.settings.llm_provider,
        model=service.llm.model,
        documents=len(service.store.documents()),
        chunks=service.store.count(),
    )


@router.post("/ingest", response_model=IngestResponse, tags=["documents"])
async def ingest(request: Request, file: UploadFile = File(...)) -> IngestResponse:
    service = _service(request)
    data = await file.read()

    max_bytes = service.settings.max_upload_mb * 1024 * 1024
    if len(data) > max_bytes:
        raise HTTPException(413, f"File exceeds {service.settings.max_upload_mb} MB limit")
    if not data:
        raise HTTPException(400, "Empty file")

    try:
        added = service.ingest(file.filename or "upload", data)
    except UnsupportedFileType as exc:
        raise HTTPException(415, str(exc)) from exc

    if added == 0:
        raise HTTPException(422, "No extractable text found in the document")

    return IngestResponse(
        source=file.filename or "upload",
        chunks_added=added,
        total_chunks=service.store.count(),
        message=f"Indexed {added} chunk(s) from {file.filename}",
    )


@router.post("/query", response_model=QueryResponse, tags=["query"])
def query(request: Request, body: QueryRequest) -> QueryResponse:
    service = _service(request)
    answer, citations = service.query(body.question, body.top_k)
    return QueryResponse(answer=answer, citations=citations, model=service.llm.model)


@router.post("/query/stream", tags=["query"])
def query_stream(request: Request, body: QueryRequest) -> StreamingResponse:
    """Stream the answer token-by-token as Server-Sent Events.

    Emits ``citations`` first, then a series of ``token`` events, then ``done``.
    """
    service = _service(request)
    token_stream, citations = service.stream(body.question, body.top_k)

    def event_generator():
        payload = [c.model_dump() for c in citations]
        yield _sse("citations", {"citations": payload, "model": service.llm.model})
        for chunk in token_stream:
            yield _sse("token", {"text": chunk})
        yield _sse("done", {})

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/documents", response_model=DocumentsResponse, tags=["documents"])
def documents(request: Request) -> DocumentsResponse:
    service = _service(request)
    docs = service.store.documents()
    return DocumentsResponse(
        documents=[DocumentInfo(source=s, chunks=n) for s, n in sorted(docs.items())],
        total_chunks=service.store.count(),
    )


@router.delete("/documents", tags=["documents"])
def clear_documents(request: Request) -> dict[str, str]:
    _service(request).store.clear()
    return {"message": "Index cleared"}


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
