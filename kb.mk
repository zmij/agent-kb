# =============================================================================
# agent-kb — includable make module
# =============================================================================
# Bring-up, indexing, querying, and MCP registration for the knowledge base.
#
# From a consuming repo's Makefile:
#
#     KB_DIR      := tools/knowledge_base     # where this repo lives (submodule/clone)
#     KB_MCP_NAME := my-project-kb            # Claude Code MCP registration name
#     include $(KB_DIR)/kb.mk
#
# Every variable below is overridable before the include. Requires a kb.yaml
# at the consuming repo's root (see kb.example.yaml).

.PHONY: kb-help kb-up kb-down kb-status kb-logs kb-install kb-index kb-sources \
        kb-collections kb-search kb-mcp kb-clean kb-verify kb-heal kb-suggest-new \
        kb-register kb-unregister

KB_MK_PATH := $(lastword $(MAKEFILE_LIST))
KB_DIR ?= $(patsubst %/,%,$(dir $(KB_MK_PATH)))
KB_VENV ?= $(KB_DIR)/.venv
KB_BIN ?= $(KB_VENV)/bin/kb
# Name under which the MCP server is registered with Claude Code. Should
# match (or at least not collide with) the server name derived from kb.yaml.
KB_MCP_NAME ?= agent-kb
# Compose invocation owning the qdrant service. Point this at your own
# compose stack if qdrant is part of it (e.g. `docker compose --profile kb`).
KB_COMPOSE ?= docker compose -f $(KB_DIR)/docker-compose.yml

kb-help: ## Show knowledge-base targets
	@echo ""
	@echo "Knowledge Base Targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(KB_MK_PATH) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

kb-up: ## Start Qdrant in docker
	@$(KB_COMPOSE) up -d
	@echo "Qdrant is up on http://localhost:6333 (gRPC :6334)"

kb-down: ## Stop Qdrant (preserves the storage volume)
	@$(KB_COMPOSE) down

kb-status: ## Show Qdrant container status
	@$(KB_COMPOSE) ps

kb-logs: ## Tail Qdrant logs
	@$(KB_COMPOSE) logs -f --tail=100 qdrant

kb-install: ## Create venv and install the kb package
	@cd $(KB_DIR) && uv venv && uv pip install -e .
	@echo "kb installed in $(KB_VENV)"

kb-index: ## Index all configured sources (SOURCE=name to scope, FULL=1 to re-embed everything)
	@if [ -n "$(SOURCE)" ]; then \
		$(KB_BIN) index $(SOURCE) $(if $(FULL),--full); \
	else \
		$(KB_BIN) index --all $(if $(FULL),--full); \
	fi

kb-sources: ## List sources and collection populations (this worktree only)
	@$(KB_BIN) sources

kb-collections: ## List Qdrant collections (this worktree only; ALL=1 for every worktree)
	@if [ -n "$(ALL)" ]; then $(KB_BIN) collections --all; else $(KB_BIN) collections; fi

kb-search: ## Search the KB (Q="query text", optional SOURCE=, K=)
	@if [ -z "$(Q)" ]; then echo "Usage: make kb-search Q=\"your question\" [SOURCE=name] [K=5]"; exit 1; fi
	@$(KB_BIN) search "$(Q)" $(if $(SOURCE),--source $(SOURCE)) $(if $(K),--top-k $(K))

kb-mcp: ## Run the MCP server over stdio (for manual testing)
	@$(KB_BIN) serve-mcp

kb-register: ## Register the KB MCP server for this worktree (self-healing)
	@# Self-healing registration. Two failure modes a naive check misses:
	@#   1. Command points at another worktree's kb binary. The slug then
	@#      derives from THAT worktree's path, not this one, so every
	@#      kb_search query lands in the wrong Qdrant collection.
	@#   2. Environment lacks KB_REPO_ROOT. Without it, the binary falls
	@#      back to auto-detection from its own location, which again ties
	@#      the slug to the binary's worktree rather than the
	@#      registration's worktree.
	@# Both modes silently produce stale answers. Fix is to detect them
	@# and re-register with the correct path + env var.
	@wanted="$$(pwd)"; \
	wanted_bin="$(abspath $(KB_BIN))"; \
	current_cmd=$$(claude mcp get $(KB_MCP_NAME) 2>/dev/null | awk '/^  Command:/{print $$2}'); \
	current_env=$$(claude mcp get $(KB_MCP_NAME) 2>/dev/null | grep -E '^\s+KB_REPO_ROOT=' | head -1 | sed 's/^[[:space:]]*KB_REPO_ROOT=//'); \
	if [ "$$current_cmd" = "$$wanted_bin" ] && [ "$$current_env" = "$$wanted" ]; then \
		echo "✓ $(KB_MCP_NAME) already points at $$wanted"; \
	else \
		if [ -n "$$current_cmd" ]; then \
			echo "Refreshing $(KB_MCP_NAME) registration:"; \
			echo "  was: $$current_cmd  KB_REPO_ROOT=$$current_env"; \
			echo "  now: $$wanted_bin  KB_REPO_ROOT=$$wanted"; \
			claude mcp remove $(KB_MCP_NAME) 2>/dev/null || true; \
		fi; \
		claude mcp add $(KB_MCP_NAME) \
			-e KB_REPO_ROOT=$$wanted \
			-- $$wanted_bin serve-mcp; \
		echo "$(KB_MCP_NAME) registered with KB_REPO_ROOT=$$wanted."; \
		echo "Restart Claude Code if it was already running here."; \
	fi

kb-unregister: ## Remove the KB MCP registration for this worktree
	@claude mcp remove $(KB_MCP_NAME)

kb-verify: ## Check every ontology binding still points at a real code symbol
	@$(KB_BIN) verify

kb-heal: ## Propose (APPLY=1 to write) replacements for missing ontology bindings
	@if [ -n "$(APPLY)" ]; then $(KB_BIN) heal --apply; else $(KB_BIN) heal; fi

kb-suggest-new: ## List concept subclasses with no ontology entry (APPLY=1 to write stubs)
	@if [ -n "$(APPLY)" ]; then $(KB_BIN) suggest-new --apply; else $(KB_BIN) suggest-new; fi

kb-clean: ## Stop Qdrant and delete the storage volume (destructive)
	@$(KB_COMPOSE) down -v
