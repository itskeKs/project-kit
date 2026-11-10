#!/usr/bin/env bash
# Install the global layer of the kit into ~/.claude: the four agents and the orchestration policy.
# Bash 3.2 compatible (macOS default).
set -euo pipefail

usage() {
    cat <<'EOF_USAGE'
Usage: install-global.sh [--dry-run] [--help]

Copies kit/global/agents/*.md to ~/.claude/agents/ and appends kit/global/orchestration-policy.md to
~/.claude/CLAUDE.md inside a marker block. Existing agent files are never overwritten, and the
policy is added only once; both cases are reported and skipped. HOME is honored.

  --dry-run  print what would be done and change nothing
  --help     show this text
EOF_USAGE
}

bad_args() {
    printf '%s\n' "$1" >&2
    usage >&2
    exit 2
}

die() {
    printf '%s\n' "$1" >&2
    exit 1
}

dry_run=false
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)
            [[ "$dry_run" == false ]] || bad_args '--dry-run may only be given once.'
            dry_run=true
            shift
            ;;
        -h | --help)
            usage
            exit 0
            ;;
        *) bad_args "Unknown argument: $1" ;;
    esac
done

KIT_DIR=$(cd "$(dirname "$0")" && pwd)
src_dir="$KIT_DIR/kit/global"
home=${HOME:-}
[[ -n "$home" ]] || die 'HOME is not set.'

marker_begin='<!-- project-kit:begin -->'
marker_end='<!-- project-kit:end -->'

claude_dir="$home/.claude"
agents_dir="$claude_dir/agents"
policy_target="$claude_dir/CLAUDE.md"
policy_source="$src_dir/orchestration-policy.md"

[[ -f "$policy_source" ]] || die "Missing $policy_source; run this script from a complete kit."

if [[ "$dry_run" == true ]]; then
    v_create='would create'
    v_copy='would copy'
    v_append='would append'
    v_skip='would skip'
else
    v_create='created'
    v_copy='copied'
    v_append='appended'
    v_skip='skipped'
fi

copied=0
skipped=0

make_dir() {
    if [[ ! -d "$1" ]]; then
        printf '%s directory %s\n' "$v_create" "$1"
        [[ "$dry_run" == true ]] || mkdir -p "$1"
    fi
}

install_agent() {
    local source=$1 dest
    dest="$agents_dir/$(basename "$source")"
    if [[ -e "$dest" || -L "$dest" ]]; then
        if cmp -s "$source" "$dest"; then
            printf '%s %s: already installed, identical to the kit version\n' "$v_skip" "$dest"
        else
            printf '%s %s: exists and differs from the kit version, kept as it is\n' "$v_skip" "$dest"
        fi
        skipped=$((skipped + 1))
        return 0
    fi
    printf '%s %s\n' "$v_copy" "$dest"
    [[ "$dry_run" == true ]] || cp "$source" "$dest"
    copied=$((copied + 1))
}

append_policy() {
    local separator
    if [[ -f "$policy_target" ]] && grep -Fq "$marker_begin" "$policy_target"; then
        printf '%s %s: the policy block is already there\n' "$v_skip" "$policy_target"
        grep -Fq "$marker_end" "$policy_target" || \
            printf 'warning: %s has the begin marker but no end marker; check it by hand\n' "$policy_target" >&2
        skipped=$((skipped + 1))
        return 0
    fi
    printf '%s the orchestration policy to %s\n' "$v_append" "$policy_target"
    if [[ "$dry_run" == false ]]; then
        # Terminate the last line of an existing file, then separate the block with a blank line.
        separator=''
        if [[ -s "$policy_target" ]]; then
            separator=$'\n'
            [[ -z $(tail -c 1 "$policy_target") ]] || separator=$'\n\n'
        fi
        {
            printf '%s' "$separator"
            printf '%s\n' "$marker_begin"
            cat "$policy_source"
            printf '%s\n' "$marker_end"
        } >> "$policy_target"
    fi
    copied=$((copied + 1))
}

make_dir "$claude_dir"
make_dir "$agents_dir"

found_agent=false
for agent in "$src_dir"/agents/*.md; do
    [[ -f "$agent" ]] || continue
    found_agent=true
    install_agent "$agent"
done
[[ "$found_agent" == true ]] || die "No agent files in $src_dir/agents; run this script from a complete kit."

append_policy

if [[ "$dry_run" == true ]]; then
    printf 'dry run: %d item(s) to install, %d to skip, nothing changed\n' "$copied" "$skipped"
else
    printf 'done: %d item(s) installed, %d skipped\n' "$copied" "$skipped"
    [[ "$copied" -eq 0 ]] || printf 'New Claude Code sessions pick up the agents and the policy.\n'
fi
