# Agent notes for {{PROJECT_NAME}}

<!-- kit: This file is the working contract for every coding agent and every human in this
repository. Replace the placeholders in double braces, delete the HTML comments, keep the rules marked "proven".
Lines marked <!-- proven --> carried their weight in a project that ran this contract for weeks
with several agents in parallel; weaken them only with a reason written here. -->

{{PROJECT_ONE_LINER}} Stack: {{STACK}}. Licence: {{LICENSE}}. Owner: {{OWNER}}.
Where it is going: [docs/roadmap.md](docs/roadmap.md). What exists: [docs/feature-status.md](docs/feature-status.md).
Design contract: [DESIGN.md](DESIGN.md). Human-facing workflow and commands: [CONTRIBUTING.md](CONTRIBUTING.md).

The software is {{SOFTWARE_LANGUAGE}}; documentation, issues, code comments, tests and commits are
English (German costs about twice the tokens).

## What the code does not tell you

<!-- kit: Three to six bullets of facts an agent cannot infer from the code: resource limits,
legal or contractual invariants, where product decisions live, which production instances exist,
which open decisions must not be pre-empted. Link the generated rule under .claude/rules/ that
holds the details. Examples of the shape: -->

- Weight matters: <!-- the hardware the software must run on; what belongs in a worker, never in the request path -->
- Hard invariants are not negotiable: <!-- data isolation, immutability, legal rules; "a shortcut there is a defect even when tests pass" -->
- Product decisions are the owner's and live in issues (decision comments); code that still
  implements an older provisional value is debt with its own issue, not licence to keep it. <!-- proven -->
- A production instance with real data exists ({{DEPLOY_TARGET}}); see "Databases and containers" below.
- Open decisions: <!-- list issue numbers that must not be pre-empted in passing -->

## Agent host integrations

Claude Code reads `CLAUDE.md` (a symlink to this file) and loads `.claude/rules/*.md`. Cursor
loads the equivalent `.cursor/rules/*.mdc`. Codex reads `AGENTS.md` and uses `.codex/hooks.json`
to attach always-on rules at session start and scoped rules before `apply_patch`, `Edit` or
`Write`. Approve the hooks with `/hooks` once per clone; see
[CONTRIBUTING.md](CONTRIBUTING.md#agent-host-setup).

Rules Sync: a rule changes in both trees in the same commit, with equivalent bodies; a Claude rule
without `paths` is Cursor `alwaysApply: true`, otherwise `paths` equals `globs` with
`alwaysApply: false`. The Codex hook reads the Cursor tree directly and needs no index.
`make test-agent-rules` checks parity, the symlink and the hook. Scoped rules add context, not
enforcement; every baseline and safety rule here stays in force. <!-- proven -->

## Work comes from issues

- A task is a {{HOST}} issue written as a spec: What → Why it happens → Proposed change →
  User check → Acceptance → Out of scope (`{{HOST_ISSUE_TEMPLATE}}`). Read it with `{{HOST_ISSUE_VIEW}}`.
  There is no task list file. <!-- proven -->
- Scope is the issue's acceptance list: nothing less, nothing unasked. Do not add request or
  response fields, parameters, configuration keys, endpoints or options the issue does not name,
  and do not refactor neighbours in passing. One issue, one branch, one {{HOST_PR_ABBR}}.
  `Closes #N` only when every acceptance box is done; otherwise `Refs #N` plus what remains. <!-- proven -->
- Red first: the scenario and the unit tests fail without the change, then the smallest change
  turns them green, then refactor with the tests still green. <!-- proven -->
- A finding outside the scope is recorded, never extra code and not an issue per finding: after
  searching the open issues, one comment line `- [ ] <class or ?> | <screen or file:line> | <what was seen> | <SHA> | {{HOST_PR_ABBR}} #M`
  goes on the open bundle of its class (label `bundle`: one open issue per class of defect), on the
  open issue that already covers it, or on the inbox issue (label `inbox`: one standing issue); a
  triage run later turns the lines into issues. Only a finding in a blocker category (below, plus
  security and data loss) or a step of a core journey that a user cannot finish becomes a new issue
  at once, from `{{HOST_ISSUE_TEMPLATE}}`; outside that a session files at most one new issue per
  {{HOST_PR_ABBR}}, for a self-contained defect on the {{HOST_PR_ABBR}}'s own journey that has no class.
  A sentence in the {{HOST_PR_ABBR}} description is not a record. Before asking the owner a question,
  check the decisions already recorded (comments headed "Owner decision"). <!-- proven -->
- Work is picked by tier, not by issue number: labels `tier:1` (launch blocker), `tier:2` (before
  launch), `tier:3` (after launch), inside a tier the roadmap order. The inbox and an issue without
  a tier are never picked; bundles are ordinary work items. <!-- proven -->
- Cut before coding: an issue that touches more than one domain mechanism (for example a
  data model plus its validation rules plus an import) is split into issues of one mechanism each,
  one {{HOST_PR_ABBR}} per issue, before the first branch exists. <!-- proven -->
- Three rounds, then freeze: a round is a fresh review of the open {{HOST_PR_ABBR}} plus the push that
  fixes its findings; the implementer's own verifier pass before the {{HOST_PR_ABBR}} does not count.
  After the third review the scope is frozen: only findings in the blocker categories ({{BLOCKER_CATEGORIES}}), red CI, a failed
  user check and conflicts are still fixed; every other finding is recorded as above, not
  another round. At most five rounds: a finding that still needs a push after the
  fifth means no merge. Blind acceptance runs: at most two per {{HOST_PR_ABBR}}; a repeat checks only
  the changed steps. <!-- proven -->
- A session pushes only its own {{HOST_PR_ABBR}} branch and merges only the {{HOST_PR_ABBR}} it works on: after
  a fresh review by an agent that gets nothing from the session's context, on green CI, under the
  merge lock (Context economy). Codex and subagents never push or merge. Never push to
  `{{DEFAULT_BRANCH}}`. <!-- proven -->
- Progress is code, tests and a commit. Do not create state, contract, receipt, evidence, handoff,
  hash or audit files, do not build sequential repair or review chains that pass such files
  along, and write no new plan, log or status documents; decisions go into the issue, the
  {{HOST_PR_ABBR}} description, or an ADR under `docs/adr/` when they bind future work. <!-- proven -->

## Verification

- Follow the testing rule under `.claude/rules/` and [features/README.md](features/README.md).
- Every new or changed entry point keeps the hard invariants named above. Where the project
  has a sweep test over its entry points, that test fails until a new entry point is covered
  or exempted with a reason; without one, the {{HOST_PR_ABBR}} body lists the entry points
  touched and how each keeps the invariants. <!-- kit: name the sweep test or feature file once it exists, or delete the second sentence when the project has one -->
- UI work is never blind. Before the {{HOST_PR_ABBR}}, a change to anything a user sees is run
  for real and the {{HOST_PR_ABBR}} body carries the evidence: {{UI_EVIDENCE}}. Evidence is
  taken with synthetic data, never on production. <!-- proven; kit: pick the project's form. Web: opened in a real browser at desktop width and 360 px, before/after screenshots. Mobile app: simulator or emulator screenshots of each changed screen on a phone and a tablet size, light and dark. No user interface (server, library, CLI): the changed output itself, e.g. the API response or CLI output, before and after -->
- Done means a user can do it. An issue whose change a user notices carries a "User check"
  written before the change ([docs/acceptance/README.md](docs/acceptance/README.md)); the
  {{HOST_PR_ABBR}} is merged only after it passed on the {{HOST_PR_ABBR}}'s state: by a blind
  acceptance run that sees only the running product ({{ACCEPTANCE_ENV}}), or by the owner where no
  agent can go. The core journeys in [docs/acceptance/journeys.md](docs/acceptance/journeys.md) run blind at
  every milestone, and each has an automated twin in `features/journeys/` that runs in CI; a
  confirmed acceptance finding first fails as a step there, then gets fixed. Expected values come from the domain, never from the implementation. <!-- proven:
  a blind run of seven journeys found 14 defects the test suite did not; kit: name the environment
  of acceptance runs (local dev stack, portable install, staging), never production -->
- Run tests selectively, `make lint` before every push, and `make test` before a merge.

## Gates

| Command | Runs |
|---|---|
| `make lint` | {{LINT_CMD}} |
| `make test` | agent rules, then {{TEST_CMD}} (takes {{SUITE_DURATION}}) |
| `make test-agent-rules` | paired rule parity, `CLAUDE.md` symlink and Codex hook contracts (no DB) |
| `make docs-check` | relative links in all Markdown outside `docs/archive/` |
| `make hooks` | enables `.githooks/pre-commit` (lint when a `lint` target exists, docs link check) |

CI (`{{HOST_CI_FILE}}`) runs the same on every {{HOST_PR}}. A red job is fixed, not skipped.
Do not bypass the hook to land code. <!-- proven -->

<!-- kit: delete this paragraph when CI runs every gate. -->
Gates CI cannot run (<!-- e.g. the macOS build and `make test` on a Mac -->) run locally on
exactly the pushed commit; the {{HOST_PR_ABBR}} body names that commit and the result, and the
merging session repeats them on the commit it merges.

Update docs in the same {{HOST_PR_ABBR}} under the documentation contract (the docs rule under
`.claude/rules/`); a change to the look or copy of the user interface updates [DESIGN.md](DESIGN.md).
`docs/archive/` is legacy: do not read it or treat it as rules unless the user asks for a
specific question.

## Design rules

<!-- proven: these nine rules settled most review arguments; keep them, add project rules below. -->

1. One source of truth: when several places decide the same thing (mode, permission, status),
   they read one table or function.
2. No configuration keys for tuning numbers or lists; documented constants. A key only for a real
   on/off switch or a deployment fact (host, secret, path).
3. State that must survive a restart lives in the database, not in memory.
4. No field, parameter or interface without a reader in the same {{HOST_PR_ABBR}}.
5. Simple checks after the action beat predictive checks before it.
6. Classify errors by structured fields (codes, types), never by message text.
7. UI reports real outcomes only; no placeholder text, no "everything OK" when there is nothing
   to report. Follow [DESIGN.md](DESIGN.md) for components and formats.
8. Test representative long inputs and many rows.
9. Use what exists and works (libraries, modules, fixtures) before writing new mechanisms.

## Commits

`type(scope): lowercase imperative summary` (~70 chars), e.g. `feat(auth): …`, `fix(import): …`,
`test(bdd): …`, `docs(roadmap): …`, `ci: …`. Body: cause → change → tests. `Refs #N` or
`Closes #N` at the end. Push only the branch of the {{HOST_PR_ABBR}} you work on; never `{{DEFAULT_BRANCH}}`.

No attribution anywhere: no `Co-Authored-By` trailer for an assistant, no "Generated with …" line,
no mention of any AI assistant or agent as author, in commits, {{HOST_PR_ABBR}} descriptions,
issues, comments, code comments or docs. Naming a tool the repo supports (`.claude/rules`, the
Codex hook) is subject matter, not attribution. <!-- proven -->

## Context economy

One issue per session, cut to fit a 64k context. Read only the files the issue names; read large
files with `rg -n` and line ranges. <!-- proven -->

A session has exactly one task: one issue, from claim to merge. The next issue gets a new session
with an empty context, never the same chat and never a fork of it: every further task in the same
chat pays for the whole previous history on every step. As soon as its {{HOST_PR}} is open, a
session starts its successor for the next issue with the filled-in brief (or names it in its
report), then stays with its own {{HOST_PR_ABBR}} until it is merged or a fixed exit applies. It never
waits for the owner; a {{HOST_PR_ABBR}} that needs the owner is left with a "Not merged" comment, and
a maintainer session that the owner starts by hand finishes it, like any other {{HOST_PR_ABBR}} that no
session works on any more. Sessions do not message each other; what another session must know is
a comment on the issue or {{HOST_PR_ABBR}}; an issue a session gives up before its {{HOST_PR_ABBR}} gets a
comment starting with `Blocked:`, and no session takes it again before a later "Owner decision".
Merges are serialized by a short lock, `/tmp/{{PROJECT_NAME}}-merge.lock` (a `mkdir`, with the {{HOST_PR_ABBR}}
number and time in `info`): taken right before the branch is brought up to date with
`{{DEFAULT_BRANCH}}` and merged, released as soon as the merge is on `{{DEFAULT_BRANCH}}`, never held longer than
for that CI run, the local gate and the merge itself, and never longer than twice
{{SUITE_DURATION}} plus 30 minutes. A lock older than that, or one naming a merged or closed
{{HOST_PR_ABBR}} and older than 30 minutes, is a crash remnant; it is removed atomically (`mv` to a
private name, check `info`, then `rm -r`). An acceptance run on a shared environment holds
`/tmp/{{PROJECT_NAME}}-acceptance.lock` under the same rules. All sessions of a project run on one
machine, because these locks and the worktree claims only work there. A maintainer session's
review worktree is detached on `origin/<branch>`, because the issue worktree holds the branch.

## Worktrees and cleanup

Work in a git worktree outside the main checkout with a predictable name: `<repo>-issue-N` for an
issue, `<repo>-review-N` for a {{HOST_PR_ABBR}} under review. A worktree lives exactly as long as its
{{HOST_PR_ABBR}} and belongs to the issue or {{HOST_PR_ABBR}}, not to the session that created it: once that
is merged or closed, check that the tree is clean and that nothing runs there (after a merge
also that it landed on `{{DEFAULT_BRANCH}}`), then `git worktree remove <dir> && git branch -D <branch>`. The session that
merges removes the issue worktree of the merged {{HOST_PR_ABBR}} (a maintainer session also its review
worktree); every new session removes stale worktrees of its kind before it starts. An existing
`<repo>-issue-N` means issue N is being worked on.
<!-- proven: dozens of stale worktrees and many gigabytes accumulated without this rule -->

Every agent cleans up after itself. What a session creates, it removes when its task ends:

- git worktrees and local branches once their {{HOST_PR_ABBR}} is merged or closed (above);
- compose projects it started for acceptance or verifier runs, completely: containers, volumes,
  networks and the locally built images of this project (`docker compose -p <name> down -v
  --rmi local`), never the production instance and never the shared test database;
- scratch directories, briefs, logs, screenshots and reports, once their content is in the
  issue or {{HOST_PR_ABBR}};
- background processes it started (dev servers, watchers, browsers, test runs);
- lock files it holds (`/tmp/{{PROJECT_NAME}}-testdb.lock` and the like), only when no process of
  its own uses them any more.

Before starting, a session checks for leftovers (`git worktree list`, `docker compose ls`, its
scratch directory, its processes) and cleans up first. It removes only what it created itself,
with one exception: issue and review worktrees whose {{HOST_PR_ABBR}} is merged or closed (above).
Every other leftover of another session or of the owner is reported, not deleted.

## Databases and containers

<!-- kit: Keep exactly one of the two variants below and delete the other. Fill it from the
project's real setup. The rules of variant A are the ones that prevented data loss; keep their shape. -->

<!-- Variant A: the project has a database with migrations and a shared test database. -->

- The production instance ({{PRODUCTION_TABOOS}}) holds real data: never stop it with volume
  removal, never delete volumes, never test against that database. <!-- proven -->
- The test database is {{TEST_DB}}. Do not start a database of your own and do not add another
  compose file. Tests may truncate tables: never run two test processes against it at the same
  time; `make` targets that touch it acquire `/tmp/{{PROJECT_NAME}}-testdb.lock` themselves, a
  direct test run holds that lock in its shell until finished. <!-- proven -->
- Never change a committed migration; never empty a downgrade to make tests pass. A new
  revision becomes the release target everywhere (deployment target, deploy docs, upgrade
  tests) in the same {{HOST_PR_ABBR}}; one migration chain at a time, and when another
  {{HOST_PR_ABBR}} took the number first, renumber and say so. Production moves only by a
  release. <!-- proven -->

<!-- Variant B: the project has no database (server software, mobile app, library, CLI). -->

- There is no test database, no lock and no migration chain in this repository; `{{TEST_DB}}`
  is `none` and tests use disposable, isolated resources only.
- What is production here ({{PRODUCTION_TABOOS}}: deployed hosts, app-store or package
  releases, signing keys, user data, shared runners' secrets) is never touched from a
  {{HOST_PR_ABBR}} branch; it moves only by a release from `{{DEFAULT_BRANCH}}`.
- Shared external resources that tests need (a device, a simulator, a staging host) have one
  user at a time; name the rule here if the project has one.
