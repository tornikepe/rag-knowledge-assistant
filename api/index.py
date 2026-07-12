"""Vercel serverless entry point.

Vercel's Python runtime serves the ASGI ``app`` exported here. We add the project
root to ``sys.path`` so the ``app`` package is importable from ``/api``.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app  # noqa: E402

__all__ = ["app"]
