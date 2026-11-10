# Global layer

The orchestration setup that the kit's session briefs assume when Claude Code is the host, kept in
your personal Claude Code configuration instead of in each project.
[install-global.sh](../../install-global.sh) installs it. With Codex as the host nothing here is
needed: the supplement skill maps these roles to Codex threads and subagents.

| File | Goes to | What it is |
| --- | --- | --- |
| `agents/scout.md` | `~/.claude/agents/` | haiku, mechanical search, extraction and sweeps; leaf |
| `agents/builder.md` | `~/.claude/agents/` | sonnet at xhigh, the default worker for well-specified changes; leaf |
| `agents/verifier.md` | `~/.claude/agents/` | opus at high, adversarial review; verdict CONFIRMED or REFUTED; leaf |
| `agents/architect.md` | `~/.claude/agents/` | opus at xhigh, design and hard debugging; may delegate to `builder` and `scout` |
| `orchestration-policy.md` | appended to `~/.claude/CLAUDE.md` | the orchestration policy: roles, model tiers, depth limit |

The policy assumes the chat model is the most expensive model you use and delegates downward
from it. If you run on another tier, adjust `model` in the agent files and the tier map in the
policy to match. The roles in [roles.md](../../playbook/roles.md) describe how the agents are used.

## What stays yours

- The skills `/rpa-init` and `/rpa-gen-rules`: install them from
  [EvilFreelancer/rpa-skills](https://github.com/EvilFreelancer/rpa-skills).
- `codex-task`, only in the mixed setup where a Claude Code session delegates implementation to
  Codex. The kit does not ship it; it is a thin wrapper
  that you supply. The briefs call it as `codex-task DIR BRIEF_FILE [LOG]`. It runs
  `codex exec --ephemeral -C DIR` with your own Codex configuration and the brief from BRIEF_FILE
  (`-` means stdin), writes the output to LOG (default: a file in a temporary directory) and
  exits with Codex's exit code. [codex-briefs.md](../../playbook/codex-briefs.md) says how it is
  invoked and what a brief must contain; [onboarding.md](../../onboarding.md) lists it among the
  prerequisites.
