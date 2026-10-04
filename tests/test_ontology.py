from pathlib import Path

from kb.indexers.ontology import OntologyIndexer


ENTRY = """\
---
concept: x-wing
title: X-Wing
kind: technique
implements:
  - sudoku::XWingTechnique
underlying:
  - sudoku::FishBase
related_symbols:
  - sudoku::CandidateSet
related_concepts: [swordfish]
domain_refs: [DOC-7]
owner: solver
stores:
  - solver.technique_registry
  - techniques.yaml
confidence: 3
settled: true
---

A fish pattern on two rows and two columns.
"""

MINIMAL = """\
---
concept: naked-single
implements:
  - sudoku::NakedSingle
---

One candidate left in a cell.
"""

COLLIDING = """\
---
concept: impostor
path: somewhere/else.md
content_hash: deadbeef
doc_uri: ontology://not-this
owner: solver
---

An entry trying to overwrite what the indexer owns.
"""


def _index(tmp_path: Path, name: str, text: str):
    root = tmp_path / "docs" / "ontology"
    root.mkdir(parents=True, exist_ok=True)
    (root / name).write_text(text, encoding="utf-8")
    indexer = OntologyIndexer(root=root, repo_root=tmp_path)
    return list(indexer.iter_chunks())


def test_arbitrary_keys_reach_the_payload(tmp_path: Path):
    """The indexer is not taught these names; it carries whatever is written."""
    (chunk,) = _index(tmp_path, "x_wing.md", ENTRY)
    assert chunk.payload["owner"] == "solver"
    assert chunk.payload["stores"] == [
        "solver.technique_registry",
        "techniques.yaml",
    ]
    assert chunk.payload["confidence"] == 3
    assert chunk.payload["settled"] is True


def test_arbitrary_keys_are_embedded_not_only_stored(tmp_path: Path):
    """The point of the fields is that a search for them can hit.

    A payload-only field answers nothing until something else has already
    returned the chunk, which is what made `domain_refs` useless.
    """
    (chunk,) = _index(tmp_path, "x_wing.md", ENTRY)
    assert "owner: solver" in chunk.text
    assert "solver.technique_registry, techniques.yaml" in chunk.text
    assert "confidence: 3" in chunk.text


def test_domain_refs_are_embedded(tmp_path: Path):
    (chunk,) = _index(tmp_path, "x_wing.md", ENTRY)
    assert "DOC-7" in chunk.text


def test_bindings_still_embed(tmp_path: Path):
    """The control: the pre-existing fields must not have been displaced."""
    (chunk,) = _index(tmp_path, "x_wing.md", ENTRY)
    assert "sudoku::XWingTechnique" in chunk.text
    assert "sudoku::FishBase" in chunk.text
    assert "sudoku::CandidateSet" in chunk.text
    assert "swordfish" in chunk.text
    assert "A fish pattern" in chunk.text


def test_a_rendered_key_is_not_repeated_as_an_extra(tmp_path: Path):
    """`implements` has its own line; it must not also appear as a raw key."""
    (chunk,) = _index(tmp_path, "x_wing.md", ENTRY)
    assert "Implements: sudoku::XWingTechnique" in chunk.text
    # Precise: no *line* is the raw key, which is what a duplicate would be.
    # ("(concept kind: technique)" legitimately contains "kind: ".)
    starts = [line.split(":")[0] for line in chunk.text.splitlines() if ":" in line]
    for key in ("implements", "title", "kind", "underlying", "related_symbols"):
        assert key not in starts, f"{key} rendered twice"


def test_an_entry_without_extras_is_unchanged(tmp_path: Path):
    """Absent is absent — no empty keys, no empty lines."""
    (chunk,) = _index(tmp_path, "naked_single.md", MINIMAL)
    assert "owner" not in chunk.payload
    assert "stores" not in chunk.payload
    assert "owner:" not in chunk.text
    assert "Domain refs:" not in chunk.text
    assert "sudoku::NakedSingle" in chunk.text


def test_an_entry_cannot_displace_the_indexers_own_keys(tmp_path: Path):
    """A stray `path` would make the chunk lie about where it came from."""
    (chunk,) = _index(tmp_path, "impostor.md", COLLIDING)
    assert chunk.payload["path"].endswith("impostor.md")
    assert chunk.payload["path"] != "somewhere/else.md"
    assert chunk.payload["content_hash"] != "deadbeef"
    assert chunk.payload["doc_uri"] == "ontology://impostor"
    # …while a non-reserved key on the same entry still comes through.
    assert chunk.payload["owner"] == "solver"
