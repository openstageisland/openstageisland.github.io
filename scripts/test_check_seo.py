#!/usr/bin/env python3
"""test_check_seo.py -- prove check_seo.py can still fail.

A gate that cannot fail is worse than no gate, because it converts "I did not
check" into "I checked and it was fine". This file exists because check_seo.py
had two silent-failure bugs during the build that introduced it, and neither
would have shown up as a red build:

  1. `script` was in the parser's skip-set, so the JSON-LD branch was
     unreachable. The gate reported "no structured data on any page" on a site
     that was full of it -- and, having already been ignored once, would have
     been ignored for ever after.

  2. The cross-page accumulator was the same dict as the per-page one, so every
     collected value was written into a throwaway object. The
     duplicate-description rule compared an always-empty mapping against itself
     and reported clean on the exact defect it was written to catch: eighteen
     tool pages sharing one description.

Both are the same shape of failure -- a check that is silently inert. So each
test here feeds the real functions a page containing the defect and asserts the
gate notices. If a future edit makes a rule inert again, this file fails loudly
and names which one.

    python scripts/test_check_seo.py

Exit code 0 = the gate still detects every defect it claims to detect.
"""

from __future__ import print_function

import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SITE_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)

import check_seo  # noqa: E402

ORIGIN = "https://example.github.io"

FAILURES = []
PASSED = [0]


def expect(name, condition, detail=""):
    if condition:
        PASSED[0] += 1
    else:
        FAILURES.append("%s%s" % (name, ("  -- " + detail) if detail else ""))


# --------------------------------------------------------------------------
# page fixtures. Each is a minimal but COMPLETE head, so a rule under test is
# never failing for an unrelated reason.
# --------------------------------------------------------------------------

GOOD_LD = (
    '<script type="application/ld+json">'
    '{"@context":"https://schema.org","@graph":['
    '{"@id":"https://example.github.io/#organization","@type":"Organization",'
    '"name":"Example"},'
    '{"@id":"https://example.github.io/#website","@type":"WebSite","name":"Example"},'
    '{"@id":"https://example.github.io/#tools","@type":"ItemList"},'
    '{"@id":"https://example.github.io/tools/x/#tool","@type":"SoftwareApplication"}'
    ']}</script>'
)

GOOD_PAGE_LD = (
    '<script type="application/ld+json">'
    '[{"@type":"WebPage","@id":"https://example.github.io/#webpage"}]'
    "</script>"
)


def page(title="Example tool", desc=None, canonical=None, og_image=True,
         twitter_card="summary_large_image", ld=True, robots=None,
         desc_count=1, title_count=1, canonical_count=1, og_count=1):
    """Build a page, with knobs for injecting each defect the gate hunts."""
    desc = desc if desc is not None else ("A distinct description that is long "
                                         "enough to pass the minimum length rule "
                                         "without being cut off in a SERP.")
    canonical = canonical if canonical is not None else ORIGIN + "/tools/x/"
    out = ['<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">']
    for _ in range(title_count):
        out.append("<title>%s</title>" % title)
    for _ in range(desc_count):
        out.append('<meta name="description" content="%s">' % desc)
    if robots:
        out.append('<meta name="robots" content="%s">' % robots)
    for _ in range(canonical_count):
        out.append('<link rel="canonical" href="%s">' % canonical)
    for _ in range(og_count):
        out.append('<meta property="og:title" content="%s">' % title)
        out.append('<meta property="og:description" content="%s">' % desc)
        out.append('<meta property="og:url" content="%s">' % canonical)
        out.append('<meta property="og:type" content="website">')
        out.append('<meta property="og:site_name" content="Example">')
        if og_image:
            out.append('<meta property="og:image" content="%s/assets/og/x.png">' % ORIGIN)
            out.append('<meta property="og:image:width" content="1200">')
            out.append('<meta property="og:image:height" content="630">')
            out.append('<meta property="og:image:alt" content="card">')
        out.append('<meta name="twitter:card" content="%s">' % twitter_card)
        out.append('<meta name="twitter:title" content="%s">' % title)
        out.append('<meta name="twitter:description" content="%s">' % desc)
        if og_image:
            out.append('<meta name="twitter:image" content="%s/assets/og/x.png">' % ORIGIN)
            out.append('<meta name="twitter:image:alt" content="card">')
    if ld:
        out.append(GOOD_LD)
        out.append(GOOD_PAGE_LD)
    out.append("</head><body><h1>%s</h1></body></html>" % title)
    return "".join(out)


def run(html, exp=None):
    """Run check_page over a page and return the failed check names."""
    check_seo.RESULTS = []
    exp = exp if exp is not None else {"rel": "p.html"}
    shared = {"descriptions": {}, "site_types": set(), "page_types": set(),
              "noindex": []}
    check_seo.check_page("p.html", html, ORIGIN, "Example", exp, shared)
    return set(n for n, ok, _ in check_seo.RESULTS if not ok), shared


# --------------------------------------------------------------------------
# 1. the baseline must be clean, or every negative test below is meaningless
# --------------------------------------------------------------------------

fails, shared = run(page())
expect("baseline page passes every per-page rule", not fails,
       "clean fixture failed: %s" % sorted(fails))
expect("baseline accumulates descriptions", len(shared["descriptions"]) == 1,
       "got %r" % shared["descriptions"])
expect("baseline accumulates site types",
       "Organization" in shared["site_types"], repr(shared["site_types"]))
expect("baseline accumulates page types", "WebPage" in shared["page_types"],
       repr(shared["page_types"]))

# --------------------------------------------------------------------------
# 2. duplicate title / description -- the defects that shipped
# --------------------------------------------------------------------------

fails, _ = run(page(title_count=2))
expect("two <title> elements are caught", any("exactly one <title>" in f for f in fails),
       "the original defect (a hand-written title plus {% seo %}) was missed")

fails, _ = run(page(desc_count=2))
expect("two meta descriptions are caught",
       any("exactly one meta description" in f for f in fails))

fails, _ = run(page(desc="too short"))
expect("a placeholder-length description is caught",
       any("description length" in f for f in fails))

# --------------------------------------------------------------------------
# 3. canonical
# --------------------------------------------------------------------------

fails, _ = run(page(canonical_count=0))
expect("a missing canonical is caught",
       any("exactly one canonical" in f for f in fails))

fails, _ = run(page(canonical="https://elsewhere.example/tools/x/"))
expect("an off-host canonical is caught",
       any("canonical is on" in f for f in fails),
       "this is the silent de-index bug; the gate must not miss it")

fails, _ = run(page(canonical="/tools/x/"))
expect("a relative canonical is caught", any("canonical is absolute" in f for f in fails))

# --------------------------------------------------------------------------
# 4. the social card
# --------------------------------------------------------------------------

fails, _ = run(page(og_image=False))
expect("a missing og:image is caught", any("exactly one og:image" in f for f in fails))
expect("a missing og:image:width is caught",
       any("og:image:width" in f for f in fails))
expect("a missing twitter:image is caught", any("twitter:image present" in f for f in fails))

fails, _ = run(page(twitter_card="summary"))
expect("twitter:card=summary is caught",
       any("summary_large_image" in f for f in fails))

fails, _ = run(page(og_count=0))
expect("missing Open Graph tags are caught",
       any("exactly one og:title" in f for f in fails))

# --------------------------------------------------------------------------
# 5. JSON-LD -- the parser bug this file exists to prevent a repeat of
# --------------------------------------------------------------------------

fails, shared = run(page(ld=True))
expect("a well-formed JSON-LD block is parsed",
       not any("parses" in f for f in fails),
       "parser cannot read its own output: %s" % sorted(fails))

fails, _ = run(page(ld=False))
expect("a page with no JSON-LD is caught", any("has a JSON-LD block" in f for f in fails))

# Invalid JSON must be reported as invalid, not silently accepted. A gate that
# lets malformed structured data through is worse than one that ignores it,
# because the data looks present.
broken = page().replace(GOOD_LD, '<script type="application/ld+json">{not json}</script>')
fails, _ = run(broken)
expect("malformed JSON-LD is reported", any("parses" in f for f in fails))

# A JSON-LD block that appears inside a comment or a script body must NOT be
# counted. This is the whole reason the collector is a parser and not a regex.
commented = page(ld=False).replace(
    "<head>", "<head><!-- <script type=\"application/ld+json\">"
              "{\"@type\":\"Organization\"}</script> -->")
fails, _ = run(commented)
expect("JSON-LD inside an HTML comment is not counted",
       any("has a JSON-LD block" in f for f in fails))

# --------------------------------------------------------------------------
# 6. the cross-page accumulator -- the second silent-failure bug
# --------------------------------------------------------------------------

# Two pages with the same description must be detectable ACROSS calls. If the
# accumulator is per-page again, both calls individually look fine and the
# duplicate is invisible, which is exactly how it got shipped.
shared = {"descriptions": {}, "site_types": set(), "page_types": set(),
          "noindex": []}
dup_desc = "An identical description reused on two different pages, long enough to clear the floor."
for rel in ("a.html", "b.html"):
    check_seo.RESULTS = []
    check_seo.check_page(rel, page(desc=dup_desc), ORIGIN, "Example",
                         {"rel": rel}, shared)
expect("a repeated description lands in the shared accumulator",
       len(shared["descriptions"]) == 2,
       "the accumulator is per-page again; the uniqueness rule cannot work")

if len(shared["descriptions"]) == 2:
    values = list(shared["descriptions"].values())
    dupes = {}
    for rel, d in shared["descriptions"].items():
        dupes.setdefault(d, []).append(rel)
    expect("the duplicate is detectable across pages",
           any(len(v) > 1 for v in dupes.values()),
           "unexpected: %r" % dupes)

# A noindex page must be excludable, since a rename stub and an alias are
# SUPPOSED to share copy.
shared_ni = {"descriptions": {}, "site_types": set(), "page_types": set(),
             "noindex": []}
for rel, robots in (("a.html", "noindex, follow"), ("b.html", None)):
    check_seo.RESULTS = []
    check_seo.check_page(rel, page(desc=dup_desc, robots=robots), ORIGIN,
                         "Example", {"rel": rel}, shared_ni)
expect("a noindex page is recorded as noindex",
       shared_ni["noindex"] == ["a.html"], repr(shared_ni["noindex"]))

# --------------------------------------------------------------------------
# 7. the comment-stripping helper -- a checker must not flag its own docs
# --------------------------------------------------------------------------

doc = ('{% comment %}'
       '  The <title> that used to be here was removed, and {% seo %} went with it.'
       '{% endcomment %}'
       '<link rel="stylesheet" href="/a.css">')
stripped = check_seo.strip_comments(doc)
expect("strip_comments removes a Liquid comment body",
       "<title>" not in stripped and "{% seo %}" not in stripped,
       repr(stripped))
expect("strip_comments leaves real markup alone",
       '/a.css' in stripped)
expect("strip_comments removes HTML comments",
       "<title>" not in check_seo.strip_comments("<!-- <title>x</title> -->keep"))

# --------------------------------------------------------------------------
# 8. url_slug must match Jekyll's own slugify
# --------------------------------------------------------------------------

import build_seo  # noqa: E402

for raw, want in (
    ("BlackGlass", "blackglass"),
    ("HoneyScan", "honeyscan"),
    ("cripple-netstrip", "cripple-netstrip"),
    ("lanscan", "lanscan"),
    ("auto-resume", "auto-resume"),
    ("mesh-vanity-key", "mesh-vanity-key"),
    ("TristarMania", "tristarmania"),
    ("Some Name Here", "some-name-here"),
    ("a  b", "a-b"),
):
    got = build_seo.url_slug(raw)
    expect("url_slug(%r) == %r" % (raw, want), got == want, "got %r" % got)

# --------------------------------------------------------------------------
# 9. build_seo must refuse to emit a cluster with no page
# --------------------------------------------------------------------------

cfg = {
    "origin": ORIGIN, "brand": "Example",
    "organization": {"type": "Organization", "description": "d"},
    "social": {"same_as": []},
    "og": {"image": "/assets/og/example.png", "width": 1200, "height": 630},
    "topics": [{"id": "live-with-no-page", "claim": "live", "label": "L",
                "summary": "s", "keywords": []}],
    "tools": {},
}
problems = build_seo.validate(cfg, [])
expect("a claim:live topic with no page is rejected",
       any("no page" in p for p in problems), repr(problems))

cfg["topics"] = [{"id": "roadmap", "claim": "roadmap", "label": "R",
                  "summary": "s", "keywords": []}]
# Assert on the specific rule, not on "no problems at all": the fixture's
# og.image deliberately points at a file this test does not create, so the
# unrelated reference check is expected to fire and must not mask this one.
expect("a claim:roadmap topic with no page is allowed",
       not any("no page" in p for p in build_seo.validate(cfg, [])),
       repr(build_seo.validate(cfg, [])))

# --------------------------------------------------------------------------
# 10. description builder: unique, terminated, acronym-safe
# --------------------------------------------------------------------------

d1 = build_seo.tool_description(
    {"tagline": "A tool for scanning networks", "platform": "Linux",
     "language": "Python", "category": "Net", "keywords": ["lan scanner"]}, {})
d2 = build_seo.tool_description(
    {"tagline": "A different tool entirely", "platform": "Windows",
     "language": "Go", "category": "Net", "keywords": ["lan scanner"]}, {})
expect("descriptions for different tools differ", d1 != d2)
expect("a description ends with a full stop", d1.endswith("."), repr(d1))
# "lan scanner" is an acronym case, not a casing bug: the table maps it to LAN.
# The real defect this guards is a keyword that is neither an acronym nor
# capitalised -- "search. second life chat." -- which reads as a bug in the SERP.
expect("an acronym keyword is upper-cased, not title-cased",
       "LAN scanner." in d1, repr(d1))
expect("a plain leading keyword is capitalised",
       build_seo._sentence("blocked ads at dns level", capitalize=True)
       == "Blocked ads at DNS level.",
       build_seo._sentence("blocked ads at dns level", capitalize=True))
expect("an acronym keyword keeps its case",
       build_seo._sentence("rss reader", capitalize=True) == "RSS reader.",
       build_seo._sentence("rss reader", capitalize=True))
expect("a word that merely contains an acronym is not rewritten",
       build_seo._titlecase_fragment("android tools") == "Android tools",
       build_seo._titlecase_fragment("android tools"))

# --------------------------------------------------------------------------

print("")
for f in FAILURES:
    print("  FAIL  %s" % f)
print("")
if FAILURES:
    print("FAILED: %d of %d assertions" % (len(FAILURES),
                                           len(FAILURES) + PASSED[0]))
    print("")
    print("A failing assertion means check_seo.py has stopped detecting a defect")
    print("it claims to detect. The gate is inert until this passes.")
    sys.exit(1)

print("OK: %d assertions -- check_seo.py still detects every defect it targets"
      % PASSED[0])
sys.exit(0)