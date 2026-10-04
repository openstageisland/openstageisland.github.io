"""Tests for .github/scripts/check_local_references.py.

The pipeline this replaces skipped every reference beginning with "/" and, on
this site, therefore inspected nothing at all. These tests pin the behaviour
that was missing: root-absolute references must be resolved, missing assets must
fail, and missing page links must only warn.
"""

import importlib.util
import os
import shutil
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "check_local_references.py")

_spec = importlib.util.spec_from_file_location("check_local_references", TARGET)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)

CONFIG = 'title: t\nurl: "https://example.github.io"\nbaseurl: ""\n'


def page(body: str) -> str:
    return (
        "<!DOCTYPE html><html lang=\"en\"><head>"
        '<meta name="description" content="d"><title>T</title>'
        "</head><body>" + body + "</body></html>"
    )


class ReferenceCheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="osi-refs-")
        self.site = os.path.join(self.tmp, "_site")
        self.config = os.path.join(self.tmp, "_config.yml")
        os.makedirs(self.site)
        with open(self.config, "w", encoding="utf-8") as fh:
            fh.write(CONFIG)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, rel: str, content: str = "x") -> None:
        path = os.path.join(self.site, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)

    def run_check(self):
        return mod.main(["--site", self.site, "--config", self.config])

    def errors_for(self, body: str, baseurl: str = ""):
        path = os.path.join(self.site, "index.html")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(page(body))
        return mod.check_page(path, self.site, baseurl)[0]

    # ---- the behaviour the old pipeline lacked
    def test_root_absolute_asset_that_exists_resolves(self):
        self.write("assets/css/site-chrome.css")
        self.write("index.html", page('<link rel="stylesheet" href="/assets/css/site-chrome.css">'))
        self.assertEqual(self.run_check(), 0)

    def test_root_absolute_asset_that_is_missing_fails(self):
        self.write("index.html", page('<script src="/assets/js/gone.js"></script>'))
        self.assertEqual(self.run_check(), 1)

    def test_missing_stylesheet_fails(self):
        self.write("index.html", page('<link rel="stylesheet" href="/assets/style.css">'))
        self.assertEqual(self.run_check(), 1)

    def test_missing_image_fails(self):
        self.write("index.html", page('<img src="/images/hero.png">'))
        self.assertEqual(self.run_check(), 1)

    def test_missing_page_link_only_warns(self):
        # The network's shared partials link to /privacy/ and /tos/, which only
        # the hub site serves. Satellite sites must not fail on those.
        self.write("index.html", page('<a href="/privacy/">Privacy</a>'))
        self.assertEqual(self.run_check(), 0)

    def test_existing_page_route_resolves(self):
        self.write("privacy/index.html", page("<p>p</p>"))
        self.write("index.html", page('<a href="/privacy/">Privacy</a>'))
        self.assertEqual(self.run_check(), 0)

    def test_root_index_resolves(self):
        self.write("index.html", page('<a href="/">Home</a>'))
        self.assertEqual(self.run_check(), 0)

    # ---- relative references
    def test_relative_asset_resolves_against_page_directory(self):
        self.write("assets/js/app.js")
        self.write("privacy/index.html", page('<script src="../assets/js/app.js"></script>'))
        self.assertEqual(self.run_check(), 0)

    def test_relative_asset_missing_fails(self):
        self.write("privacy/index.html", page('<script src="../assets/js/nope.js"></script>'))
        self.assertEqual(self.run_check(), 1)

    # ---- noise that must be ignored
    def test_external_and_special_schemes_are_skipped(self):
        self.write("index.html", page(
            '<a href="https://example.com/">e</a>'
            '<a href="//cdn.example.com/x">c</a>'
            '<a href="mailto:a@b.c">m</a>'
            '<img src="data:image/png;base64,AAA">'
            '<a href="secondlife://Derwent/248/128/22">sl</a>'
            '<a href="#top">t</a>'
            '<a href="">blank</a>'
        ))
        self.assertEqual(self.run_check(), 0)

    def test_query_and_fragment_are_stripped_before_resolving(self):
        self.write("assets/js/app.js")
        self.write("index.html", page('<script src="/assets/js/app.js?v=2#x"></script>'))
        self.assertEqual(self.run_check(), 0)

    # ---- baseurl handling: the silent-coverage-loss risk
    def test_baseurl_prefix_is_stripped(self):
        self.write("assets/js/app.js")
        self.write("index.html", page('<script src="/blog/assets/js/app.js"></script>'))
        self.assertEqual(mod.check_page(os.path.join(self.site, "index.html"), self.site, "/blog")[0], [])

    def test_path_outside_baseurl_is_skipped_not_flagged(self):
        # Another mount entirely; not this build's problem.
        self.write("index.html", page('<a href="/elsewhere/thing/">x</a>'))
        self.assertEqual(mod.check_page(os.path.join(self.site, "index.html"), self.site, "/blog")[0], [])

    def test_baseurl_equal_to_root_resolves(self):
        self.write("assets/js/app.js")
        self.write("index.html", page('<script src="/assets/js/app.js"></script>'))
        self.assertEqual(mod.check_page(os.path.join(self.site, "index.html"), self.site, "/")[0], [])

    def test_missing_config_warns_but_does_not_crash(self):
        os.remove(self.config)
        self.write("index.html", page("<p>x</p>"))
        self.assertEqual(self.run_check(), 0)

    # ---- classification
    def test_classify_splits_assets_from_pages(self):
        self.assertEqual(mod.classify("/a/style.css"), "asset")
        self.assertEqual(mod.classify("/a/app.js"), "asset")
        self.assertEqual(mod.classify("/img/x.PNG"), "asset")
        self.assertEqual(mod.classify("/privacy/"), "page")
        self.assertEqual(mod.classify("/dashboard/"), "page")

    def test_page_url_derivation(self):
        self.assertEqual(mod.page_url("index.html"), "/")
        self.assertEqual(mod.page_url("privacy/index.html"), "/privacy/")

    # ---- invocation errors
    def test_missing_site_is_an_error(self):
        shutil.rmtree(self.site)
        self.assertEqual(self.run_check(), 2)

    def test_no_pages_is_an_error(self):
        self.assertEqual(self.run_check(), 1)

    # ---- mirrors the real homepage, to de-risk a spurious CI failure
    def test_real_homepage_shape_passes_with_warnings_only(self):
        """The deployed homepage's exact reference profile.

        Every asset it references exists; the three unresolved references are
        page routes (/dashboard/, /privacy/, /tos/) coming from the network's
        shared partials. Those must warn, not fail, or every deploy blocks.
        """
        for asset in (
            "assets/style.css",
            "assets/css/network-ux.css",
            "assets/css/auth-bar.css",
            "assets/css/site-chrome.css",
            "assets/js/auth-bar.js",
            "assets/js/live-data.js",
            "assets/js/network-ux.js",
            "assets/js/section-nav.js",
            "images/destination-image.png",
        ):
            self.write(asset)
        self.write("index.html", page(
            '<link rel="stylesheet" href="/assets/style.css">'
            '<link rel="stylesheet" href="/assets/css/network-ux.css">'
            '<link rel="stylesheet" href="/assets/css/auth-bar.css">'
            '<link rel="stylesheet" href="/assets/css/site-chrome.css">'
            '<script src="/assets/js/auth-bar.js" defer></script>'
            '<script src="/assets/js/live-data.js" defer></script>'
            '<script src="/assets/js/network-ux.js" defer></script>'
            '<script src="/assets/js/section-nav.js" defer></script>'
            '<img src="/images/destination-image.png">'
            '<a href="/">Home</a>'
            '<a href="/dashboard/">Dashboard</a>'
            '<a href="/privacy/">Privacy</a>'
            '<a href="/tos/">Terms of Service</a>'
            '<a href="https://secondlife.com/destination/open-stage-island">SL</a>'
            '<a href="#welcome">Guide</a>'
        ))
        self.assertEqual(self.run_check(), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
