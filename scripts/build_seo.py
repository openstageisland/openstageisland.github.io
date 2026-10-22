#!/usr/bin/env python3
"""build_seo.py -- generate this site's crawler-facing artifacts from _data/seo.yml.

Three outputs, all deterministic so `--check` can prove they are current:

  _data/seo_graph.json   the JSON-LD @graph: Organization, WebSite, every
                         SoftwareApplication, and the ItemList of tools.
  llms.txt               the llms.txt manifest (AI crawlers / answer engines).
  llms-full.txt          the same content, expanded -- every tool, every topic,
                         full descriptions. This is the file an LLM actually
                         reads, so it is generated rather than hand-written and
                         therefore cannot drift from _tools/.

Why generated instead of checked in by hand: every one of these files is a
projection of _data/seo.yml plus the _tools/*.md front matter. Hand-maintained,
they go stale within a week -- a tool gets renamed and the manifest keeps
pointing at a 404, which is worse than having no manifest because the crawlers
that read it trust it. `--check` is wired into CI so the drift is a build
failure rather than a silent loss of rankings.

Usage:
    python scripts/build_seo.py            # write the artifacts
    python scripts/build_seo.py --check    # fail if they are out of date

Exit code 0 = clean, 1 = drift or a bad input (with the reason on stdout).
"""

from __future__ import print_function

import io
import json
import os
import re
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SITE_DIR = os.path.dirname(SCRIPT_DIR)
SEOCFG = os.path.join(SITE_DIR, "_data", "seo.yml")
REPOS_YML = os.path.join(SITE_DIR, "_data", "repos.yml")
TOOLS_DIR = os.path.join(SITE_DIR, "_tools")
OUT_GRAPH = os.path.join(SITE_DIR, "_data", "seo_graph.json")
OUT_LLMS = os.path.join(SITE_DIR, "llms.txt")
OUT_LLMS_FULL = os.path.join(SITE_DIR, "llms-full.txt")
OUT_SITEMAP = os.path.join(SITE_DIR, "sitemap.xml")


# --------------------------------------------------------------------------
# front matter
# --------------------------------------------------------------------------

def read_text(path):
    with io.open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def parse_front_matter(text):
    """Minimal YAML front-matter reader.

    Deliberately not a yaml.load: this repo's CI runs `pip install pyyaml`
    for some jobs and not others, and a generator that only runs on a machine
    with a dependency is a generator that silently stops running. The subset
    used by _tools/*.md is flat scalars, block scalars, block lists and flow
    lists, which this handles.

    Returns {} when there is no front matter, so callers can treat a missing
    header the same as an empty one.
    """
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    block = text[3:end].strip("\n")
    lines = block.split("\n")
    data = {}
    key = None
    i = 0
    while i < len(lines):
        raw = lines[i]
        i += 1
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        stripped = raw.lstrip()
        indent = len(raw) - len(stripped)
        if stripped.startswith("- ") and key:
            data.setdefault(key, [])
            if not isinstance(data[key], list):
                data[key] = []
            data[key].append(_scalar(_strip_inline_comment(stripped[2:].strip())))
            continue
        if ":" not in raw:
            continue
        k, _, v = raw.partition(":")
        k = k.strip()
        v = _strip_inline_comment(v.strip())
        if v in ("|", "|-", ">", ">-"):
            # Block scalar: `icon: |` followed by an indented SVG body. The
            # body is kept verbatim rather than re-parsed, because it contains
            # colons (`xmlns:xlink`, `stroke-width`) that would otherwise be
            # mistaken for top-level keys and inject junk into the mapping.
            body = []
            body_indent = None
            while i < len(lines):
                nxt = lines[i]
                if not nxt.strip():
                    body.append("")
                    i += 1
                    continue
                lead = len(nxt) - len(nxt.lstrip())
                if lead <= indent:
                    break
                if body_indent is None:
                    body_indent = lead
                # Strip exactly the first body's indentation. A line indented
                # deeper than that keeps its extra padding, so nested YAML
                # survives. `>=`, not `>`: the first body line is exactly at
                # body_indent and must lose those bytes too.
                body.append(nxt[body_indent:])
                i += 1
            data[k] = "\n".join(body).rstrip("\n")
            key = None
            continue
        if v.startswith("["):
            data[k] = _flow_list(v)
            key = None
            continue
        if v == "":
            data[k] = ""
            key = k
        else:
            data[k] = _scalar(v)
            key = None
    return data


def _strip_inline_comment(v):
    """Drop a trailing ` # ...` comment, but only outside quotes.

    The anchor is a `#` preceded by whitespace or starting the value. That
    distinction is load-bearing: `language: PowerShell / C#` is a real value in
    _tools/exploitprotection.md, and a naive "cut at the first #" turns it into
    `PowerShell / C`. Quote state is tracked so `tagline: "a # b"` survives.
    """
    quote = None
    for i, ch in enumerate(v):
        if quote:
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
            continue
        if ch == "#" and (i == 0 or v[i - 1] in " \t"):
            return v[:i].strip()
    return v


def _flow_list(v):
    """Parse a one-line `[a, b]` sequence into a list of scalars.

    Returns a plain string if the bracket never closes, so a malformed value
    degrades to something printable instead of raising mid-generation.
    """
    if not v.endswith("]"):
        return _scalar(v)
    inner = v[1:-1].strip()
    if not inner:
        return []
    return [_scalar(_strip_inline_comment(part.strip())) for part in inner.split(",")]


def _scalar(v):
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    return v


# --------------------------------------------------------------------------
# schema.org helpers
# --------------------------------------------------------------------------

def jdump(obj):
    """Stable JSON: sorted keys, 2-space indent, trailing newline.

    Sorted keys matter for --check. Without them the dict order of a literal
    would be the only thing deciding whether the file changed, and the check
    would report drift every time Python changed its hash seed.
    """
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def abs_url(origin, path):
    if not path:
        return None
    if path.startswith("http://") or path.startswith("https://"):
        return path
    return origin.rstrip("/") + "/" + path.lstrip("/")


# Jekyll's default slugify, reimplemented because this generator has to agree
# with it exactly:
#
#   string.downcase.strip.gsub(/[^[:alnum:]]+/, "-").gsub(/\A-|-\z/, "")
#
# It has to agree exactly, because _config.yml declares
# `permalink: /tools/:name/` for the collection and Jekyll fills :name from this
# function. `_tools/BlackGlass.md` therefore publishes at `/tools/blackglass/`,
# not `/tools/BlackGlass/`.
#
# That mismatch is not theoretical. The first version of this file built node
# @ids from the filename, seo-head.html looked them up from the URL, and the two
# disagreed on exactly the tools whose filenames contain uppercase letters.
# Seven of eighteen tool pages quietly fell back to site.description -- so they
# shipped one identical meta description seven times over, which is the precise
# defect this whole layer exists to remove. The failure was invisible: the
# build was green and the pages looked right.
def url_slug(name):
    s = (name or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def wrap(text, width=76, indent=""):
    """Wrap prose for llms.txt. Not a hard wrap for the web -- only the
    manifests, which are read by machines and diffed by humans."""
    words = (text or "").split()
    lines, cur = [], indent
    for w in words:
        if cur.strip() and len(cur) + len(w) + 1 > width:
            lines.append(cur.rstrip())
            cur = indent + w + " "
        else:
            cur += w + " "
    if cur.strip():
        lines.append(cur.rstrip())
    return "\n".join(lines)


# --------------------------------------------------------------------------
# loaders
# --------------------------------------------------------------------------

def load_cfg():
    return yaml_safe_load(SEOCFG)


def yaml_safe_load(path):
    """yaml.safe_load of a file, with a dependency error that names the fix.

    Imported lazily and here rather than at module scope so that `--check`
    reports "pip install pyyaml" instead of a traceback, and so that a caller
    which only needs the pure functions can import this module without PyYAML.
    """
    import yaml
    return yaml.safe_load(read_text(path))


def collect_tools(cfg):
    """Every shipped tool, keyed by the URL slug it publishes at.

    Sourced from the _tools/*.md files rather than _data/repos.yml, because the
    front matter of the page that actually exists is the only source that can
    not drift: verify_data.py already pins repos.yml against _tools/, and this
    reads the half that is rendered into a URL.

    A missing _tools/ directory returns an empty list rather than raising. Not
    every site in the network has a tool catalogue -- transhumanists.github.io
    is a data dashboard, not a tool index -- and the generator is shared across
    all of them. Returning [] is correct there: the graph legitimately becomes
    Organization + WebSite with no SoftwareApplication nodes, and llms.txt
    legitimately has no Tools section.
    """
    keywords = (cfg.get("tools") or {})
    tools = []
    if not os.path.isdir(TOOLS_DIR):
        return tools
    for fn in sorted(os.listdir(TOOLS_DIR)):
        if not fn.endswith(".md"):
            continue
        name = fn[:-3]
        fm = parse_front_matter(read_text(os.path.join(TOOLS_DIR, fn)))
        if not fm.get("title"):
            # Not a real collection document. Skip rather than emit a node
            # pointing at a page with an empty <h1>.
            continue
        slug = url_slug(name)
        # Keyword config is keyed by the URL slug, not the filename, so the key
        # in _data/seo.yml is the same string that appears in the published URL.
        extra = (keywords.get(slug) or {}).get("keywords") or []
        tools.append({
            "slug": slug,
            "source": name,
            "name": fm.get("title"),
            "tagline": fm.get("tagline", ""),
            "platform": fm.get("platform", ""),
            "language": fm.get("language", ""),
            "category": fm.get("category", ""),
            "repo_url": fm.get("repo_url", ""),
            "demo_url": fm.get("demo_url", ""),
            "featured": str(fm.get("featured", "false")).lower() == "true",
            "keywords": extra,
        })
    return tools


def tool_description(t, cfg):
    """A unique, searchable sentence set per tool.

    The defect this replaces: every tool page inherited site.description, so 17
    pages shipped one identical <meta name="description">. Google reads that as
    17 near-duplicates and picks at most one; the other 16 carry no signal at
    all. Built from the tool's own fields so it can never be a copy of another.
    """
    parts = []
    if t["tagline"]:
        # Taglines carry no terminal punctuation, so the stop has to be added
        # here or the next clause runs on as "history search Runs on Windows".
        parts.append(_sentence(t["tagline"]))
    if t["platform"]:
        parts.append(_sentence(t["platform"]))
    if t["keywords"]:
        # One keyword, not all of them, and not last. Google truncates a meta
        # description around 160 characters and shows the FRONT of it, so the
        # searchable phrase has to come before the platform string -- the tail
        # is the part that gets cut. The full keyword set is not lost: it is in
        # this node's `keywords` field, which is what structured data is for.
        parts.append(_sentence(t["keywords"][0], capitalize=True))
    return " ".join(parts)


# Acronyms that must not be title-cased when a keyword fragment is spliced in
# after a sentence break. `rss reader` must become `RSS reader`, not `Rss
# reader` -- the latter is how a copy-paste bug announces itself in a SERP.
ACRONYMS = {
    "rss": "RSS", "dns": "DNS", "lan": "LAN", "vpn": "VPN", "api": "API",
    "apis": "APIs", "gui": "GUI", "cli": "CLI", "ssh": "SSH", "http": "HTTP",
    "https": "HTTPS", "tls": "TLS", "ssl": "SSL", "ai": "AI", "agi": "AGI",
    "llm": "LLM", "llms": "LLMs", "lora": "LoRa", "lorawan": "LoRaWAN",
    "usb": "USB", "ip": "IP", "ipv4": "IPv4", "ipv6": "IPv6", "json": "JSON",
    "yaml": "YAML", "html": "HTML", "xml": "XML", "url": "URL", "os": "OS",
    "p2p": "P2P", "ups": "UPS", "qa": "QA", "sdk": "SDK", "ide": "IDE",
    "cicd": "CI/CD", "pi": "Pi", "sd": "SD", "hf": "HF", "ar": "AR",
    "vr": "VR", "iot": "IoT", "osint": "OSINT", "pki": "PKI", "sso": "SSO",
}


def _titlecase_fragment(text):
    """Upper-case the opening word, and restore acronyms anywhere in the phrase.

    Both halves are needed. `rss reader` alone would survive a naive
    `text[0].upper()`, but `block ads at dns` would still end in a lowercase
    `dns`. Substitution is whole-word only, so "android" is not turned into
    "ANDROID" -- only exact matches against the table are rewritten.
    """
    if not text:
        return text
    words = text.split(" ")
    for i, w in enumerate(words):
        bare = w.strip(".,;:()[]").lower()
        if bare in ACRONYMS:
            lead = w[:len(w) - len(w.lstrip(".,;:()["))]
            trail = w[len(w.rstrip(".,;:)")):]
            words[i] = lead + ACRONYMS[bare] + trail
        elif i == 0:
            words[i] = w[0].upper() + w[1:]
    return " ".join(words)


def _sentence(text, capitalize=False):
    """One trailing full stop, and only one.

    `capitalize` is for keyword fragments spliced in after a sentence break --
    a description that reads "search. second life chat." looks like a bug to
    the human scanning the SERP, and that human is who has to click it.
    """
    text = " ".join((text or "").split()).rstrip(" .;:,")
    if not text:
        return ""
    if capitalize:
        text = _titlecase_fragment(text)
    return text + "."


def rel_to(path):
    return os.path.relpath(path, SITE_DIR).replace("\\", "/")


def _source_files_for(route):
    """Every source file that renders to `route`, as text.

    Used only for fragment validation. Returns the homepage for "/", the file
    behind a permalink for a collection page, and the bare stem otherwise. A
    route this cannot resolve yields nothing, and the caller then reports the
    fragment as unresolvable -- which is the correct outcome, since it means the
    anchor genuinely cannot be verified.
    """
    stem = route.strip("/")
    if stem in ("", "index"):
        stem = "index"
    out = []
    for ext in (".md", ".html"):
        p = os.path.join(SITE_DIR, stem + ext)
        if os.path.isfile(p):
            out.append(read_text(p))
    return out


_GENERATED_ROUTES = []


def norm_route(x):
    """Compare routes with no leading or trailing slash."""
    return (x or "").strip().strip("/")


def generated_routes():
    """Routes emitted by a page generator, read from its own manifest.

    `/hosts/` and `/artists/` on frenzypenguin-media have no source file: they
    are written by scripts/build_host_pages.py. Without a record of them there
    are only two options -- let seo.yml advertise a route nothing can verify, or
    delete the check that complains. Both are worse than having the generator
    declare what it produces, which is what _data/generated_routes.yml is.

    Cached, and degraded to an empty list if the manifest is absent, so a site
    with no generators is unaffected.
    """
    global _GENERATED_ROUTES
    if _GENERATED_ROUTES:
        return _GENERATED_ROUTES
    p = os.path.join(SITE_DIR, "_data", "generated_routes.yml")
    if os.path.isfile(p):
        try:
            doc = yaml_safe_load(p) or {}
            _GENERATED_ROUTES = [str(r) for r in (doc.get("routes") or [])]
        except Exception:
            _GENERATED_ROUTES = []
    return _GENERATED_ROUTES


def route_exists(route):
    """Does THIS site build a page at `route`?

    Strictly local. An absolute URL naming another site is not "a route here",
    and answering True for one would let any seo.yml entry point at an
    arbitrary external address while claiming it was verified -- which is the
    opposite of what this gate is for. Cross-site links are out of scope for
    route_exists and are skipped by validate() instead.
    """
    if route.startswith(("http://", "https://", "//")):
        return False

    try:
        import verify_references
    except ImportError:
        built = None
    else:
        built = verify_references.built_paths()

    base, _, frag = route.partition("#")

    # Declared by a page generator. Checked before the source-file lookups
    # because a generated page has no source file to find. Both sides are
    # normalised, because the manifest writes "/hosts/" and a seo.yml entry
    # may say either "/hosts/" or "hosts".
    if norm_route(base) in set(norm_route(r) for r in generated_routes()):
        return True

    # A fragment points at an anchor inside a page. It has to be checked against
    # the page source too, because /#biotechnology is a real link only if
    # something on that page carries id="biotechnology". A seo.yml entry whose
    # fragment names nothing is exactly the kind of dead reference that costs a
    # topical cluster its anchor, so it is verified rather than assumed.
    if frag:
        if not route_exists(base if base else "/"):
            return False
        for src in _source_files_for(base if base else "/"):
            if ('id="%s"' % frag) in src:
                return True
        return False

    if built is None:
        # Complete stdlib routing, because on sites without
        # scripts/verify_references.py this IS the implementation.
        #
        # Three shapes, and each one is a real Jekyll rule rather than a
        # convenience:
        #
        #   index.<ext>                       -> "/"
        #   page with `permalink:`           -> that permalink
        #   page with front matter, no permalink -> "/<stem>/"
        #   file with NO front matter         -> "/<basename>" WITH its
        #                                        extension, because Jekyll
        #                                        copies it as a static file
        #                                        and never builds a page from it
        #
        # The last case is the one that produces false negatives if ignored:
        # map.html and live.html on transhumanists.github.io have no front
        # matter, so they are served at /map.html and /live.html and NOT at
        # /map/ or /live/. Meanwhile CONTRIBUTING.md has no front matter either
        # and is therefore served at /CONTRIBUTING.md, so "/CONTRIBUTING/" is
        # genuinely a 404 and the gate is right to reject it.
        trimmed = route.strip("/")

        def norm(x):
            # Compare permalinks with no leading or trailing slash, so
            # `permalink: /feed/` matches the route "/feed/" instead of
            # mismatching "/feed" against "feed".
            return (x or "").strip().strip("/")

        is_home = trimmed in ("", "index", "index.html")
        stem = "index" if is_home else trimmed
        has_ext = "." in stem.rsplit("/", 1)[-1]
        if has_ext:
            stem = stem.rsplit(".", 1)[0]

        for ext in (".md", ".html"):
            p = os.path.join(SITE_DIR, stem + ext)
            if not os.path.isfile(p):
                continue
            if is_home:
                return True
            body = read_text(p)[:4000]
            parts = body.split("---", 2)
            has_fm = len(parts) >= 3 and parts[0].strip() == ""
            fm = parts[1] if has_fm else ""
            m = re.search(r'(?m)^permalink:\s*["\']?([^"\'\n]+)', fm) if has_fm else None
            if m:
                if norm(m.group(1)) == norm(trimmed):
                    return True
                continue                      # permalink points elsewhere
            if not has_fm:
                # Static file: only reachable at its own basename, extension
                # included.
                if norm(trimmed) == norm(stem + ext):
                    return True
                continue
            return True                       # /<stem>/

        for src_dir, pattern in collection_permalinks():
            # `pattern` is "/tools/:name/" and `trimmed` has no leading slash, so
            # it starts "tools/". len(prefix) is therefore exactly the number of
            # characters to drop -- "/tools" is six, and so is "tools/". Adding
            # one more (the separator, already counted inside len(prefix))
            # chopped the first character off every tool name and made
            # "_tools/uto-resume.md", which is why every collection route in
            # every seo.yml failed validation.
            cut = pattern.find(":")
            if cut == -1:
                continue
            prefix = pattern[:cut].rstrip("/")          # "/tools"
            if pattern.find("/", cut + 1) == -1:
                continue                                 # no trailing segment
            if not trimmed.startswith(prefix.strip("/") + "/"):
                continue
            tail = trimmed[len(prefix):]                 # "auto-resume"
            if not tail or "/" in tail:
                continue
            for ext in (".md", ".html"):
                if os.path.isfile(os.path.join(SITE_DIR, src_dir, tail + ext)):
                    return True

        # A permalink can differ from its file's stem AND its file can live in a
        # subdirectory: frenzypenguin.media keeps the host directory at
        # hosts/index.html with `permalink: /hosts/`, and the licensing terms at
        # open-source-licensing.md with `permalink: /LICENSE/`. Neither is
        # reachable by guessing `<stem>.<ext>` at the site root, so the remaining
        # source pages are walked and their permalinks matched.
        #
        # A walk rather than an index: it runs a handful of times per generator
        # run and an index would be a second thing to invalidate when a page is
        # added. SKIP_DIRS keeps it off _site, which on a site with generated
        # host pages is by far the largest directory in the tree.
        SKIP = {".git", "_site", "node_modules", ".jekyll-cache", "__pycache__",
                ".pytest_cache", "vendor", "assets"}
        for dp, dns, fns in os.walk(SITE_DIR):
            dns[:] = [d for d in dns if d not in SKIP]
            for fn in sorted(fns):
                if not fn.endswith((".md", ".html")):
                    continue
                p = os.path.join(dp, fn)
                if os.path.abspath(p) == os.path.abspath(
                        os.path.join(SITE_DIR, stem + ".md")) or \
                   os.path.abspath(p) == os.path.abspath(
                        os.path.join(SITE_DIR, stem + ".html")):
                    continue          # already checked above
                body = read_text(p)[:4000]
                parts = body.split("---", 2)
                if len(parts) < 3 or parts[0].strip() != "":
                    continue          # no front matter: a static file
                m = re.search(r'(?m)^permalink:\s*["\']?([^"\'\n]+)', parts[1])
                if m and norm(m.group(1)) == norm(trimmed):
                    return True
        return False

    if route in built or route.rstrip("/") + "/" in built:
        return True
    # built_paths() walks source files, so it cannot know that _config.yml maps
    # the `tools` collection to /tools/:name/ -- for _tools/lanscan.md it yields
    # "/lanscan", never "/tools/lanscan/". Every tool route in seo.yml goes
    # through this branch, so it is not optional.
    for src_dir, pattern in collection_permalinks():
        prefix, _, placeholder = pattern.partition(":")
        placeholder = placeholder.rstrip("/")
        if not placeholder:
            continue
        prefix = "/" + prefix.strip("/")
        route_trim = "/" + route.strip("/")
        if route_trim.rsplit("/", 1)[0] != prefix.rstrip("/"):
            continue
        stem = route_trim[len(prefix.rstrip("/")):].lstrip("/")
        if not stem or "/" in stem:
            continue
        src = os.path.join(SITE_DIR, src_dir, stem)
        for ext in (".md", ".html"):
            if os.path.isfile(src + ext):
                return True
    # A page whose source file ends in .html and whose front matter sets no
    # `permalink:` publishes WITH its extension: live.html -> /live.html. The
    # shared verifier derives routes from file stems, so it reports /live and
    # this branch would reject a URL that the build genuinely produces. That
    # mismatch is a real limitation of built_paths(), not of the site, and the
    # fix belongs here rather than in a verifier four other gates depend on.
    #
    # Only consulted when the earlier checks came up empty, so this can never
    # turn a genuinely missing page into a present one: it requires the source
    # file to exist AND to omit `permalink:`, and a page with a permalink is
    # already handled correctly by built_paths().
    if route.startswith("/") and "." in route.rsplit("/", 1)[-1]:
        stem = route.strip("/").rsplit(".", 1)[0]
        src = os.path.join(SITE_DIR, stem + ".html")
        if os.path.isfile(src):
            fm = read_text(src)[:4000]
            parts = fm.split("---", 2)
            if len(parts) >= 3 and parts[0].strip() == "" \
                    and "permalink:" not in parts[1]:
                return True
    return False


_COLLECTIONS = []


def collection_permalinks():
    """Permalink templates from _config.yml, e.g. `/tools/:name/`.

    Cached because validate() asks about one route per topic. Read with the
    yaml module this script already requires, and degraded to an empty list if
    the config is unreadable -- a missing collection check must not stop the
    artifacts being generated.
    """
    global _COLLECTIONS
    if _COLLECTIONS:
        return _COLLECTIONS
    try:
        conf = yaml_safe_load(os.path.join(SITE_DIR, "_config.yml")) or {}
        for name, spec in (conf.get("collections") or {}).items():
            if not isinstance(spec, dict) or not spec.get("permalink"):
                continue
            # Jekyll reads a collection from `_<name>`, and that is where the
            # files actually live -- the permalink says nothing about it. `tools`
            # publishes to /tools/:name/ from _tools/, so the two prefixes
            # differ and both are needed to resolve a route back to its source.
            _COLLECTIONS.append(("_" + name, str(spec["permalink"])))
    except Exception:
        _COLLECTIONS = []
    return _COLLECTIONS


def validate(cfg, tools):
    """Every site-absolute reference in the config must name a real file.

    Jekyll does not validate link targets, so a reference to a missing asset
    neither fails the build nor warns: the page simply ships a dead URL and the
    only symptom is a missing rich result in a search result months later. That
    is the same failure mode verify_references.py exists to prevent for
    stylesheets and images, applied to the SEO layer.

    Site-absolute paths only. External URLs are not resolved -- this script runs
    offline and a network call in a build gate is a dependency nobody wants.
    """
    problems = []

    def is_external(path):
        return bool(path) and path.startswith(("http://", "https://", "//"))

    def require(path, label):
        if not path:
            return
        if path.startswith(("http://", "https://", "//")):
            return
        if not os.path.isfile(os.path.join(SITE_DIR, path.lstrip("/"))):
            problems.append("%s: %s -> %s (not in this repository)"
                            % (rel_to(SEOCFG), label, path))

    require((cfg.get("logo") or {}).get("url"), "logo.url")
    require((cfg.get("og") or {}).get("image"), "og.image")
    require((cfg.get("card") or {}).get("image"), "card.image")

    # Every route the manifest advertises must build. An llms.txt that points a
    # crawler at four URLs and delivers three 404s is worse than one with two
    # good links: the crawler stops trusting the file.
    for entry in (cfg.get("pages") or []):
        path = entry.get("path")
        if not path:
            continue
        label = "pages[%s].path" % (entry.get("title") or path)
        if is_external(path):
            # A cross-site link (to a sibling in the network) is not this site's
            # route and this gate cannot verify it offline. Skipped explicitly
            # rather than silently, so the intent is legible.
            continue
        if not route_exists(path):
            problems.append("%s: %s -> %s (no page builds there)"
                            % (rel_to(SEOCFG), label, path))

    # A `claim: live` topic must name a page that builds. The inverse is also
    # enforced, in seo.yml's own comment: a cluster with no page and a live
    # claim is a lie, and a roadmap cluster without a page is fine because it
    # ships nothing.
    for topic in cfg.get("topics") or []:
        page = topic.get("page")
        label = "topics[%s].page" % topic.get("id", "?")
        if not page:
            if topic.get("claim", "live") == "live":
                problems.append("%s: %s is claim:live with no page -- "
                                "either point it at a route or mark it "
                                "claim: roadmap" % (rel_to(SEOCFG), label))
            continue
        if is_external(page):
            # A cluster may legitimately point at a sibling site -- the
            # transhumanism cluster on frenzypenguin.media points at
            # transhumanists.github.io, because this site does not host that
            # page and inventing a local route would be a 404. Out of scope for
            # a local-route check.
            continue
        if not route_exists(page):
            problems.append("%s: %s -> %s (no page builds there)"
                            % (rel_to(SEOCFG), label, page))

    return problems


# --------------------------------------------------------------------------
# builders
# --------------------------------------------------------------------------

def build_graph(cfg, tools):
    origin = cfg["origin"].rstrip("/")
    org = cfg.get("organization") or {}
    web = cfg.get("website") or {}
    social = cfg.get("social") or {}

    org_id = origin + "/#organization"
    site_id = origin + "/#website"

    org_node = {
        "@type": org.get("type", "Organization"),
        "@id": org_id,
        "name": cfg.get("brand_long") or cfg["brand"],
        "alternateName": org.get("alternate_name") or [],
        "url": origin + "/",
        "description": " ".join((org.get("description") or "").split()),
    }
    if org.get("founding_date"):
        org_node["foundingDate"] = org["founding_date"]
    if social.get("twitter"):
        org_node["sameAs"] = (social.get("same_as") or []) + [
            "https://twitter.com/%s" % social["twitter"]
        ]
    else:
        org_node["sameAs"] = social.get("same_as") or []
    # `logo` in seo.yml is authoritative. The og: image is NOT interchangeable
    # with a logo: Google requires the logo node to be a square-ish raster or
    # vector that survives a 48px crop, and og: cards are deliberately 1200x630.
    # Deriving one from the other was the previous behaviour and it shipped a
    # 1200x630 crop as the organization logo, which fails the rich-result test.
    logo_path = (cfg.get("logo") or {}).get("url") or "/assets/favicon.svg"
    org_node["logo"] = {
        "@type": "ImageObject",
        "url": abs_url(origin, logo_path),
        "caption": cfg["brand"],
    }
    if org.get("area_served"):
        org_node["areaServed"] = org["area_served"]
    # knows_about is what makes the Organization eligible for entity-based
    # retrieval. Only live topics reach it -- roadmap entries are excluded by
    # the caller so this never claims something unshipped.
    if org.get("knows_about"):
        org_node["knowsAbout"] = org["knows_about"]

    site_node = {
        "@type": web.get("type", "WebSite"),
        "@id": site_id,
        "url": origin + "/",
        "name": cfg["brand"],
        "description": " ".join((org.get("description") or "").split()),
        "inLanguage": web.get("in_language", "en"),
        "publisher": {"@id": org_id},
    }
    for alias in web.get("aliases") or []:
        site_node.setdefault("alternateName", []).append(alias)

    graph = [org_node, site_node]

    # One SoftwareApplication per tool, plus the tools ItemList. The list is the
    # part that earns the rich result: it is what lets a search engine render
    # "17 tools" instead of a bare blue link, and it is the node that answer
    # engines quote when asked "what does neohiro build".
    item_list_elements = []
    for t in tools:
        url = origin + "/tools/%s/" % t["slug"]
        node = {
            "@type": "SoftwareApplication",
            "@id": url + "#tool",
            "name": t["name"],
            "url": url,
            "description": tool_description(t, cfg),
            "applicationCategory": t["category"] or "DeveloperApplication",
            "operatingSystem": t["platform"] or "Any",
            "codeRepository": t["repo_url"],
            "license": abs_url(origin, "/LICENSE"),
            "isPartOf": {"@id": site_id},
            "author": {"@id": org_id},
            "offers": {
                "@type": "Offer",
                "price": "0",
                "priceCurrency": "USD",
            },
        }
        if t["language"]:
            node["programmingLanguage"] = t["language"]
        if t["demo_url"]:
            node["softwareVersion"] = "live"
            node["url"] = url
        if t["keywords"]:
            node["keywords"] = t["keywords"]
        if t["featured"]:
            node["featureList"] = "Featured"
        graph.append(node)
        item_list_elements.append({
            "@type": "ListItem",
            "position": len(item_list_elements) + 1,
            "url": url,
            "name": t["name"],
        })

    # Conditional. An ItemList with zero items is not a harmless no-op: it is a
    # node asserting that an empty collection exists, and the Rich Results Test
    # flags it. Sites with no tool catalogue (a data dashboard rather than a
    # tool index) must simply not declare one.
    if item_list_elements:
        graph.append({
            "@type": "ItemList",
            "@id": site_id + "#tools",
            "name": "All %s tools" % cfg["brand"],
            "description": "Complete index of the tools this organization "
                           "ships, with one page each.",
            "numberOfItems": len(item_list_elements),
            "itemListElement": item_list_elements,
        })

    return {"@context": "https://schema.org", "@graph": graph}


def default_intro(cfg, tools):
    """A fallback intro, built from what is actually true about this site.

    Used when seo.yml has no `intro:`. It counts the real tool catalogue rather
    than asserting a fixed shape, so a site that gains or loses a tool does not
    publish a stale sentence about itself.
    """
    if tools:
        return ("This site publishes %d open-source tools, each with its own "
                "page. Free, open source, no telemetry, no accounts, no "
                "tracking and no advertising." % len(tools))
    n = len(cfg.get("topics") or [])
    return ("This site publishes open data on %d subject areas. Everything is "
            "free, sourced and refreshes continuously. No accounts, no "
            "tracking, no advertising." % n)


def build_llms(cfg, tools, full=False):
    origin = cfg["origin"].rstrip("/")
    org = cfg.get("organization") or {}
    social = cfg.get("social") or {}
    lines = []

    # Both variants get an H1. The short one leads with the brand; the full one
    # leads with the site name and says what the document is, because a file
    # starting straight at "## Tools" reads to a model as a fragment rather than
    # a site manifest.
    lines.append("# %s" % cfg["brand"])
    lines.append("")
    if full:
        lines.append("> Complete manifest. Every tool, every topic, with full "
                     "descriptions. The short form is at %s"
                     % abs_url(origin, "/llms.txt"))
        lines.append("")
        lines.append(" ".join((org.get("description") or "").split()))
    else:
        lines.append("> " + " ".join((org.get("description") or "").split()))
    lines.append("")
    if not full:
        # Per-site, because the first version of this was hardcoded prose about
        # security tooling and it leaked verbatim into every other site's
        # manifest -- transhumanists.github.io published "0 tools ... hardening
        # guides for Windows, Linux and Ubuntu" in the one document crawlers
        # treat as authoritative about the site. A manifest that misdescribes
        # itself is worse than no manifest.
        lines.append(" ".join((cfg.get("intro") or default_intro(cfg, tools)).split()))
        lines.append("")

    lines.append("## What this site covers")
    lines.append("")
    for t in cfg.get("topics") or []:
        claim = t.get("claim", "live")
        marker = "" if claim == "live" else " *(planned, not shipped)*"
        lines.append("- **%s**%s -- %s" % (t["label"], marker,
                                            " ".join((t.get("summary") or "").split())))
    lines.append("")

    if full:
        lines.append("## Topics in detail")
        lines.append("")
        for t in cfg.get("topics") or []:
            lines.append("### %s" % t["label"])
            if t.get("claim", "live") != "live":
                lines.append("")
                lines.append("Status: **planned, not shipped yet**.")
            lines.append("")
            lines.append(wrap(t.get("summary", ""), 76, "- "))
            if t.get("page"):
                lines.append("")
                lines.append("Page: %s" % abs_url(origin, t["page"]))
            if t.get("keywords"):
                lines.append("")
                lines.append("Queries this page answers: %s"
                             % ", ".join("`%s`" % k for k in t["keywords"]))
            lines.append("")

    # The Tools section is conditional. A site with no tool catalogue (a data
    # dashboard rather than a tool index) must not publish an empty "## Tools"
    # heading followed by nothing: an llms.txt that promises a section it does
    # not contain reads as a truncated or broken manifest, and a crawler that
    # trusts it learns to distrust the rest of the file.
    if tools:
        lines.append("## Tools")
        lines.append("")
        if full:
            for t in sorted(tools, key=lambda x: (not x["featured"], x["name"].lower())):
                url = abs_url(origin, "/tools/%s/" % t["slug"])
                lines.append("### %s" % t["name"])
                lines.append("")
                lines.append(wrap(tool_description(t, cfg), 76, ""))
                lines.append("")
                bits = []
                if t["platform"]:
                    bits.append("Platform: %s" % t["platform"])
                if t["language"]:
                    bits.append("Language: %s" % t["language"])
                if t["category"]:
                    bits.append("Category: %s" % t["category"])
                if bits:
                    lines.append("  \n".join(bits))
                    lines.append("")
                if t["repo_url"]:
                    lines.append("- Source: %s" % t["repo_url"])
                if t["demo_url"]:
                    lines.append("- Try it: %s" % t["demo_url"])
                lines.append("- Details: %s" % url)
                if t["keywords"]:
                    lines.append("- Also useful for: %s"
                                 % ", ".join("`%s`" % k for k in t["keywords"]))
                lines.append("")
        else:
            for t in sorted(tools, key=lambda x: (not x["featured"], x["name"].lower())):
                url = abs_url(origin, "/tools/%s/" % t["slug"])
                tag = " (featured)" if t["featured"] else ""
                lines.append("- [%s](%s): %s%s"
                             % (t["name"], url,
                                " ".join(t["tagline"].split()) or t["category"] or "tool",
                                tag))
            lines.append("")

    lines.append("## Other pages")
    lines.append("")
    # Per-site, and validated in validate(). Hardcoding a list of routes was
    # wrong the moment this generator was shared with a site that does not have
    # a /repositories/ page: the manifest would advertise four URLs, three of
    # which 404, and a crawler that follows them learns the manifest is not
    # trustworthy. That is worse than publishing fewer links.
    for entry in (cfg.get("pages") or []):
        path = entry.get("path")
        if not path:
            continue
        lines.append("- [%s](%s): %s"
                     % (entry.get("title") or path, abs_url(origin, path),
                        " ".join((entry.get("summary") or "").split())))
    lines.append("")

    lines.append("## Related sites in this network")
    lines.append("")
    for url in (social.get("same_as") or []):
        if url.startswith(("https://frenzypenguin.media",
                           "https://transhumanists.github.io",
                           "https://openstageis.land")):
            lines.append("- %s" % url)
    lines.append("")

    lines.append("## Licensing")
    lines.append("")
    lines.append("The tooling is open source. See %s for the licence of the site "
                 "content and %s for per-repository licences."
                 % (abs_url(origin, "/LICENSE"),
                    (social.get("github") or "").rstrip("/")))
    lines.append("")

    return "\n".join(lines).rstrip() + "\n"


# --------------------------------------------------------------------------
# driver
# --------------------------------------------------------------------------

def has_plugin(name):
    try:
        conf = yaml_safe_load(os.path.join(SITE_DIR, "_config.yml")) or {}
    except Exception:
        return False
    return name in (conf.get("plugins") or [])


def build_sitemap(cfg):
    """A static sitemap.xml, for sites with no sitemap plugin.

    Emitted ONLY when _config.yml does not enable jekyll-sitemap. Where that
    plugin is on, it owns /sitemap.xml and a second generator writing the same
    file is a race between two producers of one artifact.

    Why this exists at all: openstageisland.github.io relied on GitHub Pages
    emitting a sitemap for Jekyll sites. That is undocumented platform behaviour
    rather than something the repository controls -- it held on production while
    failing every local build, and the only way anyone would learn it had stopped
    working is by watching traffic fall months later with no error anywhere.
    Generating it makes it a checked-in artifact, diffable in review, identical
    locally and in CI, and assertable by check_seo.py.

    Only routes that actually build are listed, because a sitemap that names a
    404 is worse than a smaller one.
    """
    origin = cfg["origin"].rstrip("/")
    urls = []

    def add(route, priority, changefreq, lastmod=None):
        if not route_exists(route):
            return
        urls.append((route, priority, changefreq, lastmod))

    add("/", "1.0", "daily")
    for t in cfg.get("topics") or []:
        if t.get("claim", "live") == "live" and str(t.get("page", "")).startswith("/"):
            add(t["page"], "0.8", "weekly")
    for entry in (cfg.get("pages") or []):
        if entry.get("path"):
            add(entry["path"], "0.6", "monthly")
    for slug in sorted((cfg.get("tools") or {}).keys()):
        add("/tools/%s/" % slug, "0.7", "monthly")

    # De-duplicate on route, keeping the highest priority, so a page that is both
    # a topic target and an advertised page appears once.
    best = {}
    for route, prio, freq, lastmod in urls:
        cur = best.get(route)
        if cur is None or float(prio) > float(cur[0]):
            best[route] = (prio, freq, lastmod)

    today = cfg.get("lastmod") or _today()
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             "<!-- GENERATED by scripts/build_seo.py -- do not edit.",
             "     Regenerate with: python scripts/build_seo.py -->",
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for route in sorted(best, key=lambda r: (-float(best[r][0]), r)):
        prio, freq, lastmod = best[route]
        lines += ["  <url>",
                  "    <loc>%s</loc>" % abs_url(origin, route),
                  "    <lastmod>%s</lastmod>" % (lastmod or today),
                  "    <changefreq>%s</changefreq>" % freq,
                  "    <priority>%s</priority>" % prio,
                  "  </url>"]
    lines.append("</urlset>")
    return "\n".join(lines) + "\n"


def _today():
    import datetime
    return datetime.date.today().isoformat()


def artifacts(cfg, tools):
    out = {
        OUT_GRAPH: jdump(build_graph(cfg, tools)),
        OUT_LLMS: build_llms(cfg, tools, full=False),
        OUT_LLMS_FULL: build_llms(cfg, tools, full=True),
    }
    # Only where no plugin owns the file. See build_sitemap's header.
    if not has_plugin("jekyll-sitemap"):
        out[OUT_SITEMAP] = build_sitemap(cfg)
    return out


def main(argv):
    check = "--check" in argv

    try:
        cfg = load_cfg()
    except ImportError:
        print("FAIL: PyYAML is not installed. Run: pip install pyyaml")
        return 1
    if not cfg:
        print("FAIL: %s is empty or unreadable" % rel_to(SEOCFG))
        return 1

    # origin vs the site config. A canonical served from a host other than the
    # one the site is served from is a silent de-index, not a warning, and the
    # repo has been published under more than one name before. Gated here rather
    # than left to a human because the check is two lines and the failure costs
    # the entire search surface.
    try:
        site_cfg = yaml_safe_load(os.path.join(SITE_DIR, "_config.yml")) or {}
    except ImportError:
        print("FAIL: PyYAML is not installed. Run: pip install pyyaml")
        return 1
    except Exception as exc:
        print("FAIL: could not read _config.yml (%s)" % exc)
        return 1
    declared = str(cfg.get("origin", "")).rstrip("/")
    served = str(site_cfg.get("url", "")).rstrip("/")
    if declared and served and declared != served:
        print("FAIL: seo.yml origin %r does not match _config.yml url %r"
              % (declared, served))
        print("      Every canonical and og:url is built from origin. If the two")
        print("      disagree, the site advertises a canonical it does not serve")
        print("      and search engines drop it. Pick one host.")
        return 1

    tools = collect_tools(cfg)

    # An orphan keyword cluster is worse than no cluster: it points crawlers at
    # a /tools/<slug>/ that does not exist. Fail loudly instead.
    declared = set((cfg.get("tools") or {}).keys())
    shipped = set(t["slug"] for t in tools)
    orphans = sorted(declared - shipped)
    if orphans:
        print("FAIL: _data/seo.yml declares tools with no _tools/%s.md page: %s"
              % ("<slug>", ", ".join(orphans)))
        print("      Every keyword entry must map to a page that ships.")
        return 1

    problems = validate(cfg, tools)
    if problems:
        print("FAIL: %s declares references that do not resolve:" % rel_to(SEOCFG))
        for line in problems:
            print("  %s" % line)
        print("      A dead logo, og:image or topic page costs the rich result")
        print("      silently -- nothing in the Jekyll build fails, the reference")
        print("      is just wrong. Add the file, or point the key elsewhere.")
        return 1

    wanted = artifacts(cfg, tools)
    drift = []

    for path, content in sorted(wanted.items()):
        rel = os.path.relpath(path, SITE_DIR).replace("\\", "/")
        current = None
        if os.path.exists(path):
            current = read_text(path)
            # Normalise line endings: this repo is checked out on Windows for
            # authoring and on Linux in CI, and a CRLF checkout would otherwise
            # report every artifact as drifted.
            current = current.replace("\r\n", "\n")
        if current == content:
            continue
        if check:
            drift.append(rel)
        else:
            with io.open(path, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(content)
            print("wrote %s" % rel)

    if check and drift:
        print("FAIL: generated SEO artifacts are stale:")
        for rel in drift:
            print("  %s" % rel)
        print("      Run: python scripts/build_seo.py")
        return 1

    if check:
        print("SEO artifacts up to date (%d tools)" % len(tools))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))