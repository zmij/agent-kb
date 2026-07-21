"""Configuration for the knowledge base.

Two layers, deliberately separate:

* :class:`Settings` — environment-driven *infrastructure* config (Qdrant
  endpoint, embedding backend, repo root, worktree slug). Owned by the
  machine/session, not the project.
* :class:`KBConfig` — file-driven *project* config (``kb.yaml`` at the
  consuming repo's root): which sources exist, where their corpora live,
  and how the ontology binds to code symbols. Owned by the project and
  committed to its repository.

The package itself ships no project knowledge; without a ``kb.yaml`` the
CLI and MCP server have no sources to index or search.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_repo_root() -> Path:
    """Best-effort repo root when ``KB_REPO_ROOT`` isn't set.

    Walk up from the CWD looking for a ``kb.yaml`` (the project config is
    the anchor a consuming repo commits at its root). Fall back to the CWD
    so error messages carry a sensible path.
    """

    cwd = Path.cwd()
    for candidate in (cwd, *cwd.parents):
        if (candidate / "kb.yaml").exists():
            return candidate
    return cwd


_SLUG_SANITISE = re.compile(r"[^a-z0-9]+")


def _slugify_worktree(path: Path) -> str:
    """Derive a Qdrant-friendly slug from a worktree path.

    Used to scope each worktree's collections to its own namespace so
    ``kb index`` in worktree A never touches worktree B's data.
    """

    name = path.name.lower() or "kb"
    slug = _SLUG_SANITISE.sub("_", name).strip("_")
    return slug or "kb"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    qdrant_host: str = "localhost"
    qdrant_http_port: int = 6333
    qdrant_grpc_port: int = 6334
    qdrant_prefer_grpc: bool = True
    # Per-RPC timeout (seconds). Bulk upserts with wait=True can take a
    # while under concurrent indexing; the qdrant-client default of 5s is
    # too tight. Override via ``QDRANT_CLIENT_TIMEOUT`` env if needed.
    qdrant_client_timeout: float = 60.0

    kb_embed_backend: str = "fastembed"
    kb_fastembed_model: str = "BAAI/bge-small-en-v1.5"

    kb_ollama_url: str = "http://localhost:11434"
    kb_ollama_model: str = "nomic-embed-text"

    kb_repo_root: Path = Field(default_factory=_default_repo_root)

    # Path to the project config file. Defaults to <repo_root>/kb.yaml.
    kb_config: Path | None = None

    # Per-worktree collection isolation. Each worktree's KB writes to a
    # Qdrant collection suffixed with its slug (auto-derived from the
    # worktree directory name) so concurrent indexing across worktrees
    # cannot clobber each other. Override via the env var if multiple
    # worktrees should share a namespace (rare).
    kb_worktree_slug: str = ""

    @property
    def repo_root(self) -> Path:
        return self.kb_repo_root or _default_repo_root()

    @property
    def worktree_slug(self) -> str:
        return self.kb_worktree_slug or _slugify_worktree(self.repo_root)

    @property
    def config_path(self) -> Path:
        return self.kb_config or (self.repo_root / "kb.yaml")


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


# ----------------------------------------------------------------- project config


class SourceConfig(BaseModel):
    """One entry under ``sources:`` in ``kb.yaml``."""

    type: str  # "markdown" | "ontology" | "make_targets"
    collection: str | None = None  # defaults to the project default collection
    root: str | None = None  # repo-relative corpus root (markdown / ontology)
    exclude: list[str] = Field(default_factory=list)  # markdown: top-level subdirs to skip
    uri_prefix: str | None = None  # markdown: doc_uri base, e.g. "docs://techniques"
    lang: str = "en"
    files: list[str] = Field(default_factory=list)  # make_targets: file globs


class SymbolsConfig(BaseModel):
    """How ontology entries bind to code symbols (``symbols:``).

    Drives the maintenance loop (``kb verify`` / ``kb heal`` /
    ``kb suggest-new``): where the public headers live, which base classes
    mark a discoverable concept, and how stub filenames are derived.
    """

    language: str = "cpp"
    include_root: str  # repo-relative path to the public header tree
    base_classes: list[str] = Field(default_factory=list)  # e.g. ["Technique"]
    strip_suffixes: list[str] = Field(default_factory=list)  # e.g. ["Technique", "Rule"]
    stub_subdir: str = "concepts"  # under the ontology root, where stubs are written
    stub_kind: str = "concept"  # value for the stub's ``kind:`` frontmatter field


class KBConfig(BaseModel):
    """Project-level config, loaded from ``kb.yaml`` at the consuming repo root."""

    project: str
    mcp_name: str | None = None  # MCP server name; defaults to "<project>-kb"
    default_collection: str | None = None  # defaults to "<project>_kb" (slug-sanitised)
    sources: dict[str, SourceConfig] = Field(default_factory=dict)
    symbols: SymbolsConfig | None = None

    @model_validator(mode="after")
    def _validate_sources(self) -> "KBConfig":
        for name, src in self.sources.items():
            if src.type in {"markdown", "ontology"} and not src.root:
                raise ValueError(f"source {name!r} (type {src.type}) requires 'root'")
        return self

    @property
    def server_name(self) -> str:
        return self.mcp_name or f"{self.project}-kb"

    @property
    def collection(self) -> str:
        if self.default_collection:
            return self.default_collection
        return _SLUG_SANITISE.sub("_", self.project.lower()).strip("_") + "_kb"

    def collection_for(self, source: str) -> str:
        src = self.sources[source]
        return src.collection or self.collection

    @property
    def ontology_root(self) -> Path | None:
        """Repo-relative ontology root, from the first source of type ``ontology``."""

        for src in self.sources.values():
            if src.type == "ontology" and src.root:
                return Path(src.root)
        return None


class ConfigError(RuntimeError):
    pass


def load_config(path: Path | None = None) -> KBConfig:
    """Load and validate ``kb.yaml``. Raises :class:`ConfigError` with an
    actionable message when the file is missing or malformed."""

    s = get_settings()
    path = path or s.config_path
    if not path.exists():
        raise ConfigError(
            f"Project config not found: {path}\n"
            "Create a kb.yaml at your repo root declaring the sources to index\n"
            "(see kb.example.yaml in the agent-kb repository), or point the\n"
            "KB_CONFIG env var at an existing config file."
        )
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        raise ConfigError(f"Could not parse {path}: {e}") from e
    try:
        return KBConfig.model_validate(raw)
    except ConfigError:
        raise
    except Exception as e:  # pydantic ValidationError, kept generic for the CLI
        raise ConfigError(f"Invalid project config {path}: {e}") from e


_config: KBConfig | None = None


def get_config() -> KBConfig:
    global _config
    if _config is None:
        _config = load_config()
    return _config


def set_config(config: KBConfig | None) -> None:
    """Inject a config (tests) or reset the cache (``None``)."""

    global _config
    _config = config
