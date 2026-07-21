"""MCP server exposing the knowledge base over stdio.

Tools:

* ``kb_search`` — semantic search across one or all collections.
* ``kb_get`` — fetch a single chunk by id.
* ``kb_list_sources`` — enumerate collections and their populations.
* ``kb_reindex`` — re-run an indexer.

The server is intentionally small. All retrieval shapes (e.g. structured
``term_lookup``) get their own tools as we add them, rather than being
overloaded onto ``kb_search``.

The server name is derived from the consuming project's ``kb.yaml``
(``mcp_name``, default ``<project>-kb``) so that multiple projects on one
machine register distinct servers.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from kb.config import ConfigError, get_config
from kb.embedding import get_provider
from kb.indexers import build, known_sources
from kb.qdrant_client import KBStore
from kb.runner import run_index


def _server_name() -> str:
    try:
        return get_config().server_name
    except ConfigError:
        # No kb.yaml yet — still boot so the tools can report the problem.
        return "agent-kb"


mcp = FastMCP(_server_name())


def _snippet(text: str, limit: int = 280) -> str:
    text = text.strip().replace("\n", " ")
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _hit_to_dict(hit: Any) -> dict[str, Any]:
    payload = hit.payload or {}
    return {
        "id": str(hit.id),
        "score": round(hit.score, 4),
        "source": payload.get("source"),
        "doc_uri": payload.get("doc_uri"),
        "title": payload.get("title"),
        "heading": payload.get("heading_label"),
        "tags": payload.get("tags") or [],
        "snippet": _snippet(payload.get("content") or ""),
    }


@mcp.tool()
def kb_search(
    query: str,
    source: str | None = None,
    top_k: int = 8,
) -> dict[str, Any]:
    """Semantic search across indexed knowledge.

    Args:
        query: Natural-language question or keyword phrase.
        source: Optional source name (see ``kb_list_sources``) to filter
            results. If omitted, searches every configured collection.
        top_k: Maximum hits to return per collection.
    """

    provider = get_provider()
    store = KBStore()
    vec = provider.embed_query(query)

    known = known_sources()
    if source:
        if source not in known:
            return {"error": f"Unknown source: {source!r}", "known": known}
        collections = [build(source).collection]
    else:
        collections = sorted({build(name).collection for name in known})

    existing = {c["logical_name"] for c in store.list_collections()}
    payload_filter = {"source": source} if source else None
    results: list[dict[str, Any]] = []
    for coll in collections:
        if coll not in existing:
            continue
        hits = store.search(coll, vec, top_k=top_k, payload_filter=payload_filter)
        results.extend(_hit_to_dict(h) for h in hits)

    results.sort(key=lambda r: r["score"], reverse=True)
    return {"query": query, "hits": results[:top_k]}


@mcp.tool()
def kb_get(id: str, source: str | None = None) -> dict[str, Any]:
    """Fetch the full text and payload of a chunk by id.

    Args:
        id: The chunk id returned by ``kb_search``.
        source: Optional source hint to scope which collection to look in.
            If omitted, every known collection is checked.
    """

    store = KBStore()
    known = known_sources()
    if source:
        if source not in known:
            return {"error": f"Unknown source: {source!r}", "known": known}
        collections = [build(source).collection]
    else:
        collections = sorted({build(name).collection for name in known})

    existing = {c["logical_name"] for c in store.list_collections()}
    for coll in collections:
        if coll not in existing:
            continue
        rec = store.get(coll, id)
        if rec:
            return {"collection": coll, **rec}
    return {"error": f"No chunk with id {id!r} in {collections}"}


@mcp.tool()
def kb_list_sources() -> dict[str, Any]:
    """List configured sources and the state of their Qdrant collections."""

    store = KBStore()
    populations = {c["logical_name"]: c for c in store.list_collections()}
    sources = []
    for name in known_sources():
        indexer = build(name)
        coll = populations.get(indexer.collection)
        per_source = store.count_by_source(indexer.collection, name)
        sources.append(
            {
                "source": name,
                "collection": indexer.collection,
                "indexed": coll is not None,
                "points": per_source,
                "dim": (coll or {}).get("dim"),
            }
        )
    return {"sources": sources, "worktree_slug": store.slug}


@mcp.tool()
def kb_reindex(source: str) -> dict[str, Any]:
    """Re-run an indexer.

    Args:
        source: Indexer name from ``kb_list_sources``.
    """

    if source not in known_sources():
        return {"error": f"Unknown source: {source!r}", "known": known_sources()}
    result = run_index(source)
    return {
        "source": result.source,
        "collection": result.collection,
        "upserted": result.upserted,
        "embedding_provider": result.embedding_provider,
    }


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
