#!/usr/bin/env python3
"""Structural assertions over the HTML that Jekyll actually generated.

This is the gate that can only run after a real build, so it deliberately
checks the things that are impossible to catch from source:

  - unrendered Liquid (``{{ ... }}`` / ``{% ... %}``) leaking into output
  - duplicate element ids, which silently break ``#anchor`` navigation
  - internal ``href="#id"`` links pointing at ids that do not exist on the page
  - heading structure: exactly one h1, no skipped levels
  - the basics the previous inline grep step checked (doctype, lang, title,
    description, balanced <section>)

Every rule is a hard failure. They are all properties of a correct page, so a
violation is a real defect rather than a style opinion.

Usage:
    check_rendered_html.py [--site _site]

Exit codes: 0 all pages pass, 1 violations found, 2 bad invocation.
"""

from __future__ import annotations

import argparse
import os
import re
import sys

# A Liquid tag or output that survived rendering. Balanced braces are required
# so that legitimate CSS/JS in inline <style>/<script> (e.g. `${x}`) does not
# trip the check, and so a stray "{%" inside prose still gets caught.
LIQUID_TAG = re.compile(r"\{%-?.*?-?%\}", re.S)
LIQUID_OUTPUT = re.compile(r"\{\{.*?\}\}", re.S)

# The class of bug this replaced: a stray newline escape inside a <noscript>
# block rendering as visible text.
BACKTICK_ARTIFACT = re.compile(r"`[nr]\b")

HEADING = re.compile(r"<(h[1-6])[\s>]", re.I)
ID_ATTR = re.compile(r"\sid=\"([^\"]+)\"", re.I)
ANY_LINK = re.compile(r"href=\"([^\"]+)\"", re.I)

# Security-relevant patterns for cross-checking the Content-Security-Policy.
# The policy value is delimited by the same quote character it opens with, and
# it contains single quotes of its own ('self', 'unsafe-inline'), so a
# backreference is required -- a [^"'] class would stop at the first 'self'.
CSP_META = re.compile(
    r"<meta[^>]*http-equiv=[\"']Content-Security-Policy[\"'][^>]*"
    r"content=(?P<q>[\"'])(?P<policy>.*?)(?P=q)",
    re.I | re.S,
)
INLINE_SCRIPT = re.compile(r"<script(?![^>]*\ssrc=)[^>]*>", re.I)
# on*="..." as an attribute, e.g. onclick=, onerror=, onload=
EVENT_ATTR = re.compile(r"\son[a-z]+\s*=\s*[\"']", re.I)


def page_url(rel: str) -> str:
    """Map an output file to the URL a browser would request for it."""
    url = "/" + rel
    if url.endswith("/index.html"):
        return url[: -len("index.html")]
    return url


def find_pages(site_dir: str) -> list[str]:
    pages: list[str] = []
    for root, _dirs, files in os.walk(site_dir):
        for name in files:
            if name.lower().endswith(".html") or name.lower().endswith(".htm"):
                pages.append(os.path.join(root, name))
    return sorted(pages)


def check_csp(html: str, rel: str) -> list[str]:
    """Cross-check the page's CSP against the inline script it actually contains.

    Two directions, both worth enforcing:

      - inline script or an on*= handler while script-src lacks
        'unsafe-inline' means the page is silently broken: the browser blocks
        the code and nothing in CI notices.
      - 'unsafe-inline' in script-src when the page contains no inline script
        at all means the permission has gone stale and is quietly widening the
        XSS surface. That is the failure this whole gate exists to prevent, so
        it is reported rather than left to rot.
    """
    problems: list[str] = []
    match = CSP_META.search(html)
    if not match:
        return problems

    policy = match.group("policy")
    directives: dict[str, str] = {}
    for part in policy.split(";"):
        tokens = part.split()
        if tokens:
            directives[tokens[0].lower()] = " ".join(t for t in tokens[1:])

    script_src = directives.get("script-src", "")
    if not script_src:
        return problems  # absent script-src falls back to default-src; not checked

    inline_scripts = len(INLINE_SCRIPT.findall(html))
    event_handlers = len(EVENT_ATTR.findall(html))
    inline_total = inline_scripts + event_handlers
    permits_inline = "'unsafe-inline'" in script_src

    if inline_total and not permits_inline:
        kinds = []
        if inline_scripts:
            kinds.append(f"{inline_scripts} inline <script>")
        if event_handlers:
            kinds.append(f"{event_handlers} on*= handler(s)")
        problems.append(
            f"CSP script-src lacks 'unsafe-inline' but the page has "
            f"{' and '.join(kinds)}; the browser will block them"
        )
    elif permits_inline and inline_total == 0:
        problems.append(
            "CSP script-src grants 'unsafe-inline' but the page has no inline "
            "script or event handler; drop it to narrow the XSS surface"
        )
    return problems


def check_page(path: str, site_dir: str, baseurl: str = "") -> list[str]:
    rel = os.path.relpath(path, site_dir).replace(os.sep, "/")
    with open(path, encoding="utf-8", errors="replace") as fh:
        html = fh.read()

    problems: list[str] = []

    def bad(msg: str) -> None:
        problems.append(f"{rel}: {msg}")

    low = html.lower()

    if "<!doctype html>" not in low:
        bad("missing <!DOCTYPE html>")
    if not re.search(r"<html[^>]*\blang=", html, re.I):
        bad("missing <html lang=...>")

    m = re.search(r"<title>(.*?)</title>", html, re.I | re.S)
    if not m or not m.group(1).strip():
        bad("missing or empty <title>")
    if not re.search(r'name="description"', html, re.I):
        bad('missing meta name="description"')

    for tag in ("section", "div", "ul", "ol", "li", "main", "nav"):
        opened = len(re.findall(r"<%s\b" % tag, html, re.I))
        closed = len(re.findall(r"</%s>" % tag, html, re.I))
        if opened != closed:
            bad(f"unbalanced <{tag}>: {opened} open vs {closed} close")

    # Unrendered Liquid. A {{ or {% in shipped output is always a bug.
    for pattern, label in ((LIQUID_TAG, "Liquid tag"), (LIQUID_OUTPUT, "Liquid output")):
        found = pattern.search(html)
        if found:
            snippet = " ".join(found.group(0).split())[:60]
            bad(f"unrendered {label} in output: {snippet!r}")

    stray = BACKTICK_ARTIFACT.search(html)
    if stray:
        bad(f"stray escape artifact {stray.group(0)!r} rendered as text")

    # Duplicate ids break getElementById and #anchor navigation.
    ids = ID_ATTR.findall(html)
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        bad("duplicate element id(s): " + ", ".join(dupes[:6]))

    # Internal anchors must resolve on the same page. Both bare fragments
    # ("#faq") and absolute links to this same page ("/#faq", used by the global
    # top bar) count as same-document; a link to a *different* page is out of
    # scope here and is left to the reference validator.
    #
    # baseurl matters: with a non-empty baseurl every generated path is
    # prefixed, so comparing raw hrefs against the output-relative URL would
    # silently exempt every anchor. With --baseurl passed, coverage is kept.
    me = page_url(rel)
    dangling = set()
    checked = 0
    for href in ANY_LINK.findall(html):
        hash_at = href.find("#")
        if hash_at == -1:
            continue
        frag = href[hash_at + 1:]
        if not frag:
            continue
        path = href[:hash_at].split("?")[0]
        if baseurl:
            if path == baseurl:
                path = "/"
            elif path.startswith(baseurl + "/"):
                path = path[len(baseurl):]
        if path and path != me:
            continue
        checked += 1
        if frag not in set(ids):
            dangling.add(frag)
    if dangling:
        bad("anchor(s) with no target: " + ", ".join(sorted(dangling)[:8]))
    elif baseurl and checked == 0:
        print(
            f"::warning file={args.site}/{rel}::no same-document anchors were checked; "
            f"is --baseurl {baseurl!r} correct?"
        )

    # Heading structure.
    levels = [int(h[1]) for h in HEADING.findall(html)]
    h1s = levels.count(1)
    if h1s != 1:
        bad(
            f"expected exactly one <h1>, found {h1s}"
            + (" — a UTF-8 BOM before a Markdown '#' heading stops kramdown"
               " recognising it, so the line renders as literal text"
               if h1s == 0 else "")
        )
    for a, b in zip(levels, levels[1:]):
        if b - a > 1:
            bad(f"heading level skipped: h{a} -> h{b}")
            break

    for problem in check_csp(html, rel):
        bad(problem)

    return problems


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", default="_site")
    parser.add_argument("--baseurl", default="",
                        help="site.baseurl, so root-absolute anchors are still "
                             "recognised as same-document")
    args = parser.parse_args(argv)

    if not os.path.isdir(args.site):
        print(f"::error::{args.site}/ does not exist - did the build run?")
        return 2

    baseurl = args.baseurl.strip().rstrip("/")

    pages = find_pages(args.site)
    if not pages:
        print(f"::error::no HTML pages found under {args.site}/")
        return 1

    all_problems: list[str] = []
    for page in pages:
        all_problems.extend(check_page(page, args.site, baseurl))

    if all_problems:
        print(f"::error::{len(all_problems)} structural problem(s) in {len(pages)} page(s):")
        for problem in all_problems[:40]:
            print(f"::error file={args.site}/{problem.split(':')[0]}::{problem.split(': ', 1)[1]}")
        if len(all_problems) > 40:
            print(f"::error::... and {len(all_problems) - 40} more")
        return 1

    print(f"OK   {len(pages)} page(s) passed all structural checks")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
