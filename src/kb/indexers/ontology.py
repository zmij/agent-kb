"""Index an ontology tree (``**/*.md``) — concept → code symbol bindings.

These entries are the load-bearing artefacts of the KB: each one names a
domain concept (a technique, a subsystem, a core type) and lists the code
symbols that implement it. The KB stops there — it does NOT carry file
paths or line numbers; resolution to live locations is LSP's job.

The chunk text intentionally bakes the symbol list into the embeddable body
so queries like "which class implements X-Wing" hit the bound symbol names,
not just the prose. The frontmatter is also lifted into the payload so the
agent can read symbols out structurally without parsing the chunk text.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterator

import yaml

from kb.config import get_settings
from kb.indexers.base import ChunkRecord, ShouldIndex, stable_id
from kb.util import file_content_hash


_FRONT_MATTER_RE = re.compile(r"^---\n(.*?\n)---\n", re.DOTALL)


def _split_front_matter(text: str) -> tuple[dict[str, Any], str]:
    m = _FRONT_MATTER_RE.match(text)
    if not m:
        return {}, text
    try:
        meta = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        meta = {}
    return meta, text[m.end():]


class OntologyIndexer:
    def __init__(
        self,
        root: Path | None = None,
        *,
        name: str = "ontology",
        collection: str = "kb_default",
        repo_root: Path | None = None,
    ) -> None:
        # Sharing the prose corpus's collection enables cross-source
        # retrieval in a single search; the factory passes it in from config.
        self.name = name
        self.collection = collection
        self._repo_root = repo_root or get_settings().repo_root
        self._root = root or (self._repo_root / "docs" / "ontology")

    def iter_chunks(
        self, *, should_index: ShouldIndex | None = None
    ) -> Iterator[ChunkRecord]:
        if not self._root.exists():
            raise FileNotFoundError(f"Ontology root not found: {self._root}")

        for md_path in sorted(self._root.rglob("*.md")):
            # Skip the index README — it documents the format, isn't a concept.
            if md_path.name.lower() in {"readme.md", "index.md"}:
                continue

            rel = str(md_path.relative_to(self._repo_root))
            content_hash = file_content_hash(md_path)
            if should_index is not None and not should_index(rel, content_hash):
                continue

            text = md_path.read_text(encoding="utf-8")
            meta, body = _split_front_matter(text)
            if not meta or "concept" not in meta:
                continue

            concept = str(meta["concept"])
            title = str(meta.get("title") or concept)
            kind = str(meta.get("kind") or "")
            implements = [str(s) for s in (meta.get("implements") or [])]
            underlying = [str(s) for s in (meta.get("underlying") or [])]
            related_symbols = [str(s) for s in (meta.get("related_symbols") or [])]
            domain_refs = [str(s) for s in (meta.get("domain_refs") or [])]
            related_concepts = [str(s) for s in (meta.get("related_concepts") or [])]

            chunk_text = _render_chunk(
                title=title,
                kind=kind,
                implements=implements,
                underlying=underlying,
                related_symbols=related_symbols,
                related_concepts=related_concepts,
                body=body,
            )
            payload = {
                "source": self.name,
                "collection": self.collection,
                "path": rel,
                "content_hash": content_hash,
                "concept": concept,
                "title": title,
                "kind": kind,
                "implements": implements,
                "underlying": underlying,
                "related_symbols": related_symbols,
                "domain_refs": domain_refs,
                "related_concepts": related_concepts,
                "doc_uri": f"ontology://{concept}",
                "content": chunk_text,
                "lang": "en",
            }
            yield ChunkRecord(
                id=stable_id(self.name, concept),
                text=chunk_text,
                payload=payload,
            )


def _render_chunk(
    *,
    title: str,
    kind: str,
    implements: list[str],
    underlying: list[str],
    related_symbols: list[str],
    related_concepts: list[str],
    body: str,
) -> str:
    parts: list[str] = [f"{title}"]
    if kind:
        parts.append(f"(concept kind: {kind})")
    if implements:
        parts.append("Implements: " + ", ".join(implements))
    if underlying:
        parts.append("Underlying: " + ", ".join(underlying))
    if related_symbols:
        parts.append("Related symbols: " + ", ".join(related_symbols))
    if related_concepts:
        parts.append("Related concepts: " + ", ".join(related_concepts))
    body = body.strip()
    if body:
        parts.append("")
        parts.append(body)
    return "\n".join(parts)
