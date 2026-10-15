/* Open Stage Island — Side Tags Navigation
 *
 * Vertical scroll navigation that:
 * - Shows tags for each guide section on the right side
 * - Highlights the current section as you scroll
 * - Animates an indicator line that moves between tags
 * - Reveals tag labels on hover/focus and for active section
 */
(function () {
  "use strict";

  var sideTags = document.querySelector(".side-tags");
  var tagLinks = sideTags ? sideTags.querySelectorAll(".side-tags__link") : [];
  var indicator = sideTags ? sideTags.querySelector(".side-tags__indicator") : null;
  var tagItems = sideTags ? sideTags.querySelectorAll(".side-tags__item") : [];

  if (!sideTags || !tagLinks.length) return;

  var sections = [];
  var tagMap = {};

  /* Build section map from tag links */
  tagLinks.forEach(function (link) {
    var sectionId = link.getAttribute("data-section");
    var section = document.getElementById(sectionId);
    if (section) {
      sections.push(section);
      tagMap[sectionId] = link;
    }
  });

  if (!sections.length) return;

  var reduceMotion = window.matchMedia
    ? window.matchMedia("(prefers-reduced-motion: reduce)")
    : null;

  function prefersReduced() {
    return !!(reduceMotion && reduceMotion.matches);
  }

  /* Get scroll position */
  function scrollY() {
    return window.pageYOffset || document.documentElement.scrollTop || document.body.scrollTop || 0;
  }

  /* Get viewport height */
  function viewportHeight() {
    return window.innerHeight || document.documentElement.clientHeight;
  }

  /* Check if element is in viewport (with offset for hero) */
  function isSectionActive(section) {
    var rect = section.getBoundingClientRect();
    var vh = viewportHeight();
    /* Section is active when its top has crossed the 40% line of viewport */
    return rect.top <= vh * 0.4 && rect.bottom >= vh * 0.1;
  }

  /* Update active tag based on scroll position */
  function updateActiveTag() {
    var activeSection = null;
    var activeLink = null;

    /* Find the last section whose top has crossed the activation line */
    for (var i = 0; i < sections.length; i++) {
      if (isSectionActive(sections[i])) {
        activeSection = sections[i];
      }
    }

    /* If no section is active (e.g., still in hero), default to first */
    if (!activeSection && sections.length) {
      activeSection = sections[0];
    }

    if (activeSection) {
      var activeId = activeSection.id;
      activeLink = tagMap[activeId];
    }

    /* Update active state on links */
    tagLinks.forEach(function (link) {
      if (link === activeLink) {
        link.classList.add("is-active");
      } else {
        link.classList.remove("is-active");
      }
    });

    /* Animate indicator to active tag */
    if (indicator && activeLink) {
      var linkRect = activeLink.getBoundingClientRect();
      var tagsRect = sideTags.getBoundingClientRect();
      var top = linkRect.top - tagsRect.top + linkRect.height / 2;
      var height = linkRect.height;

      if (prefersReduced()) {
        indicator.style.top = top + "px";
        indicator.style.height = height + "px";
      } else {
        indicator.style.top = top + "px";
        indicator.style.height = height + "px";
      }
    }
  }

  /* Handle tag visibility based on scroll */
  function updateTagVisibility() {
    var scrollTop = scrollY();
    var vh = viewportHeight();
    var heroHeight = vh; /* Hero is 100vh */

    /* Start showing tags after scrolling past hero */
    var showThreshold = heroHeight * 0.3;

    tagItems.forEach(function (item, index) {
      var delay = index * 50; /* Staggered reveal */
      if (scrollTop > showThreshold) {
        setTimeout(function () {
          item.classList.add("is-visible");
        }, delay);
      } else {
        item.classList.remove("is-visible");
      }
    });
  }

  /* Throttled scroll handler */
  var ticking = false;
  function onScroll() {
    if (!ticking) {
      window.requestAnimationFrame(function () {
        updateActiveTag();
        updateTagVisibility();
        ticking = false;
      });
      ticking = true;
    }
  }

  /* Smooth scroll to section when tag clicked */
  tagLinks.forEach(function (link) {
    link.addEventListener("click", function (e) {
      var href = link.getAttribute("href");
      if (href && href.startsWith("#")) {
        var targetId = href.slice(1);
        var target = document.getElementById(targetId);
        if (target) {
          e.preventDefault();
          var top = target.getBoundingClientRect().top + scrollY() - 80;
          window.scrollTo({
            top: top,
            behavior: prefersReduced() ? "auto" : "smooth"
          });
          /* Update hash without jumping */
          history.pushState(null, "", href);
        }
      }
    });
  });

  /* Initialize */
  function init() {
    updateActiveTag();
    updateTagVisibility();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll, { passive: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();