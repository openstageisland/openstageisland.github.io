"""Tests for .github/scripts/check_rendered_html.py.

Same reasoning as the artifact gate: this runs only after a real Jekyll build,
which cannot be reproduced here, so the rules themselves are exercised against
synthetic pages. Each rule gets a page that must fail it and a clean page that
must not, to guard against the checker being toothless.

Run with:  python .github/scripts/test_check_rendered_html.py
"""

import importlib.util
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "check_rendered_html.py")

_spec = importlib.util.spec_from_file_location("check_rendered_html", TARGET)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


def page(body: str = "", head: str = "") -> str:
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="description" content="d">\n'
        "<title>T</title>\n"
        f"{head}\n"
        "</head>\n<body>\n"
        "<main id=\"main\">\n"
        f"{body}\n"
        "</main>\n"
        "</body>\n</html>\n"
    )


CLEAN = page(
    "<h1>One</h1>\n"
    '<section id="a"><h2>A</h2><p>x</p></section>\n'
    '<nav><a href="#a">A</a><a href="#b">B</a></nav>\n'
    '<section id="b"><h2>B</h2></section>'
)


class CheckerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="osi-html-")
        self.site = os.path.join(self.tmp, "_site")
        os.makedirs(self.site)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, rel: str, content: str) -> str:
        path = os.path.join(self.site, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
        return path

    def run_check(self):
        return mod.main(["--site", self.site])

    def problems_for(self, content: str) -> str:
        path = self.write("index.html", content)
        return " | ".join(mod.check_page(path, self.site))

    # ---- the happy path must stay green
    def test_clean_page_passes(self):
        self.write("index.html", CLEAN)
        self.write("privacy/index.html", CLEAN)
        self.assertEqual(self.run_check(), 0)

    def test_inline_script_with_braces_is_not_flagged(self):
        # Real pages carry inline JS/CSS; `{{` must only be judged inside a
        # balanced Liquid expression, not any brace pair in a script tag.
        body = "<h1>One</h1><script>var o={a:1};var s=`x`;if(a){b()}</script>"
        self.assertEqual(self.problems_for(page(body)), "")

    # ---- each rule must actually bite
    def test_catches_unrendered_liquid_output(self):
        got = self.problems_for(page("<h1>{{ page.title }}</h1>"))
        self.assertIn("unrendered Liquid output", got)

    def test_catches_unrendered_liquid_tag(self):
        got = self.problems_for(page("<h1>{% seo %}</h1>"))
        self.assertIn("unrendered Liquid tag", got)

    def test_catches_stray_escape_artifact(self):
        # The exact bug class this replaces: a literal `n left in a noscript.
        got = self.problems_for(
            page("<h1>x</h1><noscript>stats`n  View`n</noscript>")
        )
        self.assertIn("stray escape artifact", got)

    def test_catches_duplicate_ids(self):
        got = self.problems_for(
            page('<h1>x</h1><div id="dup"></div><span id="dup"></span>')
        )
        self.assertIn("duplicate element id", got)

    def test_catches_dangling_anchor(self):
        got = self.problems_for(page('<h1>x</h1><a href="#nope">go</a>'))
        self.assertIn("anchor(s) with no target", got)

    def test_catches_duplicate_h1(self):
        got = self.problems_for(page("<h1>a</h1><h1>b</h1>"))
        self.assertIn("exactly one <h1>", got)

    def test_catches_skipped_heading_level(self):
        got = self.problems_for(page("<h1>a</h1><h3>b</h3>"))
        self.assertIn("heading level skipped", got)

    def test_catches_unbalanced_section(self):
        got = self.problems_for(page("<h1>x</h1><section><h2>a</h2>"))
        self.assertIn("unbalanced <section>", got)

    def test_catches_missing_title(self):
        broken = "<!DOCTYPE html><html lang=\"en\"><head><meta name=\"description\" content=\"d\"></head><body><main id=\"main\"><h1>x</h1></main></body></html>"
        got = self.problems_for(broken)
        self.assertIn("<title>", got)

    def test_catches_missing_lang(self):
        broken = CLEAN.replace('<html lang="en">', "<html>")
        self.assertIn("lang=", self.problems_for(broken))

    def test_catches_missing_description(self):
        broken = CLEAN.replace('<meta name="description" content="d">', "")
        self.assertIn("description", self.problems_for(broken))

    def test_catches_missing_doctype(self):
        self.assertIn("DOCTYPE", self.problems_for(CLEAN.replace("<!DOCTYPE html>", "")))

    # ---- invocation errors
    def test_missing_site_is_an_error(self):
        shutil.rmtree(self.site)
        self.assertEqual(self.run_check(), 2)

    def test_no_pages_is_a_failure(self):
        self.assertEqual(self.run_check(), 1)

    def test_failure_exit_code_when_a_page_is_bad(self):
        self.write("index.html", CLEAN)
        self.write("tos/index.html", page("<h1>x</h1>{% seo %}"))
        self.assertEqual(self.run_check(), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
