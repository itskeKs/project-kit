#!/usr/bin/env bash
set -euo pipefail

KIT_DIR=$(cd "$(dirname "$0")/.." && pwd)
TEST_ROOT=$(mktemp -d)
trap 'rm -rf "$TEST_ROOT"' EXIT

fail() {
    printf 'test_bootstrap: FAIL: %s\n' "$*" >&2
    exit 1
}

assert_file() {
    [[ -f "$1" ]] || fail "missing required file: $1"
}

# grep -q exits at the first match and can leave printf with a broken pipe, which pipefail turns
# into a random failure; let grep read everything and discard its output instead.
output_grep() {
    printf '%s\n' "$output" | grep "$@" > /dev/null
}

new_target() {
    mkdir -p "$1"
    git -C "$1" init -q -b main
}

# /bin/bash is 3.2 on macOS: the oldest shell the script must support.
BOOTSTRAP_BASH=bash
[[ -x /bin/bash ]] && BOOTSTRAP_BASH=/bin/bash

bootstrap() {
    "$BOOTSTRAP_BASH" "$KIT_DIR/bootstrap.sh" "$@"
}

assert_cli_substitution() {
    local host=$1 target=$2 expected=$3 source relative
    # Prefer the contributor guide when it contains the CLI token.
    for source in "$KIT_DIR/kit/common/CONTRIBUTING.md" \
        "$KIT_DIR/kit/$host/repo/CONTRIBUTING.md"; do
        if [[ -f "$source" ]] && grep -Iq . "$source" && \
            grep -Fq '{{HOST_CLI}}' "$source"; then
            grep -Fq "$expected" "$target/CONTRIBUTING.md" || \
                fail "$host: CLI token was not replaced in CONTRIBUTING.md"
            return
        fi
    done
    for source in "$KIT_DIR/kit/common" "$KIT_DIR/kit/$host/repo"; do
        while IFS= read -r -d '' relative; do
            if grep -Iq . "$source/$relative" && \
                grep -Fq '{{HOST_CLI}}' "$source/$relative"; then
                grep -Fq "$expected" "$target/$relative" || \
                    fail "$host: CLI token was not replaced in $relative"
                return
            fi
        done < <(cd "$source" && find . -type f -print0)
    done
    printf 'test_bootstrap: WARN: %s kit has no HOST_CLI token yet\n' "$host"
}

# The default branch must reach every kit file that carries the token, and nothing may keep it.
assert_default_branch() {
    local host=$1 target=$2 branch=$3 source relative remaining status
    if remaining=$(grep -rIlF --exclude-dir=.git '{{DEFAULT_BRANCH}}' "$target"); then
        fail "$host: unreplaced DEFAULT_BRANCH token in: $remaining"
    else
        status=$?
        [[ "$status" -eq 1 ]] || fail "$host: DEFAULT_BRANCH-token scan failed ($status)"
    fi
    for source in "$KIT_DIR/kit/common" "$KIT_DIR/kit/$host/repo"; do
        while IFS= read -r -d '' relative; do
            if grep -IqF '{{DEFAULT_BRANCH}}' "$source/$relative"; then
                grep -Fq -- "$branch" "$target/$relative" || \
                    fail "$host: default branch '$branch' missing in $relative"
            fi
        done < <(cd "$source" && find . -type f -print0)
    done
    if [[ "$host" == github ]]; then
        grep -Fq "branches: [$branch]" "$target/.github/workflows/tests-on-pr.yaml" || \
            fail "github: tests-on-pr.yaml does not run on pushes to $branch"
        grep -Fq "origin/$branch" "$target/.github/workflows/release-image.yaml" || \
            fail "github: release-image.yaml does not require origin/$branch"
    fi
}

for host in github gitlab; do
    target="$TEST_ROOT/$host"
    new_target "$target"
    expect_repo=false
    if grep -rIqF '{{REPO}}' "$KIT_DIR/kit/common" "$KIT_DIR/kit/$host/repo"; then
        expect_repo=true
    fi
    output=$(bootstrap "$target" --host "$host")

    for required in AGENTS.md .codex/hooks.json scripts/check_docs.py Makefile; do
        assert_file "$target/$required"
    done
    [[ -L "$target/CLAUDE.md" ]] || fail "$host: CLAUDE.md is not a symlink"
    [[ $(readlink "$target/CLAUDE.md") == AGENTS.md ]] || \
        fail "$host: CLAUDE.md must link to exactly AGENTS.md"

    if [[ "$host" == github ]]; then
        assert_file "$target/.github/PULL_REQUEST_TEMPLATE.md"
        cli=gh
        request='pull request'
        other_request='merge request'
    else
        assert_file "$target/.gitlab/merge_request_templates/Default.md"
        assert_file "$target/.gitlab-ci.yml"
        cli=glab
        request='merge request'
        other_request='pull request'
    fi

    if remaining=$(grep -rIl --exclude-dir=.git '{{HOST_' "$target"); then
        fail "$host: unreplaced HOST tokens in: $remaining"
    else
        status=$?
        [[ "$status" -eq 1 ]] || fail "$host: HOST-token scan failed ($status)"
    fi
    if [[ "$expect_repo" == true ]]; then
        grep -rIqF --exclude-dir=.git '{{REPO}}' "$target" || \
            fail "$host: PROJECT token {{REPO}} did not survive"
    fi
    if [[ -f "$target/CONTRIBUTING.md" ]]; then
        grep -Fq "$request" "$target/CONTRIBUTING.md" || \
            fail "$host: CONTRIBUTING.md is missing '$request'"
        if grep -Fq "$other_request" "$target/CONTRIBUTING.md"; then
            fail "$host: CONTRIBUTING.md contains '$other_request'"
        fi
    fi
    assert_cli_substitution "$host" "$target" "$cli"
    # The target was created with init -b main, so main is detected and substituted.
    assert_default_branch "$host" "$target" main
    output_grep -Fx 'Default branch: main' || \
        fail "$host: output does not report 'Default branch: main'"

    output=$(bootstrap "$target" --host "$host")
    output_grep -E '^Summary: copied 0, skipped [0-9]+$' || \
        fail "$host: second bootstrap did not report copied 0"
    printf 'test_bootstrap: %s files, tokens, symlink and idempotence OK\n' "$host"
done

target="$TEST_ROOT/non-overwrite"
new_target "$target"
printf '%s\n' 'keep me' > "$target/SECURITY.md"
output=$(bootstrap "$target" --host github)
[[ $(cat "$target/SECURITY.md") == 'keep me' ]] || fail 'SECURITY.md was overwritten'
printf '%s\n' "$output" | awk '
    /^Skipped \(already present\):$/ { skipped = 1; next }
    skipped && /^  SECURITY\.md$/ { found = 1 }
    skipped && /^[^ ]/ { skipped = 0 }
    END { exit !found }
' || fail 'SECURITY.md was not listed under Skipped (already present)'
printf 'test_bootstrap: non-overwrite OK\n'

target="$TEST_ROOT/keep-claude"
new_target "$target"
printf '%s\n' 'my own notes' > "$target/CLAUDE.md"
mkdir -p "$target/docs/adr/README.md"           # a directory where the kit has a file
ln -s /nonexistent "$target/features"           # a symlinked parent must not be written through
output=$(bootstrap "$target" --host gitlab)
[[ ! -L "$target/CLAUDE.md" && $(cat "$target/CLAUDE.md") == 'my own notes' ]] || fail 'an existing CLAUDE.md was replaced'
output_grep -F '  CLAUDE.md' || fail 'existing CLAUDE.md was not reported as skipped'
[[ -d "$target/docs/adr/README.md" ]] || fail 'a directory in the way of a kit file was replaced'
[[ ! -e /nonexistent/README.md && -L "$target/features" ]] || fail 'a symlinked parent was written through'
output_grep -F 'features/README.md (a parent is a file or a symlink)' || fail 'symlinked parent not reported'
printf 'test_bootstrap: existing CLAUDE.md, directory and symlinked parent OK\n'

# A file in the way of a kit directory must not abort the run half-way; once it is removed,
# the second run copies the rest with its tokens substituted.
target="$TEST_ROOT/partial"
new_target "$target"
printf 'x\n' > "$target/.github"
output=$(bootstrap "$target" --host github) || fail 'a file in the way of .github aborted the run'
output_grep -F '.github/PULL_REQUEST_TEMPLATE.md (a parent is a file or a symlink)' || fail 'blocked .github files not reported'
[[ -L "$target/CLAUDE.md" ]] || fail 'partial run did not create the symlink'
rm "$target/.github"
bootstrap "$target" --host github > /dev/null
assert_file "$target/.github/PULL_REQUEST_TEMPLATE.md"
if remaining=$(grep -rIl --exclude-dir=.git '{{HOST_' "$target"); then
    fail "partial run left HOST tokens in: $remaining"
fi
printf 'test_bootstrap: partial run recovery OK\n'

target="$TEST_ROOT/dry-run"
new_target "$target"
output=$(bootstrap "$target" --host github --dry-run --default-branch trunk)
unexpected=$(find "$target" -mindepth 1 -name .git -prune -o -mindepth 1 -print)
[[ -z "$unexpected" ]] || fail "dry run changed target: $unexpected"
output_grep -Fx 'Default branch: trunk' || fail "dry run does not report 'Default branch: trunk'"
printf 'test_bootstrap: dry run OK\n'

# The default branch is detected from the target, with --default-branch as the override.
for host in github gitlab; do
    target="$TEST_ROOT/develop-$host"
    mkdir -p "$target"
    git -C "$target" init -q -b develop
    output=$(bootstrap "$target" --host "$host")
    output_grep -Fx 'Default branch: develop' || \
        fail "$host: a develop repository was not detected"
    assert_default_branch "$host" "$target" develop
    grep -Fq develop "$target/AGENTS.md" || fail "$host: AGENTS.md does not name develop"
    if [[ "$host" == github ]] && grep -Fq 'branches: [main]' "$target/.github/workflows/tests-on-pr.yaml"; then
        fail 'github: tests-on-pr.yaml still names main in a develop repository'
    fi
done
printf 'test_bootstrap: default branch detection OK\n'

target="$TEST_ROOT/override"
new_target "$target"
output=$(bootstrap "$target" --host github --default-branch trunk)
output_grep -Fx 'Default branch: trunk' || fail '--default-branch trunk was not reported'
assert_default_branch github "$target" trunk
if grep -rIqF --exclude-dir=.git 'branches: [main]' "$target"; then
    fail '--default-branch trunk left branches: [main] behind'
fi
printf 'test_bootstrap: --default-branch override OK\n'

# origin/HEAD wins over the checked-out branch: a kit added from a feature branch must still
# name the repository's default branch.
target="$TEST_ROOT/feature-branch"
mkdir -p "$target"
git -C "$target" init -q -b master
git -C "$target" symbolic-ref refs/remotes/origin/HEAD refs/remotes/origin/master
git -C "$target" checkout -q -b chore/add-kit
output=$(bootstrap "$target" --host github)
output_grep -Fx 'Default branch: master' || fail 'origin/HEAD was not preferred over the feature branch'
assert_default_branch github "$target" master
if grep -rIqF --exclude-dir=.git 'chore/add-kit' "$target"; then
    fail 'the feature branch leaked into the copied files'
fi
printf 'test_bootstrap: origin/HEAD beats the current branch OK\n'

# Not a git repository, or a detached HEAD: fall back to main.
target="$TEST_ROOT/no-git"
mkdir -p "$target"
output=$(bootstrap "$target" --host github --dry-run)
output_grep -Fx 'Default branch: main' || fail 'a target without git did not fall back to main'
target="$TEST_ROOT/detached"
mkdir -p "$target"
git -C "$target" init -q -b develop
git -C "$target" -c user.name=kit-test -c user.email=kit-test@example.invalid -c commit.gpgsign=false \
    commit -q --allow-empty -m 'test commit'
git -C "$target" checkout -q --detach
output=$(bootstrap "$target" --host github --dry-run)
output_grep -Fx 'Default branch: main' || fail 'a detached HEAD did not fall back to main'
printf 'test_bootstrap: default branch fallback OK\n'

# Bytecode in the kit (python3 run inside it) must never reach a target.
cp -R "$KIT_DIR" "$TEST_ROOT/kit-copy"
mkdir -p "$TEST_ROOT/kit-copy/kit/common/scripts/__pycache__"
printf 'x' > "$TEST_ROOT/kit-copy/kit/common/scripts/__pycache__/probe.cpython-312.pyc"
printf 'x' > "$TEST_ROOT/kit-copy/kit/github/repo/.github/stray.pyc"
assert_file "$TEST_ROOT/kit-copy/kit/common/scripts/__pycache__/probe.cpython-312.pyc"
target="$TEST_ROOT/bytecode"
new_target "$target"
output=$("$BOOTSTRAP_BASH" "$TEST_ROOT/kit-copy/bootstrap.sh" "$target" --host github)
assert_file "$target/scripts/check_docs.py"
bytecode=$(find "$target" -name .git -prune -o \( -name __pycache__ -o -name '*.pyc' \) -print)
[[ -z "$bytecode" ]] || fail "bytecode was copied: $bytecode"
if output_grep -E '__pycache__|\.pyc'; then
    fail 'the Copied list mentions bytecode'
fi
printf 'test_bootstrap: bytecode is not copied OK\n'

# Links that leave the repository fail even when the target exists (umbrella checkouts).
links="$TEST_ROOT/links"
mkdir -p "$links/repo/docs"
git -C "$links/repo" init -q -b main
printf '# Outside\n' > "$links/outside.md"
printf '# Readme\n' > "$links/repo/README.md"
printf '[readme](../README.md)\n' > "$links/repo/docs/ok.md"
git -C "$links/repo" add -A
python3 "$KIT_DIR/kit/common/scripts/check_docs.py" --root "$links/repo" > "$links/check.log" 2>&1 || \
    fail "the link checker rejected a repository with only inside links: $(cat "$links/check.log")"
printf '[o](../../outside.md)\n' > "$links/repo/docs/x.md"
git -C "$links/repo" add -A
if python3 "$KIT_DIR/kit/common/scripts/check_docs.py" --root "$links/repo" > "$links/check.log" 2>&1; then
    fail 'a link that leaves the repository passed the link checker'
fi
grep -Fq 'leaves the repository' "$links/check.log" || \
    fail "the link checker did not say 'leaves the repository': $(cat "$links/check.log")"
rm "$links/repo/docs/x.md"
git -C "$links/repo" add -A
python3 "$KIT_DIR/kit/common/scripts/check_docs.py" --root "$links/repo" > "$links/check.log" 2>&1 || \
    fail "the link checker still fails after the outside link was removed: $(cat "$links/check.log")"
printf 'test_bootstrap: links that leave the repository OK\n'

for host in github gitlab; do
    target="$TEST_ROOT/$host"
    # Only the disposable bootstrapped repository is staged for the link checker.
    git -C "$target" add -A
    (cd "$target" && python3 scripts/check_docs.py) || fail "$host: bootstrapped docs check failed"
    (cd "$target" && python3 -B scripts/test_agent_rules.py >/dev/null 2>&1) || fail "$host: agent-rule tests failed"
done

assert_bad_args() {
    local status
    if bootstrap "$@" > "$TEST_ROOT/bad-args.log" 2>&1; then
        fail "invalid arguments succeeded: $*"
    else
        status=$?
    fi
    [[ "$status" -eq 2 ]] || fail "invalid arguments returned $status, expected 2: $*"
    grep -Fq 'Usage:' "$TEST_ROOT/bad-args.log" || fail 'invalid arguments omitted usage'
}

assert_bad_args
assert_bad_args "$TEST_ROOT/github" --host unknown
assert_bad_args "$TEST_ROOT/does-not-exist" --host github
grep -Fq 'init -b main' "$TEST_ROOT/bad-args.log" || fail 'the create-it-first hint does not suggest main'
assert_bad_args "$TEST_ROOT/does-not-exist" --host github --default-branch trunk
grep -Fq 'init -b trunk' "$TEST_ROOT/bad-args.log" || fail 'the create-it-first hint ignores --default-branch'
assert_bad_args "$TEST_ROOT/github" --host github --default-branch 'bad name'
assert_bad_args "$TEST_ROOT/github" --host github --default-branch
assert_bad_args "$TEST_ROOT/github" --host github --default-branch --dry-run
assert_bad_args "$TEST_ROOT/github" --host github --default-branch '@{-1}'
assert_bad_args "$TEST_ROOT/github" --host github --default-branch a --default-branch b
assert_bad_args "$TEST_ROOT/github" --host github --default-branch ''
assert_bad_args "$TEST_ROOT/github" --host github --default-branch 'a,b'
# shellcheck disable=SC2016  # the literal dollar sign is the point of this case
assert_bad_args "$TEST_ROOT/github" --host github --default-branch 'x$y'
assert_bad_args "$TEST_ROOT/github" --host github --default-branch "it's"
printf 'test_bootstrap: bad arguments OK\n'
printf 'test_bootstrap: PASS\n'
