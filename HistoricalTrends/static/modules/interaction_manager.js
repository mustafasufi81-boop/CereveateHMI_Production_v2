/**
 * INTERACTION MANAGER MODULE
 * Handles all user interactions and gestures
 */

class InteractionManager {
    
    static isDragging = false;
    static dragStartY = 0;
    static dragCurrentY = 0;
    static currentZoomLevel = 1.0;
    static minZoom = 0.1;
    static maxZoom = 10.0;
    
    /**
     * Initialize mouse drag zoom on a chart
     * @param {String} containerId - Chart container ID
     * @param {Function} onZoomChange - Callback when zoom changes
     */
    static initializeDragZoom(containerId, onZoomChange) {
        const container = document.getElementById(containerId);
        if (!container) return;
        
        // Mouse down - start drag
        container.addEventListener('mousedown', (e) => {
            this.isDragging = true;
            this.dragStartY = e.clientY;
            this.dragCurrentY = e.clientY;
            container.style.cursor = 'ns-resize';
        });
        
        // Mouse move - calculate zoom
        container.addEventListener('mousemove', (e) => {
            if (!this.isDragging) return;
            
            this.dragCurrentY = e.clientY;
            const deltaY = this.dragStartY - this.dragCurrentY; // Positive = drag down
            
            // Calculate zoom factor (drag down 100px = 2x zoom, drag up 100px = 0.5x zoom)
            const zoomDelta = deltaY / 100;
            let newZoom = this.currentZoomLevel * (1 + zoomDelta * 0.5);
            
            // Clamp zoom level
            newZoom = Math.max(this.minZoom, Math.min(this.maxZoom, newZoom));
            
            // Show zoom indicator
            this.showZoomIndicator(container, newZoom, deltaY);
        });
        
        // Mouse up - apply zoom
        container.addEventListener('mouseup', (e) => {
            if (!this.isDragging) return;
            
            const deltaY = this.dragStartY - this.dragCurrentY;
            const zoomDelta = deltaY / 100;
            let newZoom = this.currentZoomLevel * (1 + zoomDelta * 0.5);
            newZoom = Math.max(this.minZoom, Math.min(this.maxZoom, newZoom));
            
            // Apply zoom
            this.currentZoomLevel = newZoom;
            if (onZoomChange) {
                onZoomChange(newZoom, deltaY > 0 ? 'in' : 'out');
            }
            
            // Reset
            this.isDragging = false;
            container.style.cursor = 'default';
            this.hideZoomIndicator(container);
        });
        
        // Mouse leave - cancel drag
        container.addEventListener('mouseleave', () => {
            if (this.isDragging) {
                this.isDragging = false;
                container.style.cursor = 'default';
                this.hideZoomIndicator(container);
            }
        });
    }
    
    /**
     * Show zoom level indicator during drag
     * @param {HTMLElement} container - Chart container
     * @param {Number} zoomLevel - Current zoom level
     * @param {Number} deltaY - Drag distance
     */
    static showZoomIndicator(container, zoomLevel, deltaY) {
        let indicator = container.querySelector('.zoom-indicator');
        
        if (!indicator) {
            indicator = document.createElement('div');
            indicator.className = 'zoom-indicator';
            indicator.style.cssText = `
                position: absolute;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                background: rgba(0, 212, 255, 0.9);
                color: #0f0f1e;
                padding: 20px 40px;
                border-radius: 12px;
                font-size: 24px;
                font-weight: bold;
                pointer-events: none;
                z-index: 1000;
                box-shadow: 0 8px 32px rgba(0, 212, 255, 0.5);
                border: 3px solid #00ff88;
            `;
            container.appendChild(indicator);
        }
        
        const direction = deltaY > 0 ? '🔍 ZOOM IN' : '🔎 ZOOM OUT';
        const percentage = (zoomLevel * 100).toFixed(0);
        indicator.innerHTML = `
            <div style="font-size: 32px; margin-bottom: 10px;">${direction}</div>
            <div style="font-size: 20px;">${percentage}%</div>
            <div style="font-size: 14px; margin-top: 10px; opacity: 0.8;">
                ${deltaY > 0 ? '▼ Drag Down: Enlarge' : '▲ Drag Up: Shrink'}
            </div>
        `;
        indicator.style.display = 'block';
    }
    
    /**
     * Hide zoom indicator
     * @param {HTMLElement} container - Chart container
     */
    static hideZoomIndicator(container) {
        const indicator = container.querySelector('.zoom-indicator');
        if (indicator) {
            indicator.style.display = 'none';
        }
    }
    
    /**
     * Apply zoom to Plotly chart
     * @param {String} chartId - Plotly chart div ID
     * @param {Number} zoomLevel - Zoom level (1.0 = 100%)
     * @param {String} direction - 'in' or 'out'
     */
    static applyPlotlyZoom(chartId, zoomLevel, direction) {
        const chartDiv = document.getElementById(chartId);
        if (!chartDiv || !chartDiv.data) return;
        
        // Get current axis ranges
        const layout = chartDiv.layout;
        if (!layout || !layout.xaxis) return;
        
        const xaxis = layout.xaxis;
        const yaxis = layout.yaxis;
        
        // Calculate new ranges based on zoom level
        if (xaxis.range && xaxis.range.length === 2) {
            const xCenter = (xaxis.range[0] + xaxis.range[1]) / 2;
            const xRange = xaxis.range[1] - xaxis.range[0];
            const newXRange = xRange / zoomLevel;
            
            Plotly.relayout(chartId, {
                'xaxis.range': [xCenter - newXRange / 2, xCenter + newXRange / 2]
            });
        }
        
        if (yaxis && yaxis.range && yaxis.range.length === 2) {
            const yCenter = (yaxis.range[0] + yaxis.range[1]) / 2;
            const yRange = yaxis.range[1] - yaxis.range[0];
            const newYRange = yRange / zoomLevel;
            
            Plotly.relayout(chartId, {
                'yaxis.range': [yCenter - newYRange / 2, yCenter + newYRange / 2]
            });
        }
    }
    
    /**
     * Initialize double-click to reset zoom
     * @param {String} containerId - Container ID
     * @param {String} chartId - Chart ID
     */
    static initializeDoubleClickReset(containerId, chartId) {
        const container = document.getElementById(containerId);
        if (!container) return;
        
        container.addEventListener('dblclick', () => {
            this.currentZoomLevel = 1.0;
            Plotly.relayout(chartId, {
                'xaxis.autorange': true,
                'yaxis.autorange': true
            });
            
            // Show reset notification
            this.showNotification(container, '↺ Zoom Reset to 100%');
        });
    }
    
    /**
     * Show temporary notification
     * @param {HTMLElement} container - Container element
     * @param {String} message - Message to show
     */
    static showNotification(container, message) {
        const notification = document.createElement('div');
        notification.style.cssText = `
            position: absolute;
            top: 20px;
            right: 20px;
            background: rgba(0, 255, 136, 0.9);
            color: #0f0f1e;
            padding: 15px 25px;
            border-radius: 8px;
            font-size: 16px;
            font-weight: bold;
            z-index: 1000;
            animation: slideIn 0.3s ease-out;
        `;
        notification.textContent = message;
        container.appendChild(notification);
        
        setTimeout(() => {
            notification.style.animation = 'fadeOut 0.3s ease-out';
            setTimeout(() => notification.remove(), 300);
        }, 2000);
    }
    
    /**
     * Initialize mouse wheel zoom
     * @param {String} chartId - Chart ID
     */
    static initializeWheelZoom(chartId) {
        const chartDiv = document.getElementById(chartId);
        if (!chartDiv) return;
        
        chartDiv.addEventListener('wheel', (e) => {
            e.preventDefault();
            
            const zoomFactor = e.deltaY < 0 ? 1.1 : 0.9; // Wheel up = zoom in
            this.currentZoomLevel *= zoomFactor;
            this.currentZoomLevel = Math.max(this.minZoom, Math.min(this.maxZoom, this.currentZoomLevel));
            
            this.applyPlotlyZoom(chartId, this.currentZoomLevel, e.deltaY < 0 ? 'in' : 'out');
        }, { passive: false });
    }
    
    /**
     * Initialize pinch zoom for touch devices
     * @param {String} chartId - Chart ID
     */
    static initializePinchZoom(chartId) {
        const chartDiv = document.getElementById(chartId);
        if (!chartDiv) return;
        
        let initialDistance = 0;
        let initialZoom = 1.0;
        
        chartDiv.addEventListener('touchstart', (e) => {
            if (e.touches.length === 2) {
                const touch1 = e.touches[0];
                const touch2 = e.touches[1];
                initialDistance = Math.hypot(
                    touch2.clientX - touch1.clientX,
                    touch2.clientY - touch1.clientY
                );
                initialZoom = this.currentZoomLevel;
            }
        });
        
        chartDiv.addEventListener('touchmove', (e) => {
            if (e.touches.length === 2) {
                e.preventDefault();
                const touch1 = e.touches[0];
                const touch2 = e.touches[1];
                const currentDistance = Math.hypot(
                    touch2.clientX - touch1.clientX,
                    touch2.clientY - touch1.clientY
                );
                
                const zoomFactor = currentDistance / initialDistance;
                this.currentZoomLevel = initialZoom * zoomFactor;
                this.currentZoomLevel = Math.max(this.minZoom, Math.min(this.maxZoom, this.currentZoomLevel));
                
                this.applyPlotlyZoom(chartId, this.currentZoomLevel, zoomFactor > 1 ? 'in' : 'out');
            }
        }, { passive: false });
    }
}

// Export for use in main script (both Node.js and browser)
if (typeof module !== 'undefined' && module.exports) {
    module.exports = InteractionManager;
} else if (typeof window !== 'undefined') {
    window.InteractionManager = InteractionManager;
}
