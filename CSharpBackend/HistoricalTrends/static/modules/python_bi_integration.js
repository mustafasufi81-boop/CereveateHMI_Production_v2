// =====================================================
// BI Dashboard - Python Backend Integration
// Replace JavaScript engine with REST API calls
// =====================================================

/**
 * Configuration for Python backend API
 */
const BI_API_CONFIG = {
    baseUrl: `${window.location.origin}/api/v1`,
    timeout: 60000  // 60 seconds
};

/**
 * Call Python backend for full BI analysis
 * 
 * @param {Array} data - Time-series data
 * @param {string} productionTag - Main production tag
 * @param {Array} influencingTags - List of influencing tags
 * @param {number} ratedCapacity - Plant rated capacity
 * @returns {Promise} Analysis results
 */
async function runPythonBIAnalysis(data, productionTag, influencingTags, ratedCapacity) {
    console.log('🐍 Calling Python BI Engine API...');
    console.log(`  Data points: ${data.length}`);
    console.log(`  Production tag: ${productionTag}`);
    console.log(`  Influencing tags: ${influencingTags.length}`);
    
    const startTime = performance.now();
    
    try {
        const response = await fetch(`${BI_API_CONFIG.baseUrl}/analyze/full`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                data: data,
                production_tag: productionTag,
                influencing_tags: influencingTags,
                rated_capacity: ratedCapacity
            }),
            signal: AbortSignal.timeout(BI_API_CONFIG.timeout)
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || `HTTP ${response.status}`);
        }
        
        const result = await response.json();
        
        const elapsed = performance.now() - startTime;
        console.log(`✅ Python BI analysis complete in ${elapsed.toFixed(0)}ms`);
        
        return result.results;
        
    } catch (error) {
        console.error('❌ Python BI API error:', error);
        
        if (error.name === 'AbortError') {
            throw new Error('Analysis timeout - dataset too large');
        }
        
        throw error;
    }
}

/**
 * Calculate baseline only (faster endpoint)
 */
async function calculateBaselinePython(data, tag) {
    console.log(`📊 Calculating baseline for ${tag} via Python...`);
    
    try {
        const response = await fetch(`${BI_API_CONFIG.baseUrl}/calculate/baseline`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({data, tag})
        });
        
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        const result = await response.json();
        return result.baseline;
        
    } catch (error) {
        console.error('❌ Baseline API error:', error);
        throw error;
    }
}

/**
 * Calculate influence map only
 */
async function calculateInfluenceMapPython(data, primaryTag, influencingTags) {
    console.log(`🔗 Calculating influence map via Python...`);
    
    try {
        const response = await fetch(`${BI_API_CONFIG.baseUrl}/calculate/influence_map`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                data,
                primary_tag: primaryTag,
                influencing_tags: influencingTags
            })
        });
        
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        const result = await response.json();
        return result.influence_map;
        
    } catch (error) {
        console.error('❌ Influence map API error:', error);
        throw error;
    }
}

/**
 * Calculate availability metrics only
 */
async function calculateAvailabilityPython(data, loadCol, ratedCapacity) {
    console.log(`📈 Calculating availability via Python...`);
    
    try {
        const response = await fetch(`${BI_API_CONFIG.baseUrl}/calculate/availability`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                data,
                load_col: loadCol,
                rated_capacity: ratedCapacity
            })
        });
        
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        const result = await response.json();
        return result.availability;
        
    } catch (error) {
        console.error('❌ Availability API error:', error);
        throw error;
    }
}

/**
 * Invalidate Python backend cache
 */
async function invalidatePythonCache(operation = null) {
    try {
        const url = operation 
            ? `${BI_API_CONFIG.baseUrl}/cache/invalidate?operation=${operation}`
            : `${BI_API_CONFIG.baseUrl}/cache/invalidate`;
        
        const response = await fetch(url, {method: 'POST'});
        
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        console.log('✓ Python cache invalidated');
        
    } catch (error) {
        console.error('❌ Cache invalidation error:', error);
    }
}

/**
 * Get Python backend cache statistics
 */
async function getPythonCacheStats() {
    try {
        const response = await fetch(`${BI_API_CONFIG.baseUrl}/cache/stats`);
        
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        const result = await response.json();
        return result.cache_stats;
        
    } catch (error) {
        console.error('❌ Cache stats error:', error);
        return null;
    }
}

/**
 * Check if Python backend is available
 */
async function checkPythonBackendHealth() {
    try {
        const response = await fetch(`${BI_API_CONFIG.baseUrl.replace('/api/v1', '')}/health`, {
            signal: AbortSignal.timeout(5000)
        });
        
        if (!response.ok) return false;
        
        const result = await response.json();
        return result.status === 'healthy';
        
    } catch (error) {
        console.warn('⚠️ Python backend not available:', error.message);
        return false;
    }
}

// =====================================================
// INTEGRATION WITH EXISTING DASHBOARD
// =====================================================

/**
 * Modified openAdvancedBIDashboard to use Python backend
 */
async function openAdvancedBIDashboardPython() {
    console.log('🚀 Opening Advanced BI Dashboard (Python Backend)...');
    
    // Check if Python backend is available
    const isBackendAvailable = await checkPythonBackendHealth();
    
    if (!isBackendAvailable) {
        alert('⚠️ Python BI backend not available. Please start: python bi_api.py');
        return;
    }
    
    // Get current trend data
    if (!window.currentTrendData || window.currentTrendData.length === 0) {
        alert('⚠️ No trend data loaded. Please load data first.');
        return;
    }
    
    // Get selected tags
    const selectedTags = Array.from(document.querySelectorAll('.tag-item.selected'))
        .map(item => item.dataset.tag);
    
    if (selectedTags.length < 2) {
        alert('⚠️ Please select at least 2 tags (1 production + 1 influencing parameter)');
        return;
    }
    
    // Auto-detect production tag (first selected or 'Load')
    const productionTag = selectedTags.find(t => 
        t.toLowerCase().includes('load') || 
        t.toLowerCase().includes('mw') ||
        t.toLowerCase().includes('power')
    ) || selectedTags[0];
    
    const influencingTags = selectedTags.filter(t => t !== productionTag);
    
    // Get rated capacity from user
    const ratedCapacity = parseFloat(
        localStorage.getItem('plant_rated_capacity') ||
        prompt('Enter plant rated capacity (MW):', '660')
    );
    
    if (!ratedCapacity || ratedCapacity <= 0) {
        alert('❌ Invalid rated capacity');
        return;
    }
    
    // Save for future use
    localStorage.setItem('plant_rated_capacity', ratedCapacity);
    
    // Show loading overlay
    showLoadingOverlay('Analyzing via Python backend...');
    
    try {
        // Call Python backend
        const results = await runPythonBIAnalysis(
            window.currentTrendData,
            productionTag,
            influencingTags,
            ratedCapacity
        );
        
        // Display results in dashboard
        displayBIResultsPython(results);
        
    } catch (error) {
        console.error('❌ BI Analysis failed:', error);
        alert(`Analysis Error: ${error.message}`);
    } finally {
        hideLoadingOverlay();
    }
}

/**
 * Display Python backend results in dashboard
 */
function displayBIResultsPython(results) {
    console.log('📊 Displaying Python BI results...');
    
    // Create results HTML
    const html = `
        <div class="bi-results-python">
            <h2>🐍 BI Analysis Results (Python Backend)</h2>
            
            <div class="bi-summary">
                <h3>Executive Summary</h3>
                <div class="summary-grid">
                    <div class="metric">
                        <span class="label">Baseline Production:</span>
                        <span class="value">${results.summary.baseline_production.toFixed(2)} MW</span>
                    </div>
                    <div class="metric">
                        <span class="label">Availability:</span>
                        <span class="value">${results.summary.availability_percentage.toFixed(1)}%</span>
                    </div>
                    <div class="metric">
                        <span class="label">Stability:</span>
                        <span class="value">${results.summary.stability_index.toFixed(3)} (${results.stability.rating})</span>
                    </div>
                    <div class="metric">
                        <span class="label">Total Loss:</span>
                        <span class="value">${results.summary.total_loss_mw.toFixed(2)} MW</span>
                    </div>
                </div>
            </div>
            
            <div class="bi-section">
                <h3>🔗 Top Influencing Parameters</h3>
                <table class="influence-table">
                    <thead>
                        <tr>
                            <th>Parameter</th>
                            <th>Correlation</th>
                            <th>Impact %</th>
                            <th>Relationship</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${Object.entries(results.influence_map)
                            .sort((a, b) => Math.abs(b[1].pearson) - Math.abs(a[1].pearson))
                            .slice(0, 5)
                            .map(([param, metrics]) => `
                                <tr>
                                    <td>${param}</td>
                                    <td>${metrics.pearson.toFixed(3)}</td>
                                    <td>${metrics.impact_percentage.toFixed(2)}%</td>
                                    <td>${metrics.relationship}</td>
                                </tr>
                            `).join('')}
                    </tbody>
                </table>
            </div>
            
            <div class="bi-section">
                <h3>🔍 Loss Attribution</h3>
                <table class="loss-table">
                    <thead>
                        <tr>
                            <th>Parameter</th>
                            <th>Loss (MW)</th>
                            <th>Loss %</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${results.loss_attribution.top_contributors
                            .map(contrib => `
                                <tr>
                                    <td>${contrib.parameter}</td>
                                    <td>${contrib.loss_amount.toFixed(2)}</td>
                                    <td>${contrib.loss_percentage.toFixed(1)}%</td>
                                </tr>
                            `).join('')}
                    </tbody>
                </table>
            </div>
        </div>
    `;
    
    // Insert into DOM (adjust selector to your dashboard container)
    const container = document.getElementById('bi-dashboard-container') || document.body;
    container.innerHTML = html;
}

// Export for use
window.runPythonBIAnalysis = runPythonBIAnalysis;
window.openAdvancedBIDashboardPython = openAdvancedBIDashboardPython;
window.checkPythonBackendHealth = checkPythonBackendHealth;

console.log('✓ Python BI Backend integration loaded');
