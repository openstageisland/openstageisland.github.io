/**
 * Shared auth bar — cross-site GitHub OAuth + private assistant contact.
 *
 * Flow (simplest possible, matches the user's "gh auth only" spec):
 *   1. User clicks Login tab.
 *   2. Browser is redirected to github.com/login/oauth/authorize with
 *      client_id + redirect_uri + state. No tokens stored client-side.
 *   3. GitHub redirects back to /auth/callback?code=...&state=...
 *   4. The site's server (functions/api/auth.js) exchanges the code for
 *      a token, uses the host's `gh` CLI credentials to verify org
 *      membership, and returns a session_id derived from the role.
 *   5. Auth bar reads #session= from the URL, stores session_id in
 *      localStorage as the only client-side artifact, then displays
 *      the role-aware UI.
 *
 * Cross-domain session sharing:
 *   - Session key and OAuth state key are namespaced under a stable
 *     "neohiro_session_v1" / "neohiro_oauth_state_v1" prefix. This is
 *     INTENTIONAL: it lets the same user move from
 *     openstageisland.github.io → transhumanists.github.io →
 *     frenzypenguin-media.github.io → neohiro.github.io without
 *     re-authenticating, because the localStorage entries survive the
 *     host switch on a single browser profile. (LocalStorage is
 *     origin-bound in modern browsers, so the cross-site case requires
 *     either a shared parent domain OR a server-side session — the
 *     latter is what we use: every origin calls the same Brain
 *     /auth/state endpoint, which holds the canonical session.)
 *   - The Brain endpoint at /auth/state returns the session for
 *     whatever user has a live session_id stored server-side. The
 *     browser passes the session_id in the URL hash; the server looks
 *     it up. This is why the localStorage key is constant across
 *     hosts: the server is the source of truth, and the key just
 *     holds the opaque handle.
 *   - The auth bar resolves the Brain base URL via a global override
 *     (window.AUTH_BRAIN_BASE) so each site (neohiro, FPM, OSI, H+)
 *     can point at its nearest Brain. Default: / (same origin).
 *
 * Required:
 *   - auth-bar.html (markup)
 *   - auth-bar.css  (styles)
 *   - /auth/state, /auth/session, /auth/session DELETE, /auth/callback
 *     endpoints reachable from this origin (Brain or gateway in front
 *     of Brain)
 *
 * Optional globals:
 *   window.OAUTH_CLIENT_ID    — required for login; configure per host
 *   window.AUTH_BRAIN_BASE    — override the API base (default '')
 *   window.AUTH_CALLBACK      — override callback path (default '/auth/callback')
 *   window.AUTH_GH_USER       — override the godadmin login check
 *   window.DASHBOARD_URL      — override dashboard URL (default '/dashboard/')
 */

(function () {
  'use strict';

  // Stable session keys: do not change between neohiro/FPM/OSI/H+ hosts.
  // This is on purpose — see "Cross-domain session sharing" above.
  var SESSION_KEY = 'neohiro_session_v1';
  var OAUTH_STATE_KEY = 'neohiro_oauth_state_v1';

  // Default fallback for the godadmin login check. Hosts can override via
  // window.AUTH_GH_USER when a different user is the godadmin on that org.
  var DEFAULT_GH_USER = 'neohiro';

  var GH_USER = (typeof window !== 'undefined' && window.AUTH_GH_USER) || DEFAULT_GH_USER;
  var BRAIN_BASE = (typeof window !== 'undefined' && window.AUTH_BRAIN_BASE) || '';
  var AUTH_CALLBACK = (typeof window !== 'undefined' && window.AUTH_CALLBACK) || '/auth/callback';
  var DASHBOARD_URL = (typeof window !== 'undefined' && window.DASHBOARD_URL) || '/dashboard/';
  var AUTH_STATE_ENDPOINT = BRAIN_BASE + '/auth/state';
  var AUTH_SESSION_ENDPOINT = BRAIN_BASE + '/auth/session';
  var CONTACT_ENDPOINT = BRAIN_BASE + '/api/contact';
  var SESSION_MAX_AGE_MS = 24 * 60 * 60 * 1000;

  var state = { activeTab: null };

  function $(id) { return document.getElementById(id); }
  function qa(sel, ctx) { return Array.from((ctx || document).querySelectorAll(sel)); }

  function show(panel) {
    if (panel) { panel.hidden = false; panel.removeAttribute('hidden'); }
  }
  function hide(panel) {
    if (panel) { panel.hidden = true; panel.setAttribute('hidden', ''); }
  }

  function closeAll() {
    qa('.auth-bar__panel').forEach(hide);
    qa('.auth-bar__tab').forEach(t => {
      t.setAttribute('aria-selected', 'false');
      t.classList.remove('active');
    });
    hide($('auth-bar__overlay'));
    state.activeTab = null;
  }

  function selectTab(tabId) {
    if (!tabId) { closeAll(); return; }
    qa('.auth-bar__panel').forEach(hide);
    qa('.auth-bar__tab').forEach(t => {
      t.setAttribute('aria-selected', 'false');
      t.classList.remove('active');
    });
    var tab = $(`auth-bar__tab--${tabId}`);
    var panel = $(`auth-bar__panel--${tabId}`);
    if (!tab || !panel) return;
    tab.setAttribute('aria-selected', 'true');
    tab.classList.add('active');
    show(panel);
    state.activeTab = tabId;
    var overlay = $('auth-bar__overlay');
    if (tabId === 'contact' || tabId === 'login') show(overlay); else hide(overlay);
    if (tabId === 'contact') {
      setTimeout(() => { var input = $('auth-bar__contact-input'); if (input) input.focus(); }, 350);
    }
  }

  function appendSize(avatarUrl, size) {
    if (!avatarUrl) return '';
    return avatarUrl + (avatarUrl.indexOf('?') >= 0 ? '&' : '?') + 's=' + size;
  }

  function readSessionIdFromUrl() {
    var hash = location.hash || '';
    var m = hash.match(/session=([a-f0-9]+)/i);
    if (m) return m[1];
    var u = new URLSearchParams(location.search);
    return u.get('session');
  }

  async function fetchState() {
    try {
      var r = await fetch(AUTH_STATE_ENDPOINT, { credentials: 'same-origin' });
      if (!r.ok) return null;
      var data = await r.json();
      return data && data.state;
    } catch (_) { return null; }
  }

  function storeSession(sessionId, profile, role) {
    if (!sessionId) return null;
    var record = {
      session_id: sessionId,
      login: profile.login,
      name: profile.name || null,
      avatar_url: profile.avatar_url || null,
      role: role || 'user',
      expiresAt: Date.now() + SESSION_MAX_AGE_MS,
    };
    localStorage.setItem(SESSION_KEY, JSON.stringify(record));
    return record;
  }

  function readStoredSession() {
    try {
      var raw = localStorage.getItem(SESSION_KEY);
      if (!raw) return null;
      var s = JSON.parse(raw);
      if (!s || !s.session_id || !Number.isFinite(s.expiresAt) || s.expiresAt < Date.now()) {
        localStorage.removeItem(SESSION_KEY);
        return null;
      }
      return s;
    } catch (_) { return null; }
  }

  function clearSession() {
    var s = readStoredSession();
    if (s && s.session_id) {
      fetch(AUTH_SESSION_ENDPOINT + '?session=' + encodeURIComponent(s.session_id), { method: 'DELETE' }).catch(() => {});
    }
    localStorage.removeItem(SESSION_KEY);
  }

  function setUser(session) {
    var loginTab = $('auth-bar__tab--login');
    var dashboardTab = $('auth-bar__tab--dashboard');
    var userTab = $('auth-bar__tab--user');
    var dashboardLink = $('auth-bar__dashboard-link');
    var userDashboardLink = $('auth-bar__user-dashboard-link');

    if (session && session.login) {
      if (loginTab) loginTab.classList.add('hidden');
      if (dashboardTab) dashboardTab.classList.remove('hidden');
      if (userTab) userTab.classList.remove('hidden');

      var avatar = $('auth-bar__avatar');
      var avatarLg = $('auth-bar__user-avatar-lg');
      var username = $('auth-bar__username');
      var userName = $('auth-bar__user-name');
      var userLogin = $('auth-bar__user-login');
      var role = $('auth-bar__role');

      if (avatar) avatar.src = appendSize(session.avatar_url, 40);
      if (avatarLg) avatarLg.src = appendSize(session.avatar_url, 72);
      if (username) username.textContent = session.login;
      if (userName) userName.textContent = session.name || session.login;
      if (userLogin) userLogin.textContent = '@' + session.login;
      if (role) {
        var r = session.role || (session.login === GH_USER ? 'godadmin' : 'user');
        role.textContent = r;
        role.className = 'auth-bar__role-badge auth-bar__role-badge--' + r;
      }
      // Dashboard URL is host-configurable so OSI can route to its own
      // dashboard on Brain without going through neohiro.
      var dash;
      try {
        dash = new URL(DASHBOARD_URL, location.origin).toString();
      } catch (_) {
        dash = location.origin + DASHBOARD_URL;
      }
      var dashWithUser = dash + (dash.indexOf('?') >= 0 ? '&' : '?') + 'user=' + encodeURIComponent(session.login);
      if (dashboardLink) dashboardLink.href = dashWithUser;
      if (userDashboardLink) userDashboardLink.href = dashWithUser;
    } else {
      if (loginTab) loginTab.classList.remove('hidden');
      if (dashboardTab) dashboardTab.classList.add('hidden');
      if (userTab) userTab.classList.add('hidden');
    }
  }

  async function startOAuth() {
    var clientId = (typeof window !== 'undefined' && window.OAUTH_CLIENT_ID) || '';
    if (!clientId) {
      console.warn('[auth-bar] OAUTH_CLIENT_ID not set — login unavailable on this host');
      return;
    }
    var stateVal = await fetchState();
    if (!stateVal) {
      console.warn('[auth-bar] failed to fetch OAuth state from server');
      return;
    }
    sessionStorage.setItem(OAUTH_STATE_KEY, stateVal);
    // Redirect back to the host's own callback so the localStorage key
    // is set on the same origin where the user is browsing. The
    // /auth/callback endpoint forwards the session_id to whatever URL
    // is in the `return_to` query string.
    var callbackUrl = new URL(AUTH_CALLBACK, location.origin).toString();
    var returnTo = encodeURIComponent(location.pathname + location.search);
    var url =
      'https://github.com/login/oauth/authorize?client_id=' + encodeURIComponent(clientId) +
      '&redirect_uri=' + encodeURIComponent(callbackUrl) +
      '&scope=read:user%20read:org' +
      '&state=' + encodeURIComponent(stateVal) +
      '&return_to=' + returnTo;
    location.href = url;
  }

  async function consumeCallback() {
    var sessionId = readSessionIdFromUrl();
    if (!sessionId) return false;
    if (location.hash.includes('session=')) {
      history.replaceState({}, '', location.pathname + location.search);
    } else {
      var u = new URLSearchParams(location.search);
      u.delete('session');
      var q = u.toString();
      history.replaceState({}, '', location.pathname + (q ? '?' + q : ''));
    }
    try {
      var r = await fetch(AUTH_SESSION_ENDPOINT + '?session=' + encodeURIComponent(sessionId));
      if (!r.ok) return false;
      var profile = await r.json();
      storeSession(sessionId, profile, profile.role);
      return profile;
    } catch (_) { return false; }
  }

  async function sendContact() {
    var form = $('auth-bar__contact-form');
    var success = $('auth-bar__contact-success');
    var error = $('auth-bar__contact-error');
    var errorMsg = $('auth-bar__contact-error-msg');
    var input = $('auth-bar__contact-input');
    var submitBtn = form ? form.querySelector('[type=submit]') : null;

    if (!input || !input.value.trim()) return;
    if (submitBtn) submitBtn.disabled = true;
    hide(success); hide(error);

    var session = readStoredSession();
    try {
      var body = {
        message: input.value.trim(),
        source: location.origin + location.pathname,
        ts: new Date().toISOString(),
      };
      if (session) body.session_id = session.session_id;

      var r = await fetch(CONTACT_ENDPOINT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!r.ok) {
        var d = await r.json().catch(() => ({}));
        throw new Error(d.error || `HTTP ${r.status}`);
      }
      hide(form);
      show(success);
      input.value = '';
    } catch (e) {
      if (errorMsg) errorMsg.textContent = e.message || 'Something went wrong. Try again.';
      show(error);
    } finally {
      if (submitBtn) submitBtn.disabled = false;
    }
  }

  function initContactForm() {
    var form = $('auth-bar__contact-form');
    var input = $('auth-bar__contact-input');
    var charCount = $('auth-bar__char-count');
    if (input && charCount) {
      input.addEventListener('input', () => {
        var len = input.value.length;
        charCount.textContent = `${len} / 1000`;
        charCount.style.color = len > 900 ? 'var(--red, #f85149)' : '';
      });
    }
    if (form) form.addEventListener('submit', (e) => { e.preventDefault(); sendContact(); });
  }

  function initOverlay() {
    var overlay = $('auth-bar__overlay');
    if (overlay) overlay.addEventListener('click', () => selectTab(null));
  }

  async function init() {
    await consumeCallback();

    qa('.auth-bar__tab').forEach(tab => {
      tab.addEventListener('click', () => {
        var id = tab.id.replace('auth-bar__tab--', '');
        selectTab(id === state.activeTab ? null : id);
      });
    });

    var ghBtn = $('auth-bar__gh-btn');
    if (ghBtn) ghBtn.addEventListener('click', startOAuth);

    var logoutDashboard = $('auth-bar__logout-btn');
    var logoutUser = $('auth-bar__user-logout');
    [logoutDashboard, logoutUser].forEach(btn => {
      if (btn) btn.addEventListener('click', () => { clearSession(); setUser(null); });
    });

    initContactForm();
    initOverlay();
    setUser(readStoredSession());
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  window.AuthBar = { selectTab };
})();
