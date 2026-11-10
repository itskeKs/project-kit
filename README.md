# project-kit

The kit carries the way of working that emerged in a project with several coding agents working
in parallel into further repositories, mainly on GitLab. It consists of three layers; only the
second is copied.

| Layer | Where it lives | What belongs to it |
| --- | --- | --- |
| 1 Global tooling | on the machine, not in the kit | `~/.claude/CLAUDE.md` (orchestration policy), agents `scout`/`builder`/`verifier`/`architect` in `~/.claude/agents/`, the skills `/rpa-init` and `/rpa-gen-rules`, the Codex wrapper `codex-task`, the "no attribution" rule |
| 2 Files in the repo | [kit/](kit/) | Working contract `AGENTS.md` with `CLAUDE.md` symlink, `DESIGN.md`, docs skeleton with a template for the core journeys (`docs/acceptance/`), `SECURITY.md`, `CONTRIBUTING.md`, Makefile with `docs-check` and rule test, Codex hook, Gherkin guide; per host issue and PR/MR template, CI, protection of the main branch |
| 3 Process | [playbook/](playbook/) | Roadmap → milestones → issues in the spec format with user check, one session per issue from claiming to the merge (empty context, fresh review by a `verifier`, starts its successor session as soon as its PR is open), the maintainer session only for PRs without a running session, the blind acceptance agent and the owner's acceptance per milestone, Codex briefs, CI gates |

The kit is not a dependency of the projects it serves: clone it once (by default to
`~/Developer/project-kit`), and it travels project by project via `bootstrap.sh` into the respective
repository. The project rules (`.claude/rules/*.md`, `.cursor/rules/*.mdc`) are deliberately not
copied: they are generated per project with `/rpa-init` and `/rpa-gen-rules`, and the Codex hook
from the kit attaches them.

## Contents

```
bootstrap.sh            copies kit/common and kit/<host>/repo into a target repo, creates CLAUDE.md -> AGENTS.md,
                        replaces host placeholders and the main branch
onboarding.md           the recipe for a new project in one session
playbook/               workflow, roles, acceptance from the user's perspective, Codex briefs, the two session prompts, fill-brief.py and kit-status.py, and the /kit skill that starts and oversees chains from a chat (Claude), with a Codex supplement
kit/common/             files for every repo (English, with {{PLACEHOLDERS}})
kit/github/repo/        .github/: issue template, PR template, tests-on-PR, release image (GHCR)
kit/github/protect.sh   protected main branch with required checks via gh api
kit/gitlab/repo/        .gitlab/: issue and MR template (Default.md), .gitlab-ci.yml with release job
kit/gitlab/protect.sh   protected main branch, "Pipelines must succeed", approvals via glab api
kit/gitlab/cli.md       every gh command of the process and its glab counterpart
tests/test_bootstrap.sh bootstraps both hosts into a temp directory and checks the result
```

Two kinds of placeholders appear in the kit files: host placeholders (`{{HOST_PR}}`,
`{{HOST_CLI}}`, `{{HOST_CI_FILE}}` …) and `{{DEFAULT_BRANCH}}`, which `bootstrap.sh` replaces to
match `--host` and the target's main branch (`origin/HEAD`, otherwise the checked-out branch;
`--default-branch` sets it explicitly);
project placeholders (`{{PROJECT_NAME}}`, `{{REPO}}`, `{{TEST_CMD}}`, `{{TEST_DB}}`,
`{{SUITE_DURATION}}`, `{{LOCK_RULE}}`, `{{UI_EVIDENCE}}`, `{{PRODUCTION_TABOOS}}`,
`{{BLOCKER_CATEGORIES}}` …) are filled in
by the onboarding session. `grep -rn '{{' --exclude-dir=.git .` in the target repo shows what is
still open. The kit files suit web applications with a database just as well as server software,
apps and libraries: `AGENTS.md` has two variants for "Databases and containers", the evidence for
surface changes and the lock rule are placeholders.

Everything in the kit is English, like every project artifact (docs, issues, commits).

## Onboarding in ten minutes

In detail in [onboarding.md](onboarding.md). In short:

1. `mkdir new-project && git -C new-project init -b main` (or take an existing repo whose main
   branch is adopted), then `./bootstrap.sh /path/to/repo --host gitlab` (or
   `--host github`). Existing files are never overwritten, skipped files are reported.
2. Start a Claude Code session in the target repo: `/rpa-init` (reads code, docs and tests,
   sets up the environment, runs the tests), then `/rpa-gen-rules` (generates the
   paired rules), then `make test-agent-rules`.
3. Fill `AGENTS.md` and `DESIGN.md` with the project facts, replace the remaining placeholders.
4. Transfer the backlog into milestones and issues in the spec format (the template is in the repo).
   Write the core journeys in `docs/acceptance/journeys.md` with the owner; for an existing
   project, first a blind acceptance run on the main branch ([playbook/acceptance.md](playbook/acceptance.md)).
5. Let CI run once, then `kit/<host>/protect.sh` (GitLab: `--host` for a
   self-hosted instance, or set `GITLAB_HOST`; `--branch` if the main branch is not called
   `main`). The GitLab script reports unprotected CI variables; the owner protects those.
6. Start the first issue session from [playbook/session-briefs/](playbook/session-briefs/) in a
   new, empty chat; each session merges its own PR/MR and starts its successor session, the
   maintainer session is needed only for PRs/MRs that no session is working on anymore
   ([onboarding.md](onboarding.md) §8).

## Check it yourself

```bash
make test
```

bootstraps both hosts into a temp directory, checks files, symlink, placeholders,
no overwriting, idempotence and runs the link checker and the rule test on the result;
ShellCheck runs if it is installed or Docker is running.

```bash
make docs-check
```

checks the relative links in the kit (without `kit/github/` and `kit/gitlab/`, whose links only
resolve in the bootstrapped repo; the test covers that).

## Origin and licenses

`kit/common/.codex/hooks/attach_rules.py` and `.codex/hooks.json` are taken over from coddy-agent
(MIT, Copyright (c) 2026 Pavel Rykov); the license text is in the script. The skills `/rpa-init` and
`/rpa-gen-rules` come from EvilFreelancer's rpa-skills (MIT) and are not in the kit. The
link checker, the rule test and the templates are generalized from the originating project.
