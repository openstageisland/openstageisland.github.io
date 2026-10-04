#!/usr/bin/env python3
"""Validate _config.yml for the keys the site and its tooling depend on.

Extracted from an inline `python3 -c "..."` block in ci.yml. That form was the
reason ci.yml did not parse as YAML: the embedded Python sat at column 0 inside
a `run: |` block scalar, which terminates the block and makes YAML re-parse
those lines as mapping keys. Keeping logic in a real file also makes it
importable and testable.

Usage:
    check_config.py [--config _config.yml]

Exit codes: 0 valid, 1 validation failure, 2 file missing.
"""

from __future__ import annotations

import argparse
import os
import sys

REQUIRED_KEYS = ("url", "github_username")

# The layout renders {% seo %}, which raises a Liquid syntax error unless the
# providing gem is registered. Checking it here means a dropped `plugins:` entry
# fails the build with a clear message instead of an opaque Liquid error.
REQUIRED_PLUGINS = ("jekyll-seo-tag",)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="_config.yml")
    args = parser.parse_args(argv)

    if not os.path.isfile(args.config):
        print(f"::error::{args.config} not found")
        return 2

    try:
        import yaml  # type: ignore
    except ImportError:
        print("::error::PyYAML is required to validate _config.yml")
        return 2

    try:
        with open(args.config, encoding="utf-8") as fh:
            config = yaml.safe_load(fh) or {}
    except yaml.YAMLError as exc:
        print(f"::error::YAML parse error: {exc}")
        return 1

    if not isinstance(config, dict):
        print("::error::_config.yml did not parse to a mapping")
        return 1

    failures = 0
    for key in REQUIRED_KEYS:
        if key not in config:
            print(f"::error::Missing required key: {key}")
            failures += 1
        else:
            print(f"OK   {key}: {config[key]!r}")

    plugins = config.get("plugins") or []
    if isinstance(plugins, str):
        plugins = [plugins]
    for plugin in REQUIRED_PLUGINS:
        if plugin not in plugins:
            print(
                f"::error::plugins is missing '{plugin}'. _layouts/default.html uses "
                f"{{% {plugin.replace('jekyll-', '').replace('-tag', '')} %}}, which is an "
                f"unknown Liquid tag without it and fails the build."
            )
            failures += 1
        else:
            print(f"OK   plugin registered: {plugin}")

    # A typo in `exclude` silently publishes whatever it should have hidden.
    exclude = config.get("exclude") or []
    if "tests" not in exclude:
        print("::error::exclude is missing 'tests'; test sources would be published")
        failures += 1
    else:
        print("OK   exclude covers 'tests'")

    if failures:
        print(f"::error::{failures} config problem(s)")
        return 1

    print("OK   _config.yml is valid")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
