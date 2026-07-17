"""Provider-wiring tests for the Gemini LLM + embedding integrations.

These stay fully offline: the google-genai client is swapped for a fake, so no
network and no API key are needed. They verify our streaming, task-type, and
factory/fallback logic — the seams where the app meets the SDK.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.config import Settings
from app.core.embeddings import GeminiEmbeddings, build_embedding_provider
from app.core.llm import EchoLLM, GeminiLLM, build_llm_provider


# --- a minimal fake of the google-genai client -------------------------------
class _FakeChunk:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeEmbedding:
    def __init__(self, values: list[float]) -> None:
        self.values = values


class _FakeModels:
    def __init__(self, record: dict) -> None:
        self._record = record

    def generate_content_stream(self, *, model, contents, config):
        self._record["gen"] = {"model": model, "contents": contents, "config": config}
        # Include an empty chunk to prove GeminiLLM.stream skips it.
        for piece in ("Hello", " world", ""):
            yield _FakeChunk(piece)

    def embed_content(self, *, model, contents, config):
        self._record.setdefault("embed_calls", []).append(
            {"model": model, "contents": list(contents), "task_type": config.task_type}
        )
        # One deterministic, non-unit vector per input (so normalization is testable).
        return type(
            "Resp",
            (),
            {"embeddings": [_FakeEmbedding([float(len(t)), 1.0, 2.0]) for t in contents]},
        )()


class _FakeClient:
    last: _FakeClient | None = None

    def __init__(self, *, api_key: str) -> None:
        self.record: dict = {"api_key": api_key}
        self.models = _FakeModels(self.record)
        _FakeClient.last = self


@pytest.fixture
def fake_genai(monkeypatch):
    """Replace google.genai.Client with the fake and expose the last instance."""
    monkeypatch.setattr("google.genai.Client", _FakeClient)
    _FakeClient.last = None
    return _FakeClient


# --- LLM ---------------------------------------------------------------------
def test_gemini_llm_streams_and_skips_empty_chunks(fake_genai):
    llm = GeminiLLM("test-key", model="gemini-flash-latest", max_tokens=256, thinking_budget=0)
    assert llm.complete("SYSTEM", "USER") == "Hello world"

    rec = fake_genai.last.record
    assert rec["api_key"] == "test-key"
    assert rec["gen"]["model"] == "gemini-flash-latest"
    cfg = rec["gen"]["config"]
    assert cfg.system_instruction == "SYSTEM"
    assert cfg.max_output_tokens == 256
    # Thinking disabled -> a ThinkingConfig with a zero budget is attached.
    assert cfg.thinking_config is not None
    assert cfg.thinking_config.thinking_budget == 0


def test_build_llm_provider_gemini_without_key_falls_back_to_echo(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    settings = Settings(llm_provider="gemini")
    assert isinstance(build_llm_provider(settings), EchoLLM)


def test_build_llm_provider_gemini_with_key(fake_genai):
    settings = Settings(llm_provider="gemini", gemini_api_key="k")
    assert isinstance(build_llm_provider(settings), GeminiLLM)


# --- embeddings --------------------------------------------------------------
def test_gemini_embeddings_task_types_and_normalization(fake_genai):
    emb = GeminiEmbeddings("test-key", model="gemini-embedding-001", dim=3)

    docs = emb.embed_documents(["aa", "bbbb"])
    assert docs.shape == (2, 3)
    assert np.allclose(np.linalg.norm(docs, axis=1), 1.0)  # rows are L2-normalized

    query = emb.embed_query("hello")
    assert query.shape == (3,)
    assert np.isclose(np.linalg.norm(query), 1.0)

    calls = fake_genai.last.record["embed_calls"]
    assert calls[0]["task_type"] == "RETRIEVAL_DOCUMENT"
    assert calls[-1]["task_type"] == "RETRIEVAL_QUERY"


def test_gemini_embeddings_empty_input_is_shaped_zero(fake_genai):
    emb = GeminiEmbeddings("test-key", dim=3)
    assert emb.embed_documents([]).shape == (0, 3)


def test_build_embedding_provider_gemini_without_key_raises(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    settings = Settings(embedding_provider="gemini")
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        build_embedding_provider(settings)


def test_build_embedding_provider_gemini_with_key(fake_genai):
    settings = Settings(embedding_provider="gemini", gemini_api_key="k", gemini_embedding_dim=3)
    provider = build_embedding_provider(settings)
    assert isinstance(provider, GeminiEmbeddings)
    assert provider.dim == 3
