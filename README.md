# agent-kb

A drop-in, local-first knowledge base for LLM coding agents. Index your
repository's documentation, concept ontology, and build targets into
[Qdrant](https://qdrant.tech/), and expose retrieval to any MCP-capable agent
(Claude Code, Cursor, custom agents) as tools — not context stuffing.

No closed corpora, no paid APIs, no managed vector database: one Qdrant
container, CPU-local embeddings via [fastembed](https://github.com/qdrant/fastembed),
and a small Python MCP server.

## The idea

Agents lose accuracy the moment they're asked about anything outside their
pre-training corpus. The usual fix is RAG, but *how the agent consumes
retrieval* matters more than the embedding model: inline context-stuffing
burns tokens and amplifies noise; **tool-shaped retrieval lets the agent
ground claims selectively**, the same way it already uses other tools.

Grounding splits into three layers with different staleness profiles:

| Layer | Question shape | Owned by |
|-------|----------------|----------|
| **Prose** | "How does X work?" "What's the deployment story?" | this KB (markdown sources) |
| **Ontology** | "Which class implements concept X?" | this KB (concept → symbol bindings) |
| **Live code** | "Where is that class *right now*? Who calls it?" | your LSP — see [agent-code-intel](https://github.com/zmij/agent-code-intel) |

The KB deliberately stops at the symbol *name*. It never stores file paths or
line numbers for code — that's the LSP's job, and indexing source into a
vector store just guarantees churn.

## Install as a Claude Code plugin (fastest)

The repo doubles as a plugin marketplace covering both grounding repos:

```
/plugin marketplace add zmij/agent-kb
/plugin install agent-kb@agent-grounding
/plugin install agent-code-intel@agent-grounding   # optional: the LSP layer
```

The `agent-kb` plugin ships the `knowledge-base` operating skill **and** the
MCP server — Claude Code launches `kb serve-mcp` via `uv run` from the plugin
checkout, and the server discovers your repo root by walking up from the
session's working directory to the nearest `kb.yaml`. No per-worktree
registration needed.

Still on you: a `kb.yaml` at your repo root (below), Qdrant running
(`docker compose up -d` in the plugin/clone dir, or `make kb-up`), and one
`kb index --all`. Requires [uv](https://docs.astral.sh/uv/) on PATH.

## Install (clone / submodule)

Requirements: Python 3.11+, [uv](https://docs.astral.sh/uv/), Docker (for Qdrant).

```bash
git clone https://github.com/zmij/agent-kb          # next to your repo, or as a submodule
cd agent-kb
make install        # uv venv + editable install
make up             # start Qdrant (docker compose)
```

Or from your own repo, if you vendor this as a submodule and include `kb.mk`
in your Makefile (see [Make integration](#make-integration)):

```bash
make kb-install kb-up
```

## Configure your project

Create `kb.yaml` at **your repository's root** (not in this repo). It declares
the project identity and the sources to index:

```yaml
project: my-project           # → collection "my_project_kb", MCP server "my-project-kb"

sources:
  user_docs:
    type: markdown            # heading-aware chunking, frontmatter lifted to payload
    root: docs/guides
    uri_prefix: "docs://guides"   # optional: preserve your internal link scheme
  arch_docs:
    type: markdown
    root: docs
    exclude: [guides, ontology]   # subtrees that have their own indexers
  ontology:
    type: ontology            # concept → code-symbol bindings (see below)
    root: docs/ontology
  make_targets:
    type: make_targets        # every documented `target: ## description`
    files: [Makefile, "scripts/make/*.mk"]

# Only needed if you use the ontology maintenance loop (verify/heal/suggest-new)
symbols:
  language: cpp
  include_root: include/myproject   # public header tree to parse
  base_classes: [Strategy]          # subclasses of these are discoverable concepts
  strip_suffixes: [Strategy, Impl]  # trimmed when deriving stub titles/slugs
  stub_subdir: strategies           # stubs land in docs/ontology/strategies/
  stub_kind: strategy               # `kind:` value written into stubs
```

All sources share one collection by default (cross-source retrieval in a
single search); override per-source with `collection:` or globally with
`default_collection:`.

## Index and search

```bash
kb index --all                 # chunk → embed → upsert (incremental by default)
kb search "how do I deploy"    # semantic search across all sources
kb sources                     # what's indexed, per source
kb index user_docs --full      # re-embed one source from scratch
```

Incremental indexing hashes file content and only re-embeds changed files;
chunks of deleted files are evicted automatically.

## Expose to your agent (MCP)

```bash
kb serve-mcp                   # stdio MCP server
```

For Claude Code, register per project/worktree:

```bash
claude mcp add my-project-kb -e KB_REPO_ROOT=$(pwd) -- \
  /path/to/agent-kb/.venv/bin/kb serve-mcp
```

(the `kb-register` make target below does this for you, self-healing).

Tools exposed: `kb_search`, `kb_get`, `kb_list_sources`, `kb_reindex`.

## The ontology layer

An ontology entry is a small markdown file binding a *domain concept* to the
*code symbols* that implement it:

```markdown
---
concept: x-wing
title: X-Wing
kind: technique
implements:
  - sudoku::XWingTechnique
related_concepts: [swordfish]
---

A fish pattern on two rows and two columns…
```

The chunk text bakes the symbol list into the embeddable body, so "which
class implements X-Wing" hits the bound names, not just prose. And because
bindings are curated, they need a maintenance loop:

| Command | What it does |
|---------|--------------|
| `kb verify` | Checks every `implements:`/`underlying:` binding still resolves to a symbol defined under `symbols.include_root`. Non-zero exit on drift — wire it into pre-commit. |
| `kb heal` | Proposes replacements for broken bindings by name-similarity against current symbols (deterministic, stdlib-only). `--apply` rewrites entries when confidence ≥ 0.85. |
| `kb suggest-new` | Finds subclasses of `symbols.base_classes` with no ontology entry and drafts stub files (`--apply` to write). Stubs carry only the binding + header `@brief`; prose is for humans. |

Currently the symbol parser covers C++ headers (tree-sitter). Other languages:
PRs welcome — the parser interface is one function, `parse_header(path, root)
-> [Symbol]`.

## Make integration

`kb.mk` ships includable targets (`kb-up`, `kb-index`, `kb-search`,
`kb-register`, `kb-verify`, …). From a consuming repo:

```makefile
KB_DIR := tools/knowledge_base       # wherever the submodule/clone lives
KB_MCP_NAME := my-project-kb
include $(KB_DIR)/kb.mk
```

Run `make kb-help` for the full target list.

## Per-worktree collection scoping

If you use git worktrees, each worktree writes to its own Qdrant collections,
suffixed with a slug derived from the worktree directory name
(`my_project_kb_backend`, `my_project_kb_frontend`, …). Concurrent indexing
across worktrees never collides, while one Qdrant container serves them all.

The slug derives from `KB_REPO_ROOT` — `kb-register` bakes
`KB_REPO_ROOT=$(pwd)` into the MCP registration so queries always land in the
registering worktree's collections. `kb collections --all` shows every
worktree's collections.

## Configuration reference

Environment (infrastructure — machine-level, `.env` supported):

| Variable | Default | Purpose |
|----------|---------|---------|
| `KB_REPO_ROOT` | auto-detected (kb.yaml walk-up) | Consuming repo root |
| `KB_CONFIG` | `<repo_root>/kb.yaml` | Project config path |
| `KB_WORKTREE_SLUG` | derived from repo root basename | Collection suffix override |
| `KB_EMBED_BACKEND` | `fastembed` | `fastembed` or `ollama` |
| `KB_FASTEMBED_MODEL` | `BAAI/bge-small-en-v1.5` | Embedding model |
| `QDRANT_HOST` / `QDRANT_HTTP_PORT` / `QDRANT_GRPC_PORT` | `localhost` / 6333 / 6334 | Qdrant endpoint |

Switching embedding backends changes vector dimensions — re-index with
`kb index --all --full`.

## Layout

```
agent-kb/
├── kb.example.yaml        # annotated project-config template
├── kb.mk                  # includable make module
├── docker-compose.yml     # Qdrant
├── src/kb/
│   ├── config.py          # Settings (env) + KBConfig (kb.yaml)
│   ├── chunking/          # heading-aware markdown chunker
│   ├── embedding/         # provider Protocol + fastembed/ollama backends
│   ├── indexers/          # markdown / ontology / make_targets
│   ├── parsing/           # C++ header parser (tree-sitter)
│   ├── runner.py          # chunk → embed → upsert, incremental + retries
│   ├── verify.py, heal.py, discover.py   # ontology maintenance loop
│   ├── qdrant_client.py   # store wrapper, per-worktree namespacing
│   ├── mcp_server.py      # stdio MCP server
│   └── cli.py             # `kb` entrypoint
├── tests/
└── docs/WORKSHOP.md       # background: design rationale and the workshop story
```

## For agents

If you are an LLM agent working in a repo that uses agent-kb, read
[AGENTS.md](AGENTS.md) for when to search the KB, how to phrase queries per
source, and how to run the ontology maintenance loop.

## Licence

MIT.
