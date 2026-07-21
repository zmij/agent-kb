"""Index a tree of markdown documents into a Qdrant collection.

One indexer covers every prose corpus: user-facing docs, architecture
notes, runbooks. Per-source behaviour is configuration, not code:

* ``root`` — the corpus root (walked recursively for ``*.md``).
* ``exclude`` — top-level subdirectories of ``root`` to skip (used when a
  subtree has its own indexer, e.g. an ontology directory).
* ``uri_prefix`` — base for the chunk's ``doc_uri``. When set, the URI is
  ``<uri_prefix>/<path relative to root>``; otherwise it falls back to
  ``docs://<path relative to repo root>``. This is how a project's internal
  link scheme (``docs://techniques/...``) survives retrieval.

YAML frontmatter (title, description, tags, related) is lifted onto each
chunk's payload so retrieval results carry filterable metadata.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterator

import yaml

from kb.chunking import chunk_markdown
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


class MarkdownDocsIndexer:
    def __init__(
        self,
        *,
        name: str,
        collection: str,
        root: Path,
        repo_root: Path | None = None,
        exclude: tuple[str, ...] | list[str] = (),
        uri_prefix: str | None = None,
        lang: str = "en",
    ) -> None:
        self.name = name
        self.collection = collection
        self._repo_root = repo_root or get_settings().repo_root
        self._root = root
        self._exclude = set(exclude)
        self._uri_prefix = uri_prefix.rstrip("/") if uri_prefix else None
        self._lang = lang

    def _doc_uri(self, md_path: Path) -> str:
        if self._uri_prefix:
            rel = md_path.relative_to(self._root).with_suffix("")
            return f"{self._uri_prefix}/{rel.as_posix()}"
        rel = md_path.relative_to(self._repo_root).with_suffix("")
        return f"docs://{rel.as_posix()}"

    def iter_chunks(
        self, *, should_index: ShouldIndex | None = None
    ) -> Iterator[ChunkRecord]:
        if not self._root.exists():
            raise FileNotFoundError(f"Markdown corpus root not found: {self._root}")

        for md_path in sorted(self._root.rglob("*.md")):
            rel_to_root = md_path.relative_to(self._root)
            if rel_to_root.parts and rel_to_root.parts[0] in self._exclude:
                continue

            rel = md_path.relative_to(self._repo_root)
            content_hash = file_content_hash(md_path)
            if should_index is not None and not should_index(str(rel), content_hash):
                continue

            text = md_path.read_text(encoding="utf-8")
            meta, body = _split_front_matter(text)

            title = str(
                meta.get("title") or md_path.stem.replace("_", " ").replace("-", " ")
            )
            tags = list(meta.get("tags") or [])
            related = list(meta.get("related") or [])
            description = str(meta.get("description") or "")
            base_uri = self._doc_uri(md_path)

            chunks = chunk_markdown(body)
            if not chunks:
                continue
            for chunk in chunks:
                anchor = chunk.anchor
                uri = f"{base_uri}#{anchor}" if anchor else base_uri
                heading_path = (
                    [title, *chunk.heading_path]
                    if title not in chunk.heading_path[:1]
                    else list(chunk.heading_path)
                )
                payload = {
                    "source": self.name,
                    "collection": self.collection,
                    "path": str(rel),
                    "content_hash": content_hash,
                    "doc_uri": uri,
                    "title": title,
                    "description": description,
                    "tags": tags,
                    "related": related,
                    "heading_path": heading_path,
                    "heading_label": " > ".join(heading_path),
                    "part": chunk.part,
                    "lang": self._lang,
                    "content": chunk.text,
                }
                yield ChunkRecord(
                    id=stable_id(
                        self.name,
                        str(rel),
                        "/".join(chunk.heading_path),
                        str(chunk.part),
                    ),
                    text=chunk.text,
                    payload=payload,
                )
