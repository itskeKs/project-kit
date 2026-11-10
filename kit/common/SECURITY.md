# Security policy

Reports about anything that breaks {{PROJECT_NAME}}'s hard invariants (see
[DESIGN.md](DESIGN.md) and [AGENTS.md](AGENTS.md)), bypasses authentication or authorization,
or exposes data, documents, secrets or backups are welcome and taken seriously.

## Reporting a vulnerability

Do not open a public issue with vulnerability details. Use {{HOST_SECURITY_CHANNEL}}.
If that channel is not available to you, open an issue that says only "security report"
with no detail and you will be contacted.

Include what you can: the affected route, page or script, steps to reproduce, the version
(git sha or artifact digest) and the affected deployment or distribution. You will get an
answer within a week; fixes land on `{{DEFAULT_BRANCH}}` and in the next release.

## Scope

- In scope: `<application components, distributed artifacts and maintained deployment tooling>`.
- Out of scope: `<third-party services, independently operated hosts and test-only configurations>`.

## Supported versions

Before the first release, `{{DEFAULT_BRANCH}}` is the supported line. After releases are published, the
latest release is supported. Document any additional maintained version lines here.
