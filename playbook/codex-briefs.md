# Codex briefs

Codex works as well and as safely as its brief. `codex-task` gives it full rights, so the brief is the only barrier. This text sets out what every brief contains and why runs fail. Roles: [roles.md](roles.md), flow of a change: [workflow.md](workflow.md).

## Invocation

`codex-task DIR BRIEF_FILE [LOG]` runs `codex exec --ephemeral -C DIR`. DIR is a checkout or worktree of the branch (or, for the maintainer session, a detached worktree on `origin/<branch>`; the brief says so), BRIEF_FILE a file, LOG optional (default: a timestamped temp directory); the exit code is that of Codex. Brief and log live outside the repo and are never committed. In one worktree at most one Codex run goes at a time; parallel runs get worktrees of their own. A run takes minutes to hours; the orchestrator starts it in the background and afterwards reads the report and the diff, not the log.

## What every brief contains

A brief names the working directory and the branch as well as the number of the issue with its acceptance boxes verbatim; this list is the entire scope. It says explicitly "nothing unasked": no new fields, parameters, configuration keys, endpoints and no refactorings. It demands red first and names the test files in which the red tests come into being (scenario in `features/`, unit tests in the test file of the area).

Prohibited are `git push`, merge, any change to the main branch, production containers, volumes and databases, deleting volumes, changing committed migrations, creating status, receipt, handover or plan files, and attribution lines of any kind. Required are lint and the named, targeted tests as well as a report with the changes as `file:line` and the test evidence, without file excerpts. The brief fixes the language of the artifacts (code, comments, commits and docs in English, UI texts in the language of the software) and whether Codex commits. Usual is one commit on the branch in the format `type(scope): summary`, body: cause, change, tests, with `Refs #N`, and never a push.

## Pitfalls

**1. stdin.** `codex-task DIR -` reads the brief from stdin and does not get along with commands that need stdin themselves (loops with `read`, pipes). Care is needed even with a brief as a file: according to `codex exec --help`, a pipe on stdin is appended to the prompt as a `<stdin>` block as soon as a prompt argument is present. So pass the brief as a file and start the call with `</dev/null`. The wrapper passes the brief on as an argument, so the system's argument limit (ARG_MAX) limits its size: the brief stays short and points to files (issue text, notes in the scratchpad) instead of pasting contents.

**2. Sandbox.** The wrapper runs with the owner's configuration, so without a sandbox. A call of one's own, `codex exec -s workspace-write` (or a run without this configuration, say in another environment), writes only in the working directory. Then the lock `/tmp/<project>-testdb.lock` and caches outside the workspace fail or hang, installations fail. Remedy: use `codex-task`. Because Codex may then do everything, the prohibitions in the brief are not negotiable.

**3. Lock nesting.** Make targets that use the test database take the lock themselves. If you wrap them in a second lock acquisition, the inner `mkdir` waits forever for the outer one (deadlock). Direct test runs (for example pytest on one file), on the other hand, need the lock in the same shell. The brief says which case applies and forbids a lock of its own around make targets.

**4. Scope creep.** Codex likes to add options and fields, tidy up neighbouring code and "improve" docs. Remedy: the brief declares the acceptance list to be the entire scope, and the `verifier` searches the diff specifically for additions; additions are removed, not justified after the fact.

**5. Release target.** A new migration without raising the release target at all places breaks upgrade tests and deploys. If the base of a stack lands in the main branch first, the number also shifts. The brief names the migration rule, the files of the release target and whether the branch is stacked.

**6. Long runs.** The whole suite can take a long time (the project's duration is given as `{{SUITE_DURATION}}` in the session briefs). The brief names the targeted tests and says that Codex does not start the whole suite; it runs with the orchestrator or in CI, and CI decides.

**7. Honesty.** Codex reports red tests as red. The brief forbids loosening, deleting or skipping tests or adapting expectations just to make them green; if Codex considers a test wrong, it justifies that in the report. The orchestrator reads the diff of the test files itself.

**8. Brief sentences as standing rules.** Codex adopts wordings from the brief into files with standing rules: "this task authorizes you to edit AGENTS.md" becomes a sentence in AGENTS.md, "with explicit owner authorization the implementer pushes" an exception in CONTRIBUTING.md. That way a one-time permission for an onboarding or a session ends up as policy in the repo. Remedy: the brief says that permissions of the brief apply only to this run and must appear in no file; the `verifier` checks the diff of `AGENTS.md`, `CONTRIBUTING.md`, `DESIGN.md`, `.claude/rules/` and `.cursor/rules/` for sentences with one-time authorization ("this task authorizes", "with explicit owner authorization", "for this onboarding", "in this session", "you are allowed to … for this change") and the orchestrator strikes them.

## Skeleton

```text
Working directory: <DIR>, branch: <type/short-name>, goal: issue #<N>.
(Maintainer variant: working directory: <DIR>, detached HEAD on origin/<type/short-name>; commit on HEAD, do not switch branches, the orchestrator pushes.)
Read first: <paths of the files the issue names>; issue text: <path of the file in the scratchpad>.

Scope (complete, nothing beyond it, nothing unasked):
<acceptance boxes of #N, verbatim>

Approach: Red first. Write <scenario in features/<name>.feature> and <unit tests in <test file>>,
run them and confirm the intended failure. Then the smallest change that turns them green.
Follow the design rules in AGENTS.md. Do not loosen, delete or skip any test.

Testing: <make lint>, <targeted tests>. Do not start the whole suite.
<Shared test resources ({{LOCK_RULE}}): make targets take the lock themselves, do not add a lock of your own around them. / Direct runs: lock in the same shell. / None.>

Prohibited: git push, merge, changes to the main branch, production containers, volumes, databases,
deleting volumes, changing committed migrations, new status, handover or plan files,
attribution lines. Permissions in this brief apply only to this run and appear in no file.
<Migration: new revision <NNNN>, raise the release target in <files>.>

Language: code, comments, commits, docs in English; UI texts in <language of the software>.
Commit: one commit on the branch, `type(scope): summary`, body: cause, change, tests, `Refs #<N>`. No push.
Report: changes as file:line, test evidence (red before, green after), open risks; no file excerpts.
```

## After the run

The orchestrator reads the report, checks `git status` and the diff, runs the targeted tests itself and starts the `verifier` on the diff. Mechanical checks (running the tests, searching for prohibited patterns) it can give to a cheaper agent, the judgment it cannot.

The `verifier`'s checklist for every Codex diff:

- Additions that the acceptance list does not name (fields, parameters, options, endpoints, refactorings, files).
- Loosened, deleted or skipped tests, or adapted expectations.
- Sentences with one-time authorization in files with standing rules (pitfall 8).
- Status, handover, receipt or plan files and attribution lines.
- For migrations: number and release target at all places.
- Concrete failure scenarios against the change itself: input or state, wrong result, file:line.
