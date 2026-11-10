# Developer workflow. `make help` lists the targets. Merge these targets into an existing Makefile if the project already has one.

SHELL := /bin/bash
.DEFAULT_GOAL := help

# A DB-bound target uses this in one recipe shell: @$(TESTDB_LOCK); …
# Delete this block when the project has no shared test database.
define TESTDB_LOCK
if ! mkdir /tmp/{{PROJECT_NAME}}-testdb.lock 2>/dev/null; then \
  echo "waiting for /tmp/{{PROJECT_NAME}}-testdb.lock — remove it if no test process is running" >&2; \
  until mkdir /tmp/{{PROJECT_NAME}}-testdb.lock 2>/dev/null; do sleep 10; done; \
fi; \
trap 'rmdir /tmp/{{PROJECT_NAME}}-testdb.lock' EXIT
endef

.PHONY: help test test-agent-rules lint docs-check hooks

help: ## List the documented targets
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  %-16s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

test: test-agent-rules ## Agent-rule contracts followed by the project test suite
	{{TEST_CMD}}

test-agent-rules: ## Paired rules, CLAUDE.md symlink and Codex hook contracts (stdlib only; no DB)
	python3 -B scripts/test_agent_rules.py

lint: ## Run the project static checks
	{{LINT_CMD}}

docs-check: ## Relative Markdown links and image paths resolve (docs/archive/ excluded)
	python3 scripts/check_docs.py

hooks: ## Enable pre-commit lint and Markdown link checks
	git config core.hooksPath .githooks
	@echo "Enabled .githooks: 'git commit' runs scripts/checks.sh."
