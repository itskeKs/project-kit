# project-kit

You have a software project. You want coding agents to do the work: pick up an issue, implement it,
test it, get it reviewed, merge it, and move on to the next one. You want to decide, not to babysit.

project-kit gives your repository the files and the routine for that. It works with Claude Code or
with Codex, on GitHub or GitLab.

## What it does

- **Rules for the agents in your repo.** A working contract (`AGENTS.md`), design rules, a docs
  skeleton, issue and pull request templates, CI, a protected main branch.
- **One issue, one session.** Every issue is worked by its own agent session, from claiming it to
  the merge. A fresh agent reviews the change. Findings are fixed in rounds; what does not fit
  becomes a follow-up issue.
- **Acceptance from the user's side.** Every issue says what a user does and sees afterwards. An
  agent that never sees the code tries exactly that before the merge. Per milestone, you accept.
- **A chain that keeps going.** When a session has opened its pull request, it starts the session
  for the next issue. Several chains can run in parallel.
- **Repositories that someone else merges.** With `MERGE_BY=maintainer` in the project file, a
  session hands its pull request over to the maintainer instead of merging it, posts no comment on
  their issues or pull requests, and stops when the maintainer pushes to it.
- **`/kit` in Claude Code, `$kit` in Codex.** `/kit status` shows what is running and what waits for
  you. `/kit next` starts the next issue. `/kit bug <text>` turns a sentence into an issue and starts
  its session. The sessions themselves run as Claude Code sessions or as Codex threads.

## What you do

You write the roadmap and the issues (or let `/kit bug` and `/kit feat` draft them). You answer
the questions only you can answer, as a comment "Owner decision". You accept each milestone. You log
in to GitHub or GitLab once; agents never handle credentials. Everything else an agent can do, an
agent does.

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
| [REFERENCE.md](REFERENCE.md) | Everything technical: layout, placeholders, scripts, tests, licenses |

The Codex hook is taken from [coddy-agent](https://github.com/coddy-project/coddy-agent) (MIT).
This repository itself is under the [MIT License](LICENSE).
