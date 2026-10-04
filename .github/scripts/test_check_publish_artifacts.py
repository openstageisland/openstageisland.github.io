"""Tests for .github/scripts/check_publish_artifacts.py.

An unverified CI gate is worse than no gate: a false positive blocks every
deploy. So the gate is exercised here against synthetic _site trees covering
both the leak it exists to catch and the shapes that must stay legal.

Run with:  python -m unittest discover -s .github/scripts -v
       or: python .github/scripts/test_check_publish_artifacts.py
"""

import importlib.util
import os
import shutil
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "check_publish_artifacts.py")

_spec = importlib.util.spec_from_file_location("check_publish_artifacts", TARGET)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


def write(root: str, rel: str, content: str = "x") -> None:
    path = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)


CONFIG = """\
title: Test
url: "https://example.github.io"
github_username: example
exclude:
  - Gemfile
  - Gemfile.lock
  - node_modules
  - vendor
  - .github
  - tests
  - README.md
  - LICENSE
  - "*.ps1"
  - "*.sh"
"""


class GateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="osi-gate-")
        self.site = os.path.join(self.tmp, "_site")
        self.config = os.path.join(self.tmp, "_config.yml")
        os.makedirs(self.site)
        with open(self.config, "w", encoding="utf-8") as fh:
            fh.write(CONFIG)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_gate(self):
        return mod.main(["--site", self.site, "--config", self.config])

    # ---- must FAIL: the leak this gate exists to catch
    def test_rejects_published_tests_directory(self):
        write(self.site, "tests/section-nav.test.js", "test source")
        self.assertEqual(self.run_gate(), 1)

    def test_rejects_gemfile(self):
        write(self.site, "Gemfile", 'source "https://rubygems.org"')
        self.assertEqual(self.run_gate(), 1)

    def test_rejects_nested_excluded_dir(self):
        write(self.site, "assets/vendor/lib.js", "vendored")
        self.assertEqual(self.run_gate(), 1)

    def test_rejects_stray_script_and_backup_files(self):
        write(self.site, "scratch.py", "print(1)")
        write(self.site, "notes.bak", "old")
        self.assertEqual(self.run_gate(), 1)

    def test_rejects_readme_and_license(self):
        write(self.site, "README.md", "# hi")
        write(self.site, "LICENSE", "MIT")
        self.assertEqual(self.run_gate(), 1)

    def test_rejects_workflow_yaml(self):
        write(self.site, "ci.yml", "name: ci")
        self.assertEqual(self.run_gate(), 1)

    def test_rejects_pycache(self):
        write(self.site, "__pycache__/mod.cpython-312.pyc", "bin")
        self.assertEqual(self.run_gate(), 1)

    # ---- must PASS: the shapes a real build legitimately produces
    def test_accepts_normal_build_output(self):
        write(self.site, "index.html", '<a href="/assets/js/section-nav.js">x</a>')
        write(self.site, "assets/js/section-nav.js", "console.log(1)")
        write(self.site, "assets/css/site-chrome.css", "body{}")
        write(self.site, "images/destination-image.png", "png")
        write(self.site, "privacy/index.html", "<html></html>")
        write(self.site, "CNAME", "openstageis.land")
        write(self.site, "data.json", "{}")
        self.assertEqual(self.run_gate(), 0)

    def test_accepts_empty_site(self):
        self.assertEqual(self.run_gate(), 0)

    def test_orphaned_asset_warns_but_does_not_fail(self):
        # Prevents the gate from blocking deploys on conditionally-loaded files.
        write(self.site, "index.html", "<html></html>")
        write(self.site, "assets/js/never-loaded.js", "console.log(1)")
        self.assertEqual(self.run_gate(), 0)

    def test_leaked_underscore_dir_warns_but_does_not_fail(self):
        write(self.site, "_layouts/default.html", "<html></html>")
        self.assertEqual(self.run_gate(), 0)

    # ---- invocation errors must be loud, not silently green
    def test_missing_site_dir_is_an_error(self):
        shutil.rmtree(self.site)
        self.assertEqual(self.run_gate(), 2)

    def test_missing_config_is_an_error(self):
        os.remove(self.config)
        self.assertEqual(self.run_gate(), 2)

    # ---- exclude list is genuinely derived from the config
    def test_forbidden_set_tracks_the_config(self):
        patterns = mod.build_forbidden(["tests", "*.ps1"])
        self.assertTrue(any("tests" in p for p in patterns))
        self.assertIn("*.ps1", patterns)
        self.assertIn("*/tests", patterns, "a bare dir name must match at depth")
        self.assertIn("*/tests/*", patterns, "and its contents too")

    def test_exclude_parsed_without_pyyaml(self):
        entries = mod.load_exclude(self.config)
        for expected in ("Gemfile", "tests", "*.ps1", "*.sh"):
            self.assertIn(expected, entries)

    def test_matching_is_case_insensitive_on_every_platform(self):
        # fnmatch.fnmatch() folds case via os.path.normcase, which is a no-op on
        # Linux but lowercases on Windows. The gate must not change strictness
        # depending on the runner, so it matches case-insensitively everywhere.
        patterns = mod.build_forbidden(["tests"])
        self.assertTrue(mod.is_forbidden("tests", patterns))
        self.assertTrue(
            mod.is_forbidden("Tests", patterns), "a differently-cased path must still be caught"
        )
        self.assertTrue(mod.is_forbidden("TESTS/section-nav.test.js", patterns))
        self.assertFalse(
            mod.is_forbidden("testimony/index.html", patterns),
            "unrelated names must not be swept up",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
