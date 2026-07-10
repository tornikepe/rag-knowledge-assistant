"""Shared pytest fixtures.

Every test runs in fully offline mode (hash embeddings + echo LLM) against a
throwaway storage directory, so the suite needs no API keys and no network.
"""

from __future__ import annotations

import pytest

from app.config import Settings
from app.core.service import RAGService, build_service


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        storage_dir=tmp_path / "storage",
        embedding_provider="hash",
        embedding_dim=128,
        llm_provider="echo",
        chunk_size=300,
        chunk_overlap=40,
        top_k=3,
    )


@pytest.fixture
def service(settings) -> RAGService:
    return build_service(settings)


@pytest.fixture
def client(settings, monkeypatch):
    """A FastAPI TestClient wired to the offline settings."""
    from fastapi.testclient import TestClient

    import app.main as main_module

    monkeypatch.setattr(main_module, "get_settings", lambda: settings)
    app = main_module.create_app()
    with TestClient(app) as test_client:
        yield test_client
