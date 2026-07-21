"""``kb`` command-line entrypoint."""

from __future__ import annotations

import json
import sys

import click

from kb.config import ConfigError
from kb.embedding import get_provider
from kb.indexers import build, known_sources
from kb.qdrant_client import KBStore
from kb.runner import run_index


@click.group()
def main() -> None:
    """Qdrant-backed knowledge base for LLM agents.

    Sources are declared in the consuming repo's kb.yaml; see
    kb.example.yaml in the agent-kb repository for the format.
    """


@main.command("sources")
def cmd_sources() -> None:
    """List configured sources and Qdrant collection populations (this worktree only)."""
    store = KBStore()
    populations = {c["logical_name"]: c for c in store.list_collections()}
    click.echo(f"(worktree slug: {store.slug})")
    rows: list[tuple[str, str, str, str]] = []
    for name in known_sources():
        ix = build(name)
        coll = populations.get(ix.collection)
        per_source = store.count_by_source(ix.collection, name)
        rows.append(
            (
                name,
                ix.collection,
                str(per_source) if per_source is not None else "—",
                str(coll["dim"]) if coll else "—",
            )
        )
    if not rows:
        click.echo("(no sources configured — add them to kb.yaml)")
        return
    width_src = max(len("source"), *(len(r[0]) for r in rows))
    width_coll = max(len("collection"), *(len(r[1]) for r in rows))
    click.echo(f"{'source'.ljust(width_src)}  {'collection'.ljust(width_coll)}  points  dim")
    click.echo(f"{'-' * width_src}  {'-' * width_coll}  ------  ---")
    for name, coll, pts, dim in rows:
        click.echo(f"{name.ljust(width_src)}  {coll.ljust(width_coll)}  {pts:>6}  {dim:>3}")


@main.command("collections")
@click.option("--all", "show_all", is_flag=True, help="Show collections from every worktree.")
def cmd_collections(show_all: bool) -> None:
    """List Qdrant collections — by default just this worktree's."""
    store = KBStore()
    cols = store.list_collections(all_worktrees=show_all)
    if not cols:
        click.echo(f"(no collections{' for this worktree' if not show_all else ''})")
        return
    width = max(len("collection"), *(len(c["name"]) for c in cols))
    click.echo(f"{'collection'.ljust(width)}  points  dim")
    click.echo(f"{'-' * width}  ------  ---")
    for c in cols:
        click.echo(f"{c['name'].ljust(width)}  {c['points']:>6}  {c['dim']:>3}")


@main.command("index")
@click.argument("source", required=False)
@click.option("--all", "index_all", is_flag=True, help="Index every configured source.")
@click.option(
    "--full",
    is_flag=True,
    help="Force a complete re-embed (skip the content-hash check). "
    "Use after changing the chunker or embedding model.",
)
def cmd_index(source: str | None, index_all: bool, full: bool) -> None:
    """Run an indexer (chunk → embed → upsert).

    Defaults to incremental: only files whose content has changed since the
    last index are re-embedded. Pass --full to re-embed every file.
    """
    if not source and not index_all:
        raise click.UsageError("Pass a source name or --all.")
    known = known_sources()
    targets = known if index_all else [source]  # type: ignore[list-item]
    mode = "full" if full else "incremental"
    any_failure = False
    for name in targets:
        if name not in known:
            raise click.UsageError(
                f"Unknown source {name!r}; known: {', '.join(known)}"
            )
        click.echo(f"→ indexing {name} ({mode}) …")
        try:
            result = run_index(name, incremental=not full)
        except BaseException as exc:
            # Bubble up cleanly instead of dumping a traceback — the
            # detail is already on stderr from _with_retry.
            click.echo(
                f"  ✗ {name} indexing failed: {type(exc).__name__}: {exc}",
                err=True,
            )
            any_failure = True
            continue
        msg = (
            f"  upserted={result.upserted} collection={result.collection} "
            f"provider={result.embedding_provider}"
        )
        if not full:
            msg += (
                f" skipped_files={result.skipped_files}"
                f" orphans_evicted={result.deleted_orphans}"
            )
        click.echo(msg)
        if not result.ok:
            click.echo(
                f"  ⚠ {result.failed_batches} batch(es) failed; "
                f"{len(result.failed_paths)} file path(s) may be incomplete:",
                err=True,
            )
            for p in result.failed_paths[:10]:
                click.echo(f"      {p}", err=True)
            if len(result.failed_paths) > 10:
                click.echo(
                    f"      … and {len(result.failed_paths) - 10} more",
                    err=True,
                )
            any_failure = True
    if any_failure:
        raise SystemExit(1)


@main.command("search")
@click.argument("query")
@click.option("--source", "-s", default=None, help="Restrict to one source's collection.")
@click.option("--top-k", "-k", default=5, show_default=True, type=int)
@click.option("--json", "as_json", is_flag=True, help="Emit JSON instead of a table.")
def cmd_search(query: str, source: str | None, top_k: int, as_json: bool) -> None:
    """Search the knowledge base."""
    provider = get_provider()
    store = KBStore()
    vec = provider.embed_query(query)

    known = known_sources()
    if source:
        if source not in known:
            raise click.UsageError(f"Unknown source {source!r}; known: {', '.join(known)}")
        collections = [build(source).collection]
    else:
        collections = sorted({build(name).collection for name in known})
    existing = {c["logical_name"] for c in store.list_collections()}
    payload_filter = {"source": source} if source else None

    hits = []
    for coll in collections:
        if coll not in existing:
            continue
        for h in store.search(coll, vec, top_k=top_k, payload_filter=payload_filter):
            hits.append({"collection": coll, "id": str(h.id), "score": h.score, "payload": h.payload})
    hits.sort(key=lambda r: r["score"], reverse=True)
    hits = hits[:top_k]

    if as_json:
        click.echo(json.dumps(hits, indent=2, ensure_ascii=False))
        return

    if not hits:
        click.echo("(no hits — is the index built? try `kb index --all`)")
        return
    for h in hits:
        p = h["payload"] or {}
        location = p.get("doc_uri") or (
            f"{p.get('header_path')}:{p.get('line_start')}"
            if p.get("header_path")
            else "?"
        )
        click.echo(f"{h['score']:.3f}  {location}")
        label = (
            p.get("heading_label")
            or p.get("title")
            or p.get("qualified_name")
            or ""
        )
        click.echo(f"        {label}")
        snippet = (p.get("content") or "").strip().replace("\n", " ")
        if len(snippet) > 200:
            snippet = snippet[:199] + "…"
        click.echo(f"        {snippet}")
        click.echo()


@main.command("serve-mcp")
def cmd_serve_mcp() -> None:
    """Run the stdio MCP server."""
    from kb.mcp_server import main as mcp_main

    mcp_main()


@main.command("drop")
@click.argument("collection")
@click.confirmation_option(prompt="Drop the collection?")
def cmd_drop(collection: str) -> None:
    """Drop a Qdrant collection (irreversible)."""
    KBStore().drop_collection(collection)
    click.echo(f"Dropped {collection}")


@main.command("verify")
def cmd_verify() -> None:
    """Check that every ontology binding still points at a real code symbol."""
    from kb.verify import verify

    report = verify()
    click.echo(
        f"Checked {report.checked_concepts} concept(s), "
        f"{report.checked_symbols} bound symbol(s)."
    )
    if report.ok:
        click.echo("All bindings resolve. ✓")
        return
    click.echo(f"✗ {len(report.missing)} unresolved binding(s):")
    for m in report.missing:
        click.echo(f"  {m.entry_path}  concept={m.concept}  {m.field}: {m.symbol}")
    raise SystemExit(1)


@main.command("heal")
@click.option("--apply", is_flag=True, help="Rewrite ontology files in place.")
@click.option(
    "--min-confidence",
    default=0.85,
    show_default=True,
    type=float,
    help="Only auto-apply suggestions at or above this score.",
)
def cmd_heal(apply: bool, min_confidence: float) -> None:
    """Propose replacements for missing ontology bindings (heuristic)."""
    from kb.heal import heal

    suggestions, written = heal(apply=apply, min_confidence=min_confidence)
    if not suggestions:
        click.echo("Nothing to heal — ontology resolves cleanly. ✓")
        return

    for sug in suggestions:
        m = sug.missing
        click.echo(f"\n{m.entry_path}  {m.concept}  {m.field}:")
        click.echo(f"  missing: {m.symbol}")
        if not sug.candidates:
            click.echo("  (no candidate replacements found)")
            continue
        for c in sug.candidates:
            mark = "→" if c is sug.best else " "
            click.echo(f"  {mark} {c.symbol}  [{c.reason}, score={c.score:.2f}]")

    if apply:
        if written:
            click.echo(f"\nUpdated {len(written)} file(s):")
            for p in written:
                click.echo(f"  {p}")
            click.echo("Run `kb verify` to confirm and `kb index <ontology-source>` to refresh the index.")
        else:
            click.echo(
                f"\nNo files written — no candidate cleared --min-confidence={min_confidence:.2f}."
            )
    else:
        click.echo("\n(dry run; pass --apply to rewrite ontology files)")


@main.command("suggest-new")
@click.option("--apply", is_flag=True, help="Write stub files for every uncovered concept.")
@click.option("--limit", type=int, default=None, help="Cap the number of suggestions shown/written.")
def cmd_suggest_new(apply: bool, limit: int | None) -> None:
    """Find concept subclasses that have no ontology entry yet."""
    from kb.discover import apply_stubs, discover_uncovered

    proposals = discover_uncovered()
    if limit:
        proposals = proposals[:limit]

    if not proposals:
        click.echo("All discoverable concept classes are covered by the ontology. ✓")
        return

    click.echo(f"{len(proposals)} uncovered concept class(es):\n")
    for p in proposals:
        click.echo(f"  {p.qualified_name}")
        click.echo(f"    → would write {p.target_path}")
        click.echo(f"    title: {p.title}")
        if p.brief:
            click.echo(f"    brief: {p.brief}")
        click.echo()

    if apply:
        written = apply_stubs(proposals)
        click.echo(f"Wrote {len(written)} stub(s).")
        if len(written) < len(proposals):
            click.echo(
                f"({len(proposals) - len(written)} skipped — target files already exist)"
            )
        if written:
            click.echo("Review the stubs and re-index the ontology source once curated.")
    else:
        click.echo("(dry run; pass --apply to write stub files)")


def run() -> None:
    """Console-script entrypoint: surface config errors without a traceback."""

    try:
        main()
    except ConfigError as e:
        click.echo(f"error: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    run()
