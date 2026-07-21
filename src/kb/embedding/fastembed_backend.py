"""fastembed-based embedding provider (CPU, ONNX, no API keys)."""

from __future__ import annotations

from functools import cached_property
from typing import Sequence

from kb.config import get_settings


class FastEmbedProvider:
    def __init__(self, model_name: str | None = None) -> None:
        self._model_name = model_name or get_settings().kb_fastembed_model

    @property
    def name(self) -> str:
        return f"fastembed:{self._model_name}"

    @cached_property
    def _model(self):
        from fastembed import TextEmbedding

        return TextEmbedding(model_name=self._model_name)

    @cached_property
    def dim(self) -> int:
        # fastembed exposes dimension via the model description list.
        from fastembed import TextEmbedding

        for desc in TextEmbedding.list_supported_models():
            if desc["model"] == self._model_name:
                return int(desc["dim"])
        # Fall back to embedding a probe string.
        probe = next(iter(self._model.embed(["dim-probe"])))
        return len(probe)

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        return [list(map(float, v)) for v in self._model.embed(list(texts))]

    def embed_query(self, text: str) -> list[float]:
        # fastembed's query_embed exists for retrieval-tuned models; fall back
        # to plain embed when unavailable.
        embed = getattr(self._model, "query_embed", self._model.embed)
        vec = next(iter(embed([text])))
        return list(map(float, vec))
