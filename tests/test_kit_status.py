"""Tests for playbook/session-briefs/kit-status.py. Offline: the classification functions run on small
fixtures, and the end-to-end run uses fake `gh` / `glab` programs on PATH plus real local git repositories."""

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "playbook" / "session-briefs" / "kit-status.py"


def load_module():
    spec = importlib.util.spec_from_file_location("kit_status", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["kit_status"] = module
    spec.loader.exec_module(module)
    return module


ks = load_module()
NOW = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)


def c(body, **extra):
    return {"body": body, **extra}


class ClassifyPrCommentsTest(unittest.TestCase):
    def kind(self, *bodies):
        return ks.classify_pr_comments([c(b) for b in bodies])

    def test_no_marker_means_no_review_yet(self):
        marker = self.kind()
        self.assertEqual(marker["kind"], "none")
        self.assertEqual(ks.marker_label(marker), "no review yet")
        self.assertEqual(self.kind("looks good", "please rebase")["kind"], "none")

    def test_newest_round_wins_and_keeps_k(self):
        marker = self.kind("Round 1 of at most 5 pushed (`abc`):\n\nFindings", "thanks", "Round 2 of at most 5 pushed (`def`)")
        self.assertEqual((marker["kind"], marker["round"]), ("round", 2))
        self.assertEqual(ks.marker_label(marker), "Round 2")
        self.assertEqual(marker["line"], "Round 2 of at most 5 pushed (`def`)")

    def test_not_merged_keeps_its_first_line(self):
        marker = self.kind("Round 3 of at most 5 pushed", "Not merged: user check pending (owner).\n\nState: CI green")
        self.assertEqual(marker["kind"], "not_merged")
        self.assertEqual(marker["line"], "Not merged: user check pending (owner).")
        self.assertEqual(ks.marker_label(marker), "Not merged: user check pending (owner).")

    def test_a_later_round_supersedes_an_earlier_not_merged(self):
        marker = self.kind("Not merged: parked.", "Round 4 of at most 5 pushed")
        self.assertEqual((marker["kind"], marker["round"]), ("round", 4))

    def test_merged_and_blocked(self):
        self.assertEqual(self.kind("Round 1 of at most 5 pushed", "Merged after 2 rounds (abc123).")["kind"], "merged")
        self.assertEqual(self.kind("Merged as is (abc123).")["kind"], "merged")
        marker = self.kind("Blocked: waiting for the base MR")
        self.assertEqual((marker["kind"], marker["line"]), ("blocked", "Blocked: waiting for the base MR"))

    def test_only_comments_that_start_with_a_marker_count(self):
        self.assertEqual(self.kind("I think round 2 was fine")["kind"], "none")
        self.assertEqual(self.kind("Merged origin/main into the branch")["kind"], "none")
        self.assertEqual(self.kind("Rounding errors in the total")["kind"], "none")
        self.assertEqual(self.kind("See below.\nNot merged: x")["kind"], "none")

    def test_markdown_decoration_and_case_are_tolerated(self):
        self.assertEqual(self.kind("**Round 2** of at most 5 pushed")["round"], 2)
        self.assertEqual(self.kind("## Not merged: red CI")["kind"], "not_merged")
        self.assertEqual(self.kind("  not merged: red CI")["kind"], "not_merged")

    def test_url_of_the_marker_comment_is_kept(self):
        marker = ks.classify_pr_comments([c("Round 1 of at most 5", url="https://x/1"), c("noise", url="https://x/2")])
        self.assertEqual(marker["url"], "https://x/1")


class IssueFlagsTest(unittest.TestCase):
    def flags(self, *bodies, pr=False, wt=False):
        return ks.issue_flags([c(b) for b in bodies], pr, wt)

    def test_plain_issue_has_no_flags(self):
        flags = self.flags("some discussion")
        self.assertEqual({k: v for k, v in flags.items() if k != "note"},
                         {"pr": False, "blocked": False, "question": False, "in_progress": False})

    def test_pr_and_worktree_are_passed_through(self):
        flags = self.flags(pr=True, wt=True)
        self.assertTrue(flags["pr"])
        self.assertTrue(flags["in_progress"])

    def test_blocked_until_an_owner_decision_follows(self):
        self.assertTrue(self.flags("Blocked: spec is wrong")["blocked"])
        self.assertEqual(self.flags("Blocked: spec is wrong")["note"], "Blocked: spec is wrong")
        for decision in ("Owner decision: use option (a)", "## Owner decision\n\nOption B", "**Decision:** (1) a now, follow-up #9",
                         "Owner decision (7 November 2026): approved"):
            with self.subTest(decision=decision):
                self.assertFalse(self.flags("Blocked: x", decision)["blocked"])

    def test_a_decision_before_the_block_does_not_unblock(self):
        self.assertTrue(self.flags("Owner decision: a", "Blocked: new problem")["blocked"])

    def test_other_comments_do_not_unblock(self):
        self.assertTrue(self.flags("Blocked: x", "any news?", "Round 1 of at most 5")["blocked"])

    def test_question_comment_is_a_question_not_blocked(self):
        flags = self.flags("Questions before implementation. The rest is being implemented without them.\n\n1. ...")
        self.assertTrue(flags["question"])
        self.assertFalse(flags["blocked"])
        self.assertTrue(flags["note"].startswith("Questions before implementation"))

    def test_blocked_owner_decision_is_both_and_a_decision_clears_both(self):
        asked = "Blocked: owner decision needed on the questions below.\n\n1. ..."
        flags = self.flags(asked)
        self.assertTrue(flags["blocked"] and flags["question"])
        flags = self.flags(asked, "**Decision:** (1) option (a)")
        self.assertFalse(flags["blocked"] or flags["question"])
        self.assertEqual(flags["note"], "")

    def test_older_owner_decision_needed_is_a_question_not_an_answer(self):
        asked = "**Owner decision needed:** whether the second factor is mandatory."
        self.assertTrue(self.flags(asked)["question"])
        self.assertFalse(self.flags(asked, "## Owner decision — 5 November\n\nMandatory.")["question"])

    def test_question_after_a_resolved_block_is_open_again(self):
        flags = self.flags("Blocked: x", "Owner decision: a", "Questions before implementation.\n\n1. ...")
        self.assertTrue(flags["question"])
        self.assertFalse(flags["blocked"])


class LockStateTest(unittest.TestCase):
    def info(self, pr, minutes_ago):
        return f"{pr} {(NOW - timedelta(minutes=minutes_ago)).strftime('%Y-%m-%dT%H:%M:%SZ')}\n"

    def test_fresh_lock_is_not_stale(self):
        state = ks.lock_state(self.info(42, 7), NOW, 34)
        self.assertEqual((state["pr"], state["age_minutes"], state["stale"]), (42, 7, False))

    def test_older_than_lock_max_is_stale(self):
        state = ks.lock_state(self.info(42, 35), NOW, 34)
        self.assertTrue(state["stale"])
        self.assertIn("34", state["note"])
        self.assertFalse(ks.lock_state(self.info(42, 34), NOW, 34)["stale"])

    def test_lock_naming_a_closed_pr_is_a_remnant_after_thirty_minutes(self):
        self.assertTrue(ks.lock_state(self.info(42, 31), NOW, 120, open_prs={7})["stale"])
        self.assertFalse(ks.lock_state(self.info(42, 29), NOW, 120, open_prs={7})["stale"])
        self.assertFalse(ks.lock_state(self.info(42, 31), NOW, 120, open_prs={42})["stale"])
        self.assertFalse(ks.lock_state(self.info(42, 31), NOW, 120)["stale"])  # open PRs unknown

    def test_unreadable_info_uses_the_fallback_or_stays_unjudged(self):
        state = ks.lock_state("garbage", NOW, 30, fallback=NOW - timedelta(minutes=50))
        self.assertTrue(state["stale"])
        self.assertEqual(state["age_minutes"], 50)
        state = ks.lock_state("", NOW, 30)
        self.assertEqual((state["age_minutes"], state["stale"]), (None, False))

    def test_lock_max_parsing(self):
        self.assertEqual(ks.parse_lock_max("34 minutes"), 34)
        self.assertEqual(ks.parse_lock_max("34"), 34)
        self.assertEqual(ks.parse_lock_max("2 hours"), 120)
        for bad in (None, "", "TODO", "soon", "0 minutes"):
            self.assertEqual(ks.parse_lock_max(bad), 120)

    def test_collect_locks_reads_both_lock_directories_of_a_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name, text in (("demo-merge.lock", self.info(5, 90)), ("demo-acceptance.lock", self.info(6, 3))):
                (Path(tmp) / name).mkdir()
                (Path(tmp) / name / "info").write_text(text)
            (Path(tmp) / "demo-merge.lock.stale.5").mkdir()  # moved-away remnant: not a lock
            (Path(tmp) / "other-merge.lock").mkdir()
            project = ks.project_from_env({"PROJECT_NAME": "demo", "LOCK_MAX": "30 minutes"}, "demo")
            locks = {lock["name"]: lock for lock in ks.collect_locks(project, NOW, tmp)}
        self.assertEqual(sorted(locks), ["acceptance.lock", "merge.lock"])
        self.assertTrue(locks["merge.lock"]["stale"])
        self.assertFalse(locks["acceptance.lock"]["stale"])


class SmallParsersTest(unittest.TestCase):
    def test_summarize_checks(self):
        ok = {"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "SUCCESS"}
        skipped = {"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "SKIPPED"}
        running = {"__typename": "CheckRun", "status": "IN_PROGRESS", "conclusion": ""}
        failed = {"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "FAILURE"}
        self.assertEqual(ks.summarize_checks([]), "none")
        self.assertEqual(ks.summarize_checks(None), "none")
        self.assertEqual(ks.summarize_checks([skipped]), "none")
        self.assertEqual(ks.summarize_checks([ok, skipped]), "green")
        self.assertEqual(ks.summarize_checks([ok, running]), "pending")
        self.assertEqual(ks.summarize_checks([ok, running, failed]), "red")
        self.assertEqual(ks.summarize_checks([{"__typename": "StatusContext", "state": "SUCCESS"}]), "green")
        self.assertEqual(ks.summarize_checks([{"__typename": "StatusContext", "state": "PENDING"}]), "pending")
        self.assertEqual(ks.summarize_checks([{"__typename": "StatusContext", "state": "ERROR"}]), "red")
        self.assertEqual(ks.summarize_checks([{"status": "COMPLETED", "conclusion": "CANCELLED"}]), "red")

    def test_summarize_pipeline(self):
        for status, expected in (("success", "green"), ("SUCCESS", "green"), ("failed", "red"), ("CANCELED", "red"),
                                 ("running", "pending"), ("PENDING", "pending"), ("manual", "pending"),
                                 (None, "none"), ("skipped", "none")):
            self.assertEqual(ks.summarize_pipeline(status), expected, status)

    def test_parse_worktrees(self):
        text = ("worktree /w/demo\nHEAD aaa\nbranch refs/heads/main\n\n"
                "worktree /w/demo-issue-7\nHEAD bbb\nbranch refs/heads/feat/seven\n\n"
                "worktree /w/demo-review-9\nHEAD ccc\ndetached\n")
        entries = ks.parse_worktrees(text)
        self.assertEqual([e["path"] for e in entries], ["/w/demo", "/w/demo-issue-7", "/w/demo-review-9"])
        self.assertEqual([e["branch"] for e in entries], ["main", "feat/seven", None])
        self.assertEqual(entries[1]["head"], "bbb")

    def test_remote_host(self):
        for url, host in (("git@git.example.org:acme/api.git", "git.example.org"),
                          ("ssh://git@gitlab.example.com:2222/g/p.git", "gitlab.example.com"),
                          ("https://user:tok@gitlab.com/g/p.git", "gitlab.com"),
                          ("https://github.com/o/r", "github.com"), ("", "")):
            self.assertEqual(ks.remote_host(url), host, url)

    def test_issue_refs(self):
        self.assertEqual(ks.issue_refs("feat: x (#12)", "Closes #34\nSee #12 and PR!5", "feat/x"), [12, 34])
        self.assertEqual(ks.issue_refs("t", "", "issue-9"), [9])
        self.assertEqual(ks.issue_refs("t", "", "codex/issue-33-eu-checkout"), [33])
        self.assertEqual(ks.issue_refs("t", "tissue-4 and a#5 and url/#6", "reissue-3"), [])


class ConfigTest(unittest.TestCase):
    def test_parse_env_ignores_comments_and_quotes(self):
        env = ks.parse_env("# comment\n\nPROJECT_NAME=demo\nREPO = 'acme/demo'\nMILESTONE=\"M 1\"\nnot a pair\n")
        self.assertEqual(env, {"PROJECT_NAME": "demo", "REPO": "acme/demo", "MILESTONE": "M 1"})

    def test_project_from_env_normalizes(self):
        project = ks.project_from_env({"PROJECT_NAME": "demo", "REPO": "acme/demo", "HOST_CLI": "glab", "MILESTONE": "none",
                                       "LOCK_MAX": "TODO", "REPO_PATH": "/x/demo"}, "demo-file")
        self.assertEqual((project.name, project.host_cli, project.pr_abbr, project.milestone, project.lock_max),
                         ("demo", "glab", "MR", "", 120))
        self.assertEqual(ks.project_from_env({"MILESTONE": "M1"}, "stem").milestone, "M1")
        self.assertEqual(ks.project_from_env({}, "stem").name, "stem")

    def test_load_projects_filters_by_file_name_and_honors_config_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            briefs = Path(tmp) / "briefs"
            briefs.mkdir()
            for stem in ("acme-web", "acme-api", "billing"):
                (briefs / f"{stem}.env").write_text(f"PROJECT_NAME={stem}\nREPO=acme/{stem}\n")
            (briefs / "notes.txt").write_text("PROJECT_NAME=ignored\n")
            self.assertEqual([p.name for p in ks.load_projects(Path(tmp))], ["acme-api", "acme-web", "billing"])
            self.assertEqual([p.name for p in ks.load_projects(Path(tmp), ["acme"])], ["acme-api", "acme-web"])
            self.assertEqual([p.name for p in ks.load_projects(Path(tmp), ["WEB", "bill"])], ["acme-web", "billing"])
            self.assertEqual(ks.load_projects(Path(tmp), ["nothing"]), [])
            old = os.environ.get("PROJECT_KIT_CONFIG")
            os.environ["PROJECT_KIT_CONFIG"] = tmp
            try:
                self.assertEqual(ks.config_root(), Path(tmp))
            finally:
                if old is None:
                    del os.environ["PROJECT_KIT_CONFIG"]
                else:
                    os.environ["PROJECT_KIT_CONFIG"] = old


def project_result(**extra):
    base = {"name": "demo", "pr_abbr": "PR", "milestone": None, "errors": [], "prs": [], "issues": [], "worktrees": [],
            "locks": [], "prs_ok": True, "issues_ok": True}
    base.update(extra)
    return base


def issue(number, title="t", **flags):
    merged = {"pr": False, "blocked": False, "question": False, "in_progress": False, "note": ""}
    merged.update(flags)
    return {"number": number, "title": title, "url": f"https://h/i/{number}", "flags": merged, "checked": True}


def pr(number, kind="none", line="", **extra):
    base = {"number": number, "title": f"pr {number}", "url": f"https://h/p/{number}", "parked": False,
            "marker": {"kind": kind, "round": None, "line": line, "url": ""}}
    base.update(extra)
    return base


def worktree(number, **extra):
    base = {"name": f"demo-issue-{number}", "path": f"/w/demo-issue-{number}", "kind": "issue", "number": number,
            "pr": None, "idle_hours": 1.0, "commit_age_hours": 1.0}
    base.update(extra)
    return base


class NeedsYouTest(unittest.TestCase):
    def kinds(self, *projects):
        return [(i["project"], i["kind"]) for i in ks.needs_you(projects)]

    def test_quiet_project_needs_nothing(self):
        self.assertEqual(ks.needs_you([project_result(prs=[pr(1, "round")], issues=[issue(2)])]), [])

    def test_blocked_issue_and_open_question_with_urls(self):
        items = ks.needs_you([project_result(issues=[issue(3, "blocked one", blocked=True, question=True, note="Blocked: owner decision needed"),
                                                      issue(4, "asks", question=True), issue(5)])])
        self.assertEqual([(i["kind"], i["url"]) for i in items], [("blocked", "https://h/i/3"), ("question", "https://h/i/4")])
        self.assertIn("Blocked: owner decision needed", items[0]["text"])

    def test_not_merged_with_reason_and_parked_label(self):
        items = ks.needs_you([project_result(prs=[pr(7, "not_merged", "Not merged: user check pending (owner)."),
                                                  pr(8, "round", parked=True), pr(9, "blocked", "Blocked: base missing")])])
        self.assertEqual([i["kind"] for i in items], ["not_merged", "pr_blocked", "parked"])
        self.assertIn("Not merged: user check pending (owner).", items[0]["text"])
        self.assertEqual(items[0]["url"], "https://h/p/7")

    def test_stale_lock_only_when_stale(self):
        lock = {"name": "merge.lock", "path": "/tmp/demo-merge.lock", "info": "5 2026-11-09T09:00:00Z", "age_minutes": 180,
                "stale": True, "note": "older than 120 minutes"}
        items = ks.needs_you([project_result(locks=[lock, {**lock, "name": "acceptance.lock", "stale": False}])])
        self.assertEqual([i["kind"] for i in items], ["stale_lock"])
        self.assertIn("merge.lock", items[0]["text"])

    def test_orphan_claim_needs_old_issue_worktree_without_pr(self):
        projects = project_result(worktrees=[worktree(1, idle_hours=30), worktree(2, idle_hours=30, pr=9), worktree(3, idle_hours=3),
                                             worktree(4, idle_hours=30, kind="review")])
        items = ks.needs_you([projects])
        self.assertEqual([(i["kind"], i["url"]) for i in items], [("orphan", "/w/demo-issue-1")])
        self.assertEqual(ks.needs_you([{**projects, "prs_ok": False}]), [])  # PR list unknown: no verdict

    def test_orphan_uses_idle_time_not_only_the_last_commit(self):
        fresh_claim = worktree(1, idle_hours=0.5, commit_age_hours=300)
        self.assertEqual(ks.needs_you([project_result(worktrees=[fresh_claim])]), [])

    def test_chain_ended_needs_a_milestone_no_pr_no_work_and_a_free_issue(self):
        base = dict(milestone="M1", issues=[issue(1, blocked=True), issue(2, "next one"), issue(3)])
        items = ks.needs_you([project_result(**base)])
        self.assertEqual([i["kind"] for i in items], ["blocked", "chain_ended"])
        self.assertIn("#2 next one", items[1]["text"])
        self.assertEqual(self.kinds(project_result(**{**base, "milestone": None})), [("demo", "blocked")])
        self.assertNotIn(("demo", "chain_ended"), self.kinds(project_result(**{**base, "prs": [pr(10)]})))
        self.assertNotIn(("demo", "chain_ended"), self.kinds(project_result(**{**base, "worktrees": [worktree(2)]})))
        self.assertNotIn(("demo", "chain_ended"), self.kinds(project_result(**{**base, "issues": [issue(1, blocked=True), issue(2, pr=True)]})))
        self.assertNotIn(("demo", "chain_ended"), self.kinds(project_result(**{**base, "issues_ok": False})))

    def test_errors_are_listed_first_per_project(self):
        items = ks.needs_you([project_result(name="a", errors=["glab: 401 Unauthorized"], issues=[issue(1, blocked=True)]),
                              project_result(name="b", issues=[issue(2, question=True)])])
        self.assertEqual([(i["project"], i["kind"]) for i in items], [("a", "error"), ("a", "blocked"), ("b", "question")])


# ---------------------------------------------------------------------------------------------
# End to end with fake CLIs
# ---------------------------------------------------------------------------------------------

FAKE_GH = '''#!{python}
import json, sys
args = sys.argv[1:]
repo = args[args.index("-R") + 1] if "-R" in args else ""
NOW = {now!r}
def ago(minutes):
    import datetime
    return (datetime.datetime.strptime(NOW, "%Y-%m-%dT%H:%M:%SZ") - datetime.timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")
ok = {{"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "SUCCESS"}}
bad = {{"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "FAILURE"}}
def comment(body, minutes):
    return {{"body": body, "createdAt": ago(minutes), "url": "https://gh/c"}}
DATA = {{
  "acme/demo": {{
    "pr": [
      {{"number": 20, "title": "feat: eight", "headRefName": "feat/eight", "isDraft": False, "labels": [], "url": "https://gh/pull/20",
        "body": "Closes #8", "statusCheckRollup": [ok],
        "comments": [comment("Round 2 of at most 5 pushed (`abc`)", 5), comment("Round 1 of at most 5 pushed (`abb`)", 50)]}},
      {{"number": 21, "title": "fix: parked", "headRefName": "fix/parked", "isDraft": True, "labels": [{{"name": "parked"}}],
        "url": "https://gh/pull/21", "body": "", "statusCheckRollup": [ok, bad],
        "comments": [comment("Not merged: CI red for reasons outside the diff.\\n\\nState: CI red", 10)]}},
    ],
    "issue": [
      {{"number": 5, "title": "blocked issue", "labels": [], "url": "https://gh/issues/5",
        "comments": [comment("Blocked: owner decision needed on the questions below.\\n\\n1. ...", 30)]}},
      {{"number": 6, "title": "asks a question", "labels": [], "url": "https://gh/issues/6",
        "comments": [comment("Questions before implementation. The rest is being implemented without them.", 30)]}},
      {{"number": 7, "title": "claimed long ago", "labels": [], "url": "https://gh/issues/7", "comments": []}},
      {{"number": 8, "title": "has a pr", "labels": [], "url": "https://gh/issues/8", "comments": []}},
      {{"number": 9, "title": "answered", "labels": [], "url": "https://gh/issues/9",
        "comments": [comment("Blocked: x", 90), comment("## Owner decision\\n\\nGo ahead.", 60)]}},
    ],
  }},
  "acme/empty": {{"pr": [], "issue": [
      {{"number": 1, "title": "next in line", "labels": [], "url": "https://gh/issues/1", "comments": []}}]}},
}}
if repo not in DATA:
    sys.stderr.write("GraphQL: Could not resolve to a Repository with the name '" + repo + "'. (repository)\\n")
    sys.exit(1)
if args[:2] == ["pr", "list"]:
    print(json.dumps(DATA[repo]["pr"]))
elif args[:2] == ["issue", "list"]:
    milestone = args[args.index("--milestone") + 1] if "--milestone" in args else "M1"
    if milestone not in ("M1", "M2"):
        sys.stderr.write("no milestone found with the title or number '" + milestone + "'\\n")
        sys.exit(1)
    print(json.dumps(DATA[repo]["issue"] if milestone == "M1" else []))
else:
    sys.stderr.write("fake gh: unexpected " + " ".join(args) + "\\n")
    sys.exit(2)
'''

FAKE_GLAB = '''#!{python}
import json, os, sys
args = sys.argv[1:]
if args[0] != "api" or os.environ.get("GITLAB_HOST") != "gitlab.example.test":
    sys.stderr.write("401 Unauthorized (GITLAB_HOST=%s)\\n" % os.environ.get("GITLAB_HOST"))
    sys.exit(1)
path = args[1]
def note(body, created, system=False, id=1):
    return {{"id": id, "body": body, "created_at": created, "system": system}}
if path == "graphql":
    print(json.dumps({{"data": {{"project": {{"mergeRequests": {{"nodes": [
        {{"iid": "3", "headPipeline": {{"status": "FAILED"}}}}, {{"iid": "4", "headPipeline": None}}]}}}}}}}}))
elif path.startswith("projects/acme%2Fgl/merge_requests?"):
    print(json.dumps([
        {{"iid": 3, "title": "Draft: fix: three", "source_branch": "fix/three", "draft": True, "labels": ["parked"],
          "web_url": "https://gl/mr/3", "description": "Refs #2", "user_notes_count": 2}},
        {{"iid": 4, "title": "feat: four", "source_branch": "feat/four", "draft": False, "labels": [],
          "web_url": "https://gl/mr/4", "description": "", "user_notes_count": 0}}]))
elif path.startswith("projects/acme%2Fgl/merge_requests/3/notes?") and "sort=desc" in path:
    print(json.dumps([note("Not merged: waiting for the owner.", "2026-11-09T11:00:00.000Z", id=3),
                      note("added 1 commit", "2026-11-09T10:30:00.000Z", True, 2),
                      note("Round 1 of at most 5 pushed", "2026-11-09T10:00:00.000Z", id=1)]))
elif path.startswith("projects/acme%2Fgl/issues?"):
    print(json.dumps([{{"iid": 2, "title": "gl blocked", "labels": [], "web_url": "https://gl/issues/2", "user_notes_count": 1}},
                      {{"iid": 1, "title": "gl quiet", "labels": [], "web_url": "https://gl/issues/1", "user_notes_count": 0}}]))
elif path.startswith("projects/acme%2Fgl/issues/2/notes?"):
    print(json.dumps([note("Blocked: spec is wrong", "2026-11-09T09:00:00.000Z")]))
else:
    sys.stderr.write("fake glab: unexpected " + path + "\\n")
    sys.exit(2)
'''


def git(*args, cwd=None, env=None):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t.test", *args], cwd=cwd, check=True,
                   capture_output=True, env={**os.environ, **(env or {})})


class EndToEndTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = self.base = Path(self.tmp.name)
        now = datetime.now(timezone.utc).replace(microsecond=0)
        self.now = now
        stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")

        bin_dir = base / "bin"
        bin_dir.mkdir()
        for name, template in (("gh", FAKE_GH), ("glab", FAKE_GLAB)):
            program = bin_dir / name
            program.write_text(template.format(python=sys.executable, now=stamp))
            program.chmod(0o755)

        # demo: a repository with an old orphan claim (issue 7), a fresh claim with a PR (issue 8), a review checkout
        demo = base / "demo"
        demo.mkdir()
        git("init", "-q", "-b", "main", str(demo))
        old = {"GIT_AUTHOR_DATE": "2020-01-01T00:00:00Z", "GIT_COMMITTER_DATE": "2020-01-01T00:00:00Z"}
        git("commit", "--allow-empty", "-q", "-m", "init", cwd=demo, env=old)
        git("worktree", "add", "-q", "../demo-issue-7", "-b", "issue-7", cwd=demo)
        git("worktree", "add", "-q", "../demo-issue-8", "-b", "feat/eight", cwd=demo)
        git("worktree", "add", "-q", "--detach", "../demo-review-21", cwd=demo)
        # issue 7 was claimed five days ago: its git admin files are old too; issue 8 and the review checkout stay fresh
        for name in ("demo-issue-7", "demo-review-21"):
            for part in ("index", "HEAD"):
                target = demo / ".git" / "worktrees" / name / part
                if target.exists():
                    os.utime(target, (0, 0))
        self.demo = demo

        empty = base / "empty"
        empty.mkdir()
        git("init", "-q", "-b", "main", str(empty))
        gl = base / "gl"
        gl.mkdir()
        git("init", "-q", "-b", "main", str(gl))
        git("remote", "add", "origin", "git@gitlab.example.test:acme/gl.git", cwd=gl)

        self.lock_dir = base / "locks"
        self.lock_dir.mkdir()
        for name, minutes, pr_no in (("kitdemo-merge.lock", 100, 20), ("kitdemo-acceptance.lock", 5, 21)):
            (self.lock_dir / name).mkdir()
            (self.lock_dir / name / "info").write_text(f"{pr_no} {(now - timedelta(minutes=minutes)).strftime('%Y-%m-%dT%H:%M:%SZ')}\n")

        briefs = base / "config" / "briefs"
        briefs.mkdir(parents=True)
        projects = {
            "demo": f"PROJECT_NAME=kitdemo\nREPO=acme/demo\nHOST_CLI=gh\nHOST_PR_ABBR=PR\nREPO_PATH={demo}\nMAIN_BRANCH=main\nMILESTONE=M1\nLOCK_MAX=30 minutes\n",
            "empty": f"PROJECT_NAME=kitempty\nREPO=acme/empty\nHOST_CLI=gh\nHOST_PR_ABBR=PR\nREPO_PATH={empty}\nMAIN_BRANCH=main\nMILESTONE=M1\nLOCK_MAX=TODO\n",
            "gitlab": f"PROJECT_NAME=kitgl\nREPO=acme/gl\nHOST_CLI=glab\nHOST_PR_ABBR=MR\nREPO_PATH={gl}\nMAIN_BRANCH=main\nMILESTONE=none\nLOCK_MAX=TODO\n",
            "broken": f"PROJECT_NAME=kitbroken\nREPO=acme/nowhere\nHOST_CLI=gh\nHOST_PR_ABBR=PR\nREPO_PATH={base / 'missing'}\nMAIN_BRANCH=main\nMILESTONE=none\nLOCK_MAX=TODO\n",
        }
        for stem, text in projects.items():
            (briefs / f"{stem}.env").write_text(text)
        self.env = {**os.environ, "PROJECT_KIT_CONFIG": str(base / "config"), "PROJECT_KIT_LOCK_DIR": str(self.lock_dir),
                    "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}

    def tearDown(self):
        self.tmp.cleanup()

    def run_script(self, *args, env=None, expect=0):
        proc = subprocess.run([sys.executable, str(SCRIPT), *args], env=env or self.env, capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, expect, proc.stdout + proc.stderr)
        return proc

    def document(self, *args):
        return json.loads(self.run_script("--json", *args).stdout)

    def test_github_project_end_to_end(self):
        doc = self.document("demo")
        self.assertEqual([p["name"] for p in doc["projects"]], ["kitdemo"])
        project = doc["projects"][0]
        self.assertEqual(project["errors"], [])
        prs = {p["number"]: p for p in project["prs"]}
        self.assertEqual((prs[20]["ci"], prs[20]["marker_label"], prs[20]["draft"], prs[20]["parked"]), ("green", "Round 2", False, False))
        self.assertEqual((prs[21]["ci"], prs[21]["marker"]["kind"], prs[21]["draft"], prs[21]["parked"]), ("red", "not_merged", True, True))
        issues = {i["number"]: i for i in project["issues"]}
        self.assertTrue(issues[5]["flags"]["blocked"] and issues[5]["flags"]["question"])
        self.assertTrue(issues[6]["flags"]["question"] and not issues[6]["flags"]["blocked"])
        self.assertTrue(issues[7]["flags"]["in_progress"] and not issues[7]["flags"]["pr"])
        self.assertTrue(issues[8]["flags"]["pr"] and issues[8]["flags"]["in_progress"])
        self.assertEqual(issues[8]["pr_numbers"], [20])
        self.assertFalse(issues[9]["flags"]["blocked"])
        worktrees = {w["name"]: w for w in project["worktrees"]}
        self.assertEqual(sorted(worktrees), ["demo-issue-7", "demo-issue-8", "demo-review-21"])
        self.assertEqual(worktrees["demo-issue-8"]["pr"], 20)
        self.assertIsNone(worktrees["demo-issue-7"]["pr"])
        self.assertEqual(worktrees["demo-review-21"]["pr"], 21)
        self.assertGreater(worktrees["demo-issue-7"]["idle_hours"], 24)
        self.assertLess(worktrees["demo-issue-8"]["idle_hours"], 2)  # fresh claim although the commit is from 2020
        self.assertGreater(worktrees["demo-issue-8"]["commit_age_hours"], 24)
        locks = {lock["name"]: lock for lock in project["locks"]}
        self.assertTrue(locks["merge.lock"]["stale"])  # 100 minutes > LOCK_MAX 30
        self.assertFalse(locks["acceptance.lock"]["stale"])
        self.assertEqual(locks["merge.lock"]["pr"], 20)
        kinds = [item["kind"] for item in doc["needs_you"]]
        self.assertEqual(kinds, ["stale_lock", "blocked", "question", "not_merged", "parked", "orphan"])
        urls = {item["kind"]: item["url"] for item in doc["needs_you"]}
        self.assertEqual((urls["blocked"], urls["not_merged"]), ("https://gh/issues/5", "https://gh/pull/21"))

    def test_text_output_has_blocks_and_a_needs_you_section(self):
        out = self.run_script("demo").stdout
        self.assertIn("== kitdemo", out)
        self.assertIn("Round 2", out)
        self.assertIn("PARKED", out)
        self.assertIn("demo-issue-7", out)
        self.assertIn("STALE", out)
        needs = out.split("Needs you")[-1]
        self.assertIn("[kitdemo] not_merged:", needs)
        self.assertIn("Not merged: CI red for reasons outside the diff.", needs)
        self.assertIn("https://gh/issues/5", needs)

    def test_chain_that_looks_ended_is_reported(self):
        doc = self.document("empty")
        self.assertEqual([i["kind"] for i in doc["needs_you"]], ["chain_ended"])
        self.assertIn("#1 next in line", doc["needs_you"][0]["text"])

    def test_gitlab_project_uses_note_counts_graphql_ci_and_remote_host(self):
        project = self.document("gitlab")["projects"][0]
        self.assertEqual(project["errors"], [])
        mrs = {m["number"]: m for m in project["prs"]}
        self.assertEqual((mrs[3]["ci"], mrs[3]["marker"]["kind"], mrs[3]["draft"], mrs[3]["parked"]), ("red", "not_merged", True, True))
        self.assertEqual((mrs[4]["ci"], mrs[4]["marker_label"]), ("none", "no review yet"))  # no notes, none requested
        issues = {i["number"]: i for i in project["issues"]}
        self.assertTrue(issues[2]["flags"]["blocked"])
        self.assertEqual(issues[2]["pr_numbers"], [3])  # MR 3 says "Refs #2"
        self.assertFalse(issues[1]["flags"]["blocked"])

    def test_errors_stay_in_their_project_and_do_not_stop_the_run(self):
        doc = self.document("broken", "demo")
        broken = next(p for p in doc["projects"] if p["name"] == "kitbroken")
        demo = next(p for p in doc["projects"] if p["name"] == "kitdemo")
        self.assertTrue(any("is not a directory" in e for e in broken["errors"]))
        self.assertTrue(any("acme/nowhere" in e for e in broken["errors"]))
        self.assertEqual(demo["errors"], [])
        self.assertIn(("kitbroken", "error"), [(i["project"], i["kind"]) for i in doc["needs_you"]])
        text = self.run_script("broken").stdout
        self.assertIn("  ! ", text)

    def test_missing_cli_is_an_error_not_a_crash(self):
        only_git = self.base / "only-git"
        only_git.mkdir()
        (only_git / "git").write_text(f'#!/bin/sh\nexec "{shutil.which("git")}" "$@"\n')
        (only_git / "git").chmod(0o755)
        env = {**self.env, "PATH": str(only_git)}
        doc = json.loads(self.run_script("--json", "demo", env=env).stdout)
        project = doc["projects"][0]
        self.assertTrue(any("gh not found" in e for e in project["errors"]))
        self.assertEqual(len(project["worktrees"]), 3)  # the local part still works

    def with_milestone(self, milestone):
        briefs = self.base / "config" / "briefs"
        text = re.sub(r"^MILESTONE=.*$", f"MILESTONE={milestone}", (briefs / "empty.env").read_text(), flags=re.M)
        (briefs / "empty.env").write_text(text)
        return self.document("empty")["projects"][0]

    def test_milestone_without_open_issues_is_noted_and_unknown_one_is_an_error(self):
        project = self.with_milestone("M2")
        self.assertEqual(project["issues"], [])
        self.assertTrue(any("'M2' has no open issues" in n for n in project["notes"]))
        project = self.with_milestone("M9")
        self.assertTrue(any("no milestone found" in e for e in project["errors"]))

    def test_no_issues_skips_the_issue_list(self):
        project = self.document("demo", "--no-issues")["projects"][0]
        self.assertEqual(project["issues"], [])
        self.assertEqual(len(project["prs"]), 2)
        self.assertNotIn("chain_ended", [i["kind"] for i in self.document("empty", "--no-issues")["needs_you"]])

    def test_unknown_project_exits_one(self):
        proc = self.run_script("nothing-like-this", expect=1)
        self.assertIn("no project file matches", proc.stderr)


if __name__ == "__main__":
    unittest.main()
