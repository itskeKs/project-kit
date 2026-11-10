<!-- Commit subjects: type(scope): lowercase imperative summary. Body: cause → change → tests.
See CONTRIBUTING.md, "Opening a merge request". -->

## What this change is for

<!-- One or two sentences. `Closes #N` only when every acceptance box of the issue is done, otherwise
`Refs #N` plus what remains. -->

Refs #

## Scenarios and tests

<!-- Which scenario in features/ and which unit tests were added or changed, and that they were
red before the change. Use unit tests only when the project has no Gherkin. "None" needs a reason. -->

## User check

<!-- Copy the issue's user check. The acceptance run on this state reports here as a comment
(passed / not passed per point, findings); for `owner` checks the owner answers here. Delete when
the issue has no user check. -->

## Checks

- [ ] `make lint` green
- [ ] `make test` green (whole suite, against the test database if the project uses one)
- [ ] `make docs-check` green
- [ ] Docs updated in the same MR (owning page, `docs/feature-status.md` if a status changed)
- [ ] Screenshots section filled in if the UI changed; `DESIGN.md` updated if look or copy changed

## Screenshots

<!-- Mandatory for a visible UI change, otherwise delete this section. Before and after, desktop
and narrow (360 px), taken from a local instance with representative test data — never from a production instance. -->

| | Desktop | Narrow (360 px) |
| --- | --- | --- |
| Before | | |
| After | | |

## Notes for the reviewer

<!-- Only facts the diff does not show: stack and merge order, migration number, where the evidence is. No risks, no rationale, no "look here first": the reviewer reads the diff without them. Delete if empty. -->
