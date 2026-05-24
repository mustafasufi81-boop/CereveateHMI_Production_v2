// =====================================================
// DATA QUALITY & DOWNTIME MANAGEMENT SYSTEM
// For Power Plant Operations
// 
// CRITICAL: This module NEVER modifies original parquet data
// All interpolation is managed in external cache file
// =====================================================

/**
 * Data Quality Configuration
 * Stores rules for handling missing/invalid data
 * Data is managed externally - original parquet NEVER modified
 */
class DataQualityConfig {
    constructor() {
        this.config = this.loadConfig();
        this.useInterpolatedView = false; // Default: show RAW data
    }
    
    /**
     * Default configuration structure
     */
    getDefaultConfig() {
        // Use global appConfig if available, otherwise fallback to hardcoded defaults
        const globalConfig = window.appConfig?.DataQualitySettings || {};
        
        return {
            globalRules: {
                missingValueHandling: globalConfig.MissingValueHandling || 'ignore',
                interpolationMethod: globalConfig.InterpolationMethod || 'linear',
                downtimeThreshold: {
                    consecutiveMissing: globalConfig.DowntimeThreshold?.ConsecutiveMissing || 5,
                    durationMinutes: globalConfig.DowntimeThreshold?.DurationMinutes || 5
                },
                garbageDetection: {
                    enabled: globalConfig.GarbageDetection?.Enabled !== false,
                    unrealisticRangeMultiplier: globalConfig.GarbageDetection?.UnrealisticRangeMultiplier || 5,
                    constantValueDuration: globalConfig.GarbageDetection?.ConstantValueDuration || 10
                }
            },
            tagSpecificRules: {},
            downtimeRegister: [],
            repairLog: [],
            viewMode: 'raw'
        };
    }
    
    /**
     * Toggle view mode (raw vs interpolated)
     */
    toggleViewMode() {
        this.useInterpolatedView = !this.useInterpolatedView;
        this.config.viewMode = this.useInterpolatedView ? 'interpolated' : 'raw';
        this.saveConfig();
        return this.useInterpolatedView;
    }
    
    /**
     * Get current view mode
     */
    getViewMode() {
        return this.config.viewMode || 'raw';
    }
    
    /**
     * Load configuration from localStorage
     */
    loadConfig() {
        try {
            const stored = localStorage.getItem('dataQualityConfig');
            if (stored) {
                const config = JSON.parse(stored);
                this.useInterpolatedView = config.viewMode === 'interpolated';
                return config;
            }
        } catch (e) {
            console.error('Failed to load data quality config:', e);
        }
        return this.getDefaultConfig();
    }
    
    /**
     * Save configuration to localStorage
     */
    saveConfig() {
        try {
            localStorage.setItem('dataQualityConfig', JSON.stringify(this.config));
            console.log('✓ Data quality config saved');
            return true;
        } catch (e) {
            console.error('Failed to save data quality config:', e);
            return false;
        }
    }
    
    /**
     * Get rules for a specific tag (with fallback to global)
     */
    getTagRules(tagName) {
        if (this.config.tagSpecificRules[tagName]) {
            return { ...this.config.globalRules, ...this.config.tagSpecificRules[tagName] };
        }
        return this.config.globalRules;
    }
    
    /**
     * Set tag-specific rules
     */
    setTagRules(tagName, rules) {
        this.config.tagSpecificRules[tagName] = rules;
        this.saveConfig();
    }
    
    /**
     * Update global rules
     */
    updateGlobalRules(rules) {
        this.config.globalRules = { ...this.config.globalRules, ...rules };
        this.saveConfig();
    }
    
    /**
     * Add downtime event to register
     */
    registerDowntime(event) {
        this.config.downtimeRegister.push({
            id: Date.now(),
            startTime: event.startTime,
            endTime: event.endTime,
            duration: event.duration,
            affectedTags: event.affectedTags,
            reason: event.reason || 'Data unavailable',
            severity: event.severity || 'medium',
            timestamp: new Date().toISOString()
        });
        this.saveConfig();
    }
    
    /**
     * Add repair event to log
     */
    registerRepair(event) {
        this.config.repairLog.push({
            id: Date.now(),
            downtime: event.downtime,
            repairStartTime: event.repairStartTime,
            repairEndTime: event.repairEndTime,
            repairDuration: event.repairDuration,
            technician: event.technician || 'Auto-detected',
            notes: event.notes || '',
            timestamp: new Date().toISOString()
        });
        this.saveConfig();
    }
    
    /**
     * Get downtime statistics
     */
    getDowntimeStats(startDate, endDate) {
        const start = new Date(startDate).getTime();
        const end = new Date(endDate).getTime();
        
        const relevantDowntimes = this.config.downtimeRegister.filter(dt => {
            const dtStart = new Date(dt.startTime).getTime();
            const dtEnd = new Date(dt.endTime).getTime();
            return (dtStart >= start && dtStart <= end) || (dtEnd >= start && dtEnd <= end);
        });
        
        const totalDowntime = relevantDowntimes.reduce((sum, dt) => sum + (dt.duration || 0), 0);
        const totalRepairTime = this.config.repairLog
            .filter(r => {
                const repairStart = new Date(r.repairStartTime).getTime();
                return repairStart >= start && repairStart <= end;
            })
            .reduce((sum, r) => sum + (r.repairDuration || 0), 0);
        
        return {
            totalDowntimeEvents: relevantDowntimes.length,
            totalDowntimeMinutes: totalDowntime,
            totalRepairMinutes: totalRepairTime,
            downtimePercentage: (totalDowntime / ((end - start) / 60000)) * 100,
            events: relevantDowntimes
        };
    }
}

/**
 * Data Quality Processor
 * CRITICAL: Does NOT modify data - uses backend interpolation cache
 */
class DataQualityProcessor {
    constructor(config) {
        this.config = config;
    }
    
    /**
     * Create interpolation cache using backend API
     * Original parquet file is NEVER modified
     */
    async createInterpolationCache(startDate, endDate, tags) {
        const rules = this.config.getGlobalRules();
        
        try {
            const response = await fetch('/api/interpolation/create', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    start_date: startDate,
                    end_date: endDate,
                    tags: tags,
                    method: rules.interpolationMethod
                })
            });
            
            const result = await response.json();
            
            if (!result.success) {
                throw new Error(result.error);
            }
            
            console.log(`✓ Interpolation cache created:`);
            console.log(`  - ${result.interpolated_count} points interpolated`);
            console.log(`  - Cache file: ${result.cache_file}`);
            console.log(`  - Method: ${rules.interpolationMethod}`);
            
            return result;
        } catch (error) {
            console.error('Failed to create interpolation cache:', error);
            throw error;
        }
    }
    
    /**
     * Get interpolation cache statistics
     */
    async getCacheStats() {
        try {
            const response = await fetch('/api/interpolation/stats');
            const result = await response.json();
            
            if (!result.success) {
                throw new Error(result.error);
            }
            
            return result.stats;
        } catch (error) {
            console.error('Failed to get cache stats:', error);
            return null;
        }
    }
    
    /**
     * Clear interpolation cache
     */
    async clearCache(tags = null) {
        try {
            const response = await fetch('/api/interpolation/clear', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ tags })
            });
            
            const result = await response.json();
            
            if (!result.success) {
                throw new Error(result.error);
            }
            
            console.log(`✓ ${result.message}`);
            return result;
        } catch (error) {
            console.error('Failed to clear cache:', error);
            throw error;
        }
    }
    
    /**
     * Process data according to quality rules
     * Analyzes quality but does NOT modify data
     */
    processData(data, tags) {
        const processedData = [];
        const detectedDowntimes = [];
        const garbagePoints = [];
        
        tags.forEach(tag => {
            const rules = this.config.getTagRules(tag);
            const tagData = this.extractTagData(data, tag);
            
            // Analyze quality (read-only)
            const quality = this.analyzeDataQuality(tagData, tag, rules);
            
            // Detect downtimes (read-only)
            if (rules.missingValueHandling === 'downtime') {
                const downtimeEvents = this.detectDowntimeEvents(tagData, tag, rules);
                detectedDowntimes.push(...downtimeEvents);
            }
            
            processedData.push({ tag, data: tagData, quality });
        });
        
        // Register detected downtimes
        detectedDowntimes.forEach(dt => this.config.registerDowntime(dt));
        
        return {
            processedData,
            downtimes: detectedDowntimes,
            summary: this.generateQualitySummary(processedData)
        };
    }
    
    /**
     * Extract data for a specific tag
     */
    extractTagData(data, tag) {
        return data.map(row => ({
            timestamp: row.Timestamp,
            value: row[tag],
            raw: row
        }));
    }
    
    /**
     * Analyze data quality for a tag (read-only)
     */
    analyzeDataQuality(tagData, tagName, rules) {
        const total = tagData.length;
        const missing = tagData.filter(d => d.value === null || d.value === undefined || isNaN(d.value)).length;
        const valid = total - missing;
        
        // Detect garbage values
        const validValues = tagData.filter(d => d.value !== null && !isNaN(d.value)).map(d => d.value);
        const stats = this.calculateStats(validValues);
        
        let garbage = 0;
        let constantStuck = 0;
        
        if (rules.garbageDetection.enabled && stats) {
            // Detect unrealistic values (beyond 5x std dev)
            const threshold = rules.garbageDetection.unrealisticRangeMultiplier * stats.stdDev;
            garbage = validValues.filter(v => Math.abs(v - stats.mean) > threshold).length;
            
            // Detect stuck sensor (constant value)
            constantStuck = this.detectConstantValues(tagData, rules.garbageDetection.constantValueDuration);
        }
        
        return {
            tag: tagName,
            total,
            valid,
            missing,
            garbage,
            constantStuck,
            missingPercentage: (missing / total) * 100,
            garbagePercentage: (garbage / valid) * 100,
            quality: this.calculateQualityScore(valid, missing, garbage, total)
        };
    }
    
    /**
     * Calculate quality score (0-100)
     */
    calculateQualityScore(valid, missing, garbage, total) {
        const validScore = (valid / total) * 70;
        const garbagePenalty = (garbage / total) * 30;
        return Math.max(0, Math.min(100, validScore - garbagePenalty));
    }
    
    /**
     * Detect constant values (stuck sensor)
     */
    detectConstantValues(tagData, durationMinutes) {
        let constantCount = 0;
        let lastValue = null;
        let constantStart = null;
        
        tagData.forEach((point, idx) => {
            if (point.value === null || isNaN(point.value)) return;
            
            if (lastValue !== null && point.value === lastValue) {
                if (constantStart === null) {
                    constantStart = idx;
                }
                const duration = idx - constantStart;
                if (duration >= durationMinutes) {
                    constantCount++;
                }
            } else {
                constantStart = null;
            }
            
            lastValue = point.value;
        });
        
        return constantCount;
    }
    
    /**
     * Filter out invalid data points
     */
    filterValidData(tagData) {
        return tagData.filter(d => d.value !== null && d.value !== undefined && !isNaN(d.value));
    }
    
    /**
     * Detect downtime events (read-only analysis)
     */
    detectDowntimeEvents(tagData, tagName, rules) {
        const downtimes = [];
        let missingStart = null;
        let consecutiveMissing = 0;
        
        tagData.forEach((point, idx) => {
            const isMissing = point.value === null || point.value === undefined || isNaN(point.value);
            
            if (isMissing) {
                if (missingStart === null) {
                    missingStart = point.timestamp;
                }
                consecutiveMissing++;
            } else {
                // Check if we had a downtime
                if (consecutiveMissing >= rules.downtimeThreshold.consecutiveMissing) {
                    const endTime = point.timestamp;
                    const duration = (new Date(endTime) - new Date(missingStart)) / 60000; // minutes
                    
                    if (duration >= rules.downtimeThreshold.durationMinutes) {
                        downtimes.push({
                            tag: tagName,
                            startTime: missingStart,
                            endTime: endTime,
                            duration: duration,
                            missingPoints: consecutiveMissing,
                            type: 'auto-detected',
                            timestamp: new Date().toISOString()
                        });
                    }
                }
                
                missingStart = null;
                consecutiveMissing = 0;
            }
        });
        
        return downtimes;
    }
    
    /**
     * Detect and mark downtime periods
     */
    detectAndMarkDowntime(tagData, tagName, rules) {
        const downtimes = [];
        let missingCount = 0;
        let downtimeStart = null;
        
        tagData.forEach((point, idx) => {
            const isMissing = point.value === null || point.value === undefined || isNaN(point.value);
            
            if (isMissing) {
                if (downtimeStart === null) {
                    downtimeStart = point.timestamp;
                }
                missingCount++;
            } else {
                // Check if we just ended a downtime period
                if (missingCount >= rules.downtimeThreshold.consecutiveMissing) {
                    const downtimeEnd = point.timestamp;
                    const duration = (new Date(downtimeEnd) - new Date(downtimeStart)) / 60000; // minutes
                    
                    if (duration >= rules.downtimeThreshold.durationMinutes) {
                        downtimes.push({
                            startTime: downtimeStart,
                            endTime: downtimeEnd,
                            duration,
                            affectedTags: [tagName],
                            reason: `${missingCount} consecutive missing values`,
                            severity: duration > 60 ? 'high' : duration > 15 ? 'medium' : 'low'
                        });
                    }
                }
                
                missingCount = 0;
                downtimeStart = null;
            }
        });
        
        return { data: tagData, downtimes };
    }
    
    /**
     * Calculate basic statistics
     */
    calculateStats(values) {
        if (values.length === 0) return null;
        
        const mean = values.reduce((sum, v) => sum + v, 0) / values.length;
        const variance = values.reduce((sum, v) => sum + Math.pow(v - mean, 2), 0) / values.length;
        const stdDev = Math.sqrt(variance);
        
        return { mean, stdDev, min: Math.min(...values), max: Math.max(...values) };
    }
    
    /**
     * Generate quality summary report
     */
    generateQualitySummary(processedData) {
        const totalTags = processedData.length;
        const avgQuality = processedData.reduce((sum, p) => sum + p.quality.quality, 0) / totalTags;
        const poorQuality = processedData.filter(p => p.quality.quality < 60).length;
        const goodQuality = processedData.filter(p => p.quality.quality >= 80).length;
        
        return {
            totalTags,
            averageQuality: avgQuality.toFixed(1),
            poorQualityTags: poorQuality,
            goodQualityTags: goodQuality,
            recommendation: avgQuality >= 80 ? 'Excellent' : avgQuality >= 60 ? 'Acceptable' : 'Needs Attention'
        };
    }
}

// =====================================================
// UI FUNCTIONS
// =====================================================

/**
 * Show data quality configuration modal
 */
function showDataQualityConfigModal() {
    const config = new DataQualityConfig();
    const currentRules = config.config.globalRules;
    
    const modal = document.createElement('div');
    modal.id = 'dataQualityModal';
    modal.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0, 0, 0, 0.9);
        display: flex;
        justify-content: center;
        align-items: center;
        z-index: 10000;
        overflow-y: auto;
    `;
    
    modal.innerHTML = `
        <div style="background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); padding: 30px; border-radius: 12px; border: 2px solid #00d4ff; max-width: 800px; width: 90%; max-height: 90vh; overflow-y: auto;">
            <h2 style="color: #00d4ff; margin-bottom: 20px;">🔧 Data Quality & Downtime Configuration</h2>
            
            <div style="background: rgba(0, 212, 255, 0.1); padding: 15px; border-radius: 8px; margin-bottom: 20px; border-left: 4px solid #00d4ff;">
                <h3 style="color: #00d4ff; margin-bottom: 10px;">ℹ️ Configuration Purpose</h3>
                <p style="color: #e0e0e0; font-size: 13px; line-height: 1.6;">
                    This configuration determines how the system handles missing, invalid, or garbage data values.
                    Set these rules ONCE and they will be applied automatically to all future data loads.
                </p>
            </div>
            
            <!-- Missing Value Handling -->
            <div style="margin-bottom: 25px;">
                <h3 style="color: #00ff88; margin-bottom: 15px;">1️⃣ Missing Value Handling</h3>
                <label style="color: #888; display: block; margin-bottom: 8px;">When data is missing or unavailable:</label>
                <select id="missingValueHandling" style="width: 100%; background: rgba(15, 52, 96, 0.6); border: 1px solid #00d4ff; color: #fff; padding: 10px; border-radius: 4px; font-size: 14px; margin-bottom: 10px;">
                    <option value="ignore" ${currentRules.missingValueHandling === 'ignore' ? 'selected' : ''}>Ignore - Skip missing values (show gaps in chart)</option>
                    <option value="interpolate" ${currentRules.missingValueHandling === 'interpolate' ? 'selected' : ''}>Interpolate - Fill gaps using mathematical methods</option>
                    <option value="downtime" ${currentRules.missingValueHandling === 'downtime' ? 'selected' : ''}>Mark as Downtime - Register as system failure</option>
                </select>
                <div style="font-size: 12px; color: #666; font-style: italic;">
                    💡 Recommended: "Mark as Downtime" for critical plant monitoring
                </div>
            </div>
            
            <!-- Interpolation Method -->
            <div id="interpolationSection" style="margin-bottom: 25px; ${currentRules.missingValueHandling === 'interpolate' ? '' : 'display: none;'}">
                <h3 style="color: #00ff88; margin-bottom: 15px;">2️⃣ Interpolation Method</h3>
                <label style="color: #888; display: block; margin-bottom: 8px;">How to fill missing values:</label>
                <select id="interpolationMethod" style="width: 100%; background: rgba(15, 52, 96, 0.6); border: 1px solid #00d4ff; color: #fff; padding: 10px; border-radius: 4px; font-size: 14px; margin-bottom: 10px;">
                    <option value="linear" ${currentRules.interpolationMethod === 'linear' ? 'selected' : ''}>Linear - Straight line between points (smooth)</option>
                    <option value="forward" ${currentRules.interpolationMethod === 'forward' ? 'selected' : ''}>Forward Fill - Use last known value</option>
                    <option value="backward" ${currentRules.interpolationMethod === 'backward' ? 'selected' : ''}>Backward Fill - Use next known value</option>
                    <option value="mean" ${currentRules.interpolationMethod === 'mean' ? 'selected' : ''}>Mean Fill - Use average of all values</option>
                </select>
                <div style="font-size: 12px; color: #666; font-style: italic;">
                    💡 Linear is best for smooth trends, Forward Fill for step changes
                </div>
            </div>
            
            <!-- Downtime Detection -->
            <div id="downtimeSection" style="margin-bottom: 25px; ${currentRules.missingValueHandling === 'downtime' ? '' : 'display: none;'}">
                <h3 style="color: #00ff88; margin-bottom: 15px;">3️⃣ Downtime Detection Thresholds</h3>
                
                <label style="color: #888; display: block; margin-bottom: 5px;">Consecutive Missing Points to Mark as Downtime:</label>
                <input type="number" id="consecutiveMissing" value="${currentRules.downtimeThreshold.consecutiveMissing}" min="1" max="100" 
                    style="width: 100%; background: rgba(15, 52, 96, 0.6); border: 1px solid #00d4ff; color: #fff; padding: 8px; border-radius: 4px; margin-bottom: 15px;">
                
                <label style="color: #888; display: block; margin-bottom: 5px;">Minimum Duration (minutes):</label>
                <input type="number" id="durationMinutes" value="${currentRules.downtimeThreshold.durationMinutes}" min="1" max="120" 
                    style="width: 100%; background: rgba(15, 52, 96, 0.6); border: 1px solid #00d4ff; color: #fff; padding: 8px; border-radius: 4px; margin-bottom: 10px;">
                
                <div style="font-size: 12px; color: #666; font-style: italic;">
                    ⚠️ System will register downtime only if BOTH conditions are met
                </div>
            </div>
            
            <!-- Garbage Detection -->
            <div style="margin-bottom: 25px;">
                <h3 style="color: #00ff88; margin-bottom: 15px;">4️⃣ Garbage Value Detection</h3>
                
                <label style="display: flex; align-items: center; gap: 10px; margin-bottom: 15px; cursor: pointer;">
                    <input type="checkbox" id="garbageEnabled" ${currentRules.garbageDetection.enabled ? 'checked' : ''} 
                        style="width: 20px; height: 20px; cursor: pointer;">
                    <span style="color: #e0e0e0;">Enable automatic garbage value detection</span>
                </label>
                
                <div id="garbageOptions" style="${currentRules.garbageDetection.enabled ? '' : 'opacity: 0.5; pointer-events: none;'}">
                    <label style="color: #888; display: block; margin-bottom: 5px;">Unrealistic Range Multiplier (x Std Dev):</label>
                    <input type="number" id="unrealisticRange" value="${currentRules.garbageDetection.unrealisticRangeMultiplier}" min="2" max="10" step="0.5"
                        style="width: 100%; background: rgba(15, 52, 96, 0.6); border: 1px solid #00d4ff; color: #fff; padding: 8px; border-radius: 4px; margin-bottom: 15px;">
                    
                    <label style="color: #888; display: block; margin-bottom: 5px;">Stuck Sensor Duration (minutes of constant value):</label>
                    <input type="number" id="constantDuration" value="${currentRules.garbageDetection.constantValueDuration}" min="5" max="60"
                        style="width: 100%; background: rgba(15, 52, 96, 0.6); border: 1px solid #00d4ff; color: #fff; padding: 8px; border-radius: 4px; margin-bottom: 10px;">
                    
                    <div style="font-size: 12px; color: #666; font-style: italic;">
                        🔍 Values beyond 5× standard deviation will be marked as garbage
                    </div>
                </div>
            </div>
            
            <!-- Current Stats -->
            <div style="background: rgba(0, 212, 255, 0.05); padding: 15px; border-radius: 8px; margin-bottom: 20px;">
                <h3 style="color: #ffd700; margin-bottom: 10px;">📊 Current Downtime Register</h3>
                <div style="color: #e0e0e0; font-size: 13px;">
                    <div>Total Downtime Events: <strong>${config.config.downtimeRegister.length}</strong></div>
                    <div>Total Repair Logs: <strong>${config.config.repairLog.length}</strong></div>
                </div>
                <button id="viewDowntimeLog" style="margin-top: 10px; padding: 8px 15px; background: rgba(255, 215, 0, 0.2); border: 1px solid #ffd700; color: #ffd700; border-radius: 4px; cursor: pointer; font-size: 13px;">
                    📋 View Downtime Log
                </button>
            </div>
            
            <!-- Action Buttons -->
            <div style="display: flex; gap: 10px; margin-top: 25px;">
                <button id="saveConfig" style="flex: 1; padding: 12px; background: linear-gradient(135deg, #34c759, #30d158); border: none; color: white; font-weight: bold; border-radius: 6px; cursor: pointer; font-size: 15px;">
                    ✓ Save Configuration
                </button>
                <button id="resetConfig" style="flex: 1; padding: 12px; background: rgba(255, 149, 0, 0.8); border: none; color: white; font-weight: bold; border-radius: 6px; cursor: pointer; font-size: 15px;">
                    ↻ Reset to Default
                </button>
                <button id="closeConfig" style="flex: 1; padding: 12px; background: rgba(255, 59, 48, 0.8); border: none; color: white; font-weight: bold; border-radius: 6px; cursor: pointer; font-size: 15px;">
                    ✕ Cancel
                </button>
            </div>
        </div>
    `;
    
    document.body.appendChild(modal);
    
    // Event handlers
    document.getElementById('missingValueHandling').addEventListener('change', (e) => {
        document.getElementById('interpolationSection').style.display = e.target.value === 'interpolate' ? 'block' : 'none';
        document.getElementById('downtimeSection').style.display = e.target.value === 'downtime' ? 'block' : 'none';
    });
    
    document.getElementById('garbageEnabled').addEventListener('change', (e) => {
        document.getElementById('garbageOptions').style.opacity = e.target.checked ? '1' : '0.5';
        document.getElementById('garbageOptions').style.pointerEvents = e.target.checked ? 'auto' : 'none';
    });
    
    document.getElementById('saveConfig').onclick = () => {
        const newConfig = {
            missingValueHandling: document.getElementById('missingValueHandling').value,
            interpolationMethod: document.getElementById('interpolationMethod').value,
            downtimeThreshold: {
                consecutiveMissing: parseInt(document.getElementById('consecutiveMissing').value),
                durationMinutes: parseInt(document.getElementById('durationMinutes').value)
            },
            garbageDetection: {
                enabled: document.getElementById('garbageEnabled').checked,
                unrealisticRangeMultiplier: parseFloat(document.getElementById('unrealisticRange').value),
                constantValueDuration: parseInt(document.getElementById('constantDuration').value)
            }
        };
        
        config.updateGlobalRules(newConfig);
        alert('✓ Data quality configuration saved!\n\nThese rules will be applied automatically to all future data loads.');
        modal.remove();
        
        // Trigger data reload if data exists
        if (typeof currentData !== 'undefined' && currentData) {
            loadTrendData();
        }
    };
    
    document.getElementById('resetConfig').onclick = () => {
        if (confirm('Reset to default configuration?')) {
            config.config = config.getDefaultConfig();
            config.saveConfig();
            modal.remove();
            showDataQualityConfigModal();
        }
    };
    
    document.getElementById('viewDowntimeLog').onclick = () => {
        showDowntimeLogModal(config);
    };
    
    document.getElementById('closeConfig').onclick = () => modal.remove();
    modal.onclick = (e) => { if (e.target === modal) modal.remove(); };
}

/**
 * Show downtime log modal
 */
function showDowntimeLogModal(config) {
    const modal = document.createElement('div');
    modal.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0, 0, 0, 0.9);
        display: flex;
        justify-content: center;
        align-items: center;
        z-index: 10001;
    `;
    
    const downtimes = config.config.downtimeRegister.slice().reverse(); // Most recent first
    
    let html = `
        <div style="background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); padding: 30px; border-radius: 12px; border: 2px solid #ffd700; max-width: 900px; width: 90%; max-height: 80vh; overflow-y: auto;">
            <h2 style="color: #ffd700; margin-bottom: 20px;">📋 Downtime Register</h2>
            
            <div style="margin-bottom: 20px; background: rgba(255, 215, 0, 0.1); padding: 15px; border-radius: 8px;">
                <h3 style="color: #ffd700;">Total Events: ${downtimes.length}</h3>
                <p style="color: #e0e0e0; font-size: 13px; margin-top: 10px;">
                    Total Downtime: ${(downtimes.reduce((sum, dt) => sum + (dt.duration || 0), 0) / 60).toFixed(1)} hours
                </p>
            </div>
            
            <div style="max-height: 500px; overflow-y: auto;">
    `;
    
    if (downtimes.length === 0) {
        html += '<div style="text-align: center; color: #888; padding: 40px;">No downtime events recorded</div>';
    } else {
        downtimes.forEach((dt, idx) => {
            const severityColor = dt.severity === 'high' ? '#ff3b30' : dt.severity === 'medium' ? '#ff9500' : '#ffd700';
            html += `
                <div style="background: rgba(0, 0, 0, 0.3); padding: 15px; margin-bottom: 10px; border-radius: 6px; border-left: 4px solid ${severityColor};">
                    <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
                        <span style="color: ${severityColor}; font-weight: bold;">Event #${downtimes.length - idx}</span>
                        <span style="color: #888; font-size: 12px;">${new Date(dt.timestamp).toLocaleString()}</span>
                    </div>
                    <div style="color: #e0e0e0; font-size: 13px; line-height: 1.6;">
                        <div><strong>Start:</strong> ${new Date(dt.startTime).toLocaleString()}</div>
                        <div><strong>End:</strong> ${new Date(dt.endTime).toLocaleString()}</div>
                        <div><strong>Duration:</strong> ${dt.duration.toFixed(1)} minutes</div>
                        <div><strong>Affected Tags:</strong> ${dt.affectedTags.join(', ')}</div>
                        <div><strong>Reason:</strong> ${dt.reason}</div>
                    </div>
                </div>
            `;
        });
    }
    
    html += `
            </div>
            
            <div style="display: flex; gap: 10px; margin-top: 20px;">
                <button id="exportDowntime" style="flex: 1; padding: 10px; background: rgba(0, 212, 255, 0.8); border: none; color: white; font-weight: bold; border-radius: 6px; cursor: pointer;">
                    💾 Export to CSV
                </button>
                <button id="clearDowntime" style="flex: 1; padding: 10px; background: rgba(255, 59, 48, 0.8); border: none; color: white; font-weight: bold; border-radius: 6px; cursor: pointer;">
                    🗑️ Clear All
                </button>
                <button id="closeDowntimeLog" style="flex: 1; padding: 10px; background: rgba(0, 0, 0, 0.5); border: 1px solid #888; color: white; font-weight: bold; border-radius: 6px; cursor: pointer;">
                    ✕ Close
                </button>
            </div>
        </div>
    `;
    
    modal.innerHTML = html;
    document.body.appendChild(modal);
    
    document.getElementById('exportDowntime').onclick = () => {
        const csv = 'Event,Start,End,Duration (min),Tags,Reason,Severity\n' +
            downtimes.map((dt, idx) => 
                `${downtimes.length - idx},${dt.startTime},${dt.endTime},${dt.duration},${dt.affectedTags.join(';')},${dt.reason},${dt.severity}`
            ).join('\n');
        
        const blob = new Blob([csv], { type: 'text/csv' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `downtime_register_${new Date().toISOString().slice(0,10)}.csv`;
        a.click();
    };
    
    document.getElementById('clearDowntime').onclick = () => {
        if (confirm('⚠️ Clear all downtime records? This cannot be undone!')) {
            config.config.downtimeRegister = [];
            config.saveConfig();
            modal.remove();
        }
    };
    
    document.getElementById('closeDowntimeLog').onclick = () => modal.remove();
    modal.onclick = (e) => { if (e.target === modal) modal.remove(); };
}

// Export for use in other modules
if (typeof window !== 'undefined') {
    window.DataQualityConfig = DataQualityConfig;
    window.DataQualityProcessor = DataQualityProcessor;
    window.showDataQualityConfigModal = showDataQualityConfigModal;
    window.showDowntimeLogModal = showDowntimeLogModal;
}
