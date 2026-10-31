"""Checks the CI workflow. A pull request must wait for approval and use a hosted runner.

The checks read the YAML as text, because the build has no YAML parser.
Bazel can cache this test.
"""

import os
import re
import unittest
from pathlib import Path

WORKFLOW = Path(os.environ["WORKFLOW"]).read_text()
HOSTED = re.compile(r"^(ubuntu|macos|windows)-[a-z0-9.]+$")
NOT_PR = "github.event_name != 'pull_request'"
ONLY_PR = "github.event_name == 'pull_request'"


def triggers():
    block = re.search(r"^on:\n((?:[ ]+.*\n|\n)+)", WORKFLOW, re.MULTILINE).group(1)
    return set(re.findall(r"^  ([a-z_]+):", block, re.MULTILINE))


def jobs():
    """Returns {name: text} for each job under the top-level jobs key."""
    body = WORKFLOW.split("\njobs:\n", 1)[1]
    parts = re.split(r"^  ([a-z0-9_-]+):\n", body, flags=re.MULTILINE)
    return dict(zip(parts[1::2], parts[2::2]))


def field(text, name):
    match = re.search(rf"^    {name}: (.*)$", text, re.MULTILINE)
    return match.group(1).strip() if match else None


class Triggers(unittest.TestCase):
    def test_only_the_allowed_triggers(self):
        self.assertEqual(triggers(), {"push", "workflow_dispatch", "pull_request"})

    def test_push_runs_on_main_only(self):
        self.assertRegex(WORKFLOW, r"push:\n\s+branches: \[main\]")

    def test_no_pull_request_target(self):
        self.assertNotIn("pull_request_target", WORKFLOW)

    def test_token_is_read_only(self):
        self.assertRegex(WORKFLOW, r"(?m)^permissions:\n  contents: read\n")


class PullRequestJobs(unittest.TestCase):
    def test_there_is_a_pull_request_job(self):
        self.assertTrue([n for n, t in jobs().items() if field(t, "if") == ONLY_PR])

    def test_pull_request_jobs_wait_for_approval(self):
        for name, text in jobs().items():
            if field(text, "if") == ONLY_PR:
                self.assertEqual(field(text, "environment"), "pr-approval", name)

    def test_pull_request_jobs_use_a_hosted_runner(self):
        for name, text in jobs().items():
            if field(text, "if") == ONLY_PR:
                self.assertRegex(field(text, "runs-on"), HOSTED, name)


class PushJobs(unittest.TestCase):
    def test_every_job_is_gated_on_the_event(self):
        for name, text in jobs().items():
            self.assertIn(field(text, "if"), {ONLY_PR, NOT_PR}, f"{name} runs on every event")

    def test_only_push_jobs_read_the_runner_variable(self):
        for name, text in jobs().items():
            runs_on = field(text, "runs-on")
            if "vars." in runs_on or "self-hosted" in runs_on:
                self.assertEqual(field(text, "if"), NOT_PR, name)
                self.assertNotIn("environment", text, name)

    def test_push_jobs_use_the_runner_variable_with_a_hosted_fallback(self):
        selected = [t for t in jobs().values() if field(t, "if") == NOT_PR]
        self.assertTrue(selected)
        for text in selected:
            self.assertEqual(
                field(text, "runs-on"),
                "${{ fromJSON(vars.CI_RUNS_ON || '\"ubuntu-latest\"') }}",
            )

    def test_no_job_hardcodes_self_hosted(self):
        self.assertNotRegex(WORKFLOW, r"runs-on: \[?\s*self-hosted")


if __name__ == "__main__":
    unittest.main()
