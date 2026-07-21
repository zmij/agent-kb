"""Thin wrapper around qdrant-client.

Keeps connection details, collection lifecycle and payload conventions in one
place so indexers and the MCP server don't repeat themselves.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from kb.config import get_settings


@dataclass
class SearchHit:
    id: str | int
    score: float
    payload: dict[str, Any]


def _client() -> QdrantClient:
    s = get_settings()
    return QdrantClient(
        host=s.qdrant_host,
        port=s.qdrant_http_port,
        grpc_port=s.qdrant_grpc_port,
        prefer_grpc=s.qdrant_prefer_grpc,
        # Default gRPC timeout is 5s. Bulk upserts (especially with
        # ``wait=True``, forcing server-side index sync) routinely exceed
        # that when multiple worktrees index concurrently or when Qdrant
        # is compacting. 60s leaves plenty of headroom without papering
        # over genuine failures.
        timeout=s.qdrant_client_timeout,
    )


class KBStore:
    """Thin wrapper around qdrant-client with per-worktree namespacing.

    Indexers and callers refer to "logical" collection names (e.g.
    ``my_project_kb``); the store transparently suffixes them with the
    current worktree's slug so concurrent indexing across worktrees never
    touches the same Qdrant collection. Override the slug via the
    ``KB_WORKTREE_SLUG`` env var.
    """

    def __init__(self, client: QdrantClient | None = None, slug: str | None = None) -> None:
        self.client = client or _client()
        self._slug = slug if slug is not None else get_settings().worktree_slug

    @property
    def slug(self) -> str:
        return self._slug

    def _qualified(self, logical_name: str) -> str:
        """Map a logical collection name to its per-worktree Qdrant name."""

        return f"{logical_name}_{self._slug}" if self._slug else logical_name

    # ------------------------------------------------------------------ collections

    def ensure_collection(self, name: str, dim: int) -> None:
        qname = self._qualified(name)
        existing = {c.name for c in self.client.get_collections().collections}
        if qname in existing:
            info = self.client.get_collection(qname)
            current_dim = info.config.params.vectors.size
            if current_dim != dim:
                raise RuntimeError(
                    f"Collection {qname!r} exists with dim {current_dim}, "
                    f"but embedding provider reports dim {dim}. "
                    "Drop the collection or use a different name."
                )
            return
        self.client.create_collection(
            collection_name=qname,
            vectors_config=qm.VectorParams(size=dim, distance=qm.Distance.COSINE),
        )

    def drop_collection(self, name: str) -> None:
        """Drop the collection. Accepts either a logical name (suffixed
        automatically) or a fully-qualified name (used as-is)."""

        qname = name if name.endswith(f"_{self._slug}") or not self._slug else self._qualified(name)
        self.client.delete_collection(collection_name=qname)

    def list_collections(self, all_worktrees: bool = False) -> list[dict[str, Any]]:
        """List collections. By default only those belonging to this worktree
        (matching the ``_<slug>`` suffix); pass ``all_worktrees=True`` to see
        everything in Qdrant."""

        suffix = f"_{self._slug}" if self._slug else ""
        out = []
        for c in self.client.get_collections().collections:
            if not all_worktrees and suffix and not c.name.endswith(suffix):
                continue
            info = self.client.get_collection(c.name)
            out.append(
                {
                    "name": c.name,
                    "logical_name": c.name[: -len(suffix)] if suffix and c.name.endswith(suffix) else c.name,
                    "points": info.points_count,
                    "dim": info.config.params.vectors.size,
                    "distance": info.config.params.vectors.distance.name,
                }
            )
        return out

    def count_by_source(self, collection: str, source: str) -> int | None:
        """Return point count where payload.source == ``source``, or None if the
        collection doesn't exist."""

        qname = self._qualified(collection)
        existing = {c.name for c in self.client.get_collections().collections}
        if qname not in existing:
            return None
        result = self.client.count(
            collection_name=qname,
            count_filter=qm.Filter(
                must=[
                    qm.FieldCondition(key="source", match=qm.MatchValue(value=source))
                ]
            ),
            exact=True,
        )
        return result.count

    # ------------------------------------------------------------------ points

    def upsert(
        self,
        collection: str,
        ids: Sequence[str | int],
        vectors: Sequence[Sequence[float]],
        payloads: Sequence[dict[str, Any]],
        *,
        wait: bool = True,
    ) -> None:
        """Upsert points. ``wait=False`` lets the server pipeline writes,
        which is much faster during bulk indexing — pair with a final
        ``flush()`` call to make sure everything has landed before
        returning."""

        points = [
            qm.PointStruct(id=i, vector=list(v), payload=p)
            for i, v, p in zip(ids, vectors, payloads, strict=True)
        ]
        self.client.upsert(
            collection_name=self._qualified(collection),
            points=points,
            wait=wait,
        )

    def delete_by_source(self, collection: str, source: str) -> None:
        """Delete every point in ``collection`` whose payload ``source`` matches.

        Used by the runner during a full re-index to start from an empty
        slate for that source.
        """

        qname = self._qualified(collection)
        existing = {c.name for c in self.client.get_collections().collections}
        if qname not in existing:
            return
        self.client.delete(
            collection_name=qname,
            points_selector=qm.FilterSelector(
                filter=qm.Filter(
                    must=[
                        qm.FieldCondition(
                            key="source", match=qm.MatchValue(value=source)
                        )
                    ]
                )
            ),
            wait=True,
        )

    def delete_by_path(self, collection: str, source: str, path: str) -> None:
        """Delete all chunks of ``source`` whose payload ``path`` matches.

        Used by the incremental runner to evict stale chunks for a single
        file before re-indexing it (or to remove chunks for a file that has
        been deleted from the source corpus).
        """

        qname = self._qualified(collection)
        existing = {c.name for c in self.client.get_collections().collections}
        if qname not in existing:
            return
        self.client.delete(
            collection_name=qname,
            points_selector=qm.FilterSelector(
                filter=qm.Filter(
                    must=[
                        qm.FieldCondition(key="source", match=qm.MatchValue(value=source)),
                        qm.FieldCondition(key="path", match=qm.MatchValue(value=path)),
                    ]
                )
            ),
            wait=True,
        )

    def enumerate_file_hashes(
        self, collection: str, source: str
    ) -> dict[str, str]:
        """Return ``{path: content_hash}`` for every distinct file currently
        indexed for ``source`` in ``collection``.

        Multiple chunks share the same (path, content_hash) — the value
        returned is whatever hash the first encountered chunk for that path
        carries. The runner uses this map to decide whether each source file
        needs re-embedding.

        Uses Qdrant's scroll API to iterate the collection in pages. Empty
        return when the collection doesn't exist yet (first-time index).
        """

        qname = self._qualified(collection)
        existing = {c.name for c in self.client.get_collections().collections}
        if qname not in existing:
            return {}

        result: dict[str, str] = {}
        next_offset = None
        while True:
            points, next_offset = self.client.scroll(
                collection_name=qname,
                scroll_filter=qm.Filter(
                    must=[
                        qm.FieldCondition(
                            key="source", match=qm.MatchValue(value=source)
                        )
                    ]
                ),
                with_payload=["path", "content_hash"],
                limit=256,
                offset=next_offset,
            )
            for p in points:
                payload = p.payload or {}
                path = payload.get("path")
                content_hash = payload.get("content_hash")
                if path and content_hash and path not in result:
                    result[path] = content_hash
            if next_offset is None:
                break
        return result

    def get(self, collection: str, point_id: str | int) -> dict[str, Any] | None:
        records = self.client.retrieve(
            collection_name=self._qualified(collection),
            ids=[point_id],
            with_payload=True,
            with_vectors=False,
        )
        if not records:
            return None
        r = records[0]
        return {"id": r.id, "payload": r.payload}

    def search(
        self,
        collection: str,
        vector: Sequence[float],
        top_k: int = 8,
        payload_filter: dict[str, Any] | None = None,
    ) -> list[SearchHit]:
        qfilter = None
        if payload_filter:
            qfilter = qm.Filter(
                must=[
                    qm.FieldCondition(key=k, match=qm.MatchValue(value=v))
                    for k, v in payload_filter.items()
                ]
            )
        response = self.client.query_points(
            collection_name=self._qualified(collection),
            query=list(vector),
            limit=top_k,
            query_filter=qfilter,
            with_payload=True,
        )
        return [
            SearchHit(id=p.id, score=float(p.score), payload=p.payload or {})
            for p in response.points
        ]
