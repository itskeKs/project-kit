# Roadmap

**Goal:** {{PROJECT_ONE_LINER}} The milestones below order the work toward that goal.
What exists today: [feature-status.md](feature-status.md).

## How work is tracked

- Every piece of work is a {{HOST}} issue written as a spec (`{{HOST_ISSUE_TEMPLATE}}`):
  What → Why → Proposed change → User check → Acceptance → Out of scope. One issue, one branch, one
  {{HOST_PR_ABBR}}; `Closes #N` only when every acceptance box is done, otherwise `Refs #N`.
- Order comes from milestones (below), inside a milestone from the tier label of the issue (`tier:1` before
  `tier:2` before `tier:3`), and inside a tier from the list order here.
- Read one issue with `{{HOST_ISSUE_VIEW}}`.

## Milestones

### 1 Foundation: gates and specs

1. Quality gates — Makefile, pre-commit hook, lint and CI.
2. Executable specs — a pilot for the core user journey, where Gherkin fits.
3. Documentation skeleton — architecture, roadmap, feature status, ADRs and operations.
4. Area-scoped agent rules with paired bodies and hook contracts.
5. DESIGN.md — the design contract.

### 2 <next milestone>

<!-- Replace this example heading and add the milestone's ordered issues. -->

## Open decisions

Only the owner decides product scope, hard invariants and release commitments. List each
open decision here with its issue and the milestone it affects.
