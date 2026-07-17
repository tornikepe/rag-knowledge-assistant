"""Answer-generation LLM providers.

The RAG pipeline retrieves context; the LLM turns that context into a grounded,
citation-bearing answer. Three providers implement one interface:

* ``GeminiLLM`` — Google Gemini via the google-genai SDK, streamed. The recommended
  provider: Gemini's free tier runs real answers at no cost.
* ``AnthropicLLM`` — Claude via the official Anthropic SDK, with token streaming.
* ``EchoLLM`` — a deterministic offline stand-in that composes an answer from the
  retrieved context. It needs no API key, so the app (and its tests) run anywhere.
"""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from collections.abc import Iterator

from app.config import Settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are Peit, a sharp and friendly knowledge assistant. Answer the user's question "
    "using ONLY the numbered context passages provided. Write in a natural, conversational "
    "tone — clear and helpful, like a knowledgeable colleague, not a robot. Lead with a "
    "direct answer to the question, then add the supporting detail that matters. Use short "
    "paragraphs, and bullet points when they aid clarity; format with Markdown. Cite every "
    "claim with inline markers like [1] or [2] that map to the passages you used. If the "
    "passages don't contain the answer, say so honestly and suggest what the user could add. "
    "Never invent facts beyond the context."
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
    """Offline provider: a lightweight extractive answerer built from the retrieved
    context. It reads the numbered passages, picks the sentences most relevant to the
    question, and stitches them into a natural, cited answer — no API key required, so
    the app and its tests run anywhere. Set ``LLM_PROVIDER=gemini`` (free) or
    ``anthropic`` for real generation.
    """

    model = "echo"

    def stream(self, system: str, user: str) -> Iterator[str]:
        question = _extract_question(user)
        passages = _extract_passages(user)
        if not passages:
            yield (
                "I don't see anything about that in this chat's files yet. "
                "Try attaching a document, or rephrasing your question."
            )
            return

        picks = [(_tidy(text), marker) for text, marker in _relevant_sentences(question, passages, limit=4)]
        # Stream the answer in natural chunks so it reads as it arrives.
        yield _lead_in(question)
        if len(picks) == 1:
            text, marker = picks[0]
            yield f"{text} [{marker}]"
        else:
            for text, marker in picks:
                yield f"\n- {text} [{marker}]"
        closing = _closing(picks, passages)
        if closing:
            yield closing


class GeminiLLM(LLMProvider):
    """Google Gemini via the google-genai SDK, streamed.

    The recommended real provider: Gemini's free tier makes grounded answers cost
    nothing to run, and one ``GEMINI_API_KEY`` also powers ``GeminiEmbeddings``.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-flash-latest",
        max_tokens: int = 1024,
        thinking_budget: int | None = 0,
    ) -> None:
        from google import genai  # lazy import so other modes need no google-genai dep
        from google.genai import types

        self._types = types
        self._client = genai.Client(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens
        self.thinking_budget = thinking_budget

    def stream(self, system: str, user: str) -> Iterator[str]:
        types = self._types
        config_kwargs: dict = {
            "system_instruction": system,
            "max_output_tokens": self.max_tokens,
        }
        # Answering from retrieved passages needs no chain-of-thought; disabling
        # "thinking" on flash models keeps replies fast and stops reasoning tokens
        # from consuming the max_output_tokens budget (which can otherwise return an
        # empty answer). Guarded so older SDKs without ThinkingConfig still work.
        thinking_config = getattr(types, "ThinkingConfig", None)
        if thinking_config is not None and self.thinking_budget is not None:
            config_kwargs["thinking_config"] = thinking_config(
                thinking_budget=self.thinking_budget
            )
        config = types.GenerateContentConfig(**config_kwargs)
        for chunk in self._client.models.generate_content_stream(
            model=self.model, contents=user, config=config
        ):
            if chunk.text:
                yield chunk.text


class AnthropicLLM(LLMProvider):
    """Claude via the Anthropic Messages API, streamed."""

    def __init__(self, api_key: str, model: str = "claude-opus-4-8", max_tokens: int = 1024) -> None:
        try:
            import anthropic  # lazy import: only needed when LLM_PROVIDER=anthropic
        except ModuleNotFoundError as exc:  # pragma: no cover - optional dependency
            raise ModuleNotFoundError(
                "LLM_PROVIDER=anthropic needs the Anthropic SDK. Install it with "
                "`pip install anthropic`. The default free provider is Gemini "
                "(LLM_PROVIDER=gemini), which needs no extra install."
            ) from exc

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
    """Factory: choose an LLM provider from settings.

    A misconfigured provider must never take the whole app down: this runs at
    import time on serverless (see ``app.main``), so raising here would 500 every
    route — including the landing page and offline ``echo`` mode. When a cloud
    provider is requested but its key is missing, we log a warning and fall back to
    ``EchoLLM`` so the site stays up; set the provider's key to restore real answers.
    """
    provider = settings.llm_provider.lower()
    if provider == "gemini":
        if not settings.gemini_api_key:
            logger.warning(
                "LLM_PROVIDER=gemini but GEMINI_API_KEY is not set — falling back to "
                "offline 'echo' answers. Set GEMINI_API_KEY to enable Gemini."
            )
            return EchoLLM()
        return GeminiLLM(
            settings.gemini_api_key,
            settings.gemini_model,
            settings.max_tokens,
            settings.gemini_thinking_budget,
        )
    if provider == "anthropic":
        if not settings.anthropic_api_key:
            logger.warning(
                "LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is not set — falling "
                "back to offline 'echo' answers. Set ANTHROPIC_API_KEY to enable Claude."
            )
            return EchoLLM()
        return AnthropicLLM(
            settings.anthropic_api_key, settings.anthropic_model, settings.max_tokens
        )
    if provider == "echo":
        return EchoLLM()
    logger.warning(
        "Unknown LLM_PROVIDER=%r — falling back to offline 'echo' answers.",
        settings.llm_provider,
    )
    return EchoLLM()


# --- helpers for the offline EchoLLM ---------------------------------------
_STOPWORDS = frozenset(
    "a an the this that these those is are was were be been being do does did of to in on "
    "for with and or but if then else how what why when where who which does can could should "
    "would will about into over under from as at by it its their your our my his her they we you "
    "i me us them he she him".split()
)


def _extract_question(user: str) -> str:
    m = re.search(r"Question:\s*(.+?)\s*(?:\n\n|$)", user, re.S)
    return m.group(1).strip() if m else ""


def _extract_passages(user: str) -> list[tuple[int, str, str]]:
    """Parse the numbered ``[n] (source: X)\\n text`` blocks from the prompt."""
    body = user
    m = re.search(r"Context passages:\s*(.*?)\s*Question:", user, re.S)
    if m:
        body = m.group(1)
    out: list[tuple[int, str, str]] = []
    for block in re.split(r"\n\s*\n(?=\[\d+\])", body):
        hm = re.match(r"\s*\[(\d+)\]\s*(?:\(source:[^)]*\))?\s*\n?(.*)", block, re.S)
        if hm and hm.group(2).strip():
            out.append((int(hm.group(1)), "", hm.group(2).strip()))
    return out


def _clean_lines(text: str) -> list[str]:
    """Drop markdown headings, strip bullet/emphasis marks, keep content lines."""
    lines: list[str] = []
    for raw in text.split("\n"):
        line = raw.strip()
        if not line or line.startswith("#"):  # blank or markdown heading
            continue
        line = re.sub(r"^[-*+]\s+", "", line)       # list bullets
        line = re.sub(r"\*\*|__|`", "", line)       # bold / code emphasis
        line = re.sub(r"\s+", " ", line).strip()
        if line:
            lines.append(line)
    return lines


def _split_sentences(text: str) -> list[str]:
    """Extract clean, self-contained sentences, skipping chunk-boundary fragments."""
    out: list[str] = []
    for line in _clean_lines(text):
        for part in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", line):
            s = part.strip(" -–—•*:")
            if not (30 <= len(s) <= 320):
                continue
            # Skip fragments that start mid-word (chunking cuts on character count).
            if not (s[:1].isupper() or s[:1].isdigit()):
                continue
            if s.count("-") > 4 or s.count("|") > 1:  # leftover list/table noise
                continue
            out.append(s)
    return out


def _keywords(question: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", question.lower())
    return {w for w in words if len(w) > 2 and w not in _STOPWORDS}


def _relevant_sentences(
    question: str, passages: list[tuple[int, str, str]], limit: int = 4
) -> list[tuple[str, int]]:
    """Rank sentences across passages by keyword overlap with the question."""
    keys = _keywords(question)
    scored: list[tuple[float, int, int, str, int]] = []  # (score, passage_rank, order, text, marker)
    order = 0
    for rank, (marker, _src, text) in enumerate(passages):
        for sentence in _split_sentences(text):
            overlap = len(keys & _keywords(sentence))
            # Prefer complete sentences (chunking can truncate the last one) and, all
            # else equal, earlier passages (which have the better retrieval rank).
            complete = 0.6 if sentence[-1:] in ".!?" else 0.0
            score = overlap + complete - rank * 0.1
            scored.append((score, rank, order, sentence, marker))
            order += 1

    if not scored:
        # No usable sentences — echo the top passage's opening as a last resort.
        first_marker, _s, first_text = passages[0]
        snippet = _split_sentences(first_text) or [first_text[:200].strip()]
        return [(snippet[0], first_marker)]

    # Take the highest-scoring sentences, de-duplicating near-identical ones that
    # overlapping chunks repeat.
    seen: set[str] = set()
    picked: list[tuple[float, int, int, str, int]] = []
    for item in sorted(scored, key=lambda s: (-s[0], s[1], s[2])):
        norm = re.sub(r"\W+", " ", item[3].lower()).strip()
        if norm in seen:
            continue
        seen.add(norm)
        picked.append(item)
        if len(picked) >= limit:
            break
    # Restore reading order (by passage rank, then position) for a coherent answer.
    picked.sort(key=lambda s: (s[1], s[2]))
    return [(text, marker) for _sc, _r, _o, text, marker in picked]


def _tidy(sentence: str) -> str:
    """Signal chunk-truncated sentences with an ellipsis so they read intentionally."""
    if sentence and sentence[-1] not in ".!?":
        return sentence.rstrip(" ,;:-–—") + "…"
    return sentence


def _lead_in(question: str) -> str:
    q = question.lower()
    if any(w in q for w in ("summar", "overview", "tl;dr", "key point", "takeaway")):
        return "Here's the gist, based on the files in this chat:\n"
    if q.startswith(("how", "in what way")):
        return "Here's how your documents explain it:\n"
    if q.startswith("why"):
        return "Here's what your documents point to:\n"
    if q.startswith(("who", "what", "which", "when", "where")):
        return "Here's what I found in your documents:\n"
    return "Based on the documents in this chat:\n"


def _closing(picks: list[tuple[str, int]], passages: list[tuple[int, str, str]]) -> str:
    used = {m for _t, m in picks}
    if len(passages) > len(used):
        return "\n\nWant more detail? Ask a follow-up and I'll pull from the other passages too."
    return ""
