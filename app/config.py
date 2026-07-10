"""Application configuration.

All settings are read from environment variables (or a local ``.env`` file) via
``pydantic-settings``. The defaults are chosen so the project runs end-to-end with
**zero API keys** (``EMBEDDING_PROVIDER=hash`` + ``LLM_PROVIDER=echo``), and switches
to real models by setting the provider + key envs. See ``.env.example``.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- App ---
    app_name: str = "RAG Knowledge Assistant"
    environment: str = "development"
    cors_origins: list[str] = ["*"]

    # --- Storage (the vector index is persisted here) ---
    storage_dir: Path = Path("storage")

    # --- Chunking / retrieval ---
    chunk_size: int = 900          # target characters per chunk
    chunk_overlap: int = 150       # overlapping characters between chunks
    top_k: int = 4                 # chunks retrieved per query
    max_upload_mb: int = 20

    # --- Embeddings ---
    # "openai"  -> OpenAI text-embedding-3-small  (needs OPENAI_API_KEY)
    # "hash"    -> deterministic offline embeddings (no key; for demos / CI)
    embedding_provider: str = "hash"
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 256       # only used by the "hash" provider
    openai_api_key: str | None = None

    # --- LLM (answer generation) ---
    # "anthropic" -> Claude via the Anthropic SDK (needs ANTHROPIC_API_KEY)
    # "echo"      -> deterministic offline answer (no key; for demos / CI)
    llm_provider: str = "echo"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-opus-4-8"
    max_tokens: int = 1024

    @property
    def index_dir(self) -> Path:
        return self.storage_dir / "index"


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()
