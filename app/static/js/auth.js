/* Session metadata only. Inventory drafts and JWT cookies are never read here. */
(() => {
  'use strict';
  const config = document.currentScript.dataset;
  const idleMs = Number(config.idleSeconds) * 1000;
  const heartbeatMs = 45000;
  const nativeFetch = window.fetch.bind(window);
  let context = config.sessionContext;
  let lastActivity = Date.now() - idleMs + Number(config.remainingSeconds) * 1000;
  let lastAcknowledged = lastActivity;
  let lastAttempt = 0;
  let lastPublished = 0;
  let busy = false;
  let stopped = false;
  let interval;
  const key = kind => `inventario-auth-v1-${context}-${kind}`;
  const read = kind => {
    try {
      const value = Number(localStorage.getItem(key(kind)));
      return Number.isFinite(value) && value <= Date.now() ? value : 0;
    } catch (_) { return 0; }
  };
  const publish = (kind, value) => {
    try { localStorage.setItem(key(kind), String(Math.max(read(kind), value))); }
    catch (_) { /* Cookie/server still enforce expiration if storage is unavailable. */ }
  };
  const latest = () => Math.max(lastActivity, lastAcknowledged, read('activity'), read('ack'));

  function expire() {
    if (stopped) return;
    stopped = true;
    clearInterval(interval);
    // Never POST logout on a local timer: another tab may have a newer cookie.
    window.location.replace('/auth/expired');
  }

  function observe(response) {
    const server = Number(response.headers.get('X-Server-Time'));
    const activity = Number(response.headers.get('X-Session-Activity-At'));
    const nextContext = response.headers.get('X-Session-Context');
    if (!nextContext || !server || !activity) return;
    if (nextContext !== context) {
      context = nextContext;
      lastActivity = 0;
      lastAcknowledged = 0;
    }
    const acknowledged = Date.now() - Math.max(0, server - activity) * 1000;
    lastAcknowledged = Math.max(lastAcknowledged, acknowledged);
    publish('ack', lastAcknowledged);
  }

  async function tick() {
    if (stopped || busy) return;
    const now = Date.now();
    const last = latest();
    const timedOut = now - last >= idleMs;
    const ack = Math.max(lastAcknowledged, read('ack'));
    if (!timedOut && (last <= ack || now - lastAttempt < heartbeatMs)) return;
    busy = true;
    lastAttempt = now;
    try {
      const response = await nativeFetch(timedOut ? '/auth/status' : '/auth/activity', {
        method: 'POST', credentials: 'same-origin', cache: 'no-store',
        headers: {'Content-Type': 'application/json', 'X-Requested-With': 'InventariosPDV'},
        body: timedOut ? '{}' : JSON.stringify({idle_seconds: Math.max(0, now - last) / 1000})
      });
      if (response.status === 401) { expire(); return; }
      if (response.ok) {
        observe(response);
        // A status check is read-only: it cannot keep an idle session alive.
        if (timedOut && Date.now() - latest() >= idleMs) expire();
      } else if (timedOut) expire();
    } catch (_) {
      if (timedOut) expire();
      // During a temporary outage, retry on a later tick; no offline renewal.
    } finally { busy = false; }
  }

  function activity(event) {
    if (stopped || !event.isTrusted) return;
    const now = Date.now();
    if (now - latest() >= idleMs) { void tick(); return; }
    lastActivity = now;
    // At most one shared timestamp write per second, regardless of mouse rate.
    if (now - lastPublished >= 1000) {
      publish('activity', now);
      lastPublished = now;
    }
    void tick();
  }

  for (const event of ['click', 'keydown', 'input', 'scroll', 'touchstart', 'mousemove']) {
    document.addEventListener(event, activity, {passive: true, capture: true});
  }
  window.addEventListener('storage', event => {
    if (event.key === key('activity') || event.key === key('ack')) void tick();
  });
  // A suspended/bfcache tab checks the shared cookie before returning to work.
  window.addEventListener('pageshow', () => { void tick(); });
  document.addEventListener('visibilitychange', () => { if (!document.hidden) void tick(); });

  window.fetch = async (input, options = {}) => {
    const url = new URL(typeof input === 'string' ? input : input.url, window.location.href);
    if (url.origin !== window.location.origin || !url.pathname.startsWith('/api/')) {
      return nativeFetch(input, options);
    }
    const headers = new Headers(options.headers || (typeof input !== 'string' ? input.headers : undefined));
    headers.set('X-Requested-With', 'InventariosPDV');
    const response = await nativeFetch(input, {...options, headers, credentials: 'same-origin'});
    if (response.status === 401) expire();
    // API calls do not fabricate human activity; heartbeats handle real events.
    return response;
  };

  // Explicit logout is available to UI integrations without exposing the cookie.
  window.inventoryAuth = Object.freeze({logout: async () => {
    const response = await nativeFetch('/auth/logout', {
      method: 'POST', credentials: 'same-origin', headers: {'X-Requested-With': 'InventariosPDV'}
    });
    if (response.ok || response.status === 401) expire();
    return response.ok;
  }});
  interval = setInterval(() => {
    if (lastActivity > read('activity')) publish('activity', lastActivity);
    void tick();
  }, 5000);
  void tick();
})();
