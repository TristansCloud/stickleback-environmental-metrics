// Offline UI regression tests. Run: node --test tests/ee_downloads.test.cjs
const assert = require('node:assert/strict');
const {test} = require('node:test');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const source = fs.readFileSync(path.join(__dirname,
  '../apps/earth_engine_validation/ee_full_review_app.js'), 'utf8');
const block = source.slice(source.indexOf('var downloadStatus ='),
  source.indexOf("panel.add(label('STICKLEBACK"));

function setup({lookup = true, throwCsv = false} = {}) {
  const calls = [], timers = new Map();
  let nextTimer = 0;
  function widget(value) {
    return {value, url: null, disabled: false,
      setValue(v) { this.value = v; }, setUrl(v) { this.url = v; },
      setDisabled(v) { this.disabled = v; }, style() { return {set() {}}; }};
  }
  function collection(name, filters = []) {
    return {filter(f) { return collection(name, filters.concat([f])); },
      getDownloadURL(...args) {
        // EE accepts one named object OR positional arguments, never a mix.
        assert.equal(args.length, 1);
        const options = args[0];
        assert.equal(typeof options.format, 'string');
        assert.ok(['CSV', 'GEOJSON'].includes(options.format.toUpperCase()));
        assert.equal(typeof options.callback, 'function');
        calls.push({name, filters, ...options});
        if (name === 'sites' && throwCsv) throw new Error('CSV request failed');
      }};
  }
  const ctx = {label: widget, RELEASE: 'release', sites: collection('sites'),
    lookup: lookup ? collection('lookup') : null, osmLakes: collection('osmLakes'),
    ee: {Filter: {eq: (key, value) => ({eq: [key, value]}),
      neq: (key, value) => ({neq: [key, value]})},
      FeatureCollection: () => collection('empty')},
    ui: {Panel: () => ({rows: [], add(row) {this.rows.push(row);}, clear() {this.rows = [];}}),
      Button: (title, callback) => ({...widget(title), click: callback}),
      util: {setTimeout(fn, delay) { assert.equal(delay, 30000); timers.set(++nextTimer, fn); return nextTimer; },
        clearTimeout(id) {timers.delete(id);}}}};
  vm.createContext(ctx);
  vm.runInContext(block, ctx);
  return {ctx, calls, timers};
}

test('CSV is usable while GIS requests are pending; each gets supported async arguments', () => {
  const {ctx, calls, timers} = setup();
  ctx.download.click();
  assert.equal(calls.length, 3);
  assert.equal(calls[0].filename, 'release_sites');
  assert.equal(calls[1].filters[0].eq[1], 'inland_water');
  assert.equal(calls[2].filters[1].neq[1], 'HydroRIVERS');
  calls[0].callback('https://example.test/sites.csv');
  assert.equal(ctx.downloads.rows[0].url, 'https://example.test/sites.csv');
  assert.equal(ctx.download.disabled, true);
  calls[2].callback(null, 'Permission denied');
  calls[1].callback('https://example.test/lakes.geojson');
  assert.equal(ctx.download.disabled, false);
  assert.match(ctx.downloadStatus.value, /1 download link\(s\) failed/);
  assert.equal(timers.size, 0);
});

test('timeouts allow retry and old callbacks cannot change the new request', () => {
  const {ctx, calls, timers} = setup();
  ctx.download.click();
  for (const timer of [...timers.values()]) timer();
  assert.equal(ctx.download.disabled, false);
  assert.match(ctx.downloads.rows[0].value, /timed out/);
  ctx.download.click();
  calls[0].callback('https://example.test/stale.csv');
  assert.equal(ctx.downloads.rows[0].url, null);
  for (const call of calls.slice(3)) call.callback('https://example.test/new');
  assert.match(ctx.downloadStatus.value, /Choose a link to download/);
  assert.equal(ctx.download.disabled, false);
});

test('synchronous exceptions and absent URLs show errors without blocking other files', () => {
  const {ctx, calls} = setup({lookup: false, throwCsv: true});
  ctx.download.click();
  assert.equal(calls.length, 3);
  assert.equal(calls[1].name, 'osmLakes');
  assert.equal(calls[2].name, 'empty');
  assert.match(ctx.downloads.rows[0].value, /CSV request failed/);
  calls[1].callback(null);
  calls[2].callback('https://example.test/empty.geojson');
  assert.equal(ctx.download.disabled, false);
  assert.match(ctx.downloads.rows[1].value, /No download URL/);
  assert.match(ctx.downloadStatus.value, /2 download link\(s\) failed/);
});
