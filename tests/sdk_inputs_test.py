"""The macOS SDK files are declared inputs of the Node build, so the cache key follows their content.

On Linux the SDK repository is empty, and the file checks do not apply.
"""

import json
import os
import re
import sys
import unittest
from pathlib import Path

INFO = json.loads(Path(os.environ["SDK_INFO"]).read_text())
FILES = [Path(item) for item in os.environ["SDK_FILES"].split()]
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
        names = {str(path) for path in FILES}
        self.assertGreater(len(FILES), 1000)
        self.assertTrue(any(name.endswith("/sdk/SDKSettings.json") for name in names))
        self.assertTrue(any(name.endswith("/sdk/usr/lib/libSystem.B.tbd") for name in names))

    @unittest.skipUnless(ON_MAC, "the SDK repository is empty on Linux")
    def test_info_json_records_the_sdk_dir_and_the_declared_settings_match(self):
        self.assertEqual(INFO["sdk_dir"], "sdk")
        settings = next(p for p in FILES if str(p).endswith("/sdk/SDKSettings.json"))
        self.assertEqual(json.loads(settings.read_text())["Version"], INFO["version"])


if __name__ == "__main__":
    unittest.main()
