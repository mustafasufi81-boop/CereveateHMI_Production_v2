/**
 * HMI Dashboard JavaScript - High Performance Real-Time + Historical Trends
 * Connects to Flask-SocketIO backend (which connects to C# SignalR)
 * NO CHANGES to existing C# services required
 */

// Global state
const state = {
    socket: null,
    charts: [], // Support multiple charts
    chartMode: 'live',
    liveData: {},
    historicalData: {},
    selectedTags: [],
    updateCount: 0,
    lastUpdateTime: Date.now(),
    config: {},
    samplingConfig: null, // Sampling configuration from server
    maxDataPoints: 500, // Show 500 points in window
    isFullscreen: false,
    tagBuffer: new Map(), // Store time-series data for each tag
    isPaused: false, // Pause live chart updates (but keep data collecting in background)
    viewMode: 'live', // 'live' or 'historical'
    historicalViewEnd: null, // When viewing historical data, this is the end timestamp of view window
    
    // Performance optimization
    maxLivePoints: 500,      // Max points in live view before decimation
    maxHistoricalPoints: 5000, // Max points in historical view
    dataWindow: {
        start: null,         // Start of visible window (Date)
        end: null,           // End of visible window (Date)
        isScrolling: false   // Scroll mode active
    }
};

// SCADA-style professional colors - high contrast, easily distinguishable
const CHART_COLORS = [
    '#00D9FF',  // Cyan (primary)
    '#FF6B35',  // Orange-Red
    '#00FF88',  // Green
    '#FFD93D',  // Yellow
    '#FF006E',  // Magenta
    '#8338EC',  // Purple
    '#3A86FF',  // Blue
    '#FB5607',  // Orange
    '#06FFA5',  // Mint
    '#F72585',  // Pink
    '#4CC9F0',  // Sky Blue
    '#F77F00',  // Amber
    '#06D6A0',  // Teal
    '#FFB703',  // Gold
    '#E63946',  // Red
    '#A8DADC',  // Light Blue
    '#F4A261',  // Peach
    '#2A9D8F',  // Dark Teal
    '#E9C46A',  // Sand
    '#457B9D'   // Steel Blue
];

/**
 * Initialize dashboard on page load
 */
document.addEventListener('DOMContentLoaded', async () => {
    console.log('🚀 HMI Dashboard initializing...');
    
    // Load configuration (includes sampling config)
    await loadConfig();
    
    // Load enabled tags from database automatically
    await loadEnabledTagsFromDB();
    
    // Also immediately try to load from live API (don't wait)
    try {
        const response = await fetch('/api/tags/latest');
        if (response.ok) {
            const data = await response.json();
            // Handle both formats: direct tags object or nested in 'tags' property
            const tagsObject = data.tags || data;
            if (tagsObject && Object.keys(tagsObject).length > 0) {
                const tags = Object.keys(tagsObject).map(tagId => ({
                    tagId: tagId,
                    tagName: tagId,
                    description: 'Live tag',
                    unit: '',
                    dataType: 'double'
                }));
                console.log(`🔄 Loaded ${tags.length} tags from live API`);
                populateTagCheckboxes(tags);
            }
        }
    } catch (error) {
        console.error('Failed to load live tags:', error);
    }
    
    // Force immediate tag loading from live API as backup
    setTimeout(async () => {
        const container = document.getElementById('tag-checkboxes');
        if (container && container.children.length === 0) {
            console.log('🔄 No tags loaded, forcing immediate fetch from live API');
            try {
                const response = await fetch('/api/tags/latest');
                if (response.ok) {
                    const data = await response.json();
                    if (data && Object.keys(data).length > 0) {
                        const tags = Object.keys(data).map(tagId => ({
                            tagId: tagId,
                            tagName: tagId,
                            description: 'Live tag',
                            unit: '',
                            dataType: 'double'
                        }));
                        populateTagCheckboxes(tags);
                    }
                }
            } catch (error) {
                console.error('❌ Immediate tag fetch failed:', error);
            }
        }
    }, 1000);
    
    // Initialize WebSocket connection
    initializeWebSocket();
    
    // Initialize main chart
    initializeChart('main-chart', 0);
    
    // Setup event listeners
    setupEventListeners();
    
    // Setup resizable panel
    setupResizablePanel();
    
    // Setup fullscreen
    setupFullscreen();
    
    // Setup selection controls (Select All / Clear All)
    setupSelectionControls();
    
    // Setup time range change listener
    setupTimeRangeListener();
    
    // Load saved dashboard from localStorage
    loadDashboardFromLocal();
    
    // Start update rate counter
    startUpdateRateCounter();
    
    // Start polling for tag values if WebSocket fails
    startTagPolling();
    
    console.log('✅ HMI Dashboard initialized');
});

/**
 * Load configuration from backend
 */
async function loadConfig() {
    try {
        const response = await fetch('/api/config');
        state.config = await response.json();
        
        // Store sampling configuration
        state.samplingConfig = state.config.sampling;
        
        // Populate sampling interval selector
        if (state.samplingConfig) {
            populateSamplingSelector();
        }
        
        console.log('✅ Configuration loaded:', state.config);
        console.log('🔗 Backend URL from config:', state.config.backendUrl);
        
        // Update UI based on available connections
        if (state.config.connections) {
            updateStatusIndicator('signalr-status', state.config.connections.signalr);
            updateStatusIndicator('db-status', state.config.connections.database);
            
            // Show mode notification
            if (!state.config.connections.signalr && !state.config.connections.database) {
                showModeNotification('DEMO MODE', 'UI exploration only. No data sources connected.', 'info');
            } else if (!state.config.connections.signalr) {
                showModeNotification('HISTORICAL MODE', 'Live data unavailable. Start OpcDaWebBrowser.exe for live updates.', 'warning');
                // Auto-switch to historical mode
                const chartMode = document.getElementById('chart-mode');
                if (chartMode) {
                    chartMode.value = 'historical';
                    state.chartMode = 'historical';
                }
                const histControls = document.getElementById('historical-controls');
                if (histControls) {
                    histControls.style.display = 'flex';
                }
            } else if (!state.config.connections.database) {
                showModeNotification('LIVE MODE', 'Historical data unavailable. Check database connection.', 'warning');
            }
        }
    } catch (error) {
        console.error('❌ Failed to load config:', error);
        // Use defaults
        state.config = {
            updateInterval: 1000,
            maxPointsLive: 100,
            maxPointsHistorical: 1000,
            connections: { signalr: false, database: false }
        };
    }
}

/**
 * Initialize WebSocket connection to Flask-SocketIO (optional - graceful degradation)
 */
/**
 * Initialize WebSocket connection (DISABLED - using HTTP polling instead)
 */
function initializeWebSocket() {
    console.log('ℹ️ WebSocket/SignalR DISABLED - using HTTP polling mode for better reliability');
    updateStatusIndicator('websocket-status', false);
    updateStatusIndicator('signalr-status', false);
    
    // HTTP polling (startTagPolling) provides all data - no WebSocket needed
    // This eliminates "SignalR not connected" errors blocking JavaScript execution
}

/**
 * Handle tag updates from backend
 */
function handleTagUpdate(tagsData) {
    state.updateCount++;
    
    if (!Array.isArray(tagsData)) {
        tagsData = [tagsData];
    }
    
    // Update live data cache AND buffer
    tagsData.forEach(tag => {
        const tagId = tag.itemID || tag.ItemID || tag.tagId;
        if (!tagId) return;
        
        const value = parseFloat(tag.value || tag.Value || 0);
        const quality = tag.quality || tag.Quality || 'UNKNOWN';
        const timestamp = tag.timestamp || tag.Timestamp || new Date().toISOString();
        
        state.liveData[tagId] = {
            value: value,
            quality: quality,
            timestamp: timestamp
        };
        
        // Add to buffer for smooth 500-point chart
        addDataPointToBuffer(tagId, timestamp, value);
        
        // Feed to trend engine if initialized
        if (window.trendEngine && state.selectedTags.includes(tagId)) {
            window.trendEngine.addLivePoint(tagId, new Date(timestamp), value, quality);
        }
    });
    
    // Update UI
    updateLiveValuesTable();
    
    // Update chart if in live mode (legacy chart support)
    if (state.chartMode === 'live' || state.chartMode === 'both') {
        updateLiveChart();
    }
    
    // Update footer stats
    updateFooterStats();
}

/**
 * Update live values table
 */
function updateLiveValuesTable() {
    const tbody = document.getElementById('live-values-body');
    
    if (!tbody) return;
    
    if (Object.keys(state.liveData).length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" class="loading">Waiting for data...</td></tr>';
        return;
    }
    
    // Show only selected tags in the table
    const tagsToShow = state.selectedTags.length > 0 
        ? state.selectedTags 
        : Object.keys(state.liveData).slice(0, 10); // Show first 10 if none selected
    
    const rows = tagsToShow
        .filter(tagId => state.liveData[tagId])
        .sort((a, b) => a.localeCompare(b))
        .map(tagId => {
            const data = state.liveData[tagId];
            const qualityClass = getQualityClass(data.quality);
            const timestamp = new Date(data.timestamp).toLocaleTimeString();
            
            // Format value - handle both numbers and strings
            const displayValue = typeof data.value === 'number' 
                ? data.value.toFixed(2) 
                : String(data.value);
            
            return `
                <tr>
                    <td><strong>${tagId}</strong></td>
                    <td style="font-family: monospace; font-size: 14px; font-weight: bold; color: #00FF88;">${displayValue}</td>
                    <td class="${qualityClass}">${data.quality}</td>
                    <td style="font-size: 11px;">${timestamp}</td>
                </tr>
            `;
        })
        .join('');
    
    tbody.innerHTML = rows || '<tr><td colspan="4" class="loading">No data available</td></tr>';
}

/**
 * Get CSS class for quality indicator
 */
function getQualityClass(quality) {
    const q = quality.toUpperCase();
    if (q.includes('GOOD')) return 'quality-good';
    if (q.includes('BAD')) return 'quality-bad';
    return 'quality-uncertain';
}

/**
 * Toggle tag in chart
 */
function toggleTagChart(tagId) {
    const index = state.selectedTags.indexOf(tagId);
    
    if (index > -1) {
        // Remove tag
        state.selectedTags.splice(index, 1);
    } else {
        // Add tag (limit to 10 for performance)
        if (state.selectedTags.length >= 10) {
            alert('Maximum 10 tags can be charted simultaneously');
            return;
        }
        state.selectedTags.push(tagId);
    }
    
    // Update chart
    updateChart();
    updateLiveValuesTable();
    updateTagSelector();
    
    // Subscribe to tags via WebSocket
    if (state.socket && state.socket.connected) {
        state.socket.emit('subscribe_tags', { tagIds: state.selectedTags });
    }
}

/**
 * Update tag selector display
 */
function updateTagSelector() {
    const selector = document.getElementById('tag-selector');
    
    // Skip if element doesn't exist in the page
    if (!selector) return;
    
    if (state.selectedTags.length === 0) {
        selector.innerHTML = '<span style="color: #7f8c8d;">No tags selected</span>';
        return;
    }
    
    selector.innerHTML = state.selectedTags
        .map(tag => `<span class="tag-badge">${tag}</span>`)
        .join(' ');
}

/**
 * Initialize Chart.js chart with SCADA styling
 */
function initializeChart(canvasId, chartIndex) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) {
        console.warn(`⚠️ Chart canvas ${canvasId} not found`);
        return;
    }
    
    // Destroy existing chart at this index
    if (state.charts[chartIndex]) {
        console.log(`🗑️ Destroying existing chart ${chartIndex}`);
        state.charts[chartIndex].destroy();
    }
    
    const ctx = canvas.getContext('2d');
    
    state.charts[chartIndex] = new Chart(ctx, {
        type: 'line',
        data: {
            datasets: []
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: {
                duration: 300,  // Smooth updates
                easing: 'linear'
            },
            interaction: {
                mode: 'index',
                intersect: false
            },
            elements: {
                line: {
                    tension: 0.4,  // SCADA smooth curves
                    borderWidth: 2.5,  // Professional line thickness
                    borderJoinStyle: 'round'
                },
                point: {
                    radius: 0,  // NO POINTS - clean SCADA look
                    hitRadius: 10,  // Still clickable
                    hoverRadius: 5,  // Show on hover
                    hoverBorderWidth: 2
                }
            },
            scales: {
                x: {
                    type: 'time',
                    time: {
                        displayFormats: {
                            millisecond: 'HH:mm:ss.SSS',
                            second: 'HH:mm:ss',
                            minute: 'HH:mm',
                            hour: 'HH:mm',
                            day: 'MMM dd',
                            week: 'MMM dd',
                            month: 'MMM yyyy',      // ✅ Show month with year
                            quarter: 'MMM yyyy',    // ✅ Show quarter with year
                            year: 'yyyy'
                        },
                        tooltipFormat: 'MMM dd yyyy, HH:mm:ss'  // ✅ Full date in tooltips
                    },
                    ticks: { 
                        color: '#B0B0B0',
                        font: { size: 11, family: 'Consolas, monospace' },
                        maxRotation: 45,
                        minRotation: 0,
                        autoSkip: true,
                        autoSkipPadding: 20,
                        maxTicksLimit: 15
                    },
                    grid: { 
                        color: 'rgba(255, 255, 255, 0.05)',  // Subtle grid
                        lineWidth: 1
                    },
                    border: { color: '#404040' }
                },
                y: {
                    ticks: { 
                        color: '#B0B0B0',
                        font: { size: 11, family: 'Consolas, monospace' },
                        callback: function(value) {
                            // Format large numbers with K/M suffix
                            if (Math.abs(value) >= 1000000) {
                                return (value / 1000000).toFixed(1) + 'M';
                            } else if (Math.abs(value) >= 1000) {
                                return (value / 1000).toFixed(1) + 'K';
                            }
                            return value.toFixed(2);
                        }
                    },
                    grid: { 
                        color: 'rgba(255, 255, 255, 0.05)',  // Subtle grid
                        lineWidth: 1
                    },
                    border: { color: '#404040' }
                }
            },
            plugins: {
                legend: {
                    display: true,
                    position: 'top',
                    labels: { 
                        color: '#E0E0E0',
                        font: { size: 11, family: 'Arial, sans-serif', weight: '500' },
                        padding: 15,
                        usePointStyle: true,  // Clean legend markers
                        pointStyle: 'line',
                        boxWidth: 40,
                        boxHeight: 3
                    }
                },
                tooltip: {
                    enabled: true,
                    mode: 'index',
                    intersect: false,
                    backgroundColor: 'rgba(20, 20, 20, 0.95)',
                    titleColor: '#00D9FF',
                    bodyColor: '#E0E0E0',
                    borderColor: '#404040',
                    borderWidth: 1,
                    padding: 12,
                    displayColors: true,
                    callbacks: {
                        label: function(context) {
                            let label = context.dataset.label || '';
                            if (label) {
                                label += ': ';
                            }
                            label += context.parsed.y.toFixed(2);
                            return label;
                        }
                    }
                },
                zoom: {
                    pan: {
                        enabled: true,
                        mode: 'xy',
                        threshold: 10,
                        onPanComplete: function({chart}) {
                            updateZoomInfo(chart);
                        }
                    },
                    zoom: {
                        wheel: {
                            enabled: true,
                            speed: 0.1,
                            modifierKey: null  // No modifier key needed
                        },
                        drag: {
                            enabled: true,
                            backgroundColor: 'rgba(0, 217, 255, 0.3)',  // Brighter selection box
                            borderColor: 'rgba(0, 217, 255, 1.0)',      // Bright cyan border
                            borderWidth: 3,                              // Thicker border for visibility
                            threshold: 5                                 // Minimum drag distance (pixels)
                        },
                        pinch: {
                            enabled: true
                        },
                        mode: 'xy',
                        onZoomComplete: function({chart}) {
                            updateZoomInfo(chart);
                            // Check if we need more detailed data
                            checkAndReloadForZoom(chart);
                        },
                        onZoomRejected: function({chart}) {
                            console.log('Zoom rejected - limits reached');
                        }
                    },
                    limits: {
                        x: {min: 'original', max: 'original'},
                        y: {min: 'original', max: 'original'}
                    }
                }
            }
        }
    });
    
    console.log(`✅ Chart ${chartIndex} initialized (${canvasId})`);
}

/**
 * Update all charts with current data
 */
function updateChart(chartIndex = 0) {
    const chart = state.charts[chartIndex];
    if (!chart) return;
    
    // Clear existing datasets
    chart.data.datasets = [];
    
    // Add dataset for each selected tag
    state.selectedTags.forEach((tagId, index) => {
        const color = CHART_COLORS[index % CHART_COLORS.length];
        
        // Get all data from buffer
        const buffer = state.tagBuffer.get(tagId) || [];
        
        if (buffer.length === 0) return;  // Skip if no data
        
        let displayData = buffer;
        
        // PERFORMANCE: Apply data windowing if scrolling
        if (state.dataWindow.isScrolling && state.dataWindow.start && state.dataWindow.end) {
            displayData = buffer.filter(point => 
                point.x >= state.dataWindow.start && point.x <= state.dataWindow.end
            );
        }
        
        // PERFORMANCE: Decimate if too many points
        // Use higher point limit for historical mode
        const isHistorical = state.isPaused || state.viewMode === 'historical';
        const maxPoints = isHistorical ? state.maxHistoricalPoints : state.maxLivePoints;
        if (displayData.length > maxPoints) {
            displayData = decimateData(displayData, maxPoints);
            console.log(`📉 Decimated ${buffer.length} → ${displayData.length} points for ${tagId}`);
        }
        
        // Live mode: show last N points (only when NOT in historical mode)
        if (!isHistorical && !state.dataWindow.isScrolling) {
            displayData = displayData.slice(-state.maxLivePoints);
        }
        
        chart.data.datasets.push({
            label: tagId,
            data: displayData,
            borderColor: color,
            backgroundColor: 'transparent',
            borderWidth: 2.5,
            pointRadius: 0,
            pointHoverRadius: 5,
            tension: 0.4,
            fill: false,
            spanGaps: true  // Prevent extra lines from gaps in data
        });
    });
    
    // Auto-scale Y-axis based on visible data
    autoScaleYAxis(chart);
    
    chart.update('none');  // Update without animation
    updateChartStats();
}

/**
 * Decimate data using LTTB (Largest Triangle Three Buckets) algorithm
 * Pure JavaScript implementation - NO external dependencies
 */
function decimateData(data, targetPoints) {
    if (data.length <= targetPoints) return data;
    if (targetPoints < 3) return data.slice(0, targetPoints);
    
    const result = [];
    const bucketSize = (data.length - 2) / (targetPoints - 2);
    
    // Always keep first point
    result.push(data[0]);
    
    let a = 0;  // Previous selected point
    
    for (let i = 0; i < targetPoints - 2; i++) {
        // Calculate average point in next bucket for comparison
        const avgRangeStart = Math.floor((i + 1) * bucketSize) + 1;
        const avgRangeEnd = Math.min(Math.floor((i + 2) * bucketSize) + 1, data.length);
        
        let avgX = 0, avgY = 0;
        let avgCount = 0;
        
        for (let j = avgRangeStart; j < avgRangeEnd; j++) {
            avgX += data[j].x.getTime();
            avgY += data[j].y;
            avgCount++;
        }
        
        if (avgCount > 0) {
            avgX /= avgCount;
            avgY /= avgCount;
        }
        
        // Find point in current bucket with largest triangle area
        const rangeStart = Math.floor(i * bucketSize) + 1;
        const rangeEnd = Math.floor((i + 1) * bucketSize) + 1;
        
        let maxArea = -1;
        let maxAreaIndex = rangeStart;
        
        const pointAX = data[a].x.getTime();
        const pointAY = data[a].y;
        
        for (let j = rangeStart; j < rangeEnd; j++) {
            if (j >= data.length) break;
            
            const pointBX = data[j].x.getTime();
            const pointBY = data[j].y;
            
            // Calculate triangle area
            const area = Math.abs(
                (pointAX - avgX) * (pointBY - pointAY) - 
                (pointAX - pointBX) * (avgY - pointAY)
            ) / 2;
            
            if (area > maxArea) {
                maxArea = area;
                maxAreaIndex = j;
            }
        }
        
        result.push(data[maxAreaIndex]);
        a = maxAreaIndex;
    }
    
    // Always keep last point
    result.push(data[data.length - 1]);
    
    return result;
}

/**
 * Get buffered data points for a tag (last 500 points)
 */
function getBufferedDataPoints(tagId) {
    const buffer = state.tagBuffer.get(tagId);
    if (!buffer || buffer.length === 0) return [];
    
    // Return last 500 points for smooth scrolling window
    return buffer.slice(-state.maxDataPoints);
}

/**
 * Add data point to tag buffer - ONLY REAL DATA, NO GAP FILLING
 */
function addDataPointToBuffer(tagId, timestamp, value) {
    if (!state.tagBuffer.has(tagId)) {
        state.tagBuffer.set(tagId, []);
    }
    
    const buffer = state.tagBuffer.get(tagId);
    buffer.push({
        x: new Date(timestamp),
        y: parseFloat(value)
    });
    
    // Keep buffer size manageable (max 1000 points, show 500)
    if (buffer.length > 1000) {
        buffer.shift();
    }
}

/**
 * Auto-scale Y-axis based on currently visible data in selected tags
 */
function autoScaleYAxis(chart) {
    if (!chart || chart.data.datasets.length === 0) return;
    
    let minValue = Infinity;
    let maxValue = -Infinity;
    
    // Find min/max from all visible datasets
    chart.data.datasets.forEach(dataset => {
        if (dataset.data && dataset.data.length > 0) {
            dataset.data.forEach(point => {
                const value = point.y;
                if (!isNaN(value) && isFinite(value)) {
                    minValue = Math.min(minValue, value);
                    maxValue = Math.max(maxValue, value);
                }
            });
        }
    });
    
    // Add 10% padding for better visualization
    if (isFinite(minValue) && isFinite(maxValue)) {
        const range = maxValue - minValue;
        const padding = range * 0.1;
        
        chart.options.scales.y.min = minValue - padding;
        chart.options.scales.y.max = maxValue + padding;
    } else {
        // Reset to auto if no valid data
        chart.options.scales.y.min = undefined;
        chart.options.scales.y.max = undefined;
    }
}

/**
 * Clear historical data and return to live mode
 */
function clearHistoricalData() {
    console.log('🗑️ Clearing historical data...');
    
    // Keep only last 100 points (live data) for each tag
    state.tagBuffer.forEach((buffer, tagId) => {
        if (buffer.length > 100) {
            const livePoints = buffer.slice(-100);
            state.tagBuffer.set(tagId, livePoints);
        }
    });
    
    // Return to live mode
    state.isPaused = false;
    state.viewMode = 'live';
    state.historicalData = {};
    
    // Reset data window (exit scroll mode)
    state.dataWindow.start = null;
    state.dataWindow.end = null;
    state.dataWindow.isScrolling = false;
    
    // Update UI
    const pauseBtn = document.getElementById('btn-pause');
    if (pauseBtn) {
        pauseBtn.textContent = '⏸️ Pause';
    }
    
    // Update live mode button
    const liveBtn = document.getElementById('btn-live');
    if (liveBtn) {
        liveBtn.classList.add('active');
    }
    
    // ✅ FIX: Properly reset chart time axis to live mode configuration
    state.charts.forEach(chart => {
        if (!chart || !chart.options.scales.x) return;
        
        // Reset to live mode time settings (1 hour default)
        chart.options.scales.x.time.unit = 'minute';  // Live mode default
        chart.options.scales.x.ticks.stepSize = 5;  // 5-minute intervals
        chart.options.scales.x.ticks.maxTicksLimit = 12;
        chart.options.scales.x.ticks.maxRotation = 45;
        chart.options.scales.x.ticks.minRotation = 0;
        chart.options.scales.x.ticks.autoSkip = true;
        chart.options.scales.x.ticks.autoSkipPadding = 20;
        
        // Reset zoom limits to allow panning/zooming again
        if (chart.options.plugins && chart.options.plugins.zoom) {
            chart.resetZoom();
        }
        
        // Force chart update to apply new settings
        chart.update('none');
    });
    
    // Update time range display
    const timeDisplay = document.getElementById('time-range-display');
    if (timeDisplay) {
        timeDisplay.textContent = 'LIVE MODE';
    }
    
    // ✅ FIX: Restart live updates if they were stopped
    if (!state.pollingInterval) {
        console.log('✅ Restarting live data polling...');
        startTagPolling();
    }
    
    // Update charts
    updateChart();
    
    // Update scroll controls
    updateScrollControls();
    
    console.log('✅ Historical data cleared, returned to live mode');
}

/**
 * Reset everything - clear all selected tags, history, and return to clean state
 */
function resetAll() {
    console.log('🔄 RESET ALL: Clearing everything...');
    
    // 1. Clear all selected tags
    state.selectedTags = [];
    
    // 2. Clear all buffers
    state.tagBuffer.clear();
    
    // 3. Clear historical data
    state.historicalData = {};
    
    // 4. Clear live data
    state.liveData = {};
    
    // 5. Return to live mode
    state.isPaused = false;
    state.viewMode = 'live';
    
    // 6. Reset data window
    state.dataWindow.start = null;
    state.dataWindow.end = null;
    state.dataWindow.isScrolling = false;
    
    // 6. Uncheck all tag checkboxes
    const checkboxes = document.querySelectorAll('#tag-list input[type="checkbox"]');
    checkboxes.forEach(cb => cb.checked = false);
    
    // 7. Clear selected tags display
    const selector = document.getElementById('selected-tags');
    if (selector) {
        selector.innerHTML = '<span style="color: #7f8c8d;">No tags selected</span>';
    }
    
    // 8. Update pause button
    const pauseBtn = document.getElementById('btn-pause');
    if (pauseBtn) {
        pauseBtn.textContent = '⏸️ Pause';
    }
    
    // 9. Reset chart time axis
    state.charts.forEach(chart => {
        if (chart && chart.options.scales.x.time) {
            chart.options.scales.x.time.unit = undefined;
            chart.options.scales.x.ticks.stepSize = undefined;
        }
    });
    
    // 10. Update charts (will show empty)
    updateChart();
    
    console.log('✅ RESET COMPLETE: All tags cleared, returned to clean state');
}

/**
 * Scroll data window backward in time
 */
function scrollBackward() {
    const chart = state.charts[0];
    if (!chart || state.selectedTags.length === 0) return;
    
    // Get current time range from chart
    const scales = chart.scales;
    const currentMin = scales.x.min || Date.now() - 3600000;
    const currentMax = scales.x.max || Date.now();
    const range = currentMax - currentMin;
    
    // Shift window backward by 50% of visible range
    const shift = range * 0.5;
    
    state.dataWindow.start = new Date(currentMin - shift);
    state.dataWindow.end = new Date(currentMax - shift);
    state.dataWindow.isScrolling = true;
    
    console.log(`⬅️ Scroll back: ${state.dataWindow.start.toLocaleString()} - ${state.dataWindow.end.toLocaleString()}`);
    
    updateChart();
    updateScrollControls();
}

/**
 * Scroll data window forward in time
 */
function scrollForward() {
    const chart = state.charts[0];
    if (!chart || state.selectedTags.length === 0) return;
    
    // Get current time range
    const scales = chart.scales;
    const currentMin = scales.x.min || Date.now() - 3600000;
    const currentMax = scales.x.max || Date.now();
    const range = currentMax - currentMin;
    
    // Shift window forward by 50% of visible range
    const shift = range * 0.5;
    
    const newStart = new Date(currentMin + shift);
    const newEnd = new Date(currentMax + shift);
    const now = new Date();
    
    // Don't scroll beyond current time
    if (newEnd > now) {
        state.dataWindow.start = null;
        state.dataWindow.end = null;
        state.dataWindow.isScrolling = false;
        console.log('➡️ Reached live data - exiting scroll mode');
    } else {
        state.dataWindow.start = newStart;
        state.dataWindow.end = newEnd;
        state.dataWindow.isScrolling = true;
        console.log(`➡️ Scroll forward: ${state.dataWindow.start.toLocaleString()} - ${state.dataWindow.end.toLocaleString()}`);
    }
    
    updateChart();
    updateScrollControls();
}

/**
 * Jump to live data (exit scroll mode)
 */
function scrollToLive() {
    state.dataWindow.start = null;
    state.dataWindow.end = null;
    state.dataWindow.isScrolling = false;
    state.isPaused = false;
    
    console.log('⏩ Jump to live data');
    
    updateChart();
    updateLiveModeButton();
    updateScrollControls();
}

/**
 * Update scroll control button states
 */
function updateScrollControls() {
    const backBtn = document.getElementById('scroll-back-btn');
    const fwdBtn = document.getElementById('scroll-forward-btn');
    const liveBtn = document.getElementById('scroll-live-btn');
    
    if (!backBtn || !fwdBtn || !liveBtn) return;
    
    const isScrolling = state.dataWindow.isScrolling;
    
    // Enable/disable buttons
    backBtn.disabled = state.selectedTags.length === 0;
    fwdBtn.disabled = state.selectedTags.length === 0;
    liveBtn.disabled = !isScrolling;
    
    // Visual feedback
    if (isScrolling) {
        liveBtn.style.opacity = '1';
        liveBtn.style.animation = 'pulse 2s infinite';
    } else {
        liveBtn.style.opacity = '0.5';
        liveBtn.style.animation = 'none';
    }
}

/**
 * Update live mode button visual state
 */
function updateLiveModeButton() {
    const liveBtn = document.getElementById('btn-live');
    const pauseBtn = document.getElementById('btn-pause');
    
    if (liveBtn) {
        if (state.isPaused) {
            liveBtn.classList.remove('active');
        } else {
            liveBtn.classList.add('active');
        }
    }
    
    if (pauseBtn) {
        pauseBtn.textContent = state.isPaused ? '▶️ Resume' : '⏸️ Pause';
    }
}

/**
 * Update live chart (called on each tag update)
 */
function updateLiveChart() {
    if (state.charts.length === 0 || state.selectedTags.length === 0) return;
    
    // Update all charts
    state.charts.forEach((chart, chartIndex) => {
        if (!chart) return;
        updateChart(chartIndex);
    });
}

/**
 * Determine optimal time unit for Chart.js X-axis based on time range
 * @param {number} hours - Time range in hours
 * @returns {string} - Chart.js time unit ('minute', 'hour', 'day', 'week', 'month')
 */
function getOptimalTimeUnit(hours) {
    if (hours <= 1) return 'minute';        // 1 hour: show minutes
    if (hours <= 24) return 'hour';         // 1 day: show hours
    if (hours <= 168) return 'day';         // 1 week: show days
    if (hours <= 720) return 'day';         // 1 month: show days
    if (hours <= 2160) return 'week';       // 3 months: show weeks
    if (hours <= 4320) return 'month';      // 6 months: show months
    return 'month';                          // 1 year: show months
}

/**
 * Update chart X-axis time configuration based on loaded data range
 * @param {number} hours - Time range in hours
 */
function updateChartTimeAxis(hours) {
    const timeUnit = getOptimalTimeUnit(hours);
    
    state.charts.forEach(chart => {
        if (!chart) return;
        
        // Update the time unit dynamically
        chart.options.scales.x.time.unit = timeUnit;
        
        // Update step size for better spacing based on time range
        if (hours <= 1) {
            chart.options.scales.x.ticks.stepSize = 5;  // 5-minute intervals
            chart.options.scales.x.ticks.maxTicksLimit = 12;
        } else if (hours <= 24) {
            chart.options.scales.x.ticks.stepSize = 2;  // 2-hour intervals
            chart.options.scales.x.ticks.maxTicksLimit = 15;
        } else if (hours <= 168) {
            chart.options.scales.x.ticks.stepSize = 1;  // 1-day intervals
            chart.options.scales.x.ticks.maxTicksLimit = 10;
        } else if (hours <= 720) {
            chart.options.scales.x.ticks.stepSize = 3;  // 3-day intervals
            chart.options.scales.x.ticks.maxTicksLimit = 12;
        } else if (hours <= 2160) {
            // 3 months - show weeks
            chart.options.scales.x.ticks.stepSize = 7;  // 1-week intervals
            chart.options.scales.x.ticks.maxTicksLimit = 15;
        } else {
            // 1 year - show months
            chart.options.scales.x.ticks.stepSize = undefined;  // Auto
            chart.options.scales.x.ticks.maxTicksLimit = 12;
        }
        
        // Ensure X-axis labels are visible and properly rotated
        chart.options.scales.x.ticks.maxRotation = 45;
        chart.options.scales.x.ticks.minRotation = 0;
        chart.options.scales.x.ticks.autoSkip = true;
        chart.options.scales.x.ticks.autoSkipPadding = 20;
        
        // Reset zoom limits to show all data
        if (chart.options.plugins && chart.options.plugins.zoom && chart.options.plugins.zoom.limits) {
            chart.options.plugins.zoom.limits.x = {
                min: 'original',
                max: 'original'
            };
            chart.options.plugins.zoom.limits.y = {
                min: 'original',
                max: 'original'
            };
        }
        
        chart.update('none');  // Update without animation
    });
    
    console.log(`📅 X-axis updated: ${hours}h range → ${timeUnit} unit`);
}

/**
 * Load historical data from PostgreSQL via Python backend
 * PERFORMANCE: Python queries TimescaleDB with intelligent downsampling
 */
async function loadHistoricalData() {
    if (state.selectedTags.length === 0) {
        alert('⚠️ Please select tags first (check 1-5 tag boxes on the left)');
        return;
    }
    
    const timeRangeEl = document.getElementById('historical-range');
    const samplingEl = document.getElementById('sampling-interval-select');
    const hours = timeRangeEl ? parseInt(timeRangeEl.value) : 1;
    const samplingInterval = samplingEl ? parseInt(samplingEl.value) : 30;
    
    // Calculate max points based on sampling interval
    const maxPoints = calculateMaxPoints(hours, samplingInterval);
    
    console.log(`📊 Loading ${hours}h data: ${samplingInterval}s interval (~${maxPoints} points)...`);
    
    try {
        // Show loading indicator with sampling info
        const loadBtn = document.getElementById('load-historical');
        if (loadBtn) {
            loadBtn.disabled = true;
            loadBtn.textContent = `⏳ Loading (${samplingInterval}s)...`;
        }
        
        // Call OPTIMIZED Python backend (single query, intelligent downsampling)
        const response = await fetch('/api/historical/multiple', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                tagIds: state.selectedTags,
                hours: hours,
                maxPoints: maxPoints,
                samplingInterval: samplingInterval  // ✅ NEW: Send explicit sampling interval
            })
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const result = await response.json();
        
        // Log the raw response for debugging
        console.log(`📊 API Response:`, result);
        
        // IMPORTANT: Clear existing buffers BEFORE loading historical data
        // This ensures we show ONLY historical data without mixing old live data
        state.selectedTags.forEach(tagId => {
            state.tagBuffer.set(tagId, []);
        });
        
        // Load historical data into buffers
        let totalPoints = 0;
        if (result.trends) {
            Object.entries(result.trends).forEach(([tagId, dataPoints]) => {
                if (!state.tagBuffer.has(tagId)) {
                    state.tagBuffer.set(tagId, []);
                }
                
                const buffer = state.tagBuffer.get(tagId);
                if (dataPoints && Array.isArray(dataPoints)) {
                    dataPoints.forEach(point => {
                        if (point.value !== null && point.value !== undefined) {
                            buffer.push({
                                x: new Date(point.timestamp),
                                y: parseFloat(point.value)
                            });
                        }
                    });
                    totalPoints += dataPoints.length;
                } else {
                    console.warn(`⚠️ No data points for tag ${tagId}:`, dataPoints);
                }
            });
        } else {
            console.error('❌ No trends in response:', result);
        }
        
        console.log(`✅ Loaded ${totalPoints} historical points (${result.startTime} to ${result.endTime})`);
        
        // DON'T pause - let live data continue updating
        // User can manually pause if they want
        state.viewMode = 'historical';
        
        // Update chart X-axis time unit based on time range
        updateChartTimeAxis(hours);
        
        // Update chart with historical data
        updateChart();
        
        // Success feedback
        if (loadBtn) {
            loadBtn.textContent = `✅ Loaded ${totalPoints} pts`;
            setTimeout(() => {
                loadBtn.disabled = false;
                loadBtn.textContent = '📜 Load Historical';
            }, 2000);
        }
        
    } catch (error) {
        console.error('❌ Failed to load historical data:', error);
        
        const loadBtn = document.getElementById('load-historical');
        if (loadBtn) {
            loadBtn.disabled = false;
            loadBtn.textContent = '❌ Load Failed';
            setTimeout(() => {
                loadBtn.textContent = '📜 Load Historical';
            }, 3000);
        }
        
        alert(`Failed to load historical data:\n${error.message}\n\nCheck:\n1. Database connection\n2. historian_raw.historian_timeseries table has data\n3. Python backend console for errors`);
    }
}

/**
 * Update chart statistics display
 */
function updateChartStats() {
    const statsDiv = document.getElementById('chart-stats');
    
    if (!statsDiv) return;
    
    // Get chart to check time range
    const chart = state.charts[0];
    if (!chart) return;
    
    let statsHTML = '';
    
    // Show time range if viewing historical data
    if (state.viewMode === 'historical' && state.tagBuffer.size > 0) {
        // Get min/max timestamps from all buffered data
        let minTime = Infinity;
        let maxTime = -Infinity;
        let totalPoints = 0;
        
        state.tagBuffer.forEach((buffer, tagId) => {
            if (buffer.length > 0) {
                const firstTime = buffer[0].x.getTime();
                const lastTime = buffer[buffer.length - 1].x.getTime();
                minTime = Math.min(minTime, firstTime);
                maxTime = Math.max(maxTime, lastTime);
                totalPoints += buffer.length;
            }
        });
        
        if (minTime !== Infinity && maxTime !== -Infinity) {
            const start = new Date(minTime);
            const end = new Date(maxTime);
            const rangeMs = maxTime - minTime;
            const rangeHours = rangeMs / (1000 * 3600);
            
            let timeRangeText = '';
            if (rangeHours < 1) {
                timeRangeText = `${Math.round(rangeHours * 60)} minutes`;
            } else if (rangeHours < 24) {
                timeRangeText = `${rangeHours.toFixed(1)} hours`;
            } else {
                timeRangeText = `${(rangeHours / 24).toFixed(1)} days`;
            }
            
            const avgInterval = totalPoints > 1 ? (rangeMs / (totalPoints / state.selectedTags.length)) / 1000 : 0;
            
            statsHTML = `
                <span style="color: #00D9FF;">📅 ${start.toLocaleDateString()} ${start.toLocaleTimeString()} → ${end.toLocaleDateString()} ${end.toLocaleTimeString()}</span>
                <span>📊 Range: ${timeRangeText}</span>
                <span>📈 Points: ${totalPoints}</span>
                <span>⏱️ Avg: ${avgInterval.toFixed(1)}s interval</span>
                <span style="color: #FFD93D;">💡 Scroll wheel to zoom, drag to pan</span>
            `;
        }
    } else if (state.selectedTags.length > 0) {
        const stats = state.selectedTags.map(tagId => {
            const latest = state.liveData[tagId];
            if (!latest) return '';
            
            return `
                <span>
                    <strong>${tagId}:</strong> 
                    ${latest.value.toFixed(2)} 
                    <small>(${latest.quality})</small>
                </span>
            `;
        }).join('');
        
        statsHTML = stats || '<span>Waiting for live data...</span>';
    } else {
        statsHTML = '<span>No tags selected</span>';
    }
    
    statsDiv.innerHTML = statsHTML;
}

/**
 * Update status indicator
 */
function updateStatusIndicator(elementId, isOnline, status = null) {
    const element = document.getElementById(elementId);
    if (!element) return;
    
    element.classList.remove('online', 'offline');
    
    if (status === 'loading') {
        element.textContent = element.textContent.split(' ')[0] + ' (Loading...)';
        return;
    }
    
    element.classList.add(isOnline ? 'online' : 'offline');
}

/**
 * Update footer statistics
 */
function updateFooterStats() {
    const clientCount = document.getElementById('client-count');
    if (clientCount) {
        clientCount.textContent = '1'; // Single client for now
    }
    
    const totalPoints = state.chart ? 
        state.chart.data.datasets.reduce((sum, ds) => sum + ds.data.length, 0) : 0;
    const dataPoints = document.getElementById('data-points');
    if (dataPoints) {
        dataPoints.textContent = totalPoints;
    }
}

/**
 * Start update rate counter
 */
function startUpdateRateCounter() {
    setInterval(() => {
        const now = Date.now();
        const elapsed = (now - state.lastUpdateTime) / 1000;
        const rate = state.updateCount / elapsed;
        
        const updateRate = document.getElementById('update-rate');
        if (updateRate) {
            updateRate.textContent = rate.toFixed(1);
        }
        
        // Reset counter
        state.updateCount = 0;
        state.lastUpdateTime = now;
    }, 5000); // Update every 5 seconds
}

/**
 * Setup event listeners
 */
function setupEventListeners() {
    // Chart mode selector
    const chartModeEl = document.getElementById('chart-mode');
    if (chartModeEl) {
        chartModeEl.addEventListener('change', (e) => {
            state.chartMode = e.target.value;
            
            const histControls = document.getElementById('historical-controls');
            if (histControls) {
                histControls.style.display = 
                    (state.chartMode === 'historical' || state.chartMode === 'both') ? 'flex' : 'none';
            }
            
            updateChart();
        });
    }
    
    // Load historical button
    const loadHistBtn = document.getElementById('load-historical');
    if (loadHistBtn) {
        loadHistBtn.addEventListener('click', loadHistoricalData);
    }
    
    // Pause/Resume button
    const pauseBtn = document.getElementById('btn-pause');
    if (pauseBtn) {
        pauseBtn.addEventListener('click', () => {
            state.isPaused = !state.isPaused;
            
            if (state.isPaused) {
                // Paused - freeze current view
                pauseBtn.textContent = '▶️ Resume Live';
                state.viewMode = 'historical';
            } else {
                // Resume - return to live mode
                pauseBtn.textContent = '⏸️ Pause';
                state.viewMode = 'live';
                updateChart();
            }
        });
    }
    
    // Live button - jump back to live data
    const liveBtn = document.getElementById('btn-live');
    if (liveBtn) {
        liveBtn.addEventListener('click', () => {
            state.isPaused = false;
            state.viewMode = 'live';
            
            const pauseBtn = document.getElementById('btn-pause');
            if (pauseBtn) {
                pauseBtn.textContent = '⏸️ Pause';
            }
            
            updateChart();
            console.log('⚡ Jumped to LIVE view');
        });
    }
    
    // Clear Historical button
    const clearHistBtn = document.getElementById('clear-historical');
    if (clearHistBtn) {
        clearHistBtn.addEventListener('click', () => {
            if (confirm('Clear all historical data and return to live mode?')) {
                clearHistoricalData();
            }
        });
    }
    
    // Reset All button
    const resetAllBtn = document.getElementById('reset-all');
    if (resetAllBtn) {
        resetAllBtn.addEventListener('click', () => {
            if (confirm('RESET ALL: Clear all selected tags, history, and return to clean state?')) {
                resetAll();
            }
        });
    }
    
    // Quick time range buttons
    const btn1h = document.getElementById('btn-back-1h');
    if (btn1h) {
        btn1h.addEventListener('click', () => loadHistoricalDataQuick(1));
    }
    
    const btn6h = document.getElementById('btn-back-6h');
    if (btn6h) {
        btn6h.addEventListener('click', () => loadHistoricalDataQuick(6));
    }
    
    const btn24h = document.getElementById('btn-back-24h');
    if (btn24h) {
        btn24h.addEventListener('click', () => loadHistoricalDataQuick(24));
    }
    
    // New quick range buttons
    const btn1week = document.getElementById('btn-back-1week');
    if (btn1week) {
        btn1week.addEventListener('click', () => loadHistoricalDataQuick(168)); // 7 days
    }
    
    const btn1month = document.getElementById('btn-back-1month');
    if (btn1month) {
        btn1month.addEventListener('click', () => loadHistoricalDataQuick(720)); // 30 days
    }
    
    const btn3months = document.getElementById('btn-back-3months');
    if (btn3months) {
        btn3months.addEventListener('click', () => loadHistoricalDataQuick(2160)); // 90 days
    }
    
    const btn1year = document.getElementById('btn-back-1year');
    if (btn1year) {
        btn1year.addEventListener('click', () => loadHistoricalDataQuick(8760)); // 365 days
    }
    
    const btnFwd1h = document.getElementById('btn-forward-1h');
    if (btnFwd1h) {
        btnFwd1h.addEventListener('click', () => loadHistoricalDataQuick(1));
    }
    
    const btnFwd6h = document.getElementById('btn-forward-6h');
    if (btnFwd6h) {
        btnFwd6h.addEventListener('click', () => loadHistoricalDataQuick(6));
    }
    
    // Dashboard management
    const saveDashBtn = document.getElementById('save-dashboard');
    if (saveDashBtn) {
        saveDashBtn.addEventListener('click', saveDashboardToLocal);
    }
    const loadDashBtn = document.getElementById('load-dashboard');
    if (loadDashBtn) {
        loadDashBtn.addEventListener('click', loadDashboardFromLocal);
    }
    document.getElementById('clear-charts').addEventListener('click', clearAllCharts);
    
    // Initialize scroll control states
    updateScrollControls();
}

/**
 * Quick load historical data with preset time range
 * AUTO-CONFIGURES: sampling interval, time axis, and data display
 */
async function loadHistoricalDataQuick(hours) {
    if (state.selectedTags.length === 0) {
        alert('⚠️ Please select tags first (check 1-5 tag boxes on the left)');
        return;
    }
    
    // Get button element for visual feedback
    const buttonId = hours === 1 ? 'btn-back-1h' :
                     hours === 6 ? 'btn-back-6h' :
                     hours === 24 ? 'btn-back-24h' :
                     hours === 168 ? 'btn-back-1week' :
                     hours === 720 ? 'btn-back-1month' :
                     hours === 2160 ? 'btn-back-3months' :
                     hours === 8760 ? 'btn-back-1year' : null;
    
    const button = buttonId ? document.getElementById(buttonId) : null;
    const originalText = button ? button.textContent : '';
    
    // Update the dropdown to match
    const rangeSelect = document.getElementById('historical-range');
    const samplingEl = document.getElementById('sampling-interval-select');
    
    if (rangeSelect) {
        // Find matching option or use custom
        const options = Array.from(rangeSelect.options);
        const matchingOption = options.find(opt => parseInt(opt.value) === hours);
        if (matchingOption) {
            rangeSelect.value = matchingOption.value;
        }
    }
    
    // AUTO-SELECT optimal sampling interval based on time range
    const defaultInterval = getDefaultSamplingInterval(hours);
    if (samplingEl) {
        samplingEl.value = defaultInterval;
    }
    const samplingInterval = samplingEl ? parseInt(samplingEl.value) : defaultInterval;
    
    // Calculate max points
    const maxPoints = calculateMaxPoints(hours, samplingInterval);
    
    // Get friendly names
    const rangeName = hours === 1 ? '1 Hour' :
                      hours === 6 ? '6 Hours' :
                      hours === 24 ? '1 Day' :
                      hours === 168 ? '1 Week' :
                      hours === 720 ? '1 Month' :
                      hours === 2160 ? '3 Months' :
                      hours === 8760 ? '1 Year' : `${hours}h`;
    
    console.log(`⚡ Quick load ${rangeName}: ${samplingInterval}s interval (~${maxPoints} pts)`);
    
    // Visual feedback - button shows loading
    if (button) {
        button.disabled = true;
        button.textContent = '⏳ Loading...';
    }
    
    try {
        const response = await fetch('/api/historical/multiple', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                tagIds: state.selectedTags,
                hours: hours,
                maxPoints: maxPoints,
                samplingInterval: samplingInterval  // ✅ NEW: Send explicit sampling interval
            })
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        const result = await response.json();
        
        // Log the raw response for debugging
        console.log(`📊 Quick Load API Response:`, result);
        
        // IMPORTANT: Clear existing buffers BEFORE loading historical data
        state.selectedTags.forEach(tagId => {
            state.tagBuffer.set(tagId, []);
        });
        
        let totalPoints = 0;
        if (result.trends) {
            Object.entries(result.trends).forEach(([tagId, dataPoints]) => {
                if (!state.tagBuffer.has(tagId)) {
                    state.tagBuffer.set(tagId, []);
                }
                
                const buffer = state.tagBuffer.get(tagId);
                if (dataPoints && Array.isArray(dataPoints)) {
                    dataPoints.forEach(point => {
                        if (point.value !== null && point.value !== undefined) {
                            buffer.push({
                                x: new Date(point.timestamp),
                                y: parseFloat(point.value)
                            });
                        }
                    });
                    totalPoints += dataPoints.length;
                } else {
                    console.warn(`⚠️ No data points for tag ${tagId}:`, dataPoints);
                }
            });
        } else {
            console.error('❌ No trends in response:', result);
        }
        
        console.log(`✅ Loaded ${totalPoints} points (${rangeName}, ${samplingInterval}s sampling)`);
        
        // DON'T pause - let live data continue overlaying
        // state.isPaused remains false
        
        // Update chart time axis based on range
        updateChartTimeAxis(hours);
        
        // Update chart display
        updateChart();
        
        // Update time range display
        const timeDisplay = document.getElementById('time-range-display');
        if (timeDisplay) {
            timeDisplay.textContent = `${rangeName} (${totalPoints} pts, ${samplingInterval}s)`;
        }
        
        // Success feedback - button shows checkmark briefly
        if (button) {
            button.textContent = '✅ Loaded';
            button.style.backgroundColor = '#28a745';
            setTimeout(() => {
                button.textContent = originalText;
                button.disabled = false;
                button.style.backgroundColor = '';
            }, 2000);
        }
        
    } catch (error) {
        console.error(`❌ Failed to load ${rangeName}:`, error);
        
        // Error feedback
        if (button) {
            button.textContent = '❌ Failed';
            button.style.backgroundColor = '#dc3545';
            setTimeout(() => {
                button.textContent = originalText;
                button.disabled = false;
                button.style.backgroundColor = '';
            }, 3000);
        }
        
        alert(`Failed to load ${rangeName} data: ${error.message}`);
    }
}

/**
 * Save dashboard configuration to localStorage
 */
function saveDashboardToLocal() {
    const config = {
        selectedTags: state.selectedTags,
        chartMode: state.chartMode,
        timeRange: (function() {
            const tr = document.getElementById('time-range');
            return tr ? tr.value : '1';
        })(),
        savedAt: new Date().toISOString()
    };
    
    localStorage.setItem('hmi_dashboard_config', JSON.stringify(config));
    
    alert('✅ Dashboard saved to local storage!');
    console.log('💾 Dashboard saved:', config);
}

/**
 * Load dashboard configuration from localStorage
 */
function loadDashboardFromLocal() {
    const saved = localStorage.getItem('hmi_dashboard_config');
    
    if (!saved) {
        console.log('ℹ️ No saved dashboard found');
        return;
    }
    
    try {
        const config = JSON.parse(saved);
        
        // Restore selected tags (limit to 10 max)
        const savedTags = config.selectedTags || [];
        state.selectedTags = savedTags.slice(0, 10);  // Limit to 10
        
        console.log(`📂 Restored ${state.selectedTags.length} tags from localStorage:`, state.selectedTags);
        
        state.chartMode = config.chartMode || 'live';
        
        const chartMode = document.getElementById('chart-mode');
        if (chartMode) {
            chartMode.value = state.chartMode;
        }
        const timeRange = document.getElementById('time-range');
        if (timeRange) {
            timeRange.value = config.timeRange || '1';
        }
        
        updateChart();
        updateTagSelector();
        
        console.log('📂 Dashboard loaded:', config);
        
    } catch (error) {
        console.error('❌ Failed to load dashboard:', error);
        // Clear corrupted localStorage
        localStorage.removeItem('hmi_dashboard_config');
    }
}

/**
 * Load enabled tags from database automatically on startup
 */
async function loadEnabledTagsFromDB() {
    try {
        console.log('📋 Loading enabled tags from database...');
        const response = await fetch('/api/tags/enabled');
        const data = await response.json();
        
        if (data.tags && data.tags.length > 0) {
            console.log(`✅ Loaded ${data.count} enabled tags from tag_master`);
            
            // Populate checkbox list (do NOT auto-select all)
            populateTagCheckboxes(data.tags);
            
            // Initialize live data structure for all tags
            data.tags.forEach(tag => {
                state.liveData[tag.tagId] = {
                    value: 0,
                    quality: 'WAITING',
                    timestamp: new Date().toISOString(),
                    name: tag.tagName,
                    unit: tag.unit,
                    description: tag.description
                };
            });
            
            // Update UI
            updateTagSelector();
            updateLiveValuesTable();
            
            // Subscribe via WebSocket if connected
            if (state.socket && state.socket.connected) {
                state.socket.emit('subscribe_tags', { tagIds: state.selectedTags });
            }
            
            console.log(`🎯 Auto-monitoring ${state.selectedTags.length} enabled tags`);
        } else {
            console.warn('⚠️ No enabled tags found in tag_master table - trying live API as fallback');
            // Fallback: try to get tags from live API
            try {
                const liveResponse = await fetch('/api/tags/latest');
                if (liveResponse.ok) {
                    const liveData = await liveResponse.json();
                    if (liveData && Object.keys(liveData).length > 0) {
                        const liveTags = Object.keys(liveData).map(tagId => ({
                            tagId: tagId,
                            tagName: tagId,
                            description: 'Live tag from MQTT/OPC',
                            unit: '',
                            dataType: 'double'
                        }));
                        console.log(`🔄 Loaded ${liveTags.length} tags from live API fallback`);
                        populateTagCheckboxes(liveTags);
                    }
                }
            } catch (fallbackError) {
                console.error('❌ Fallback API also failed:', fallbackError);
            }
        }
    } catch (error) {
        console.error('❌ Failed to load enabled tags:', error);
        // Continue without tags - graceful degradation
    }
}

/**
 * Start polling for tag values from OPC service (NOT database)
 * Reads from C# OPC TagValuesPoolService for real-time performance
 * Only updates tags that are mapped in historian_meta.tag_master
 */
function startTagPolling() {
    const backendUrl = state.config.backendUrl || 'http://localhost:5001';
    console.log('🚀 Starting tag polling (1 second interval)');
    console.log(`🔗 Backend URL: ${backendUrl}`);
    
    let consecutiveErrors = 0;
    
    setInterval(async () => {
        try {
            let allTags = [];
            let hasOpcData = false;
            let hasPlcData = false;
            
            // STEP 1: Try to get OPC data from C# backend
            try {
                const opcController = new AbortController();
                const opcTimeoutId = setTimeout(() => opcController.abort(), 2000);
                
                const opcResponse = await fetch(`${backendUrl}/api/opc/values`, {
                    signal: opcController.signal,
                    mode: 'cors'
                });
                
                clearTimeout(opcTimeoutId);
                
                if (opcResponse.ok) {
                    const opcData = await opcResponse.json();
                    if (opcData.tags && opcData.tags.length > 0) {
                        allTags = [...opcData.tags]; // Start with OPC tags
                        hasOpcData = true;
                        console.log(`✅ OPC: ${opcData.tags.length} tags from C# backend`);
                    }
                }
            } catch (opcError) {
                console.log(`⚠️ OPC backend unavailable: ${opcError.message}`);
            }
            
            // STEP 2: Try to get PLC data from HMI MQTT API
            try {
                const plcController = new AbortController();
                const plcTimeoutId = setTimeout(() => plcController.abort(), 1000);
                
                const plcResponse = await fetch(`/api/tags/latest`, {
                    signal: plcController.signal,
                    mode: 'cors'
                });
                
                clearTimeout(plcTimeoutId);
                
                if (plcResponse.ok) {
                    const plcData = await plcResponse.json();
                    // Handle both formats: direct tags object or nested in 'tags' property
                    const tagsObject = plcData.tags || plcData;
                    if (tagsObject && typeof tagsObject === 'object') {
                        // Convert HMI API format to OPC format and add to allTags
                        Object.entries(tagsObject).forEach(([tagId, tagData]) => {
                            // Accept both MQTT_PLC and HISTORIAN sources
                            if (tagData.source === 'MQTT_PLC' || tagData.source === 'HISTORIAN') {
                                // Add PLC tags in OPC format
                                allTags.push({
                                    tagId: tagId,
                                    value: tagData.value,
                                    quality: tagData.quality,
                                    timestamp: tagData.timestamp
                                });
                                hasPlcData = true;
                            }
                        });
                        console.log(`✅ PLC: ${Object.keys(tagsObject).length} tags from MQTT`);
                    }
                }
            } catch (plcError) {
                console.log(`⚠️ PLC MQTT unavailable: ${plcError.message}`);
            }
            
            // STEP 3: Process combined data
            if (allTags.length === 0) {
                consecutiveErrors++;
                if (consecutiveErrors > 5) {
                    updateStatusIndicator('signalr-status', false);
                }
                console.log(`❌ No data from OPC (${hasOpcData}) or PLC (${hasPlcData})`);
                return;
            }
            
            consecutiveErrors = 0; // Reset on success
            
            // HMI API returns data.tags as object, not array
            if (allTags && allTags.length > 0) {
                // Update ALL tags in liveData (for table display)
                // Only chart the SELECTED tags
                let updatedCount = 0;
                
                // Process combined OPC + PLC tags
                allTags.forEach(tag => {
                    // Handle both numeric and string values
                    let value = tag.value;
                    const numValue = parseFloat(value);
                    if (!isNaN(numValue)) {
                        value = numValue;
                    }
                    
                    // Store ALL tags (needed for table and checkbox display)
                    state.liveData[tag.tagId] = {
                        value: value,
                        quality: tag.quality || 'UNKNOWN',
                        timestamp: tag.timestamp || new Date().toISOString()
                    };
                    
                    // Add to buffer only if selected for charting
                    if (state.selectedTags.includes(tag.tagId)) {
                        addDataPointToBuffer(tag.tagId, tag.timestamp || new Date().toISOString(), value);
                    }
                    
                    updatedCount++;
                });
                
                // Log only every 10 seconds to avoid console spam
                if (!startTagPolling.lastLog || Date.now() - startTagPolling.lastLog > 10000) {
                    console.log(`🔄 Live: ${updatedCount} tags, ${state.selectedTags.length} charted`);
                    startTagPolling.lastLog = Date.now();
                }
                
                // Always ensure tag checkboxes are populated
                const container = document.getElementById('tag-checkboxes');
                if (container && allTags.length > 0) {
                    // Always repopulate to ensure fresh state
                    console.log(`🏷️ Refreshing ${allTags.length} tags in list`);
                    populateTagCheckboxes(allTags);
                }
                
                // Update UI (only left panel for selected tags)
                updateLeftPanelValues();
                
                // Update chart if not paused
                if (!state.isPaused) {
                    updateLiveChart();
                }
                updateFooterStats();
                
                updateStatusIndicator('signalr-status', true);
            }
        } catch (error) {
            // Log the actual error for debugging
            console.error(`❌ OPC fetch error (${consecutiveErrors + 1}/6):`, error.message);
            
            consecutiveErrors++;
            if (consecutiveErrors > 5) {
                updateStatusIndicator('signalr-status', false);
                console.error('🚨 OPC connection lost after 5+ consecutive errors');
            }
        }
    }, 1000); // Poll every 1 second
}

/**
 * Clear all charts and reset
 */
function clearAllCharts() {
    if (!confirm('Clear all charts and selected tags?')) return;
    
    state.selectedTags = [];
    state.historicalData = {};
    
    updateChart();
    updateTagSelector();
    updateLiveValuesTable();
    
    console.log('🗑️ Charts cleared');
}

/**
 * Show mode notification banner
 */
function showModeNotification(mode, message, type = 'info') {
    // Disabled - no notifications
    return;
    banner.style.cssText = `
        position: fixed;
        top: 10px;
        left: 50%;
        transform: translateX(-50%);
        background: ${type === 'warning' ? '#f39c12' : type === 'info' ? '#3498db' : '#27ae60'};
        color: white;
        padding: 15px 30px;
        border-radius: 8px;
        box-shadow: 0 4px 8px rgba(0,0,0,0.3);
        z-index: 10000;
        font-weight: bold;
        max-width: 80%;
        text-align: center;
    `;
    banner.innerHTML = `
        <div style="font-size: 18px; margin-bottom: 5px;">${mode}</div>
        <div style="font-size: 14px; opacity: 0.9;">${message}</div>
    `;
    
    document.body.appendChild(banner);
    
    // Auto-remove after 10 seconds
    setTimeout(() => {
        banner.style.transition = 'opacity 0.5s';
        banner.style.opacity = '0';
        setTimeout(() => banner.remove(), 500);
    }, 10000);
}

/**
 * Setup resizable left panel
 */
function setupResizablePanel() {
    const leftPanel = document.getElementById('left-panel');
    const rightPanel = document.getElementById('right-panel');
    const resizeHandle = document.getElementById('resize-handle');
    const toggleBtn = document.getElementById('toggle-panel');
    
    if (!leftPanel || !resizeHandle) return;
    
    let isResizing = false;
    let isPanelCollapsed = false;
    
    resizeHandle.addEventListener('mousedown', (e) => {
        isResizing = true;
        document.body.style.cursor = 'ew-resize';
        e.preventDefault();
    });
    
    document.addEventListener('mousemove', (e) => {
        if (!isResizing) return;
        
        const containerWidth = leftPanel.parentElement.offsetWidth;
        const newWidth = (e.clientX / containerWidth) * 100;
        
        // Limit between 15% and 50%
        if (newWidth >= 15 && newWidth <= 50) {
            leftPanel.style.flex = `0 0 ${newWidth}%`;
        }
    });
    
    document.addEventListener('mouseup', () => {
        if (isResizing) {
            isResizing = false;
            document.body.style.cursor = 'default';
        }
    });
    
    // Toggle panel collapse with restore
    if (toggleBtn) {
        toggleBtn.addEventListener('click', () => {
            isPanelCollapsed = !isPanelCollapsed;
            if (isPanelCollapsed) {
                // Collapse to minimal size
                leftPanel.style.flex = '0 0 40px';
                leftPanel.style.overflow = 'hidden';
                leftPanel.classList.add('collapsed');
                toggleBtn.textContent = '▶';
                toggleBtn.title = 'Expand Tag Panel';
                resizeHandle.style.display = 'none';
            } else {
                // Restore to original size
                leftPanel.style.flex = '0 0 20%';
                leftPanel.style.overflow = 'auto';
                leftPanel.classList.remove('collapsed');
                toggleBtn.textContent = '◀';
                toggleBtn.title = 'Collapse Tag Panel';
                resizeHandle.style.display = 'block';
            }
        });
    }
}

/**
 * Setup fullscreen mode for chart
 */
function setupFullscreen() {
    const fullscreenBtn = document.getElementById('fullscreen-btn');
    const chartContainer = document.getElementById('chart-container');
    
    if (!fullscreenBtn || !chartContainer) return;
    
    fullscreenBtn.addEventListener('click', () => {
        if (!state.isFullscreen) {
            // Enter fullscreen
            if (chartContainer.requestFullscreen) {
                chartContainer.requestFullscreen();
            } else if (chartContainer.webkitRequestFullscreen) {
                chartContainer.webkitRequestFullscreen();
            } else if (chartContainer.msRequestFullscreen) {
                chartContainer.msRequestFullscreen();
            }
            state.isFullscreen = true;
            fullscreenBtn.textContent = '✕ Exit Fullscreen';
        } else {
            // Exit fullscreen
            if (document.exitFullscreen) {
                document.exitFullscreen();
            } else if (document.webkitExitFullscreen) {
                document.webkitExitFullscreen();
            } else if (document.msExitFullscreen) {
                document.msExitFullscreen();
            }
            state.isFullscreen = false;
            fullscreenBtn.textContent = '⛶ Fullscreen';
        }
    });
    
    // Reset zoom button
    const resetZoomBtn = document.getElementById('reset-zoom');
    if (resetZoomBtn) {
        resetZoomBtn.addEventListener('click', () => {
            state.charts.forEach(chart => {
                if (chart && chart.resetZoom) {
                    chart.resetZoom();
                    updateZoomInfo(chart);
                }
            });
        });
    }
    
    // Handle fullscreen change events
    document.addEventListener('fullscreenchange', () => {
        state.isFullscreen = !!document.fullscreenElement;
        if (fullscreenBtn) {
            fullscreenBtn.textContent = state.isFullscreen ? '✕ Exit Fullscreen' : '⛶ Fullscreen';
        }
    });
}

/**
 * Populate tag checkboxes from enabled tags
 */
function populateTagCheckboxes(tags) {
    const container = document.getElementById('tag-checkboxes');
    const totalCountElem = document.getElementById('total-count');
    
    if (!container) {
        console.error('❌ tag-checkboxes container not found');
        return;
    }
    
    if (!tags || tags.length === 0) {
        console.log('⚠️ No tags provided to populate');
        return;
    }
    
    container.innerHTML = '';
    
    tags.forEach(tag => {
        const checkbox = document.createElement('div');
        checkbox.className = 'tag-checkbox-item';
        const isSelected = state.selectedTags.includes(tag.tagId);
        
        // Show value ONLY if tag is selected
        const valueDisplay = isSelected && state.liveData[tag.tagId] 
            ? `<span class="tag-value">${state.liveData[tag.tagId].value || 'N/A'}</span>`
            : '';
        
        checkbox.innerHTML = `
            <label>
                <input type="checkbox" value="${tag.tagId}" ${isSelected ? 'checked' : ''}>
                <span class="tag-label">${tag.tagId}</span>
                ${valueDisplay}
            </label>
        `;
        
        checkbox.querySelector('input').addEventListener('change', (e) => {
            const tagId = e.target.value;
            if (e.target.checked) {
                if (!state.selectedTags.includes(tagId)) {
                    // Limit to 10 tags maximum (consistent with toggleTagChart)
                    if (state.selectedTags.length >= 10) {
                        e.target.checked = false;
                        alert('⚠️ Maximum 10 tags can be selected for optimal performance');
                        return;
                    }
                    state.selectedTags.push(tagId);
                    console.log(`✅ Added tag: ${tagId}, total selected: ${state.selectedTags.length}`);
                }
            } else {
                state.selectedTags = state.selectedTags.filter(t => t !== tagId);
                console.log(`❌ Removed tag: ${tagId}, total selected: ${state.selectedTags.length}`);
            }
            updateSelectedCount();
            updateLeftPanelValues(); // Update value display
            updateChart();
        });
        
        container.appendChild(checkbox);
    });
    
    if (totalCountElem) {
        totalCountElem.textContent = tags.length;
    }
    updateSelectedCount();
}

/**
 * Update left panel to show values only for selected tags
 */
function updateLeftPanelValues() {
    const checkboxes = document.querySelectorAll('#tag-checkboxes .tag-checkbox-item');
    
    checkboxes.forEach(item => {
        const input = item.querySelector('input');
        const label = item.querySelector('label');
        const tagId = input.value;
        const isSelected = state.selectedTags.includes(tagId);
        
        if (isSelected && state.liveData[tagId]) {
            // Show value for selected tags
            const tagLabel = label.querySelector('.tag-label');
            let valueSpan = label.querySelector('.tag-value');
            
            if (!valueSpan) {
                valueSpan = document.createElement('span');
                valueSpan.className = 'tag-value';
                label.appendChild(valueSpan);
            }
            
            valueSpan.textContent = state.liveData[tagId].value || 'N/A';
        } else {
            // Remove value for unselected tags
            const valueSpan = label.querySelector('.tag-value');
            if (valueSpan) {
                valueSpan.remove();
            }
        }
    });
}

/**
 * Update selected tag count display
 */
function updateSelectedCount() {
    const selectedCountElem = document.getElementById('selected-count');
    if (selectedCountElem) {
        selectedCountElem.textContent = state.selectedTags.length;
    }
}

/**
 * Setup Select All / Clear All buttons
 */
function setupSelectionControls() {
    const selectAllBtn = document.getElementById('select-all');
    const clearAllBtn = document.getElementById('clear-all');
    
    if (selectAllBtn) {
        selectAllBtn.addEventListener('click', () => {
            const checkboxes = document.querySelectorAll('#tag-checkboxes input[type="checkbox"]');
            let selectedCount = state.selectedTags.length;
            
            checkboxes.forEach(cb => {
                if (selectedCount < 10 && !cb.checked) {
                    cb.checked = true;
                    if (!state.selectedTags.includes(cb.value)) {
                        state.selectedTags.push(cb.value);
                        selectedCount++;
                    }
                }
            });
            
            console.log(`✅ Select All: ${state.selectedTags.length} tags selected`);
            updateSelectedCount();
            updateChart();
        });
    }
    
    if (clearAllBtn) {
        clearAllBtn.addEventListener('click', () => {
            const checkboxes = document.querySelectorAll('#tag-checkboxes input[type="checkbox"]');
            checkboxes.forEach(cb => cb.checked = false);
            state.selectedTags = [];
            updateSelectedCount();
            updateChart();
        });
    }
}

/**
 * Update zoom info display based on current chart view
 */
function updateZoomInfo(chart) {
    const xScale = chart.scales.x;
    if (!xScale) return;
    
    const min = xScale.min;
    const max = xScale.max;
    
    if (!min || !max) return;
    
    const rangeMs = max - min;
    const rangeHours = rangeMs / (1000 * 3600);
    
    // Calculate visible data points
    let visiblePoints = 0;
    chart.data.datasets.forEach(dataset => {
        if (dataset.data) {
            visiblePoints += dataset.data.filter(point => 
                point.x >= min && point.x <= max
            ).length;
        }
    });
    
    // Update stats display
    const statsEl = document.getElementById('chart-stats');
    if (statsEl) {
        let timeInfo = '';
        if (rangeHours < 1) {
            timeInfo = `${Math.round(rangeHours * 60)} minutes`;
        } else if (rangeHours < 24) {
            timeInfo = `${rangeHours.toFixed(1)} hours`;
        } else {
            timeInfo = `${(rangeHours / 24).toFixed(1)} days`;
        }
        
        const avgInterval = visiblePoints > 1 ? rangeMs / (visiblePoints * 1000) : 0;
        let intervalInfo = '';
        if (avgInterval > 0) {
            if (avgInterval < 60) {
                intervalInfo = `${avgInterval.toFixed(1)}s interval`;
            } else {
                intervalInfo = `${(avgInterval / 60).toFixed(1)}min interval`;
            }
        }
        
        statsEl.innerHTML = `
            <span>📊 Visible: ${timeInfo}</span>
            <span>📈 Points: ${visiblePoints}</span>
            ${intervalInfo ? `<span>⏱️ ${intervalInfo}</span>` : ''}
            <span style="color: #FFD93D;">💡 Zoom in for more detail, or increase Max Points for finer data</span>
        `;
    }
}

/**
 * Check if zoom level requires reloading with more detailed data
 */
function checkAndReloadForZoom(chart) {
    if (state.viewMode !== 'historical') return;
    
    const xScale = chart.scales.x;
    if (!xScale) return;
    
    const min = xScale.min;
    const max = xScale.max;
    
    if (!min || !max) return;
    
    const rangeMs = max - min;
    const rangeHours = rangeMs / (1000 * 3600);
    
    // Calculate visible data points
    let visiblePoints = 0;
    chart.data.datasets.forEach(dataset => {
        if (dataset.data) {
            visiblePoints += dataset.data.filter(point => 
                point.x >= min && point.x <= max
            ).length;
        }
    });
    
    const pointsPerHour = visiblePoints / rangeHours;
    
    // If zoomed in significantly and data is sparse, suggest reload
    if (rangeHours < 24 && pointsPerHour < 100) {
        const statsEl = document.getElementById('chart-stats');
        if (statsEl) {
            statsEl.innerHTML += `
                <span style="color: #FF6B35;">⚠️ Sparse data - increase "Max Points" and reload for more detail</span>
            `;
        }
    }
}

/**
 * Setup time range change listener to auto-adjust sampling interval
 */
function setupTimeRangeListener() {
    const rangeSelect = document.getElementById('historical-range');
    const samplingSelect = document.getElementById('sampling-interval-select');
    
    if (rangeSelect && samplingSelect) {
        rangeSelect.addEventListener('change', () => {
            const hours = parseInt(rangeSelect.value);
            const defaultInterval = getDefaultSamplingInterval(hours);
            samplingSelect.value = defaultInterval;
            
            const maxPoints = calculateMaxPoints(hours, defaultInterval);
            console.log(`📊 Range changed to ${hours}h → Auto-set ${defaultInterval}s sampling (~${maxPoints} points)`);
        });
    }
}

/**
 * Populate sampling interval dropdown from config
 */
function populateSamplingSelector() {
    console.log('🔧 populateSamplingSelector() called');
    const selector = document.getElementById('sampling-interval-select');
    
    if (!selector) {
        console.error('❌ Sampling selector element not found!');
        return;
    }
    
    if (!state.samplingConfig) {
        console.error('❌ No sampling config available!', state.config);
        return;
    }
    
    selector.innerHTML = '';
    
    const intervals = state.samplingConfig.available_intervals || [5, 10, 20, 30, 60];
    const labels = state.samplingConfig.interval_labels || {};
    
    console.log(`📋 Populating ${intervals.length} intervals:`, intervals);
    
    intervals.forEach(interval => {
        const option = document.createElement('option');
        option.value = interval;
        option.textContent = labels[interval] || `${interval} sec`;
        selector.appendChild(option);
    });
    
    // Set default selection (5 seconds)
    if (intervals.includes(5)) {
        selector.value = 5;
    }
    
    console.log(`✅ Successfully populated ${intervals.length} sampling intervals`);
}

/**
 * Get default sampling interval for a given time range in hours
 */
function getDefaultSamplingInterval(hours) {
    if (!state.samplingConfig || !state.samplingConfig.default_by_hours) {
        return 30; // Fallback default
    }
    
    const defaults = state.samplingConfig.default_by_hours;
    
    // Find closest matching range
    const hoursKey = hours.toString();
    if (defaults[hoursKey]) {
        return defaults[hoursKey];
    }
    
    // Find nearest higher range
    const sortedKeys = Object.keys(defaults).map(Number).sort((a, b) => a - b);
    for (const key of sortedKeys) {
        if (key >= hours) {
            return defaults[key];
        }
    }
    
    // Default to last value
    return defaults[sortedKeys[sortedKeys.length - 1]] || 30;
}

/**
 * Calculate max points based on time range and sampling interval
 */
function calculateMaxPoints(hours, samplingIntervalSeconds) {
    const totalSeconds = hours * 3600;
    return Math.ceil(totalSeconds / samplingIntervalSeconds);
}

// Initialize on page load
console.log('✅ Dashboard.js loaded successfully');

