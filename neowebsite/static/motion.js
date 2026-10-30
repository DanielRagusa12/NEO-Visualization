(() => {
    const preference = window.matchMedia('(prefers-reduced-motion: reduce)');
    const control = document.getElementById('motionToggle');
    let controlReady = false;
    let observer = null;
    let sizeObserver = null;
    let images = [];
    let paused = false;
    try {
        paused = sessionStorage.getItem('neoMotionPaused') === 'true';
    } catch (_) {
        // Playback controls also work when browser storage is unavailable.
    }

    function updateVisibility(image) {
        const bounds = image.getBoundingClientRect();
        image.dataset.inView = String(bounds.bottom > 0 && bounds.top < innerHeight
            && bounds.right > 0 && bounds.left < innerWidth);
    }

    function shouldPlay(image) {
        const bounds = image.getBoundingClientRect();
        return !paused && !preference.matches && !document.hidden
            && ('IntersectionObserver' in window)
            && Math.max(bounds.width, bounds.height) >= 32
            && image.dataset.inView === 'true' && image.dataset.spinFailed !== 'true';
    }

    function stop(image, showPoster = true) {
        const video = image.nextElementSibling;
        if (video?.classList.contains('neo-video')) {
            video.dataset.requested = 'false';
            video.pause();
            video.hidden = showPoster;
        }
        image.style.visibility = showPoster ? 'visible' : 'hidden';
        image.dataset.spinning = 'false';
    }

    function reveal(image, video) {
        if (!shouldPlay(image) || video.paused || video.dataset.alphaVerified !== 'true') return;
        video.hidden = false;
        image.style.visibility = 'hidden';
        image.dataset.spinning = 'true';
    }

    function fail(image, video) {
        image.dataset.spinFailed = 'true';
        stop(image);
        video.removeAttribute('src');
        video.load();
    }

    function syncImage(image) {
        const video = image.nextElementSibling;
        if (!video?.classList.contains('neo-video')) return;
        if (!shouldPlay(image)) {
            const holdFrame = paused && !preference.matches && !document.hidden
                && image.dataset.inView === 'true' && image.dataset.spinFailed !== 'true'
                && video.dataset.alphaVerified === 'true' && video.readyState >= 2;
            stop(image, !holdFrame);
            return;
        }
        if (video.dataset.requested === 'true') return;
        video.dataset.requested = 'true';
        if (!video.getAttribute('src')) video.src = video.dataset.spinSrc;
        const request = video.play();
        request?.catch(error => {
            if (error.name !== 'AbortError' && shouldPlay(image)) fail(image, video);
        });
    }

    function syncAll() {
        images.forEach(syncImage);
        if (!control) return;
        control.disabled = preference.matches;
        control.textContent = preference.matches ? 'Reduced motion enabled'
            : paused ? 'Play asteroid motion' : 'Pause asteroid motion';
    }

    function ensureControl() {
        if (controlReady || !control) return;
        controlReady = true;
        control.parentElement.hidden = false;
        control.addEventListener('click', () => {
            paused = !paused;
            try {
                sessionStorage.setItem('neoMotionPaused', String(paused));
            } catch (_) {
                // Keep the in-memory setting if storage is blocked.
            }
            syncAll();
        });
    }

    function observe(grid) {
        observer?.disconnect();
        sizeObserver?.disconnect();
        images.forEach(image => {
            stop(image);
            const video = image.nextElementSibling;
            video.dataset.disposed = 'true';
            video.removeAttribute('src');
            video.load();
            video.remove();
        });
        ensureControl();
        images = [...grid.querySelectorAll('.neo-image[data-spin-src]')];
        if (control) control.parentElement.hidden = images.length === 0;
        images.forEach(image => {
            updateVisibility(image);
            image.dataset.spinning = 'false';
            const video = document.createElement('video');
            video.className = 'neo-video';
            video.loop = true;
            video.muted = true;
            video.defaultMuted = true;
            video.playsInline = true;
            video.preload = 'none';
            video.hidden = true;
            video.setAttribute('aria-hidden', 'true');
            video.dataset.spinSrc = image.dataset.spinSrc;
            image.after(video);
            if (!video.canPlayType('video/webm; codecs="vp9"')) {
                image.dataset.spinFailed = 'true';
            }
            video.addEventListener('loadeddata', () => {
                if (video.dataset.disposed === 'true') return;
                try {
                    // VP9 support alone does not guarantee transparent video support.
                    const canvas = document.createElement('canvas');
                    canvas.width = video.videoWidth;
                    canvas.height = video.videoHeight;
                    const context = canvas.getContext('2d', { willReadFrequently: true });
                    context.drawImage(video, 0, 0);
                    if (context.getImageData(0, 0, 1, 1).data[3] !== 0) {
                        fail(image, video);
                        return;
                    }
                    video.dataset.alphaVerified = 'true';
                    reveal(image, video);
                } catch (_) {
                    fail(image, video);
                }
            });
            video.addEventListener('playing', () => {
                if (video.dataset.disposed === 'true') return;
                if (shouldPlay(image)) reveal(image, video);
                else syncImage(image);
            });
            video.addEventListener('error', () => {
                if (video.dataset.disposed !== 'true' && image.dataset.spinFailed !== 'true') {
                    fail(image, video);
                }
            });
        });
        if ('IntersectionObserver' in window) {
            observer = new IntersectionObserver(entries => {
                entries.forEach(entry => {
                    entry.target.dataset.inView = String(entry.isIntersecting);
                    syncImage(entry.target);
                });
            }, { threshold: 0.05 });
            images.forEach(image => observer.observe(image));
        }
        if ('ResizeObserver' in window) {
            sizeObserver = new ResizeObserver(entries => {
                entries.forEach(entry => {
                    updateVisibility(entry.target);
                    syncImage(entry.target);
                });
            });
            images.forEach(image => sizeObserver.observe(image));
        }
        syncAll();
    }

    function refresh() {
        images.forEach(updateVisibility);
        syncAll();
    }

    window.NeoMotion = { observe, refresh };
    document.addEventListener('visibilitychange', syncAll);
    preference.addEventListener('change', syncAll);
})();
