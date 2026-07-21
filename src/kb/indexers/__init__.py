"""Source indexers.

Each indexer is a small object that knows how to walk a corpus and emit
:class:`ChunkRecord` items. The CLI/MCP layer takes care of embedding and
upserting; indexers stay free of Qdrant and embedding-model concerns.

Which sources exist is *project configuration* (``kb.yaml`` at the
consuming repo's root), not code: :func:`build` instantiates the right
indexer type for a configured source. ``TYPES`` maps the config ``type:``
field to an indexer class; ``REGISTRY`` holds explicit overrides (tests
inject scoped indexers there — entries win over configured sources).
"""

from __future__ import annotations

from typing import Callable

from kb.config import KBConfig, SourceConfig, get_config, get_settings
from kb.indexers.base import ChunkRecord, Indexer
from kb.indexers.make_targets import MakeTargetsIndexer
from kb.indexers.markdown_docs import MarkdownDocsIndexer
from kb.indexers.ontology import OntologyIndexer

TYPES: dict[str, type] = {
    "markdown": MarkdownDocsIndexer,
    "ontology": OntologyIndexer,
    "make_targets": MakeTargetsIndexer,
}

# Explicit source-name → zero-arg factory overrides. Entries here shadow
# configured sources of the same name.
REGISTRY: dict[str, Callable[[], Indexer]] = {}


def _from_config(name: str, src: SourceConfig, config: KBConfig) -> Indexer:
    repo_root = get_settings().repo_root
    collection = src.collection or config.collection
    if src.type == "markdown":
        return MarkdownDocsIndexer(
            name=name,
            collection=collection,
            root=repo_root / (src.root or "."),
            repo_root=repo_root,
            exclude=src.exclude,
            uri_prefix=src.uri_prefix,
            lang=src.lang,
        )
    if src.type == "ontology":
        return OntologyIndexer(
            root=repo_root / (src.root or "."),
            name=name,
            collection=collection,
            repo_root=repo_root,
        )
    if src.type == "make_targets":
        return MakeTargetsIndexer(
            name=name,
            collection=collection,
            files=src.files or ["Makefile"],
            repo_root=repo_root,
        )
    known = ", ".join(sorted(TYPES))
    raise KeyError(f"Source {name!r} has unknown type {src.type!r}; known: {known}")


def known_sources(config: KBConfig | None = None) -> list[str]:
    config = config or get_config()
    return sorted(set(config.sources) | set(REGISTRY))


def build(name: str, config: KBConfig | None = None) -> Indexer:
    if name in REGISTRY:
        return REGISTRY[name]()
    config = config or get_config()
    try:
        src = config.sources[name]
    except KeyError as e:
        known = ", ".join(known_sources(config))
        raise KeyError(f"Unknown source {name!r}; known: {known}") from e
    return _from_config(name, src, config)


__all__ = [
    "ChunkRecord",
    "Indexer",
    "REGISTRY",
    "TYPES",
    "build",
    "known_sources",
]
