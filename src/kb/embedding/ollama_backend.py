"""Ollama-served embedding provider.

Implemented against the ``/api/embeddings`` endpoint. Activate by setting
``KB_EMBED_BACKEND=ollama`` and ensuring an Ollama daemon is reachable at
``KB_OLLAMA_URL`` with the chosen model pulled.
"""

from __future__ import annotations

from functools import cached_property
from typing import Sequence

import httpx

from kb.config import get_settings


class OllamaProvider:
    def __init__(self, base_url: str | None = None, model: str | None = None) -> None:
        s = get_settings()
        self._base_url = (base_url or s.kb_ollama_url).rstrip("/")
        self._model = model or s.kb_ollama_model
        self._client = httpx.Client(timeout=60.0)

    @property
    def name(self) -> str:
        return f"ollama:{self._model}"

    @cached_property
    def dim(self) -> int:
        return len(self.embed_query("dim-probe"))

    def _embed_one(self, text: str) -> list[float]:
        r = self._client.post(
            f"{self._base_url}/api/embeddings",
            json={"model": self._model, "prompt": text},
        )
        r.raise_for_status()
        return [float(x) for x in r.json()["embedding"]]

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed_one(text)
