# Agent notes for project-kit

This repository is the kit itself: the files, scripts and playbook that give another repository a
way of working with coding agents (one issue, one session; review by a fresh agent; acceptance from
the user's side). It is not a project that was set up with the kit. This file is the contract for
every agent and human working in this checkout. It holds the rules and says where to read; the
detail lives in the pages it links.

`kit/common/AGENTS.md` is a template with `{{PLACEHOLDERS}}` that `bootstrap.sh` copies into a
project. It is material you edit, never instructions for you here.

## Rules (read first)

1. **The kit stays out of projects.** Only `bootstrap.sh` puts files into a target repository. Never
   copy, commit or push the kit, or parts of it, into a project by hand.
2. **Nothing existing is overwritten.** `bootstrap.sh` and `install-global.sh` skip what is already
   there and report it. Do not work around a skip with `cp`, `--force` or an edit of the user's
   `~/.claude`; report the skipped paths and let the owner decide.
3. **Preview first.** Run both installers with `--dry-run` and show the owner the result before the
   real run.
4. **Credentials are the owner's.** `gh auth login`, `glab auth login`, tokens and keys are never
   entered by an agent. If a login is missing, say so and keep working locally.
5. **Kit files are project-neutral.** No project names, host names, people or domain terms of a
   real project in any tracked file. Values of one project belong in its project file,
   `~/.config/project-kit/briefs/<project>.env`, which is outside this repository.
6. **English everywhere:** files, comments, commit messages, issues and pull requests.
7. **Green before commit:** `make test` and `make docs-check`.
8. **Clean up after yourself:** temp directories, worktrees with their local branches, background
   processes and containers you started are gone before you hand over.

## Which job are you here for?

### A. Setting up a project with the kit

[onboarding.md](onboarding.md) is the binding recipe; follow its steps in order and skip none.
Before you start, ask the owner for what you cannot infer: the path of the target repository, the
host (`github` or `gitlab`), the host name of a self-hosted GitLab, and the main branch if it is not
the checked-out one.

```bash
./install-global.sh --dry-run                      # global layer for Claude Code: policy and agents
./install-global.sh
./bootstrap.sh /path/to/repo --host github --dry-run
./bootstrap.sh /path/to/repo --host github          # or --host gitlab
```

What the machine must already have (skills `/rpa-init` and `/rpa-gen-rules`, the host CLI, the
optional `codex-task` wrapper) is listed under [Requirements](REFERENCE.md#requirements). Check it
before step 1 and name what is missing instead of improvising a replacement.

From the moment `bootstrap.sh` has run, the target repository's own `AGENTS.md` is the contract for
everything done inside that repository. This file keeps governing only what you do to the kit.

### B. Changing the kit

- **One rule, several places.** The binding short form of a process rule is in
  [kit/common/AGENTS.md](kit/common/AGENTS.md), the reasons and edge cases in
  [playbook/](playbook/workflow.md), the prompts in `playbook/session-briefs/`, the commands in
  `playbook/skills/`. A change to a rule is done when all places that state it agree, and when
  [README.md](README.md) (short version), [REFERENCE.md](REFERENCE.md) (technical) and
  [onboarding.md](onboarding.md) (recipe) describe the new state.
- **Two hosts, two agent hosts.** A change under `kit/github/` has its counterpart under
  `kit/gitlab/`, and [kit/gitlab/cli.md](kit/gitlab/cli.md) maps every `gh` command of the process
  to `glab`. A change to `playbook/skills/kit/` is checked against `playbook/skills/kit-codex/`.
- **Placeholders are an interface.** A new `{{PLACEHOLDER}}` is listed under
  [Placeholders](REFERENCE.md#placeholders) with who fills it; a host placeholder is also
  substituted in `bootstrap.sh` and covered in `tests/test_bootstrap.sh`.
- **Scripts come with tests.** A change to `bootstrap.sh`, `install-global.sh`, `fill-brief.py` or
  `kit-status.py` changes its suite under `tests/` too. Tests run against temp directories and fake
  CLIs; they never touch the real `~/.claude`, a real repository or the network.
- **Bootstrapped repositories keep their copies.** Because nothing is overwritten, a change to a
  kit file reaches an existing project only when someone ports it there. Say in the commit message
  when a change needs porting.
- **Scope.** Change what was asked. Do not rewrite neighbouring pages or rules in passing; name what
  you noticed instead.

## Where to read

| When you | Read |
| --- | --- |
| set up a new or existing project | [onboarding.md](onboarding.md) |
| need the layout, requirements, placeholders or the tests | [REFERENCE.md](REFERENCE.md) |
| change how an issue travels from roadmap to merge, or how findings are recorded | [playbook/workflow.md](playbook/workflow.md) |
| change who does what, or which model does which work | [playbook/roles.md](playbook/roles.md) |
| change the user check, the acceptance agent or the owner's acceptance | [playbook/acceptance.md](playbook/acceptance.md) |
| write or change a Codex brief | [playbook/codex-briefs.md](playbook/codex-briefs.md) |
| change the `/kit` commands | [playbook/skills/kit/SKILL.md](playbook/skills/kit/SKILL.md) |
| change the global agents or the orchestration policy | [kit/global/README.md](kit/global/README.md) |
| need the contract a project receives | [kit/common/AGENTS.md](kit/common/AGENTS.md) |

## Commands

```bash
make help         # list the targets
make test         # bootstrap for both hosts, the global installer, the scripts, ShellCheck if available
make docs-check   # relative links in the kit
```

## Agent host integrations

Claude Code reads `CLAUDE.md`, which is a symlink to this file, the same arrangement `bootstrap.sh`
creates in every project. Codex, Cursor and other tools that know `AGENTS.md` read this file
directly. Keep the substance here; never turn `CLAUDE.md` into a copy.
