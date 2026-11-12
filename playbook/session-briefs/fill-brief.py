#!/usr/bin/env python3
"""Fill a session brief with a project's values.

The two briefs in this folder start with a placeholder table. This script reads that table,
takes the values from a per-project file outside the repository
(~/.config/project-kit/briefs/<project>.env) and prints everything below the brief's `---`
with the placeholders filled in, optionally straight into the clipboard. Placeholders a
session fills at run time (such as <PR_NO> in the issue brief) are not in the table and stay.

    fill-brief.py init [<repo-path>]                    write the project file with derived values and TODOs
    fill-brief.py check [<project>]                     list keys that are still missing or TODO
    fill-brief.py issue [<project>] <issue-no> [--milestone T] [--handover "after merge"|"after PR"] [--copy]
    fill-brief.py maintainer [<project>] <pr-no> [--copy]

<project> is a checkout path or a project name that matches one file in the config folder
(a unique part of the name is enough, e.g. "shop"). Left out, it is the project whose
checkout contains the current directory.

Values given on the command line win over the project file; the project file wins over the
derived defaults. Nothing here touches the repository.

The briefs hold conditional blocks, each marker on a line of its own, no nesting:

    <!-- if MERGE_BY=maintainer -->
    text kept when the project file says MERGE_BY=maintainer
    <!-- else -->
    text kept for every other value (optional; without it nothing is kept)
    <!-- endif -->

The marker lines are dropped and one branch stays, so with MERGE_BY=session (the default, also for a
project file without the key) a brief renders exactly as it did before the blocks existed.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KIT_PATH = HERE.parent.parent
BRIEFS = {"issue": HERE / "issue-session.md", "maintainer": HERE / "maintainer-session.md"}
CONFIG_DIR = Path(os.environ.get("PROJECT_KIT_CONFIG", Path.home() / ".config" / "project-kit")) / "briefs"
TODO = "TODO"
MERGE_BY_VALUES = ("session", "maintainer")
MERGE_ONLY = ("MERGE_METHOD", "LOCK_MAX")  # with MERGE_BY=maintainer these need a value only where a brief still names them
CONDITIONAL = re.compile(
    r"^<!-- if (\w+)=(\w+) -->\n(.*?)^(?:<!-- else -->\n(.*?))?<!-- endif -->(?:\n|\Z)", re.M | re.S)
MARKER = re.compile(r"^<!-- (?:if \w+=\w+|else|endif) -->", re.M)

# Keys the owner fills once per project, with the help text written into the project file.
PROJECT_KEYS = [
    ("PROJECT_NAME", "short project name; also the prefix of the /tmp locks"),
    ("REPO", "owner/name on GitHub or group/project on GitLab"),
    ("HOST_CLI", "gh or glab"),
    ("HOST_PR_ABBR", "PR (GitHub) or MR (GitLab)"),
    ("HOST_ISSUE_TEMPLATE", "path of the issue template in the project"),
    ("HOST_PR_TEMPLATE", "path of the PR/MR template in the project"),
    ("TEST_CMD", "command behind make test"),
    ("LINT_CMD", "command behind make lint"),
    ("SUITE_DURATION", "how long make test takes, e.g. 'two minutes'"),
    ("TEST_DB", "how the test database is provided, or 'none'"),
    ("LOCK_RULE", "how shared test resources are serialized, or 'none: tests use isolated resources'"),
    ("ACCEPTANCE_ENV", "how the acceptance environment is started and stopped, and whether it is isolated per run"),
    ("UI_EVIDENCE", "the evidence required for UI changes"),
    ("PRODUCTION_TABOOS", "what is never touched: containers, volumes, databases, hosts, releases, keys"),
    ("BLOCKER_CATEGORIES", "finding categories still fixed after the scope freeze: data loss or corruption, wrong core results, access across users or tenants, data protection"),
    ("REPO_PATH", "absolute path of the main checkout"),
    ("KIT_PATH", "absolute path of this kit"),
    ("MAIN_BRANCH", "main, master, develop ..."),
    ("MERGE_METHOD", "squash or merge"),
    ("MERGE_BY", "'session' (the issue session merges its own PR) or 'maintainer' (upstream: someone else merges; the session hands over and never merges)"),
    ("LOCAL_GATE", "gates the CI cannot run, or 'none'"),
    ("LOCK_MAX", "twice SUITE_DURATION plus 30 minutes, e.g. '34 minutes'"),
    ("MILESTONE", "default milestone for issue chains, or 'none'"),
    ("HANDOVER", "'after merge' (one issue at a time) or 'after PR' (parallel chain)"),
]


def run(cmd, cwd=None):
    try:
        return subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def table_keys(brief: Path):
    """Placeholder names from the brief's table: <NAME> and {{NAME}} in the first cell."""
    keys = []
    for line in brief.read_text().splitlines():
        if line == "---":
            break
        if not line.startswith("| `"):
            continue
        cell = line.split("|")[1]
        keys += re.findall(r"<([A-Z_]+)>|\{\{([A-Z_]+)\}\}", cell)
    return [a or b for a, b in keys]


def derive(repo: Path):
    """Values that can be read from the checkout; the rest is TODO."""
    values = {k: TODO for k, _ in PROJECT_KEYS}
    values["PROJECT_NAME"] = repo.name
    values["REPO_PATH"] = str(repo)
    values["KIT_PATH"] = str(KIT_PATH)
    values["MERGE_METHOD"] = "squash"
    values["LOCAL_GATE"] = "none"
    values["HANDOVER"] = "after merge"
    values["MERGE_BY"] = "session"
    values["MILESTONE"] = "none"
    url = run(["git", "-C", str(repo), "remote", "get-url", "origin"])
    m = re.match(r"(?:git@|https?://)([^:/]+)[:/](.+?)(?:\.git)?$", url)
    if m:
        host, path = m.group(1), m.group(2)
        values["REPO"] = path
        if host == "github.com":
            values["HOST_CLI"], values["HOST_PR_ABBR"] = "gh", "PR"
            if (repo / ".github/ISSUE_TEMPLATE/task.md").exists():
                values["HOST_ISSUE_TEMPLATE"] = ".github/ISSUE_TEMPLATE/task.md"
            if (repo / ".github/PULL_REQUEST_TEMPLATE.md").exists():
                values["HOST_PR_TEMPLATE"] = ".github/PULL_REQUEST_TEMPLATE.md"
        else:
            values["HOST_CLI"], values["HOST_PR_ABBR"] = "glab", "MR"
            if (repo / ".gitlab/issue_templates/Default.md").exists():
                values["HOST_ISSUE_TEMPLATE"] = ".gitlab/issue_templates/Default.md"
            if (repo / ".gitlab/merge_request_templates/Default.md").exists():
                values["HOST_PR_TEMPLATE"] = ".gitlab/merge_request_templates/Default.md"
    head = run(["git", "-C", str(repo), "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"])
    if head.startswith("origin/"):
        values["MAIN_BRANCH"] = head[len("origin/"):]
    makefile = repo / "Makefile"
    if makefile.exists():
        targets = set(re.findall(r"^([a-zA-Z_-]+):", makefile.read_text(), re.M))
        if "test" in targets:
            values["TEST_CMD"] = "make test"
        if "lint" in targets:
            values["LINT_CMD"] = "make lint"
    return values


def config_path(repo: Path) -> Path:
    return CONFIG_DIR / f"{repo.name}.env"


def repo_here(cwd: Path):
    """The registered checkout that contains `cwd`, else None; `below` lists the projects under a workspace folder."""
    cwd = Path(cwd).resolve()
    repo_here.below = []
    for f in sorted(CONFIG_DIR.glob("*.env")):
        repo = read_config(f).get("REPO_PATH", "")
        if not repo:
            continue
        repo = Path(repo).resolve()
        if repo in (cwd, *cwd.parents):
            return repo
        if cwd in repo.parents:
            repo_here.below.append(f.stem)
    return None


def resolve_repo(arg) -> Path:
    """A checkout path, a project name that matches exactly one project file, or (None) the project of the current directory."""
    if arg is None:
        here = repo_here(Path.cwd())
        if here is None:
            names = ", ".join(repo_here.below) or ", ".join(p.stem for p in sorted(CONFIG_DIR.glob("*.env"))) or "none yet (run init <repo-path>)"
            sys.exit(f"not inside a registered project; name one: {names}")
        return here
    path = Path(arg).expanduser()
    if (path / ".git").exists():
        return path.resolve()
    hits = sorted(p for p in CONFIG_DIR.glob("*.env") if arg.lower() in p.stem.lower())
    exact = [p for p in hits if p.stem.lower() == arg.lower()]
    hits = exact or hits
    if len(hits) != 1:
        names = ", ".join(p.stem for p in sorted(CONFIG_DIR.glob("*.env"))) or "none yet (run init <repo-path>)"
        sys.exit(f"{arg!r} is neither a checkout nor exactly one project; projects: {names}")
    repo = Path(read_config(hits[0]).get("REPO_PATH", ""))
    if not (repo / ".git").exists():
        sys.exit(f"{hits[0]}: REPO_PATH {repo} is not a checkout")
    return repo


def read_config(path: Path):
    values = {}
    if not path.exists():
        return values
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def write_config(path: Path, values):
    lines = [
        f"# Values for the session briefs of {values['PROJECT_NAME']}, read by fill-brief.py.",
        "# One KEY=value per line. Replace every TODO; quotes are optional.",
        "",
    ]
    for key, help_text in PROJECT_KEYS:
        lines.append(f"# {help_text}")
        lines.append(f"{key}={values[key]}")
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))


def missing(values, keys):
    return [k for k in keys if values.get(k, TODO) in ("", TODO)]


def merge_by_error(values):
    """Why the project's MERGE_BY is not usable, or ''."""
    if values["MERGE_BY"] in MERGE_BY_VALUES:
        return ""
    return f"MERGE_BY must be {' or '.join(MERGE_BY_VALUES)}, is {values['MERGE_BY']!r}"


def resolve_conditionals(body, values):
    """Keep the branch of every `<!-- if KEY=value -->` block that the project's values select."""
    def pick(match):
        key, expected, then, otherwise = match.groups()
        if key not in values:
            sys.exit(f"conditional block on unknown key {key}")
        return then if values[key] == expected else (otherwise or "")

    body = CONDITIONAL.sub(pick, body)
    if MARKER.search(body):
        sys.exit("unbalanced conditional marker in the brief")
    return body


def brief_body(kind, values):
    """The brief below its separator, conditional blocks resolved, placeholders still in place."""
    if merge_by_error(values):
        sys.exit(merge_by_error(values))
    return resolve_conditionals(BRIEFS[kind].read_text().split("\n---\n", 1)[1], values)


def names(text, key):
    return f"<{key}>" in text or f"{{{{{key}}}}}" in text


def fill(kind, values):
    brief = BRIEFS[kind]
    keys = table_keys(brief)
    body = brief_body(kind, values)
    gaps = missing(values, keys)
    if values["MERGE_BY"] != "session":
        gaps = [k for k in gaps if k not in MERGE_ONLY or names(body, k)]
    if gaps:
        sys.exit(f"missing or TODO: {', '.join(gaps)} (edit {config_path(Path(values['REPO_PATH']))})")
    for key in keys:
        body = body.replace(f"<{key}>", values[key]).replace(f"{{{{{key}}}}}", values[key])
    left = [k for k in keys if names(body, k)]
    if left:
        sys.exit(f"placeholders left after filling: {', '.join(left)}")
    return body.lstrip("\n")


def copy_to_clipboard(text):
    for tool in (["pbcopy"], ["wl-copy"], ["xclip", "-selection", "clipboard"]):
        if shutil.which(tool[0]):
            subprocess.run(tool, input=text, text=True, check=True)
            return tool[0]
    return None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_init = sub.add_parser("init", help="write the project file with derived values and TODOs")
    p_init.add_argument("repo", nargs="?", default=".", help="the checkout to register; default: the current directory")
    p_init.add_argument("--force", action="store_true", help="overwrite an existing project file")
    p_check = sub.add_parser("check", help="list keys that are still missing or TODO")
    p_check.add_argument("repo", nargs="?", help="project name or checkout; default: the project of the current directory")
    for kind, number in (("issue", "issue_no"), ("maintainer", "pr_no")):
        p = sub.add_parser(kind, help=f"fill the {kind} brief")
        p.add_argument("repo", nargs="?", help="project name or checkout; default: the project of the current directory")
        p.add_argument(number, type=int)
        p.add_argument("--copy", action="store_true", help="copy the brief to the clipboard instead of printing it")
        p.add_argument("--out", help="write the brief to this file")
        if kind == "issue":
            p.add_argument("--milestone", help="milestone the next issue comes from, or 'none'")
            p.add_argument("--handover", choices=["after merge", "after PR"], help="when the successor session starts")
    args = parser.parse_args(argv)
    if args.cmd == "init":
        repo = Path(args.repo).expanduser().resolve()
        if not (repo / ".git").exists():
            sys.exit(f"{repo} is not a git checkout")
    else:
        repo = resolve_repo(args.repo)
    path = config_path(repo)

    if args.cmd == "init":
        if path.exists() and not args.force:
            sys.exit(f"{path} exists; edit it, or run init --force to rebuild it from the checkout")
        values = derive(repo)
        write_config(path, values)
        todo = missing(values, [k for k, _ in PROJECT_KEYS])
        print(f"wrote {path}")
        print(f"fill in: {', '.join(todo)}" if todo else "no TODOs left")
        return

    values = {**{k: TODO for k, _ in PROJECT_KEYS}, "MERGE_BY": "session", **read_config(path)}
    if args.cmd == "check":
        if merge_by_error(values):
            sys.exit(f"{path}: {merge_by_error(values)}")
        todo = missing(values, [k for k, _ in PROJECT_KEYS])
        if values["MERGE_BY"] != "session":
            text = "".join(brief_body(kind, values) for kind in BRIEFS)
            todo = [k for k in todo if k not in MERGE_ONLY or names(text, k)]
        print(f"{path}: " + (f"fill in {', '.join(todo)}" if todo else "complete"))
        return

    if args.cmd == "issue":
        values["TASK"] = f"Issue #{args.issue_no}"
        if args.milestone:
            values["MILESTONE"] = args.milestone
        if args.handover:
            values["HANDOVER"] = args.handover
    else:
        values["PR_NO"] = str(args.pr_no)
    text = fill(args.cmd, values)

    if args.out:
        Path(args.out).write_text(text)
        print(f"wrote {args.out} ({len(text)} bytes)", file=sys.stderr)
    if args.copy:
        tool = copy_to_clipboard(text)
        if tool:
            print(f"copied {len(text)} bytes to the clipboard with {tool}; paste into a new, empty chat in {repo}", file=sys.stderr)
        else:
            sys.exit("no clipboard tool found (pbcopy, wl-copy, xclip); use --out or print")
    if not args.out and not args.copy:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
