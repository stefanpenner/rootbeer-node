"""Every external download must have a checksum, and no external source may come from a moving ref.

The scan reads MODULE.bazel and the .bzl files of the repository rules as text.
"""

import os
import re
import unittest
from pathlib import Path

FILES = {name: Path(path).read_text() for name, path in
         (item.split("=", 1) for item in os.environ["FILES"].split())}
DOWNLOADING = re.compile(r"\b(http_archive|http_file|http_jar)\(")
MOVING = re.compile(r"\b(git_repository|new_git_repository|local_repository|new_local_repository)\(|\bcommit\s*=|\bbranch\s*=|\btag\s*=\s*\"")


def calls(text, pattern):
    """Yields the text of each call that the pattern opens, up to the matching parenthesis."""
    for match in pattern.finditer(text):
        depth, index = 1, match.end()
        while depth and index < len(text):
            depth += {"(": 1, ")": -1}.get(text[index], 0)
            index += 1
        yield text[match.start():index]


def unpinned(text):
    return [call.split("\n")[0] for call in calls(text, DOWNLOADING)
            if not re.search(r"\b(sha256|integrity)\s*=", call)]


def downloads_without_checksum(text):
    return [call.split("\n")[0] for call in calls(text, re.compile(r"\.download(_and_extract)?\("))
            if not re.search(r"\b(sha256|integrity)\s*=", call)]


class Pinned(unittest.TestCase):
    def test_the_scan_flags_a_download_with_no_checksum(self):
        self.assertEqual(unpinned('http_archive(\n  name = "x",\n  urls = ["u"],\n)'), ["http_archive("])
        self.assertEqual(downloads_without_checksum('rctx.download(url = "u", output = "o")'),
                         ['.download(url = "u", output = "o")'])
        self.assertEqual(unpinned('http_archive(\n  name = "x",\n  sha256 = "ab",\n)'), [])

    def test_the_scan_sees_the_downloads_of_the_repository(self):
        total = sum(len(list(calls(text, DOWNLOADING))) for text in FILES.values())
        self.assertGreaterEqual(total, 7)

    def test_every_http_archive_has_a_checksum(self):
        for name, text in FILES.items():
            self.assertEqual(unpinned(text), [], name)

    def test_no_repository_rule_downloads_without_a_checksum(self):
        for name, text in FILES.items():
            self.assertEqual(downloads_without_checksum(text), [], name)

    def test_no_source_comes_from_a_moving_ref_or_the_host_tree(self):
        for name, text in FILES.items():
            code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
            self.assertIsNone(MOVING.search(code), name)


if __name__ == "__main__":
    unittest.main()
