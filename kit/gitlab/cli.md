# GitHub CLI → GitLab CLI

Flags checked against the installed `gh 2.102.0` and `glab 1.121.0` command help.
`N` is a project-local issue or PR/MR number; `RUN_ID`, `PIPELINE_ID` and `JOB_ID`
are their respective run, pipeline and job IDs. Replace `MILESTONE`, `TITLE`,
`BRANCH` and file names with the actual values. Append `-R {{REPO}}` to commands
that support it when the current checkout is not the target repository.

| GitHub (`gh`) | GitLab (`glab`) | Note |
| --- | --- | --- |
| `gh auth status --hostname github.com` | `glab auth status --hostname gitlab.com` | Select the actual host for a self-managed instance. |
| `gh auth login --hostname github.com` | `glab auth login --hostname gitlab.com` | Interactive authentication; use the CLI's supported credential store. |
| `gh issue view N -R {{REPO}}` | `glab issue view N -R {{REPO}}` | Add `--comments` to show discussion. |
| `gh issue list --milestone MILESTONE` | `glab issue list --milestone MILESTONE` | Creation accepts a global milestone ID or title; list help describes an ID and also shows a title example. |
| `gh issue create --title TITLE --body-file issue.md --label task --milestone MILESTONE` | `glab issue create --title TITLE --description-file issue.md --label task --milestone MILESTONE` | Both accept `-` as the description file for standard input. |
| `gh issue comment N --body-file note.md` | `glab issue note N --message "$(cat note.md)"` | `note` accepts message text, without a body-file flag; command substitution removes trailing newlines. |
| `gh issue close N --comment "Reason"` | `glab issue note N --message "Reason"` then `glab issue close N` | The GitLab close command has no `--comment`; add the note first. |
| `gh pr create --title TITLE --body-file mr.md --base main --head BRANCH` | `glab mr create --title TITLE --description-file mr.md --target-branch main --source-branch BRANCH --remove-source-branch` | `-d` supplies description text; `--description-file` reads a file. Removal happens on merge. |
| `gh pr view N --json number,state,headRefName,baseRefName` | `glab mr view N -F json` | GitLab returns the full object; fields include `iid`, `state`, `source_branch`, `target_branch`. Parse the returned JSON as needed. |
| `gh pr list --state open` / `closed` / `merged` / `all` | `glab mr list` / `glab mr list --closed` / `glab mr list --merged` / `glab mr list --all` | Open is the default. `glab mr list` has no `--state` flag in this version. |
| `gh pr checks N --watch` | `glab ci status --branch BRANCH --live`; `glab ci view --branch BRANCH` | Select the MR source branch. `ci view` is interactive; inspect the MR's pipeline when several pipelines exist. |
| `gh pr merge N --merge --delete-branch` | `glab mr merge N --remove-source-branch --auto-merge` | Auto-merge waits for the pipeline; the older `--when-pipeline-succeeds` spelling is deprecated. GitLab's project merge method controls merge commits. Not used under the merge lock, which is released only once the merge is on the main branch. |
| `gh pr merge N --merge --delete-branch` after checks pass | `glab mr merge N --remove-source-branch --auto-merge=false` | Only the session that owns the MR, under the merge lock. Plain immediate merge; `glab mr merge N` defaults to auto-merge when a pipeline is running. Pin the reviewed head with `--sha SHA` (gh: `--match-head-commit SHA`). |
| `gh pr comment N --body-file note.md` | `glab mr note create N --message "$(cat note.md)"` | `glab mr note N --message ...` is a deprecated compatibility form; current help uses the `create` subcommand. |
| `gh pr edit N --base main` | `glab mr update N --target-branch main` | Retarget a stacked PR/MR after its parent lands; review its diff and pipeline again. |
| `gh pr close N` | `glab mr close N` | Closes without merging. |
| `gh run watch RUN_ID` | `glab ci status --branch BRANCH --live` (or `--wait`); `glab ci view --pipelineid PIPELINE_ID` | `ci status` selects by branch; `ci view` can select a pipeline ID. IDs are not interchangeable. |
| `gh run view RUN_ID --log-failed` | `glab ci trace JOB_ID --pipeline-id PIPELINE_ID` | Select the failed job first; `ci trace` streams that job's log, without a failed-steps-only filter. |
| `gh api repos/{{REPO}}/branches/main/protection` | `glab api projects/:id/protected_branches` | `:id` resolves from the current checkout. For another project, resolve its URL-encoded path to a numeric ID first. |
| `gh api repos/{{REPO}}/milestones -f title=TITLE` | `glab api projects/:id/milestones -f title=TITLE` | Adding fields defaults to POST. Contrary to older guidance, this installed `glab` also has `glab milestone create --title TITLE`. |
| `gh label create task --description "Task spec" --color 428BCA` | `glab label create --name task --description "Task spec" --color 428BCA` | GitLab takes the label name via `--name`. |
| `gh repo create {{REPO}} --private` | `glab repo create --group GROUP --name PROJECT --private` | Use the project's namespace and final path component. Add `--skipGitInit` if no local setup is wanted. For a self-managed instance set `GITLAB_HOST=<host>` (or pass a full project URL); `glab` otherwise targets its default host. |
| `gh release create v1.2.3 --title TITLE --notes-file release.md` | `glab release create v1.2.3 --name TITLE --notes-file release.md` | GitLab updates an existing release unless `--no-update` is supplied. |

## Differences that matter

- Conflicts do not prevent configured source-branch MR pipelines from running.
  Those pipelines test the source branch, ignoring the target branch. A merged
  results pipeline cannot form its temporary merge commit when there are
  conflicts; GitLab runs a standard MR pipeline instead. See
  [merge request pipelines](https://docs.gitlab.com/ci/pipelines/merge_request_pipelines/)
  and [merged results pipelines](https://docs.gitlab.com/ci/pipelines/merged_results_pipelines/).
- `Default.md` in `.gitlab/issue_templates/` and `.gitlab/merge_request_templates/`
  supplies the default description in GitLab's creation UI when present on the
  default branch. Higher-priority project or group defaults can override it.
  CLI calls with an explicit description should pass the template's filled-in
  content; do not assume the UI default is inserted into an API request. See
  [description templates](https://docs.gitlab.com/user/project/description_templates/).
- Protected branches distinguish permission to push from permission to merge.
  `push_access_level=0` means no direct pushes, including by maintainers;
  `merge_access_level=40` permits maintainers to merge through MRs. Check for
  overlapping wildcard or group rules because the most permissive matching
  protection can grant access. See
  [protected branch access levels](https://docs.gitlab.com/api/protected_branches/#valid-access-levels).
- Required approval rules depend on the GitLab tier; Free supports optional
  approvals, while enforceable rules require Premium or Ultimate. The protection
  tool tolerates approval HTTP 403/404 on its `POST .../approvals` call;
  `approvals_before_merge` is the project-wide minimum, finer rules live in the
  approval-rules API. Verify the resulting approval requirement on your instance. See
  [merge request approvals](https://docs.gitlab.com/user/project/merge_requests/approvals/)
  and the [approvals API](https://docs.gitlab.com/api/merge_request_approvals/#update-approval-configuration-for-a-project).
- Resolve a project with `glab api --hostname HOST projects/ENCODED_PATH`, then
  use the returned numeric `id`. Encode every slash, including subgroup slashes:
  `group/subgroup/project` becomes `group%2Fsubgroup%2Fproject`. For example,
  `python3 -c 'import urllib.parse; print(urllib.parse.quote("{{REPO}}", safe=""))'`.
  Branch names with slashes also need URL encoding in endpoint path segments.
  Pass `--hostname HOST` to `glab api`; `-h` means help.
- Both CLIs spell repository selection `-R` / `--repo`. `gh` accepts
  `[HOST/]OWNER/REPO`; `glab` accepts nested `GROUP/NAMESPACE/PROJECT` paths and
  full HTTPS or Git URLs. API calls use endpoint IDs or paths instead of `-R`.
- JSON flags vary by command: `gh ... --json field1,field2` selects fields;
  `glab mr view`, `mr list`, `issue view` and `ci status` use `-F json` /
  `--output json`. `glab issue list` uses `-O json` / `--output json`, while
  its `-F` means `--output-format`. `glab api` prints JSON by default, and its
  `-F` means a typed request field. `ci status --live` cannot output JSON.
- This installed `glab 1.121.0` has a `milestone` subcommand. The API form in
  the table remains useful for scripts and older versions without that command.
  Use each command's `--help` before carrying flags across versions.
