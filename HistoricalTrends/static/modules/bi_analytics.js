/**
 * BI Analytics Module
 * Advanced multi-dimensional analysis with pivot-like functionality
 */

const BIAnalytics = {
    xAxisTags: [],
    yAxisTags: [],
    currentData: null,
    currentVisualization: null,
    worker: null,
    cachedStats: null,
    config: null,

    /**
     * Auto-calculate optimal data points based on dataset size
     */
    getOptimalSampleSize(dataLength) {
        if (dataLength <= 1000) return dataLength;
        if (dataLength <= 10000) return Math.min(dataLength, 5000);
        if (dataLength <= 100000) return Math.min(dataLength, 10000);
        if (dataLength <= 1000000) return Math.min(dataLength, 50000);
        return 100000; // For millions of rows
    },

    /**
     * Initialize BI Analytics module
     */
    async initialize(data, tags) {
        console.log('🚀 BIAnalytics.initialize called with:', {
            dataProvided: !!data,
            dataType: typeof data,
            isArray: Array.isArray(data),
            dataLength: data?.length,
            tagsProvided: !!tags,
            tagsLength: tags?.length,
            firstDataRow: data?.[0],
            sampleTags: tags?.slice(0, 3)
        });
        
        // Load minimal config
        if (!this.config) {
            try {
                const response = await fetch('/api/config');
                const result = await response.json();
                this.config = {
                    GroupedBarSettings: result.GroupedBarSettings || {},
                    TimeSeriesBarSettings: result.TimeSeriesBarSettings || {},
                    EnableAutoDetection: result.GroupedBarSettings?.EnableAutoDetection !== false
                };
                console.log('✅ BI Config loaded:', this.config);
            } catch (e) {
                console.warn('⚠️ Config load failed, using defaults');
                this.config = {
                    GroupedBarSettings: {},
                    TimeSeriesBarSettings: {},
                    EnableAutoDetection: true
                };
            }
        }
        
        // Initialize web worker for heavy calculations
        try {
            this.worker = new Worker('static/modules/bi_worker.js');
            console.log('✅ BI Worker initialized');
        } catch (e) {
            console.warn('⚠️ Web Worker not available, using main thread');
        }
        
        // Auto-sample data based on size (dynamic!)
        const optimalSize = this.getOptimalSampleSize(data.length);
        if (data.length > optimalSize) {
            console.log(`📊 Auto-sampling: ${data.length.toLocaleString()} → ${optimalSize.toLocaleString()} points`);
            const step = Math.ceil(data.length / optimalSize);
            this.currentData = data.filter((_, i) => i % step === 0);
        } else {
            this.currentData = data;
        }
        
        // Backup reference in case of scope issues
        window._biDataBackup = this.currentData;
        window._biAnalyticsInstance = this; // Store entire instance
        
        console.log('✅ this.currentData set:', {
            length: this.currentData.length,
            firstRow: this.currentData[0],
            isArray: Array.isArray(this.currentData),
            backupStored: !!window._biDataBackup,
            instanceStored: !!window._biAnalyticsInstance
        });
        
        this.renderAxisSelectors(tags);
        this.setupEventListeners();
    },

    /**
     * Render tag selectors for X and Y axes
     */
    renderAxisSelectors(tags) {
        const xSelector = document.getElementById('xAxisSelector');
        const ySelector = document.getElementById('yAxisSelector');
        
        xSelector.innerHTML = '';
        ySelector.innerHTML = '';
        
        tags.forEach(tag => {
            // X-Axis selector
            const xCheckbox = document.createElement('div');
            xCheckbox.style.cssText = 'margin: 8px 0; padding: 8px; background: rgba(0, 255, 136, 0.1); border-radius: 4px; cursor: pointer;';
            xCheckbox.innerHTML = `
                <label style="cursor: pointer; display: flex; align-items: center;">
                    <input type="checkbox" class="x-axis-tag" value="${tag}" style="width: 18px; height: 18px; margin-right: 10px; cursor: pointer; accent-color: #00ff88;">
                    <span style="color: #e0e0e0; font-size: 14px;">${tag}</span>
                </label>
            `;
            xSelector.appendChild(xCheckbox);
            
            // Y-Axis selector
            const yCheckbox = document.createElement('div');
            yCheckbox.style.cssText = 'margin: 8px 0; padding: 8px; background: rgba(255, 215, 0, 0.1); border-radius: 4px; cursor: pointer;';
            yCheckbox.innerHTML = `
                <label style="cursor: pointer; display: flex; align-items: center;">
                    <input type="checkbox" class="y-axis-tag" value="${tag}" style="width: 18px; height: 18px; margin-right: 10px; cursor: pointer; accent-color: #ffd700;">
                    <span style="color: #e0e0e0; font-size: 14px;">${tag}</span>
                </label>
            `;
            ySelector.appendChild(yCheckbox);
        });
    },

    /**
     * Setup event listeners
     */
    setupEventListeners() {
        // Apply configuration button
        document.getElementById('applyBIConfig').addEventListener('click', () => {
            this.updateAxisSelection();
            if (this.xAxisTags.length > 0 || this.yAxisTags.length > 0) {
                this.showMessage('Configuration applied! Select a visualization type below.', 'success');
            } else {
                this.showMessage('Please select at least one axis!', 'warning');
            }
        });

        // Chart type buttons
        document.querySelectorAll('.bi-chart-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const type = e.target.dataset.type;
                this.currentVisualization = type;
                this.renderVisualization(type);
                
                // Update active state
                document.querySelectorAll('.bi-chart-btn').forEach(b => b.classList.remove('active'));
                e.target.classList.add('active');
            });
        });
    },

    /**
     * Update axis selection from checkboxes
     */
    updateAxisSelection() {
        this.xAxisTags = Array.from(document.querySelectorAll('.x-axis-tag:checked')).map(cb => cb.value);
        this.yAxisTags = Array.from(document.querySelectorAll('.y-axis-tag:checked')).map(cb => cb.value);
        
        console.log('📊 BI Config:', {
            xAxis: this.xAxisTags,
            yAxis: this.yAxisTags,
            dataPoints: this.currentData?.length
        });
    },

    /**
     * Render selected visualization
     */
    async renderVisualization(type) {
        const container = document.getElementById('biChartContainer');
        
        console.log('🎨 renderVisualization called:', {
            type,
            thisInstance: this === window._biAnalyticsInstance,
            hasCurrentData: !!this.currentData,
            currentDataLength: this.currentData?.length,
            hasBackup: !!window._biDataBackup,
            backupLength: window._biDataBackup?.length
        });
        
        // Restore from backup if needed
        if ((!this.currentData || this.currentData.length === 0) && window._biDataBackup) {
            console.warn('⚠️ Restoring currentData from backup in renderVisualization');
            this.currentData = window._biDataBackup;
        }
        
        // Show loading indicator
        container.innerHTML = '<div style="text-align: center; padding: 60px; color: #00d4ff;"><div style="border: 5px solid rgba(0, 212, 255, 0.1); border-top: 5px solid #00d4ff; border-radius: 50%; width: 60px; height: 60px; animation: spin 1s linear infinite; margin: 0 auto 20px;"></div><p style="font-size: 18px; font-weight: bold;">🔄 Loading visualization...</p><p style="color: #888; font-size: 14px;">Please wait, processing data...</p></div>';
        
        // Allow UI to update
        await new Promise(resolve => setTimeout(resolve, 50));

        if (!this.currentData || this.currentData.length === 0) {
            console.error('❌ No data available after backup check:', {
                hasCurrentData: !!this.currentData,
                hasBackup: !!window._biDataBackup
            });
            container.innerHTML = '<p style="color: #ff6b6b; text-align: center; padding: 40px;">No data loaded. Please load data first!</p>';
            return;
        }

        // Only check axes for charts that require them (not groupedbar, treemap, pivot)
        const chartsRequiringAxes = ['scatter3d', 'bar', 'correlation', 'pie', 'heatmap', 'parallel', 'sunburst'];
        if (chartsRequiringAxes.includes(type) && this.xAxisTags.length === 0 && this.yAxisTags.length === 0) {
            container.innerHTML = '<p style="color: #ffd700; text-align: center; padding: 40px;">Please configure axes and click Apply Configuration!</p>';
            return;
        }

        try {
            switch (type) {
            case 'scatter3d':
                await this.render3DScatter(container);
                break;
            case 'bar':
                await this.renderBarChart(container);
                break;
            case 'groupedbar':
                await this.renderGroupedBarChart(container);
                break;
            case 'timeseriesbar':
                await this.renderTimeSeriesGroupedBar(container);
                break;
            case 'correlation':
                await this.renderCorrelationAnalysis(container);
                break;
            case 'pie':
                await this.renderPieChart(container);
                break;
            case 'heatmap':
                await this.renderHeatmap(container);
                break;
            case 'parallel':
                await this.renderParallelCoordinates(container);
                break;
            case 'sunburst':
                await this.renderSunburst(container);
                break;
            case 'treemap':
                await this.renderTreemap(container);
                break;
            case 'pivot':
                await this.renderPivotTable(container);
                break;
            default:
                container.innerHTML = '<p style="color: #888; text-align: center; padding: 40px;">Visualization type not implemented yet.</p>';
            }
        } catch (error) {
            console.error('❌ Visualization error:', error);
            container.innerHTML = `<p style="color: #ff6b6b; text-align: center; padding: 40px;">⚠️ Error rendering visualization: ${error.message}</p>`;
        }
    },

    /**
     * Render 3D Scatter Plot
     */
    async render3DScatter(container) {
        await new Promise(resolve => setTimeout(resolve, 10));
        console.log('🎯 Rendering 3D Scatter...');
        console.log('X-Axis tags:', this.xAxisTags);
        console.log('Y-Axis tags:', this.yAxisTags);
        
        if (this.xAxisTags.length < 2 || this.yAxisTags.length < 1) {
            container.innerHTML = '<p style="color: #dc3545; text-align: center; padding: 40px; font-size: 16px;">⚠️ Need at least 2 X-axis tags and 1 Y-axis tag for 3D scatter!<br><span style="color: #888; font-size: 14px;">Currently: ' + this.xAxisTags.length + ' X-axis, ' + this.yAxisTags.length + ' Y-axis</span></p>';
            return;
        }

        const xTag1 = this.xAxisTags[0];
        const xTag2 = this.xAxisTags[1];
        const yTag = this.yAxisTags[0];

        const validData = this.currentData.filter(d =>
            d[xTag1] != null && d[xTag2] != null && d[yTag] != null &&
            !isNaN(d[xTag1]) && !isNaN(d[xTag2]) && !isNaN(d[yTag])
        );

        const trace = {
            x: validData.map(d => d[xTag1]),
            y: validData.map(d => d[xTag2]),
            z: validData.map(d => d[yTag]),
            mode: 'markers',
            type: 'scatter3d',
            marker: {
                size: 5,
                color: validData.map(d => d[yTag]),
                colorscale: [
                    [0, '#1e3a5f'],    // Dark navy
                    [0.33, '#2563eb'], // Royal blue
                    [0.66, '#9333ea'], // Purple
                    [1, '#dc2626']     // Deep red
                ],
                showscale: true,
                colorbar: {
                    title: yTag,
                    titlefont: { color: '#ffffff', size: 12 },
                    tickfont: { color: '#e0e0e0' },
                    bgcolor: 'rgba(20, 30, 50, 0.9)',
                    bordercolor: '#2563eb',
                    borderwidth: 2,
                    thickness: 20
                },
                line: { color: '#1e40af', width: 0.5 }
            },
            text: validData.map(d => `${xTag1}: ${d[xTag1]}<br>${xTag2}: ${d[xTag2]}<br>${yTag}: ${d[yTag]}`),
            hovertemplate: '%{text}<extra></extra>'
        };
        
        console.log('✅ 3D Scatter data ready, points:', validData.length);

        const layout = {
            paper_bgcolor: 'rgba(0,0,0,0)',
            plot_bgcolor: 'rgba(15, 52, 96, 0.3)',
            font: { color: '#e0e0e0', family: 'Segoe UI' },
            title: `3D Scatter: ${xTag1} vs ${xTag2} vs ${yTag}`,
            scene: {
                xaxis: { title: xTag1, gridcolor: 'rgba(100, 150, 200, 0.2)', color: '#60a5fa' },
                yaxis: { title: xTag2, gridcolor: 'rgba(100, 150, 200, 0.2)', color: '#a78bfa' },
                zaxis: { title: yTag, gridcolor: 'rgba(100, 150, 200, 0.2)', color: '#fbbf24' }
            },
            height: 600,
            autosize: true
        };

        const chartDiv = document.createElement('div');
        chartDiv.id = 'bi3dScatter';
        chartDiv.style.cssText = 'width: 100%; height: 600px;';
        
        // Clear loading indicator before adding chart
        container.innerHTML = '';
        container.appendChild(chartDiv);
        
        Plotly.newPlot('bi3dScatter', [trace], layout, { responsive: true })
            .then(() => console.log('✅ 3D Scatter rendered successfully'))
            .catch(err => console.error('❌ 3D Scatter error:', err));
    },

    /**
     * Render Business Metrics Bar Chart
     * Shows meaningful KPIs for equipment performance decision-making
     */
    async renderBarChart(container) {
        await new Promise(resolve => setTimeout(resolve, 10));
        const allTags = [...this.xAxisTags, ...this.yAxisTags];
        if (allTags.length === 0) {
            container.innerHTML = '<p style="color: #dc3545; text-align: center; padding: 40px;">Please select at least one tag!</p>';
            return;
        }

        // Calculate comprehensive business metrics
        const metrics = allTags.map((tag, index) => {
            const validData = this.currentData.filter(d => d[tag] != null && !isNaN(d[tag]));
            const values = validData.map(d => d[tag]);
            
            if (values.length === 0) {
                return null;
            }
            
            const sorted = [...values].sort((a, b) => a - b);
            const mean = values.reduce((a, b) => a + b, 0) / values.length;
            const variance = values.reduce((sum, val) => sum + Math.pow(val - mean, 2), 0) / values.length;
            const stdDev = Math.sqrt(variance);
            const min = sorted[0];
            const max = sorted[sorted.length - 1];
            const range = max - min;
            
            // Business KPIs
            const cv = mean !== 0 ? (stdDev / Math.abs(mean)) * 100 : 0; // Coefficient of Variation
            const stability = range !== 0 ? (1 - (stdDev / range)) * 100 : 100; // Stability Score (0-100)
            const utilization = mean !== 0 ? (mean / max) * 100 : 0; // Utilization %
            const efficiency = range !== 0 ? ((max - min) / max) * 100 : 0; // Efficiency %
            
            return {
                tag,
                mean,
                stdDev,
                min,
                max,
                range,
                cv,
                stability,
                utilization,
                efficiency,
                count: values.length
            };
        }).filter(m => m !== null);

        // Create grouped bar chart with business metrics
        const traces = [
            {
                name: 'Stability Score',
                x: metrics.map(m => m.tag),
                y: metrics.map(m => m.stability),
                type: 'bar',
                marker: { color: '#10b981', opacity: 0.9 },
                text: metrics.map(m => `${typeof m.stability === 'number' && !isNaN(m.stability) ? m.stability.toFixed(1) : '0'}%`),
                textposition: 'outside',
                hovertemplate: '<b>%{x}</b><br>Stability: %{y:.1f}%<br>(Higher is better)<extra></extra>'
            },
            {
                name: 'Variability (CV)',
                x: metrics.map(m => m.tag),
                y: metrics.map(m => m.cv),
                type: 'bar',
                marker: { color: '#f59e0b', opacity: 0.9 },
                text: metrics.map(m => `${typeof m.cv === 'number' && !isNaN(m.cv) ? m.cv.toFixed(1) : '0'}%`),
                textposition: 'outside',
                hovertemplate: '<b>%{x}</b><br>Variability: %{y:.1f}%<br>(Lower is better)<extra></extra>'
            },
            {
                name: 'Utilization',
                x: metrics.map(m => m.tag),
                y: metrics.map(m => m.utilization),
                type: 'bar',
                marker: { color: '#3b82f6', opacity: 0.9 },
                text: metrics.map(m => `${typeof m.utilization === 'number' && !isNaN(m.utilization) ? m.utilization.toFixed(1) : '0'}%`),
                textposition: 'outside',
                hovertemplate: '<b>%{x}</b><br>Utilization: %{y:.1f}%<br>(Mean/Max ratio)<extra></extra>'
            }
        ];

        const layout = {
            paper_bgcolor: 'rgba(0,0,0,0)',
            plot_bgcolor: 'rgba(15, 52, 96, 0.3)',
            font: { color: '#e0e0e0', family: 'Segoe UI', size: 11 },
            title: {
                text: 'Equipment Performance KPIs - Business Decision Metrics',
                font: { size: 16, color: '#ffffff' }
            },
            xaxis: { 
                gridcolor: 'rgba(100, 150, 200, 0.1)', 
                color: '#e0e0e0',
                title: 'Parameters'
            },
            yaxis: { 
                gridcolor: 'rgba(100, 150, 200, 0.1)', 
                color: '#e0e0e0', 
                title: 'Score (%)',
                range: [0, 110]
            },
            barmode: 'group',
            height: 500,
            showlegend: true,
            legend: {
                x: 0.5,
                xanchor: 'center',
                y: 1.15,
                orientation: 'h',
                bgcolor: 'rgba(0, 0, 0, 0.5)',
                bordercolor: '#2563eb',
                borderwidth: 1
            },
            annotations: metrics.map((m, i) => ({
                x: i,
                y: -15,
                text: `<b>Range:</b> ${typeof m.min === 'number' && !isNaN(m.min) ? m.min.toFixed(1) : 'N/A'} - ${typeof m.max === 'number' && !isNaN(m.max) ? m.max.toFixed(1) : 'N/A'}<br><b>Mean:</b> ${typeof m.mean === 'number' && !isNaN(m.mean) ? m.mean.toFixed(1) : 'N/A'}`,
                showarrow: false,
                font: { size: 9, color: '#888' },
                xref: 'x',
                yref: 'y'
            }))
        };

        const chartDiv = document.createElement('div');
        chartDiv.id = 'biBarChart';
        container.innerHTML = '';
        container.appendChild(chartDiv);
        
        Plotly.newPlot('biBarChart', traces, layout, { responsive: true })
            .then(() => console.log('✅ Business Metrics rendered'))
            .catch(err => console.error('❌ Bar chart error:', err));
        
        // Add interpretation guide
        const guideDiv = document.createElement('div');
        guideDiv.style.cssText = 'margin-top: 20px; padding: 15px; background: linear-gradient(135deg, rgba(30, 64, 175, 0.2), rgba(124, 58, 237, 0.2)); border-radius: 8px; border: 1px solid rgba(59, 130, 246, 0.3);';
        guideDiv.innerHTML = `
            <h4 style="color: #60a5fa; margin: 0 0 10px 0;">📊 Business Interpretation Guide</h4>
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 10px; font-size: 13px; color: #cbd5e1;">
                <div><strong style="color: #10b981;">Stability Score:</strong> Higher = More consistent operation (Target: >80%)</div>
                <div><strong style="color: #f59e0b;">Variability (CV):</strong> Lower = More predictable (Target: <20%)</div>
                <div><strong style="color: #3b82f6;">Utilization:</strong> Higher = Better resource usage (Target: 70-90%)</div>
            </div>
            <div style="margin-top: 10px; padding: 8px; background: rgba(220, 38, 38, 0.1); border-left: 3px solid #dc2626; font-size: 12px; color: #fca5a5;">
                <strong>⚠️ Action Required If:</strong> Stability < 60% OR Variability > 30% OR Utilization < 50% - Indicates potential equipment issues
            </div>
        `;
        container.appendChild(guideDiv);
    },

    /**
     * Render Grouped Bar Chart - Turbine Health Metrics
     * Shows Design vs Last Period vs Current for selected Y-axis tags
     */
    async renderGroupedBarChart(container) {
        await new Promise(resolve => setTimeout(resolve, 10));
        console.log('📊 Rendering Grouped Bar...');
        
        // Restore data from backup if needed
        if (!this.currentData && window._biDataBackup) {
            console.warn('⚠️ Restoring currentData from backup');
            this.currentData = window._biDataBackup;
        }
        
        if (!this.currentData || this.currentData.length === 0) {
            container.innerHTML = '<p style="color: #ff6b6b; text-align: center; padding: 40px;">⚠️ No data loaded. Please load data first!</p>';
            return;
        }
        
        // Use Y-axis tags (same as other charts)
        const tagsToShow = this.yAxisTags;
        
        if (tagsToShow.length === 0) {
            container.innerHTML = '<p style="color: #fbbf24; text-align: center; padding: 40px; font-size: 16px;">⚠️ Please select Y-Axis tags first, then click Apply Configuration!</p>';
            return;
        }
        
        console.log('📊 Selected tags for Grouped Bar:', tagsToShow);
        console.log('📊 Data available:', this.currentData.length, 'rows');
        console.log('📊 Available columns in data:', Object.keys(this.currentData[0]));
        console.log('📊 Tag match check:', tagsToShow.map(t => ({
            selected: t,
            existsInData: t in this.currentData[0],
            actualValue: this.currentData[0][t]
        })));
        
        // Get configurable factors with fallback defaults
        const globalDesignFactor = this.config?.GroupedBarSettings?.DesignFactor || 1.05;
        const globalDesignValue = this.config?.GroupedBarSettings?.DesignValue || null;
        const lastPeriodPercentile = this.config?.GroupedBarSettings?.LastPeriodPercentile || 0.75;
        const tagSpecificLimits = this.config?.GroupedBarSettings?.TagSpecificLimits || {};
        
        console.log(`📊 Global defaults: DesignFactor=${globalDesignFactor}, LastPeriodPercentile=${lastPeriodPercentile}`);
        console.log(`📊 Tag-specific limits configured for: ${Object.keys(tagSpecificLimits).join(', ') || 'none'}`);
        
        const stats = { current: [], design: [], lastPeriod: [] };
        const labels = [];

        tagsToShow.forEach(tag => {
            console.log(`🔍 Processing tag: ${tag}`);
            
            // Check for tag-specific limits
            const tagLimits = tagSpecificLimits[tag] || {};
            const designFactor = tagLimits.DesignFactor || globalDesignFactor;
            const designValue = tagLimits.DesignValue !== undefined ? tagLimits.DesignValue : globalDesignValue;
            const minOperating = tagLimits.MinOperating || null;
            const maxOperating = tagLimits.MaxOperating || null;
            
            const values = this.currentData
                .map(row => {
                    let val = row[tag];
                    // Convert string numbers to actual numbers
                    if (typeof val === 'string' && !isNaN(val) && val.trim() !== '') {
                        val = parseFloat(val);
                    }
                    return val;
                })
                .filter(v => v !== null && v !== undefined && !isNaN(v) && typeof v === 'number');

            console.log(`   Found ${values.length} valid values for ${tag}`);
            if (values.length === 0) {
                console.warn(`   ⚠️ Skipping ${tag} - no valid numeric data`);
                return;
            }

            const sorted = [...values].sort((a, b) => a - b);
            const currentValue = values[values.length - 1]; // Latest value
            const lastPeriodValue = values[Math.floor(values.length * lastPeriodPercentile)] || currentValue;
            
            // Design value: Tag-specific > Global fixed > Global multiplier
            const calculatedDesign = designValue !== null ? designValue : sorted[sorted.length - 1] * designFactor;

            const logMsg = designValue !== null ? 
                `   ✓ ${tag}: current=${currentValue.toFixed(2)}, lastPeriod=${lastPeriodValue.toFixed(2)}, design=${calculatedDesign.toFixed(2)} (FIXED${minOperating !== null ? `, range=${minOperating}-${maxOperating}` : ''})` :
                `   ✓ ${tag}: current=${currentValue.toFixed(2)}, lastPeriod=${lastPeriodValue.toFixed(2)}, design=${calculatedDesign.toFixed(2)} (DYNAMIC: max×${designFactor})`;
            
            console.log(logMsg);
            
            labels.push(tag.replace(/_/g, ' '));
            stats.current.push(currentValue);
            stats.lastPeriod.push(lastPeriodValue);
            stats.design.push(calculatedDesign);
        });

        console.log('📊 Final stats:', { labels: labels.length, current: stats.current.length });
        
        if (labels.length === 0) {
            container.innerHTML = '<p style="color: #ff6b6b; text-align: center; padding: 40px;">⚠️ No valid data to display!<br><small>Check console for details</small></p>';
            return;
        }

        const traces = [
            {
                x: labels,
                y: stats.design,
                name: 'Design/Target',
                type: 'bar',
                marker: { color: '#60a5fa', line: { color: '#3b82f6', width: 1.5 } }
            },
            {
                x: labels,
                y: stats.lastPeriod,
                name: 'Last Period',
                type: 'bar',
                marker: { color: '#fbbf24', line: { color: '#f59e0b', width: 1.5 } }
            },
            {
                x: labels,
                y: stats.current,
                name: 'Current',
                type: 'bar',
                marker: { color: '#10b981', line: { color: '#059669', width: 1.5 } }
            }
        ];

        const layout = {
            paper_bgcolor: 'rgba(0,0,0,0)',
            plot_bgcolor: 'rgba(15, 52, 96, 0.3)',
            font: { color: '#e0e0e0', family: 'Segoe UI', size: 11 },
            title: { text: '🏭 Turbine Performance - Design vs Last Period vs Current', font: { color: '#60a5fa', size: 16 } },
            barmode: 'group',
            xaxis: { title: 'Parameters', tickangle: -45, gridcolor: 'rgba(255,255,255,0.1)', tickfont: { size: 10 } },
            yaxis: { title: 'Values', gridcolor: 'rgba(255,255,255,0.1)' },
            showlegend: true,
            legend: { bgcolor: 'rgba(0,0,0,0.7)', bordercolor: '#60a5fa', borderwidth: 2 },
            margin: { l: 60, r: 30, t: 80, b: 120 }
        };

        const chartDiv = document.createElement('div');
        chartDiv.id = 'biGroupedBarChart';
        container.innerHTML = '';
        container.appendChild(chartDiv);

        Plotly.newPlot('biGroupedBarChart', traces, layout, { responsive: true })
            .then(() => console.log('✅ Grouped bar chart rendered'))
            .catch(err => console.error('❌ Grouped bar error:', err));
    },

    /**
     * Render Time-Series Grouped Bar Chart
     * Shows Design vs Actual values over time periods (hourly/daily/weekly)
     * Allows visualization of cumulative trends and performance degradation
     */
    async renderTimeSeriesGroupedBar(container) {
        await new Promise(resolve => setTimeout(resolve, 10));
        console.log('📊 Rendering Time-Series Grouped Bar...');
        
        // Restore data from backup if needed
        if (!this.currentData && window._biDataBackup) {
            console.warn('⚠️ Restoring currentData from backup');
            this.currentData = window._biDataBackup;
        }
        
        if (!this.currentData || this.currentData.length === 0) {
            container.innerHTML = '<p style="color: #ff6b6b; text-align: center; padding: 40px;">⚠️ No data loaded. Please load data first!</p>';
            return;
        }
        
        // Use Y-axis tags
        const selectedTags = this.yAxisTags;
        
        if (selectedTags.length === 0) {
            container.innerHTML = '<p style="color: #fbbf24; text-align: center; padding: 40px; font-size: 16px;">⚠️ Please select Y-Axis tags first, then click Apply Configuration!</p>';
            return;
        }
        
        console.log('📊 Selected tags for Time-Series Bar:', selectedTags);
        console.log('📊 Data available:', this.currentData.length, 'rows');
        
        // Group data by time intervals
        const dataWithTime = this.currentData.map(row => {
            const timestamp = row.Timestamp || row.timestamp || row.DateTime || row.datetime;
            return { ...row, _timestamp: timestamp ? new Date(timestamp) : null };
        }).filter(row => row._timestamp !== null);
        
        if (dataWithTime.length === 0) {
            container.innerHTML = '<p style="color: #ff6b6b; text-align: center; padding: 40px;">⚠️ No timestamp column found in data!</p>';
            return;
        }
        
        // Sort by timestamp
        dataWithTime.sort((a, b) => a._timestamp - b._timestamp);
        
        // Determine time grouping (hourly, daily, or weekly based on data span)
        const timeSpan = dataWithTime[dataWithTime.length - 1]._timestamp - dataWithTime[0]._timestamp;
        const hours = timeSpan / (1000 * 60 * 60);
        
        let groupBy, formatStr;
        if (hours <= 48) {
            groupBy = 'hour';
            formatStr = 'MMM DD HH:00';
        } else if (hours <= 720) { // 30 days
            groupBy = 'day';
            formatStr = 'MMM DD';
        } else {
            groupBy = 'week';
            formatStr = 'MMM DD';
        }
        
        console.log(`📊 Time grouping: ${groupBy} (data span: ${hours.toFixed(1)} hours)`);
        
        // Group data by time periods
        const timeGroups = {};
        dataWithTime.forEach(row => {
            const ts = row._timestamp;
            let key;
            
            if (groupBy === 'hour') {
                key = `${ts.getFullYear()}-${String(ts.getMonth() + 1).padStart(2, '0')}-${String(ts.getDate()).padStart(2, '0')} ${String(ts.getHours()).padStart(2, '0')}:00`;
            } else if (groupBy === 'day') {
                key = `${ts.getFullYear()}-${String(ts.getMonth() + 1).padStart(2, '0')}-${String(ts.getDate()).padStart(2, '0')}`;
            } else { // week
                const weekStart = new Date(ts);
                weekStart.setDate(ts.getDate() - ts.getDay());
                key = `${weekStart.getFullYear()}-${String(weekStart.getMonth() + 1).padStart(2, '0')}-${String(weekStart.getDate()).padStart(2, '0')}`;
            }
            
            if (!timeGroups[key]) {
                timeGroups[key] = [];
            }
            timeGroups[key].push(row);
        });
        
        const timePeriods = Object.keys(timeGroups).sort();
        console.log(`📊 Created ${timePeriods.length} time periods`);
        
        // Get configurable design factor with fallback
        const globalDesignFactor = this.config?.TimeSeriesBarSettings?.DesignFactor || 1.05;
        const globalDesignValue = this.config?.TimeSeriesBarSettings?.DesignValue || null;
        
        // Get tag-specific limits - prefer TimeSeriesBarSettings, fallback to GroupedBarSettings
        let tagSpecificLimits = this.config?.TimeSeriesBarSettings?.TagSpecificLimits || {};
        // If TimeSeriesBarSettings.TagSpecificLimits is empty, use GroupedBarSettings
        if (Object.keys(tagSpecificLimits).length === 0) {
            tagSpecificLimits = this.config?.GroupedBarSettings?.TagSpecificLimits || {};
        }
        
        console.log(`📊 Tag-specific limits for time-series: ${Object.keys(tagSpecificLimits).join(', ') || 'none'}`);
        
        // For each selected tag, create traces
        const traces = [];
        const colors = ['#60a5fa', '#fbbf24', '#10b981', '#ec4899', '#8b5cf6', '#f97316'];
        
        selectedTags.forEach((tag, tagIndex) => {
            // Get tag-specific limits
            const tagLimits = tagSpecificLimits[tag] || {};
            const designFactor = tagLimits.DesignFactor || globalDesignFactor;
            const designValue = tagLimits.DesignValue !== undefined ? tagLimits.DesignValue : globalDesignValue;
            
            console.log(`📊 Processing ${tag}: designValue=${designValue}, designFactor=${designFactor}`);
            
            const designValues = [];
            const actualValues = [];
            const labels = [];
            
            timePeriods.forEach(period => {
                const periodData = timeGroups[period];
                
                // Extract values for this tag
                const values = periodData.map(row => {
                    let val = row[tag];
                    if (typeof val === 'string' && !isNaN(val) && val.trim() !== '') {
                        val = parseFloat(val);
                    }
                    return val;
                }).filter(v => v !== null && v !== undefined && !isNaN(v) && typeof v === 'number');
                
                if (values.length > 0) {
                    const avg = values.reduce((sum, v) => sum + v, 0) / values.length;
                    const max = Math.max(...values);
                    
                    // Use fixed design value if configured, otherwise calculate dynamically
                    const design = designValue !== null ? designValue : max * designFactor;
                    
                    labels.push(period);
                    actualValues.push(avg);
                    designValues.push(design);
                }
            });
            
            if (actualValues.length > 0) {
                // Design trace
                traces.push({
                    x: labels,
                    y: designValues,
                    name: `${tag.replace(/_/g, ' ')} - Design`,
                    type: 'bar',
                    marker: { 
                        color: colors[tagIndex % colors.length],
                        opacity: 0.6,
                        line: { color: colors[tagIndex % colors.length], width: 1 }
                    },
                    legendgroup: `group${tagIndex}`,
                    showlegend: true
                });
                
                // Actual trace
                traces.push({
                    x: labels,
                    y: actualValues,
                    name: `${tag.replace(/_/g, ' ')} - Actual`,
                    type: 'bar',
                    marker: { 
                        color: colors[tagIndex % colors.length],
                        opacity: 1.0,
                        line: { color: '#000', width: 1.5 }
                    },
                    legendgroup: `group${tagIndex}`,
                    showlegend: true
                });
            }
        });
        
        if (traces.length === 0) {
            container.innerHTML = '<p style="color: #ff6b6b; text-align: center; padding: 40px;">⚠️ No valid data to display!</p>';
            return;
        }
        
        const layout = {
            paper_bgcolor: 'rgba(0,0,0,0)',
            plot_bgcolor: 'rgba(15, 52, 96, 0.3)',
            font: { color: '#e0e0e0', family: 'Segoe UI', size: 11 },
            title: { 
                text: `📈 Time-Series Performance - Design vs Actual (${groupBy}ly)`, 
                font: { color: '#60a5fa', size: 16 } 
            },
            barmode: 'group',
            xaxis: { 
                title: `Time Period (${groupBy})`, 
                tickangle: -45, 
                gridcolor: 'rgba(255,255,255,0.1)', 
                tickfont: { size: 9 }
            },
            yaxis: { 
                title: 'Values', 
                gridcolor: 'rgba(255,255,255,0.1)' 
            },
            showlegend: true,
            legend: { 
                bgcolor: 'rgba(0,0,0,0.7)', 
                bordercolor: '#60a5fa', 
                borderwidth: 2,
                orientation: 'v',
                x: 1.02,
                y: 1
            },
            margin: { l: 60, r: 200, t: 80, b: 120 }
        };

        const chartDiv = document.createElement('div');
        chartDiv.id = 'biTimeSeriesBarChart';
        container.innerHTML = '';
        container.appendChild(chartDiv);

        Plotly.newPlot('biTimeSeriesBarChart', traces, layout, { responsive: true })
            .then(() => console.log('✅ Time-series grouped bar chart rendered'))
            .catch(err => console.error('❌ Time-series bar error:', err));
            
        // Add interpretation guide
        const guideDiv = document.createElement('div');
        guideDiv.style.cssText = 'margin-top: 20px; padding: 15px; background: linear-gradient(135deg, rgba(30, 64, 175, 0.2), rgba(124, 58, 237, 0.2)); border-radius: 8px; border: 1px solid rgba(59, 130, 246, 0.3);';
        guideDiv.innerHTML = `
            <h4 style="color: #60a5fa; margin: 0 0 10px 0;">📊 Time-Series Interpretation Guide</h4>
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 10px; font-size: 13px; color: #cbd5e1;">
                <div><strong style="color: #60a5fa;">Design (Lighter bars):</strong> Target capacity for each period (5% above period max)</div>
                <div><strong style="color: #10b981;">Actual (Darker bars):</strong> Average actual value for each period</div>
                <div><strong style="color: #f59e0b;">Trend Analysis:</strong> Compare periods to see performance changes over time</div>
            </div>
            <div style="margin-top: 10px; padding: 8px; background: rgba(59, 130, 246, 0.1); border-left: 3px solid #3b82f6; font-size: 12px; color: #93c5fd;">
                <strong>💡 Key Insights:</strong> Widening gap between Design and Actual = Performance degradation | Consistent gap = Stable operation | Actual exceeding Design = Over-performance
            </div>
        `;
        container.appendChild(guideDiv);
    },

    /**
     * Render Correlation Analysis - Shows correlations between all parameters
     */
    async renderCorrelationAnalysis(container) {
        const allTags = [...this.xAxisTags, ...this.yAxisTags];
        if (allTags.length < 2) {
            container.innerHTML = '<p style="color: #ff6b6b; text-align: center; padding: 40px;">⚠️ Please select at least 2 tags for correlation analysis!</p>';
            return;
        }

        // Calculate correlation matrix
        const correlations = [];
        let processed = 0;
        const total = (allTags.length * (allTags.length - 1)) / 2;
        for (let i = 0; i < allTags.length; i++) {
            for (let j = i + 1; j < allTags.length; j++) {
                // Update progress every 5 calculations
                if (processed % 5 === 0) {
                    container.innerHTML = `<div style="text-align: center; padding: 20px; color: #00d4ff;">🔄 Calculating correlations... ${Math.round((processed/total)*100)}%</div>`;
                    await new Promise(resolve => setTimeout(resolve, 1));
                }
                processed++;
                
                const tag1 = allTags[i];
                const tag2 = allTags[j];
                
                const values1 = [];
                const values2 = [];
                
                this.currentData.forEach(row => {
                    const v1 = row[tag1];
                    const v2 = row[tag2];
                    if (v1 !== null && v1 !== undefined && !isNaN(v1) && typeof v1 === 'number' &&
                        v2 !== null && v2 !== undefined && !isNaN(v2) && typeof v2 === 'number') {
                        values1.push(v1);
                        values2.push(v2);
                    }
                });
                
                if (values1.length > 1) {
                    const corr = this.calculateCorrelation(values1, values2);
                    if (!isNaN(corr) && typeof corr === 'number') {
                        correlations.push({
                            tag1,
                            tag2,
                            correlation: corr,
                            strength: Math.abs(corr),
                            type: corr > 0 ? 'Positive' : 'Negative',
                            samples: values1.length
                        });
                    }
                }
            }
        }

        // Sort by strength (absolute value)
        correlations.sort((a, b) => b.strength - a.strength);

        // Display results
        container.innerHTML = '';
        
        const titleDiv = document.createElement('div');
        titleDiv.style.cssText = 'text-align: center; padding: 20px; background: linear-gradient(135deg, rgba(37, 99, 235, 0.2), rgba(124, 58, 237, 0.2)); border-radius: 8px; margin-bottom: 20px;';
        titleDiv.innerHTML = `
            <h3 style="color: #60a5fa; margin: 0 0 10px 0;">📈 Correlation Analysis</h3>
            <p style="color: #cbd5e1; font-size: 14px; margin: 0;">Found ${correlations.length} parameter relationships | ${allTags.length} tags analyzed</p>
        `;
        container.appendChild(titleDiv);

        const gridDiv = document.createElement('div');
        gridDiv.style.cssText = 'display: grid; grid-template-columns: repeat(auto-fill, minmax(350px, 1fr)); gap: 15px;';

        correlations.forEach((corr, idx) => {
            const strengthLabel = corr.strength > 0.9 ? 'Very Strong' : 
                                 corr.strength > 0.7 ? 'Strong' : 
                                 corr.strength > 0.5 ? 'Moderate' : 
                                 corr.strength > 0.3 ? 'Weak' : 'Very Weak';
            
            const color = corr.type === 'Positive' ? '#10b981' : '#ef4444';
            const bgColor = corr.type === 'Positive' ? 'rgba(16, 185, 129, 0.1)' : 'rgba(239, 68, 68, 0.1)';
            
            const card = document.createElement('div');
            card.style.cssText = `background: ${bgColor}; border: 1px solid ${color}; border-radius: 6px; padding: 15px;`;
            card.innerHTML = `
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                    <span style="color: #e0e0e0; font-weight: bold; font-size: 13px;">#${idx + 1}</span>
                    <span style="color: ${color}; font-weight: bold; font-size: 16px;">${(corr.correlation * 100).toFixed(1)}%</span>
                </div>
                <div style="color: #cbd5e1; font-size: 14px; margin-bottom: 8px;">
                    <div style="margin-bottom: 4px;">📊 <strong>${corr.tag1}</strong></div>
                    <div style="text-align: center; color: #888; font-size: 12px;">⬍⬍ ${corr.type} Correlation ⬍⬍</div>
                    <div style="margin-top: 4px;">📊 <strong>${corr.tag2}</strong></div>
                </div>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; font-size: 11px; color: #888;">
                    <div><strong>Strength:</strong> ${strengthLabel}</div>
                    <div><strong>Samples:</strong> ${corr.samples.toLocaleString()}</div>
                </div>
                <div style="margin-top: 10px; padding: 8px; background: rgba(0,0,0,0.3); border-radius: 4px; font-size: 11px; color: #cbd5e1;">
                    ${corr.type === 'Positive' ? 
                        '➕ When one increases, the other tends to increase' : 
                        '➖ When one increases, the other tends to decrease'}
                </div>
            `;
            gridDiv.appendChild(card);
        });

        container.appendChild(gridDiv);

        console.log('✅ Correlation analysis rendered:', correlations.length, 'relationships');
    },

    /**
     * Render Pie Chart
     */
    async renderPieChart(container) {
        await new Promise(resolve => setTimeout(resolve, 10));
        const allTags = [...this.xAxisTags, ...this.yAxisTags];
        if (allTags.length === 0) {
            container.innerHTML = '<p style="color: #ff6b6b; text-align: center; padding: 40px;">Please select at least one tag!</p>';
            return;
        }

        // Calculate total contribution of each tag
        const contributions = allTags.map(tag => {
            const validData = this.currentData.filter(d => d[tag] != null && !isNaN(d[tag]));
            const total = validData.reduce((sum, d) => sum + Math.abs(d[tag]), 0);
            return { tag, total };
        });

        const trace = {
            labels: contributions.map(c => c.tag),
            values: contributions.map(c => c.total),
            type: 'pie',
            marker: {
                colors: ['#2563eb', '#7c3aed', '#dc2626', '#ea580c', '#0891b2', '#4f46e5', '#64748b', '#ef4444'],
                line: { color: '#1e293b', width: 3 }
            },
            textfont: { color: '#ffffff', size: 13, family: 'Segoe UI', weight: 700 },
            textposition: 'inside',
            insidetextorientation: 'radial',
            hovertemplate: '<b>%{label}</b><br>Total: %{value:.2f}<br>Percent: %{percent}<extra></extra>',
            pull: contributions.map((_, i) => i === 0 ? 0.1 : 0)
        };

        const layout = {
            paper_bgcolor: 'rgba(0,0,0,0)',
            font: { color: '#e0e0e0', family: 'Segoe UI' },
            title: 'Tag Contribution Distribution',
            height: 500,
            showlegend: true,
            legend: { font: { color: '#e0e0e0' } }
        };

        const chartDiv = document.createElement('div');
        chartDiv.id = 'biPieChart';
        container.innerHTML = '';
        container.appendChild(chartDiv);
        Plotly.newPlot('biPieChart', [trace], layout, { responsive: true });
    },

    /**
     * Render Correlation Heatmap (Optimized with Web Worker)
     */
    async renderHeatmap(container) {
        await new Promise(resolve => setTimeout(resolve, 10));
        const allTags = [...this.xAxisTags, ...this.yAxisTags];
        if (allTags.length < 2) {
            container.innerHTML = '<p style="color: #dc3545; text-align: center; padding: 40px;">Need at least 2 tags for heatmap!</p>';
            return;
        }

        // Show loading indicator
        container.innerHTML = '<div style="text-align: center; padding: 60px; color: #60a5fa;"><div style="font-size: 48px;">⏳</div><div style="margin-top: 10px;">Calculating correlations...</div></div>';

        // Use worker if available for better performance
        if (this.worker) {
            this.worker.postMessage({
                type: 'correlation',
                data: this.currentData,
                tags: allTags
            });

            this.worker.onmessage = (e) => {
                if (e.data.success) {
                    this.renderHeatmapChart(container, allTags, e.data.result);
                } else {
                    container.innerHTML = `<p style="color: #dc2626; text-align: center; padding: 40px;">Error: ${e.data.error}</p>`;
                }
            };
        } else {
            // Fallback to main thread
            const correlationMatrix = this.calculateCorrelationMatrix(allTags);
            this.renderHeatmapChart(container, allTags, correlationMatrix);
        }
    },

    renderHeatmapChart(container, labels, correlationMatrix) {
        container.innerHTML = '';
        
        const trace = {
            z: correlationMatrix,
            x: labels,
            y: labels,
            type: 'heatmap',
            colorscale: [
                [0, '#1e3a5f'],    // Dark navy (low correlation)
                [0.25, '#3b82f6'], // Blue
                [0.5, '#64748b'],  // Neutral gray
                [0.75, '#9333ea'], // Purple
                [1, '#dc2626']     // Red (high correlation)
            ],
            zmid: 0,
            text: correlationMatrix.map(row => row.map(val => (typeof val === 'number' && !isNaN(val)) ? val.toFixed(3) : '0.000')),
            texttemplate: '%{text}',
            textfont: { color: '#ffffff', size: 11, family: 'Consolas' },
            hovertemplate: '%{y} vs %{x}<br>Correlation: %{z:.3f}<extra></extra>',
            colorbar: {
                title: 'Correlation',
                titlefont: { color: '#ffffff', size: 12 },
                tickfont: { color: '#e0e0e0' },
                bgcolor: 'rgba(20, 30, 50, 0.9)',
                bordercolor: '#2563eb',
                borderwidth: 2,
                thickness: 20
            }
        };

        const layout = {
            paper_bgcolor: 'rgba(0,0,0,0)',
            plot_bgcolor: 'rgba(15, 52, 96, 0.3)',
            font: { color: '#e0e0e0', family: 'Segoe UI' },
            title: 'Correlation Heatmap',
            xaxis: { color: '#e0e0e0' },
            yaxis: { color: '#e0e0e0' },
            height: 600
        };

        const chartDiv = document.createElement('div');
        chartDiv.id = 'biHeatmap';
        container.innerHTML = '';
        container.appendChild(chartDiv);
        
        Plotly.newPlot('biHeatmap', [trace], layout, { responsive: true })
            .then(() => {
                console.log('✅ Heatmap rendered');
                this.addHeatmapInsights(container, labels, correlationMatrix);
            })
            .catch(err => console.error('❌ Heatmap error:', err));
    },
    
    addHeatmapInsights(container, labels, matrix) {
        // Find strong correlations
        const insights = [];
        for (let i = 0; i < labels.length; i++) {
            for (let j = i + 1; j < labels.length; j++) {
                const corr = matrix[i][j];
                if (corr !== null && corr !== undefined && typeof corr === 'number' && !isNaN(corr) && Math.abs(corr) > 0.7) {
                    insights.push({
                        tag1: labels[i],
                        tag2: labels[j],
                        correlation: corr,
                        type: corr > 0 ? 'positive' : 'negative'
                    });
                }
            }
        }
        
        if (insights.length > 0) {
            insights.sort((a, b) => Math.abs(b.correlation) - Math.abs(a.correlation));
            
            const insightDiv = document.createElement('div');
            insightDiv.style.cssText = 'margin-top: 20px; padding: 20px; background: linear-gradient(135deg, rgba(30, 64, 175, 0.2), rgba(124, 58, 237, 0.2)); border-radius: 10px; border: 2px solid rgba(59, 130, 246, 0.3);';
            
            let html = `
                <h4 style="color: #60a5fa; margin: 0 0 15px 0; font-size: 18px;">🔍 Key Findings - Process Relationships</h4>
                <div style="color: #cbd5e1; font-size: 13px; line-height: 1.6;">
                    <p style="margin: 0 0 15px 0; color: #e0e0e0;"><strong>Correlation Analysis:</strong> Understanding how process parameters influence each other</p>
            `;
            
            insights.slice(0, 5).forEach((insight, idx) => {
                const color = insight.type === 'positive' ? '#10b981' : '#ef4444';
                const icon = insight.type === 'positive' ? '📈' : '📉';
                const strength = Math.abs(insight.correlation) > 0.9 ? 'Very Strong' : 'Strong';
                const direction = insight.type === 'positive' ? 'together' : 'inversely';
                
                html += `
                    <div style="margin: 10px 0; padding: 12px; background: rgba(30, 41, 59, 0.5); border-left: 4px solid ${color}; border-radius: 6px;">
                        <div style="color: ${color}; font-weight: 600; margin-bottom: 5px;">
                            ${icon} ${strength} ${insight.type === 'positive' ? 'Positive' : 'Negative'} Correlation (${(insight.correlation * 100).toFixed(1)}%)
                        </div>
                        <div style="color: #94a3b8;">
                            <strong style="color: #e0e0e0;">${insight.tag1}</strong> and <strong style="color: #e0e0e0;">${insight.tag2}</strong> move ${direction}
                        </div>
                        <div style="color: #64748b; font-size: 11px; margin-top: 5px;">
                            💡 <em>${insight.type === 'positive' 
                                ? 'When one increases, the other tends to increase - indicates dependent process'
                                : 'When one increases, the other decreases - indicates control relationship or opposing forces'}</em>
                        </div>
                    </div>
                `;
            });
            
            if (insights.length === 0) {
                html += '<p style="color: #fbbf24;">⚠️ No strong correlations detected. Parameters appear to operate independently.</p>';
            }
            
            html += `
                    <div style="margin-top: 15px; padding: 12px; background: rgba(16, 185, 129, 0.1); border-radius: 6px; border: 1px solid rgba(16, 185, 129, 0.3);">
                        <strong style="color: #10b981;">📊 Business Impact:</strong>
                        <ul style="margin: 8px 0; padding-left: 20px; color: #94a3b8;">
                            <li>Strong correlations (>70%) suggest process dependencies</li>
                            <li>Use positive correlations to predict equipment behavior</li>
                            <li>Negative correlations may indicate control loops or safety interlocks</li>
                            <li>Monitor correlated parameters together for root cause analysis</li>
                        </ul>
                    </div>
                </div>
            `;
            
            insightDiv.innerHTML = html;
            container.appendChild(insightDiv);
        }
    },

    async calculateCorrelationMatrix(allTags) {
        try {
            // Try Python API first (much faster)
            const response = await fetch(`${window.location.origin}/api/v1/analytics/correlation_matrix`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    data: this.currentData,
                    tags: allTags
                })
            });
            
            if (response.ok) {
                const result = await response.json();
                const matrix = result.matrix;
                
                // Convert dict to array format
                const correlationMatrix = [];
                allTags.forEach(tag1 => {
                    const row = [];
                    allTags.forEach(tag2 => {
                        row.push(matrix[tag1]?.[tag2] || 0);
                    });
                    correlationMatrix.push(row);
                });
                
                console.log('✓ Correlation matrix calculated via Python API');
                return correlationMatrix;
            }
        } catch (error) {
            console.error('Correlation Matrix API Error:', error);
            throw error;
        }

        return [];
    },

    /**
     * Render Parallel Coordinates
     */
    async renderParallelCoordinates(container) {
        await new Promise(resolve => setTimeout(resolve, 10));
        const allTags = [...this.xAxisTags, ...this.yAxisTags];
        if (allTags.length < 2) {
            container.innerHTML = '<p style="color: #ff6b6b; text-align: center; padding: 40px;">Need at least 2 tags for parallel coordinates!</p>';
            return;
        }

        // Sample data if too large
        const maxPoints = 5000;
        const sampledData = this.currentData.length > maxPoints 
            ? this.currentData.filter((_, i) => i % Math.ceil(this.currentData.length / maxPoints) === 0)
            : this.currentData;

        const dimensions = allTags.map((tag, index) => {
            const validData = sampledData.filter(d => d[tag] != null && !isNaN(d[tag]));
            const values = validData.map(d => d[tag]);
            
            return {
                label: tag,
                values: sampledData.map(d => d[tag] || 0),
                range: [Math.min(...values), Math.max(...values)]
            };
        });

        const trace = {
            type: 'parcoords',
            line: {
                color: sampledData.map((d, i) => i),
                colorscale: 'Viridis',
                showscale: true,
                cmin: 0,
                cmax: sampledData.length
            },
            dimensions: dimensions
        };

        const layout = {
            paper_bgcolor: 'rgba(0,0,0,0)',
            font: { color: '#e0e0e0', family: 'Segoe UI' },
            title: 'Parallel Coordinates Plot',
            height: 600
        };

        const chartDiv = document.createElement('div');
        chartDiv.id = 'biParallel';
        container.innerHTML = '';
        container.appendChild(chartDiv);
        Plotly.newPlot('biParallel', [trace], layout, { responsive: true });
    },

    /**
     * Render Sunburst Chart
     */
    async renderSunburst(container) {
        await new Promise(resolve => setTimeout(resolve, 10));
        // Create hierarchical data structure
        const rootLabel = 'All Tags';
        const labels = [rootLabel];
        const parents = [''];
        const values = [];

        // Add X-axis group
        if (this.xAxisTags.length > 0) {
            labels.push('Inputs (X)');
            parents.push(rootLabel);
            values.push(0);

            this.xAxisTags.forEach(tag => {
                const validData = this.currentData.filter(d => d[tag] != null && !isNaN(d[tag]));
                const total = validData.reduce((sum, d) => sum + Math.abs(d[tag]), 0);
                labels.push(tag);
                parents.push('Inputs (X)');
                values.push(total);
            });
        }

        // Add Y-axis group
        if (this.yAxisTags.length > 0) {
            labels.push('Outputs (Y)');
            parents.push(rootLabel);
            values.push(0);

            this.yAxisTags.forEach(tag => {
                const validData = this.currentData.filter(d => d[tag] != null && !isNaN(d[tag]));
                const total = validData.reduce((sum, d) => sum + Math.abs(d[tag]), 0);
                labels.push(tag);
                parents.push('Outputs (Y)');
                values.push(total);
            });
        }

        const trace = {
            type: 'sunburst',
            labels: labels,
            parents: parents,
            values: values,
            marker: { 
                colors: ['#1e293b', '#2563eb', '#7c3aed', '#dc2626', '#ea580c', '#0891b2', '#4f46e5', '#64748b', '#ef4444', '#8b5cf6'],
                line: { color: '#1e40af', width: 2 }
            },
            textfont: { color: '#ffffff', size: 13, family: 'Segoe UI', weight: 600 },
            hovertemplate: '<b>%{label}</b><br>Value: %{value:.2f}<extra></extra>'
        };

        const layout = {
            paper_bgcolor: 'rgba(0,0,0,0)',
            font: { color: '#e0e0e0', family: 'Segoe UI' },
            title: 'Sunburst - Hierarchical View',
            height: 600
        };

        const chartDiv = document.createElement('div');
        chartDiv.id = 'biSunburst';
        container.innerHTML = '';
        container.appendChild(chartDiv);
        Plotly.newPlot('biSunburst', [trace], layout, { responsive: true });
    },

    /**
     * Render Treemap
     */
    async renderTreemap(container) {
        await new Promise(resolve => setTimeout(resolve, 10));
        console.log('🌳 Rendering Treemap...');
        
        const rootLabel = 'All Parameters';
        const labels = [rootLabel];
        const parents = [''];
        const values = [0];
        const colors = [];
        const texts = [];

        // Professional color palette
        const colorPalette = ['#2563eb', '#7c3aed', '#dc2626', '#ea580c', '#0891b2', '#4f46e5', '#64748b', '#ef4444', '#8b5cf6', '#06b6d4'];
        
        // Add category layers
        if (this.xAxisTags.length > 0) {
            labels.push('Inputs (X-Axis)');
            parents.push(rootLabel);
            const xTotal = this.xAxisTags.reduce((sum, tag) => {
                const validData = this.currentData.filter(d => d[tag] != null && !isNaN(d[tag]));
                return sum + validData.reduce((s, d) => s + Math.abs(d[tag]), 0);
            }, 0);
            values.push(xTotal);
            colors.push('#1e40af');
            texts.push('');

            this.xAxisTags.forEach((tag, idx) => {
                const validData = this.currentData.filter(d => d[tag] != null && !isNaN(d[tag]));
                const total = validData.reduce((sum, d) => sum + Math.abs(d[tag]), 0);
                const mean = validData.length > 0 ? total / validData.length : 0;
                
                labels.push(tag);
                parents.push('Inputs (X-Axis)');
                values.push(total);
                colors.push(colorPalette[idx % colorPalette.length]);
                texts.push(`Mean: ${(typeof mean === 'number' && !isNaN(mean)) ? mean.toFixed(2) : 'N/A'}<br>Count: ${validData.length}`);
            });
        }

        if (this.yAxisTags.length > 0) {
            labels.push('Outputs (Y-Axis)');
            parents.push(rootLabel);
            const yTotal = this.yAxisTags.reduce((sum, tag) => {
                const validData = this.currentData.filter(d => d[tag] != null && !isNaN(d[tag]));
                return sum + validData.reduce((s, d) => s + Math.abs(d[tag]), 0);
            }, 0);
            values.push(yTotal);
            colors.push('#7c3aed');
            texts.push('');

            this.yAxisTags.forEach((tag, idx) => {
                const validData = this.currentData.filter(d => d[tag] != null && !isNaN(d[tag]));
                const total = validData.reduce((sum, d) => sum + Math.abs(d[tag]), 0);
                const mean = validData.length > 0 ? total / validData.length : 0;
                
                labels.push(tag);
                parents.push('Outputs (Y-Axis)');
                values.push(total);
                colors.push(colorPalette[(idx + this.xAxisTags.length) % colorPalette.length]);
                texts.push(`Mean: ${(typeof mean === 'number' && !isNaN(mean)) ? mean.toFixed(2) : 'N/A'}<br>Count: ${validData.length}`);
            });
        }

        const trace = {
            type: 'treemap',
            labels: labels,
            parents: parents,
            values: values,
            text: texts,
            textposition: 'middle center',
            marker: {
                colors: colors,
                line: { color: '#1e293b', width: 3 },
                pad: { t: 30, l: 5, r: 5, b: 5 }
            },
            textfont: { 
                color: '#ffffff', 
                size: 14, 
                family: 'Segoe UI',
                weight: 700
            },
            hovertemplate: '<b>%{label}</b><br>Total: %{value:.2f}<br>%{text}<extra></extra>',
            pathbar: {
                visible: true,
                edgeshape: '>',
                thickness: 20,
                textfont: { color: '#ffffff', size: 12 }
            }
        };

        const layout = {
            paper_bgcolor: 'rgba(0,0,0,0)',
            font: { color: '#e0e0e0', family: 'Segoe UI' },
            title: {
                text: 'Treemap - Hierarchical Value Distribution',
                font: { size: 18, color: '#ffffff' }
            },
            height: 650,
            margin: { t: 50, l: 5, r: 5, b: 5 }
        };

        const chartDiv = document.createElement('div');
        chartDiv.id = 'biTreemap';
        chartDiv.style.cssText = 'width: 100%; height: 650px;';
        container.innerHTML = '';
        container.appendChild(chartDiv);
        
        Plotly.newPlot('biTreemap', [trace], layout, { responsive: true })
            .then(() => console.log('✅ Treemap rendered successfully'))
            .catch(err => console.error('❌ Treemap error:', err));
    },

    /**
     * Render Pivot Table - Turbine Health KPI Dashboard
     */
    async renderPivotTable(container) {
        console.log('📊 Rendering Turbine Health KPI Dashboard...');
        await new Promise(resolve => setTimeout(resolve, 10));
        container.innerHTML = '';
        
        const allTags = [...this.xAxisTags, ...this.yAxisTags];
        if (allTags.length === 0) {
            container.innerHTML = '<p style="color: #fbbf24; text-align: center; padding: 40px; font-size: 16px;">⚠️ Please select X-Axis and Y-Axis tags first, then click Apply Configuration!</p>';
            return;
        }

        // Show loading
        container.innerHTML = '<div style="text-align: center; padding: 60px; color: #00d4ff;"><div style="border: 5px solid rgba(0, 212, 255, 0.1); border-top: 5px solid #00d4ff; border-radius: 50%; width: 60px; height: 60px; animation: spin 1s linear infinite; margin: 0 auto 20px;"></div><p>🔄 Analyzing turbine health indicators...</p></div>';

        // Get configuration
        const pivotConfig = this.config?.PivotTableSettings || {};
        const kpiGroups = pivotConfig.KPIGroups || {};
        const healthIndicators = pivotConfig.HealthIndicators || {};
        
        // Call Python API for statistics
        let statsData = {};
        try {
            const response = await fetch(`${window.location.origin}/api/v1/analytics/pivot_statistics`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    data: this.currentData,
                    tags: allTags
                })
            });
            
            if (!response.ok) {
                throw new Error(`API returned ${response.status}: ${response.statusText}`);
            }
            
            const result = await response.json();
            
            if (!result.success) {
                throw new Error(result.error || 'API call failed');
            }
            
            statsData = result.stats;
            console.log('✅ Received stats from Python API:', statsData);
        } catch (error) {
            console.error('❌ Python API error:', error);
            container.innerHTML = `<div style="color: #ff6b6b; text-align: center; padding: 40px;">
                <p style="font-size: 18px; margin-bottom: 10px;">⚠️ Failed to calculate statistics</p>
                <p style="font-size: 14px; color: #888;">Error: ${error.message}</p>
                <p style="font-size: 12px; color: #666; margin-top: 10px;">Make sure Flask server is running on port 5002</p>
            </div>`;
            return;
        }
        
        const gridDiv = document.createElement('div');
        gridDiv.id = 'biPivotGrid';
        gridDiv.style.cssText = 'width: 100%; overflow-x: auto; overflow-y: auto; max-height: 800px;';
        container.appendChild(gridDiv);
        
        // Render turbine health KPI dashboard
        let html = '<div style="background: linear-gradient(135deg, rgba(15, 52, 96, 0.6), rgba(26, 26, 46, 0.6)); padding: 25px; border-radius: 12px; border: 2px solid rgba(0, 212, 255, 0.3);">';
        html += '<h3 style="color: #00d4ff; margin: 0 0 20px 0; font-size: 22px; text-shadow: 0 0 10px rgba(0, 212, 255, 0.5);">🔬 Turbine Health Analytics - KPI Dashboard</h3>';
        
        // If configuration has KPI groups, render structured view
        if (Object.keys(kpiGroups).length > 0) {
            html += this.renderTurbineHealthKPIs(statsData, kpiGroups, healthIndicators, allTags);
        } else {
            // Auto-detection fallback
            html += this.renderAutoDetectedKPIs(statsData, allTags);
        }
        
        html += '</div>';
        gridDiv.innerHTML = html;
        
        console.log('✓ Turbine Health KPI Dashboard rendered successfully');
    },
    
    renderTurbineHealthKPIs(statsData, kpiGroups, healthIndicators, allTags) {
        // Get alarm limits configuration
        const pivotConfig = this.config?.PivotTableSettings || {};
        const alarmLimits = pivotConfig.AlarmLimits || {};
        const defaultLimits = pivotConfig.DefaultLimits || {};
        const healthThresholds = pivotConfig.HealthThresholds || { Good: 70, Warning: 85, Critical: 100 };
        const stabilityThresholds = pivotConfig.StabilityThresholds || { Stable: 15, Moderate: 30, Unstable: 50 };
        
        // Build parameter list grouped by equipment
        const parametersByGroup = {};
        for (const [groupKey, groupConfig] of Object.entries(kpiGroups)) {
            const groupTags = groupConfig.Parameters.filter(tag => allTags.includes(tag));
            if (groupTags.length > 0) {
                parametersByGroup[groupKey] = {
                    title: groupConfig.Title || groupKey,
                    icon: groupConfig.Icon || '📊',
                    tags: groupTags,
                    config: groupConfig
                };
            }
        }
        
        if (Object.keys(parametersByGroup).length === 0) {
            return '<p style="color: #fbbf24; text-align: center; padding: 20px;">No matching parameters found for configured KPI groups.</p>';
        }
        
        // Render CONDITION MONITORING pivot table
        let html = '<div style="margin-bottom: 25px; background: rgba(0, 0, 0, 0.3); padding: 20px; border-radius: 8px; border: 2px solid rgba(0, 212, 255, 0.4);">';
        html += '<h5 style="color: #00ff88; margin: 0 0 15px 0; font-size: 18px; border-bottom: 2px solid rgba(0, 255, 136, 0.4); padding-bottom: 10px;">🔬 Condition Monitoring - Turbine Health Status</h5>';
        html += '<div style="overflow-x: auto;"><table style="width: 100%; border-collapse: collapse; font-size: 12px;">';
        
        // Table header
        html += '<thead><tr style="background: linear-gradient(135deg, rgba(0, 212, 255, 0.25), rgba(0, 255, 136, 0.15));">';
        html += '<th style="padding: 12px; border: 2px solid rgba(0, 212, 255, 0.5); color: #00d4ff; text-align: left; font-weight: 700; position: sticky; left: 0; background: rgba(15, 52, 96, 0.95); z-index: 10; min-width: 200px;">Parameter</th>';
        html += '<th style="padding: 10px; border: 2px solid rgba(0, 212, 255, 0.4); color: #ffd700; font-weight: 600; text-align: center; min-width: 80px;">Mean<br/><span style="font-size:10px;color:#aaa;">(µm)</span></th>';
        html += '<th style="padding: 10px; border: 2px solid rgba(0, 212, 255, 0.4); color: #ffd700; font-weight: 600; text-align: center; min-width: 80px;">Std Dev<br/><span style="font-size:10px;color:#aaa;">(µm)</span></th>';
        html += '<th style="padding: 10px; border: 2px solid rgba(0, 212, 255, 0.4); color: #ffd700; font-weight: 600; text-align: center; min-width: 80px;">Peak<br/><span style="font-size:10px;color:#aaa;">(µm)</span></th>';
        html += '<th style="padding: 10px; border: 2px solid rgba(0, 212, 255, 0.4); color: #ffd700; font-weight: 600; text-align: center; min-width: 100px;">Health %<br/><span style="font-size:10px;color:#aaa;">(of Trip)</span></th>';
        html += '<th style="padding: 10px; border: 2px solid rgba(0, 212, 255, 0.4); color: #ffd700; font-weight: 600; text-align: center; min-width: 100px;">Stability<br/><span style="font-size:10px;color:#aaa;">(CV%)</span></th>';
        html += '<th style="padding: 10px; border: 2px solid rgba(0, 212, 255, 0.4); color: #ffd700; font-weight: 600; text-align: center; min-width: 100px;">Status</th>';
        html += '</tr></thead><tbody>';
        
        // Render each group
        for (const [groupKey, groupData] of Object.entries(parametersByGroup)) {
            // Group header row
            html += `<tr style="background: rgba(0, 255, 136, 0.15);"><td colspan="7" style="padding: 10px; border: 1px solid rgba(0, 212, 255, 0.3); color: #00ff88; font-weight: 700; font-size: 14px;">${groupData.icon} ${groupData.title}</td></tr>`;
            
            // Parameter rows
            groupData.tags.forEach((tag, idx) => {
                const stats = statsData[tag];
                if (!stats) {
                    html += `<tr><td colspan="7" style="padding: 10px; border: 1px solid rgba(0, 212, 255, 0.2); color: #888;">No data for ${tag}</td></tr>`;
                    return;
                }
                
                // Get limits for this tag
                const limits = this.getTagLimits(tag, alarmLimits, defaultLimits);
                
                // Calculate metrics
                const mean = stats.mean !== null && stats.mean !== undefined ? stats.mean : null;
                const stdDev = stats.std_dev !== null && stats.std_dev !== undefined ? stats.std_dev : null;
                const peak = stats.max !== null && stats.max !== undefined ? stats.max : null;
                
                // Health % (percentage of trip limit)
                let healthPercent = null;
                let healthClass = '';
                if (mean !== null && limits.Trip) {
                    healthPercent = (mean / limits.Trip) * 100;
                    if (healthPercent >= healthThresholds.Critical) {
                        healthClass = 'background: rgba(239, 68, 68, 0.4); color: #ff6b6b; font-weight: 700;';
                    } else if (healthPercent >= healthThresholds.Warning) {
                        healthClass = 'background: rgba(251, 191, 36, 0.4); color: #fbbf24; font-weight: 600;';
                    } else if (healthPercent >= healthThresholds.Good) {
                        healthClass = 'background: rgba(34, 197, 94, 0.3); color: #22c55e; font-weight: 600;';
                    } else {
                        healthClass = 'background: rgba(16, 185, 129, 0.4); color: #10b981; font-weight: 600;';
                    }
                }
                
                // Stability Index (CV%)
                let stabilityCV = null;
                let stabilityClass = '';
                if (mean !== null && stdDev !== null && mean !== 0) {
                    stabilityCV = (stdDev / mean) * 100;
                    if (stabilityCV >= stabilityThresholds.Unstable) {
                        stabilityClass = 'background: rgba(239, 68, 68, 0.3); color: #ff6b6b;';
                    } else if (stabilityCV >= stabilityThresholds.Moderate) {
                        stabilityClass = 'background: rgba(251, 191, 36, 0.3); color: #fbbf24;';
                    } else if (stabilityCV >= stabilityThresholds.Stable) {
                        stabilityClass = 'background: rgba(34, 197, 94, 0.2); color: #22c55e;';
                    } else {
                        stabilityClass = 'background: rgba(16, 185, 129, 0.3); color: #10b981;';
                    }
                }
                
                // Overall Status
                let status = 'GOOD';
                let statusIcon = '✓';
                let statusClass = 'background: rgba(16, 185, 129, 0.4); color: #10b981; font-weight: 700;';
                
                if (peak !== null && limits.Trip && peak >= limits.Trip) {
                    status = 'CRITICAL';
                    statusIcon = '🔴';
                    statusClass = 'background: rgba(239, 68, 68, 0.5); color: #ff6b6b; font-weight: 700; animation: pulse 2s infinite;';
                } else if (peak !== null && limits.Alarm && peak >= limits.Alarm) {
                    status = 'ALARM';
                    statusIcon = '🔶';
                    statusClass = 'background: rgba(239, 68, 68, 0.4); color: #ff6b6b; font-weight: 700;';
                } else if (mean !== null && limits.Warning && mean >= limits.Warning) {
                    status = 'WARNING';
                    statusIcon = '⚠️';
                    statusClass = 'background: rgba(251, 191, 36, 0.4); color: #fbbf24; font-weight: 600;';
                }
                
                const bgColor = idx % 2 === 0 ? 'rgba(0, 0, 0, 0.2)' : 'rgba(0, 212, 255, 0.05)';
                html += `<tr style="background: ${bgColor}; transition: all 0.2s;" onmouseover="this.style.background='rgba(0, 212, 255, 0.15)'" onmouseout="this.style.background='${bgColor}'">`;
                html += `<td style="padding: 10px; border: 1px solid rgba(0, 212, 255, 0.3); color: #e0e0e0; position: sticky; left: 0; background: ${bgColor}; z-index: 5; font-weight: 500;">${this.formatTagName(tag)}</td>`;
                html += `<td style="padding: 10px; border: 1px solid rgba(0, 212, 255, 0.3); text-align: center; color: #e0e0e0; font-family: 'Consolas', monospace;">${mean !== null ? mean.toFixed(2) : 'N/A'}</td>`;
                html += `<td style="padding: 10px; border: 1px solid rgba(0, 212, 255, 0.3); text-align: center; color: #e0e0e0; font-family: 'Consolas', monospace;">${stdDev !== null ? stdDev.toFixed(2) : 'N/A'}</td>`;
                html += `<td style="padding: 10px; border: 1px solid rgba(0, 212, 255, 0.3); text-align: center; color: #e0e0e0; font-family: 'Consolas', monospace;">${peak !== null ? peak.toFixed(2) : 'N/A'}</td>`;
                html += `<td style="padding: 10px; border: 1px solid rgba(0, 212, 255, 0.3); text-align: center; font-family: 'Consolas', monospace; ${healthClass}">${healthPercent !== null ? healthPercent.toFixed(1) + '%' : 'N/A'}</td>`;
                html += `<td style="padding: 10px; border: 1px solid rgba(0, 212, 255, 0.3); text-align: center; font-family: 'Consolas', monospace; ${stabilityClass}">${stabilityCV !== null ? stabilityCV.toFixed(1) + '%' : 'N/A'}</td>`;
                html += `<td style="padding: 10px; border: 1px solid rgba(0, 212, 255, 0.3); text-align: center; ${statusClass}">${statusIcon} ${status}</td>`;
                html += '</tr>';
            });
        }
        
        html += '</tbody></table></div></div>';
        
        // Add visual dashboard
        html += this.renderConditionMonitoringCharts(statsData, parametersByGroup, alarmLimits, defaultLimits);
        
        // Derived Health Indicators
        if (healthIndicators && Object.keys(healthIndicators).length > 0) {
            html += this.renderDerivedHealthIndicators(statsData, healthIndicators, allTags);
        }
        
        return html;
    },
    
    getTagLimits(tag, alarmLimits, defaultLimits) {
        // Try to get tag-specific limits first
        if (alarmLimits[tag]) {
            return alarmLimits[tag];
        }
        
        // Fallback to default limits based on tag type
        const upperTag = tag.toUpperCase();
        if (upperTag.includes('BEARING') && upperTag.includes('VIB')) {
            return defaultLimits.BearingVibration || { Warning: 25, Alarm: 30, Trip: 40 };
        } else if (upperTag.includes('SHAFT') && upperTag.includes('VIB')) {
            return defaultLimits.ShaftVibration || { Warning: 180, Alarm: 220, Trip: 300 };
        } else if (upperTag.includes('TEMP')) {
            return defaultLimits.Temperature || { Warning: 550, Alarm: 560, Trip: 570 };
        } else if (upperTag.includes('PRESSURE') || upperTag.includes('PRESS')) {
            return defaultLimits.Pressure || { Warning: 175, Alarm: 180, Trip: 185 };
        }
        
        // Ultimate fallback
        return { Warning: null, Alarm: null, Trip: null };
    },
    
    renderConditionMonitoringCharts(statsData, parametersByGroup, alarmLimits, defaultLimits) {
        // Prepare chart data
        const healthData = [];
        const stabilityData = [];
        const statusData = { GOOD: 0, WARNING: 0, ALARM: 0, CRITICAL: 0 };
        
        for (const [groupKey, groupData] of Object.entries(parametersByGroup)) {
            groupData.tags.forEach(tag => {
                const stats = statsData[tag];
                if (!stats) return;
                
                const limits = this.getTagLimits(tag, alarmLimits, defaultLimits);
                const mean = stats.mean;
                const stdDev = stats.std_dev;
                const peak = stats.max;
                const tagLabel = this.formatTagName(tag);
                
                // Health % data
                if (mean !== null && mean !== undefined && limits.Trip) {
                    healthData.push({
                        tag: tagLabel,
                        value: (mean / limits.Trip) * 100,
                        group: groupData.title,
                        tripLimit: limits.Trip
                    });
                }
                
                // Stability data
                if (mean !== null && mean !== undefined && stdDev !== null && stdDev !== undefined && mean !== 0) {
                    stabilityData.push({
                        tag: tagLabel,
                        value: (stdDev / mean) * 100,
                        group: groupData.title
                    });
                }
                
                // Status count
                if (peak !== null && peak !== undefined && limits.Trip && peak >= limits.Trip) {
                    statusData.CRITICAL++;
                } else if (peak !== null && peak !== undefined && limits.Alarm && peak >= limits.Alarm) {
                    statusData.ALARM++;
                } else if (mean !== null && mean !== undefined && limits.Warning && mean >= limits.Warning) {
                    statusData.WARNING++;
                } else {
                    statusData.GOOD++;
                }
            });
        }
        
        let html = '<div style="margin-top: 30px;"><h5 style="color: #00d4ff; margin: 0 0 20px 0; font-size: 18px; border-bottom: 2px solid rgba(0, 212, 255, 0.4); padding-bottom: 10px;">📊 Condition Monitoring Dashboard</h5>';
        html += '<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(400px, 1fr)); gap: 20px;">';
        
        // Chart containers
        html += `
            <div style="background: rgba(0, 0, 0, 0.3); padding: 20px; border-radius: 8px; border: 1px solid rgba(0, 212, 255, 0.3);">
                <h6 style="color: #ffd700; margin: 0 0 15px 0; font-size: 14px;">Health Status (% of Trip Limit)</h6>
                <div id="healthStatusChart" style="width: 100%; height: 300px;"></div>
            </div>
            <div style="background: rgba(0, 0, 0, 0.3); padding: 20px; border-radius: 8px; border: 1px solid rgba(0, 212, 255, 0.3);">
                <h6 style="color: #ffd700; margin: 0 0 15px 0; font-size: 14px;">Stability Index (CV%)</h6>
                <div id="stabilityIndexChart" style="width: 100%; height: 300px;"></div>
            </div>
            <div style="background: rgba(0, 0, 0, 0.3); padding: 20px; border-radius: 8px; border: 1px solid rgba(0, 212, 255, 0.3);">
                <h6 style="color: #ffd700; margin: 0 0 15px 0; font-size: 14px;">Overall Status Distribution</h6>
                <div id="statusDistChart" style="width: 100%; height: 300px;"></div>
            </div>
        `;
        
        html += '</div></div>';
        
        // Render charts after DOM ready
        setTimeout(() => {
            this.renderHealthStatusChart(healthData);
            this.renderStabilityIndexChart(stabilityData);
            this.renderStatusDistributionChart(statusData);
        }, 100);
        
        return html;
    },
    
    renderHealthStatusChart(data) {
        if (data.length === 0 || !document.getElementById('healthStatusChart')) return;
        
        const traces = [{
            x: data.map(d => d.tag),
            y: data.map(d => d.value),
            type: 'bar',
            marker: {
                color: data.map(d => {
                    if (d.value >= 100) return 'rgba(239, 68, 68, 0.9)';
                    if (d.value >= 85) return 'rgba(251, 191, 36, 0.9)';
                    if (d.value >= 70) return 'rgba(34, 197, 94, 0.8)';
                    return 'rgba(16, 185, 129, 0.9)';
                }),
                line: { color: '#00d4ff', width: 1 }
            },
            text: data.map(d => d.value.toFixed(1) + '%'),
            textposition: 'outside',
            textfont: { color: '#e0e0e0', size: 10 }
        }];
        
        const layout = {
            paper_bgcolor: 'rgba(0,0,0,0)',
            plot_bgcolor: 'rgba(0,0,0,0.2)',
            font: { color: '#e0e0e0', size: 10 },
            margin: { l: 50, r: 20, t: 20, b: 100 },
            xaxis: { 
                tickangle: -45,
                gridcolor: 'rgba(0, 212, 255, 0.1)',
                title: { text: 'Parameters', font: { size: 11 } }
            },
            yaxis: { 
                gridcolor: 'rgba(0, 212, 255, 0.1)',
                title: { text: '% of Trip Limit', font: { size: 11 } }
            },
            shapes: [
                { type: 'line', x0: -0.5, x1: data.length - 0.5, y0: 70, y1: 70, line: { color: '#22c55e', width: 2, dash: 'dash' }},
                { type: 'line', x0: -0.5, x1: data.length - 0.5, y0: 85, y1: 85, line: { color: '#fbbf24', width: 2, dash: 'dash' }},
                { type: 'line', x0: -0.5, x1: data.length - 0.5, y0: 100, y1: 100, line: { color: '#ff6b6b', width: 2, dash: 'dash' }}
            ]
        };
        
        Plotly.newPlot('healthStatusChart', traces, layout, { responsive: true, displayModeBar: false });
    },
    
    renderStabilityIndexChart(data) {
        if (data.length === 0 || !document.getElementById('stabilityIndexChart')) return;
        
        const traces = [{
            x: data.map(d => d.tag),
            y: data.map(d => d.value),
            type: 'bar',
            marker: {
                color: data.map(d => {
                    if (d.value >= 50) return 'rgba(239, 68, 68, 0.9)';
                    if (d.value >= 30) return 'rgba(251, 191, 36, 0.9)';
                    if (d.value >= 15) return 'rgba(34, 197, 94, 0.8)';
                    return 'rgba(16, 185, 129, 0.9)';
                }),
                line: { color: '#00ff88', width: 1 }
            },
            text: data.map(d => d.value.toFixed(1) + '%'),
            textposition: 'outside',
            textfont: { color: '#e0e0e0', size: 10 }
        }];
        
        const layout = {
            paper_bgcolor: 'rgba(0,0,0,0)',
            plot_bgcolor: 'rgba(0,0,0,0.2)',
            font: { color: '#e0e0e0', size: 10 },
            margin: { l: 50, r: 20, t: 20, b: 100 },
            xaxis: { 
                tickangle: -45,
                gridcolor: 'rgba(0, 212, 255, 0.1)',
                title: { text: 'Parameters', font: { size: 11 } }
            },
            yaxis: { 
                gridcolor: 'rgba(0, 212, 255, 0.1)',
                title: { text: 'CV% (Lower is Better)', font: { size: 11 } }
            },
            shapes: [
                { type: 'line', x0: -0.5, x1: data.length - 0.5, y0: 15, y1: 15, line: { color: '#22c55e', width: 2, dash: 'dash' }},
                { type: 'line', x0: -0.5, x1: data.length - 0.5, y0: 30, y1: 30, line: { color: '#fbbf24', width: 2, dash: 'dash' }}
            ]
        };
        
        Plotly.newPlot('stabilityIndexChart', traces, layout, { responsive: true, displayModeBar: false });
    },
    
    renderStatusDistributionChart(data) {
        if (!document.getElementById('statusDistChart')) return;
        
        const traces = [{
            values: [data.GOOD, data.WARNING, data.ALARM, data.CRITICAL],
            labels: ['GOOD', 'WARNING', 'ALARM', 'CRITICAL'],
            type: 'pie',
            marker: {
                colors: ['rgba(16, 185, 129, 0.9)', 'rgba(251, 191, 36, 0.9)', 'rgba(239, 68, 68, 0.7)', 'rgba(220, 38, 38, 0.9)']
            },
            textinfo: 'label+percent+value',
            textfont: { color: '#fff', size: 12, family: 'Arial Black' },
            hole: 0.4
        }];
        
        const layout = {
            paper_bgcolor: 'rgba(0,0,0,0)',
            plot_bgcolor: 'rgba(0,0,0,0)',
            font: { color: '#e0e0e0', size: 11 },
            margin: { l: 20, r: 20, t: 20, b: 20 },
            showlegend: true,
            legend: {
                x: 0, y: 0,
                bgcolor: 'rgba(0, 0, 0, 0.5)',
                bordercolor: 'rgba(0, 212, 255, 0.5)',
                borderwidth: 1
            }
        };
        
        Plotly.newPlot('statusDistChart', traces, layout, { responsive: true, displayModeBar: false });
    },
    

    
    renderAutoDetectedKPIs(statsData, allTags) {
        const groups = this.autoDetectGroups(allTags);
        
        let html = `<div style="background: rgba(251, 191, 36, 0.15); padding: 15px; border-radius: 8px; border: 1px solid rgba(251, 191, 36, 0.3); margin-bottom: 20px;">
            <p style="margin: 0; color: #fbbf24; font-size: 13px;"><strong>ℹ️ Auto-Detection Mode:</strong> No PivotTableSettings found in configuration. 
            Automatically grouping parameters by type. Add PivotTableSettings to trends-config.json for custom turbine health KPI grouping.</p>
        </div>`;
        
        for (const [groupName, groupTags] of Object.entries(groups)) {
            if (groupTags.length === 0) continue;
            
            html += `<div style="margin-bottom: 25px; background: rgba(0, 0, 0, 0.2); padding: 20px; border-radius: 8px; border: 1px solid rgba(0, 212, 255, 0.2);">`;
            html += `<h5 style="color: #00ff88; margin: 0 0 15px 0; font-size: 16px; border-bottom: 2px solid rgba(0, 255, 136, 0.3); padding-bottom: 8px;">📊 ${groupName}</h5>`;
            html += '<div style="overflow-x: auto;"><table style="width: 100%; border-collapse: collapse; font-size: 13px;">';
            
            // Table header
            html += '<thead><tr style="background: rgba(0, 212, 255, 0.15);">';
            html += '<th style="padding: 12px; border: 1px solid rgba(0, 212, 255, 0.3); color: #00d4ff; text-align: left; font-weight: 600;">Metric</th>';
            groupTags.forEach(tag => {
                html += `<th style="padding: 12px; border: 1px solid rgba(0, 212, 255, 0.3); color: #ffd700; font-weight: 600;">${this.formatTagName(tag)}</th>`;
            });
            html += '</tr></thead><tbody>';
            
            const defaultMetrics = ['Mean', 'Min', 'Max', 'StdDev', 'Peak'];
            defaultMetrics.forEach((metric, idx) => {
                const bgColor = idx % 2 === 0 ? 'rgba(0, 0, 0, 0.1)' : 'rgba(0, 212, 255, 0.05)';
                html += `<tr style="background: ${bgColor};">`;
                html += `<td style="padding: 10px; border: 1px solid rgba(0, 212, 255, 0.2); color: #00d4ff; font-weight: 500;">${metric}</td>`;
                
                groupTags.forEach(tag => {
                    const value = this.calculateMetric(metric, statsData[tag], {}, tag);
                    html += `<td style="padding: 10px; border: 1px solid rgba(0, 212, 255, 0.2); text-align: center; color: #e0e0e0;">${value}</td>`;
                });
                
                html += '</tr>';
            });
            
            html += '</tbody></table></div></div>';
        }
        
        return html;
    },
    
    autoDetectGroups(tags) {
        const groups = {
            'Vibration Parameters': [],
            'Temperature Parameters': [],
            'Pressure Parameters': [],
            'Flow Parameters': [],
            'Load Parameters': [],
            'Other Parameters': []
        };

        tags.forEach(tag => {
            const upperTag = tag.toUpperCase();
            if (upperTag.includes('VIB') || upperTag.includes('BEARING') || upperTag.includes('SHAFT')) {
                groups['Vibration Parameters'].push(tag);
            } else if (upperTag.includes('TEMP')) {
                groups['Temperature Parameters'].push(tag);
            } else if (upperTag.includes('PRESSURE') || upperTag.includes('PRESS')) {
                groups['Pressure Parameters'].push(tag);
            } else if (upperTag.includes('FLOW')) {
                groups['Flow Parameters'].push(tag);
            } else if (upperTag.includes('LOAD') || upperTag.includes('MW')) {
                groups['Load Parameters'].push(tag);
            } else {
                groups['Other Parameters'].push(tag);
            }
        });

        return groups;
    },
    
    calculateMetric(metric, tagStats, groupConfig, tagName) {
        if (!tagStats) return 'N/A';
        
        switch (metric) {
            case 'Mean':
                return tagStats.mean !== null && tagStats.mean !== undefined ? tagStats.mean.toFixed(2) : 'N/A';
            
            case 'Min':
                return tagStats.min !== null && tagStats.min !== undefined ? tagStats.min.toFixed(2) : 'N/A';
            
            case 'Max':
            case 'Peak':
                return tagStats.max !== null && tagStats.max !== undefined ? tagStats.max.toFixed(2) : 'N/A';
            
            case 'StdDev':
                return tagStats.std_dev !== null && tagStats.std_dev !== undefined ? tagStats.std_dev.toFixed(2) : 'N/A';
            
            case '95thPercentile':
                if (tagStats.mean !== null && tagStats.mean !== undefined && tagStats.std_dev !== null && tagStats.std_dev !== undefined) {
                    const p95 = tagStats.mean + (1.645 * tagStats.std_dev);
                    return p95.toFixed(2);
                }
                return 'N/A';
            
            case 'DeviationFromDesign':
                const designValue = groupConfig.DesignValues?.[tagName] || groupConfig.DesignLimits;
                if (designValue && tagStats.mean !== null && tagStats.mean !== undefined) {
                    const deviation = ((tagStats.mean - designValue) / designValue * 100);
                    return `${deviation > 0 ? '+' : ''}${deviation.toFixed(1)}%`;
                }
                return 'N/A';
            
            case 'MaxToMeanRatio':
                if (tagStats.max !== null && tagStats.max !== undefined && tagStats.mean !== null && tagStats.mean !== undefined && tagStats.mean !== 0) {
                    return (tagStats.max / tagStats.mean).toFixed(2);
                }
                return 'N/A';
            
            case 'AlarmingPoints':
                const alarmThreshold = groupConfig.AlarmThreshold;
                if (alarmThreshold && tagStats.max !== null && tagStats.max !== undefined) {
                    return tagStats.max > alarmThreshold ? '⚠️ YES' : '✓ NO';
                }
                return 'N/A';
            
            case 'CV':
                if (tagStats.mean !== null && tagStats.mean !== undefined && tagStats.std_dev !== null && tagStats.std_dev !== undefined && tagStats.mean !== 0) {
                    return `${((tagStats.std_dev / tagStats.mean) * 100).toFixed(1)}%`;
                }
                return 'N/A';
            
            case 'Range':
                if (tagStats.min !== null && tagStats.min !== undefined && tagStats.max !== null && tagStats.max !== undefined) {
                    return (tagStats.max - tagStats.min).toFixed(2);
                }
                return 'N/A';
            
            case 'LoadToSteamRatio':
            case 'MWperTPH':
            case 'TrendDrift':
            case 'HourlyDrift':
            case 'CorrelationToLoad':
                return 'Calc'; // Placeholder for cross-tag calculations
            
            default:
                return tagStats.mean !== null && tagStats.mean !== undefined ? tagStats.mean.toFixed(2) : 'N/A';
        }
    },
    
    getHealthCssClass(metric, value, groupConfig, tagName) {
        if (metric === 'DeviationFromDesign') {
            const numValue = parseFloat(value);
            if (isNaN(numValue)) return '';
            
            if (Math.abs(numValue) > 10) return 'background: rgba(239, 68, 68, 0.3); color: #ff6b6b;';
            if (Math.abs(numValue) > 5) return 'background: rgba(251, 191, 36, 0.3); color: #fbbf24;';
            return 'background: rgba(16, 185, 129, 0.3); color: #10b981;';
        }
        
        if (metric === 'AlarmingPoints' && value.includes('YES')) {
            return 'background: rgba(239, 68, 68, 0.3); color: #ff6b6b; font-weight: 600;';
        }
        
        return '';
    },
    
    renderDerivedHealthIndicators(statsData, healthIndicators, allTags) {
        let html = '<div style="margin-top: 25px;"><h5 style="color: #00d4ff; margin: 0 0 15px 0; font-size: 16px; border-bottom: 2px solid rgba(0, 212, 255, 0.3); padding-bottom: 8px;">💡 Derived Health Indicators</h5>';
        html += '<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 15px;">';
        
        // Bearing Health Index
        if (healthIndicators.BearingHealthIndex?.Enabled) {
            const designLimits = healthIndicators.BearingHealthIndex.DesignLimits || {};
            const bearingTags = Object.keys(designLimits).filter(tag => allTags.includes(tag));
            
            if (bearingTags.length > 0) {
                let avgHealthIndex = 0;
                let count = 0;
                
                bearingTags.forEach(tag => {
                    const mean = statsData[tag]?.mean;
                    const limit = designLimits[tag];
                    if (mean !== null && mean !== undefined && limit) {
                        avgHealthIndex += (mean / limit) * 100;
                        count++;
                    }
                });
                
                if (count > 0) {
                    avgHealthIndex = avgHealthIndex / count;
                    const healthColor = avgHealthIndex > 80 ? '#ff6b6b' : avgHealthIndex > 60 ? '#fbbf24' : '#10b981';
                    const bgColor = avgHealthIndex > 80 ? 'rgba(239, 68, 68, 0.15)' : avgHealthIndex > 60 ? 'rgba(251, 191, 36, 0.15)' : 'rgba(16, 185, 129, 0.15)';
                    const borderColor = avgHealthIndex > 80 ? 'rgba(239, 68, 68, 0.4)' : avgHealthIndex > 60 ? 'rgba(251, 191, 36, 0.4)' : 'rgba(16, 185, 129, 0.4)';
                    
                    html += `<div style="background: ${bgColor}; border: 2px solid ${borderColor}; border-radius: 8px; padding: 20px; text-align: center;">
                        <h6 style="margin: 0 0 10px 0; color: #00d4ff; font-size: 14px;">Bearing Health Index</h6>
                        <div style="font-size: 36px; font-weight: 700; color: ${healthColor}; margin: 10px 0;">${avgHealthIndex.toFixed(1)}%</div>
                        <small style="color: #999; font-size: 11px;">Lower is better (% of design limit)</small>
                    </div>`;
                }
            }
        }
        
        // Shaft Stability Index
        if (healthIndicators.ShaftStabilityIndex?.Enabled) {
            const shaftTags = allTags.filter(tag => tag.toUpperCase().includes('SHAFT'));
            
            if (shaftTags.length > 0) {
                let avgStability = 0;
                let count = 0;
                
                shaftTags.forEach(tag => {
                    const mean = statsData[tag]?.mean;
                    const stdDev = statsData[tag]?.std_dev;
                    if (mean !== null && mean !== undefined && stdDev !== null && stdDev !== undefined && mean !== 0) {
                        avgStability += stdDev / mean;
                        count++;
                    }
                });
                
                if (count > 0) {
                    avgStability = avgStability / count;
                    const goodThreshold = healthIndicators.ShaftStabilityIndex.GoodThreshold || 0.15;
                    const warningThreshold = healthIndicators.ShaftStabilityIndex.WarningThreshold || 0.30;
                    
                    const healthColor = avgStability > warningThreshold ? '#ff6b6b' : avgStability > goodThreshold ? '#fbbf24' : '#10b981';
                    const bgColor = avgStability > warningThreshold ? 'rgba(239, 68, 68, 0.15)' : avgStability > goodThreshold ? 'rgba(251, 191, 36, 0.15)' : 'rgba(16, 185, 129, 0.15)';
                    const borderColor = avgStability > warningThreshold ? 'rgba(239, 68, 68, 0.4)' : avgStability > goodThreshold ? 'rgba(251, 191, 36, 0.4)' : 'rgba(16, 185, 129, 0.4)';
                    
                    html += `<div style="background: ${bgColor}; border: 2px solid ${borderColor}; border-radius: 8px; padding: 20px; text-align: center;">
                        <h6 style="margin: 0 0 10px 0; color: #00d4ff; font-size: 14px;">Shaft Stability Index</h6>
                        <div style="font-size: 36px; font-weight: 700; color: ${healthColor}; margin: 10px 0;">${avgStability.toFixed(3)}</div>
                        <small style="color: #999; font-size: 11px;">Lower is better (StdDev/Mean)</small>
                    </div>`;
                }
            }
        }
        
        // Steam Stability Score
        if (healthIndicators.SteamStabilityScore?.Enabled) {
            const steamParams = healthIndicators.SteamStabilityScore.Parameters || [];
            const steamTags = steamParams.filter(tag => allTags.includes(tag));
            
            if (steamTags.length > 0) {
                let avgCV = 0;
                let count = 0;
                
                steamTags.forEach(tag => {
                    const mean = statsData[tag]?.mean;
                    const stdDev = statsData[tag]?.std_dev;
                    if (mean !== null && mean !== undefined && stdDev !== null && stdDev !== undefined && mean !== 0) {
                        avgCV += (stdDev / mean) * 100;
                        count++;
                    }
                });
                
                if (count > 0) {
                    avgCV = avgCV / count;
                    const stabilityScore = 100 - avgCV;
                    const healthColor = stabilityScore < 90 ? '#ff6b6b' : stabilityScore < 95 ? '#fbbf24' : '#10b981';
                    const bgColor = stabilityScore < 90 ? 'rgba(239, 68, 68, 0.15)' : stabilityScore < 95 ? 'rgba(251, 191, 36, 0.15)' : 'rgba(16, 185, 129, 0.15)';
                    const borderColor = stabilityScore < 90 ? 'rgba(239, 68, 68, 0.4)' : stabilityScore < 95 ? 'rgba(251, 191, 36, 0.4)' : 'rgba(16, 185, 129, 0.4)';
                    
                    html += `<div style="background: ${bgColor}; border: 2px solid ${borderColor}; border-radius: 8px; padding: 20px; text-align: center;">
                        <h6 style="margin: 0 0 10px 0; color: #00d4ff; font-size: 14px;">Steam Stability Score</h6>
                        <div style="font-size: 36px; font-weight: 700; color: ${healthColor}; margin: 10px 0;">${stabilityScore.toFixed(1)}</div>
                        <small style="color: #999; font-size: 11px;">Higher is better (100 - CV%)</small>
                    </div>`;
                }
            }
        }
        
        html += '</div></div>';
        return html;
    },
    
    formatTagName(tag) {
        return tag.replace(/_/g, ' ').replace(/-/g, ' ');
    },

    /**
     * Calculate correlation between two arrays via Python API
     */
    async calculateCorrelation(arr1, arr2) {
        if (arr1.length !== arr2.length || arr1.length === 0) return 0;

        try {
            const response = await fetch(`${window.location.origin}/api/v1/analytics/correlation`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ arr1, arr2 })
            });
            
            if (!response.ok) return 0;
            const result = await response.json();
            return result.correlation || 0;
        } catch (error) {
            console.error('Correlation API Error:', error);
            throw error;
        }
    },

    /**
     * Show message to user
     */
    showMessage(message, type = 'info') {
        const colors = {
            success: '#00ff88',
            warning: '#ffd700',
            error: '#ff6b6b',
            info: '#00d4ff'
        };

        const msgDiv = document.createElement('div');
        msgDiv.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: linear-gradient(135deg, rgba(26, 26, 46, 0.95), rgba(15, 52, 96, 0.95));
            border: 2px solid ${colors[type]};
            color: ${colors[type]};
            padding: 15px 25px;
            border-radius: 8px;
            font-size: 14px;
            font-weight: bold;
            z-index: 10000;
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.5);
            animation: slideIn 0.3s ease-out;
        `;
        msgDiv.textContent = message;
        document.body.appendChild(msgDiv);

        setTimeout(() => {
            msgDiv.style.opacity = '0';
            msgDiv.style.transition = 'opacity 0.3s';
            setTimeout(() => msgDiv.remove(), 300);
        }, 3000);
    }
};

// Export for use in main trends.js (both Node.js and browser)
if (typeof module !== 'undefined' && module.exports) {
    module.exports = BIAnalytics;
} else if (typeof window !== 'undefined') {
    window.BIAnalytics = BIAnalytics;
}
