/* Open Stage Island — single-page guide navigation
 *
 * Drives the persistent bottom bar (.bottom-bar) and any same-page anchor
 * link on the visitor guide.
 *
 * Scroll animation
 * ----------------
 * Activating a section link plays a two-phase "overshoot and settle" move:
 *
 *   phase 1  start -> past the target, by OVERSHOOT_RATIO of the viewport
 *            (ease-out, quick) so a sliver of the neighbouring section peeks
 *            in above the fold — the "oops, too far" beat;
 *   phase 2  overshoot -> exact section top (ease-in-out, slower) so the
 *            section settles into its final resting place rather than stopping
 *            dead.
 *
 * The overshoot is deliberately proportional to the viewport rather than a
 * fixed pixel count, so it reads the same on a phone and on a desktop.
 *
 * Robustness
 * ----------
 * - prefers-reduced-motion: reduce short-circuits to an instant jump.
 * - Any manual scroll input (wheel / touch / pointer / navigation key) cancels
 *   an in-flight animation, so the page never fights the user for the scroll
 *   position.
 * - Missing targets, zero-distance moves and detached nodes are no-ops rather
 *   than errors: the guide is also reachable with JavaScript disabled, and the
 *   native fragment jump is the fallback.
 * - The scroll position is written per-frame with scroll-behavior forced to
 *   `auto` (html[data-scroll-anim]) so the CSS `scroll-behavior: smooth` rule
 *   in style.css cannot fight the tween.
 *
 * Targets ES5 syntax to match assets/js/live-data.js. IntersectionObserver is
 * the only modern API relied upon; without it the bar still navigates, it just
 * does not highlight the current section.
 */
(function () {
  "use strict";

  /* Fraction of the viewport height to overshoot by. */
  var OVERSHOOT_RATIO = 0.07;
  /* Phase 1 (start -> overshoot), ms. */
  var OUT_DURATION = 380;
  /* Phase 2 (overshoot -> target), ms. Deliberately slower than phase 1. */
  var BACK_DURATION = 520;
  /* Breathing room above the target, px. */
  var TOP_GAP = 12;

  var docEl = document.documentElement;
  var bottomBar = document.querySelector(".bottom-bar");
  var barList = bottomBar ? bottomBar.querySelector(".bottom-bar__list") : null;

  var rafId = 0;
  var reduceMotion = window.matchMedia
    ? window.matchMedia("(prefers-reduced-motion: reduce)")
    : null;

  /* ── helpers ─────────────────────────────────────────────────────── */

  function scrollY() {
    return window.pageYOffset ||
      (docEl.scrollTop ? docEl.scrollTop : 0) ||
      document.body.scrollTop || 0;
  }

  function maxScroll() {
    var docHeight = Math.max(
      docEl.scrollHeight,
      docEl.offsetHeight,
      document.body.scrollHeight,
      document.body.offsetHeight
    );
    return Math.max(0, docHeight - window.innerHeight);
  }

  function clamp(value, min, max) {
    return value < min ? min : (value > max ? max : value);
  }

  function prefersReduced() {
    return !!(reduceMotion && reduceMotion.matches);
  }

  /* Absolute document offset that puts `el` a comfortable distance below the
   * top of the viewport.
   *
   * The fixed bottom chrome does not need to be subtracted here: CSS
   * scroll-padding-* only applies to browser-driven scrolling, not to the
   * window.scrollTo() calls below, so the clearance it provides comes from the
   * body padding-bottom in site-chrome.css, which is already part of the
   * document height that maxScroll() measures. */
  function targetOffsetFor(el) {
    var rect = el.getBoundingClientRect();
    var top = rect.top + scrollY() - TOP_GAP;
    var limit = maxScroll();
    /* The last section can never reach the top of the viewport; clamping keeps
     * it from scrolling past the end of the document. */
    return clamp(top, 0, limit);
  }

  function easeOutCubic(t) {
    var inv = 1 - t;
    return 1 - inv * inv * inv;
  }

  function easeInOutSine(t) {
    return -(Math.cos(Math.PI * t) - 1) / 2;
  }

  function cancel() {
    if (rafId) {
      window.cancelAnimationFrame(rafId);
      rafId = 0;
    }
    docEl.removeAttribute("data-scroll-anim");
  }

  /* One phase of the animation. Calls `done` exactly once, on completion or
   * on cancellation, so the phase chain cannot be left half-open. */
  function tween(from, to, duration, ease, done) {
    var startTime = null;
    var settled = false;

    function finish() {
      if (settled) return;
      settled = true;
      rafId = 0;
      if (done) done();
    }

    function frame(now) {
      if (settled) return;
      if (startTime === null) startTime = now;
      var elapsed = now - startTime;
      var t = duration > 0 ? Math.min(1, elapsed / duration) : 1;
      window.scrollTo(0, from + (to - from) * ease(t));
      if (t < 1) {
        rafId = window.requestAnimationFrame(frame);
      } else {
        finish();
      }
    }

    /* duration <= 0 means "no animation": land immediately. */
    if (duration <= 0) {
      window.scrollTo(0, to);
      finish();
      return;
    }
    rafId = window.requestAnimationFrame(frame);
  }

  /* ── navigation ─────────────────────────────────────────────────── */

  /* Move focus to the target's heading so keyboard and screen-reader users
   * land inside the section rather than staying on the bar link. `preventScroll`
   * keeps this from fighting the animation. */
  function focusHeading(el) {
    var heading = el.querySelector("h2, h3") || el;
    if (!heading || typeof heading.focus !== "function") return;
    if (!heading.hasAttribute("tabindex")) {
      heading.setAttribute("tabindex", "-1");
    }
    try {
      heading.focus({ preventScroll: true });
    } catch (err) {
      /* Older browsers ignore the options bag; a plain focus would jump the
       * scroll position, so skip it rather than undo the animation. */
    }
  }

  function updateHash(id) {
    try {
      window.history.pushState(null, "", "#" + id);
    } catch (err) {
      /* pushState can throw on file:// and in sandboxed frames. The visual
       * navigation already happened, so this is safe to ignore. */
    }
  }

  function goToSection(el, id) {
    cancel();

    var target = targetOffsetFor(el);
    updateHash(id);
    focusHeading(el);

    if (prefersReduced()) {
      window.scrollTo(0, target);
      return;
    }

    var start = scrollY();
    var distance = target - start;

    /* Nothing meaningful to animate (same position, or a sub-pixel nudge). */
    if (Math.abs(distance) < 2) {
      window.scrollTo(0, target);
      return;
    }

    /* Scale the overshoot down for very short moves so a small step does not
     * visibly sail past a neighbouring section. */
    var overshoot = Math.min(
      window.innerHeight * OVERSHOOT_RATIO,
      Math.max(0, Math.abs(distance) - TOP_GAP)
    ) * (distance > 0 ? 1 : -1);

    var limit = maxScroll();
    var past = clamp(target + overshoot, 0, limit);

    /* For very short moves the overshoot collapses onto the target, which
     * would make phase 2 a no-op; fall back to a single eased move. */
    if (Math.abs(past - target) < 2) {
      docEl.setAttribute("data-scroll-anim", "");
      tween(start, target, OUT_DURATION + BACK_DURATION, easeInOutSine, function () {
        docEl.removeAttribute("data-scroll-anim");
      });
      return;
    }

    docEl.setAttribute("data-scroll-anim", "");
    tween(start, past, OUT_DURATION, easeOutCubic, function () {
      tween(past, target, BACK_DURATION, easeInOutSine, function () {
        docEl.removeAttribute("data-scroll-anim");
      });
    });
  }

  /* Intercept same-page fragment links and animate instead. Modified clicks and
   * non-primary buttons fall through to the browser (open in new tab, etc.). */
  function onClick(e) {
    if (e.defaultPrevented) return;
    if (e.button !== 0) return;
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;

    var anchor = e.target && e.target.closest
      ? e.target.closest("a[href^='#']")
      : null;
    if (!anchor) return;

    /* A skip link exists to get keyboard users past the chrome *immediately*.
     * Animating it would delay the very content it promises. */
    if (anchor.classList && anchor.classList.contains("skip-link")) return;

    var href = anchor.getAttribute("href");
    if (!href || href === "#" || href.length < 2) return;

    var id = href.slice(1);
    var el = null;
    try {
      el = document.getElementById(id);
    } catch (err) {
      return;
    }
    if (!el) return;

    e.preventDefault();
    goToSection(el, id);
  }

  /* ── current-section marker ─────────────────────────────────────── */

  /* Bring the active chip into view *within the bar only*, by adjusting the
   * bar's own scrollLeft. Element.scrollIntoView() is deliberately not used:
   * it also scrolls ancestor scrollports, including the document, which would
   * fight the scroll animation still in flight.
   *
   * Deltas are computed from getBoundingClientRect() rather than offsetLeft,
   * because offsetLeft is measured from the nearest positioned ancestor (here
   * the fixed .bottom-bar) while scrollLeft belongs to .bottom-bar__list. The
   * two only coincide while the list spans the bar exactly. */
  function revealChip(chip) {
    if (!barList || !chip) return;
    var pad = 16;
    var chipRect = chip.getBoundingClientRect();
    var listRect = barList.getBoundingClientRect();
    if (!listRect.width) return;
    var delta = 0;
    if (chipRect.left < listRect.left + pad) {
      delta = chipRect.left - (listRect.left + pad);
    } else if (chipRect.right > listRect.right - pad) {
      delta = chipRect.right - (listRect.right - pad);
    }
    if (!delta) return;
    /* Clamp explicitly: the first chip can sit entirely left of the viewport,
     * and a naive subtraction would ask for a negative scrollLeft. Browsers
     * clamp it anyway, but relying on that hides the intent. */
    barList.scrollLeft = Math.max(0, barList.scrollLeft + delta);
  }

  function setCurrent(id) {
    if (!bottomBar || !id) return;
    var chips = bottomBar.querySelectorAll("[data-section-link]");
    var active = null;
    var i;
    for (i = 0; i < chips.length; i++) {
      if (chips[i].getAttribute("data-section-link") === id) {
        active = chips[i];
        chips[i].setAttribute("aria-current", "true");
      } else {
        chips[i].removeAttribute("aria-current");
      }
    }
    revealChip(active);
  }

  /* Pick the section the reader is actually in: the last one whose top has
   * crossed the band line. Scanning the ordered list makes the result
   * independent of IntersectionObserver callback ordering, which is not
   * guaranteed and previously made the marker jump between sections during
   * fast scrolling. */
  function updateCurrent(sections) {
    var line = window.innerHeight * 0.45;
    var chosen = null;
    var i;
    for (i = 0; i < sections.length; i++) {
      if (sections[i].getBoundingClientRect().top <= line) {
        chosen = sections[i];
      }
    }
    /* Nothing has crossed the line yet (still inside the hero): keep the bar
     * marked rather than leaving it blank. */
    setCurrent((chosen || sections[0]).id);
  }

  function observeSections() {
    if (!bottomBar || typeof IntersectionObserver !== "function") return;

    var sections = document.querySelectorAll("[data-guide-section]");
    if (!sections.length) return;

    /* The observer is only a cheap trigger — the authoritative choice is made
     * by the ordered scan in updateCurrent(). */
    var observer = new IntersectionObserver(function () {
      updateCurrent(sections);
    }, {
      /* A thin band across the middle of the viewport. */
      rootMargin: "-45% 0px -50% 0px",
      threshold: 0
    });

    for (var i = 0; i < sections.length; i++) {
      observer.observe(sections[i]);
    }
  }

  /* ── wiring ─────────────────────────────────────────────────────── */

  function init() {
    /* The bottom bar is the guide's marker; pages without it have no sections
     * to navigate between. Click handling is delegated from document, so it
     * also covers links injected later (e.g. by network-ux.js). */
    if (!bottomBar) return;

    document.addEventListener("click", onClick);

    /* Manual input always wins over an in-flight animation. `passive` keeps
     * these listeners off the scrolling critical path. */
    var CANCEL_EVENTS = ["wheel", "touchstart", "pointerdown", "mousedown"];
    var i;
    for (i = 0; i < CANCEL_EVENTS.length; i++) {
      window.addEventListener(CANCEL_EVENTS[i], cancel, { passive: true });
    }

    var NAV_KEYS = {
      ArrowUp: 1, ArrowDown: 1, PageUp: 1, PageDown: 1,
      Home: 1, End: 1, " ": 1, Spacebar: 1
    };
    document.addEventListener("keydown", function (e) {
      if (NAV_KEYS[e.key]) cancel();
    });

    /* The page can also be resized mid-animation (mobile URL bar collapse),
     * which invalidates the cached offsets. */
    window.addEventListener("resize", cancel, { passive: true });

    /* Re-anchor after a back/forward navigation, which restores the scroll
     * position natively without firing our click handler. */
    window.addEventListener("popstate", function () {
      var id = window.location.hash.slice(1);
      if (!id) return;
      var el = document.getElementById(id);
      if (el) window.scrollTo(0, targetOffsetFor(el));
    });

    observeSections();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  /* Exposed for the footer in-page links and for manual verification. */
  window.OSISectionNav = {
    goTo: function (id) {
      var el = document.getElementById(id);
      if (el) goToSection(el, id);
    },
    cancel: cancel
  };
})();
