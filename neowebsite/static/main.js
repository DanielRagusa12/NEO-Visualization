const DATA_URL = '/data/latest.json';

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
    activeSortId: 'visual_interest'
};

document.addEventListener('DOMContentLoaded', init);

async function init() {
    try {
        const response = await fetch(DATA_URL);

        if (!response.ok) {
            throw new Error(`Data endpoint returned ${response.status}`);
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
        hideStatus();
    } catch (error) {
        showStatus(`Unable to load NEO data. ${error.message}`);
    }
}

function renderSummary(data) {
    const summary = data.summary || {};

    setText('windowRange', `${formatDate(data.window_start_date)} - ${formatDate(data.window_end_date)}`);
    setText('returnedCount', `${summary.returned_count || data.neos?.length || 0} of ${summary.candidate_count || '--'}`);
    setText('largestNeo', summary.largest_neo_name || '--');
    setText('closestNeo', summary.closest_neo_name || '--');
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
    return `reference-object reference-${comparison.category} reference-${comparison.id}${rendered}${tiny}`;
}

function createNeoCard(neo) {
    const card = document.createElement('article');
    card.className = 'neo-card';

    const metrics = neo.metrics || {};
    const ranking = neo.ranking || {};
    const approach = neo.close_approach || {};
    const comparison = getDisplayComparison(neo);
    const visualVars = getVisualVariables(neo, comparison);
    const asset = getNeoAsset(neo);

    card.style.setProperty('--asteroid-size', `${visualVars.asteroidSize}px`);
    card.style.setProperty('--reference-size', `${visualVars.referenceSize}px`);
    card.style.setProperty('--reference-aspect', visualVars.referenceAspect);

    card.innerHTML = `
        <div class="visual-panel" aria-hidden="true">
            <div class="asteroid-wrap">
                <div class="asteroid">
                    <img class="neo-image" src="${asset.poster}" data-spin-src="${asset.video}" alt="" decoding="async">
                </div>
            </div>
            <div class="reference-marker">
                <div class="reference-scale-line"></div>
                <div class="${escapeAttribute(referenceClassName(comparison))}" title="${escapeAttribute(comparison.name)}">
                    ${createReferenceMarkup(comparison)}
                </div>
            </div>
        </div>
        <div class="neo-content">
            <div class="card-topline">
                <span class="rank-pill">#${ranking.visual_interest_rank || '--'} Interesting</span>
                ${metrics.is_hazardous ? '<span class="hazard-pill">Potentially hazardous</span>' : ''}
            </div>
            <h3>${escapeHtml(neo.name || 'Unnamed NEO')}</h3>
            <div class="reference-select-label">
                Compare against
                <div class="reference-picker">
                    <button class="reference-picker-button" type="button" aria-expanded="false">
                        <span>${escapeHtml(comparison.name)}</span>
                    </button>
                    <div class="reference-picker-menu" role="listbox">
                        ${createReferenceOptions(comparison.id)}
                    </div>
                </div>
            </div>
            <p class="comparison-label">${escapeHtml(comparison.label)}</p>
            <div class="metric-grid">
                ${metricMarkup('Avg Diameter', `${formatNumber(metrics.diameter_avg_m)} m`)}
                ${metricMarkup('Closest Pass', `${formatNumber(metrics.miss_distance_lunar)} lunar`)}
                ${metricMarkup('Speed', `${formatNumber(metrics.velocity_kph)} km/h`)}
                ${metricMarkup('Approach', formatApproach(approach))}
            </div>
            <div class="neo-footer">
                <span>#${ranking.size_rank || '--'} largest</span>
                <span>#${ranking.closest_rank || '--'} closest</span>
                <span>#${ranking.fastest_rank || '--'} fastest</span>
                <a href="${escapeAttribute(neo.nasa_jpl_url || '#')}" target="_blank" rel="noreferrer">NASA JPL</a>
            </div>
        </div>
    `;

    setupReferencePicker(card, neo);

    return card;
}

function metricMarkup(label, value) {
    return `
        <div class="metric">
            <span class="meta-label">${escapeHtml(label)}</span>
            <strong>${escapeHtml(value)}</strong>
        </div>
    `;
}

function updateCardComparison(card, neo, referenceId) {
    const comparison = getDisplayComparison(neo, referenceId);
    const visualVars = getVisualVariables(neo, comparison);
    const referenceObject = card.querySelector('.reference-object');

    card.style.setProperty('--asteroid-size', `${visualVars.asteroidSize}px`);
    card.style.setProperty('--reference-size', `${visualVars.referenceSize}px`);
    card.style.setProperty('--reference-aspect', visualVars.referenceAspect);
    card.querySelector('.comparison-label').textContent = comparison.label;

    referenceObject.className = referenceClassName(comparison);
    referenceObject.title = comparison.name;
    referenceObject.innerHTML = createReferenceMarkup(comparison);
    card.querySelector('.reference-picker-button span').textContent = comparison.name;

    card.querySelectorAll('.reference-picker-option').forEach(option => {
        option.classList.toggle('active', option.dataset.referenceId === comparison.id);
        option.setAttribute('aria-selected', option.dataset.referenceId === comparison.id ? 'true' : 'false');
    });
}

function createReferenceOptions(selectedReferenceId) {
    return [...state.referenceObjects.values()].map(reference => `
        <button class="reference-picker-option ${reference.id === selectedReferenceId ? 'active' : ''}" type="button" role="option" aria-selected="${reference.id === selectedReferenceId ? 'true' : 'false'}" data-reference-id="${escapeAttribute(reference.id)}">
            ${escapeHtml(reference.name)}
        </button>
    `).join('');
}

function setupReferencePicker(card, neo) {
    const picker = card.querySelector('.reference-picker');
    const button = card.querySelector('.reference-picker-button');
    const options = card.querySelectorAll('.reference-picker-option');

    button.addEventListener('click', event => {
        event.stopPropagation();
        const isOpen = picker.classList.toggle('open');
        button.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
    });

    options.forEach(option => {
        option.addEventListener('click', event => {
            event.stopPropagation();
            updateCardComparison(card, neo, option.dataset.referenceId);
            picker.classList.remove('open');
            button.setAttribute('aria-expanded', 'false');
        });
    });
}

document.addEventListener('click', () => {
    document.querySelectorAll('.reference-picker.open').forEach(picker => {
        picker.classList.remove('open');
        picker.querySelector('.reference-picker-button').setAttribute('aria-expanded', 'false');
    });
});

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

function createReferenceShapeMarkup(category) {
    if (category === 'person') {
        return '<span class="reference-head"></span><span class="reference-torso"></span><span class="reference-base"></span>';
    }

    if (category === 'mountain') {
        return '<span class="mountain-silhouette"></span>';
    }

    return '<span class="landmark-silhouette"></span>';
}

function createReferenceMarkup(comparison) {
    const asset = REFERENCE_ASSETS[comparison.id];

    if (asset) {
        return `<img class="reference-image" src="${asset.src}" alt="" decoding="async">`;
    }

    if (comparison.id === 'average_human') {
        return `
            <svg class="reference-svg reference-svg-human" viewBox="0 0 44 120" aria-hidden="true" focusable="false">
                <path d="M22 2c8 0 14 6 14 14s-6 14-14 14S8 24 8 16 14 2 22 2z" />
                <path d="M18 28h8c8 0 14 7 14 16v37h-9V45h-3v73h-9V45h-3v36H7V44c0-9 5-16 11-16z" />
            </svg>
        `;
    }

    return createReferenceShapeMarkup(comparison.category);
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

    return {
        asteroidSize: clamp((diameter / largestMeters) * sceneMaxPx, sceneMinPx, sceneMaxPx),
        referenceSize: clamp((referenceMeters / largestMeters) * sceneMaxPx, sceneMinPx, sceneMaxPx),
        referenceAspect: REFERENCE_ASSETS[comparison.id]?.aspectRatio || 1
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
    if (!approach.date) return '--';
    const days = Number(approach.days_until);
    if (days === 0) return 'Today';
    if (days === 1) return 'Tomorrow';
    return `${formatDate(approach.date)} (${days} days)`;
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
}

function showStatus(message) {
    const status = document.getElementById('statusMessage');
    status.innerHTML = escapeHtml(message);
    status.classList.remove('hidden');
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
