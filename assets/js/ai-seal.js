/* ai-seal.js -- reveal logic for the "back up" control.
 *
 * The control is shipped hidden and stays hidden until this file has decided the
 * visitor has something to go back to, which is the whole behaviour: a back-up
 * arrow that is already on screen when the page opens is a control that does
 * nothing, and the only affordance it offers is confusion.
 *
 * The trigger, in order of preference:
 *
 *   1. The bottom edge of the worldmap, when the page has one. transhumanists
 *      ships #world-map on both the index and /map.html, and the requirement
 *      for this control is that it appears *after* the worldmap -- not merely
 *      after a fixed scroll distance, which on /map.html (a full-viewport map)
 *      would never fire at all.
 *   2. One viewport height, on every page without a worldmap. Anything less and
 *      the arrow appears while the first screenful is still on screen.
 *
 * Authored once in template-shared/assets/js/ and copied into every site by
 * site_forge.py and publish-shared.ps1. No dependencies, no build step, and it
 * degrades to "the arrow never appears" if anything below throws -- a broken
 * watermark script must not take a page's scroll behaviour with it.
 */
(function () {
  "use strict";

  var MARKERS = [
    "#world-map",
    "#worldmap",
    ".world-map",
    ".worldmap",
    "[data-worldmap]",
    "#world-map-canvas",
  ];

  function triggerOffset() {
    var last = null;
    for (var i = 0; i < MARKERS.length; i++) {
      var found = document.querySelectorAll(MARKERS[i]);
      for (var j = 0; j < found.length; j++) {
        var box = found[j].getBoundingClientRect();
        if (box.height === 0 && box.width === 0) continue;
        var bottom = box.bottom + window.pageYOffset;
        if (last === null || bottom > last) last = bottom;
      }
    }
    return last === null ? window.innerHeight : last;
  }

  function ready(fn) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", fn, { once: true });
    } else {
      fn();
    }
  }

  ready(function () {
    var button = document.querySelector("[data-ai-totop]");
    if (!button) return;

    var label = button.getAttribute("data-ai-totop-label");
    var span = button.querySelector(".ai-visually-hidden");
    if (label) {
      if (span) span.textContent = label;
      button.setAttribute("aria-label", label);
      button.setAttribute("title", label);
    }

    var offset = triggerOffset();
    var ticking = false;

    function evaluate() {
      ticking = false;
      var scrollable = document.documentElement.scrollHeight - window.innerHeight;
      if (scrollable <= 8) {
        /* Nothing to scroll: a control that cannot do anything stays off. */
        button.classList.remove("is-visible");
        button.setAttribute("aria-hidden", "true");
        return;
      }
      button.removeAttribute("aria-hidden");
      button.classList.toggle("is-visible", window.pageYOffset >= offset);
    }

    function onScroll() {
      /* One rAF per frame regardless of how many scroll events fire. Reading
       * scrollY inside a scroll handler forces layout on every event otherwise. */
      if (ticking) return;
      ticking = true;
      window.requestAnimationFrame(evaluate);
    }

    window.addEventListener("scroll", onScroll, { passive: true });

    var resizeTimer = 0;
    window.addEventListener("resize", function () {
      window.clearTimeout(resizeTimer);
      resizeTimer = window.setTimeout(function () {
        /* The worldmap can be responsive, so the trigger is re-derived rather
         * than cached. Reflow also invalidates a stale offset in both
         * directions: rotating a phone can grow the map past the old trigger. */
        offset = triggerOffset();
        evaluate();
      }, 150);
    });

    button.addEventListener("click", function () {
      var reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      var top = document.getElementById("main") || document.body;
      try {
        window.scrollTo({ top: 0, left: 0, behavior: reduced ? "auto" : "smooth" });
      } catch (err) {
        /* Safari < 15.4 has no options form. */
        window.scrollTo(0, 0);
      }
      /* Move the keyboard with the viewport, or focus stays on a button that
       * has just scrolled out of sight and the next Tab continues from the
       * bottom of the document. preventScroll because the scroll is already
       * under way and a focus-driven jump would fight it. */
      if (top && typeof top.focus === "function") {
        top.focus({ preventScroll: true });
      }
      offset = triggerOffset();
    });

    evaluate();
  });
})();
