# Workshop Notes — A Local Knowledge Base for LLM Agents

Reference document for the future workshop on equipping LLM agents with domain
knowledge. Written so that the agent that helped build the system can be used
verbatim as the demo subject and so that a workshop attendee can stand the
whole thing up on their laptop in under fifteen minutes.

The goal of the workshop is to give attendees something **they can run** —
no closed corpora, no paid embeddings, no managed vector database — and to
let them compare a useful baseline (`fastembed` + Qdrant) against more
sophisticated options without rewriting the surrounding plumbing.

---

## 1. Why this exists

Production agents lose accuracy the moment they're asked questions outside
their pre-training corpus. The standard answer is RAG: index your domain
content, retrieve at query time, stuff retrieved chunks into context.

The interesting bit is **how the agent consumes the retrieval**. There are
three obvious shapes:

1. **Inline context stuffing**: the agent gets retrieved chunks pre-pended to
   every turn. Cheap to wire up; expensive on tokens; brittle when retrieval
   is noisy.
2. **Tool-based retrieval**: the agent decides when to call a search tool.
   More tokens spent on tool definitions, fewer on retrieved noise; the
   agent learns to ground assertions selectively.
3. **Sub-agent retrieval**: a dedicated retrieval agent does the searching
   and returns a synthesised summary. Best for very deep retrieval chains;
   adds coordination cost.

This project picks (2) because the audience already knows MCP, and because
tool-shaped retrieval composes well with other tool-shaped agent capabilities
(reading files, running shell, etc.). The workshop's central thesis: **give
agents knowledge through tools, not through context-window injection.**

The author's production deployment at work runs the equivalent on Databricks
with a closed SQL corpus — not reproducible by an external audience. This
repo is the reproducible reference: same architecture, OSS-only components,
domain content the audience can intuit (Sudoku) instead of a custom SQL
dialect.

---

## 2. What's in the box

| Component | Role | Reproducible because |
|-----------|------|----------------------|
| Qdrant (Docker) | Vector database | OSS, single container, persistent volume |
| `fastembed` | Default embedding backend (BGE-small-en) | CPU-only ONNX, ~120 MB model, no API |
| `kb-mcp` | stdio MCP server | Talks to any MCP client (Claude Code, others) |
| `kb` CLI | `index`, `search`, `sources`, `serve-mcp`, `drop` | Pure local |
| Indexers | One per source, pluggable | Each ~100 LoC, easy to fork |
| `knowledge-base` skill | Tells the agent when to query | Plain markdown, no infra |

Anything an attendee replaces (different DB, different embedding model,
different corpus) only touches one layer. No vendor lock-in.

---

## 3. The corpus story

Five logical corpora across three semantic *layers* of grounding. The layers
are the real talk point — different staleness, different precision, different
ideal retrieval shape — and the corpora are the worked examples.

### Three layers of grounding

| Layer | Question shape | Where it lives | Staleness |
|-------|---------------|----------------|-----------|
| **Prose** — what we *teach* about the domain | "How does X-Wing work?" "Why is FFI split this way?" | Sudoku technique docs, architecture docs, external theory | Hours–weeks; drifts from code |
| **Ontology** — what *concepts bind to which symbols* | "Which class implements X-Wing?" "What's the base class for techniques?" "What goes through the FFI?" | `docs/ontology/`, indexed into the KB | Tracks code at the *name* level only — stable across worktrees, breaks only on rename |
| **Live code** — where symbols actually *are* right now | "What's the current signature of `FishTechnique::detect`?" "Who calls `applyHint`?" "Show me this method's body" | LSP via Serena MCP (`tools/code_intelligence/`) — clangd for C++, Dart Analysis Server for Dart | Live, per-worktree, ground truth |

The interesting layer — and the one most KB talks botch — is the middle
one. The original instinct is to "index the code into the KB." That's the
wrong shape: code is volatile (lines move every commit, names get renamed,
worktrees diverge), but the *binding from domain concept to symbol name*
is stable. "X-Wing is implemented by `XWingTechnique` over `FishTechnique`"
was true a year ago, will be true next year, and is the same statement in
every worktree. **The KB owns the binding; the LSP owns the live
resolution.**

Why this matters: re-indexing code into a vector store on every commit is
expensive churn that buys you nothing the LSP can't deliver more accurately.
Re-indexing the *ontology* happens when a concept entry is authored or
edited — human-paced, not commit-paced. And the ontology stays the same
across all worktrees, so one Qdrant instance serves every branch.

#### Live data from this codebase (workshop slide)

We did initially build "annotated code" the wrong way — auto-extracting
~3000 symbols (class + doxygen + file:line) into the KB. The lessons:

- **Locations rot fast.** A header reflow at commit time invalidates every
  chunk pointing at that header.
- **Worktree divergence.** Same symbol, different line per branch — pick a
  worktree to index against and you've already lost.
- **Dense embeddings on short identifiers are noisy.** `"x-wing class"`
  returned `XYZWingTechnique` ahead of `XWingTechnique` because the latter
  is a `using` alias with no doxygen body. Same observation that motivated
  the BM25-comparison slide, now for a different reason.

Switching to ontology + verifier moved 3000 noisy chunks down to ~10
curated, high-signal entries. Retrieval got sharper, infra got smaller,
talk got more interesting.

### 3.1 Sudoku technique docs (prose layer, primary)
- Source: `docs/ui/en/techniques/**/*.md`
- ~80 markdown files with YAML frontmatter (title, tags, related)
- Well-structured: H1 per technique, H2/H3 sections
- Cleanest signal-to-noise; ideal for the first retrieval demo

### 3.2 Project architecture docs (prose layer, secondary)
- Source: `docs/*.md`
- Long-form developer-facing docs (FFI, settings, layers, etc.)
- Same indexer as technique docs with a different root

### 3.3 Ontology (binding layer)
- Source: `docs/ontology/**/*.md`
- Hand-authored concept entries with frontmatter:
  `implements: [sudoku::XWingTechnique, …]`,
  `underlying: [sudoku::FishTechnique]`,
  `related_symbols: […]`,
  `domain_refs: [docs://…]`
- Indexed into the same `sudoku_theory` collection as prose, distinguished
  by `source=ontology`
- Verified by `make kb-verify` — the parser scans
  `core_engine/include/sudoku/` and reports any `implements:`/`underlying:`
  symbol that no longer exists. The verifier is the only piece of code that
  reads the C++ source; everything else operates on the curated bindings.

### 3.4 External Sudoku theory (deferred for v1)
- SudokuWiki, Hodoku, papers
- Talk angle: shows how to add a scraper indexer to an existing pipeline
  without disturbing what already works

### 3.5 Cross-language terminology (structured)
- Source: `l10n/strings/<lang>/techniques/*.yaml`
- 14 languages × ~80 techniques × a name + description
- Joined across language YAMLs to produce a glossary table
- **Key talk point**: this is *not* a vector-search problem. A translator
  asking "how do we render *Naked Pair* in Russian?" wants a structured
  lookup, not a similarity score against an embedded sentence. The KB
  exposes this as `term_lookup`, a separate tool, even though it lives in
  the same Qdrant instance for ops convenience.

---

## 4. Architectural decisions worth re-explaining at the workshop

### 4.1 Multiple collections, not one

Different corpora have different chunking, different language assumptions, and
different ideal retrieval ergonomics. Putting them in one collection forces
either a one-size-fits-all embedding or a lot of payload-based filtering.
Three collections keep each pipeline simple:

- `sudoku_theory` — English, dense, BGE-small-en
- `project_docs` — English, dense, BGE-small-en
- `terms_glossary` — multilingual, structured, multilingual-e5-small

### 4.2 Embedding backend behind a `Protocol`

```python
class EmbeddingProvider(Protocol):
    @property
    def name(self) -> str: ...
    @property
    def dim(self) -> int: ...
    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...
```

`fastembed_backend.py` is the default; `ollama_backend.py` is the swap-in.
Adding a third (a paid API, a custom model) is one file.

**Caveat to discuss at the workshop**: switching backends means re-indexing.
Collections are dimension-locked. The wrapper raises a friendly error if you
try to upsert into a collection whose dimension doesn't match the provider.
A more "production" system might host one collection per (corpus × backend)
and let queries fan out — overkill for a teaching example.

### 4.3 Indexers know nothing about Qdrant or embeddings

Each indexer is a generator of `ChunkRecord(id, text, payload)`. The runner
(`kb.runner.run_index`) takes care of embedding and upserting. This means:

- An indexer is testable without infrastructure.
- Switching embedding backends doesn't touch any indexer.
- An attendee adapting this to their own corpus only writes one file.

### 4.4 Stable, deterministic chunk ids

`uuid5(KB_NAMESPACE, "source::path::heading::part")`. Re-indexing the same
content produces the same ids, so upserts are idempotent. Discuss the
trade-off: renames create orphan chunks that linger until the collection is
dropped. A "production" pipeline would track a generation counter; we don't
to keep the demo simple.

### 4.5 MCP over stdio, not HTTP

MCP supports both. stdio is friendlier for an agent client running locally
(no port-binding, no auth story, same lifecycle as the client process). It
also means the workshop demo doesn't need a reverse proxy.

### 4.6 The skill is part of the deliverable

A KB is useless if the agent doesn't *use* it. The
`.claude/skills/knowledge-base/SKILL.md` companion tells the agent **when**
to query and what tools exist. The workshop should treat the skill as a
first-class artifact, not an afterthought — it's the difference between an
agent that has a KB and an agent that grounds its answers in one.

---

## 5. The "compare retrieval shapes" demo

The most original workshop slot. Same corpus, three retrieval shapes:

| Shape | Tool | Strength | Weakness |
|-------|------|----------|----------|
| Dense vector (Qdrant + fastembed) | `kb_search` | Robust to paraphrase, handles fuzzy queries | Misses precise terms; struggles with multi-word identifiers |
| Sparse / BM25 (Qdrant has a hybrid mode) | `kb_search_bm25` | High precision on technique names, codes, identifiers | Brittle to paraphrase |
| Structured lookup | `term_lookup` | Authoritative answers for closed-vocab questions | Only works inside its closed vocabulary |

Worked queries to show during the workshop:

- "How does the X-Wing work?" → dense wins (prose KB)
- "What's `BUG+1`?" → BM25 wins (rare identifier)
- **"Which class implements X-Wing in the engine?"** → annotated-code KB
  surfaces `XWingTechnique` alias; dense ranks `XYZWingTechnique` higher
  because the alias has no doxygen. **This is a live observation from the
  current `engine_api` indexer and a perfect motivation for BM25 on code.**
- "How do we translate *Naked Pair* in Russian?" → structured wins; dense
  returns plausible-sounding but wrong nearby chunks

Lesson: **vector RAG is one tool in a toolbox.** A real domain-knowledge
system mixes shapes. Picking the right shape per query is a more interesting
talking point than tuning a re-ranker.

---

## 6. Reproducibility checklist (for the workshop)

What an attendee needs on their laptop, in order:

1. Docker (Desktop or compatible).
2. `uv` (`curl -LsSf https://astral.sh/uv/install.sh | sh`).
3. `git clone` of this repo.
4. `make kb-up && make kb-install && make kb-index && make kb-sources`.
5. `make kb-search Q="x-wing fin"` — see a result.
6. Register the MCP server with their Claude Code (or other MCP client) by
   pointing at `tools/knowledge_base/.venv/bin/kb` with `serve-mcp`.

Total time from a blank machine on home wifi: ~10 minutes (most of it is
docker pulling Qdrant and uv resolving the Python deps).

---

## 7. What this *isn't*

Worth being explicit at the workshop so attendees calibrate expectations:

- Not a production-grade RAG service. No re-ranking, no query rewriting, no
  observability beyond Qdrant's own metrics.
- Not multi-tenant. Every collection assumes a single tenant.
- Not optimised for huge corpora. fastembed is CPU; this is fine for
  thousands of chunks and uncomfortable past tens of thousands.
- Not a search relevance benchmark. The "dense vs BM25 vs structured" demo
  is qualitative; if you want hard numbers, build an eval set.

---

## 8. The maintenance loop (gate / heal / grow)

A curated ontology dies if nothing actively tends it. The pipeline has
three jobs and two guard rails, all OSS-only and local-first — no CI, no
API keys, no bot tokens:

| Job | Command | Trigger |
|-----|---------|---------|
| **Gate** | `make kb-verify` | Pre-commit hook + Claude Code `PostToolUse` hook on edits under `core_engine/include/` or `docs/ontology/`. Drift surfaces immediately. |
| **Heal** | `make kb-heal [APPLY=1]` | After verify fails. Deterministic name-similarity scoring picks rename candidates; high-confidence ones can rewrite the YAML automatically. |
| **Grow** | `make kb-suggest-new [APPLY=1]` | Periodically. Finds new Technique subclasses with no ontology entry; drafts stubs from doxygen `@brief`. |

### Workshop talking points

- **Gate is cheap, heal is the magic.** The verifier is 100 lines of YAML
  + parser. The healer is interesting because it shows how far a stdlib
  `difflib`-based heuristic gets you (further than expected — exact-local-
  name matches catch namespace moves, prefix scoring catches the common
  rename pattern). No API key, no LLM, all reproducible. Heuristic
  failures motivate the "and here's where you'd plug in Claude" slide.
- **The Claude Code hook is the no-interaction part.** The agent edits a
  header, the hook runs verify, drift triggers a stderr message the
  agent's own session reads as a system reminder. The agent can then call
  `make kb-heal` itself and continue. No human in the loop until review.
  This is "agent maintains its own knowledge base" as a live demo —
  ~30 lines of bash.
- **Pre-commit is the fall-through.** When an attendee or contributor
  doesn't run the agent in their editor, the pre-commit hook still
  catches drift before push.

### Where to go next (post-workshop follow-ups)

- Add hybrid search (Qdrant's `fusion` between dense and sparse).
- Add a small evaluation harness — a YAML of (query, expected doc_uri)
  pairs scored against the current index.
- Add an "explain my retrieval" tool: given a hit, return *why* it
  matched (top contributing tokens for BM25, nearest neighbours in vector
  space for dense). Powerful pedagogically.
- Swap the embedding backend to a multilingual model and re-index.
- Swap heal's heuristic for an LLM call (Claude API): read the recent
  diff, infer the rename intent, propose a confidence-scored fix. Better
  recall on semantic renames; needs an API key.
- Extend `suggest-new` beyond Technique subclasses to other engine
  abstractions (algorithms, types, FFI surface).

## 9. Wiring the LSP (Serena) for the live-code layer

The "live code" leg of the three-layer story is realised by
[Serena](https://github.com/oraios/serena) installed globally as a
`uv tool`. The project ships:

- `.serena/project.yml` — committed, declares languages (cpp, dart),
  points clangd at `build/debug/macos/compile_commands.json` via
  `ls_specific_settings.cpp.compile_commands_dir`, ignores noisy paths
  (build output, generated Dart, `.ipp` files).
- `tools/code_intelligence/README.md` — what this layer is, how to bring it up.
- `.claude/skills/code-intelligence/SKILL.md` — when the agent should
  reach for `find_symbol` / `find_referencing_symbols` instead of grep.
- `scripts/make/ci.mk` — `make ci-install`, `ci-prepare`, `ci-register`,
  `ci-status`, `ci-mcp-list`.

**Workshop-friendly because:** Serena is an off-the-shelf MCP server, no
custom code; the project config is ~80 lines of YAML; the make targets
are wrappers around two CLI invocations. Demonstrably reproducible.

**Workshop talking points:**

- The composition: KB query → symbol name → Serena query → file:line +
  signature. One slide, two tools, no hand-wave.
- Why we didn't index code into the KB (rotting locations, worktree
  divergence — the misstep already documented in §3.3) maps cleanly to
  "and that's what Serena does instead, live, every query."
- Real failure modes worth showing: clangd needs `compile_commands.json`
  (fix: `make ci-prepare`); clangd dies on unknown extensions like
  `.ipp` (fix: exclude in `project.yml`). These are the bits attendees
  will hit on their own codebases.

The Serena fork ideas from §5 ("polyglot routing in one instance",
"warm subprocess across MCP sessions", "header-only TU trick") are still
follow-ups — the upstream binary is enough for now.

---

## 9. Open questions left to write up

- Best way to teach the "skill drives usage" point. Maybe a side-by-side:
  same agent, with-skill vs without-skill, asked the same question. The
  hallucination delta should be obvious.
- Whether to demo with Claude Code specifically or with a "any-MCP-client"
  flavour. The architecture supports either.
- How long the SudokuWiki / Hodoku ingestion section should be — risk of
  derailing into "scrape ethics" when the talk is about retrieval.
