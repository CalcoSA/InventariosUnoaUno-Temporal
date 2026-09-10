/* Vanilla DOM test double: no browser and no Google requests. */
const fs = require('fs');
const vm = require('vm');
const assert = require('assert/strict');
const nodes = new Map();
function element() {
  const classes = new Set();
  return {value: '', textContent: '', innerHTML: '', className: '', disabled: false, style: {},
    classList: {add: x => classes.add(x), remove: x => classes.delete(x), contains: x => classes.has(x)},
    appendChild() {}};
}
const get = id => {if (!nodes.has(id)) nodes.set(id, element()); return nodes.get(id);};
const drafts = new Map();
let calls = [], failure = false, confirms = [];
const context = vm.createContext({console, URLSearchParams, Date, document: {
  getElementById: get, addEventListener() {}, createElement: element
}, window: {confirm: message => {confirms.push(message); return true;}, scrollTo() {}},
localStorage: {setItem: (k,v) => drafts.set(k,v), getItem: k => drafts.get(k) ?? null, removeItem: k => drafts.delete(k)},
fetch: async (url, options) => {
  calls.push([url, options]);
  let data;
  if (url.startsWith('/api/puntos-venta')) data = ['PDV ÁRBOL'];
  if (url.startsWith('/api/categorias')) data = ['BEBIDAS'];
  if (url.startsWith('/api/productos')) data = [
    {id: 1, categoria: 'BEBIDAS', item: '001', producto: 'Água', udm: 'X 12'},
    {id: 2, categoria: 'BEBIDAS', item: '002', producto: 'Jugo', udm: 'X 6'}];
  if (url === '/api/inventarios') data = failure ? {correcto: false, mensaje: 'Duplicado exacto'} : {correcto: true, registros: 2};
  return {ok: !failure, json: async () => data};
}});
vm.runInContext(fs.readFileSync('app/static/js/inventory.js', 'utf8'), context);
const tick = () => new Promise(resolve => setImmediate(resolve));
(async () => {
  context.asignarFechaActual();
  assert.match(get('fechaInventario').value, /^\d{4}-\d{2}-\d{2}$/);
  context.cargarPuntosVenta(); await tick();
  get('puntoVenta').value = 'PDV ÁRBOL';
  context.cargarCategoriasPDV(); await tick();
  assert.equal(get('categoriaInventario').disabled, false);
  get('fechaInventario').value = '2026-09-08'; get('categoriaInventario').value = 'BEBIDAS';
  context.comenzarInventario(); await tick();
  assert.equal(get('textoProgreso').textContent, '0 de 2 (0%)');
  context.registrarCantidad(0, 'cerrado', '2'); context.registrarCantidad(0, 'abierto', '3');
  assert.equal(get('textoProgreso').textContent, '1 de 2 (50%)');
  const key = 'inventario-uno-a-uno-v3-PDV ÁRBOL-2026-09-08-BEBIDAS';
  assert.equal(JSON.parse(drafts.get(key))[0].cerrado, '2');
  context.guardarInventario();
  assert.match(get('mensajeInventario').textContent, /Faltan 1 productos/);
  context.completarVaciosConCero();
  assert.equal(confirms.at(-1), 'Se marcarán 2 casillas vacías con valor 0. ¿Desea continuar?');
  assert.equal(get('textoProgreso').textContent, '2 de 2 (100%)');
  vm.runInContext("productos[0].cerrado = ''; recuperarBorrador();", context);
  assert.equal(vm.runInContext('productos[0].cerrado', context), '2');
  get('buscador').value = 'agua'; context.mostrarProductos();
  assert.match(get('listaProductos').innerHTML, /Água/);
  assert.doesNotMatch(get('listaProductos').innerHTML, /Jugo/);
  get('buscador').value = 'nada'; context.mostrarProductos();
  assert.match(get('listaProductos').innerHTML, /No se encontraron productos/);
  failure = true; context.guardarInventario(); await tick();
  assert.equal(get('mensajeInventario').textContent, 'Duplicado exacto');
  assert.ok(drafts.has(key));
  assert.equal(get('botonGuardar').disabled, false);
  failure = false; context.guardarInventario(); await tick();
  assert.equal(drafts.has(key), false);
  assert.equal(get('pantallaInventario').classList.contains('oculto'), true);
  const payload = JSON.parse(calls.at(-1)[1].body);
  assert.equal(payload.puntoVenta, 'PDV ÁRBOL');
  assert.equal(payload.conteos[0].cerrado, '2');
  assert.equal(context.formatearFecha('2026-09-08'), '08/09/2026');
  context.nuevoInventario();
  assert.equal(get('puntoVenta').value, '');
  console.log('Frontend: HTTP, búsqueda, borrador, progreso, completar, error y éxito OK');
})().catch(error => {console.error(error); process.exitCode = 1;});
