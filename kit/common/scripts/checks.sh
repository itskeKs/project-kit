#!/usr/bin/env bash
# Run repository lint when available and always check tracked Markdown links.
# Bash 3.2 compatible (macOS default).
set -o pipefail
cd "$(dirname "$0")/.." || exit 1

status=0
python3 scripts/check_docs.py || status=1

if [ -f Makefile ] && grep -q '^lint:' Makefile; then
  make -s lint || status=1
fi

if [ "$status" -eq 0 ]; then
  printf 'checks: PASS\n' >&2
else
  printf 'checks: FAIL\n' >&2
fi
exit "$status"
