---
name: kit
description: >-
  Use when the user invokes /kit or $kit, including status, next, issue, pr, bug,
  feat, or init, or explicitly asks to use their local Project Kit in Codex.
---

# Project Kit: Codex supplement

Read the original skill at
`~/Developer/project-kit/playbook/skills/kit/SKILL.md` and follow its
command workflows. This file adds only the Codex host integration. Do not modify,
copy, or replace the original skill, the shared scripts, the briefs, or the Claude
symlink. The original remains the source of truth for command meanings and
project selection; the additions below apply only in Codex. Installing this
supplement does not invoke a kit command or authorize project work.

Use the existing project registry at `~/.config/project-kit/briefs/` and the
scripts under `~/Developer/project-kit/playbook/session-briefs/`. Run
them with `env -u USER python3`, in the user's actual checkout or workspace
directory. For example, `/kit status` runs:

```sh
env -u USER python3 "$HOME"/Developer/project-kit/playbook/session-briefs/kit-status.py
```

Keep the original's language and reporting conventions. Surface script errors,
partial results, and capped issue lists; do not describe them as complete.

## Codex task integration

Discover the current `mcp__codex_app__*` tool schemas before using them. Tool
availability and schemas are authoritative; the Claude tool names in the source
are not Codex tools. The mapping:

| Claude (desktop app)          | Codex                                                      |
|-------------------------------|------------------------------------------------------------|
| `start_session`               | `create_thread` (a peer task; non-blocking)                |
| `detach_session`              | nothing; a peer task never wakes its starter               |
| `set_session_title`           | the title at creation, plus the native rename if available |
| `bind_pr`                     | none; sessions are not archived automatically             |
| `list_sessions`               | `list_threads`, then `read_thread` for a candidate         |

- **List sessions:** match the project path and the issue/PR, not just a number
  in a title. Paginate history when needed; an absent entry on one page is not
  proof of no task. Report running/idle status only when returned explicitly.
  Codex cannot establish the state of Claude sessions; preserve that uncertainty
  and use the original worktree/lock checks as well. Never infer that a foreign
  worktree is abandoned.
- **Start a session:** `/kit issue N`, `/kit pr N`, and `/kit next` request one new
  task, after the original eligibility and duplicate checks. Use `list_projects`,
  match the registered `REPO_PATH` on the current host exactly, and use its
  returned project ID with `create_thread`. Do not choose a similarly named
  project or silently switch host. If the project or tool is unavailable, explain
  the missing prerequisite; do not launch a CLI substitute.
- **Task arguments:** set `target` to
  `{type: "project", projectId: <returned ID>, environment: {type: "local"}}` and
  pass the prepared prompt below. Omit `model` and `thinking` unless the user
  explicitly requested them. Do not use a fork or a collaboration subagent as the
  independent issue/maintainer task.
- **Title:** exactly the original's convention with `PROJECT_NAME` from the project
  file, verbatim: `<PROJECT_NAME> #<N>` at creation, and the task renames itself to
  `<PROJECT_NAME> #<N>: <issue title>` (issue) or
  `<PROJECT_NAME> #<issue>: review <PR_ABBR> <N>` (maintainer) once it has read the
  issue. Never substitute the product's marketing name, a slogan or a summary of
  the work; `kit-status.py` and the owner match sessions by this prefix.
- **Prepare the prompt:** generate the original brief with `fill-brief.py` as
  documented, using a unique task-owned temporary directory for `--out`. Put the
  user's actual request first, then the full "Codex execution rules" section
  below, then the generated brief under the heading "Session brief". Do not
  invent authorization. Read the brief only to compose that prompt. Remove the
  temporary brief and directory after the call, including on failure.
- **Links:** return only the task identifier/link actually supplied by the tool;
  do not invent a `#<sessionId>` URL or treat a pending `clientThreadId` as
  `threadId`.
- **Draft an issue:** follow the original full-draft approval and separate start
  steps. Where it names a Claude `builder`, write the draft directly or use the
  applicable Codex orchestration policy; read the local orchestration guide
  before delegating and do not enable `subagent-driven-development`. `/kit init`
  uses the shared script unchanged.

## Codex execution rules

This section applies to a Codex task started by this skill. It translates the
brief's Claude mechanics into Codex; it does not change the kit's flow, which is
the same in both hosts: one session takes an issue from claiming it to the merge
and then starts its successor as `<HANDOVER>` says.

1. The target repository's current `AGENTS.md` and the brief apply, in that
   order. Preserve the user's actual request, scope, and the authorization
   boundaries the brief itself draws (owner user checks, "Owner decision", stack
   handling, the merge lock, the review-round limit, the local gates). Do not
   change standing project rules to fit a brief, and do not add approval steps
   the brief does not have: the merge of the task's own PR after the fresh review,
   green CI and the gates is authorized by the brief, no chat confirmation is
   needed for it. Ask the owner only where the brief asks. A brief for a project
   with `MERGE_BY=maintainer` has no merge at all: it hands the PR over to the
   maintainer and posts no comment on any issue or PR.
2. Handover: follow `<HANDOVER>` exactly as a Claude session would. At the point
   the brief names (after the PR, or after the merge), start the successor with
   `create_thread` in the same project, the same title convention and a brief
   generated with `fill-brief.py issue <next>` as described above, at most one
   successor per task. If no issue qualifies, end the chain as the brief says.
3. Codex is the session. Where the brief delegates implementation to Codex
   (`codex-task`), implement directly in this task. Where it requires an agent
   with fresh context that sees only listed inputs (the `verifier` review of the
   PR, the blind acceptance run), use a separate Codex thread or subagent that
   receives exactly those inputs and nothing from this task's history. If no
   such tool is available, do the review in this task and state in the PR comment
   (in a `MERGE_BY=maintainer` brief: in the PR description) that it was not independent; never claim an independent review you did not
   run. Never re-enable disabled skills.
4. Tool mapping: `start_session` is `create_thread`; `detach_session` has no
   counterpart and is skipped; `set_session_title` is the native rename, or the
   title was set at creation; `bind_pr` has no counterpart, so the final report
   says that this session is not archived automatically; `list_sessions` is
   `list_threads`. None of these requires switching models or starting a nested
   CLI.
5. Worktree: the task's own worktree replaces the brief's worktree claim; branch
   name, commits, PR and everything else follow the brief. Clean up only
   resources this task created and owns. Preserve the owner's changes, foreign
   worktrees, branches and locks, production, and shared test services. Never
   follow a generic forced worktree removal or compose cleanup from the brief when
   ownership or project authorization is missing. Honor project-specific
   container, database, lock, and worktree rules. Remove disposable task briefs
   and stop task-started processes before the report; report cleanup briefly.
6. Keep `USER` excluded from child processes. Use supported credential stores;
   never copy or scrape browser/app sessions. Report unsupported or unverified
   operations honestly, including a task launch that has not completed setup.
