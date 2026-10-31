"""Tests the helper that packs a local SDK. The tests use a fake SDK with no Apple bytes."""

import hashlib
import json
import os
import stat
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

HELPER = Path(os.environ["PACK_MACOS_SDK"]).resolve()


class PackMacosSdk(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.sdk = self.fake_sdk("MacOSX99.0.sdk")

    def tearDown(self):
        self.temp.cleanup()

    def fake_sdk(self, name, tbd="archs: [ arm64 ]\n"):
        sdk = self.root / "sdks" / name
        (sdk / "usr/lib").mkdir(parents=True)
        (sdk / "SDKSettings.json").write_text(json.dumps({"Version": "99.0"}))
        (sdk / "usr/lib/libSystem.B.tbd").write_text(tbd)
        (sdk / "usr/current").symlink_to("lib")
        return sdk

    def pack(self, sdk, out):
        return subprocess.run([sys.executable, "-I", str(HELPER), "--sdk", str(sdk), "--out", str(out)],
                              capture_output=True, text=True)

    def test_it_writes_a_private_tarball_and_prints_its_sha256(self):
        out = self.root / "private" / "sdk.tar.gz"
        result = self.pack(self.sdk, out)
        self.assertEqual(result.returncode, 0, result.stderr)
        digest = hashlib.sha256(out.read_bytes()).hexdigest()
        self.assertIn(digest, result.stdout)
        self.assertEqual(stat.S_IMODE(out.stat().st_mode), 0o600)

    def test_the_tarball_holds_the_sdk_directory_and_keeps_links(self):
        out = self.root / "sdk.tar.gz"
        self.assertEqual(self.pack(self.sdk, out).returncode, 0)
        with tarfile.open(out) as archive:
            names = archive.getnames()
            link = archive.getmember("MacOSX99.0.sdk/usr/current")
            self.assertTrue(link.issym())
        self.assertIn("MacOSX99.0.sdk/SDKSettings.json", names)

    def test_two_runs_write_the_same_bytes(self):
        first, second = self.root / "a.tar.gz", self.root / "b.tar.gz"
        self.assertEqual(self.pack(self.sdk, first).returncode, 0)
        self.assertEqual(self.pack(self.sdk, second).returncode, 0)
        self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_it_follows_a_generic_link_to_the_versioned_sdk(self):
        link = self.root / "sdks" / "MacOSX.sdk"
        link.symlink_to(self.sdk)
        out = self.root / "sdk.tar.gz"
        self.assertEqual(self.pack(link, out).returncode, 0)
        with tarfile.open(out) as archive:
            self.assertIn("MacOSX99.0.sdk/SDKSettings.json", archive.getnames())

    def test_it_refuses_a_path_in_a_git_work_tree(self):
        repo = self.root / "repo"
        (repo / ".git").mkdir(parents=True)
        (repo / "sub").mkdir()
        out = repo / "sub" / "sdk.tar.gz"
        result = self.pack(self.sdk, out)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("outside", result.stderr)
        self.assertFalse(out.exists())

    def test_it_refuses_a_directory_that_is_not_an_sdk(self):
        other = self.root / "other"
        other.mkdir()
        result = self.pack(other, self.root / "sdk.tar.gz")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SDKSettings.json", result.stderr)

    def test_it_refuses_an_sdk_that_lld_cannot_read(self):
        sdk = self.fake_sdk("MacOSX98.0.sdk", tbd="archs: [ arm64e.x1 ]\n")
        result = self.pack(sdk, self.root / "sdk.tar.gz")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ld64.lld", result.stderr)


if __name__ == "__main__":
    unittest.main()
