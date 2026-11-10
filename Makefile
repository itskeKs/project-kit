.PHONY: help test docs-check

help: ## List the documented targets
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z_-]+:.*## / {printf "  %-16s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

test: ## Test both bootstrap hosts and check shell scripts when shellcheck is installed
	bash tests/test_bootstrap.sh
	python3 tests/test_fill_brief.py
	python3 tests/test_kit_status.py
	@if command -v shellcheck >/dev/null 2>&1; then \
		shellcheck bootstrap.sh tests/test_bootstrap.sh kit/*/protect.sh kit/common/scripts/checks.sh; \
	elif docker info >/dev/null 2>&1; then \
		docker run --rm -v "$$PWD:/mnt:ro" koalaman/shellcheck:stable bootstrap.sh tests/test_bootstrap.sh kit/github/protect.sh kit/gitlab/protect.sh kit/common/scripts/checks.sh; \
	else \
		printf '%s\n' 'shellcheck not installed and docker not running — skipped'; \
	fi

docs-check: ## Check documentation links outside the host-specific templates
	python3 kit/common/scripts/check_docs.py --root . --exclude kit/github/ --exclude kit/gitlab/
