"""Per-worktree collection slugging and KBStore qualification."""

from pathlib import Path

from kb.config import _slugify_worktree


def test_slugify_basic_names():
    assert _slugify_worktree(Path("/home/u/proj/backend")) == "backend"
    assert _slugify_worktree(Path("/home/u/proj/publish")) == "publish"
    assert _slugify_worktree(Path("/home/u/proj/aic-als")) == "aic_als"
    assert _slugify_worktree(Path("/home/u/proj/foo.bar")) == "foo_bar"


def test_slugify_root_fallback():
    assert _slugify_worktree(Path("/")) == "kb"


def test_slugify_strips_edges():
    assert _slugify_worktree(Path("/foo/__weird__")) == "weird"


def test_store_qualifies_logical_names(monkeypatch):
    """KBStore should suffix every collection name with the worktree slug."""
    from kb.qdrant_client import KBStore

    class FakeClient:
        def __init__(self):
            self.calls: list[tuple[str, str]] = []

        def get_collections(self):
            class _Resp:
                collections = []
            return _Resp()

    store = KBStore(client=FakeClient(), slug="publish")
    assert store._qualified("sudoku_theory") == "sudoku_theory_publish"
    assert store.slug == "publish"


def test_store_empty_slug_passes_through():
    from kb.qdrant_client import KBStore

    class FakeClient:
        def get_collections(self):
            class _Resp:
                collections = []
            return _Resp()

    store = KBStore(client=FakeClient(), slug="")
    assert store._qualified("sudoku_theory") == "sudoku_theory"


def test_settings_honours_kb_repo_root_env(monkeypatch, tmp_path):
    """Confirms the make-target trick — passing KB_REPO_ROOT at MCP
    registration time — drives the slug derivation, not __file__'s
    location."""
    fake_worktree = tmp_path / "publish"
    fake_worktree.mkdir()
    monkeypatch.setenv("KB_REPO_ROOT", str(fake_worktree))

    # Build a fresh Settings (the module-level cache is bypassed by
    # constructing directly).
    from kb.config import Settings

    s = Settings()
    assert s.repo_root == fake_worktree
    assert s.worktree_slug == "publish"


def test_settings_kb_worktree_slug_overrides_repo_root(monkeypatch, tmp_path):
    """Explicit KB_WORKTREE_SLUG wins over KB_REPO_ROOT-derived slug."""
    monkeypatch.setenv("KB_REPO_ROOT", str(tmp_path / "publish"))
    monkeypatch.setenv("KB_WORKTREE_SLUG", "custom-name")

    from kb.config import Settings

    s = Settings()
    assert s.worktree_slug == "custom-name"
