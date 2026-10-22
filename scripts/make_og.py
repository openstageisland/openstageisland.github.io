#!/usr/bin/env python3
"""make_og.py -- render the Open Graph / Twitter card images.

Every page on this site used to ship without an og:image, so a link pasted into
Slack, Discord, Bluesky or X rendered as a bare URL: no title, no picture, no
description. That is the single largest piece of free distribution a site like
this can have, and it costs nothing but a PNG.

Output:
  assets/og/<brand>.png        the site card, 1200x630
  assets/og/tools/<slug>.png   one card per tool, same dimensions

1200x630 is the Open Graph default and the largest size Facebook, X, Bluesky,
LinkedIn and Mastodon all render without downscaling. Anything smaller is
letterboxed on one axis or the other.

Why these are committed rather than built in CI: the renderer needs a font, and
the font available differs between the authoring machine and the Linux runner.
Rendering in CI would produce a different PNG from the same input and the drift
check would fail on every run for a reason that has nothing to do with the
content. So the images are generated once, committed, and verified for SIZE and
PRESENCE by check_seo.py -- never byte-compared.

Usage:
    python scripts/make_og.py            # (re)render every card
    python scripts/make_og.py --one NAME # render a single card by slug

Requires Pillow:  pip install pillow
"""

from __future__ import print_function

import io
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SITE_DIR = os.path.dirname(SCRIPT_DIR)

W, H = 1200, 630

# Palette lifted from the site's own CSS custom properties (assets/css/
# site-tokens.css) so a card and the page it links to are recognisably the same
# product. Overridable per site from _data/seo.yml (`card.palette`), because
# this script is shared by four sites with four different palettes and a
# hard-coded colour would render the transhumanists card in neohiro's purple.
#
# Parsed out of the stylesheet? No, deliberately: a generator that depends on a
# regex over a CSS file is a generator that breaks when someone reformats that
# file. The values are stated here and in seo.yml, and check_seo.py does not
# verify them against the CSS -- an unverified promise is better than a fragile
# derivation, and a reviewer changing a brand colour should change this file.
PALETTE = {
    "ink": (11, 12, 18),
    "ink_soft": (18, 20, 30),
    "accent": (168, 85, 247),      # --accent, the purple-matrix palette
    "accent_dim": (88, 44, 124),
    "fg": (244, 244, 250),
    "fg_muted": (162, 164, 182),
    "border": (38, 40, 56),
}


def palette_for(cfg):
    """Resolve the palette for this site, from seo.yml if it declares one."""
    out = dict(PALETTE)
    for k, v in ((cfg.get("card") or {}).get("palette") or {}).items():
        if k not in out:
            continue
        try:
            out[k] = tuple(int(x, 16) if isinstance(x, str) else int(x) for x in v)
        except (TypeError, ValueError):
            # A malformed colour must not stop the card rendering; fall back to
            # the default for that one key.
            continue
    return out

# Font search order. First hit wins; the list is tried in order so a machine
# with the display face gets the heavier card.
FONT_CANDIDATES_DISPLAY = [
    "C:/Windows/Fonts/seguibl.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
]
FONT_CANDIDATES_TEXT = [
    "C:/Windows/Fonts/segoeui.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/Library/Fonts/Arial.ttf",
]
FONT_CANDIDATES_MONO = [
    "C:/Windows/Fonts/consola.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/System/Library/Fonts/Menlo.ttc",
    "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
]


def load_font(candidates, size):
    from PIL import ImageFont
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    raise SystemExit(
        "make_og.py: no usable font found.\n"
        "Tried:\n  " + "\n  ".join(candidates) +
        "\nOn Linux: apt-get install fonts-dejavu-core fonts-liberation"
    )


def text_width(draw, text, font):
    try:
        return draw.textlength(text, font=font)
    except AttributeError:
        # Pillow < 8 has no textlength; this is a fallback, not the path taken.
        return draw.textsize(text, font=font)[0]


def wrap_text(draw, text, font, max_w):
    """Greedy wrap on measured width.

    Measured, not counted: character counts assume a monospace average that no
    proportional face actually has, so a counted wrap overruns the safe area on
    the words that matter most (usually the tool name).
    """
    words, lines, cur = (text or "").split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if cur and text_width(draw, trial, font) > max_w:
            lines.append(cur)
            cur = w
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines


def base_canvas(pal):
    from PIL import Image, ImageDraw
    ink, ink_soft = pal["ink"], pal["ink_soft"]
    accent, accent_dim = pal["accent"], pal["accent_dim"]
    fg, fg_muted, border = pal["fg"], pal["fg_muted"], pal["border"]
    img = Image.new("RGB", (W, H), ink)
    d = ImageDraw.Draw(img)

    # Vertical gradient. 630 rows in pure Python is fine -- it runs once, at
    # authoring time, and never in CI.
    for y in range(H):
        t = y / float(H - 1)
        d.line(
            [(0, y), (W, y)],
            fill=tuple(int(ink[i] + (ink_soft[i] - ink[i]) * t) for i in range(3)),
        )

    # A soft accent bloom, upper-left, so the card has depth without an
    # external asset or a filter. Kept deliberately weak: the first pass used
    # a 70/255 alpha at full strength and the subtitle text sat on a near-white
    # purple, which is the worst possible contrast for the one element that has
    # to be readable at thumbnail size in a feed.
    #
    # Computed analytically at 1/8 scale and upscaled bicubically. The first
    # pass drew concentric ellipses at a 6px step, and the step edges survive
    # the upscale as visible concentric rings across the whole upper-left --
    # banding is exactly the artefact a low-frequency gradient cannot hide.
    # Evaluating a smooth falloff on a 150x79 grid and letting the resampler
    # interpolate is both smoother and roughly 40x faster than per-pixel.
    from PIL import Image as _Image
    gw, gh = W // 8, H // 8
    small = _Image.new("RGB", (gw, gh))
    px = small.load()
    cx, cy = -4.0, -2.0           # centre, in grid units, just off the corner
    radius = 105.0
    # Peak mix is bounded by a contrast requirement, not by taste: the subtitle
    # starts at (64, ~250) and must stay on a dark ground. At this radius the
    # text sits around a 0.16 mix, which keeps white above 12:1 on it. Raising
    # peak much past 0.4 drops the left half of the subtitle into a light
    # lavender at exactly the size a feed renders it.
    peak = 0.34
    for gy in range(gh):
        for gx in range(gw):
            dx, dy = gx - cx, gy - cy
            # Normalised, slightly super-linear falloff: a linear ramp reads as
            # a hard-edged disc once it is stretched across the canvas.
            dist = ((dx * dx + dy * dy) ** 0.5) / radius
            t = 0.0 if dist >= 1.0 else (1.0 - dist) ** 1.8
            px[gx, gy] = tuple(
                int(ink_soft[i] + (accent[i] - ink_soft[i]) * t * peak)
                for i in range(3)
            )
    glow = small.resize((W, H), _Image.BICUBIC)

    from PIL import ImageChops
    img = ImageChops.screen(img, glow)

    # Faint scanlines, echoing the site's own `decor-scanlines` body class.
    # Applied as a MULTIPLY by a near-white layer rather than by drawing black
    # lines: drawing black darkens by a fixed absolute amount, so it punches
    # visible stripes through the bright part of the glow and disappears in the
    # dark part. Multiplying by 0.87 darkens by the same 13% everywhere, which
    # is what "faint" has to mean over a gradient. The first pass drew solid
    # black every fourth row -- 25% of the card at 100% -- and the subtitle
    # became harder to read than the card without it.
    stripe = _Image.new("RGB", (W, H), (255, 255, 255))
    sd = ImageDraw.Draw(stripe)
    for y in range(0, H, 6):
        sd.line([(0, y), (W, y)], fill=(222, 222, 222))
    img = ImageChops.multiply(img, stripe)

    return img, ImageDraw.Draw(img)


def accent_rule(draw, pal, x, y, w, h=5):
    draw.rectangle([x, y, x + w, y + h], fill=pal["accent"])


def draw_footer(draw, pal, brand, domain, mono):
    """The bottom strip: brand, domain, and the promise that differentiates."""
    draw.line([(64, H - 92), (W - 64, H - 92)], fill=pal["border"], width=2)
    draw.text((64, H - 68), brand, font=mono, fill=pal["accent"])
    w = text_width(draw, domain, mono)
    draw.text((W - 64 - w, H - 68), domain, font=mono, fill=pal["fg_muted"])


def render_site_card(cfg, pal, out_path):
    from PIL import Image
    accent, accent_dim = pal["accent"], pal["accent_dim"]
    fg, fg_muted = pal["fg"], pal["fg_muted"]
    img, d = base_canvas(pal)

    display = load_font(FONT_CANDIDATES_DISPLAY, 84)
    sub = load_font(FONT_CANDIDATES_TEXT, 34)
    mono = load_font(FONT_CANDIDATES_MONO, 26)

    card = cfg.get("card") or {}
    brand = cfg["brand"]

    # Layout is bounded, not flowed. The first pass flowed top-to-bottom and a
    # three-line subtitle pushed the chips straight through the footer rule, so
    # the subtitle is clipped to its zone and the chips are anchored to the
    # bottom and trimmed to whatever is left. A card that crops cleanly beats a
    # card that silently overlaps.
    RULE_Y = H - 92
    TOP = 130
    SAFE_L, SAFE_R = 64, W - 64

    accent_rule(d, pal, SAFE_L, 92, 96)

    d.text((SAFE_L, TOP), card.get("title") or brand, font=display, fill=fg)

    y = TOP + 108
    subtitle = " ".join((card.get("subtitle") or "").split())
    lines = wrap_text(d, subtitle, sub, SAFE_R - SAFE_L)
    for ln in lines[:2]:
        if y + 46 > RULE_Y - 70:
            break
        d.text((SAFE_L, y), ln, font=sub, fill=fg_muted)
        y += 46

    # Chips, bottom-anchored above the rule, at most three.
    topics = [t["label"] for t in (cfg.get("topics") or [])
              if t.get("claim", "live") == "live"]
    chip_h, chip_gap = 44, 14
    cy = RULE_Y - 28 - chip_h
    drawn = 0
    for label in topics:
        w = text_width(d, label, mono)
        if SAFE_L + w + 40 > SAFE_R:
            continue          # will not fit horizontally; skip, never crop
        if cy < y + 12:
            break             # would collide with the subtitle; stop
        d.rounded_rectangle(
            [SAFE_L, cy, SAFE_L + w + 40, cy + chip_h], radius=22, fill=accent_dim
        )
        d.text((SAFE_L + 20, cy + 9), label, font=mono, fill=fg)
        cy -= chip_h + chip_gap
        drawn += 1
        if drawn >= 3:
            break

    draw_footer(d, pal, brand, cfg["origin"].replace("https://", "").rstrip("/"), mono)

    img.save(out_path, "PNG", optimize=True)
    return out_path


def render_tool_card(cfg, pal, tool, out_path):
    from PIL import Image
    accent, accent_dim = pal["accent"], pal["accent_dim"]
    fg, fg_muted = pal["fg"], pal["fg_muted"]
    img, d = base_canvas(pal)

    display = load_font(FONT_CANDIDATES_DISPLAY, 72)
    sub = load_font(FONT_CANDIDATES_TEXT, 32)
    mono = load_font(FONT_CANDIDATES_MONO, 24)

    RULE_Y = H - 92
    SAFE_L, SAFE_R = 64, W - 64

    accent_rule(d, pal, SAFE_L, 88, 72, 5)

    eyebrow = "  ".join(
        b for b in (tool.get("category"), tool.get("platform")) if b
    )
    d.text((SAFE_L, 116), eyebrow[:78], font=mono, fill=accent)

    # Same bounded layout as the site card: the name gets up to two lines, the
    # tagline fills whatever vertical room is left above the rule.
    y = 164
    for ln in wrap_text(d, tool["name"], display, SAFE_R - SAFE_L)[:2]:
        d.text((SAFE_L, y), ln, font=display, fill=fg)
        y += 82

    y += 18
    tagline = " ".join((tool.get("tagline") or "").split())
    for ln in wrap_text(d, tagline, sub, SAFE_R - SAFE_L):
        if y + 42 > RULE_Y - 24:
            break
        d.text((SAFE_L, y), ln, font=sub, fill=fg_muted)
        y += 42

    # The tool's own query terms, bottom-anchored above the rule. Short taglines
    # otherwise leave half the card empty, and these strings are already the
    # ones in this node's `keywords` field -- so putting them here costs
    # nothing and makes the image useful on its own when a feed renders the
    # picture without the link text.
    kws = [k for k in (tool.get("keywords") or [])[:3]]
    if kws:
        chip_h, chip_gap = 40, 12
        cy = RULE_Y - 26 - chip_h
        x = SAFE_L
        for kw in kws:
            label = " ".join(kw.split())
            w = text_width(d, label, mono)
            if x + w + 36 > SAFE_R:
                break                      # never let a chip run off the edge
            if cy < y + 10:
                break                      # would collide with the tagline
            d.rounded_rectangle([x, cy, x + w + 36, cy + chip_h],
                                radius=20, fill=accent_dim)
            d.text((x + 18, cy + 8), label, font=mono, fill=fg)
            x += w + 36 + 10

    draw_footer(d, pal, cfg["brand"], cfg["origin"].replace("https://", "").rstrip("/"), mono)

    img.save(out_path, "PNG", optimize=True)
    return out_path


def main(argv):
    try:
        import yaml
    except ImportError:
        raise SystemExit("make_og.py: PyYAML missing. pip install pyyaml")

    sys.path.insert(0, SCRIPT_DIR)
    import build_seo

    cfg = yaml.safe_load(build_seo.read_text(build_seo.SEOCFG))
    tools = build_seo.collect_tools(cfg)
    pal = palette_for(cfg)

    one = None
    if "--one" in argv:
        one = argv[argv.index("--one") + 1]

    og = (cfg.get("og") or {})
    site_out = os.path.join(SITE_DIR, (og.get("image") or "/assets/og/%s.png" % cfg["brand"]).lstrip("/").replace("/", os.sep))

    made = []
    if one is None:
        os.makedirs(os.path.dirname(site_out), exist_ok=True)
        render_site_card(cfg, pal, site_out)
        made.append(os.path.relpath(site_out, SITE_DIR))

    tools_dir = os.path.join(SITE_DIR, "assets", "og", "tools")
    if one is None:
        os.makedirs(tools_dir, exist_ok=True)
    for t in tools:
        if one and t["slug"] != one:
            continue
        # t["slug"] is already the Jekyll URL slug (build_seo.url_slug), which is
        # the same string seo-head.html builds the og:image path from. Keying
        # this off the filename instead is how the cards and the tags end up
        # disagreeing for every tool whose file name is not already lowercase.
        out = os.path.join(tools_dir, t["slug"] + ".png")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        render_tool_card(cfg, pal, t, out)
        made.append(os.path.relpath(out, SITE_DIR).replace("\\", "/"))

    if one and not made:
        raise SystemExit("make_og.py: no tool with slug %r" % one)

    for m in made:
        print("wrote %s" % m)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))