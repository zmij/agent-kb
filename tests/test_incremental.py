"""Incremental index rebuild — hash check, skip behaviour, orphan cleanup."""

from pathlib import Path

import pytest

from kb.indexers.ontology import OntologyIndexer
from kb.util import file_content_hash


@pytest.fixture
def tmp_ontology(tmp_path: Path) -> Path:
    """Build a tiny ontology root with two valid concept entries."""
    root = tmp_path / "ontology"
    root.mkdir()
    (root / "x.md").write_text(
        "---\nconcept: x\ntitle: X\nkind: type\nimplements:\n  - sudoku::X\n---\nBody X.\n"
    )
    (root / "y.md").write_text(
        "---\nconcept: y\ntitle: Y\nkind: type\nimplements:\n  - sudoku::Y\n---\nBody Y.\n"
    )
    return root


def test_file_content_hash_is_stable(tmp_path: Path):
    f = tmp_path / "a.txt"
    f.write_text("hello world")
    assert file_content_hash(f) == file_content_hash(f)


def test_file_content_hash_changes_with_content(tmp_path: Path):
    f = tmp_path / "a.txt"
    f.write_text("hello world")
    h1 = file_content_hash(f)
    f.write_text("HELLO WORLD")
    h2 = file_content_hash(f)
    assert h1 != h2


def test_ontology_payload_includes_content_hash(tmp_path: Path, tmp_ontology: Path, monkeypatch):
    # Point the indexer's repo_root at tmp_path so the relative path is sane.
    indexer = OntologyIndexer(root=tmp_ontology)
    monkeypatch.setattr(indexer, "_repo_root", tmp_path)
    chunks = list(indexer.iter_chunks())
    assert len(chunks) == 2
    for c in chunks:
        assert "content_hash" in c.payload
        assert len(c.payload["content_hash"]) == 64  # sha256 hex


def test_should_index_callback_skips_files(tmp_path: Path, tmp_ontology: Path, monkeypatch):
    indexer = OntologyIndexer(root=tmp_ontology)
    monkeypatch.setattr(indexer, "_repo_root", tmp_path)

    # Skip every file: yields nothing.
    chunks = list(indexer.iter_chunks(should_index=lambda path, h: False))
    assert chunks == []

    # Allow every file: yields both concepts.
    chunks = list(indexer.iter_chunks(should_index=lambda path, h: True))
    assert {c.payload["concept"] for c in chunks} == {"x", "y"}


def test_should_index_callback_receives_real_hashes(
    tmp_path: Path, tmp_ontology: Path, monkeypatch
):
    indexer = OntologyIndexer(root=tmp_ontology)
    monkeypatch.setattr(indexer, "_repo_root", tmp_path)

    seen: dict[str, str] = {}

    def callback(path: str, content_hash: str) -> bool:
        seen[path] = content_hash
        return True

    list(indexer.iter_chunks(should_index=callback))

    assert len(seen) == 2
    # Hashes match what we'd compute directly from the source files.
    assert seen["ontology/x.md"] == file_content_hash(tmp_ontology / "x.md")
    assert seen["ontology/y.md"] == file_content_hash(tmp_ontology / "y.md")


def test_should_index_called_even_for_skipped_files(
    tmp_path: Path, tmp_ontology: Path, monkeypatch
):
    """The runner relies on this to track which files were SEEN, even when
    skipped, so orphan cleanup at the end is correct."""
    indexer = OntologyIndexer(root=tmp_ontology)
    monkeypatch.setattr(indexer, "_repo_root", tmp_path)

    seen_paths: set[str] = set()

    def callback(path: str, content_hash: str) -> bool:
        seen_paths.add(path)
        return False  # skip everything

    chunks = list(indexer.iter_chunks(should_index=callback))
    assert chunks == []
    assert seen_paths == {"ontology/x.md", "ontology/y.md"}


def test_kbstore_enumerate_file_hashes_empty_collection():
    """When the collection doesn't exist yet, returns empty map."""
    from kb.qdrant_client import KBStore

    class FakeClient:
        def get_collections(self):
            class _R:
                collections = []
            return _R()

    store = KBStore(client=FakeClient(), slug="test")
    assert store.enumerate_file_hashes("anything", "anysource") == {}


# ---------------------------------------------------------------------------
# Runner-level orphan and reindex behaviour (no real Qdrant — fake store).
# ---------------------------------------------------------------------------


class _FakeStore:
    """In-memory stand-in for KBStore — tracks upserts and deletes."""

    def __init__(self, existing: dict[str, str] | None = None):
        # existing: {path: content_hash} as if previously indexed.
        self._existing = dict(existing or {})
        self.upserted_ids: list[str] = []
        self.upserted_payloads: list[dict] = []
        self.deleted_paths: list[str] = []
        self.deleted_sources: list[str] = []

    def ensure_collection(self, *args, **kwargs):
        pass

    def delete_by_source(self, collection, source):
        self.deleted_sources.append(source)
        self._existing.clear()

    def enumerate_file_hashes(self, collection, source):
        return dict(self._existing)

    def delete_by_path(self, collection, source, path):
        self.deleted_paths.append(path)
        self._existing.pop(path, None)

    def upsert(self, collection, ids, vectors, payloads):
        self.upserted_ids.extend(ids)
        self.upserted_payloads.extend(payloads)


class _FakeProvider:
    name = "fake"
    dim = 4

    def embed_texts(self, texts):
        return [[0.0, 0.0, 0.0, 0.0] for _ in texts]


def test_runner_orphan_cleanup_on_deleted_file(tmp_path: Path, monkeypatch):
    """If a file existed in Qdrant but is no longer in the corpus, the runner
    deletes its chunks at the end of an incremental run."""
    from kb.runner import run_index

    # Build a tiny ontology root with only y.md; pretend x.md was indexed before.
    ontology_root = tmp_path / "ontology"
    ontology_root.mkdir()
    (ontology_root / "y.md").write_text(
        "---\nconcept: y\ntitle: Y\nkind: type\nimplements:\n  - sudoku::Y\n---\nBody Y.\n"
    )

    # Pre-populate the fake store as if x.md and y.md were both there with stale
    # (different) hashes.
    fake_store = _FakeStore(existing={
        "ontology/x.md": "stalehashx",
        "ontology/y.md": "stalehashy",
    })

    # Inject the indexer with the tmp ontology root.
    from kb.indexers import REGISTRY

    class _ScopedOntologyIndexer(OntologyIndexer):
        def __init__(self):
            super().__init__(root=ontology_root)
            self._repo_root = tmp_path

    monkeypatch.setitem(REGISTRY, "ontology", _ScopedOntologyIndexer)

    result = run_index("ontology", provider=_FakeProvider(), store=fake_store)

    # y.md is the only file present → its old chunks get evicted before new
    # ones are upserted; x.md is the orphan and gets deleted at the end.
    assert "ontology/y.md" in fake_store.deleted_paths  # pre-upsert eviction
    assert "ontology/x.md" in fake_store.deleted_paths  # orphan cleanup
    assert result.deleted_orphans == 1
    assert result.upserted == 1
    assert result.skipped_files == 0


def test_runner_skips_unchanged_files(tmp_path: Path, monkeypatch):
    """When every file's hash matches what's in Qdrant, nothing is embedded
    and no chunks are deleted."""
    from kb.runner import run_index
    from kb.indexers import REGISTRY

    ontology_root = tmp_path / "ontology"
    ontology_root.mkdir()
    x_md = ontology_root / "x.md"
    x_md.write_text(
        "---\nconcept: x\ntitle: X\nkind: type\nimplements:\n  - sudoku::X\n---\nBody.\n"
    )

    fake_store = _FakeStore(existing={"ontology/x.md": file_content_hash(x_md)})

    class _ScopedOntologyIndexer(OntologyIndexer):
        def __init__(self):
            super().__init__(root=ontology_root)
            self._repo_root = tmp_path

    monkeypatch.setitem(REGISTRY, "ontology", _ScopedOntologyIndexer)

    result = run_index("ontology", provider=_FakeProvider(), store=fake_store)

    assert result.upserted == 0
    assert result.skipped_files == 1
    assert result.deleted_orphans == 0
    assert fake_store.deleted_paths == []
    assert fake_store.upserted_ids == []
