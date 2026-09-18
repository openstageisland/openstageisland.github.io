/* ─────────────────────────────────────────────────────────────────────
 * neohiro-network :: Universal cross-site UX module
 *   - AI assistant input bar (full width, dynamic cursor, typing indicator)
 *   - Conversation modal (sway-down, user/assistant bubbles, typing indicator)
 *   - Previous-button (cross-domain navigation back to last visited site)
 *   - Universal top-nav auth tabs (Login / Dashboard) — render-only hook
 *   - Starfield parallax background
 *   - Heart/Mouth heartbeat detection (API fetch with local classify fallback)
 *   - Stranger tracking (localStorage + neohiro:stranger event)
 *
 * Loaded by every site in the neohiro network. Self-contained.
 * ───────────────────────────────────────────────────────────────────── */
(function () {
  'use strict';

  var NEohiro = {
    NETWORK: ['neohiro.github.io', 'frenzypenguin-media.github.io', 'transhumanists.github.io', 'openstageisland.github.io'],
    PREV_KEY: 'neohiro.prev.v1',
    init: init
  };

  function init() {
    document.addEventListener('DOMContentLoaded', boot);
    if (document.readyState !== 'loading') boot();
  }

  function boot() {
    mountStarfield();
    mountPreviousButton();
    mountConversationModal();
    mountAssistantBar();
    fillAvatarSlots(document.body); // ai-dock chat avatar (site identity)
    injectNavAuth();
    detectStranger();
    wireInteractions();
    runDiagnostics();
  }

  /* ── Universal interaction wiring (ripples, tilt, reveal) ─── */
  function wireInteractions() {
    // Click ripple on any element with [data-ripple] or .btn-primary, .btn-secondary, .btn
    document.addEventListener('click', function (e) {
      const target = e.target.closest('[data-ripple], .btn-primary, .btn-secondary, .btn-themed, .cta-button, .cta-themed, .nav-link, .glide-card, .ai-conv__send, .tool-card, .guide-card, .community-card, .fpm-spotlight, .milestone-card, .feed-item');
      if (!target) return;
      const rect = target.getBoundingClientRect();
      if (rect.width === 0) return;
      const ripple = document.createElement('span');
      ripple.className = 'click-ripple';
      const size = Math.max(rect.width, rect.height) * 1.3;
      ripple.style.width = ripple.style.height = size + 'px';
      ripple.style.left = (e.clientX - rect.left - size / 2) + 'px';
      ripple.style.top = (e.clientY - rect.top - size / 2) + 'px';
      // Make sure target is positioned — avoid getComputedStyle (forces layout)
      // Check inline style first; only fall back to computed if needed.
      if (!target.style.position || target.style.position === 'static') {
        target.style.position = 'relative';
      }
      target.appendChild(ripple);
      setTimeout(() => ripple.remove(), 700);
    });

    // Card 3D tilt on .card-3d
    document.querySelectorAll('.card-3d').forEach(card => {
      card.addEventListener('mousemove', e => {
        const r = card.getBoundingClientRect();
        const x = (e.clientX - r.left) / r.width - 0.5;
        const y = (e.clientY - r.top) / r.height - 0.5;
        card.style.setProperty('--mx', (x * 12) + 'px');
        card.style.setProperty('--my', (y * 12) + 'px');
      });
      card.addEventListener('mouseleave', () => {
        card.style.setProperty('--mx', '0px');
        card.style.setProperty('--my', '0px');
      });
    });

    // Reveal-on-scroll for .reveal (auto-mark major sections)
    const auto = document.querySelectorAll('.section, .tool-card, .guide-card, .community-card, .milestone-card, .feature, .glide-card, .fpm-spotlight, .quote-card, .feature-card, .row-card, .step-card, .cta-card, .panel, .lesson-card, .ep-card, .ep-stream-card, .ep-tile, .post-card, .article-card, .commit-card, .metric-card');
    auto.forEach(el => el.classList.add('reveal'));
    if ('IntersectionObserver' in window) {
      const io = new IntersectionObserver(entries => {
        entries.forEach(entry => {
          if (entry.isIntersecting) {
            entry.target.classList.add('reveal-in');
            io.unobserve(entry.target);
          }
        });
      }, { threshold: 0.08, rootMargin: '0px 0px -8% 0px' });
      auto.forEach(el => io.observe(el));
    } else {
      auto.forEach(el => el.classList.add('reveal-in'));
    }

    // Animated orbs: randomize positions slightly
    try {
      document.documentElement.style.setProperty('--orb1-x', (10 + Math.random() * 20) + '%');
      document.documentElement.style.setProperty('--orb1-y', (10 + Math.random() * 25) + '%');
      document.documentElement.style.setProperty('--orb2-x', (60 + Math.random() * 30) + '%');
      document.documentElement.style.setProperty('--orb2-y', (50 + Math.random() * 35) + '%');
    } catch (_) {}
  }

  /* ── Starfield (parallax deep-space, 3 layers) ───────────── */
  function mountStarfield() {
    if (document.getElementById('starfield')) return;
    const s = document.createElement('div');
    s.id = 'starfield';
    s.className = 'starfield';
    s.setAttribute('aria-hidden', 'true');
    document.body.appendChild(s);

    // Parallax on scroll: shift the starfield at half speed
    let raf = 0;
    const onScroll = () => {
      if (raf) return;
      raf = requestAnimationFrame(() => {
        s.style.setProperty('--sy', (window.scrollY * 0.4) + 'px');
        raf = 0;
      });
    };
    window.addEventListener('scroll', onScroll, { passive: true });

    // Mouse parallax: rAF-throttled to avoid 100+ writes/sec on hi-DPI
    // trackpads. setProperty on a CSS custom property only invalidates
    // a style subtree, but coalescing to one frame is still ~5x cheaper.
    var mouseRaf = 0;
    var mouseX = 0, mouseY = 0;
    document.addEventListener('mousemove', function (e) {
      mouseX = e.clientX;
      mouseY = e.clientY;
      if (mouseRaf) return;
      mouseRaf = requestAnimationFrame(function () {
        mouseRaf = 0;
        s.style.setProperty('--mx', ((mouseX / window.innerWidth - 0.5) * 16) + 'px');
        s.style.setProperty('--my', ((mouseY / window.innerHeight - 0.5) * 16) + 'px');
      });
    });

    // Third ambient orb (pinky) — additive
    if (!document.querySelector('.ambient-orb')) {
      const orb = document.createElement('div');
      orb.className = 'ambient-orb';
      orb.setAttribute('aria-hidden', 'true');
      document.body.appendChild(orb);
    }
  }

  /* ── Cross-domain Previous button ─────────────────────────────── */
  function mountPreviousButton() {
    if (sessionStorage.getItem('neohiro.prev.skip') === '1') return;
    const last = readLast();
    if (!last) return;
    if (last.url === location.href) return;
    if (hostOf(last.url) === location.hostname) {
      // Same-origin: native back is more useful than this button.
      return;
    }

    const btn = document.createElement('a');
    btn.className = 'prev-btn';
    btn.href = last.url;
    btn.setAttribute('aria-label', `Back to ${last.label}`);
    btn.innerHTML = `
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" width="14" height="14" aria-hidden="true">
        <path d="M15 18l-6-6 6-6"/>
      </svg>
      <span class="prev-label">Back to ${escapeHtml(last.label)}</span>
      <span class="prev-host" aria-hidden="true">${escapeHtml(hostOf(last.url))}</span>
    `;
    btn.addEventListener('click', () => sessionStorage.setItem('neohiro.prev.skip', '1'));
    document.body.appendChild(btn);
  }

  function recordCurrent() {
    try {
      const existing = readLast();
      if (existing && existing.url === location.href) return; // already recorded
      sessionStorage.setItem(NEohiro.PREV_KEY, JSON.stringify({
        url: location.href,
        label: labelFor(location.hostname),
        ts: Date.now()
      }));
    } catch (_) {}
  }
  function readLast() {
    try {
      const raw = sessionStorage.getItem(NEohiro.PREV_KEY);
      if (!raw) return null;
      const v = JSON.parse(raw);
      if (!v || !v.url) return null;
      if (Date.now() - v.ts > 12 * 3600 * 1000) return null;
      return v;
    } catch (_) { return null; }
  }
  function hostOf(url) { try { return new URL(url).hostname; } catch (_) { return ''; } }
  function labelFor(host) {
    if (host.startsWith('transhumanists')) return 'transhumanists';
    if (host.startsWith('frenzypenguin'))   return 'FrenzyPenguin Media';
    if (host.startsWith('openstageisland')) return 'Open Stage Island';
    return 'neohiro';
  }
  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }

  /* ── Org avatar (site identity) ───────────────────────────────────
   * Every site in the neohiro network shows its own avatar in the
   * assistant conversation and the AI dock. The self-hosted profile.png
   * is preferred where it exists (neohiro/frenzypenguin enforce
   * `img-src 'self'`), otherwise the GitHub org avatar URL is used
   * (transhumanists/openstageisland allow https:). */
  var SITE_AVATAR = (function () {
    var host = (location.hostname || '').toLowerCase();
    if (host.indexOf('frenzypenguin') === 0)    return '/assets/profile.png';
    if (host.indexOf('transhumanists') === 0)   return 'https://github.com/transhumanists.png';
    if (host.indexOf('openstageisland') === 0)  return 'https://github.com/openstageisland.png';
    if (host.indexOf('neohiro') === 0)          return '/assets/profile.png';
    return '/assets/profile.png';
  })();

  function buildAvatarImg(cls) {
    var img = document.createElement('img');
    img.className = cls || 'ai-avatar-img';
    img.src = SITE_AVATAR;
    img.alt = '';
    img.loading = 'lazy';
    img.decoding = 'async';
    img.setAttribute('aria-hidden', 'true');
    img.onerror = function () { if (img.parentNode) img.parentNode.removeChild(img); };
    return img;
  }

  // Injects the org avatar into every assistant avatar slot + the
  // conversation header brand. The slot's existing glyph (✦ / 🤖) stays
  // underneath as a graceful offline fallback: if the image errors out it
  // is removed and the glyph + tinted circle remain.
  function fillAvatarSlots(root) {
    if (!root || typeof root.querySelectorAll !== 'function') return;
    Array.prototype.forEach.call(root.querySelectorAll('.ai-conv__avatar, .ai-dock__chat-avatar'), function (slot) {
      if (!slot || slot.querySelector('img')) return;
      slot.appendChild(buildAvatarImg());
    });
    Array.prototype.forEach.call(root.querySelectorAll('.ai-conv__brand'), function (brand) {
      if (brand.querySelector('.ai-conv__brand-avatar')) return;
      brand.insertBefore(buildAvatarImg('ai-conv__brand-avatar ai-avatar-img'), brand.firstChild);
    });
  }

  function showToast(msg, duration) {
    if (document.getElementById('neohiro-toast')) return;
    var el = document.createElement('div');
    el.id = 'neohiro-toast';
    el.setAttribute('role', 'status');
    el.setAttribute('aria-live', 'polite');
    el.textContent = msg;
    Object.assign(el.style, {
      position: 'fixed', bottom: '120px', left: '50%', transform: 'translateX(-50%)',
      zIndex: '9999', padding: '10px 20px',
      background: 'var(--bg-elevated, #161e26)',
      border: '1px solid var(--accent, #7c4dff)',
      borderRadius: '999px', color: 'var(--fg, #eceff1)',
      fontFamily: 'var(--font-ui, system-ui, sans-serif)',
      fontSize: '0.85rem', fontWeight: '600',
      boxShadow: '0 8px 24px rgba(0,0,0,0.5)',
      pointerEvents: 'none', whiteSpace: 'nowrap',
      animation: 'neohiroToastIn 0.3s ease both'
    });
    document.body.appendChild(el);
    var ms = duration || 3000;
    var outTid = setTimeout(function () {
      el.style.animation = 'neohiroToastOut 0.3s ease both';
      setTimeout(function () { if (el.parentNode) el.remove(); }, 300);
    }, ms);
    // Cancel the timer if the page is hiding (back/forward cache, navigation)
    // so the queued work doesn't fire on a no-longer-attached element.
    var onHide = function () {
      clearTimeout(outTid);
      if (el.parentNode) el.remove();
    };
    window.addEventListener('pagehide', onHide, { once: true });
    document.addEventListener('visibilitychange', function () {
      if (document.visibilityState === 'hidden') onHide();
    }, { once: true });
  }

  /* ── Conversation modal (sway-down, bubbles, typing indicator) ── */
  // Built hidden on first AI-bar mount; activated on submit.
  // Animates down from the AI bar, displays the user's query as a bubble,
  // then a typing indicator while Heart/Mouth is queried for a reply.
  function mountConversationModal() {
    if (document.getElementById('ai-conv')) return;
    const modal = document.createElement('div');
    modal.className = 'ai-conv hidden';
    modal.id = 'ai-conv';
    modal.setAttribute('role', 'dialog');
    modal.setAttribute('aria-modal', 'false');
    modal.setAttribute('aria-label', 'Conversation with the neohiro assistant');
    modal.innerHTML = `
      <div class="ai-conv__chrome">
        <div class="ai-conv__header">
          <span class="ai-conv__brand">
            <span class="ai-conv__pulse" aria-hidden="true"></span>
            neohiro assistant
          </span>
          <span class="ai-conv__heart" id="ai-conv__heart" aria-live="polite" title="Heart status">
            <span class="ai-conv__heart-dot" aria-hidden="true"></span>
            <span id="ai-conv__heart-text">connecting…</span>
          </span>
          <button type="button" class="ai-conv__close" id="ai-conv__close" aria-label="Close conversation">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18" aria-hidden="true">
              <path d="M6 6l12 12M18 6L6 18"/>
            </svg>
          </button>
        </div>
        <div class="ai-conv__messages" id="ai-conv__messages" role="log" aria-live="polite">
          <div class="ai-conv__msg ai-conv__msg--assistant">
            <div class="ai-conv__avatar" aria-hidden="true">✦</div>
            <div class="ai-conv__bubble">
              Hey — I'm the neohiro assistant. I run across all 4 network sites and
              learn more about what you ask, so I can route you faster next time.
            </div>
          </div>
        </div>
        <div class="ai-conv__typing hidden" id="ai-conv__typing" role="status" aria-live="polite">
          <div class="ai-conv__avatar" aria-hidden="true">✦</div>
          <div class="ai-conv__bubble ai-conv__bubble--typing">
            <span class="ai-conv__dots" aria-hidden="true"><span></span><span></span><span></span></span>
            <span id="ai-conv__typing-text">Mouth is composing your reply…</span>
          </div>
        </div>
        <div class="ai-conv__footer">
          <span class="ai-conv__notice">We collect information so we can learn more about you</span>
          <a class="ai-conv__privacy" href="https://neohiro.github.io/privacy/" rel="noopener" target="_blank">Privacy</a>
        </div>
      </div>
    `;
    document.body.appendChild(modal);
    fillAvatarSlots(modal); // org avatar in conversation header + welcome bubble
    // Close handlers
    document.getElementById('ai-conv__close').addEventListener('click', hideConversationModal);
    // Esc to close (handler is page-singleton; no leak)
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && isConvOpen()) hideConversationModal();
    });
    // Tab focus trap: keep focus inside the modal while open
    document.addEventListener('keydown', (e) => {
      if (e.key !== 'Tab' || !isConvOpen()) return;
      var focusables = modal.querySelectorAll(
        'a[href], button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])'
      );
      if (focusables.length === 0) return;
      var first = focusables[0];
      var last = focusables[focusables.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    });
    // Click outside the chrome closes the modal too
    modal.addEventListener('click', (e) => {
      if (e.target === modal) hideConversationModal();
    });
  }

  function isConvOpen() {
    const m = document.getElementById('ai-conv');
    return m && !m.classList.contains('hidden');
  }

  var _prevFocus = null;
  var _closeTid = 0;

  function showConversationModal() {
    var m = document.getElementById('ai-conv');
    if (!m) return;
    // Cancel any in-flight close-timer from a prior hide; otherwise its
    // 240ms callback will fire `m.classList.add('hidden')` on the now-open
    // modal and yank it out of view.
    if (_closeTid) { clearTimeout(_closeTid); _closeTid = 0; }
    m.classList.remove('hidden', 'ai-conv--closing');
    _prevFocus = document.activeElement;
    void m.offsetWidth;
    m.classList.add('ai-conv--open');
    m.setAttribute('aria-modal', 'true');
    // Focus first focusable element inside the modal chrome.
    var first = m.querySelector('input, textarea, button, [tabindex]:not([tabindex="-1"])');
    if (first) first.focus();
    else m.focus();
  }

  function hideConversationModal() {
    var m = document.getElementById('ai-conv');
    if (!m) return;
    m.classList.remove('ai-conv--open');
    m.classList.add('ai-conv--closing');
    if (_closeTid) clearTimeout(_closeTid);
    _closeTid = setTimeout(function () {
      _closeTid = 0;
      m.classList.add('hidden');
      m.classList.remove('ai-conv--closing');
    }, 240);
    m.setAttribute('aria-modal', 'false');
    // Restore focus to the element that was active before the modal opened.
    // Guard: the original element may have been removed from the DOM
    // (e.g. a card that got re-rendered). Only restore if still focusable.
    if (_prevFocus && _prevFocus.isConnected && typeof _prevFocus.focus === 'function') {
      try { _prevFocus.focus(); } catch (_) {}
    }
    _prevFocus = null;
  }

  function appendConvMessage(role, md) {
    const box = document.getElementById('ai-conv__messages');
    if (!box) return;
    // Validate role — only 'user' or 'assistant' allowed to prevent CSS injection via className
    var safeRole = (role === 'user' || role === 'assistant') ? role : 'assistant';
    const row = document.createElement('div');
    row.className = 'ai-conv__msg ai-conv__msg--' + (safeRole === 'user' ? 'user' : 'assistant');
    if (safeRole === 'user') {
      // User text is always escaped — no markdown/HTML allowed.
      const safe = escapeHtml(String(md));
      row.innerHTML = `<div class="ai-conv__bubble">${safe}</div>`;
    } else {
      // Assistant markdown comes from classify() (trusted) or Mouth API (future).
      // Render via safe markdown→DOM (no HTML passthrough). For Mouth API responses
      // that might contain raw HTML, fall back to renderSafeHtml.
      var safeHtml;
      if (typeof md === 'string' && /[#*_`\[\]]/.test(md)) {
        safeHtml = renderMarkdown(md);
      } else {
        safeHtml = renderSafeHtml(md);
      }
      row.innerHTML = `
        <div class="ai-conv__avatar" aria-hidden="true">✦</div>
        <div class="ai-conv__bubble">${safeHtml}</div>
      `;
    }
    box.appendChild(row);
    fillAvatarSlots(row); // org avatar on assistant replies
    box.scrollTop = box.scrollHeight;
  }

  // ── Safe HTML renderer ──────────────────────────────────────────
  // Parses `html` with DOMParser (safe, no execution), then walks the
  // tree and returns a sanitized string. Strips:
  //   - All tags except: p b i a div span br strong em ul ol li
  //   - All attributes except: href (whitelisted scheme), target (whitelisted), class (allowlisted prefixes)
  //   - All on* event handlers (onerror, onclick, onload …)
  //   - javascript:, data:, vbscript: URL schemes (with leading whitespace
  //     and HTML-encoded prefixes to defeat obfuscation)
  //   - id attributes (would collide with page IDs and CSS)
  // Notes:
  //   - rel="noopener nofollow" is added programmatically for external https: links
  //   - class attribute values must match ALLOWED_CLASS_PREFIXES (ai-step, ai-conv, ai-bar, role-badge + BEM modifiers)
  // Falls back to plain-text escape if DOMParser is unavailable.
  var ALLOWED_TAGS = {'p':1,'b':1,'i':1,'a':1,'div':1,'span':1,'br':1,'strong':1,'em':1,'ul':1,'ol':1,'li':1};
  var ALLOWED_ATTRS = {'href':1,'target':1};
  // Only allow the ai-step / ai-conv namespaced classes that classify() emits.
  // Reject all other class values to prevent Mouth from injecting arbitrary
  // CSS that could break page layout or override host-site styles.
  // Matches exact class token: "ai-step" or "ai-step other-class" but NOT "ai-step-malicious"
  var ALLOWED_CLASS_PREFIXES = ['ai-step','ai-conv','ai-bar','role-badge'];
  var _allowedClassRx = null;  // lazily built RegExp
  function _allowClass(v) {
    if (!_allowedClassRx) {
      // Each class token must be exactly one of the allowed prefixes, optionally followed by --modifier (BEM)
      // e.g., "ai-step", "ai-step--large", "role-badge role-badge--godadmin"
      // but NOT "ai-step-malicious" or "ai-step evil"
      var tokenPattern = '(' + ALLOWED_CLASS_PREFIXES.map(function (p) { return p.replace('-', '\\-') + '(?:--[a-z0-9-]+)?'; }).join('|') + ')';
      _allowedClassRx = new RegExp('^' + tokenPattern + '(?:\\s+' + tokenPattern + ')*$');
    }
    return _allowedClassRx.test(v);
  }
  // Strip leading whitespace, control chars, and HTML-encoded NULL bytes
  // that some browsers strip before evaluation but only after the regex test
  // would have already run on the raw attribute value.
  function _trimHref(v) {
    return String(v).replace(/[\s\x00-\x1F]+/g, '').replace(/&#x?[0-9a-fA-F]+;?/g, '');
  }
  function _isSafeUrl(v) {
    var t = _trimHref(v);
    if (!t) return false;
    if (/^(javascript|data|vbscript|file):/i.test(t)) return false;
    return /^(https?:|mailto:|\/|#|\?)/i.test(t) || /^[a-z0-9._~!$&'()*+,;=:@\/?%#-]+$/i.test(t);
  }

  // ── Markdown → DOM renderer (safe, no HTML passthrough) ────────────────
// Renders a trusted markdown subset used by classify() and Mouth.
// Supported: paragraphs, **bold**, *italic*, `code`, [links](url),
// unordered lists (- item), ordered lists (1. item), step blocks
// (:::step\n**Title**\nContent\n:::) which become .ai-step with .n badge.
function renderMarkdown(md) {
  var str = String(md || '').trim();
  if (!str) return '';

  // Split into blocks (blank-line separated)
  var blocks = str.split(/\n\s*\n/);
  var frag = document.createDocumentFragment();

  blocks.forEach(function (block) {
    block = block.trim();
    if (!block) return;

    // Step block: :::step\n**Title**\nBody\n:::
    // Closing delimiter must be exactly ::: on its own line (or :::step-end)
    if (/^:::step\b/.test(block)) {
      var lines = block.split('\n');
      var endIdx = lines.findIndex(function (l, i) { return i > 0 && /^:::(?:step-end)?\s*$/i.test(l.trim()); });
      var contentLines = (endIdx > 0) ? lines.slice(1, endIdx) : lines.slice(1);
      var stepHtml = contentLines.join('\n').trim();
      var stepEl = document.createElement('div');
      stepEl.className = 'ai-step';
      // Render inline markdown inside the step
      stepEl.innerHTML = renderInline(stepHtml);
      frag.appendChild(stepEl);
      return;
    }

    // Ordered list: 1. item / 2. item
    if (/^\d+\.\s/.test(block)) {
      var ol = document.createElement('ol');
      block.split('\n').forEach(function (line) {
        var m = line.match(/^\d+\.\s+(.*)$/);
        if (m) {
          var li = document.createElement('li');
          li.innerHTML = renderInline(m[1]);
          ol.appendChild(li);
        }
      });
      frag.appendChild(ol);
      return;
    }

    // Unordered list: - item
    if (/^-\s/.test(block)) {
      var ul = document.createElement('ul');
      block.split('\n').forEach(function (line) {
        var m = line.match(/^-\s+(.*)$/);
        if (m) {
          var li = document.createElement('li');
          li.innerHTML = renderInline(m[1]);
          ul.appendChild(li);
        }
      });
      frag.appendChild(ul);
      return;
    }

    // Regular paragraph
    var p = document.createElement('p');
    p.innerHTML = renderInline(block);
    frag.appendChild(p);
  });

  // Serialize back to string
  var tmp = document.createElement('div');
  tmp.appendChild(frag);
  return tmp.innerHTML;
}

// Inline markdown renderer (no block elements)
  // Handles: **bold**, *italic*, `code`, [text](url)
  // Strategy: tokenize by markdown patterns, escape plain text, keep tokens.
  function renderInline(text) {
    var str = String(text);
    if (!str) return '';

    // Token types: LINK, BOLD, ITALIC, CODE, TEXT
    var tokens = [];
    var pos = 0;

    // Regex for all inline patterns (ordered by precedence)
    var patterns = [
      { type: 'LINK',    re: /\[([^\]]+)\]\(([^)]+)\)/ },
      { type: 'BOLD',    re: /\*\*([^\*]+)\*\*/ },
      { type: 'ITALIC',  re: /\*([^\*]+)\*/ },
      { type: 'CODE',    re: /`([^`]+)`/ }
    ];

    while (pos < str.length) {
      var match = null;
      var matchType = null;
      var matchIndex = -1;

      // Find earliest match among all patterns
      patterns.forEach(function (p) {
        var m = str.slice(pos).match(p.re);
        if (m && (matchIndex === -1 || m.index < matchIndex)) {
          match = m;
          matchType = p.type;
          matchIndex = m.index;
        }
      });

      if (match) {
        // Text before match
        if (match.index > 0) {
          tokens.push({ type: 'TEXT', content: str.slice(pos, pos + match.index) });
        }
        // The match
        if (matchType === 'LINK') {
          var label = match[1];
          var url = match[2];
          var safe = _isSafeUrl(url) ? _trimHref(url) : '#';
          tokens.push({ type: 'LINK', label: label, url: safe });
        } else {
          tokens.push({ type: matchType, content: match[1] });
        }
        pos += match.index + match[0].length;
      } else {
        // No more matches - rest is plain text
        tokens.push({ type: 'TEXT', content: str.slice(pos) });
        break;
      }
    }

    // Render tokens
    return tokens.map(function (t) {
      switch (t.type) {
        case 'LINK':
          return '<a href="' + escapeHtml(t.url) + '" target="_blank" rel="noopener nofollow">' + escapeHtml(t.label) + '</a>';
        case 'BOLD':
          return '<b>' + escapeHtml(t.content) + '</b>';
        case 'ITALIC':
          return '<i>' + escapeHtml(t.content) + '</i>';
        case 'CODE':
          return '<code>' + escapeHtml(t.content) + '</code>';
        case 'TEXT':
        default:
          return escapeHtml(t.content);
      }
    }).join('');
  }

function renderSafeHtml(html) {
    var str = String(html || '');
    if (!str || !/<[a-z]/i.test(str)) return escapeHtml(str);
    try {
      var dp = new DOMParser();
      var doc = dp.parseFromString('<!DOCTYPE html><div xmlns="http://www.w3.org/1999/xhtml">' + str + '</div>', 'application/xhtml+xml');
      var frag = document.createDocumentFragment();
      function walk(n) {
        if (n.nodeType === 3) {
          frag.appendChild(n.cloneNode(false));
          return;
        }
        if (n.nodeType !== 1) return;
        var tag = n.nodeName.toLowerCase();
        if (!ALLOWED_TAGS[tag]) {
          // Non-allowed tag: recurse into children but don't emit the tag.
          Array.prototype.forEach.call(n.childNodes, walk);
          return;
        }
        var el = document.createElement(tag);
        // Copy only allowed attributes; drop event handlers and bad URL schemes.
        Array.prototype.forEach.call(n.attributes, function (attr) {
          var an = attr.name.toLowerCase();
          if (!ALLOWED_ATTRS[an]) return;
          // Defense against namespace confusion: any attribute starting with
          // "on" is an event handler regardless of prefix.
          if (an.indexOf('on') === 0) return;
          var av = attr.value;
          if (an === 'href') {
            if (!_isSafeUrl(av)) return;
            if (/^https?:\/\//i.test(av)) el.setAttribute('rel', 'noopener nofollow');
          }
          if (an === 'class') {
            if (!_allowClass(av)) return;
          }
          if (an === 'target' && !/^(_blank|_self|_parent|_top)$/i.test(av)) return;
          el.setAttribute(an, av);
        });
        Array.prototype.forEach.call(n.childNodes, walk);
        frag.appendChild(el);
      }
      Array.prototype.forEach.call(doc.documentElement.childNodes, walk);
      // Serialize the sanitized fragment back to HTML string.
      var tmp = document.createElement('div');
      tmp.appendChild(frag);
      return tmp.innerHTML;
    } catch (_) {
      // DOMParser unavailable (unlikely) — fall back to escaping all HTML.
      return escapeHtml(str);
    }
  }

  function setConvTyping(on, text) {
    const t = document.getElementById('ai-conv__typing');
    if (!t) return;
    t.classList.toggle('hidden', !on);
    if (on && text) {
      const span = document.getElementById('ai-conv__typing-text');
      if (span) span.textContent = text;
    }
    const box = document.getElementById('ai-conv__messages');
    if (box) box.scrollTop = box.scrollHeight;
  }

  function setConvHeart(state, text) {
    const wrap = document.getElementById('ai-conv__heart');
    const dot  = wrap && wrap.querySelector('.ai-conv__heart-dot');
    const span = document.getElementById('ai-conv__heart-text');
    if (!wrap) return;
    // Validate state — only known states allowed to prevent arbitrary class injection
    var validStates = ['ai-conv__heart--up', 'ai-conv__heart--down', 'ai-conv__heart--probe'];
    var safeState = (state && validStates.indexOf(state) !== -1) ? state : '';
    wrap.classList.remove('ai-conv__heart--up', 'ai-conv__heart--down', 'ai-conv__heart--probe');
    if (safeState) wrap.classList.add(safeState);
    if (span && text) span.textContent = text;
  }

  /* ── Heart/Mouth heartbeat detection ─────────────────────────── */
  // Probes a well-known heart-endpoint to decide whether the body is online.
  // Falls back to local classify() if Heart is unreachable. This is the
  // "goes through heartbeat detection" wire you asked for.
  const HEART_ENDPOINTS = [
    'https://neohiro.github.io/.well-known/heartbeat',
    'https://neohiro.github.io/heartbeats/health.json'
  ];
  const MOUTH_ENDPOINT = 'https://neohiro.github.io/.well-known/ask';
  let _heartUp = null;
  let _heartProbed = false;

  function fetchWithTimeout(url, opts, ms) {
    var ctrl = typeof AbortController !== 'undefined' ? new AbortController() : null;
    var signal = ctrl ? ctrl.signal : null;
    var tid = setTimeout(function () { if (ctrl) ctrl.abort(); }, ms);
    return fetch(url, Object.assign({}, opts || {}, { signal: signal }))
      .finally(function () { clearTimeout(tid); });
  }

  function probeHeart() {
    if (_heartProbed) return Promise.resolve(_heartUp);
    _heartProbed = true;
    setConvHeart('ai-conv__heart--probe', 'probing heart…');
    // Try each endpoint in sequence until one succeeds
    return HEART_ENDPOINTS.reduce(function (promise, url) {
      return promise.catch(function () {
        return fetchWithTimeout(url, { cache: 'no-store', mode: 'cors' }, 8000)
          .then(function (r) { return r && r.ok; });
      });
    }, Promise.reject(new Error('no endpoints')))
      .then(function (up) { _heartUp = up; return up; })
      .catch(function () { _heartUp = false; return false; })
      .then(function (up) {
        setConvHeart(up ? 'ai-conv__heart--up' : 'ai-conv__heart--down',
                     up ? 'heart online' : 'heart offline (local brain)');
        return up;
      });
  }

  function fetchMouthReply(q) {
    return fetchWithTimeout(
      MOUTH_ENDPOINT + '?q=' + encodeURIComponent(q),
      { cache: 'no-store', mode: 'cors' },
      10000
    )
      .then(function (r) { if (!r.ok) throw new Error('Mouth HTTP ' + r.status); return r.json(); })
      .then(function (j) { return j && (j.reply || j.answer || j.text) || null; })
      .catch(function () { return null; });
  }

  function detectStranger() {
    try {
      const KEY = 'neohiro.visitor.v1';
      const raw = localStorage.getItem(KEY);
      if (raw) {
        const v = JSON.parse(raw);
        if (v && v.firstSeen) return; // not new
      }
      const stamp = {
        firstSeen: new Date().toISOString(),
        host: location.hostname,
        path: location.pathname,
        ref: document.referrer || null,
        ua: (navigator.userAgent || '').slice(0, 200)
      };
      localStorage.setItem(KEY, JSON.stringify(stamp));
      window.dispatchEvent(new CustomEvent('neohiro:stranger', { detail: stamp }));
    } catch (_) { /* private mode etc. */ }
  }

  /* ── AI assistant input bar (full width) ──────────────────────── */
  function mountAssistantBar() {
    if (document.getElementById('ai-bar')) return;

    recordCurrent(); // register this page for the cross-domain back button

    const wrap = document.createElement('div');
    wrap.className = 'ai-bar';
    wrap.id = 'ai-bar';
    wrap.setAttribute('role', 'region');
    wrap.setAttribute('aria-label', 'Ask the neohiro assistant');
    wrap.innerHTML = `
      <div class="ai-bar__inner">
        <span class="ai-bar__hint" aria-hidden="true">ask anything · reports · repo discovery · guided tours</span>
        <form class="ai-bar__form" id="ai-bar__form" autocomplete="off">
          <span class="ai-bar__icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="20" height="20">
              <path d="M12 2L9 8l-6 1 4.5 4.5L6 20l6-3.5L18 20l-1.5-6.5L21 9l-6-1z"/>
            </svg>
          </span>
          <input
            id="ai-bar__input"
            class="ai-bar__input"
            type="text"
            name="q"
            placeholder="Ask the neohiro assistant — find a repo, report a bug, get a guide, or describe what you need…"
            aria-label="Ask the neohiro assistant"
            maxlength="600" />
          <button type="submit" class="ai-bar__send" id="ai-bar__send" aria-label="Send message">
            <span>Send</span>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14" aria-hidden="true">
              <path d="M5 12h14M12 5l7 7-7 7"/>
            </svg>
          </button>
        </form>
        <div class="ai-bar__typing hidden" id="ai-bar__typing" role="status" aria-live="polite">
          <span class="ai-bar__dots" aria-hidden="true"><span></span><span></span><span></span></span>
          <span id="ai-bar__typing-text">Mouth is composing your reply…</span>
        </div>
        <div class="ai-bar__response hidden" id="ai-bar__response" role="region" aria-live="polite"></div>
        <div class="ai-bar__counter" id="ai-bar__counter" aria-live="off" aria-atomic="true">0 / 600</div>
      </div>
    `;

    // Insert into hero-content if present (hero middle), otherwise fall back to body
    const heroContent = document.querySelector('.hero-content');
    if (heroContent) {
      heroContent.appendChild(wrap);
    } else {
      document.body.appendChild(wrap);
    }

    // Add bottom padding so the bar doesn't cover content (idempotent)
    if (!document.documentElement.style.getPropertyValue('--ai-bar-pad')) {
      document.documentElement.style.setProperty('--ai-bar-pad', '110px');
      document.documentElement.style.paddingBottom = 'var(--ai-bar-pad)';
    }

    const form = document.getElementById('ai-bar__form');
    const input = document.getElementById('ai-bar__input');
    const counter = document.getElementById('ai-bar__counter');
    form.addEventListener('submit', onAsk);
    // Live char counter: shows how much is left so users self-correct
    // before hitting the 600-char cap and getting a silent truncation.
    function updateCounter() {
      var n = input.value.length;
      counter.textContent = n + ' / 600';
      counter.classList.toggle('ai-bar__counter--near', n >= 540);
      counter.classList.toggle('ai-bar__counter--over', n > 600);
    }
    input.addEventListener('input', updateCounter);
    updateCounter();
    // Cute dynamic cursor: shift placeholder text on focus/blur
    const placeholders = [
      'Ask the neohiro assistant — find a repo, report a bug, get a guide, or describe what you need…',
      'Try: “harden my Windows laptop in 5 minutes”',
      'Try: “show me encryption tools”',
      'Try: “report a bug in Cripple-NetStrip”',
      'Try: “take me to the world map dashboard”',
      'Try: “how do I file a security advisory?”'
    ];
    let pIdx = 0;
    input.addEventListener('focus', () => {
      if (!input.value) {
        pIdx = (pIdx + 1) % placeholders.length;
        input.placeholder = placeholders[pIdx];
      }
    });
  }

  // ── In-flight state (singleton guards) ──
  let _inFlightInt = null;
  let _inFlightTO  = null;
  let _inFlightVer = 0;

  // Cancel any pending AI work on page nav. Bumps _inFlightVer so pending
  // .then() callbacks short-circuit DOM writes; clears the timer + interval
  // so they don't fire on a detached page (browsers usually suppress this,
  // but bfcache restoration can re-run them).
  function _cancelInFlight() {
    if (_inFlightTO) { clearTimeout(_inFlightTO); _inFlightTO = null; }
    if (_inFlightInt) { clearInterval(_inFlightInt); _inFlightInt = null; }
    _inFlightVer++;  // invalidate any in-flight .then() guards
  }
  window.addEventListener('pagehide', _cancelInFlight);

  function onAsk(e) {
    e.preventDefault();
    const input = document.getElementById('ai-bar__input');
    const raw = input.value;
    // Sanitize: strip C0/C1 control chars (incl. \0, \r, \v, \f, ESC) and
    // collapse runs of whitespace. Defends against:
    //   - zero-width / RTL-override chars spoofing intent
    //   - tab/CR injection into the classify() regex subject
    //   - log-spamming via \b\b\b or terminal escapes
    const q = raw.replace(/[\u0000-\u001F\u007F-\u009F\u200B-\u200F\u202A-\u202E\u2066-\u2069]+/g, ' ').replace(/\s+/g, ' ').trim();
    if (!q) { input.focus(); return; }
    if (q.length > 600) {
      // Truncate — the live counter already warned at 540+ (amber) and 600+ (red).
      // No toast needed; user self-corrects before submit.
      input.value = q.slice(0, 600);
      input.focus();
      return;
    }

    // If already processing, ignore rapid resubmit (prevents leak + race)
    if (_inFlightTO) return;

    const wrap = document.getElementById('ai-bar');
    wrap.classList.add('ai-bar--sent');
    input.setAttribute('aria-busy', 'true');
    input.disabled = true;

    // ── Step 1: show the conversation modal ─────────────────────
    showConversationModal();
    appendConvMessage('user', q);
    input.value = '';
    // Reset char counter (stale after programmatic clear; updateCounter()
    // lives in mountAssistantBar's closure so we write directly).
    var ctr = document.getElementById('ai-bar__counter');
    if (ctr) { ctr.textContent = '0 / 600'; ctr.className = 'ai-bar__counter'; }

    // ── Step 2: probe Heart while typing indicator starts ─────────
    probeHeart();

    const cycle = [
      'Mouth is reading your question…',
      'Triage: identifying who you are and what you need…',
      'Pulling the right repo / docs / step-by-step…',
      'Composing a helpful reply…'
    ];
    const myVer = ++_inFlightVer;
    let c = 0;
    setConvTyping(true, cycle[0]);
    _inFlightInt = setInterval(() => {
      if (myVer !== _inFlightVer) return;
      c = (c + 1) % cycle.length;
      setConvTyping(true, cycle[c]);
    }, 900);

    // ── Step 3: fetch from Heart/Mouth → fall back to local classify ─
    const delay = 1500 + Math.random() * 600;
    _inFlightTO = setTimeout(() => {
      _inFlightInt && clearInterval(_inFlightInt);
      _inFlightInt = null;
      _inFlightTO = null;
      if (myVer !== _inFlightVer) return;

      setConvTyping(false);
      const reply = fetchMouthReply(q)
        .then(mouthText => mouthText || classify(q))
        .catch(() => classify(q));

      reply.then(replyHtml => {
        if (myVer !== _inFlightVer) return;
        appendConvMessage('assistant', replyHtml);
        input.removeAttribute('aria-busy');
        input.disabled = false;
        wrap.classList.remove('ai-bar--sent');
        input.focus();
      });
    }, delay);
  }

  function classify(q) {
    const t = q.toLowerCase();
    // Word-boundary anchored patterns to avoid false positives like
    //   "I have a security issue"  → NOT harden
    //   "stream of consciousness"  → NOT media hub
    //   "world map" css layout     → still matches dashboard
    // Each branch is ordered by specificity (most specific first).
    const isBugSec = /(security\s+(vuln|issue|advisory|advisories|disclosure|bug)|cve|advisory|vulnerability|exploit|disclosure)/.test(t);
    const isBug    = /(\bbug|\bissue|\bcrash|\bbroken\b|broken\s*link|not\s*working|stopped\s*working|throws?\s+an?\s+error|\berror\s+when)/.test(t);
    const isReport = /(\breport\b|file\s+(a|an|the|this|my)?\s*(bug|issue|advisory|cve|security)|open\s+a\s+ticket|submit\s+(a|an|the|this|my)?\s*(report|bug|issue|advisory|advisories|disclosure))/i.test(t);
    const isHard   = /(harden|hardening|hardened|secure\s+(windows|linux|ubuntu|debian|server|laptop|system|machine)|stig|baseline\s+(config|hardening|security)|lockdown|defend\s+against|mitigat(e|ion))/i.test(t);
    const isDash   = /(dashboard|world\s*map|worldmap|metrics?|chart|graph|gauge)/i.test(t);
    const isMedia  = /(video(\s+(tutorial|guide|deep[-\s]*dive))?|media\s*hub|youtube|frenzypenguin|stream(ing)?\s+(live|server|music|video))/i.test(t);
    const isSponsor = /(sponsor|donate|patreon|fund(ing|raise)?|support\s+(this|the|a|our|your)\s*(project|team|developers|creator|channel)|tip\s+jar)/i.test(t);
    const isRepo   = /(repo|repository|which\s+tool|find\s+(a|me|the|an?)\s+(tool|app|software|repo)|looking\s+for\s+(a|an?)\s+(tool|app|software|repo|replacement|alternative))/i.test(t);
    const isOS     = /(linux|ubuntu|debian|arch|fedora|rhel|suse|manjaro|windows|mac\s*os|osx)/i.test(t);

    if (isBugSec || (isBug && /(security|secure|vuln|advisory|cve)/.test(t))) {
      return stepsForBug();
    }
    // Bug takes priority over report (more specific intent signal).
    if (isBug || isReport) {
      return stepsForBug();
    }
    // Hardening: requires both harden intent AND an OS keyword.
    if (isHard) {
      if (isOS) return stepsForHardening(t);
      // STIG without explicit OS -> assume Linux (STIG is Linux-specific baseline)
      if (/\bstig\b/i.test(t)) return stepsForHardening('linux ' + t);
    }
    if (isDash) {
      return `
**Dashboard** — live ops, world map, and metrics are at the central neohiro dashboard.

:::step
**Step 1** — [Open the dashboard](https://neohiro.github.io/dashboard/)
:::
:::step
**Step 2** — switch to the World Map panel
:::
:::step
**Step 3** — pin the categories you care about
:::

If you want to see heartbeats for the org, open [/heartbeats/](https://neohiro.github.io/heartbeats/) (public/authed/godadmin tiers).
      `.trim();
    }
    if (isMedia) {
      return `
**Media hub:** [FrenzyPenguin Media](https://neohiro.github.io/media/) — video deep-dives on hardening, exploit mitigation, and privacy engineering.

**YouTube:** [@FrenzyPenguinMedia](https://www.youtube.com/FrenzyPenguinMedia?sub_confirmation=1)
      `.trim();
    }
    if (isSponsor) {
      return `
Thanks for considering support — every bit keeps the tools free and telemetry-free.

- [Sponsor on GitHub](https://github.com/sponsors/neohiro)
- [Patreon](https://www.patreon.com/frenzypenguin_media)
- [Linktree](https://linktr.ee/frenzypenguin.media)
      `.trim();
    }
    if (isRepo) {
      return stepsForRepo();
    }
    // Default helpful response
    return `
Got it — I can help you with that. To give you the most useful answer, tell me one of these:

:::step
**1** — *"I'm looking for a tool to…"* — e.g. harden Windows, encrypt DNS, monitor a server. I'll match you to the right repo.
:::
:::step
**2** — *"I found a bug / want to report a security issue"* — I'll walk you to the right repo and pre-fill the issue template.
:::
:::step
**3** — *"Take me to the dashboard / world map / media hub / sponsors"* — instant cross-site navigation.
:::
    `.trim();
  }

  function stepsForBug() {
    return `
**Bug / Issue report** — I'll route you to the right repo and pre-fill diagnostics. Pick the project below:

:::step
**1** — **Identify the project.** Browse [all repositories](https://neohiro.github.io/repositories/) with filter/sort. If unsure, I'll suggest based on keywords.
:::
:::step
**2** — **Security vulnerability?** Use the repo's *Security* tab (private disclosure) — not the public issue tracker. [Open neohiro org](https://github.com/neohiro?tab=repositories).
:::
:::step
**3** — **Regular bug?** Open the repo's *Issues* tab, click *New issue*, choose the *Bug report* template, and include: OS, version, steps to reproduce, expected vs actual.
:::
:::step
**4** — **Need a discussion instead?** Use the repo's *Discussions* tab — great for questions, ideas, and showcases.
:::
    `.trim();
  }

  function stepsForRepo() {
    return `
**Repo discovery** — 15+ projects across security, privacy, networking, developer tools, and games.

:::step
**1** — Open the [All Repositories](https://neohiro.github.io/repositories/) page.
:::
:::step
**2** — Use the filter chips (Security & Privacy, Network, Developer, Games, …) and the search box.
:::
:::step
**3** — Sort by stars, recent activity, or year. Each card has Bug / Sec / Discuss quick-links.
:::
    `.trim();
  }

  function stepsForHardening(t) {
    const linux = /(linux|ubuntu|debian|arch|fedora|rhel|suse|manjaro)/.test(t);
    return linux
      ? `
**Linux hardening** — automated post-install path:

:::step
**1** — Run the [neohiro/linux](https://github.com/neohiro/linux) script (UFW + DNSCrypt + Tor + auditd + AppArmor + sysctl + SSH).
:::
:::step
**2** — For Ubuntu: [neohiro/ubuntu](https://github.com/neohiro/ubuntu) with snap/flatpak control + GNOME privacy.
:::
:::step
**3** — Network layer: [Cripple-NetStrip](https://github.com/neohiro/Cripple-NetStrip) (DNS sinkhole + encrypted DNS + firewall).
:::
      `.trim()
      : `
**Windows hardening** — pick a depth:

:::step
**1** — One-command STIG-style: [Harden-Windows](https://github.com/neohiro/windows) (18 modules, 4 profiles, rollback, dry-run).
:::
:::step
**2** — GUI exploit-mitigation catalog: [ExploitProtection](https://github.com/neohiro/ExploitProtection) (ASR + CFG + DEP + SEHOP).
:::
:::step
**3** — Network + DNS: [Cripple-NetStrip](https://github.com/neohiro/Cripple-NetStrip) and [dnscrypt-proxy-gui](https://github.com/neohiro/dnscrypt-proxy-gui).
:::
      `.trim();
  }

  /* ── Universal top-nav auth tabs ──────────────────────────────── */
  function injectNavAuth() {
    const nav = document.querySelector('.site-nav') || document.querySelector('header nav') || document.querySelector('nav');
    if (!nav) return;

    // Skip if already present
    if (nav.querySelector('[data-nav-auth]')) return;

    const frag = document.createDocumentFragment();

    // Login tab
    const login = document.createElement('button');
    login.className = 'nav-auth nav-auth--login';
    login.id = 'nav-auth__login';
    login.type = 'button';
    login.setAttribute('data-nav-auth', 'login');
    login.innerHTML = `
      <svg viewBox="0 0 24 24" fill="currentColor" width="14" height="14" aria-hidden="true">
        <path d="M12 0C5.374 0 0 5.373 0 12c0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23A11.509 11.509 0 0112 5.803c1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576C20.566 21.797 24 17.3 24 12c0-6.627-5.373-12-12-12z"/>
      </svg>
      <span>Login</span>
    `;
    login.addEventListener('click', () => {
      // Defer to existing auth-bar if present, else trigger OAuth popup hint
      if (window.AuthBar && typeof window.AuthBar.selectTab === 'function') {
        window.AuthBar.selectTab('login');
      } else {
        // Fallback: try to open the GitHub auth-bar drawer
        const authTab = document.getElementById('auth-bar__tab--login');
        if (authTab) authTab.click();
        else showToast('Sign in: open the Login tab in the floating panel (top right).');
      }
    });
    frag.appendChild(login);

    // Dashboard tab
    const dash = document.createElement('a');
    dash.className = 'nav-auth nav-auth--dashboard hidden';
    dash.id = 'nav-auth__dashboard';
    dash.setAttribute('data-nav-auth', 'dashboard');
    dash.href = 'https://neohiro.github.io/dashboard/';
    dash.innerHTML = `
      <svg viewBox="0 0 20 20" fill="currentColor" width="14" height="14" aria-hidden="true">
        <path fill-rule="evenodd" d="M3 3a1 1 0 000 2v8a2 2 0 002 2h2.586l-1.293 1.293a1 1 0 101.414 1.414L10 15.414l2.293 2.293a1 1 0 001.414-1.414L12.414 15H15a2 2 0 002-2V5a1 1 0 100-2H3zm11.707 4.707a1 1 0 00-1.414-1.414L10 9.586 8.707 8.293a1 1 0 00-1.414 0l-2 2a1 1 0 101.414 1.414L8 10.414l1.293 1.293a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/>
      </svg>
      <span>Dashboard</span>
    `;
    frag.appendChild(dash);

    // User tab (shown when signed in)
    const user = document.createElement('a');
    user.className = 'nav-auth nav-auth--user hidden';
    user.id = 'nav-auth__user';
    user.setAttribute('data-nav-auth', 'user');
    user.href = 'https://neohiro.github.io/dashboard/';
    user.innerHTML = `
      <img id="nav-auth__avatar" src="" alt="" />
      <span id="nav-auth__name"></span>
      <span id="nav-auth__role" class="role-badge"></span>
    `;
    frag.appendChild(user);

    // Insert before the sponsor link if present, else at the end
    const sponsor = nav.querySelector('.nav-sponsor');
    if (sponsor) nav.insertBefore(frag, sponsor);
    else nav.appendChild(frag);

    // Sync with auth-bar's existing session if any
    syncAuthFromBar();
  }

  function syncAuthFromBar() {
    try {
      const raw = localStorage.getItem('neohiro_session_v1');
      if (!raw) { showLoggedOutNav(); return; }
      const s = JSON.parse(raw);
      if (!s || !s.login || !Number.isFinite(s.expiresAt) || s.expiresAt < Date.now()) {
        localStorage.removeItem('neohiro_session_v1');
        showLoggedOutNav();
        return;
      }
      showUserNav(s);
    } catch (_) { showLoggedOutNav(); }
  }

  function showUserNav(s) {
    const login = document.getElementById('nav-auth__login');
    const dash = document.getElementById('nav-auth__dashboard');
    const user = document.getElementById('nav-auth__user');
    if (login) login.classList.add('hidden');
    if (dash) dash.classList.remove('hidden');
    if (user) {
      user.classList.remove('hidden');
      const av = document.getElementById('nav-auth__avatar');
      const nm = document.getElementById('nav-auth__name');
      const ro = document.getElementById('nav-auth__role');
      if (av) {
        var avUrl = s.avatar_url || '';
        if (avUrl) {
          av.src = avUrl + (avUrl.indexOf('?') >= 0 ? '&' : '?') + 's=40';
          av.alt = (s.login || 'user') + ' avatar';
        } else {
          av.removeAttribute('src');
          av.alt = '';
        }
      }
      if (nm) nm.textContent = s.login || 'user';
      if (ro) {
        const r = s.role || (s.login === 'neohiro' ? 'godadmin' : 'user');
        ro.textContent = r;
        ro.className = 'role-badge role-badge--' + r;
      }
    }
    _navAuthSuppress = 1;
    window.dispatchEvent(new CustomEvent('neohiro:nav-auth', { detail: { session: s } }));
  }

  // ── Cross-script hook: allow auth-bar to trigger nav update ──
  // Guard against feedback: showUserNav/showLoggedOutNav dispatch this same
  // event after mutating DOM, so the listener must suppress self-dispatches.
  var _navAuthSuppress = 0;
  window.addEventListener('neohiro:nav-auth', (e) => {
    if (_navAuthSuppress) { _navAuthSuppress = 0; return; }
    if (e.detail && e.detail.session) showUserNav(e.detail.session);
    else showLoggedOutNav();
  });
  // Auth-bar stores session in localStorage under 'neohiro_session_v1'.
  // Sync on `storage` events (cross-tab) and on focus/visibility (same-tab after OAuth).
  try {
    window.addEventListener('storage', (e) => {
      if (e.key === 'neohiro_session_v1') syncAuthFromBar();
    });
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible') syncAuthFromBar();
    });
    window.addEventListener('pageshow', () => syncAuthFromBar());
  } catch (_) { /* older browsers */ }

  function showLoggedOutNav() {
    const login = document.getElementById('nav-auth__login');
    const dash  = document.getElementById('nav-auth__dashboard');
    const user  = document.getElementById('nav-auth__user');
    if (login) login.classList.remove('hidden');
    if (dash)  dash.classList.add('hidden');
    if (user)  user.classList.add('hidden');
    _navAuthSuppress = 1;
    window.dispatchEvent(new CustomEvent('neohiro:nav-auth', { detail: { session: null } }));
  }

  // ── Diagnostics probe ─────────────────────────────────────────
  // Fires once on boot, logs a structured health block to the console,
  // and exposes NEohiro.diagnose() so godadmins can call it from the
  // devtools console without inspecting network tab.
  //
  // Probes: localStorage, sessionStorage, Heart endpoint, Mouth endpoint,
  // GH Pages branch, Tailscale, network-ux.js self-integrity.
  // Results are written to window.NEohiro._lastDiag for tab-inspection.
  // If running on neohiro.github.io with godadmin session, also injects
  // a one-line [Diagnostics] status into the nav-auth area.
  function runDiagnostics() {
    var d = {
      ts: new Date().toISOString(),
      host: location.hostname,
      version: '1.0.0',
      storage: { local: false, session: false },
      network: { heart: null, mouth: null, ghPages: null, tailscale: null, uxSelf: null }
    };
    try { localStorage.setItem('_diag', '1'); localStorage.removeItem('_diag'); d.storage.local = true; } catch (_) {}
    try { sessionStorage.setItem('_diag', '1'); sessionStorage.removeItem('_diag'); d.storage.session = true; } catch (_) {}
    function probe(label, url, ms) {
      return fetchWithTimeout(url, { cache: 'no-store' }, ms)
        .then(function (r) { return { label: label, ok: r.ok, status: r.status }; })
        .catch(function (e) { return { label: label, ok: false, status: 0, err: e.message }; });
    }
    Promise.all([
      probe('heart', HEART_ENDPOINTS[0], 5000),
      probe('mouth', MOUTH_ENDPOINT + '?q=test', 5000),
      probe('gh-pages', 'https://neohiro.github.io/', 5000),
      probe('tailscale', 'https://neohiro.github.io/.well-known/tailscale', 5000),
      // ux-self: probe the current page's network-ux.js (relative) to detect CDN staleness
      probe('ux-self', 'assets/js/network-ux.js', 5000)
    ]).then(function (results) {
      d.network.heart = results[0];
      d.network.mouth = results[1];
      d.network.ghPages = results[2];
      d.network.tailscale = results[3];
      d.network.uxSelf = results[4];
      NEohiro._lastDiag = d;
      if (typeof console !== 'undefined' && console.groupCollapsed) {
        var lines = ['[NEohiro Diagnostics] ' + d.ts];
        lines.push('  localStorage : ' + (d.storage.local ? 'OK' : 'BLOCKED'));
        lines.push('  sessionStorage: ' + (d.storage.session ? 'OK' : 'BLOCKED'));
        lines.push('  Heart        : ' + (d.network.heart.ok ? 'UP ' + d.network.heart.status : 'DOWN (' + (d.network.heart.err || d.network.heart.status) + ')'));
        lines.push('  Mouth        : ' + (d.network.mouth.ok ? 'UP ' + d.network.mouth.status : 'DOWN (' + (d.network.mouth.err || d.network.mouth.status) + ')'));
        lines.push('  GH Pages     : ' + (d.network.ghPages.ok ? 'UP ' + d.network.ghPages.status : 'DOWN (' + (d.network.ghPages.err || d.network.ghPages.status) + ')'));
        lines.push('  Tailscale    : ' + (d.network.tailscale.ok ? 'UP ' + d.network.tailscale.status : 'DOWN (' + (d.network.tailscale.err || d.network.tailscale.status) + ')'));
        lines.push('  UX Self      : ' + (d.network.uxSelf.ok ? 'UP ' + d.network.uxSelf.status : 'DOWN (' + (d.network.uxSelf.err || d.network.uxSelf.status) + ')'));
        lines.push('  Full report : NEohiro.diagnose() in console');
        console.groupCollapsed.apply(console, lines);
        console.log('NEohiro diagnostic payload:', JSON.stringify(d, null, 2));
        console.groupEnd();
      }
      // Godadmin inline status (only on neohiro.github.io with godadmin session)
      try {
        var raw = localStorage.getItem('neohiro_session_v1');
        if (raw && location.hostname === 'neohiro.github.io') {
          var s = JSON.parse(raw);
          if (s && s.role === 'godadmin') {
            injectDiagStatus(d);
          }
        }
      } catch (_) {}
    });
  }

  function injectDiagStatus(d) {
    var wrap = document.getElementById('nav-auth__user') || document.getElementById('nav-auth__dashboard') || document.getElementById('nav-auth__login');
    if (!wrap) return;
    var up = [d.network.heart, d.network.mouth, d.network.ghPages, d.network.tailscale, d.network.uxSelf].filter(function (r) { return r && r.ok; }).length;
    var total = 5;
    var el = document.createElement('span');
    el.className = 'diag-status';
    el.style.cssText = 'margin-left:8px;font-family:var(--font-mono,monospace);font-size:0.65rem;padding:2px 6px;border-radius:4px;background:' + (up === total ? 'var(--green,#66bb6a)' : up >= 3 ? 'var(--amber,#ffb74d)' : 'var(--red,#ef5350)') + ';color:#fff;';
    el.textContent = '[Diagnostics: ' + up + '/' + total + ' up]';
    el.title = 'Full report: NEohiro.diagnose() in console';
    wrap.parentNode.insertBefore(el, wrap.nextSibling);
  }

  NEohiro.diagnose = function () { return NEohiro._lastDiag || null; };

  // Expose
  window.NEohiro = NEohiro;
})();
