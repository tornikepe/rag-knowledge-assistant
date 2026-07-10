"""Answer-generation LLM providers.

The RAG pipeline retrieves context; the LLM turns that context into a grounded,
citation-bearing answer. Two providers implement one interface:

* ``AnthropicLLM`` — Claude via the official Anthropic SDK, with token streaming.
* ``EchoLLM`` — a deterministic offline stand-in that composes an answer from the
  retrieved context. It needs no API key, so the app (and its tests) run anywhere.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections.abc import Iterator

from app.config import Settings

SYSTEM_PROMPT = (
    "You are a precise knowledge assistant. Answer the user's question using ONLY the "
    "numbered context passages provided. Cite the passages you rely on with inline "
    "markers like [1] or [2]. If the answer is not contained in the context, say so "
    "plainly instead of guessing. Be concise and factual."
)


class LLMProvider(ABC):
    """Generates an answer from a fully-formed prompt."""

    model: str

    @abstractmethod
    def stream(self, system: str, user: str) -> Iterator[str]:
        """Yield the answer as a stream of text chunks."""

    def complete(self, system: str, user: str) -> str:
        """Return the full answer as a single string."""
        return "".join(self.stream(system, user))


class EchoLLM(LLMProvider):
    """Offline provider: extractive answer built from the context. No API key needed."""

    model = "echo"

    def stream(self, system: str, user: str) -> Iterator[str]:
        # The user prompt embeds the numbered context; surface passage [1] as the
        # grounded answer so the end-to-end flow (and citations) is demonstrable offline.
        passage = _first_context_passage(user)
        if passage:
            yield "**Based on the retrieved context:**\n\n"
            yield f"{passage} [1]\n\n"
            yield "_Offline demo answer — set `LLM_PROVIDER=anthropic` to get Claude-generated responses._"
        else:
            yield "I couldn't find anything relevant in the indexed documents."


class AnthropicLLM(LLMProvider):
    """Claude via the Anthropic Messages API, streamed."""

    def __init__(self, api_key: str, model: str = "claude-opus-4-8", max_tokens: int = 1024) -> None:
        import anthropic  # lazy import so `echo` mode needs no anthropic dependency

        self._client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens

    def stream(self, system: str, user: str) -> Iterator[str]:
        with self._client.messages.stream(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        ) as stream:
            yield from stream.text_stream


def build_llm_provider(settings: Settings) -> LLMProvider:
    """Factory: choose an LLM provider from settings."""
    provider = settings.llm_provider.lower()
    if provider == "anthropic":
        if not settings.anthropic_api_key:
            raise ValueError(
                "LLM_PROVIDER=anthropic requires ANTHROPIC_API_KEY. "
                "Set it in .env, or use LLM_PROVIDER=echo for offline mode."
            )
        return AnthropicLLM(
            settings.anthropic_api_key, settings.anthropic_model, settings.max_tokens
        )
    if provider == "echo":
        return EchoLLM()
    raise ValueError(f"Unknown LLM_PROVIDER: {settings.llm_provider!r}")


# --- helpers for the offline EchoLLM ---------------------------------------
def _first_context_passage(user: str) -> str:
    """Pull the text of the top-ranked passage out of the numbered prompt."""
    if "[1]" not in user:
        return ""
    after = user.split("[1]", 1)[1]
    for terminator in ("\n[2]", "\n\nQuestion:", "\nQuestion:"):
        if terminator in after:
            after = after.split(terminator, 1)[0]
    # Drop the "(source: filename)" line the prompt prepends to each passage.
    after = re.sub(r"^\s*\(source:[^)]*\)\s*", "", after)
    return after.strip().strip(":").strip()
