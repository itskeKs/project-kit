#!/usr/bin/env bash
set -euo pipefail

KIT_DIR=$(cd "$(dirname "$0")/.." && pwd)
TEST_ROOT=$(mktemp -d)
trap 'rm -rf "$TEST_ROOT"' EXIT

AGENTS='scout builder verifier architect'
MARK_BEGIN='<!-- project-kit:begin -->'
MARK_END='<!-- project-kit:end -->'

fail() {
    printf 'test_install_global: FAIL: %s\n' "$*" >&2
    exit 1
}

# grep -q exits at the first match and can leave printf with a broken pipe, which pipefail turns
# into a random failure; let grep read everything and discard its output instead.
output_grep() {
    printf '%s\n' "$output" | grep "$@" > /dev/null
}

# /bin/bash is 3.2 on macOS: the oldest shell the script must support.
INSTALL_BASH=bash
[[ -x /bin/bash ]] && INSTALL_BASH=/bin/bash

# Run the installer against a home directory of its own; never against the real HOME.
install() {
    local home=$1
    shift
    HOME="$home" "$INSTALL_BASH" "$KIT_DIR/install-global.sh" "$@" 2>&1
}

# Run the installer and keep its output in $output; a failing run fails the test with that output.
install_ok() {
    local status=0
    output=$(install "$@") || status=$?
    [[ $status -eq 0 ]] || fail "the installer exited $status: $output"
}

new_home() {
    mkdir -p "$TEST_ROOT/$1"
    printf '%s\n' "$TEST_ROOT/$1"
}

# Every path and the checksum of every file below a directory, in one stable listing.
snapshot() {
    local dir=$1 path
    (
        cd "$dir"
        find . -print | LC_ALL=C sort | while IFS= read -r path; do
            if [[ -f "$path" ]]; then
                printf '%s %s\n' "$path" "$(cksum < "$path")"
            else
                printf '%s\n' "$path"
            fi
        done
    )
}

count_lines() {
    local count
    count=$(grep -Fxc "$1" "$2" || true)
    printf '%s\n' "$count"
}

# The shipped files are well-formed and carry nothing personal.
for agent in $AGENTS; do
    file="$KIT_DIR/kit/global/agents/$agent.md"
    [[ -f "$file" ]] || fail "missing kit/global/agents/$agent.md"
    [[ $(sed -n 1p "$file") == '---' ]] || fail "$agent.md does not start with frontmatter"
    grep -Fxq "name: $agent" "$file" || fail "$agent.md: name does not match the file"
    grep -q '^description: .' "$file" || fail "$agent.md: no description"
    grep -q '^model: .' "$file" || fail "$agent.md: no model"
done
[[ -f "$KIT_DIR/kit/global/orchestration-policy.md" ]] || fail 'missing kit/global/orchestration-policy.md'
[[ -f "$KIT_DIR/kit/global/README.md" ]] || fail 'missing kit/global/README.md'
if grep -rniE 'fable|usage-limit|mandatory cleanup' "$KIT_DIR/kit/global" > /dev/null; then
    fail 'kit/global names a specific model or carries personal rules'
fi
printf 'test_install_global: shipped files OK\n'

# Fresh install: four agents and one marker block.
home=$(new_home fresh)
install_ok "$home"
for agent in $AGENTS; do
    [[ -f "$home/.claude/agents/$agent.md" ]] || fail "fresh install: missing $agent.md"
    cmp -s "$KIT_DIR/kit/global/agents/$agent.md" "$home/.claude/agents/$agent.md" || \
        fail "fresh install: $agent.md differs from the kit version"
done
assert_one_block() {
    [[ $(count_lines "$MARK_BEGIN" "$1") == 1 ]] || fail "$2: expected exactly one begin marker"
    [[ $(count_lines "$MARK_END" "$1") == 1 ]] || fail "$2: expected exactly one end marker"
}
[[ -f "$home/.claude/CLAUDE.md" ]] || fail 'fresh install: missing CLAUDE.md'
assert_one_block "$home/.claude/CLAUDE.md" 'fresh install'
[[ $(sed -n 1p "$home/.claude/CLAUDE.md") == "$MARK_BEGIN" ]] || fail 'fresh install: block does not start the file'
[[ $(tail -n 1 "$home/.claude/CLAUDE.md") == "$MARK_END" ]] || fail 'fresh install: block does not end the file'
# Everything between the markers is the policy file, unchanged.
sed '1d;$d' "$home/.claude/CLAUDE.md" | cmp -s - "$KIT_DIR/kit/global/orchestration-policy.md" || \
    fail 'fresh install: the block differs from kit/global/orchestration-policy.md'
output_grep -F 'copied' || fail 'fresh install: the output does not report copied files'
printf 'test_install_global: fresh install OK\n'

# A second run changes nothing and says so.
before=$(snapshot "$home")
install_ok "$home"
after=$(snapshot "$home")
[[ "$before" == "$after" ]] || fail 'second run changed files'
assert_one_block "$home/.claude/CLAUDE.md" 'second run'
output_grep -F 'skipped' || fail 'second run: the output does not report skipped files'
if output_grep -F 'copied'; then fail 'second run: the output reports copied files'; fi
printf 'test_install_global: idempotence OK\n'

# An existing agent file with other content is kept and reported; the others are still installed.
home=$(new_home own-agent)
mkdir -p "$home/.claude/agents"
printf 'my own builder\n' > "$home/.claude/agents/builder.md"
install_ok "$home"
[[ $(cat "$home/.claude/agents/builder.md") == 'my own builder' ]] || fail 'an existing agent file was overwritten'
output_grep -F "$home/.claude/agents/builder.md" || fail 'the kept agent file is not reported'
output_grep -F 'differs' || fail 'the kept agent file is not reported as different'
for agent in scout verifier architect; do
    [[ -f "$home/.claude/agents/$agent.md" ]] || fail "own agent: missing $agent.md"
done
before=$(snapshot "$home")
install_ok "$home"
[[ "$before" == "$(snapshot "$home")" ]] || fail 'own agent: second run changed files'
printf 'test_install_global: existing agent file is kept OK\n'

# An existing agent file that is a symlink is not followed or replaced.
home=$(new_home symlink-agent)
mkdir -p "$home/.claude/agents"
printf 'elsewhere\n' > "$TEST_ROOT/elsewhere.md"
ln -s "$TEST_ROOT/elsewhere.md" "$home/.claude/agents/scout.md"
install_ok "$home"
[[ -L "$home/.claude/agents/scout.md" ]] || fail 'a symlinked agent file was replaced'
[[ $(cat "$TEST_ROOT/elsewhere.md") == 'elsewhere' ]] || fail 'a symlinked agent file was written through'
printf 'test_install_global: symlinked agent file OK\n'

# An existing CLAUDE.md keeps its content, with or without a final newline; a block that is there is not doubled.
home=$(new_home own-claude)
mkdir -p "$home/.claude"
printf '# My rules\n\nBe brief.' > "$home/.claude/CLAUDE.md"
install_ok "$home"
head -c 22 "$home/.claude/CLAUDE.md" | cmp -s - <(printf '# My rules\n\nBe brief.\n') || \
    fail 'existing CLAUDE.md content was changed'
assert_one_block "$home/.claude/CLAUDE.md" 'existing CLAUDE.md'
[[ $(tail -n 1 "$home/.claude/CLAUDE.md") == "$MARK_END" ]] || fail 'existing CLAUDE.md: block does not end the file'
before=$(snapshot "$home")
install_ok "$home"
[[ "$before" == "$(snapshot "$home")" ]] || fail 'existing CLAUDE.md: second run changed files'
home=$(new_home own-claude-nl)
mkdir -p "$home/.claude"
printf '# My rules\n' > "$home/.claude/CLAUDE.md"
install_ok "$home"
head -c 11 "$home/.claude/CLAUDE.md" | cmp -s - <(printf '# My rules\n') || \
    fail 'existing CLAUDE.md with final newline was changed'
assert_one_block "$home/.claude/CLAUDE.md" 'existing CLAUDE.md with final newline'
home=$(new_home own-block)
mkdir -p "$home/.claude"
printf '%s\nold policy\n%s\n' "$MARK_BEGIN" "$MARK_END" > "$home/.claude/CLAUDE.md"
install_ok "$home"
[[ "$(cat "$home/.claude/CLAUDE.md")" == "$(printf '%s\nold policy\n%s' "$MARK_BEGIN" "$MARK_END")" ]] || \
    fail 'an existing marker block was changed'
output_grep -F 'already there' || fail 'an existing marker block is not reported'
printf 'test_install_global: existing CLAUDE.md OK\n'

# --dry-run on an empty home creates nothing, not even the directories.
home=$(new_home dry)
before=$(snapshot "$home")
install_ok "$home" --dry-run
[[ "$before" == "$(snapshot "$home")" ]] || fail '--dry-run changed files'
[[ ! -e "$home/.claude" ]] || fail '--dry-run created ~/.claude'
output_grep -F 'would copy' || fail '--dry-run does not say what it would copy'
output_grep -F 'would append' || fail '--dry-run does not say what it would append'
# --dry-run on a populated home changes nothing either, and reports what it would skip.
home=$(new_home dry-own)
mkdir -p "$home/.claude/agents"
printf 'my own builder\n' > "$home/.claude/agents/builder.md"
before=$(snapshot "$home")
install_ok "$home" --dry-run
[[ "$before" == "$(snapshot "$home")" ]] || fail '--dry-run on a populated home changed files'
output_grep -F 'would skip' || fail '--dry-run does not say what it would skip'
printf 'test_install_global: dry run OK\n'

# Arguments and environment.
set +e
output=$(install "$TEST_ROOT/bad" --bogus)
status=$?
set -e
[[ $status -eq 2 ]] || fail 'an unknown argument must exit 2'
output_grep -F 'Unknown argument' || fail 'an unknown argument is not named'
[[ ! -e "$TEST_ROOT/bad" ]] || fail 'an unknown argument created files'
install_ok "$TEST_ROOT/bad" --help
output_grep -F 'Usage:' || fail '--help prints no usage'
[[ ! -e "$TEST_ROOT/bad" ]] || fail '--help created files'
set +e
output=$(env -u HOME "$INSTALL_BASH" "$KIT_DIR/install-global.sh" 2>&1)
status=$?
set -e
[[ $status -ne 0 ]] || fail 'a missing HOME must fail'
output_grep -F 'HOME is not set' || fail 'a missing HOME is not named'
printf 'test_install_global: bad arguments OK\n'
printf 'test_install_global: PASS\n'
