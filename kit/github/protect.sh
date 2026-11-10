#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: protect.sh OWNER/REPO [--branch main] --check "Context name" [--check ...] [--reviews N] [--dry-run]

Requires python3 and an authenticated gh (gh auth status).
The default requires a pull request with 0 approving reviews: nobody pushes to the branch
directly, a single maintainer can still merge. --reviews N (0-6) requires N approving reviews.
--dry-run prints the request without network calls.
EOF
}

fail() { printf 'Error: %s\n' "$*" >&2; exit 1; }

repo=''
branch=main
reviews=0
dry_run=false
checks=()
while (($#)); do
  case "$1" in
    --help|-h) usage; exit 0 ;;
    --branch|--check|--reviews)
      (($# >= 2)) && [[ -n "$2" && "$2" != --* ]] || fail "$1 requires a value"
      case "$1" in
        --branch) branch=$2 ;;
        --check) checks+=("$2") ;;
        --reviews) reviews=$2 ;;
      esac
      shift 2 ;;
    --dry-run) dry_run=true; shift ;;
    -*) fail "unknown option: $1" ;;
    *) [[ -z "$repo" ]] || fail 'provide one OWNER/REPO'; repo=$1; shift ;;
  esac
done
[[ "$repo" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || fail 'provide OWNER/REPO'
((${#checks[@]} > 0)) || fail 'provide at least one --check'
[[ "$reviews" =~ ^[0-6]$ ]] || fail '--reviews must be an integer from 0 to 6 (the GitHub limit)'
command -v python3 >/dev/null || fail 'python3 is required'

body=$(python3 - "$reviews" "${checks[@]}" <<'PY'
import json
import sys

reviews = {"required_approving_review_count": int(sys.argv[1])}
print(json.dumps({
    "required_status_checks": {"strict": False, "contexts": sys.argv[2:]},
    "enforce_admins": True,
    "required_pull_request_reviews": reviews,
    "restrictions": None,
    "allow_force_pushes": False,
    "allow_deletions": False,
    "required_linear_history": False,
    "required_conversation_resolution": False,
}, indent=2))
PY
)

encoded_branch=$(python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$branch")
if "$dry_run"; then
  printf 'gh api -X PUT repos/%s/branches/%s/protection --input - <<JSON\n%s\nJSON\n' "$repo" "$encoded_branch" "$body"
  exit 0
fi

command -v gh >/dev/null || fail 'gh is required'
gh auth status
printf '%s\n' "$body" | gh api -X PUT "repos/$repo/branches/$encoded_branch/protection" --input - >/dev/null
printf 'Protected %s branch %s with these settings:\n%s\n' "$repo" "$branch" "$body"
