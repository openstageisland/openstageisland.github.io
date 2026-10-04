#!/usr/bin/env python3
"""Verify that local href/src references in the built site resolve.

Replaces an inline shell pipeline that skipped every reference beginning with
"/". Because `relative_url` emits root-absolute paths when `baseurl` is empty,
that pipeline inspected *zero* references on this site while reporting success
-- a gate that cannot fail. It missed three live 404s (/dashboard/, /privacy/,
/tos/).

Severity split:
  - missing assets (css, js, images, fonts) -> error, fails the build. A broken
    stylesheet or script is a broken page.
  - missing page links -> warning. The network's shared partials link to pages
    (/privacy/, /tos/, /dashboard/) that only the hub site serves, so these are
    expected on the satellite sites and must not block deploys.

Usage:
    check_local_references.py [--site _site] [--config _config.yml]

Exit codes: 0 no errors (warnings allowed), 1 broken assets, 2 bad invocation.
"""

from __future__ import annotations

import argparse
import os
import posixpath
import re
import sys

# href/src prefixes that are not local file references.
SKIP_PREFIXES = (
    "http://", "https://", "//", "mailto:", "data:", "javascript:",
    "secondlife:", "tel:", "sms:", "ftp://", "irc:", "news:", "feed:",
)

# A reference with one of these extensions is an asset: missing means the page
# is broken, so it fails the build.
ASSET_EXTENSIONS = {
    ".css", ".js", ".mjs", ".map",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".avif", ".ico", ".bmp",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".mp3", ".mp4", ".webm", ".ogg", ".wav",
    ".json", ".xml", ".txt", ".pdf", ".zip",
}

# <script>/<style> bodies are not markup. Inline JS frequently builds HTML as
# string concatenation -- live.html has '<a href="' + DEST_URL + '" ...' -- and a
# naive href/src scan reads that as a reference to the literal text
# "' + DEST_URL + '". The tags are kept (so CSP rules can still see them); only
# the bodies are dropped.
SCRIPT_STYLE_BODY = re.compile(
    r"(<(?:script|style)\b[^>]*>).*?(</(?:script|style)\s*>)",
    re.I | re.S,
)
HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)


def strip_non_markup(html: str) -> str:
    """Blank out comments and <script>/<style> bodies, keeping the tags."""
    html = HTML_COMMENT.sub(" ", html)
    return SCRIPT_STYLE_BODY.sub(r"\1\2", html)


def load_baseurl(config_path: str) -> str:
    """Read site.baseurl so root-absolute refs can be mapped into _site.

    A non-empty baseurl that this script cannot see would make every
    root-absolute reference look like it belongs to another mount, and those
    references would be skipped silently -- the same failure mode this script
    exists to end. So an unreadable or malformed config is reported loudly
    rather than treated as "no baseurl".
    """
    if not os.path.isfile(config_path):
        print(f"::warning::{config_path} not found; assuming baseurl is empty")
        return ""
    try:
        import yaml  # type: ignore
    except ImportError:
        print("::warning::PyYAML unavailable; assuming baseurl is empty")
        return ""
    try:
        with open(config_path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except Exception as exc:  # noqa: BLE001 - yaml raises several types
        print(f"::warning::could not parse {config_path} ({exc}); assuming baseurl is empty")
        return ""
    base = str(data.get("baseurl") or "").strip()
    if base and not base.startswith("/"):
        base = "/" + base
    return base.rstrip("/")


def page_url(rel: str) -> str:
    url = "/" + rel.replace(os.sep, "/")
    if url.endswith("/index.html"):
        return url[: -len("index.html")]
    return url


def strip_url_noise(ref: str) -> str:
    """Drop fragment and query, leaving the path portion."""
    ref = ref.split("#", 1)[0]
    ref = ref.split("?", 1)[0]
    return ref.strip()


def classify(ref_path: str) -> str:
    ext = posixpath.splitext(ref_path)[1].lower()
    return "asset" if ext in ASSET_EXTENSIONS else "page"


def resolves(site_dir: str, target: str) -> bool:
    """True when target names a file, a directory, or a directory index."""
    if not target:
        return False
    path = os.path.join(site_dir, *target.split("/"))
    if os.path.isfile(path):
        return True
    if os.path.isdir(path):
        return True
    # A route like /privacy/ is satisfied by privacy/index.html
    if target.endswith("/"):
        return os.path.isfile(os.path.join(path, "index.html"))
    return False


def find_pages(site_dir: str) -> list[str]:
    pages: list[str] = []
    for root, _dirs, files in os.walk(site_dir):
        for name in files:
            if name.lower().endswith((".html", ".htm")):
                pages.append(os.path.join(root, name))
    return sorted(pages)


def check_page(path: str, site_dir: str, baseurl: str) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Return (asset_errors, page_warnings) for one built page."""
    rel = os.path.relpath(path, site_dir).replace(os.sep, "/")
    me = page_url(rel)
    me_dir = posixpath.dirname(me) or "/"

    with open(path, encoding="utf-8", errors="replace") as fh:
        html = strip_non_markup(fh.read())

    errors: list[tuple[str, str]] = []
    warnings: list[tuple[str, str]] = []

    idx = 0
    while True:
        found = -1
        marker = None
        for m in ('href="', 'src="'):
            at = html.find(m, idx)
            if at != -1 and (found == -1 or at < found):
                found, marker = at, m
        if found == -1 or marker is None:
            break
        start = found + len(marker)
        end = html.find('"', start)
        if end == -1:
            break
        idx = end
        raw = html[start:end]
        ref = strip_url_noise(raw)
        if not ref or ref.startswith(SKIP_PREFIXES) or ref.startswith("#"):
            continue

        if ref.startswith("/"):
            target = ref
            if baseurl:
                if target == baseurl:
                    target = "/"
                elif target.startswith(baseurl + "/"):
                    target = target[len(baseurl):]
                else:
                    # Outside the configured baseurl: another mount, not ours.
                    continue
            target = target.lstrip("/")
        else:
            target = posixpath.normpath(posixpath.join(me_dir, ref)).lstrip("/")

        if not target or target == ".":
            continue
        if resolves(site_dir, target):
            continue

        entry = (rel, raw)
        if classify(ref) == "asset":
            errors.append(entry)
        else:
            warnings.append(entry)

    return errors, warnings


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", default="_site")
    parser.add_argument("--config", default="_config.yml")
    args = parser.parse_args(argv)

    if not os.path.isdir(args.site):
        print(f"::error::{args.site}/ does not exist - did the build run?")
        return 2

    baseurl = load_baseurl(args.config)
    pages = find_pages(args.site)
    if not pages:
        print(f"::error::no HTML pages found under {args.site}/")
        return 1

    all_errors: list[tuple[str, str]] = []
    all_warnings: list[tuple[str, str]] = []
    for page in pages:
        e, w = check_page(page, args.site, baseurl)
        all_errors.extend(e)
        all_warnings.extend(w)

    # Aggregate by target so one bad link repeated across pages is one line.
    def report(entries: list[tuple[str, str]], level: str) -> None:
        pages_by_ref: dict[str, set[str]] = {}
        for page_name, ref in entries:
            pages_by_ref.setdefault(ref, set()).add(page_name)
        for ref in sorted(pages_by_ref):
            where = ", ".join(sorted(pages_by_ref[ref]))
            print(f"::{level} file={args.site}::'{ref}' referenced by: {where}")

    report(all_errors, "error")
    report(all_warnings, "warning")

    print(
        f"Local reference check: {len(pages)} page(s), "
        f"{len(all_errors)} broken asset(s), {len(all_warnings)} unresolved page link(s)"
        + (f" (baseurl {baseurl!r})" if baseurl else "")
    )

    return 1 if all_errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
