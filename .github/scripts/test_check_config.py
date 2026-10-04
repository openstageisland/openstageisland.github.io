"""Tests for .github/scripts/check_config.py."""

import importlib.util
import os
import shutil
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "check_config.py")

_spec = importlib.util.spec_from_file_location("check_config", TARGET)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

GOOD = """\
title: Open Stage Island
url: "https://openstageisland.github.io"
baseurl: ""
github_username: openstageisland
plugins:
  - jekyll-seo-tag
exclude:
  - Gemfile
  - tests
  - README.md
"""


class ConfigCheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="osi-cfg-")
        self.path = os.path.join(self.tmp, "_config.yml")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, text: str) -> str:
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return self.path

    def run_check(self):
        return mod.main(["--config", self.path])

    def test_valid_config_passes(self):
        self.write(GOOD)
        self.assertEqual(self.run_check(), 0)

    def test_missing_url_fails(self):
        self.write(GOOD.replace('url: "https://openstageisland.github.io"\n', ""))
        self.assertEqual(self.run_check(), 1)

    def test_missing_github_username_fails(self):
        self.write(GOOD.replace("github_username: openstageisland\n", ""))
        self.assertEqual(self.run_check(), 1)

    def test_missing_seo_tag_plugin_fails(self):
        # The exact latent failure: {% seo %} with no gem registered raises a
        # Liquid syntax error at build time with no useful context.
        self.write(GOOD.replace("plugins:\n  - jekyll-seo-tag\n", ""))
        self.assertEqual(self.run_check(), 1)

    def test_missing_tests_exclude_fails(self):
        self.write(GOOD.replace("  - tests\n", ""))
        self.assertEqual(self.run_check(), 1)

    def test_broken_yaml_fails(self):
        self.write('url: "unterminated\n  bad: [\n')
        self.assertEqual(self.run_check(), 1)

    def test_missing_file_is_an_error(self):
        self.assertEqual(self.run_check(), 2)

    def test_plugin_given_as_string_is_accepted(self):
        self.write(GOOD.replace("plugins:\n  - jekyll-seo-tag\n", "plugins: jekyll-seo-tag\n"))
        self.assertEqual(self.run_check(), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
