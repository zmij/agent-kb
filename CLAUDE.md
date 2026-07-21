# agent-kb

Read [AGENTS.md](AGENTS.md) — it is the canonical agent operating guide for
this repository (usage of the `kb_*` tools, the ontology maintenance loop,
and the conventions for changing this codebase).

Repo-specific quick facts:

- Install: `make install` (uv). Tests: `make test`. Never run `pip` directly.
- The package must stay project-agnostic: anything project-specific belongs
  in the consuming repo's `kb.yaml`, never hardcoded here.
- Indexers take explicit constructor params; only `kb.indexers.build()`
  reads config.
