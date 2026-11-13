# Acceptance from the user's side

Code review and tests check whether the code does what the issue says. They do not check whether the
product works for a user: the same agent that builds the feature writes the tests, so they confirm
its implementation. A project that only agents check turns green issue by issue and still does not
work in the end. This part of the kit closes the gap with three building blocks: the **user check**
in the issue, a **blind acceptance agent** and the **owner's acceptance** per milestone.

This is backed by a pilot in the originating project (2026-11-01): an agent without code access found 16 findings
against seven user journeys in 26 minutes. The owner rated 14 as defects and 2 as usability
problems, none as a false alarm. No existing test covered at least three of them (bank format,
decimal comma, due date).

## The user check in the issue

Every issue whose change a user notices carries a section **User check**: what a user does and what
they see afterwards, in their words, with concrete values. It is written **before** implementation,
by the owner or by the issue session; in the second case the owner confirms the expectation if it
contains a domain or legal decision.

```markdown
## User check

A user uploads her bank's CSV export (January to October): every transaction is imported with
counterparty and IBAN, incoming payments are suggested for the right customer account, uploading
it again creates no duplicate. Checked by: agent.
```

- **Values instead of properties.** "The reminder names 7 April 2026 as the due date and €3.64
  interest up to 31 October." is checkable, "the reminder is correct" is not.
- **The expectation comes from the domain, never from the implementation**: a law, a standard, a
  bank format, an invoice calculated by hand. Whoever reads the expectation off the code checks the
  code against itself.
- **Checked by:** `agent` or `owner`. `owner` only where no agent can get to: real devices (VPN
  profile, push notification), real mail delivery, real payments, a judgement of feel and tone.
- If an issue changes nothing a user sees (pure refactoring, CI), the section is omitted.

## Journeys and sample data in the project

`docs/acceptance/` in the project holds the **core journeys**: the five to fifteen flows the product
exists for, in user language, and the **sample data** for them (a made-up object, an account, a
record) with the correct results calculated by hand. They are the truth that checks run against and
change only with a decision by the owner. The format is in `docs/acceptance/README.md` of the kit.

The journeys are not Gherkin scenarios: a scenario tests a function with steps that the implementer
sets; a journey describes a goal, and the acceptance agent has to find the way itself. Where it has
to search, guess or go back, that is a finding.

## The acceptance agent

The acceptance agent is a role of its own beside the implementer and the `verifier`. It gets
**only**:

- the running app (address, test login, never production),
- the user check of the issue or the core journeys,
- the sample data and files a user would have (bank statement, PDF),
- a browser that it operates like a human.

It does **not** get: code, diff, PR, issue discussion, API description, logs. If it knows the
implementation, it confirms it. Model: Sonnet at high effort was enough in the pilot.

The brief is below. Two lessons from the pilot are already built into it:

- **Browser with files:** The browser window of the Claude app cannot attach a local file and cannot
  open a download; the pilot had to leave both to the owner. Hence Playwright from the shell
  (`page.set_input_files`, `page.expect_download`), with screenshots that the agent looks at.
- **Click, don't script:** The agent may not make an assignment or a booking by script or API, even
  when that would be faster. What it cannot manage by hand is a finding ("tedious"), and numbers
  that rest on its own shortcuts are not reliable.

### When it runs

- **Per PR with user check `agent`:** The session that merges the PR (as a rule the issue session
  that opened it, in the special case a maintainer session) starts it on the state of the PR before
  the merge, as soon as the fresh review has no open finding left. Its result comes as a comment on
  the PR: for each point of the user check passed or failed, plus the findings. Nothing is merged
  without a passed user check.
- **Per milestone or release:** It runs all core journeys on the main branch; the owner starts the
  run. This finds what every PR had green on its own and breaks in combination.
- **When onboarding an existing project:** a first run on the main branch as an inventory, before
  the first issues are written (see [onboarding.md](../onboarding.md)).

### What it delivers

A short report in the session's scratchpad, never in the repository: for each journey **passed**,
**failed** or **not checkable**, then the findings with step, expectation, observation, screenshot,
severity (**blocking**, **wrong**, **tedious**, **cosmetic**) and a class guess (a kind of defect
that one mechanism fixes at many places, such as a wrong spelling or a table cut off on a phone, or
`?`), and what it could not check. The agent keeps reporting everything it sees; it files nothing
and does not decide where a finding goes. The session that started it reconciles the findings with
code and logs, confirms them and records each confirmed one once (see "Recording the findings").
At most two runs per PR; a repeat run checks only the changed steps.

### Recording the findings

A confirmed finding is recorded, not filed: one comment line on the open bundle of its class, on
the open issue that already covers it, or on the project's inbox issue; a new issue at once only
for a blocker category, security, data loss or a core-journey step a user cannot finish, and at
most one other new issue per PR. The line format, the search before it and the cap are the section
"Findings" of the [issue session](session-briefs/issue-session.md); the
[triage session](session-briefs/triage-session.md) later turns the recorded lines into issues and
bundles. A finding the session cannot confirm is refuted with the reason in the PR comment only.

## The bridge to the E2E tests

The acceptance agent finds what nobody thought of, but it is expensive and not deterministic. E2E
tests in CI cost almost nothing per run and hold on to what once worked, but only check what someone
wrote into them. Both together close the circle:

1. **Every core journey has an automated twin**: a browser scenario under `features/journeys/` with
   the tag `@journey` that walks the journey's flow through the real UI and checks the expected
   values from `docs/acceptance/journeys.md` verbatim. It runs on every PR in CI. The values come
   from the journey the owner approved, never from the code; the fresh review checks that before the
   merge. Date-dependent journeys set a fixed reference date in the twin so that it stays
   deterministic.
2. **Every confirmed defect first becomes a red step when it is fixed.** The issue that fixes a
   finding of the acceptance agent requires that the finding fails, before the fix, as a step in the
   journey's twin (or as a new scenario there). That way the agent has to find a defect only once;
   after that CI holds it, and the next run reports only what is new.

The twins do not replace the blind run: they walk a path that someone has fixed. Whether a user finds
the way on their own is checked only by the blind run. They come into being with the fixes, not in
advance: at onboarding the list of journeys is enough, a twin comes with the first issue that touches
the journey.

## The owner's acceptance

The owner does not check every feature. For each milestone the owner gets a short list and needs at
most half an hour for it:

1. the findings of the last run over the core journeys, one verdict per finding:
   **Defect** (the product does something wrong), **Usability** (works, but the user gets stuck),
   **False alarm** (the agent is mistaken), **As intended** (meant to be that way; then the journey is
   corrected);
2. the user checks with `owner` that have been open since the last milestone;
3. one or two spot checks that the owner clicks through personally.

These verdicts and the owner's feedback are recorded like any finding (defect and usability
problems as lines on a bundle, an open issue or the inbox, the triage session files what needs
filing) or become corrections of the journeys (intended). The share of false alarms is the measure of whether the acceptance agent is any
good: if it rises above a third, the brief or the journeys are sharpened before building further on
it.

## Brief for the acceptance agent

Template; the session that starts the run fills in the placeholders. Values a tester quotes from a
German UI (labels, button texts) are quoted as they appear in the app.

```text
You are <PERSONA>, <ONE SENTENCE ON KNOWLEDGE AND GOAL>. You are trying out <PRODUCT> and deciding
whether to entrust your work to it.

You are not a tester of the code. Do not read any file of a repository or worktree, no source code,
no API description, no issues or pull requests, no logs, and do not look into the network requests.
What a user sees is allowed: the pages, their help texts, emails, downloaded files.

You have:
- the app at <URL> with the access from <ACCESS_FILE>; only this address, everything else on the
  machine is off limits, never production;
- your task: <USER CHECK OR PATH TO THE JOURNEYS>; the expected values in it are correct, and if the
  app deviates, that is a finding, not a reason to adjust the expectation;
- your files: <PATHS>;
- Playwright from the shell (Python, Chromium). Upload files with set_input_files, open downloads
  with expect_download, take a screenshot after every important step to <FOLDER>/<journey>-<no>.png
  and look at it before you go on.

How you proceed:
1. Go through each journey as <PERSONA> would: read the goal, look for the way in the app, without
   instructions. Where you have to search, guess or go back, note it.
2. At the end, compare every expected statement with what you see, and recalculate numbers.
3. Check the views the journey names at 360 px width as well.
4. If something breaks, try once more and note both.
5. Book, assign and create only through the UI, never by script or API. What takes too long by hand
   is a finding.
6. Invent nothing. If you are unsure, write "unsure" and why.

You deliver <FOLDER>/report.md: for each journey passed, failed or not checkable with one sentence;
the findings with journey, intent, observation, expectation, screenshot, severity (blocking,
wrong, tedious, cosmetic) and a class guess (a kind of defect that one mechanism fixes at many
places, or "?"); everything you see, nothing left out; what you could not check; three sentences on whether you would keep using
the product. You write to no repository, open no issues and send no messages. You do not start, stop
or change anything about the app, containers or processes.

At the end, clean up: close every browser and end every Playwright or Python process you started,
and delete everything you created outside <FOLDER> (downloads, temporary files). Only report.md and
the screenshots it refers to stay in <FOLDER>.
```

## Environment

The agent needs a running instance with an empty or known state, separate from production and, if
possible, without blocking the shared test database. Which environment that is in the project (local
dev stack, portable package, staging) is in the project's `AGENTS.md` under "Verification", together
with whether each run gets an environment of its own. The session that starts the run starts and
stops it, never the acceptance agent. If the environment is shared (shared staging, fixed ports), the
run holds `/tmp/<project>-acceptance.lock`: a `mkdir` before the environment starts, PR and time in
`info`, waiting and leftovers from crashes as with the merge lock ([workflow.md](workflow.md), "One
session, one task"), released right after the environment is torn down.

## Clean up after every run

An acceptance run is finished only when its leftovers are gone. The session that started it
afterwards checks that the agent has ended its browsers and processes, and then cleans up itself:

1. The run's environment completely: the Compose project with containers, volumes, networks and the
   project's locally built images (`docker compose -p <name> down -v --rmi local`), a portable
   package together with its unpacked directory, a dev server and its processes. Never production,
   never the shared test database, never an environment the session did not start itself.
2. The folder with report and screenshots, as soon as the result and confirmed findings are in place
   as a comment on the PR or as issues; screenshots that a finding needs are attached there.
3. Copies of the sample data, test logins and downloads outside this folder.
4. Locks that the session took for the run.

As a check: `docker compose ls` and `docker ps -a` show no project of the run any more,
`docker volume ls` no volumes with its project name, and no process of the run is still running.
Leftovers of other runs that turn up are reported to the owner by the session instead of deleted.
