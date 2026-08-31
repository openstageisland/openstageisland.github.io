/* Open Stage Island — Live Data Counter
 * Embeds the official secondlife.com/destination page for Open Stage Island
 * inside a sandboxed iframe with graceful fallback when blocked.
 *
 * Counters:
 *   - Site visits (freevisitorcounters slot 1631175)
 *   - SL destination traffic (slot 1631180)
 *   - Live local clock ticker
 *
 * No external deps. Targets ES5 for broad compatibility (no padStart).
 */
(function (root) {
  "use strict";

  var ROOT_ID    = "osi-live-data";
  var DEST_URL   = "https://secondlife.com/destination/open-stage-island";
  var SLURL_HREF = "https://maps.secondlife.com/secondlife/Derwent/248/128/22";
  var TIMEOUT_MS = 6500;

  function byId(id) { return document.getElementById(id); }

  function el(tag, attrs, children) {
    var node = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        if (k === "text") {
          node.appendChild(document.createTextNode(attrs[k]));
        } else if (k === "class") {
          node.className = attrs[k];
        } else {
          node.setAttribute(k, attrs[k]);
        }
      });
    }
    if (children) {
      children.forEach(function (c) {
        if (c) node.appendChild(c);
      });
    }
    return node;
  }

  function renderFallback(reason) {
    var card = el("div", { "class": "osi-live-card osi-live-fallback" });
    card.appendChild(el("p", {
      "class": "osi-live-status",
      "text": "Live destination page could not be embedded (" + reason + ")."
    }));
    card.appendChild(el("a", {
      "class": "cta-button cta-themed",
      href: DEST_URL,
      rel: "noopener",
      target: "_blank",
      "text": "Open official destination page \u2191"
    }));
    card.appendChild(el("p", { "class": "osi-live-meta", "text":
      "Region: Derwent \xb7 248 / 128 / 22 \xb7 Moderate"
    }));
    return card;
  }

  function renderStatSlot(id, label, foot) {
    var item = el("div", { "class": "osi-live-stat" });
    item.appendChild(el("span", { "class": "osi-live-stat-label", "text": label }));
    item.appendChild(el("span", { "class": "osi-live-stat-value", id: id, "text": "\u2014" }));
    item.appendChild(el("span", { "class": "osi-live-stat-foot", "text": foot }));
    return item;
  }

  function renderStatsPanel() {
    var stats = el("div", {
      "class": "osi-live-stats",
      "aria-live": "polite",
      "aria-atomic": "false"
    });
    stats.appendChild(renderStatSlot("osi-stat-site", "Site visits",
      "freevisitorcounters #1631175"));
    stats.appendChild(renderStatSlot("osi-stat-sl", "Destination traffic",
      "freevisitorcounters #1631180"));
    stats.appendChild(renderStatSlot("osi-stat-time", "Local time",
      "updates every second"));
    return stats;
  }

  function loadCounter(slot, targetId, okClass) {
    var img = new Image();
    // Counter provider must not learn the visitor page via Referer.
    img.referrerPolicy = "no-referrer";
    img.alt = "";
    img.style.display = "none";
    img.src = "https://www.freevisitorcounters.com/en/home/counter/" + slot + "/t/1?cb=" + Date.now();

    var cleanup = function () {
      img.onload = img.onerror = null;
      if (img.parentNode) img.parentNode.removeChild(img);
    };

    img.onload = function () {
      cleanup();
      var t = byId(targetId);
      if (!t) return;
      t.textContent = "live \xb7 #" + slot;
      if (okClass) t.classList.add(okClass);
    };
    img.onerror = function () {
      cleanup();
      var t = byId(targetId);
      if (!t) return;
      t.textContent = "offline";
      t.classList.add("osi-live-stat-value--warn");
    };
  }

  var _clockInterval = null;
  function tickClock(targetId) {
    if (_clockInterval !== null) return;
    function paint() {
      var t = byId(targetId);
      if (!t) return;
      var d = new Date();
      // ES5-friendly zero-pad (no padStart).
      var pad = function (n) { return ("0" + n).slice(-2); };
      t.textContent = pad(d.getHours()) + ":" + pad(d.getMinutes()) + ":" + pad(d.getSeconds());
    }
    paint();
    _clockInterval = setInterval(paint, 1000);
  }

  function init() {
    var host = byId(ROOT_ID);
    if (!host) return;
    if (host.dataset.osiLiveInit) return;
    host.dataset.osiLiveInit = "1";

    host.appendChild(renderStatsPanel());

    loadCounter("1631175", "osi-stat-site", "osi-live-stat-value--ok");
    loadCounter("1631180", "osi-stat-sl",   "osi-live-stat-value--ok");
    tickClock("osi-stat-time");

    var frameWrap = el("div", { "class": "osi-live-frame-wrap" });
    var iframe = el("iframe", {
      src:            DEST_URL,
      title:          "Open Stage Island \u2014 official Second Life destination page",
      loading:        "lazy",
      "class":        "osi-live-frame",
      sandbox:        "allow-popups",
      referrerpolicy: "no-referrer-when-downgrade"
    });
    frameWrap.appendChild(iframe);
    host.appendChild(frameWrap);

    host.appendChild(el("p", { "class": "osi-live-manual" }, [
      el("a", {
        href:    SLURL_HREF,
        target: "_blank",
        rel:    "noopener",
        "text": "Open Second Life maps \u2191"
      })
    ]));

    var didLoad = false;
    iframe.addEventListener("load", function () { didLoad = true; });

    // Fallback for X-Frame-Options / CSP blocks. If the iframe fires `load`
    // after 6.5s, didLoad=true but the fallback has already shown — that's
    // intentional: we don't want to disturb the fallback UI to flash empty
    // when the slow iframe finally loads.
    setTimeout(function () {
      if (didLoad) return;
      iframe.style.display = "none";
      frameWrap.appendChild(renderFallback("X-Frame-Options or CSP blocked the embed"));
    }, TIMEOUT_MS);
  }

  if (document.readyState === "loading") {
    root.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

}(window));
