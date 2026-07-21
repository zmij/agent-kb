"""Embedding backends.

Backends implement :class:`EmbeddingProvider`. Pick one with
:func:`get_provider`, which respects ``KB_EMBED_BACKEND``.
"""

from __future__ import annotations

from typing import Iterable, Protocol, Sequence, runtime_checkable

from kb.config import get_settings


@runtime_checkable
class EmbeddingProvider(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def dim(self) -> int: ...

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


def get_provider(backend: str | None = None) -> EmbeddingProvider:
    backend = backend or get_settings().kb_embed_backend
    if backend == "fastembed":
        from kb.embedding.fastembed_backend import FastEmbedProvider

        return FastEmbedProvider()
    if backend == "ollama":
        from kb.embedding.ollama_backend import OllamaProvider

        return OllamaProvider()
    raise ValueError(
        f"Unknown KB_EMBED_BACKEND={backend!r}; expected 'fastembed' or 'ollama'"
    )


__all__ = ["EmbeddingProvider", "get_provider"]
