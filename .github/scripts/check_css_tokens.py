#!/usr/bin/env python3
"""Fail if the shared network widgets read a design token this site never defines.

Why this exists
---------------
`assets/css/network-ux.css` and `assets/css/auth-bar.css` are synced to all four
`*.github.io` sites from `template-shared/` and read one neutral vocabulary
(`--bg`, `--fg`, `--border`, `--accent`, ...). Each site defines its own tokens
(`--color-*` here). Every shared read carries a hard-coded fallback, so a missing
token is silent: the widget renders in the fallback palette rather than the
site's. That is exactly what happened here -- the assistant dock, the screenwide
conversation sheet and the network widgets rendered dark-on-light while the page
was light, and nothing failed.

`assets/css/site-chrome.css` bridges the two vocabularies with aliases. This gate
is what keeps the bridge honest: a `template-shared` sync that starts reading a
new token, or a site rename, fails the build instead of quietly reverting to a
fallback.

Tokens that are legitimately constant across the network (status colours, spacing
steppers) are allowed to remain unresolved, because a fixed value is the correct
behaviour for them. Everything theme-sensitive must resolve.

Usage:
    check_css_tokens.py [--site .] [--config _config.yml]

Exit codes: 0 clean, 1 unresolved theme tokens, 2 bad invocation.
"""

from __future__ import annotations

import argparse
import os
import re
import sys

DECL = re.compile(r"(--[A-Za-z0-9_-]+)\s*:")
USE = re.compile(r"var\(\s*(--[A-Za-z0-9_-]+)")

# Stylesheets synced across the network. These read the neutral vocabulary.
SHARED_STYLESHEETS = ("assets/css/network-ux.css", "assets/css/auth-bar.css")

# Local stylesheets that define this site's palette.
SITE_STYLESHEETS = ("assets/style.css", "assets/css/site-chrome.css")

# Tokens whose value is intentionally the same on every site, so a fallback is
# the correct behaviour rather than a theme mismatch.
ALLOWED_UNRESOLVED = {
    # status / semantic colours, fixed per meaning across the network
    "--green", "--amber", "--red", "--cyan", "--purple", "--blue", "--pink",
    # spacing and sizing steppers local to a component
    "--mx", "--my", "--sx", "--sy", "--ai-bar-pad", "--dock-h",
}


def read(path: str) -> str:
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def collect(paths, pattern, root):
    found = {}
    for rel in paths:
        path = os.path.join(root, *rel.split("/"))
        if not os.path.isfile(path):
            continue
        for match in pattern.finditer(read(path)):
            found.setdefault(match.group(1), set()).add(rel)
    return found


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", default=".")
    args = parser.parse_args(argv)

    if not os.path.isdir(args.site):
        print(f"::error::{args.site} is not a directory")
        return 2

    declared = set(collect(SITE_STYLESHEETS, DECL, args.site))
    declared |= set(collect(SHARED_STYLESHEETS, DECL, args.site))
    used = collect(SHARED_STYLESHEETS, USE, args.site)

    unresolved = sorted(
        t for t in used
        if t not in declared and t not in ALLOWED_UNRESOLVED
    )

    if unresolved:
        print(
            f"::error::{len(unresolved)} theme token(s) read by the shared "
            f"network CSS are defined nowhere; each falls back to a hard-coded "
            f"value and will render in the wrong palette:"
        )
        for token in unresolved:
            where = ", ".join(sorted(x.split("/")[-1] for x in used[token]))
            print(f"::error::  {token}  (read by {where})")
        print(
            "::error::define an alias in assets/css/site-chrome.css :root, "
            "mapping the shared vocabulary onto this site's --color-* tokens"
        )
        return 1

    print(
        f"OK   every theme-sensitive token read by the shared network CSS "
        f"resolves ({len(used)} tokens checked, "
        f"{len(ALLOWED_UNRESOLVED & set(used))} intentionally constant)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
