# Roles and models

A project with the kit has one human and several kinds of workers. The split follows one principle: the most expensive model judges and coordinates, cheaper models and Codex do the bulk, and only what a fresh reviewer without knowledge of the implementation could not refute is merged. The flow itself is in [workflow.md](workflow.md).

## The owner

The owner is the human. The owner maintains the roadmap and milestones, makes the decisions that no agent may make (product scope, hard invariants, release commitments) and answers questions as a comment "Owner decision". The owner does not check every feature, but accepts each milestone: the owner classifies the findings of the acceptance agent, checks the user checks that only a human can check and clicks through one or two spot checks personally, altogether at most half an hour ([acceptance.md](acceptance.md)). Merging is done only by the session that carries the PR; the owner is never asked to run anything that an agent can run itself. There is one exception: sign-in and credentials. `gh auth login`, `glab auth login`, tokens and keys belong to the owner, agents never enter credentials. What only the owner can do (DNS, server settings, platform switches) appears as a note "For the owner" in the PR (GitLab: MR) and blocks nothing.

## The orchestrator

In every session the chat model at maximum reasoning effort (on the owner's Mac: Fable) is the orchestrator. It plans, decomposes, writes the briefs, reads the reports, checks the diff and integrates. It does not write bulk work itself, because its tokens are the most expensive in the system and belong to judgment. A small change in a known file it makes directly, because a brief would cost more than the change. The chat model never runs as a subagent.

## The Codex worker

`codex-task DIR BRIEF_FILE [LOG]` starts Codex without follow-up questions in directory DIR (`codex exec --ephemeral -C DIR`) with the owner's configuration: full filesystem and network access, no approvals. Codex writes code, tests and docs according to the brief and commits only if the brief demands it. Because technically nothing holds it back, the brief is the only barrier: it must state scope and prohibitions, above all push, merge, production and production database. What a brief must contain and why runs fail is in [codex-briefs.md](codex-briefs.md).

## Subagents

The orchestrator delegates downward in model tier and upward in effort: a cheaper model at high reasoning effort usually reaches the result of a more expensive one at standard effort. The predefined agents set model and effort themselves.

| Agent | Model, effort | Task |
|---|---|---|
| `scout` | haiku | search, inventory, extraction, scanning logs, boilerplate; mechanical and without judgment |
| `builder` | sonnet, xhigh | well-specified implementation, tests, docs, focused research; the default worker |
| `verifier` | opus, high | adversarial review of a diff; verdict CONFIRMED or REFUTED with a concrete failure scenario, changes nothing itself |
| `architect` | opus, xhigh | design, difficult debugging, security review; may use `scout` and `builder` |

Delegation goes at most two levels deep below the chat: orchestrator, then a sub-orchestrator (`architect`), then leaf workers that delegate nothing further. The depth is not counted automatically; every orchestrator writes the level and the remaining budget into the child's prompt. These definitions are not in the project but in the owner's personal configuration (`~/.claude/CLAUDE.md`, `~/.claude/agents/`); the kit only describes them.

## The acceptance agent

The acceptance agent checks the running product from a user's point of view and is blind: it gets the app, the user check or the core journeys and the files a user would have, but no code, no diff, no PR and no issue discussion, because whoever knows the implementation confirms it. It operates a browser (Playwright) like a human, books nothing by script and reports per item passed, failed or not checkable, with findings and screenshots. Before every merge with a user check, the session that merges the PR starts it; the owner starts the run per milestone over all core journeys. It changes nothing, neither the code nor the environment. Model: Sonnet at high effort. Brief and flow are in [acceptance.md](acceptance.md).

## The local model

A local model (Qwen) on the owner's network relieves the orchestrator of reading large texts: summaries and factual questions over documents, logs or diffs from about 40 KB. It is slow and serves one request after the other, it writes no code, does not judge and does not review. It never gets secrets, `.env` files or credentials. Its answers are hints and are spot-checked against the source.

## Helper tools for the start

Two skills from EvilFreelancer's rpa-skills (MIT, installed under `~/.claude/skills/`) help with setup. `/rpa-init` warms up a session on a repository: read code, docs and tests, set up the environment as the project intends, run tests, short report. `/rpa-gen-rules` generates, checks and reconciles project rules (root `AGENTS.md`, `.cursor/rules`, `.claude/rules`) when the rule trees drift apart. The flow in a new project is in [onboarding.md](../onboarding.md).

## Two roles, one session per task

The issue session takes an issue from claiming it to the merge: it implements it, opens the PR, starts the session for the next issue, has the PR checked by a `verifier` with fresh context, fixes the findings and merges it itself ([issue-session.md](session-briefs/issue-session.md)). Whoever writes does not do the checking alone: the `verifier` gets nothing from the issue session's context except path and numbers and reads diff, issue and CI itself. The maintainer session is the special case for a PR that no session works on any more; the owner starts it by hand, it checks and merges under the same rules and starts no successor ([maintainer-session.md](session-briefs/maintainer-session.md)). Every issue gets a session of its own with an empty context; a session starts its successor as soon as its PR is open, instead of continuing in the same chat ([workflow.md](workflow.md), "One session, one task"). Several issue sessions may run in parallel as long as their issues do not touch the same files; a shared test database serialises them via the lock, projects with isolated test resources do not need that. The merges run one after the other under a short merge lock that encloses only updating and merging.

| Role | Commit | Push | Open PR | Merge |
|---|---|---|---|---|
| Issue session (one per issue) | yes | own branch only, after the PR one push per round | yes | its own PR, after fresh review, with green CI, under the merge lock |
| Maintainer session (special case, started by the owner) | on the PR branch (fixes, conflict resolution) | PR branch only, one push per round | rarely | the PR it took over, under the same rules |
| Codex worker | only per brief | never | never | never |
| Subagents | no | never | never | never |
| Acceptance agent | no | never | never | never |

Nobody pushes to the main branch directly. The owner does not merge personally; the owner gives priorities and decisions as a comment on the issue or PR and starts a maintainer session when a PR without a running session is to be finished.
