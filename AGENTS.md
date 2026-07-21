# agent-kb — agent operating guide

You are an LLM agent in a repository that exposes a knowledge base through
the `kb_*` MCP tools (server name: `<project>-kb`, from the repo's
`kb.yaml`). This document tells you when to reach for it, how to phrase
queries, and how to keep the ontology healthy.

## When to search the KB

Search **before asserting**, not after failing. Reach for `kb_search` when
you are about to:

- state a fact about the project's domain, architecture, or conventions;
- name the class/symbol that implements a domain concept;
- quote a `make` invocation ("I think it's `make deploy-something`" — stop,
  search `make_targets` instead);
- restate the rationale behind a design decision.

Do **not** use the KB to locate code positions (file paths, line numbers,
signatures). The KB deliberately stops at symbol *names*; resolving a name
to its live location is the job of the LSP layer (Serena `find_symbol` /
`find_referencing_symbols` if available in this repo).

## Query patterns by source

Call `kb_list_sources` once if you don't know what's indexed. Then:

| You want | Query shape | Source filter |
|----------|-------------|---------------|
| Domain/user-facing explanation | natural question: "how does X work" | the prose source (often `user_docs` / `technique_docs`) |
| Architecture / design rationale | "how does <subsystem> handle <concern>" | `arch_docs` |
| Concept → implementing symbol | "which class implements <concept>" | `ontology` |
| Exact make target for an intent | "how do I <build/deploy/test> <thing>" | `make_targets` |

Results carry a `doc_uri` (e.g. `docs://…`, `ontology://<concept>`,
`make://<target>`) and a snippet; use `kb_get` with the hit `id` for the
full chunk. Ontology hits carry `implements` / `underlying` /
`related_symbols` structurally in the payload — read them from there rather
than parsing the snippet.

If a search returns nothing plausible, say so rather than guessing — an
empty KB answer is a signal the docs have a gap, which is worth surfacing.

## Composition with code intelligence

The canonical two-step for "work on the code behind concept X":

1. `kb_search(query="X implementation class", source="ontology")` →
   qualified symbol name.
2. LSP tools (`find_symbol`, `find_referencing_symbols`) → current
   location, signature, call sites.

Never skip step 1 and grep for names you *think* are right; never use the
KB result as a substitute for step 2.

## Ontology maintenance loop

The ontology is curated and drifts as code is renamed. You are part of the
maintenance loop:

- After renaming/moving a public symbol bound in the ontology, run
  `kb verify` (or `make kb-verify`). Non-zero exit lists broken bindings.
- `kb heal` proposes replacements with confidence scores; review them, then
  `kb heal --apply` writes those ≥ 0.85. Re-run `kb verify` to confirm and
  re-index the ontology source (`kb index <ontology-source>`).
- After adding a new public concept class, run `kb suggest-new` — it drafts
  stub entries. Write the prose yourself before committing: a stub with no
  body is a gap made visible, not a finished entry.
- After editing any indexed markdown, re-index that source (incremental, so
  it's cheap): `kb index <source>` or the `kb_reindex` MCP tool.

## Failure modes

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `kb_search` errors with connection failure | Qdrant down | `make kb-up` |
| Every search returns nothing | Index never built | `kb index --all` |
| Hits describe another worktree's state | MCP registration points at another worktree's binary or lacks `KB_REPO_ROOT` | `make kb-register` (self-healing), then restart the agent session |
| "Project config not found: …/kb.yaml" | Repo hasn't declared sources | Create `kb.yaml` from `kb.example.yaml` |
| Hits look stale after a doc edit | Source not re-indexed | `kb index <source>` |

## Working on agent-kb itself

- Python 3.11+, `uv`; install with `make install`, test with `make test`.
- Indexer classes take explicit constructor parameters; **only the factory
  (`kb.indexers.build`) reads config**. Keep it that way — it's what makes
  the classes testable without a `kb.yaml`.
- Tests inject scoped indexers via `kb.indexers.REGISTRY` (name → zero-arg
  factory); registry entries shadow configured sources.
- New source types: add a class in `src/kb/indexers/`, register it in
  `TYPES`, document the config shape in `kb.example.yaml`, and add tests.
- New symbol-parser languages: implement `parse_header(path, repo_root) ->
  [Symbol]` alongside `parsing/cpp.py` and dispatch on
  `symbols.language`.
