"""Checks that every place that names a Node line agrees with the node.version tags.

MODULE.bazel holds one tag per version. The hub repo turns the tags into versions.json.
Everything else (CI matrix, README, patches, make_patches.py) must follow that list.
Adding a version fails here until each place is updated, and the message names the place.
"""

import json
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

VERSIONS = json.loads(Path(os.environ["VERSIONS_JSON"]).read_text())
MODULE = Path(os.environ["MODULE_BAZEL"])
README = Path(os.environ["README"]).read_text()
STATUS = Path(os.environ["STATUS"]).read_text()
WORKFLOW = Path(os.environ["WORKFLOW"]).read_text()
MAKE_PATCHES = Path(os.environ["MAKE_PATCHES"])
PATCHES = [Path(p) for p in os.environ["PATCHES"].split()]
MAJORS = [str(line["major"]) for line in VERSIONS]
TRUST_PATCHES = {"0001-empty-root-certs.patch", "0002-force-local-store.patch"}
OLD_V8_PATCHES = {"0003-libcxx-19-char-traits.patch", "0004-zlib-macos-test.patch",
                  "0005-predictable-snapshot.patch"}


def prose(majors):
    """Returns '16, 18, 20, and 22'."""
    ordered = sorted(majors, key=int)
    return ", ".join(ordered[:-1]) + ", and " + ordered[-1]


def build_jobs():
    body = WORKFLOW.split("\njobs:\n", 1)[1]
    parts = re.split(r"^  ([a-z0-9_-]+):\n", body, flags=re.MULTILINE)
    return {n: t for n, t in zip(parts[1::2], parts[2::2]) if "matrix:" in t}


class Hub(unittest.TestCase):
    def test_lines_are_newest_first(self):
        self.assertEqual(MAJORS, sorted(MAJORS, key=int, reverse=True))

    def test_each_version_is_in_its_line(self):
        for line in VERSIONS:
            self.assertTrue(line["version"].startswith(f"{line['major']}."), line)

    def test_source_hashes_are_sha256(self):
        for line in VERSIONS:
            self.assertRegex(line["source_sha256"], r"^[0-9a-f]{64}$", line)


class Ci(unittest.TestCase):
    @staticmethod
    def matrix_lines(text):
        match = re.search(r"^        node: \[(.*)\]$", text, re.MULTILINE)
        return [item.strip() for item in match.group(1).split(",")] if match else None

    def test_matrix_covers_every_node_line(self):
        self.assertEqual(
            self.matrix_lines(build_jobs()["build"]),
            sorted(MAJORS, key=int),
            "build: edit the node list in .github/workflows/ci.yml",
        )

    def test_pull_requests_build_the_oldest_and_newest_line_only(self):
        # A full matrix costs 12 long jobs. The build job on main still builds every line.
        ordered = sorted(MAJORS, key=int)
        self.assertEqual(
            self.matrix_lines(build_jobs()["build-pr"]),
            [ordered[0], ordered[-1]],
            "build-pr: edit the node list in .github/workflows/ci.yml",
        )

    def test_source_tests_run_as_one_suite(self):
        # A line with its own target name in the workflow is easy to forget.
        self.assertIn("//tests:source_tests", WORKFLOW)
        self.assertNotRegex(WORKFLOW, r"//tests:source_\d+_test")


class Readme(unittest.TestCase):
    def test_table_lists_every_version_and_hash(self):
        rows = re.findall(r"^\| (\d+) \| ([0-9.]+) \| `([0-9a-f]{64})` \|", README, re.MULTILINE)
        expected = [(str(l["major"]), l["version"], l["source_sha256"]) for l in VERSIONS]
        self.assertEqual(rows, expected, "edit the table in README.md")

    def test_prose_lists_every_line(self):
        text = prose(MAJORS)
        self.assertIn(f"Node.js {text} with no bundled root certificates", README)
        self.assertIn(f"builds Node {text} on macOS 14", README)


class Status(unittest.TestCase):
    """STATUS.md holds the evidence for each result that the README states."""

    result = STATUS.split("## Result\n")[1].split("\n## ")[0]

    def test_table_lists_every_version(self):
        rows = re.findall(r"^\| (\d+\.\d+\.\d+) \|", self.result, re.MULTILINE)
        self.assertEqual(rows, [l["version"] for l in VERSIONS], "edit the Result table in STATUS.md")

    def test_readme_gives_the_same_result(self):
        readme = re.findall(r"^\| \d+ \| ([0-9.]+) \| `[0-9a-f]{64}` \| ([^|]+) \| ([^|]+) \|", README, re.MULTILINE)
        status = re.findall(r"^\| (\d+\.\d+\.\d+) \| ([^|]+) \| ([^|]+) \|", self.result, re.MULTILINE)
        self.assertEqual(readme, status, "README.md and STATUS.md disagree")


class Patches(unittest.TestCase):
    def test_each_line_has_exactly_its_patches(self):
        found = {}
        for path in PATCHES:
            found.setdefault(path.parent.name, set()).add(path.name)
        expected = {
            str(l["major"]): TRUST_PATCHES | (OLD_V8_PATCHES if l["old_v8"] else set())
            for l in VERSIONS
        }
        self.assertEqual(found, expected, "run tools/make_patches.py")

    def test_make_patches_reads_the_same_versions(self):
        out = subprocess.run(
            [sys.executable, str(MAKE_PATCHES), "--list", str(MODULE)],
            capture_output=True, text=True, check=True,
        ).stdout
        listed = [line.split() for line in out.splitlines()]
        expected = [[str(l["major"]), l["version"], str(l["old_v8"]).lower()] for l in VERSIONS]
        self.assertEqual(sorted(listed), sorted(expected))


if __name__ == "__main__":
    unittest.main()
