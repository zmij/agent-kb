---
name: knowledge-base
description: Query the project knowledge base (domain docs, architecture docs, concept-to-symbol ontology, make targets) via the agent-kb MCP server. AUTO-TRIGGER when about to assert a domain fact, an architecture claim, which symbol implements a concept, or a make/build invocation — search first instead of guessing. Also covers updating the index when source docs change and maintaining the ontology (verify / heal / suggest-new).
---

# Knowledge Base

A local, Qdrant-backed semantic index over this project's curated corpora.
Use it **before** stating facts the repo's docs already answer — domain
mechanics, architecture decisions, build invocations, concept-to-symbol
bindings. Cheaper than re-reading docs every time, and it keeps answers
grounded in what the project actually says.

Sources are declared in `kb.yaml` at the repo root. Call `kb_list_sources`
once per session if you don't know what's indexed here.

## When to query (auto-trigger)

The KB owns **what is true about the project as written down** — prose and
bindings. It does NOT carry file paths, line numbers, or live signatures —
those rot per-commit and diverge per-worktree, and are LSP territory
(see the `code-intelligence` skill if installed). Compose the two: KB
answers *what is the symbol*, the LSP answers *where it is right now*.

Typical source types and their question shapes:

- **markdown sources** (user docs, architecture docs) — about to describe
  how something works, why a design is the way it is, or quote a workflow.
  `kb_search` with `source="<name>"`.
- **ontology** — about to claim *which class/function* implements a
  concept, what the base class or substrate is. Returns qualified symbol
  names structurally in the payload; hand them to the LSP for live
  location and signature.
- **make_targets** — about to suggest "run this make target" or answer
  "what target does X". Each hit carries the target, module, description,
  dependencies and the exact invocation.
- **cross-source** — "where is X documented" with no scope hint: omit
  `source` and let all corpora rank together.

## When NOT to query

- Pure code questions where reading the file is faster (`Read`, `grep`).
- Anything outside the indexed corpora (third-party APIs, OS docs).
- Questions about the user's intent or current task state.

## MCP tools

| Tool              | Purpose                                                    |
|-------------------|------------------------------------------------------------|
| `kb_search`       | Semantic search; pass `source` to scope, `top_k` to widen. |
| `kb_get`          | Fetch the full chunk by id (returned by `kb_search`).      |
| `kb_list_sources` | What is indexed and how many points each collection has.   |
| `kb_reindex`      | Run an indexer (rare — usually done from the shell).       |

Typical pattern: `kb_search` → pick top result → `kb_get` to read the full
chunk → quote/paraphrase with the `doc_uri` as the source link.

## The composition pattern (with an LSP)

For "extend the detector behind concept X":

1. `kb_search(query="X implementation class", source="ontology")` →
   qualified symbol name(s) and what they alias/derive from.
2. LSP `find_symbol(<name>)` → live file:line + current signature,
   **in this worktree**.
3. LSP `find_referencing_symbols(<name>)` → call sites, so the blast
   radius is known before editing.

Don't grep for the class name to find the file; don't ask the KB for a
file path (it doesn't carry one, by design); don't quote signatures from
memory.

## Maintaining the ontology

If this project has an `ontology` source, three commands keep the
bindings from rotting (via the includable `kb.mk`, usually wrapped as
project make targets):

| Command | Purpose |
|---------|---------|
| `kb verify` | Reports any bound symbol that no longer exists. Non-zero exit on drift. |
| `kb heal` | Proposes replacements for missing symbols (name similarity); `--apply` rewrites entries when the best candidate clears 0.85 confidence. |
| `kb suggest-new` | Lists concept classes with no ontology entry; `--apply` writes stub entries from their doc comments. |

When a drift message appears (e.g. from a PostToolUse hook wired to
`kb verify`), prefer `kb heal` over hand-editing the YAML — its proposal
includes a confidence score and reason, which is the information needed
to decide.

## Updating the index

After docs change (run from the repo root):

```bash
kb index --source <name>      # one source   (or: make kb-index SOURCE=<name>)
kb index                      # all sources  (or: make kb-index)
```

Indexing is incremental (content-hash per file) and idempotent
(deterministic chunk ids); stale chunks of changed or deleted files are
evicted automatically.

## Infrastructure

Qdrant runs locally via docker compose (`make up` in the agent-kb
checkout, or the consuming repo's `make kb-up`). Embeddings default to
fastembed — CPU-only ONNX, no API keys. `KB_EMBED_BACKEND=ollama` swaps
backends; that changes the vector dimension, so drop and re-index each
collection afterwards.
