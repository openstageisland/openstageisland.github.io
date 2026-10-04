"""Tests for .github/scripts/check_css_tokens.py."""

import importlib.util
import os
import shutil
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "check_css_tokens.py")

_spec = importlib.util.spec_from_file_location("check_css_tokens", TARGET)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


SHARED = """:root { --ai-dock-z: 1000; }
.x { color: var(--fg, #eceff1); background: var(--bg-card, #0f1318);
     border-color: var(--border, #1a2030); }
.y { color: var(--green, #00cc88); }
"""

SITE_LIGHT = """:root {
  --color-bg: #f5f5f5; --color-surface: #ffffff; --color-text: #333333;
  --color-border: #e5e7eb; --color-accent: #4a90d9; --color-accent-hover: #357abd;
}
"""

BRIDGE = """:root {
  --fg: var(--color-text); --bg-card: var(--color-surface);
  --border: var(--color-border); --accent: var(--color-accent);
}
"""


class TokenGateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="osi-tokens-")
        self.write("assets/css/network-ux.css", SHARED)
        self.write("assets/style.css", SITE_LIGHT)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, rel, content):
        path = os.path.join(self.tmp, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)

    def run_gate(self):
        return mod.main(["--site", self.tmp])

    def test_missing_bridge_fails(self):
        self.assertEqual(self.run_gate(), 1)

    def test_bridge_makes_it_pass(self):
        self.write("assets/css/site-chrome.css", BRIDGE)
        self.assertEqual(self.run_gate(), 0)

    def test_shared_css_may_define_its_own_tokens(self):
        # A token the shared sheet both reads and declares needs no alias.
        self.write("assets/css/network-ux.css", ":root { --fg: #fff; }\n" + SHARED)
        self.write("assets/css/site-chrome.css", BRIDGE)
        self.assertEqual(self.run_gate(), 0)

    def test_status_colours_may_stay_unresolved(self):
        # A fixed value is the correct behaviour for a status colour, so --green
        # must not be reported.
        self.write("assets/css/site-chrome.css", BRIDGE)
        self.assertEqual(self.run_gate(), 0)

    def test_alias_must_be_in_a_root_that_is_actually_loaded(self):
        # Declaring the bridge in a stylesheet nothing links would not help, so
        # the gate only trusts the two files the layout actually loads.
        self.write("assets/css/unused.css", BRIDGE)
        self.assertEqual(self.run_gate(), 1)

    def test_missing_site_dir_is_an_error(self):
        shutil.rmtree(self.tmp)
        self.assertEqual(self.run_gate(), 2)

    def test_missing_shared_sheets_is_not_a_failure(self):
        # Only network-ux.css present; auth-bar.css absent must not crash.
        os.remove(os.path.join(self.tmp, "assets", "css", "network-ux.css"))
        os.remove(os.path.join(self.tmp, "assets", "style.css"))
        self.assertEqual(self.run_gate(), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
