#!/usr/bin/env bash
# Check that this machine has what the kit needs and print the exact fix for each missing piece.
# Strictly read-only: creates, changes and deletes nothing. Bash 3.2 compatible (macOS default).
# The messages quote commands in backticks and name $kit literally; none of it is meant to expand.
# shellcheck disable=SC2016
set -euo pipefail

# printf instead of a here-document: bash 3.2 writes a here-document to a temporary file.
usage() {
    printf '%s\n' \
        'Usage: doctor.sh [--help]' \
        '' \
        'Checks whether this machine has what the kit needs and prints the fix for each missing piece.' \
        '' \
        '  Required     git, bash, python3 and a logged-in gh or glab; a missing item makes the exit status 1' \
        '  Claude Code  the orchestration policy, the agents and the skills; matters only if Claude Code is your host' \
        '  Codex        the $kit supplement skill; matters only if Codex is your host' \
        '  Optional     ShellCheck or Docker, codex-task and the kit location; never changes the exit status' \
        '' \
        'Strictly read-only. HOME is honored; GITLAB_HOST selects the host for the glab login check.' \
        'The output of gh and glab is never shown, only whether they report a login.' \
        '' \
        '  --help  show this text'
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

while [[ $# -gt 0 ]]; do
    case "$1" in
        -h | --help)
            usage
            exit 0
            ;;
        *) bad_args "Unknown argument: $1" ;;
    esac
done

unset CDPATH

case "$0" in
    */*) script_dir=${0%/*} ;;
    *) script_dir=. ;;
esac
KIT_DIR=$(cd "$script_dir" && pwd -P)
home=${HOME:-}
[[ -n "$home" ]] || die 'HOME is not set.'
gitlab_host=${GITLAB_HOST:-}

marker_begin='<!-- project-kit:begin -->'
# The first words of kit/global/orchestration-policy.md; a copy pasted by hand carries them too.
policy_heading='# Subagent orchestration policy'
claude_dir="$home/.claude"
agents_dir="$claude_dir/agents"
rpa_fix='install from EvilFreelancer/rpa-skills, see REFERENCE.md "Requirements"'

# A path as it has to be written in a command line that someone pastes.
shell_path() {
    case "$1" in
        *[!A-Za-z0-9_./+@%-]*) printf '"%s"' "$1" ;;
        *) printf '%s' "$1" ;;
    esac
}

required_missing=0
host_missing=0
first_section=true

section() {
    if [[ "$first_section" == false ]]; then
        printf '\n'
    fi
    first_section=false
    printf '%s\n' "$1"
}

# report STATUS ITEM [FIX]: one line, the status word padded to 8 columns.
report() {
    if [[ $# -ge 3 ]]; then
        printf '%-8s %s — %s\n' "$1" "$2" "$3"
    else
        printf '%-8s %s\n' "$1" "$2"
    fi
}

# A Required item that is missing fails the run.
required_gone() {
    report MISSING "$1" "$2"
    required_missing=$((required_missing + 1))
}

# A Claude Code or Codex item that is missing is reported but does not fail the run.
host_gone() {
    report MISSING "$1" "$2"
    host_missing=$((host_missing + 1))
}

check_tool() {
    if command -v "$1" > /dev/null 2>&1; then
        report ok "$1"
    else
        required_gone "$1" "$2"
    fi
}

# check_file ITEM FILE FIX: found when FILE exists; symlinks are followed.
check_file() {
    if [[ -f "$2" ]]; then
        report ok "$1"
    else
        host_gone "$1" "$3"
    fi
}

# check_skill NAME: an rpa skill is a skills/NAME/SKILL.md or a plugin that ships a directory NAME.
check_skill() {
    local name=$1 found=''
    if [[ -f "$claude_dir/skills/$name/SKILL.md" ]]; then
        report ok "skill $name"
        return 0
    fi
    # -H follows only the start directory itself; symlinks inside the plugin tree stay unfollowed.
    if [[ -d "$claude_dir/plugins" ]]; then
        found=$(find -H "$claude_dir/plugins" -maxdepth 8 -type d -name "$name" 2> /dev/null || true)
    fi
    if [[ -n "$found" ]]; then
        report ok "skill $name"
    else
        host_gone "skill $name" "$rpa_fix"
    fi
}

physical_dir() {
    (cd "$1" 2> /dev/null && pwd -P) || true
}

glab_logged_in() {
    if [[ -n "$gitlab_host" ]]; then
        glab auth status --hostname "$gitlab_host" < /dev/null > /dev/null 2>&1
    else
        glab auth status < /dev/null > /dev/null 2>&1
    fi
}

section 'Required'
check_tool git 'install git, for example `xcode-select --install` on macOS or your package manager on Linux'
check_tool bash 'install bash 3.2 or newer with your package manager'
check_tool python3 'install Python 3, for example from python.org or your package manager'

# Only the exit codes of gh and glab are used: their status output can contain token details.
host_cli_installed=false
host_cli_logged_in=false
if command -v gh > /dev/null 2>&1; then
    host_cli_installed=true
    if gh auth status < /dev/null > /dev/null 2>&1; then
        host_cli_logged_in=true
        report ok 'gh, logged in'
    else
        report note 'gh installed, not logged in' 'run `gh auth login` yourself; only needed for GitHub projects'
    fi
fi
if command -v glab > /dev/null 2>&1; then
    host_cli_installed=true
    if glab_logged_in; then
        host_cli_logged_in=true
        report ok 'glab, logged in'
    elif [[ -n "$gitlab_host" ]]; then
        report note 'glab installed, not logged in' "run \`glab auth login --hostname $gitlab_host\` yourself; only needed for GitLab projects"
    else
        report note 'glab installed, not logged in' 'run `glab auth login` yourself; only needed for GitLab projects'
    fi
fi
if [[ "$host_cli_logged_in" == false ]]; then
    login_fix='run `gh auth login` or `glab auth login` yourself; agents never enter credentials'
    if [[ "$host_cli_installed" == false ]]; then
        login_fix="install \`gh\` (GitHub) or \`glab\` (GitLab), then $login_fix"
    fi
    required_gone 'host CLI login' "$login_fix"
fi

kit_skill_source=$(shell_path "$KIT_DIR/playbook/skills/kit")
codex_skill_source=$(shell_path "$KIT_DIR/playbook/skills/kit-codex")

section 'Claude Code'
if [[ -f "$claude_dir/CLAUDE.md" ]] && grep -Fq "$marker_begin" "$claude_dir/CLAUDE.md"; then
    report ok 'orchestration policy in ~/.claude/CLAUDE.md'
elif [[ -f "$claude_dir/CLAUDE.md" ]] && grep -Fq "$policy_heading" "$claude_dir/CLAUDE.md"; then
    # install-global.sh looks only for the marker and would append a second copy here.
    report ok 'orchestration policy in ~/.claude/CLAUDE.md (kept by hand, no marker block)'
else
    host_gone 'orchestration policy in ~/.claude/CLAUDE.md' 'run `./install-global.sh`'
fi
for agent in scout builder verifier architect; do
    check_file "agent $agent" "$agents_dir/$agent.md" 'run `./install-global.sh`'
done
check_file 'skill /kit' "$claude_dir/skills/kit/SKILL.md" \
    "run \`mkdir -p ~/.claude/skills && ln -s $kit_skill_source ~/.claude/skills/kit\`"
check_skill rpa-init
check_skill rpa-gen-rules

section 'Codex'
check_file 'skill $kit' "$home/.agents/skills/kit/SKILL.md" \
    "run \`mkdir -p ~/.agents/skills && ln -s $codex_skill_source ~/.agents/skills/kit\`"

section 'Optional'
if command -v shellcheck > /dev/null 2>&1; then
    report ok 'ShellCheck'
elif command -v docker > /dev/null 2>&1 && docker info < /dev/null > /dev/null 2>&1; then
    report ok 'Docker'
else
    report note 'ShellCheck or Docker' 'optional, for the shell lint in `make test`'
fi
if command -v codex-task > /dev/null 2>&1; then
    report ok 'codex-task'
else
    report note 'codex-task' 'only for the mixed setup where Claude Code delegates to Codex'
fi
expected_kit=$(physical_dir "$home/Developer/project-kit")
if [[ "$expected_kit" == "$KIT_DIR" ]]; then
    report ok 'kit location'
else
    report note 'kit location' "the /kit skills expect the kit at ~/Developer/project-kit; this checkout is at $KIT_DIR"
fi

printf '\n'
if [[ "$host_missing" -gt 0 ]]; then
    printf '%s\n' 'Claude Code and Codex items matter only for the agent host you use.'
fi
if [[ "$required_missing" -eq 0 ]]; then
    printf 'doctor: ready\n'
else
    printf 'doctor: %d required item(s) missing\n' "$required_missing"
    exit 1
fi
