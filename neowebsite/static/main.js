const DATA_URL = '/data/latest.json';
const FEED_STALE_AFTER_MS = 36 * 60 * 60 * 1000;

const ASSET_ROOT = 'assets/models/v1';
const REFERENCE_ASSETS = {
    average_human: { src: `${ASSET_ROOT}/references/human.png`, aspectRatio: 168 / 440 },
    statue_of_liberty: { src: `${ASSET_ROOT}/references/statue-of-liberty.png`, aspectRatio: 144 / 440 },
    eiffel_tower: { src: `${ASSET_ROOT}/references/eiffel-tower.png`, aspectRatio: 217 / 440 },
    burj_khalifa: { src: `${ASSET_ROOT}/references/burj-khalifa.png`, aspectRatio: 71 / 440 },
    mount_everest: { src: `${ASSET_ROOT}/references/everest.png`, aspectRatio: 480 / 314 }
};
const NEO_ASSETS = ['cratered', 'angular', 'elongated', 'wedge'].map(id => ({
    poster: `${ASSET_ROOT}/neos/${id}-poster.webp`,
    video: `${ASSET_ROOT}/neos/${id}-spin-30fps.webm`
}));
const ALLOWED_REFERENCE_IDS = new Set([
    'average_human',
    'statue_of_liberty',
    'eiffel_tower',
    'burj_khalifa',
    'mount_everest'
]);

const state = {
    data: null,
    neos: [],
    referenceObjects: new Map(),
    activeSortId: 'visual_interest',
    referenceSelections: new Map(),
    loading: false
};

document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('retryLoad')?.addEventListener('click', init);
    init();
    // Recheck age locally, without polling the data endpoint.
    setInterval(refreshFeedAge, 60000);
});
document.addEventListener('visibilitychange', refreshFeedAge);

async function init() {
    if (state.loading) return;
    state.loading = true;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    const grid = document.getElementById('neoGrid');
    grid.setAttribute('aria-busy', 'true');
    showStatus('Loading the observation feed...', { busy: true });

    try {
        const response = await fetch(DATA_URL, { signal: controller.signal });

        if (!response.ok) {
            throw new Error(`The observation feed returned HTTP ${response.status}.`);
        }

        state.data = await response.json();
        state.neos = [...(state.data.neos || [])];
        state.referenceObjects = new Map(
            (state.data.reference_objects || [])
                .filter(reference => ALLOWED_REFERENCE_IDS.has(reference.id))
                .map(reference => [reference.id, reference])
        );

        renderSummary(state.data);
        renderSortControls(state.data.sort_options || []);
        renderCards(sortNeos(state.neos, state.activeSortId));
        if (state.neos.length === 0) {
            showStatus('The feed returned no objects for this observation window. Try loading it again later.');
        } else {
            const retry = document.getElementById('retryLoad');
            const moveFocus = retry && document.activeElement === retry;
            hideStatus();
            if (moveFocus) document.getElementById('observations')?.focus();
        }
    } catch (error) {
        showStatus(error.name === 'AbortError'
            ? 'The observation feed did not respond in time. Try loading it again.'
            : `Unable to load NEO data. ${error.message} Check your connection and try again.`);
    } finally {
        clearTimeout(timeout);
        state.loading = false;
        grid.setAttribute('aria-busy', 'false');
        document.getElementById('retryLoad')?.setAttribute('aria-disabled', 'false');
    }
}

function renderSummary(data) {
    const summary = data.summary || {};

    setText('windowRange', `${formatDate(data.window_start_date)} - ${formatDate(data.window_end_date)}`);
    setText('returnedCount', `${summary.returned_count ?? data.neos?.length ?? 0} of ${summary.candidate_count ?? '--'}`);
    setText('largestNeo', summary.largest_neo_name || '--');
    setText('closestNeo', summary.closest_neo_name || '--');
    renderFreshness(data);
}

function feedFreshness(data, now = Date.now()) {
    const fetched = Date.parse(data.fetched_at || '');
    const windowEnd = Date.parse(`${data.window_end_date || ''}T00:00:00Z`) + 86400000;
    const label = Number.isFinite(fetched)
        ? `Updated ${new Intl.DateTimeFormat('en', {
            year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
            timeZone: 'UTC', timeZoneName: 'short', hourCycle: 'h23'
        }).format(new Date(fetched))}`
        : 'Update time unavailable';
    let warning = '';
    if (Number.isFinite(windowEnd) && now >= windowEnd) {
        warning = 'This observation window has ended. The published feed may be outdated.';
    } else if (Number.isFinite(fetched) && fetched > now + 300000) {
        warning = 'The feed timestamp is in the future. Its age could not be verified.';
    } else if (Number.isFinite(fetched) && now - fetched > FEED_STALE_AFTER_MS) {
        warning = 'This feed is more than 36 hours old. It may not include the latest observations.';
    }
    return { label, warning };
}

function renderFreshness(data) {
    const freshness = feedFreshness(data);
    const stamp = document.getElementById('feedFreshness');
    const warning = document.getElementById('feedWarning');
    if (stamp && stamp.textContent !== freshness.label) stamp.textContent = freshness.label;
    if (warning) {
        if (warning.textContent !== freshness.warning) warning.textContent = freshness.warning;
        warning.hidden = !freshness.warning;
    }
}

function refreshFeedAge() {
    if (!document.hidden && state.data) renderFreshness(state.data);
}

function renderSortControls(sortOptions) {
    const container = document.getElementById('sortControls');
    container.innerHTML = '';

    sortOptions.forEach(option => {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'sort-button';
        button.textContent = option.label;
        button.dataset.sortId = option.id;
        button.setAttribute('aria-pressed', option.id === state.activeSortId ? 'true' : 'false');

        if (option.id === state.activeSortId) {
            button.classList.add('active');
        }

        button.addEventListener('click', () => {
            state.activeSortId = option.id;
            updateActiveSortButton();
            renderCards(sortNeos(state.neos, state.activeSortId));
        });

        container.appendChild(button);
    });
}

function updateActiveSortButton() {
    document.querySelectorAll('.sort-button').forEach(button => {
        const isActive = button.dataset.sortId === state.activeSortId;
        button.classList.toggle('active', isActive);
        button.setAttribute('aria-pressed', isActive ? 'true' : 'false');
    });
}

function sortNeos(neos, sortId) {
    const sortOption = (state.data?.sort_options || []).find(option => option.id === sortId);
    if (!sortOption) return neos;

    return [...neos].sort((a, b) => {
        const aValue = getValueByPath(a, sortOption.field);
        const bValue = getValueByPath(b, sortOption.field);

        if (typeof aValue === 'boolean' || typeof bValue === 'boolean') {
            return sortOption.direction === 'asc'
                ? Number(aValue) - Number(bValue)
                : Number(bValue) - Number(aValue);
        }

        const aNumber = Number(aValue);
        const bNumber = Number(bValue);

        if (Number.isFinite(aNumber) && Number.isFinite(bNumber)) {
            return sortOption.direction === 'asc' ? aNumber - bNumber : bNumber - aNumber;
        }

        return String(aValue).localeCompare(String(bValue));
    });
}

function renderCards(neos) {
    const grid = document.getElementById('neoGrid');
    grid.innerHTML = '';

    neos.forEach(neo => {
        grid.appendChild(createNeoCard(neo));
    });
    window.NeoMotion?.observe(grid);
}

function getNeoAsset(neo) {
    const seed = seedFromString(neo.visualization?.asteroid_shape_seed || neo.neo_id || neo.name || 'neo');
    return NEO_ASSETS[seed % NEO_ASSETS.length];
}

function referenceClassName(comparison) {
    const rendered = REFERENCE_ASSETS[comparison.id] ? ' reference-render' : '';
    const tiny = comparison.ratio > 40 ? ' reference-tiny' : '';
    return `reference-object${rendered}${tiny}`;
}

function rankLabel(neo, sortId = state.activeSortId) {
    const ranks = {
        visual_interest: ['visual_interest_rank', 'in visual interest'],
        largest: ['size_rank', 'largest'],
        closest: ['closest_rank', 'closest'],
        fastest: ['fastest_rank', 'fastest'],
        soonest: ['soonest_rank', 'soonest']
    };
    if (sortId === 'hazardous') return 'Grouped by hazard classification';
    const config = ranks[sortId];
    return config ? `#${neo.ranking?.[config[0]] || '--'} ${config[1]}` : 'Observation';
}

function createNeoCard(neo) {
    const card = document.createElement('article');
    card.className = 'neo-card';

    const metrics = neo.metrics || {};
    const ranking = neo.ranking || {};
    const approach = neo.close_approach || {};
    const comparison = getDisplayComparison(neo, state.referenceSelections.get(String(neo.neo_id || neo.name || '')));
    const visualVars = getVisualVariables(neo, comparison);
    const asset = getNeoAsset(neo);

    card.style.setProperty('--asteroid-size', `${visualVars.asteroidSize}px`);
    card.style.setProperty('--reference-size', `${visualVars.referenceSize}px`);
    card.style.setProperty('--reference-aspect', visualVars.referenceAspect);

    card.innerHTML = `
        <header class="card-heading">
            <div class="card-topline">
                <span class="rank-pill">${escapeHtml(rankLabel(neo))}</span>
                ${metrics.is_hazardous ? '<span class="hazard-pill">Potentially hazardous</span>' : ''}
            </div>
            <h3>${escapeHtml(neo.name || 'Unnamed NEO')}</h3>
        </header>
        <div class="visual-panel" aria-hidden="true">
            <span class="visual-kicker">Diameter / height comparison</span>
            <div class="asteroid-wrap">
                <div class="asteroid">
                    <img class="neo-image" src="${asset.poster}" data-spin-src="${asset.video}" alt="" decoding="async">
                </div>
                <span class="object-label">Asteroid</span>
            </div>
            <div class="reference-marker">
                <div class="${escapeAttribute(referenceClassName(comparison))}">
                    ${createReferenceMarkup(comparison)}
                </div>
                <span class="object-label">Reference</span>
            </div>
        </div>
        <div class="neo-content">
            <div>
                <label class="reference-select-label">
                    <span>Compare against</span>
                    <select class="reference-select" aria-label="Compare ${escapeAttribute(neo.name || 'this object')} against">
                        ${createReferenceOptions(comparison.id)}
                    </select>
                </label>
                <p class="comparison-label">${escapeHtml(comparison.label)}</p>
                <p class="scale-note"${visualVars.enlargementNote ? '' : ' hidden'}>${escapeHtml(visualVars.enlargementNote)}</p>
            </div>
            <dl class="metric-grid">
                ${metricMarkup('Avg diameter', `${formatNumber(metrics.diameter_avg_m)} m`)}
                ${metricMarkup('Closest pass', `${formatNumber(metrics.miss_distance_lunar)} lunar`)}
                ${metricMarkup('Speed', `${formatNumber(metrics.velocity_kph)} km/h`)}
                ${metricMarkup('Approach date, UTC', formatApproach(approach))}
            </dl>
        </div>
        <footer class="neo-footer">
            <div class="rank-summary" aria-label="Other rankings">
                <span>#${escapeHtml(ranking.size_rank || '--')} largest</span>
                <span>#${escapeHtml(ranking.closest_rank || '--')} closest</span>
                <span>#${escapeHtml(ranking.fastest_rank || '--')} fastest</span>
            </div>
            <a href="${escapeAttribute(neo.nasa_jpl_url || '#')}" target="_blank" rel="noopener noreferrer" aria-label="NASA JPL details for ${escapeAttribute(neo.name || 'this object')}, opens in a new tab">NASA JPL ↗</a>
        </footer>
    `;

    card.querySelector('.reference-select').addEventListener('change', event => {
        updateCardComparison(card, neo, event.target.value);
    });

    return card;
}

function metricMarkup(label, value) {
    return `
        <div class="metric">
            <dt class="meta-label">${escapeHtml(label)}</dt>
            <dd>${escapeHtml(value)}</dd>
        </div>
    `;
}

function updateCardComparison(card, neo, referenceId) {
    const comparison = getDisplayComparison(neo, referenceId);
    state.referenceSelections.set(String(neo.neo_id || neo.name || ''), comparison.id);
    const visualVars = getVisualVariables(neo, comparison);
    const referenceObject = card.querySelector('.reference-object');

    card.style.setProperty('--asteroid-size', `${visualVars.asteroidSize}px`);
    card.style.setProperty('--reference-size', `${visualVars.referenceSize}px`);
    card.style.setProperty('--reference-aspect', visualVars.referenceAspect);
    card.querySelector('.comparison-label').textContent = comparison.label;
    const note = card.querySelector('.scale-note');
    note.textContent = visualVars.enlargementNote;
    note.hidden = !visualVars.enlargementNote;

    referenceObject.className = referenceClassName(comparison);
    referenceObject.innerHTML = createReferenceMarkup(comparison);
    card.querySelector('.reference-select').value = comparison.id || '';
    window.NeoMotion?.refresh?.();
}

function createReferenceOptions(selectedReferenceId) {
    return [...state.referenceObjects.values()].map(reference => `
        <option value="${escapeAttribute(reference.id)}"${reference.id === selectedReferenceId ? ' selected' : ''}>${escapeHtml(reference.name)}</option>
    `).join('');
}

function getDisplayComparison(neo, selectedReferenceId) {
    const visualization = neo.visualization || {};
    const metrics = neo.metrics || {};
    const preferredReferenceId = selectedReferenceId || visualization.closest_reference_id || visualization.primary_reference_id;
    const referenceId = state.referenceObjects.has(preferredReferenceId)
        ? preferredReferenceId
        : state.referenceObjects.keys().next().value;
    const ratio = (visualization.comparison_ratios || []).find(comparison => comparison.reference_id === referenceId);
    const reference = state.referenceObjects.get(referenceId) || {
        id: referenceId,
        name: visualization.closest_reference_name || visualization.primary_reference_name || 'reference object',
        category: 'landmark'
    };
    const diameter = Number(metrics.diameter_avg_m || visualization.diameter_avg_m || 0);
    const referenceSize = Number(reference.height_m || ratio?.reference_height_m || 0);
    const neoToReferenceRatio = referenceSize > 0 && diameter > 0
        ? diameter / referenceSize
        : Number(ratio?.neo_to_reference_ratio ?? visualization.primary_reference_ratio ?? 1);
    const measurement = measurementWord(reference.category);

    return {
        id: reference.id,
        name: reference.name,
        category: normalizeCategory(reference.category),
        ratio: neoToReferenceRatio,
        label: `About ${formatRatio(neoToReferenceRatio)}x the ${measurement} of ${referencePhrase(reference)}`
    };
}

function createReferenceMarkup(comparison) {
    const asset = REFERENCE_ASSETS[comparison.id];
    return asset
        ? `<img class="reference-image" src="${asset.src}" alt="" decoding="async">`
        : '<span class="reference-fallback">?</span>';
}

function getVisualVariables(neo, comparison) {
    const metrics = neo.metrics || {};
    const visualization = neo.visualization || {};
    const diameter = Number(metrics.diameter_avg_m || visualization.diameter_avg_m || 50);
    const ratio = Number.isFinite(Number(comparison.ratio)) ? Number(comparison.ratio) : 1;
    const referenceMeters = diameter / (ratio > 0 ? ratio : 1);
    const largestMeters = Math.max(diameter, referenceMeters);
    // Fit the mountain's wider silhouette without stretching it or changing the size ratio.
    const sceneMaxPx = comparison.id === 'mount_everest' ? 120 : 220;
    const sceneMinPx = 8;

    const asteroidPixels = (diameter / largestMeters) * sceneMaxPx;
    const referencePixels = (referenceMeters / largestMeters) * sceneMaxPx;
    const enlargementNote = asteroidPixels < sceneMinPx
        ? 'Asteroid enlarged for visibility. The diagram is not to scale.'
        : referencePixels < sceneMinPx
            ? 'Reference enlarged for visibility. The diagram is not to scale.' : '';
    return {
        asteroidSize: clamp(asteroidPixels, sceneMinPx, sceneMaxPx),
        referenceSize: clamp(referencePixels, sceneMinPx, sceneMaxPx),
        referenceAspect: REFERENCE_ASSETS[comparison.id]?.aspectRatio || 1,
        enlargementNote
    };
}

function measurementWord(category) {
    return category === 'mountain' ? 'summit elevation' : 'height';
}

function normalizeCategory(category = '') {
    if (category === 'person') return 'person';
    if (category === 'mountain') return 'mountain';
    return 'landmark';
}

function referencePhrase(reference) {
    if (reference.category === 'landmark') {
        return `the ${reference.name}`;
    }

    if (reference.category === 'mountain') {
        return reference.name;
    }

    const name = lowercaseFirst(reference.name || 'reference object');
    const article = startsWithVowelSound(name) ? 'an' : 'a';
    return `${article} ${name}`;
}

function lowercaseFirst(value) {
    return value.charAt(0).toLowerCase() + value.slice(1);
}

function startsWithVowelSound(value = '') {
    return /^[aeiou]/i.test(value.trim());
}

function formatRatio(value) {
    if (!Number.isFinite(value)) return '--';
    if (value > 0 && value < 0.01) {
        return '<0.01';
    }

    return new Intl.NumberFormat('en', { maximumFractionDigits: value >= 10 ? 0 : 2 }).format(value);
}

function seedFromString(value) {
    return String(value).split('').reduce((hash, char) => hash + char.charCodeAt(0), 0);
}

function getValueByPath(object, path) {
    return path.split('.').reduce((value, key) => value?.[key], object);
}

function formatDate(value) {
    if (!value) return '--';
    const date = new Date(`${value}T00:00:00Z`);
    return new Intl.DateTimeFormat('en', { month: 'short', day: 'numeric' }).format(date);
}

function formatApproach(approach) {
    const date = new Date(`${approach.date || ''}T00:00:00Z`);
    if (!Number.isFinite(date.getTime())) return '--';
    return new Intl.DateTimeFormat('en', {
        month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC'
    }).format(date);
}

function formatNumber(value) {
    const number = Number(value);
    if (!Number.isFinite(number)) return '--';
    return new Intl.NumberFormat('en', { maximumFractionDigits: number >= 100 ? 0 : 1 }).format(number);
}

function clamp(value, min, max) {
    return Math.min(Math.max(value, min), max);
}

function setText(id, value) {
    document.getElementById(id).textContent = value;
}

function hideStatus() {
    document.getElementById('statusMessage').classList.add('hidden');
    const retry = document.getElementById('retryLoad');
    if (retry) retry.hidden = true;
}

function showStatus(message, { busy = false } = {}) {
    const status = document.getElementById('statusMessage');
    status.innerHTML = `${busy ? '<span class="loader" aria-hidden="true"></span>' : ''}${escapeHtml(message)}`;
    status.classList.remove('hidden');
    const retry = document.getElementById('retryLoad');
    if (retry) {
        if (!busy) retry.hidden = false;
        retry.setAttribute('aria-disabled', String(busy));
    }
}

function escapeHtml(value) {
    return String(value)
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#039;');
}

function escapeAttribute(value) {
    return escapeHtml(value);
}
