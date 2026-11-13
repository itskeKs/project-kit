# project-kit

You have a software project. You want coding agents to do the work: pick up an issue, implement it,
test it, get it reviewed, merge it, and move on to the next one. You want to decide, not to babysit.

project-kit gives your repository the files and the routine for that. It works with Claude Code or
with Codex, on GitHub or GitLab.

## What it does

- **Rules for the agents in your repo.** A working contract (`AGENTS.md`), design rules, a docs
  skeleton, issue and pull request templates, CI, a protected main branch.
- **One issue, one session.** Every issue is worked by its own agent session, from claiming it to
  the merge. A fresh agent reviews the change. Findings inside the issue's scope are fixed in rounds.
- **Acceptance from the user's side.** Every issue says what a user does and sees afterwards. An
  agent that never sees the code tries exactly that before the merge. Per milestone, you accept.
- **A backlog that does not flood.** What a review or an acceptance run finds outside the issue's
  scope is written down once, as one line, instead of becoming an issue each time. A triage run
  turns the collected lines into work. See [Findings, bundles and the inbox](#findings-bundles-and-the-inbox).
- **Work by importance.** Every issue carries a tier: launch blocker, before launch, after launch.
  Sessions take the most urgent free issue, not the lowest number. An issue without a tier is never
  picked.
- **A chain that keeps going.** When a session has opened its pull request, it starts the session
  for the next issue. Several chains can run in parallel.
- **Repositories that someone else merges.** With `MERGE_BY=maintainer` in the project file, a
  session hands its pull request over to the maintainer instead of merging it, posts no comment on
  their issues or pull requests, and stops when the maintainer pushes to it.
- **`/kit` in Claude Code, `$kit` in Codex.** `/kit status` shows what is running and what waits for
  you, how many issues were opened and closed in the last seven days, how full the inbox is and how
  many issues are open per tier. `/kit next` starts the next issue by tier. `/kit bug <text>` turns
  a sentence into an issue and starts its session. `/kit triage` empties the inbox. The sessions
  themselves run as Claude Code sessions or as Codex threads.

## Findings, bundles and the inbox

Reviews and acceptance runs see more than the issue they belong to: a misspelled label two screens
away, a table that is cut off on a phone, an error message in the wrong language. If each of these
becomes an issue the moment it is seen, the backlog grows faster than it is worked, and most of it
is the same defect at another place. The kit therefore separates writing a finding down from filing
an issue.

- **Every confirmed finding is recorded once.** The session that confirmed it adds one line with the
  place, what was seen and the commit:
  ```text
  - [ ] <class or ?> | <screen or file:line> | <what was seen> | <SHA> | PR #<n>
  ```
  The line goes to the first place that fits: the **bundle** of its class (one open issue per kind
  of defect, label `bundle`), the open issue that already covers it, or the **inbox** (one standing
  issue per project, label `inbox`).
- **An issue is filed at once only when it cannot wait:** a finding in one of the project's blocker
  categories, a security or data-loss problem, or a step of a core journey a user cannot finish.
  Beyond that a session files at most one new issue per pull request.
- **A triage run empties the inbox.** `/kit status` suggests it when the inbox holds 15 or more open
  lines; five merged pull requests since the last run also make it due. It runs on a cheap model and
  changes no code. Every line gets a recorded result and is ticked: a new issue, appended to a
  bundle (three or more lines of one kind open a new bundle), covered by an existing issue, or
  dismissed with a reason. A line in a blocker category is never dismissed. Nothing disappears
  without a trace.
- **A class is closed at its cause.** A bundle is done when the places are fixed and a guard (a
  test, a lint rule, a check) fails as soon as the defect comes back.
- **Questions are asked once.** Before a session puts a question to you, it reads the decisions you
  already recorded and answers on the issue what they settle.

A pull request's merge comment names what was recorded where, so you can follow every finding from
the run that saw it to the issue that fixes it.

## What you do

You write the roadmap and the issues (or let `/kit bug` and `/kit feat` draft them) and give each
issue its tier. You answer the questions only you can answer, as a comment "Owner decision". You
accept each milestone. You log in to GitHub or GitLab once; agents never handle credentials.
Everything else an agent can do, an agent does.

## What you need

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) or the
  [Codex](https://github.com/openai/codex) app. Both run the whole process; pick one or use both.
- The `gh` or `glab` CLI, logged in.
- The skills `/rpa-init` and `/rpa-gen-rules` from
  [EvilFreelancer/rpa-skills](https://github.com/EvilFreelancer/rpa-skills). They read your project
  and generate its rules. In Claude Code:
  ```text
  /plugin marketplace add EvilFreelancer/rpa-skills
  /plugin install rpa-init@rpa-skills
  /plugin install rpa-gen-rules@rpa-skills
  ```
  In Codex: `codex plugin marketplace add EvilFreelancer/rpa-skills`, then install both from
  `/plugins`.
- With Claude Code only: the agents and the orchestration policy the sessions rely on. The kit
  ships them; after cloning (below), run `./install-global.sh` in the kit directory once. It never
  overwrites a file. Codex needs none of this; it brings its own orchestration.
- With Codex: the kit's hook feeds your project rules into every Codex session. Approve it once per
  clone with `/hooks`.

## Getting started

1. Clone the kit.
   ```bash
   git clone git@github.com:itskeKs/project-kit.git ~/Developer/project-kit
   ```
2. Copy the files into your repository (nothing existing is overwritten):
   ```bash
   cd ~/Developer/project-kit
   ./bootstrap.sh /path/to/your/repo --host github    # or --host gitlab
   ```
3. Open Claude Code or Codex in your repository and run `/rpa-init`, then `/rpa-gen-rules` (Codex:
   `$rpa-init`, `$rpa-gen-rules`). Fill the remaining `{{PLACEHOLDERS}}` in `AGENTS.md` and
   `DESIGN.md` with your project's facts.
4. Turn your backlog into milestones and issues, using the issue template that is now in your repo.
   Once per project, create the labels `bundle`, `inbox`, `tier:1`, `tier:2` and `tier:3` and the
   inbox issue, put its number into the project file as `INBOX_ISSUE`, and give every issue a tier
   label ([onboarding.md](onboarding.md), step 8, has the commands).
5. Link the `/kit` skill and start the first session. Claude Code:
   ```bash
   ln -s ~/Developer/project-kit/playbook/skills/kit ~/.claude/skills/kit
   ```
   Codex (the supplement reads the Claude skill, so link both):
   ```bash
   ln -s ~/Developer/project-kit/playbook/skills/kit ~/.claude/skills/kit
   ln -s ~/Developer/project-kit/playbook/skills/kit-codex ~/.agents/skills/kit
   ```
   In a chat inside your repository: `/kit init`, then `/kit next` (Codex: `$kit init`, `$kit next`).

[onboarding.md](onboarding.md) walks through this in detail, including CI and branch protection.

## Read more

| | |
| --- | --- |
| [onboarding.md](onboarding.md) | Setting up a project, step by step |
| [playbook/workflow.md](playbook/workflow.md) | The path of a change, from roadmap to merge |
| [playbook/roles.md](playbook/roles.md) | Who does what: owner, sessions, reviewer, acceptance agent, workers |
| [playbook/acceptance.md](playbook/acceptance.md) | The user check and the acceptance run |
| [playbook/session-briefs/triage-session.md](playbook/session-briefs/triage-session.md) | The triage run that empties the inbox |
| [REFERENCE.md](REFERENCE.md) | Everything technical: layout, placeholders, scripts, tests, licenses |

The Codex hook is taken from [coddy-agent](https://github.com/coddy-project/coddy-agent) (MIT).
This repository itself is under the [MIT License](LICENSE).
