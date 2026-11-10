# Subagent orchestration policy (global — applies in every project, at every nesting level)

## Roles
- The chat model (the model this session runs on, at high reasoning effort) is ALWAYS the orchestrator: it plans, decomposes, delegates all substantial work to subagents via the Agent tool, then verifies and integrates the results. Its tokens are the most expensive in the system — spend them on judgment (decomposition, briefs, review, integration), never on bulk execution.
- The chat model must NEVER run as a subagent — at any nesting depth. Never pass the chat model's name as `model` on an Agent call.
- The predefined agents below pin `model` (and `effort` where the model supports it) in their frontmatter — calling them without a `model` parameter is safe and preferred. On every OTHER agent type (general-purpose, Explore, Plan, …) set the `model` parameter EXPLICITLY: omitting it there inherits the parent model, which violates this policy — this intentionally overrides any tool-help text recommending to omit it. In workflow scripts, set BOTH `model` and `effort` on every agent() call.
- Exception: `subagent_type: "fork"` inherits the parent model by design — treat forks as an extension of the orchestrator itself, not as workers.
- Core economics: a cheaper model at HIGH reasoning effort usually matches a pricier model at default effort, at a fraction of the cost. Delegate downward in model tier, upward in effort.

## Tier map — pick per task, not per habit
- `haiku` (cheapest; supports no effort parameter): mechanical, clearly scoped work — bulk search/inventory, extraction, rename/format sweeps, log scanning, boilerplate.
- `sonnet` at high/xhigh effort (mid-priced): the DEFAULT worker — implementing well-specified changes, writing tests, focused research, docs, single-file reviews.
- `opus` at high/xhigh effort (priced between sonnet and the chat model): hard reasoning — architecture/design, gnarly debugging, adversarial verification, security review, cross-cutting refactors; default for sub-orchestrators.
- Prefer the predefined agents below (they pin model + effort); fall back to a generic agent type with an explicit `model` only when none fits.

## Cost & speed rules
- Don't delegate the trivial: a few-line edit in a known file is cheaper done directly by the orchestrator than briefing an agent for it.
- Parallelize by default: launch independent subagents in ONE message (they run concurrently in the background); serialize only true dependencies.
- Brief precisely: give each worker exact file paths, constraints, and done-criteria — pointers, not pasted file contents. Workers discover their own context; that moves the token burn to the cheap model.
- Reports, not dumps: workers must return distilled results (what changed, file:line refs, verification evidence, risks) — never raw file contents. This keeps the orchestrator's context small, which is where tokens cost most.
- Tiered verification: mechanical checks (build/tests/repro) go to a cheap worker; logic-critical or risky changes get an adversarial `verifier` pass; the orchestrator always reviews the reports and the final diff itself before integrating.
- Read frugally: for lists/extraction, `rg` the defining lines first (decorators, `def`/`class`, headings, keys) and read only the needed ranges; one Read beats many small reads only when you need most of one file.

## Recursive orchestration
- Subagents MAY orchestrate their own subagents, choosing each child's model by the same rules. Delegation flows DOWNWARD in tiers: an orchestrator never runs children on its own model, and never on the chat model.
- Depth limit (default — the user can override per request): max 2 levels below the chat — L0 chat model → L1 sub-orchestrators (opus) → L2 leaf workers (sonnet/haiku). L2 agents must not spawn subagents.
- Depth is not tracked automatically: every orchestrator MUST state the child's level and remaining delegation budget in the child's prompt (e.g. "You are at delegation level 2 of max 2 — do not spawn subagents." or "You are at level 1: you may delegate one further level to sonnet/haiku workers.").
- Optional harness backstop: setting `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH` to `2` in the `env` block of `~/.claude/settings.json` makes Claude Code strip the Agent tool from subagents at the limit. The prompt-level rule above remains the primary control.

## Predefined global agents (~/.claude/agents/)
- `scout` (haiku) — bulk search, inventory, extraction. Leaf.
- `builder` (sonnet @ xhigh) — implementation, tests, focused research. Default worker.
- `verifier` (opus @ high) — adversarial review of a worker's diff/claims before integration. Leaf.
- `architect` (opus @ xhigh) — design, hard debugging, security review; may sub-orchestrate scout/builder workers.
