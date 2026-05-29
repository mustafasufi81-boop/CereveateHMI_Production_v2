// =====================================================
// INDUSTRIAL FEATURES MODULE
// Power Plant Grade Enhancements
// =====================================================

// Operating Band Configuration Storage
let operatingBands = {};

// Event Markers Storage
let eventMarkers = [];

// Shift Configuration
let shiftConfig = {
    duration: 8, // 8 or 12 hours
    startTime: '00:00'
};

// =====================================================
// 1. OPERATING BAND INDICATOR
// =====================================================

/**
 * Calculate default operating bands from data via Python API
 * Uses statistical analysis if user hasn't configured bands
 */
async function calculateDefaultBands(data, tag) {
    try {
        const response = await fetch(`${window.location.origin}/api/v1/industrial/operating_bands`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ data, tag })
        });
        
        if (response.ok) {
            const result = await response.json();
            console.log(`✓ Operating bands calculated via Python for ${tag}`);
            return result;
        }
    } catch (error) {
        console.error('Operating Bands API Error:', error);
        throw error;
    }
    
    return null;
}

/**
 * Get operating bands for a tag (user-configured or auto-calculated)
 */
function getOperatingBands(data, tag) {
    // Return user-configured bands if available
    if (operatingBands[tag]) {
        return operatingBands[tag];
    }
    
    // Otherwise calculate from data
    return calculateDefaultBands(data, tag);
}

/**
 * Render operating bands on a chart
 */
function renderOperatingBands(plotDiv, data, tag, yaxis = 'y') {
    const bands = getOperatingBands(data, tag);
    if (!bands) return [];
    
    const shapes = [];
    
    // Critical High Band (Red)
    if (bands.critical && bands.veryHigh) {
        shapes.push({
            type: 'rect',
            xref: 'paper',
            yref: yaxis,
            x0: 0,
            x1: 1,
            y0: bands.critical,
            y1: bands.veryHigh,
            fillcolor: 'rgba(255, 59, 48, 0.08)',
            line: { width: 0 },
            layer: 'below'
        });
    }
    
    // Warning High Band (Orange)
    if (bands.high && bands.critical) {
        shapes.push({
            type: 'rect',
            xref: 'paper',
            yref: yaxis,
            x0: 0,
            x1: 1,
            y0: bands.high,
            y1: bands.critical,
            fillcolor: 'rgba(255, 149, 0, 0.08)',
            line: { width: 0 },
            layer: 'below'
        });
    }
    
    // Normal Operating Band (Green)
    shapes.push({
        type: 'rect',
        xref: 'paper',
        yref: yaxis,
        x0: 0,
        x1: 1,
        y0: bands.normalMin,
        y1: bands.normalMax,
        fillcolor: 'rgba(52, 199, 89, 0.08)',
        line: { width: 0 },
        layer: 'below'
    });
    
    // Warning Low Band (Orange)
    if (bands.low && bands.normalMin) {
        shapes.push({
            type: 'rect',
            xref: 'paper',
            yref: yaxis,
            x0: 0,
            x1: 1,
            y0: bands.low,
            y1: bands.normalMin,
            fillcolor: 'rgba(255, 149, 0, 0.08)',
            line: { width: 0 },
            layer: 'below'
        });
    }
    
    // Critical Low Band (Red)
    if (bands.veryLow && bands.low) {
        shapes.push({
            type: 'rect',
            xref: 'paper',
            yref: yaxis,
            x0: 0,
            x1: 1,
            y0: bands.veryLow,
            y1: bands.low,
            fillcolor: 'rgba(255, 59, 48, 0.08)',
            line: { width: 0 },
            layer: 'below'
        });
    }
    
    // Add horizontal reference lines
    const lines = [
        { y: bands.normalMax, color: 'rgba(52, 199, 89, 0.5)', dash: 'dot', text: 'Normal Max' },
        { y: bands.normalMin, color: 'rgba(52, 199, 89, 0.5)', dash: 'dot', text: 'Normal Min' },
        { y: bands.high, color: 'rgba(255, 149, 0, 0.6)', dash: 'dash', text: 'High Warning' },
        { y: bands.low, color: 'rgba(255, 149, 0, 0.6)', dash: 'dash', text: 'Low Warning' },
        { y: bands.critical, color: 'rgba(255, 59, 48, 0.8)', dash: 'solid', text: 'Critical High' }
    ];
    
    lines.forEach(line => {
        if (line.y !== undefined && line.y !== null && !isNaN(line.y)) {
            shapes.push({
                type: 'line',
                xref: 'paper',
                yref: yaxis,
                x0: 0,
                x1: 1,
                y0: line.y,
                y1: line.y,
                line: {
                    color: line.color,
                    width: 1,
                    dash: line.dash
                }
            });
        }
    });
    
    return shapes;
}

/**
 * Show operating band configuration modal
 */
function showBandConfigModal(tag) {
    const bands = operatingBands[tag] || calculateDefaultBands(currentData, tag);
    
    const modal = document.createElement('div');
    modal.id = 'bandConfigModal';
    modal.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0, 0, 0, 0.8);
        display: flex;
        justify-content: center;
        align-items: center;
        z-index: 10000;
    `;
    
    modal.innerHTML = `
        <div style="background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); padding: 30px; border-radius: 12px; border: 2px solid #00d4ff; max-width: 600px; width: 90%;">
            <h2 style="color: #00d4ff; margin-bottom: 20px;">⚙️ Configure Operating Bands: ${tag}</h2>
            
            <div style="display: grid; gap: 15px;">
                <div class="band-input-group">
                    <label style="color: #ff3b30; font-weight: bold;">🔴 Critical High:</label>
                    <input type="number" id="band-critical" value="${(bands?.critical || 0).toFixed(2)}" step="0.01" style="background: rgba(255, 59, 48, 0.1); border: 1px solid #ff3b30; color: #fff; padding: 8px; border-radius: 4px; width: 100%;">
                </div>
                
                <div class="band-input-group">
                    <label style="color: #ff9500; font-weight: bold;">🟠 High Warning:</label>
                    <input type="number" id="band-high" value="${(bands?.high || 0).toFixed(2)}" step="0.01" style="background: rgba(255, 149, 0, 0.1); border: 1px solid #ff9500; color: #fff; padding: 8px; border-radius: 4px; width: 100%;">
                </div>
                
                <div class="band-input-group">
                    <label style="color: #34c759; font-weight: bold;">🟢 Normal Max:</label>
                    <input type="number" id="band-normalMax" value="${(bands?.normalMax || 0).toFixed(2)}" step="0.01" style="background: rgba(52, 199, 89, 0.1); border: 1px solid #34c759; color: #fff; padding: 8px; border-radius: 4px; width: 100%;">
                </div>
                
                <div class="band-input-group">
                    <label style="color: #34c759; font-weight: bold;">🟢 Normal Min:</label>
                    <input type="number" id="band-normalMin" value="${(bands?.normalMin || 0).toFixed(2)}" step="0.01" style="background: rgba(52, 199, 89, 0.1); border: 1px solid #34c759; color: #fff; padding: 8px; border-radius: 4px; width: 100%;">
                </div>
                
                <div class="band-input-group">
                    <label style="color: #ff9500; font-weight: bold;">🟠 Low Warning:</label>
                    <input type="number" id="band-low" value="${(bands?.low || 0).toFixed(2)}" step="0.01" style="background: rgba(255, 149, 0, 0.1); border: 1px solid #ff9500; color: #fff; padding: 8px; border-radius: 4px; width: 100%;">
                </div>
                
                <div class="band-input-group">
                    <label style="color: #ff3b30; font-weight: bold;">🔴 Critical Low:</label>
                    <input type="number" id="band-veryLow" value="${(bands?.veryLow || 0).toFixed(2)}" step="0.01" style="background: rgba(255, 59, 48, 0.1); border: 1px solid #ff3b30; color: #fff; padding: 8px; border-radius: 4px; width: 100%;">
                </div>
            </div>
            
            <div style="display: flex; gap: 10px; margin-top: 25px;">
                <button id="saveBands" style="flex: 1; padding: 12px; background: linear-gradient(135deg, #34c759, #30d158); border: none; color: white; font-weight: bold; border-radius: 6px; cursor: pointer;">
                    ✓ Save Configuration
                </button>
                <button id="resetBands" style="flex: 1; padding: 12px; background: rgba(255, 149, 0, 0.8); border: none; color: white; font-weight: bold; border-radius: 6px; cursor: pointer;">
                    ↻ Auto Calculate
                </button>
                <button id="closeBands" style="flex: 1; padding: 12px; background: rgba(255, 59, 48, 0.8); border: none; color: white; font-weight: bold; border-radius: 6px; cursor: pointer;">
                    ✕ Cancel
                </button>
            </div>
        </div>
    `;
    
    document.body.appendChild(modal);
    
    // Event handlers
    document.getElementById('saveBands').onclick = () => {
        operatingBands[tag] = {
            critical: parseFloat(document.getElementById('band-critical').value),
            high: parseFloat(document.getElementById('band-high').value),
            normalMax: parseFloat(document.getElementById('band-normalMax').value),
            normalMin: parseFloat(document.getElementById('band-normalMin').value),
            low: parseFloat(document.getElementById('band-low').value),
            veryLow: parseFloat(document.getElementById('band-veryLow').value)
        };
        saveBandsToStorage();
        modal.remove();
        if (currentData) renderCombinedChart();
    };
    
    document.getElementById('resetBands').onclick = () => {
        const autoBands = calculateDefaultBands(currentData, tag);
        document.getElementById('band-critical').value = (autoBands?.critical || 0).toFixed(2);
        document.getElementById('band-high').value = (autoBands?.high || 0).toFixed(2);
        document.getElementById('band-normalMax').value = (autoBands?.normalMax || 0).toFixed(2);
        document.getElementById('band-normalMin').value = (autoBands?.normalMin || 0).toFixed(2);
        document.getElementById('band-low').value = (autoBands?.low || 0).toFixed(2);
        document.getElementById('band-veryLow').value = (autoBands?.veryLow || 0).toFixed(2);
    };
    
    document.getElementById('closeBands').onclick = () => modal.remove();
    modal.onclick = (e) => { if (e.target === modal) modal.remove(); };
}

/**
 * Save bands to localStorage
 */
function saveBandsToStorage() {
    try {
        localStorage.setItem('operatingBands', JSON.stringify(operatingBands));
    } catch (e) {
        console.error('Failed to save operating bands:', e);
    }
}

/**
 * Load bands from localStorage
 */
function loadBandsFromStorage() {
    try {
        const stored = localStorage.getItem('operatingBands');
        if (stored) {
            operatingBands = JSON.parse(stored);
        }
    } catch (e) {
        console.error('Failed to load operating bands:', e);
    }
}

// =====================================================
// 2. SHIFT SUMMARY (8hr / 12hr)
// =====================================================

/**
 * Calculate shift statistics via Python API
 */
async function calculateShiftStats(data, tag, shiftStart, shiftEnd) {
    try {
        const response = await fetch(`${window.location.origin}/api/v1/industrial/shift_stats`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                data: data,
                tag: tag,
                shift_start: shiftStart,
                shift_end: shiftEnd
            })
        });
        
        if (response.ok) {
            const result = await response.json();
            console.log(`✓ Shift stats calculated via Python for ${tag}`);
            return result;
        }
    } catch (error) {
        console.error('Shift Stats API Error:', error);
        throw error;
    }
    
    return null;
}

/**
 * REMOVED: JavaScript fallback - API only mode
 */
function calculateShiftStatsJS(data, tag, shiftStart, shiftEnd) {
    const shiftData = data.filter(d => {
        const time = new Date(d.Timestamp);
        return time >= shiftStart && time <= shiftEnd && d[tag] !== null && !isNaN(d[tag]);
    });
    
    if (shiftData.length === 0) return null;
    
    const values = shiftData.map(d => d[tag]);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const avg = values.reduce((a, b) => a + b, 0) / values.length;
    
    // Calculate trend score (comparing first half vs second half)
    const mid = Math.floor(values.length / 2);
    const firstHalfAvg = values.slice(0, mid).reduce((a, b) => a + b, 0) / mid;
    const secondHalfAvg = values.slice(mid).reduce((a, b) => a + b, 0) / (values.length - mid);
    const trendScore = secondHalfAvg > firstHalfAvg ? '↑' : secondHalfAvg < firstHalfAvg ? '↓' : '→';
    const trendPercent = ((secondHalfAvg - firstHalfAvg) / firstHalfAvg * 100).toFixed(1);
    
    return { min, max, avg, trendScore, trendPercent, dataPoints: values.length };
}

/**
 * Render shift summary panel
 */
function renderShiftSummary(data, tags) {
    const shiftPanel = document.getElementById('shiftSummaryPanel');
    if (!shiftPanel) return;
    
    // Calculate current shift
    const now = new Date();
    const shiftDuration = shiftConfig.duration * 60 * 60 * 1000; // hours to ms
    const shiftStart = new Date(now.getTime() - shiftDuration);
    
    let html = `
        <div style="background: rgba(0, 212, 255, 0.05); padding: 15px; border-radius: 8px; border: 1px solid rgba(0, 212, 255, 0.3);">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                <h3 style="color: #00d4ff; margin: 0;">⏱ Current ${shiftConfig.duration}-Hour Shift Summary</h3>
                <div>
                    <button id="shift8hr" style="padding: 5px 10px; margin-right: 5px; ${shiftConfig.duration === 8 ? 'background: #00d4ff; color: #000;' : 'background: rgba(0, 212, 255, 0.2); color: #00d4ff;'} border: 1px solid #00d4ff; border-radius: 4px; cursor: pointer;">8 Hr</button>
                    <button id="shift12hr" style="padding: 5px 10px; ${shiftConfig.duration === 12 ? 'background: #00d4ff; color: #000;' : 'background: rgba(0, 212, 255, 0.2); color: #00d4ff;'} border: 1px solid #00d4ff; border-radius: 4px; cursor: pointer;">12 Hr</button>
                </div>
            </div>
            <div style="font-size: 12px; color: #888; margin-bottom: 10px;">
                ${shiftStart.toLocaleString()} → ${now.toLocaleString()}
            </div>
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 10px;">
    `;
    
    tags.forEach(tag => {
        const stats = calculateShiftStats(data, tag, shiftStart, now);
        if (!stats) return;
        
        const trendColor = stats.trendScore === '↑' ? '#34c759' : stats.trendScore === '↓' ? '#ff3b30' : '#888';
        
        html += `
            <div style="background: rgba(22, 33, 62, 0.6); padding: 12px; border-radius: 6px; border-left: 3px solid #00d4ff;">
                <div style="font-weight: bold; color: #00d4ff; margin-bottom: 8px;">${tag}</div>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; font-size: 13px;">
                    <div>
                        <div style="color: #888;">Min</div>
                        <div style="color: #ff6b6b; font-weight: bold;">${stats.min.toFixed(2)}</div>
                    </div>
                    <div>
                        <div style="color: #888;">Max</div>
                        <div style="color: #34c759; font-weight: bold;">${stats.max.toFixed(2)}</div>
                    </div>
                    <div>
                        <div style="color: #888;">Average</div>
                        <div style="color: #00d4ff; font-weight: bold;">${stats.avg.toFixed(2)}</div>
                    </div>
                    <div>
                        <div style="color: #888;">Trend</div>
                        <div style="color: ${trendColor}; font-weight: bold; font-size: 16px;">${stats.trendScore} ${stats.trendPercent}%</div>
                    </div>
                </div>
                <div style="margin-top: 8px; font-size: 11px; color: #666;">
                    ${stats.dataPoints} data points
                </div>
            </div>
        `;
    });
    
    html += `</div></div>`;
    shiftPanel.innerHTML = html;
    shiftPanel.style.display = 'block';
    
    // Add shift duration toggle handlers
    document.getElementById('shift8hr').onclick = () => {
        shiftConfig.duration = 8;
        renderShiftSummary(data, tags);
    };
    document.getElementById('shift12hr').onclick = () => {
        shiftConfig.duration = 12;
        renderShiftSummary(data, tags);
    };
}

// =====================================================
// 3. DATA QUALITY INDICATOR
// =====================================================

/**
 * Assess data quality for a tag
 */
function assessDataQuality(data, tag) {
    const values = data.filter(d => d[tag] !== null && d[tag] !== undefined && !isNaN(d[tag]))
                       .map(d => d[tag]);
    
    if (values.length < 10) return 'INSUFFICIENT';
    
    // Calculate variance and outlier percentage
    const mean = values.reduce((a, b) => a + b, 0) / values.length;
    const variance = values.reduce((sum, val) => sum + Math.pow(val - mean, 2), 0) / values.length;
    const stdDev = Math.sqrt(variance);
    
    // Count outliers (beyond 3 sigma)
    const outliers = values.filter(v => Math.abs(v - mean) > 3 * stdDev).length;
    const outlierPercent = (outliers / values.length) * 100;
    
    // Calculate coefficient of variation
    const cv = (stdDev / mean) * 100;
    
    // Quality assessment
    if (outlierPercent > 10 || cv > 50) return 'FAULTY';
    if (outlierPercent > 5 || cv > 25) return 'NOISY';
    return 'GOOD';
}

/**
 * Get quality indicator icon and color
 */
function getQualityIndicator(quality) {
    switch (quality) {
        case 'GOOD': return { icon: '🟢', color: '#34c759', text: 'Good Quality' };
        case 'NOISY': return { icon: '🟡', color: '#ff9500', text: 'Noisy Data' };
        case 'FAULTY': return { icon: '🔴', color: '#ff3b30', text: 'Sensor Suspected Faulty' };
        default: return { icon: '⚪', color: '#888', text: 'Insufficient Data' };
    }
}

/**
 * Render data quality indicators
 */
function renderDataQualityIndicators(data, tags) {
    const container = document.getElementById('dataQualityPanel');
    if (!container) return;
    
    let html = '<div style="display: flex; gap: 15px; flex-wrap: wrap; padding: 15px; background: rgba(0, 0, 0, 0.3); border-radius: 8px;">';
    
    tags.forEach(tag => {
        const quality = assessDataQuality(data, tag);
        const indicator = getQualityIndicator(quality);
        
        html += `
            <div style="display: flex; align-items: center; gap: 8px; padding: 8px 15px; background: rgba(${indicator.color === '#34c759' ? '52, 199, 89' : indicator.color === '#ff9500' ? '255, 149, 0' : '255, 59, 48'}, 0.1); border: 1px solid ${indicator.color}; border-radius: 6px;">
                <span style="font-size: 18px;">${indicator.icon}</span>
                <div>
                    <div style="font-weight: bold; color: ${indicator.color}; font-size: 13px;">${tag}</div>
                    <div style="font-size: 11px; color: #888;">${indicator.text}</div>
                </div>
            </div>
        `;
    });
    
    html += '</div>';
    container.innerHTML = html;
    container.style.display = 'block';
}

// =====================================================
// 4. HEALTH SCORE (STABILITY, VARIATION, DEVIATION)
// =====================================================

/**
 * Calculate health scores for a tag via Python API
 */
async function calculateHealthScores(data, tag) {
    try {
        const response = await fetch(`${window.location.origin}/api/v1/industrial/health_scores`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ data, tag })
        });
        
        if (response.ok) {
            const result = await response.json();
            console.log(`✓ Health scores calculated via Python for ${tag}`);
            return result;
        }
    } catch (error) {
        console.error('Health Scores API Error:', error);
        throw error;
    }
    
    return null;
}

/**
 * REMOVED: JavaScript fallback - API only mode
 */
function calculateHealthScoresJS(data, tag) {
    const values = data.filter(d => d[tag] !== null && !isNaN(d[tag])).map(d => d[tag]);
    
    if (values.length < 10) return null;
    
    const mean = values.reduce((a, b) => a + b, 0) / values.length;
    const variance = values.reduce((sum, val) => sum + Math.pow(val - mean, 2), 0) / values.length;
    const stdDev = Math.sqrt(variance);
    
    // Stability Score (100 - coefficient of variation)
    const cv = (stdDev / Math.abs(mean)) * 100;
    const stabilityScore = Math.max(0, Math.min(100, 100 - cv));
    
    // Variation Score (inverse of range relative to mean)
    const range = Math.max(...values) - Math.min(...values);
    const rangePercent = (range / Math.abs(mean)) * 100;
    const variationScore = Math.max(0, Math.min(100, 100 - rangePercent / 2));
    
    // Deviation Score (percentage of values within 1 sigma)
    const withinOneSigma = values.filter(v => Math.abs(v - mean) <= stdDev).length;
    const deviationScore = (withinOneSigma / values.length) * 100;
    
    return {
        stability: stabilityScore,
        variation: variationScore,
        deviation: deviationScore
    };
}

/**
 * Render health scores panel
 */
function renderHealthScores(data, tags) {
    const container = document.getElementById('healthScorePanel');
    if (!container) return;
    
    let html = `
        <div style="background: linear-gradient(135deg, rgba(102, 126, 234, 0.1), rgba(118, 75, 162, 0.1)); padding: 20px; border-radius: 10px; border: 1px solid rgba(102, 126, 234, 0.3);">
            <h3 style="color: #667eea; margin-bottom: 15px; display: flex; align-items: center; gap: 10px;">
                <span style="font-size: 24px;">💊</span>
                Plant Health Score
            </h3>
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 15px;">
    `;
    
    tags.forEach(tag => {
        const scores = calculateHealthScores(data, tag);
        if (!scores) return;
        
        const getScoreColor = (score) => {
            if (score >= 80) return '#34c759';
            if (score >= 60) return '#ff9500';
            return '#ff3b30';
        };
        
        html += `
            <div style="background: rgba(22, 33, 62, 0.8); padding: 15px; border-radius: 8px; border-left: 4px solid #667eea;">
                <div style="font-weight: bold; color: #00d4ff; margin-bottom: 12px; font-size: 14px;">${tag}</div>
                
                <div style="margin-bottom: 10px;">
                    <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
                        <span style="font-size: 12px; color: #888;">Stability Score</span>
                        <span style="font-weight: bold; color: ${getScoreColor(scores.stability)};">${scores.stability.toFixed(1)}%</span>
                    </div>
                    <div style="background: rgba(0, 0, 0, 0.3); height: 6px; border-radius: 3px; overflow: hidden;">
                        <div style="width: ${scores.stability}%; height: 100%; background: ${getScoreColor(scores.stability)}; transition: width 0.3s;"></div>
                    </div>
                </div>
                
                <div style="margin-bottom: 10px;">
                    <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
                        <span style="font-size: 12px; color: #888;">Variation Score</span>
                        <span style="font-weight: bold; color: ${getScoreColor(scores.variation)};">${scores.variation.toFixed(1)}%</span>
                    </div>
                    <div style="background: rgba(0, 0, 0, 0.3); height: 6px; border-radius: 3px; overflow: hidden;">
                        <div style="width: ${scores.variation}%; height: 100%; background: ${getScoreColor(scores.variation)}; transition: width 0.3s;"></div>
                    </div>
                </div>
                
                <div>
                    <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
                        <span style="font-size: 12px; color: #888;">Deviation Score</span>
                        <span style="font-weight: bold; color: ${getScoreColor(scores.deviation)};">${scores.deviation.toFixed(1)}%</span>
                    </div>
                    <div style="background: rgba(0, 0, 0, 0.3); height: 6px; border-radius: 3px; overflow: hidden;">
                        <div style="width: ${scores.deviation}%; height: 100%; background: ${getScoreColor(scores.deviation)}; transition: width 0.3s;"></div>
                    </div>
                </div>
            </div>
        `;
    });
    
    html += `</div></div>`;
    container.innerHTML = html;
    container.style.display = 'block';
}

// =====================================================
// 5. EVENT MARKERS
// =====================================================

/**
 * Add event marker
 */
function addEventMarker(timestamp, type, description) {
    eventMarkers.push({
        timestamp: new Date(timestamp),
        type: type, // 'trip', 'startup', 'shutdown', 'sootblowing', 'loadchange'
        description: description || ''
    });
    saveEventMarkersToStorage();
}

/**
 * Get event marker shapes for Plotly
 */
function getEventMarkerShapes() {
    const shapes = [];
    const annotations = [];
    
    eventMarkers.forEach(marker => {
        const icons = {
            trip: '⚠️',
            startup: '▶️',
            shutdown: '⏹️',
            sootblowing: '💨',
            loadchange: '⚡'
        };
        
        const colors = {
            trip: '#ff3b30',
            startup: '#34c759',
            shutdown: '#ff9500',
            sootblowing: '#00d4ff',
            loadchange: '#ffd700'
        };
        
        // Vertical line
        shapes.push({
            type: 'line',
            x0: marker.timestamp,
            x1: marker.timestamp,
            yref: 'paper',
            y0: 0,
            y1: 1,
            line: {
                color: colors[marker.type] || '#888',
                width: 2,
                dash: 'dash'
            }
        });
        
        // Annotation
        annotations.push({
            x: marker.timestamp,
            y: 1,
            yref: 'paper',
            text: `${icons[marker.type]} ${marker.description}`,
            showarrow: true,
            arrowhead: 2,
            arrowcolor: colors[marker.type] || '#888',
            ax: 0,
            ay: -40,
            bgcolor: 'rgba(0, 0, 0, 0.8)',
            bordercolor: colors[marker.type] || '#888',
            font: { color: '#fff', size: 10 }
        });
    });
    
    return { shapes, annotations };
}

/**
 * Show event marker modal
 */
function showEventMarkerModal() {
    const modal = document.createElement('div');
    modal.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0, 0, 0, 0.8);
        display: flex;
        justify-content: center;
        align-items: center;
        z-index: 10000;
    `;
    
    modal.innerHTML = `
        <div style="background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); padding: 30px; border-radius: 12px; border: 2px solid #00d4ff; max-width: 500px; width: 90%;">
            <h2 style="color: #00d4ff; margin-bottom: 20px;">📌 Add Event Marker</h2>
            
            <div style="display: grid; gap: 15px;">
                <div>
                    <label style="color: #888; display: block; margin-bottom: 5px;">Event Time:</label>
                    <input type="datetime-local" id="eventTime" style="width: 100%; background: rgba(15, 52, 96, 0.6); border: 1px solid #00d4ff; color: #fff; padding: 8px; border-radius: 4px;">
                </div>
                
                <div>
                    <label style="color: #888; display: block; margin-bottom: 5px;">Event Type:</label>
                    <select id="eventType" style="width: 100%; background: rgba(15, 52, 96, 0.6); border: 1px solid #00d4ff; color: #fff; padding: 8px; border-radius: 4px;">
                        <option value="trip">⚠️ Trip</option>
                        <option value="startup">▶️ Start-up</option>
                        <option value="shutdown">⏹️ Shutdown</option>
                        <option value="sootblowing">💨 Soot-blowing</option>
                        <option value="loadchange">⚡ Load Change</option>
                    </select>
                </div>
                
                <div>
                    <label style="color: #888; display: block; margin-bottom: 5px;">Description:</label>
                    <input type="text" id="eventDesc" placeholder="Optional description" style="width: 100%; background: rgba(15, 52, 96, 0.6); border: 1px solid #00d4ff; color: #fff; padding: 8px; border-radius: 4px;">
                </div>
            </div>
            
            <div style="display: flex; gap: 10px; margin-top: 25px;">
                <button id="saveEvent" style="flex: 1; padding: 12px; background: linear-gradient(135deg, #34c759, #30d158); border: none; color: white; font-weight: bold; border-radius: 6px; cursor: pointer;">
                    ✓ Add Marker
                </button>
                <button id="closeEvent" style="flex: 1; padding: 12px; background: rgba(255, 59, 48, 0.8); border: none; color: white; font-weight: bold; border-radius: 6px; cursor: pointer;">
                    ✕ Cancel
                </button>
            </div>
        </div>
    `;
    
    document.body.appendChild(modal);
    
    // Set current time as default
    const now = new Date();
    now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
    document.getElementById('eventTime').value = now.toISOString().slice(0, 16);
    
    document.getElementById('saveEvent').onclick = () => {
        const time = document.getElementById('eventTime').value;
        const type = document.getElementById('eventType').value;
        const desc = document.getElementById('eventDesc').value;
        
        if (time) {
            addEventMarker(time, type, desc);
            modal.remove();
            if (currentData) renderCombinedChart();
        }
    };
    
    document.getElementById('closeEvent').onclick = () => modal.remove();
    modal.onclick = (e) => { if (e.target === modal) modal.remove(); };
}

/**
 * Save event markers to localStorage
 */
function saveEventMarkersToStorage() {
    try {
        localStorage.setItem('eventMarkers', JSON.stringify(eventMarkers));
    } catch (e) {
        console.error('Failed to save event markers:', e);
    }
}

/**
 * Load event markers from localStorage
 */
function loadEventMarkersFromStorage() {
    try {
        const stored = localStorage.getItem('eventMarkers');
        if (stored) {
            eventMarkers = JSON.parse(stored).map(m => ({
                ...m,
                timestamp: new Date(m.timestamp)
            }));
        }
    } catch (e) {
        console.error('Failed to load event markers:', e);
    }
}

// =====================================================
// INITIALIZATION
// =====================================================

// Load saved configurations on module load
loadBandsFromStorage();
loadEventMarkersFromStorage();

// Export functions for use in other modules
if (typeof window !== 'undefined') {
    window.IndustrialFeatures = {
        renderOperatingBands,
        showBandConfigModal,
        renderShiftSummary,
        renderDataQualityIndicators,
        renderHealthScores,
        getEventMarkerShapes,
        showEventMarkerModal,
        calculateHealthScores,
        assessDataQuality
    };
}
