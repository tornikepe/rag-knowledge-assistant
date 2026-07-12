"""FastAPI application entry point.

Builds the RAG service when the app is created (so it works even on serverless
platforms that don't run ASGI lifespan events), mounts the JSON API under ``/api``,
and serves the single-page chat UI from ``frontend/`` at the root.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api.routes import router
from app.config import Settings, get_settings
from app.core.service import RAGService, build_service

ROOT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT_DIR / "frontend"
SAMPLE_DOCS_DIR = ROOT_DIR / "data" / "sample_docs"


def _seed_sample_docs(service: RAGService) -> None:
    """Ingest bundled sample documents when the index is empty."""
    if service.store.count() > 0 or not SAMPLE_DOCS_DIR.exists():
        return
    for path in sorted(SAMPLE_DOCS_DIR.glob("*")):
        if path.is_file():
            try:
                service.ingest(path.name, path.read_bytes())
            except Exception:  # noqa: BLE001 — never let seeding break startup
                pass


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description="Retrieval-Augmented Generation API with citations.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.service = build_service(settings)
    if settings.seed_sample_docs:
        _seed_sample_docs(app.state.service)

    app.include_router(router)

    if FRONTEND_DIR.exists():
        app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

    return app


app = create_app()
