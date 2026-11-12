# project-kit: reference

This is the technical reference. [README.md](README.md) is the short version, [onboarding.md](onboarding.md)
the step-by-step recipe.

project-kit is a way of working for repositories in which several coding agents work in parallel,
plus the files and scripts that install it. Each issue gets its own agent session, every change is
reviewed by a fresh agent, and every milestone is accepted from the user's side. The owner decides
and logs in; agents do everything else that an agent can do. The kit targets GitHub and GitLab.

## How it works

The kit has three layers. Only the second is copied into your repository.

| Layer | Where it lives | What belongs to it |
| --- | --- | --- |
| 1 Global tooling | On your machine; policy and agents ship in [kit/global/](kit/global/) | The skills `/rpa-init` and `/rpa-gen-rules` (both hosts); with Claude Code the orchestration policy in `~/.claude/CLAUDE.md` and the agents `scout`, `builder`, `verifier` and `architect` in `~/.claude/agents/`; with Codex its own orchestration; in a mixed setup the Codex wrapper `codex-task` |
| 2 Files in the repo | [kit/](kit/) | Working contract `AGENTS.md` with a `CLAUDE.md` symlink, `DESIGN.md`, docs skeleton with a template for the core journeys, `SECURITY.md`, `CONTRIBUTING.md`, Makefile with `docs-check` and a rule test, Codex hook, Gherkin guide; per host an issue template, a PR/MR template, CI and a script that protects the main branch |
| 3 Process | [playbook/](playbook/) | The workflow, the roles, acceptance from the user's side, Codex briefs, the two session prompts and the `/kit` skill that starts and oversees sessions |

The kit is not a dependency of the projects it serves. Clone it once, run `install-global.sh` once
per machine for the policy and the agents of layer 1, and `bootstrap.sh` copies layer 2 into each
repository. Project rules (`.claude/rules/`, `.cursor/rules/`) are not copied.
`/rpa-init` and `/rpa-gen-rules` generate them per project, and the Codex hook from the kit
attaches them.

A change follows this path. The owner keeps a roadmap with milestones. Each backlog item becomes an
issue in a spec format, with a user check that says what a user does and sees. One session per
issue takes it from claiming to merge. It works in its own worktree, writes tests red first and
opens the PR (GitLab: MR). A fresh `verifier` agent reviews it, and the session fixes the findings
in rounds. After the third review the scope is frozen, and findings outside it become follow-up
issues. As soon as its PR is open, or after its merge, the session starts a successor session for
the next unblocked issue. Before the merge of a PR with a user check, a blind acceptance agent
without code access tries the user check. Per milestone it runs over all core journeys, and the
owner accepts the result. A maintainer session exists only for PRs that no session works on
anymore. Merges run one at a time under a short lock, so CI has checked exactly what lands.

In a repository where someone else merges (an upstream project we contribute to), the project file
says `MERGE_BY=maintainer`. The same briefs then switch blocks: the session claims its issue by
assigning it to the owner, hands its PR over to the maintainer instead of merging it, posts no
comment on issues or PRs (questions and outcomes go into its report), merges `origin/<main>` into
its branch, never rebases or force-pushes, and stops at once when anyone else pushes to the PR. It
picks successor issues only from the owner's own (assigned to the owner, or opened by the owner
without an assignee), and the maintainer session shrinks to one round of fixes on our open PR.
`kit-status.py` lists those PRs as "Waiting for maintainer". Without the key, `MERGE_BY=session`
applies and nothing changes.

Details: [workflow.md](playbook/workflow.md) (the path of a change), [roles.md](playbook/roles.md)
(owner, orchestrator, Codex, subagents), [acceptance.md](playbook/acceptance.md) (user check and
acceptance), [session-briefs/](playbook/session-briefs/) (the two session prompts).

## Requirements

- `git`, `bash` and Python 3.
- `gh` (GitHub) or `glab` (GitLab), logged in by the owner. Agents never enter credentials.
- Claude Code or the Codex app; both run the whole process. In Claude Code the `/kit` skill starts
  detached sessions with the desktop app's session tools; in Codex the supplement skill runs the
  same commands as `$kit` and starts threads (see [Working with Codex](#working-with-codex)). In a
  terminal you paste the filled brief into a new chat instead.
- Optional: ShellCheck or Docker, for the shell lint in `make test`.

The briefs expect the following on your machine. The kit ships the first two, which only Claude
Code needs, and installs them with `install-global.sh`; the rest is yours.

- With Claude Code: the orchestration policy in `~/.claude/CLAUDE.md`. Source: [kit/global/orchestration-policy.md](kit/global/orchestration-policy.md).
- With Claude Code: the agents `scout`, `builder`, `verifier` and `architect` in `~/.claude/agents/`. Source:
  [kit/global/agents/](kit/global/agents/). [roles.md](playbook/roles.md) describes what each one does.
  Codex has no counterpart to install; the supplement skill maps these roles to Codex threads and
  subagents.
- The skills `/rpa-init` and `/rpa-gen-rules`, from [EvilFreelancer/rpa-skills](https://github.com/EvilFreelancer/rpa-skills)
  (MIT). In Claude Code: `/plugin marketplace add EvilFreelancer/rpa-skills`, then
  `/plugin install rpa-init@rpa-skills` and `/plugin install rpa-gen-rules@rpa-skills`. In Codex:
  `codex plugin marketplace add EvilFreelancer/rpa-skills`, then install both from `/plugins`.
- The wrapper `codex-task DIR BRIEF_FILE [LOG]`, needed only in the mixed setup where Claude Code
  is the host and delegates implementation to Codex. You supply it; [kit/global/README.md](kit/global/README.md)
  says what the briefs expect of it. A Codex-hosted session implements directly and needs no wrapper.

`./install-global.sh` copies `kit/global/agents/*.md` to `~/.claude/agents/` and appends
`kit/global/orchestration-policy.md` to `~/.claude/CLAUDE.md`, inside a block between `<!-- project-kit:begin -->`
and `<!-- project-kit:end -->`. It creates missing directories and honors `HOME`. It never
overwrites an existing agent file and never adds a second block; it reports and skips both.
`--dry-run` prints what it would do and changes nothing. To take a newer version of a file, remove
the old one (or the block) by hand and run it again. It does not touch `settings.json`.

If you use other tooling for these pieces, provide equivalents before you start sessions.

## Quick start

[onboarding.md](onboarding.md) has the long form. In short:

1. Clone the kit. Any path works for `bootstrap.sh`; the docs and the `/kit` skill assume
   `~/Developer/project-kit`. Install the policy and the agents once per machine.
   ```bash
   git clone git@github.com:itskeKs/project-kit.git ~/Developer/project-kit
   cd ~/Developer/project-kit && ./install-global.sh
   ```
2. Bootstrap the target repository, a new one or an existing one. Run this from the kit
   directory. Existing files are never overwritten, and skipped files are reported. Add
   `--dry-run` to preview.
   ```bash
   git -C ~/work/acme init -b main      # skip for an existing repository
   ./bootstrap.sh ~/work/acme --host github   # or --host gitlab
   ```
   The main branch comes from `origin/HEAD`, else the checked-out branch. `--default-branch NAME`
   sets it explicitly.
3. Start Claude Code in the target repository. Run `/rpa-init`, then `/rpa-gen-rules`, then
   `make test-agent-rules`.
4. Fill `AGENTS.md` and `DESIGN.md` with the project facts and replace the open placeholders
   (see [Placeholders](#placeholders)). Then get `make lint`, `make test`, `make docs-check` and
   `make hooks` green and commit.
5. Move the backlog into milestones and issues in the spec format. Write the core journeys in
   `docs/acceptance/journeys.md` with the owner. [kit/gitlab/cli.md](kit/gitlab/cli.md) maps
   every `gh` command of the process to `glab`.
6. Let CI run once so the job names exist, then protect the main branch. Run this from the kit
   directory. `--host` is for a self-hosted GitLab instance.
   ```bash
   kit/github/protect.sh owner/repo --check lint --check test --check docs
   kit/gitlab/protect.sh group/project --host gitlab.example.com
   ```
   The checks are the job names from `tests-on-pr.yaml`. The GitLab script also lists unprotected
   CI variables; the owner protects those.
7. Start the first issue session in a new, empty chat, from the kit directory.
   `fill-brief.py init` writes the project file `~/.config/project-kit/briefs/<project>.env`
   once. Complete the TODO values it lists; `MERGE_BY` is `session` unless someone else merges the
   project's PRs. `/kit` reads the same file.
   ```bash
   playbook/session-briefs/fill-brief.py init ~/work/acme
   playbook/session-briefs/fill-brief.py issue ~/work/acme 1 --copy
   ```
   Or use the skill: `ln -s ~/Developer/project-kit/playbook/skills/kit ~/.claude/skills/kit`.
   In a chat that runs in the project checkout, `/kit init` does the same as `fill-brief.py init`.
   `/kit next` then starts the next unblocked issue, and `/kit status` shows what needs the owner.
   `/kit issue <N>`, `/kit pr <N>`, `/kit bug <text>` and `/kit feat <text>` start other sessions.

Each session merges its own PR (with `MERGE_BY=maintainer`: hands it over) and starts its successor.
All sessions of a project run on one machine, because the merge lock and the worktree claims live
under `/tmp`.

## Repository layout

```
bootstrap.sh              copies kit/common and kit/<host>/repo into a repository,
                          creates CLAUDE.md -> AGENTS.md, fills host placeholders and the main branch
install-global.sh         copies kit/global/agents/*.md to ~/.claude/agents/ and appends the policy
                          to ~/.claude/CLAUDE.md in a marker block; never overwrites, --dry-run previews
onboarding.md             the recipe for a new project
Makefile                  make test and make docs-check for the kit itself
playbook/
  workflow.md             the path of a change from roadmap to merge
  roles.md                owner, orchestrator, Codex worker, subagents, acceptance agent
  acceptance.md           user check, blind acceptance agent, owner's acceptance
  codex-briefs.md         what a Codex brief contains and why runs fail
  session-briefs/         issue-session.md, maintainer-session.md, fill-brief.py, kit-status.py
  skills/kit/             the /kit skill for Claude Code
  skills/kit-codex/       supplement that runs the same commands as $kit in Codex
kit/global/               global layer: agents/ (scout, builder, verifier, architect), orchestration-policy.md
                          (the orchestration policy), README.md (what stays yours, codex-task)
kit/common/               files for every repository, with {{PLACEHOLDERS}}
  AGENTS.md DESIGN.md SECURITY.md CONTRIBUTING.md Makefile
  docs/                   skeleton: roadmap, architecture, feature status, ADRs, operations,
                          acceptance journeys
  features/               Gherkin guide
  scripts/                link checker, rule test, pre-commit checks
  .codex/                 hook that attaches the generated rules to Codex sessions
  .githooks/              pre-commit hook, enabled with make hooks
kit/github/repo/.github/  issue template, PR template, tests-on-PR workflow, release image (GHCR)
kit/github/protect.sh     protected main branch with required checks, via gh api
kit/gitlab/repo/          .gitlab-ci.yml with a release job, issue and MR templates
kit/gitlab/protect.sh     protected main branch, "Pipelines must succeed", approvals, via glab api
kit/gitlab/cli.md         every gh command of the process and its glab counterpart
tests/                    test_bootstrap.sh, test_install_global.sh, test_fill_brief.py,
                          test_kit_status.py
```

## Placeholders

Kit files carry two kinds of placeholders.

| Kind | Placeholders | Filled by |
| --- | --- | --- |
| Host | `{{HOST}}`, `{{HOST_CLI}}`, `{{HOST_PR}}`, `{{HOST_PR_ABBR}}`, `{{HOST_ISSUE_TEMPLATE}}`, `{{HOST_PR_TEMPLATE}}`, `{{HOST_CI_FILE}}`, `{{HOST_ISSUE_VIEW}}`, `{{HOST_SECURITY_CHANNEL}}`, `{{DEFAULT_BRANCH}}` | `bootstrap.sh`, to match `--host` and the main branch |
| Project | `{{PROJECT_NAME}}`, `{{PROJECT_ONE_LINER}}`, `{{REPO}}`, `{{OWNER}}`, `{{STACK}}`, `{{LICENSE}}`, `{{SOFTWARE_LANGUAGE}}`, `{{TEST_CMD}}`, `{{LINT_CMD}}`, `{{TEST_DB}}`, `{{SUITE_DURATION}}`, `{{LOCK_RULE}}`, `{{UI_EVIDENCE}}`, `{{ACCEPTANCE_ENV}}`, `{{PRODUCTION_TABOOS}}`, `{{BLOCKER_CATEGORIES}}`, `{{CI_IMAGE}}`, `{{DEPLOY_TARGET}}`, `{{PERSONA}}`, `{{SAMPLE_DATA}}`, `{{JOURNEY_TITLE}}` | The onboarding session, from the `/rpa-init` report and the owner |

`{{BLOCKER_CATEGORIES}}` names the finding categories that are still fixed after the scope
freeze. `{{LOCK_RULE}}`, `{{SUITE_DURATION}}`, `{{UI_EVIDENCE}}` and `{{BLOCKER_CATEGORIES}}` also
appear in the session briefs.

Run this in the target repository to list what is still open:

```bash
grep -rn '{{' --exclude-dir=.git .
```

`AGENTS.md` has two variants for "Databases and containers", one for projects with a database and
one without. Keep exactly one. The same file suits web applications, servers, apps and libraries.

## Working with Codex

Codex is a full host for the kit, not only a worker. The supplement skill in
`playbook/skills/kit-codex/` runs the `/kit` commands as `$kit` and maps the Claude desktop app's
session tools to the Codex app's thread tools. A task started there follows the same brief,
including the handover to its successor and the merge, and names itself `<project> #N: …` like a
Claude session. Two differences remain: Codex implements directly instead of delegating to
`codex-task`, and a finished task is not archived automatically. The supplement reads the Claude
skill, so link both:

```bash
ln -s ~/Developer/project-kit/playbook/skills/kit ~/.claude/skills/kit
ln -s ~/Developer/project-kit/playbook/skills/kit-codex ~/.agents/skills/kit
```

The hook in `kit/common/.codex/` attaches the generated rules to Codex sessions: the always-on
rules at session start, the scoped rules before `apply_patch`, `Edit` or `Write`. It reads the
`.cursor/rules/` tree; approve it once per clone with `/hooks`.
[codex-briefs.md](playbook/codex-briefs.md) lists what every Codex brief states: scope, red-first
tests, prohibitions on push, merge and production, and a short report. They apply to the mixed
setup, where a Claude Code session hands implementation to Codex through `codex-task`.

## Tests

```bash
make test
```

runs four suites. `tests/test_bootstrap.sh` bootstraps both hosts into a temp directory. It checks
files, the symlink, placeholders, default-branch detection, no overwriting and idempotence. On the
result it runs the link checker and the rule test. `tests/test_install_global.sh` runs
`install-global.sh` against temporary home directories. It checks a fresh install, that a second run
changes nothing, that an existing agent file or `CLAUDE.md` content is kept, that `--dry-run`
creates nothing and bad arguments. It never touches your real `~/.claude`.
`tests/test_fill_brief.py` covers `fill-brief.py`.
`tests/test_kit_status.py` covers `kit-status.py` offline, with fake `gh` and `glab`. ShellCheck
then runs over the shell scripts, directly if installed or through Docker, else it is skipped.

```bash
make docs-check
```

checks the relative links in the kit. It skips `kit/github/` and `kit/gitlab/`, whose links resolve
only in a bootstrapped repository; `test_bootstrap.sh` covers those.

## Origin and licenses

`kit/common/.codex/hooks/attach_rules.py` and `.codex/hooks.json` are taken over from
[coddy-agent](https://github.com/coddy-project/coddy-agent) (MIT, Copyright (c) 2026 Pavel Rykov); the license text is in the script. The skills `/rpa-init`
and `/rpa-gen-rules` come from [EvilFreelancer/rpa-skills](https://github.com/EvilFreelancer/rpa-skills) (MIT)
and are not in the kit. The link
checker, the rule test and the templates are generalized from the project where the process
originated. The repository itself is under the [MIT License](LICENSE).
