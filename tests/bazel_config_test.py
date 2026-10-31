"""Checks the Bazel settings that keep the build hermetic. Bazel can cache this test.

The checks read .bazelrc, .gitignore, and the lockfile as text.
"""

import json
import os
import re
import unittest
from pathlib import Path

BAZELRC = Path(os.environ["BAZELRC"]).read_text()
GITIGNORE = Path(os.environ["GITIGNORE"]).read_text().splitlines()
LOCKFILE = Path(os.environ["LOCKFILE"])
TEXTS = {name: Path(path).read_text() for name, path in
         (item.split("=", 1) for item in os.environ["TEXTS"].split())}


def settings():
    """Returns the .bazelrc lines that are not comments, with spaces folded."""
    return [" ".join(line.split()) for line in BAZELRC.splitlines()
            if line.strip() and not line.lstrip().startswith("#")]


class Lockfile(unittest.TestCase):
    def test_the_lockfile_is_not_ignored(self):
        self.assertNotIn("MODULE.bazel.lock", [line.strip().lstrip("/") for line in GITIGNORE])

    def test_the_lockfile_pins_the_registry_files(self):
        data = json.loads(LOCKFILE.read_text())
        self.assertGreater(len(data["registryFileHashes"]), 50)

    def test_bazel_fails_when_the_lockfile_is_stale(self):
        self.assertIn("common --lockfile_mode=error", settings())

    def test_no_command_turns_the_lockfile_off(self):
        for name, text in TEXTS.items():
            self.assertNotRegex(text, r"--lockfile_mode=(off|update|refresh)", name)


class ActionEnvironment(unittest.TestCase):
    def test_actions_get_a_fixed_environment(self):
        self.assertIn("build --incompatible_strict_action_env", settings())

    def test_no_action_env_forwards_a_host_variable(self):
        for line in settings():
            self.assertFalse(re.search(r"--(action|test|host_action)_env=\w+$", line), line)

    def test_actions_have_no_network(self):
        self.assertIn("build --sandbox_default_allow_network=false", settings())

    def test_bazel_does_not_look_for_a_host_c_compiler(self):
        self.assertIn("common --repo_env=BAZEL_DO_NOT_DETECT_CPP_TOOLCHAIN=1", settings())


if __name__ == "__main__":
    unittest.main()
