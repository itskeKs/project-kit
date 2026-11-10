# Executable specifications

The happy path of a behaviour, and the few scenarios a user would describe, live here as
Gherkin `.feature` files. They run like any other test, so a spec that no longer holds fails
the build. pytest-bdd is the example runner; any Gherkin runner of the stack works.
API and UI features share the same step library.

## When to use Gherkin at all

Use Gherkin only for user-visible behaviour of software with an API or UI. A library or CLI
without user journeys uses plain unit tests and the issue's acceptance boxes alone.

## Feature file or unit test?

| Goes into a `.feature` file | Stays an ordinary unit test (next to the code) |
| --- | --- |
| What a user would tell a colleague: "I preview the file, then import it" | Validation, boundary values, malformed input |
| The happy path and the one or two scenarios that define the behaviour | Error handling, permissions per role, races, retries |
| Observable through the HTTP API or the real browser UI | Anything that needs a service, a model or the database directly |

Rules for a feature file:

- Plain English, user-level language: no ids, status codes, table names or JSON. Say "is not
  found", not "answers 404"; the step decides what that means.
- Deterministic: no network, no LLM, no clock-dependent data.
- Short: a handful of scenarios. If a scenario needs a long list of cases, it is a unit test.
- One feature per file, named after the behaviour in `snake_case`: `file_import.feature`.
  The title line is `Feature: <same words>`; the paragraph under it states the rule in prose.
- Scenario names are sentences that read as claims ("Importing the same file again adds
  nothing"). They become the test names and the names in failure reports.

## How the step library is organised

- One `.feature` file contains the spec for a behaviour.
- One binding module per feature only binds the file to the runner; it contains no logic.
- A shared step library has one module per area. Each `Given`/`When`/`Then` phrase is defined
  once and may be used by every feature, so phrase patterns must stay unique. Reuse a phrase
  before inventing a new one.
- A `World` object holds per-scenario state: who is signed in, the last answer and records
  created so far. The runner's fixtures provide it to the steps.

API steps talk to the app through its API; UI steps use the real UI. They do not call
services directly.

## Journey twins

Each core journey in [docs/acceptance/journeys.md](../docs/acceptance/journeys.md) has an
automated twin under `features/journeys/`, tagged `@journey`: a browser scenario that walks the
journey through the real UI and asserts its expected values word for word. The values come from
the journey the owner approved, never from the code. A journey that depends on the date sets a
fixed reference date in its `Given` steps. A twin grows with the fixes: a finding from a blind
acceptance run first fails as a step in the twin of its journey, then the fix turns it green.
Twins run in CI on every {{HOST_PR}}; they do not replace the blind run, which checks that a user
finds the way at all.

## When a scenario fails

Use the failing scenario and step to locate the broken claim. Fix the behaviour or, if the
behaviour was changed on purpose, change the sentence in the feature file in the same commit.

## Running

Run the specs with the project's test command:

```sh
{{TEST_CMD}}
```

Use the chosen runner's file or scenario filter to narrow `{{TEST_CMD}}` while iterating.
