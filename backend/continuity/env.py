"""Load `.env` once, from wherever the process was started.

Secrets belong in a file that is gitignored, not in a shell history. `.env` is read at
the API entry point and by anything that needs a key directly; the engine never calls
this, because the engine never reads configuration at all.

**A real environment variable always wins.** Deployment sets variables directly, and a
stale `.env` left in a working tree must not override what the platform injected.
"""

from __future__ import annotations

import os
from pathlib import Path

_loaded = False

SEARCH_FROM = Path(__file__).resolve().parent.parent
"""`backend/`. Walks upward, so a `.env` at the repo root is found too."""


def load(*, override: bool = False) -> Path | None:
    """Read the nearest `.env`. Idempotent — later calls are free."""
    global _loaded
    if _loaded and not override:
        return None

    try:
        from dotenv import find_dotenv, load_dotenv
    except ImportError:
        _loaded = True
        return None

    path = find_dotenv(usecwd=True) or find_dotenv(str(SEARCH_FROM / ".env"))
    if path:
        load_dotenv(path, override=override)
    _loaded = True
    return Path(path) if path else None


def flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}
