"""Contract test for playbook/session-briefs/fill-brief.py: table placeholders are filled,
run-time placeholders stay, missing values are refused, the conditional blocks of MERGE_BY
leave a project that merges its own PRs with exactly the brief it always had, and the findings
intake (inbox issue, labels, the triage brief) is known to init, check and every brief."""

import importlib.util
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BRIEFS = ROOT / "playbook" / "session-briefs"
SCRIPT = BRIEFS / "fill-brief.py"


def load_module():
    spec = importlib.util.spec_from_file_location("fill_brief", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fb = load_module()


def without_maintainer_blocks(text):
    """The body of a brief as a project that merges its own PRs gets it, written without fill-brief's regex: marker
    lines dropped, what lies between `if` and `else` (or `endif`) dropped, the rest kept."""
    keep, state = [], None
    for line in text.split("\n---\n", 1)[1].splitlines(keepends=True):
        if re.fullmatch(r"<!-- if MERGE_BY=maintainer -->\n", line):
            state = "maintainer"
        elif line == "<!-- else -->\n":
            state = None
        elif line == "<!-- endif -->\n":
            state = None
        elif state is None:
            keep.append(line)
    return "".join(keep)


class FillBriefTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.repo = base / "demo-project"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        subprocess.run(["git", "-C", str(self.repo), "remote", "add", "origin",
                        "git@github.com:acme/demo-project.git"], check=True)
        (self.repo / "Makefile").write_text("test:\n\ttrue\nlint:\n\ttrue\n")
        (self.repo / ".github/ISSUE_TEMPLATE").mkdir(parents=True)
        (self.repo / ".github/ISSUE_TEMPLATE/task.md").write_text("x")
        (self.repo / ".github/PULL_REQUEST_TEMPLATE.md").write_text("x")
        self.env = {**os.environ, "PROJECT_KIT_CONFIG": str(base / "config")}
        self.config = base / "config" / "briefs" / "demo-project.env"

    def tearDown(self):
        self.tmp.cleanup()

    def run_script(self, *args, expect=0):
        proc = subprocess.run([sys.executable, str(SCRIPT), *args], env=self.env,
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, expect, proc.stdout + proc.stderr)
        return proc

    def complete_config(self):
        text = self.config.read_text()
        text = re.sub(r"^(\w+)=TODO$", lambda m: f"{m.group(1)}={'34' if m.group(1) == 'INBOX_ISSUE' else 'value for ' + m.group(1)}", text, flags=re.M)
        self.config.write_text(text)

    def test_init_derives_host_and_templates_and_refuses_overwrite(self):
        out = self.run_script("init", str(self.repo)).stdout
        self.assertIn("wrote", out)
        text = self.config.read_text()
        self.assertIn("HOST_CLI=gh", text)
        self.assertIn("HOST_PR_ABBR=PR", text)
        self.assertIn("REPO=acme/demo-project", text)
        self.assertIn("HOST_ISSUE_TEMPLATE=.github/ISSUE_TEMPLATE/task.md", text)
        self.assertIn("TEST_CMD=make test", text)
        self.assertIn("HANDOVER=after merge", text)
        self.assertIn("MERGE_BY=session", text)
        self.run_script("init", str(self.repo), expect=1)

    def test_issue_brief_refuses_todos_then_fills_only_table_placeholders(self):
        self.run_script("init", str(self.repo))
        proc = self.run_script("issue", str(self.repo), "7", expect=1)
        self.assertIn("missing or TODO", proc.stderr)
        self.complete_config()
        text = self.run_script("issue", str(self.repo), "7", "--milestone", "M1",
                               "--handover", "after PR").stdout
        self.assertIn("**Issue #7**", text)
        self.assertIn("after PR", text)
        self.assertIn('--milestone "M1"', text)
        self.assertNotIn("{{", text)
        for key in ("TASK", "REPO_PATH", "KIT_PATH", "MAIN_BRANCH", "MILESTONE", "HANDOVER",
                    "MERGE_METHOD", "LOCAL_GATE", "LOCK_MAX"):
            self.assertNotIn(f"<{key}>", text)
        # run-time placeholders the session fills stay
        self.assertIn("<PR_NO>", text)
        self.assertIn("<ISSUE_NO>", text)
        self.assertIn("<WORKTREE_PATH>", text)
        self.assertFalse(text.startswith("\n"))
        self.assertNotIn("| Placeholder |", text)

    def test_init_writes_the_intake_keys_with_their_defaults(self):
        self.run_script("init", str(self.repo))
        values = fb.read_config(self.config)
        self.assertEqual((values["INBOX_LABEL"], values["BUNDLE_LABEL"]), ("inbox", "bundle"))
        self.assertEqual((values["TIER_1_LABEL"], values["TIER_2_LABEL"], values["TIER_3_LABEL"]), ("tier:1", "tier:2", "tier:3"))
        self.assertEqual(values["INBOX_ISSUE"], "TODO")  # no default: the project creates its inbox issue
        self.assertIn("fill in:", self.run_script("init", str(self.repo), "--force").stdout)
        self.assertIn("INBOX_ISSUE", self.run_script("init", str(self.repo), "--force").stdout)

    def test_a_project_file_that_predates_the_intake_needs_only_the_inbox_issue(self):
        self.run_script("init", str(self.repo))
        self.complete_config()
        for key in ("INBOX_LABEL", "BUNDLE_LABEL", "TIER_1_LABEL", "TIER_2_LABEL", "TIER_3_LABEL", "INBOX_ISSUE"):
            self.set_key(key)  # an old file knows none of the keys
        self.assertEqual(self.run_script("check", "demo").stdout.split(": ", 1)[1].strip(), "fill in INBOX_ISSUE")
        self.assertIn("missing or TODO: INBOX_ISSUE", self.run_script("issue", "demo", "7", expect=1).stderr)
        self.set_key("INBOX_ISSUE", "34")
        self.assertIn("complete", self.run_script("check", "demo").stdout)
        text = self.run_script("issue", "demo", "7").stdout
        self.assertIn("issue #34 (label `inbox`)", text)  # the defaults filled the labels
        self.assertIn("`tier:1`", text)
        self.assertIn("`bundle`", text)

    def test_the_inbox_issue_is_a_bare_number(self):
        self.run_script("init", str(self.repo))
        self.complete_config()
        self.set_key("INBOX_ISSUE", "#34")
        self.assertIn("INBOX_ISSUE must be the issue number", self.run_script("check", "demo", expect=1).stderr)
        for kind, args in (("issue", ("7",)), ("maintainer", ("42",)), ("triage", ())):
            self.assertIn("INBOX_ISSUE must be the issue number", self.run_script(kind, "demo", *args, expect=1).stderr)

    def test_intake_keys_reach_the_briefs(self):
        self.run_script("init", str(self.repo))
        self.complete_config()
        self.set_key("INBOX_ISSUE", "58")
        self.set_key("BUNDLE_LABEL", "class")
        self.set_key("TIER_2_LABEL", "p2")
        for text in (self.render("issue", "7"), self.render("maintainer", "42"), self.run_script("triage", "demo").stdout):
            self.assertIn("#58", text)
            self.assertIn("`class`", text)
            self.assertNotIn("{{", text)
            self.assertNotIn("<INBOX_ISSUE>", text)
        self.assertIn("`p2`", self.render("issue", "7"))
        self.assertIn("`p2`", self.run_script("triage", "demo").stdout)

    def test_the_issue_brief_orders_by_tier_and_records_findings(self):
        self.run_script("init", str(self.repo))
        self.complete_config()
        text = self.render("issue", "7")
        for needle in ("The order is the tier, not the issue number", "every issue without one of the labels", "are never picked",
                       "Issues labelled `bundle` are ordinary work items", "## Findings", "you file at most one new issue per", "Finding line"):
            self.assertIn(needle, text)
        self.assertNotIn("the order is the issue number", text)
        self.assertIn("Recorded: <n> line(s)", text)  # the merge comment names what was recorded where

    def test_a_project_whose_maintainer_merges_records_findings_in_the_report_and_needs_no_inbox(self):
        self.run_script("init", str(self.repo))
        self.complete_config()
        self.set_key("MERGE_BY", "maintainer")
        self.set_key("INBOX_ISSUE", "TODO")
        issue, maintainer = self.render("issue", "7"), self.render("maintainer", "42")
        for text in (issue, maintainer):
            self.assertNotIn("inbox", text.lower().replace("no inbox", ""))
            self.assertIn("Finding line", text)
        self.assertIn("goes into the final report as one line", issue)
        self.assertIn("the order is the issue number", issue)  # no tiers in a tracker that is not ours
        self.assertIn("complete", self.run_script("check", "demo").stdout)
        self.set_key("MERGE_BY", "session")
        self.assertIn("missing or TODO: INBOX_ISSUE", self.run_script("maintainer", "demo", "42", expect=1).stderr)

    def test_triage_brief_is_filled_and_refused_where_the_maintainer_merges(self):
        self.run_script("init", str(self.repo))
        self.complete_config()
        text = self.run_script("triage", "demo").stdout
        self.assertTrue(text.startswith("You are the triage session for demo"))
        self.assertNotIn("| Placeholder |", text)
        self.assertNotIn("<!--", text)
        for key in fb.table_keys(BRIEFS / "triage-session.md"):
            self.assertNotIn(f"<{key}>", text)
            self.assertNotIn(f"{{{{{key}}}}}", text)
        self.assertEqual(text, self.reference_triage())
        self.assertIn("empty the inbox, issue #34", text)
        self.assertIn("/tmp/demo-project-triage.lock", text)
        self.assertEqual(self.run_script("triage", str(self.repo)).stdout, text)  # a checkout path instead of the name
        self.set_key("MERGE_BY", "maintainer")
        self.assertIn("triage needs MERGE_BY=session", self.run_script("triage", "demo", expect=1).stderr)
        self.assertIn("complete", self.run_script("check", "demo").stdout)  # check leaves the unusable brief out

    def reference_triage(self):
        values = fb.read_config(self.config)
        body = (BRIEFS / "triage-session.md").read_text().split("\n---\n", 1)[1]
        for key in fb.table_keys(BRIEFS / "triage-session.md"):
            body = body.replace(f"<{key}>", values[key]).replace(f"{{{{{key}}}}}", values[key])
        return body.lstrip("\n")

    def test_placeholder_tables_are_complete(self):
        """Every placeholder a brief uses outside its table is in the table (or filled at run time), and every key of a
        table that the project file supplies is one `init` knows."""
        runtime = {"PR_NO", "ISSUE_NO", "WORKTREE_PATH", "SHA"}
        project_keys = {key for key, _ in fb.PROJECT_KEYS}
        for kind, brief in fb.BRIEFS.items():
            with self.subTest(brief=kind):
                text = brief.read_text()
                table_keys = set(fb.table_keys(brief))
                body = text.split("\n---\n", 1)[1]
                used = {a or b for a, b in re.findall(r"<([A-Z][A-Z0-9_]+)>|\{\{([A-Z][A-Z0-9_]+)\}\}", body)}
                self.assertEqual(used - table_keys - runtime, set())
                self.assertEqual(table_keys - used, set(), "a table row for a placeholder the brief never uses")
                self.assertEqual({k for k in table_keys if k not in project_keys} - {"TASK", "PR_NO"} - {"DEFAULT_BRANCH"}, set())
        for key in ("INBOX_ISSUE", "INBOX_LABEL", "BUNDLE_LABEL", "TIER_1_LABEL", "TIER_2_LABEL", "TIER_3_LABEL"):
            self.assertIn(key, project_keys)
            self.assertIn(key, fb.table_keys(BRIEFS / "issue-session.md"))
            self.assertIn(key, fb.table_keys(BRIEFS / "triage-session.md"))

    def test_maintainer_brief_fills_pr_number(self):
        self.run_script("init", str(self.repo))
        self.complete_config()
        text = self.run_script("maintainer", "demo", "42").stdout  # project name instead of path
        here = subprocess.run([sys.executable, str(SCRIPT), "maintainer", "42"], env=self.env, cwd=self.repo,
                              capture_output=True, text=True)  # no project: the checkout of the cwd
        self.assertEqual(here.returncode, 0, here.stderr)
        self.assertEqual(here.stdout, text)
        self.assertIn("#42", text)
        self.assertNotIn("<PR_NO>", text)
        self.assertNotIn("{{", text)
        self.assertNotIn("<HANDOVER>", text)

    def render(self, kind, number):
        return self.run_script(kind, "demo", number).stdout

    def set_key(self, key, value=None):
        """Set `key` in the project file; None removes the line."""
        text = re.sub(rf"^{key}=.*\n", "", self.config.read_text(), flags=re.M)
        self.config.write_text(text if value is None else text + f"{key}={value}\n")

    def reference(self, kind, number):
        """The brief file without its maintainer blocks, filled the way a project file fills it."""
        values = {**fb.read_config(self.config), "TASK": f"Issue #{number}", "PR_NO": str(number)}
        body = without_maintainer_blocks((BRIEFS / f"{kind}-session.md").read_text())
        for key in fb.table_keys(BRIEFS / f"{kind}-session.md"):
            body = body.replace(f"<{key}>", values[key]).replace(f"{{{{{key}}}}}", values[key])
        return body.lstrip("\n")

    def test_a_project_that_merges_its_own_prs_gets_the_brief_without_the_blocks(self):
        self.run_script("init", str(self.repo))
        self.complete_config()
        for kind, number in (("issue", "7"), ("maintainer", "42")):
            with self.subTest(kind=kind):
                expected = self.reference(kind, number)
                self.set_key("MERGE_BY", "session")
                self.assertEqual(self.render(kind, number), expected)
                self.set_key("MERGE_BY")  # a project file that never heard of the key
                self.assertNotIn("MERGE_BY=", self.config.read_text())
                self.assertEqual(self.render(kind, number), expected)
                self.assertNotIn("<!--", expected)
                self.assertNotIn("{{", expected)
                self.assertIn("Merge under the lock", expected)

    def test_a_project_whose_maintainer_merges_gets_the_other_branch(self):
        self.run_script("init", str(self.repo))
        self.complete_config()
        self.set_key("MERGE_BY", "maintainer")
        issue, maintainer = self.render("issue", "7"), self.render("maintainer", "42")
        for text in (issue, maintainer):
            self.assertNotIn("<!--", text)
            self.assertNotIn("Merge under the lock", text)
            self.assertNotIn("{{", text)
            self.assertIn("Hands off", text)
        self.assertIn("Hand over to the maintainer", issue)
        self.assertIn("## Maintainer mode", issue)
        self.assertNotIn("Merged <after k round(s)", issue)  # the "Merged" and "Not merged" comment patterns are gone
        self.assertIn("Fresh review (prompt for the `verifier`", issue)  # what both modes share stays
        self.assertIn("**Issue #7**", issue)
        self.assertIn("#42", maintainer)

    def test_merge_by_must_name_a_mode(self):
        self.run_script("init", str(self.repo))
        self.complete_config()
        self.set_key("MERGE_BY", "owner")
        self.assertIn("MERGE_BY must be session or maintainer", self.run_script("check", "demo", expect=1).stderr)
        self.assertIn("MERGE_BY must be session or maintainer", self.run_script("issue", "demo", "7", expect=1).stderr)
        self.set_key("MERGE_BY", "maintainer")
        self.assertIn("complete", self.run_script("check", "demo").stdout)

    def test_merge_only_keys_need_a_value_only_when_a_brief_still_names_them(self):
        self.run_script("init", str(self.repo))
        self.complete_config()
        self.set_key("MERGE_METHOD", "TODO")
        self.assertIn("missing or TODO: MERGE_METHOD", self.run_script("issue", "demo", "7", expect=1).stderr)
        self.assertIn("fill in MERGE_METHOD", self.run_script("check", "demo").stdout)
        self.set_key("MERGE_BY", "maintainer")
        self.assertIn("**Issue #7**", self.render("issue", "7"))
        self.assertIn("complete", self.run_script("check", "demo").stdout)
        self.set_key("LOCK_MAX", "TODO")  # the acceptance lock of the maintainer brief still names it
        self.assertIn("missing or TODO: LOCK_MAX", self.run_script("issue", "demo", "7", expect=1).stderr)
        self.assertIn("fill in LOCK_MAX", self.run_script("check", "demo").stdout)

    def test_conditional_blocks(self):
        values = {"MERGE_BY": "maintainer", "OTHER": "x"}
        resolve = fb.resolve_conditionals
        block = "a\n<!-- if MERGE_BY=maintainer -->\nm\n<!-- else -->\ns\n<!-- endif -->\nz\n"
        self.assertEqual(resolve(block, values), "a\nm\nz\n")
        self.assertEqual(resolve(block, {**values, "MERGE_BY": "session"}), "a\ns\nz\n")
        only = "a\n<!-- if MERGE_BY=maintainer -->\nm\n<!-- endif -->\nz\n"
        self.assertEqual(resolve(only, values), "a\nm\nz\n")
        self.assertEqual(resolve(only, {**values, "MERGE_BY": "session"}), "a\nz\n")
        self.assertEqual(resolve("<!-- if OTHER=x -->\n1\n<!-- endif -->\n<!-- if OTHER=y -->\n2\n<!-- else -->\n3\n<!-- endif -->", values), "1\n3\n")
        self.assertEqual(resolve("no markers\n", values), "no markers\n")
        for broken in ("<!-- if MERGE_BY=maintainer -->\nm\n", "m\n<!-- endif -->\n", "<!-- else -->\n"):
            with self.assertRaises(SystemExit, msg=broken):
                resolve(broken, values)
        with self.assertRaises(SystemExit):
            resolve("<!-- if NOPE=1 -->\nm\n<!-- endif -->\n", values)


if __name__ == "__main__":
    unittest.main()
