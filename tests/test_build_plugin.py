"""Tests for the release checks in tools/build_plugin.py."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import build_plugin as bp  # noqa: E402


def errors_for(**changes):
    md = {"name": "X", "qgisMinimumVersion": "3.22", "description": "One line.", "about": "Text.",
          "version": "0.1.0", "author": "A", "email": "a@b.c", "repository": "https://x",
          "tracker": "https://x/issues", "homepage": "https://x", "icon": "icon.png",
          "tags": "irrigation", "category": "Vector", "changelog": "c", "experimental": "True"}
    md.update(changes)
    rep = bp.Report()
    bp.check_metadata(md, rep)
    return rep.errors


class TestReleaseChecks(unittest.TestCase):
    def test_current_metadata_passes(self):
        rep = bp.Report()
        bp.check_metadata(bp.read_metadata(rep), rep)
        self.assertEqual(rep.errors, [])

    def test_valid_example(self):
        self.assertEqual(errors_for(), [])

    def test_detects_problems(self):
        cases = {"category": ("Analysis", "category"), "repository": ("", "repository"),
                 "version": ("v1", "version"), "experimental": ("yes", "experimental"),
                 "about": ("<b>bold</b>", "HTML"), "icon": ("icon.svg", "PNG or JPEG"),
                 "description": ("two\nlines", "single line")}
        for key, (value, word) in cases.items():
            with self.subTest(field=key):
                errs = errors_for(**{key: value})
                self.assertTrue(any(word in e for e in errs), errs)

    def test_package_files(self):
        rep = bp.Report()
        files = bp.collect_files(rep)
        names = {rel for _, rel in files}
        self.assertTrue({"metadata.txt", "__init__.py", "LICENSE", "icon.png"} <= names)
        self.assertFalse([n for n in names if "__pycache__" in n or n.endswith(".pyc")])
        bp.check_package(files, rep)
        self.assertEqual(rep.errors, [])


if __name__ == "__main__":
    unittest.main()
