"""The macOS SDK files are declared inputs of the Node build, so the cache key follows their content.

On Linux the SDK repository is empty, and the file checks do not apply.
"""

import json
import os
import re
import sys
import unittest
from pathlib import Path

# The file list is too long for an environment variable, so the test walks the runfiles.
INFO_PATH = Path(os.environ["SDK_INFO"])
INFO = json.loads(INFO_PATH.read_text())
SDK_DIR = INFO_PATH.parent / "sdk"
BAZEL_BUILD = Path(os.environ["BAZEL_BUILD"]).read_text()
ON_MAC = sys.platform == "darwin"


def sysroot_files_macos_branch():
    """Returns the macOS branch of the sysroot_files select in bazel/BUILD.bazel."""
    block = re.search(r'name = "sysroot_files".*?\n\)', BAZEL_BUILD, re.S).group(0)
    return re.search(r'":macos_arm64": \[(.*?)\]', block, re.S).group(1)


class SdkInputs(unittest.TestCase):
    def test_the_node_build_receives_the_sdk_files(self):
        self.assertIn("@macos_sdk//:files", sysroot_files_macos_branch())

    @unittest.skipUnless(ON_MAC, "the SDK repository is empty on Linux")
    def test_the_declared_files_are_the_sdk_of_info_json(self):
        count = sum(len(names) for _, _, names in os.walk(SDK_DIR))
        self.assertGreater(count, 1000)
        self.assertTrue((SDK_DIR / "SDKSettings.json").is_file())
        self.assertTrue((SDK_DIR / "usr/lib/libSystem.B.tbd").is_file())

    @unittest.skipUnless(ON_MAC, "the SDK repository is empty on Linux")
    def test_info_json_records_the_sdk_dir_and_the_declared_settings_match(self):
        self.assertEqual(INFO["sdk_dir"], "sdk")
        settings = SDK_DIR / "SDKSettings.json"
        self.assertEqual(json.loads(settings.read_text())["Version"], INFO["version"])

    @unittest.skipUnless(ON_MAC and "source" not in INFO, "only the default host SDK on macOS")
    def test_the_default_info_json_is_the_host_sdk_and_holds_no_pin(self):
        self.assertEqual(set(INFO), {"path", "sdk_dir", "version", "settings_sha256"})
        self.assertTrue(os.path.isabs(INFO["path"]), INFO["path"])

    @unittest.skipUnless(INFO.get("source") == "pinned", "only with --config=pinned-sdk")
    def test_the_pinned_info_json_names_the_declared_files_and_no_address(self):
        self.assertEqual(INFO["path"], "sdk")
        self.assertRegex(INFO["tarball_sha256"], r"^[0-9a-f]{64}$")
        self.assertNotIn("://", INFO_PATH.read_text())


if __name__ == "__main__":
    unittest.main()
