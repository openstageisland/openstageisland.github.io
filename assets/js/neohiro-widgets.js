(function (root) {
  'use strict';

  var _cfg = {};
  var _counters = {};
  var _timers = [];
  var _sharedIO = null;

  /* ──────────────────────────────────────────────────────────────────────────
   * Config
   * ────────────────────────────────────────────────────────────────────────── */
  function init(cfg) {
    cfg = cfg || {};
    _cfg = {
      heartbeatBase: cfg.heartbeatBase || '',
      visitorCounterBase: cfg.visitorCounterBase || 'https://www.freevisitorcounters.com/en/home/counter',
      apiBase: cfg.apiBase || '',
      apiToken: cfg.apiToken || '',
      pollInterval: cfg.pollInterval || 30000,
      healthInterval: cfg.healthInterval || 30000,
      sparkInterval: cfg.sparkInterval || 10000,
    };
    wireAutoDestroy();
  }

  /* ──────────────────────────────────────────────────────────────────────────
   * DOM helpers
   * ────────────────────────────────────────────────────────────────────────── */
  function byId(id) { return document.getElementById(id); }
  function el(tag, attrs, children) {
    var n = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        if (k === 'text') n.appendChild(document.createTextNode(attrs[k]));
        else if (k === 'class') n.className = attrs[k];
        else n.setAttribute(k, attrs[k]);
      });
    }
    if (children) children.forEach(function (c) { if (c) n.appendChild(c); });
    return n;
  }

  var _visible = true;

  function trackTimer(fn, ms) {
    var id = setInterval(function () {
      if (!_visible) return;
      fn();
    }, ms);
    _timers.push(id);
    return id;
  }

  function destroyAllTimers() {
    _timers.forEach(function (id) { clearInterval(id); });
    // Clear any pending fetch backoff timers
    Object.keys(_fetchBackoffTimer).forEach(function (url) {
      clearTimeout(_fetchBackoffTimer[url]);
    });
    _timers = [];
    _fetchCache = {};
    _fetchOrder = [];
    _pendingFetch = {};
    _fetchFailures = {};
    _fetchBackoffTimer = {};
  }

  var _autoDestroyWired = false;
  function wireAutoDestroy() {
    if (_autoDestroyWired || typeof root === 'undefined') return;
    _autoDestroyWired = true;
    var fire = function () { destroyAllTimers(); };
    if (typeof root.addEventListener === 'function') {
      root.addEventListener('pagehide', fire, { capture: true });
      root.addEventListener('beforeunload', fire, { capture: true });
      root.addEventListener('visibilitychange', function () {
        _visible = root.document.visibilityState === 'visible';
      }, { capture: true, passive: true });
    }
  }

  /* ──────────────────────────────────────────────────────────────────────────
   * 1.  Heartbeat SVG cards  (self-updating)
   * ────────────────────────────────────────────────────────────────────────── */
  function loadHeartbeat(containerId, tiers, opts) {
    opts = opts || {};
    var container = typeof containerId === 'string' ? byId(containerId) : containerId;
    if (!container) return;
    tiers = Array.isArray(tiers) ? tiers : [tiers || 'public'];

    tiers.forEach(function (tier) {
      var svgPath = (opts.basePath || _cfg.heartbeatBase) + '/' + tier + '.svg';
      var wrapper = el('div', { 'class': 'nhw-svg-tier nhw-tier-' + tier });
      var img = el('img', {
        'class': 'nhw-svg-img',
        alt: tier + ' heartbeat',
        src: svgPath + '?t=' + Date.now(),
      });
      var meta = el('div', { 'class': 'nhw-svg-meta', text: 'Loading ' + tier + '…' });
      var embed = el('div', { 'class': 'nhw-svg-embed' });
      embed.appendChild(img);
      wrapper.appendChild(embed);
      wrapper.appendChild(meta);
      container.appendChild(wrapper);

      img.onload = function () {
        meta.textContent = 'Updated just now · Refreshes every heartbeat cycle';
        meta.className = 'nhw-svg-meta nhw-meta-ok';
      };
      img.onerror = function () {
        meta.textContent = 'Heartbeat unavailable — will retry shortly';
        meta.className = 'nhw-svg-meta nhw-meta-err';
        img.style.opacity = '0.3';
      };

      var pollMs = opts.pollMs || 300000; // default 5 min
      (function (imgEl, svgP, mEl) {
        trackTimer(function () {
          imgEl.src = svgP + '?t=' + Date.now();
        }, pollMs);
      })(img, svgPath, meta);
    });
  }

  /* ──────────────────────────────────────────────────────────────────────────
   * 2.  Visitor counter (beacon, never blocks render)
   * ────────────────────────────────────────────────────────────────────────── */
  function loadVisitorCounter(slotId, targetId, opts) {
    opts = opts || {};
    var target = typeof targetId === 'string' ? byId(targetId) : targetId;
    if (!target) return;
    slotId = String(slotId || '').trim();
    if (!/^\d{6,8}$/.test(slotId)) {
      target.textContent = '—';
      return;
    }
    var base = _cfg.visitorCounterBase;
    var img = new Image();
    img.referrerPolicy = 'no-referrer';
    img.src = base + '/' + slotId + '/t/1?cb=' + Date.now();
    img.onload = function () {
      target.textContent = 'live · #' + slotId;
      target.className = 'nhw-stat-value nhw-ok';
      _counters[slotId] = { status: 'ok', ts: Date.now() };
      img.onload = img.onerror = null;
    };
    img.onerror = function () {
      target.textContent = 'counter offline';
      target.className = 'nhw-stat-value nhw-warn';
      _counters[slotId] = { status: 'offline', ts: Date.now() };
      img.onload = img.onerror = null;
    };
    if (opts.pollMs) {
      (function (imgBase, sl, tgt) {
        trackTimer(function () {
          var i = new Image();
          i.referrerPolicy = 'no-referrer';
          i.src = imgBase + '/' + sl + '/t/1?cb=' + Date.now();
          i.onload = function () { tgt.textContent = 'live · #' + sl; tgt.className = 'nhw-stat-value nhw-ok'; i.onload = i.onerror = null; };
          i.onerror = function () { tgt.textContent = 'counter offline'; tgt.className = 'nhw-stat-value nhw-warn'; i.onload = i.onerror = null; };
        }, opts.pollMs);
      })(base, slotId, target);
    }
  }

  /* ──────────────────────────────────────────────────────────────────────────
   * 3.  Live stat card (value + optional sparkline + direction flash)
   * ────────────────────────────────────────────────────────────────────────── */
  function renderStatCard(containerId, spec) {
    spec = spec || {};
    var container = typeof containerId === 'string' ? byId(containerId) : containerId;
    if (!container) return;
    var id = spec.id || 'stat-' + Math.random().toString(36).slice(2);
    var card = el('div', { 'class': 'nhw-stat-card' });

    var label = el('div', { 'class': 'nhw-stat-label', text: spec.label || '' });
    var value = el('div', { 'class': 'nhw-stat-value', id: id, text: spec.value != null ? spec.value : '—' });
    var sub = el('div', { 'class': 'nhw-stat-sub', text: spec.sub || '' });
    var barWrap = null;
    var barFill = null;
    if (spec.showBar) {
      barWrap = el('div', { 'class': 'nhw-stat-bar' });
      barFill = el('div', { 'class': 'nhw-stat-bar-fill', id: id + '-bar' });
      if (spec.barColor) barFill.style.background = spec.barColor;
      barWrap.appendChild(barFill);
    }

    card.appendChild(label);
    card.appendChild(value);
    if (barWrap) card.appendChild(barWrap);
    card.appendChild(sub);
    container.appendChild(card);

    if (spec.sparkCanvas) {
      var spark = byId(spec.sparkCanvas);
      if (spark) spec._sparkCanvas = spark;
    }

    return { id: id, el: card, barFill: barFill, sparkCanvas: spec._sparkCanvas };
  }

  function updateStatValue(id, value, opts) {
    opts = opts || {};
    var el2 = typeof id === 'string' ? byId(id) : id;
    if (!el2) return;
    var prev = parseFloat(el2.dataset.nhwVal) || 0;
    var num = parseFloat(value);
    if (!isNaN(num)) {
      el2.textContent = opts.format ? opts.format(num) : fmtCount(num);
      el2.dataset.nhwVal = num;
      if (opts.barFill) {
        var pct = opts.barMax ? Math.min(100, (num / opts.barMax) * 100) : num;
        opts.barFill.style.width = pct + '%';
        if (opts.barColorFn) opts.barFill.style.background = opts.barColorFn(pct);
      }
      if (opts.direction !== undefined) {
        flashBump(el2, opts.direction > 0 ? 'up' : opts.direction < 0 ? 'down' : 'flash', 1200);
      } else if (!isNaN(prev) && prev !== num) {
        flashBump(el2, num > prev ? 'up' : 'down', 1200);
      }
    }
  }

  /* ──────────────────────────────────────────────────────────────────────────
   * 4.  Health strip (Heart cycle JSON)
   * ────────────────────────────────────────────────────────────────────────── */
  function loadHealthStrip(containerId, apiPath, opts) {
    opts = opts || {};
    var container = typeof containerId === 'string' ? byId(containerId) : containerId;
    if (!container) return;
    var healthDiv = el('div', { 'class': 'nhw-health-strip' });
    var scoreEl = el('div', { 'class': 'nhw-health-score', id: 'nhw-health-score', text: '—' });
    var bandEl = el('div', { 'class': 'nhw-health-band', id: 'nhw-health-band', text: '' });
    var metaEl = el('div', { 'class': 'nhw-health-meta', id: 'nhw-health-meta', text: 'Loading…' });
    var barEl = el('div', { 'class': 'nhw-health-bar-wrap' });
    var barFill = el('div', { 'class': 'nhw-health-bar-fill', id: 'nhw-health-bar-fill' });
    barEl.appendChild(barFill);
    healthDiv.appendChild(scoreEl);
    healthDiv.appendChild(bandEl);
    healthDiv.appendChild(barEl);
    healthDiv.appendChild(metaEl);
    container.appendChild(healthDiv);

    var prev = null;
    function poll() {
      fetchJson(apiPath, function (data) {
        if (!data) return;
        var score = data.score != null ? data.score : 0;
        var band = data.band || bandOf(score);
        var mode = data.mode || '';
        var ts = data.t ? new Date(data.t * 1000).toLocaleTimeString() : '—';
        var repos = data.repos_known != null ? data.repos_known : '—';
        scoreEl.textContent = score + '/100';
        scoreEl.className = 'nhw-health-score nhw-score-' + band;
        bandEl.textContent = band.toUpperCase();
        bandEl.className = 'nhw-health-band nhw-band-' + band;
        barFill.style.width = score + '%';
        barFill.className = 'nhw-health-bar-fill nhw-bar-' + band;
        metaEl.textContent = 'Mode: ' + mode + ' · Repos: ' + repos + ' · ' + ts;
        if (prev !== null && score !== prev) {
          flashBump(scoreEl, score > prev ? 'up' : 'down', 1200);
        }
        prev = score;
      });
    }
    poll();
    var ms = opts.interval || _cfg.healthInterval;
    trackTimer(poll, ms);
  }

  /* ──────────────────────────────────────────────────────────────────────────
   * 5.  Activity feed (GitHub events)
   * ────────────────────────────────────────────────────────────────────────── */
  function loadActivityFeed(containerId, repos, opts) {
    opts = opts || {};
    var container = typeof containerId === 'string' ? byId(containerId) : containerId;
    if (!container) return;
    var feed = el('div', { 'class': 'nhw-feed' });
    var header = el('div', { 'class': 'nhw-feed-header' });
    header.appendChild(el('span', { 'class': 'nhw-feed-title', text: opts.title || 'Recent Activity' }));
    var count = el('span', { 'class': 'nhw-feed-count', id: 'nhw-feed-count', text: '—' });
    header.appendChild(count);
    feed.appendChild(header);
    var list = el('div', { 'class': 'nhw-feed-list', id: 'nhw-feed-list' });
    feed.appendChild(list);
    container.appendChild(feed);

    function poll() {
      fetchGitHubEvents(repos, opts.token, function (events) {
        if (!events || !events.length) {
          list.innerHTML = '<div class="nhw-feed-empty">No recent activity</div>';
          return;
        }
        count.textContent = events.length + ' events';
        list.innerHTML = '';
        events.slice(0, opts.limit || 10).forEach(function (ev) {
          list.appendChild(renderFeedItem(ev));
        });
        if (opts.direction !== undefined) {
          flashBump(count, opts.direction, 1000);
        }
      });
    }
    poll();
    trackTimer(poll, opts.interval || _cfg.pollInterval);
  }

  function renderFeedItem(ev) {
    var item = el('div', { 'class': 'nhw-feed-item' });
    var icon = el('span', { 'class': 'nhw-feed-icon', text: evIcon(ev.type) });
    var body = el('div', { 'class': 'nhw-feed-body' });
    var repo = el('span', { 'class': 'nhw-feed-repo', text: ev.repo });
    var action = el('span', { 'class': 'nhw-feed-action', text: ev.action });
    var time = el('span', { 'class': 'nhw-feed-time', text: ev.time });
    body.appendChild(repo);
    body.appendChild(action);
    item.appendChild(icon);
    item.appendChild(body);
    item.appendChild(time);
    return item;
  }

  /* ──────────────────────────────────────────────────────────────────────────
   * 6.  Social counters panel
   * ────────────────────────────────────────────────────────────────────────── */
  function loadSocialCounters(containerId, apiPath, opts) {
    opts = opts || {};
    var container = typeof containerId === 'string' ? byId(containerId) : containerId;
    if (!container) return;
    var panel = el('div', { 'class': 'nhw-social-panel' });
    var header = el('div', { 'class': 'nhw-social-header' });
    header.appendChild(el('span', { 'class': 'nhw-social-title', text: 'Social Media' }));
    var updated = el('span', { 'class': 'nhw-social-updated', id: 'nhw-social-updated' });
    header.appendChild(updated);
    panel.appendChild(header);
    var grid = el('div', { 'class': 'nhw-social-grid' });
    panel.appendChild(grid);
    container.appendChild(panel);

    var prev = {};
    function poll() {
      fetchJson(apiPath, function (data) {
        if (!data) return;
        updated.textContent = data.updated_at ? 'Updated ' + new Date(data.updated_at).toLocaleString() : '';
        var platforms = [
          { key: 'youtube', label: 'YouTube', sub: 'subscribers', icon: '\u25B6' },
          { key: 'x', label: 'X / Twitter', sub: 'followers', icon: '\uD835\uDD4F' },
          { key: 'instagram', label: 'Instagram', sub: 'followers', icon: '\uD83D\uDCF7' },
          { key: 'twitch', label: 'Twitch', sub: 'followers', icon: '\uD83C\uDFAE' },
        ];
        grid.innerHTML = '';
        platforms.forEach(function (p) {
          var d = data[p.key] || {};
          var val = d.subscribers || d.followers || 0;
          var card = el('div', { 'class': 'nhw-social-card' });
          card.appendChild(el('div', { 'class': 'nhw-social-icon', text: p.icon }));
          card.appendChild(el('div', { 'class': 'nhw-social-name', text: p.label }));
          var valEl = el('div', { 'class': 'nhw-social-value', id: 'nhw-sc-' + p.key, text: fmtCount(val) });
          card.appendChild(valEl);
          card.appendChild(el('div', { 'class': 'nhw-social-sub', text: p.sub }));
          grid.appendChild(card);

          if (prev[p.key] !== undefined && prev[p.key] !== val) {
            var dir = val > prev[p.key] ? 1 : -1;
            flashBump(valEl, dir > 0 ? 'up' : 'down', 1200);
          }
          prev[p.key] = val;
        });
      });
    }
    poll();
    trackTimer(poll, opts.interval || _cfg.pollInterval);
  }

  /* ──────────────────────────────────────────────────────────────────────────
   * 7.  Sparkline (canvas)
   * ────────────────────────────────────────────────────────────────────────── */
  function renderSparkline(canvasId, data, opts) {
    opts = opts || {};
    var canvas = typeof canvasId === 'string' ? byId(canvasId) : canvasId;
    if (!canvas) return;
    var ctx = canvas.getContext('2d');
    if (!ctx) return;
    var dpr = window.devicePixelRatio || 1;
    var w = canvas.offsetWidth || 120;
    var h = canvas.offsetHeight || 40;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    var color = opts.color || '#7c4dff';
    var fill = opts.fillColor || (color + '30');
    var points = Array.isArray(data) ? data : [];
    if (points.length < 2) return;
    var max = Math.max.apply(null, points);
    var min = Math.min.apply(null, points);
    var range = max - min || 1;
    var step = w / (points.length - 1);
    var pad = 2;
    var toX = function (i) { return i * step; };
    var toY = function (v) { return h - pad - ((v - min) / range) * (h - pad * 2); };

    ctx.clearRect(0, 0, w, h);
    ctx.beginPath();
    points.forEach(function (v, i) {
      var x = toX(i), y = toY(v);
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    });
    ctx.strokeStyle = color;
    ctx.lineWidth = opts.lineWidth || 1.5;
    ctx.stroke();

    if (opts.fill) {
      ctx.lineTo(toX(points.length - 1), h);
      ctx.lineTo(toX(0), h);
      ctx.closePath();
      ctx.fillStyle = fill;
      ctx.fill();
    }
  }

  /* ──────────────────────────────────────────────────────────────────────────
   * 8.  Live sparkline updater (continuous)
   * ────────────────────────────────────────────────────────────────────────── */
  function startSparkline(canvasId, dataPath, opts) {
    opts = opts || {};
    var canvas = typeof canvasId === 'string' ? byId(canvasId) : canvasId;
    if (!canvas) return;
    var history = [];
    var maxPoints = opts.maxPoints || 60;

    function update() {
      fetchJson(dataPath, function (data) {
        if (!data) return;
        var val;
        if (opts.transform) {
          val = opts.transform(data);
        } else if (Array.isArray(data)) {
          history = data.slice(-maxPoints);
          renderSparkline(canvas, history, opts);
          return;
        } else if (typeof data === 'number') {
          val = data;
        } else if (data.score != null) {
          val = data.score;
        }
        if (val != null && !isNaN(val)) {
          history.push(val);
          if (history.length > maxPoints) history = history.slice(-maxPoints);
          renderSparkline(canvas, history, opts);
        }
      });
    }
    update();
    trackTimer(update, opts.interval || _cfg.sparkInterval);
  }

  /* ──────────────────────────────────────────────────────────────────────────
   * 9.  Milestone cards
   * ────────────────────────────────────────────────────────────────────────── */
  function loadMilestones(containerId, apiPath, opts) {
    opts = opts || {};
    var container = typeof containerId === 'string' ? byId(containerId) : containerId;
    if (!container) return;
    var section = el('div', { 'class': 'nhw-milestones' });
    var header = el('div', { 'class': 'nhw-section-header' });
    header.appendChild(el('h3', { 'class': 'nhw-section-title', text: opts.title || 'Frontier Milestones' }));
    var grid = el('div', { 'class': 'nhw-milestones-grid', id: 'nhw-ms-grid' });
    section.appendChild(header);
    section.appendChild(grid);
    container.appendChild(section);

    var prevItems = null;
    function poll() {
      fetchJson(apiPath, function (data) {
        if (!data) return;
        var items = data.recent || data.milestones || [];
        grid.innerHTML = '';
        items.slice(0, opts.limit || 8).forEach(function (m) {
          grid.appendChild(renderMilestoneCard(m));
        });
        if (opts.direction !== undefined && items.length !== prevItems) {
          var headerEl = byId('nhw-ms-grid');
          if (headerEl && headerEl.parentElement) flashBump(headerEl.parentElement.querySelector('.nhw-section-title'), opts.direction, 1000);
        }
        prevItems = items.length;
      });
    }
    poll();
    trackTimer(poll, opts.interval || _cfg.pollInterval);
  }

  function renderMilestoneCard(m) {
    var card = el('a', { 'class': 'nhw-ms-card', href: m.url || '#', target: '_blank', rel: 'noopener' });
    card.style.setProperty('--ms-color', m.color || '#7c4dff');
    var header = el('div', { 'class': 'nhw-ms-header' });
    header.appendChild(el('span', { 'class': 'nhw-ms-icon', text: m.icon || '\uD83D\uDCCA' }));
    header.appendChild(el('span', { 'class': 'nhw-ms-category', text: m.category || '' }));
    card.appendChild(header);
    card.appendChild(el('h4', { 'class': 'nhw-ms-title', text: m.title || '' }));
    var valWrap = el('div', { 'class': 'nhw-ms-value-wrap' });
    var valEl = el('div', { 'class': 'nhw-ms-value', 'data-counter': m.value || '0', text: m.value || '0' });
    valWrap.appendChild(valEl);
    valWrap.appendChild(el('div', { 'class': 'nhw-ms-unit', text: m.unit || '' }));
    card.appendChild(valWrap);
    card.appendChild(el('div', { 'class': 'nhw-ms-meta', text: (m.source || '') + (m.date ? ' · ' + m.date : '') }));
    if (m.is_new) card.appendChild(el('span', { 'class': 'nhw-ms-new', text: 'NEW' }));

    observeAndCountup(valEl, m.value);
    return card;
  }

  /* ──────────────────────────────────────────────────────────────────────────
   * 10. Pulse ring animation
   * ────────────────────────────────────────────────────────────────────────── */
  function pulseRing(el2) {
    el2 = typeof el2 === 'string' ? byId(el2) : el2;
    if (!el2) return;
    el2.classList.add('nhw-pulse');
    setTimeout(function () { el2.classList.remove('nhw-pulse'); }, 1200);
  }

  /* ──────────────────────────────────────────────────────────────────────────
   * 11. Count-up animation (RAF-based)
   * ────────────────────────────────────────────────────────────────────────── */
  function animateCount(el2, target, opts) {
    el2 = typeof el2 === 'string' ? byId(el2) : el2;
    if (!el2) return Promise.resolve();
    opts = opts || {};
    var duration = opts.duration || 700;
    var start = parseFloat(el2.dataset.nhwVal) || 0;
    var end = parseFloat(target) || 0;
    var fmt = opts.format || fmtCount;
    var startTime = performance.now();
    return new Promise(function (resolve) {
      function tick(now) {
        var t = Math.min((now - startTime) / duration, 1);
        var eased = 1 - Math.pow(1 - t, 3);
        var val = start + (end - start) * eased;
        el2.textContent = fmt(val);
        if (t < 1) {
          requestAnimationFrame(tick);
        } else {
          el2.textContent = fmt(end);
          el2.dataset.nhwVal = end;
          resolve();
        }
      }
      requestAnimationFrame(tick);
    });
  }

  /* ──────────────────────────────────────────────────────────────────────────
   * 12. SSE stream (generic)
   * ────────────────────────────────────────────────────────────────────────── */
  function createSSE(url, handlers) {
    handlers = handlers || {};
    var es = null;
    var reconnectDelay = 1000;
    var maxDelay = 30000;
    var closed = false;

    function connect() {
      if (closed) return;
      try { es = new EventSource(url); } catch (e) { return; }

      es.onopen = function () {
        reconnectDelay = 1000;
        if (handlers.onOpen) handlers.onOpen();
      };
      es.onmessage = function (e) {
        try {
          var data = JSON.parse(e.data);
          if (handlers.onMessage) handlers.onMessage(data, e);
        } catch {}
      };
      es.onerror = function () {
        es.close();
        if (closed) return;
        if (handlers.onError) handlers.onError();
        setTimeout(connect, reconnectDelay);
        reconnectDelay = Math.min(reconnectDelay * 2, maxDelay);
      };
    }
    connect();
    return {
      close: function () {
        closed = true;
        if (es) es.close();
      }
    };
  }

  /* ──────────────────────────────────────────────────────────────────────────
   * Utilities
   * ────────────────────────────────────────────────────────────────────────── */
  function flashBump(el2, direction, ms) {
    el2 = typeof el2 === 'string' ? byId(el2) : el2;
    if (!el2) return;
    var valid = { up: 1, down: 1, flash: 1 };
    if (!valid[direction]) return;
    var cls = 'nhw-bump-' + direction;
    el2.classList.add(cls);
    pulseRing(el2);
    setTimeout(function () { el2.classList.remove(cls); }, ms || 1200);
  }

  function fmtCount(n) {
    n = parseFloat(n);
    if (isNaN(n)) return '—';
    if (n >= 1e9) return (n / 1e9).toFixed(1) + 'B';
    if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M';
    if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K';
    return String(Math.round(n));
  }

  function bandOf(score) {
    if (score >= 85) return 'green';
    if (score >= 65) return 'yellow';
    if (score >= 35) return 'red';
    return 'black';
  }

  function evIcon(type) {
    var map = {
      'PushEvent': '\uD83D\uDCE4', 'CreateEvent': '\u2728', 'IssuesEvent': '\uD83D\uDCCB',
      'PullRequestEvent': '\uD83D\uDC80', 'WatchEvent': '\u2B50', 'ForkEvent': '\uD83C\uDF89',
      'ReleaseEvent': '\uD83D\uDCE6', 'IssueCommentEvent': '\uD83D\uDCAC', 'CommitCommentEvent': '\uD83D\uDCDD',
    };
    return map[type] || '\u26A1';
  }

  function observeAndCountup(el2, target) {
    if (!el2 || !target) return;
    if (!_sharedIO) {
      _sharedIO = new IntersectionObserver(function (entries) {
        entries.forEach(function (en) {
          if (!en.isIntersecting) return;
          var num = parseFloat(en.target.dataset.nhwCountTarget);
          if (isNaN(num)) return;
          var start = performance.now();
          var dur = 1500;
          function tick(now) {
            var t = Math.min((now - start) / dur, 1);
            var eased = 1 - Math.pow(1 - t, 3);
            var val = num * eased;
            en.target.textContent = Number.isInteger(num) ? Math.round(val) : val.toFixed(1);
            if (t < 1) requestAnimationFrame(tick);
            else en.target.textContent = Number.isInteger(num) ? Math.round(num) : num.toFixed(1);
          }
          requestAnimationFrame(tick);
          _sharedIO.unobserve(en.target);
        });
      }, { threshold: 0.3 });
    }
    el2.dataset.nhwCountTarget = target;
    _sharedIO.observe(el2);
  }

  var _fetchCache = {};
  var _pendingFetch = {};
  var _fetchOrder = [];
  var _fetchFailures = {};
  var _fetchBackoffTimer = {};
  var _MAX_FETCH_CACHE = 20;
  var _MAX_BACKOFF_MS = 60000;

  function fetchJson(url, cb) {
    var token = _cfg.apiToken;

    if (_fetchCache[url] && Date.now() - _fetchCache[url].ts < 60000) {
      cb(_fetchCache[url].data);
    }

    if (_pendingFetch[url]) return;

    // If a backoff timer is already scheduled, don't schedule another
    if (_fetchBackoffTimer[url]) return;

    var failures = _fetchFailures[url] || 0;
    var backoffMs = Math.min(1000 * Math.pow(2, failures), _MAX_BACKOFF_MS);
    if (backoffMs > 1000) {
      var timerId = setTimeout(doFetch, backoffMs);
      _fetchBackoffTimer[url] = timerId;
      _timers.push(timerId);
      return;
    }
    doFetch();

    function doFetch() {
      delete _fetchBackoffTimer[url];
      if (_pendingFetch[url]) return;
      _pendingFetch[url] = true;
      fetch(url, { cache: 'no-store', headers: token ? { Authorization: 'Bearer ' + token } : {} })
        .then(function (r) {
          if (!r.ok) throw new Error('HTTP ' + r.status);
          return r.json();
        })
        .then(function (d) {
          delete _pendingFetch[url];
          _fetchFailures[url] = 0;
          if (d) {
            _fetchCache[url] = { data: d, ts: Date.now() };
            var idx = _fetchOrder.indexOf(url);
            if (idx !== -1) _fetchOrder.splice(idx, 1);
            _fetchOrder.push(url);
            while (_fetchOrder.length > _MAX_FETCH_CACHE) {
              var evict = _fetchOrder.shift();
              delete _fetchCache[evict];
            }
          }
          cb(d);
        })
        .catch(function () {
          delete _pendingFetch[url];
          _fetchFailures[url] = (_fetchFailures[url] || 0) + 1;
          cb(null);
        });
    }
  }

  function fetchGitHubEvents(repos, token, cb) {
    if (!repos || !repos.length) return cb([]);
    var all = [];
    var done = 0;
    repos.forEach(function (r) {
      var url = 'https://api.github.com/repos/' + r + '/events?per_page=10';
      fetch(url, { cache: 'no-store', headers: token ? { Authorization: 'Bearer ' + token } : {} })
        .then(function (res) { return res.ok ? res.json() : []; })
        .then(function (evts) {
          evts.forEach(function (e) {
            all.push({
              type: e.type,
              repo: e.repo.name,
              action: e.type.replace('Event', '').replace(/([A-Z])/g, ' $1').trim(),
              time: new Date(e.created_at).toLocaleDateString(),
              _ts: new Date(e.created_at).getTime(),
            });
          });
        })
        .catch(function () {})
        .finally(function () {
          done++;
          if (done === repos.length) {
            all.sort(function (a, b) { return b._ts - a._ts; });
            cb(all);
          }
        });
    });
  }

  /* ──────────────────────────────────────────────────────────────────────────
   * Public API
   * ────────────────────────────────────────────────────────────────────────── */
  root.NeohiroWidgets = {
    init: init,
    loadHeartbeat: loadHeartbeat,
    loadVisitorCounter: loadVisitorCounter,
    renderStatCard: renderStatCard,
    updateStatValue: updateStatValue,
    loadHealthStrip: loadHealthStrip,
    loadActivityFeed: loadActivityFeed,
    loadSocialCounters: loadSocialCounters,
    renderSparkline: renderSparkline,
    startSparkline: startSparkline,
    loadMilestones: loadMilestones,
    pulseRing: pulseRing,
    animateCount: animateCount,
    flashBump: flashBump,
    createSSE: createSSE,
    fmtCount: fmtCount,
    bandOf: bandOf,
    destroyAllTimers: destroyAllTimers,
  };

}(window));
