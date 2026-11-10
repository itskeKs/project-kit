# Onboarding a new project

One session, one afternoon: at the end the repo has the working contract, the gates, the
templates, milestones and issues, and the first issue session can start. The steps build on each
other; anyone taking over an existing repo with a backlog needs all of them.

## Prerequisites

The global layer is on the machine: `~/.claude/CLAUDE.md`, the agents in `~/.claude/agents/`, the
skills `/rpa-init` and `/rpa-gen-rules`, the wrapper `codex-task`. `./install-global.sh` in the kit
directory installs the policy and the four agents and skips what already exists (`--dry-run`
previews it); the skills and `codex-task` you provide yourself. The host CLI (`glab` or `gh`) is
logged in by the owner: `glab auth status --hostname <host>` or `gh auth status`. Agents never
enter tokens; if the login is missing, the session reports it and keeps working locally.

The kit itself is never pushed into a project; only the copied files land in the target
repository. For a self-hosted GitLab instance the host is a parameter everywhere there:
`glab auth login --hostname <host>`, `GITLAB_HOST=<host>` for `glab` commands in the project,
`kit/gitlab/protect.sh --host <host>`.

## 1 Bootstrap

```bash
./bootstrap.sh /path/to/repo --host gitlab
```

The target must exist and be a Git repo (`mkdir … && git -C … init -b main`).
`bootstrap.sh` copies `kit/common/` and `kit/gitlab/repo/` (or `kit/github/repo/`), creates the
symlink `CLAUDE.md -> AGENTS.md`, replaces the host placeholders and `{{DEFAULT_BRANCH}}` in the
copied files and prints the next steps. It reads the main branch from the remote's current
default branch (`origin/HEAD`, set on a clone) and otherwise from the checked-out branch; an
existing repo therefore stays on `main`, `master` or `develop`.
Anyone copying the kit from a feature branch into a repo without `origin/HEAD` passes
`--default-branch <name>`; the output says where the value came from. Bytecode (`__pycache__`,
`*.pyc`) is never copied. Existing files are left untouched and listed as skipped;
if the repo already has a `Makefile`, the targets from `kit/common/Makefile`
(`test-agent-rules`, `docs-check`, `hooks`, the `TESTDB_LOCK`) are taken over by hand. First
commit: `chore: add project kit`.

## 2 Warm up context: `/rpa-init`

Start a Claude Code session in the target repo and run `/rpa-init`. The skill reads code, docs and
tests, sets up the development environment the way the repo documents it, runs the tests and
writes a short project report (behavior from tests, gaps, risks). This report is the source for
`AGENTS.md` "What the code does not tell you", for the placeholders `{{TEST_CMD}}`,
`{{LINT_CMD}}`, `{{TEST_DB}}` and for the first issues.

## 3 Generate rules: `/rpa-gen-rules`

`/rpa-gen-rules` generates the paired rules `.claude/rules/<topic>.md` and
`.cursor/rules/<topic>.mdc` from code, tests and docs; the Codex hook from the kit
(`.codex/hooks.json`, `.codex/hooks/attach_rules.py`) attaches them. Afterwards:

```bash
make test-agent-rules
```

The test checks parity of the two trees, the symlink and the hook; before the rules are generated
it skips the rule tests with a clear notice. After that it requires, for every topic with `globs`,
a representative path in the dictionary `PROJECT_CASES` at the top of
`scripts/test_agent_rules.py` (path → topic; the set of topics must match the generated rules
exactly), so that a moved path or a new topic without a case stands out; the always-on topics are
checked by the SessionStart test.
Codex needs `/hooks` once per clone to confirm the two handlers.

## 4 Fill in the project facts

`grep -rn '{{' --exclude-dir=.git .` lists the open placeholders. Order:

- `AGENTS.md`: intro sentence, stack, license, owner; "What the code does not tell you" from the
  rpa-init report; the gates table with the real commands and `{{SUITE_DURATION}}`; under
  "Verification" the evidence for surface changes (`{{UI_EVIDENCE}}`: web, app or
  "no user interface", the comment names the three forms) and the sentence on the sweep test, if
  there is one; under "Databases and containers" keep exactly one of the two variants: A for
  projects with a database, migrations and a shared test DB (test DB, lock, production taboos),
  B for projects without a database (server, app, library: production is then hosts, releases,
  signing keys). The rules marked with `<!-- proven -->` stay, the HTML comments
  go. Without a test DB the lock section in `CONTRIBUTING.md` and the
  `TESTDB_LOCK` block in the Makefile also go.
- For the session briefs: note `{{SUITE_DURATION}}`, `{{LOCK_RULE}}` ("none" if the tests
  use isolated resources), `{{UI_EVIDENCE}}`, `{{BLOCKER_CATEGORIES}}` (the finding categories
  that are still fixed after the third review: data loss or corruption, wrong results in the
  core domain, access across users or tenants, data protection; `AGENTS.md` carries the same
  list) and `<LOCK_MAX>` (twice the suite duration plus 30 minutes); they appear in the tables
  of the briefs.
- `DESIGN.md`: derive it from the existing surface (tokens, components, states, formats);
  note deviations as debt with an issue number. Without a UI the file governs the visible
  surface that does exist (CLI output, API shapes, error codes).
- `docs/architecture.md`, `docs/feature-status.md`, `docs/roadmap.md`, `SECURITY.md`,
  `CONTRIBUTING.md`, the project's `README.md` (the docs map `docs/README.md` links to it).
- CI: in `.gitlab-ci.yml` the image `{{CI_IMAGE}}` and, if needed, the database service; in
  `.github/workflows/tests-on-pr.yaml` the toolchain step. Both only call Make targets. The
  gates (`lint`, `test`, `docs-check`) start immediately, release and deploy jobs depend on them
  and carry explicit rules so that an MR pipeline never creates a deploy job; manual
  runs ("Run pipeline") go through the gates like a push. Gates that CI cannot run
  (such as a build that needs macOS) are listed in the CI header comment, in `AGENTS.md` and as
  `<LOCAL_GATE>` in the briefs. If tests check file permissions, GitLab's Docker executor needs
  `FF_DISABLE_UMASK_FOR_DOCKER_EXECUTOR` (comment in the `test` job).

Then get `make lint`, `make test`, `make docs-check` and `make hooks` green and commit.

### Contract tests that pin down the old state

Many repos have tests that check sentences or sections of the previous `AGENTS.md`, `README.md`
or docs (documentation contracts, router tests). After the bootstrap they turn red. Before filling
in, search with `rg -n 'AGENTS.md|README.md|CONTRIBUTING.md' tests/` (or the stack's test
directory) and plan for them: these tests are switched to the new contract in the same PR or MR,
not loosened or deleted; a sentence that a test demands and that still holds stays in the
new `AGENTS.md`. Budget a round of its own per repo for this.

## 5 Backlog into milestones and issues

The roadmap (`docs/roadmap.md`) gets the goal in one sentence and the milestones as
headings with numbered issue lists; milestone 1 "Foundation" is pre-filled. Each backlog item
becomes an issue in the spec format of the template (`.gitlab/issue_templates/Default.md` or
`.github/ISSUE_TEMPLATE/task.md`): What, Why it happens (defects and gaps only, checked against
`main` with file:line), Proposed change (smallest change, reuse, files named), Acceptance
(checkboxes, each one verifiable), Out of scope (where it belongs instead). What only the owner
can decide goes in "Open decisions" of the roadmap and as an issue comment, never as a silent
assumption.

Commands for GitLab are in [kit/gitlab/cli.md](kit/gitlab/cli.md) (`glab milestone create`,
`glab issue create --description-file … --label task --milestone …`); for GitHub the
`gh` column of the same table. The issue session can take over the transfer if the
backlog exists as a file; the decision what goes in stays with the owner.

## 6 Core journeys and first acceptance

Write five to fifteen core journeys with the owner in `docs/acceptance/journeys.md`: the flows
the product exists for, in user language, with a shared sample world (placeholders
`{{PERSONA}}`, `{{SAMPLE_DATA}}`, `{{JOURNEY_TITLE}}`) and results calculated by hand; the
files a user would bring along go under `docs/acceptance/data/`. In `AGENTS.md` under
"Verification" is `{{ACCEPTANCE_ENV}}`: where acceptance runs take place (local dev stack, portable
package, staging), never production, and whether every run gets its own environment. The owner
says this; if it is shared (shared staging, fixed ports), the sessions serialize their runs
via `/tmp/<project>-acceptance.lock`.

For an **existing project**, a first run of the blind acceptance agent over all journeys on the
main branch follows immediately ([playbook/acceptance.md](playbook/acceptance.md)). It shows what
does not work for a user today, before new work is added. The owner sorts the findings (Defect,
Usability, False alarm, As intended); the defects and usability problems become issues in the spec
format with a user check, and they come in the roadmap before new capabilities. A project that only
agents have checked in particular is green at issue level and still unusable for a user; this run
is the honest starting point. The automated twins of the journeys (`features/journeys/`)
come into being with these issues: every finding fails as a step in the twin before its fix.

## 7 CI gates and protection of the main branch

Let a pipeline or workflow run first so that the job names exist, then:

```bash
kit/gitlab/protect.sh group/project --host <host>
```

sets the protected main branch (`--branch` if it is not called `main`; nobody pushes directly,
maintainers merge), "Pipelines must succeed", "all discussions resolved", delete the source branch
after the merge; with `--approvals N` additionally required approvals, as far as the instance
offers them: on GitLab Free and on a self-hosted instance without Premium there are no
enforceable approvals, the API answers 403 or 404, and the script reports that and carries on.
Finally it lists CI variables that are not "protected": MR pipelines run branch code and can read
every unprotected variable, so deploy keys and tokens are set to "Protect variable" in the
project settings (the script does not change them). For GitHub:

```bash
kit/github/protect.sh owner/repo --check lint --check test --check docs
```

with exactly the job names from `tests-on-pr.yaml` as required checks (`--branch` if the main
branch is not called `main`). A pull request is required
(without required approvals, so that a single maintainer can merge; `--reviews N` raises that),
direct pushes are thereby off, admins are included, force-push and deletion are off. The release
job and the release workflow react to tags `vX.Y.Z`, which must lie on the main branch, and push
the image to the host's registry.

## 8 Start the session chain

Every issue gets its own session with empty context, which takes it from claiming it to the merge;
the templates are in [playbook/session-briefs/](playbook/session-briefs/) (`<KIT_PATH>`
in the templates is the kit's local path, because the playbook does not live in the project). The
owner starts only the beginning of a chain, after that each session starts its successor session
itself: with `<HANDOVER>` = `after PR` as soon as its own PR/MR is open, with `after merge` only
after its merge, so that one issue at a time is in progress ([Workflow](playbook/workflow.md), "One
session, one task"). Start with `after merge`; switch to `after PR` once the chain runs smoothly.

The simplest way is the `/kit` skill, used in a chat that runs in the project's main checkout:
link it once with `ln -s <KIT_PATH>/playbook/skills/kit ~/.claude/skills/kit`, register the project
with `/kit init` and complete the TODO values it names, then `/kit next` starts the next unblocked
issue as a detached session, `/kit pr <N>` a maintainer session, `/kit bug <text>` or
`/kit feat <text>` drafts an issue from a sentence and starts it after your OK, and `/kit status`
shows the project's PRs, issues, worktrees and locks and what needs you. Outside a checkout the commands take
the project name, and `/kit status` covers all registered projects.

In Codex the same commands run as `$kit …`: link the supplement once with
`ln -s <KIT_PATH>/playbook/skills/kit-codex ~/.agents/skills/kit`. It reads the Claude skill and
maps the desktop app's session tools to the Codex app's thread tools, so a task started there
follows the same brief, including the handover and the merge, and names itself
`<project> #N: …` like a Claude session. Two differences remain: Codex implements directly instead
of delegating to `codex-task`, and a finished task is not archived automatically. By hand:

1. A new, empty chat with the [issue session](playbook/session-briefs/issue-session.md) and
   `<TASK>` = first issue of the milestone; `playbook/session-briefs/fill-brief.py issue <repo-path> <N>
   --copy` fills the brief from `~/.config/project-kit/briefs/<project>.env`, which
   `fill-brief.py init <repo-path>` creates once. It opens the PR/MR, starts the issue session
   for the next issue, has its PR/MR checked by a `verifier` with fresh context,
   fixes the findings and merges it itself. If there is no unblocked issue left, the chain ends,
   and the owner restarts it as soon as the milestone has open issues again.
2. The [maintainer session](playbook/session-briefs/maintainer-session.md) only for a PR/MR
   that no session is working on anymore, with `<PR_NO>` = that PR/MR: an issue session ended
   without a merge (it never waits for the owner, for example for a user check `owner` or an
   answer, and waits at most an hour for a stack base; the comment "Not merged" on the PR/MR
   and its report give the reason), a session was aborted, a parked PR/MR has been released,
   or it comes from outside the kit. It brings it to completion and starts no successor
   session. For a member of a stack whose session ended before the base was merged, the base's
   session starts it itself after its merge.

In the Claude desktop app a session starts its successor session with `start_session` (fresh
context, no fork, without an app worktree); that is why the owner also starts the first session of
each chain in the main checkout without an app worktree, because a successor session inherits its
predecessor's location.
The owner starts it from a new, empty chat, never from the chat in which they are planning: the app
wakes a session's starter with its whole context at the end of each of that session's turns, and
a full planning chat pays for that again for every finished session. Every session therefore
detaches from its starter first thing with `detach_session` (it is in the briefs). For the
project sessions only the connectors and plugins the project needs should be switched on;
every MCP server pays its tool list in every step of every session.
In the terminal a session names the next issue in its report, and the owner copies the
filled-in brief into a new chat. All sessions of a project run on one machine,
because the locks under `/tmp` and the worktree claims apply only there. Merging happens one at a
time under a short lock (`/tmp/<project>-merge.lock`), which a session holds only around updating
and merging, at most `<LOCK_MAX>` long; anyone who finds it taken waits for a limited time. All
sessions follow the [workflow](playbook/workflow.md) and the [roles](playbook/roles.md); Codex
briefs follow [playbook/codex-briefs.md](playbook/codex-briefs.md).

## What is deliberately not copied

- The project rules under `.claude/rules/` and `.cursor/rules/`: they describe layers,
  paths and invariants of a specific project and are generated per project with
  `/rpa-gen-rules`. Only the hook that attaches them comes from the kit.
- Domain pages (`docs/m*.md`), ADR contents, feature catalog, operations pages: the kit supplies
  skeletons and the rule for when a page comes into being, not the content.
- Deploy scripts, installers, compose files, server bootstrap: too project-specific. The kit
  names only the form (release on tag, deploy via an SSH key with a forced command,
  production taboos in `AGENTS.md`).
- The global layer (`~/.claude/…`, `codex-task`, skills): is already on the machine (the policy
  and the agents come from `install-global.sh`) and is maintained per machine, not per repo.
- `.gitignore`, license file, `.env.example`: depend on the stack and on the owner's choice of
  license.
