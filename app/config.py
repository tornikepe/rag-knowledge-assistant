"""Application configuration.

All settings are read from environment variables (or a local ``.env`` file) via
``pydantic-settings``. The defaults are chosen so the project runs end-to-end with
**zero API keys** (``EMBEDDING_PROVIDER=hash`` + ``LLM_PROVIDER=echo``), and switches
to real models by setting the provider + key envs. See ``.env.example``.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Vercel's filesystem is read-only except for /tmp, and serverless instances are
# ephemeral. On Vercel we therefore write the index to /tmp and seed the bundled
# sample document at startup so the live demo is queryable out of the box.
_ON_VERCEL = bool(os.getenv("VERCEL"))


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
    storage_dir: Path = Path("/tmp/storage") if _ON_VERCEL else Path("storage")

    # Documents are scoped per chat (users upload into a specific conversation),
    # so there is no shared global corpus to seed.
    seed_sample_docs: bool = False

    # --- Chunking / retrieval ---
    chunk_size: int = 900          # target characters per chunk
    chunk_overlap: int = 150       # overlapping characters between chunks
    top_k: int = 4                 # chunks retrieved per query
    max_upload_mb: int = 20

    # --- Embeddings ---
    # "gemini"  -> Google Gemini embeddings  (needs GEMINI_API_KEY; free tier)
    # "openai"  -> OpenAI text-embedding-3-small  (needs OPENAI_API_KEY)
    # "hash"    -> deterministic offline embeddings (no key; for demos / CI)
    embedding_provider: str = "hash"
    gemini_embedding_model: str = "gemini-embedding-001"  # used by the "gemini" provider
    gemini_embedding_dim: int = 768        # Gemini output dimensionality (128–3072)
    embedding_model: str = "text-embedding-3-small"  # used by the "openai" provider
    embedding_dim: int = 256               # only used by the "hash" provider
    openai_api_key: str | None = None

    # --- LLM (answer generation) ---
    # "gemini"    -> Gemini via the google-genai SDK (needs GEMINI_API_KEY; free tier)
    # "anthropic" -> Claude via the Anthropic SDK (needs ANTHROPIC_API_KEY)
    # "echo"      -> deterministic offline answer (no key; for demos / CI)
    llm_provider: str = "echo"
    gemini_model: str = "gemini-flash-latest"
    # Gemini "thinking" budget: 0 disables it (fast + cheap — ideal for grounded RAG
    # answers on flash models), -1 lets the model decide. Only used by the gemini LLM.
    gemini_thinking_budget: int = 0
    # Retries for transient Gemini errors (503 overloaded / 429 rate-limited / 500),
    # with exponential backoff. Keeps the free tier resilient. Used by both LLM + embeddings.
    gemini_max_retries: int = 3
    anthropic_model: str = "claude-opus-4-8"
    max_tokens: int = 1024

    # A single free Gemini key powers both the LLM and the embeddings above.
    gemini_api_key: str | None = None
    anthropic_api_key: str | None = None

    # --- OAuth (real Google / GitHub sign-in) ---
    # Enabled per-provider only when both id + secret are set; otherwise the UI
    # falls back to demo login. See README → "Real Google / GitHub OAuth".
    google_client_id: str | None = None
    google_client_secret: str | None = None
    github_client_id: str | None = None
    github_client_secret: str | None = None
    session_secret: str = "dev-insecure-change-me"  # set a strong value in production
    # Exact public base URL for OAuth redirects, e.g. https://your-app.vercel.app
    # (must match the provider's registered redirect URI). Derived from the request
    # when unset.
    oauth_redirect_base: str | None = None

    # --- Email (sign-up verification codes) ---
    # When SMTP is configured the sign-up flow emails a 6-digit code; otherwise the
    # code is returned to the client as a demo fallback so the flow still works.
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None  # defaults to smtp_user when unset
    smtp_starttls: bool = True

    @property
    def email_enabled(self) -> bool:
        return bool(self.smtp_host and self.smtp_user and self.smtp_password)

    @property
    def index_dir(self) -> Path:
        return self.storage_dir / "index"


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()
