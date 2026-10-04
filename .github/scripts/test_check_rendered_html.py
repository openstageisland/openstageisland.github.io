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


def page(body: str = "", head: str = "", csp: str | None = None) -> str:
    meta = ""
    if csp is not None:
        meta = (
            '<meta http-equiv="Content-Security-Policy" '
            f'content="{csp}">'
        )
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="description" content="d">\n'
        f"{meta}\n"
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

    def problems_for(self, content: str, baseurl: str = "") -> str:
        path = self.write("index.html", content)
        return " | ".join(mod.check_page(path, self.site, baseurl))

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

    def test_absolute_link_to_same_page_is_checked(self):
        # The global top bar links to the guide as "/#faq". On the guide that
        # is same-document and must resolve; on another page it is out of scope.
        got = self.problems_for(
            page('<h1>x</h1><section id="faq"></section><a href="/#missing">go</a>')
        )
        self.assertIn("missing", got)

    def test_absolute_link_to_same_page_resolves_when_present(self):
        got = self.problems_for(
            page('<h1>x</h1><section id="faq"></section><a href="/#faq">go</a>')
        )
        self.assertEqual(got, "")

    def test_link_to_another_page_is_out_of_scope(self):
        # "/privacy/#faq" from the guide is not this page's anchor to validate.
        got = self.problems_for(page('<h1>x</h1><a href="/privacy/#faq">go</a>'))
        self.assertEqual(got, "")

    def test_nested_page_url_is_derived_correctly(self):
        self.assertEqual(mod.page_url("index.html"), "/")
        self.assertEqual(mod.page_url("privacy/index.html"), "/privacy/")
        self.assertEqual(mod.page_url("live.html"), "/live.html")

    def test_baseurl_prefixed_anchor_is_still_same_document(self):
        # With baseurl "/blog", the top bar emits "/blog/#faq". Without baseurl
        # handling this would be treated as another page and silently skipped.
        got = self.problems_for(
            page('<h1>x</h1><section id="faq"></section><a href="/blog/#missing">go</a>'),
            baseurl="/blog",
        )
        self.assertIn("missing", got)

    def test_baseurl_prefixed_anchor_resolves_when_present(self):
        got = self.problems_for(
            page('<h1>x</h1><section id="faq"></section><a href="/blog/#faq">go</a>'),
            baseurl="/blog",
        )
        self.assertEqual(got, "")

    def test_catches_duplicate_h1(self):
        got = self.problems_for(page("<h1>a</h1><h1>b</h1>"))
        self.assertIn("exactly one <h1>", got)

    def test_zero_h1_message_points_at_the_bom_cause(self):
        # The real cause of a missing h1 on CODE_OF_CONDUCT was a UTF-8 BOM
        # between the front matter and the '#' heading, which stops kramdown
        # treating it as a heading. The message should say so.
        got = self.problems_for(page("<p>no heading here</p>"))
        self.assertIn("BOM", got)

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

    # ---- CSP cross-check
    TIGHT = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'"
    LOOSE = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'"

    def test_unused_unsafe_inline_in_script_src_is_flagged(self):
        # The permission has gone stale and is widening the XSS surface for
        # nothing. This is the direction that rots silently.
        got = self.problems_for(page("<h1>x</h1>", csp=self.LOOSE))
        self.assertIn("drop it to narrow", got)

    def test_tight_script_src_without_inline_script_passes(self):
        got = self.problems_for(page("<h1>x</h1>", csp=self.TIGHT))
        self.assertEqual(got, "")

    def test_inline_script_without_permission_is_flagged(self):
        # The page would be silently broken: the browser blocks the code and
        # nothing in CI notices.
        got = self.problems_for(
            page('<h1>x</h1><script>console.log(1)</script>', csp=self.TIGHT)
        )
        self.assertIn("lacks 'unsafe-inline'", got)

    def test_event_handler_without_permission_is_flagged(self):
        got = self.problems_for(
            page('<h1>x</h1><button onclick="go()">b</button>', csp=self.TIGHT)
        )
        self.assertIn("on*= handler", got)

    def test_inline_script_with_permission_passes(self):
        got = self.problems_for(
            page('<h1>x</h1><script src="/a.js"></script><script>go()</script>',
                 csp=self.LOOSE)
        )
        self.assertEqual(got, "")

    def test_external_script_src_does_not_count_as_inline(self):
        got = self.problems_for(
            page('<h1>x</h1><script src="/a.js" defer></script>', csp=self.LOOSE)
        )
        self.assertIn("drop it", got, "a src= script must not count as inline")

    def test_no_csp_meta_is_not_flagged(self):
        # live.html sits outside the layout and has no CSP; that is a separate
        # concern and must not be reported as a CSP mismatch.
        got = self.problems_for(page("<h1>x</h1>"))
        self.assertEqual(got, "")

    def test_script_src_absent_is_not_flagged(self):
        csp = "default-src 'self'"
        self.assertEqual(self.problems_for(page("<h1>x</h1>", csp=csp)), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
