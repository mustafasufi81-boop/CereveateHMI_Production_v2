/**
 * PLC Tag Browser Module - Clean Design
 * Browse PLC tags, search, and view live values
 * 
 * Features:
 * - Search/filter tags
 * - Click tag to see live value
 * - Good/Bad quality indicators with counts
 * - Live value updates for selected tags
 */

const PlcTagBrowser = (function() {
    'use strict';

    // Private state
    let _currentPlcId = null;
    let _allTags = [];
    let _selectedTagForLive = null;
    let _isLoading = false;
    let _searchFilter = '';
    let _liveUpdateInterval = null;

    // DOM element IDs
    const MODAL_ID = 'plcTagBrowserModal';
    const TAG_LIST_ID = 'plcTagBrowserList';
    const SEARCH_ID = 'plcTagBrowserSearch';
    const STATUS_ID = 'plcTagBrowserStatus';
    const QUALITY_STATS_ID = 'plcQualityStats';

    /**
     * Helper: Check if quality is good
     */
    function _isGoodQuality(quality) {
        if (quality === undefined || quality === null) return null; // Unknown
        if (typeof quality === 'string') {
            return quality.toLowerCase() === 'good';
        }
        if (typeof quality === 'number') {
            return quality === 192 || quality >= 192; // OPC quality codes
        }
        return false;
    }

    /**
     * Initialize the tag browser module
     */
    function init() {
        console.log('[PlcTagBrowser] Module initialized');
        _createModal();
    }

    /**
     * Open the tag browser for a specific PLC
     */
    async function open(plcId) {
        if (_isLoading) {
            console.warn('[PlcTagBrowser] Already loading, please wait...');
            return;
        }

        _currentPlcId = plcId;
        _allTags = [];
        _selectedTagForLive = null;
        _searchFilter = '';

        _showModal();
        _setLoading(true, 'Loading tags from PLC...');

        try {
            const result = await _browseTags(plcId);
            
            if (result.success) {
                _allTags = result.tags || [];
                _renderTagList();
                _updateQualityStats();
                _updateStatus(`${_allTags.length} tags available`);
                
                // Immediately fetch live values
                await _refreshTagValues();
                
                // Start live updates
                _startLiveUpdates();
            } else {
                _showError(result.error || 'Failed to load tags');
            }
        } catch (error) {
            console.error('[PlcTagBrowser] Error:', error);
            _showError(error.message || 'Connection error');
        } finally {
            _setLoading(false);
        }
    }

    /**
     * Close the tag browser modal
     */
    function close() {
        _stopLiveUpdates();
        const modal = document.getElementById(MODAL_ID);
        if (modal) {
            modal.style.display = 'none';
        }
        _currentPlcId = null;
        _selectedTagForLive = null;
    }

    /**
     * Browse tags from PLC via API
     */
    async function _browseTags(plcId) {
        const response = await fetch(`/api/plc/browse/${plcId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });

        if (!response.ok) {
            const text = await response.text();
            throw new Error(`HTTP ${response.status}: ${text}`);
        }

        return await response.json();
    }

    /**
     * Start live value updates
     */
    function _startLiveUpdates() {
        _stopLiveUpdates();
        _liveUpdateInterval = setInterval(async () => {
            if (_currentPlcId && _allTags.length > 0) {
                await _refreshTagValues();
            }
        }, 1000);
    }

    /**
     * Stop live value updates
     */
    function _stopLiveUpdates() {
        if (_liveUpdateInterval) {
            clearInterval(_liveUpdateInterval);
            _liveUpdateInterval = null;
        }
    }

    /**
     * Refresh tag values from API
     */
    async function _refreshTagValues() {
        try {
            const response = await fetch(`/api/plc/values?plcId=${_currentPlcId}`);
            if (response.ok) {
                const data = await response.json();
                
                // API returns { success: true, values: [...] }
                const values = data.values || data;
                if (values && Array.isArray(values)) {
                    values.forEach(tagValue => {
                        const tag = _allTags.find(t => t.name === tagValue.tagName || t.name === tagValue.address);
                        if (tag) {
                            tag.value = tagValue.value;
                            tag.quality = tagValue.quality;
                            tag.dataType = tagValue.dataType;
                            tag.timestamp = tagValue.timestamp;
                        }
                    });
                }
                
                _updateQualityStats();
                _updateLiveValueDisplay();
                _renderTagList(); // Re-render to show quality dots
            }
        } catch (error) {
            console.error('[PlcTagBrowser] Error refreshing values:', error);
        }
    }

    /**
     * Filter tags by search term
     */
    function filterTags(searchTerm) {
        _searchFilter = (searchTerm || '').toLowerCase().trim();
        _renderTagList();
    }

    /**
     * Get filtered tags based on search
     */
    function _getFilteredTags() {
        if (!_searchFilter) return _allTags;
        
        return _allTags.filter(tag => 
            tag.name.toLowerCase().includes(_searchFilter) ||
            (tag.dataType && tag.dataType.toLowerCase().includes(_searchFilter))
        );
    }

    /**
     * Select a tag to view live value
     */
    function selectTagForLive(tagName) {
        _selectedTagForLive = tagName;
        _renderTagList();
        _updateLiveValueDisplay();
    }

    /**
     * Update the live value display for selected tag
     */
    function _updateLiveValueDisplay() {
        const livePanel = document.getElementById('liveValuePanel');
        if (!livePanel) return;

        if (!_selectedTagForLive) {
            livePanel.innerHTML = `
                <div style="text-align:center; padding:20px; color:#888;">
                    <div style="font-size:24px; margin-bottom:10px;">👆</div>
                    <div>Click a tag to see live value</div>
                </div>`;
            return;
        }

        const tag = _allTags.find(t => t.name === _selectedTagForLive);
        if (!tag) {
            livePanel.innerHTML = `<div style="padding:20px; color:#888;">Tag not found</div>`;
            return;
        }

        const qualityResult = _isGoodQuality(tag.quality);
        const isGood = qualityResult === true;
        const hasQuality = qualityResult !== null;
        const qualityColor = hasQuality ? (isGood ? '#28a745' : '#dc3545') : '#888';
        const qualityText = hasQuality ? (isGood ? 'Good' : 'Bad') : 'N/A';
        
        let valueDisplay = tag.value;
        if (valueDisplay === null || valueDisplay === undefined) {
            valueDisplay = '--';
        } else if (typeof valueDisplay === 'boolean') {
            valueDisplay = valueDisplay ? 'TRUE' : 'FALSE';
        } else if (typeof valueDisplay === 'number') {
            valueDisplay = Number.isInteger(valueDisplay) ? valueDisplay : valueDisplay.toFixed(2);
        }

        livePanel.innerHTML = `
            <div style="padding:15px;">
                <div style="font-weight:600; color:#2c3e50; font-size:14px; margin-bottom:10px; word-break:break-all;">
                    ${tag.name}
                </div>
                <div style="display:flex; align-items:center; gap:15px;">
                    <div style="font-size:32px; font-weight:700; color:${isGood ? '#28a745' : '#333'};">
                        ${valueDisplay}
                    </div>
                    <div style="display:flex; flex-direction:column; gap:4px;">
                        <span style="font-size:12px; padding:3px 8px; border-radius:4px; background:${qualityColor}; color:white;">
                            ${qualityText}
                        </span>
                        <span style="font-size:11px; color:#888;">
                            ${tag.dataType || 'Unknown'}
                        </span>
                    </div>
                </div>
                ${tag.timestamp ? `<div style="font-size:11px; color:#888; margin-top:8px;">${new Date(tag.timestamp).toLocaleString()}</div>` : ''}
            </div>`;
    }

    /**
     * Update quality statistics
     */
    function _updateQualityStats() {
        const statsDiv = document.getElementById(QUALITY_STATS_ID);
        if (!statsDiv) return;

        let goodCount = 0;
        let badCount = 0;
        
        _allTags.forEach(tag => {
            const qualityResult = _isGoodQuality(tag.quality);
            if (qualityResult === true) {
                goodCount++;
            } else if (qualityResult === false) {
                badCount++;
            }
        });

        statsDiv.innerHTML = `
            <div style="display:flex; gap:20px; align-items:center;">
                <div style="display:flex; align-items:center; gap:6px;">
                    <span style="width:12px; height:12px; border-radius:50%; background:#28a745; display:inline-block;"></span>
                    <span style="font-weight:600; color:#28a745;">${goodCount}</span>
                    <span style="color:#666;">Good</span>
                </div>
                <div style="display:flex; align-items:center; gap:6px;">
                    <span style="width:12px; height:12px; border-radius:50%; background:#dc3545; display:inline-block;"></span>
                    <span style="font-weight:600; color:#dc3545;">${badCount}</span>
                    <span style="color:#666;">Bad</span>
                </div>
                <div style="color:#888; font-size:12px;">
                    Total: ${_allTags.length} tags
                </div>
            </div>`;
    }

    /**
     * Render the tag list
     */
    function _renderTagList() {
        const container = document.getElementById(TAG_LIST_ID);
        if (!container) return;

        const filteredTags = _getFilteredTags();

        if (filteredTags.length === 0) {
            container.innerHTML = `
                <div style="text-align:center; padding:40px; color:#666;">
                    ${_allTags.length === 0 ? 
                        '<div style="font-size:32px; margin-bottom:10px;">📋</div><div>No tags found</div>' : 
                        '<div style="font-size:32px; margin-bottom:10px;">🔍</div><div>No tags match your search</div>'}
                </div>`;
            return;
        }

        const html = filteredTags.map(tag => {
            const isSelected = _selectedTagForLive === tag.name;
            const qualityResult = _isGoodQuality(tag.quality);
            const isGood = qualityResult === true;
            const hasQuality = qualityResult !== null;
            
            let bgColor = '#fff';
            let borderColor = '#e0e0e0';
            let qualityDot = '';
            
            if (isSelected) {
                bgColor = '#e3f2fd';
                borderColor = '#2196f3';
            }
            
            if (hasQuality) {
                qualityDot = `<span style="width:8px; height:8px; border-radius:50%; background:${isGood ? '#28a745' : '#dc3545'}; display:inline-block; margin-right:8px;"></span>`;
            }

            return `
                <div class="tag-item" 
                     data-tag="${tag.name}"
                     onclick="PlcTagBrowser.selectTagForLive('${tag.name}')"
                     style="display:flex; align-items:center; padding:10px 12px; border:1px solid ${borderColor}; 
                            border-radius:6px; margin:4px 0; background:${bgColor}; cursor:pointer;
                            transition: all 0.15s ease;"
                     onmouseover="this.style.background='${isSelected ? '#e3f2fd' : '#f5f5f5'}'"
                     onmouseout="this.style.background='${bgColor}'">
                    ${qualityDot}
                    <div style="flex:1; overflow:hidden;">
                        <div style="font-weight:500; color:#333; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">
                            ${tag.name}
                        </div>
                        <div style="font-size:11px; color:#888;">
                            ${tag.dataType || 'Unknown type'}
                        </div>
                    </div>
                    ${isSelected ? '<span style="color:#2196f3; font-size:18px;">◀</span>' : ''}
                </div>`;
        }).join('');

        container.innerHTML = html;
    }

    /**
     * Create the modal HTML
     */
    function _createModal() {
        const existing = document.getElementById(MODAL_ID);
        if (existing) existing.remove();

        const modal = document.createElement('div');
        modal.id = MODAL_ID;
        modal.className = 'modal';
        modal.style.cssText = 'display:none; position:fixed; z-index:1000; left:0; top:0; width:100%; height:100%; background:rgba(0,0,0,0.5);';
        
        modal.innerHTML = `
            <div class="modal-content" style="max-width:700px; margin:5% auto; background:white; border-radius:12px; 
                        box-shadow:0 10px 40px rgba(0,0,0,0.3); max-height:85vh; display:flex; flex-direction:column;">
                
                <!-- Header -->
                <div style="padding:16px 20px; border-bottom:1px solid #eee; display:flex; justify-content:space-between; align-items:center;">
                    <h2 style="margin:0; color:#2c3e50; font-size:18px;">📋 PLC Tag Browser</h2>
                    <button onclick="PlcTagBrowser.close()" style="background:none; border:none; font-size:24px; cursor:pointer; color:#999; line-height:1;">&times;</button>
                </div>

                <!-- Quality Stats Bar -->
                <div id="${QUALITY_STATS_ID}" style="padding:10px 20px; background:#f8f9fa; border-bottom:1px solid #eee;">
                    <div style="color:#888;">Loading...</div>
                </div>

                <!-- Search Bar -->
                <div style="padding:12px 20px; border-bottom:1px solid #eee;">
                    <input type="text" id="${SEARCH_ID}" placeholder="🔍 Search tags by name..." 
                           oninput="PlcTagBrowser.filterTags(this.value)"
                           style="width:100%; padding:10px 14px; border:1px solid #ddd; border-radius:6px; font-size:14px; box-sizing:border-box;">
                </div>

                <!-- Main content area -->
                <div style="display:flex; flex:1; overflow:hidden; min-height:350px;">
                    
                    <!-- Tag list (left side) -->
                    <div style="flex:1; display:flex; flex-direction:column; border-right:1px solid #eee;">
                        <div id="${STATUS_ID}" style="padding:8px 15px; background:#fff; color:#666; font-size:12px; border-bottom:1px solid #f0f0f0;">
                            Ready
                        </div>
                        <div id="${TAG_LIST_ID}" style="flex:1; overflow-y:auto; padding:10px 15px;">
                            <div style="text-align:center; padding:40px; color:#666;">Loading...</div>
                        </div>
                    </div>

                    <!-- Live Value Panel (right side) -->
                    <div id="liveValuePanel" style="width:200px; background:#fafafa; display:flex; align-items:center; justify-content:center;">
                        <div style="text-align:center; padding:20px; color:#888;">
                            <div style="font-size:24px; margin-bottom:10px;">👆</div>
                            <div>Click a tag to see live value</div>
                        </div>
                    </div>
                </div>

                <!-- Footer -->
                <div style="padding:12px 20px; border-top:1px solid #eee; display:flex; justify-content:flex-end; background:#f8f9fa;">
                    <button onclick="PlcTagBrowser.close()" class="btn btn-secondary" style="padding:8px 20px;">
                        Close
                    </button>
                </div>
            </div>
        `;

        document.body.appendChild(modal);
    }

    /**
     * Show the modal
     */
    function _showModal() {
        const modal = document.getElementById(MODAL_ID);
        if (modal) {
            modal.style.display = 'block';
            
            const searchInput = document.getElementById(SEARCH_ID);
            if (searchInput) searchInput.value = '';
        }
    }

    /**
     * Set loading state
     */
    function _setLoading(loading, message) {
        _isLoading = loading;
        const container = document.getElementById(TAG_LIST_ID);
        
        if (loading && container) {
            container.innerHTML = `
                <div style="text-align:center; padding:40px;">
                    <div style="font-size:32px; animation:spin 1s linear infinite;">⏳</div>
                    <p style="margin-top:15px; color:#666; font-size:13px;">${message || 'Loading...'}</p>
                </div>
                <style>
                    @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
                </style>`;
        }
    }

    /**
     * Show error message
     */
    function _showError(message) {
        const container = document.getElementById(TAG_LIST_ID);
        if (container) {
            container.innerHTML = `
                <div style="text-align:center; padding:40px;">
                    <div style="font-size:32px;">❌</div>
                    <p style="margin-top:15px; color:#dc3545; font-weight:500;">${message}</p>
                    <button onclick="PlcTagBrowser.refresh()" class="btn btn-outline-primary btn-sm" style="margin-top:15px;">
                        🔄 Try Again
                    </button>
                </div>`;
        }
        _updateStatus('Error: ' + message);
    }

    /**
     * Update status bar
     */
    function _updateStatus(message) {
        const status = document.getElementById(STATUS_ID);
        if (status) {
            status.textContent = message;
        }
    }

    /**
     * Refresh the tag list
     */
    async function refresh() {
        if (_currentPlcId) {
            await open(_currentPlcId);
        }
    }

    // Public API
    return {
        init,
        open,
        close,
        refresh,
        filterTags,
        selectTagForLive
    };

})();

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', function() {
    PlcTagBrowser.init();
});

// Global function for easy access
function browsePlcTags(plcId) {
    PlcTagBrowser.open(plcId);
}
