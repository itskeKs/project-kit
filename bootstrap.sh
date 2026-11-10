#!/usr/bin/env bash
set -euo pipefail

usage() {
    printf 'Usage: %s TARGET_DIR --host gitlab|github [--default-branch NAME] [--dry-run]\n' "$0" >&2
    printf '  --default-branch NAME  default branch of the target (default: its current branch, else main)\n' >&2
}

bad_args() {
    printf '%s\n' "$1" >&2
    usage
    exit 2
}

[[ $# -gt 0 ]] || bad_args 'TARGET_DIR is required.'
target=$1
shift
[[ "$target" != -* ]] || bad_args 'TARGET_DIR must be the first argument.'
host=''
default_branch=''
dry_run=false
while [[ $# -gt 0 ]]; do
    case "$1" in
        --host)
            [[ $# -ge 2 ]] || bad_args '--host requires gitlab or github.'
            [[ -z "$host" ]] || bad_args '--host may only be given once.'
            host=$2
            shift 2
            ;;
        --default-branch)
            [[ $# -ge 2 ]] || bad_args '--default-branch requires a branch name.'
            [[ -z "$default_branch" ]] || bad_args '--default-branch may only be given once.'
            command -v git > /dev/null 2>&1 || bad_args 'git is required to validate --default-branch.'
            # The name lands in YAML lists, shell snippets and prose of the copied files, so only
            # letters, digits, dot, underscore, slash and dash are accepted; --branch also expands
            # forms such as @{-1}, so accept only a name that maps to itself.
            [[ -n "$2" && "$2" =~ ^[A-Za-z0-9._/-]+$ ]] || bad_args "--default-branch is not a valid branch name: $2"
            [[ $(git check-ref-format --branch "$2" 2> /dev/null) == "$2" ]] || \
                bad_args "--default-branch is not a valid branch name: $2"
            default_branch=$2
            shift 2
            ;;
        --dry-run)
            [[ "$dry_run" == false ]] || bad_args '--dry-run may only be given once.'
            dry_run=true
            shift
            ;;
        *) bad_args "Unknown argument: $1" ;;
    esac
done

case "$host" in
    github)
        host_name=GitHub
        host_cli=gh
        host_pr='pull request'
        host_pr_abbr=PR
        host_issue_template='.github/ISSUE_TEMPLATE/task.md'
        host_pr_template='.github/PULL_REQUEST_TEMPLATE.md'
        host_ci_file='.github/workflows/tests-on-pr.yaml'
        host_issue_view='gh issue view N -R {{REPO}}'
        host_security_channel="GitHub's private report form: <https://github.com/{{REPO}}/security/advisories/new>"
        host_registry_image='ghcr.io/{{REPO}}'
        ;;
    gitlab)
        host_name=GitLab
        host_cli=glab
        host_pr='merge request'
        host_pr_abbr=MR
        host_issue_template='.gitlab/issue_templates/Default.md'
        host_pr_template='.gitlab/merge_request_templates/Default.md'
        host_ci_file='.gitlab-ci.yml'
        host_issue_view='glab issue view N -R {{REPO}}'
        host_security_channel="a confidential issue (\`glab issue create --confidential -R {{REPO}}\`), visible only to project members"
        host_registry_image='registry.gitlab.com/{{REPO}}'
        ;;
    *) bad_args '--host must be gitlab or github.' ;;
esac

if [[ ! -d "$target" ]]; then
    printf 'Target directory must already exist: %s\n' "$target" >&2
    printf 'Create it first: mkdir -p %q && git -C %q init -b %q\n' "$target" "$target" "${default_branch:-main}" >&2
    usage
    exit 2
fi

KIT_DIR=$(cd "$(dirname "$0")" && pwd)
target=$(cd "$target" && pwd)
# Without --default-branch, take the remote's default branch (origin/HEAD), then the target's
# current branch; main when it is not a git repository, git is missing, or HEAD is detached.
# The current branch is a guess: a kit added from a feature branch must still name the real one.
if [[ -n "$default_branch" ]]; then
    default_branch_source='given with --default-branch'
elif default_branch=$(git -C "$target" symbolic-ref --quiet --short refs/remotes/origin/HEAD 2> /dev/null) && [[ "$default_branch" == origin/?* ]]; then
    default_branch=${default_branch#origin/}
    default_branch_source='default branch of the remote origin; override with --default-branch NAME'
elif default_branch=$(git -C "$target" symbolic-ref --quiet --short HEAD 2> /dev/null) && [[ -n "$default_branch" ]]; then
    default_branch_source='current branch of the target, which has no origin/HEAD; if this is a feature branch, re-run with --default-branch NAME'
else
    default_branch=main
    default_branch_source='the target is not a git repository or has a detached HEAD; override with --default-branch NAME'
fi
for source in "$KIT_DIR/kit/common" "$KIT_DIR/kit/$host/repo"; do
    if [[ ! -d "$source" ]]; then
        printf 'Missing kit directory: %s\n' "$source" >&2
        exit 1
    fi
done
if [[ "$dry_run" == false ]] && ! command -v python3 > /dev/null 2>&1; then
    printf 'python3 is required to substitute HOST tokens.\n' >&2
    exit 1
fi

# A sentinel keeps these arrays defined with nounset on Bash 3.2.
copied_paths=('')
skipped_paths=('')
copied_count=0
skipped_count=0

already_planned() {
    local planned
    for planned in "${copied_paths[@]}"; do
        [[ "$planned" != "$1" ]] || return 0
    done
    return 1
}

# Every ancestor of a destination must be a real directory (or absent): a file in the
# way would abort the run half-way, a symlink would write outside the target.
parents_ok() {
    local ancestor=$1
    while [[ "$ancestor" == */* ]]; do
        ancestor=${ancestor%/*}
        if [[ -L "$target/$ancestor" ]] || [[ -e "$target/$ancestor" && ! -d "$target/$ancestor" ]]; then
            return 1
        fi
    done
    return 0
}

substitute_host_tokens() {
    # Empty files and binary files need no token substitution.
    grep -Iq . "$1" || return 0
    KIT_HOST="$host_name" KIT_HOST_CLI="$host_cli" \
    KIT_HOST_PR="$host_pr" KIT_HOST_PR_ABBR="$host_pr_abbr" \
    KIT_HOST_ISSUE_TEMPLATE="$host_issue_template" KIT_HOST_PR_TEMPLATE="$host_pr_template" \
    KIT_HOST_CI_FILE="$host_ci_file" KIT_HOST_ISSUE_VIEW="$host_issue_view" \
    KIT_HOST_SECURITY_CHANNEL="$host_security_channel" KIT_HOST_REGISTRY_IMAGE="$host_registry_image" \
    KIT_DEFAULT_BRANCH="$default_branch" \
    python3 - "$1" <<'PY'
import os
from pathlib import Path
import sys

path = Path(sys.argv[1])
content = path.read_bytes()
for token in (
    "HOST", "HOST_CLI", "HOST_PR", "HOST_PR_ABBR", "HOST_ISSUE_TEMPLATE",
    "HOST_PR_TEMPLATE", "HOST_CI_FILE", "HOST_ISSUE_VIEW",
    "HOST_SECURITY_CHANNEL", "HOST_REGISTRY_IMAGE",
    # Last: a branch name that looks like a token must not be expanded again.
    "DEFAULT_BRANCH",
):
    content = content.replace(
        ("{{" + token + "}}").encode("ascii"),
        os.environ["KIT_" + token].encode("utf-8"),
    )
path.write_bytes(content)
PY
}

# The kit never ships bytecode: __pycache__ and *.pyc appear when scripts are run inside the kit.
for source in "$KIT_DIR/kit/common" "$KIT_DIR/kit/$host/repo"; do
    while IFS= read -r -d '' source_file; do
        relative=${source_file#./}
        destination="$target/$relative"
        if [[ -e "$destination" || -L "$destination" ]] || already_planned "$relative"; then
            skipped_paths+=("$relative")
            skipped_count=$((skipped_count + 1))
            continue
        fi
        if ! parents_ok "$relative"; then
            skipped_paths+=("$relative (a parent is a file or a symlink)")
            skipped_count=$((skipped_count + 1))
            continue
        fi
        if [[ "$dry_run" == false ]]; then
            mkdir -p "$(dirname "$destination")"
            cp -p "$source/$relative" "$destination"
            # Substitute at once: an interrupted run must never leave a copied file with HOST tokens.
            substitute_host_tokens "$destination"
        fi
        copied_paths+=("$relative")
        copied_count=$((copied_count + 1))
    done < <(cd "$source" && find . -name __pycache__ -prune -o -type f ! -name '*.pyc' -print0)
done

if [[ -e "$target/CLAUDE.md" || -L "$target/CLAUDE.md" ]] || already_planned CLAUDE.md; then
    skipped_paths+=(CLAUDE.md)
    skipped_count=$((skipped_count + 1))
    symlink_action='skipped (already present)'
elif [[ ! -e "$target/AGENTS.md" ]] && ! already_planned AGENTS.md; then
    skipped_paths+=('CLAUDE.md (no AGENTS.md to link to)')
    skipped_count=$((skipped_count + 1))
    symlink_action='skipped (no AGENTS.md)'
elif [[ "$dry_run" == true ]]; then
    symlink_action='would create'
else
    ln -s AGENTS.md "$target/CLAUDE.md"
    symlink_action=created
fi

if [[ "$dry_run" == true ]]; then
    printf 'Dry run: no files will be changed.\nCopied (would copy):\n'
else
    printf 'Copied:\n'
fi
for relative in "${copied_paths[@]}"; do
    [[ -z "$relative" ]] || printf '  %s\n' "$relative"
done
[[ "$copied_count" -ne 0 ]] || printf '  (none)\n'
printf 'Skipped (already present):\n'
for relative in "${skipped_paths[@]}"; do
    [[ -z "$relative" ]] || printf '  %s\n' "$relative"
done
[[ "$skipped_count" -ne 0 ]] || printf '  (none)\n'
printf 'Symlink: %s CLAUDE.md -> AGENTS.md\n' "$symlink_action"
printf 'Default branch: %s\n  (%s)\n\n' "$default_branch" "$default_branch_source"

printf '%s\n' \
    'Next steps' \
    '1. Review the copied files, then run: git add -A && git commit -m "chore: add project kit"' \
    '2. In Claude Code, run /rpa-init to warm up on the repository, run tests, and write the report.' \
    '3. Run /rpa-gen-rules to generate paired .claude/rules/*.md and .cursor/rules/*.mdc (the Codex hook attaches them), then run make test-agent-rules.' \
    "4. Fill the {{PROJECT_*}}, {{REPO}}, {{OWNER}} and other project tokens; list them with: grep -rn '{{' --exclude-dir=.git ."
printf '5. Convert the backlog into milestones and issues using %s.\n' "$host_issue_template"
protect_branch=''
[[ "$default_branch" == main ]] || protect_branch=$(printf ' --branch %q' "$default_branch")
printf '6. Once CI has run, run %s/kit/%s/protect.sh%s.\n' "$KIT_DIR" "$host" "$protect_branch"
printf '%s\n' '7. Run make hooks and make docs-check.'
printf '\nThe process documents live in the kit\047s playbook/: %s/playbook/\n' "$KIT_DIR"
printf '\nSummary: copied %s, skipped %s\n' "$copied_count" "$skipped_count"
