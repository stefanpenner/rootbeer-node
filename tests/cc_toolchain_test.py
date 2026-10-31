"""The C++ toolchain is the pinned LLVM. An autodetected host cc must fail here.

cc_probe.json comes from analysis of the toolchain that Bazel resolved.
cc_smoke is a real program that the same toolchain compiled and linked.
"""

import json
import os
import re
import subprocess
import unittest
from pathlib import Path

PINNED_LLVM = (19, 1, 7)
PINNED_REPOS = re.compile(r"^external/[^/]*llvm_(darwin_arm64|linux_x64)/bin/")

ROOT = Path(os.environ["TEST_SRCDIR"]) / os.environ["TEST_WORKSPACE"]
PROBE = json.loads((ROOT / "tests" / "cc_probe.json").read_text())
SMOKE = ROOT / "tests" / "cc_smoke"


class PinnedToolchainTest(unittest.TestCase):
    def test_every_tool_comes_from_the_pinned_llvm(self) -> None:
        self.assertTrue(PROBE["tools"], "the probe saw no tools")
        for action, tool in PROBE["tools"].items():
            with self.subTest(action=action):
                self.assertRegex(tool, PINNED_REPOS)

    def test_no_include_directory_is_a_host_path(self) -> None:
        self.assertTrue(PROBE["include_directories"], "the probe saw no includes")
        for directory in PROBE["include_directories"]:
            with self.subTest(directory=directory):
                self.assertTrue(
                    directory.startswith("external/"),
                    f"{directory} is outside the pinned inputs",
                )

    def test_toolchain_is_not_the_autodetected_one(self) -> None:
        self.assertNotIn("local", PROBE["toolchain_id"])
        self.assertTrue(PROBE["toolchain_id"].startswith("rootbeerz-llvm-"))

    def test_the_compiled_program_names_the_pinned_clang(self) -> None:
        seen = subprocess.run(
            [SMOKE], check=True, capture_output=True, text=True
        ).stdout.split()
        self.assertEqual(tuple(int(part) for part in seen), PINNED_LLVM)


if __name__ == "__main__":
    unittest.main()
