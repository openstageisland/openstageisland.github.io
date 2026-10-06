#!/usr/bin/env python3
"""Self-test for check_chrome_contract.py.

The gate now runs in four deploy pipelines, so a bug in the gate is a bug in the
release process: a checker that silently stops detecting things reports green.
Every assertion here pins a defect that this gate actually had, or a false
alarm it actually produced, so the failure modes stay closed.

Kept next to the gate it exercises. Sibling self-tests in this network are not
uniform about the directory: openstageisland.github.io keeps them in
`.github/scripts/`, transhumanists.github.io in `scripts/`. Both work; what matters
is that the self-test is copied alongside the gate it tests, because the gate is
byte-identical across the four repos.

Run:
    python scripts/test_check_chrome_contract.py

Every assertion is verified to bite: sabotaging the gate's token resolution turns
this file red. An assertion that passes for any gate output is worthless, so if
you add a check here, break the gate on purpose and confirm the new assertion
fails before trusting it.

Layout note: the assertions run at import time under a `main()` call, not at module
top level. That is deliberate. This file lives in `scripts/`, and transhumanists
runs `pytest scripts/` over that directory, so pytest imports this module to look
for `test_*` functions -- and a `sys.exit()` at import time raises SystemExit
inside pytest's collector, which kills the whole run with an INTERNALERROR and no
test results at all. The `test_gate_detects_each_defect` wrapper below means
pytest gets a normal pass/fail for this file instead.
"""

from __future__ import print_function

import io
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
GATE = os.path.join(HERE, "check_chrome_contract.py")

failures = []
checks_run = 0
_last_output = ""


def check(name, condition, detail=""):
    """Assert, and on failure quote what the gate actually printed.

    Quoting the output matters: a gate that hangs or dies early looks identical
    to one that simply did not flag the defect, and that is exactly the
    confusion this file exists to prevent.
    """
    global checks_run
    checks_run += 1
    if not condition:
        tail = "\n        | ".join(
            [ln for ln in _last_output.strip().splitlines() if ln.strip()][-12:])
        failures.append((name, detail))
        print("  FAIL  %s%s" % (name, ("  -> %s" % detail) if detail else ""))
        if tail:
            print("        | " + tail)


def write(path, text):
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with io.open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def make_site(root, layout_links=None):
    """A minimal site the gate can run against.

    Deliberately incomplete: these tests assert that specific defects are
    DETECTED, so the fixture does not need to satisfy every rule, only the ones
    each test is about.
    """
    site = os.path.join(root, "fixture-site")
    write(os.path.join(site, "_layouts", "default.html"), layout_links or "")
    write(os.path.join(site, "assets", "css", "main.css"), ":root{--fg:#eee;}\n")
    write(os.path.join(site, "assets", "css", "auth-bar.css"),
          ".ai-dock {\n  display: none;\n}\n"
          ".ai-dock[hidden] {\n  display: none !important;\n}\n"
          ".ai-dock__panel[hidden] {\n  display: none !important;\n}\n")
    write(os.path.join(site, "assets", "js", "network-ux.js"),
          "function labelFor(h){return h;}\n")
    write(os.path.join(site, "_includes", "bottom-bar.html"),
          '<ul class="bottom-bar__list" data-bar-scroller></ul>\n'
          '<button type="button" data-bar-scroll="prev" aria-label="left"></button>\n'
          '<button type="button" data-bar-scroll="next" aria-label="right"></button>\n')
    return site


def run_gate(site):
    global _last_output
    proc = subprocess.Popen(
        [sys.executable, GATE, "--site", site],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    # A timeout, because a gate that cannot terminate is itself a defect and an
    # unbounded wait here would look exactly like a slow test run.
    try:
        raw = proc.communicate(timeout=60)[0]
    except subprocess.TimeoutExpired:
        proc.kill()
        _last_output = "GATE TIMED OUT after 60s"
        return 124, _last_output
    _last_output = raw.decode("utf-8", "replace")
    return proc.returncode, _last_output


def with_site(mutate=None, layout_links=None):
    """Build a fixture, optionally mutate it, run the gate, return (code, output)."""
    tmp = tempfile.mkdtemp(prefix="chrome-contract-")
    try:
        site = make_site(tmp, layout_links)
        if mutate:
            mutate(site)
        return run_gate(site)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def output_has(out, needle):
    return needle in out


def failing(out, needle):
    """True only if a FAIL line mentions `needle`.

    Deliberately not `needle in out`: the gate prints the check name on passing
    lines too, so a substring test passes whether or not the gate flagged the
    defect. The first version of these tests did exactly that and reported two
    green checks that had never fired.
    """
    for line in out.splitlines():
        if "FAIL" in line and needle in line:
            return True
    return False


# ---------------------------------------------------------------------------

def main():
    """Run every assertion and return a process exit code."""
    # Reset first, before any assertion runs. `main()` is called both from the
    # command line and by the pytest wrapper, and can be called twice in one
    # process; without this the second run would inherit the first run's tally and
    # report its own results against the previous run's count.
    del failures[:]
    globals()["checks_run"] = 0
    globals()["_last_output"] = ""

    # 1. A bare var() whose token no linked stylesheet defines must be reported.
    #    This is the transparent-background bug: bottom-bar.css read --color-stage,
    #    which only assets/style.css defines, and three of four layouts never link
    #    that file.
    # ---------------------------------------------------------------------------
    def mut_bare_token(site):
        write(os.path.join(site, "assets", "css", "bottom-bar.css"),
              ".bottom-bar__ai {\n  background: var(--stage-glass);\n}\n")

    code, out = with_site(mut_bare_token,
                          '<link rel="stylesheet" href="{{ \'/assets/css/bottom-bar.css\' | relative_url }}">')
    check("unresolvable token is reported",
          code == 1 and failing(out, "no fallback and not defined by any linked stylesheet"),
          "exit=%d" % code)
    check("unresolvable token names the file and the token",
          failing(out, "bottom-bar.css") and failing(out, "--stage-glass"), "")

    # The same file with a fallback is fine.
    def mut_token_with_fallback(site):
        write(os.path.join(site, "assets", "css", "bottom-bar.css"),
              ".bottom-bar__ai {\n  background: var(--stage-glass, var(--accent, #7c4dff));\n}\n")

    code, out = with_site(mut_token_with_fallback,
                          '<link rel="stylesheet" href="{{ \'/assets/css/bottom-bar.css\' | relative_url }}">')
    check("fallback clears the token finding",
          not failing(out, "--stage-glass"), "")


    # ---------------------------------------------------------------------------
    # 2. A token defined by a stylesheet the page does NOT link is still unresolved.
    #    This distinction is the whole point: the token existed in the repo, which is
    #    why a grep-based review missed it.
    # ---------------------------------------------------------------------------
    def mut_token_in_unlinked(site):
        write(os.path.join(site, "assets", "css", "bottom-bar.css"),
              ".bottom-bar__ai {\n  background: var(--stage-glass);\n}\n")
        write(os.path.join(site, "assets", "style.css"), ":root{--stage-glass:#ff4d8d;}\n")

    code, out = with_site(
        mut_token_in_unlinked,
        '<link rel="stylesheet" href="{{ \'/assets/css/bottom-bar.css\' | relative_url }}">')
    check("token defined only in an unlinked sheet is still reported",
          code == 1 and failing(out, "--stage-glass")
          and failing(out, "no fallback and not defined"), "exit=%d" % code)


    # ---------------------------------------------------------------------------
    # 3. Both Liquid href shapes must be parsed.
    #    The layouts use BOTH `{{ '/x.css' }}` and `{{ "/x.css" }}` -- the second
    #    embeds double quotes inside a double-quoted attribute, and a non-greedy
    #    parser drops that stylesheet, which then makes its tokens look unresolved.
    # ---------------------------------------------------------------------------
    def mut_needs_orbtokens(site):
        write(os.path.join(site, "assets", "css", "orb.css"), ":root{--orb1-x:15%;}\n")
        write(os.path.join(site, "assets", "css", "bottom-bar.css"),
              ".bottom-bar__left {\n  left: var(--orb1-x);\n}\n")

    code, out = with_site(
        mut_needs_orbtokens,
        '<link rel="stylesheet" href="{{ "/assets/css/orb.css" | relative_url }}">')
    check("href with nested double quotes is parsed",
          not failing(out, "--orb1-x"), out.strip().splitlines()[-1:] and "")

    code, out = with_site(
        mut_needs_orbtokens,
        '<link rel="stylesheet" href="{{ \'/assets/css/orb.css\' | relative_url }}">')
    check("href with single quotes is parsed",
          not failing(out, "--orb1-x"), "")

    code, out = with_site(mut_needs_orbtokens, "<!-- no links at all -->")
    check("a layout with no stylesheet links is reported, not silently passed",
          code == 1 and failing(out, "could not find any"), "exit=%d" % code)


    # ---------------------------------------------------------------------------
    # 4. Selector matching must not read the wrong rule.
    #    `.ai-dock` once matched `body.ai-conv-active .ai-dock`, so a correct
    #    `display: none` was reported as `display: flex`.
    # ---------------------------------------------------------------------------
    def mut_dock_compound(site):
        write(os.path.join(site, "assets", "css", "auth-bar.css"),
              ".ai-dock {\n  display: none;\n}\n"
              ".ai-dock[hidden] {\n  display: none !important;\n}\n"
              ".ai-dock__panel[hidden] {\n  display: none !important;\n}\n"
              "body.ai-conv-active .ai-dock {\n  display: flex;\n}\n")

    code, out = with_site(mut_dock_compound)
    check("a descendant .ai-dock rule is not mistaken for the base rule",
          not failing(out, "retired .ai-dock is not display"), "")

    def mut_dock_really_flex(site):
        write(os.path.join(site, "assets", "css", "auth-bar.css"),
              ".ai-dock {\n  display: flex;\n}\n"
              ".ai-dock[hidden] {\n  display: none !important;\n}\n"
              ".ai-dock__panel[hidden] {\n  display: none !important;\n}\n")

    code, out = with_site(mut_dock_really_flex)
    check("a base .ai-dock set to flex IS reported",
          code == 1 and failing(out, "retired .ai-dock is not display"), "exit=%d" % code)


    # ---------------------------------------------------------------------------
    # 5. Prose in a comment must not satisfy or defeat a check.
    #    Several rules carry a comment naming the value they replaced, and an
    #    earlier version matched against the raw file and so failed on the very fix
    #    that had been made.
    # ---------------------------------------------------------------------------
    def mut_comment_mentions_colour(site):
        write(os.path.join(site, "assets", "css", "bottom-bar.css"),
              "/* Was color: #ffffff, a hardcoded white. */\n"
              ".bottom-bar__ai {\n  background: var(--stage-glass, var(--accent, #7c4dff));\n}\n")

    code, out = with_site(mut_comment_mentions_colour,
                          '<link rel="stylesheet" href="{{ \'/assets/css/bottom-bar.css\' | relative_url }}">')
    check("comment prose does not produce a false alarm",
          not failing(out, "no fallback and not defined"), "")


    # ---------------------------------------------------------------------------
    # 6. The chip scroll buttons must be keyboard reachable.
    # ---------------------------------------------------------------------------
    def mut_tabindex(site):
        write(os.path.join(site, "_includes", "bottom-bar.html"),
              '<ul class="bottom-bar__list" data-bar-scroller></ul>\n'
              '<button type="button" data-bar-scroll="prev" tabindex="-1" aria-label="left"></button>\n'
              '<button type="button" data-bar-scroll="next" tabindex="-1" aria-label="right"></button>\n')

    code, out = with_site(mut_tabindex)
    check("tabindex on the chip scroll buttons is reported",
          code == 1 and failing(out, "keyboard reachable"), "exit=%d" % code)

    code, out = with_site()
    check("keyboard-reachable scroll buttons pass that check",
          not failing(out, "keyboard reachable"), "")


    # ---------------------------------------------------------------------------
    # 7. The seal must not be driven off :has(), and must stand down for the
    #    conversation sheet it used to float over.
    # ---------------------------------------------------------------------------
    def mut_seal_has_crossfade(site):
        write(os.path.join(site, "assets", "css", "ai-seal.css"),
              "body:has(.ai-totop.is-visible) .ai-seal {\n  opacity: 0;\n}\n")

    code, out = with_site(mut_seal_has_crossfade)
    check("crossfade driven off :has() is reported",
          code == 1 and failing(out, "does not depend on :has()"), "exit=%d" % code)


    # ---------------------------------------------------------------------------
    # 8. Internal tooling notes must not be shipped as HTML comments.
    # ---------------------------------------------------------------------------
    def mut_html_comment_note(site):
        write(os.path.join(site, "_layouts", "default.html"),
              "<!-- fonts: managed by template-shared/site_forge.py from sites.yaml -->\n")

    code, out = with_site(mut_html_comment_note)
    check("internal tooling note as an HTML comment is reported",
          code == 1 and failing(out, "Liquid comment, not HTML"), "exit=%d" % code)


    # ---------------------------------------------------------------------------
    # 9. The cross-site diff, which is the check that exists because these files have
    #    drifted before. The previous version of this test built two sites and then
    #    invoked `--diff --site <one of them>`, so `check_shared_files()` returned
    #    early on `len(SITES) < 2` and never ran: the assertion passed for free and
    #    EOL normalisation, the drift case the whole function exists to handle, had
    #    no coverage at all.
    #
    #    Exercising it needs a real workspace, because the gate locates sites as
    #    siblings of template-shared/. So the gate is copied into a temp workspace and
    #    two real site names are created beside it.
    # ---------------------------------------------------------------------------
    def workspace_run(site_bodies, argv=None):
        """Run the gate as if from <ws>/template-shared/tests/, over N real sites.

        `site_bodies` maps a site directory name to a callable that writes that
        site's files. Returns (exit code, output).
        """
        tmp = tempfile.mkdtemp(prefix="chrome-contract-ws-")
        try:
            # The gate derives the workspace root from its own path
            # (<ws>/template-shared/tests/), so it has to be *placed* there rather than
            # merely pointed at, or it will look for siblings beside this repo.
            tests_dir = os.path.join(tmp, "template-shared", "tests")
            os.makedirs(tests_dir, exist_ok=True)
            gate = os.path.join(tests_dir, "check_chrome_contract.py")
            shutil.copyfile(GATE, gate)
            for name in site_bodies:
                site_bodies[name](os.path.join(tmp, name))
            proc = subprocess.Popen(
                [sys.executable, gate] + (argv or []),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            out = proc.communicate(timeout=60)[0].decode("utf-8", "replace")
            return proc.returncode, out
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


    SHARED_CSS = ".bottom-bar__ai {\n  background: var(--accent);\n}\n"


    def two_sites(second_body, first_body=None):
        """Two sites sharing every file except bottom-bar.css, which is given
        separately so a test can vary exactly one thing."""
        def build(tmp_site, css_body):
            write(os.path.join(tmp_site, "_layouts", "default.html"), "")
            write(os.path.join(tmp_site, "assets", "js", "network-ux.js"),
                  "function labelFor(h){return h;}\n")
            write(os.path.join(tmp_site, "assets", "css", "network-ux.css"),
                  ".ai-conv__chrome {\n  height: 88vh;\n}\n")
            write(os.path.join(tmp_site, "assets", "css", "ai-seal.css"),
                  ".ai-totop {\n  opacity: 1;\n}\n")
            write(os.path.join(tmp_site, "assets", "js", "bottom-bar.js"),
                  "const x = 1;\n")
            write(os.path.join(tmp_site, "_includes", "bottom-bar.html"),
                  '<ul class="bottom-bar__list" data-bar-scroller></ul>\n')
            write(os.path.join(tmp_site, "assets", "css", "bottom-bar.css"), css_body)

        return {
            "neohiro.github.io": lambda s: build(s, first_body or SHARED_CSS),
            "openstageisland.github.io": lambda s: build(s, second_body),
        }


    # Identical content, different line endings: must NOT read as drift.
    code, out = workspace_run(two_sites(SHARED_CSS.replace("\n", "\r\n")), ["--diff"])
    check("CRLF vs LF is not reported as shared-file drift",
          code == 0 and not failing(out, "shared file identical"),
          "exit=%d" % code)

    # Genuinely different content: must be reported, naming the odd copy out.
    code, out = workspace_run(two_sites(SHARED_CSS + ".extra { color: red; }\n"), ["--diff"])
    check("real content drift across two sites IS reported",
          code == 1 and failing(out, "shared file identical"), "exit=%d" % code)

    # --diff must report only the shared-file checks. It used to parse the flag and
    # then ignore it, running and reporting all 150 per-site checks, so a green
    # --diff proved nothing about drift and looked identical to a plain run.
    code, out = workspace_run(two_sites(SHARED_CSS), ["--diff"])
    check("--diff reports only the shared-file checks",
          "checks passed across 2 sites" in out and not failing(out, "keyboard reachable"),
          out.strip().splitlines()[-1:] and "")
    check("--diff does not run the per-site rules",
          not failing(out, "retired .ai-dock"), "")

    # Single-site --diff has nothing to compare and must not claim the files match.
    single = tempfile.mkdtemp(prefix="chrome-contract-single-")
    try:
        site = make_site(single, "")
        proc = subprocess.Popen([sys.executable, GATE, "--diff", "--site", site],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        out = proc.communicate(timeout=60)[0].decode("utf-8", "replace")
        check("single-site --diff does not claim the shared files match",
              not failing(out, "shared file identical"), "")
    finally:
        shutil.rmtree(single, ignore_errors=True)


    # ---------------------------------------------------------------------------
    # 9b. An undecodable file must be named, not turned into a cascade of
    #     "rule not found" failures on rules that are present and correct.
    # ---------------------------------------------------------------------------
    def undecodable_css(site, rel="assets/css/bottom-bar.css"):
        # `make_site` already built the rest of the fixture around `site`; the
        # caller passes the site path itself, not a temp root to create one in.
        path = os.path.join(site, rel.replace("/", os.sep))
        d = os.path.dirname(path)
        if not os.path.isdir(d):
            os.makedirs(d)
        with open(path, "wb") as fh:
            fh.write(SHARED_CSS.encode("utf-8"))
            fh.write(b"/* latin-1 caf\xe9 */\n")

    tmp = tempfile.mkdtemp(prefix="chrome-contract-enc-")
    try:
        fixture = make_site(tmp, "")
        undecodable_css(fixture)
        code, out = run_gate(fixture)
        check("an undecodable stylesheet does not crash the gate",
              "Traceback" not in out, out.strip().splitlines()[-1] if out.strip() else "")
        check("an undecodable stylesheet is named explicitly",
              code == 1 and failing(out, "decodes as UTF-8"), "exit=%d" % code)

        # Two sites, one unreadable file: the good site must not be blamed.
        def two_sites_one_unreadable():
            # The layout links ai-seal.css on purpose. Token resolution re-reads
            # every linked stylesheet, so this is what makes one bad file be read
            # more than once -- and therefore what makes the report's dedupe
            # observable. With no links in the layout the file is read exactly once
            # and the dedupe assertion below would pass even with dedupe removed.
            link = '<link rel="stylesheet" href="{{ \'/assets/css/ai-seal.css\' | relative_url }}">'

            def build(tmp_site, bad_seal):
                make_site(tmp_site, link)
                for rel, txt in [("assets/js/bottom-bar.js", "const x = 1;\n"),
                                 ("assets/css/network-ux.css",
                                  ".ai-conv__chrome {\n  height: 88vh;\n}\n"),
                                 ("assets/css/ai-seal.css", ".ai-totop {\n  opacity: 1;\n}\n"),
                                 ("assets/css/bottom-bar.css", SHARED_CSS)]:
                    write(os.path.join(tmp_site, rel.replace("/", os.sep)), txt)
                if bad_seal:
                    undecodable_css(tmp_site, rel="assets/css/ai-seal.css")

            return {
                "neohiro.github.io": lambda s: build(s, True),
                "openstageisland.github.io": lambda s: build(s, False),
            }

        code, out = workspace_run(two_sites_one_unreadable())
        # The gate prints a `-- <site> --` header and then that site's results, so
        # a failing line has to be attributed through the header rather than
        # read off the line itself.
        current, blamed = None, []
        for ln in out.splitlines():
            if ln.startswith("-- ") and ln.rstrip().endswith(" --"):
                current = ln.strip()[3:-3].strip()
            elif "decodes as UTF-8" in ln and ln.strip().startswith("FAIL"):
                blamed.append((current, ln.strip()))

        check("an unreadable file is blamed only on the site that has it",
              len(blamed) == 1
              and blamed[0][0] == "neohiro.github.io"
              and "openstageisland" not in blamed[0][1]
              and ".." not in blamed[0][1],
              " | ".join("%s :: %s" % (s, l[:60]) for s, l in blamed) or "none reported")

        # Known gap: the report's dedupe of repeated reads of the same file is not
        # covered here. How many times a file is read depends on which rules
        # reference it and on what the layout links, so a fixture that forces
        # several reads is fragile. Deliberately left as a note rather than an
        # assertion that would pass either way.
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


    # ---------------------------------------------------------------------------
    # 10. Mojibake must be reported, not silently shipped.
    #     This corruption shipped: a mis-set PowerShell encoding rewrote files in
    #     place, so the bottom bar's `title=` read "Talk to the neohiro assistant
    #     â€” questions". Nothing else caught it -- the files still parsed as UTF-8,
    #     three of four copies still hashed equal, and the page still rendered, just
    #     with â€” where an em dash belonged.
    # ---------------------------------------------------------------------------
    def mojibake_em_dash():
        # What an em dash becomes when its UTF-8 bytes are decoded as cp1252.
        return "\u2014".encode("utf-8").decode("cp1252")

    def mut_mojibake(site):
        path = os.path.join(site, "assets", "css", "bottom-bar.css")
        with io.open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write("/* note: em dash %s here */\n" % mojibake_em_dash())

    code, out = with_site(mut_mojibake)
    check("mojibake is reported with its file and line",
          code == 1 and failing(out, "no mojibake in assets/css/bottom-bar.css"),
          "exit=%d" % code)
    check("mojibake report quotes the offending sequence",
          failing(out, mojibake_em_dash()[:3]), "")

    # A genuine non-ASCII character must not be mistaken for corruption. The
    # signature is U+00E2/U+00C3 followed by another cp1252-mapped byte; a correct
    # em dash or ellipsis is not that, and a gate that cried wolf here would be
    # disabled.
    def mut_correct_dashes(site):
        write(os.path.join(site, "assets", "css", "bottom-bar.css"),
              "/* em dash \u2014 ellipsis \u2026 arrow \u2192 accented caf\u00e9 */\n"
              ".bottom-bar__ai {\n  content: \"\u2014\";\n}\n")

    code, out = with_site(mut_correct_dashes)
    check("correct non-ASCII characters are not reported as mojibake",
          not failing(out, "no mojibake in"), "")


    # ---------------------------------------------------------------------------
    # 11. The gate must not crash on a nearly-empty site.
    # ---------------------------------------------------------------------------
    def mut_strip_everything(site):
        shutil.rmtree(os.path.join(site, "_includes"))
        shutil.rmtree(os.path.join(site, "assets"))

    code, out = with_site(mut_strip_everything)
    check("a site missing its assets produces a result, not a traceback",
          "Traceback" not in out, out.strip().splitlines()[-1] if out.strip() else "")


    print("")
    print("Results: %d passed, %d failed" % (checks_run - len(failures), len(failures)))
    if failures:
        print("")
        for name, detail in failures:
            print("  FAILED: %s%s" % (name, (" -> %s" % detail) if detail else ""))
        return 1
    print("  OK: the gate detects each defect it was written for")
    return 0


def test_gate_detects_each_defect():
    """pytest entry point.

    pytest imports this module because the filename matches `test_*`, and a
    module-level sys.exit() raises SystemExit inside the collector, which
    aborts the whole run with an INTERNALERROR and reports nothing at all.
    One wrapper test keeps this file usable by `pytest scripts/`.
    """
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
