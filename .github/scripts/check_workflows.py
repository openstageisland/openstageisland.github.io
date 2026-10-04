#!/usr/bin/env python3
"""Validate every GitHub Actions workflow in .github/workflows/.

Why this exists
---------------
A workflow whose YAML does not parse is not "a failing test" - GitHub cannot
load it at all, so the run is reported as a failure with **zero jobs and no
logs**. That is invisible in review and looks identical to infrastructure
flakiness.

The cause seen twice in this repo was the same: a multi-line script embedded
inline in a `run: |` block. Any line not indented to the block's level ends the
block scalar, and YAML then tries to read the next line as a mapping key:

    ScannerError: while scanning a simple key ... could not find expected ':'

So this checker exists to turn that silent, log-less failure into a loud,
local, zero-dependency one.

What it checks
--------------
1. Every *.yml / *.yaml under .github/workflows/ parses as YAML.
2. The result looks like a workflow (has `jobs` and a name/trigger).
3. No `run: |` block scalar contains a line at column 0, which is the specific
   defect above. YAML may accept it in some positions, so this is asserted
   explicitly rather than left to the parser.
4. Every job-level `uses:` pointing at another repository resolves to a
   workflow that exists and declares `workflow_call`.

Usage
-----
    python3 .github/scripts/check_workflows.py [--dir .github/workflows] [--no-network]

Exit codes: 0 = all good, 1 = at least one problem (all problems are reported).
`--no-network` skips check 4 so the script runs offline in unit tests.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.stderr.write("check-workflows: PyYAML is required (pip install pyyaml)\n")
    raise SystemExit(2)


# A reusable-workflow reference, e.g. neohiro/doctor/.github/workflows/x.yml@main
REUSABLE_RE = re.compile(
    r"^(?P<owner>[^/\s]+)/(?P<repo>[^/\s]+)/\.github/workflows/(?P<file>[^\s@]+)(?:@(?P<ref>[^\s]+))?$"
)

# A step-level action reference, e.g. actions/checkout@v4  (these are never checked)
ACTION_RE = re.compile(r"^[\w.-]+/[\w.-]+(/[^@\s]+)?@[\w.\-]+$")


class Problem:
    def __init__(self, path: str, message: str) -> None:
        self.path = path
        self.message = message

    def __str__(self) -> str:
        return f"{self.path}: {self.message}"


def list_workflows(directory: str) -> list[str]:
    if not os.path.isdir(directory):
        return []
    out = []
    for name in sorted(os.listdir(directory)):
        if name.endswith((".yml", ".yaml")):
            out.append(os.path.join(directory, name))
    return out


# Methods called on an expression operand, e.g. inputs.repo.replace('/', '_').
# GitHub Actions expressions support property access (github.sha), indexing
# (inputs.list[0]) and built-in functions (format(), contains(), hashFiles()),
# but NOT method calls on values. `inputs.x.replace(...)` is rejected when the
# workflow is parsed, which makes the workflow unloadable - reported as a failed
# run with zero jobs and no logs. The leading dot is what distinguishes a method
# call from a built-in function call, which never has one.
METHOD_CALL_RE = re.compile(r"\.\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(")

# Known methods, named so the error can say what to use instead. Anything else
# matching METHOD_CALL_RE is still an error, it just gets a generic message.
KNOWN_METHODS = {
    "replace": "use format() and do the substitution in a shell or script step",
    "split": "no split() in expressions; do the split in a run step",
    "join": "use join(array, ',') - the built-in, without a dot",
    "trim": "no trim() in expressions",
    "toLower": "no toLower() in expressions; use a shell step",
    "toUpper": "no toUpper() in expressions; use a shell step",
    "contains": "contains() is a built-in - call it without a dot",
    "startsWith": "startsWith() is a built-in - call it without a dot",
    "endsWith": "endsWith() is a built-in - call it without a dot",
    "length": "no .length; use a shell step",
}


def check_expressions(path: str, text: str) -> list[Problem]:
    """Reject method calls inside ${{ }} expression spans."""
    problems: list[Problem] = []
    lines = text.split("\n")

    for i, line in enumerate(lines):
        # Only consider the inside of an expression span, so a dot-paren in
        # ordinary YAML (a run: command, a URL) is not a false positive.
        for span in re.finditer(r"\$\{\{(.*?)\}\}", line):
            body = span.group(1)
            for m in METHOD_CALL_RE.finditer(body):
                name = m.group(1)
                advice = KNOWN_METHODS.get(
                    name,
                    f"GitHub expressions have no methods; '{name}' is not callable on a value",
                )
                problems.append(
                    Problem(
                        path,
                        f"line {i + 1}: method call '.{name}(' inside a ${{{{ }}}} expression "
                        f"is rejected by GitHub and makes this workflow unloadable "
                        f"({advice}): {line.strip()[:80]}",
                    )
                )
    return problems


def check_column_zero_in_block_scalars(path: str, text: str) -> list[Problem]:
    """Flag lines at column 0 that sit inside a `run: |` block.

    A block scalar's content must be indented further than its parent key. A
    column-0 line ends the scalar, which is the exact defect that broke
    ci.yml and heartbeat.yml. Reported separately from the parse error because
    PyYAML's failure position points at the *next* line, not the culprit.
    """
    problems: list[Problem] = []
    lines = text.split("\n")
    in_block = False
    block_indent = 0

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not in_block:
            # Start of a block scalar: `key: |` / `key: >` (optionally chomped).
            if re.search(r":\s*[|>][-+]?\s*$", line):
                in_block = True
                block_indent = len(line) - len(line.lstrip())
            continue

        if stripped == "":
            continue
        indent = len(line) - len(line.lstrip())
        if indent <= block_indent:
            # Scalar ended. If this line is not a new YAML construct it means the
            # scalar was terminated by unindented content - the bug we hunt.
            in_block = False
            if indent == 0 and not re.match(r"^[^\s:]+:", line):
                problems.append(
                    Problem(
                        path,
                        f"line {i + 1}: unindented line inside a `run: |` block "
                        f"terminates the block scalar and breaks YAML parsing: {stripped[:60]!r}",
                    )
                )
    return problems


def gh_api(path: str) -> tuple[int, str]:
    """Return (returncode, stdout) for a `gh api` call."""
    try:
        proc = subprocess.run(
            ["gh", "api", path],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, str(exc)
    return proc.returncode, proc.stdout


def reusable_workflow_declares_workflow_call(
    owner: str, repo: str, path: str, ref: str
) -> tuple[bool, str]:
    """Check that owner/repo/path@ref exists, is usable, and has `workflow_call`.

    Three failure modes, all of which make the *calling* workflow fail to load
    with zero jobs and no logs:

    1. the file cannot be read (typo, wrong ref, no access)
    2. the file exists but does not declare `on: workflow_call`
    3. the repository is archived - workflows in an archived repo are disabled,
       so the reusable workflow can never run. This is the subtle one: the file
       is present and correct, so only checking (1) and (2) passes.
    """
    code, out = gh_api(f"repos/{owner}/{repo}")
    if code != 0:
        return False, f"cannot read repo {owner}/{repo}"
    try:
        meta = json.loads(out)
    except Exception as exc:
        return False, f"{owner}/{repo} metadata unreadable: {exc}"
    if meta.get("archived"):
        return False, (
            f"{owner}/{repo} is ARCHIVED - workflows in an archived repo are disabled, "
            f"so {path}@{ref} can never run. Un-archive it or point at a live copy."
        )

    code, out = gh_api(f"repos/{owner}/{repo}/contents/{path}?ref={ref}")
    if code != 0:
        return False, f"cannot read {owner}/{repo}/{path}@{ref}"

    try:
        content = base64.b64decode(json.loads(out)["content"]).decode("utf-8")
        doc = yaml.safe_load(content)
    except Exception as exc:
        return False, f"{owner}/{repo}/{path}@{ref} unreadable: {exc}"

    if not isinstance(doc, dict):
        return False, f"{owner}/{repo}/{path}@{ref} is not a mapping"

    # PyYAML resolves the `on:` key to boolean True (YAML 1.1).
    triggers = doc.get("on", doc.get(True))
    if isinstance(triggers, str):
        names = {triggers}
    elif isinstance(triggers, dict) or isinstance(triggers, list):
        names = set(triggers)
    else:
        names = set()

    if "workflow_call" not in names:
        return False, f"{owner}/{repo}/{path}@{ref} does not declare `on: workflow_call`"
    return True, ""


def check_workflows(directory: str, network: bool = True) -> list[Problem]:
    problems: list[Problem] = []
    paths = list_workflows(directory)

    if not paths:
        return [Problem(directory, "no workflow files found")]

    for path in paths:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()

        problems.extend(check_expressions(path, text))
        problems.extend(check_column_zero_in_block_scalars(path, text))

        try:
            doc = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            mark = getattr(exc, "problem_mark", None)
            where = f" at line {mark.line + 1}, column {mark.column + 1}" if mark else ""
            problems.append(Problem(path, f"invalid YAML{where}: {getattr(exc, 'problem', exc)}"))
            continue

        if not isinstance(doc, dict):
            problems.append(Problem(path, "top level is not a mapping"))
            continue
        if "jobs" not in doc:
            problems.append(Problem(path, "no `jobs` key - not a workflow"))
            continue
        if not isinstance(doc.get("jobs"), dict) or not doc["jobs"]:
            problems.append(Problem(path, "`jobs` is empty"))
            continue

        for job_name, job in doc["jobs"].items():
            if not isinstance(job, dict):
                continue
            uses = job.get("uses")
            if not isinstance(uses, str):
                continue
            if ".github/workflows/" in uses:
                pass  # A reusable workflow, never a plain action.
            elif ACTION_RE.match(uses):
                continue
            m = REUSABLE_RE.match(uses)
            if not m:
                problems.append(
                    Problem(path, f"job `{job_name}` has an unrecognised `uses: {uses}`")
                )
                continue
            if not network:
                continue
            ok, why = reusable_workflow_declares_workflow_call(
                m.group("owner"), m.group("repo"), m.group("file"), m.group("ref") or "main"
            )
            if not ok:
                problems.append(Problem(path, f"job `{job_name}` calls {uses} but {why}"))

    return problems


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--dir", default=".github/workflows", help="workflow directory")
    ap.add_argument("--no-network", action="store_true", help="skip reusable-workflow resolution")
    args = ap.parse_args(argv)

    problems = check_workflows(args.dir, network=not args.no_network)

    if not problems:
        count = len(list_workflows(args.dir))
        print(f"check-workflows: {count} workflow(s) OK")
        return 0

    print(f"check-workflows: {len(problems)} problem(s) found", file=sys.stderr)
    for problem in problems:
        print(f"::error file={problem.path}::{problem.message}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
