"""Tests tools/add_node_version.py on copies of the real files. No network."""

import importlib.util
import os
import re
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("add_node_version", os.environ["ADD_NODE_VERSION"])
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)

MODULE = Path(os.environ["MODULE_BAZEL"]).read_text()
WORKFLOW = Path(os.environ["WORKFLOW"]).read_text()
README = Path(os.environ["README"]).read_text()


def shasums(version):
    names = [f"node-v{version}.tar.gz", f"node-v{version}-darwin-arm64.tar.gz",
             f"node-v{version}-linux-x64.tar.gz", f"node-v{version}-win-x64.zip"]
    return "".join(f"{(str(i) * 64)[:64]}  {name}\n" for i, name in enumerate(names, 1))


def tags(module):
    return re.findall(r'^    major = "(\d+)",\n    version = "([^"]+)",', module, re.MULTILINE)


class Bump(unittest.TestCase):
    def setUp(self):
        self.module, self.workflow, self.readme = tool.update(
            MODULE, WORKFLOW, README, "22.99.0", shasums("22.99.0"), old_v8=False)

    def test_replaces_the_tag_of_the_line(self):
        self.assertEqual(tags(self.module), [("22", "22.99.0"), ("20", "20.20.2"), ("18", "18.20.8"), ("16", "16.20.2")])

    def test_reads_each_hash_from_its_file_name(self):
        self.assertIn(f'sha256 = "{"1" * 64}"', self.module)
        self.assertIn(f'stock_darwin_arm64_sha256 = "{"2" * 64}"', self.module)
        self.assertIn(f'stock_linux_x64_sha256 = "{"3" * 64}"', self.module)

    def test_leaves_the_matrix_alone(self):
        self.assertEqual(self.workflow, WORKFLOW)

    def test_updates_the_readme_row(self):
        self.assertIn(f"| 22 | 22.99.0 | `{'1' * 64}` |", self.readme)
        self.assertNotIn("22.23.4 | `", self.readme)


class NewLine(unittest.TestCase):
    def setUp(self):
        self.module, self.workflow, self.readme = tool.update(
            MODULE, WORKFLOW, README, "24.22.2", shasums("24.22.2"), old_v8=False)

    def test_adds_the_line_newest_first(self):
        self.assertEqual([m for m, _ in tags(self.module)], ["24", "22", "20", "18", "16"])

    def test_extends_every_matrix(self):
        self.assertEqual(self.workflow.count("node: [16, 18, 20, 22, 24]"), 2)
        self.assertNotIn("node: [16, 18, 20, 22]", self.workflow)

    def test_extends_the_readme(self):
        self.assertIn("Node.js 16, 18, 20, 22, and 24 with no bundled root certificates", self.readme)
        self.assertIn("builds Node 16, 18, 20, 22, and 24 on macOS 14", self.readme)
        rows = re.findall(r"^\| (\d+) \| ", self.readme, re.MULTILINE)
        self.assertEqual(rows[:5], ["24", "22", "20", "18", "16"])

    def test_old_v8_is_written_only_when_asked(self):
        module, _, _ = tool.update(MODULE, WORKFLOW, README, "17.9.1", shasums("17.9.1"), old_v8=True)
        self.assertRegex(module, r'major = "17",[^)]*old_v8 = True,')


class Refusals(unittest.TestCase):
    def test_missing_hash_is_an_error(self):
        broken = "".join(l for l in shasums("24.22.2").splitlines(True) if "linux-x64" not in l)
        with self.assertRaises(SystemExit):
            tool.update(MODULE, WORKFLOW, README, "24.22.2", broken, old_v8=False)

    def test_bad_version_is_an_error(self):
        with self.assertRaises(SystemExit):
            tool.update(MODULE, WORKFLOW, README, "v24", shasums("24.22.2"), old_v8=False)


if __name__ == "__main__":
    unittest.main()
