/* Real auth.js in two VM tabs, shared storage/cookie and a deterministic clock. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('app/static/js/auth.js', 'utf8');
const draftKey = 'inventario-uno-a-uno-v3-PDV-2026-09-09-BEBIDAS';
const draft = '[{"item":"001","cerrado":"2","abierto":"3"}]';
const settle = () => new Promise(resolve => setImmediate(resolve));

function world(storageAvailable = true) {
  let now = 1800000000000, last = now, expiry = now + 1200000;
  const entries = new Map([[draftKey, draft]]), tabs = [], calls = [];
  async function request(url, options = {}) {
    calls.push({url: String(url), options, at: now});
    let status = now < expiry ? 204 : 401;
    if (status === 204 && url === '/auth/activity') {
      assert.equal(options.headers['X-Requested-With'], 'InventariosPDV');
      last = Math.max(last, now - Math.ceil(JSON.parse(options.body).idle_seconds) * 1000);
      expiry = last + 1200000;
    }
    if (url === '/auth/logout') expiry = now;
    return {status, ok: status < 400, headers: new Map([
      ['X-Server-Time', String(now / 1000)], ['X-Session-Activity-At', String(last / 1000)],
      ['X-Session-Expires-At', String(expiry / 1000)], ['X-Session-Context', 'test-context']
    ])};
  }
  function tab() {
    const events = {}, docEvents = {}, intervals = new Set(), redirects = [];
    const add = (list, name, callback) => (list[name] ||= []).push(callback);
    const fire = (list, name, event = {}) => (list[name] || []).forEach(fn => fn(event));
    const t = {intervals, redirects, storage: event => fire(events, 'storage', event),
      event: (name, trusted = true) => fire(docEvents, name, {isTrusted: trusted})};
    tabs.push(t);
    const storage = {
      getItem(k) { if (!storageAvailable) throw Error('storage disabled'); return entries.get(k) ?? null; },
      setItem(k, v) {
        if (!storageAvailable) throw Error('storage disabled');
        const old = entries.get(k); entries.set(k, v);
        if (old !== v) tabs.filter(other => other !== t).forEach(other => other.storage({key: k, newValue: v}));
      },
      removeItem() { throw Error('Auth must never delete storage'); },
      clear() { throw Error('Auth must never clear storage'); }
    };
    const document = {currentScript: {dataset: {idleSeconds: '1200', remainingSeconds: String((expiry - now) / 1000), sessionContext: 'test-context'}},
      addEventListener: (name, cb) => add(docEvents, name, cb), hidden: false};
    const window = {fetch: request, addEventListener: (name, cb) => add(events, name, cb),
      location: {href: 'https://inventory.test/', origin: 'https://inventory.test', replace: path => redirects.push(path)}};
    const context = vm.createContext({window, document, localStorage: storage, Headers, URL, console,
      Date: class extends Date { static now() { return now; } },
      setInterval: fn => { intervals.add(fn); return fn; }, clearInterval: fn => intervals.delete(fn)});
    vm.runInContext(source, context);
    Object.assign(t, {window, context, storage});
    return t;
  }
  async function advance(seconds) {
    for (let elapsed = 0; elapsed < seconds; elapsed += 5) {
      now += Math.min(5, seconds - elapsed) * 1000;
      for (const t of tabs) for (const fn of [...t.intervals]) fn();
      await settle();
    }
  }
  return {tab, advance, entries, calls, get expiry() { return expiry; }, get now() { return now; }};
}

(async () => {
  {
    const w = world(), a = w.tab();
    await w.advance(1199);
    assert.equal(w.calls.length, 0, 'No heartbeat without human input');
    assert.deepEqual(a.redirects, []);
    await w.advance(1);
    assert.deepEqual(a.redirects, ['/auth/expired']);
    assert.equal(a.intervals.size, 0);
    assert.equal(w.entries.get(draftKey), draft);
    assert.ok(w.calls.every(call => call.url === '/auth/status'));
    // Load actual inventory code after a new login and recover the unchanged draft.
    const fresh = w.tab();
    vm.runInContext(fs.readFileSync('app/static/js/inventory.js', 'utf8'), fresh.context);
    vm.runInContext("puntoVentaActual='PDV'; fechaActual='2026-09-09'; categoriaActual='BEBIDAS'; productos=[{item:'001',cerrado:'',abierto:''}]; recuperarBorrador();", fresh.context);
    assert.equal(vm.runInContext('productos[0].cerrado', fresh.context), '2');
    assert.equal(vm.runInContext('productos[0].abierto', fresh.context), '3');
  }
  for (const storageAvailable of [true, false]) {
    const w = world(storageAvailable), a = w.tab(), b = w.tab();
    for (let minute = 0; minute < 40; minute++) {
      await w.advance(60);
      b.event('input');
      await settle();
    }
    assert.deepEqual(a.redirects, [], `Idle tab must observe the active shared session (storage=${storageAvailable}, calls=${w.calls.length}, remaining=${w.expiry-w.now})`);
    assert.deepEqual(b.redirects, []);
    assert.ok(w.expiry > w.now);
    await w.advance(1200);
    assert.deepEqual(a.redirects, ['/auth/expired']);
    assert.deepEqual(b.redirects, ['/auth/expired']);
    assert.equal(w.entries.get(draftKey), draft);
    assert.ok(!w.calls.some(call => call.url === '/auth/logout'), 'Idle tabs never delete the shared cookie');
  }
  {
    const w = world(), a = w.tab();
    await w.advance(1);
    for (const event of ['click', 'keydown', 'input', 'scroll', 'touchstart', 'mousemove']) a.event(event, false);
    await settle();
    assert.equal(w.calls.length, 0, 'Synthetic events are not human activity');
    for (let i = 0; i < 1000; i++) a.event('mousemove');
    await settle();
    assert.equal(w.calls.filter(c => c.url === '/auth/activity').length, 1);
    await w.advance(10);
    a.event('keydown');
    await w.advance(40);
    assert.equal(w.expiry, w.now - 40000 + 1200000, 'Delayed heartbeat uses event time');
    const heartbeats = w.calls.filter(c => c.url === '/auth/activity');
    assert.equal(heartbeats.length, 2);
    assert.ok(heartbeats[1].at - heartbeats[0].at >= 45000);
    assert.ok([...w.entries.keys()].every(k => k === draftKey || k.startsWith('inventario-auth-v1-')));
  }
  {
    const w = world(), a = w.tab();
    await a.window.fetch('/api/inventarios', {method: 'POST', body: '{}'});
    assert.equal(w.calls.at(-1).options.headers.get('X-Requested-With'), 'InventariosPDV');
    await w.advance(1200);
    await a.window.fetch('/api/productos');
    assert.equal(w.entries.get(draftKey), draft);
    assert.equal(a.redirects.length, 1, '401 does not start repeated redirects');
  }
  {
    const w = world(), a = w.tab();
    assert.equal(await a.window.inventoryAuth.logout(), true);
    assert.equal(w.entries.get(draftKey), draft);
    assert.deepEqual(a.redirects, ['/auth/expired']);
  }
  console.log('Auth frontend: inactivity, sliding time, two tabs, disabled storage, throttling, 401, logout and actual draft recovery OK');
})().catch(error => { console.error(error); process.exitCode = 1; });
