"""Verify ontology bindings against the live code.

For every ontology entry, collect the symbols listed in ``implements:`` and
``underlying:`` and confirm each one is actually defined under the project's
public header tree (``symbols.include_root`` in ``kb.yaml``). This is the
bit-rot defence for the ontology layer: a renamed class breaks the verifier
and forces an update.

The verifier is intentionally tolerant of template alias subtleties — when
checking a ``using`` alias, the parser does emit it as an ``alias`` symbol,
so the qualified-name match works. Symbols declared as forward declarations
are skipped by the parser already, so the verifier won't falsely pass on a
forward-only reference.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import yaml

from kb.config import ConfigError, get_config, get_settings
from kb.parsing.cpp import parse_header


@dataclass
class MissingBinding:
    concept: str
    field: str  # "implements" | "underlying"
    symbol: str
    entry_path: str


@dataclass
class VerifyReport:
    checked_concepts: int
    checked_symbols: int
    missing: list[MissingBinding]

    @property
    def ok(self) -> bool:
        return not self.missing


def collect_engine_symbols(include_root: Path, repo_root: Path) -> set[str]:
    """Return the set of qualified-names defined under ``include_root``."""

    symbols: set[str] = set()
    for hpp in include_root.rglob("*.hpp"):
        for sym in parse_header(hpp, repo_root):
            if sym.qualified_name:
                symbols.add(sym.qualified_name)
    return symbols


def _ontology_entries(ontology_root: Path) -> Iterable[tuple[Path, dict]]:
    for md in sorted(ontology_root.rglob("*.md")):
        if md.name.lower() in {"readme.md", "index.md"}:
            continue
        text = md.read_text(encoding="utf-8")
        if not text.startswith("---\n"):
            continue
        end = text.find("\n---\n", 4)
        if end < 0:
            continue
        try:
            meta = yaml.safe_load(text[4:end]) or {}
        except yaml.YAMLError:
            continue
        if "concept" not in meta:
            continue
        yield md, meta


def resolve_symbol_roots(
    *,
    ontology_root: Path | None = None,
    include_root: Path | None = None,
    repo_root: Path | None = None,
) -> tuple[Path, Path, Path]:
    """Fill in ``(repo_root, ontology_root, include_root)`` from ``kb.yaml``
    for whichever of the two corpus roots the caller didn't pass explicitly."""

    repo_root = repo_root or get_settings().repo_root
    if ontology_root is None or include_root is None:
        cfg = get_config()
        if ontology_root is None:
            rel = cfg.ontology_root
            if rel is None:
                raise ConfigError(
                    "kb.yaml declares no source of type 'ontology' — nothing to verify."
                )
            ontology_root = repo_root / rel
        if include_root is None:
            if cfg.symbols is None:
                raise ConfigError(
                    "kb.yaml has no 'symbols:' section — the verifier needs\n"
                    "symbols.include_root to know where public headers live."
                )
            include_root = repo_root / cfg.symbols.include_root
    return repo_root, ontology_root, include_root


def verify(
    *,
    ontology_root: Path | None = None,
    include_root: Path | None = None,
    repo_root: Path | None = None,
) -> VerifyReport:
    repo_root, ontology_root, include_root = resolve_symbol_roots(
        ontology_root=ontology_root, include_root=include_root, repo_root=repo_root
    )

    # Use a parser-friendly root: prefer the real repo root, but fall back to
    # the include root's parent when callers (notably tests) point at a path
    # outside the worktree.
    parse_root = repo_root if _is_under(include_root, repo_root) else include_root.parent

    known = collect_engine_symbols(include_root, parse_root)

    missing: list[MissingBinding] = []
    checked_concepts = 0
    checked_symbols = 0

    for path, meta in _ontology_entries(ontology_root):
        checked_concepts += 1
        concept = str(meta["concept"])
        entry_path = (
            str(path.relative_to(repo_root))
            if _is_under(path, repo_root)
            else str(path)
        )
        for field in ("implements", "underlying"):
            for sym in meta.get(field) or []:
                checked_symbols += 1
                if sym not in known:
                    missing.append(
                        MissingBinding(
                            concept=concept,
                            field=field,
                            symbol=str(sym),
                            entry_path=entry_path,
                        )
                    )

    return VerifyReport(
        checked_concepts=checked_concepts,
        checked_symbols=checked_symbols,
        missing=missing,
    )


def _is_under(p: Path, root: Path) -> bool:
    try:
        p.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False
