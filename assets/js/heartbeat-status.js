/* Live heartbeat status poller for _includes/heartbeat-status.html.
 *
 * Lives in a file rather than inline in the partial because the layout's
 * Content-Security-Policy sets script-src 'self' with no 'unsafe-inline'. An
 * inline <script> there is blocked by the browser, silently: the badge renders
 * but never leaves its initial state. check_rendered_html.py enforces the
 * invariant in both directions, so this cannot regress unnoticed.
 *
 * Reads the edge origin from the element's data-hb-origin attribute, so the
 * partial stays free of per-site configuration.
 */(function () {
  var el = document.getElementById('hb');
  if (!el) return;
  var origin = el.getAttribute('data-hb-origin');
  var detail = el.querySelector('[data-hb-detail]');
  var PERIOD = 30000;

  function set(state, text) {
    el.setAttribute('data-state', state);
    detail.textContent = text;
  }

  function ms(n) { return Math.round(n) + 'ms'; }

  function fail(text) {
    set('down', text);
    setTimeout(poll, PERIOD);
  }

  function poll() {
    var started = performance.now();
    var ctrl = typeof AbortController === 'function' ? new AbortController() : null;
    var timer = setTimeout(function () { if (ctrl) ctrl.abort(); }, 8000);

    fetch(origin + '/heartbeat', {
      cache: 'no-store',
      signal: ctrl ? ctrl.signal : undefined
    }).then(function (r) {
      if (!r.ok) throw new Error('edge ' + r.status);
      return r.json();
    }).then(function () {
      var edge = performance.now() - started;
      // The edge answered. Now ask whether the body behind it is actually up.
      return fetch(origin + '/status', { cache: 'no-store' })
        .then(function (r) { return r.ok ? r.json() : null; })
        .catch(function () { return null; })
        .then(function (body) {
          clearTimeout(timer);
          if (body && body.status === 'ok') {
            set('alive', 'alive · ' + ms(edge));
          } else {
            set('degraded', 'edge only · ' + ms(edge));
          }
        });
    }).catch(function () {
      clearTimeout(timer);
      // Rejected fetch usually means the CSP blocked it or the node is gone;
      // say which is unknowable and let the visitor see it is not working.
      fail('unreachable');
    });
  }

  poll();
  document.addEventListener('visibilitychange', function () {
    if (!document.hidden) poll();
  });
})();

