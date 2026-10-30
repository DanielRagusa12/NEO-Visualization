import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const source = readFileSync(new URL('../static/motion.js', import.meta.url), 'utf8');

class Element extends EventTarget {
    constructor() {
        super();
        this.dataset = {};
        this.style = {};
        this.attributes = new Map();
        this.className = '';
        this.hidden = false;
    }
    get classList() { return { contains: name => this.className.split(' ').includes(name) }; }
    setAttribute(name, value) { this.attributes.set(name, String(value)); }
    getAttribute(name) { return this.attributes.get(name) ?? null; }
    removeAttribute(name) { this.attributes.delete(name); }
    emit(type) { this.dispatchEvent(new Event(type)); }
}

class Image extends Element {
    constructor(size = 120, top = 100) {
        super();
        this.size = size;
        this.top = top;
        this.connected = true;
        this.dataset.spinSrc = 'assets/models/v1/neos/cratered-spin-30fps.webm';
    }
    getBoundingClientRect() {
        if (!this.connected) return { top: 0, bottom: 0, left: 0, right: 0, width: 0, height: 0 };
        return { top: this.top, bottom: this.top + this.size, left: 100, right: 100 + this.size,
            width: this.size, height: this.size };
    }
    after(video) { this.nextElementSibling = video; video.image = this; }
}

function setup(options = {}) {
    const videos = [];
    const control = new Element();
    control.parentElement = { hidden: true };
    const document = new EventTarget();
    document.hidden = false;
    document.getElementById = id => id === 'motionToggle' ? control : null;
    document.createElement = tag => {
        if (tag === 'canvas') return {
            getContext: () => ({ drawImage() {}, getImageData: () => ({ data: [0, 0, 0, options.alpha ?? 0] }) })
        };
        assert.equal(tag, 'video');
        const video = new Element();
        video.paused = true;
        video.readyState = 0;
        video.videoWidth = 256;
        video.videoHeight = 256;
        video.playCalls = 0;
        video.loadCalls = 0;
        video.canPlayType = () => options.codec === false ? '' : 'probably';
        Object.defineProperty(video, 'src', {
            get: () => video.getAttribute('src') ?? '',
            set: value => video.setAttribute('src', value)
        });
        video.play = () => {
            video.playCalls++;
            if (options.rejectPlay) return Promise.reject(new Error('Playback blocked'));
            video.paused = false;
            return Promise.resolve();
        };
        video.pause = () => { video.paused = true; };
        video.load = () => { video.loadCalls++; video.readyState = 0; video.paused = true; };
        video.remove = () => { if (video.image.nextElementSibling === video) video.image.nextElementSibling = null; };
        videos.push(video);
        return video;
    };
    const preference = new EventTarget();
    preference.matches = options.reduced ?? false;
    const observers = [];
    const resizers = [];
    class Observer {
        constructor(callback) { this.callback = callback; this.targets = []; observers.push(this); }
        observe(target) { this.targets.push(target); }
        disconnect() { this.targets = []; }
        intersect(target, isIntersecting) { this.callback([{ target, isIntersecting }]); }
    }
    class Resizer extends Observer {
        constructor(callback) { super(callback); resizers.push(this); }
        resize(target) { this.callback([{ target }]); }
    }
    const storage = new Map();
    const window = { matchMedia: () => preference, ResizeObserver: Resizer };
    if (options.observer !== false) window.IntersectionObserver = Observer;
    const context = vm.createContext({
        window, document, innerHeight: 1000, innerWidth: 1000,
        IntersectionObserver: Observer, ResizeObserver: Resizer,
        sessionStorage: {
            getItem: key => { if (options.noStorage) throw Error(); return storage.get(key) ?? null; },
            setItem: (key, value) => { if (options.noStorage) throw Error(); storage.set(key, value); }
        }
    });
    vm.runInContext(source, context);
    return {
        videos, control, document, preference, observers, resizers,
        observe(images) { window.NeoMotion.observe({ querySelectorAll: () => images }); },
        refresh() { window.NeoMotion.refresh(); },
        ready(video = videos[0]) { video.readyState = 4; video.emit('loadeddata'); video.emit('playing'); },
        reduce(value) { preference.matches = value; preference.dispatchEvent(new Event('change')); }
    };
}

test('only visible, sufficiently large asteroids get a video source', () => {
    const app = setup();
    const visible = new Image(), offscreen = new Image(120, 1200), tiny = new Image(8);
    app.observe([visible, offscreen, tiny]);
    assert.ok(app.videos[0].src.endsWith('.webm'));
    assert.equal(app.videos[1].src, '');
    assert.equal(app.videos[2].src, '');
    assert.equal(app.videos[0].preload, 'none');
    assert.equal(app.videos[0].muted, true);
    assert.equal(app.videos[0].playsInline, true);
    app.ready();
    assert.equal(visible.dataset.spinning, 'true');
    assert.equal(visible.style.visibility, 'hidden');
    assert.equal(app.videos[0].hidden, false);
});

test('empty feeds hide motion controls and a later load restores them', () => {
    const app = setup();
    app.observe([]);
    assert.equal(app.control.parentElement.hidden, true);
    app.observe([new Image()]);
    assert.equal(app.control.parentElement.hidden, false);
});

test('reduced motion loads no video and switching the preference stops playback', () => {
    const app = setup({ reduced: true });
    const image = new Image();
    app.observe([image]);
    assert.equal(app.videos[0].src, '');
    assert.equal(app.control.disabled, true);
    app.reduce(false);
    app.ready();
    assert.equal(image.dataset.spinning, 'true');
    app.reduce(true);
    assert.equal(app.videos[0].paused, true);
    assert.equal(app.videos[0].hidden, true);
    assert.equal(image.style.visibility, 'visible');
});

test('pause freezes the current frame and play resumes it', () => {
    const app = setup({ noStorage: true });
    const image = new Image();
    app.observe([image]);
    app.ready();
    app.control.emit('click');
    assert.equal(app.videos[0].paused, true);
    assert.equal(app.videos[0].hidden, false);
    assert.equal(app.control.textContent, 'Play asteroid motion');
    app.control.emit('click');
    assert.equal(app.videos[0].paused, false);
    assert.equal(app.control.textContent, 'Pause asteroid motion');
});

test('offscreen and background playback stops; returning resumes it', () => {
    const app = setup();
    const image = new Image();
    app.observe([image]);
    app.ready();
    app.observers[0].intersect(image, false);
    assert.equal(app.videos[0].paused, true);
    assert.equal(image.style.visibility, 'visible');
    app.observers[0].intersect(image, true);
    assert.equal(app.videos[0].paused, false);
    app.document.hidden = true;
    app.document.dispatchEvent(new Event('visibilitychange'));
    assert.equal(app.videos[0].paused, true);
    app.document.hidden = false;
    app.document.dispatchEvent(new Event('visibilitychange'));
    assert.equal(app.videos[0].paused, false);
});

test('resizing a comparison starts or stops decoding at the size threshold', () => {
    const app = setup();
    const image = new Image(8);
    app.observe([image]);
    assert.equal(app.videos[0].src, '');
    image.size = 80;
    app.resizers[0].resize(image);
    assert.ok(app.videos[0].src);
    app.ready();
    image.size = 8;
    app.resizers[0].resize(image);
    assert.equal(app.videos[0].paused, true);
});

test('reference changes can refresh playback immediately without waiting for an observer', () => {
    const app = setup();
    const image = new Image();
    app.observe([image]);
    app.ready();
    image.size = 8;
    app.refresh();
    assert.equal(app.videos[0].paused, true);
    assert.equal(image.style.visibility, 'visible');
    image.size = 120;
    app.refresh();
    assert.equal(app.videos[0].paused, false);
});

test('unsupported codecs, missing alpha, and failed playback keep the poster', async () => {
    for (const options of [{ codec: false }, { alpha: 255 }, { rejectPlay: true }, { observer: false }]) {
        const app = setup(options);
        const image = new Image();
        app.observe([image]);
        if (options.alpha === 255) app.ready();
        await Promise.resolve();
        assert.notEqual(image.dataset.spinning, 'true');
        assert.equal(image.style.visibility, 'visible');
        assert.equal(app.videos[0].hidden, true);
    }
});

test('sorting releases retired players and does not duplicate the pause listener', () => {
    const app = setup();
    const old = new Image();
    app.observe([old]);
    app.ready();
    old.connected = false;
    const replacement = new Image();
    app.observe([replacement]);
    assert.equal(app.videos[0].paused, true);
    assert.equal(app.videos[0].src, '');
    assert.equal(old.nextElementSibling, null);
    assert.ok(app.videos[1].src);
    app.control.emit('click');
    assert.equal(app.control.textContent, 'Play asteroid motion');
    assert.equal(app.videos[1].paused, true);
});
