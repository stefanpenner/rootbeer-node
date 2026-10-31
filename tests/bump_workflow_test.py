"""Tests the shape of the daily version check. It reads the workflow as text, as ci_test.py does."""

import os
import re
import unittest
from pathlib import Path

WORKFLOW = Path(os.environ["BUMP_WORKFLOW"]).read_text()


def indented(block, name):
    """Returns the lines under `name:` that have a larger indent."""
    indent = name[:len(name) - len(name.lstrip())]
    match = re.search(rf"^{re.escape(name)}:[^\n]*\n((?:{indent} +[^\n]*\n|\n)*)", block, re.MULTILINE)
    return match.group(1) if match else None


def jobs():
    return re.findall(r"^  ([a-z][a-z0-9_-]*):$", indented(WORKFLOW, "jobs"), re.MULTILINE)


def code_only():
    return "\n".join(line for line in WORKFLOW.splitlines() if not line.lstrip().startswith("#"))


class Shape(unittest.TestCase):
    def test_runs_daily_and_by_hand_only(self):
        self.assertEqual(re.findall(r"^  ([a-z_]+):", indented(WORKFLOW, "on"), re.MULTILINE),
                         ["schedule", "workflow_dispatch"])
        self.assertRegex(indented(WORKFLOW, "on"), r"cron: '\d+ \d+ \* \* \*'")

    def test_the_default_permission_is_none(self):
        self.assertRegex(WORKFLOW, r"(?m)^permissions: \{\}$")

    def test_has_one_job(self):
        self.assertEqual(jobs(), ["bump"])

    def test_the_job_has_only_the_two_write_permissions(self):
        job = indented(WORKFLOW, "  bump")
        rows = re.findall(r"^      (\S+: \S+)$", indented(job, "    permissions"), re.MULTILINE)
        self.assertEqual(sorted(rows), ["contents: write", "pull-requests: write"])

    def test_runs_only_from_main(self):
        self.assertIn("if: github.ref == 'refs/heads/main'", indented(WORKFLOW, "  bump"))

    def test_runs_on_a_hosted_runner(self):
        self.assertIn("runs-on: ubuntu-latest", WORKFLOW)
        self.assertNotIn("vars.", WORKFLOW)
        self.assertNotIn("self-hosted", WORKFLOW)

    def test_pins_each_external_action_by_full_sha(self):
        uses = re.findall(r"uses: (\S+)", WORKFLOW)
        self.assertTrue(uses)
        for action in uses:
            if not action.startswith("./"):
                self.assertRegex(action, r"^[^@]+@[0-9a-f]{40}$")

    def test_checkout_keeps_no_credential(self):
        self.assertIn("persist-credentials: false", WORKFLOW)


class Limits(unittest.TestCase):
    """The job must not work around the signed commit rule or the pr-approval gate."""

    def test_uses_only_the_github_token(self):
        self.assertEqual(set(re.findall(r"secrets\.(\w+)", WORKFLOW)), {"GITHUB_TOKEN"})

    def test_does_not_push_with_git(self):
        self.assertNotIn("git push", code_only())
        self.assertNotIn("git commit", code_only())

    def test_does_not_dispatch_a_workflow(self):
        code = code_only()
        self.assertNotIn("actions: write", code)
        self.assertNotIn("gh workflow", code)
        self.assertNotIn("/dispatches", code)

    def test_has_no_privileged_trigger(self):
        self.assertNotIn("pull_request", code_only().replace("pull-requests: write", ""))

    def test_passes_the_commit_of_the_checkout(self):
        self.assertIn('--base-sha "$GITHUB_SHA"', WORKFLOW)
        self.assertIn('--repo "$GITHUB_REPOSITORY"', WORKFLOW)


if __name__ == "__main__":
    unittest.main()
