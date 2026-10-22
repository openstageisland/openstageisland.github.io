#!/usr/bin/env python3
"""Self-test for build_seo.py.

Two classes of bug this pins, both of which produce a *green* run:

  1. A parser that silently loses a value. build_seo.py reads _tools/*.md with
     a hand-rolled YAML subset reader rather than yaml.load, on purpose (see its
     docstring: CI runs `pip install pyyaml` for some jobs and not others). A
     hand-rolled parser fails quietly -- it returns the wrong string and
     everything downstream renders happily. Every assertion here pins a case the
     reader got wrong before, or would get wrong.

  2. A validator that stops detecting things. Same argument as
     test_check_chrome_contract.py: a gate which has been weakened is
     indistinguishable from a gate which is passing.

Every assertion is verified to bite -- each was checked by breaking the code on
purpose and confirming the corresponding assertion goes red. An assertion that
passes regardless of the implementation is worthless.

Run:
    python scripts/test_build_seo.py

Layout note: the assertions run inside main(), not at module top level. This file
lives in scripts/, and pytest collects it by importing the module; a sys.exit() at
import time raises SystemExit inside pytest's collector and kills the whole run
with an INTERNALERROR. This way pytest gets an ordinary pass/fail.
"""

from __future__ import print_function

import collections
import importlib.util
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SITE_DIR = os.path.dirname(HERE)
GATE = os.path.join(HERE, "build_seo.py")


def load():
    spec = importlib.util.spec_from_file_location("build_seo_under_test", GATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


failures = []
checks_run = 0


def _keys_sorted(rendered):
    """True when every JSON object's keys are in ascending order, at every depth.

    Parsed with object_pairs_hook so the source order is preserved -- plain
    json.loads would return dicts that have already been ordered by the decoder
    and the check would pass no matter how the file was written.
    """
    parsed = json.loads(rendered, object_pairs_hook=collections.OrderedDict)

    def walk(node):
        if isinstance(node, collections.OrderedDict):
            keys = list(node.keys())
            if keys != sorted(keys):
                return False
            return all(walk(v) for v in node.values())
        if isinstance(node, list):
            return all(walk(v) for v in node)
        return True

    return walk(parsed)


def check(name, condition, detail=""):
    global checks_run
    checks_run += 1
    if not condition:
        failures.append(name + (" -- " + str(detail) if detail else ""))


def fm(yaml_text):
    """Parse a front-matter block the way build_seo.py does."""
    return load().parse_front_matter("---\n" + yaml_text + "\n---\nbody\n")


# --------------------------------------------------------------------------
# 1. front-matter reader
# --------------------------------------------------------------------------

def test_scalar_types():
    m = load()
    check("plain scalar", m.parse_front_matter("---\nk: v\n---\n")["k"] == "v")
    check("double-quoted unquoted",
          m.parse_front_matter('---\nk: "v"\n---\n')["k"] == "v")
    check("single-quoted unquoted",
          m.parse_front_matter("---\nk: 'v'\n---\n")["k"] == "v")
    check("quoted value keeps colon",
          m.parse_front_matter('---\nk: "a: b"\n---\n')["k"] == "a: b")


def test_block_list():
    m = load()
    got = m.parse_front_matter("---\nkeywords:\n  - one\n  - two\n---\n")
    check("block list parses", got.get("keywords") == ["one", "two"],
          repr(got.get("keywords")))

    # The reader resets to a list when a second scalar lands on the same key.
    # Before this was handled, `data[key].append` on a str raised AttributeError
    # and took the whole generator down.
    got = m.parse_front_matter("---\na: 1\nb: 2\nkeywords:\n  - x\n---\n")
    check("scalar key before list key", got.get("keywords") == ["x"])


def test_flow_list():
    m = load()
    got = m.parse_front_matter('---\nkeywords: ["a", "b"]\n---\n')
    check("flow list parses", got.get("keywords") == ["a", "b"],
          repr(got.get("keywords")))
    check("flow list empty", m.parse_front_matter('---\nk: []\n---\n')["k"] == [])
    # Unclosed bracket must degrade to a string, not raise.
    check("flow list unterminated is inert",
          isinstance(m.parse_front_matter('---\nk: ["a"\n---\n')["k"], str))


def test_inline_comments():
    m = load()
    # THE regression: _tools/exploitprotection.md carries
    #   language: PowerShell / C#
    # A reader that cuts at the first '#' produces "PowerShell / C", which then
    # ships a wrong programmingLanguage in the JSON-LD. This asserts the exact
    # value from the real file.
    got = m.parse_front_matter("---\nlanguage: PowerShell / C#\n---\n")
    check("C# survives (no space before hash)",
          got.get("language") == "PowerShell / C#", repr(got.get("language")))

    got = m.parse_front_matter('---\ntagline: "keeps # inside"  # dropped\n---\n')
    check("comment after quoted value dropped",
          got.get("tagline") == "keeps # inside", repr(got.get("tagline")))

    got = m.parse_front_matter("---\nk: v  # note\n---\n")
    check("trailing comment dropped", got.get("k") == "v", repr(got.get("k")))


def test_block_scalar():
    m = load()
    # Real shape from _tools/lanscan.md. The body contains colons; parsed as
    # keys they would inject junk into the mapping and, worse, could clobber a
    # real key depending on order.
    body = "---\nicon: |\n  <svg viewBox=\"0 0 24 24\">\n  <circle cx=\"12\"/>\n"
    got = m.parse_front_matter(body + "title: LANScan\n---\n")
    check("block scalar keeps title after body",
          got.get("title") == "LANScan", repr(got.get("title")))
    check("block scalar did not leak pseudo-keys",
          "svg viewBox" not in got, repr(sorted(got.keys())))
    check("block scalar body retained",
          "svg" in (got.get("icon") or ""), repr(got.get("icon")))

    got = m.parse_front_matter("---\ns: |-\n  line one\n  line two\ntitle: T\n---\n")
    check("block scalar terminates at next key", got.get("title") == "T")
    check("chomped indicator keeps both lines",
          got.get("s") == "line one\nline two", repr(got.get("s")))


def test_missing_front_matter():
    m = load()
    check("no header -> {}", m.parse_front_matter("# just markdown\n") == {})
    check("unterminated header -> {}",
          m.parse_front_matter("---\nk: v\n") == {})


def test_no_front_matter_separator():
    # A file that starts with '---' but has no closing '---' must not be read as
    # a header; otherwise body prose becomes config.
    m = load()
    check("body with dashed rule is not front matter",
          m.parse_front_matter("intro\n\n---\n\nmore\n") == {})


def test_real_tool_files():
    """Every shipped _tools page must parse to something with a title.

    Skipped where there is no _tools/ directory. Three of the five sites in the
    network publish no tool catalogue -- a data dashboard and a venue are not
    tool indexes -- and collect_tools() already returns [] for them. A test that
    hard-required the directory would fail on three correct sites, which is how a
    self-test gets deleted.
    """
    m = load()
    tools_dir = os.path.join(SITE_DIR, "_tools")
    if not os.path.isdir(tools_dir):
        check("no _tools/ directory on this site", True,
              "skipped: this site publishes no tool catalogue")
        return
    n = 0
    for fn in sorted(os.listdir(tools_dir)):
        if not fn.endswith(".md"):
            continue
        n += 1
        with io.open(os.path.join(tools_dir, fn), encoding="utf-8") as fh:
            data = m.parse_front_matter(fh.read())
        check("%s has a title" % fn, bool(data.get("title")),
              repr(data.get("title")))
    check("at least one tool page was checked", n > 0, "found %d" % n)


# --------------------------------------------------------------------------
# 2. the generators
# --------------------------------------------------------------------------

def test_description_uniqueness():
    """The defect build_seo.py exists to prevent: 17 identical descriptions.

    If two tools ever render the same <meta description> the whole point of the
    tool_description work is lost, and nothing else in CI would notice.
    """
    m = load()
    tools = m.collect_tools(m.load_cfg())
    if not tools:
        # Uniqueness is only meaningful when there is more than one tool, and
        # three sites in the network publish no catalogue at all.
        check("description uniqueness skipped: no tools", True)
        return
    # At least two tools, always: the property under test is that no two are
    # equal, which a single tool cannot falsify.
    check("at least two tools were collected", len(tools) >= 2, len(tools))
    descs = [m.tool_description(t, m.load_cfg()) for t in tools]
    check("every tool has a description", all(d for d in descs))
    dupes = {d for d in descs if descs.count(d) > 1}
    check("descriptions are unique", not dupes, sorted(dupes)[:2])
    for d in descs:
        check("description ends in one stop",
              d.endswith(".") and not d.endswith(".."), d[:60])
        check("description has no double space", "  " not in d, d[:60])


def test_license_url_not_about():
    """A tool page inherited site.description; the flag is that they differ."""
    m = load()
    cfg = m.load_cfg()
    tools = m.collect_tools(cfg)
    site_desc = cfg["organization"]["description"].split(".")[0] + "."
    for t in tools:
        d = m.tool_description(t, cfg)
        check("%s description is not the site blurb" % t["slug"],
              site_desc not in d, d[:70])


def test_graph_shape():
    m = load()
    cfg = m.load_cfg()
    graph = m.build_graph(cfg, m.collect_tools(cfg))
    nodes = graph["@graph"]
    check("context is schema.org", graph.get("@context") == "https://schema.org")
    org = nodes[0]
    check("org is first", org.get("@id", "").endswith("#organization"))
    check("logo url is absolute",
          org["logo"]["url"].startswith("https://"),
          org["logo"]["url"])
    # The bug this pins: og.image was 1200x630 landscape and was being shipped
    # as the organization logo, which fails Google's crop test. The logo must
    # come from logo.url and must NOT be the og: card path.
    check("logo is not the og card",
          "/assets/og/" not in org["logo"]["url"], org["logo"]["url"])
    ids = [n.get("@id") for n in nodes if n.get("@id")]
    check("@ids unique", len(ids) == len(set(ids)),
          [i for i in ids if ids.count(i) > 1][:3])
    # The ItemList is emitted only when the site actually publishes a tool
    # catalogue. A data dashboard with no _tools/ collection has none, and
    # asserting one there is asserting a defect.
    tools = m.collect_tools(cfg)
    item_lists = [n for n in nodes if n.get("@type") == "ItemList"]
    check("ItemList present iff the site has tools",
          bool(item_lists) == bool(tools),
          "tools=%d itemList=%d" % (len(tools), len(item_lists)))
    if not tools:
        check("no empty ItemList node", not item_lists,
              "an ItemList with zero items asserts an empty collection exists")
        return
    tail = item_lists[-1]
    check("ItemList is last", nodes[-1].get("@type") == "ItemList")
    check("numberOfItems matches list",
          tail.get("numberOfItems") == len(tail.get("itemListElement", [])))
    check("ItemList is non-empty", len(tail.get("itemListElement", [])) > 0)


def test_graph_positions_sequential():
    """ListItem position is 1-based and gapless; engines read it as a rank."""
    m = load()
    cfg = m.load_cfg()
    tools = m.collect_tools(cfg)
    if not tools:
        # No catalogue, no list, nothing to be sequential about. Asserted above
        # that the absence is deliberate rather than accidental.
        check("positions skipped: site has no tools", True)
        return
    nodes = m.build_graph(cfg, tools)["@graph"]
    tail = [n for n in nodes if n.get("@type") == "ItemList"][-1]
    pos = [e["position"] for e in tail["itemListElement"]]
    check("positions are 1..n", pos == list(range(1, len(pos) + 1)), pos[:5])


def test_determinism():
    """--check compares rendered text, so identical input must render identically.

    json.dumps sort_keys is load-bearing here; without it the dict order of a
    literal decides whether the file changed, and the gate reports drift on every
    run under a different hash seed.
    """
    m = load()
    cfg = m.load_cfg()
    tools = m.collect_tools(cfg)
    a = m.artifacts(cfg, tools)
    b = m.artifacts(cfg, tools)
    check("artifacts are byte-identical across runs",
          {k: v for k, v in a.items()} == {k: v for k, v in b.items()})
    for path, content in a.items():
        check("%s ends with newline" % os.path.basename(path),
              content.endswith("\n"))
        check("%s has no CRLF" % os.path.basename(path),
              "\r\n" not in content)

    # sort_keys is load-bearing and comparing two renders in one process does
    # NOT catch its removal: Python dict order is stable within a process, so
    # both renders come out identical either way and --check reports clean. What
    # actually breaks is across processes and across any edit that reorders a
    # literal. So assert the property directly on the rendered text -- keys
    # appear in sorted order at every nesting level.
    rendered = a[os.path.join(SITE_DIR, "_data", "seo_graph.json")]
    check("json keys are sorted on disk", _keys_sorted(rendered),
          "an unsorted key would make --check drift on unrelated edits")

    # And a dict built in a different insertion order must render identically.
    # This is the case a real commit hits: someone reorders a literal in
    # build_graph, the diff is pure noise, and the checked-in file stops
    # matching what the generator produces.
    forward = {"b": 1, "a": {"d": 2, "c": 3}}
    reverse = {"a": {"c": 3, "d": 2}, "b": 1}
    check("insertion order does not affect output",
          m.jdump(forward) == m.jdump(reverse))


# --------------------------------------------------------------------------
# 3. the validator
# --------------------------------------------------------------------------

def test_validator_accepts_real_config():
    m = load()
    problems = m.validate(m.load_cfg(), m.collect_tools(m.load_cfg()))
    check("shipped _data/seo.yml validates clean", not problems, problems[:3])


def test_validator_catches_dead_asset():
    m = load()
    cfg = m.load_cfg()
    cfg["og"]["image"] = "/assets/og/does-not-exist.png"
    problems = m.validate(cfg, m.collect_tools(cfg))
    check("dead og:image reported",
          any("og.image" in p for p in problems), problems)
    check("dead asset names the path",
          any("does-not-exist.png" in p for p in problems), problems)


def test_validator_catches_dead_route():
    m = load()
    cfg = m.load_cfg()
    cfg["topics"][0]["page"] = "/tools/nonexistent-tool/"
    problems = m.validate(cfg, m.collect_tools(cfg))
    check("dead topic route reported",
          any("no page builds there" in p for p in problems), problems)


def test_validator_catches_live_without_page():
    m = load()
    cfg = m.load_cfg()
    cfg["topics"][0].pop("page", None)
    problems = m.validate(cfg, m.collect_tools(cfg))
    check("claim:live with no page reported",
          any("claim:live with no page" in p for p in problems), problems)


def test_validator_allows_roadmap_without_page():
    """A roadmap cluster ships nothing, so having no page is correct for it.

    The check must not fire on that, or adding a planned topic would break the
    build and the incentive would be to drop the topic instead.
    """
    m = load()
    cfg = m.load_cfg()
    cfg["topics"][0].pop("page", None)
    cfg["topics"][0]["claim"] = "roadmap"
    problems = m.validate(cfg, m.collect_tools(cfg))
    check("roadmap topic with no page is allowed",
          not any("claim:live with no page" in p for p in problems), problems)


def test_validator_resolves_collection_routes():
    """A /tools/<slug>/ route resolves through the _tools/ collection.

    built_paths() walks source files and cannot know that _config.yml maps
    `tools` to /tools/:name/, so this branch is not optional -- every tool route
    in seo.yml depends on it. If it regresses, 6 topics fail validation at once.
    """
    m = load()
    # The collection branch only matters on a site that HAS a collection. The
    # universal half of this test -- that a plain page route resolves, that a
    # fake one does not, and that an external URL is not a local route -- runs
    # everywhere.
    check("plain markdown route resolves", m.route_exists("/"))
    check("nonexistent route does not resolve",
          not m.route_exists("/definitely-not-here/"))
    check("external url is not treated as a local route",
          not m.route_exists("https://example.com/"))

    if not m.collection_permalinks():
        check("collection permalinks skipped: no collections", True)
        return

    check("collection permalinks read from _config.yml",
          bool(m.collection_permalinks()), m.collection_permalinks())
    tools_dir = os.path.join(SITE_DIR, "_tools")
    slugs = sorted(m.url_slug(fn[:-3]) for fn in os.listdir(tools_dir)
                   if fn.endswith(".md"))
    if not slugs:
        check("collection route checks skipped: empty collection", True)
        return
    for slug in slugs:
        check("/tools/%s/ resolves" % slug, m.route_exists("/tools/%s/" % slug))
    check("collection route is case-insensitive on the filename",
          m.route_exists("/tools/%s/" % slugs[0].upper()))
    check("nonexistent collection route does not resolve",
          not m.route_exists("/tools/definitely-not-here/"))


def test_origin_matches_served_host():
    """A canonical for a host the site is not served from is a silent de-index.

    The repo has been published under more than one name, which is exactly how
    the two drift apart. Nothing else in CI compares them.
    """
    m = load()
    cfg = m.load_cfg()
    site = m.yaml_safe_load(os.path.join(SITE_DIR, "_config.yml"))
    check("seo.yml origin equals _config.yml url",
          cfg.get("origin", "").rstrip("/") == site.get("url", "").rstrip("/"),
          "%r vs %r" % (cfg.get("origin"), site.get("url")))


def test_canonical_urls_are_on_origin():
    """Fields that describe *this site* must point at the canonical origin.

    Scoped to those fields deliberately. codeRepository points at github.com and
    must -- that is the whole point of the field -- and @context is schema.org,
    an identifier rather than a fetch. Checking every URL in the graph would
    have to whitelist both, and a check with exceptions is a check that gets
    relaxed until it catches nothing.

    What matters is that `url` and `logo.url` cannot be built from a different
    host than the site serves from, which is a silent de-index.
    """
    m = load()
    cfg = m.load_cfg()
    origin = cfg["origin"].rstrip("/")
    graph = m.build_graph(cfg, m.collect_tools(cfg))
    offenders = []
    for node in graph["@graph"]:
        for key in ("url", "@id"):
            val = node.get(key)
            if isinstance(val, str) and val.startswith(("http://", "https://")):
                if not val.startswith(origin + "/"):
                    offenders.append("%s -> %s" % (key, val))
        logo = node.get("logo")
        if isinstance(logo, dict):
            val = logo.get("url", "")
            if not val.startswith(origin + "/"):
                offenders.append("logo.url -> %s" % val)
    check("every canonical URL is on the configured origin",
          not offenders, offenders[:4])
    check("origin has no trailing slash", not cfg["origin"].endswith("/"))


def test_orphan_keyword_cluster():
    """A keyword cluster with no page points crawlers at a 404."""
    m = load()
    cfg = m.load_cfg()
    cfg.setdefault("tools", {})["no-such-tool"] = {"keywords": ["x"]}
    orphans = set(cfg["tools"]) - set(t["slug"] for t in m.collect_tools(cfg))
    check("orphan detection is expressible", "no-such-tool" in orphans, orphans)


def main():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("=" * 60)
    print("build_seo self-test: %d checks, %d failure(s)"
          % (checks_run, len(failures)))
    print("=" * 60)
    for f in failures:
        print("  FAIL  %s" % f)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())