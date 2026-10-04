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
HASH_LINK = re.compile(r"href=\"#([^\"]+)\"", re.I)


def find_pages(site_dir: str) -> list[str]:
    pages: list[str] = []
    for root, _dirs, files in os.walk(site_dir):
        for name in files:
            if name.lower().endswith(".html") or name.lower().endswith(".htm"):
                pages.append(os.path.join(root, name))
    return sorted(pages)


def check_page(path: str, site_dir: str) -> list[str]:
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

    # Internal anchors must resolve on the same page.
    dangling = sorted({a for a in HASH_LINK.findall(html) if a and a not in set(ids)})
    if dangling:
        bad("anchor(s) with no target: " + ", ".join(dangling[:6]))

    # Heading structure.
    levels = [int(h[1]) for h in HEADING.findall(html)]
    h1s = levels.count(1)
    if h1s != 1:
        bad(f"expected exactly one <h1>, found {h1s}")
    for a, b in zip(levels, levels[1:]):
        if b - a > 1:
            bad(f"heading level skipped: h{a} -> h{b}")
            break

    return problems


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", default="_site")
    args = parser.parse_args(argv)

    if not os.path.isdir(args.site):
        print(f"::error::{args.site}/ does not exist - did the build run?")
        return 2

    pages = find_pages(args.site)
    if not pages:
        print(f"::error::no HTML pages found under {args.site}/")
        return 1

    all_problems: list[str] = []
    for page in pages:
        all_problems.extend(check_page(page, args.site))

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
