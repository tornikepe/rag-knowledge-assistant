"""Ingest the bundled sample document into the index.

Usage:
    python scripts/ingest_sample.py [path/to/file ...]

With no arguments it ingests everything under ``data/sample_docs/``.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make ``app`` importable when run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.core.service import build_service  # noqa: E402

DEFAULT_DIR = Path(__file__).resolve().parent.parent / "data" / "sample_docs"


def main(paths: list[str]) -> None:
    service = build_service(get_settings())
    files = [Path(p) for p in paths] if paths else sorted(DEFAULT_DIR.glob("*"))
    if not files:
        print("No files to ingest.")
        return
    for path in files:
        added = service.ingest(path.name, path.read_bytes())
        print(f"  ✓ {path.name}: {added} chunk(s)")
    print(f"Index now holds {service.store.count()} chunk(s) across "
          f"{len(service.store.documents())} document(s).")


if __name__ == "__main__":
    main(sys.argv[1:])
