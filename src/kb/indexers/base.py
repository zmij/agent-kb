"""Indexer protocol."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator, Protocol, runtime_checkable


_KB_NAMESPACE = uuid.UUID("9c5b9b5c-7e3e-4b9a-9c8a-1f2a3b4c5d6e")


def stable_id(source: str, *parts: str) -> str:
    """UUIDv5 derived from (source, *parts). Stable across re-indexes."""

    return str(uuid.uuid5(_KB_NAMESPACE, "::".join((source, *parts))))


@dataclass
class ChunkRecord:
    id: str
    text: str
    payload: dict[str, Any] = field(default_factory=dict)


# Callback the runner passes to indexers for incremental indexing.
# Indexers call it for every source file with (relative_path, content_hash).
# A True return means "yes, (re)index this file"; False means "skip — the
# file is unchanged since the last index". Indexers MUST call the callback
# for every file they walk, even when skipping, so the runner can correctly
# distinguish unchanged files from deleted files (for orphan cleanup).
ShouldIndex = Callable[[str, str], bool]


@runtime_checkable
class Indexer(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def collection(self) -> str: ...

    def iter_chunks(
        self, *, should_index: ShouldIndex | None = None
    ) -> Iterator[ChunkRecord]: ...
