"""Index documented Make targets across a configured set of makefiles.

Assumes the widespread convention ``target: deps ## description`` for
user-facing targets (the same one self-documenting ``make help`` recipes
parse). This indexer makes every documented target findable via KB search —
an agent asking "how do I build for a device" gets back the exact ``make``
target plus the module it lives in.

Each target produces one chunk. The chunk text bundles target name,
module, description, and the dependencies, so embeddings see both the
intent and the surface name.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator

from kb.config import get_settings
from kb.indexers.base import ChunkRecord, ShouldIndex, stable_id
from kb.util import file_content_hash


# target_name: deps ## description
_TARGET_RE = re.compile(r"^([a-zA-Z_-][a-zA-Z0-9_-]*)\s*:([^=]*?)##\s*(.+)$")


class MakeTargetsIndexer:
    def __init__(
        self,
        *,
        name: str = "make_targets",
        collection: str = "kb_default",
        files: tuple[str, ...] | list[str] = ("Makefile",),
        repo_root: Path | None = None,
    ) -> None:
        self.name = name
        self.collection = collection
        self._repo_root = repo_root or get_settings().repo_root
        # Repo-relative globs, e.g. ["Makefile", "scripts/make/*.mk"].
        self._file_globs = list(files)

    def _resolve_files(self) -> list[Path]:
        out: list[Path] = []
        for pattern in self._file_globs:
            candidate = self._repo_root / pattern
            if candidate.exists() and candidate.is_file():
                out.append(candidate)
            else:
                out.extend(sorted(self._repo_root.glob(pattern)))
        return out

    def iter_chunks(
        self, *, should_index: ShouldIndex | None = None
    ) -> Iterator[ChunkRecord]:
        files = self._resolve_files()

        for mk_path in files:
            if not mk_path.exists():
                continue
            rel = str(mk_path.relative_to(self._repo_root))
            module = mk_path.stem  # "Makefile" or e.g. "kb"
            content_hash = file_content_hash(mk_path)
            if should_index is not None and not should_index(rel, content_hash):
                continue

            for lineno, line in enumerate(
                mk_path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                m = _TARGET_RE.match(line)
                if not m:
                    continue
                target, deps, description = m.group(1), m.group(2).strip(), m.group(3).strip()
                # Skip targets ending in suffixes that aren't user-facing
                # (e.g. -help noise — they're already enumerated in `make help`).
                content = _render(
                    target=target,
                    module=module,
                    rel=rel,
                    description=description,
                    deps=deps,
                )
                yield ChunkRecord(
                    id=stable_id(self.name, rel, target),
                    text=content,
                    payload={
                        "source": self.name,
                        "collection": self.collection,
                        "target": target,
                        "module": module,
                        "path": rel,
                        "content_hash": content_hash,
                        "line": lineno,
                        "description": description,
                        "deps": deps,
                        "invocation": f"make {target}",
                        "content": content,
                        "doc_uri": f"make://{target}",
                        "lang": "en",
                    },
                )


def _render(*, target: str, module: str, rel: str, description: str, deps: str) -> str:
    parts = [
        f"make {target}",
        f"  {description}",
        "",
        f"defined in {rel} (module: {module})",
    ]
    if deps:
        parts.append(f"depends on: {deps}")
    return "\n".join(parts)
