// =====================================================
// PREDICTIVE INTERPOLATION MODULE
// ML-based prediction with model comparison
// =====================================================

class PredictiveInterpolation {
    constructor() {
        this.availableModels = null;
        this.comparisonResults = null;
        this.activeTasks = {};
    }
    
    /**
     * Load available prediction models
     */
    async loadAvailableModels() {
        try {
            const response = await fetch('/api/prediction/available_models');
            const result = await response.json();
            
            if (result.success) {
                this.availableModels = result.models;
                console.log(`✓ Loaded ${Object.keys(result.models).length} prediction models`);
                return result.models;
            }
        } catch (error) {
            console.error('Failed to load models:', error);
            return null;
        }
    }
    
    /**
     * Show model comparison modal
     */
    async showModelComparisonModal(tag, startDate, endDate) {
        if (!this.availableModels) {
            await this.loadAvailableModels();
        }
        
        const modal = document.createElement('div');
        modal.id = 'modelComparisonModal';
        modal.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.95);
            display: flex;
            justify-content: center;
            align-items: center;
            z-index: 10000;
            overflow-y: auto;
        `;
        
        const modelCheckboxes = Object.entries(this.availableModels).map(([key, desc]) => `
            <label style="display: block; margin: 10px 0; cursor: pointer;">
                <input type="checkbox" value="${key}" checked style="margin-right: 10px;">
                <span style="color: #00d4ff; font-weight: bold;">${key.toUpperCase()}</span>
                <br>
                <span style="color: #888; font-size: 12px; margin-left: 30px;">${desc}</span>
            </label>
        `).join('');
        
        modal.innerHTML = `
            <div style="background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); padding: 30px; border-radius: 12px; border: 2px solid #00d4ff; max-width: 900px; width: 90%; max-height: 90vh; overflow-y: auto;">
                <h2 style="color: #00d4ff; margin-bottom: 20px;">🔮 ML-Based Trend Prediction</h2>
                
                <div style="background: rgba(255, 215, 0, 0.1); padding: 15px; border-radius: 8px; margin-bottom: 20px; border-left: 4px solid #ffd700;">
                    <strong style="color: #ffd700;">⚡ FFT Recommended</strong><br>
                    <span style="color: #ccc; font-size: 13px;">
                        Based on research, FFT (Fourier Transform) is best for power plant cyclic data.
                        However, you can compare all models and choose the one that fits your data best.
                    </span>
                </div>
                
                <div style="background: rgba(0, 212, 255, 0.1); padding: 15px; border-radius: 8px; margin-bottom: 20px;">
                    <strong style="color: #00d4ff;">Selected Tag:</strong> <span style="color: #fff;">${tag}</span><br>
                    <strong style="color: #00d4ff;">Date Range:</strong> <span style="color: #fff;">${startDate} to ${endDate}</span>
                </div>
                
                <h3 style="color: #00d4ff; margin: 20px 0 10px 0;">Select Models to Compare:</h3>
                <div style="background: rgba(255, 255, 255, 0.05); padding: 15px; border-radius: 8px; margin-bottom: 20px;">
                    ${modelCheckboxes}
                </div>
                
                <div id="comparisonProgress" style="display: none; margin: 20px 0;">
                    <div style="background: rgba(0, 212, 255, 0.2); padding: 15px; border-radius: 8px;">
                        <div style="color: #00d4ff; margin-bottom: 10px;">⏳ Running predictions... (system remains responsive)</div>
                        <div style="background: rgba(0, 0, 0, 0.3); height: 30px; border-radius: 15px; overflow: hidden;">
                            <div id="progressBar" style="background: linear-gradient(90deg, #00d4ff, #667eea); height: 100%; width: 0%; transition: width 0.3s;"></div>
                        </div>
                        <div id="progressText" style="color: #888; margin-top: 10px; font-size: 12px;">Starting...</div>
                    </div>
                </div>
                
                <div id="comparisonResults" style="display: none; margin: 20px 0;"></div>
                
                <div style="margin-top: 20px; display: flex; gap: 10px;">
                    <button id="runComparison" class="btn" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 12px 25px; border: none; border-radius: 6px; font-weight: bold; cursor: pointer;">
                        🚀 Run Comparison
                    </button>
                    <button id="closeModal" class="btn" style="background: rgba(255, 255, 255, 0.1); color: white; padding: 12px 25px; border: 1px solid #666; border-radius: 6px; cursor: pointer;">
                        Close
                    </button>
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
        
        // Event handlers
        document.getElementById('runComparison').addEventListener('click', () => {
            const selectedModels = Array.from(modal.querySelectorAll('input[type="checkbox"]:checked'))
                .map(cb => cb.value);
            
            if (selectedModels.length === 0) {
                alert('Please select at least one model');
                return;
            }
            
            this.runComparison(tag, startDate, endDate, selectedModels);
        });
        
        document.getElementById('closeModal').addEventListener('click', () => {
            document.body.removeChild(modal);
        });
    }
    
    /**
     * Run model comparison (async)
     */
    async runComparison(tag, startDate, endDate, models) {
        const progressDiv = document.getElementById('comparisonProgress');
        const progressBar = document.getElementById('progressBar');
        const progressText = document.getElementById('progressText');
        const resultsDiv = document.getElementById('comparisonResults');
        
        progressDiv.style.display = 'block';
        resultsDiv.style.display = 'none';
        
        try {
            // Start comparison
            const response = await fetch('/api/prediction/compare', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    start_date: startDate,
                    end_date: endDate,
                    tag: tag,
                    models: models
                })
            });
            
            const result = await response.json();
            
            if (!result.success) {
                throw new Error(result.error);
            }
            
            const taskId = result.task_id;
            this.activeTasks[taskId] = { tag, models };
            
            // Poll for results
            this.pollTaskStatus(taskId, progressBar, progressText, resultsDiv);
            
        } catch (error) {
            console.error('Comparison failed:', error);
            progressText.innerHTML = `<span style="color: #ff3b30;">❌ Error: ${error.message}</span>`;
        }
    }
    
    /**
     * Poll task status
     */
    async pollTaskStatus(taskId, progressBar, progressText, resultsDiv) {
        const poll = async () => {
            try {
                const response = await fetch(`/api/prediction/status/${taskId}`);
                const result = await response.json();
                
                if (!result.success) {
                    throw new Error('Task not found');
                }
                
                const task = result.task;
                
                // Update progress
                progressBar.style.width = task.progress + '%';
                progressText.textContent = `Status: ${task.status} (${task.progress}%)`;
                
                if (task.status === 'completed') {
                    this.displayComparisonResults(task.results, resultsDiv);
                    document.getElementById('comparisonProgress').style.display = 'none';
                } else if (task.status === 'failed') {
                    progressText.innerHTML = `<span style="color: #ff3b30;">❌ Failed: ${task.error}</span>`;
                } else {
                    // Continue polling
                    setTimeout(poll, 1000);
                }
                
            } catch (error) {
                console.error('Polling error:', error);
            }
        };
        
        poll();
    }
    
    /**
     * Display comparison results with preview charts
     */
    displayComparisonResults(results, container) {
        container.style.display = 'block';
        
        const models = results.models;
        const modelKeys = Object.keys(models);
        
        let html = '<h3 style="color: #00d4ff; margin-bottom: 15px;">📊 Comparison Results</h3>';
        
        html += '<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 15px;">';
        
        // Color scheme for each model
        const colors = {
            'fft': '#ffd700',
            'arima': '#00d4ff',
            'prophet': '#667eea',
            'exponential': '#ff9500',
            'polynomial': '#34c759',
            'random_forest': '#ff3b30',
            'linear': '#888888'
        };
        
        modelKeys.forEach(modelKey => {
            const modelData = models[modelKey];
            const predictions = modelData.predictions;
            const color = colors[modelKey] || '#00d4ff';
            
            // Calculate average confidence
            const avgConfidence = predictions.length > 0 
                ? (predictions.reduce((sum, p) => sum + (p.Confidence || 0.5), 0) / predictions.length * 100).toFixed(1)
                : 0;
            
            html += `
                <div style="background: rgba(255, 255, 255, 0.05); padding: 15px; border-radius: 8px; border: 2px solid ${color};">
                    <h4 style="color: ${color}; margin: 0 0 10px 0;">${modelKey.toUpperCase()}</h4>
                    <div style="color: #ccc; font-size: 13px; margin-bottom: 10px;">
                        <strong>Predicted Points:</strong> ${predictions.length}<br>
                        <strong>Confidence:</strong> ${avgConfidence}%
                    </div>
                    <div style="margin: 15px 0;">
                        <canvas id="preview_${modelKey}" style="max-height: 150px;"></canvas>
                    </div>
                    <button class="selectModel" data-model="${modelKey}" data-predictions='${JSON.stringify(predictions)}' style="background: ${color}; color: #000; width: 100%; padding: 10px; border: none; border-radius: 6px; font-weight: bold; cursor: pointer;">
                        ✓ Select This Model
                    </button>
                </div>
            `;
        });
        
        html += '</div>';
        
        container.innerHTML = html;
        
        // Render preview charts
        setTimeout(() => {
            modelKeys.forEach(modelKey => {
                this.renderPreviewChart(modelKey, models[modelKey].predictions, colors[modelKey]);
            });
        }, 100);
        
        // Add event listeners to select buttons
        container.querySelectorAll('.selectModel').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const model = e.target.dataset.model;
                const predictions = JSON.parse(e.target.dataset.predictions);
                this.confirmAndSaveModel(model, predictions, results.tag);
            });
        });
    }
    
    /**
     * Render mini preview chart for each model
     */
    renderPreviewChart(modelKey, predictions, color) {
        const canvas = document.getElementById(`preview_${modelKey}`);
        if (!canvas) return;
        
        const ctx = canvas.getContext('2d');
        
        // Sample data for preview (show predicted values)
        const values = predictions.map(p => p.PredictedValue);
        
        if (values.length === 0) return;
        
        new Chart(ctx, {
            type: 'line',
            data: {
                labels: predictions.map((p, i) => i),
                datasets: [{
                    label: 'Predicted',
                    data: values,
                    borderColor: color,
                    backgroundColor: color + '20',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false }
                },
                scales: {
                    x: { display: false },
                    y: {
                        display: true,
                        ticks: { color: '#888', font: { size: 10 } },
                        grid: { color: 'rgba(255, 255, 255, 0.1)' }
                    }
                }
            }
        });
    }
    
    /**
     * Confirm and save selected model
     */
    async confirmAndSaveModel(model, predictions, tag) {
        if (!confirm(`Confirm using ${model.toUpperCase()} model for ${tag}?\n\nThis will save ${predictions.length} predicted points.`)) {
            return;
        }
        
        try {
            const response = await fetch('/api/prediction/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    predictions: predictions,
                    model: model,
                    tag: tag,
                    user_confirmed: true
                })
            });
            
            const result = await response.json();
            
            if (result.success) {
                alert(`✓ Saved ${result.saved} predictions using ${model.toUpperCase()} model!\n\nReload trends to see interpolated data.`);
                
                // Close modal
                const modal = document.getElementById('modelComparisonModal');
                if (modal) {
                    document.body.removeChild(modal);
                }
                
                // Reload trends with interpolated view
                const qualityConfig = new window.DataQualityConfig();
                qualityConfig.config.viewMode = 'interpolated';
                qualityConfig.saveConfig();
                
                // Trigger reload
                if (typeof loadTrendData === 'function') {
                    loadTrendData();
                }
            } else {
                alert('Failed to save predictions: ' + result.error);
            }
            
        } catch (error) {
            console.error('Save failed:', error);
            alert('Failed to save predictions: ' + error.message);
        }
    }
}

// Create global instance
window.PredictiveInterpolation = new PredictiveInterpolation();

console.log('✓ Predictive Interpolation module loaded');
