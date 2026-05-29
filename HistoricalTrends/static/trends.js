// Global variables
let allTags = [];
let selectedTags = [];

/**
 * Returns a chart label for a tag.
 * Priority: tag_name (if differs from tag_id) → description → tag_id alone.
 */
function tagLabel(tagId) {
    const t = allTags.find(x => (typeof x === 'object' ? x.tag_id : x) === tagId);
    if (t && typeof t === 'object') {
        const name = (t.tag_name && t.tag_name !== tagId) ? t.tag_name : null;
        const desc = (t.description && t.description !== tagId) ? t.description : null;
        const label = name || desc;
        if (label) return `${tagId} – ${label}`;
    }
    return tagId;
}

/**
 * Updates the Query Engine status badge from an /api/data response object.
 * Expected fields: query_mode, bucket_seconds, est_rows_db, sampled, elapsed_ms, count
 */
function _updateQEBadge(result) {
    const badge  = document.getElementById('qeModeBadge');
    const detail = document.getElementById('qeDetail');
    if (!badge || !detail) return;

    const mode    = (result.query_mode || 'unknown').toUpperCase();
    const est     = result.est_rows_db != null ? result.est_rows_db.toLocaleString() : '?';
    const returned = (result.count || 0).toLocaleString();
    const ms      = result.elapsed_ms != null ? result.elapsed_ms : '?';
    const bucket  = result.bucket_seconds;

    const modeColors = { RAW: '#00ff88', 'TIME-BUCKET': '#ffd700', LTTB: '#ff9500', UNKNOWN: '#888' };
    badge.textContent  = mode;
    badge.style.color  = modeColors[mode] || '#888';

    let detailText = `${est} DB rows → ${returned} points · ${ms}ms`;
    if (bucket) detailText += ` · bucket ${bucket}s`;
    detail.textContent = detailText;
}

let currentData = null;
let tagStatistics = {}; // Store statistics from API
let appConfig = null; // Store application configuration from API
// Guard flag to prevent multiple simultaneous loads
let isLoadingTrends = false;
let chartMode = 'lines';
let scaleOverrides = {}; // Store custom scale adjustments for each tag

// PERFORMANCE: Response cache to avoid redundant API calls
let dataCache = {
    key: null,
    data: null,
    timestamp: null,
    ttl: 30000 // 30 second cache
};

// Rendering state management
let renderingState = {
    isRendering: false,
    currentMode: null,
    abortController: null,
    renderedCharts: new Set()
};

/**
 * CRITICAL: Normalize timestamp keys across entire dataset
 * Fixes Bug #1 - Inconsistent timestamp property names
 */
function normalizeTimestamps(data) {
    if (!data || data.length === 0) return data;
    
    return data.map(row => {
        const normalized = { ...row };
        
        // Find timestamp field (case-insensitive)
        const tsKey = Object.keys(row).find(k => k.toLowerCase() === 'timestamp');
        
        if (tsKey && tsKey !== 'Timestamp') {
            normalized.Timestamp = row[tsKey];
            delete normalized[tsKey];
        }
        
        return normalized;
    });
}

// Color palette for SCADA style
const tagColors = [
    '#00d4ff', '#00ff88', '#ffd700', '#ff6b6b', '#a78bfa',
    '#fb923c', '#38bdf8', '#4ade80', '#f472b6', '#facc15'
];

// Helper function to safely convert timestamps and filter invalid data
function getValidDataPoints(data, tag = null) {
    return data.filter(d => {
        // Check if timestamp is valid
        if (!d.Timestamp) return false;
        const date = new Date(d.Timestamp);
        if (isNaN(date.getTime())) return false;
        
        // If tag specified, check if value is valid
        if (tag !== null) {
            const value = d[tag];
            // CRITICAL FIX: Add isNaN check (Bug #3)
            if (value === null || value === undefined || isNaN(value)) return false;
        }
        
        return true;
    });
}

// Decimate data for scatter mode (keep max 10,000 points for performance)
function decimateData(data, maxPoints = 10000) {
    if (!data || data.length <= maxPoints) return data;
    
    const step = Math.ceil(data.length / maxPoints);
    const decimated = [];
    
    for (let i = 0; i < data.length; i += step) {
        decimated.push(data[i]);
    }
    
    // Always include last point
    if (decimated[decimated.length - 1] !== data[data.length - 1]) {
        decimated.push(data[data.length - 1]);
    }
    
    console.log(`📊 Decimated ${data.length} points to ${decimated.length} for performance`);
    return decimated;
}

/**
 * Fetch with timeout to prevent hanging
 * Fixes: No watchdog timer issue
 */
async function fetchWithTimeout(url, options = {}, timeoutMs = 30000) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
    
    try {
        const response = await fetch(url, {
            ...options,
            signal: controller.signal
        });
        clearTimeout(timeoutId);
        return response;
    } catch (error) {
        clearTimeout(timeoutId);
        if (error.name === 'AbortError') {
            throw new Error(`Request timeout after ${timeoutMs}ms`);
        }
        throw error;
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    loadAppConfig().then(() => {
        initializeDatePickers();
        loadTags();
        setupEventListeners();
    });
});

/**
 * Load application configuration from API
 */
async function loadAppConfig() {
    try {
        const response = await fetch('/api/config');
        if (!response.ok) {
            throw new Error('Failed to load configuration');
        }
        appConfig = await response.json();
        console.log('✅ Configuration loaded:', appConfig);
        return appConfig;
    } catch (error) {
        console.error('❌ Failed to load config, using defaults:', error);
        appConfig = getDefaultConfig();
        return appConfig;
    }
}

/**
 * Fallback default configuration
 */
function getDefaultConfig() {
    return {
        Performance: {
            MaxBoxPlotSamples: 5000,
            MaxDistributionSamples: 10000,
            MaxChartDataPoints: 50000
        },
        DataQualitySettings: {
            MissingValueHandling: "ignore",
            InterpolationMethod: "linear",
            DowntimeThreshold: {
                ConsecutiveMissing: 5,
                DurationMinutes: 5
            },
            GarbageDetection: {
                Enabled: true,
                UnrealisticRangeMultiplier: 5,
                ConstantValueDuration: 10
            }
        },
        BIAnalyticsSettings: {
            BaselineWindow: 30,
            TopPercentile: 10,
            OutlierThreshold: 3,
            OutlierMethod: "sigma"
        },
        OperatingBands: {
            DefaultBandWidth: 2,
            ShowBands: false,
            BandMethod: "stddev"
        }
    };
}

// Initialize date pickers with 1-year max range validation
function initializeDatePickers() {
    const now = new Date();
    const yesterday = new Date(now.getTime() - 24 * 60 * 60 * 1000);
    
    flatpickr('#startDate', {
        enableTime: true,
        dateFormat: 'Y-m-d H:i',
        defaultDate: yesterday,
        time_24hr: true,
        onChange: function(selectedDates) {
            validateDateRange();
        }
    });
    
    flatpickr('#endDate', {
        enableTime: true,
        dateFormat: 'Y-m-d H:i',
        defaultDate: now,
        time_24hr: true,
        onChange: function(selectedDates) {
            validateDateRange();
        }
    });
}

// Validate that date range doesn't exceed 1 year
function validateDateRange() {
    const startDate = document.getElementById('startDate')._flatpickr.selectedDates[0];
    const endDate = document.getElementById('endDate')._flatpickr.selectedDates[0];
    
    if (!startDate || !endDate) return true;
    
    const ONE_YEAR_MS = 365 * 24 * 60 * 60 * 1000;
    const rangeDuration = endDate - startDate;
    
    if (rangeDuration > ONE_YEAR_MS) {
        showError('⚠ Maximum date range is 1 year (365 days). Please select a smaller range.');
        document.getElementById('loadDataBtn').disabled = true;
        return false;
    } else if (rangeDuration < 0) {
        showError('⚠ Start date must be before end date.');
        document.getElementById('loadDataBtn').disabled = true;
        return false;
    } else {
        hideError();
        document.getElementById('loadDataBtn').disabled = false;
        return true;
    }
}

// Setup event listeners
function setupEventListeners() {
    document.getElementById('loadDataBtn').addEventListener('click', loadTrendData);

    // Force RAW toggle
    const forceRawBtn = document.getElementById('forceRawBtn');
    if (forceRawBtn) {
        forceRawBtn.addEventListener('click', () => {
            window._forceRaw = !window._forceRaw;
            forceRawBtn.style.background = window._forceRaw
                ? 'linear-gradient(135deg, #ff9500 0%, #cc7700 100%)'
                : 'rgba(255,165,0,0.15)';
            forceRawBtn.style.color = window._forceRaw ? '#fff' : '#ff9500';
            forceRawBtn.textContent = window._forceRaw ? '🔢 RAW ON' : '🔢 Force RAW';
            forceRawBtn.title = window._forceRaw
                ? 'RAW mode active — click to disable. All rows will be fetched without sampling.'
                : 'Bypass smart sampling — fetch every raw value from the database.';
            // Reload data with new mode if data is already displayed
            if (window.currentChartData && window.currentChartData.length > 0) {
                loadTrendData();
            }
        });
    }
    window._forceRaw = false;
    document.getElementById('exportCsvBtn').addEventListener('click', exportCsv);
    document.getElementById('exportExcelBtn').addEventListener('click', exportExcel);
    document.getElementById('quickRange').addEventListener('change', handleQuickRange);
    document.getElementById('normalizeCheckbox').addEventListener('change', handleNormalizationToggle);
    
    // Select All / Deselect All buttons
    document.getElementById('selectAllBtn').addEventListener('click', selectAllTags);
    document.getElementById('deselectAllBtn').addEventListener('click', deselectAllTags);
    document.getElementById('modeLines').addEventListener('click', async () => await setChartMode('lines'));
    document.getElementById('modeScatter').addEventListener('click', async () => await setChartMode('scatter'));
    document.getElementById('modeBoxPlot').addEventListener('click', async () => await setChartMode('boxplot'));
    document.getElementById('modeDistribution').addEventListener('click', async () => await setChartMode('distribution'));
    document.getElementById('modeBIAnalytics').addEventListener('click', async () => await setChartMode('bianalytics'));
    
    // Industrial features event handlers (optional - may be hidden)
    const toggleBands = document.getElementById('toggleBands');
    const configureBands = document.getElementById('configureBands');
    const configureDataQuality = document.getElementById('configureDataQuality');
    const predictMissingData = document.getElementById('predictMissingData');
    const toggleViewMode = document.getElementById('toggleViewMode');
    const addEventMarker = document.getElementById('addEventMarker');
    const toggleShiftSummary = document.getElementById('toggleShiftSummary');
    const toggleHealthScore = document.getElementById('toggleHealthScore');
    const toggleDataQuality = document.getElementById('toggleDataQuality');
    
    if (toggleBands) toggleBands.addEventListener('click', toggleOperatingBands);
    if (configureBands) configureBands.addEventListener('click', configureBandsForSelectedTags);
    if (configureDataQuality) configureDataQuality.addEventListener('click', () => window.showDataQualityConfigModal());
    if (predictMissingData) predictMissingData.addEventListener('click', openMLPredictionModal);
    if (toggleViewMode) toggleViewMode.addEventListener('click', toggleViewMode);
    if (addEventMarker) addEventMarker.addEventListener('click', () => window.IndustrialFeatures.showEventMarkerModal());
    if (toggleShiftSummary) toggleShiftSummary.addEventListener('click', toggleShiftSummary);
    if (toggleHealthScore) toggleHealthScore.addEventListener('click', toggleHealthScore);
    if (toggleDataQuality) toggleDataQuality.addEventListener('click', toggleDataQuality);
    
    // Best/Worst analysis handlers
    document.getElementById('analyzeBest').addEventListener('click', () => analyzePeakMoment('best'));
    document.getElementById('analyzeWorst').addEventListener('click', () => analyzePeakMoment('worst'));
    document.getElementById('analyzeBoth').addEventListener('click', () => analyzeBothCases());
    
    // Auto-update chart when target tag changes in Best/Worst mode
    document.getElementById('peakTargetTag').addEventListener('change', (e) => {
        if (chartMode === 'bestworst' && e.target.value) {
            // Clear previous results to show new selection is active
            document.getElementById('peakResults').innerHTML = '';
            document.getElementById('peakResults').style.display = 'none';
            document.getElementById('correlationChart').innerHTML = '';
            
            // Re-render the combined chart with new selection
            renderCombinedChart();
        }
    });
}

// Handle quick range selection
function handleQuickRange(e) {
    const range = e.target.value;
    if (!range) return;
    
    const now = new Date();
    let start = new Date();
    
    switch(range) {
        case '1h':
            start = new Date(now.getTime() - 60 * 60 * 1000);
            break;
        case '6h':
            start = new Date(now.getTime() - 6 * 60 * 60 * 1000);
            break;
        case '24h':
            start = new Date(now.getTime() - 24 * 60 * 60 * 1000);
            break;
        case '7d':
            start = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
            break;
        case '30d':
            start = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
            break;
        case '90d':
            start = new Date(now.getTime() - 90 * 24 * 60 * 60 * 1000);
            break;
        case '180d':
            start = new Date(now.getTime() - 180 * 24 * 60 * 60 * 1000);
            break;
        case '1y':
            start = new Date(now.getTime() - 365 * 24 * 60 * 60 * 1000);
            break;
    }
    
    document.getElementById('startDate')._flatpickr.setDate(start);
    document.getElementById('endDate')._flatpickr.setDate(now);
}

// Load available tags
async function loadTags() {
    console.log('Loading tags from /api/tags...');
    try {
        const response = await fetch('/api/tags');
        console.log('Response received:', response.status);
        const result = await response.json();
        console.log('Tags loaded:', result);
        
        if (result.success) {
            // allTags is now array of objects: {tag_id, tag_name, server_progid, description, eng_unit}
            allTags = result.tags;
            renderTagSelector();
        } else {
            showError('Failed to load tags: ' + result.error);
        }
    } catch (error) {
        console.error('Error loading tags:', error);
        showError('Error loading tags: ' + error.message);
    }
}

// Render tag selector
function renderTagSelector() {
    const container = document.getElementById('tagSelector');
    container.innerHTML = '';
    
    if (allTags.length === 0) {
        container.innerHTML = '<div style="padding: 20px; text-align: center; color: #888;">No tags available</div>';
        return;
    }
    
    // Add search box
    const searchBox = document.createElement('input');
    searchBox.type = 'text';
    searchBox.placeholder = '🔍 Search tags...';
    searchBox.style.cssText = 'width: 100%; padding: 10px; margin-bottom: 10px; background: rgba(15, 52, 96, 0.6); border: 1px solid #00d4ff; border-radius: 6px; color: #e0e0e0; font-size: 14px;';
    searchBox.addEventListener('input', (e) => filterTags(e.target.value));
    container.appendChild(searchBox);
    
    // Create tag list container with optimized scrolling
    const tagList = document.createElement('div');
    tagList.id = 'tagList';
    tagList.style.cssText = 'max-height: 320px; overflow-y: auto; overflow-x: hidden; scroll-behavior: smooth; transform: translateZ(0); will-change: scroll-position;';
    container.appendChild(tagList);
    
    // Render all tags initially
    filterTags('');
}

// Filter and render tags based on search — grouped by server_progid
function filterTags(searchTerm) {
    const tagList = document.getElementById('tagList');
    if (!tagList) return;
    
    const lowerSearch = searchTerm.toLowerCase();
    
    const filteredTags = searchTerm === ''
        ? allTags
        : allTags.filter(t =>
            t.tag_id.toLowerCase().includes(lowerSearch) ||
            (t.tag_name && t.tag_name.toLowerCase().includes(lowerSearch)) ||
            (t.description && t.description.toLowerCase().includes(lowerSearch))
          );
    
    if (filteredTags.length === 0) {
        tagList.innerHTML = '<div style="padding: 20px; text-align: center; color: #888;">No tags match your search</div>';
        return;
    }
    
    // PARTITION: UNSELECTED on LEFT, SELECTED on RIGHT
    const selectedFiltered   = filteredTags.filter(t => selectedTags.includes(t.tag_id));
    const unselectedFiltered = filteredTags.filter(t => !selectedTags.includes(t.tag_id));
    
    // Group each side by server_progid
    function groupBySource(tagArr) {
        const groups = {};
        tagArr.forEach(t => {
            const src = t.server_progid || 'Unknown Source';
            if (!groups[src]) groups[src] = [];
            groups[src].push(t);
        });
        return groups;
    }
    
    // Build a column DOM node with source group headers
    function buildColumn(tagArr, isSelected) {
        const col = document.createElement('div');
        const groups = groupBySource(tagArr);

        if (Object.keys(groups).length === 0) {
            col.innerHTML = `<div style="padding:16px;text-align:center;color:#555;font-size:12px;">${isSelected ? 'No tags selected' : 'All tags selected'}</div>`;
            return col;
        }

        // Header row for the whole column
        const colHeader = document.createElement('div');
        colHeader.style.cssText = `padding:5px 10px;font-weight:bold;font-size:11px;border-radius:4px;margin-bottom:6px;${
            isSelected
            ? 'background:rgba(0,255,136,0.15);color:#00ff88;'
            : 'background:rgba(100,100,100,0.15);color:#888;'
        }`;
        colHeader.textContent = isSelected ? `✓ SELECTED (${tagArr.length})` : `○ AVAILABLE (${tagArr.length})`;
        col.appendChild(colHeader);

        Object.entries(groups).forEach(([source, tags]) => {
            // Unique key for collapse state
            const colKey = `src_${isSelected ? 'sel' : 'avail'}_${source.replace(/[^a-z0-9]/gi,'_')}`;
            const isCollapsed = window._srcCollapsed && window._srcCollapsed[colKey];

            // Source group header — clickable to collapse/expand
            const srcHeader = document.createElement('div');
            srcHeader.style.cssText = 'display:flex;align-items:center;gap:6px;padding:5px 8px;margin:6px 0 3px;border-left:3px solid #00d4ff;background:rgba(0,212,255,0.07);border-radius:0 4px 4px 0;cursor:pointer;user-select:none;';
            const arrow = isCollapsed ? '▶' : '▼';
            srcHeader.innerHTML = `<span style="color:#00d4ff;font-size:10px;font-weight:700;letter-spacing:0.8px;text-transform:uppercase;">📡 ${source}</span><span style="color:#5a8aaa;font-size:10px;">(${tags.length})</span><span style="color:#00d4ff;font-size:9px;margin-left:auto;">${arrow}</span>`;

            // Tags wrapper — toggles visibility
            const tagsWrapper = document.createElement('div');
            tagsWrapper.style.display = isCollapsed ? 'none' : 'block';

            srcHeader.addEventListener('click', () => {
                if (!window._srcCollapsed) window._srcCollapsed = {};
                window._srcCollapsed[colKey] = !window._srcCollapsed[colKey];
                // Re-render with current search to reflect new state
                const searchBox = document.querySelector('#tagSelector input[type="text"]');
                filterTags(searchBox ? searchBox.value : '');
            });

            col.appendChild(srcHeader);
            tags.forEach(t => tagsWrapper.appendChild(createTagItem(t, isSelected)));
            col.appendChild(tagsWrapper);
        });

        return col;
    }
    
    // Two-column layout
    const outerGrid = document.createElement('div');
    outerGrid.style.cssText = 'display:grid;grid-template-columns:1fr 1fr;gap:10px;height:100%;';
    
    const leftCol = buildColumn(unselectedFiltered, false);
    leftCol.style.cssText = 'border-right:2px solid rgba(100,100,100,0.3);padding-right:10px;';
    
    const rightCol = buildColumn(selectedFiltered, true);
    rightCol.style.cssText = 'padding-left:10px;';
    
    outerGrid.appendChild(leftCol);
    outerGrid.appendChild(rightCol);
    
    tagList.innerHTML = '';
    tagList.appendChild(outerGrid);
}

// Helper function to create tag item (accepts tag object {tag_id, tag_name, ...})
function createTagItem(tagObj, isChecked) {
    // tagObj may be a plain string (legacy) or an object
    const tagId   = (typeof tagObj === 'object') ? tagObj.tag_id   : tagObj;
    // Prefer tag_name if different from tag_id, else fall back to description
    const rawName = (typeof tagObj === 'object') ? tagObj.tag_name   : null;
    const rawDesc = (typeof tagObj === 'object') ? tagObj.description : null;
    const tagName = (rawName && rawName !== tagId) ? rawName
                  : (rawDesc && rawDesc !== tagId) ? rawDesc
                  : null;
    const engUnit = (typeof tagObj === 'object' && tagObj.eng_unit) ? tagObj.eng_unit : null;

    const tagIndex = allTags.findIndex(t =>
        (typeof t === 'object' ? t.tag_id : t) === tagId
    );
    const color = tagColors[tagIndex % tagColors.length];
    
    const item = document.createElement('div');
    item.className = 'tag-item';
    item.style.cssText = (isChecked ? 'background:rgba(0,255,136,0.08);' : '') + 'align-items:center;';
    
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.id = `tag_${tagIndex}`;
    checkbox.value = tagId;
    checkbox.checked = isChecked;
    checkbox.addEventListener('change', updateSelectedTags);

    // Left: tag ID (bold)
    const nameSpan = document.createElement('label');
    nameSpan.htmlFor = `tag_${tagIndex}`;
    nameSpan.style.cssText = 'flex:1;min-width:0;font-size:13px;font-weight:600;color:#e0e0e0;cursor:pointer;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;';
    nameSpan.textContent = tagId;

    // Right: description (muted, smaller)
    const descSpan = document.createElement('span');
    if (tagName) {
        descSpan.style.cssText = 'font-size:11px;color:#5a8aaa;white-space:nowrap;margin-left:6px;flex-shrink:0;max-width:130px;overflow:hidden;text-overflow:ellipsis;';
        descSpan.textContent = tagName + (engUnit ? ` (${engUnit})` : '');
        descSpan.title = tagName + (engUnit ? ` (${engUnit})` : '');
    }
    
    const colorBar = document.createElement('div');
    colorBar.className = 'tag-color';
    colorBar.style.background = color;
    
    item.appendChild(checkbox);
    item.appendChild(nameSpan);
    item.appendChild(descSpan);
    item.appendChild(colorBar);
    
    return item;
}

// Update selected tags
function updateSelectedTags() {
    // Get currently visible checkboxes
    const visibleChecked = Array.from(document.querySelectorAll('#tagSelector input:checked'))
        .map(cb => cb.value);
    
    // Get currently visible unchecked (to remove from selection)
    const visibleUnchecked = Array.from(document.querySelectorAll('#tagSelector input:not(:checked)'))
        .map(cb => cb.value);
    
    // Preserve selections that are not currently visible (filtered out)
    const hiddenSelections = selectedTags.filter(tag => !visibleUnchecked.includes(tag));
    
    // Combine visible checked tags with hidden selections
    selectedTags = [...new Set([...visibleChecked, ...hiddenSelections])];
    
    document.getElementById('statTags').textContent = selectedTags.length;
    
    // Re-render to update partitioning
    const searchBox = document.querySelector('#tagSelector input[type="text"]');
    if (searchBox) {
        filterTags(searchBox.value);
    }
}

// Select all visible tags
function selectAllTags() {
    const visibleCheckboxes = document.querySelectorAll('#tagList input[type="checkbox"]');
    visibleCheckboxes.forEach(cb => cb.checked = true);
    updateSelectedTags();
}

// Deselect all tags
function deselectAllTags() {
    selectedTags = [];
    const allCheckboxes = document.querySelectorAll('#tagList input[type="checkbox"]');
    allCheckboxes.forEach(cb => cb.checked = false);
    document.getElementById('statTags').textContent = 0;
    const searchBox = document.querySelector('#tagSelector input[type="text"]');
    if (searchBox) {
        filterTags(searchBox.value);
    }
}

/**
 * Fetch with timeout to prevent hanging
 * CRITICAL FIX: Add watchdog timer for API calls
 */
async function fetchWithTimeout(url, options = {}, timeoutMs = 30000) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
    
    try {
        const response = await fetch(url, {
            ...options,
            signal: options.signal || controller.signal
        });
        clearTimeout(timeoutId);
        return response;
    } catch (error) {
        clearTimeout(timeoutId);
        if (error.name === 'AbortError') {
            throw new Error(`Request timeout after ${timeoutMs/1000}s`);
        }
        throw error;
    }
}

// Load trend data
async function loadTrendData() {
    // Prevent duplicate concurrent loads
    if (isLoadingTrends) {
        console.log('⏳ Duplicate load request ignored (already loading)');
        return;
    }
    if (selectedTags.length === 0) {
        showError('Please select at least one tag');
        return;
    }
    
    const startDate = document.getElementById('startDate').value;
    const endDate = document.getElementById('endDate').value;
    
    if (!startDate || !endDate) {
        showError('Please select start and end dates');
        return;
    }
    
    // Validate date range before loading
    if (!validateDateRange()) {
        return;
    }

    // ── Force RAW: hard limits (20 days, 5 tags) ────────────────────────
    if (window._forceRaw) {
        const RAW_MAX_DAYS = 20;
        const RAW_MAX_TAGS = 5;

        const rawStart = new Date(startDate);
        const rawEnd   = new Date(endDate);
        const diffDays = (rawEnd - rawStart) / (1000 * 60 * 60 * 24);

        if (diffDays > RAW_MAX_DAYS) {
            showError(
                `⚠️ Force RAW mode is ON — date range is too large (${Math.round(diffDays)} days). ` +
                `Maximum allowed in RAW mode is ${RAW_MAX_DAYS} days. ` +
                `Please shorten your date range or turn off Force RAW to use smart sampling.`
            );
            return;
        }
        if (selectedTags.length > RAW_MAX_TAGS) {
            showError(
                `⚠️ Force RAW mode is ON — too many tags selected (${selectedTags.length}). ` +
                `Maximum allowed in RAW mode is ${RAW_MAX_TAGS} tags. ` +
                `Please deselect some tags or turn off Force RAW to use smart sampling.`
            );
            return;
        }
    }
    // ─────────────────────────────────────────────────────────────────────

    // Mark loading started
    isLoadingTrends = true;
    // CRITICAL: Abort any previous loading to prevent race conditions
    if (renderingState.abortController) {
        renderingState.abortController.abort();
    }
    renderingState.abortController = new AbortController();
    
    showLoading(true, 'Fetching data...', `${selectedTags.length} tags selected`);
    hideError();
    
    try {
        // Check if user wants interpolated data (from external cache)
        const qualityConfig = new window.DataQualityConfig();
        const useInterpolated = qualityConfig.getViewMode() === 'interpolated';
        
        // Fetch data (raw or with interpolation applied from cache)
        const endpoint = useInterpolated ? '/api/interpolation/data' : '/api/data';
        
        const params = new URLSearchParams({
            start_date: new Date(startDate).toISOString(),
            end_date: new Date(endDate).toISOString(),
            tags: JSON.stringify(selectedTags)
        });
        
        if (useInterpolated) {
            params.append('use_interpolated', 'true');
        }
        if (window._forceRaw) {
            params.append('force_raw', '1');
        }
        
        // PERFORMANCE: Check cache first
        const cacheKey = `${endpoint}?${params}`;
        const now = Date.now();
        if (dataCache.key === cacheKey && dataCache.data && (now - dataCache.timestamp) < dataCache.ttl) {
            console.log('📦 Using cached data (age: ' + Math.round((now - dataCache.timestamp)/1000) + 's)');
            const result = dataCache.data;
            // Skip to processing (jump past API call)
            processLoadedData(result, useInterpolated);
            return;
        }
        
        console.log('🌐 Fetching fresh data from API...');
        const fetchStart = performance.now();
        
        // CRITICAL FIX: Add timeout to prevent UI freeze on API hang
        const response = await fetchWithTimeout(`${endpoint}?${params}`, {
            signal: renderingState.abortController.signal
        }, 120000); // 120s timeout for large datasets
        
        const result = await response.json();
        
        const fetchDuration = Math.round(performance.now() - fetchStart);
        console.log(`⏱️ API fetch completed in ${fetchDuration}ms`);
        
        // Cache the result
        dataCache = {
            key: cacheKey,
            data: result,
            timestamp: now,
            ttl: 30000
        };
        
        processLoadedData(result, useInterpolated);
        
    } catch (error) {
        console.error('Error loading data:', error);
        showError('Error loading data: ' + error.message);
    } finally {
        showLoading(false);
        isLoadingTrends = false;
    }
}

// PERFORMANCE: Separate processing function for cache reuse
function processLoadedData(result, useInterpolated) {
    try {
        if (result.success) {
            const qualityConfig = new window.DataQualityConfig();
            
            // Analyze data quality (read-only, does NOT modify data)
            const qualityProcessor = new window.DataQualityProcessor(qualityConfig);
            const qualityResult = qualityProcessor.processData(result.data, selectedTags);
            
            // Show quality summary
            if (qualityResult.downtimes.length > 0) {
                console.log(`⚠️ Detected ${qualityResult.downtimes.length} downtime events`);
            }
            console.log(`📊 Data Quality: ${qualityResult.summary.recommendation} (${qualityResult.summary.averageQuality}%)`);
            console.log(`🔍 View Mode: ${useInterpolated ? 'INTERPOLATED' : 'RAW DATA'}`);
            
            // Apply sampling rate and method if selected
            const samplingRate = 0;      // handled by QueryEngine on server
            const samplingMethod = 'avg'; // handled by QueryEngine on server
            let processedData = result.data; // no client-side resample needed

            // Update Query Engine status badge
            _updateQEBadge(result);
            
            // CRITICAL FIX: Normalize timestamps across dataset (Bug #1)
            currentData = normalizeTimestamps(processedData);
            
            // Store statistics from API
            tagStatistics = result.statistics || {};
            
            // Update statistics with resampled data
            const updatedResult = {
                ...result,
                data: currentData,
                count: currentData.length
            };
            
            updateStatistics(updatedResult);
            renderCharts();
            enableExportButtons();
        } else {
            showError('Failed to load data: ' + result.error);
        }
    } catch (error) {
        showError('Error loading data: ' + error.message);
    } finally {
        showLoading(false);
        isLoadingTrends = false;
    }
}

// Update statistics
function updateStatistics(result) {
    document.getElementById('statRecords').textContent = result.count.toLocaleString();
    
    if (result.data.length > 0 && result.data[0].Timestamp) {
        const dates = result.data.map(d => new Date(d.Timestamp));
        const minDate = new Date(Math.min(...dates));
        const maxDate = new Date(Math.max(...dates));
        
        document.getElementById('statDateRange').textContent = 
            `${minDate.toLocaleDateString()} - ${maxDate.toLocaleDateString()}`;
    }
    
    document.getElementById('statsPanel').style.display = 'grid';
}

// Render charts
function renderCharts() {
    if (!currentData || currentData.length === 0) {
        showError('No data to display');
        return;
    }
    
    // Show combined chart
    document.getElementById('combinedChartContainer').style.display = 'block';
    
    // Create scale adjustment controls
    createScaleControls();
    
    renderCombinedChart();
    
    // Individual charts now handled by setChartMode() instead of renderSeparateCharts()
}

// Handle normalization toggle
function handleNormalizationToggle() {
    if (currentData && currentData.length > 0) {
        renderCharts();
    }
}

// Create scale adjustment controls for each tag
function createScaleControls() {
    const scaleControlsDiv = document.getElementById('scaleControls');
    const scalePanel = document.getElementById('scaleAdjustPanel');
    
    // Only show for lines/scatter modes
    if (chartMode === 'lines' || chartMode === 'scatter') {
        scalePanel.style.display = 'block';
    } else {
        scalePanel.style.display = 'none';
        return;
    }
    
    scaleControlsDiv.innerHTML = '';
    
    selectedTags.forEach((tag, index) => {
        const color = tagColors[index % tagColors.length];
        const values = currentData.map(d => d[tag]).filter(v => v !== null && v !== undefined && !isNaN(v));
        
        if (values.length === 0) return;
        
        const min = Math.min(...values);
        const max = Math.max(...values);
        const currentMin = scaleOverrides[tag]?.min ?? min;
        const currentMax = scaleOverrides[tag]?.max ?? max;
        
        const controlHtml = `
            <div class="scale-control" style="border-left: 3px solid ${color};">
                <label>${tag}</label>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
                    <div>
                        <div style="font-size: 11px; color: #888; margin-bottom: 3px;">Min Value</div>
                        <input type="number" id="scaleMin_${index}" value="${currentMin.toFixed(2)}" step="any" 
                               data-tag="${tag}" data-type="min" class="scale-input">
                    </div>
                    <div>
                        <div style="font-size: 11px; color: #888; margin-bottom: 3px;">Max Value</div>
                        <input type="number" id="scaleMax_${index}" value="${currentMax.toFixed(2)}" step="any"
                               data-tag="${tag}" data-type="max" class="scale-input">
                    </div>
                </div>
                <div class="scale-info">
                    <span>Data Range: ${min.toFixed(2)} to ${max.toFixed(2)}</span>
                </div>
            </div>
        `;
        
        scaleControlsDiv.insertAdjacentHTML('beforeend', controlHtml);
    });
    
    // Add event listeners to scale inputs
    document.querySelectorAll('.scale-input').forEach(input => {
        input.addEventListener('change', handleScaleChange);
    });
    
    // Reset button
    document.getElementById('resetScalesBtn').addEventListener('click', resetScales);
}

// Handle scale changes
function handleScaleChange(e) {
    const tag = e.target.dataset.tag;
    const type = e.target.dataset.type;
    const value = parseFloat(e.target.value);
    
    if (!scaleOverrides[tag]) {
        scaleOverrides[tag] = {};
    }
    
    scaleOverrides[tag][type] = value;
    
    // Re-render the chart with new scales
    renderCombinedChart();
}

// Reset all scale overrides
function resetScales() {
    scaleOverrides = {};
    createScaleControls();
    renderCombinedChart();
}

// Statistical helper functions
function calculateStats(values) {
    const filtered = values.filter(v => v !== null && v !== undefined && !isNaN(v));
    if (filtered.length === 0) return null;
    
    const sorted = filtered.sort((a, b) => a - b);
    const mean = filtered.reduce((sum, v) => sum + v, 0) / filtered.length;
    const variance = filtered.reduce((sum, v) => sum + Math.pow(v - mean, 2), 0) / filtered.length;
    const stdDev = Math.sqrt(variance);
    
    const q1Index = Math.floor(sorted.length * 0.25);
    const q3Index = Math.floor(sorted.length * 0.75);
    const q1 = sorted[q1Index];
    const q3 = sorted[q3Index];
    const iqr = q3 - q1;
    
    return {
        mean,
        stdDev,
        min: sorted[0],
        max: sorted[sorted.length - 1],
        median: sorted[Math.floor(sorted.length / 2)],
        q1,
        q3,
        iqr,
        lowerBound: mean - 3 * stdDev,
        upperBound: mean + 3 * stdDev,
        count: filtered.length
    };
}

function detectAnomalies(tag) {
    const values = currentData.map(d => d[tag]).filter(v => v !== null && v !== undefined && !isNaN(v));
    const stats = calculateStats(values);
    if (!stats) return { anomalies: [], stats: null };
    
    const anomalies = currentData.map((d, idx) => {
        const value = d[tag];
        if (value === null || value === undefined || isNaN(value)) return null;
        
        const isAnomaly = value < stats.lowerBound || value > stats.upperBound;
        return isAnomaly ? { index: idx, timestamp: d.Timestamp, value, tag } : null;
    }).filter(a => a !== null);
    
    return { anomalies, stats };
}

// Render combined chart
async function renderCombinedChart() {
    const anomalyInfo = document.getElementById('anomalyInfo');
    if (anomalyInfo) anomalyInfo.innerHTML = '';
    
    // OPTIMIZED: Always use ChartRenderer module for consistent, optimized rendering
    const isNormalized = document.getElementById('normalizeCheckbox')?.checked || false;
    
    // Validate data has valid timestamps before rendering
    if (!currentData || currentData.length === 0) {
        console.warn('No data to render');
        return;
    }
    
    // Filter out rows with invalid timestamps
    const validData = currentData.filter(d => {
        if (!d.Timestamp) return false;
        const date = new Date(d.Timestamp);
        return !isNaN(date.getTime());
    });
    
    if (validData.length === 0) {
        console.error('No valid timestamps in data');
        document.getElementById('trendChart').innerHTML = '<div style="color: #ff6b6b; text-align: center; padding: 40px;">❌ No valid timestamp data found</div>';
        return;
    }
    
    // Single render call - no individual charts
    ChartRenderer.renderMultiScaleChart(validData, selectedTags, isNormalized, 'trendChart', chartMode);
    
    console.log(`✓ Rendered ${chartMode} chart with ${selectedTags.length} tags (${validData.length}/${currentData.length} valid points)`);
}

// Fullscreen functionality for charts
function toggleFullscreen(chartId) {
    const chartDiv = document.getElementById(chartId);
    if (!chartDiv) return;
    
    if (!document.fullscreenElement) {
        chartDiv.requestFullscreen().then(() => {
            // Resize chart when entering fullscreen
            setTimeout(() => {
                Plotly.Plots.resize(chartId);
            }, 100);
        }).catch(err => {
            console.error('Error entering fullscreen:', err);
        });
    } else {
        document.exitFullscreen();
    }
}

// Listen for fullscreen changes to resize charts
document.addEventListener('fullscreenchange', () => {
    if (!document.fullscreenElement) {
        // Exiting fullscreen - resize all charts
        setTimeout(() => {
            if (document.getElementById('trendChart')) {
                Plotly.Plots.resize('trendChart');
            }
            selectedTags.forEach((tag, index) => {
                const chartId = `individualChart_${index}`;
                if (document.getElementById(chartId)) {
                    Plotly.Plots.resize(chartId);
                }
            });
        }, 100);
    }
});

// Render individual charts for each tag below the combined chart
function renderIndividualCharts() {
    if (!currentData || selectedTags.length === 0) return;
    
    const section = document.getElementById('individualChartsSection');
    const container = document.getElementById('individualCharts');
    
    section.style.display = 'block';
    
    // Only create containers if they don't exist
    if (container.children.length !== selectedTags.length) {
        container.innerHTML = '';
        selectedTags.forEach((tag, index) => {
            const color = tagColors[index % tagColors.length];
            const chartDiv = document.createElement('div');
            chartDiv.style.cssText = 'background: rgba(15, 52, 96, 0.3); padding: 20px; border-radius: 10px; border: 2px solid rgba(0, 212, 255, 0.2); position: relative;';
            chartDiv.innerHTML = `
                <div style="margin-bottom: 15px; display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <h3 style="color: ${color}; margin: 0 0 10px 0; font-size: 18px;">${tag}</h3>
                        <div id="stats_${index}" style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; font-size: 12px; color: #888;">
                            <div>Min: <strong style="color: #ff6b6b">--</strong></div>
                            <div>Mean: <strong style="color: #00d4ff">--</strong></div>
                            <div>Max: <strong style="color: #00ff88">--</strong></div>
                            <div>Std: <strong style="color: #ffd700">--</strong></div>
                        </div>
                    </div>
                    <button onclick="toggleFullscreen('individualChart_${index}')" style="background: linear-gradient(135deg, #667eea, #764ba2); color: white; border: none; padding: 8px 15px; border-radius: 6px; cursor: pointer; font-size: 12px; display: flex; align-items: center; gap: 5px;" title="Toggle Fullscreen">
                        <span style="font-size: 16px;">⛶</span> Fullscreen
                    </button>
                </div>
                <div id="individualChart_${index}" style="width: 100%; height: 300px;"></div>
            `;
            container.appendChild(chartDiv);
        });
    }
    
    // Update each chart with current mode
    selectedTags.forEach((tag, index) => {
        const color = tagColors[index % tagColors.length];
        let validData = getValidDataPoints(currentData, tag);
        
        if (validData.length === 0) {
            const statsDiv = document.getElementById(`stats_${index}`);
            if (statsDiv) {
                statsDiv.innerHTML = `
                    <div>Min: <strong style="color: #ff6b6b">--</strong></div>
                    <div>Mean: <strong style="color: #00d4ff">--</strong></div>
                    <div>Max: <strong style="color: #00ff88">--</strong></div>
                    <div>Std: <strong style="color: #ffd700">--</strong></div>
                `;
            }

            const emptyDiv = document.getElementById(`individualChart_${index}`);
            if (emptyDiv) {
                emptyDiv.innerHTML = '<div style="color:#888;text-align:center;padding:30px;">No data available for this tag in the selected range</div>';
            }
            return;
        }
        
        // Decimate for scatter mode if too many points
        if (chartMode === 'scatter' && validData.length > 10000) {
            validData = decimateData(validData, 10000);
        }
        
        // Get statistics from API instead of calculating in JS
        let mean, min, max, stdDev;
        if (tagStatistics[tag]) {
            mean = tagStatistics[tag].mean || 0;
            min = tagStatistics[tag].min || 0;
            max = tagStatistics[tag].max || 0;
            stdDev = tagStatistics[tag].std || 0;
        } else {
            // Fallback: calculate if API didn't provide stats
            const values = validData.map(d => d[tag]).filter(v => v !== null && v !== undefined && !isNaN(v));
            if (values.length === 0) return;
            mean = values.reduce((a, b) => a + b, 0) / values.length;
            min = Math.min(...values);
            max = Math.max(...values);
            stdDev = Math.sqrt(values.reduce((sum, val) => sum + Math.pow(val - mean, 2), 0) / values.length);
        }
        
        // Update statistics display
        const statsDiv = document.getElementById(`stats_${index}`);
        if (statsDiv) {
            statsDiv.innerHTML = `
                <div>Min: <strong style="color: #ff6b6b">${min.toFixed(2)}</strong></div>
                <div>Mean: <strong style="color: #00d4ff">${mean.toFixed(2)}</strong></div>
                <div>Max: <strong style="color: #00ff88">${max.toFixed(2)}</strong></div>
                <div>Std: <strong style="color: #ffd700">${stdDev.toFixed(2)}</strong></div>
            `;
        }
        
        // Create trace based on chart mode
        let trace;
        let layout;
        
        if (chartMode === 'boxplot') {
            // Box plot for this tag - extract values from data
            const values = validData.map(d => d[tag]).filter(v => v !== null && v !== undefined && !isNaN(v));
            
            trace = {
                y: values,
                type: 'box',
                name: tagLabel(tag),
                marker: { color: color },
                boxmean: 'sd',
                hovertemplate: `<b>${tagLabel(tag)}</b><br>Value: %{y:.4f}<extra></extra>`
            };
            
            layout = {
                paper_bgcolor: 'rgba(0,0,0,0)',
                plot_bgcolor: 'rgba(15, 52, 96, 0.2)',
                font: { color: '#e0e0e0', family: 'Segoe UI' },
                yaxis: {
                    title: 'Value',
                    gridcolor: 'rgba(0, 212, 255, 0.1)',
                    color: color,
                    autorange: true
                },
                margin: { l: 60, r: 20, t: 10, b: 40 },
                height: 300,
                showlegend: false
            };
            
        } else if (chartMode === 'distribution') {
            // Histogram/distribution for this tag - extract values from data
            const values = validData.map(d => d[tag]).filter(v => v !== null && v !== undefined && !isNaN(v));
            
            trace = {
                x: values,
                type: 'histogram',
                name: tagLabel(tag),
                marker: { 
                    color: color,
                    line: { color: '#fff', width: 1 }
                },
                nbinsx: 30,
                hovertemplate: `<b>${tagLabel(tag)}</b><br>Range: %{x}<br>Count: %{y}<extra></extra>`
            };
            
            layout = {
                paper_bgcolor: 'rgba(0,0,0,0)',
                plot_bgcolor: 'rgba(15, 52, 96, 0.2)',
                font: { color: '#e0e0e0', family: 'Segoe UI' },
                xaxis: {
                    title: 'Value',
                    gridcolor: 'rgba(0, 212, 255, 0.1)',
                    color: '#00d4ff'
                },
                yaxis: {
                    title: 'Frequency',
                    gridcolor: 'rgba(0, 212, 255, 0.1)',
                    color: color
                },
                margin: { l: 60, r: 20, t: 10, b: 40 },
                height: 300,
                showlegend: false,
                bargap: 0.05
            };
            
        } else {
            // Lines or Scatter mode
            trace = {
                x: validData.map(d => new Date(d.Timestamp)),
                y: validData.map(d => d[tag]),
                name: tagLabel(tag),
                type: 'scattergl',
                mode: chartMode === 'lines' ? 'lines' : 'markers',
                hovertemplate: `<b>${tagLabel(tag)}</b><br>Value: %{y:.4f}<br>Time: %{x}<extra></extra>`
            };
            
            // Add line/marker properties based on mode
            if (chartMode === 'lines') {
                trace.line = { color: color, width: 2 };
            } else if (chartMode === 'scatter') {
                trace.marker = { color: color, size: 4, opacity: 0.6 };
            }
            
            layout = {
                paper_bgcolor: 'rgba(0,0,0,0)',
                plot_bgcolor: 'rgba(15, 52, 96, 0.2)',
                font: { color: '#e0e0e0', family: 'Segoe UI' },
                xaxis: {
                    gridcolor: 'rgba(0, 212, 255, 0.1)',
                    color: '#00d4ff',
                    type: 'date'
                },
                yaxis: {
                    gridcolor: 'rgba(0, 212, 255, 0.1)',
                    color: color,
                    autorange: true
                },
                margin: { l: 60, r: 20, t: 10, b: 40 },
                height: 300,
                showlegend: false,
                hovermode: 'closest'
            };
        }
        
        const config = {
            responsive: true,
            displayModeBar: true,
            displaylogo: false,
            modeBarButtonsToRemove: ['lasso2d', 'select2d'],
            scrollZoom: true
        };
        
        // React (update) existing chart instead of creating new one
        const chartDiv = document.getElementById(`individualChart_${index}`);
        if (chartDiv && chartDiv.data) {
            Plotly.react(`individualChart_${index}`, [trace], layout, config);
        } else {
            Plotly.newPlot(`individualChart_${index}`, [trace], layout, config);
        }
    });
}

// Set chart mode with modular rendering
async function setChartMode(mode) {
    // Prevent double clicks - if already rendering, ignore
    if (renderingState.isRendering) {
        console.log('⚠️ Rendering in progress, please wait...');
        return;
    }
    
    renderingState.isRendering = true;
    renderingState.currentMode = mode;
    renderingState.abortController = new AbortController();
    chartMode = mode;
    
    // Disable all chart mode buttons to prevent double clicks
    disableChartModeButtons(true);
    
    // Show loading indicator
    const chartContainer = document.getElementById('trendChart');
    chartContainer.innerHTML = '<div style="text-align: center; padding: 60px; color: #00d4ff;"><div style="font-size: 48px; margin-bottom: 15px;">⏳</div><div style="font-size: 18px;">Loading ' + mode + ' view...</div></div>';
    
    // Allow UI to update
    await new Promise(resolve => requestAnimationFrame(resolve));
    
    // Update UI buttons (with null checks for removed buttons)
    const modeButtons = {
        'modeLines': 'lines',
        'modeScatter': 'scatter',
        'modeBoxPlot': 'boxplot',
        'modeDistribution': 'distribution',
        'modeBIAnalytics': 'bianalytics'
    };
    
    Object.keys(modeButtons).forEach(btnId => {
        const btn = document.getElementById(btnId);
        if (btn) {
            btn.classList.toggle('active', mode === modeButtons[btnId]);
        }
    });
    
    // CRITICAL: Clear ALL previous renders to prevent memory leaks and hanging
    clearAllCharts();
    
    // Hide all panels initially with null checks
    const peakPanel = document.getElementById('peakAnalysisPanel');
    const syncPanel = document.getElementById('syncStatsPanel');
    const anomalyPanel = document.getElementById('anomalyInfo');
    const corrChart = document.getElementById('correlationChart');
    const biModule = document.getElementById('biAnalyticsModule');
    const individualSection = document.getElementById('individualChartsSection');
    const trendChart = document.getElementById('trendChart');
    const separateCharts = document.getElementById('separateCharts');
    
    if (peakPanel) peakPanel.style.display = 'none';
    if (syncPanel) syncPanel.innerHTML = '';
    if (anomalyPanel) anomalyPanel.innerHTML = '';
    if (corrChart) corrChart.innerHTML = '';
    if (biModule) biModule.style.display = 'none';
    if (individualSection) individualSection.style.display = 'none';
    if (trendChart) trendChart.style.display = 'block';
    if (separateCharts) separateCharts.innerHTML = '';
    
    if (currentData) {
        try {
            // MODULAR RENDERING: Only render the active view, nothing else
            if (mode === 'bianalytics') {
                chartContainer.innerHTML = '';
                const biModule = document.getElementById('biAnalyticsModule');
                const trendChart = document.getElementById('trendChart');
                if (biModule) biModule.style.display = 'block';
                if (trendChart) trendChart.style.display = 'none';
                await renderModular(() => BIAnalytics.initialize(currentData, selectedTags));
            } else if (mode === 'correlation') {
                chartContainer.innerHTML = '';
                await renderModular(() => renderCorrelationView());
            } else if (mode === 'syncstats') {
                chartContainer.innerHTML = '';
                await renderModular(() => renderSyncStatsView());
            } else if (mode === 'bestworst') {
                chartContainer.innerHTML = '';
                await renderModular(() => renderBestWorstMode());
            } else if (mode === 'loadcorrelation') {
                chartContainer.innerHTML = '';
                await renderModular(() => renderLoadCorrelationMode());
            } else if (mode === 'lines' || mode === 'scatter') {
                // Render combined chart + individual charts below
                chartContainer.innerHTML = '';
                await renderModular(() => renderCombinedChart());
                await renderModular(() => renderIndividualCharts());
            } else if (mode === 'boxplot') {
                chartContainer.innerHTML = '';
                await renderModular(async () => {
                    await new Promise(resolve => setTimeout(resolve, 100));
                    await ChartRenderer.renderBoxPlot(currentData, selectedTags, 'trendChart');
                });
                await renderModular(() => renderIndividualCharts());
            } else if (mode === 'distribution') {
                chartContainer.innerHTML = '';
                await renderModular(async () => {
                    await new Promise(resolve => setTimeout(resolve, 100));
                    await ChartRenderer.renderDistribution(currentData, selectedTags, 'trendChart');
                });
                await renderModular(() => renderIndividualCharts());
            } else if (mode === 'anomaly') {
                chartContainer.innerHTML = '';
                await renderModular(() => renderAnomalyView());
            } else {
                chartContainer.innerHTML = '';
                await renderModular(() => renderCombinedChart());
            }
        } catch (error) {
            console.error('Error in setChartMode:', error);
            chartContainer.innerHTML = '<div style="color: #ff6b6b; text-align: center; padding: 40px;">❌ Error loading chart: ' + error.message + '</div>';
        } finally {
            renderingState.isRendering = false;
            // Re-enable all chart mode buttons
            disableChartModeButtons(false);
        }
    } else {
        chartContainer.innerHTML = '<div style="text-align: center; padding: 60px; color: #888;">No data loaded. Please select date range and tags.</div>';
        renderingState.isRendering = false;
        disableChartModeButtons(false);
    }
}

/**
 * Clear all Plotly charts to prevent memory leaks
 */
function clearAllCharts() {
    // Clear main chart
    const mainChart = document.getElementById('trendChart');
    if (mainChart && mainChart.data) {
        try {
            Plotly.purge('trendChart');
        } catch (e) {
            console.warn('Failed to purge trendChart:', e);
        }
    }
    
    // Clear individual charts section
    const individualSection = document.getElementById('individualCharts');
    if (individualSection) {
        const chartDivs = individualSection.querySelectorAll('[id^="individualChart_"]');
        chartDivs.forEach(div => {
            try {
                Plotly.purge(div.id);
            } catch (e) {
                // Ignore if chart doesn't exist
            }
        });
    }
    
    // Clear correlation chart
    try {
        const corrChart = document.getElementById('correlationChart');
        if (corrChart && corrChart.data) {
            Plotly.purge('correlationChart');
        }
    } catch (e) {
        console.warn('Failed to purge correlationChart:', e);
    }
    
    // Track cleared charts
    renderingState.renderedCharts.clear();
    console.log('✓ All charts cleared');
}

/**
 * Disable/Enable chart mode buttons to prevent double clicks
 */
function disableChartModeButtons(disabled) {
    const buttons = [
        'modeLines', 'modeScatter', 'modeBoxPlot',
        'modeDistribution', 'modeBIAnalytics'
    ];
    
    buttons.forEach(btnId => {
        const btn = document.getElementById(btnId);
        if (btn) {
            btn.disabled = disabled;
            btn.style.opacity = disabled ? '0.5' : '1';
            btn.style.cursor = disabled ? 'not-allowed' : 'pointer';
        }
    });
}

/**
 * Modular rendering wrapper with async control
 */
async function renderModular(renderFunction) {
    const signal = renderingState.abortController.signal;
    
    if (signal.aborted) {
        console.log('⚠️ Render aborted');
        return;
    }
    
    // Use setTimeout to break execution into smaller chunks and prevent UI freeze
    await new Promise(resolve => setTimeout(resolve, 0));
    
    // Yield to browser for smooth UI
    await new Promise(resolve => requestAnimationFrame(resolve));
    
    // Execute render function
    await renderFunction();
    
    console.log(`✓ Rendered ${renderingState.currentMode} mode`);
}

// Render Anomaly View
async function renderAnomalyView() {
    await new Promise(resolve => setTimeout(resolve, 10));
    
    const traces = [];
    let anomalyHTML = '<div class="anomaly-panel"><h3>⚠ Anomaly Detection Results</h3>';
    
    selectedTags.forEach((tag, index) => {
        const color = tagColors[index % tagColors.length];
        const { anomalies, stats } = detectAnomalies(tag);
        
        // Skip if no valid stats
        if (!stats || stats.count === 0) {
            anomalyHTML += `
                <div style="margin: 10px 0; padding: 10px; background: rgba(255, 68, 68, 0.1); border-radius: 4px;">
                    <strong style="color: ${color}">${tag}</strong>
                    <div style="color: #888; margin-top: 5px;">No valid data available</div>
                </div>
            `;
            return;
        }
        
        // Normal data
        const validData = getValidDataPoints(currentData, tag);
        traces.push({
            x: validData.map(d => new Date(d.Timestamp)),
            y: validData.map(d => d[tag]),
            name: tagLabel(tag),
            type: 'scatter',
            mode: 'lines',
            line: { color: color, width: 1 }
        });
        
        // Anomalies as markers
        if (anomalies.length > 0) {
            const validAnomalies = anomalies.filter(a => a.timestamp && !isNaN(new Date(a.timestamp).getTime()));
            if (validAnomalies.length > 0) {
                traces.push({
                    x: validAnomalies.map(a => new Date(a.timestamp)),
                    y: validAnomalies.map(a => a.value),
                    name: `${tag} (Anomalies)`,
                    type: 'scatter',
                    mode: 'markers',
                    marker: { color: '#ff6b6b', size: 10, symbol: 'x' }
                });
            }
        }
        
        // Add 3-sigma bounds
        if (stats) {
            traces.push({
                x: validData.map(d => new Date(d.Timestamp)),
                y: Array(validData.length).fill(stats.upperBound),
                name: `${tag} (+3σ)`,
                type: 'scatter',
                mode: 'lines',
                line: { color: color, width: 1, dash: 'dash' },
                showlegend: false
            });
            
            traces.push({
                x: validData.map(d => new Date(d.Timestamp)),
                y: Array(validData.length).fill(stats.lowerBound),
                name: `${tag} (-3σ)`,
                type: 'scatter',
                mode: 'lines',
                line: { color: color, width: 1, dash: 'dash' },
                showlegend: false
            });
            
            anomalyHTML += `
                <div style="margin: 10px 0; padding: 10px; background: rgba(0,212,255,0.1); border-radius: 4px;">
                    <strong style="color: ${color}">${tag}</strong>
                    <div class="stats-grid">
                        <div class="stat-item"><div class="label">Anomalies</div><div class="value">${anomalies.length}</div></div>
                        <div class="stat-item"><div class="label">Mean</div><div class="value">${stats.mean.toFixed(2)}</div></div>
                        <div class="stat-item"><div class="label">Std Dev</div><div class="value">${stats.stdDev.toFixed(2)}</div></div>
                        <div class="stat-item"><div class="label">Min</div><div class="value">${stats.min.toFixed(2)}</div></div>
                        <div class="stat-item"><div class="label">Max</div><div class="value">${stats.max.toFixed(2)}</div></div>
                        <div class="stat-item"><div class="label">Median</div><div class="value">${stats.median.toFixed(2)}</div></div>
                    </div>
                </div>
            `;
        }
    });
    
    anomalyHTML += '</div>';
    document.getElementById('anomalyInfo').innerHTML = anomalyHTML;
    
    const layout = {
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(15, 52, 96, 0.3)',
        font: { color: '#e0e0e0', family: 'Segoe UI', size: 12 },
        title: 'Anomaly Detection (3-Sigma Method)',
        xaxis: { title: 'Time', gridcolor: 'rgba(0, 212, 255, 0.1)', color: '#00d4ff' },
        yaxis: { title: 'Value', gridcolor: 'rgba(0, 212, 255, 0.1)', color: '#00d4ff' },
        height: 500,
        hovermode: 'x unified'
    };
    
    Plotly.newPlot('trendChart', traces, layout, { responsive: true, scrollZoom: true });
}

// Export to CSV
async function exportCsv() {
    if (!currentData) return;
    
    const startDate = document.getElementById('startDate').value;
    const endDate = document.getElementById('endDate').value;
    
    const params = new URLSearchParams({
        start_date: new Date(startDate).toISOString(),
        end_date: new Date(endDate).toISOString(),
        tags: JSON.stringify(selectedTags)
    });
    
    window.location.href = `/api/export/csv?${params}`;
}

// Export to Excel
async function exportExcel() {
    if (!currentData) return;
    
    const startDate = document.getElementById('startDate').value;
    const endDate = document.getElementById('endDate').value;
    
    const params = new URLSearchParams({
        start_date: new Date(startDate).toISOString(),
        end_date: new Date(endDate).toISOString(),
        tags: JSON.stringify(selectedTags)
    });
    
    window.location.href = `/api/export/excel?${params}`;
}

// Enable export buttons
function enableExportButtons() {
    document.getElementById('exportCsvBtn').disabled = false;
    document.getElementById('exportExcelBtn').disabled = false;
}

// Show/hide loading
function showLoading(show, message = '', details = '') {
    const indicator = document.getElementById('loadingIndicator');
    const progressEl = document.getElementById('loadingProgress');
    const detailsEl = document.getElementById('loadingDetails');
    
    indicator.classList.toggle('active', show);
    
    if (show && progressEl && detailsEl) {
        progressEl.textContent = message;
        detailsEl.textContent = details;
    }
    
    const btn = document.getElementById('loadDataBtn');
    if (btn) {
        if (show) {
            btn.disabled = true;
            btn.dataset.originalText = btn.dataset.originalText || btn.textContent.trim();
            btn.textContent = '⏳ Loading...';
        } else {
            btn.disabled = false;
            if (btn.dataset.originalText) {
                btn.textContent = btn.dataset.originalText;
            }
        }
    }
}

// Show error
function showError(message) {
    const errorDiv = document.getElementById('errorDisplay');
    errorDiv.textContent = message;
    errorDiv.classList.add('active');
}

// Hide error
function hideError() {
    document.getElementById('errorDisplay').classList.remove('active');
}

// Calculate synchronized statistics for multiple tags
async function renderSyncStatsView() {
    if (!currentData || selectedTags.length === 0) return;
    
    await new Promise(resolve => setTimeout(resolve, 10));
    
    // Hide other views
    document.getElementById('trendChart').style.display = 'block';
    document.getElementById('correlationChart').style.display = 'none';
    document.getElementById('anomalyInfo').style.display = 'none';
    document.getElementById('syncStatsPanel').style.display = 'block';
    
    // Build synchronized data structure
    const syncData = {};
    const tagMaps = {};
    
    // Create timestamp maps for each tag
    selectedTags.forEach(tag => {
        tagMaps[tag] = new Map();
        currentData.forEach(point => {
            if (point[tag] !== null && point[tag] !== undefined && !isNaN(point[tag])) {
                tagMaps[tag].set(point.timestamp, point[tag]);
            }
        });
    });
    
    // Calculate statistics for each tag using API data if available
    const tagStats = {};
    selectedTags.forEach(tag => {
        // First try to use API statistics
        if (tagStatistics[tag]) {
            const apiStats = tagStatistics[tag];
            const values = currentData
                .map(p => p[tag])
                .filter(v => v !== null && v !== undefined && !isNaN(v));
            
            const allTimestamps = new Set();
            currentData.forEach(point => allTimestamps.add(point.Timestamp));
            
            tagStats[tag] = {
                count: apiStats.count || values.length,
                mean: apiStats.mean || 0,
                stdDev: apiStats.std || 0,
                min: apiStats.min || 0,
                max: apiStats.max || 0,
                median: apiStats.median || (apiStats.min + apiStats.max) / 2,
                coverage: values.length > 0 ? (values.length / allTimestamps.size) * 100 : 0
            };
        } else {
            // Fallback: calculate from data
            const values = currentData
                .map(p => p[tag])
                .filter(v => v !== null && v !== undefined && !isNaN(v));
            
            if (values.length > 0) {
                const sorted = values.slice().sort((a, b) => a - b);
                const sum = values.reduce((a, b) => a + b, 0);
                const mean = sum / values.length;
                const variance = values.reduce((acc, val) => acc + Math.pow(val - mean, 2), 0) / values.length;
                const stdDev = Math.sqrt(variance);
                
                const allTimestamps = new Set();
                currentData.forEach(point => allTimestamps.add(point.Timestamp));
                
                tagStats[tag] = {
                    count: values.length,
                    mean: mean,
                    stdDev: stdDev,
                    min: sorted[0],
                    max: sorted[sorted.length - 1],
                    median: sorted[Math.floor(sorted.length / 2)],
                    coverage: (values.length / allTimestamps.size) * 100
                };
            }
        }
    });
    
    // Render statistics panel
    let html = '<h3>🔗 Synchronized Tag Statistics</h3>';
    html += '<div class="sync-stats-grid">';
    
    selectedTags.forEach(tag => {
        const stats = tagStats[tag];
        if (stats && typeof stats.mean === 'number') {
            html += `
                <div class="tag-stats-card">
                    <h4>${tag}</h4>
                    <div class="stat-row">
                        <span class="stat-label">Sample Count:</span>
                        <span class="stat-value">${stats.count || 0}</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">Coverage:</span>
                        <span class="stat-value">${(stats.coverage || 0).toFixed(1)}%</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">Average (μ):</span>
                        <span class="stat-value">${(stats.mean || 0).toFixed(4)}</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">Std Dev (σ):</span>
                        <span class="stat-value">${(stats.stdDev || 0).toFixed(4)}</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">Min Value:</span>
                        <span class="stat-value">${(stats.min || 0).toFixed(4)}</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">Max Value:</span>
                        <span class="stat-value">${(stats.max || 0).toFixed(4)}</span>
                    </div>
                    <div class="stat-row">
                        <span class="stat-label">Median:</span>
                        <span class="stat-value">${(stats.median || 0).toFixed(4)}</span>
                    </div>
                </div>
            `;
        }
    });
    
    html += '</div>';
    document.getElementById('syncStatsPanel').innerHTML = html;
    
    // Render synchronized time-series chart
    const traces = selectedTags.map((tag, index) => {
        const x = [];
        const y = [];
        
        currentData.forEach(point => {
            if (point[tag] !== null && point[tag] !== undefined && !isNaN(point[tag])) {
                x.push(point.timestamp);
                y.push(point[tag]);
            }
        });
        
        return {
            x: x,
            y: y,
            name: tagLabel(tag),
            type: 'scatter',
            mode: 'lines+markers',
            marker: { size: 4, color: tagColors[index % tagColors.length] },
            line: { width: 2, color: tagColors[index % tagColors.length] }
        };
    });
    
    const layout = {
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(15, 52, 96, 0.3)',
        font: { color: '#e0e0e0', family: 'Segoe UI', size: 12 },
        title: 'Time-Synchronized Multi-Tag Trends',
        xaxis: { 
            title: 'Time', 
            gridcolor: 'rgba(0, 212, 255, 0.1)', 
            color: '#00d4ff',
            type: 'date'
        },
        yaxis: { 
            title: 'Value', 
            gridcolor: 'rgba(0, 212, 255, 0.1)', 
            color: '#00d4ff' 
        },
        hovermode: 'x unified',
        height: 500,
        margin: { l: 60, r: 30, t: 60, b: 60 }
    };
    
    const config = {
        responsive: true,
        displayModeBar: true,
        scrollZoom: true
    };
    
    Plotly.newPlot('trendChart', traces, layout, config);
}

// Render correlation view for multiple tags
async function renderCorrelationView() {
    if (!currentData || selectedTags.length < 2) {
        document.getElementById('anomalyInfo').innerHTML = '<div class="correlation-info"><p>⚠️ Please select at least 2 tags to see correlation analysis</p></div>';
        document.getElementById('anomalyInfo').style.display = 'block';
        document.getElementById('trendChart').style.display = 'none';
        document.getElementById('correlationChart').style.display = 'none';
        document.getElementById('syncStatsPanel').style.display = 'none';
        return;
    }
    
    await new Promise(resolve => setTimeout(resolve, 10));
    
    // Show correlation view
    document.getElementById('trendChart').style.display = 'none';
    document.getElementById('correlationChart').style.display = 'block';
    document.getElementById('anomalyInfo').style.display = 'block';
    document.getElementById('syncStatsPanel').style.display = 'none';
    
    // Build timestamp-aligned data
    const tagMaps = {};
    selectedTags.forEach(tag => {
        tagMaps[tag] = new Map();
        currentData.forEach(point => {
            if (point[tag] !== null && point[tag] !== undefined && !isNaN(point[tag])) {
                tagMaps[tag].set(point.timestamp, point[tag]);
            }
        });
    });
    
    // Find common timestamps
    const commonTimestamps = [];
    const firstTag = selectedTags[0];
    tagMaps[firstTag].forEach((value, ts) => {
        const hasAllTags = selectedTags.every(tag => tagMaps[tag].has(ts));
        if (hasAllTags) {
            commonTimestamps.push(ts);
        }
    });
    
    // Build correlation matrix
    const correlations = [];
    const correlationText = [];
    
    for (let i = 0; i < selectedTags.length; i++) {
        const row = [];
        const textRow = [];
        for (let j = 0; j < selectedTags.length; j++) {
            if (i === j) {
                row.push(1.0);
                textRow.push('1.00');
            } else {
                const xValues = commonTimestamps.map(ts => tagMaps[selectedTags[i]].get(ts));
                const yValues = commonTimestamps.map(ts => tagMaps[selectedTags[j]].get(ts));
                const corr = calculateCorrelation(xValues, yValues);
                row.push(corr || 0);
                textRow.push(corr ? corr.toFixed(3) : 'N/A');
            }
        }
        correlations.push(row);
        correlationText.push(textRow);
    }
    
    // Display correlation info
    let infoHtml = `
        <div class="correlation-info">
            <h3>📊 Tag Correlation Analysis</h3>
            <p><strong>Common Time Points:</strong> ${commonTimestamps.length} synchronized samples</p>
            <p><strong>Selected Tags:</strong> ${selectedTags.join(', ')}</p>
    `;
    
    // Show strongest correlation
    let maxCorr = -1;
    let maxPair = '';
    for (let i = 0; i < selectedTags.length; i++) {
        for (let j = i + 1; j < selectedTags.length; j++) {
            const corr = Math.abs(correlations[i][j]);
            if (corr > maxCorr) {
                maxCorr = corr;
                maxPair = `${selectedTags[i]} ↔ ${selectedTags[j]}`;
            }
        }
    }
    
    if (maxCorr >= 0) {
        infoHtml += `<p><strong>Strongest Correlation:</strong> ${maxPair} (r = ${maxCorr.toFixed(3)})</p>`;
    }
    
    infoHtml += '</div>';
    document.getElementById('anomalyInfo').innerHTML = infoHtml;
    
    // Render correlation heatmap
    const trace = {
        z: correlations,
        x: selectedTags,
        y: selectedTags,
        text: correlationText,
        type: 'heatmap',
        colorscale: [
            [0, '#ff0000'],
            [0.5, '#ffffff'],
            [1, '#00ff00']
        ],
        zmin: -1,
        zmax: 1,
        colorbar: {
            title: 'Correlation',
            titleside: 'right',
            tickmode: 'linear',
            tick0: -1,
            dtick: 0.5,
            font: { color: '#e0e0e0' }
        },
        hovertemplate: '<b>%{y} vs %{x}</b><br>Correlation: %{z:.3f}<extra></extra>'
    };
    
    const layout = {
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(15, 52, 96, 0.3)',
        font: { color: '#e0e0e0', family: 'Segoe UI', size: 12 },
        title: 'Correlation Matrix Heatmap',
        xaxis: { 
            tickangle: -45,
            color: '#00d4ff',
            side: 'bottom'
        },
        yaxis: { 
            color: '#00d4ff' 
        },
        height: 500,
        margin: { l: 150, r: 100, t: 60, b: 150 }
    };
    
    const config = {
        responsive: true,
        displayModeBar: true
    };
    
    Plotly.newPlot('correlationChart', [trace], layout, config);
}

// Calculate Pearson correlation coefficient
function calculateCorrelation(x, y) {
    if (x.length !== y.length || x.length === 0) return null;
    
    const n = x.length;
    const sumX = x.reduce((a, b) => a + b, 0);
    const sumY = y.reduce((a, b) => a + b, 0);
    const sumXY = x.reduce((sum, xi, i) => sum + xi * y[i], 0);
    const sumX2 = x.reduce((sum, xi) => sum + xi * xi, 0);
    const sumY2 = y.reduce((sum, yi) => sum + yi * yi, 0);
    
    const numerator = n * sumXY - sumX * sumY;
    const denominator = Math.sqrt((n * sumX2 - sumX * sumX) * (n * sumY2 - sumY * sumY));
    
    if (denominator === 0) return null;
    return numerator / denominator;
}

// Render Best/Worst Case Mode
function renderBestWorstMode() {
    document.getElementById('peakAnalysisPanel').style.display = 'block';
    
    // Clear previous results
    document.getElementById('peakResults').style.display = 'none';
    document.getElementById('peakResults').innerHTML = '';
    document.getElementById('correlationChart').innerHTML = '';
    
    // Check if data is loaded
    if (!currentData || currentData.length === 0) {
        document.getElementById('peakResults').innerHTML = '<p style="color: #ff6b6b; text-align: center; padding: 20px;">⚠ Please load data first before using Best/Worst analysis!</p>';
        document.getElementById('peakResults').style.display = 'block';
        return;
    }
    
    // Populate target tag dropdown with only tags that have data
    const targetTagSelect = document.getElementById('peakTargetTag');
    targetTagSelect.innerHTML = '<option value="">Select target tag...</option>';
    
    const tagsWithData = selectedTags.filter(tag => {
        // Check if this tag has any non-null values
        return currentData.some(row => row[tag] !== null && row[tag] !== undefined && !isNaN(row[tag]));
    });
    
    if (tagsWithData.length === 0) {
        document.getElementById('peakResults').innerHTML = '<p style="color: #ff6b6b; text-align: center; padding: 20px;">⚠ No valid data found in loaded tags!</p>';
        document.getElementById('peakResults').style.display = 'block';
        return;
    }
    
    tagsWithData.forEach(tag => {
        const option = document.createElement('option');
        option.value = tag;
        option.textContent = tag;
        targetTagSelect.appendChild(option);
    });
    
    // Show normal chart
    renderCombinedChart();
}

// Analyze Peak Moment (Best or Worst Case)
async function analyzePeakMoment(type) {
    const targetTag = document.getElementById('peakTargetTag').value;
    
    if (!targetTag) {
        alert('⚠ Please select a target tag first!');
        return;
    }
    
    if (!currentData || currentData.length === 0) {
        alert('⚠ No data loaded!');
        return;
    }
    
    // Show loading indicator
    const resultsDiv = document.getElementById('peakResults');
    resultsDiv.innerHTML = '<div style="text-align: center; padding: 40px; color: #00d4ff;"><div class="spinner" style="border: 4px solid rgba(0, 212, 255, 0.1); border-top: 4px solid #00d4ff; border-radius: 50%; width: 40px; height: 40px; animation: spin 1s linear infinite; margin: 0 auto 10px;"></div><p>🔄 Analyzing data...</p></div>';
    
    // Use setTimeout to allow UI to update
    await new Promise(resolve => setTimeout(resolve, 100));
    
    // Find peak moment
    let peakValue, peakTimestamp, peakIndex;
    
    if (type === 'best') {
        // Find maximum value
        peakValue = -Infinity;
        currentData.forEach((row, idx) => {
            if (row[targetTag] !== null && row[targetTag] !== undefined && row[targetTag] > peakValue) {
                peakValue = row[targetTag];
                peakTimestamp = row.Timestamp;
                peakIndex = idx;
            }
        });
    } else {
        // Find minimum value
        peakValue = Infinity;
        currentData.forEach((row, idx) => {
            if (row[targetTag] !== null && row[targetTag] !== undefined && row[targetTag] < peakValue) {
                peakValue = row[targetTag];
                peakTimestamp = row.Timestamp;
                peakIndex = idx;
            }
        });
    }
    
    if (peakIndex === undefined) {
        alert(`⚠ Could not find peak value for "${targetTag}"!\n\nPossible reasons:\n- Tag has no data in the loaded time range\n- All values are null or invalid\n- Please select a different tag`);
        return;
    }
    
    // Validate we have other tags to compare
    if (selectedTags.length < 2) {
        alert('⚠ Please select at least 2 tags to perform comparison analysis!');
        return;
    }
    
    // Get data around peak moment (±10 minutes window for context)
    const peakTime = new Date(peakTimestamp);
    const windowMs = 10 * 60 * 1000; // 10 minutes
    const startTime = new Date(peakTime.getTime() - windowMs);
    const endTime = new Date(peakTime.getTime() + windowMs);
    
    const windowData = currentData.filter(row => {
        const rowTime = new Date(row.Timestamp);
        return rowTime >= startTime && rowTime <= endTime;
    });
    
    // Allow UI to breathe before heavy calculations
    await new Promise(resolve => setTimeout(resolve, 50));
    
    // Calculate statistics for all tags at peak moment and in window
    const tagStats = {};
    const tagsToProcess = selectedTags.filter(tag => tag !== targetTag);
    
    // Process tags in chunks to avoid blocking
    const chunkSize = 5;
    for (let i = 0; i < tagsToProcess.length; i += chunkSize) {
        const chunk = tagsToProcess.slice(i, i + chunkSize);
        
        chunk.forEach(tag => {
            const windowValues = windowData
                .map(row => row[tag])
                .filter(v => v !== null && v !== undefined && !isNaN(v));
            
            if (windowValues.length === 0) {
                tagStats[tag] = null;
                return;
            }
            
            const peakMomentValue = currentData[peakIndex][tag];
            const mean = windowValues.reduce((a, b) => a + b, 0) / windowValues.length;
            const sorted = [...windowValues].sort((a, b) => a - b);
            const stdDev = Math.sqrt(windowValues.reduce((sum, val) => sum + Math.pow(val - mean, 2), 0) / windowValues.length);
            
            tagStats[tag] = {
                atPeak: peakMomentValue,
                mean: mean,
                stdDev: stdDev,
                min: sorted[0],
                max: sorted[sorted.length - 1],
                median: sorted[Math.floor(sorted.length / 2)]
            };
        });
        
        // Let UI update between chunks
        if (i + chunkSize < tagsToProcess.length) {
            await new Promise(resolve => setTimeout(resolve, 10));
        }
    }
    
    // Display results (async to prevent blocking)
    await displayPeakAnalysis(type, targetTag, peakValue, peakTimestamp, tagStats, windowData);
    
    // Highlight peak moment on chart
    highlightPeakOnChart(peakTimestamp, type, targetTag);
}

// Display Peak Analysis Results
async function displayPeakAnalysis(type, targetTag, peakValue, peakTimestamp, tagStats, windowData) {
    const resultsDiv = document.getElementById('peakResults');
    const typeLabel = type === 'best' ? 'BEST CASE (Maximum)' : 'WORST CASE (Minimum)';
    const typeColor = type === 'best' ? '#00ff88' : '#ff6b6b';
    const typeIcon = type === 'best' ? '📈' : '📉';
    
    const peakVal = (typeof peakValue === 'number' && !isNaN(peakValue)) ? peakValue.toFixed(2) : 'N/A';
    
    let html = `
        <div style="background: rgba(0, 0, 0, 0.3); border-radius: 8px; padding: 15px; margin-bottom: 15px;">
            <div style="color: #00d4ff; font-size: 16px; font-weight: bold; margin-bottom: 10px; text-align: center;">
                ${typeIcon} ${typeLabel}
            </div>
            <div style="font-size: 24px; font-weight: bold; text-align: center; margin-bottom: 10px; color: ${typeColor};">
                ${targetTag}: ${peakVal}
            </div>
            <div style="color: #888; text-align: center; font-size: 14px;">
                📅 ${new Date(peakTimestamp).toLocaleString()}
            </div>
            <div style="color: #888; text-align: center; font-size: 12px; margin-top: 5px;">
                Analysis Window: ±10 minutes (${windowData.length} data points)
            </div>
        </div>
        
        <h4 style="color: #00d4ff; margin: 15px 0; font-size: 16px;">
            📊 Parameter Behavior at Peak Moment:
        </h4>
        
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 10px;">
    `;
    
    Object.keys(tagStats).forEach(tag => {
        const stats = tagStats[tag];
        if (!stats) {
            html += `
                <div style="background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 68, 68, 0.3); border-radius: 6px; padding: 10px;">
                    <div style="color: #ff6b6b; font-size: 13px; font-weight: bold; margin-bottom: 5px;">${tag}</div>
                    <div style="color: #888; font-size: 11px;">No data available</div>
                </div>
            `;
            return;
        }
        
        const deviation = stats.atPeak !== null ? Math.abs(stats.atPeak - stats.mean) : 0;
        const deviationPercent = stats.mean !== 0 ? (deviation / Math.abs(stats.mean) * 100).toFixed(1) : 0;
        const isAbnormal = deviation > stats.stdDev * 2;
        const borderColor = isAbnormal ? 'rgba(255, 215, 0, 0.5)' : 'rgba(0, 212, 255, 0.2)';
        
        const atPeakVal = stats.atPeak !== null && typeof stats.atPeak === 'number' ? stats.atPeak.toFixed(2) : 'N/A';
        const meanVal = typeof stats.mean === 'number' ? stats.mean.toFixed(2) : stats.mean;
        const stdDevVal = typeof stats.stdDev === 'number' ? stats.stdDev.toFixed(2) : stats.stdDev;
        const minVal = typeof stats.min === 'number' ? stats.min.toFixed(2) : stats.min;
        const maxVal = typeof stats.max === 'number' ? stats.max.toFixed(2) : stats.max;
        const medianVal = typeof stats.median === 'number' ? stats.median.toFixed(2) : stats.median;
        
        html += `
            <div style="background: rgba(255, 255, 255, 0.05); border: 2px solid ${borderColor}; border-radius: 6px; padding: 10px;">
                <div style="color: #00d4ff; font-size: 13px; font-weight: bold; margin-bottom: 8px;">
                    ${tag} ${isAbnormal ? '⚠' : ''}
                </div>
                <div style="display: flex; flex-direction: column; gap: 4px; font-size: 11px;">
                    <div style="display: flex; justify-content: space-between;">
                        <span style="color: #888;">At Peak:</span>
                        <span style="color: ${typeColor}; font-weight: bold;">${atPeakVal}</span>
                    </div>
                    <div style="display: flex; justify-content: space-between;">
                        <span style="color: #888;">Window Avg:</span>
                        <span style="color: white; font-weight: bold;">${meanVal}</span>
                    </div>
                    <div style="display: flex; justify-content: space-between;">
                        <span style="color: #888;">Std Dev:</span>
                        <span style="color: white;">${stdDevVal}</span>
                    </div>
                    <div style="display: flex; justify-content: space-between;">
                        <span style="color: #888;">Min/Max:</span>
                        <span style="color: white;">${minVal} / ${maxVal}</span>
                    </div>
                    <div style="display: flex; justify-content: space-between;">
                        <span style="color: #888;">Median:</span>
                        <span style="color: white;">${medianVal}</span>
                    </div>
                    ${isAbnormal ? `
                        <div style="margin-top: 5px; padding: 5px; background: rgba(255, 215, 0, 0.2); border-radius: 3px; text-align: center;">
                            <span style="color: #ffd700; font-weight: bold; font-size: 10px;">⚠ ABNORMAL (>${deviationPercent}% deviation)</span>
                        </div>
                    ` : ''}
                </div>
            </div>
        `;
    });
    
    html += `</div>`;
    
    resultsDiv.innerHTML = html;
    resultsDiv.style.display = 'block';
    
    // Render bar chart comparison below the cards (async to prevent blocking)
    await new Promise(resolve => setTimeout(resolve, 50));
    renderPeakComparisonChart(type, targetTag, tagStats);
}

// Render Bar Chart Comparison with Variation Bands
function renderPeakComparisonChart(type, targetTag, tagStats) {
    const chartDiv = document.getElementById('correlationChart');
    chartDiv.innerHTML = '<h3 style="color: #00d4ff; text-align: center; margin: 20px 0;">📊 Parameter Comparison with Variation Bands</h3><div id="peakBarChart"></div>';
    
    const tags = Object.keys(tagStats).filter(tag => tagStats[tag] !== null);
    
    if (tags.length === 0) {
        chartDiv.innerHTML += '<p style="color: #888; text-align: center;">No parameter data available for comparison</p>';
        return;
    }
    
    const typeColor = type === 'best' ? '#00ff88' : '#ff6b6b';
    
    // Create traces for the bar chart
    const traces = [];
    
    // Trace 1: Average values (baseline)
    traces.push({
        x: tags,
        y: tags.map(tag => tagStats[tag].mean),
        name: 'Average (Baseline)',
        type: 'bar',
        marker: {
            color: 'rgba(255, 255, 255, 0.3)',
            line: { color: '#888', width: 1 }
        },
        text: tags.map(tag => {
            const mean = tagStats[tag].mean;
            return `Avg: ${typeof mean === 'number' ? mean.toFixed(2) : mean}`;
        }),
        textposition: 'none',
        hovertemplate: '<b>%{x}</b><br>Average: %{y:.2f}<extra></extra>'
    });
    
    // Trace 2: Peak moment values
    traces.push({
        x: tags,
        y: tags.map(tag => tagStats[tag].atPeak !== null ? tagStats[tag].atPeak : 0),
        name: type === 'best' ? 'At Best Case' : 'At Worst Case',
        type: 'bar',
        marker: {
            color: typeColor,
            opacity: 0.8,
            line: { color: typeColor, width: 2 }
        },
        text: tags.map(tag => {
            const atPeak = tagStats[tag].atPeak;
            if (atPeak === null) return 'N/A';
            return typeof atPeak === 'number' ? atPeak.toFixed(2) : atPeak;
        }),
        textposition: 'outside',
        textfont: { color: typeColor, size: 11, family: 'Arial Black' },
        hovertemplate: '<b>%{x}</b><br>' + (type === 'best' ? 'Best Case' : 'Worst Case') + ': %{y:.2f}<extra></extra>'
    });
    
    // Add error bars showing ±1 standard deviation
    const shapes = [];
    const annotations = [];
    
    tags.forEach((tag, index) => {
        const stats = tagStats[tag];
        const x = index;
        const mean = stats.mean;
        const stdDev = stats.stdDev;
        const upperBound = mean + stdDev;
        const lowerBound = mean - stdDev;
        
        // Create variation band as rectangle
        shapes.push({
            type: 'rect',
            xref: 'x',
            yref: 'y',
            x0: x - 0.4,
            x1: x + 0.4,
            y0: lowerBound,
            y1: upperBound,
            fillcolor: 'rgba(0, 212, 255, 0.15)',
            line: {
                color: 'rgba(0, 212, 255, 0.4)',
                width: 1,
                dash: 'dot'
            },
            layer: 'below'
        });
        
        // Add Min/Max markers
        shapes.push({
            type: 'line',
            x0: x - 0.3,
            x1: x + 0.3,
            y0: stats.min,
            y1: stats.min,
            line: {
                color: '#ff6b6b',
                width: 2
            }
        });
        
        shapes.push({
            type: 'line',
            x0: x - 0.3,
            x1: x + 0.3,
            y0: stats.max,
            y1: stats.max,
            line: {
                color: '#00ff88',
                width: 2
            }
        });
        
        // Add annotations for abnormal values
        const deviation = Math.abs(stats.atPeak - mean);
        if (deviation > stdDev * 2) {
            annotations.push({
                x: x,
                y: stats.atPeak,
                text: '⚠',
                showarrow: false,
                font: {
                    size: 20,
                    color: '#ffd700'
                },
                xshift: 15,
                yshift: 10
            });
        }
    });
    
    const layout = {
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(15, 52, 96, 0.3)',
        font: { color: '#e0e0e0', family: 'Segoe UI', size: 11 },
        title: {
            text: `Parameter Behavior at ${type === 'best' ? 'BEST' : 'WORST'} Case Moment<br><sub>Shaded area = ±1σ (Standard Deviation) | Red/Green lines = Min/Max range</sub>`,
            font: { color: '#00d4ff', size: 14 }
        },
        xaxis: {
            title: 'Parameters',
            gridcolor: 'rgba(0, 212, 255, 0.1)',
            color: '#00d4ff',
            tickangle: -45
        },
        yaxis: {
            title: 'Value',
            gridcolor: 'rgba(0, 212, 255, 0.1)',
            color: '#00d4ff'
        },
        barmode: 'group',
        bargap: 0.3,
        bargroupgap: 0.1,
        height: 500,
        showlegend: true,
        legend: {
            bgcolor: 'rgba(0, 0, 0, 0.5)',
            bordercolor: '#00d4ff',
            borderwidth: 1,
            font: { color: '#e0e0e0' }
        },
        shapes: shapes,
        annotations: annotations,
        hovermode: 'closest'
    };
    
    const config = {
        responsive: true,
        displayModeBar: true,
        modeBarButtonsToRemove: ['lasso2d', 'select2d'],
        toImageButtonOptions: {
            format: 'png',
            filename: `peak_analysis_${type}_${new Date().toISOString().slice(0,10)}`,
            height: 800,
            width: 1200,
            scale: 2
        }
    };
    
    Plotly.newPlot('peakBarChart', traces, layout, config);
}

// Highlight Peak Moment on Chart
function highlightPeakOnChart(peakTimestamp, type, targetTag) {
    const color = type === 'best' ? '#00ff88' : '#ff6b6b';
    
    // Add vertical line annotation at peak moment
    const layout = {
        shapes: [{
            type: 'line',
            x0: peakTimestamp,
            x1: peakTimestamp,
            y0: 0,
            y1: 1,
            yref: 'paper',
            line: {
                color: color,
                width: 3,
                dash: 'dash'
            }
        }],
        annotations: [{
            x: peakTimestamp,
            y: 1,
            yref: 'paper',
            text: type === 'best' ? '📈 BEST' : '📉 WORST',
            showarrow: true,
            arrowhead: 2,
            arrowsize: 1,
            arrowwidth: 2,
            arrowcolor: color,
            ax: 0,
            ay: -40,
            font: {
                color: color,
                size: 14,
                family: 'Arial Black'
            },
            bgcolor: 'rgba(0, 0, 0, 0.8)',
            bordercolor: color,
            borderwidth: 2
        }]
    };
    
    Plotly.relayout('trendChart', layout);
}

// Compare Both Best and Worst Cases
function analyzeBothCases() {
    const targetTag = document.getElementById('peakTargetTag').value;
    
    if (!targetTag) {
        alert('⚠ Please select a target tag first!');
        return;
    }
    
    if (!currentData || currentData.length === 0) {
        alert('⚠ No data loaded!');
        return;
    }
    
    if (selectedTags.length < 2) {
        alert('⚠ Please select at least 2 tags to perform comparison analysis!');
        return;
    }
    
    // Find both best and worst moments
    let bestValue = -Infinity, worstValue = Infinity;
    let bestTimestamp, worstTimestamp, bestIndex, worstIndex;
    
    currentData.forEach((row, idx) => {
        const val = row[targetTag];
        if (val !== null && val !== undefined) {
            if (val > bestValue) {
                bestValue = val;
                bestTimestamp = row.Timestamp;
                bestIndex = idx;
            }
            if (val < worstValue) {
                worstValue = val;
                worstTimestamp = row.Timestamp;
                worstIndex = idx;
            }
        }
    });
    
    if (bestIndex === undefined || worstIndex === undefined) {
        alert('⚠ Could not find peak values for this tag!');
        return;
    }
    
    // Calculate statistics for both moments
    const windowMs = 10 * 60 * 1000; // 10 minutes
    
    // Best case statistics
    const bestTime = new Date(bestTimestamp);
    const bestWindowData = currentData.filter(row => {
        const rowTime = new Date(row.Timestamp);
        return rowTime >= new Date(bestTime.getTime() - windowMs) && 
               rowTime <= new Date(bestTime.getTime() + windowMs);
    });
    const bestStats = calculateWindowStats(bestWindowData, bestIndex, targetTag);
    
    // Worst case statistics
    const worstTime = new Date(worstTimestamp);
    const worstWindowData = currentData.filter(row => {
        const rowTime = new Date(row.Timestamp);
        return rowTime >= new Date(worstTime.getTime() - windowMs) && 
               rowTime <= new Date(worstTime.getTime() + windowMs);
    });
    const worstStats = calculateWindowStats(worstWindowData, worstIndex, targetTag);
    
    // Render comparison chart
    renderBothCasesComparison(targetTag, bestValue, bestTimestamp, bestStats, worstValue, worstTimestamp, worstStats);
}

// Helper function to calculate window statistics
function calculateWindowStats(windowData, peakIndex, targetTag) {
    const tagStats = {};
    
    selectedTags.forEach(tag => {
        if (tag === targetTag) return;
        
        const windowValues = windowData
            .map(row => row[tag])
            .filter(v => v !== null && v !== undefined && !isNaN(v));
        
        if (windowValues.length === 0) {
            tagStats[tag] = null;
            return;
        }
        
        const peakMomentValue = currentData[peakIndex][tag];
        const mean = windowValues.reduce((a, b) => a + b, 0) / windowValues.length;
        const sorted = [...windowValues].sort((a, b) => a - b);
        const stdDev = Math.sqrt(windowValues.reduce((sum, val) => sum + Math.pow(val - mean, 2), 0) / windowValues.length);
        
        tagStats[tag] = {
            atPeak: peakMomentValue,
            mean: mean,
            stdDev: stdDev,
            min: sorted[0],
            max: sorted[sorted.length - 1],
            median: sorted[Math.floor(sorted.length / 2)]
        };
    });
    
    return tagStats;
}

// Render Both Cases Comparison
function renderBothCasesComparison(targetTag, bestValue, bestTimestamp, bestStats, worstValue, worstTimestamp, worstStats) {
    const resultsDiv = document.getElementById('peakResults');
    const chartDiv = document.getElementById('correlationChart');
    
    const bestVal = typeof bestValue === 'number' ? bestValue.toFixed(2) : bestValue;
    const worstVal = typeof worstValue === 'number' ? worstValue.toFixed(2) : worstValue;
    const rangeVal = typeof bestValue === 'number' && typeof worstValue === 'number' ? (bestValue - worstValue).toFixed(2) : 'N/A';
    const swingVal = typeof bestValue === 'number' && typeof worstValue === 'number' && worstValue !== 0 ? ((bestValue - worstValue) / worstValue * 100).toFixed(1) : 'N/A';
    
    // Display summary cards
    let html = `
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-bottom: 20px;">
            <!-- Best Case Card -->
            <div style="background: linear-gradient(135deg, rgba(0, 255, 136, 0.2), rgba(0, 212, 255, 0.2)); border: 2px solid #00ff88; border-radius: 8px; padding: 15px;">
                <div style="color: #00ff88; font-size: 16px; font-weight: bold; margin-bottom: 10px; text-align: center;">
                    📈 BEST CASE (Maximum)
                </div>
                <div style="font-size: 24px; font-weight: bold; text-align: center; margin-bottom: 10px; color: #00ff88;">
                    ${targetTag}: ${bestVal}
                </div>
                <div style="color: #ddd; text-align: center; font-size: 14px;">
                    📅 ${new Date(bestTimestamp).toLocaleString()}
                </div>
            </div>
            
            <!-- Worst Case Card -->
            <div style="background: linear-gradient(135deg, rgba(255, 107, 107, 0.2), rgba(255, 68, 68, 0.2)); border: 2px solid #ff6b6b; border-radius: 8px; padding: 15px;">
                <div style="color: #ff6b6b; font-size: 16px; font-weight: bold; margin-bottom: 10px; text-align: center;">
                    📉 WORST CASE (Minimum)
                </div>
                <div style="font-size: 24px; font-weight: bold; text-align: center; margin-bottom: 10px; color: #ff6b6b;">
                    ${targetTag}: ${worstVal}
                </div>
                <div style="color: #ddd; text-align: center; font-size: 14px;">
                    📅 ${new Date(worstTimestamp).toLocaleString()}
                </div>
            </div>
        </div>
        
        <div style="background: rgba(255, 215, 0, 0.1); border: 1px solid rgba(255, 215, 0, 0.3); border-radius: 8px; padding: 15px; margin-bottom: 20px; text-align: center;">
            <span style="color: #ffd700; font-size: 18px; font-weight: bold;">
                📊 Range: ${rangeVal} | Swing: ${swingVal}%
            </span>
        </div>
    `;
    
    resultsDiv.innerHTML = html;
    resultsDiv.style.display = 'block';
    
    // Render comprehensive comparison bar chart
    renderBothCasesBarChart(targetTag, bestStats, worstStats);
}

// Render Bar Chart Comparing Best vs Worst Cases
function renderBothCasesBarChart(targetTag, bestStats, worstStats) {
    const chartDiv = document.getElementById('correlationChart');
    chartDiv.innerHTML = '<h3 style="color: #00d4ff; text-align: center; margin: 20px 0;">📊 Best vs Worst - Parameter Behavior Comparison</h3><div id="peakBarChart"></div>';
    
    const tags = Object.keys(bestStats).filter(tag => bestStats[tag] !== null && worstStats[tag] !== null);
    
    if (tags.length === 0) {
        chartDiv.innerHTML += '<p style="color: #888; text-align: center;">No parameter data available for comparison</p>';
        return;
    }
    
    const traces = [];
    
    // Trace 1: Average baseline
    traces.push({
        x: tags,
        y: tags.map(tag => bestStats[tag].mean),
        name: 'Average (Baseline)',
        type: 'bar',
        marker: {
            color: 'rgba(255, 255, 255, 0.2)',
            line: { color: '#888', width: 1 }
        },
        hovertemplate: '<b>%{x}</b><br>Avg: %{y:.2f}<extra></extra>'
    });
    
    // Trace 2: Best case values
    traces.push({
        x: tags,
        y: tags.map(tag => bestStats[tag].atPeak !== null ? bestStats[tag].atPeak : 0),
        name: '📈 At Best Case',
        type: 'bar',
        marker: {
            color: '#00ff88',
            opacity: 0.8,
            line: { color: '#00ff88', width: 2 }
        },
        text: tags.map(tag => bestStats[tag].atPeak !== null ? bestStats[tag].atPeak.toFixed(2) : 'N/A'),
        textposition: 'outside',
        textfont: { color: '#00ff88', size: 10, family: 'Arial' },
        hovertemplate: '<b>%{x}</b><br>Best: %{y:.2f}<extra></extra>'
    });
    
    // Trace 3: Worst case values
    traces.push({
        x: tags,
        y: tags.map(tag => worstStats[tag].atPeak !== null ? worstStats[tag].atPeak : 0),
        name: '📉 At Worst Case',
        type: 'bar',
        marker: {
            color: '#ff6b6b',
            opacity: 0.8,
            line: { color: '#ff6b6b', width: 2 }
        },
        text: tags.map(tag => worstStats[tag].atPeak !== null ? worstStats[tag].atPeak.toFixed(2) : 'N/A'),
        textposition: 'outside',
        textfont: { color: '#ff6b6b', size: 10, family: 'Arial' },
        hovertemplate: '<b>%{x}</b><br>Worst: %{y:.2f}<extra></extra>'
    });
    
    // Add variation bands and annotations
    const shapes = [];
    const annotations = [];
    
    tags.forEach((tag, index) => {
        const stats = bestStats[tag];
        const x = index;
        const mean = stats.mean;
        const stdDev = stats.stdDev;
        const upperBound = mean + stdDev;
        const lowerBound = mean - stdDev;
        
        // Variation band (±1σ)
        shapes.push({
            type: 'rect',
            xref: 'x',
            yref: 'y',
            x0: x - 0.45,
            x1: x + 0.45,
            y0: lowerBound,
            y1: upperBound,
            fillcolor: 'rgba(0, 212, 255, 0.1)',
            line: {
                color: 'rgba(0, 212, 255, 0.3)',
                width: 1,
                dash: 'dot'
            },
            layer: 'below'
        });
        
        // Min/Max range markers
        shapes.push({
            type: 'line',
            x0: x - 0.35,
            x1: x + 0.35,
            y0: stats.min,
            y1: stats.min,
            line: { color: 'rgba(255, 107, 107, 0.5)', width: 2 }
        });
        
        shapes.push({
            type: 'line',
            x0: x - 0.35,
            x1: x + 0.35,
            y0: stats.max,
            y1: stats.max,
            line: { color: 'rgba(0, 255, 136, 0.5)', width: 2 }
        });
        
        // Check for abnormal deviations
        const bestDeviation = Math.abs(bestStats[tag].atPeak - mean);
        const worstDeviation = Math.abs(worstStats[tag].atPeak - mean);
        
        if (bestDeviation > stdDev * 2) {
            annotations.push({
                x: x - 0.15,
                y: bestStats[tag].atPeak,
                text: '⚠',
                showarrow: false,
                font: { size: 18, color: '#ffd700' },
                yshift: 15
            });
        }
        
        if (worstDeviation > stdDev * 2) {
            annotations.push({
                x: x + 0.15,
                y: worstStats[tag].atPeak,
                text: '⚠',
                showarrow: false,
                font: { size: 18, color: '#ffd700' },
                yshift: 15
            });
        }
    });
    
    const layout = {
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(15, 52, 96, 0.3)',
        font: { color: '#e0e0e0', family: 'Segoe UI', size: 11 },
        title: {
            text: `Parameter Comparison: BEST vs WORST<br><sub>Shaded area = Normal range (Avg ± 1σ) | ⚠ = Critical deviation (>2σ) | Horizontal lines = Min/Max</sub>`,
            font: { color: '#00d4ff', size: 14 }
        },
        xaxis: {
            title: 'Parameters',
            gridcolor: 'rgba(0, 212, 255, 0.1)',
            color: '#00d4ff',
            tickangle: -45
        },
        yaxis: {
            title: 'Value',
            gridcolor: 'rgba(0, 212, 255, 0.1)',
            color: '#00d4ff'
        },
        barmode: 'group',
        bargap: 0.2,
        bargroupgap: 0.1,
        height: 550,
        showlegend: true,
        legend: {
            bgcolor: 'rgba(0, 0, 0, 0.5)',
            bordercolor: '#00d4ff',
            borderwidth: 1,
            font: { color: '#e0e0e0' },
            orientation: 'h',
            y: -0.2
        },
        shapes: shapes,
        annotations: annotations,
        hovermode: 'closest'
    };
    
    const config = {
        responsive: true,
        displayModeBar: true,
        modeBarButtonsToRemove: ['lasso2d', 'select2d'],
        toImageButtonOptions: {
            format: 'png',
            filename: `best_vs_worst_comparison_${new Date().toISOString().slice(0,10)}`,
            height: 900,
            width: 1400,
            scale: 2
        }
    };
    
    Plotly.newPlot('peakBarChart', traces, layout, config);
}

// =====================================================
// INDUSTRIAL FEATURES INTEGRATION
// =====================================================

// Global state for industrial features
let bandsEnabled = false;
let shiftSummaryVisible = false;
let healthScoreVisible = false;
let dataQualityVisible = false;

/**
 * Toggle operating bands on/off
 */
function toggleOperatingBands() {
    bandsEnabled = !bandsEnabled;
    const btn = document.getElementById('toggleBands');
    
    if (bandsEnabled) {
        btn.style.background = 'rgba(52, 199, 89, 0.4)';
        btn.style.borderWidth = '2px';
    } else {
        btn.style.background = 'rgba(52, 199, 89, 0.2)';
        btn.style.borderWidth = '1px';
    }
    
    if (currentData) {
        renderCombinedChart();
    }
}

/**
 * Show configuration modal for selected tags
 */
function configureBandsForSelectedTags() {
    if (selectedTags.length === 0) {
        showError('Please select at least one tag to configure operating bands.');
        return;
    }
    
    // Show modal for first selected tag
    window.IndustrialFeatures.showBandConfigModal(selectedTags[0]);
}

/**
 * Toggle shift summary panel
 */
function toggleShiftSummary() {
    shiftSummaryVisible = !shiftSummaryVisible;
    const btn = document.getElementById('toggleShiftSummary');
    const panel = document.getElementById('shiftSummaryPanel');
    
    if (shiftSummaryVisible && currentData) {
        btn.style.background = 'rgba(102, 126, 234, 0.4)';
        btn.style.borderWidth = '2px';
        window.IndustrialFeatures.renderShiftSummary(currentData, selectedTags);
        panel.style.display = 'block';
    } else {
        btn.style.background = 'rgba(102, 126, 234, 0.2)';
        btn.style.borderWidth = '1px';
        panel.style.display = 'none';
    }
}

/**
 * Toggle health score panel
 */
function toggleHealthScore() {
    healthScoreVisible = !healthScoreVisible;
    const btn = document.getElementById('toggleHealthScore');
    const panel = document.getElementById('healthScorePanel');
    
    if (healthScoreVisible && currentData) {
        btn.style.background = 'rgba(255, 149, 0, 0.4)';
        btn.style.borderWidth = '2px';
        window.IndustrialFeatures.renderHealthScores(currentData, selectedTags);
        panel.style.display = 'block';
    } else {
        btn.style.background = 'rgba(255, 149, 0, 0.2)';
        btn.style.borderWidth = '1px';
        panel.style.display = 'none';
    }
}

/**
 * Toggle data quality panel
 */
function toggleDataQuality() {
    dataQualityVisible = !dataQualityVisible;
    const btn = document.getElementById('toggleDataQuality');
    const panel = document.getElementById('dataQualityPanel');
    
    if (dataQualityVisible && currentData) {
        btn.style.background = 'rgba(138, 75, 162, 0.4)';
        btn.style.borderWidth = '2px';
        window.IndustrialFeatures.renderDataQualityIndicators(currentData, selectedTags);
        panel.style.display = 'block';
    } else {
        btn.style.background = 'rgba(138, 75, 162, 0.2)';
        btn.style.borderWidth = '1px';
        panel.style.display = 'none';
    }
}

/**
 * Load Correlation Mode - Overlay Turbine Load with any tag
 */
async function renderLoadCorrelationMode() {
    const plotDiv = document.getElementById('trendChart');
    plotDiv.innerHTML = '';
    
    // Find Turbine Load tag (search for common patterns)
    const loadTagPatterns = ['load', 'mw', 'power', 'gen'];
    let loadTag = selectedTags.find(tag => 
        loadTagPatterns.some(pattern => tag.toLowerCase().includes(pattern))
    );
    
    if (!loadTag && selectedTags.length > 0) {
        // If no load tag found, use first tag as reference
        loadTag = selectedTags[0];
    }
    
    if (!loadTag) {
        plotDiv.innerHTML = '<div style="color: #ff6b6b; padding: 20px; text-align: center;">Please select tags to view Load Correlation</div>';
        return;
    }
    
    const traces = [];
    const otherTags = selectedTags.filter(tag => tag !== loadTag);
    
    // Add load tag as primary trace on y-axis 1
    const loadData = getValidDataPoints(currentData, loadTag);
    traces.push({
        x: loadData.map(d => new Date(d.Timestamp)),
        y: loadData.map(d => d[loadTag]),
        name: `${loadTag} (Load Reference)`,
        type: 'scatter',
        mode: 'lines',
        line: { color: '#ffd700', width: 3 },
        yaxis: 'y',
        hovertemplate: `<b>${loadTag}</b><br>%{y:.2f}<br>%{x}<extra></extra>`
    });
    
    // Add other tags as overlay traces on y-axis 2
    otherTags.forEach((tag, idx) => {
        const tagData = getValidDataPoints(currentData, tag);
        traces.push({
            x: tagData.map(d => new Date(d.Timestamp)),
            y: tagData.map(d => d[tag]),
            name: tagLabel(tag),
            type: 'scatter',
            mode: 'lines',
            line: { color: tagColors[idx % tagColors.length], width: 2 },
            yaxis: 'y2',
            hovertemplate: `<b>${tagLabel(tag)}</b><br>%{y:.2f}<br>%{x}<extra></extra>`
        });
    });
    
    const layout = {
        title: {
            text: `⚡ Load Correlation Analysis<br><sub>Primary: ${loadTag} | Overlaid Parameters: ${otherTags.join(', ')}</sub>`,
            font: { color: '#ffd700', size: 16 }
        },
        plot_bgcolor: 'rgba(15, 52, 96, 0.3)',
        paper_bgcolor: 'transparent',
        xaxis: {
            title: 'Time',
            gridcolor: 'rgba(0, 212, 255, 0.1)',
            color: '#00d4ff',
            showspikes: true,
            spikemode: 'across',
            spikesnap: 'cursor'
        },
        yaxis: {
            title: `${loadTag} (Load)`,
            gridcolor: 'rgba(255, 215, 0, 0.2)',
            color: '#ffd700',
            side: 'left',
            showgrid: true
        },
        yaxis2: {
            title: 'Other Parameters',
            overlaying: 'y',
            side: 'right',
            color: '#00d4ff',
            showgrid: false
        },
        hovermode: 'x unified',
        showlegend: true,
        legend: {
            bgcolor: 'rgba(0, 0, 0, 0.7)',
            bordercolor: '#00d4ff',
            borderwidth: 1,
            font: { color: '#e0e0e0' }
        },
        height: 600,
        margin: { l: 80, r: 80, t: 100, b: 80 }
    };
    
    const config = {
        responsive: true,
        displayModeBar: true,
        toImageButtonOptions: {
            format: 'png',
            filename: `load_correlation_${new Date().toISOString().slice(0,10)}`
        }
    };
    
    await new Promise(resolve => setTimeout(resolve, 10));
    Plotly.newPlot(plotDiv, traces, layout, config);
    
    // Show correlation statistics
    const statsHtml = `
        <div style="background: rgba(255, 215, 0, 0.1); padding: 15px; border-radius: 8px; border: 1px solid rgba(255, 215, 0, 0.3); margin-top: 15px;">
            <h3 style="color: #ffd700; margin-bottom: 10px;">💡 Load Correlation Insights</h3>
            <p style="color: #e0e0e0; font-size: 13px; line-height: 1.6;">
                This view shows how process parameters correlate with ${loadTag}. 
                Parameters that track closely with load changes are load-dependent, 
                while stable parameters are load-independent. Use this to identify:
            </p>
            <ul style="color: #00d4ff; font-size: 13px; margin-left: 20px; margin-top: 10px;">
                <li>Process efficiency at different load levels</li>
                <li>Parameters affected by load changes</li>
                <li>Optimal operating points for specific loads</li>
                <li>Load-dependent vs load-independent factors</li>
            </ul>
        </div>
    `;
    
    const correlationContainer = document.getElementById('correlationChartContainer');
    correlationContainer.innerHTML = statsHtml;
    correlationContainer.style.display = 'block';
}

// =====================================================
// ML PREDICTIVE INTERPOLATION FUNCTIONS
// =====================================================

/**
 * Open ML prediction modal for selected tag
 */
function openMLPredictionModal() {
    if (selectedTags.length === 0) {
        alert('⚠️ Please select at least one tag first');
        return;
    }
    
    // For simplicity, predict for first selected tag
    // (can be enhanced to support multi-tag prediction)
    const tag = selectedTags[0];
    
    const startDate = document.getElementById('startDate').value;
    const endDate = document.getElementById('endDate').value;
    
    if (!startDate || !endDate) {
        alert('⚠️ Please select date range first');
        return;
    }
    
    // Show prediction modal
    window.PredictiveInterpolation.showModelComparisonModal(
        tag,
        new Date(startDate).toISOString(),
        new Date(endDate).toISOString()
    );
}

/**
 * Toggle view mode between raw and interpolated data
 */
function toggleViewMode() {
    const btn = document.getElementById('toggleViewMode');
    const qualityConfig = new window.DataQualityConfig();
    
    // Toggle mode
    const isInterpolated = qualityConfig.toggleViewMode();
    
    // Update button appearance
    if (isInterpolated) {
        btn.textContent = '👁️ PREDICTED DATA';
        btn.style.background = 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)';
        btn.style.border = 'none';
        btn.style.color = '#fff';
        btn.style.fontWeight = 'bold';
    } else {
        btn.textContent = '👁️ RAW DATA';
        btn.style.background = 'rgba(50, 50, 50, 0.3)';
        btn.style.border = '1px solid #888';
        btn.style.color = '#888';
        btn.style.fontWeight = 'normal';
    }
    
    // Reload data with new view mode
    loadTrendData();
}

/**
 * Show modular date range selector for Advanced BI
 */
function showBIDateRangeSelector() {
    // Get current date range from main controls
    const mainStartDate = document.getElementById('startDate').value;
    const mainEndDate = document.getElementById('endDate').value;
    
    // Create modal
    const modal = document.createElement('div');
    modal.id = 'biDateSelectorModal';
    modal.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0, 0, 0, 0.9);
        z-index: 9999;
        display: flex;
        align-items: center;
        justify-content: center;
    `;
    
    modal.innerHTML = `
        <div style="background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); border-radius: 12px; padding: 30px; border: 2px solid #00d4ff; max-width: 600px; width: 90%;">
            <h2 style="color: #00d4ff; margin-top: 0;">📅 Select Analysis Period for Advanced BI</h2>
            
            <div style="margin-bottom: 20px;">
                <label style="color: #888; font-size: 12px; display: block; margin-bottom: 5px;">Quick Select</label>
                <select id="biQuickDateSelect" style="width: 100%; background: rgba(255, 255, 255, 0.1); border: 1px solid rgba(0, 212, 255, 0.5); color: #fff; padding: 12px; border-radius: 6px; font-size: 14px;">
                    <option value="">Custom Range</option>
                    <option value="today">Today</option>
                    <option value="yesterday">Yesterday</option>
                    <option value="week">Last 7 Days</option>
                    <option value="month">Last 30 Days</option>
                    <option value="quarter">Last 90 Days</option>
                    <option value="all">All Available Data</option>
                </select>
            </div>
            
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-bottom: 20px;">
                <div>
                    <label style="color: #888; font-size: 12px; display: block; margin-bottom: 5px;">Baseline Start Date</label>
                    <input type="date" id="biStartDateInput" style="width: 100%; background: rgba(255, 255, 255, 0.1); border: 1px solid rgba(0, 212, 255, 0.5); color: #fff; padding: 12px; border-radius: 6px; font-size: 14px;" value="${mainStartDate.split('T')[0]}">
                </div>
                <div>
                    <label style="color: #888; font-size: 12px; display: block; margin-bottom: 5px;">Baseline End Date</label>
                    <input type="date" id="biEndDateInput" style="width: 100%; background: rgba(255, 255, 255, 0.1); border: 1px solid rgba(0, 212, 255, 0.5); color: #fff; padding: 12px; border-radius: 6px; font-size: 14px;" value="${mainEndDate.split('T')[0]}">
                </div>
            </div>
            
            <div style="margin-bottom: 20px;">
                <label style="color: #888; font-size: 12px; display: block; margin-bottom: 5px;">Target Production Date (to compare against baseline)</label>
                <input type="date" id="biTargetDateInput" style="width: 100%; background: rgba(255, 255, 255, 0.1); border: 1px solid rgba(0, 212, 255, 0.5); color: #fff; padding: 12px; border-radius: 6px; font-size: 14px;" value="${mainEndDate.split('T')[0]}">
                <div style="color: #666; font-size: 11px; margin-top: 5px;">Leave blank to use last date of baseline range</div>
            </div>
            
            <div style="display: flex; gap: 10px; justify-content: flex-end;">
                <button id="biDateCancel" style="background: rgba(255, 59, 48, 0.2); border: 1px solid #ff3b30; color: #ff3b30; padding: 12px 25px; border-radius: 6px; cursor: pointer;">
                    Cancel
                </button>
                <button id="biDateConfirm" style="background: linear-gradient(135deg, #00d4ff 0%, #0099cc 100%); border: none; color: #fff; padding: 12px 25px; border-radius: 6px; cursor: pointer; font-weight: bold;">
                    🚀 Run Analysis
                </button>
            </div>
        </div>
    `;
    
    document.body.appendChild(modal);
    
    // Quick date selector
    document.getElementById('biQuickDateSelect').addEventListener('change', (e) => {
        const today = new Date();
        let start, end;
        
        switch(e.target.value) {
            case 'today':
                start = end = today;
                break;
            case 'yesterday':
                start = end = new Date(today.getTime() - 24*60*60*1000);
                break;
            case 'week':
                start = new Date(today.getTime() - 7*24*60*60*1000);
                end = today;
                break;
            case 'month':
                start = new Date(today.getTime() - 30*24*60*60*1000);
                end = today;
                break;
            case 'quarter':
                start = new Date(today.getTime() - 90*24*60*60*1000);
                end = today;
                break;
            case 'all':
                // Leave empty to use all data
                document.getElementById('biStartDateInput').value = '';
                document.getElementById('biEndDateInput').value = '';
                return;
        }
        
        if (start) {
            document.getElementById('biStartDateInput').value = start.toISOString().split('T')[0];
        }
        if (end) {
            document.getElementById('biEndDateInput').value = end.toISOString().split('T')[0];
        }
    });
    
    // Cancel
    document.getElementById('biDateCancel').addEventListener('click', () => {
        modal.remove();
    });
    
    // Inline error container
    const inlineError = document.createElement('div');
    inlineError.id = 'biDateError';
    inlineError.style.cssText = 'margin-top:10px;color:#ff3b30;font-size:12px;font-weight:bold;display:none;';
    modal.querySelector('div').appendChild(inlineError);

    // Confirm and launch BI (only close modal if data valid)
    document.getElementById('biDateConfirm').addEventListener('click', async () => {
        const baselineStart = document.getElementById('biStartDateInput').value;
        const baselineEnd = document.getElementById('biEndDateInput').value;
        const targetDate = document.getElementById('biTargetDateInput').value || baselineEnd;

        console.log('📅 USER SELECTED:');
        console.log('   Baseline Range:', baselineStart, 'to', baselineEnd);
        console.log('   Target Date:', targetDate);

        inlineError.style.display = 'none';
        inlineError.textContent = '';

        const success = await launchAdvancedBIDashboard(baselineStart, baselineEnd, targetDate, { validateOnly: false });
        if (!success) {
            inlineError.textContent = '⚠ Selected baseline or target date has no data. Adjust dates.';
            inlineError.style.display = 'block';
            return; // Keep modal open
        }
        modal.remove();
    });
}

/**
 * Open Advanced BI + AI Dashboard
 */
async function openAdvancedBIDashboard() {
    if (!currentData || currentData.length === 0) {
        alert('⚠️ Please load trend data first before running BI analysis');
        return;
    }
    
    if (selectedTags.length === 0) {
        alert('⚠️ Please select at least one tag');
        return;
    }
    
    // Show date range selector first
    showBIDateRangeSelector();
}

/**
 * Launch Advanced BI Dashboard with selected dates
 */
async function launchAdvancedBIDashboard(baselineStart, baselineEnd, targetDate, options = {}) {
    console.log('🚀 LAUNCHING BI DASHBOARD');
    console.log('   Baseline Range:', baselineStart, 'to', baselineEnd);
    console.log('   Target Date:', targetDate);
    console.log('   Total currentData points:', currentData ? currentData.length : 0);
    
    if (!currentData || currentData.length === 0) {
        console.warn('⚠️ No data available for BI dashboard');
        return false;
    }
    
    // Build day-boundary Date objects to avoid UTC/date-string issues
    const baselineStartDt = new Date(`${baselineStart}T00:00:00`);
    const baselineEndDt = new Date(`${baselineEnd}T23:59:59.999`);
    const targetStartDt = new Date(`${targetDate}T00:00:00`);
    const targetEndDt = new Date(`${targetDate}T23:59:59.999`);

    // Filter baseline data (range for averaging) using actual Date comparisons
    const baselineData = currentData.filter(row => {
        const t = new Date(row.Timestamp);
        return t >= baselineStartDt && t <= baselineEndDt;
    });
    
    // Filter target date data (specific date to compare) using Date comparisons
    const targetDateData = currentData.filter(row => {
        const t = new Date(row.Timestamp);
        return t >= targetStartDt && t <= targetEndDt;
    });
    
    console.log('📊 DATA SUMMARY:');
    console.log('   Baseline Period:', baselineStart, 'to', baselineEnd, '→', baselineData.length, 'points');
    console.log('   Target Date:', targetDate, '→', targetDateData.length, 'points');
    
    // DEBUG: Check actual date range in filtered data
    if (baselineData.length > 0) {
        const baselineDates = baselineData.map(r => {
            const d = new Date(r.Timestamp);
            const mm = String(d.getMonth() + 1).padStart(2, '0');
            const dd = String(d.getDate()).padStart(2, '0');
            return `${d.getFullYear()}-${mm}-${dd}`;
        });
        const uniqueDates = [...new Set(baselineDates)].sort();
        console.log('🔍 BASELINE DATES DEBUG:');
        console.log('   Requested range:', baselineStart, 'to', baselineEnd);
        console.log('   Actual dates found:', uniqueDates.length, 'unique dates');
        console.log('   First date:', uniqueDates[0]);
        console.log('   Last date:', uniqueDates[uniqueDates.length - 1]);
        console.log('   All dates:', uniqueDates);
    }
    
    // Validate we have data
    if (!baselineData || baselineData.length === 0) {
        console.warn(`⚠️ No baseline data found for ${baselineStart} to ${baselineEnd}`);
        return false;
    }
    
    if (!targetDateData || targetDateData.length === 0) {
        console.warn(`⚠️ No target date data found for ${targetDate}`);
        return false;
    }
    
    // Auto-detect production tag (first selected tag or one with 'Load', 'MW', 'Power' in name)
    let productionTag = selectedTags[0];
    const productionKeywords = ['Load', 'MW', 'Power', 'Generation', 'Output'];
    const detectedProduction = selectedTags.find(tag => 
        productionKeywords.some(keyword => tag.includes(keyword))
    );
    if (detectedProduction) {
        productionTag = detectedProduction;
    }
    
    // All other selected tags are influencing parameters
    const influencingTags = selectedTags.filter(t => t !== productionTag);
    
    // Try to get rated capacity from baseline_config.json
    let ratedCapacity = null;
    try {
        const configResponse = await fetch('/api/baseline/config');
        if (configResponse.ok) {
            const configData = await configResponse.json();
            
            // Check if production tag exists in config
            if (configData.tags && configData.tags[productionTag]) {
                ratedCapacity = configData.tags[productionTag].rated_capacity;
                console.log(`✓ Loaded rated capacity from config: ${ratedCapacity} MW`);
            }
            
            // If not found, try global default
            if (!ratedCapacity && configData.global_settings) {
                ratedCapacity = configData.global_settings.default_rated_capacity_fallback;
                console.log(`ℹ Using global default rated capacity: ${ratedCapacity} MW`);
            }
        }
    } catch (error) {
        console.warn('⚠️ Could not load baseline config:', error);
    }
    
    // Fallback: Auto-detect from data if config not available
    if (!ratedCapacity) {
        ratedCapacity = 250; // Last resort fallback
        if (currentData.length > 0 && currentData[0][productionTag]) {
            const productionValues = currentData
                .map(d => d[productionTag])
                .filter(v => v !== null && !isNaN(v));
            if (productionValues.length > 0) {
                const maxObserved = Math.max(...productionValues);
                ratedCapacity = Math.ceil(maxObserved * 1.1); // 10% margin above max observed
                console.log(`⚠️ Auto-detected rated capacity from data: ${ratedCapacity} MW (may be inaccurate)`);
            }
        }
    }
    
    // Configuration - all from baseline_config.json or auto-detected
    const config = {
        productionTag: productionTag,
        influencingTags: influencingTags,
        ratedCapacity: ratedCapacity,
        parametersToScore: selectedTags,
        customThresholds: {},
        dateRange: {
            mode: 'range',
            baselineStart: baselineStart,
            baselineEnd: baselineEnd,
            targetDate: targetDate
        },
        baselineData: baselineData,  // Range data for averaging
        targetDateData: targetDateData  // Specific date to analyze
    };
    
    console.log('🎯 Dashboard configuration:', config);
    
    // Show dashboard with target date data (for analysis)
    await window.AdvancedBIDashboard.showDashboard(targetDateData, config, baselineStart, baselineEnd);
    return true;
}


