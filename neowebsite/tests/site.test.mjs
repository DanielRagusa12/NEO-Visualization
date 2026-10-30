import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, existsSync, readdirSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const staticRoot = new URL('../static/', import.meta.url);
const source = readFileSync(new URL('main.js', staticRoot), 'utf8');
const fixture = JSON.parse(readFileSync(new URL('fixtures/latest.json', import.meta.url), 'utf8'));

function loadSite(fetch = async () => ({ ok: false, status: 503 }), timers = { setTimeout, clearTimeout }) {
    const elements = new Map();
    const document = {
        addEventListener() {},
        createElement() {
            const nodes = new Map();
            const properties = new Map();
            let html = '';
            return {
                htmlWrites: 0,
                get innerHTML() { return html; },
                set innerHTML(value) { html = value; this.htmlWrites++; },
                style: { setProperty: (name, value) => properties.set(name, value), properties },
                querySelector(selector) {
                    if (!nodes.has(selector)) {
                        const listeners = new Map();
                        nodes.set(selector, { listeners, addEventListener: (type, fn) => listeners.set(type, fn) });
                    }
                    return nodes.get(selector);
                }
            };
        },
        getElementById(id) {
            if (!elements.has(id)) {
                const classes = new Set(['hidden']);
                const attributes = new Map();
                elements.set(id, {
                    textContent: '', innerHTML: '', hidden: true, children: [],
                    setAttribute: (name, value) => attributes.set(name, value),
                    getAttribute: name => attributes.get(name),
                    appendChild(child) { this.children.push(child); },
                    focus() { document.activeElement = this; },
                    classList: { add: c => classes.add(c), remove: c => classes.delete(c), contains: c => classes.has(c) }
                });
            }
            return elements.get(id);
        }
    };
    const context = vm.createContext({ document, window: {}, fetch, Intl, Map, Set, fixture, AbortController, ...timers });
    vm.runInContext(source, context);
    vm.runInContext('state.data = fixture; state.referenceObjects = new Map(fixture.reference_objects.map(r => [r.id, r]));', context);
    return { evaluate: code => vm.runInContext(code, context), document };
}

const plain = value => JSON.parse(JSON.stringify(value));

test('production data stays on the same-origin curated JSON path', () => {
    const { evaluate } = loadSite();
    assert.equal(evaluate('DATA_URL'), '/data/latest.json');
    assert.equal(source.includes('/data/neo-study.json'), false);
    assert.equal(source.includes('neo-motion-pilot'), false);
});

test('NEO variants are deterministic and do not depend on sort or reference selection', () => {
    const { evaluate } = loadSite();
    const before = plain(evaluate('Object.fromEntries(fixture.neos.map(n => [n.neo_id, getNeoAsset(n)]))'));
    const sorted = plain(evaluate('sortNeos(fixture.neos, "largest").map(n => [n.neo_id, getNeoAsset(n)])'));
    for (const [id, asset] of sorted) assert.deepEqual(asset, before[id]);
    assert.equal(new Set(Object.values(before).map(a => a.poster)).size, 4);
    assert.equal(evaluate('getNeoAsset(fixture.neos[0]).poster === getNeoAsset({...fixture.neos[0], visualization: {...fixture.neos[0].visualization, closest_reference_id: "average_human"}}).poster'), true);
    assert.match(evaluate('getNeoAsset({neo_id: "../../anything<script>"}).video'), /^assets\/models\/v1\/neos\/(cratered|angular|elongated|wedge)-spin-30fps\.webm$/);
});

test('all five reference images use their real aspect ratios', () => {
    const { evaluate } = loadSite();
    const references = plain(evaluate('REFERENCE_ASSETS'));
    for (const [id, asset] of Object.entries(references)) {
        const bytes = readFileSync(new URL(asset.src, staticRoot));
        assert.equal(asset.aspectRatio, bytes.readUInt32BE(16) / bytes.readUInt32BE(20));
        assert.match(evaluate(`createReferenceMarkup({id: ${JSON.stringify(id)}})`), /<img /);
        assert.match(evaluate(`referenceClassName({id: ${JSON.stringify(id)}, category: "landmark", ratio: 1})`), /reference-render/);
    }
    assert.equal(Object.keys(references).length, 5);
    assert.match(evaluate('createReferenceMarkup({id: "statue_of_liberty"})'), /statue-of-liberty\.png/);
    assert.match(evaluate('referenceClassName({id: "average_human", category: "person", ratio: 100})'), /reference-tiny/);
});

test('comparison sizes remain bounded and Everest is labeled as summit elevation', () => {
    const { evaluate } = loadSite();
    const equal = plain(evaluate('getVisualVariables({metrics: {diameter_avg_m: 1.7}}, {id: "average_human", ratio: 1})'));
    assert.equal(equal.asteroidSize, 220);
    assert.equal(equal.referenceSize, 220);
    const mountain = plain(evaluate('getVisualVariables({metrics: {diameter_avg_m: 22}}, {id: "mount_everest", ratio: 22 / 8849})'));
    assert.equal(mountain.referenceSize, 120);
    assert.equal(mountain.asteroidSize, 8);
    assert.ok(mountain.referenceSize * mountain.referenceAspect < 190);
    assert.match(evaluate('getDisplayComparison(fixture.neos[0], "mount_everest").label'), /summit elevation/);
    assert.equal(evaluate('getDisplayComparison(fixture.neos[0], "mount_everest").ratio'), 180 / 8849);
    assert.equal(evaluate('formatRatio(0.001)'), '<0.01');
});

test('unavailable JSON preserves the accessible error state', async () => {
    const { evaluate, document } = loadSite();
    await evaluate('init()');
    const status = document.getElementById('statusMessage');
    assert.match(status.innerHTML, /Unable to load NEO data.*503/);
    assert.equal(status.classList.contains('hidden'), false);
    assert.equal(document.getElementById('retryLoad').hidden, false);
    assert.match(status.innerHTML, /try again/);
    assert.match(readFileSync(new URL('index.html', staticRoot), 'utf8'), /id="statusMessage"[^>]+role="status"/);
});

test('an empty feed explains the result and preserves zero counts', async () => {
    const empty = { ...fixture, neos: [], sort_options: [], summary: { returned_count: 0, candidate_count: 0 } };
    const { evaluate, document } = loadSite(async () => ({ ok: true, json: async () => empty }));
    await evaluate('init()');
    assert.equal(document.getElementById('returnedCount').textContent, '0 of 0');
    assert.match(document.getElementById('statusMessage').innerHTML, /feed returned no objects/);
    assert.equal(document.getElementById('retryLoad').hidden, false);
    assert.equal(document.getElementById('neoGrid').getAttribute('aria-busy'), 'false');
});

test('stalled loads time out, preserve retry focus, and reject duplicate requests', async () => {
    let abort, calls = 0, cleared = false;
    const fetch = (_url, { signal }) => new Promise((_resolve, reject) => {
        calls++;
        signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')));
    });
    const { evaluate, document } = loadSite(fetch, {
        setTimeout(fn, delay) { assert.equal(delay, 15000); abort = fn; return 1; },
        clearTimeout(id) { assert.equal(id, 1); cleared = true; }
    });
    const retry = document.getElementById('retryLoad');
    retry.hidden = false;
    document.activeElement = retry;
    const pending = evaluate('init()');
    await evaluate('init()');
    assert.equal(calls, 1);
    assert.equal(retry.getAttribute('aria-disabled'), 'true');
    assert.equal(retry.hidden, false);
    assert.equal(document.activeElement, retry);
    abort();
    await pending;
    assert.match(document.getElementById('statusMessage').innerHTML, /did not respond in time/);
    assert.equal(retry.getAttribute('aria-disabled'), 'false');
    assert.equal(evaluate('state.loading'), false);
    assert.equal(cleared, true);
});

test('a successful retry clears the error and focuses the observation region', async () => {
    let calls = 0;
    const data = { ...fixture, neos: [fixture.neos[0]], sort_options: [] };
    const { evaluate, document } = loadSite(async () => ++calls === 1
        ? { ok: false, status: 503 }
        : { ok: true, json: async () => data });
    await evaluate('init()');
    const retry = document.getElementById('retryLoad');
    document.activeElement = retry;
    await evaluate('init()');
    assert.equal(calls, 2);
    assert.equal(document.getElementById('statusMessage').classList.contains('hidden'), true);
    assert.equal(retry.hidden, true);
    assert.equal(document.activeElement, document.getElementById('observations'));
    assert.equal(document.getElementById('neoGrid').children.length, 1);
});

test('reference choices survive card rebuilding and stay scoped to their NEO', () => {
    const { evaluate } = loadSite();
    const card = evaluate('createNeoCard(fixture.neos[0])');
    card.querySelector('.reference-select').listeners.get('change')({ target: { value: 'eiffel_tower' } });
    const rebuilt = evaluate('createNeoCard(sortNeos(fixture.neos, "largest").find(n => n.neo_id === fixture.neos[0].neo_id))');
    assert.match(rebuilt.innerHTML, /value="eiffel_tower" selected/);
    assert.match(evaluate('createNeoCard(fixture.neos[1])').innerHTML, /value="average_human" selected/);
});

test('text from the dataset is escaped and obsolete CSS animation is gone', () => {
    const { evaluate } = loadSite();
    assert.equal(evaluate('escapeHtml("<script>bad()</script>")'), '&lt;script&gt;bad()&lt;/script&gt;');
    const card = evaluate('createNeoCard({...fixture.neos[0], name: "<script>bad()</script>"})');
    assert.match(card.innerHTML, /<h3>&lt;script&gt;bad\(\)&lt;\/script&gt;<\/h3>/);
    assert.equal(card.innerHTML.includes('<script>'), false);
    const css = readFileSync(new URL('styles.css', staticRoot), 'utf8');
    assert.equal(css.includes('@keyframes tumble'), false);
    assert.equal(css.includes('@keyframes floaty'), false);
    assert.match(css, /\.neo-video\[hidden\]/);
    assert.match(css, /\.motion-controls\[hidden\]/);
});

test('native reference choices update labels and sizes without rebuilding the card', () => {
    const { evaluate } = loadSite();
    evaluate('window.NeoMotion = {refresh: () => { window.refreshed = true; }}');
    const card = evaluate('createNeoCard(fixture.neos[0])');
    const select = card.querySelector('.reference-select');
    assert.match(card.innerHTML, /<select class="reference-select" aria-label="Compare Demo asteroid 1 against">/);
    assert.match(card.innerHTML, /<dl class="metric-grid">/);
    assert.match(card.innerHTML, /<dt class="meta-label">Avg diameter<\/dt>/);
    assert.equal((card.innerHTML.match(/<option /g) || []).length, 5);
    assert.match(card.innerHTML, /value="statue_of_liberty" selected/);
    select.listeners.get('change')({ target: { value: 'mount_everest' } });
    assert.equal(select.value, 'mount_everest');
    assert.equal(card.style.properties.get('--reference-size'), '120px');
    assert.equal(card.style.properties.get('--asteroid-size'), '8px');
    assert.match(card.querySelector('.comparison-label').textContent, /summit elevation/);
    assert.match(card.querySelector('.reference-object').innerHTML, /everest\.png/);
    assert.equal(card.htmlWrites, 1);
    assert.equal(evaluate('window.refreshed'), true);
});

test('styles remove legacy illustrations and use shared responsive comparison scaling', () => {
    const css = readFileSync(new URL('styles.css', staticRoot), 'utf8');
    for (const legacy of ['.statue-', '.building-', '.mountain-snow', '.reference-svg', '.reference-picker', '.reference-head']) {
        assert.equal(css.includes(legacy), false, legacy);
    }
    assert.ok(Buffer.byteLength(css) < 15000, 'Keep the stylesheet small without minifying source');
    assert.match(css, /width: calc\(var\(--asteroid-size\) \* var\(--comparison-scale\)\)/);
    assert.match(css, /height: calc\(var\(--reference-size\) \* var\(--comparison-scale\)\)/);
    const html = readFileSync(new URL('index.html', staticRoot), 'utf8');
    assert.match(html, /class="skip-link" href="#observations"/);
    assert.match(html, /<details id="comparison-notes" class="reading-note">/);
    assert.match(html, /href="#comparison-explanation"/);
    assert.match(html, /id="comparison-explanation" class="visual-note"/);
    assert.match(html, /aria-controls="neoGrid"/);
    assert.match(css, /@media \(prefers-reduced-motion: reduce\)/);
    assert.equal(source.includes('setupReferencePicker'), false);
});

test('every shipped model matches the reviewed asset manifest', () => {
    const manifest = JSON.parse(readFileSync(new URL('../art/manifest.json', import.meta.url), 'utf8'));
    const folder = new URL('assets/models/v1/', staticRoot);
    assert.equal(Object.keys(manifest.assets).length, 13);
    assert.ok(Object.values(manifest.assets).reduce((sum, entry) => sum + entry.bytes, 0) <= 4 * 1024 ** 2);
    for (const [name, entry] of Object.entries(manifest.assets)) {
        const data = readFileSync(new URL(name, folder));
        assert.equal(createHash('sha256').update(data).digest('hex'), entry.sha256, name);
        assert.equal(data.length, entry.bytes, name);
        if (name.endsWith('.webm')) {
            assert.ok(entry.bytes <= 1024 ** 2, name + ' exceeds the video delivery budget');
            assert.equal(entry.fps, 30);
            assert.equal(entry.frames, entry.duration_seconds * 30);
            assert.equal(entry.alpha_verified, true);
        }
    }
    const { evaluate } = loadSite();
    for (const asset of plain(evaluate('NEO_ASSETS'))) {
        assert.ok(existsSync(new URL(asset.poster, staticRoot)));
        assert.ok(existsSync(new URL(asset.video, staticRoot)));
    }
    const blend = readFileSync(new URL('../art/' + manifest.source.file, import.meta.url));
    assert.equal(createHash('sha256').update(blend).digest('hex'), manifest.source.sha256);
});

test('Blender sources are not deployed and Terraform serves both new media formats', () => {
    const files = readdirSync(fileURLToPath(staticRoot), { recursive: true });
    assert.equal(files.some(f => f.endsWith('.blend') || f.endsWith('.blend1')), false);
    const tf = readFileSync(new URL('../../terraform/website.tf', import.meta.url), 'utf8');
    assert.match(tf, /webm\s*=\s*"video\/webm"/);
    assert.match(tf, /webp\s*=\s*"image\/webp"/);
    assert.match(tf, /website_files\s*=\s*fileset\(local.website_root, "\*\*"\)/);
});
