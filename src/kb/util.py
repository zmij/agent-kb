"""Shared utilities used across indexers and runner."""

from __future__ import annotations

import hashlib
from pathlib import Path


def file_content_hash(path: Path) -> str:
    """SHA-256 hex digest of a file's bytes.

    Used by the incremental index runner to detect whether a source file's
    content has changed since the last index. Embeddings dominate index
    time; hashing every file lets us skip the embedding step when a file
    is unchanged.
    """

    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
