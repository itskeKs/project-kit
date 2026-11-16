#!/usr/bin/env bash
# Tests for doctor.sh. Fully offline: every run gets a home directory of its own and fake gh and
# glab programs first on PATH; the real ~/.claude, gh and glab are never touched.
# The messages quote commands in backticks and name $kit literally; none of it is meant to expand.
# shellcheck disable=SC2016
set -euo pipefail

KIT_DIR=$(cd "$(dirname "$0")/.." && pwd)
KIT_PHYS=$(cd "$KIT_DIR" && pwd -P)
TEST_ROOT=$(mktemp -d)
trap 'rm -rf "$TEST_ROOT"' EXIT

AGENTS='scout builder verifier architect'
MARK_BEGIN='<!-- project-kit:begin -->'
MARK_END='<!-- project-kit:end -->'
FAKE_TOKEN='ghp_FAKE0TOKEN0FOR0THE0TEST'
INSTALL_HINT='run `./install-global.sh`'

fail() {
    printf 'test_doctor: FAIL: %s\n' "$*" >&2
    if [[ -n "${output:-}" ]]; then
        printf '%s\n' "$output" >&2
    fi
    exit 1
}

# /bin/bash is 3.2 on macOS: the oldest shell the script must support.
DOCTOR_BASH=$(command -v bash)
[[ -x /bin/bash ]] && DOCTOR_BASH=/bin/bash

# grep -q exits at the first match and can leave printf with a broken pipe, which pipefail turns
# into a random failure; let grep read everything and discard its output instead.
has_line() {
    printf '%s\n' "$output" | grep -Fx -- "$1" > /dev/null
}

has_text() {
    printf '%s\n' "$output" | grep -F -- "$1" > /dev/null
}

last_line() {
    printf '%s\n' "$output" | tail -n 1
}

# The lines of one section: from its heading to the next blank line.
section_lines() {
    printf '%s\n' "$output" | awk -v s="$1" '$0 == s { on = 1; next } /^$/ { on = 0 } on'
}

section_count() {
    section_lines "$1" | awk 'END { print NR }'
}

assert_section_all_ok() {
    local bad
    bad=$(section_lines "$1" | grep -v '^ok ' || true)
    [[ -z "$bad" ]] || fail "section $1 has lines that are not ok: $bad"
}

assert_no_missing_in() {
    local bad
    bad=$(section_lines "$1" | grep '^MISSING' || true)
    [[ -z "$bad" ]] || fail "section $1 has MISSING lines: $bad"
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

# Directories that must stay empty: the working directory and the temporary directory of every run.
mkdir -p "$TEST_ROOT/cwd" "$TEST_ROOT/tmp" "$TEST_ROOT/calls"
CALLS="$TEST_ROOT/calls"

# A fake gh or glab: records its arguments, prints a fake token on both streams, exits as told.
make_fake_cli() {
    local name=$1 exit_var=$2
    cat > "$BIN/$name" <<EOF_STUB
#!/bin/sh
printf '%s\n' "\$*" >> "\$FAKE_LOG_DIR/$name.args"
echo "token $FAKE_TOKEN on stdout"
echo "token $FAKE_TOKEN on stderr" >&2
exit "\${$exit_var:-1}"
EOF_STUB
    chmod +x "$BIN/$name"
}

BIN="$TEST_ROOT/bin"
mkdir -p "$BIN"
make_fake_cli gh FAKE_GH_EXIT
make_fake_cli glab FAKE_GLAB_EXIT
# A fake ShellCheck keeps doctor.sh away from the real docker.
printf '#!/bin/sh\nexit 0\n' > "$BIN/shellcheck"
chmod +x "$BIN/shellcheck"
FULL_PATH="$BIN:$PATH"

# A PATH that holds only what doctor.sh itself needs (find, grep) and do-nothing stubs for the tools listed.
REAL_FIND=$(command -v find)
REAL_GREP=$(command -v grep)
make_min_bin() {
    local dir=$1 tool
    shift
    mkdir -p "$dir"
    ln -s "$REAL_FIND" "$dir/find"
    ln -s "$REAL_GREP" "$dir/grep"
    for tool in "$@"; do
        printf '#!/bin/sh\nexit 0\n' > "$dir/$tool"
        chmod +x "$dir/$tool"
    done
}

# run_doctor HOME PATH GH_EXIT GLAB_EXIT [ARG...]
# The result is in $output (stdout and stderr together) and $status. GITLAB_HOST for the run comes
# from $TEST_GITLAB_HOST. Every run is also checked for what it must never do: leak the token of the
# fake CLIs, or leave files in its working directory or temporary directory.
TEST_GITLAB_HOST=''
run_doctor() {
    local home=$1 path=$2 gh_exit=$3 glab_exit=$4
    shift 4
    rm -f "$CALLS/gh.args" "$CALLS/glab.args"
    status=0
    output=$(
        cd "$TEST_ROOT/cwd"
        env HOME="$home" PATH="$path" TMPDIR="$TEST_ROOT/tmp" GITLAB_HOST="$TEST_GITLAB_HOST" \
            FAKE_GH_EXIT="$gh_exit" FAKE_GLAB_EXIT="$glab_exit" FAKE_LOG_DIR="$CALLS" \
            "$DOCTOR_BASH" "$KIT_DIR/doctor.sh" "$@" 2>&1
    ) || status=$?
    if has_text "$FAKE_TOKEN"; then fail 'the token of a fake CLI reached the output'; fi
    [[ -z "$(ls -A "$TEST_ROOT/cwd")" ]] || fail 'a run left files in its working directory'
    [[ -z "$(ls -A "$TEST_ROOT/tmp")" ]] || fail 'a run left files in its temporary directory'
}

# A path as doctor.sh writes it into a command line: quoted only when it has unusual characters.
shell_path() {
    case "$1" in
        *[!A-Za-z0-9_./+@%-]*) printf '"%s"' "$1" ;;
        *) printf '%s' "$1" ;;
    esac
}

new_home() {
    mkdir -p "$TEST_ROOT/$1"
    printf '%s\n' "$TEST_ROOT/$1"
}

# A home with everything the Claude Code and Codex sections look for. The /kit skill is a symlink,
# as it is after the documented `ln -s`.
make_complete_home() {
    local home=$1 agent skill
    mkdir -p "$home/.claude/agents" "$home/.claude/skills" "$home/.agents/skills/kit" \
        "$TEST_ROOT/kit-skill-target"
    printf '%s\npolicy\n%s\n' "$MARK_BEGIN" "$MARK_END" > "$home/.claude/CLAUDE.md"
    for agent in $AGENTS; do
        printf 'agent\n' > "$home/.claude/agents/$agent.md"
    done
    printf 'skill\n' > "$TEST_ROOT/kit-skill-target/SKILL.md"
    ln -s "$TEST_ROOT/kit-skill-target" "$home/.claude/skills/kit"
    for skill in rpa-init rpa-gen-rules; do
        mkdir -p "$home/.claude/skills/$skill"
        printf 'skill\n' > "$home/.claude/skills/$skill/SKILL.md"
    done
    printf 'skill\n' > "$home/.agents/skills/kit/SKILL.md"
}

# The fake CLIs themselves behave as the tests assume, including the token they print.
leak=$(FAKE_GH_EXIT=0 FAKE_LOG_DIR="$CALLS" "$BIN/gh" auth status 2>&1)
printf '%s\n' "$leak" | grep -F -- "$FAKE_TOKEN" > /dev/null || fail 'the fake gh does not print its token'
rm -f "$CALLS/gh.args"

# Complete machine: both host CLIs logged in, every Claude Code and Codex piece in place.
home=$(new_home complete)
make_complete_home "$home"
run_doctor "$home" "$FULL_PATH" 0 0
[[ $status -eq 0 ]] || fail "complete machine: exit $status"
for heading in 'Required' 'Claude Code' 'Codex' 'Optional'; do
    has_line "$heading" || fail "complete machine: no section heading $heading"
done
has_line 'ok       git' || fail 'complete machine: git is not ok'
has_line 'ok       bash' || fail 'complete machine: bash is not ok'
has_line 'ok       python3' || fail 'complete machine: python3 is not ok'
has_line 'ok       gh, logged in' || fail 'complete machine: gh is not ok'
has_line 'ok       glab, logged in' || fail 'complete machine: glab is not ok'
has_line 'ok       orchestration policy in ~/.claude/CLAUDE.md' || fail 'complete machine: policy is not ok'
for agent in $AGENTS; do
    has_line "ok       agent $agent" || fail "complete machine: agent $agent is not ok"
done
has_line 'ok       skill /kit' || fail 'complete machine: /kit is not ok'
has_line 'ok       skill rpa-init' || fail 'complete machine: rpa-init is not ok'
has_line 'ok       skill rpa-gen-rules' || fail 'complete machine: rpa-gen-rules is not ok'
has_line 'ok       skill $kit' || fail 'complete machine: $kit is not ok'
for heading in 'Required' 'Claude Code' 'Codex'; do
    assert_section_all_ok "$heading"
done
assert_no_missing_in 'Optional'
[[ $(section_count 'Required') -eq 5 ]] || fail 'complete machine: expected 5 Required lines'
[[ $(section_count 'Claude Code') -eq 8 ]] || fail 'complete machine: expected 8 Claude Code lines'
[[ $(section_count 'Codex') -eq 1 ]] || fail 'complete machine: expected 1 Codex line'
[[ "$(last_line)" == 'doctor: ready' ]] || fail 'complete machine: the last line is not "doctor: ready"'
if has_text 'matter only for the agent host'; then fail 'complete machine: the closing sentence is printed'; fi
[[ "$(cat "$CALLS/gh.args")" == 'auth status' ]] || fail 'complete machine: gh was not asked for "auth status"'
[[ "$(cat "$CALLS/glab.args")" == 'auth status' ]] || fail 'complete machine: glab was not asked for "auth status"'
printf 'test_doctor: complete machine OK\n'

# Neither host CLI is logged in: the one required item that fails, and the exit status says so.
run_doctor "$home" "$FULL_PATH" 1 1
[[ $status -eq 1 ]] || fail "no login: exit $status, expected 1"
has_line 'MISSING  host CLI login — run `gh auth login` or `glab auth login` yourself; agents never enter credentials' || \
    fail 'no login: the host CLI login line is missing or has another text'
has_text 'note     gh installed, not logged in — run `gh auth login`' || fail 'no login: gh is not reported'
has_text 'note     glab installed, not logged in — run `glab auth login`' || fail 'no login: glab is not reported'
[[ "$(last_line)" == 'doctor: 1 required item(s) missing' ]] || fail 'no login: the last line does not count 1 missing item'
assert_no_missing_in 'Claude Code'
printf 'test_doctor: no login OK\n'

# Only glab logged in; GITLAB_HOST is handed to it as --hostname and only to it.
run_doctor "$home" "$FULL_PATH" 1 0
[[ $status -eq 0 ]] || fail "only glab: exit $status"
has_line 'ok       glab, logged in' || fail 'only glab: glab is not ok'
has_text 'note     gh installed, not logged in' || fail 'only glab: gh is not noted'
[[ "$(last_line)" == 'doctor: ready' ]] || fail 'only glab: the last line is not "doctor: ready"'
[[ "$(cat "$CALLS/glab.args")" == 'auth status' ]] || fail 'only glab: unexpected glab arguments without GITLAB_HOST'
TEST_GITLAB_HOST=example.invalid
run_doctor "$home" "$FULL_PATH" 1 0
[[ $status -eq 0 ]] || fail "only glab with GITLAB_HOST: exit $status"
[[ "$(cat "$CALLS/glab.args")" == 'auth status --hostname example.invalid' ]] || \
    fail "only glab with GITLAB_HOST: glab got: $(cat "$CALLS/glab.args")"
[[ "$(cat "$CALLS/gh.args")" == 'auth status' ]] || fail 'GITLAB_HOST leaked into the gh arguments'
run_doctor "$home" "$FULL_PATH" 1 1
has_text 'run `glab auth login --hostname example.invalid` yourself' || \
    fail 'GITLAB_HOST is not part of the glab login fix'
TEST_GITLAB_HOST=''
printf 'test_doctor: only glab OK\n'

# Only gh logged in.
run_doctor "$home" "$FULL_PATH" 0 1
[[ $status -eq 0 ]] || fail "only gh: exit $status"
has_line 'ok       gh, logged in' || fail 'only gh: gh is not ok'
has_text 'note     glab installed, not logged in' || fail 'only gh: glab is not noted'
printf 'test_doctor: only gh OK\n'

# An empty home with a logged-in gh: Claude Code and Codex are reported with their fixes and do not fail the run.
home=$(new_home empty)
run_doctor "$home" "$FULL_PATH" 0 1
[[ $status -eq 0 ]] || fail "empty home: exit $status"
has_line "MISSING  orchestration policy in ~/.claude/CLAUDE.md — $INSTALL_HINT" || fail 'empty home: policy line'
for agent in $AGENTS; do
    has_line "MISSING  agent $agent — $INSTALL_HINT" || fail "empty home: agent $agent line"
done
has_text "MISSING  skill /kit — run \`mkdir -p ~/.claude/skills && ln -s $(shell_path "$KIT_PHYS/playbook/skills/kit") ~/.claude/skills/kit\`" || \
    fail 'empty home: /kit line or its ln -s fix'
for skill in rpa-init rpa-gen-rules; do
    has_line "MISSING  skill $skill — install from EvilFreelancer/rpa-skills, see REFERENCE.md \"Requirements\"" || \
        fail "empty home: $skill line"
done
has_text "MISSING  skill \$kit — run \`mkdir -p ~/.agents/skills && ln -s $(shell_path "$KIT_PHYS/playbook/skills/kit-codex") ~/.agents/skills/kit\`" || \
    fail 'empty home: $kit line or its ln -s fix'
[[ $(section_lines 'Claude Code' | grep -c '^MISSING') -eq 8 ]] || fail 'empty home: expected 8 MISSING lines in Claude Code'
[[ $(section_lines 'Codex' | grep -c '^MISSING') -eq 1 ]] || fail 'empty home: expected 1 MISSING line in Codex'
assert_no_missing_in 'Required'
assert_no_missing_in 'Optional'
has_line 'Claude Code and Codex items matter only for the agent host you use.' || fail 'empty home: no closing sentence'
[[ "$(last_line)" == 'doctor: ready' ]] || fail 'empty home: the last line is not "doctor: ready"'
printf 'test_doctor: empty home OK\n'

# A partial home: a CLAUDE.md without the marker, one agent missing, a /kit symlink that points nowhere.
home=$(new_home partial)
make_complete_home "$home"
printf '# My rules\n' > "$home/.claude/CLAUDE.md"
rm "$home/.claude/agents/verifier.md"
rm "$home/.claude/skills/kit"
ln -s "$TEST_ROOT/does-not-exist" "$home/.claude/skills/kit"
run_doctor "$home" "$FULL_PATH" 0 1
[[ $status -eq 0 ]] || fail "partial home: exit $status"
has_line "MISSING  orchestration policy in ~/.claude/CLAUDE.md — $INSTALL_HINT" || fail 'partial home: policy line'
has_line "MISSING  agent verifier — $INSTALL_HINT" || fail 'partial home: verifier line'
has_text 'MISSING  skill /kit — ' || fail 'partial home: a broken /kit symlink is not reported'
[[ $(section_lines 'Claude Code' | grep -c '^MISSING') -eq 3 ]] || fail 'partial home: expected exactly 3 MISSING lines'
printf 'test_doctor: partial home OK\n'

# A policy kept by hand: the kit's policy heading without the marker block counts as present, so
# nobody is told to run the installer and append a second copy.
home=$(new_home handkept)
make_complete_home "$home"
printf '# My rules\n\n# Subagent orchestration policy (global)\n' > "$home/.claude/CLAUDE.md"
run_doctor "$home" "$FULL_PATH" 0 1
[[ $status -eq 0 ]] || fail "hand-kept policy: exit $status"
has_line 'ok       orchestration policy in ~/.claude/CLAUDE.md (kept by hand, no marker block)' || \
    fail 'hand-kept policy: the heading without a marker is not accepted'
head -n 1 "$KIT_DIR/kit/global/orchestration-policy.md" | grep -Fq '# Subagent orchestration policy' || \
    fail 'kit/global/orchestration-policy.md no longer starts with the heading doctor.sh looks for'
printf 'test_doctor: hand-kept policy OK\n'

# The rpa skills: found as a skill directory, or as a directory of that name anywhere in the plugin tree.
home=$(new_home plugins)
make_complete_home "$home"
rm -r "$home/.claude/skills/rpa-init" "$home/.claude/skills/rpa-gen-rules"
mkdir -p "$home/.claude/plugins/cache/rpa-skills/rpa-init/1.0.0/skills/rpa-init"
run_doctor "$home" "$FULL_PATH" 0 1
has_line 'ok       skill rpa-init' || fail 'plugin tree: rpa-init is not found'
has_text 'MISSING  skill rpa-gen-rules — ' || fail 'plugin tree: rpa-gen-rules is reported as found'
# A file of that name does not count, and neither does a tree that is only reached through a symlink.
printf 'x\n' > "$home/.claude/plugins/rpa-gen-rules"
mkdir -p "$TEST_ROOT/unrelated/rpa-gen-rules"
ln -s "$TEST_ROOT/unrelated" "$home/.claude/plugins/link"
run_doctor "$home" "$FULL_PATH" 0 1
has_text 'MISSING  skill rpa-gen-rules — ' || fail 'plugin tree: a file or a followed symlink counted as rpa-gen-rules'
# The plugins directory itself may be a symlink (dotfile setups).
mkdir -p "$TEST_ROOT/plugin-store/market/rpa-gen-rules"
rm -rf "$home/.claude/plugins"
ln -s "$TEST_ROOT/plugin-store" "$home/.claude/plugins"
run_doctor "$home" "$FULL_PATH" 0 1
has_line 'ok       skill rpa-gen-rules' || fail 'plugin tree: a symlinked plugins directory is not searched'
printf 'test_doctor: rpa skills OK\n'

# Tools that are not installed, on a PATH that has nothing but find and grep.
home=$(new_home minimal)
make_complete_home "$home"
make_min_bin "$TEST_ROOT/min-all" git bash python3
run_doctor "$home" "$TEST_ROOT/min-all" 0 0
[[ $status -eq 1 ]] || fail "no host CLI: exit $status, expected 1"
has_line 'MISSING  host CLI login — install `gh` (GitHub) or `glab` (GitLab), then run `gh auth login` or `glab auth login` yourself; agents never enter credentials' || \
    fail 'no host CLI: the host CLI login line is missing or has another text'
if has_text 'installed, not logged in'; then fail 'no host CLI: a CLI is reported as installed'; fi
if has_text 'logged in'; then fail 'no host CLI: a CLI is reported as logged in'; fi
[[ "$(last_line)" == 'doctor: 1 required item(s) missing' ]] || fail 'no host CLI: the last line does not count 1'
has_line 'note     ShellCheck or Docker — optional, for the shell lint in `make test`' || fail 'no tools: ShellCheck or Docker line'
has_line 'note     codex-task — only for the mixed setup where Claude Code delegates to Codex' || fail 'no tools: codex-task line'
assert_no_missing_in 'Optional'
make_min_bin "$TEST_ROOT/min-nogit" bash python3
run_doctor "$home" "$TEST_ROOT/min-nogit" 0 0
[[ $status -eq 1 ]] || fail "no git: exit $status"
has_text 'MISSING  git — ' || fail 'no git: git is not reported'
[[ "$(last_line)" == 'doctor: 2 required item(s) missing' ]] || fail 'no git: the last line does not count 2'
printf 'test_doctor: missing tools OK\n'

# Optional items: ShellCheck, Docker (only when its daemon answers), codex-task.
make_min_bin "$TEST_ROOT/min-shellcheck" git bash python3 shellcheck codex-task
run_doctor "$home" "$TEST_ROOT/min-shellcheck" 0 0
has_line 'ok       ShellCheck' || fail 'optional: ShellCheck is not ok'
has_line 'ok       codex-task' || fail 'optional: codex-task is not ok'
make_min_bin "$TEST_ROOT/min-docker" git bash python3 docker
run_doctor "$home" "$TEST_ROOT/min-docker" 0 0
has_line 'ok       Docker' || fail 'optional: a working docker is not ok'
make_min_bin "$TEST_ROOT/min-docker-down" git bash python3
printf '#!/bin/sh\nexit 1\n' > "$TEST_ROOT/min-docker-down/docker"
chmod +x "$TEST_ROOT/min-docker-down/docker"
run_doctor "$home" "$TEST_ROOT/min-docker-down" 0 0
has_line 'note     ShellCheck or Docker — optional, for the shell lint in `make test`' || fail 'optional: a docker without a daemon counts as ok'
printf 'test_doctor: optional items OK\n'

# Kit location: ok when the kit is where the skills expect it (compared by physical path), else a note.
home=$(new_home location)
make_complete_home "$home"
run_doctor "$home" "$FULL_PATH" 0 0
has_line "note     kit location — the /kit skills expect the kit at ~/Developer/project-kit; this checkout is at $KIT_PHYS" || \
    fail 'kit location: the note for a kit elsewhere is missing or has another text'
mkdir -p "$home/Developer"
ln -s "$KIT_DIR" "$home/Developer/project-kit"
run_doctor "$home" "$FULL_PATH" 0 0
has_line 'ok       kit location' || fail 'kit location: a symlink to the checkout is not ok'
rm "$home/Developer/project-kit"
mkdir "$home/Developer/project-kit"
run_doctor "$home" "$FULL_PATH" 0 0
has_text 'note     kit location — ' || fail 'kit location: another directory at the expected path is ok'
# A copy of doctor.sh in a directory with a space: the fix is still a pasteable command.
mkdir -p "$TEST_ROOT/kit copy"
cp "$KIT_DIR/doctor.sh" "$TEST_ROOT/kit copy/doctor.sh"
home=$(new_home spaces)
copy_phys=$(cd "$TEST_ROOT/kit copy" && pwd -P)
output=$(env HOME="$home" PATH="$FULL_PATH" TMPDIR="$TEST_ROOT/tmp" GITLAB_HOST= FAKE_GH_EXIT=0 FAKE_GLAB_EXIT=1 FAKE_LOG_DIR="$CALLS" \
    "$DOCTOR_BASH" "$TEST_ROOT/kit copy/doctor.sh" 2>&1) || fail 'a copy of doctor.sh in a directory with a space failed'
has_text "ln -s \"$copy_phys/playbook/skills/kit\" ~/.claude/skills/kit" || fail 'a path with a space is not quoted in the fix'
has_text "this checkout is at $copy_phys" || fail 'the location note does not name the copy'
printf 'test_doctor: kit location OK\n'

# Read-only: a run changes nothing in the home it checks, in the kit directory (a copy), or in the fake CLIs' directory.
home=$(new_home readonly)
make_complete_home "$home"
mkdir -p "$home/.claude/plugins/cache/x/rpa-init" "$home/Developer"
ln -s "$KIT_DIR" "$home/Developer/project-kit"
before_home=$(snapshot "$home")
before_copy=$(snapshot "$TEST_ROOT/kit copy")
before_bin=$(snapshot "$BIN")
run_doctor "$home" "$FULL_PATH" 0 0
run_doctor "$home" "$FULL_PATH" 1 1
run_doctor "$home" "$FULL_PATH" 0 0 --help
[[ "$before_home" == "$(snapshot "$home")" ]] || fail 'read-only: a run changed the populated home'
empty_home=$(new_home readonly-empty)
before_empty=$(snapshot "$empty_home")
run_doctor "$empty_home" "$FULL_PATH" 0 0
[[ "$before_empty" == "$(snapshot "$empty_home")" ]] || fail 'read-only: a run changed the empty home'
[[ ! -e "$empty_home/.claude" && ! -e "$empty_home/.agents" ]] || fail 'read-only: a run created ~/.claude or ~/.agents'
[[ "$before_copy" == "$(snapshot "$TEST_ROOT/kit copy")" ]] || fail 'read-only: a run changed the kit directory'
[[ "$before_bin" == "$(snapshot "$BIN")" ]] || fail 'read-only: a run changed the directory of the fake CLIs'
printf 'test_doctor: read-only OK\n'

# The token the fake gh prints never shows, whether the login succeeds or not (run_doctor checks every run).
for codes in '0 0' '0 1' '1 0' '1 1'; do
    # shellcheck disable=SC2086
    run_doctor "$home" "$FULL_PATH" $codes
done
printf 'test_doctor: no token in the output OK\n'

# Arguments and environment.
home=$(new_home args)
before=$(snapshot "$home")
run_doctor "$home" "$FULL_PATH" 0 0 --bogus
[[ $status -eq 2 ]] || fail "an unknown argument must exit 2, got $status"
has_text 'Unknown argument: --bogus' || fail 'an unknown argument is not named'
has_text 'Usage:' || fail 'an unknown argument does not print the usage'
run_doctor "$home" "$FULL_PATH" 0 0 extra
[[ $status -eq 2 ]] || fail "a positional argument must exit 2, got $status"
run_doctor "$home" "$FULL_PATH" 0 0 --help
[[ $status -eq 0 ]] || fail "--help must exit 0, got $status"
has_text 'Usage:' || fail '--help prints no usage'
if has_line 'Required'; then fail '--help ran the checks'; fi
run_doctor "$home" "$FULL_PATH" 0 0 -h
[[ $status -eq 0 ]] || fail "-h must exit 0, got $status"
[[ "$before" == "$(snapshot "$home")" ]] || fail 'arguments changed the home'
set +e
output=$(env -u HOME PATH="$FULL_PATH" FAKE_GH_EXIT=0 FAKE_GLAB_EXIT=0 FAKE_LOG_DIR="$CALLS" "$DOCTOR_BASH" "$KIT_DIR/doctor.sh" 2>&1)
status=$?
set -e
[[ $status -ne 0 ]] || fail 'a missing HOME must fail'
has_text 'HOME is not set' || fail 'a missing HOME is not named'
printf 'test_doctor: bad arguments OK\n'
printf 'test_doctor: PASS\n'
