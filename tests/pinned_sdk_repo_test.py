"""Runs the macos_sdk repository rule in a temporary workspace with a fake SDK tarball.

The tarball holds a fake SDK with two small files. It holds no Apple bytes, and it stays in
a temporary directory. Nested Bazel needs the module registry, so this test has the tag
manual. Run it with `bazel test //tests:pinned_sdk_repo_test`.
"""

import hashlib
import json
import os
import pwd
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

SDK_BZL = Path(os.environ["SDK_BZL"]).resolve()
BAZEL_VERSION = Path(os.environ["BAZEL_VERSION_FILE"]).resolve().read_text()
BAZEL = shutil.which("bazel") or "/opt/homebrew/bin/bazel"
SECRET_HOST = "private-sdk-host.invalid"
ON_MAC = sys.platform == "darwin"


def write_tarball(path, sdk_names=("MacOSX99.0.sdk",), tbd="archs: [ arm64 ]\n"):
    source = path.parent / (path.name + ".src")
    for name in sdk_names:
        root = source / name
        (root / "usr/lib").mkdir(parents=True)
        (root / "SDKSettings.json").write_text(json.dumps({"Version": "99.0"}))
        (root / "usr/lib/libSystem.B.tbd").write_text(tbd)
    with tarfile.open(path, "w:gz") as archive:
        for name in sdk_names:
            archive.add(source / name, arcname=name)
    return hashlib.sha256(path.read_bytes()).hexdigest()


@unittest.skipUnless(ON_MAC, "the repository rule reads an SDK only on macOS")
class RepositoryRule(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(tempfile.mkdtemp(prefix="pinned-sdk-", dir="/tmp")).resolve()
        cls.workspace = cls.root / "workspace"
        cls.workspace.mkdir()
        (cls.workspace / ".bazelversion").write_text(BAZEL_VERSION)
        (cls.workspace / "BUILD.bazel").write_text("")
        (cls.workspace / "sdk.bzl").write_text(SDK_BZL.read_text())
        (cls.workspace / "MODULE.bazel").write_text(
            'macos_sdk = use_repo_rule("//:sdk.bzl", "macos_sdk")\nmacos_sdk(name = "macos_sdk")\n')
        cls.tarball = cls.root / "good" / "MacOSX.sdk.tar.gz"
        cls.tarball.parent.mkdir()
        cls.sha256 = write_tarball(cls.tarball)
        cls.url = cls.tarball.as_uri()

    @classmethod
    def tearDownClass(cls):
        cls.bazel("shutdown")
        shutil.rmtree(cls.root, ignore_errors=True)

    @classmethod
    def bazel(cls, *arguments):
        env = {"HOME": pwd.getpwuid(os.getuid()).pw_dir, "PATH": "/usr/bin:/bin:/opt/homebrew/bin"}
        command = [BAZEL, "--nosystem_rc", "--nohome_rc", "--output_base=" + str(cls.root / "base"), *arguments]
        return subprocess.run(command, cwd=cls.workspace, env=env, capture_output=True, text=True, timeout=600)

    def fetch(self, *repo_env):
        """Refetches the repository. The output base is shared, so read a result before the next call."""
        result = self.bazel("build", "--lockfile_mode=off", "--repository_cache=" + str(self.root / "cache"),
                            "@macos_sdk//:files", "@macos_sdk//:info.json",
                            *("--repo_env=" + item for item in repo_env))
        external = self.root / "base" / "external"
        repos = [path for path in external.glob("*macos_sdk") if path.is_dir()]
        return result, (repos[0] if repos else None)

    def pinned(self, url=None, sha256=None):
        return self.fetch("ROOTBEER_PINNED_SDK=1",
                          "ROOTBEER_PINNED_SDK_URL=" + (url or self.url),
                          "ROOTBEER_PINNED_SDK_SHA256=" + (sha256 or self.sha256))

    def assert_fails_with(self, result, text):
        self.assertNotEqual(result.returncode, 0, result.stderr)
        self.assertIn(text, result.stderr)

    def test_flag_on_with_a_good_tarball_resolves_to_the_tarball(self):
        result, repo = self.pinned()
        self.assertEqual(result.returncode, 0, result.stderr)
        info = json.loads((repo / "info.json").read_text())
        self.assertEqual(info["source"], "pinned")
        self.assertEqual(info["tarball_sha256"], self.sha256)
        self.assertEqual(info["path"], "sdk")
        self.assertEqual(info["version"], "99.0")
        settings = repo / "sdk" / "SDKSettings.json"
        self.assertTrue(settings.resolve().is_relative_to(repo.resolve()), settings.resolve())

    def test_info_json_never_records_the_address(self):
        (self.root / "named" / SECRET_HOST).mkdir(parents=True)
        tarball = self.root / "named" / SECRET_HOST / "MacOSX.sdk.tar.gz"
        digest = write_tarball(tarball)
        result, repo = self.pinned(url=tarball.as_uri(), sha256=digest)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(SECRET_HOST, (repo / "info.json").read_text())
        self.assertNotIn(str(self.root), (repo / "info.json").read_text())

    def test_flag_on_with_a_wrong_sha256_fails(self):
        result, _ = self.pinned(sha256="0" * 64)
        self.assert_fails_with(result, "ROOTBEER_PINNED_SDK_SHA256")

    def test_flag_on_with_a_malformed_sha256_fails(self):
        result, _ = self.pinned(sha256="abc")
        self.assert_fails_with(result, "64 hex")

    def test_flag_on_with_a_missing_tarball_fails(self):
        result, _ = self.pinned(url=(self.root / "absent.tar.gz").as_uri(), sha256="1" * 64)
        self.assert_fails_with(result, "Cannot fetch or verify")

    def test_flag_on_with_no_address_or_checksum_fails(self):
        result, _ = self.fetch("ROOTBEER_PINNED_SDK=1")
        self.assert_fails_with(result, "ROOTBEER_PINNED_SDK_URL")
        self.assert_fails_with(result, "ROOTBEER_PINNED_SDK_SHA256")

    def test_flag_on_refuses_the_host_override(self):
        result, _ = self.fetch("ROOTBEER_PINNED_SDK=1", "ROOTBEER_MACOS_SDK=/nonexistent",
                               "ROOTBEER_PINNED_SDK_URL=" + self.url,
                               "ROOTBEER_PINNED_SDK_SHA256=" + self.sha256)
        self.assert_fails_with(result, "ROOTBEER_MACOS_SDK")

    def test_flag_on_refuses_a_tarball_lld_cannot_read(self):
        tarball = self.root / "arch.tar.gz"
        digest = write_tarball(tarball, tbd="archs: [ arm64e.x1 ]\n")
        result, _ = self.pinned(url=tarball.as_uri(), sha256=digest)
        self.assert_fails_with(result, "ld64.lld")

    def test_flag_on_refuses_a_tarball_with_two_sdks(self):
        tarball = self.root / "two.tar.gz"
        digest = write_tarball(tarball, sdk_names=("MacOSX98.0.sdk", "MacOSX99.0.sdk"))
        result, _ = self.pinned(url=tarball.as_uri(), sha256=digest)
        self.assert_fails_with(result, "exactly one")

    def test_flag_off_ignores_an_address_and_a_checksum(self):
        default, repo = self.fetch()
        self.assertEqual(default.returncode, 0, default.stderr)
        default_info = (repo / "info.json").read_text()
        ignored, repo = self.fetch(
            "ROOTBEER_PINNED_SDK_URL=" + (self.root / "absent.tar.gz").as_uri(),
            "ROOTBEER_PINNED_SDK_SHA256=" + "0" * 64)
        self.assertEqual(ignored.returncode, 0, ignored.stderr)
        self.assertEqual(default_info, (repo / "info.json").read_text())
        self.assertEqual(set(json.loads(default_info)),
                         {"path", "sdk_dir", "version", "settings_sha256"})


if __name__ == "__main__":
    unittest.main()
