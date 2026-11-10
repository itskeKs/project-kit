# project-kit

You have a software project. You want coding agents to do the work: pick up an issue, implement it,
test it, get it reviewed, merge it, and move on to the next one. You want to decide, not to babysit.

project-kit gives your repository the files and the routine for that. It works with Claude Code,
optionally with Codex as a second worker, on GitHub or GitLab.

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
- **`/kit` in Claude Code.** `/kit status` shows what is running and what waits for you. `/kit next`
  starts the next issue. `/kit bug <text>` turns a sentence into an issue and starts its session.

## What you do

You write the roadmap and the issues (or let `/kit bug` and `/kit feat` draft them). You answer
the questions only you can answer, as a comment "Owner decision". You accept each milestone. You log
in to GitHub or GitLab once; agents never handle credentials. Everything else an agent can do, an
agent does.

## What you need

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) and the `gh` or `glab` CLI, logged in.
- The skills `/rpa-init` and `/rpa-gen-rules` from
  [EvilFreelancer/rpa-skills](https://github.com/EvilFreelancer/rpa-skills). They read your project
  and generate its rules. Install them in Claude Code:
  ```text
  /plugin marketplace add EvilFreelancer/rpa-skills
  /plugin install rpa-init@rpa-skills
  /plugin install rpa-gen-rules@rpa-skills
  ```
- Optional: [Codex](https://github.com/openai/codex) as a worker. The kit brings the hook that feeds
  it your project rules.
- The orchestration setup the briefs refer to: an orchestration policy in `~/.claude/CLAUDE.md` and
  the agents `scout`, `builder`, `verifier` and `architect` in `~/.claude/agents/`. The kit does not
  ship them yet; [REFERENCE.md](REFERENCE.md#requirements) says what they do.

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
3. Open Claude Code in your repository and run `/rpa-init`, then `/rpa-gen-rules`. Fill the
   remaining `{{PLACEHOLDERS}}` in `AGENTS.md` and `DESIGN.md` with your project's facts.
4. Turn your backlog into milestones and issues, using the issue template that is now in your repo.
5. Link the `/kit` skill and start the first session:
   ```bash
   ln -s ~/Developer/project-kit/playbook/skills/kit ~/.claude/skills/kit
   ```
   In a Claude Code chat inside your repository: `/kit init`, then `/kit next`.

[onboarding.md](onboarding.md) walks through this in detail, including CI and branch protection.

## Read more

| | |
| --- | --- |
| [onboarding.md](onboarding.md) | Setting up a project, step by step |
| [playbook/workflow.md](playbook/workflow.md) | The path of a change, from roadmap to merge |
| [playbook/roles.md](playbook/roles.md) | Who does what: owner, sessions, reviewer, acceptance agent, Codex |
| [playbook/acceptance.md](playbook/acceptance.md) | The user check and the acceptance run |
| [REFERENCE.md](REFERENCE.md) | Everything technical: layout, placeholders, scripts, tests, licenses |

The Codex hook is taken from [coddy-agent](https://github.com/coddy-project/coddy-agent) (MIT).
This repository has no license file of its own yet.
