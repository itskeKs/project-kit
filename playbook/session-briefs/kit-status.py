#!/usr/bin/env python3
"""Overview of the kit's session chains across all registered projects.

Reads the per-project files outside the repository (~/.config/project-kit/briefs/*.env, or
$PROJECT_KIT_CONFIG/briefs/*.env, the same files fill-brief.py uses) and, read-only, asks gh / glab
and git what is going on: open PRs/MRs with CI state and the latest kit marker from their comments,
open issues with their flags, the findings intake (issues created and closed in the last seven days,
open lines on the inbox issue, open bundles, open items per tier), the worktrees `<repo>-issue-N` /
`<repo>-review-N`, and the merge, acceptance and triage locks in /tmp. A final section "Needs you"
collects what only the owner can resolve.

    kit-status.py [project ...] [--json] [--no-issues]

A project argument is a part of an env file's name (several arguments add up); without one all
projects are read. Errors (auth, network, missing CLI) are reported in the project's block and never
stop the run. Optional keys in a project file: GITLAB_HOST (otherwise taken from the checkout's
origin remote), MERGE_BY (`session`, the default, or `maintainer`: someone else merges, so only our own
open PRs are listed, as "Waiting for maintainer" with CI, review decision and whether others committed
to them, and only the owner's issues: assigned to the owner, or opened by the owner without an assignee).
Intake keys of a project file: INBOX_ISSUE (the inbox issue's number; the open lines are the unticked
`- [ ]` lines in its comments), INBOX_LABEL, BUNDLE_LABEL, TIER_1_LABEL, TIER_2_LABEL, TIER_3_LABEL (defaults
inbox, bundle, tier:1, tier:2, tier:3). What a project does not have yet shows as "not set up": no
INBOX_ISSUE, or labels that do not exist on the host. A project whose maintainer merges has no intake.
$PROJECT_KIT_LOCK_DIR replaces /tmp as the place of the lock directories.

Nothing here writes to a host, a repository or a lock.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import NamedTuple
from urllib.parse import quote

ISSUE_CAP = 25  # open issues shown without a milestone, and issues whose comments are fetched
ORPHAN_HOURS = 24  # an issue worktree without PR/MR that idle for longer is an orphan claim
REMNANT_MINUTES = 30  # a lock naming a PR that is no longer open is a remnant after this long
DEFAULT_LOCK_MAX = 120
CALL_TIMEOUT = 45  # seconds per gh / glab / git call
WORKTREE_RE = re.compile(r"-(issue|review)-(\d+)$")
INTAKE_DAYS = 7  # the window of "issues created and closed"
DEFAULT_TIERS = ("tier:1", "tier:2", "tier:3")  # launch blocker, before launch, after launch
OPEN_LINE = re.compile(r"^[ \t]*[-*][ \t]+\[ \](?:[ \t]|$)", re.M)  # an unticked line of the inbox: "- [ ] ..."

# ---------------------------------------------------------------------------------------------
# Pure helpers: parsing and classification (these are what tests/test_kit_status.py exercises)
# ---------------------------------------------------------------------------------------------


def parse_env(text: str) -> dict:
    """KEY=value lines; blank lines and # comments skipped; one pair of quotes around a value dropped."""
    values = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def config_root() -> Path:
    return Path(os.environ.get("PROJECT_KIT_CONFIG", Path.home() / ".config" / "project-kit"))


def parse_lock_max(value, default: int = DEFAULT_LOCK_MAX) -> int:
    """Leading integer of '34 minutes' as minutes ('2 hours' as 120); missing or unparsable gives the default."""
    match = re.match(r"\s*(\d+)\s*(h|hours?)?\b", str(value or ""), re.I)
    if not match:
        return default
    minutes = int(match.group(1)) * (60 if match.group(2) else 1)
    return minutes if minutes > 0 else default


class Project(NamedTuple):
    stem: str
    name: str
    repo: str
    host_cli: str
    pr_abbr: str
    repo_path: str
    main_branch: str
    milestone: str  # "" when there is none
    lock_max: int
    gitlab_host: str
    merge_by: str = "session"  # "maintainer": someone else merges our PRs
    inbox_issue: str = ""  # number of the inbox issue; "" when the project has none yet
    inbox_label: str = "inbox"
    bundle_label: str = "bundle"
    tier_labels: tuple = DEFAULT_TIERS


def project_from_env(env: dict, stem: str) -> Project:
    def value(key):
        found = env.get(key, "").strip()
        return "" if found.upper() == "TODO" else found

    host_cli = value("HOST_CLI") or "gh"
    milestone = value("MILESTONE")
    return Project(
        stem=stem,
        name=value("PROJECT_NAME") or stem,
        repo=value("REPO"),
        host_cli=host_cli,
        pr_abbr=value("HOST_PR_ABBR") or ("PR" if host_cli == "gh" else "MR"),
        repo_path=os.path.expanduser(value("REPO_PATH")),
        main_branch=value("MAIN_BRANCH"),
        milestone="" if milestone.lower() == "none" else milestone,
        lock_max=parse_lock_max(env.get("LOCK_MAX")),
        gitlab_host=value("GITLAB_HOST"),
        merge_by="maintainer" if value("MERGE_BY").lower() == "maintainer" else "session",
        inbox_issue=value("INBOX_ISSUE") if value("INBOX_ISSUE").isdigit() else "",
        inbox_label=value("INBOX_LABEL") or "inbox",
        bundle_label=value("BUNDLE_LABEL") or "bundle",
        tier_labels=tuple(value(f"TIER_{n}_LABEL") or DEFAULT_TIERS[n - 1] for n in (1, 2, 3)),
    )


def projects_here(root: Path, cwd: Path) -> list:
    """Project file stems for `cwd`: the project whose REPO_PATH contains `cwd` (inside a checkout),
    else every project whose REPO_PATH lies under `cwd` (a workspace folder above several checkouts)."""
    cwd = Path(cwd).resolve()
    inside, below = [], []
    for f in sorted((Path(root) / "briefs").glob("*.env")):
        repo = parse_env(f.read_text()).get("REPO_PATH", "")
        if not repo:
            continue
        repo = Path(repo).resolve()
        if repo in (cwd, *cwd.parents):
            inside.append(f.stem)
        elif cwd in repo.parents:
            below.append(f.stem)
    return inside[:1] or below


def load_projects(root: Path, names=()) -> list:
    """Every `<root>/briefs/*.env`, or those whose file name contains one of `names` (case-insensitive)."""
    files = sorted((Path(root) / "briefs").glob("*.env"))
    wanted = [n.lower() for n in names]
    if wanted:
        files = [f for f in files if any(n in f.stem.lower() for n in wanted)]
    return [project_from_env(parse_env(f.read_text()), f.stem) for f in files]


def remote_host(url: str) -> str:
    """Host of a git remote URL: git@host:group/project.git, ssh://git@host:22/..., https://host/..."""
    url = url.strip()
    match = re.match(r"^[a-z][a-z0-9+.-]*://(?:[^@/]*@)?([^/:]+)", url, re.I) or re.match(r"^(?:[^@/]*@)?([^/:]+):", url)
    return match.group(1) if match else ""


def lead(body: str) -> str:
    """The comment's first non-empty line without markdown decoration in front."""
    for line in (body or "").splitlines():
        line = line.strip()
        if line:
            return re.sub(r"^[#*_>`\s-]+", "", line)
    return ""


def first_line(body: str, limit: int = 200) -> str:
    for line in (body or "").splitlines():
        line = " ".join(line.split())
        if line:
            return line if len(line) <= limit else line[: limit - 1] + "…"
    return ""


def _body(comment) -> str:
    return comment if isinstance(comment, str) else (comment.get("body") or "")


_ROUND = re.compile(r"^round\s+(\d+)\b", re.I)
_NOT_MERGED = re.compile(r"^not merged\b", re.I)
_MERGED = re.compile(r"^Merged(?:\s+(?:after|as is)\b|[.:(!]|$)")
_BLOCKED = re.compile(r"^blocked:", re.I)


def classify_pr_comments(comments) -> dict:
    """Latest kit marker among a PR/MR's comments (oldest first): the newest comment that starts with
    'Not merged', 'Round <k>', 'Merged' or 'Blocked:'. Kind is one of not_merged, round, merged,
    blocked, none; `line` is the comment's first line, `round` the number k."""
    for comment in reversed(list(comments or [])):
        head = lead(_body(comment))
        found = None
        if _NOT_MERGED.match(head):
            found = {"kind": "not_merged", "round": None}
        elif _BLOCKED.match(head):
            found = {"kind": "blocked", "round": None}
        elif _MERGED.match(head):
            found = {"kind": "merged", "round": None}
        else:
            match = _ROUND.match(head)
            if match:
                found = {"kind": "round", "round": int(match.group(1))}
        if found:
            found["line"] = first_line(_body(comment))
            found["url"] = "" if isinstance(comment, str) else comment.get("url", "")
            return found
    return {"kind": "none", "round": None, "line": "", "url": ""}


def marker_label(marker) -> str:
    if not marker:
        return "unknown"
    kind = marker["kind"]
    if kind == "round":
        return f"Round {marker['round']}"
    if kind == "merged":
        return "Merged"
    if kind in ("not_merged", "blocked"):
        return marker["line"] or ("Not merged" if kind == "not_merged" else "Blocked:")
    return "no review yet"


_ASKS = re.compile(r"^owner decisions?\s+(needed|requested|required)\b")  # a question, not an answer


def _is_decision(comment) -> bool:
    head = lead(_body(comment)).lower()
    return (head.startswith("owner decision") and not _ASKS.match(head)) or head.startswith("decision:")


def _is_question(comment) -> bool:
    body = _body(comment)
    head = lead(body).lower()
    return head.startswith("questions before implementation") or "blocked: owner decision" in body.lower() or bool(_ASKS.match(head))


def issue_flags(comments, has_pr: bool, has_worktree: bool) -> dict:
    """Flags of an open issue from its comments (oldest first). `blocked`: the newest comment starting
    with 'Blocked:' has no later 'Owner decision' / '**Decision:**' comment. `question`: the newest
    'Questions before implementation' comment, or one containing 'Blocked: owner decision' (or opening
    with the older 'Owner decision needed'), has no later decision. `note` is the first line of the
    comment that blocks or asks."""
    comments = list(comments or [])
    last_decision = max((i for i, c in enumerate(comments) if _is_decision(c)), default=-1)
    last_blocked = max((i for i, c in enumerate(comments) if _BLOCKED.match(lead(_body(c)))), default=-1)
    last_question = max((i for i, c in enumerate(comments) if _is_question(c)), default=-1)
    blocked = last_blocked > last_decision
    question = last_question > last_decision
    at = max(last_blocked, last_question) if blocked or question else -1
    return {
        "pr": bool(has_pr),
        "blocked": blocked,
        "question": question,
        "in_progress": bool(has_worktree),
        "note": first_line(_body(comments[at])) if at >= 0 else "",
    }


def issue_refs(title: str, body: str, branch: str) -> list:
    """Issue numbers a PR/MR names: '#N' in title or description, and branches such as issue-N."""
    refs = {int(n) for n in re.findall(r"(?<![\w&/])#(\d+)\b", f"{title}\n{body or ''}")}
    refs |= {int(n) for n in re.findall(r"(?:^|[/_-])issue[-_/]?(\d+)(?![\d])", branch or "")}
    return sorted(refs)


def count_open_lines(comments) -> int:
    """Open lines on the inbox: the unticked `- [ ]` lines in the comments (a ticked `- [x]` line is handled)."""
    return sum(len(OPEN_LINE.findall(_body(comment))) for comment in comments or [])


def tier_of(labels, tier_labels):
    """Index (0 = most urgent) of the most urgent tier label among `labels`, or None when there is none."""
    ranks = [tier_labels.index(name) for name in labels or [] if name in tier_labels]
    return min(ranks) if ranks else None


def intake_counts(issues, project) -> dict:
    """Open bundles and open items per tier over all open issues of the project (`issues`: dicts with
    'labels'). The inbox issue is no work item. An issue with several tier labels counts under the most
    urgent; `none` counts the work items without any."""
    tiers = {label: 0 for label in project.tier_labels}
    tiers["none"] = bundles = 0
    for found in issues:
        labels = found.get("labels") or []
        if project.inbox_label in labels:
            continue
        bundles += project.bundle_label in labels
        rank = tier_of(labels, project.tier_labels)
        tiers["none" if rank is None else project.tier_labels[rank]] += 1
    return {"bundles": bundles, "tiers": tiers}


def summarize_checks(entries) -> str:
    """GitHub statusCheckRollup entries (CheckRun and StatusContext) as green, red, pending or none."""
    red = pending = ok = False
    for entry in entries or []:
        if entry.get("__typename") == "StatusContext" or ("state" in entry and "status" not in entry):
            state = (entry.get("state") or "").upper()
            red |= state in ("FAILURE", "ERROR")
            pending |= state in ("PENDING", "EXPECTED", "")
            ok |= state == "SUCCESS"
            continue
        if (entry.get("status") or "").upper() != "COMPLETED":
            pending = True
            continue
        conclusion = (entry.get("conclusion") or "").upper()
        if conclusion in ("SUCCESS", "NEUTRAL", "SKIPPED"):
            ok |= conclusion == "SUCCESS"
        else:  # FAILURE, CANCELLED, TIMED_OUT, ACTION_REQUIRED, STARTUP_FAILURE, STALE
            red = True
    return "red" if red else "pending" if pending else "green" if ok else "none"


def summarize_pipeline(status) -> str:
    """GitLab pipeline status as green, red, pending or none."""
    status = (status or "").lower()
    if status in ("success", "success_with_warnings"):
        return "green"
    if status in ("failed", "canceled", "cancelled"):
        return "red"
    if status in ("", "skipped"):
        return "none"
    return "pending"  # created, waiting_for_resource, preparing, pending, running, scheduled, manual


def foreign_authors(authors, own) -> list:
    """Authors of a PR's commits that are not ours. `authors` holds one tuple of identifiers per commit author
    (a GitHub login, e-mail and name; a GitLab name and e-mail), `own` our identifiers; an author is ours when any
    of its identifiers matches one of ours, case-insensitively. Returns each foreign author's first identifier,
    sorted, once; an author without any identifier cannot be told apart and is skipped."""
    mine = {o.strip().casefold() for o in own if o and o.strip()}
    found = {}
    for identifiers in authors or []:
        known = [i.strip() for i in identifiers if i and i.strip()]
        if known and not any(i.casefold() in mine for i in known):
            found.setdefault(known[0].casefold(), known[0])
    return sorted(found.values(), key=str.casefold)


REVIEW_LABELS = {"APPROVED": "approved", "CHANGES_REQUESTED": "changes requested", "REVIEW_REQUIRED": "review required"}


def waiting_label(pr) -> str:
    """What one of our PRs that waits for the maintainer shows next to its CI state: that the maintainer took it
    over, or its conflicts and review decision."""
    if pr.get("taken_over"):
        return "taken over by maintainer"
    parts = ["conflicts"] if pr.get("conflicts") else []
    review = REVIEW_LABELS.get((pr.get("review") or "").upper())
    if review:
        parts.append(review)
    return ", ".join(parts) or "waiting"


def _parse_time(text: str):
    text = (text or "").strip()
    if not text:
        return None
    try:
        moment = datetime.fromisoformat(text[:-1] + "+00:00" if text.endswith("Z") else text)
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def lock_state(info_text: str, now: datetime, lock_max: int, fallback=None, open_prs=None) -> dict:
    """State of a lock from its `info` file ('<pr-no> <iso-time>'). Stale when older than `lock_max`
    minutes; also when `open_prs` (a set of open PR numbers, if known) lacks the PR it names and it is
    older than 30 minutes. `fallback` (a datetime) stands in for an unreadable time."""
    text = (info_text or "").strip()
    match = re.match(r"^#?(\d+)\s+(\S+)", text)
    pr = int(match.group(1)) if match else None
    since = _parse_time(match.group(2)) if match else None
    note = ""
    if since is None and fallback is not None:
        since, note = fallback, "info unreadable, age from the directory"
    elif since is None:
        note = "info unreadable"
    age = max(0, int((now - since).total_seconds() // 60)) if since else None
    stale = age is not None and age > lock_max
    if stale:
        note = f"older than {lock_max} minutes"
    elif age is not None and pr is not None and open_prs is not None and pr not in open_prs and age > REMNANT_MINUTES:
        stale, note = True, f"names #{pr}, which is not open"
    return {
        "pr": pr,
        "since": since.strftime("%Y-%m-%dT%H:%M:%SZ") if since else None,
        "age_minutes": age,
        "stale": stale,
        "note": note,
        "info": text,
    }


def parse_worktrees(text: str) -> list:
    """`git worktree list --porcelain` as [{'path', 'head', 'branch'}]; branch is None when detached."""
    entries, current = [], None
    for line in text.splitlines():
        if line.startswith("worktree "):
            current = {"path": line[len("worktree "):], "head": "", "branch": None}
            entries.append(current)
        elif current is not None and line.startswith("HEAD "):
            current["head"] = line[len("HEAD "):]
        elif current is not None and line.startswith("branch "):
            ref = line[len("branch "):]
            current["branch"] = ref[len("refs/heads/"):] if ref.startswith("refs/heads/") else ref
    return entries


def fmt_hours(hours) -> str:
    return fmt_age(None if hours is None else hours * 60)


def fmt_age(minutes) -> str:
    if minutes is None:
        return "?"
    if minutes < 90:
        return f"{int(minutes)}m"
    if minutes < 48 * 60:
        return f"{int(minutes // 60)}h"
    return f"{int(minutes // 1440)}d"


KIND_ORDER = ["error", "stale_lock", "blocked", "question", "not_merged", "pr_blocked", "parked", "orphan", "chain_ended"]


def needs_you(projects) -> list:
    """What only the owner can resolve, across the per-project result dicts of collect_project:
    [{'project', 'kind', 'text', 'url'}], grouped by project, most urgent kind first."""
    items = []
    for proj in projects:
        name, abbr = proj["name"], proj.get("pr_abbr", "PR")
        found = []

        def add(kind, text, url=""):
            found.append({"project": name, "kind": kind, "text": text, "url": url})

        for error in proj.get("errors", []):
            add("error", error)
        for pr in proj.get("prs", []):
            label = f"{abbr} #{pr['number']} {pr['title']}"
            marker = pr.get("marker") or {}
            if marker.get("kind") == "not_merged":
                add("not_merged", f"{label}: {marker.get('line') or 'Not merged'}", pr.get("url", ""))
            elif marker.get("kind") == "blocked":
                add("pr_blocked", f"{label}: {marker.get('line') or 'Blocked:'}", pr.get("url", ""))
            if pr.get("parked"):
                add("parked", f"{label} is parked", pr.get("url", ""))
        for issue in proj.get("issues", []):
            flags = issue.get("flags", {})
            reason = flags.get("note") or ""
            if flags.get("blocked"):
                add("blocked", f"#{issue['number']} {issue['title']}" + (f": {reason}" if reason else ""), issue.get("url", ""))
            elif flags.get("question"):
                add("question", f"#{issue['number']} {issue['title']}: open owner question", issue.get("url", ""))
        for lock in proj.get("locks", []):
            if lock.get("stale"):
                age = fmt_age(lock.get("age_minutes"))
                add("stale_lock", f"{lock['name']} \"{lock.get('info', '')}\" is stale ({age}, {lock.get('note', '')})", lock["path"])
        if proj.get("prs_ok", True):
            for wt in proj.get("worktrees", []):
                idle = wt.get("idle_hours", wt.get("commit_age_hours"))
                if wt["kind"] == "issue" and not wt.get("pr") and idle is not None and idle > ORPHAN_HOURS:
                    add("orphan", f"worktree {wt['name']} has no {abbr} and has been idle for {fmt_hours(idle)}"
                                  f" (last commit {fmt_hours(wt.get('commit_age_hours') or idle)} ago): orphan claim", wt["path"])
        upstream = proj.get("merge_by") == "maintainer"  # our open PRs wait for the maintainer: no running chain
        running = [wt for wt in proj.get("worktrees", []) if wt["kind"] == "issue" and not (upstream and wt.get("pr"))]
        if proj.get("milestone") and proj.get("prs_ok") and proj.get("issues_ok") and (upstream or not proj.get("prs")) and not running:
            free = [i for i in proj.get("issues", [])
                    if i.get("checked", True) and not any(i["flags"].get(k) for k in ("pr", "blocked", "question", "in_progress"))]
            untiered = []
            if not upstream:  # the next issue is picked by tier; the inbox and an issue without a tier are never picked
                tiers = tuple(proj.get("tier_labels") or DEFAULT_TIERS)
                free = [i for i in free if proj.get("inbox_label", "inbox") not in (i.get("labels") or [])]
                untiered = [i for i in free if tier_of(i.get("labels"), tiers) is None]
                free = sorted((i for i in free if tier_of(i.get("labels"), tiers) is not None),
                              key=lambda i: (tier_of(i.get("labels"), tiers), i["number"]))
            quiet = "nothing in progress" if upstream else f"no open {abbr} and nothing in progress"
            if free:
                add("chain_ended", f"{quiet}, but {len(free)} open unblocked issue(s), "
                                   f"next #{free[0]['number']} {free[0]['title']}", free[0].get("url", ""))
            elif untiered:
                add("chain_ended", f"{quiet}, but {len(untiered)} open unblocked issue(s) without a tier label, "
                                   f"which are never picked: tier them (first #{untiered[0]['number']} {untiered[0]['title']})",
                    untiered[0].get("url", ""))
        found.sort(key=lambda item: KIND_ORDER.index(item["kind"]))
        items.extend(found)
    return items


# ---------------------------------------------------------------------------------------------
# Collecting: gh / glab / git, read-only
# ---------------------------------------------------------------------------------------------


class ToolError(Exception):
    pass


_SLOTS = threading.BoundedSemaphore(16)  # concurrent child processes over all projects


def run_cmd(cmd, env_extra=None, timeout=CALL_TIMEOUT) -> str:
    env = {**os.environ, "NO_COLOR": "1", "GH_PROMPT_DISABLED": "1", "GIT_TERMINAL_PROMPT": "0", **(env_extra or {})}
    try:
        with _SLOTS:
            proc = subprocess.run(cmd, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        raise ToolError(f"{cmd[0]} not found")
    except subprocess.TimeoutExpired:
        raise ToolError(f"{' '.join(cmd[:3])} timed out after {timeout}s")
    if proc.returncode != 0:
        text = " ".join((proc.stderr.strip() or proc.stdout.strip()).split())
        text = re.sub(r"^ERROR\s+", "", text)
        text = text[:160] or f"exit {proc.returncode}"
        raise ToolError(text if text.startswith(f"{cmd[0]}:") else f"{cmd[0]}: {text}")
    return proc.stdout


def run_json(cmd, env_extra=None):
    out = run_cmd(cmd, env_extra)
    try:
        return json.loads(out)
    except ValueError:
        raise ToolError(f"{cmd[0]}: unexpected output ({' '.join(out.split())[:80] or 'empty'})")


def _comment(body, created, url):
    return {"body": body or "", "created": created or "", "url": url or ""}


def _chronological(comments):
    return sorted(comments, key=lambda c: c["created"])


class GitHub:
    """gh: two bulk calls per project, comments and checks come with the lists."""

    def __init__(self, project):
        self.p = project

    @staticmethod
    def _comments(raw):
        return _chronological([_comment(c.get("body"), c.get("createdAt"), c.get("url")) for c in raw or []])

    def prs(self):
        if self.p.merge_by == "maintainer":
            return self.own_prs()
        data = run_json(["gh", "pr", "list", "-R", self.p.repo, "--state", "open", "--limit", "100", "--json",
                         "number,title,headRefName,isDraft,labels,url,body,comments,statusCheckRollup"])
        return [{"number": d["number"], "title": d["title"], "branch": d["headRefName"], "draft": bool(d["isDraft"]),
                 "labels": [label["name"] for label in d.get("labels") or []], "url": d.get("url", ""),
                 "body": d.get("body") or "", "comments": self._comments(d.get("comments")),
                 "ci": summarize_checks(d.get("statusCheckRollup"))} for d in data]

    def own_prs(self):
        """MERGE_BY=maintainer: only our PRs; no comments (nobody posts markers), but the review decision,
        mergeability and the authors of the commits, which tell whether the maintainer has taken one over."""
        # 20, not 100: `commits` asks GitHub for up to 100 commits with up to 100 authors each per PR, and
        # 100 PRs of that exceed GraphQL's 500,000-node limit; 20 open PRs of our own is plenty.
        data = run_json(["gh", "pr", "list", "-R", self.p.repo, "--state", "open", "--author", "@me", "--limit", "20", "--json",
                         "number,title,headRefName,isDraft,labels,url,body,statusCheckRollup,reviewDecision,mergeable,commits,author"])
        return [{"number": d["number"], "title": d["title"], "branch": d["headRefName"], "draft": bool(d["isDraft"]),
                 "labels": [label["name"] for label in d.get("labels") or []], "url": d.get("url", ""),
                 "body": d.get("body") or "", "comments": [], "ci": summarize_checks(d.get("statusCheckRollup")),
                 "author": (d.get("author") or {}).get("login", ""), "author_name": (d.get("author") or {}).get("name", ""),
                 "review": d.get("reviewDecision") or "", "conflicts": d.get("mergeable") == "CONFLICTING",
                 "commit_authors": [(a.get("login"), a.get("email"), a.get("name"))
                                    for commit in d.get("commits") or [] for a in commit.get("authors") or []]} for d in data]

    def issues(self):
        cmd = ["gh", "issue", "list", "-R", self.p.repo, "--state", "open", "--limit", "100", "--json",
               "number,title,labels,url,comments"]
        if self.p.milestone:
            cmd += ["--milestone", self.p.milestone]
        if self.p.merge_by == "maintainer":  # the owner's issues: assigned to the owner, or opened by the owner and not assigned
            data = {}
            for extra in (["--assignee", "@me"], ["--author", "@me", "--search", "no:assignee"]):
                data.update({d["number"]: d for d in run_json(cmd + extra)})
            data = [data[number] for number in sorted(data)]
        else:
            data = run_json(cmd)
        return [{"number": d["number"], "title": d["title"], "url": d.get("url", ""),
                 "labels": [label["name"] for label in d.get("labels") or []], "comments": self._comments(d.get("comments"))}
                for d in data]

    # Intake: the whole project, not the milestone view of issues(); each call is one number of the intake block.
    def open_issue_labels(self):
        data = run_json(["gh", "issue", "list", "-R", self.p.repo, "--state", "open", "--limit", "1000", "--json", "number,labels"])
        return [{"number": d["number"], "labels": [label["name"] for label in d.get("labels") or []]} for d in data]

    def label_names(self):
        return {d["name"] for d in run_json(["gh", "label", "list", "-R", self.p.repo, "--limit", "1000", "--json", "name"])}

    def count_issues(self, state, field, since):
        stamp = since.strftime("%Y-%m-%dT%H:%M:%SZ")
        return len(run_json(["gh", "issue", "list", "-R", self.p.repo, "--state", state, "--search", f"{field}:>={stamp}",
                             "--limit", "1000", "--json", "number"]))

    def inbox_comments(self, number):
        data = run_json(["gh", "issue", "view", str(number), "-R", self.p.repo, "--json", "comments"])
        return self._comments(data.get("comments"))


CI_QUERY = "query($path: ID!) { project(fullPath: $path) { mergeRequests(state: opened, first: 100) { nodes { iid headPipeline { status } } } } }"


class GitLab:
    """glab api: the lists say how many user notes an item has, notes are fetched only for those;
    the CI state of all open MRs comes from one GraphQL call (REST per MR as the fallback)."""

    def __init__(self, project, host):
        self.p = project
        self.env = {"GITLAB_HOST": host} if host else {}
        self.base = f"projects/{quote(project.repo, safe='')}"

    def api(self, path):
        return run_json(["glab", "api", f"{self.base}/{path}"], self.env)

    def notes(self, path):
        """User notes of an MR or issue, oldest first; the newest 100 so that long threads keep their end."""
        raw = self.api(f"{path}/notes?sort=desc&order_by=created_at&per_page=100")
        return _chronological([_comment(n.get("body"), n.get("created_at"), f"#note_{n.get('id')}")
                               for n in raw if not n.get("system")])

    def ci_map(self):
        data = run_json(["glab", "api", "graphql", "-f", f"query={CI_QUERY}", "-f", f"path={self.p.repo}"], self.env)
        nodes = (((data.get("data") or {}).get("project") or {}).get("mergeRequests") or {}).get("nodes")
        if nodes is None:
            raise ToolError("glab: no merge request data in the GraphQL answer")
        return {int(n["iid"]): summarize_pipeline((n.get("headPipeline") or {}).get("status")) for n in nodes}

    def prs(self):
        own = self.p.merge_by == "maintainer"  # only our MRs; no notes, but commit authors and approval, fetched by complete_pr
        raw = self.api("merge_requests?state=opened&per_page=100" + ("&scope=created_by_me" if own else ""))
        try:
            ci = self.ci_map()
        except ToolError:
            ci = {}  # complete_pr asks the single MR instead
        found = [{"number": d["iid"], "title": d["title"], "branch": d["source_branch"],
                  "draft": bool(d.get("draft") or d.get("work_in_progress")), "labels": list(d.get("labels") or []),
                  "url": d.get("web_url", ""), "body": d.get("description") or "",
                  "comments": [] if own or not d.get("user_notes_count") else None, "ci": ci.get(d["iid"])} for d in raw]
        if own:
            for pr, d in zip(found, raw):
                pr.update({"author": (d.get("author") or {}).get("username", ""), "author_name": (d.get("author") or {}).get("name", ""),
                           "conflicts": bool(d.get("has_conflicts")), "commit_authors": None, "review": None})
        return found

    def issues(self):
        path = "issues?state=opened&per_page=100&order_by=created_at&sort=desc"
        if self.p.milestone:
            path += f"&milestone={quote(self.p.milestone, safe='')}"
        if self.p.merge_by == "maintainer":  # the owner's issues: assigned to the owner, or opened by the owner and not assigned
            data = {}
            for extra in ("&scope=assigned_to_me", "&scope=created_by_me&assignee_id=None"):
                data.update({d["iid"]: d for d in self.api(path + extra)})
            raw = [data[number] for number in sorted(data)]
        else:
            raw = self.api(path)
        return [{"number": d["iid"], "title": d["title"], "url": d.get("web_url", ""), "labels": list(d.get("labels") or []),
                 "comments": [] if not d.get("user_notes_count") else None} for d in raw]

    def paged(self, path, pages=10):
        """All entries of a list endpoint, 100 per page, at most `pages` pages."""
        found = []
        for page in range(1, pages + 1):
            part = self.api(f"{path}{'&' if '?' in path else '?'}per_page=100&page={page}")
            found += part
            if len(part) < 100:
                break
        return found

    # Intake: the whole project, not the milestone view of issues().
    def open_issue_labels(self):
        return [{"number": d["iid"], "labels": list(d.get("labels") or [])} for d in self.paged("issues?state=opened")]

    def label_names(self):
        return {d["name"] for d in self.paged("labels")}

    def count_issues(self, state, field, since):
        stamp = quote(since.strftime("%Y-%m-%dT%H:%M:%SZ"), safe="")
        if field == "created":
            return len(self.paged(f"issues?scope=all&created_after={stamp}"))
        closed = self.paged(f"issues?scope=all&state=closed&updated_after={stamp}")  # GitLab has no closed_after
        return sum(1 for d in closed if (_parse_time(d.get("closed_at")) or since - timedelta(days=1)) >= since)

    def inbox_comments(self, number):
        raw = self.paged(f"issues/{number}/notes?sort=asc&order_by=created_at")
        return _chronological([_comment(n.get("body"), n.get("created_at"), f"#note_{n.get('id')}") for n in raw if not n.get("system")])

    def complete_pr(self, pr):
        """Fetch what prs() left open (None): the notes and, without the GraphQL answer, the pipeline."""
        failure = None
        if pr["comments"] is None:
            try:
                pr["comments"] = self.notes(f"merge_requests/{pr['number']}")
            except ToolError as exc:
                failure = exc
        if pr["ci"] is None:
            try:
                mr = self.api(f"merge_requests/{pr['number']}")
                pr["ci"] = summarize_pipeline((mr.get("head_pipeline") or mr.get("pipeline") or {}).get("status"))
            except ToolError as exc:
                failure = failure or exc
        if pr.get("commit_authors", []) is None:
            try:
                commits = self.api(f"merge_requests/{pr['number']}/commits?per_page=100")
                pr["commit_authors"] = [(c.get("author_name"), c.get("author_email")) for c in commits]
            except ToolError as exc:
                failure = failure or exc
        if pr.get("review", "") is None:
            try:
                pr["review"] = "APPROVED" if self.api(f"merge_requests/{pr['number']}/approvals").get("approved") else ""
            except ToolError as exc:
                failure = failure or exc
        if failure:
            raise failure

    def issue_comments(self, number):
        return self.notes(f"issues/{number}")


def make_host(project):
    if project.host_cli == "gh":
        return GitHub(project)
    host = project.gitlab_host
    if not host and project.repo_path:
        try:
            host = remote_host(run_cmd(["git", "-C", project.repo_path, "remote", "get-url", "origin"]))
        except ToolError:
            host = ""
    return GitLab(project, host)


def git_identity(project) -> list:
    """The name and e-mail git commits under in the project's checkout: what our own commits carry."""
    found = []
    if not project.repo_path or not os.path.isdir(project.repo_path):
        return found
    for key in ("user.name", "user.email"):
        try:
            found.append(run_cmd(["git", "-C", project.repo_path, "config", key]).strip())
        except ToolError:
            pass
    return found


def collect_worktrees(project, now):
    if not project.repo_path or not os.path.isdir(project.repo_path):
        raise ToolError(f"REPO_PATH {project.repo_path or '(not set)'} is not a directory")
    found = []
    for wt in parse_worktrees(run_cmd(["git", "-C", project.repo_path, "worktree", "list", "--porcelain"])):
        match = WORKTREE_RE.search(os.path.basename(wt["path"].rstrip("/")))
        if not match:
            continue
        commit_ts = activity_ts = None
        if os.path.isdir(wt["path"]):
            try:
                commit_ts = float(run_cmd(["git", "-C", wt["path"], "log", "-1", "--format=%ct"]).strip() or "nan")
            except (ToolError, ValueError):
                commit_ts = None
            try:
                gitdir = run_cmd(["git", "-C", wt["path"], "rev-parse", "--absolute-git-dir"]).strip()
                stamps = [os.stat(os.path.join(gitdir, name)).st_mtime for name in ("index", "HEAD")
                          if os.path.exists(os.path.join(gitdir, name))]
                activity_ts = max(stamps) if stamps else None
            except (ToolError, OSError):
                activity_ts = None
        commit_age = (now.timestamp() - commit_ts) / 3600 if commit_ts and commit_ts == commit_ts else None
        newest = max((t for t in (commit_ts, activity_ts) if t and t == t), default=None)
        idle = (now.timestamp() - newest) / 3600 if newest else None
        found.append({"path": wt["path"], "name": os.path.basename(wt["path"].rstrip("/")), "kind": match.group(1),
                      "number": int(match.group(2)), "branch": wt["branch"], "missing": not os.path.isdir(wt["path"]),
                      "commit_age_hours": round(commit_age, 1) if commit_age is not None else None,
                      "idle_hours": round(idle, 1) if idle is not None else None, "pr": None})
    return found


def collect_locks(project, now, lock_dir, open_prs=None):
    locks = []
    pattern = os.path.join(glob.escape(lock_dir), glob.escape(project.name) + "-*.lock")
    for path in sorted(glob.glob(pattern)):
        try:
            info = Path(path, "info").read_text()
        except OSError:
            info = ""
        try:
            fallback = datetime.fromtimestamp(os.stat(path).st_mtime, timezone.utc)
        except OSError:
            fallback = None
        name = os.path.basename(path)[len(project.name) + 1:]
        # a triage lock names the inbox issue, not a PR: only its age can make it stale
        state = lock_state(info, now, project.lock_max, fallback=fallback, open_prs=None if name == "triage.lock" else open_prs)
        locks.append({"name": os.path.basename(path)[len(project.name) + 1:], "path": path, **state})
    return locks


def collect_intake(project, host, now) -> dict:
    """The findings-intake numbers of a project. Never raises: a call that fails leaves its number None and adds
    a note. `not_set_up` names what the project does not have yet: the inbox (no INBOX_ISSUE), the bundle label,
    the tier labels (none of the three exists on the host)."""
    out = {"days": INTAKE_DAYS, "created": None, "closed": None, "inbox": None, "bundles": None, "tiers": None,
           "not_set_up": [], "notes": []}

    def attempt(what, call):
        try:
            return call()
        except ToolError as exc:
            out["notes"].append(f"intake {what}: {exc}")
            return None

    since = now - timedelta(days=INTAKE_DAYS)
    out["created"] = attempt("created", lambda: host.count_issues("all", "created", since))
    out["closed"] = attempt("closed", lambda: host.count_issues("closed", "closed", since))
    if project.inbox_issue:
        comments = attempt(f"inbox #{project.inbox_issue}", lambda: host.inbox_comments(project.inbox_issue))
        if comments is not None:
            out["inbox"] = {"issue": int(project.inbox_issue), "open_lines": count_open_lines(comments)}
    else:
        out["not_set_up"].append("inbox")
    names = attempt("labels", host.label_names)
    issues = attempt("open issues", host.open_issue_labels)
    if names is not None:
        if project.bundle_label not in names:
            out["not_set_up"].append("bundles")
        if not any(label in names for label in project.tier_labels):
            out["not_set_up"].append("tiers")
    if issues is not None and names is not None:
        counts = intake_counts(issues, project)
        if "bundles" not in out["not_set_up"]:
            out["bundles"] = counts["bundles"]
        if "tiers" not in out["not_set_up"]:
            out["tiers"] = counts["tiers"]
    return out


def new_result(project):
    return {"name": project.name, "repo": project.repo, "host_cli": project.host_cli, "pr_abbr": project.pr_abbr,
            "main_branch": project.main_branch, "milestone": project.milestone or None, "lock_max_minutes": project.lock_max,
            "merge_by": project.merge_by, "waiting": [],
            "tier_labels": list(project.tier_labels), "inbox_label": project.inbox_label, "bundle_label": project.bundle_label,
            "intake": None,
            "errors": [], "notes": [], "prs": [], "issues": [], "worktrees": [], "locks": [],
            "prs_ok": False, "issues_ok": False}


def collect_project(project, now, include_issues=True, lock_dir="/tmp"):
    """Everything for one project. Never raises: problems land in result['errors']."""
    res = new_result(project)
    errors = res["errors"]
    try:
        _collect(project, now, include_issues, lock_dir, res)
    except Exception as exc:  # a bug or surprise in one project must not hide the others
        errors.append(f"{type(exc).__name__}: {exc}")
    return res


def _collect(project, now, include_issues, lock_dir, res):
    errors, abbr = res["errors"], project.pr_abbr
    remote = True
    if project.host_cli not in ("gh", "glab"):
        errors.append(f"HOST_CLI must be gh or glab, is '{project.host_cli}'")
        remote = False
    elif not project.repo:
        errors.append("REPO is missing in the project file")
        remote = False
    elif not shutil.which(project.host_cli):
        errors.append(f"{project.host_cli} not found in PATH")
        remote = False

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        wt_future = pool.submit(collect_worktrees, project, now)
        host = make_host(project) if remote else None
        pr_future = pool.submit(host.prs) if remote else None
        issue_future = pool.submit(host.issues) if remote and include_issues else None
        intake_future = pool.submit(collect_intake, project, host, now) if remote and include_issues and project.merge_by != "maintainer" else None

        worktrees = []
        try:
            worktrees = wt_future.result()
        except (ToolError, OSError) as exc:
            errors.append(str(exc))

        prs = []
        if pr_future:
            try:
                prs = pr_future.result()
                res["prs_ok"] = True
            except ToolError as exc:
                errors.append(f"{abbr} list: {exc}")
        issues = []
        if issue_future:
            try:
                issues = sorted(issue_future.result(), key=lambda i: i["number"])
                res["issues_ok"] = True
            except ToolError as exc:
                errors.append(f"issue list: {exc}")

        if intake_future:
            res["intake"] = intake_future.result()
            res["notes"] += res["intake"].pop("notes")

        if res["issues_ok"] and project.milestone and not issues:
            res["notes"].append(f"milestone '{project.milestone}' has no open issues (or the name is misspelled)")
        shown = issues
        if issues and not project.milestone and len(issues) > ISSUE_CAP:
            more = "+" if len(issues) >= 100 else ""
            res["notes"].append(f"showing the newest {ISSUE_CAP} of {len(issues)}{more} open issues (capped)")
            shown = issues[-ISSUE_CAP:]
        to_fetch = [i for i in shown if i["comments"] is None]
        if len(to_fetch) > ISSUE_CAP:
            res["notes"].append(f"comments fetched for {ISSUE_CAP} of {len(to_fetch)} issues that have some (capped)")
            to_fetch = to_fetch[:ISSUE_CAP]

        pr_jobs = {pool.submit(host.complete_pr, pr): pr for pr in prs
                   if pr["comments"] is None or pr["ci"] is None or pr.get("commit_authors", []) is None or pr.get("review", "") is None}
        issue_jobs = {pool.submit(host.issue_comments, i["number"]): i for i in to_fetch}
        for job in concurrent.futures.as_completed(list(pr_jobs) + list(issue_jobs)):
            try:
                result = job.result()
                if job in issue_jobs:
                    issue_jobs[job]["comments"] = result
            except ToolError as exc:
                target = pr_jobs.get(job)
                errors.append(f"{abbr} #{target['number']}: {exc}" if target else f"issue #{issue_jobs[job]['number']}: {exc}")

    upstream = project.merge_by == "maintainer"
    own = set(git_identity(project)) if upstream else set()
    for pr in prs:
        pr["ci"] = pr["ci"] or "unknown"
        found_comments = pr.pop("comments")
        if upstream:  # our PR waits for the maintainer: no kit markers, but who else committed to it
            pr["foreign_authors"] = foreign_authors(pr.pop("commit_authors", None) or [], own | {pr.get("author"), pr.get("author_name")})
            pr["taken_over"] = bool(pr["foreign_authors"])
            pr["review"] = pr.get("review") or ""
            pr["marker"], pr["marker_label"] = None, waiting_label(pr)
        else:
            pr["marker"] = classify_pr_comments(found_comments) if found_comments is not None else None
            pr["marker_label"] = marker_label(pr["marker"])
        pr["parked"] = "parked" in [label.lower() for label in pr["labels"]]
        pr["refs"] = issue_refs(pr["title"], pr.pop("body"), pr["branch"])
    res["prs"] = sorted(prs, key=lambda p: p["number"])
    if upstream:
        res["waiting"] = [pr["number"] for pr in res["prs"]]

    open_numbers = {pr["number"] for pr in prs}
    for wt in worktrees:
        if wt["kind"] == "review":
            wt["pr"] = wt["number"] if wt["number"] in open_numbers else None
        else:
            linked = [pr["number"] for pr in prs if (wt["branch"] and pr["branch"] == wt["branch"]) or wt["number"] in pr["refs"]]
            wt["pr"] = linked[0] if linked else None
    res["worktrees"] = worktrees

    issue_worktrees = {wt["number"] for wt in worktrees if wt["kind"] == "issue"}
    for issue in shown:
        linked = sorted({pr["number"] for pr in prs if issue["number"] in pr["refs"]}
                        | {wt["pr"] for wt in worktrees if wt["kind"] == "issue" and wt["number"] == issue["number"] and wt["pr"]})
        found_comments = issue.pop("comments")
        issue["pr_numbers"] = linked
        issue["checked"] = found_comments is not None
        issue["flags"] = issue_flags(found_comments or [], bool(linked), issue["number"] in issue_worktrees)
    res["issues"] = shown

    res["locks"] = collect_locks(project, now, lock_dir, open_numbers if res["prs_ok"] else None)


# ---------------------------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------------------------


def clip(text: str, width: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= width else text[: width - 1] + "…"


def intake_lines(intake) -> list:
    """The lines of the intake block; `?` for a number whose call failed, `not set up` for what the project lacks."""
    def number(value):
        return "?" if value is None else str(value)

    missing = intake["not_set_up"]
    lines = [f"issues created {number(intake['created'])}, closed {number(intake['closed'])} in the last {intake['days']} days"]
    if "inbox" in missing:
        lines.append("inbox: not set up")
    elif intake["inbox"] is None:
        lines.append("inbox: ?")
    else:
        count = intake["inbox"]["open_lines"]
        lines.append(f"inbox #{intake['inbox']['issue']}: {count} open line{'' if count == 1 else 's'}")
    if "bundles" in missing:
        lines.append("bundles: not set up")
    else:
        lines.append(f"bundles: {number(intake['bundles'])} open")
    if "tiers" in missing:
        lines.append("tiers: not set up")
    elif intake["tiers"] is None:
        lines.append("tiers: ?")
    else:
        lines.append("tiers (open): " + ", ".join(f"{label} {count}" for label, count in intake["tiers"].items()))
    return lines


def render_text(results, items) -> str:
    out = []
    for res in results:
        abbr = res["pr_abbr"]
        ms = res["milestone"] or "none"
        who = ", maintainer merges" if res["merge_by"] == "maintainer" else ""
        out.append(f"== {res['name']}  ({res['repo'] or '?'}, {res['host_cli']}, {res['main_branch'] or '?'}, milestone: {ms}{who})")
        for error in res["errors"]:
            out.append(f"  ! {error}")
        for note in res["notes"]:
            out.append(f"  note: {note}")
        if res["prs"] and res["merge_by"] == "maintainer":
            out.append(f"  Waiting for maintainer ({len(res['prs'])})")
            for pr in res["prs"]:
                flags = ("  DRAFT" if pr["draft"] else "") + ("  PARKED" if pr["parked"] else "")
                who = f" ({', '.join(pr['foreign_authors'])})" if pr["taken_over"] else ""
                out.append(f"    #{pr['number']:<5} {clip(pr['title'], 56):<56}  ci {pr['ci']:<7} {pr['marker_label']}{who}{flags}  [{pr['branch']}]")
        elif res["prs"]:
            out.append(f"  {abbr}s ({len(res['prs'])})")
            for pr in res["prs"]:
                flags = ("  DRAFT" if pr["draft"] else "") + ("  PARKED" if pr["parked"] else "")
                out.append(f"    #{pr['number']:<5} {clip(pr['title'], 56):<56}  ci {pr['ci']:<7} {clip(pr['marker_label'], 48)}{flags}  [{pr['branch']}]")
        elif res["prs_ok"]:
            out.append(f"  {abbr}s: none open")
        if res["issues"]:
            out.append(f"  Issues ({len(res['issues'])})")
            for issue in res["issues"]:
                flags = issue["flags"]
                tags = [name.replace("_", " ") for name in ("blocked", "question", "in_progress") if flags[name]]
                if flags["pr"]:
                    tags.insert(0, "pr " + ",".join(f"#{n}" for n in issue["pr_numbers"]))
                if not issue["checked"]:
                    tags.append("comments not checked")
                out.append(f"    #{issue['number']:<5} {clip(issue['title'], 60):<60}  {', '.join(tags)}")
        elif res["issues_ok"]:
            out.append("  Issues: none open")
        if res.get("intake"):
            out.append("  Intake")
            out += [f"    {line}" for line in intake_lines(res["intake"])]
        if res["worktrees"]:
            out.append("  Worktrees")
            for wt in res["worktrees"]:
                link = f"{abbr} #{wt['pr']}" if wt["pr"] else f"no open {abbr}"
                gone = "  MISSING DIR" if wt["missing"] else ""
                out.append(f"    {wt['name']:<28} {clip(wt['branch'] or '(detached)', 30):<30} idle {fmt_hours(wt['idle_hours'])}"
                           f", last commit {fmt_hours(wt['commit_age_hours'])} ago  {link}{gone}")
        if res["locks"]:
            out.append("  Locks")
            for lock in res["locks"]:
                state = f"STALE ({lock['note']})" if lock["stale"] else "ok" + (f" ({lock['note']})" if lock["note"] else "")
                out.append(f"    {lock['name']:<22} \"{lock['info']}\"  {fmt_age(lock['age_minutes'])} old, max {res['lock_max_minutes']}m  {state}")
        out.append("")
    out.append(f"Needs you ({len(items)})" if items else "Needs you: nothing")
    for item in items:
        url = f"  {item['url']}" if item["url"] else ""
        out.append(f"  [{item['project']}] {item['kind']}: {item['text']}{url}")
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Overview of the kit's session chains across projects (read-only).")
    parser.add_argument("projects", nargs="*", help="part of a project file name; default: the project of the current directory, the projects below it, else all")
    parser.add_argument("--all", action="store_true", help="all projects, even when run inside a project checkout")
    parser.add_argument("--json", action="store_true", help="print one JSON document instead of text")
    parser.add_argument("--no-issues", action="store_true", help="skip the issue list (faster; no issue flags or chain check)")
    args = parser.parse_args(argv)

    root = config_root()
    names = list(args.projects)
    if not names and not args.all:
        names = projects_here(root, Path.cwd())
    projects = load_projects(root, names)
    if not projects:
        where = f"{root / 'briefs'}/*.env"
        print(f"no project file matches {' '.join(args.projects)!r} in {where}" if args.projects else f"no project files in {where}",
              file=sys.stderr)
        return 1
    for name in names:
        if not any(name.lower() in p.stem.lower() for p in projects):
            print(f"warning: no project file name contains {name!r}", file=sys.stderr)

    now = datetime.now(timezone.utc)
    lock_dir = os.environ.get("PROJECT_KIT_LOCK_DIR", "/tmp")
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(projects)) as pool:
        results = list(pool.map(lambda p: collect_project(p, now, not args.no_issues, lock_dir), projects))
    items = needs_you(results)
    if args.json:
        print(json.dumps({"generated": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "projects": results, "needs_you": items},
                         indent=2, ensure_ascii=False))
    else:
        sys.stdout.write(render_text(results, items))
    return 0


if __name__ == "__main__":
    sys.exit(main())
