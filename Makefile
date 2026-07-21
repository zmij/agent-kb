# Standalone entrypoints for working on agent-kb itself. Consuming repos
# include kb.mk directly instead (see README "Make integration").

include kb.mk

.PHONY: help install up down test

help: kb-help ## Show available targets

install: kb-install ## Alias for kb-install

up: kb-up ## Alias for kb-up

down: kb-down ## Alias for kb-down

test: ## Run the test suite
	@uv run pytest tests/ -q
