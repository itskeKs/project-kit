---
name: kit
description: >
  Run when the user invokes /kit. Works on the project whose checkout the chat runs in: /kit status
  shows its open PRs, issues, worktrees and locks and what needs the owner; /kit next, /kit issue <N>
  and /kit pr <N> start a detached issue or maintainer session for it; /kit bug <text> and
  /kit feat <text> draft the issue from a sentence, create it after the owner's OK and start its
  session; /kit triage starts the detached session that empties the project's inbox of recorded
  findings. Outside a project checkout the project is named, and /kit status covers all projects.
  /kit init registers a project.
---

# /kit — start and oversee this project's session chain

The kit lives at `~/Developer/project-kit` (KIT below). A project is registered by a file
`~/.config/project-kit/briefs/<project>.env` whose `REPO_PATH` is its main checkout. **The project
is the one whose checkout contains the current working directory**; both scripts below work that
out themselves when no project is given. In a workspace folder above several checkouts (e.g.
`~/Developer/acme`), `/kit status` covers exactly those projects, and a command that starts a
session needs `<project>`: a unique part of the file name (e.g. `shop`) or a path. Elsewhere (the
kit, a launcher chat) `/kit status` covers all projects and every other command needs `<project>`.
Never ask the user which project they mean while the chat is inside a checkout.

Everything you write into files, issues, PRs or briefs is English; answer the user in the
language they use. Keep this chat small: run the scripts, start sessions, report in a few lines.
Never read a brief into the chat except to pass it as a prompt, never paste script output
verbatim, never do the project work here.

## `/kit` or `/kit status`

1. Run `python3 KIT/playbook/session-briefs/kit-status.py` (inside a checkout it reports that
   project only; elsewhere all projects, or `kit-status.py <project>`; `--all` forces all).
2. Report "Needs you" first, one line per item with its URL (blocked issues and open owner
   questions, PRs marked "Not merged" with the reason, parked PRs, stale locks, orphan worktrees,
   an ended chain). Then open PRs with CI state and review marker, the milestone's issues with
   their flags, the intake numbers (issues created and closed in seven days, open inbox lines, open
   bundles, open items per tier; "not set up" where the project has no inbox or labels yet),
   worktrees and locks. Omit empty sections. A project with `MERGE_BY=maintainer`
   (someone else merges; `merge_by` in the JSON) lists only our own PRs, as "Waiting for maintainer"
   with CI state, review decision and "taken over by maintainer" where others committed to one, and
   only the owner's issues: report those PRs as waiting, never as a running chain.
3. If the user wants to know which sessions are running, call `list_sessions` and match titles
   starting with "Issue", "Maintainer" or names `issue-*`/`maint-*`; do not guess.
4. End with the one or two commands that make sense next (e.g. `/kit next`, `/kit pr <N>` for a
   "Not merged" PR whose reason is gone, `/kit triage` when the inbox holds 15 or more open lines).

## `/kit issue <N> [--milestone T] [--handover "after merge"|"after PR"]`

1. Run `python3 KIT/playbook/session-briefs/fill-brief.py issue <N> [options] --out <scratchpad>/kit-brief.md`
   (outside a checkout: `issue <project> <N>`). If it exits non-zero, show its one-line reason
   (usually TODO values in the project file, or no registered project here) and stop.
2. `REPO_PATH`: the checkout you are in; outside one, `grep '^REPO_PATH=' ~/.config/project-kit/briefs/<project>.env`.
3. Start the session with `start_session`: `initiation: "user_asked"`, `context: "fresh"`,
   `use_worktree: false`, `cwd: <REPO_PATH>` (omit `cwd` when the chat already runs there),
   `prompt`: the full content of the brief file, `background`: "Issue session for <project>
   issue #<N>, started with /kit; the brief is the full prompt.", `name`: `issue-<N>`,
   `title`: "<project> #<N>" (the session renames itself to "<project> #<N>: <issue title>" once it
   has read the issue). Do not pass a model or effort.
4. Right after the start, call `detach_session` with the new session's id, so this chat is not
   woken by its turns (the brief also detaches itself; doing both is fine).
5. Delete the scratch brief file. Reply in one or two lines: the session link
   (`[Issue #<N>](#<sessionId>)`), that it runs on its own, and that `/kit status` shows progress.

The brief follows the project's `MERGE_BY`. With `maintainer` the session hands its PR over to the
maintainer instead of merging it and posts no comment on the issue or the PR.

## `/kit next`

1. Run `python3 KIT/playbook/session-briefs/kit-status.py --json` (plus `<project>` outside a checkout).
2. If a chain is already running (an issue in progress without PR, or an open PR whose newest
   marker is neither "Not merged" nor "Merged"), say so with the number and stop: one chain per
   project unless the user asks for a parallel one. With `MERGE_BY=maintainer` only an issue in
   progress without PR is a running chain: our open PRs wait for the maintainer.
3. Pick the first open issue that has no PR, is not blocked, has no open owner question and is
   not in progress, by tier and order, not by issue number: ignore the issue with the project's
   inbox label (`INBOX_LABEL`, default `inbox`) and every issue without a tier label
   (`TIER_1_LABEL`, `TIER_2_LABEL`, `TIER_3_LABEL`, defaults `tier:1`, `tier:2`, `tier:3`; read them
   from the project file, the defaults apply where it does not name them); sort the rest by tier
   (`tier:1` first), inside a tier by the position in the lists of `docs/roadmap.md` of the
   checkout when the project file names a milestone (read only the roadmap lines that list that
   milestone's issues; issues the roadmap does not list come after those), then by issue number.
   Issues with the bundle label (`BUNDLE_LABEL`, default `bundle`) are ordinary work items. If none
   qualifies, say what blocks the candidates (owner questions, PRs) and how many open issues have
   no tier label (they are never picked), and stop. With `MERGE_BY=maintainer` the issue list is
   already limited to issues assigned to the owner, or opened by the owner without an assignee;
   never pick another person's issue, and the tier labels do not apply: the order is the roadmap
   order of the milestone, else the issue number.
4. Continue as `/kit issue <N>` with the milestone from the project file.

## `/kit pr <N>`

Same as `/kit issue`, with `fill-brief.py maintainer <N>`, `name: maint-<N>`, title
"<project> #<issue>: review PR <N>" where `<issue>` is the issue the PR closes or references
(`gh pr view <N> --json body` / `glab mr view <N>`: `Closes #` or `Refs #`; without one, use
"<project>: review PR <N>"), and background "Maintainer session for
<project> PR <N>, started with /kit for a PR no session works on any more." Start it only for a PR
that carries a "Not merged" comment, has no live session, or that the user names explicitly. With
`MERGE_BY=maintainer` the brief is the one-round PR session (fixes, merges `origin/<main>` into the
branch, pushes once, never merges, posts nothing): start it for a PR under "Waiting for maintainer"
with red CI, conflicts or review comments to answer, and never for one marked "taken over by
maintainer": say that it is hands off instead.

## `/kit triage`

Starts the session that turns the findings recorded on the project's inbox issue into issues,
bundles and dispositions. It changes no code. Start it when the owner asks, when `/kit status`
shows 15 or more open inbox lines, or when five PRs were merged since the last "Triage run" comment
on the inbox issue.

1. If `kit-status.py` (as in `/kit status`) shows a lock `triage.lock` for the project that is not
   stale, a triage run is active: say so and stop.
2. Run `python3 KIT/playbook/session-briefs/fill-brief.py triage --out <scratchpad>/kit-brief.md`
   (outside a checkout: `triage <project>`). If it exits non-zero, show its one-line reason (no
   `INBOX_ISSUE` in the project file, `MERGE_BY=maintainer`, TODO values) and stop.
3. Start it like `/kit issue`, with `name`: `triage`, `title`: "<project>: triage", `background`:
   "Triage session for <project>, started with /kit to empty the inbox issue; it changes no code and
   writes to the issue tracker only; the brief is the full prompt." and `model`: a cheap model id
   (Sonnet or Haiku; the work is reading and writing tracker text), no `effort`.
4. Detach it, delete the scratch brief file, reply in one or two lines with the session link.

## `/kit bug <description>` and `/kit feat <description>`

The owner describes a defect or a capability in a sentence or two; you turn it into an issue that
follows the project's template and rules, get the owner's OK, create it, and start its session.

1. Facts: `REPO`, `HOST_CLI`, `HOST_ISSUE_TEMPLATE`, `MAIN_BRANCH`, `MILESTONE` from the project
   file; `REPO_PATH` is the checkout.
2. Draft with a `builder` subagent (say "You are at delegation level 1 of max 2 — do not spawn
   subagents"), so this chat stays small. Its brief: the owner's words verbatim; the template file
   at `REPO_PATH/HOST_ISSUE_TEMPLATE`; the rules "Work comes from issues" and "Cut before coding" in
   `REPO_PATH/AGENTS.md`; `docs/acceptance/README.md` for the user check. It reads the code only as
   far as the draft needs (`rg -n`, line ranges) and returns, in English: a title (imperative, under
   70 characters) and the body in the template's sections. For `bug`: "Why it happens" is
   mandatory, with file references checked against `origin/<MAIN_BRANCH>`, and the acceptance list
   names the regression test that is red before the fix. For `feat`: leave "Why it happens" out.
   "User check" has concrete values worked out from the domain, never from the implementation,
   and "Checked by: agent" unless an agent cannot go there (real device, mail, payment) — then
   `owner`. Acceptance keeps only the boxes that apply. "Out of scope" names what is deliberately
   left out. If the description bundles more than one mechanism, the builder returns one draft per
   mechanism, in build order. It may add at most two questions where the owner's words leave a
   fact open that the draft cannot do without.
3. Show the owner the title and the full body (and the builder's questions, if any) and wait for
   the OK or corrections. Do not create anything before the OK; apply corrections yourself.
4. Create it: GitHub `gh issue create -R REPO --title "<title>" --body-file <scratchpad>/kit-issue.md --label task [--milestone "<MILESTONE>"]`;
   GitLab `glab issue create -R REPO -t "<title>" -F <scratchpad>/kit-issue.md -l task [-m "<MILESTONE>"]`
   (if `-F` is not accepted, pass `-d "$(cat <file>)"`). Take the number from the output, delete
   the scratch file, and post the issue link.
5. Ask in one line whether to start it now; on yes, continue as `/kit issue <N>` (one chain per
   project: if a chain is running, say so and leave the issue for `/kit next`). With several
   drafts, create all, start only the first.

## `/kit init [<repo-path>]`

Run `python3 KIT/playbook/session-briefs/fill-brief.py init <repo-path>` (default: the checkout
you are in) and show the TODO keys it reports with their meaning (the project file explains each
key in a comment). Do not invent values; ask the user for the ones you cannot derive, write them
into the file, and run `fill-brief.py check`.

## Rules

- This chat starts sessions and drafts issues; it never implements, reviews, merges or triages itself. With
  `MERGE_BY=maintainer` no session merges either, and none comments on the maintainer's issues
  or PRs.
- An issue is created only after the owner has seen the full draft and said yes.
- One chain per project at a time unless the user asks for a parallel chain (`--handover "after PR"`).
- Never start a maintainer session for a PR whose issue session is still running.
- Never remove locks or worktrees from here; report them and let the user decide.
