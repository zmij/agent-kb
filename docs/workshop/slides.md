---
marp: true
theme: gaia
class: invert
paginate: true
style: |
  section { font-size: 26px; }
  section h1 { font-size: 42px; }
  section h2 { font-size: 34px; }
  table { font-size: 22px; }
  code { font-size: 0.9em; }
  section.lead h1 { font-size: 54px; }
  blockquote { font-size: 24px; }
---

<!-- _class: lead invert -->

# Turning Vibes into Code

## A masterclass on making agents write decent code with predictable(ish) results

Sergei Fedorov · 2026

`github.com/zmij/agent-kb` · `github.com/zmij/agent-code-intel`

<!--
SAY: Good afternoon. This is a talk about coding agents — but not about
prompts. Everyone here has seen an agent do something brilliant in one
session and something embarrassing in the next. Today is about closing
that gap with engineering rather than wishful thinking.

Here's the deal for the next 75 minutes: 45 minutes of talk, 30 minutes
hands-on. And a promise: by the end of the hands-on, your own repo — on
your laptop, with zero paid APIs — will answer agent questions from YOUR
docs and YOUR code. Everything I show is open source; the two repos on
the screen are yours to keep.

Beat: "predictable-ish" in the subtitle is not false modesty — the "ish"
is load-bearing, and I'll come back to it.
-->

---

# `/whoami`

**Sergei Fedorov** — backend engineer, long-time C++ developer,
open source at `github.com/zmij`.

- **day job**: a database engine in three stacks — C++, Rust and Scala —
  of which I know exactly one, with no ambition to learn the other two
- **night job**: **Lazy Sudoku** — a cross-platform Sudoku trainer
  (C++20 · Flutter · TypeScript · Python)
- **the intersection**: making coding agents productive in codebases
  I can't — or won't — hold entirely in my own head

![w:140 github.com/zmij](assets/qr-zmij.png)

<!--
SAY: Quick introduction. By day I work on a database engine that lives
in three stacks — C++, Rust and Scala. I know exactly one of them, and
I have no ambition to learn the other two. [pause for the laugh] By
night I build a Sudoku trainer — which sounds small until you see what's
inside it, in about two slides.

The intersection of those two jobs is this talk: making coding agents
genuinely productive in codebases I can't — or, honestly, won't — hold
entirely in my own head.

Beat: that last line is the thesis in miniature. Agents are how one
person operates across more stacks than they personally master. What
follows is a practitioner's report, not a demo built for a conference.
(No employer name on the slide — the stack makes it derivable, and
that's enough.)
-->

---

# `/vibe "make me a selling website"`

## Vibe coding works. Until it doesn't.

"**Make me a selling website**" → a working site in one prompt.

Why it works: greenfield, generic domain, one language, and a million
training examples that look exactly like it.

Then you point the same agent at a production codebase —
and the vibes stop compiling.

<!--
SAY: Let's start with the part that works. You type "make me a selling
website" and twenty minutes later there's a deployed site with a hero
image and a pricing table. That's real. I'm not here to mock it — vibe
coding is genuinely great when the model's priors match the task:
greenfield, generic domain, one language, and a million training
examples that look exactly like what you asked for.

The problem starts when you point the same agent — same model, same
tooling — at a production codebase. Then the vibes stop compiling.

Transition: so let me show you what a production codebase actually looks
like. Mine happens to be about Sudoku. Bear with me — it's a trap.
-->

---

# `/init lazy-sudoku`

## The domain: it's "just Sudoku", right?

A Sudoku app looks like a weekend project:
draw a grid, enforce three rules, check the solution.

**Lazy Sudoku** is a *trainer*: it doesn't just validate your moves —
it teaches you to solve the way strong human solvers do.

That one product decision opens the rabbit hole.

<!--
SAY: A Sudoku app sounds like a weekend project. Draw a nine-by-nine
grid, enforce three rules, check against the solution. If that's all it
were, no agent would ever struggle with it.

But Lazy Sudoku is a trainer, not a validator. It doesn't just tell you
a move is wrong — it teaches you to solve the way strong human solvers
actually solve. And that single product decision opens a rabbit hole
that goes much deeper than most people expect.

Beat: the room is assuming Sudoku is trivial right now. Good. The next
two slides are the reveal — and the real point is that EVERY product in
this room has a rabbit hole like this. The agent has to navigate yours.
-->

---

# `sudoku techniques --list`

## The rabbit hole, part 1: humans don't backtrack

Human solvers apply **named deduction patterns**:

Naked Single → Naked Pair → X-Wing → Swordfish → Y-Wing →
Unique Rectangle → ALS-XZ → 3D Medusa → Exocet …

- 94 techniques visualised in-app — each one a detector,
  an explanation, and a hint rendering
- difficulty = *which techniques a solve path needs*, not how many clues
- grading = replaying a simulated human solver over the puzzle

<!--
SAY: Part one of the rabbit hole: humans don't solve Sudoku the way
computers do. No human backtracks. Humans apply named deduction
patterns — and there's a whole taxonomy of them, from Naked Single up
through X-Wing, Swordfish, Unique Rectangles, all the way to exotica
like Exocet that maybe a few hundred people in the world use.

My app visualises 94 of these. Each one needs a detector in the engine,
an explanation, and a hint rendering. Difficulty isn't "how many clues
did we remove" — it's which techniques a human needs on the solve path.
Grading a puzzle means replaying a simulated human solver over it.

Beat: linger on the names — X-Wing, ALS, BUG+1. The model HAS seen these
words on the internet. That makes its guesses about MY implementation
more confident, not more correct. These exact words come back in three
slides as hallucinations.
-->

---

# `sudoku analyse --full`

## The rabbit hole, part 2: the iceberg below

- **C++20 bitmap engine** — techniques are templates over grid geometry;
  variants (classic, diagonal, jigsaw, killer) are compile-time geometries
- **corpus pipelines** — generate, grade, and curate puzzle databases;
  cross-validate against independent reference solvers
- **three serialisation formats** (81-char, S9B, BPSE),
  FFI + WASM bridges, terminology in 14 languages
- **documentation is a stack too** — ~150k lines: help docs in
  15 languages, architecture docs, ontology, localised strings —
  on par with the engine
- four stacks, four build systems, one head:
  **C++** (engine, ~180k LoC) · **Dart** (app, ~250k) ·
  **TypeScript** (web, ~32k) · **Python** (tooling, ~28k)
  — a one-man army + agents

<!--
SAY: Part two: the iceberg below the grid. The engine is C++20, built on
bitmaps — every technique is a template over grid geometry, and variants
like diagonal, jigsaw and killer are different compile-time geometries.
Around it: corpus pipelines that generate, grade and curate puzzle
databases, cross-validated against independent reference solvers. Three
serialisation formats, an FFI bridge to Flutter, a WASM bridge to the
web, terminology in fourteen languages.

And one number people never expect: the documentation is a stack in its
own right. About a hundred and fifty thousand lines — user-facing help
in fifteen languages, architecture docs, the ontology, localised
strings. On par with the engine, bigger than TypeScript and Python
combined. Hold that thought: that corpus is exactly what we'll be
indexing later. The docs aren't overhead — they're the fuel.

Riff on the stack line, one beat per language: C++ is my one true love.
Python I can occasionally use without puking. TypeScript and Dart I have
absolutely no desire to study. And yet — [point at LoC numbers] — there
are a quarter million lines of Dart in there. Guess who wrote most of
them. That's the one-man army plus agents.

(Numbers: code is hand-written LoC, Dart excludes another ~170k of
GENERATED localisation code. Docs: ~74k unique authored markdown — help
docs 37k across 15 languages, architecture 15k, ontology 2k, the rest
READMEs/agent docs — plus ~73k of l10n string YAML, of which 5.5k are
English sources. By the end of this slide the audience should feel that
"which class implements X-Wing" is a real question with a real answer
that no pre-training run has ever seen.)
-->

---

# `/vibe --production`

## The cliff: your domain, your rules

Same agent, real product:

- "Which class implements X-Wing?" → confident hallucination
- "How do I build for an iOS device?" → invented `make` target
- "What does BPSE encode?" → plausible nonsense

**The agent's confidence does not drop when its accuracy does.**

Every one of those questions has a real answer in the codebase you
just saw — and the model's training data contains none of it.

<!--
SAY: Now the cliff. Same agent that built the selling website, pointed
at this codebase. "Which class implements X-Wing?" — a confident
hallucination; it invents a class name that sounds plausible. "How do I
build for an iOS device?" — it invents a make target that has never
existed. "What does BPSE encode?" — fluent, plausible nonsense.

And here's the line that matters: the agent's confidence does not drop
when its accuracy does. Every one of those questions has a real answer
in the codebase you just saw. The model's training data contains none
of it — and X-Wing was on the screen two minutes ago, so you know it's
not an obscure question.

Transition: the standard industry answer is "add RAG". Partially right.
But HOW the agent consumes retrieval matters more than which embedding
model you buy — that's where we go next.
-->

---

# `set -euo pipefail`

## What "predictable(ish)" actually means

You can't make an LLM deterministic. You **can** move reliability
out of the prompt and into the pipeline:

1. **Ground** — every domain claim answered by a tool, not a memory
2. **Gate** — drift caught by deterministic checks, not by review luck
3. **Drive** — the agent operates what it builds, and *sees* the result
4. **Repeat** — the same setup reproducible per repo, per worktree, per agent

Prompt engineering tunes *one conversation*.
A pipeline survives every conversation after it.

<!--
SAY: Before the machinery, let's be honest about the promise. You cannot
make a language model deterministic — the "ish" in my subtitle is
load-bearing. What you CAN do is move reliability out of the prompt and
into the pipeline around the model. Four verbs.

Ground: every domain claim gets answered by a tool, not by the model's
memory. Gate: drift gets caught by deterministic checks, not by hoping
a reviewer notices. Drive: the agent operates the thing it builds and
sees the result — not just the exit code. Repeat: the same setup works
in every repo, every worktree, every agent, every session.

Beat: this slide is the map of the rest of the talk. Every act that
follows is one of these verbs, and the recap table at the end has one
row per verb. Prompt engineering tunes one conversation; a pipeline
survives every conversation after it.
-->

---

<!-- _class: lead invert -->

# From prompts to tools

## Where reliability actually comes from

<!--
SAY: Act one. Before any code — three architectural decisions that
determine whether your grounding works. How the agent consumes
retrieval, what splits into layers, and what deliberately does NOT go
into a vector store.
-->

---

# Three ways an agent can consume retrieval

1. **Inline context stuffing** — retrieved chunks prepended to every turn
   *cheap to wire, expensive in tokens, amplifies noise*

2. **Tool-shaped retrieval** — the agent decides when to call search
   *fewer wasted tokens; the agent grounds claims selectively*

3. **Sub-agent retrieval** — a dedicated retrieval agent synthesises
   *best for deep chains; adds coordination cost*

**This workshop picks (2)** — it composes with everything else the
agent already does through tools.

<!--
SAY: Decision one: how does retrieval reach the agent? Option one,
context stuffing — search results get prepended to every turn whether
they're relevant or not. Cheap to wire, expensive in tokens, and it
amplifies noise: irrelevant chunks anchor the model on the wrong thing.
Option three, a dedicated retrieval sub-agent — powerful for deep
research chains, but you pay coordination cost on every question.

We pick option two: retrieval as a tool the agent calls when IT decides
it needs one. The agent already makes this decision shape constantly —
"should I read this file? should I run this command?" — "should I
search the KB?" is the same muscle. And MCP makes the wiring uniform
across every client.
-->

---

# Grounding splits into three layers

| Layer | Question shape | Staleness |
|-------|----------------|-----------|
| **Prose** — what we *teach* | "How does X-Wing work?" | hours–weeks |
| **Ontology** — what concepts *bind to* | "Which class implements X-Wing?" | breaks only on rename |
| **Live code** — where symbols *are* | "Who calls `applyHint` right now?" | changes every commit |

Different staleness → different storage, different retrieval shape,
different ownership.

<!--
SAY: Decision two — and if you photograph one slide from the talk half,
this is the one. Grounding is not one problem; it splits into three
layers with fundamentally different staleness.

Prose — what we teach: how does X-Wing work? That changes when a human
edits a document — hours to weeks. Ontology — what concepts bind to:
which CLASS implements X-Wing? That only breaks when someone renames
the class. And live code — where the symbol is right now, who calls it —
that changes on every commit and diverges across branches.

Beat: different staleness means different storage, different retrieval,
different ownership. Prose lives in the vector store. Ontology lives in
the vector store but is curated and verified. Live code NEVER goes in
the vector store. The next two slides are the scar tissue behind that
"never".
-->

---

# `/postmortem`

## The layer most KB talks botch

The instinct: *"index the code into the vector store."*

We did. ~3000 auto-extracted symbols (class + doxygen + `file:line`).

**Lessons, from production:**

- **Locations rot fast** — one header reflow invalidates every chunk
- **Worktree divergence** — same symbol, different line per branch
- **Dense embeddings on identifiers are noisy** — `"x-wing class"` ranked
  `XYZWingTechnique` *above* `XWingTechnique`

<!--
SAY: Because the first instinct — mine included — is: "just index the
code into the vector store too." We did exactly that. Three thousand
auto-extracted symbols: class name, doxygen comment, file and line.

Three lessons, all from production. Locations rot fast — one header
reflow and every file:line in the index is wrong. Worktrees diverge —
the same symbol sits on a different line in every branch, so which one
do you index? And the subtle one: dense embeddings are NOISY on short
identifiers. True story: the query "x-wing class" ranked XYZWingTechnique
ABOVE XWingTechnique.

Beat: that last one isn't random. XWingTechnique is a `using` alias with
no doc comment, so its embedding is starved; XYZWing has a rich
docstring. Dense retrieval optimises for the wrong thing on short names.
The infrastructure wasn't broken — the approach was.
-->

---

# The fix: split the middle layer

> "X-Wing is implemented by `XWingTechnique` over `FishTechnique`"

…was true a year ago, is true in every worktree, survives every reflow.

**The KB owns the *binding*. The LSP owns the *live resolution*.**

3000 noisy auto-chunks → ~70 curated ontology entries.
Retrieval got sharper. Infra got smaller.

<!--
SAY: The fix was to notice what actually IS stable. The sentence
"X-Wing is implemented by XWingTechnique over FishTechnique" was true a
year ago, is true today, is true in every worktree, and survives every
header reflow. The BINDING is stable; the LOCATION is volatile.

So: the knowledge base owns the binding, and the language server owns
the live resolution. We threw away three thousand noisy auto-chunks and
replaced them with about seventy curated ontology entries. Retrieval got
sharper AND the infrastructure got smaller — that's the trade you want.

Beat: re-indexing now happens when a human authors a concept entry —
human-paced, not commit-paced. And one Qdrant instance serves every
worktree, because bindings don't diverge across branches.
-->

---

# `/plugin install ×2`

## What you take home today

Two drop-in repos, MIT, OSS-only stack:

| | |
|---|---|
| **agent-kb** | Qdrant + fastembed + MCP server + ontology maintenance loop |
| **agent-code-intel** | Serena (LSP-over-MCP) operational layer: per-worktree registration, compile-DB lifecycle, fleet introspection |

`/plugin marketplace add zmij/agent-kb` → install both →
write one `kb.yaml` → grounded. **No clone required.**

Clone/submodule + `kb.mk` only if you want the `make`-target
integration (or to hack on the tools).

<!--
SAY: Before we dive into internals — here's what you take home, so you
know why the details matter. Two repos, MIT licensed, an entirely
open-source stack. agent-kb is the knowledge base: Qdrant, CPU-local
embeddings, an MCP server, and the ontology maintenance loop. agent-code-intel
is the operational layer around Serena, the LSP-over-MCP server.

Both ship as Claude Code plugins: one marketplace add, two installs,
write one kb.yaml — grounded. No clone required. You only clone if you
want the make-target integration or you want to hack on the tools.

Beat: the Sudoku project is the worked example, not the deliverable.
Both repos were EXTRACTED from it — my codebase runs the exact bits
you'll install, just with its own kb.yaml.
-->

---

<!-- _class: lead invert -->

# Ground

## The pipeline that answers instead of guessing

<!--
SAY: Act two: Ground. The pipeline that answers instead of guessing —
what's actually inside agent-kb, and the design decisions you'd want to
steal even if you build your own.
-->

---

# `kb serve-mcp`

## agent-kb architecture

```
┌────────────────────┐         ┌──────────────────────────┐
│ Agent (MCP client) │ ──────▶ │ kb serve-mcp (stdio)     │
└────────────────────┘         │  kb_search / kb_get      │
                               │  kb_list_sources         │
                               │  kb_reindex              │
                               └────────────┬─────────────┘
                                            │ gRPC
                                            ▼
     Indexers ──chunk──▶ embed ──▶ ┌──────────────────┐
     (indexers: markdown,          │ Qdrant (docker)  │
      ontology, make_targets)      └──────────────────┘
```

One container, CPU-local embeddings (BGE-small via fastembed),
no API keys anywhere.

<!--
SAY: The whole architecture fits on one slide, deliberately. The agent
speaks MCP over stdio to a small Python server exposing four tools:
search, get, list sources, reindex. Behind it, one Qdrant container.
Indexers chunk your sources, a CPU-local model embeds them — BGE-small
via fastembed, about 120 megabytes, runs anywhere — and that's it. No
API keys anywhere in the stack.

Beat: stdio, not HTTP, is a deliberate choice — no port binding, no auth
story, the server lives and dies with the client. The workshop demo
needs no reverse proxy, and neither does your laptop.
-->

---

# `cat kb.yaml`

## Sources are configuration, not code

`kb.yaml` at **your** repo root:

```yaml
project: my-project          # → collection + MCP server name
sources:
  user_docs:
    type: markdown
    root: docs/guides
    uri_prefix: "docs://guides"
  ontology:
    type: ontology
    root: docs/ontology
  make_targets:
    type: make_targets
    files: [Makefile, "scripts/make/*.mk"]
```

Three generic indexer types cover most repos. A new *type* is ~100 LoC.

<!--
SAY: What makes it drop-in: sources are configuration, not code. One
kb.yaml at YOUR repo root. The project name derives the collection and
the MCP server name. Then you declare sources: markdown trees, an
ontology directory, and — my favourite — make targets: every documented
target becomes a searchable chunk, so "how do I build for iOS" gets THE
target, not a guess.

Three generic indexer types cover most repositories. A genuinely new
type — say, OpenAPI specs — is about a hundred lines.

Beat: confession — the original indexers hardcoded MY paths. Extracting
the repo forced the honesty: "drop-in" is only true when sources are
declarative. There's a case study on that near the end.
-->

---

# Extension points: two Protocols

An **indexer** yields chunks and knows nothing about Qdrant or
embeddings; an **embedding provider** turns text into vectors and knows
nothing about sources:

```python
class Indexer(Protocol):
    def iter_chunks(self, *, should_index=None) -> Iterator[ChunkRecord]: ...

class EmbeddingProvider(Protocol):
    def embed_texts(self, texts: list[str]) -> list[list[float]]: ...
```

- adapting to your corpus = one indexer file (~100 LoC)
- `fastembed` default (CPU ONNX, no account) · `ollama` = one env var ·
  a paid API = one new file
- **caveat**: collections are dimension-locked — switching embedding
  backends means re-index (`kb index --all --full`)

<!--
SAY: If you ever fork this — and you're allowed to, it's MIT — these two
Protocols are the only seams you need. An indexer yields chunks and
knows nothing about Qdrant or embeddings. An embedding provider turns
text into vectors and knows nothing about sources. The runner between
them does chunk, embed, upsert — with retries and incremental hashing.

Practically: adapting to your corpus is one indexer file. Swapping
fastembed for ollama is one environment variable. A paid embedding API
is one new file. One caveat worth writing down: collections are
dimension-locked, so switching backends means a full re-index.

Beat: the design invariant worth saying aloud — classes take explicit
constructor parameters; only the factory reads config. That's what keeps
every piece testable without infrastructure, and forkable in an
afternoon.
-->

---

# `kb index`

## Chunking & incremental indexing

**Chunking**: heading-aware markdown — split at H2/H3, keep
`heading_path` + anchor so every hit links back to a stable location.

**Incremental**: content-hash per file; only changed files re-embed.

**Deterministic ids**: `uuid5(ns, "source::path::heading::part")` —
re-indexing is idempotent.

**War story (this week):** a changed file that now yields *zero* chunks
was seen (not an orphan) but in no upsert batch (never evicted) —
its stale chunks survived every incremental run.

<!--
SAY: Indexing mechanics, quickly, because two details carry all the
weight. Chunking is heading-aware: split at H2 and H3, keep the heading
path and anchor, so every search hit links back to a stable place in a
document. Ids are deterministic — a uuid5 of source, path, heading and
part — which makes re-indexing idempotent. And it's incremental:
content-hash per file, only changed files re-embed.

Then the war story, from THIS week: a file changed so that it now
yields ZERO chunks. It wasn't an orphan — the file still exists. It was
in no upsert batch — nothing to write. So its stale chunks survived
every incremental run, forever. Found it because a make module got
extracted and its old targets kept answering searches.

Beat: edge cases in incremental indexing are where the real bugs live.
If you build your own, steal this test case.
-->

---

# `git worktree list`

## Worktrees: one Qdrant, many branches

Each worktree writes to collections suffixed with its slug:

```
sudoku_theory_backend
sudoku_theory_frontend
sudoku_theory_aic_als
```

- concurrent indexing never collides
- `kb collections --all` shows the fleet
- the ontology is *identical* across worktrees — only prose drifts

<!--
SAY: Real development happens in parallel branches — I run several git
worktrees at once, each with an agent in it. So each worktree writes to
its own collections, suffixed with the worktree's name. Concurrent
indexing never collides; one Qdrant container serves the whole fleet;
and there's a command to see what every worktree has indexed.

Beat: notice what this proves about the layer split — the ontology is
IDENTICAL across worktrees, because bindings don't diverge across
branches; only prose drifts. Anything keyed to file-and-line would have
forced one index per worktree per commit. The architecture decision
from act one is what makes the worktree story cheap.
-->

---

# `/skills`

## The skill is part of the deliverable

A KB the agent doesn't *use* is a Qdrant container burning RAM.

Ship a skill / instructions file that tells the agent **when**:

> Search **before asserting**, not after failing.
> About to name the class implementing a concept? → `kb_search(source="ontology")`
> About to quote a `make` invocation? → `kb_search(source="make_targets")`

- `agent-kb` plugin — ships the generic operating skill
- your repo's `CLAUDE.md` — project-specific routing table

<!--
SAY: Here's the lesson that took me longest to learn, and it isn't
technical. A knowledge base the agent doesn't USE is just a Qdrant
container burning RAM. Wiring the tool is not enough — you have to
teach the agent WHEN to reach for it.

The rule that changed behaviour: search BEFORE asserting, not after
failing. About to name the class implementing a concept? Search the
ontology first. About to quote a make invocation? Search make targets
first. That guidance ships as a skill inside the plugin; your repo's
CLAUDE.md adds the project-specific routing on top.

Beat: if there's time in Q&A, the side-by-side demo — same agent, same
question, with and without the skill — lands this better than any
slide. The hallucination delta is the whole talk in ten seconds.
-->

---

# `kb_get x-wing`

## Ontology entry anatomy

```markdown
---
concept: x-wing
title: X-Wing
kind: technique
implements:
  - sudoku::XWingTechnique
underlying:
  - sudoku::FishTechnique
related_concepts: [swordfish, jellyfish]
---

A fish pattern on two rows and two columns…
```

Symbol list is baked into the embeddable text → "which class implements
X-Wing" hits the *names*, not just prose.

Payload carries the bindings structurally — agents read them without parsing.

<!--
SAY: What does an ontology entry actually look like? A small markdown
file. Frontmatter carries the bindings — X-Wing is implemented by
XWingTechnique, over FishTechnique, related to Swordfish and Jellyfish.
Below it, a line or two of prose for humans.

Two implementation details do the work. The symbol names are baked into
the text that gets embedded — that's why "which class implements
X-Wing" now hits the right entry; the names themselves are in the
vector. And the payload carries the bindings structurally, so the agent
reads them as data, no parsing, no guessing.

Beat: seventy of these cover my entire engine. Writing one takes a
minute — and there's tooling coming in the next act that drafts them
for you.
-->

---

# Retrieval shapes: vector RAG is one tool

| Query | Winner |
|-------|--------|
| "How does X-Wing work?" | **dense** — robust to paraphrase |
| "What's `BUG+1`?" | **BM25/sparse** — rare identifier |
| "Which class implements X-Wing?" | **ontology** — curated binding (dense alone ranked the wrong class!) |
| "*Naked Pair* in Russian?" | **structured lookup** — closed vocabulary, similarity is the wrong question |

A real system routes per query shape. That routing beats re-ranker tuning.

<!--
SAY: Closing the Ground act with the uncomfortable truth about
retrieval: dense vector search is ONE tool, not THE tool. "How does
X-Wing work" — dense wins, it's robust to paraphrase. "What's BUG+1" —
a rare identifier, sparse keyword search wins. "Which class implements
X-Wing" — the curated binding wins; you saw dense rank the wrong class.
And "what's Naked Pair in Russian" — that's a closed vocabulary; the
translator wants THE term, not a similar sentence. Similarity is the
wrong question entirely.

Beat: a real system routes per query shape, and that routing beats any
amount of re-ranker tuning. The multilingual example is from my
fourteen-language localisation pipeline — same Qdrant, different tool.
Not shipped in v1; it's a documented extension point.
-->

---

<!-- _class: lead invert -->

# Gate & Repeat

## Deterministic guardrails around a stochastic collaborator

<!--
SAY: Act three: Gate and Repeat. We've made the agent answer from the
repo. Now — how do we stop the knowledge from rotting, and how do we
make the whole setup survive contact with branches, worktrees and
colleagues? Deterministic guardrails around a stochastic collaborator.
-->

---

# `kb verify && kb heal`

## Curated bindings need a maintenance loop

| Job | Command | Trigger |
|-----|---------|---------|
| **Gate** | `kb verify` | pre-commit + editor hook: every binding must resolve to a real symbol |
| **Heal** | `kb heal --apply` | after a rename: name-similarity scoring proposes fixes, ≥0.85 auto-applies |
| **Grow** | `kb suggest-new --apply` | finds concept classes with no entry; drafts stubs from doxygen |

All deterministic, stdlib-only, reproducible without an API key.

<!--
SAY: Curation has a cost: curated things rot. So the ontology gets a
maintenance loop with three jobs. Verify is the gate: every binding
must resolve to a real symbol in the current headers — non-zero exit on
drift, wired into pre-commit. Heal runs after a rename: name-similarity
scoring proposes the fix, and above 0.85 confidence it applies
automatically. And suggest-new grows the ontology: it finds concept
classes with no entry and drafts the stub from the doc comment.

Beat: all three are deterministic, standard-library-only, no API key —
they produce the same answer on every machine, which is what makes them
trustworthy as gates.

DEMO (90 seconds, if live demos are on): rename XWingTechnique in a
scratch header → verify fails → heal proposes the fix with a confidence
score → apply → verify green. Lands the point: the ontology CANNOT
silently rot.
-->

---

# `on PostToolUse: kb verify`

## The agent maintains its own KB

~30 lines of bash as a `PostToolUse` hook:

1. Agent edits an engine header
2. Hook runs `kb verify` against the edited worktree
3. Drift → stderr message → the agent's own session sees it
4. Agent runs `kb heal`, re-verifies, continues

No human in the loop until code review.

Pre-commit is the fall-through for humans who bypass the agent.

<!--
SAY: Now close the loop. Thirty lines of bash, registered as a
post-tool-use hook in the agent harness. The agent edits an engine
header. The hook runs verify against the edited worktree. If a binding
broke, the message lands in the agent's OWN session — and the agent
runs heal, re-verifies, and continues. No human in the loop until code
review. Pre-commit catches the humans who bypass the agent.

Beat: this is the "self-maintaining knowledge" money-slide, and I want
to be precise about what it is NOT. It's not AGI. It's a bash hook and
a deterministic verifier. That's the charm — boring machinery producing
agentic behaviour. The agent keeps its own knowledge base honest as a
side effect of doing its normal work.
-->

---

# `find_symbol FishTechnique`

## Layer 3: live code — don't build it, wire it

[Serena](https://github.com/oraios/serena): off-the-shelf LSP-over-MCP.
clangd (C++), Dart Analysis Server, typescript-language-server, pyright —
one server, symbol-keyed tools:

`find_symbol` · `find_referencing_symbols` · `get_symbols_overview`

**agent-code-intel** packages what makes it reliable *operationally*:

- self-healing per-worktree registration
- compile-DB lifecycle for clangd
- dashboards + usage introspection across worktrees

<!--
SAY: The third layer — live code — and the punchline is: don't build
it. Wire it. Serena is an off-the-shelf project that puts language
servers behind MCP: clangd for C++, the Dart analyser,
typescript-language-server, pyright. One server, and the agent gets
symbol-keyed tools — find this symbol, find who references it, give me
an overview of this file.

Why an LSP? Because the language server is ALREADY maintaining exactly
the index you need — incrementally, for free, in every language of a
polyglot repo. Indexing code into a vector store rebuilds a worse
version of something your editor already has.

Beat: what agent-code-intel adds is purely operational — the per-worktree
registration, the compile-database lifecycle for clangd, dashboards
across worktrees. The gap between "works in a demo" and "works every
day" is operational, and that's the next slide.
-->

---

# The failure mode worth a slide

A Serena registration whose `--project` points at **another worktree**
answers every `find_symbol` from the wrong source tree.

**Silently.**

```
make ci-register    # detects stale --project / missing env
                    # re-registers with THIS worktree's path
```

Same class of bug as the KB: `kb-register` bakes `KB_REPO_ROOT=$(pwd)`
into the MCP registration so collection scoping follows the *worktree*,
not the binary's location.

<!--
SAY: One failure mode earned its own slide. A Serena registration whose
project argument points at ANOTHER worktree answers every symbol query
from the wrong source tree. Silently. The agent asks "where is
FishTechnique", gets a real answer — real file, real line — from a
DIFFERENT branch. Nothing errors. Everything is subtly wrong.

"Silently wrong" is strictly worse than "down", because health checks
that only test liveness pass. The fix is self-healing registration:
ci-register compares the registration's config against the current
directory and repairs it. The KB had the same class of bug — solved the
same way.

Beat: found both the hard way. And an update from this week: the plugin
packaging retired the KB half of this story — the server now discovers
the repo root by walking up from the session's directory. Serena keeps
the make-based registration, because compile databases are inherently
per-checkout.
-->

---

# `kb_search → find_symbol`

## Composition: the canonical two-step

*"Extend the X-Wing detector"*

```
1. kb_search("x-wing engine class", source="ontology")
      → sudoku::XWingTechnique  (alias of FishTechnique)

2. find_symbol("FishTechnique")
      → core_engine/include/sudoku/techniques/fish.hpp:125

3. find_referencing_symbols("FishTechnique")
      → scanner, registry, hint pipeline call sites
```

KB: *which* symbol. LSP: *where* it is and *who* touches it.
Neither can do the other's job.

<!--
SAY: And here's the whole system working together — the canonical
two-step, on a real task: "extend the X-Wing detector." Step one, the
KB: which symbol implements the concept? XWingTechnique, which is an
alias of FishTechnique — a fact no grep would surface. Step two, the
LSP: where is FishTechnique right now, in THIS worktree? fish.hpp, line
125. Step three, the LSP again: who touches it? The scanner, the
registry, the hint pipeline — the blast radius, before any edit.

Beat: the KB answers WHICH. The LSP answers WHERE and WHO. Neither can
do the other's job — and that division is the entire three-layer thesis
in one worked example. Every code-touching task in my repo starts with
this dance, and the agent does it unprompted because the skill tells
it to.
-->

---

<!-- _class: lead invert -->

# Drive

## The agent operates what it builds

<!--
SAY: Act four — Drive. This is the verb most teams skip. We've taught
the agent to read and to keep knowledge honest. Now: the agent operates
what it builds. Because "the tests pass" and "the feature exists" are
different claims.
-->

---

# `/run`

## Teach the agent to *use* the software, not just build it

Build passing + tests green is table stakes. The step change is when
the agent **operates the product**:

- **CLI as MCP tools** — `sudoku analyse / hints / step`: the agent asks
  the engine instead of reciting Sudoku theory from memory
- **App puppetry** — spawn the debug build, hot-reload, navigate, tap
  cells, request hints, take screenshots — then *look* at them
- **External surfaces** — reference solvers, store APIs, deploy status:
  same tool discipline, one ring further out

An agent that can **see what it changed** stops hallucinating
that it worked.

<!--
SAY: Building and testing is table stakes — any agent can run make and
read the exit code. The step change comes when the agent OPERATES the
product. Three rings, all real and running in my repo.

The CLI as MCP tools: when the agent needs to know what hint applies to
a puzzle, it asks the engine — it doesn't recite Sudoku theory from
memory. App puppetry: the agent spawns the debug build, hot-reloads its
own edit, navigates, taps cells, requests hints, takes a screenshot —
and then LOOKS at the screenshot. And external surfaces — reference
solvers, store APIs, deployment status — same discipline, one ring out.

Beat: the loop that changed my daily work is edit → hot reload →
screenshot → the agent reads the pixels it produced. An agent that can
SEE what it changed stops hallucinating that it worked. That's Gate
applied to behaviour, not just knowledge.
-->

---

# `SKILL.md`

## Rolling your own: an operational skill for *any* product

Every product has operable surfaces. The recipe is always the same four steps:

1. **Launch** — one reproducible way up: a `make` target, a debug build,
   `docker compose up`
2. **Drive** — a tool per surface: scripts wrapping your **CLI**,
   scripts calling your **API**, a browser MCP clicking through your
   **web app**
3. **Observe** — make results machine-readable: JSON output, response
   bodies, logs, screenshots the agent actually reads
4. **Route** — a `SKILL.md` that tells the agent *when* to reach for
   which surface — and when the result means "stop and look"

Start with the surface you debug by hand most often —
that's where the agent burns your time guessing.

<!--
SAY: You don't have a Sudoku engine, so here's the recipe in the
abstract — four steps, any product. Launch: one reproducible way to
bring the thing up — a make target, a debug build, docker compose.
Drive: one tool per surface — scripts wrapping your CLI, scripts
calling your API, and for web apps, a browser MCP that actually clicks
through your UI. Observe: make the results machine-readable — JSON
output, response bodies, logs, screenshots the agent actually reads.
Route: a SKILL.md that tells the agent when to reach for which surface.

Beat: step three is the one everyone skips, and it's the difference
between verification and theatre — driving without observing is how
agents "verify" things that never happened. And a practical starting
point: begin with the surface YOU debug by hand most often. That's
where the agent is currently burning your time guessing.
-->

---

# Case study: making "drop-in" true

Extracting these repos from the monorepo forced honest generalisation:

| Was hardcoded | Became |
|---------------|--------|
| `docs/ui/en/techniques` + `docs/*.md` indexers | one `markdown` type + `kb.yaml` sources |
| `core_engine/include/sudoku`, `public Technique` | `symbols.include_root`, `base_classes` |
| collection `sudoku_theory`, server `lazy-sudoku-kb` | derived from `project:` |
| make targets with baked paths | includable `kb.mk`/`ci.mk` + `KB_*`/`CI_*` vars |

Rule that survived: **classes take explicit params; only the factory
reads config.** That's what kept every test runnable without a `kb.yaml`.

<!--
SAY: A short honesty case study before the recap. Two weeks ago none of
this was installable — it lived inside my monorepo with my paths
hardcoded everywhere. Extracting the repos forced the generalisation:
hardcoded doc paths became declarative kb.yaml sources; my C++ include
root and base class became symbols configuration; collection and server
names now derive from the project name; and the make targets became
includable modules with variables.

Beat: one design rule survived the whole extraction — classes take
explicit constructor parameters, only the factory reads config. That
single rule is why every test still ran without a kb.yaml at any point
during the surgery. And my monorepo now consumes the extracted repos as
submodules with a fifteen-line shim — same targets, same collections,
the agents already using it never noticed. That's the Repeat verb, made
concrete.
-->

---

# `/compact`

## Four things to teach your agent

| Teach the agent… | With | Backed by |
|------------------|------|-----------|
| …the **domain** | app concepts & user-facing docs | **KB** |
| …the **architecture** | architecture & design docs | **KB + LSP** |
| …to **find & edit fast** | ontology: concept → symbol bindings | **KB + LSP** |
| …to actually **USE the product** | CLI / API / app / browser tooling | **MCP + skills** |

Each row is boring on its own. Together they're the difference
between vibes and a pipeline.

<!--
SAY: The whole talk in one table — this is the photograph slide, take
your time. [pause] Teach the agent the domain: your concepts and your
user-facing docs, through the KB. Teach it the architecture: your
design docs, KB plus the language server. Teach it to find and edit
fast: the ontology bindings, KB plus LSP. And teach it to actually USE
the product: CLI, API, app, browser — MCP and skills.

Rows one to three are Ground and Gate. Row four is Drive — and it's
where most teams stop short: they teach the agent to read and never
teach it to drive.

The one line to say over this table: the KB owns the binding, the LSP
owns the resolution, the agent owns the question.

Bridge: the hands-on we start in a minute builds rows one to three in
fifteen minutes. Row four is your homework, and the SKILL.md recipe is
the template.
-->

---

<!-- _class: lead invert -->

# Hands-on

## Your repo, grounded, in ~15 minutes

<!--
SAY: Talk's over — laptops out. Thirty minutes, three five-minute
stages plus buffer, and the goal from the title slide: YOUR repo
answering agent questions from YOUR docs before you leave the room.
Helpers and the Wi-Fi password are on the whiteboard.
-->

---

# `/kb-setup`

## Hands-on: bring-up (5 min)

Prereqs: Docker, `uv`. **No clone.**

```
/plugin marketplace add zmij/agent-kb
/plugin install agent-kb@agent-grounding
/plugin install agent-code-intel@agent-grounding
```

Restart the session in **your** repo, then:

```
/kb-setup
```

The bundled skill does the rest: checks prerequisites, starts Qdrant,
asks which doc trees to index, writes `kb.yaml`, runs the first index,
and verifies search — **the agent sets up its own grounding.**

<!--
SAY: Stage one, bring-up. Prerequisites: Docker and uv — no clone, no
checkout. Add the marketplace, install both plugins, restart your agent
session inside YOUR repo, and type /kb-setup.

Then watch what happens rather than typing along: the agent checks your
prerequisites, starts Qdrant, looks at your repo, asks you ONE question —
which doc trees to index — writes the kb.yaml, runs the first index,
and verifies with a real search. The agent sets up its own grounding.
That sentence is the whole workshop in miniature.

Staging: kb-setup is idempotent — re-running on a half-configured repo
is safe, so nobody can brick anything. The wall-clock sinks are the
Qdrant docker pull and the one-time 120-megabyte embedding model
download — I have both on USB sticks if the venue Wi-Fi melts.
-->

---

# `/mcp`

## Hands-on: wire the agent (5 min)

Claude Code: already wired — check that `/mcp` lists **agent-kb**.

Then prove it: ask a question **your docs answer and the model's
pre-training doesn't**, and watch `kb_search` fire instead of a guess.

Any other MCP client — wire by hand:

```bash
claude mcp add my-project-kb -e KB_REPO_ROOT=$(pwd) -- \
  /path/to/agent-kb/.venv/bin/kb serve-mcp
# (or clone + make kb-register — self-healing)
```

<!--
SAY: Stage two, prove the wiring. On Claude Code there's nothing to
wire — the plugin did it. Type /mcp and check agent-kb is in the list.
Then the moment that matters: ask your agent a question that YOUR docs
answer and the model's pre-training doesn't. Something with your
product's vocabulary in it. Watch the tool call fire — kb_search, with
your query — instead of a guess.

On any other MCP client, the manual incantation is on the slide: point
it at the kb binary with your repo root in the environment.

Staging: walk the room during this stage — the best sound in a workshop
is someone saying "oh, it actually cited MY doc". Collect one or two of
those answers to read out before stage three.
-->

---

# Hands-on: make it yours (5 min)

Pick one:

- **Ontology starter** — write 3 concept entries for your domain,
  add a `symbols:` section, run `kb verify`
- **Make targets** — add `## descriptions` to 5 targets, index,
  ask the agent "how do I …"
- **Break it** — rename a bound class, watch `verify` fail and
  `heal` propose the fix

Then: re-ask the question the agent hallucinated this morning —
and diff the answers.

<!--
SAY: Stage three — pick one path, based on what your repo looks like.
If your product has a domain vocabulary: write three ontology entries
and run verify. If your repo runs on make: add doc-comments to five
targets, index, and ask the agent "how do I…" — this one has the best
effort-to-payoff ratio in the room. If you like breaking things: rename
a bound class, watch verify fail, watch heal propose the fix with a
confidence score.

And then the closing move, whatever path you took: re-ask the question
your agent hallucinated on this morning — and diff the answers. Same
agent, same question. The behaviour change is already installed; the
skills arrived with the plugin. There's nothing to paste.

Beat: that diff is the emotional payoff of the whole session — give it
the last word before the roadmap.
-->

---

# `/roadmap`

## Where to go next

- **Hybrid search** — Qdrant fusion of dense + sparse (the `BUG+1` fix)
- **Eval harness** — YAML of (query, expected `doc_uri`) pairs
- **"Explain my retrieval"** — why did this hit rank? (pedagogically great)
- **Multilingual embeddings** — swap model, re-index, ground 14 languages
- **LLM-backed heal** — read the diff, infer rename intent
  (better recall than `difflib`, costs an API key)
- **More parsers** — `parse_header()` for your language; PRs welcome

<!--
SAY: Scope honesty first, so nobody leaves with the wrong impression:
this is NOT a production RAG service. No re-ranking, no query
rewriting, not multi-tenant. The CPU embeddings are comfortable at
thousands of chunks and get uncomfortable past tens of thousands. And
the retrieval-shapes comparison is qualitative, not a benchmark.

What it IS: reproducible, inspectable, and small enough to fork the
same afternoon — which is exactly why everything on this list is
approachable. Hybrid search fixes the rare-identifier case you saw.
An eval harness is a YAML file away. Explain-my-retrieval is the most
teachable feature nobody ships. Multilingual embeddings, an LLM-backed
heal for better rename recall, and parsers for your language — the
parser interface is one function, and PRs are welcome. Genuinely.
-->

---

<!-- _class: lead invert -->

# `/exit`

**Thanks!**

![w:150 agent-kb](assets/qr-agent-kb.png) ![w:150 agent-code-intel](assets/qr-agent-code-intel.png) ![w:150 Download Lazy Sudoku](assets/qr-install.png)

`agent-kb` · `agent-code-intel` · **Download Lazy Sudoku** — the reference app

*Vibes are a prompt. Predictability is a pipeline.*

<!--
SAY: That's the session. Two QR codes for the repos — everything you
saw today, MIT licensed, installable before you leave the room. The
third one is the reference app itself: all of this machinery exists so
that one person can ship a four-stack product — so download the game,
and if you find a bug, well, now you know exactly how it'll get fixed.

Close: vibes are a prompt. Predictability is a pipeline. Thank you.

Staging: leave this slide up through the entire Q&A — the QRs are the
takeaway, and phones need time.
-->
