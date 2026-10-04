#!/usr/bin/env python3
"""Fail the build if anything unwanted reaches the published _site tree.

Why this exists
---------------
`_config.yml`'s `exclude:` list is the only thing standing between the repo's
working files and the public site. It is easy to add a directory (tests/, a
scratch dir, vendored code) and never notice it is being copied verbatim into
_site/ and served. This gate turns that silent failure into a build failure.

The forbidden set is derived from `_config.yml` itself rather than hardcoded,
so the two cannot drift: whatever the config claims to exclude must be absent
from the output. A small set of patterns that the config does not currently
list is added on top, because they are the ones that actually tend to leak.

Usage:
    check_publish_artifacts.py [--site _site] [--config _config.yml]

Exit codes: 0 clean, 1 violations found, 2 bad invocation / missing site tree.
"""

from __future__ import annotations

import argparse
import fnmatch
import os
import sys

# Patterns that must never be published, even if a future edit drops them from
# `exclude:`. Matched against the path relative to _site, with "/" separators.
EXTRA_FORBIDDEN = [
    "tests",
    "test",
    "__pycache__",
    "*.test.js",
    "*.spec.js",
    "*.bak",
    "*.log",
    "*.tmp",
    "*.orig",
    "*.rej",
    "*.swp",
    "Gemfile",
    "Gemfile.lock",
    "package.json",
    "package-lock.json",
    "*.py",
    "*.ps1",
    "*.sh",
    "*.bat",
    "*.yml",
    "*.yaml",
    "CNAME.lock",
]

# Jekyll never publishes entries beginning with "_" or "." ; these are listed so
# that their *absence* is reported as verified rather than merely assumed.
EXPECTED_ABSENT_DIRS = ["_includes", "_layouts", "_site", ".github", ".jekyll-cache"]


def load_exclude(config_path: str) -> list[str]:
    """Read the exclude list without requiring PyYAML.

    Falls back to a tiny line scanner if PyYAML is unavailable, so the gate
    still runs (and still fails loudly) in a minimal CI image.
    """
    try:
        import yaml  # type: ignore

        with open(config_path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        exclude = data.get("exclude") or []
        return [str(x) for x in exclude]
    except ImportError:
        pass

    entries: list[str] = []
    in_exclude = False
    with open(config_path, encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if not in_exclude:
                if stripped == "exclude:":
                    in_exclude = True
                continue
            if stripped.startswith("- "):
                entries.append(stripped[2:].strip().strip("\"'"))
            else:
                break
    return entries


def build_forbidden(exclude: list[str]) -> list[str]:
    patterns = list(EXTRA_FORBIDDEN)
    for item in exclude:
        item = item.strip().strip("\"'")
        if not item:
            continue
        # Normalise a leading "./" and any trailing slash.
        item = item[2:] if item.startswith("./") else item
        item = item.rstrip("/")
        if item:
            patterns.append(item)
            # A bare directory name should also be rejected at any depth.
            patterns.append("*/" + item)
            patterns.append("*/" + item + "/*")
    return patterns


def is_forbidden(rel_path: str, patterns: list[str]) -> str | None:
    """Return the first pattern that forbids rel_path, else None.

    Matching is case-insensitive on every platform, deliberately. fnmatch's
    default fnmatch() folds case via os.path.normcase, which is a no-op on
    Linux and lowercases on Windows -- so the same gate would be strict on one
    OS and lax on another. fnmatchcase() is explicit and identical everywhere,
    and the extra lowercase comparison makes the intent (conservative) hold
    regardless of how the path happens to be cased.
    """
    lowered = rel_path.lower()
    for pattern in patterns:
        if fnmatch.fnmatchcase(rel_path, pattern) or fnmatch.fnmatchcase(lowered, pattern.lower()):
            return pattern
    return None


def walk_site(site_dir: str):
    for root, dirs, files in os.walk(site_dir):
        dirs.sort()
        files.sort()
        for name in dirs + files:
            full = os.path.join(root, name)
            rel = os.path.relpath(full, site_dir).replace(os.sep, "/")
            yield full, rel, name in dirs


def collect_referenced_assets(site_dir: str) -> set[str]:
    """Absolute-ish paths of assets referenced by any published HTML page."""
    referenced: set[str] = set()
    for root, _dirs, files in os.walk(site_dir):
        for name in files:
            if not name.lower().endswith(".html"):
                continue
            path = os.path.join(root, name)
            try:
                with open(path, encoding="utf-8", errors="replace") as fh:
                    html = fh.read()
            except OSError:
                continue
            for marker in ('src="', 'href="'):
                idx = 0
                while True:
                    idx = html.find(marker, idx)
                    if idx == -1:
                        break
                    start = idx + len(marker)
                    end = html.find('"', start)
                    if end == -1:
                        break
                    referenced.add(html[start:end].split("?")[0].split("#")[0])
                    idx = end
    return referenced


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", default="_site")
    parser.add_argument("--config", default="_config.yml")
    args = parser.parse_args(argv)

    if not os.path.isdir(args.site):
        print(f"::error::{args.site}/ does not exist - did the build run?")
        return 2
    if not os.path.isfile(args.config):
        print(f"::error::{args.config} not found")
        return 2

    exclude = load_exclude(args.config)
    patterns = build_forbidden(exclude)

    violations: list[tuple[str, str]] = []
    published: list[str] = []

    for _full, rel, _is_dir in walk_site(args.site):
        published.append(rel)
        hit = is_forbidden(rel, patterns)
        if hit:
            violations.append((rel, hit))

    # Directories Jekyll hides by default: report, don't fail. If one ever
    # appears, the site's underscore handling changed and the derived
    # forbidden patterns need revisiting.
    leaked_defaults = [d for d in EXPECTED_ABSENT_DIRS if os.path.isdir(os.path.join(args.site, d))]

    if violations:
        print(f"::error::{len(violations)} file(s) in {args.site}/ match an exclude pattern:")
        for rel, pattern in violations[:40]:
            print(f"::error file={args.site}/{rel}::matches excluded pattern '{pattern}'")
        if len(violations) > 40:
            print(f"::error::... and {len(violations) - 40} more")
        return 1

    print(f"OK   no excluded pattern reached {args.site}/ ({len(published)} entries checked)")

    if leaked_defaults:
        print(
            f"::warning::{args.site}/ contains normally-hidden dirs: {', '.join(leaked_defaults)}"
        )

    # Orphan assets: warn only. Some bundles are loaded conditionally, and a
    # hard failure here would be a false positive that blocks deploys.
    referenced = collect_referenced_assets(args.site)
    orphans = []
    for rel in published:
        if not rel.endswith((".js", ".css")):
            continue
        if rel in referenced or ("/" + rel) in referenced:
            continue
        orphans.append(rel)
    if orphans:
        print(f"::warning::{len(orphans)} published asset(s) are not referenced by any page:")
        for rel in orphans[:20]:
            print(f"::warning file={args.site}/{rel}::orphaned asset")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
