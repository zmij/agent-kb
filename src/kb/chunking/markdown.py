"""Heading-aware markdown chunker.

The chunker walks markdown tokens, accumulates each heading section's text, and
emits chunks at H2/H3 boundaries. Long sections are split by paragraph with a
configurable token budget and overlap. ``heading_path`` and ``anchor`` are
preserved on every chunk so retrieval results can be linked back to a stable
location in the source.

Token counting uses a 4-chars-per-token approximation. The KB only needs this
to keep individual chunks within a sensible size band; precise token accounting
would couple the chunker to the embedding model and isn't worth it here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterator

from markdown_it import MarkdownIt


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(text: str) -> str:
    return _SLUG_RE.sub("-", text.strip().lower()).strip("-")


def _approx_tokens(text: str) -> int:
    return max(1, len(text) // 4)


@dataclass
class Chunk:
    text: str
    heading_path: list[str] = field(default_factory=list)
    anchor: str = ""
    # Index within the originating section after splitting (0 for the first
    # piece). Helpful for de-duplicating neighbouring hits at query time.
    part: int = 0

    @property
    def heading_label(self) -> str:
        return " > ".join(self.heading_path)


def _iter_sections(md_text: str) -> Iterator[tuple[list[str], str]]:
    """Yield (heading_path, body_text) for each H2/H3 section.

    Content above the first H2 is yielded with an empty heading path so the
    front matter / lead paragraph isn't dropped.
    """

    md = MarkdownIt("commonmark")
    tokens = md.parse(md_text)

    headings: list[tuple[int, str]] = []  # stack of (level, title)
    buffer: list[str] = []
    pending_path: list[str] = []

    def current_path() -> list[str]:
        return [title for _, title in headings]

    def flush(path: list[str]) -> Iterator[tuple[list[str], str]]:
        body = "\n\n".join(p for p in buffer if p.strip())
        if body.strip():
            yield path, body
        buffer.clear()

    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.type == "heading_open":
            yield from flush(pending_path)
            level = int(tok.tag[1])  # 'h1' → 1
            inline = tokens[i + 1]
            title = inline.content.strip() if inline.type == "inline" else ""
            # Pop deeper-or-equal levels.
            while headings and headings[-1][0] >= level:
                headings.pop()
            headings.append((level, title))
            pending_path = current_path()
            i += 3  # heading_open, inline, heading_close
            continue
        if tok.type == "inline":
            buffer.append(tok.content)
        elif tok.type == "fence":
            buffer.append(f"```{tok.info or ''}\n{tok.content.rstrip()}\n```")
        elif tok.type == "code_block":
            buffer.append(tok.content.rstrip())
        i += 1

    yield from flush(pending_path)


def _split_by_budget(text: str, max_tokens: int, overlap_tokens: int) -> list[str]:
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    if not paragraphs:
        return []
    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0
    for para in paragraphs:
        ptoks = _approx_tokens(para)
        if current and current_tokens + ptoks > max_tokens:
            chunks.append("\n\n".join(current))
            # Build overlap by retaining tail paragraphs that fit in budget.
            tail: list[str] = []
            tail_tokens = 0
            for p in reversed(current):
                t = _approx_tokens(p)
                if tail_tokens + t > overlap_tokens:
                    break
                tail.insert(0, p)
                tail_tokens += t
            current = tail
            current_tokens = tail_tokens
        current.append(para)
        current_tokens += ptoks
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def chunk_markdown(
    md_text: str,
    *,
    max_tokens: int = 512,
    overlap_tokens: int = 50,
) -> list[Chunk]:
    """Chunk a markdown document into heading-scoped pieces."""

    chunks: list[Chunk] = []
    for path, body in _iter_sections(md_text):
        anchor = _slugify(path[-1]) if path else ""
        pieces = _split_by_budget(body, max_tokens=max_tokens, overlap_tokens=overlap_tokens)
        for part_idx, piece in enumerate(pieces):
            chunks.append(
                Chunk(
                    text=piece,
                    heading_path=list(path),
                    anchor=anchor,
                    part=part_idx,
                )
            )
    return chunks
