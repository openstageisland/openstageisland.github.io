#!/usr/bin/env python3
"""Validate _config.yml for the keys the site build depends on.

Lives in a file rather than inline in ci.yml for the same reason as
scripts/check-workflows.py: a multi-line `python3 -c "..."` inside a `run: |`
block puts Python source at column 0, which terminates the YAML block scalar
and makes ci.yml itself unparseable. That happened here - the workflow failed
to load at all, with zero jobs and no logs.

Emits GitHub Actions `::error::` annotations so a failure is visible in the
Checks UI.

Usage: python3 scripts/check-config.py [path]
"""

from __future__ import annotations

import sys

try:
    import yaml
except ImportError:
    sys.stderr.write("check-config: PyYAML is required (pip install pyyaml)\n")
    raise SystemExit(2)

REQUIRED_KEYS = ("url", "github_username")


def main(argv: list) -> int:
    path = argv[0] if argv else "_config.yml"

    try:
        with open(path, encoding="utf-8") as fh:
            config = yaml.safe_load(fh)
    except FileNotFoundError:
        print(f"::error file={path}::file not found")
        return 1
    except yaml.YAMLError as exc:
        print(f"::error file={path}::YAML parse error: {exc}")
        return 1

    if not isinstance(config, dict):
        print(f"::error file={path}::top level is not a mapping")
        return 1

    missing = [key for key in REQUIRED_KEYS if key not in config]
    if missing:
        for key in missing:
            print(f"::error file={path}::missing required key: {key}")
        return 1

    for key in REQUIRED_KEYS:
        print(f"{key}: {config[key]}")
    print(f"valid {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))