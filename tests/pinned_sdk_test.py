"""Checks the opt-in `--config=pinned-sdk` settings. The checks read the files as text.

The Apple license does not allow a public copy of the SDK. These checks stop a
config, a workflow, or a tracked file that can publish the tarball.
"""

import os
import subprocess
import unittest
from pathlib import Path

BAZELRC = Path(os.environ["BAZELRC"]).read_text()
SDK_BZL = Path(os.environ["SDK_BZL"]).read_text()
CI = Path(os.environ["CI_WORKFLOW"]).read_text()


def settings():
    """Returns the .bazelrc lines that are not comments, with spaces folded."""
    return [" ".join(line.split()) for line in BAZELRC.splitlines()
            if line.strip() and not line.lstrip().startswith("#")]


def pinned_lines():
    return [line for line in settings() if ":pinned-sdk " in line]


class Config(unittest.TestCase):
    def test_the_config_turns_on_the_pin(self):
        self.assertIn("common:pinned-sdk --repo_env=ROOTBEER_PINNED_SDK=1", settings())

    def test_only_the_config_turns_on_the_pin(self):
        self.assertEqual([line for line in settings() if "ROOTBEER_PINNED_SDK=" in line],
                         ["common:pinned-sdk --repo_env=ROOTBEER_PINNED_SDK=1"])

    def test_the_config_holds_no_address_and_no_checksum(self):
        for line in pinned_lines():
            self.assertNotRegex(line, r"https?://|file://|s3://|[0-9a-f]{64}|_URL|_SHA256")

    def test_the_config_sends_nothing_to_a_remote_service(self):
        for flag in ("remote_executor", "remote_cache", "bes_backend", "experimental_remote_downloader"):
            self.assertIn(f"build:pinned-sdk --{flag}=", settings())


class RepositoryRule(unittest.TestCase):
    def test_the_rule_reads_the_address_and_the_checksum_from_the_user(self):
        for name in ("ROOTBEER_PINNED_SDK", "ROOTBEER_PINNED_SDK_URL", "ROOTBEER_PINNED_SDK_SHA256"):
            self.assertIn(f'"{name}"', SDK_BZL)

    def test_the_license_note_names_the_private_tarball(self):
        self.assertIn("never publish", SDK_BZL[:SDK_BZL.index('"""', 3)].lower())


class Ci(unittest.TestCase):
    def test_ci_does_not_turn_on_the_pin(self):
        self.assertNotIn("pinned-sdk", CI)
        self.assertNotIn("ROOTBEER_PINNED_SDK", CI)


if __name__ == "__main__":
    unittest.main()
