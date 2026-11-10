"""Contract test for playbook/session-briefs/fill-brief.py: table placeholders are filled,
run-time placeholders stay, missing values are refused."""

import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "playbook" / "session-briefs" / "fill-brief.py"


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
        text = re.sub(r"^(\w+)=TODO$", lambda m: f"{m.group(1)}=value for {m.group(1)}", text, flags=re.M)
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


if __name__ == "__main__":
    unittest.main()
