#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: protect.sh GROUP/PROJECT [--branch main] [--approvals N] [--host HOST] [--dry-run]

Requires python3 and an authenticated glab for HOST (default: $GITLAB_HOST, else gitlab.com).
Nested group paths are supported. --approvals defaults to 0 (no approval call).
Afterwards it lists CI variables that are not protected (read-only; it never changes variables).
--dry-run prints calls without authentication checks or network calls.
EOF
}

fail() { printf 'Error: %s\n' "$*" >&2; exit 1; }

project=''
branch=main
approvals=0
host=${GITLAB_HOST:-gitlab.com}
dry_run=false
while (($#)); do
  case "$1" in
    --help|-h) usage; exit 0 ;;
    --branch|--approvals|--host)
      (($# >= 2)) && [[ -n "$2" && "$2" != --* ]] || fail "$1 requires a value"
      case "$1" in
        --branch) branch=$2 ;;
        --approvals) approvals=$2 ;;
        --host) host=$2 ;;
      esac
      shift 2 ;;
    --dry-run) dry_run=true; shift ;;
    -*) fail "unknown option: $1" ;;
    *) [[ -z "$project" ]] || fail 'provide one GROUP/PROJECT'; project=$1; shift ;;
  esac
done
[[ "$project" =~ ^[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)+$ ]] || fail 'provide GROUP/PROJECT (nested groups are allowed)'
[[ "$approvals" =~ ^[0-9]+$ ]] || fail '--approvals must be a nonnegative integer'
[[ "$host" != *://* && "$host" != */* && "$host" != -* && "$host" != *[[:space:]]* ]] || fail '--host must be a hostname, optionally with a port'
command -v python3 >/dev/null || fail 'python3 is required'
approvals=$(python3 -c 'import sys; print(int(sys.argv[1]))' "$approvals")
encoded_project=$(python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$project")
encoded_branch=$(python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$branch")

api() { glab api --hostname "$host" "$@"; }
show_call() {
  printf 'glab api --hostname %q' "$host"
  printf ' %q' "$@"
  printf '\n'
}
http_error() {
  # glab prints either an HTTP status line (--include) or "(HTTP NNN)".
  local response=$1 status=$2
  [[ "$response" =~ HTTP[[:space:]]$status([^0-9]|$) || "$response" =~ HTTP/[0-9.]+[[:space:]]$status([^0-9]|$) ]]
}

if "$dry_run"; then
  show_call -X GET "projects/$encoded_project"
  project_id='<project-id>'
else
  command -v glab >/dev/null || fail 'glab is required'
  glab auth status --hostname "$host"
  project_json=$(api -X GET "projects/$encoded_project")
  project_id=$(printf '%s\n' "$project_json" | python3 -c 'import json, sys; print(json.load(sys.stdin)["id"])')
  [[ "$project_id" =~ ^[1-9][0-9]*$ ]] || fail 'the project API did not return a numeric id'
fi

protection="projects/$project_id/protected_branches"
protect_args=(-X POST "$protection" -f "name=$branch" -F push_access_level=0 -F merge_access_level=40 -F allow_force_push=false)
settings_args=(-X PUT "projects/$project_id" -F only_allow_merge_if_pipeline_succeeds=true -F allow_merge_on_skipped_pipeline=false -F only_allow_merge_if_all_discussions_are_resolved=true -F remove_source_branch_after_merge=true)
# Project approval configuration (POST per the GitLab API); approvals_before_merge is
# the project-wide minimum, approval rules per branch need a tier that has them.
approval_args=(-X POST "projects/$project_id/approvals" -F "approvals_before_merge=$approvals" -F merge_requests_author_approval=false -F reset_approvals_on_push=true)
# One page of 100 variables is enough for the report below; it only reads.
variables_path="projects/$project_id/variables?per_page=100"

if "$dry_run"; then
  printf '# Resolve <project-id> from the GET response. The next GET decides: already protected as\n# required -> nothing to do; otherwise the protection is deleted and re-created.\n'
  show_call -X GET "$protection/$encoded_branch"
  show_call -X DELETE "$protection/$encoded_branch"
  show_call "${protect_args[@]}"
  show_call "${settings_args[@]}"
  if [[ "$approvals" != 0 ]]; then
    show_call "${approval_args[@]}"
    printf '# On approval HTTP 403/404: approval rules need a GitLab tier that has them; skipped\n'
  fi
  printf '# Read-only report of CI variables with protected=false; on HTTP 403/404 check them by hand\n'
  show_call -X GET "$variables_path"
  exit 0
fi

# Access levels cannot be changed in place, so a differing protection is deleted and
# re-created. Skip that when the branch is already protected as required, and say so
# loudly if the re-creation fails: the branch is unprotected until the script is re-run.
if existing=$(api -X GET "$protection/$encoded_branch" 2>/dev/null); then
  if printf '%s\n' "$existing" | python3 -c '
import json, sys
p = json.load(sys.stdin)
push = [l["access_level"] for l in p.get("push_access_levels", [])]
merge = [l["access_level"] for l in p.get("merge_access_levels", [])]
sys.exit(0 if push == [0] and merge == [40] and not p.get("allow_force_push") else 1)
'; then
    printf 'Branch %s is already protected as required (no pushes, maintainers merge, no force push).\n' "$branch"
    recreate=false
  else
    response=$(api -X DELETE "$protection/$encoded_branch" --include 2>&1) || fail "$response"
    printf 'Removed the differing protection for %s.\n' "$branch"
    recreate=true
  fi
else
  printf 'No existing protection for %s.\n' "$branch"
  recreate=true
fi

if "$recreate"; then
  if ! response=$(api "${protect_args[@]}" 2>&1); then
    printf 'Error: creating the protection failed; branch %s is UNPROTECTED until this script succeeds:\n%s\n' "$branch" "$response" >&2
    exit 1
  fi
  printf 'Protected %s branch %s: push_access_level=0, merge_access_level=40, allow_force_push=false.\n' "$project" "$branch"
fi
api "${settings_args[@]}" >/dev/null
printf '%s\n' \
  'Set only_allow_merge_if_pipeline_succeeds=true.' \
  'Set allow_merge_on_skipped_pipeline=false.' \
  'Set only_allow_merge_if_all_discussions_are_resolved=true.' \
  'Set remove_source_branch_after_merge=true.'

if [[ "$approvals" != 0 ]]; then
  if response=$(api "${approval_args[@]}" --include 2>&1); then
    printf 'Set approvals_before_merge=%s, merge_requests_author_approval=false, reset_approvals_on_push=true.\n' "$approvals"
  elif http_error "$response" 403 || http_error "$response" 404; then
    printf '%s\n' 'approval rules need a GitLab tier that has them; skipped'
  else
    fail "$response"
  fi
fi

# MR pipelines run branch code, so any variable that is not protected is readable by it.
# Report only; changing a variable's scope can break pipelines that rely on it.
if response=$(api -X GET "$variables_path" --include 2>&1); then
  # glab --include prints the status line and headers before the JSON body, and may add
  # notices of its own (e.g. "[glab] Update available"), so take the first JSON array.
  if ! printf '%s\n' "$response" | python3 -c '
import json, re, sys
text = sys.stdin.read()
variables = None
for start in re.finditer(r"^\[", text, re.MULTILINE):
    try:
        variables, _ = json.JSONDecoder().raw_decode(text[start.start():])
        break
    except ValueError:
        continue
if not isinstance(variables, list):
    sys.exit(1)
names = []
for variable in variables:
    key = variable.get("key") if isinstance(variable, dict) else None
    if key and variable.get("protected") is False and key not in names:
        names.append(key)
for name in names:
    print(f"Warning: CI variable {name} is not protected; MR pipelines run branch code and can read it. "
          "Protect it (Settings > CI/CD > Variables) or move it to a protected environment.")
if not names:
    print(f"All {len(variables)} CI variables are protected." if variables else "No CI variables defined.")
if len(variables) == 100:
    print("Note: only the first 100 CI variables were checked; check the rest by hand.")
'; then
    printf '%s\n' 'could not read the CI variables response; check them by hand'
  fi
else
  status=''
  for code in 403 404; do
    if http_error "$response" "$code"; then status=$code; fi
  done
  [[ -n "$status" ]] || fail "$response"
  printf 'could not list CI variables (HTTP %s); check them by hand\n' "$status"
fi
