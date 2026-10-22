#!/usr/bin/env python3
"""check_seo.py -- assert this site's search surface is intact, after a build.

Every rule here corresponds to a defect that either shipped to the live site or
was caught before it could. None of them fail `jekyll build`, which is the
point: a Jekyll build is happy to emit two <title> elements, seventeen identical
meta descriptions, and a canonical pointing at a hostname this site is not
served from. A green build is not a green site.

Run it against _site (the built output), because that is what a crawler sees:

    bundle exec jekyll build
    python scripts/check_seo.py

    python scripts/check_seo.py --site .            # implied --built
    python scripts/check_seo.py --source-only       # pre-build checks only

Exit code 0 = clean, 1 = at least one failure.
"""

from __future__ import print_function

import io
import json
import os
import re
import sys
from html.parser import HTMLParser

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SITE_DIR = os.path.dirname(SCRIPT_DIR)

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    return bool(ok)


def read(path):
    with io.open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


# Liquid comments and HTML comments, whitespace-control variants included.
_LIQUID_COMMENT = re.compile(
    r"\{%-?\s*comment\s*-?%\}.*?\{%-?\s*endcomment\s*-?%\}", re.S | re.I)
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
_LIQUID_RAW = re.compile(r"\{%-?\s*raw\s*-?%\}.*?\{%-?\s*endraw\s*-?%\}", re.S | re.I)


def strip_comments(text):
    """Remove Liquid comments, Liquid raw blocks and HTML comments.

    Necessary before scanning a template for tags. Both checks this enables
    would otherwise fire on the very comments that DOCUMENT the tags: the note
    in default.html explaining why the hand-written <title> was removed
    contains the literal text `<title>`, and the note explaining that {% seo %}
    was removed contains the literal text `{% seo %}`. A checker that reports
    its own documentation as the defect is worse than no checker, because the
    obvious response is to delete the explanation.
    """
    text = _LIQUID_COMMENT.sub("", text)
    text = _LIQUID_RAW.sub("", text)
    text = _HTML_COMMENT.sub("", text)
    return text


# ---------------------------------------------------------------------------
# a small, strict head parser
# ---------------------------------------------------------------------------

class HeadParser(HTMLParser):
    """Collects the tags this gate cares about, in document order.

    Regex over HTML is how the previous generation of this check produced
    false confidence: `<title>` also matches inside a comment, and an
    attribute value can contain the literal text `rel="canonical"`. HTMLParser
    is tolerant of malformed markup, which is what a hand-rolled regex is not,
    and it is stdlib, so this runs in CI with no install step.
    """

    SKIP = {"script", "style", "svg", "template"}

    def __init__(self):
        HTMLParser.__init__(self, convert_charrefs=True)
        self.stack = []
        self.titles = []
        self.meta = []          # list of dicts
        self.links = []         # list of dicts
        self.ldjson = []        # list of raw strings
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        # JSON-LD is collected BEFORE the SKIP test. `script` is in SKIP, so
        # checking SKIP first silently discarded every structured-data block and
        # this checker reported "no JSON-LD on any page" while the pages were
        # in fact full of it -- a gate that reports the opposite of reality is
        # worse than a gate that reports nothing.
        if tag == "script" and (a.get("type") or "") == "application/ld+json":
            self.ldjson.append("")
            self.stack.append("ldjson")
            return
        if tag in self.SKIP:
            self.stack.append(tag)
            return
        if tag == "title":
            self.in_title = True
        elif tag == "meta":
            self.meta.append(a)
        elif tag == "link":
            self.links.append(a)

    def handle_endtag(self, tag):
        if self.stack and self.stack[-1] in ("script", "ldjson"):
            if tag == "script":
                self.stack.pop()
        elif self.stack and self.stack[-1] == tag:
            self.stack.pop()
        elif tag in self.SKIP:
            if tag in self.stack:
                self.stack.remove(tag)
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.titles.append(data)
        if self.stack and self.stack[-1] == "ldjson":
            self.ldjson[-1] += data

    # convenience accessors -----------------------------------------------

    def metas(self, **match):
        out = []
        for m in self.meta:
            if all((m.get(k) or "").lower() == v.lower() for k, v in match.items()):
                out.append(m)
        return out

    def links_rel(self, rel):
        return [l for l in self.links if "rel" in l
                and rel in (l.get("rel") or "").lower().split()]


def parse_head(html):
    p = HeadParser()
    p.feed(html)
    p.close()
    return p


# ---------------------------------------------------------------------------
# rules
# ---------------------------------------------------------------------------

MIN_DESC, MAX_DESC = 50, 300
DESC_WARN = 160          # above this Google truncates; warn, do not fail


def check_page(path, html, origin, brand, exp, shared):
    """Check one page.

    `exp` is this page's own expectations. `shared` is the cross-page accumulator
    (site_types, page_types, descriptions) and MUST be a distinct object owned by
    the caller.

    They were the same dict in the first version, and every cross-page result was
    written into a per-page dict that was then thrown away. The duplicate-
    description check therefore compared an always-empty mapping against itself
    and reported clean on a site that had just shipped seventeen identical
    descriptions. A check that cannot fail is worse than no check: it buys
    confidence and delivers none. See test_check_seo.py, which pins this.
    """
    rel = exp.get("rel", os.path.basename(path))
    p = parse_head(html)

    # --- one title ------------------------------------------------------
    title = "".join(p.titles).strip()
    check("%s: exactly one <title>" % rel, len(p.titles) == 1,
          "found %d" % len(p.titles))
    if title:
        check("%s: title is non-empty" % rel, len(title) > 0)
        # Google truncates around 60 chars; the brand suffix is the part that
        # is safe to lose, so the distinctive half has to come first.
        check("%s: title length %d is <= 70" % (rel, len(title)), len(title) <= 70,
              "too long for a SERP line: %r" % title)

    # --- one description -------------------------------------------------
    descs = p.metas(name="description")
    check("%s: exactly one meta description" % rel, len(descs) == 1,
          "found %d" % len(descs))
    if len(descs) == 1:
        d = (descs[0].get("content") or "").strip()
        check("%s: description length %d in [%d,%d]" % (rel, len(d), MIN_DESC, MAX_DESC),
              MIN_DESC <= len(d) <= MAX_DESC,
              "too short reads as a placeholder, too long is truncated" if d else "empty")
        if len(d) > DESC_WARN:
            print("  note: %s description is %d chars; Google shows ~%d"
                  % (rel, len(d), DESC_WARN))
        if d:
            shared["descriptions"][rel] = d

    # --- one canonical, on the right host --------------------------------
    canons = p.links_rel("canonical")
    check("%s: exactly one canonical" % rel, len(canons) == 1,
          "found %d" % len(canons))
    if len(canons) == 1:
        href = canons[0].get("href") or ""
        check("%s: canonical is absolute" % rel, href.startswith("http"), href)
        check("%s: canonical is on %s" % (rel, origin),
              href.startswith(origin + "/") or href == origin,
              "off-host canonical de-indexes the site: %s" % href)
        check("%s: canonical has no fragment" % rel, "#" not in href, href)

    # --- Open Graph ------------------------------------------------------
    og_title = p.metas(property="og:title")
    check("%s: exactly one og:title" % rel, len(og_title) == 1, "found %d" % len(og_title))
    og_desc = p.metas(property="og:description")
    check("%s: exactly one og:description" % rel, len(og_desc) == 1, "found %d" % len(og_desc))
    og_url = p.metas(property="og:url")
    check("%s: exactly one og:url" % rel, len(og_url) == 1, "found %d" % len(og_url))
    if len(og_url) == 1:
        check("%s: og:url matches canonical" % rel,
              (og_url[0].get("content") or "") == (canons[0].get("href") if canons else ""),
              "og:url=%r" % og_url[0].get("content"))

    # --- the card image --------------------------------------------------
    og_img = p.metas(property="og:image")
    check("%s: exactly one og:image" % rel, len(og_img) == 1, "found %d" % len(og_img))
    if og_img:
        check("%s: og:image is absolute" % rel,
              (og_img[0].get("content") or "").startswith("http"),
              og_img[0].get("content") or "")
        ext = (og_img[0].get("content") or "").split("?")[0].lower()
        # Facebook, X, Bluesky and LinkedIn all silently drop an SVG or a
        # WebP here. A card that renders nowhere is worse than no card,
        # because it looks configured.
        check("%s: og:image is a raster format" % rel,
              ext.endswith((".png", ".jpg", ".jpeg")), ext)
    check("%s: og:image:width present" % rel, len(p.metas(property="og:image:width")) == 1)
    check("%s: og:image:height present" % rel, len(p.metas(property="og:image:height")) == 1)
    check("%s: og:image:alt present" % rel, len(p.metas(property="og:image:alt")) == 1)

    # --- Twitter ---------------------------------------------------------
    tw_card = p.metas(name="twitter:card")
    check("%s: exactly one twitter:card" % rel, len(tw_card) == 1, "found %d" % len(tw_card))
    if tw_card:
        check("%s: twitter:card is summary_large_image" % rel,
              (tw_card[0].get("content") or "") == "summary_large_image",
              "summary renders a thumbnail that is too small to read; got %r"
              % tw_card[0].get("content"))
    check("%s: twitter:image present" % rel, len(p.metas(name="twitter:image")) == 1)
    check("%s: twitter:title present" % rel, len(p.metas(name="twitter:title")) == 1)
    check("%s: twitter:description present" % rel, len(p.metas(name="twitter:description")) == 1)

    # --- robots ----------------------------------------------------------
    robots = p.metas(name="robots")
    noindex = False
    if robots:
        want = exp.get("robots")
        if want:
            check("%s: robots is %r" % (rel, want),
                  (robots[0].get("content") or "") == want,
                  "got %r" % robots[0].get("content"))
        val = (robots[0].get("content") or "").lower()
        noindex = "noindex" in val
    shared["noindex"].append(rel) if noindex else None

    # --- JSON-LD ---------------------------------------------------------
    check("%s: has a JSON-LD block" % rel, len(p.ldjson) >= 1, "found %d" % len(p.ldjson))
    for i, raw in enumerate(p.ldjson):
        if not raw.strip():
            check("%s: JSON-LD block %d is non-empty" % (rel, i), False)
            continue
        try:
            doc = json.loads(raw)
        except ValueError as e:
            check("%s: JSON-LD block %d parses" % (rel, i), False, str(e))
            continue
        check("%s: JSON-LD block %d parses" % (rel, i), True)
        nodes = doc.get("@graph") if isinstance(doc, dict) else None
        if nodes is not None:
            types = set()
            for n in nodes:
                t = n.get("@type")
                if isinstance(t, list):
                    types.update(t)
                elif t:
                    types.add(t)
            shared["site_types"].update(types)
        elif isinstance(doc, list):
            for n in doc:
                t = n.get("@type")
                if t:
                    shared["page_types"].add(t)

    # --- heading sanity for a tool page ----------------------------------
    if exp.get("tool"):
        # A tool page whose H1 is missing is unrankable no matter what the
        # metadata says, so the metadata being perfect is not sufficient.
        m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.I | re.S)
        h1 = re.sub(r"<[^>]+>", "", m.group(1)).strip() if m else ""
        check("%s: has exactly one h1" % rel,
              len(re.findall(r"<h1[\s>]", html, re.I)) == 1,
              "found %d" % len(re.findall(r"<h1[\s>]", html, re.I)))
        check("%s: h1 is non-empty" % rel, bool(h1), repr(h1[:60]))

    return p


def iter_html(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in (".git", ".jekyll-cache")]
        for fn in filenames:
            if fn.endswith(".html"):
                yield os.path.join(dirpath, fn)


def main(argv):
    source_only = "--source-only" in argv
    site = None
    if "--site" in argv:
        site = os.path.abspath(argv[argv.index("--site") + 1])
    site = site or SITE_DIR

    built = os.path.join(site, "_site")
    built = os.path.abspath(built) if "--built" in argv or not source_only else None

    # ---------------- source-level checks (no build needed) --------------
    cfg_path = os.path.join(site, "_config.yml")
    if not os.path.isfile(cfg_path):
        print("FAIL: no _config.yml under %s" % site)
        return 1
    try:
        import yaml
        cfg = yaml.safe_load(read(cfg_path))
    except ImportError:
        print("FAIL: PyYAML required")
        return 1

    seo_path = os.path.join(site, "_data", "seo.yml")
    if not os.path.isfile(seo_path):
        check("_data/seo.yml exists", False, "the SEO single source of truth is missing")
        report()
        return 1
    seo = yaml.safe_load(read(seo_path))

    origin = (seo.get("origin") or "").rstrip("/")
    cfg_url = (cfg.get("url") or "").rstrip("/")
    check("_data/seo.yml origin matches _config.yml url",
          origin == cfg_url,
          "seo.yml says %s, _config.yml says %s -- a canonical on the wrong host "
          "is a silent de-index" % (origin, cfg_url))

    cname = os.path.join(site, "CNAME")
    if os.path.isfile(cname):
        cname_host = read(cname).strip().lower()
        check("origin host matches CNAME", origin.lower().endswith(cname_host),
              "CNAME is %s, origin is %s" % (cname_host, origin))

    # No second writer of the head.
    layout = os.path.join(site, "_layouts", "default.html")
    if os.path.isfile(layout):
        lay = strip_comments(read(layout))
        check("default.html does not write its own <title>",
              "<title>" not in lay, "a second title writer; see _includes/seo-head.html")
        check("default.html does not write its own meta description",
              not re.search(r'<meta\s+name="description"', lay, re.I))
        check("default.html includes seo-head.html",
              "seo-head.html" in read(layout))
        check("default.html no longer emits {% seo %}",
              "{% seo %}" not in lay,
              "jekyll-seo-tag and seo-head.html both write titles/canonicals")
        check("jekyll-seo-tag is not enabled in _config.yml",
              "jekyll-seo-tag" not in (cfg.get("plugins") or []))

    # Every layout that renders a full <head> must defer to the same owner, or
    # a page that uses it ships a head this gate never sees.
    layouts_dir = os.path.join(site, "_layouts")
    if os.path.isdir(layouts_dir):
        for fn in sorted(os.listdir(layouts_dir)):
            if not fn.endswith(".html"):
                continue
            lp = os.path.join(layouts_dir, fn)
            lt = strip_comments(read(lp))
            standalone = "<head" in lt
            check("_layouts/%s either defers to default or includes seo-head" % fn,
                  (not standalone) or ("seo-head.html" in read(lp)) or
                  ("layout: default" in lt),
                  "writes its own <head> with no SEO include")

    # The AI-crawler manifest exists and is non-trivial.
    for fname in ("llms.txt", "llms-full.txt"):
        fp = os.path.join(site, fname)
        ok = os.path.isfile(fp)
        check("%s exists" % fname, ok)
        if ok:
            body = read(fp)
            check("%s is not a stub" % fname, len(body) > 400, "%d bytes" % len(body))
            check("%s has an H1" % fname, body.lstrip().startswith("# "))
            check("%s links the origin" % fname, origin in body)

    # Generated artifacts are current.
    sys.path.insert(0, SCRIPT_DIR)
    try:
        import build_seo
        rc = build_seo.main(["--check"])
        check("generated SEO artifacts are up to date", rc == 0,
              "run: python scripts/build_seo.py")
    except Exception as e:                      # noqa: BLE001
        check("build_seo.py --check runs", False, "%s: %s" % (type(e).__name__, e))

    # OG images referenced actually exist and are the right size.
    try:
        from PIL import Image
        have_pil = True
    except ImportError:
        have_pil = False

    def verify_image(rel, why):
        fp = os.path.join(site, rel.lstrip("/").replace("/", os.sep))
        if not os.path.isfile(fp):
            check("%s exists (%s)" % (rel, why), False)
            return
        check("%s exists (%s)" % (rel, why), True)
        if have_pil:
            with Image.open(fp) as im:
                w, h = im.size
            check("%s is 1200x630 (%s)" % (rel, why), (w, h) == (1200, 630),
                  "is %dx%d" % (w, h))

    og = seo.get("og") or {}
    if og.get("image"):
        verify_image(og["image"], "site card")

    if source_only:
        report()
        return 0 if all(ok for _, ok, _ in RESULTS) else 1

    # ---------------- built-output checks --------------------------------
    if not os.path.isdir(built):
        print("FAIL: %s does not exist -- run `bundle exec jekyll build` first" % built)
        report()
        return 1

    pages = sorted(iter_html(built))
    check("build produced pages", len(pages) > 0, "no HTML under %s" % built)

    shared = {"descriptions": {}, "site_types": set(), "page_types": set(),
              "noindex": []}
    for path in pages:
        rel = os.path.relpath(path, built).replace("\\", "/")
        if rel.startswith("assets/") or "/assets/" in rel:
            continue
        exp = {"rel": rel}
        exp["tool"] = "/tools/" in rel
        check_page(path, read(path), origin, seo.get("brand", ""), exp, shared)

    # Uniqueness across the site. The defect this replaces: 17 tool pages all
    # rendering site.description, so Google saw 17 near-duplicates and kept
    # one.
    descs = shared["descriptions"]
    # Guard the guard. An empty accumulator would make every pairwise check
    # vacuously true, which is how the first version of this file reported a
    # site with seventeen identical descriptions as clean. If nothing was
    # collected, that is itself the failure.
    check("descriptions were collected from every page", len(descs) > 0,
          "no descriptions collected -- the cross-page accumulator is broken, "
          "so the uniqueness check below would pass vacuously")
    check("description coverage is complete",
          len(descs) == len([p for p in pages
                             if not os.path.relpath(p, built).replace("\\", "/")
                             .startswith("assets/")]),
          "collected %d descriptions for %d pages"
          % (len(descs), len([p for p in pages
                              if not os.path.relpath(p, built)
                              .replace("\\", "/").startswith("assets/")])))

    dupes = {}
    noindex = set(shared["noindex"])
    for rel, d in descs.items():
        # A noindex page is excluded from the uniqueness rule on purpose. A
        # rename stub and its replacement, or a page and the alias that forwards
        # to it, are SUPPOSED to carry identical copy -- that is what makes the
        # pair read as one page. Holding them to the same standard would push
        # authors to invent filler descriptions for pages that exist only to
        # redirect, which is worse for the site than the duplication is.
        if rel in noindex:
            continue
        dupes.setdefault(d, []).append(rel)
    bad = {d: r for d, r in dupes.items() if len(r) > 1}
    check("every indexed page has a unique meta description", not bad,
          "; ".join("%r on %s" % (d[:60], ", ".join(r)) for d, r in list(bad.items())[:3]))

    # The site-level entity must be present somewhere, or nothing on this site
    # can ever become a knowledge-graph entity.
    check("JSON-LD declares an Organization", "Organization" in shared["site_types"],
          "saw %s" % sorted(shared["site_types"]))
    check("JSON-LD declares a WebSite", "WebSite" in shared["site_types"])

    # The tools assertions apply only to a site that actually publishes a tool
    # catalogue. transhumanists.github.io is a data dashboard: it has no
    # _tools/ collection and no /tools/ routes, so it legitimately has no
    # SoftwareApplication nodes and no ItemList. Asserting them there would have
    # been a permanently red check on a correct site, which is how a gate gets
    # switched off.
    tools_dir = os.path.join(site, "_tools")
    has_tools = os.path.isdir(tools_dir) and any(
        fn.endswith(".md") for fn in os.listdir(tools_dir))
    check("JSON-LD declares an ItemList of tools",
          ("ItemList" in shared["site_types"]) == has_tools,
          "expected ItemList=%s for a site with tools=%s, saw %s"
          % (has_tools, has_tools, sorted(shared["site_types"])))
    check("JSON-LD declares SoftwareApplication nodes",
          ("SoftwareApplication" in shared["site_types"]) == has_tools,
          "expected SoftwareApplication=%s for a site with tools=%s, saw %s"
          % (has_tools, has_tools, sorted(shared["site_types"])))
    check("homepage declares WebPage",
          "WebPage" in shared["page_types"] or "WebPage" in shared["site_types"])

    # Sitemap must exist and must not list the same URL twice.
    sm = os.path.join(built, "sitemap.xml")
    if check("sitemap.xml exists", os.path.isfile(sm)):
        body = read(sm)
        locs = re.findall(r"<loc>(.*?)</loc>", body)
        check("sitemap has no duplicate <loc>", len(locs) == len(set(locs)),
              "%d urls, %d unique" % (len(locs), len(set(locs))))
        check("sitemap urls are on %s" % origin,
              all(u.startswith(origin) for u in locs),
              "first offender: %s" % next((u for u in locs if not u.startswith(origin)), ""))

    # robots.txt must exist, allow the site, and point at that same sitemap.
    rb = os.path.join(built, "robots.txt")
    if check("robots.txt exists", os.path.isfile(rb)):
        body = read(rb)
        check("robots.txt does not disallow everything",
              not re.search(r"(?im)^\s*Disallow:\s*/\s*$", body),
              "a site-wide Disallow is invisible in every search engine")
        sm_refs = re.findall(r"(?im)^\s*Sitemap:\s*(\S+)", body)
        check("robots.txt declares exactly one sitemap", len(sm_refs) == 1,
              "found %r" % sm_refs)
        if sm_refs:
            check("robots.txt sitemap matches the built one",
                  sm_refs[0].rstrip("/") == (origin + "/sitemap.xml"),
                  "%s vs %s/sitemap.xml" % (sm_refs[0], origin))
        # Named AI crawlers, because a generic User-agent group does not
        # reliably cover them and each vendor documents its own token.
        for ua in ("GPTBot", "ClaudeBot", "PerplexityBot", "Google-Extended"):
            check("robots.txt addresses %s" % ua, ua in body,
                  "no explicit grant for %s" % ua)

    # Every route this site ADVERTISES must be a page that actually builds, and
    # must appear in the sitemap.
    #
    # This check is here because its absence was a real miss. build_seo.py
    # validates routes against the SOURCE tree, and on openstageisland four pages
    # carried a `canonical:` front-matter key but no `permalink:`. Jekyll ignores
    # `canonical:` when deciding where a page publishes, so those pages were
    # served from /<name>.html while advertising /<name>/ as canonical -- and
    # /<name>/ was a 404. Source-side validation could not see it, because the
    # source-side heuristic reads the canonical string and believes it. Only
    # comparing what seo.yml advertises against what the BUILD produced finds it.
    sys.path.insert(0, SCRIPT_DIR)
    try:
        built_routes = set()
        built_index = {}
        for dp, dns, fns in os.walk(built):
            dns[:] = [d for d in dns if d not in (".git",)]
            for fn in fns:
                if fn == "index.html":
                    # Directory-style URL: /tools/lanscan/ for tools/lanscan/
                    # index.html. The trailing slash is part of the route, and
                    # forgetting it here made every advertised route report as
                    # missing -- which looked like 16 real 404s.
                    rel = os.path.relpath(dp, built).replace("\\", "/")
                    rel = "" if rel == "." else rel.strip("/")
                    built_routes.add("/" + rel + "/" if rel else "/")
                    built_index[("/" + rel + "/" if rel else "/")] = \
                        os.path.join(dp, fn)
                elif fn.endswith(".html"):
                    route = "/" + os.path.relpath(
                        os.path.join(dp, fn), built).replace("\\", "/")
                    built_routes.add(route)
                    built_index[route] = os.path.join(dp, fn)

        advertised = []
        for t in seo.get("topics") or []:
            if t.get("claim", "live") == "live" and t.get("page"):
                advertised.append(("topics[%s].page" % t.get("id"), t["page"]))
        for entry in (seo.get("pages") or []):
            if entry.get("path"):
                advertised.append(("pages[%s].path"
                                   % (entry.get("title") or entry["path"]),
                                   entry["path"]))
        for label, route in advertised:
            if route.startswith(("http://", "https://", "//")):
                continue
            raw, _, frag = route.partition("#")
            base = raw.rstrip("/")
            # Compared in both spellings on purpose: a directory route is built
            # as /<name>/index.html and a file route as /<name>.html, and an
            # seo.yml entry may legitimately name either. Normalising to one
            # spelling reports every file-style route (/live.html) as missing.
            hit = base in built_routes or (base + "/") in built_routes
            check("advertised route builds: %s -> %s" % (label, route), hit,
                  "advertised but the build produced no such page; a canonical "
                  "pointing here would be a 404")
            if not (hit and frag):
                continue
            # The anchor half. /#biotechnology is a working link only if the
            # BUILT page carries id="biotechnology" -- the thing a visitor
            # actually lands on. build_seo.py checks this against the source;
            # this checks it against the output, which is what ships.
            page = built_index.get(base if base else "/") or \
                built_index.get(base + "/")
            ok = False
            if page and os.path.isfile(page):
                body = read(page)
                ok = ('id="%s"' % frag) in body
            check("advertised anchor exists: %s -> #%s" % (label, frag), ok,
                  "the built page carries no id=%r, so the fragment scrolls "
                  "nowhere" % frag)
    except Exception as e:                              # noqa: BLE001
        check("advertised-route coverage could run", False,
              "%s: %s" % (type(e).__name__, e))

    # llms.txt must be reachable at the root, not swallowed by the data dir.
    for fname in ("llms.txt", "llms-full.txt"):
        check("%s is published at the root" % fname,
              os.path.isfile(os.path.join(built, fname)))

    # Every /tools/<slug>/ page must have a rendered card on disk. Keyed by the
    # URL slug, not the filename, for the same reason seo-head.html is.
    tools_dir = os.path.join(site, "_tools")
    if os.path.isdir(tools_dir) and have_pil:
        sys.path.insert(0, SCRIPT_DIR)
        from build_seo import url_slug
        for fn in sorted(os.listdir(tools_dir)):
            if not fn.endswith(".md"):
                continue
            slug = url_slug(fn[:-3])
            verify_image("/assets/og/tools/%s.png" % slug, "tool card")

    return report()


def report():
    fails = [(n, d) for n, ok, d in RESULTS if not ok]
    for name, ok, detail in RESULTS:
        if not ok:
            print("  FAIL  %s%s" % (name, ("  -- " + detail) if detail else ""))
    print()
    if fails:
        print("FAILED: %d of %d checks" % (len(fails), len(RESULTS)))
        return 1
    print("OK: %d SEO checks passed" % len(RESULTS))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))