---
name: kb-setup
description: Bring up the agent-kb knowledge base for the current repository from scratch — check prerequisites, start Qdrant, author kb.yaml, run the first index, and verify search. USE when the user asks to set up / install / bootstrap the knowledge base or to "ground this repo", or when kb_search fails because the repo has no kb.yaml yet.
---

# KB Setup

Goal: from "plugin installed" to "kb_search answers from this repo's docs"
with as little user effort as possible. Work through the steps in order;
each is idempotent, so re-running the skill on a half-configured repo is
safe.

## 0. Locate the plugin checkout

Some fallbacks below need the plugin's own files:

```bash
KB_PLUGIN="${CLAUDE_PLUGIN_ROOT:-$(ls -d ~/.claude/plugins/cache/agent-grounding/agent-kb/*/ 2>/dev/null | sort -V | tail -1)}"
```

## 1. Preflight

```bash
uv --version          # required — stop and tell the user to install uv if missing
docker info >/dev/null 2>&1 || echo "DOCKER-DOWN"
```

If Docker is down/absent, stop: Qdrant needs it (or the user must provide
a reachable Qdrant and set `QDRANT_HOST`/`QDRANT_GRPC_PORT`).

## 2. Qdrant

Check, then start only if needed (idempotent):

```bash
curl -s -o /dev/null -w '%{http_code}' http://localhost:6333/healthz   # 200 = already up
docker run -d --name qdrant \
  -v qdrant_storage:/qdrant/storage \
  -p 6333:6333 -p 6334:6334 qdrant/qdrant
```

If the container name exists but is stopped: `docker start qdrant`.

## 3. kb.yaml

If the repo root already has one, skip ahead. Otherwise author it:

1. Survey the repo briefly: where does prose documentation live
   (`docs/`, `doc/`, `documentation/`, a wiki subtree)? Is there a
   `Makefile` with `target: ## description` comments? Is there an
   ontology directory (rare on first setup — don't invent one)?
2. Draft a minimal config — markdown sources for real doc trees, plus
   `make_targets` only if documented targets exist:

   ```yaml
   project: <repo-name>
   sources:
     docs:
       type: markdown
       root: docs
   ```

3. Confirm the draft with the user before writing (one question: doc
   roots to include). Then write it to `<repo-root>/kb.yaml`.

Full field reference: `$KB_PLUGIN/kb.example.yaml`.

## 4. First index

Preferred — through the MCP tools if the `agent-kb` server is connected:
call `kb_reindex` per source (or ask it to run all), then `kb_list_sources`.

If the MCP server isn't available yet (it launched before `kb.yaml`
existed, or the plugin was installed mid-session), fall back to the CLI —
run from the repo root so config discovery works:

```bash
uv run --project "$KB_PLUGIN" kb index --all
uv run --project "$KB_PLUGIN" kb sources
```

Expect the first run to download the embedding model (~120 MB, one-off)
and to take longer than subsequent incremental runs.

## 5. Verify

Prove retrieval end-to-end with a question the repo's docs genuinely
answer (pick one from the indexed files — not a generic query):

- MCP: `kb_search(query="<that question>")`
- CLI fallback: `uv run --project "$KB_PLUGIN" kb search "<that question>"`

Report to the user: sources indexed, point counts, the smoke query and
its top hit. If the MCP tools were unavailable this session, say so and
tell them to restart the session — the server will pick up `kb.yaml` on
the next launch.

## Failure modes

| Symptom | Fix |
|---------|-----|
| `kb_search` errors with a config message | No `kb.yaml` at or above cwd — step 3. |
| Connection refused on 6333/6334 | Qdrant not up — step 2. |
| `uv: command not found` | Install uv (https://docs.astral.sh/uv/), then retry. |
| Search returns nothing after indexing | Wrong `root:` in a source — check paths in `kb.yaml`, re-index. |
| Vector dimension mismatch | Embedding backend changed — drop the collection (`kb drop <name>`), re-index. |
