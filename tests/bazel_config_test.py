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
PLATFORMS = Path(os.environ["PLATFORMS"]).read_text()
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


class RemoteExecution(unittest.TestCase):
    """`--config=remote-exec` must run the Linux build on a Linux executor. The endpoint is in ~/.bazelrc."""

    def test_config_selects_the_linux_platform_for_target_host_and_execution(self):
        for flag in ("platforms", "host_platform", "extra_execution_platforms"):
            self.assertIn(f"build:remote-exec --{flag}=//platforms:linux_x64_rbe", settings())

    def test_config_has_no_endpoint_and_no_secret(self):
        for line in settings():
            if line.startswith("build:remote-exec"):
                self.assertNotIn("remote_executor", line)
                self.assertNotRegex(line, r"10\.\d+\.\d+\.\d+|grpcs?://")

    def test_config_runs_everything_remotely_and_never_falls_back(self):
        self.assertIn("build:remote-exec --spawn_strategy=remote", settings())
        self.assertIn("build:remote-exec --noremote_local_fallback", settings())

    def test_platform_is_linux_x86_64_with_exec_properties(self):
        self.assertIn("@platforms//os:linux", PLATFORMS)
        self.assertIn("@platforms//cpu:x86_64", PLATFORMS)
        self.assertIn('"OSFamily": "linux"', PLATFORMS)
        self.assertRegex(PLATFORMS, r'"container-image": "docker://[^"]+@sha256:[0-9a-f]{64}"')


if __name__ == "__main__":
    unittest.main()
