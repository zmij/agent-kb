"""Project config (kb.yaml) loading and the config-driven indexer factory."""

from pathlib import Path

import pytest

from kb.config import ConfigError, KBConfig, load_config
from kb.indexers import build, known_sources
from kb.indexers.make_targets import MakeTargetsIndexer
from kb.indexers.markdown_docs import MarkdownDocsIndexer
from kb.indexers.ontology import OntologyIndexer


EXAMPLE = """
project: demo
sources:
  guides:
    type: markdown
    root: docs/guides
    uri_prefix: "docs://guides"
    exclude: [drafts]
  ontology:
    type: ontology
    root: docs/ontology
  make_targets:
    type: make_targets
    files: [Makefile, "mk/*.mk"]
symbols:
  language: cpp
  include_root: include/demo
  base_classes: [Widget]
  strip_suffixes: [Widget]
  stub_subdir: widgets
  stub_kind: widget
"""


def _write_config(tmp_path: Path, text: str = EXAMPLE) -> Path:
    p = tmp_path / "kb.yaml"
    p.write_text(text)
    return p


def test_load_config_parses_sources(tmp_path: Path):
    cfg = load_config(_write_config(tmp_path))
    assert cfg.project == "demo"
    assert cfg.server_name == "demo-kb"
    assert cfg.collection == "demo_kb"
    assert set(cfg.sources) == {"guides", "ontology", "make_targets"}
    assert cfg.collection_for("guides") == "demo_kb"
    assert cfg.ontology_root == Path("docs/ontology")
    assert cfg.symbols is not None
    assert cfg.symbols.base_classes == ["Widget"]


def test_load_config_missing_file_is_actionable(tmp_path: Path):
    with pytest.raises(ConfigError, match="kb.yaml"):
        load_config(tmp_path / "kb.yaml")


def test_markdown_source_requires_root(tmp_path: Path):
    bad = "project: demo\nsources:\n  guides:\n    type: markdown\n"
    with pytest.raises(ConfigError, match="requires 'root'"):
        load_config(_write_config(tmp_path, bad))


def test_default_collection_override(tmp_path: Path):
    text = EXAMPLE + "default_collection: demo_theory\n"
    cfg = load_config(_write_config(tmp_path, text))
    assert cfg.collection == "demo_theory"
    assert cfg.collection_for("ontology") == "demo_theory"


def test_build_instantiates_types_from_config(tmp_path: Path):
    cfg = load_config(_write_config(tmp_path))
    assert isinstance(build("guides", cfg), MarkdownDocsIndexer)
    assert isinstance(build("ontology", cfg), OntologyIndexer)
    assert isinstance(build("make_targets", cfg), MakeTargetsIndexer)
    assert known_sources(cfg) == ["guides", "make_targets", "ontology"]


def test_build_unknown_source_lists_known(tmp_path: Path):
    cfg = load_config(_write_config(tmp_path))
    with pytest.raises(KeyError, match="guides"):
        build("nope", cfg)


def test_unknown_type_raises(tmp_path: Path):
    text = "project: demo\nsources:\n  weird:\n    type: sqlite\n"
    cfg = load_config(_write_config(tmp_path, text))
    with pytest.raises(KeyError, match="unknown type"):
        build("weird", cfg)


def test_markdown_indexer_uri_prefix_and_exclude(tmp_path: Path):
    root = tmp_path / "docs" / "guides"
    (root / "drafts").mkdir(parents=True)
    (root / "setup.md").write_text("# Setup\n\n## Install\n\nRun the installer.\n")
    (root / "drafts" / "wip.md").write_text("# WIP\n\n## Later\n\nNot yet.\n")

    ix = MarkdownDocsIndexer(
        name="guides",
        collection="demo_kb",
        root=root,
        repo_root=tmp_path,
        exclude=["drafts"],
        uri_prefix="docs://guides",
    )
    chunks = list(ix.iter_chunks())
    assert chunks, "expected at least one chunk"
    uris = {c.payload["doc_uri"].split("#")[0] for c in chunks}
    assert uris == {"docs://guides/setup"}
    assert all("wip" not in c.payload["path"] for c in chunks)


def test_make_targets_globs(tmp_path: Path):
    (tmp_path / "Makefile").write_text("build: ## Build everything\n\techo hi\n")
    mk = tmp_path / "mk"
    mk.mkdir()
    (mk / "extra.mk").write_text("deploy: build ## Ship it\n\techo go\n")

    ix = MakeTargetsIndexer(
        name="make_targets",
        collection="demo_kb",
        files=["Makefile", "mk/*.mk"],
        repo_root=tmp_path,
    )
    chunks = {c.payload["target"]: c for c in ix.iter_chunks()}
    assert set(chunks) == {"build", "deploy"}
    assert chunks["deploy"].payload["deps"] == "build"
    assert chunks["deploy"].payload["module"] == "extra"
