// ============================================================================
// HIGH-PERFORMANCE UI OPTIMIZATIONS FOR 10K+ TAG DASHBOARD
// ============================================================================
// Features:
// 1. Virtual DOM for monitored tags (100+ tags at 60fps)
// 2. Virtual scrolling for available tags tree (smooth 10K tag browser)
// 3. Chart update batching & debouncing (20 charts smoothly)
// 4. DOM node recycling pool (zero GC pressure)
// 5. Web Worker for trend calculations (offload main thread)
// ============================================================================

// ============================================================================
// 1. VIRTUAL DOM FOR MONITORED TAG GRID
// ============================================================================
class VirtualTagGrid {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.virtualNodes = new Map(); // itemId -> virtual node state
        this.domNodes = new Map();     // itemId -> actual DOM element
        this.nodePool = [];            // Recycled DOM nodes
    }

    /**
     * Update grid with new tag data - performs minimal DOM patches
     * @param {Object} monitoredTags - { itemId: tagData }
     */
    update(monitoredTags) {
        const newTagIds = new Set(Object.keys(monitoredTags));
        const oldTagIds = new Set(this.virtualNodes.keys());

        // 1. Remove tags no longer monitored (recycle DOM nodes)
        for (const itemId of oldTagIds) {
            if (!newTagIds.has(itemId)) {
                this.removeNode(itemId);
            }
        }

        // 2. Add new tags or update existing ones
        for (const [itemId, tagData] of Object.entries(monitoredTags)) {
            const oldNode = this.virtualNodes.get(itemId);
            
            if (!oldNode) {
                // New tag - create DOM node
                this.addNode(itemId, tagData);
            } else if (this.needsUpdate(oldNode, tagData)) {
                // Existing tag changed - patch DOM
                this.patchNode(itemId, tagData);
            }
        }

        // 3. Update counter
        document.getElementById("monitoredCount").textContent = newTagIds.size;
    }

    /**
     * Check if node needs updating (diff virtual state)
     */
    needsUpdate(oldNode, newData) {
        return oldNode.value !== newData.value ||
               oldNode.quality !== newData.quality ||
               oldNode.timestamp !== newData.timestamp ||
               oldNode.trending !== newData.trending;
    }

    /**
     * Add new tag card (recycle from pool if available)
     */
    addNode(itemId, tagData) {
        const safeId = itemId.replace(/[^a-zA-Z0-9]/g, '_');
        const friendlyName = window.getFriendlyTagName ? window.getFriendlyTagName(itemId) : itemId;
        const showBothNames = friendlyName !== itemId;

        // Try to recycle DOM node from pool
        let cardElement = this.nodePool.pop();
        
        if (!cardElement) {
            // No recycled nodes - create new one
            cardElement = document.createElement('div');
            cardElement.className = 'value-card value-card-with-trend';
            cardElement.innerHTML = `
                <div class="trend-checkbox-container">
                    <input type="checkbox" class="trend-checkbox">
                    <label class="trend-label">Trend</label>
                </div>
                <div class="card-title"></div>
                <div class="card-value"></div>
                <div class="card-footer">
                    <span class="quality-text"></span>
                    <span class="timestamp-text"></span>
                </div>
                <button class="btn btn-sm btn-danger remove-btn" style="margin-top: 10px; width: 100%; display: none;">Remove</button>
            `;
        }

        // Update content (reuse structure)
        const checkbox = cardElement.querySelector('.trend-checkbox');
        const label = cardElement.querySelector('.trend-label');
        const title = cardElement.querySelector('.card-title');
        const value = cardElement.querySelector('.card-value');
        const quality = cardElement.querySelector('.quality-text');
        const timestamp = cardElement.querySelector('.timestamp-text');
        const removeBtn = cardElement.querySelector('.remove-btn');

        checkbox.id = `trend_${safeId}`;
        checkbox.checked = tagData.trending || false;
        checkbox.onchange = () => window.toggleTrend && window.toggleTrend(itemId);
        
        label.setAttribute('for', `trend_${safeId}`);
        
        title.innerHTML = showBothNames 
            ? `${friendlyName}<br><small style="color: #999; font-weight: normal;">${itemId}</small>`
            : friendlyName;
        
        value.textContent = tagData.value || '--';
        value.id = `value-${safeId}`;
        
        quality.textContent = tagData.quality || 'Waiting...';
        quality.id = `quality-${safeId}`;
        
        timestamp.textContent = tagData.timestamp || '--';
        timestamp.id = `timestamp-${safeId}`;

        if (window.isAdmin) {
            removeBtn.style.display = '';
            removeBtn.onclick = () => window.removeSingleTag && window.removeSingleTag(itemId);
        }

        // Store virtual state
        this.virtualNodes.set(itemId, { ...tagData });
        this.domNodes.set(itemId, cardElement);
        
        // Add to DOM
        this.container.appendChild(cardElement);
    }

    /**
     * Patch existing node (update only changed fields)
     */
    patchNode(itemId, tagData) {
        const cardElement = this.domNodes.get(itemId);
        if (!cardElement) return;

        const safeId = itemId.replace(/[^a-zA-Z0-9]/g, '_');
        const oldData = this.virtualNodes.get(itemId);

        // Only update changed fields
        if (oldData.value !== tagData.value) {
            const valueEl = cardElement.querySelector('.card-value');
            if (valueEl) valueEl.textContent = tagData.value || '--';
        }

        if (oldData.quality !== tagData.quality) {
            const qualityEl = cardElement.querySelector('.quality-text');
            if (qualityEl) qualityEl.textContent = tagData.quality || 'Waiting...';
        }

        if (oldData.timestamp !== tagData.timestamp) {
            const timestampEl = cardElement.querySelector('.timestamp-text');
            if (timestampEl) timestampEl.textContent = tagData.timestamp || '--';
        }

        if (oldData.trending !== tagData.trending) {
            const checkbox = cardElement.querySelector('.trend-checkbox');
            if (checkbox) checkbox.checked = tagData.trending || false;
        }

        // Update virtual state
        this.virtualNodes.set(itemId, { ...tagData });
    }

    /**
     * Remove node and recycle to pool
     */
    removeNode(itemId) {
        const cardElement = this.domNodes.get(itemId);
        if (cardElement) {
            cardElement.remove();
            this.nodePool.push(cardElement); // Recycle
        }
        this.virtualNodes.delete(itemId);
        this.domNodes.delete(itemId);
    }

    /**
     * Clear all nodes
     */
    clear() {
        for (const itemId of this.virtualNodes.keys()) {
            this.removeNode(itemId);
        }
    }
}

// ============================================================================
// 2. VIRTUAL SCROLLING FOR AVAILABLE TAGS TREE
// ============================================================================
class VirtualTagTree {
    constructor(containerId, itemHeight = 60) {
        this.container = document.getElementById(containerId);
        this.itemHeight = itemHeight;
        this.bufferSize = 10; // Render 10 items above/below viewport
        this.allTags = [];
        this.visibleTags = [];
        this.renderedRange = { start: 0, end: 0 };
        
        this.setupScrollContainer();
    }

    setupScrollContainer() {
        if (!this.container) return;
        
        // Wrap in scroll container
        this.scrollContainer = document.createElement('div');
        this.scrollContainer.style.height = '600px';
        this.scrollContainer.style.overflowY = 'auto';
        this.scrollContainer.style.position = 'relative';
        
        this.viewport = document.createElement('div');
        this.viewport.style.position = 'relative';
        
        this.scrollContainer.appendChild(this.viewport);
        
        // Replace container content
        this.container.innerHTML = '';
        this.container.appendChild(this.scrollContainer);
        
        // Listen to scroll events
        this.scrollContainer.addEventListener('scroll', () => this.onScroll());
    }

    /**
     * Load tags into virtual tree
     * @param {Array} tags - Array of tag objects
     */
    load(tags) {
        this.allTags = tags;
        this.viewport.style.height = `${tags.length * this.itemHeight}px`;
        this.render();
    }

    /**
     * Handle scroll - render only visible items
     */
    onScroll() {
        requestAnimationFrame(() => this.render());
    }

    /**
     * Render only visible tags
     */
    render() {
        const scrollTop = this.scrollContainer.scrollTop;
        const viewportHeight = this.scrollContainer.clientHeight;
        
        // Calculate visible range with buffer
        const startIndex = Math.max(0, Math.floor(scrollTop / this.itemHeight) - this.bufferSize);
        const endIndex = Math.min(
            this.allTags.length,
            Math.ceil((scrollTop + viewportHeight) / this.itemHeight) + this.bufferSize
        );

        // Skip if range hasn't changed
        if (startIndex === this.renderedRange.start && endIndex === this.renderedRange.end) {
            return;
        }

        this.renderedRange = { start: startIndex, end: endIndex };
        
        // Render visible slice
        const visibleSlice = this.allTags.slice(startIndex, endIndex);
        const offsetY = startIndex * this.itemHeight;
        
        this.viewport.innerHTML = visibleSlice.map((tag, i) => {
            const actualIndex = startIndex + i;
            const safeId = tag.itemID.replace(/[^a-zA-Z0-9]/g, '_');
            const friendlyName = window.getFriendlyTagName ? window.getFriendlyTagName(tag.itemID) : tag.itemID;
            const showBothNames = friendlyName !== tag.itemID;
            
            return `
                <div class="tree-node leaf" style="position: absolute; top: ${actualIndex * this.itemHeight}px; left: 0; right: 0; height: ${this.itemHeight}px; display: flex; align-items: flex-start; gap: 8px; padding: 8px;">
                    <input type="checkbox" class="available-tag-checkbox" data-tag-id="${tag.itemID}" data-tag-name="${tag.name || tag.itemID}" 
                           style="width: 18px; height: 18px; margin-top: 4px; cursor: pointer; flex-shrink: 0;"
                           onclick="event.stopPropagation()">
                    <div onclick="window.addTagToMonitor && window.addTagToMonitor('${tag.itemID}', '${tag.name || tag.itemID}')" style="flex: 1; cursor: pointer;">
                        <strong>${friendlyName}</strong>
                        ${showBothNames ? `<br><small style="color: #999;">${tag.itemID}</small>` : ''}
                        ${tag.dataType ? `<br><small style="color: #666;">${tag.dataType}</small>` : ''}
                    </div>
                </div>
            `;
        }).join('');
    }

    /**
     * Filter tags by search text
     */
    filter(searchText) {
        const searchLower = searchText.toLowerCase().trim();
        
        if (!searchLower) {
            this.visibleTags = this.allTags;
        } else {
            this.visibleTags = this.allTags.filter(tag => {
                const itemID = (tag.itemID || '').toLowerCase();
                const name = (tag.name || '').toLowerCase();
                const friendlyName = window.getFriendlyTagName ? window.getFriendlyTagName(tag.itemID).toLowerCase() : '';
                return itemID.includes(searchLower) || name.includes(searchLower) || friendlyName.includes(searchLower);
            });
        }
        
        this.allTags = this.visibleTags;
        this.viewport.style.height = `${this.visibleTags.length * this.itemHeight}px`;
        this.scrollContainer.scrollTop = 0;
        this.render();
    }
}

// ============================================================================
// 3. CHART UPDATE BATCHING & DEBOUNCING
// ============================================================================
class ChartBatcher {
    constructor(updateInterval = 2000) {
        this.updateInterval = updateInterval;
        this.pendingUpdates = new Set();
        this.isScheduled = false;
    }

    /**
     * Request chart update (batched)
     * @param {string} itemId - Tag identifier
     */
    requestUpdate(itemId) {
        this.pendingUpdates.add(itemId);
        
        if (!this.isScheduled) {
            this.isScheduled = true;
            setTimeout(() => this.flush(), this.updateInterval);
        }
    }

    /**
     * Flush all pending updates
     */
    flush() {
        if (this.pendingUpdates.size === 0) {
            this.isScheduled = false;
            return;
        }

        requestAnimationFrame(() => {
            for (const itemId of this.pendingUpdates) {
                // Call original updateChart function
                if (window.updateChartImmediate) {
                    window.updateChartImmediate(itemId);
                }
            }
            this.pendingUpdates.clear();
            this.isScheduled = false;
        });
    }

    /**
     * Force immediate update (for user interactions)
     */
    forceUpdate(itemId) {
        requestAnimationFrame(() => {
            if (window.updateChartImmediate) {
                window.updateChartImmediate(itemId);
            }
        });
    }
}

// ============================================================================
// 4. WEB WORKER FOR TREND CALCULATIONS
// ============================================================================
const trendWorkerCode = `
// Web Worker: Trend calculation offloading
self.onmessage = function(e) {
    const { type, data } = e.data;
    
    switch(type) {
        case 'calculate-stats':
            const { itemId, values } = data;
            
            if (!values || values.length === 0) {
                self.postMessage({ 
                    type: 'stats-result', 
                    itemId, 
                    stats: null 
                });
                return;
            }
            
            // Calculate min/max/avg
            let sum = 0;
            let min = values[0];
            let max = values[0];
            
            for (let i = 0; i < values.length; i++) {
                const val = values[i];
                sum += val;
                if (val < min) min = val;
                if (val > max) max = val;
            }
            
            const avg = sum / values.length;
            const range = Math.max(1e-6, Math.abs(max - min));
            const pad = Math.max(1, range * 0.1);
            
            self.postMessage({
                type: 'stats-result',
                itemId,
                stats: {
                    avg: avg.toFixed(2),
                    min: min.toFixed(2),
                    max: max.toFixed(2),
                    yMin: min - pad,
                    yMax: max + pad,
                    count: values.length
                }
            });
            break;
    }
};
`;

class TrendWorker {
    constructor() {
        const blob = new Blob([trendWorkerCode], { type: 'application/javascript' });
        this.worker = new Worker(URL.createObjectURL(blob));
        this.callbacks = new Map();
        
        this.worker.onmessage = (e) => this.handleMessage(e);
    }

    handleMessage(e) {
        const { type, itemId, stats } = e.data;
        
        if (type === 'stats-result') {
            const callback = this.callbacks.get(itemId);
            if (callback) {
                callback(stats);
                this.callbacks.delete(itemId);
            }
        }
    }

    /**
     * Calculate trend statistics in worker
     * @param {string} itemId - Tag identifier
     * @param {Array} values - Numeric values
     * @param {Function} callback - Receives stats object
     */
    calculateStats(itemId, values, callback) {
        this.callbacks.set(itemId, callback);
        this.worker.postMessage({
            type: 'calculate-stats',
            data: { itemId, values }
        });
    }

    terminate() {
        this.worker.terminate();
    }
}

// ============================================================================
// EXPORT GLOBAL INSTANCES
// ============================================================================
window.PerformanceOptimizations = {
    VirtualTagGrid,
    VirtualTagTree,
    ChartBatcher,
    TrendWorker
};

console.log('[PERFORMANCE] Optimization modules loaded: VirtualTagGrid, VirtualTagTree, ChartBatcher, TrendWorker');
