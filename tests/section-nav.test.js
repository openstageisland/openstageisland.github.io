/* Tests for assets/js/section-nav.js — the bottom-bar overshoot-and-settle
 * scroll animation.
 *
 * Run with:  node --test tests/
 * (zero dependencies; uses the Node built-in test runner)
 *
 * section-nav.js is an IIFE with no exports, so each test loads it into a fresh
 * vm context against a minimal DOM stub. The stub models the two things the
 * animation actually depends on:
 *   - getBoundingClientRect().top, which must shift as the page scrolls
 *     (docTop - currentScrollY), otherwise the target could never be derived;
 *   - a requestAnimationFrame queue driven by a fake clock, so a whole
 *     animation can be stepped deterministically instead of by wall time.
 */
"use strict";

const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const SOURCE = fs.readFileSync(
  path.join(__dirname, "..", "assets", "js", "section-nav.js"),
  "utf8"
);

/* ── DOM stub ─────────────────────────────────────────────────────── */

/* Width of the stub's horizontally scrollable chip list. */
const LIST_W = 400;

/**
 * @param {object} opts
 *   sections     map of id -> document offset (px from document top)
 *   viewportH    window.innerHeight
 *   currentY     initial window.pageYOffset
 *   docHeight    total scrollable document height
 *   reduced      prefers-reduced-motion
 *   bar          false to omit the persistent bottom bar
 */
function makeEnv(opts) {
  const sections = opts.sections || {};
  const viewportH = opts.viewportH == null ? 800 : opts.viewportH;
  const docHeight = opts.docHeight == null ? 8000 : opts.docHeight;

  const win = {
    innerHeight: viewportH,
    pageYOffset: opts.currentY || 0,
    /* Pathname of the document under test; opts.path overrides it so a test can
     * pretend to be on a non-guide page. */
    location: { pathname: opts.path || "/", hash: opts.hash || "" },
    focused: null,
    /* Recorded scroll targets, in call order. */
    scrolls: [],
    matchMedia(query) {
      return {
        media: query,
        matches: !!opts.reduced && /reduced-motion/.test(query),
        addEventListener() {},
        removeEventListener() {}
      };
    },
    scrollTo(x, y) {
      win.pageYOffset = y;
      win.scrolls.push(y);
    },
    addEventListener(type, fn) {
      (win._listeners[type] = win._listeners[type] || []).push(fn);
    },
    removeEventListener() {},
    requestAnimationFrame(fn) {
      win._raf.push(fn);
      return win._raf.length;
    },
    cancelAnimationFrame() {},
    _listeners: {},
    _raf: []
  };

  function makeEl(id, docTop) {
    /* Built inside makeEnv so focus() can close over `win` — a module-level
     * free variable here would silently throw and be swallowed by the
     * production focusHeading() try/catch, making the test vacuous. */
    const heading = {
      nodeName: "H2",
      attrs: {},
      hasAttribute(n) { return Object.prototype.hasOwnProperty.call(this.attrs, n); },
      setAttribute(n, v) { this.attrs[n] = v; },
      focus() { win.focused = heading; }
    };
    const el = {
      id,
      docTop,
      offsetHeight: 46,
      getBoundingClientRect() {
        /* Mirrors the real thing: the viewport-relative top shifts as we
         * scroll, which is what targetOffsetFor() reads. */
        return { top: docTop - win.pageYOffset, height: 600, bottom: 0 };
      },
      querySelector() { return heading; },
      getAttribute() { return null; },
      setAttribute(n, v) { el._attrs[n] = v; },
      removeAttribute(n) { delete el._attrs[n]; },
      hasAttribute(n) { return Object.prototype.hasOwnProperty.call(el._attrs, n); },
      _attrs: {},
      _heading: heading
    };
    return el;
  }

  const elements = {};
  Object.keys(sections).forEach((id) => {
    elements[id] = makeEl(id, sections[id]);
  });

  /* Chips live inside a horizontally scrollable list. Their rects are derived
   * from the list's current scrollLeft so the two stay consistent, which is
   * what the production revealChip() measures. */
  const LIST_WIDTH = LIST_W;

  const chips = Object.keys(sections).map((id, i) => {
    const baseLeft = i * 90;
    return {
      id: "chip-" + id,
      getAttribute(n) { return n === "data-section-link" ? id : null; },
      setAttribute(n, v) { this._attrs[n] = v; },
      removeAttribute(n) { delete this._attrs[n]; },
      hasAttribute(n) { return Object.prototype.hasOwnProperty.call(this._attrs, n); },
      getBoundingClientRect() {
        const left = baseLeft - barList.scrollLeft;
        return { left: left, right: left + 80, width: 80, top: 0, bottom: 46 };
      },
      _attrs: {},
      _baseLeft: baseLeft,
      _el: elements[id]
    };
  });

  const barList = {
    scrollLeft: 0,
    clientWidth: LIST_WIDTH,
    getBoundingClientRect() {
      return { left: 0, right: LIST_WIDTH, width: LIST_WIDTH, top: 0, bottom: 46 };
    },
    querySelectorAll() { return chips; }
  };

  const bar = opts.bar === false ? null : {
    offsetHeight: 46,
    querySelectorAll() { return chips; },
    querySelector(sel) { return sel === ".bottom-bar__list" ? barList : null; }
  };

  const docEl = {
    scrollHeight: docHeight,
    offsetHeight: docHeight,
    scrollTop: 0,
    _attrs: {},
    setAttribute(n, v) { docEl._attrs[n] = v; },
    removeAttribute(n) { delete docEl._attrs[n]; },
    hasAttribute(n) { return Object.prototype.hasOwnProperty.call(docEl._attrs, n); }
  };

  const docHandlers = {};

  const document = {
    readyState: "complete",
    documentElement: docEl,
    body: { scrollHeight: docHeight, offsetHeight: docHeight, scrollTop: 0 },
    getElementById(id) { return elements[id] || null; },
    querySelector(sel) {
      if (sel === ".bottom-bar") return bar;
      return null;
    },
    querySelectorAll(sel) {
      if (sel === "a[href^='#']") {
        return Object.keys(elements).map((id) => ({
          getAttribute() { return "#" + id; }
        }));
      }
      if (sel === "[data-guide-section]") {
        return Object.keys(elements).map((id) => elements[id]);
      }
      return [];
    },
    addEventListener(type, fn) {
      (docHandlers[type] = docHandlers[type] || []).push(fn);
    },
    removeEventListener() {}
  };

  /* IntersectionObserver stub: fires once with everything intersecting, which
   * is enough to exercise the current-section marker. */
  class IO {
    constructor(cb, opts) { this.cb = cb; this.opts = opts; IO.last = this; }
    observe(target) { this.targets = this.targets || []; this.targets.push(target); }
    unobserve() {}
    disconnect() {}
    /* Test hook: report the given ids as crossing the band. */
    emit(ids) {
      this.cb(ids.map((id) => ({
        target: elements[id],
        isIntersecting: true,
        boundingClientRect: elements[id].getBoundingClientRect()
      })));
    }
  }

  const env = { win, document, docEl, elements, chips, bar, barList, docHandlers, IO };

  /* Drive the rAF queue with a fake clock. */
  let clock = 0;
  env.step = function step(msPerFrame) {
    const pending = win._raf.splice(0, win._raf.length);
    pending.forEach((fn) => {
      clock += (msPerFrame == null ? 16 : msPerFrame);
      fn(clock);
    });
  };
  env.runToCompletion = function runToCompletion(maxFrames) {
    const limit = maxFrames || 400;
    let n = 0;
    while (win._raf.length && n < limit) {
      env.step(16);
      n += 1;
    }
    if (win._raf.length) throw new Error("animation did not settle");
    return n;
  };

  vm.runInNewContext(SOURCE, {
    window: win,
    document,
    IntersectionObserver: IO,
    requestAnimationFrame: win.requestAnimationFrame,
    cancelAnimationFrame: win.cancelAnimationFrame,
    setTimeout,
    clearTimeout,
    Object,
    Math,
    Date,
    String,
    parseFloat,
    console
  });

  env.nav = win.OSISectionNav;
  return env;
}

/* ── the animation contract ───────────────────────────────────────── */

test("overshoots past the target, then settles exactly on it", () => {
  const env = makeEnv({ sections: { faq: 4000 }, currentY: 0 });
  env.nav.goTo("faq");
  env.runToCompletion();

  const target = 4000 - 12;            /* docTop - TOP_GAP */
  const scrolls = env.win.scrolls;
  assert.ok(scrolls.length > 2, "expected a multi-frame animation");

  /* Phase 1 must sail past the target — that is the whole point. */
  const peak = Math.max.apply(null, scrolls);
  assert.ok(peak > target,
    `expected overshoot above ${target}, peak was ${peak}`);

  /* Phase 2 must come back and land precisely, not near. */
  assert.strictEqual(scrolls[scrolls.length - 1], target,
    "final scroll position must equal the target exactly");
  assert.strictEqual(env.win.pageYOffset, target, "document must rest at the target");
});

test("overshoot is proportional to the viewport, not a fixed pixel count", () => {
  const small = makeEnv({ sections: { faq: 4000 }, viewportH: 600, currentY: 0 });
  small.nav.goTo("faq");
  small.runToCompletion();
  const smallPeak = Math.max.apply(null, small.win.scrolls) - (4000 - 12);

  const large = makeEnv({ sections: { faq: 4000 }, viewportH: 1400, currentY: 0 });
  large.nav.goTo("faq");
  large.runToCompletion();
  const largePeak = Math.max.apply(null, large.win.scrolls) - (4000 - 12);

  assert.ok(largePeak > smallPeak,
    `taller viewport should overshoot further (${largePeak} vs ${smallPeak})`);
  /* 7% of viewport, within a frame of tolerance. */
  assert.ok(Math.abs(smallPeak - 600 * 0.07) <= 2,
    `expected ~7% of 600px, got ${smallPeak}`);
  assert.ok(Math.abs(largePeak - 1400 * 0.07) <= 2,
    `expected ~7% of 1400px, got ${largePeak}`);
});

test("scrolling upward overshoots above the target, then settles", () => {
  const env = makeEnv({ sections: { welcome: 500 }, currentY: 5000 });
  env.nav.goTo("welcome");
  env.runToCompletion();

  const target = 500 - 12;
  const scrolls = env.win.scrolls;
  assert.ok(Math.min.apply(null, scrolls) < target,
    "upward scroll should overshoot above the target");
  assert.strictEqual(scrolls[scrolls.length - 1], target);
});

test("honours prefers-reduced-motion: jumps straight to the target", () => {
  const env = makeEnv({ sections: { faq: 4000 }, currentY: 0, reduced: true });
  env.nav.goTo("faq");
  env.runToCompletion();

  assert.deepStrictEqual(env.win.scrolls, [4000 - 12],
    "reduced motion must be a single instant jump with no overshoot");
});

test("clamps to the end of the document instead of overshooting past it", () => {
  /* Section sits near the bottom, so the overshoot would leave the document. */
  const env = makeEnv({
    sections: { network: 7900 },
    docHeight: 8000,
    viewportH: 800,
    currentY: 0
  });
  env.nav.goTo("network");
  env.runToCompletion();

  const maxScroll = 8000 - 800;
  assert.ok(env.win.pageYOffset <= maxScroll,
    `must not scroll past ${maxScroll}, ended at ${env.win.pageYOffset}`);
  assert.ok(Math.max.apply(null, env.win.scrolls) <= maxScroll,
    "no frame may exceed maxScroll");
  /* And it should still arrive, not stall short of the target. */
  assert.strictEqual(env.win.pageYOffset, maxScroll);
});

test("a near-zero move does not overshoot", () => {
  const env = makeEnv({ sections: { faq: 4000 }, currentY: 3989 });
  env.nav.goTo("faq");
  env.runToCompletion();
  const target = 4000 - 12;
  assert.strictEqual(env.win.pageYOffset, target);
  assert.ok(Math.max.apply(null, env.win.scrolls) <= target + 1,
    "must not overshoot on a sub-pixel move");
});

test("clears data-scroll-anim when the animation finishes", () => {
  const env = makeEnv({ sections: { faq: 4000 }, currentY: 0 });
  assert.strictEqual(env.docEl.hasAttribute("data-scroll-anim"), false);
  env.nav.goTo("faq");
  assert.strictEqual(env.docEl.hasAttribute("data-scroll-anim"), true,
    "attribute must be set while animating, so CSS smooth-scroll stays off");
  env.runToCompletion();
  assert.strictEqual(env.docEl.hasAttribute("data-scroll-anim"), false,
    "attribute must be removed afterwards or CSS scrolling stays broken");
});

test("a user scroll gesture cancels the animation and restores CSS scrolling", () => {
  const env = makeEnv({ sections: { faq: 4000 }, currentY: 0 });
  env.nav.goTo("faq");
  env.step(16);
  env.step(16);
  assert.ok(env.win._raf.length > 0, "animation should still be in flight");
  assert.strictEqual(env.docEl.hasAttribute("data-scroll-anim"), true);

  env.win._listeners.wheel.forEach((fn) => fn({ type: "wheel" }));

  env.win._raf.length = 0;
  assert.strictEqual(env.docEl.hasAttribute("data-scroll-anim"), false,
    "cancel must clear data-scroll-anim");
});

test("cancel is safe to call when nothing is animating", () => {
  const env = makeEnv({ sections: { faq: 4000 }, currentY: 0 });
  assert.doesNotThrow(() => env.nav.cancel());
  assert.doesNotThrow(() => env.nav.cancel());
});

test("an unknown section id is a no-op rather than an error", () => {
  const env = makeEnv({ sections: { faq: 4000 }, currentY: 0 });
  assert.doesNotThrow(() => env.nav.goTo("does-not-exist"));
  assert.deepStrictEqual(env.win.scrolls, [], "must not scroll");
});

test("marks the section crossing the band, not merely the first one", () => {
  /* Two sections; scrolled so that only the second has crossed the band line
   * (viewport 800 => line at 360px). */
  const env = makeEnv({
    sections: { music: 3000, faq: 3200 },
    docHeight: 9000,
    viewportH: 800,
    currentY: 3000
  });
  /* music.top = 0, faq.top = 200. Both are <= 360, so the *last* one wins. */
  env.IO.last.emit(["music"]);
  let current = env.chips.filter((c) => c._attrs["aria-current"] === "true");
  assert.strictEqual(current.length, 1, "exactly one chip may be marked current");
  assert.strictEqual(current[0].getAttribute("data-section-link"), "faq",
    "the last section past the line must win, deterministically");

  /* Now scrolled back to the top: nothing has crossed the line, so the bar
   * must still be marked (with the first section) rather than going blank. */
  env.win.pageYOffset = 0;
  env.IO.last.emit(["music", "faq"]);
  current = env.chips.filter((c) => c._attrs["aria-current"] === "true");
  assert.strictEqual(current.length, 1);
  assert.strictEqual(current[0].getAttribute("data-section-link"), "music");
});

test("marker scrolls the bar, never the document", () => {
  const env = makeEnv({ sections: { faq: 4000 }, currentY: 0 });
  const before = env.win.pageYOffset;
  env.IO.last.emit(["faq"]);
  assert.strictEqual(env.win.pageYOffset, before,
    "marking a section must not move the document scroll position");
});

test("leaves the bar's scroll alone when the active chip is already visible", () => {
  const env = makeEnv({ sections: { welcome: 1000, faq: 4000 }, currentY: 4000 });
  /* Chips sit at 0 and 90 in a 400px-wide list: the second is already in view. */
  env.IO.last.emit(["welcome", "faq"]);
  assert.strictEqual(env.barList.scrollLeft, 0,
    "no bar scrolling when the chip is already in view");
});

test("scrolls the bar when the active chip is past the right edge", () => {
  /* Six chips at 90px pitch: the last spans [450,530] in a 400px list, so it
   * starts off-screen to the right. Scrolled to the document bottom, the
   * ordered marker scan selects the *last* section, which is that chip. */
  const ids = ["a", "b", "c", "d", "e", "f"];
  const map = {};
  ids.forEach((id, i) => { map[id] = 1000 + i * 900; });
  const env = makeEnv({ sections: map, currentY: 1000 + 5 * 900 });
  env.IO.last.emit(ids);

  assert.ok(env.barList.scrollLeft > 0,
    "the bar must scroll to reveal the off-screen chip");
  /* chip f right edge 530, list 400 wide, 16px trailing padding => 146. */
  assert.strictEqual(env.barList.scrollLeft, 146,
    "bar must scroll by exactly the overflow plus padding");
  assert.strictEqual(env.win.pageYOffset, 1000 + 5 * 900,
    "and the document must not have moved");
});

test("scrolls the bar back when the active chip is before the left edge", () => {
  const ids = ["a", "b", "c", "d", "e", "f"];
  const map = {};
  ids.forEach((id, i) => { map[id] = 1000 + i * 900; });
  const env = makeEnv({ sections: map, currentY: 1000 });

  /* Start with the bar scrolled right, then let the marker land on chip a,
   * which is now entirely left of the list viewport. */
  env.barList.scrollLeft = 200;
  env.IO.last.emit(ids);

  assert.strictEqual(env.barList.scrollLeft, 0,
    "the bar must scroll back to the start and never go negative");
});

test("moves keyboard focus into the target section", () => {
  const env = makeEnv({ sections: { faq: 4000 }, currentY: 0 });
  env.nav.goTo("faq");
  env.runToCompletion();
  assert.ok(env.win.focused, "focus should move to the section heading");
  assert.strictEqual(env.win.focused.hasAttribute("tabindex"), true,
    "heading needs tabindex=-1 to be programmatically focusable");
});

test("intercepts guide links but leaves other pages and the skip link to the browser", () => {
  const env = makeEnv({ sections: { faq: 4000 }, currentY: 0 });
  const here = env.win.location.pathname;

  function click(target, extra) {
    const ev = Object.assign({
      button: 0, defaultPrevented: false,
      preventDefault() { this.defaultPrevented = true; },
      target
    }, extra || {});
    env.docHandlers.click.forEach((fn) => fn(ev));
    return ev;
  }

  /* Builds an anchor stub with a real classList, so class-based guards in the
   * production code are exercised the way the browser would exercise them.
   * `path` is the href's resolved pathname, mirroring how the DOM reports it. */
  function anchorStub(href, className) {
    const classes = String(className || "").split(/\s+/).filter(Boolean);
    return {
      className: classes.join(" "),
      classList: {
        contains(c) { return classes.indexOf(c) !== -1; }
      },
      pathname: href.charAt(0) === "#" ? here : href.split("#")[0],
      getAttribute(n) { return n === "href" ? href : null; }
    };
  }

  const guideEvent = click({ closest: () => anchorStub("#faq") });
  assert.strictEqual(guideEvent.defaultPrevented, true,
    "guide anchor clicks should be handled");

  /* The global top bar uses "/#faq". On the guide that resolves to the current
   * document, so it must animate in place rather than navigate. */
  const absoluteSameDoc = click({ closest: () => anchorStub("/#faq") });
  assert.strictEqual(absoluteSameDoc.defaultPrevented, true,
    "an absolute link to this same page should animate, not navigate");

  /* On another page the same href points somewhere else: let the browser go. */
  const otherEnv = makeEnv({ sections: { faq: 4000 }, currentY: 0, path: "/privacy/" });
  const absoluteElsewhere = {
    button: 0, defaultPrevented: false,
    preventDefault() { this.defaultPrevented = true; },
    target: { closest: () => anchorStub("/#faq") }
  };
  otherEnv.docHandlers.click.forEach((fn) => fn(absoluteElsewhere));
  assert.strictEqual(absoluteElsewhere.defaultPrevented, false,
    "a link to another page must be left to the browser");
  assert.deepStrictEqual(otherEnv.win.scrolls, []);

  /* A skip link must jump instantly: an animated overshoot would delay the
   * content the user asked to skip to, which defeats the point of the link. */
  const skipEvent = click({ closest: () => anchorStub("#faq", "skip-link") });
  assert.strictEqual(skipEvent.defaultPrevented, false,
    "the skip link must fall through to native browser scrolling");
});

test("modified clicks are left to the browser", () => {
  const env = makeEnv({ sections: { faq: 4000 }, currentY: 0 });
  const ev = {
    button: 0, defaultPrevented: false, metaKey: true,
    preventDefault() { this.defaultPrevented = true; },
    target: {
      closest: () => ({
        classList: { contains() { return false; } },
        pathname: "/",
        getAttribute: () => "#faq"
      })
    }
  };
  env.docHandlers.click.forEach((fn) => fn(ev));
  assert.strictEqual(ev.defaultPrevented, false);
  assert.deepStrictEqual(env.win.scrolls, []);
});
