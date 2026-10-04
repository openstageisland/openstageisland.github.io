#!/usr/bin/env python3
"""Structural validation of the generated HTML in _site/.

Replaces the grep-based checks that previously lived inline in ci.yml.

Why replace them
----------------
Those checks asserted `grep -q '<title>[^<]+</title>'`, which reported every
page as "Missing or empty <title>" even though the rendered pages all carry a
title. The rendered output is correct:

    <title>Open Stage Island - Visitor Guide</title>

so the assertion, not the markup, was wrong. Byte-oriented grep against HTML is
fragile in general - multi-byte characters, entity escaping and the `+`
quantifier over a negated class all change the answer without changing the
document. Parsing the document does not have that failure mode.

Checks, per file:
  1. an <!DOCTYPE html> declaration
  2. <html lang="...">
  3. a non-empty <title>
  4. a <meta name="description"> with non-empty content
  5. balanced <section> / </section>

Emits GitHub Actions ::error:: annotations and exits non-zero on any failure.
Usage: python3 scripts/check-html.py _site
"""

from __future__ import annotations

import os
import sys
from html.parser import HTMLParser

DOCTYPE = "<!DOCTYPE html>"


class Checker(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.has_doctype = False
        self.html_lang = None
        self.title_parts: list = []
        self.in_title = False
        self.description = None
        self.section_open = 0
        self.section_close = 0

    def handle_decl(self, decl: str) -> None:
        if decl.strip().lower() == "doctype html":
            self.has_doctype = True

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "html":
            for key, value in attrs:
                if key == "lang" and value:
                    self.html_lang = value
        elif tag == "title":
            self.in_title = True
        elif tag == "meta":
            d = {k: (v or "") for k, v in attrs}
            if d.get("name", "").lower() == "description":
                self.description = d.get("content", "")
        elif tag == "section":
            self.section_open += 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.in_title = False
        elif tag == "section":
            self.section_close += 1

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_parts.append(data)

    @property
    def title(self) -> str:
        return "".join(self.title_parts).strip()


def check_file(path: str) -> list:
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        text = fh.read()

    problems = []
    if DOCTYPE.lower() not in text.lower():
        problems.append("missing <!DOCTYPE html>")

    parser = Checker()
    try:
        parser.feed(text)
        parser.close()
    except Exception as exc:  # noqa: BLE001
        return problems + [f"unparseable HTML: {exc}"]

    if not parser.has_doctype:
        problems.append("missing <!DOCTYPE html>")
    if not parser.html_lang:
        problems.append('missing <html lang="...">')
    if not parser.title:
        problems.append("missing or empty <title>")
    if not (parser.description or "").strip():
        problems.append('missing or empty <meta name="description">')
    if parser.section_open != parser.section_close:
        problems.append(
            f"unbalanced <section> tags ({parser.section_open} open vs {parser.section_close} close)"
        )
    return problems


def main(argv: list) -> int:
    root = argv[0] if argv else "_site"
    if not os.path.isdir(root):
        print(f"::error file={root}::not a directory")
        return 1

    files = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in sorted(filenames):
            if name.endswith(".html"):
                files.append(os.path.join(dirpath, name).replace("\\", "/"))

    if not files:
        print(f"::error file={root}::no HTML files found")
        return 1

    files.sort()
    failures = 0
    for path in files:
        problems = check_file(path)
        if problems:
            failures += 1
            for problem in problems:
                print(f"::error file={path}::{problem}")

    if failures:
        print(f"{failures} of {len(files)} HTML file(s) failed structural checks", file=sys.stderr)
        return 1

    print(f"{len(files)} HTML file(s) passed structural checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))