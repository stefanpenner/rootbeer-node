"""Tests tools/add_node_version.py on copies of the real files. No network."""

import importlib.util
import json
import os
import re
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("add_node_version", os.environ["ADD_NODE_VERSION"])
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)

MODULE = Path(os.environ["MODULE_BAZEL"]).read_text()
MANIFEST = Path(os.environ["NODE_MANIFEST"]).read_text()
README = Path(os.environ["README"]).read_text()


def shasums(version):
    names = [f"node-v{version}.tar.gz", f"node-v{version}-darwin-arm64.tar.gz",
             f"node-v{version}-linux-x64.tar.gz", f"node-v{version}-win-x64.zip"]
    return "".join(f"{(str(i) * 64)[:64]}  {name}\n" for i, name in enumerate(names, 1))


def tags(module):
    return re.findall(r'^    major = "(\d+)",\n    version = "([^"]+)",', module, re.MULTILINE)


class Bump(unittest.TestCase):
    def setUp(self):
        self.module, self.manifest, self.readme = tool.update(
            MODULE, MANIFEST, README, "22.99.0", shasums("22.99.0"), old_v8=False)

    def test_replaces_the_tag_of_the_line(self):
        expected = [("22", "22.99.0") if major == "22" else (major, version) for major, version in tags(MODULE)]
        self.assertEqual(tags(self.module), expected)

    def test_reads_each_hash_from_its_file_name(self):
        self.assertIn(f'sha256 = "{"1" * 64}"', self.module)
        self.assertIn(f'stock_darwin_arm64_sha256 = "{"2" * 64}"', self.module)
        self.assertIn(f'stock_linux_x64_sha256 = "{"3" * 64}"', self.module)

    def test_replaces_only_the_manifest_entry_of_the_line(self):
        old = json.loads(MANIFEST)
        new = json.loads(self.manifest)
        self.assertEqual([v["line"] for v in new["versions"]], [v["line"] for v in old["versions"]])
        for before, after in zip(old["versions"], new["versions"]):
            if before["line"] != "22":
                self.assertEqual(after, before)
        entry = next(v for v in new["versions"] if v["line"] == "22")
        self.assertEqual(entry["version"], "22.99.0")
        self.assertEqual(entry["sha256"], "1" * 64)
        self.assertIn("node-v22.99.0-", entry["artifact"])

    def test_an_unchanged_version_gives_the_same_manifest_bytes(self):
        current = next(v for v in json.loads(MANIFEST)["versions"] if v["line"] == "22")
        digest = current["sha256"]
        sums = shasums(current["version"]).replace("1" * 64, digest)
        _, manifest, _ = tool.update(MODULE, MANIFEST, README, current["version"], sums, old_v8=False)
        self.assertEqual(manifest, MANIFEST)

    def test_updates_the_readme_row(self):
        self.assertIn(f"| 22 | 22.99.0 | `{'1' * 64}` |", self.readme)
        self.assertNotIn("22.23.4 | `", self.readme)


class NewLine(unittest.TestCase):
    def setUp(self):
        self.module, self.manifest, self.readme = tool.update(
            MODULE, MANIFEST, README, "98.0.0", shasums("98.0.0"), old_v8=False)
        self.majors = [major for major, _ in tags(MODULE)]

    def test_adds_the_line_newest_first(self):
        self.assertEqual([m for m, _ in tags(self.module)], ["98"] + self.majors)

    def test_adds_the_line_to_the_manifest_newest_first(self):
        versions = json.loads(self.manifest)["versions"]
        self.assertEqual([v["line"] for v in versions], ["98"] + self.majors)
        self.assertEqual(versions[0]["target"], "//node:dist_98")
        self.assertEqual(versions[0]["test"], "//tests:node_98_tests")

    def test_extends_the_readme(self):
        ascending = ", ".join(sorted(self.majors, key=int))
        self.assertIn(f"Node.js {ascending}, and 98 with no bundled root certificates", self.readme)
        self.assertIn(f"builds Node {ascending}, and 98 on macOS 14", self.readme)
        rows = re.findall(r"^\| (\d+) \| ", self.readme, re.MULTILINE)
        self.assertEqual(rows[:len(self.majors) + 1], ["98"] + self.majors)

    def test_old_v8_is_written_only_when_asked(self):
        module, _, _ = tool.update(MODULE, MANIFEST, README, "17.9.1", shasums("17.9.1"), old_v8=True)
        self.assertRegex(module, r'major = "17",[^)]*old_v8 = True,')


class Refusals(unittest.TestCase):
    def test_missing_hash_is_an_error(self):
        broken = "".join(l for l in shasums("98.0.0").splitlines(True) if "linux-x64" not in l)
        with self.assertRaises(SystemExit):
            tool.update(MODULE, MANIFEST, README, "98.0.0", broken, old_v8=False)

    def test_bad_version_is_an_error(self):
        with self.assertRaises(SystemExit):
            tool.update(MODULE, MANIFEST, README, "v98", shasums("98.0.0"), old_v8=False)


if __name__ == "__main__":
    unittest.main()
