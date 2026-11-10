# Contributing to {{PROJECT_NAME}}

The software is {{SOFTWARE_LANGUAGE}}; everything about it — docs, issues, code comments,
commits — is English. Rules for coding agents, which apply to people too, are in
[AGENTS.md](AGENTS.md).

## Development environment

- Stack and prerequisites: {{STACK}}.
- Install the dependencies required by `{{TEST_CMD}}` and `{{LINT_CMD}}` using the stack's
  dependency manifests and lockfiles.
- Test database: {{TEST_DB}} (`none` when the project has no database). Never point tests at
  production data.
- Enable the commit gate once per clone: `make hooks`.

## Agent host setup

Root `AGENTS.md` is the common policy for every host; `CLAUDE.md` is a symlink to it (the
checkout must preserve symlinks, which Git does by default). Claude Code loads
`.claude/rules/*.md`; Cursor uses the paired `.cursor/rules/*.mdc`. A Claude rule without
`paths` is always on; otherwise its `paths` match the Cursor `globs`, with `alwaysApply: false`.
Keep bodies and descriptions equivalent and change both trees in the same commit (Rules Sync);
`make test-agent-rules` checks parity, the symlink and the hook.

For Codex, trust this checkout's project configuration and run **`/hooks` once per clone** to
review and approve both handlers in `.codex/hooks.json`. Review approval again after changing
the hook definition or script. Python 3 is required. This is separate from `make hooks`, which
installs the Git pre-commit gate.

The adapter reads Cursor rules directly: `SessionStart` attaches always-on rules and
`PreToolUse` on `apply_patch`, `Edit` or `Write` attaches rules matching the edited paths.
Use quoted block lists for `paths` and `globs`; the adapter supports this repository's flat
frontmatter convention, not arbitrary YAML. It is stateless, so matching rules attach on each
edit. Malformed input or rules fail open and never block work.
Rules provide context; AGENTS.md retains the safety baseline and tests/CI check parity.

## Running the tests

`make help` lists every target.

- **`make test`** — agent-rule contracts, then the project test suite (`{{TEST_CMD}}`, takes
  {{SUITE_DURATION}}).
- **`make lint`** — the project static checks (`{{LINT_CMD}}`).
- **`make docs-check`** — relative links and images in tracked Markdown outside `docs/archive/`.
- **`make test-agent-rules`** — paired bodies/activation, the `CLAUDE.md` symlink and Codex hook
  contracts; Python stdlib only, no database. Run after changing rules or the adapter.

Projects with a shared test database: it has a single writer. Never run two suites or a
resetting suite and a development stack against it at once. For a direct test run or
development stack, acquire the lock in that same shell and stop all database users before
releasing it:

```sh
until mkdir /tmp/{{PROJECT_NAME}}-testdb.lock 2>/dev/null; do sleep 10; done
trap 'rmdir /tmp/{{PROJECT_NAME}}-testdb.lock' EXIT
{{TEST_CMD}}
```

When a DB-bound Makefile target owns `TESTDB_LOCK`, call it without acquiring the lock again.
Projects with no test database delete this section and the `TESTDB_LOCK` block in the Makefile.

The pre-commit hook (`.githooks/pre-commit` → `scripts/checks.sh`) always checks Markdown
links and also runs `make -s lint` when the Makefile defines a `lint` target.

## Making a change

1. **Start from an issue.** Every change has one, written as a spec with
   `{{HOST_ISSUE_TEMPLATE}}`: What, Why it happens (file references checked against `{{DEFAULT_BRANCH}}`),
   Proposed change, Acceptance, Out of scope. Order: [docs/roadmap.md](docs/roadmap.md).
   Read it with `{{HOST_ISSUE_VIEW}}`; the host CLI `{{HOST_CLI}}` is authenticated by a person,
   never by an agent.
2. **Branch** from `{{DEFAULT_BRANCH}}`: `<type>/<short-name>`, e.g. `feat/signup`, `fix/import-dedup`.
   One issue = one branch = one {{HOST_PR}}.
3. **Red first.** Write the scenario (happy path, `features/`, where Gherkin fits) and the
   unit tests (edge and error cases, in the area's existing test file) and see them fail.
4. **Implement** the smallest change that turns them green. Follow the design rules in
   [AGENTS.md](AGENTS.md).
5. **Docs in the same {{HOST_PR_ABBR}}**, per the documentation contract in
   [AGENTS.md](AGENTS.md). [DESIGN.md](DESIGN.md) is the design contract: new screens follow it,
   and changes to the look or copy update it in the same {{HOST_PR_ABBR}}.
6. `make lint` green before every push; `make test` (the whole suite) before the merge — CI
   runs it on every {{HOST_PR_ABBR}}. A gate CI cannot run (for example a build that needs
   macOS) runs locally on the pushed commit, and the {{HOST_PR_ABBR}} body names that commit
   and the result. A change is merged by the session that made it, or by a maintainer
   session for a {{HOST_PR_ABBR}} no session works on any more, after a fresh review and on
   green CI; the implementers a session delegates to never push or merge.

## Opening a {{HOST_PR}}

Commit subjects follow `type(scope): lowercase imperative summary` — one lower-case line,
with the area as scope. The body says cause → change → tests and ends with `Refs #N` or
`Closes #N`. `Closes #N` only when every acceptance box of the issue is done; otherwise use
`Refs #N`.

The {{HOST_PR_ABBR}} description states what the change is for, which scenarios and tests
were added (and that they were red first), how `make test` and `make lint` went, and carries
the UI evidence ({{UI_EVIDENCE}}) when anything a user sees changed. CI (`{{HOST_CI_FILE}}`)
must be green.

## Where things live

| Path | Contents |
| --- | --- |
| `docs/` | Architecture, ADRs, operations, roadmap and feature status; add project-specific pages here. |
| `features/` | User-visible executable specifications, when the project has API or UI journeys. |
| `scripts/` | Repository checks and project-specific development commands. |
| `.claude/rules/` + `.cursor/rules/` | Paired area rules; generate and synchronise them with Rules Sync. |
| `.codex/` | Hook configuration and the adapter that attaches matching rules as context. |
