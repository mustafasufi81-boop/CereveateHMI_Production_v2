/**
 * High-Performance Trend Engine - SCADA Style
 * Modular trend handling with smooth scrolling and time navigation
 * NO data manipulation - shows exact raw values
 */

class TrendEngine {
    constructor(canvasId) {
        this.canvas = document.getElementById(canvasId);
        this.ctx = this.canvas.getContext('2d');
        this.chart = null;
        
        // Trend configuration
        this.config = {
            maxLivePoints: 1000,
            maxHistoricalPoints: 50000,
            updateInterval: 1000,
            smoothScroll: true,
            autoScale: true
        };
        
        // Time navigation state
        this.timeNav = {
            mode: 'live', // 'live' or 'historical'
            currentTime: null,
            startTime: null,
            endTime: null,
            range: 3600, // seconds (1 hour default)
            isPaused: false,
            scrollPosition: 0
        };
        
        // Data buffers (raw values only - no processing)
        this.liveBuffer = new Map(); // tagId -> [{timestamp, value, quality}]
        this.historicalCache = new Map(); // tagId -> [{timestamp, value, quality}]
        
        // Active tags
        this.activeTags = new Set();
        
        this.initializeChart();
        this.setupKeyboardShortcuts();
    }
    
    /**
     * Initialize Chart.js with high-performance settings
     */
    initializeChart() {
        const ctx = this.canvas.getContext('2d');
        
        this.chart = new Chart(ctx, {
            type: 'line',
            data: {
                datasets: []
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: false, // Disable for performance
                parsing: false, // Disable automatic parsing
                normalized: true, // Pre-sorted data
                spanGaps: true, // Connect gaps
                interaction: {
                    mode: 'nearest',
                    axis: 'x',
                    intersect: false
                },
                plugins: {
                    legend: {
                        display: true,
                        position: 'top',
                        labels: {
                            usePointStyle: true,
                            font: { size: 11 }
                        }
                    },
                    tooltip: {
                        enabled: true,
                        mode: 'index',
                        intersect: false,
                        callbacks: {
                            title: (items) => {
                                if (items.length > 0) {
                                    const timestamp = items[0].parsed.x;
                                    return new Date(timestamp).toLocaleString();
                                }
                                return '';
                            },
                            label: (context) => {
                                const label = context.dataset.label || '';
                                const value = context.parsed.y.toFixed(4);
                                return `${label}: ${value}`;
                            }
                        }
                    },
                    zoom: {
                        pan: {
                            enabled: true,
                            mode: 'x',
                            modifierKey: 'shift',
                            onPanComplete: (ctx) => this.onPanComplete(ctx)
                        },
                        zoom: {
                            wheel: {
                                enabled: true,
                                speed: 0.1
                            },
                            pinch: {
                                enabled: true
                            },
                            mode: 'x',
                            onZoomComplete: (ctx) => this.onZoomComplete(ctx)
                        }
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
                                day: 'MMM DD',
                                week: 'MMM DD',
                                month: 'MMM YYYY',
                                quarter: 'MMM YYYY',
                                year: 'YYYY'
                            }
                        },
                        ticks: {
                            source: 'auto',
                            maxRotation: 0,
                            autoSkip: true,
                            font: { size: 10 }
                        },
                        grid: {
                            display: true,
                            color: 'rgba(255, 255, 255, 0.1)'
                        }
                    },
                    y: {
                        type: 'linear',
                        position: 'left',
                        ticks: {
                            font: { size: 10 }
                        },
                        grid: {
                            display: true,
                            color: 'rgba(255, 255, 255, 0.1)'
                        }
                    }
                }
            }
        });
    }
    
    /**
     * Add live data point (exact value, no processing)
     */
    addLivePoint(tagId, timestamp, value, quality) {
        if (!this.activeTags.has(tagId)) return;
        
        if (!this.liveBuffer.has(tagId)) {
            this.liveBuffer.set(tagId, []);
        }
        
        const buffer = this.liveBuffer.get(tagId);
        
        // Add exact raw value
        buffer.push({
            x: new Date(timestamp).getTime(),
            y: parseFloat(value), // Exact value
            quality: quality
        });
        
        // Keep only max points (FIFO)
        if (buffer.length > this.config.maxLivePoints) {
            buffer.shift();
        }
        
        // Update chart if in live mode
        if (this.timeNav.mode === 'live' && !this.timeNav.isPaused) {
            this.updateLiveChart();
        }
    }
    
    /**
     * Load historical data (exact values from DB query)
     */
    async loadHistoricalData(tagId, startTime, endTime) {
        try {
            const response = await fetch(
                `/api/historical/${encodeURIComponent(tagId)}?` +
                `start=${startTime.toISOString()}&` +
                `end=${endTime.toISOString()}&` +
                `mode=raw` // CRITICAL: Request raw data, no aggregation
            );
            
            const data = await response.json();
            
            if (data.data && data.data.length > 0) {
                // Store exact raw values
                const points = data.data.map(point => ({
                    x: new Date(point.timestamp).getTime(),
                    y: parseFloat(point.value), // Exact value from DB
                    quality: point.quality
                }));
                
                this.historicalCache.set(tagId, points);
                
                console.log(`✅ Loaded ${points.length} raw points for ${tagId}`);
                return points;
            }
            
            return [];
        } catch (error) {
            console.error(`❌ Historical load error for ${tagId}:`, error);
            return [];
        }
    }
    
    /**
     * Update live chart (smooth animation)
     */
    updateLiveChart() {
        const datasets = [];
        const colors = [
            '#3498db', '#e74c3c', '#2ecc71', '#f39c12', '#9b59b6',
            '#1abc9c', '#34495e', '#e67e22'
        ];
        
        let colorIndex = 0;
        
        for (const tagId of this.activeTags) {
            const buffer = this.liveBuffer.get(tagId);
            if (buffer && buffer.length > 0) {
                const color = colors[colorIndex % colors.length];
                
                datasets.push({
                    label: `${tagId} (Live)`,
                    data: buffer, // Raw data points
                    borderColor: color,
                    backgroundColor: color,
                    borderWidth: 2,
                    pointRadius: 0, // No points for smooth line
                    pointHoverRadius: 4,
                    tension: 0, // No smoothing - exact values
                    fill: false
                });
                
                colorIndex++;
            }
        }
        
        this.chart.data.datasets = datasets;
        this.chart.update('none'); // No animation for performance
    }
    
    /**
     * Update historical chart
     */
    updateHistoricalChart() {
        const datasets = [];
        const colors = [
            '#3498db', '#e74c3c', '#2ecc71', '#f39c12', '#9b59b6',
            '#1abc9c', '#34495e', '#e67e22'
        ];
        
        let colorIndex = 0;
        
        for (const tagId of this.activeTags) {
            const points = this.historicalCache.get(tagId);
            if (points && points.length > 0) {
                const color = colors[colorIndex % colors.length];
                
                datasets.push({
                    label: `${tagId} (Historical)`,
                    data: points, // Raw historical data
                    borderColor: color,
                    backgroundColor: color,
                    borderWidth: 2,
                    pointRadius: 0,
                    pointHoverRadius: 4,
                    tension: 0, // Exact values
                    fill: false
                });
                
                colorIndex++;
            }
        }
        
        this.chart.data.datasets = datasets;
        this.chart.update('none');
    }
    
    /**
     * Switch to live mode
     */
    switchToLive() {
        this.timeNav.mode = 'live';
        this.timeNav.isPaused = false;
        this.updateLiveChart();
        console.log('📡 Switched to LIVE mode');
    }
    
    /**
     * Switch to historical mode
     */
    async switchToHistorical(hours = 1) {
        this.timeNav.mode = 'historical';
        this.timeNav.isPaused = true;
        
        const endTime = new Date();
        const startTime = new Date(endTime.getTime() - (hours * 3600 * 1000));
        
        this.timeNav.startTime = startTime;
        this.timeNav.endTime = endTime;
        this.timeNav.range = hours * 3600;
        
        // Load data for all active tags
        for (const tagId of this.activeTags) {
            await this.loadHistoricalData(tagId, startTime, endTime);
        }
        
        this.updateHistoricalChart();
        console.log(`📜 Switched to HISTORICAL mode (${hours}h)`);
    }
    
    /**
     * Navigate backward in time (smooth scroll)
     */
    async navigateBackward(seconds = 3600) {
        if (this.timeNav.mode !== 'historical') return;
        
        const newEndTime = new Date(this.timeNav.startTime.getTime());
        const newStartTime = new Date(newEndTime.getTime() - (seconds * 1000));
        
        this.timeNav.startTime = newStartTime;
        this.timeNav.endTime = newEndTime;
        
        // Load data
        for (const tagId of this.activeTags) {
            await this.loadHistoricalData(tagId, newStartTime, newEndTime);
        }
        
        this.updateHistoricalChart();
        console.log(`⏪ Navigated backward to ${newStartTime.toLocaleString()}`);
    }
    
    /**
     * Navigate forward in time
     */
    async navigateForward(seconds = 3600) {
        if (this.timeNav.mode !== 'historical') return;
        
        const newStartTime = new Date(this.timeNav.endTime.getTime());
        const newEndTime = new Date(newStartTime.getTime() + (seconds * 1000));
        const now = new Date();
        
        // Don't go beyond current time
        if (newEndTime > now) {
            this.switchToLive();
            return;
        }
        
        this.timeNav.startTime = newStartTime;
        this.timeNav.endTime = newEndTime;
        
        // Load data
        for (const tagId of this.activeTags) {
            await this.loadHistoricalData(tagId, newStartTime, newEndTime);
        }
        
        this.updateHistoricalChart();
        console.log(`⏩ Navigated forward to ${newEndTime.toLocaleString()}`);
    }
    
    /**
     * Add tag to trend
     */
    addTag(tagId) {
        this.activeTags.add(tagId);
        
        if (this.timeNav.mode === 'live') {
            this.liveBuffer.set(tagId, []);
        }
    }
    
    /**
     * Remove tag from trend
     */
    removeTag(tagId) {
        this.activeTags.delete(tagId);
        this.liveBuffer.delete(tagId);
        this.historicalCache.delete(tagId);
        
        if (this.timeNav.mode === 'live') {
            this.updateLiveChart();
        } else {
            this.updateHistoricalChart();
        }
    }
    
    /**
     * Setup keyboard shortcuts
     */
    setupKeyboardShortcuts() {
        document.addEventListener('keydown', (e) => {
            if (e.ctrlKey) {
                switch(e.key) {
                    case 'ArrowLeft':
                        e.preventDefault();
                        this.navigateBackward(3600);
                        break;
                    case 'ArrowRight':
                        e.preventDefault();
                        this.navigateForward(3600);
                        break;
                    case 'Home':
                        e.preventDefault();
                        this.switchToLive();
                        break;
                }
            }
        });
    }
    
    /**
     * Pan complete callback
     */
    onPanComplete(ctx) {
        // Could trigger data load if needed
        console.log('Pan complete');
    }
    
    /**
     * Zoom complete callback
     */
    onZoomComplete(ctx) {
        console.log('Zoom complete');
    }
    
    /**
     * Clear all data
     */
    clear() {
        this.liveBuffer.clear();
        this.historicalCache.clear();
        this.activeTags.clear();
        this.chart.data.datasets = [];
        this.chart.update();
    }
}
