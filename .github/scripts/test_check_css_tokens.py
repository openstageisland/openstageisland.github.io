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

    def test_alias_in_any_local_stylesheet_counts(self):
        # The site sheets are discovered by glob, not a fixed list, so the gate
        # stays correct on a site whose palette lives in assets/main.css.
        self.write("assets/css/palette.css", ":root { --fg: #333; --bg-card: #fff; --border: #ddd; --accent: #09f; }")
        self.assertEqual(self.run_gate(), 0)

    def test_a_token_defined_only_in_a_shared_sheet_needs_no_alias(self):
        self.write("assets/css/network-ux.css", ":root { --fg: #fff; }\n" + SHARED)
        self.write("assets/css/site-chrome.css", BRIDGE)
        self.assertEqual(self.run_gate(), 0)

    def test_commented_out_declaration_does_not_count(self):
        # The silent-pass failure mode this gate exists to prevent: leaving the
        # explanation of a deleted bridge behind would otherwise still satisfy it.
        self.write("assets/css/site-chrome.css",
                   "/* retired bridge:\n   :root { --fg: #333; --bg-card: #fff; "
                   "--border: #ddd; --accent: #09f; }\n*/\n")
        self.assertEqual(self.run_gate(), 1)

    def test_commented_var_reference_is_not_a_real_read(self):
        # Prose mentioning var(--green) must not make an unresolved --green count
        # as read in a way that masks a genuine mismatch.
        self.write("assets/css/network-ux.css",
                   SHARED + "\n/* documentation: var(--fg) explains the alias */\n")
        self.assertEqual(self.run_gate(), 1)

    def test_allowlist_holds_no_entries_the_shared_css_never_reads(self):
        # The allowlist is sized against the real synced stylesheets, not against
        # a fixture, so this invariant can only be checked against the repo.
        # An entry nothing reads is a false promise of cover: it implies a token
        # was reviewed when it may never have existed.
        repo = os.path.normpath(os.path.join(HERE, "..", ".."))
        used = set()
        found_any = False
        for rel in mod.SHARED_STYLESHEETS:
            path = os.path.join(repo, *rel.split("/"))
            if os.path.isfile(path):
                found_any = True
                with open(path, encoding="utf-8", errors="replace") as fh:
                    used |= set(mod.USE.findall(mod.COMMENT.sub(" ", fh.read())))
        if not found_any:
            self.skipTest("shared stylesheets not present in this checkout")
        stale = mod.ALLOWED_UNRESOLVED - used
        self.assertEqual(
            sorted(stale), [],
            f"allowlist entries the shared CSS never reads: {sorted(stale)}",
        )

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
