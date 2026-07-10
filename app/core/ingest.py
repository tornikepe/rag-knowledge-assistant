"""Document loading — turn raw uploaded bytes into clean text."""

from __future__ import annotations

import io
from pathlib import Path


class UnsupportedFileType(ValueError):
    pass


SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md", ".markdown", ".text"}


def extract_text(filename: str, data: bytes) -> str:
    """Extract plain text from ``data`` based on the file extension.

    Supports PDF (via pypdf) and UTF-8 text/markdown. Raises ``UnsupportedFileType``
    for anything else.
    """
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf(data)
    if suffix in SUPPORTED_EXTENSIONS:
        return data.decode("utf-8", errors="replace")
    raise UnsupportedFileType(
        f"Unsupported file type: {suffix or '(none)'}. "
        f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
    )


def _extract_pdf(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    pages = [(page.extract_text() or "") for page in reader.pages]
    return "\n\n".join(pages)
