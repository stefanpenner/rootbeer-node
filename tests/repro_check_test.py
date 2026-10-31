"""Tests the helpers of tools/repro_check.py with small fake archives. No Node build runs here."""

import io
import os
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path

import repro_check


def archive(directory, name, node, extra=b""):
    path = Path(directory) / name
    with tarfile.open(path, "w:gz") as tar:
        for member, data in (("node-v1/bin/node", node), ("node-v1/BUILDINFO.json", extra)):
            info = tarfile.TarInfo(member)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return path


class Compare(unittest.TestCase):
    def test_equal_bytes_are_equal(self):
        result = repro_check.compare(b"abc" * 100, b"abc" * 100)
        self.assertTrue(result.same)
        self.assertEqual(result.only_a, [])
        self.assertEqual(result.only_b, [])

    def test_a_different_path_is_reported_with_both_strings(self):
        a = b"\x00\x01MODULESDIR: /tmp/build-a/execroot/x\x00\x02" + b"pad" * 50
        b = b"\x00\x01MODULESDIR: /var/other-b/execroot/x\x00\x02" + b"pad" * 50
        result = repro_check.compare(a, b)
        self.assertFalse(result.same)
        self.assertIn("MODULESDIR: /tmp/build-a/execroot/x", result.only_a)
        self.assertIn("MODULESDIR: /var/other-b/execroot/x", result.only_b)
        self.assertGreater(result.first_difference, 0)

    def test_a_length_difference_with_no_string_is_still_different(self):
        result = repro_check.compare(b"\x00" * 10, b"\x00" * 12)
        self.assertFalse(result.same)

    def test_short_strings_are_not_reported(self):
        result = repro_check.compare(b"\x00ab\x00" + b"x" * 40, b"\x00cd\x00" + b"x" * 40)
        self.assertFalse(result.same)
        self.assertEqual(result.only_a, [])


    def test_random_bytes_are_not_reported_as_strings(self):
        # Compressed data and tables hold runs of printable bytes by chance. They are noise.
        a = b"\x00" + b"!,[TvB\"Od_d;l#kw?3<6 ,4" + b"\x00" + b"x" * 40
        b = b"\x00" + b"'IjGr )axrd QAHhCyS:<" + b"\x00" + b"x" * 40
        result = repro_check.compare(a, b)
        self.assertEqual(result.only_a, [])
        self.assertEqual(result.only_b, [])

    def test_the_number_of_differing_bytes_is_counted(self):
        result = repro_check.compare(b"a" * 100, b"a" * 98 + b"bb")
        self.assertEqual(result.differing_bytes, 2)


class Archives(unittest.TestCase):
    def test_node_is_read_from_the_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            path = archive(directory, "a.tar.gz", b"NODE")
            self.assertEqual(repro_check.node_binary(path), b"NODE")

    def test_compare_archives_names_the_members_that_differ(self):
        with tempfile.TemporaryDirectory() as directory:
            a = archive(directory, "a.tar.gz", b"NODE", b'{"p": "/a"}')
            b = archive(directory, "b.tar.gz", b"NODE", b'{"p": "/b"}')
            self.assertEqual(repro_check.differing_members(a, b), ["node-v1/BUILDINFO.json"])


class WorkspaceCopy(unittest.TestCase):
    def test_copy_has_tracked_and_new_files_and_not_ignored_files(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "src"
            source.mkdir()
            run = lambda *args: subprocess.run(args, cwd=source, check=True, capture_output=True)
            run("git", "init", "-q")
            (source / ".gitignore").write_text("/bazel-*\n")
            (source / "tracked.txt").write_text("1")
            run("git", "add", ".")
            run("git", "-c", "user.email=a@b", "-c", "user.name=a", "commit", "-qm", "x")
            (source / "new.txt").write_text("2")
            (source / "bazel-out").symlink_to("/nonexistent")
            target = Path(directory) / "dst"
            repro_check.workspace_copy(source, target)
            self.assertTrue((target / "tracked.txt").exists())
            self.assertTrue((target / "new.txt").exists())
            self.assertFalse((target / "bazel-out").exists())
            self.assertFalse((target / ".git").exists())


if __name__ == "__main__":
    unittest.main()
