/**
 * CHART RENDERER MODULE
 * Handles all Plotly chart rendering
 */

class ChartRenderer {
    
    static tagColors = [
        '#00d4ff', '#00ff88', '#ffd700', '#ff6b6b', '#a78bfa',
        '#fb923c', '#38bdf8', '#4ade80', '#f472b6', '#facc15'
    ];
    
    /**
     * Render time-series chart with multiple Y-axes for different scales
     * @param {Array} data - Data array
     * @param {Array} tags - Tags to plot
     * @param {Boolean} normalized - Use normalized values
     * @param {String} containerId - Container div ID
     * @param {String} mode - Chart mode: 'lines', 'scatter', 'boxplot', 'distribution'
     */
    static renderMultiScaleChart(data, tags, normalized = false, containerId = 'trendChart', mode = 'lines') {
        if (tags.length === 0) return;

        const traces = [];
        const yaxisConfig = {};
        const MAX_POINTS = 12000; // protect UI from huge payloads

        tags.forEach((tag, index) => {
            const color = this.tagColors[index % this.tagColors.length];
            const yaxis = index === 0 ? 'y' : `y${index + 1}`;

            const times = [];
            const rawValues = [];

            // Single pass gather valid points
            for (let i = 0; i < data.length; i++) {
                const d = data[i];
                if (!d || !d.Timestamp) continue;
                const ts = new Date(d.Timestamp);
                if (isNaN(ts.getTime())) continue;
                const val = d[tag];
                if (val === null || val === undefined || isNaN(val)) continue;
                times.push(ts);
                rawValues.push(val);
            }

            if (times.length === 0) {
                // Skip this tag if no valid data (use continue equivalent for forEach)
                console.warn(`No valid data for tag: ${tag}`);
                return; // This returns from forEach callback, not the main function
            }

            // Normalize if requested
            let plotValues = rawValues;
            if (normalized) {
                const norm = DataProcessor.normalizeToScale(rawValues);
                plotValues = norm.normalized;
            }

            // Decimate to avoid heavy scattergl payloads
            if (plotValues.length > MAX_POINTS) {
                const step = Math.ceil(plotValues.length / MAX_POINTS);
                const decimatedTimes = [];
                const decimatedPlot = [];
                const decimatedRaw = [];
                for (let i = 0; i < plotValues.length; i += step) {
                    decimatedTimes.push(times[i]);
                    decimatedPlot.push(plotValues[i]);
                    decimatedRaw.push(rawValues[i]);
                }
                times.splice(0, times.length, ...decimatedTimes);
                plotValues = decimatedPlot;
                rawValues.splice(0, rawValues.length, ...decimatedRaw);
            }

            const trace = {
                x: times,
                y: plotValues,
                name: tag + (normalized ? ' (Normalized)' : ''),
                type: 'scattergl',
                mode: mode === 'lines' ? 'lines' : 'markers',
                yaxis: yaxis,
                customdata: rawValues,
                hovertemplate: normalized 
                    ? `<b>${tag}</b><br>Normalized: %{y:.2f}%<br>Original: %{customdata:.4f}<extra></extra>`
                    : `<b>${tag}</b><br>Value: %{y:.4f}<extra></extra>`
            };

            if (mode === 'lines') {
                trace.line = { color: color, width: 2 };
            } else if (mode === 'scatter') {
                trace.marker = { color: color, size: 4, opacity: 0.6 };
            }

            traces.push(trace);

            const axisKey = index === 0 ? 'yaxis' : `yaxis${index + 1}`;
            yaxisConfig[axisKey] = {
                title: normalized ? 'Normalized (%)' : tag,
                titlefont: { color: color },
                tickfont: { color: color },
                gridcolor: 'rgba(0, 212, 255, 0.1)',
                color: color,
                overlaying: index === 0 ? undefined : 'y',
                side: index % 2 === 0 ? 'left' : 'right',
                position: index === 0 ? 0 : (index % 2 === 0 ? 0.05 * Math.floor(index / 2) : 1 - 0.05 * Math.floor(index / 2)),
                autorange: true
            };
        });

        const layout = {
            paper_bgcolor: 'rgba(0,0,0,0)',
            plot_bgcolor: 'rgba(15, 52, 96, 0.3)',
            font: { color: '#e0e0e0', family: 'Segoe UI', size: 12 },
            title: normalized ? 'Normalized Trends (0-100%)' : 'Multi-Scale Trends (Independent Y-Axes)',
            xaxis: {
                title: 'Time',
                gridcolor: 'rgba(0, 212, 255, 0.1)',
                color: '#00d4ff',
                autorange: true,
                type: 'date',
                fixedrange: false
            },
            ...yaxisConfig,
            height: 600,
            hovermode: 'closest',
            showlegend: true,
            legend: {
                bgcolor: 'rgba(0, 0, 0, 0.5)',
                bordercolor: '#00d4ff',
                borderwidth: 1
            },
            autosize: true,
            dragmode: 'zoom'
        };

        const config = {
            responsive: true,
            displayModeBar: true,
            modeBarButtonsToRemove: ['lasso2d', 'select2d'],
            scrollZoom: true,
            doubleClick: 'reset',
            displaylogo: false
        };

        const container = document.getElementById(containerId);
        if (!container) return;

        if (traces.length === 0) {
            container.innerHTML = '<div style="color:#888;text-align:center;padding:30px;">No data available for selected tags</div>';
            return;
        }

        Plotly.react(containerId, traces, layout, config);
    }
    
    /**
     * Render box plot comparison using Python API
     * @param {Array} data - Data array (not used, kept for compatibility)
     * @param {Array} tags - Tags to plot
     * @param {String} containerId - Container div ID
     */
    static async renderBoxPlot(data, tags, containerId = 'trendChart') {
        // Show loading state
        const container = document.getElementById(containerId);
        if (container) {
            container.innerHTML = '<div style="text-align: center; padding: 60px; color: #00d4ff;"><div style="font-size: 48px; margin-bottom: 15px;">⏳</div><div style="font-size: 18px;">Loading box plot...</div></div>';
        }
        
        try {
            // Get date range from UI
            const startDate = document.getElementById('startDate')?.value;
            const endDate = document.getElementById('endDate')?.value;
            const useInterpolated = document.getElementById('useInterpolatedCheckbox')?.checked || false;
            
            // Call Python API to calculate box plot data
            const response = await fetch(`/api/analytics/boxplot?start_date=${startDate}&end_date=${endDate}&tags=${encodeURIComponent(JSON.stringify(tags))}&use_interpolated=${useInterpolated}`);
            const result = await response.json();
            
            if (!result.success || !result.boxplot_data) {
                throw new Error('Failed to load box plot data from server');
            }
            
            // Create traces from server-calculated data
            const traces = result.boxplot_data.map((item, index) => {
                const color = this.tagColors[index % this.tagColors.length];
                return {
                    y: item.values,
                    name: item.tag,
                    type: 'box',
                    marker: { color: color },
                    boxmean: 'sd'
                };
            });
            
            const layout = {
                paper_bgcolor: 'rgba(0,0,0,0)',
                plot_bgcolor: 'rgba(15, 52, 96, 0.3)',
                font: { color: '#e0e0e0', family: 'Segoe UI', size: 12 },
                title: 'Box Plot - Statistical Distribution',
                yaxis: { 
                    title: 'Value', 
                    gridcolor: 'rgba(0, 212, 255, 0.1)', 
                    color: '#00d4ff',
                    autorange: true
                },
                height: 500
            };
            
            // Clear loading and render
            if (container) container.innerHTML = '';
            await new Promise(resolve => setTimeout(resolve, 10));
            
            Plotly.newPlot(containerId, traces, layout, { responsive: true });
            console.log('✓ Box plot rendered from Python API');
            
        } catch (error) {
            console.error('Error rendering box plot:', error);
            if (container) {
                container.innerHTML = `<div style="color: #ff6b6b; text-align: center; padding: 40px;">❌ Error: ${error.message}</div>`;
            }
        }
    }
    
    /**
     * Render distribution histogram with normal curve using Python API
     * @param {Array} data - Data array (not used, kept for compatibility)
     * @param {Array} tags - Tags to plot
     * @param {String} containerId - Container div ID
     */
    static async renderDistribution(data, tags, containerId = 'trendChart') {
        // Show loading state
        const container = document.getElementById(containerId);
        if (container) {
            container.innerHTML = '<div style="text-align: center; padding: 60px; color: #00d4ff;"><div style="font-size: 48px; margin-bottom: 15px;">⏳</div><div style="font-size: 18px;">Loading distribution...</div></div>';
        }
        
        try {
            // Get date range from UI
            const startDate = document.getElementById('startDate')?.value;
            const endDate = document.getElementById('endDate')?.value;
            const useInterpolated = document.getElementById('useInterpolatedCheckbox')?.checked || false;
            
            // Call Python API to calculate distribution data
            const response = await fetch(`/api/analytics/distribution?start_date=${startDate}&end_date=${endDate}&tags=${encodeURIComponent(JSON.stringify(tags))}&use_interpolated=${useInterpolated}&bins=30`);
            const result = await response.json();
            
            if (!result.success || !result.distribution_data) {
                throw new Error('Failed to load distribution data from server');
            }
            
            // Create traces from server-calculated data
            const traces = [];
            result.distribution_data.forEach((item, index) => {
                const color = this.tagColors[index % this.tagColors.length];
                
                // Histogram trace
                traces.push({
                    x: item.values,
                    name: item.tag,
                    type: 'histogram',
                    marker: { color: color, opacity: 0.7 },
                    nbinsx: 30
                });
                
                // Normal distribution curve trace
                traces.push({
                    x: item.normal_curve.x,
                    y: item.normal_curve.y,
                    name: `${item.tag} (Normal Curve)`,
                    type: 'scatter',
                    mode: 'lines',
                    line: { color: color, width: 3, dash: 'dash' }
                });
            });
            
            const layout = {
                paper_bgcolor: 'rgba(0,0,0,0)',
                plot_bgcolor: 'rgba(15, 52, 96, 0.3)',
                font: { color: '#e0e0e0', family: 'Segoe UI', size: 12 },
                title: 'Distribution Analysis with Normal Curve',
                xaxis: { 
                    title: 'Value', 
                    gridcolor: 'rgba(0, 212, 255, 0.1)', 
                    color: '#00d4ff',
                    autorange: true
                },
                yaxis: { 
                    title: 'Frequency', 
                    gridcolor: 'rgba(0, 212, 255, 0.1)', 
                    color: '#00d4ff',
                    autorange: true
                },
                height: 500,
                barmode: 'overlay'
            };
            
            // Clear loading and render
            if (container) container.innerHTML = '';
            await new Promise(resolve => setTimeout(resolve, 10));
            
            Plotly.newPlot(containerId, traces, layout, { responsive: true });
            console.log('✓ Distribution rendered from Python API');
            
        } catch (error) {
            console.error('Error rendering distribution:', error);
            if (container) {
                container.innerHTML = `<div style="color: #ff6b6b; text-align: center; padding: 40px;">❌ Error: ${error.message}</div>`;
            }
        }
    }
    
    /**
     * Render comparison bar chart for Best/Worst analysis
     * @param {String} targetTag - Target tag name
     * @param {Object} bestStats - Statistics at best moment
     * @param {Object} worstStats - Statistics at worst moment
     * @param {String} containerId - Container div ID
     */
    static renderBestWorstComparison(targetTag, bestStats, worstStats, containerId = 'peakBarChart') {
        const tags = Object.keys(bestStats).filter(tag => bestStats[tag] !== null && worstStats[tag] !== null);
        
        if (tags.length === 0) {
            document.getElementById(containerId).innerHTML = '<p style="color: #888;">No comparison data available</p>';
            return;
        }
        
        const traces = [
            // Average baseline
            {
                x: tags,
                y: tags.map(tag => bestStats[tag].mean),
                name: 'Average (Baseline)',
                type: 'bar',
                marker: { color: 'rgba(255, 255, 255, 0.2)', line: { color: '#888', width: 1 } }
            },
            // Best case
            {
                x: tags,
                y: tags.map(tag => bestStats[tag].atPeak || 0),
                name: '📈 At Best Case',
                type: 'bar',
                marker: { color: '#00ff88', opacity: 0.8 }
            },
            // Worst case
            {
                x: tags,
                y: tags.map(tag => worstStats[tag].atPeak || 0),
                name: '📉 At Worst Case',
                type: 'bar',
                marker: { color: '#ff6b6b', opacity: 0.8 }
            }
        ];
        
        // Add variation bands
        const shapes = [];
        tags.forEach((tag, index) => {
            const stats = bestStats[tag];
            const mean = stats.mean;
            const stdDev = stats.stdDev;
            
            shapes.push({
                type: 'rect',
                x0: index - 0.45,
                x1: index + 0.45,
                y0: mean - stdDev,
                y1: mean + stdDev,
                fillcolor: 'rgba(0, 212, 255, 0.1)',
                line: { color: 'rgba(0, 212, 255, 0.3)', width: 1, dash: 'dot' },
                layer: 'below'
            });
        });
        
        const layout = {
            paper_bgcolor: 'rgba(0,0,0,0)',
            plot_bgcolor: 'rgba(15, 52, 96, 0.3)',
            font: { color: '#e0e0e0', family: 'Segoe UI', size: 11 },
            title: `Parameter Comparison: BEST vs WORST<br><sub>Shaded area = Normal range (Avg ± 1σ)</sub>`,
            xaxis: { title: 'Parameters', tickangle: -45, color: '#00d4ff' },
            yaxis: { title: 'Value', gridcolor: 'rgba(0, 212, 255, 0.1)', color: '#00d4ff' },
            barmode: 'group',
            height: 550,
            shapes: shapes,
            showlegend: true
        };
        
        Plotly.newPlot(containerId, traces, layout, { responsive: true });
    }
    
    /**
     * Render separate box plots with individual scales (one per tag)
     * @param {Array} data - Data array
     * @param {Array} tags - Tags to plot
     * @param {String} containerSelector - Container selector for separate charts
     */
    static renderSeparateBoxPlots(data, tags, containerSelector = '#separateCharts') {
        const container = document.querySelector(containerSelector);
        container.innerHTML = '<h2 style="color: #00d4ff; text-align: center; margin: 20px 0;">📊 Individual Box Plots (Separate Scales)</h2>';
        
        tags.forEach((tag, index) => {
            const color = this.tagColors[index % this.tagColors.length];
            const values = data.map(d => d[tag]).filter(v => v !== null && v !== undefined && !isNaN(v));
            
            if (values.length === 0) return;
            
            const stats = DataProcessor.calculateStats(values);
            
            // Create chart container
            const chartDiv = document.createElement('div');
            chartDiv.className = 'chart-container';
            chartDiv.style.marginBottom = '20px';
            const minVal = typeof stats.min === 'number' ? stats.min.toFixed(2) : stats.min;
            const maxVal = typeof stats.max === 'number' ? stats.max.toFixed(2) : stats.max;
            const meanVal = typeof stats.mean === 'number' ? stats.mean.toFixed(2) : stats.mean;
            const stdVal = typeof stats.stdDev === 'number' ? stats.stdDev.toFixed(2) : stats.stdDev;
            
            chartDiv.innerHTML = `
                <div class="chart-header">
                    <h2 style="color: ${color}">${tag}</h2>
                    <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; font-size: 12px; color: #888;">
                        <div>Min: <strong style="color: #e0e0e0">${minVal}</strong></div>
                        <div>Max: <strong style="color: #e0e0e0">${maxVal}</strong></div>
                        <div>Mean: <strong style="color: #e0e0e0">${meanVal}</strong></div>
                        <div>Std: <strong style="color: #e0e0e0">${stdVal}</strong></div>
                    </div>
                </div>
                <div id="boxplot_${index}"></div>
            `;
            container.appendChild(chartDiv);
            
            const trace = {
                y: values,
                name: tag,
                type: 'box',
                marker: { color: color },
                boxmean: 'sd',
                boxpoints: 'outliers'
            };
            
            const layout = {
                paper_bgcolor: 'rgba(0,0,0,0)',
                plot_bgcolor: 'rgba(15, 52, 96, 0.3)',
                font: { color: '#e0e0e0', family: 'Segoe UI', size: 12 },
                yaxis: { 
                    title: 'Value', 
                    gridcolor: 'rgba(0, 212, 255, 0.1)', 
                    color: color,
                    autorange: true
                },
                height: 350,
                showlegend: false
            };
            
            Plotly.newPlot(`boxplot_${index}`, [trace], layout, { responsive: true });
        });
    }
    
    /**
     * Render separate distributions with individual scales (one per tag)
     * @param {Array} data - Data array
     * @param {Array} tags - Tags to plot
     * @param {String} containerSelector - Container selector for separate charts
     */
    static renderSeparateDistributions(data, tags, containerSelector = '#separateCharts') {
        const container = document.querySelector(containerSelector);
        container.innerHTML = '<h2 style="color: #00d4ff; text-align: center; margin: 20px 0;">📊 Individual Distributions (Separate Scales)</h2>';
        
        const MAX_POINTS = 5000;
        
        tags.forEach((tag, index) => {
            const color = this.tagColors[index % this.tagColors.length];
            let values = data.map(d => d[tag]).filter(v => v !== null && v !== undefined && !isNaN(v));
            
            if (values.length === 0) return;
            
            // Downsample if needed
            if (values.length > MAX_POINTS) {
                const step = Math.ceil(values.length / MAX_POINTS);
                values = values.filter((_, i) => i % step === 0);
            }
            
            const stats = DataProcessor.calculateStats(values);
            
            // Create chart container
            const chartDiv = document.createElement('div');
            chartDiv.className = 'chart-container';
            chartDiv.style.marginBottom = '20px';
            
            const minVal = typeof stats.min === 'number' ? stats.min.toFixed(2) : stats.min;
            const maxVal = typeof stats.max === 'number' ? stats.max.toFixed(2) : stats.max;
            const meanVal = typeof stats.mean === 'number' ? stats.mean.toFixed(2) : stats.mean;
            const stdVal = typeof stats.stdDev === 'number' ? stats.stdDev.toFixed(2) : stats.stdDev;
            
            chartDiv.innerHTML = `
                <div class="chart-header">
                    <h2 style="color: ${color}">${tag} - Distribution</h2>
                    <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; font-size: 12px; color: #888;">
                        <div>Min: <strong style="color: #e0e0e0">${minVal}</strong></div>
                        <div>Max: <strong style="color: #e0e0e0">${maxVal}</strong></div>
                        <div>Mean: <strong style="color: #e0e0e0">${meanVal}</strong></div>
                        <div>Std: <strong style="color: #e0e0e0">${stdVal}</strong></div>
                    </div>
                </div>
                <div id="dist_${index}"></div>
            `;
            container.appendChild(chartDiv);
            
            const traces = [];
            
            // Histogram
            traces.push({
                x: values,
                name: 'Data',
                type: 'histogram',
                marker: { color: color, opacity: 0.7 },
                nbinsx: Math.min(30, Math.floor(values.length / 20))
            });
            
            // Normal curve
            const min = stats.min;
            const max = stats.max;
            const range = max - min;
            const step = range / 100;
            const xCurve = [];
            const yCurve = [];
            
            for (let x = min; x <= max; x += step) {
                xCurve.push(x);
                const exponent = -0.5 * Math.pow((x - stats.mean) / stats.stdDev, 2);
                const y = (values.length * step) / (stats.stdDev * Math.sqrt(2 * Math.PI)) * Math.exp(exponent);
                yCurve.push(y);
            }
            
            traces.push({
                x: xCurve,
                y: yCurve,
                name: 'Normal Curve',
                type: 'scatter',
                mode: 'lines',
                line: { color: color, width: 3, dash: 'dash' }
            });
            
            const layout = {
                paper_bgcolor: 'rgba(0,0,0,0)',
                plot_bgcolor: 'rgba(15, 52, 96, 0.3)',
                font: { color: '#e0e0e0', family: 'Segoe UI', size: 12 },
                xaxis: { 
                    title: 'Value', 
                    gridcolor: 'rgba(0, 212, 255, 0.1)', 
                    color: color,
                    autorange: true
                },
                yaxis: { 
                    title: 'Frequency', 
                    gridcolor: 'rgba(0, 212, 255, 0.1)', 
                    color: color,
                    autorange: true
                },
                height: 400,
                barmode: 'overlay',
                showlegend: true
            };
            
            Plotly.newPlot(`dist_${index}`, traces, layout, { responsive: true });
        });
    }
}

// Export for use in main script (both Node.js and browser)
if (typeof module !== 'undefined' && module.exports) {
    module.exports = ChartRenderer;
} else if (typeof window !== 'undefined') {
    window.ChartRenderer = ChartRenderer;
}
