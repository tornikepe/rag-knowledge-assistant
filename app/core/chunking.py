"""Text chunking.

A retriever is only as good as its chunks: too large and irrelevant text dilutes
the context; too small and you lose the surrounding meaning. This splitter targets a
character budget, prefers to break on paragraph/sentence boundaries, and keeps a small
overlap so a fact that straddles a boundary still lands whole in at least one chunk.
"""

from __future__ import annotations

import re

# Split points, from strongest (paragraph) to weakest (space).
_SEPARATORS = ["\n\n", "\n", ". ", " "]


def _split_keep(text: str, separator: str) -> list[str]:
    if separator == "":
        return list(text)
    parts = text.split(separator)
    # Re-attach the separator to every part except the last so joins reconstruct text.
    return [p + separator for p in parts[:-1]] + parts[-1:]


def _recursive_split(text: str, chunk_size: int, separators: list[str]) -> list[str]:
    if len(text) <= chunk_size:
        return [text]
    if not separators:
        # No separator left — hard-split by size.
        return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]

    separator, *rest = separators
    pieces = _split_keep(text, separator)

    chunks: list[str] = []
    buffer = ""
    for piece in pieces:
        if len(piece) > chunk_size:
            # A single piece is too big — flush and recurse with a finer separator.
            if buffer:
                chunks.append(buffer)
                buffer = ""
            chunks.extend(_recursive_split(piece, chunk_size, rest))
        elif len(buffer) + len(piece) <= chunk_size:
            buffer += piece
        else:
            if buffer:
                chunks.append(buffer)
            buffer = piece
    if buffer:
        chunks.append(buffer)
    return chunks


def chunk_text(text: str, chunk_size: int = 900, overlap: int = 150) -> list[str]:
    """Split ``text`` into overlapping chunks of roughly ``chunk_size`` characters.

    Args:
        text: The document text.
        chunk_size: Target maximum characters per chunk.
        overlap: Characters of the previous chunk to prepend to the next one.

    Returns:
        A list of non-empty chunk strings.
    """
    text = re.sub(r"[ \t]+", " ", text or "").strip()
    if not text:
        return []
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    base_chunks = _recursive_split(text, chunk_size, _SEPARATORS)
    base_chunks = [c.strip() for c in base_chunks if c.strip()]
    if overlap == 0 or len(base_chunks) <= 1:
        return base_chunks

    # Add a tail of the previous chunk to the head of each subsequent chunk.
    overlapped: list[str] = [base_chunks[0]]
    for prev, current in zip(base_chunks, base_chunks[1:]):
        tail = prev[-overlap:].lstrip()
        overlapped.append(f"{tail} {current}".strip())
    return overlapped
