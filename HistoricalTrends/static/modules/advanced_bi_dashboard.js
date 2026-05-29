// =====================================================
// ADVANCED BI DASHBOARD UI
// Visualization for all calculation engines
// =====================================================

class AdvancedBIDashboard {
    constructor() {
        // Master engine will be created with config when showDashboard is called
        this.masterEngine = null;
        this.currentAnalysis = null;
    }
    
    /**
     * Format date range with period type (daily/weekly/monthly)
     */
    formatDateRange(startDate, endDate) {
        const start = new Date(startDate);
        const end = new Date(endDate);
        const diffDays = Math.ceil((end - start) / (1000 * 60 * 60 * 24));
        
        let periodType = '';
        if (diffDays <= 1) {
            periodType = 'Daily';
        } else if (diffDays <= 7) {
            periodType = 'Weekly';
        } else if (diffDays <= 31) {
            periodType = 'Monthly';
        } else if (diffDays <= 93) {
            periodType = 'Quarterly';
        } else {
            periodType = `${diffDays} Days`;
        }
        
        const formatDate = (d) => d.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
        return `${formatDate(start)} to ${formatDate(end)} (${periodType} - ${diffDays} days)`;
    }
    
    /**
     * Show comprehensive BI dashboard
     */
    async showDashboard(data, config, startDate = null, endDate = null) {
        console.log('🎯 Opening Advanced BI Dashboard...');
        
        // Store date range
        this.startDate = startDate;
        this.endDate = endDate;
        
        // Create master engine with dynamic configuration (no hardcoding)
        this.masterEngine = new window.MasterCalculationEngine(config.engineConfig || {});
        
        // Execute full analysis
        this.showLoadingOverlay('Running Advanced BI Analysis...');
        
        try {
            this.currentAnalysis = await this.masterEngine.executeFullAnalysis(data, config);
            
            this.hideLoadingOverlay();
            
            // Create dashboard modal
            this.renderDashboard();
            
        } catch (error) {
            this.hideLoadingOverlay();
            console.error('❌ BI Analysis Error:', error);
            console.error('Error stack:', error.stack);
            alert('Failed to generate BI analysis: ' + error.message);
        }
    }
    
    /**
     * Show loading overlay
     */
    showLoadingOverlay(message) {
        let overlay = document.getElementById('biLoadingOverlay');
        if (!overlay) {
            overlay = document.createElement('div');
            overlay.id = 'biLoadingOverlay';
            overlay.style.cssText = `
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: rgba(0, 0, 0, 0.8);
                z-index: 9999;
                display: flex;
                align-items: center;
                justify-content: center;
                color: #00d4ff;
                font-size: 24px;
                font-weight: bold;
            `;
            document.body.appendChild(overlay);
        }
        overlay.innerHTML = `<div style="text-align: center;">
            <div style="font-size: 48px; margin-bottom: 20px;">⏳</div>
            <div>${message}</div>
        </div>`;
        overlay.style.display = 'flex';
    }
    
    /**
     * Hide loading overlay
     */
    hideLoadingOverlay() {
        const overlay = document.getElementById('biLoadingOverlay');
        if (overlay) {
            overlay.remove();
        }
    }
    
    /**
     * Render full dashboard
     */
    renderDashboard() {
        const modal = document.createElement('div');
        modal.id = 'biDashboardModal';
        modal.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.95);
            z-index: 10000;
            overflow-y: auto;
            padding: 20px;
        `;
        
        const summary = this.currentAnalysis.summary;
        const data = this.currentAnalysis.data;
        
        modal.innerHTML = `
            <div style="max-width: 1400px; margin: 0 auto; background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); border-radius: 12px; padding: 30px; border: 2px solid #00d4ff;">
                
                <!-- Header -->
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                    <div>
                        <h1 style="color: #00d4ff; margin: 0;">
                            ⚡ Advanced Power Plant Intelligence Dashboard
                        </h1>
                        ${this.startDate && this.endDate ? `
                        <div style="color: #888; font-size: 14px; margin-top: 8px;">
                            📅 Analysis Period: <span style="color: #00d4ff;">${this.formatDateRange(this.startDate, this.endDate)}</span> • 
                            <span style="color: #fff;">${data.length} data points</span>
                        </div>
                        ` : ''}
                    </div>
                    <button id="closeBIDashboard" style="background: rgba(255, 59, 48, 0.2); border: 1px solid #ff3b30; color: #ff3b30; padding: 10px 20px; border-radius: 6px; cursor: pointer;">
                        ✕ Close
                    </button>
                </div>
                
                <!-- Executive Summary Cards -->
                <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; margin-bottom: 30px;">
                    ${this.renderSummaryCard('Stability', summary.overall.stabilityRating, '', '#34c759')}
                    ${this.renderSummaryCard('Availability', summary.overall.availability.toFixed(3), '%', '#ff9500')}
                    ${this.renderSummaryCard('Utilization', ((summary.production.actual / summary.production.expected) * 100).toFixed(3), '%', '#667eea')}
                </div>
                
                <!-- Production Overview -->
                <div style="background: rgba(0, 212, 255, 0.1); padding: 20px; border-radius: 8px; margin-bottom: 30px; border-left: 4px solid #00d4ff;">
                    <h2 style="color: #00d4ff; margin-top: 0;">📊 Production Analysis</h2>
                    <div style="display: grid; grid-template-columns: repeat(5, 1fr); gap: 15px;">
                        <div>
                            <div style="color: #888; font-size: 11px;">Current Avg Production</div>
                            <div style="color: #fff; font-size: 20px; font-weight: bold;">${summary.production.actual.toFixed(3)} MW</div>
                        </div>
                        <div>
                            <div style="color: #888; font-size: 11px;">Baseline (Top 10%)</div>
                            <div style="color: #ffd700; font-size: 20px; font-weight: bold;">${summary.production.baseline.toFixed(3)} MW</div>
                        </div>
                        <div>
                            <div style="color: #888; font-size: 11px;">Best/Target</div>
                            <div style="color: #00d4ff; font-size: 20px; font-weight: bold;">${summary.production.expected.toFixed(3)} MW</div>
                        </div>
                        <div>
                            <div style="color: #888; font-size: 11px;">${summary.production.isGainFromBaseline ? 'Gain' : 'Loss'} from Baseline</div>
                            <div style="color: ${summary.production.isGainFromBaseline ? '#34c759' : '#ff9500'}; font-size: 20px; font-weight: bold;">${(summary.production.deltaFromBaseline || 0).toFixed(3)} MW</div>
                        </div>
                        <div>
                            <div style="color: #888; font-size: 11px;">Loss from Best</div>
                            <div style="color: #ff3b30; font-size: 20px; font-weight: bold;">${summary.production.delta.toFixed(3)} MW</div>
                        </div>
                    </div>
                </div>
                
                <!-- Top Issues -->
                <div style="margin-bottom: 30px;">
                    ${this.renderTopIssues(summary.topIssues)}
                </div>
                
                <!-- Detailed Analytics Sections -->
                <div style="margin-bottom: 30px;">
                    <h2 style="color: #00d4ff; margin-bottom: 15px;">📈 Detailed Analytics</h2>
                    
                    <!-- Tabs -->
                    <div style="display: flex; gap: 10px; margin-bottom: 20px; border-bottom: 2px solid rgba(0, 212, 255, 0.3);">
                        <button class="bi-tab active" data-tab="baseline" style="background: rgba(0, 212, 255, 0.2); border: none; color: #00d4ff; padding: 12px 20px; cursor: pointer; border-radius: 6px 6px 0 0;">
                            Adaptive Baseline
                        </button>
                        <button class="bi-tab" data-tab="influence" style="background: rgba(255, 255, 255, 0.05); border: none; color: #888; padding: 12px 20px; cursor: pointer; border-radius: 6px 6px 0 0;">
                            Influence Map
                        </button>
                        <button class="bi-tab" data-tab="efficiency" style="background: rgba(255, 255, 255, 0.05); border: none; color: #888; padding: 12px 20px; cursor: pointer; border-radius: 6px 6px 0 0;">
                            Efficiency Adjustment
                        </button>
                        <button class="bi-tab" data-tab="availability" style="background: rgba(255, 255, 255, 0.05); border: none; color: #888; padding: 12px 20px; cursor: pointer; border-radius: 6px 6px 0 0;">
                            Availability
                        </button>
                        <button class="bi-tab" data-tab="loss" style="background: rgba(255, 255, 255, 0.05); border: none; color: #888; padding: 12px 20px; cursor: pointer; border-radius: 6px 6px 0 0;">
                            Loss Attribution
                        </button>
                        <button class="bi-tab" data-tab="conditions" style="background: rgba(255, 255, 255, 0.05); border: none; color: #888; padding: 12px 20px; cursor: pointer; border-radius: 6px 6px 0 0;">
                            Condition Scores
                        </button>
                    </div>
                    
                    <!-- Tab Content -->
                    <div id="biTabContent" style="background: rgba(255, 255, 255, 0.05); padding: 20px; border-radius: 8px;">
                        ${this.renderBaselineTab(data.baseline)}
                    </div>
                </div>
                
                <!-- Export Options -->
                <div style="display: flex; gap: 10px; justify-content: flex-end;">
                    <button id="exportBIPDF" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border: none; color: #fff; padding: 12px 25px; border-radius: 6px; cursor: pointer; font-weight: bold;">
                        📄 Export PDF Report
                    </button>
                    <button id="exportBIExcel" style="background: linear-gradient(135deg, #34c759 0%, #28a745 100%); border: none; color: #fff; padding: 12px 25px; border-radius: 6px; cursor: pointer; font-weight: bold;">
                        📊 Export to Excel
                    </button>
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
        
        // Add event listeners
        this.attachEventListeners(modal, data);
    }
    
    /**
     * Render summary card
     */
    renderSummaryCard(title, value, unit, color) {
        return `
            <div style="background: rgba(255, 255, 255, 0.05); padding: 20px; border-radius: 8px; border-left: 4px solid ${color};">
                <div style="color: #888; font-size: 12px; margin-bottom: 5px;">${title}</div>
                <div style="color: ${color}; font-size: 32px; font-weight: bold;">${value}<span style="font-size: 20px;">${unit}</span></div>
            </div>
        `;
    }
    
    /**
     * Render top issues
     */
    renderTopIssues(issues) {
        const issuesHTML = issues.slice(0, 5).map(issue => {
            const severityColor = issue.severity === 'High' ? '#ff3b30' : issue.severity === 'Medium' ? '#ff9500' : '#ffd700';
            return `
                <div style="background: rgba(255, 59, 48, 0.1); padding: 12px; border-radius: 6px; margin-bottom: 10px; border-left: 3px solid ${severityColor};">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div style="flex: 1;">
                            <div style="color: #fff; font-weight: bold;">${issue.parameter}</div>
                            <div style="color: #888; font-size: 12px;">${issue.type}</div>
                        </div>
                        <div style="background: ${severityColor}; padding: 4px 10px; border-radius: 4px; font-size: 11px; font-weight: bold;">
                            ${issue.severity}
                        </div>
                    </div>
                    ${issue.status ? `<div style="color: #ccc; margin-top: 5px; font-size: 13px;">${issue.status}</div>` : ''}
                    ${issue.lossPercentage ? `<div style="color: #ff3b30; margin-top: 5px;">Loss: ${issue.lossPercentage.toFixed(1)}%</div>` : ''}
                    ${issue.recommendation ? `<div style="color: #00d4ff; margin-top: 8px; font-size: 12px; padding: 8px; background: rgba(0, 212, 255, 0.1); border-radius: 4px;">💡 ${issue.recommendation}</div>` : ''}
                </div>
            `;
        }).join('');
        
        return `
            <div>
                <h3 style="color: #ff3b30; margin-top: 0;">🚨 Diagnostics & Issues</h3>
                ${issuesHTML || '<div style="color: #34c759;">✓ No critical issues detected. Plant operating normally.</div>'}
            </div>
        `;
    }
    

    
    /**
     * Render baseline tab
     */
    renderBaselineTab(baseline) {
        return `
            <div>
                <h3 style="color: #00d4ff;">📊 Adaptive Performance Baseline</h3>
                <div style="background: rgba(255, 215, 0, 0.1); padding: 15px; border-radius: 6px; margin-bottom: 15px; border-left: 3px solid #ffd700;">
                    <strong style="color: #ffd700;">Dynamic 30-Day Rolling Baseline</strong><br>
                    <span style="color: #ccc; font-size: 13px;">
                        This baseline recalculates every 30 days using top 10% performance window with outlier removal.
                    </span>
                </div>
                <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px;">
                    <div>
                        <div style="color: #888; font-size: 12px;">Baseline Value</div>
                        <div style="color: #ffd700; font-size: 24px; font-weight: bold;">${(baseline.baselineValue || baseline.value || 0).toFixed(2)} MW</div>
                    </div>
                    <div>
                        <div style="color: #888; font-size: 12px;">Sample Size</div>
                        <div style="color: #00d4ff; font-size: 24px; font-weight: bold;">${baseline.sampleSize || 0}</div>
                    </div>
                </div>
                <div style="margin-top: 20px;">
                    <div style="color: #888; font-size: 12px;">Baseline Period: ${this.startDate || 'N/A'} to ${this.endDate || 'N/A'}</div>
                </div>
                    </div>
                </div>
            </div>
        `;
    }
    
    /**
     * Attach event listeners
     */
    attachEventListeners(modal, data) {
        // Close button
        modal.querySelector('#closeBIDashboard').addEventListener('click', () => {
            document.body.removeChild(modal);
        });
        
        // Tab switching
        modal.querySelectorAll('.bi-tab').forEach(tab => {
            tab.addEventListener('click', (e) => {
                // Update tab styles
                modal.querySelectorAll('.bi-tab').forEach(t => {
                    t.style.background = 'rgba(255, 255, 255, 0.05)';
                    t.style.color = '#888';
                    t.classList.remove('active');
                });
                e.target.style.background = 'rgba(0, 212, 255, 0.2)';
                e.target.style.color = '#00d4ff';
                e.target.classList.add('active');
                
                // Switch content
                const tabName = e.target.dataset.tab;
                this.switchTab(tabName, modal);
            });
        });
        
        // Export buttons
        modal.querySelector('#exportBIPDF').addEventListener('click', () => this.exportToPDF());
        modal.querySelector('#exportBIExcel').addEventListener('click', () => this.exportToExcel());
    }
    
    /**
     * Switch tab content
     */
    switchTab(tabName, modal) {
        const content = modal.querySelector('#biTabContent');
        const data = this.currentAnalysis.data;
        
        switch (tabName) {
            case 'baseline':
                content.innerHTML = this.renderBaselineTab(data.baseline);
                break;
            case 'influence':
                content.innerHTML = this.renderInfluenceTab(data.influenceMap);
                break;
            case 'efficiency':
                content.innerHTML = this.renderEfficiencyTab(data.efficiencyAdjustment);
                break;
            case 'availability':
                content.innerHTML = this.renderAvailabilityTab(data.availability);
                break;
            case 'loss':
                content.innerHTML = this.renderLossTab(data.lossAttribution);
                break;
            case 'conditions':
                content.innerHTML = this.renderConditionsTab(data.conditionScores);
                break;
        }
    }
    
    /**
     * Render influence tab
     */
    renderInfluenceTab(influenceMap) {
        const influencesHTML = influenceMap.influences.map((inf, idx) => {
            const color = inf.impact > 0 ? '#34c759' : '#ff3b30';
            const arrow = inf.impact > 0 ? '↑' : '↓';
            
            return `
                <tr style="border-bottom: 1px solid rgba(255, 255, 255, 0.1);">
                    <td style="padding: 12px; color: #00d4ff;">${idx + 1}</td>
                    <td style="padding: 12px; color: #fff; font-weight: bold;">${inf.parameter}</td>
                    <td style="padding: 12px; color: #fff;">${inf.correlation.toFixed(3)}</td>
                    <td style="padding: 12px; color: ${color}; font-weight: bold;">${arrow} ${Math.abs(inf.impact).toFixed(2)}%</td>
                    <td style="padding: 12px; color: #888;">${inf.lag} min</td>
                    <td style="padding: 12px; color: #00d4ff;">${inf.relationship}</td>
                </tr>
            `;
        }).join('');
        
        return `
            <div>
                <h3 style="color: #00d4ff;">🔗 Multi-Parameter Influence Analysis</h3>
                <table style="width: 100%; border-collapse: collapse;">
                    <thead>
                        <tr style="background: rgba(0, 212, 255, 0.1);">
                            <th style="padding: 12px; text-align: left; color: #00d4ff;">#</th>
                            <th style="padding: 12px; text-align: left; color: #00d4ff;">Parameter</th>
                            <th style="padding: 12px; text-align: left; color: #00d4ff;">Correlation</th>
                            <th style="padding: 12px; text-align: left; color: #00d4ff;">Impact</th>
                            <th style="padding: 12px; text-align: left; color: #00d4ff;">Lag</th>
                            <th style="padding: 12px; text-align: left; color: #00d4ff;">Relationship</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${influencesHTML}
                    </tbody>
                </table>
            </div>
        `;
    }
    
    /**
     * Export methods (placeholder)
     */
    exportToPDF() {
        alert('PDF export functionality - integrate with jsPDF library');
    }
    
    exportToExcel() {
        alert('Excel export functionality - integrate with SheetJS library');
    }
    
    /**
     * Render efficiency tab
     */
    renderEfficiencyTab(efficiency) {
        if (!efficiency) return '<p>No efficiency data available</p>';
        
        return `
            <div>
                <h3 style="color: #00d4ff;">⚙️ Efficiency Adjustment</h3>
                <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 20px; margin-top: 20px;">
                    <div style="background: rgba(0, 212, 255, 0.1); padding: 20px; border-radius: 8px;">
                        <div style="color: #888; font-size: 14px;">Adjusted Expected</div>
                        <div style="color: #00d4ff; font-size: 32px; font-weight: bold;">${(efficiency.adjustedExpected || 0).toFixed(2)} MW</div>
                    </div>
                    <div style="background: rgba(255, 59, 48, 0.1); padding: 20px; border-radius: 8px;">
                        <div style="color: #888; font-size: 14px;">Total Loss Factor</div>
                        <div style="color: #ff3b30; font-size: 32px; font-weight: bold;">${((efficiency.totalLossFactor || 0) * 100).toFixed(2)}%</div>
                    </div>
                </div>
            </div>
        `;
    }
    
    /**
     * Render availability tab
     */
    renderAvailabilityTab(availability) {
        if (!availability) return '<p>No availability data available</p>';
        
        return `
            <div>
                <h3 style="color: #00d4ff;">📈 Availability Production</h3>
                <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; margin-top: 20px;">
                    <div style="background: rgba(0, 212, 255, 0.1); padding: 20px; border-radius: 8px;">
                        <div style="color: #888; font-size: 14px;">Cumulative Production</div>
                        <div style="color: #00d4ff; font-size: 28px; font-weight: bold;">${(availability.cumulativeProduction || 0).toFixed(2)} MWh</div>
                    </div>
                    <div style="background: rgba(52, 199, 89, 0.1); padding: 20px; border-radius: 8px;">
                        <div style="color: #888; font-size: 14px;">Utilization Factor</div>
                        <div style="color: #34c759; font-size: 28px; font-weight: bold;">${((availability.utilizationFactor || 0) * 100).toFixed(1)}%</div>
                    </div>
                    <div style="background: rgba(255, 149, 0, 0.1); padding: 20px; border-radius: 8px;">
                        <div style="color: #888; font-size: 14px;">Capacity Factor</div>
                        <div style="color: #ff9500; font-size: 28px; font-weight: bold;">${((availability.capacityFactor || 0) * 100).toFixed(1)}%</div>
                    </div>
                </div>
            </div>
        `;
    }
    
    /**
     * Render loss attribution tab
     */
    renderLossTab(lossAttribution) {
        if (!lossAttribution) return '<p>No loss data available</p>';
        
        const lossesHTML = Object.entries(lossAttribution.lossBreakdown || {}).map(([param, data]) => `
            <tr style="border-bottom: 1px solid rgba(255, 255, 255, 0.1);">
                <td style="padding: 12px; color: #fff; font-weight: bold;">${param}</td>
                <td style="padding: 12px; color: #ff3b30;">${(data.lossAmount || 0).toFixed(2)} MW</td>
                <td style="padding: 12px; color: #ff9500;">${((data.lossPercentage || 0) * 100).toFixed(2)}%</td>
            </tr>
        `).join('');
        
        return `
            <div>
                <h3 style="color: #00d4ff;">🔍 Production Loss Attribution</h3>
                <div style="margin: 20px 0;">
                    <div style="color: #888;">Total Loss</div>
                    <div style="color: #ff3b30; font-size: 32px; font-weight: bold;">${(lossAttribution.totalLoss || 0).toFixed(2)} MW</div>
                </div>
                <table style="width: 100%; border-collapse: collapse; margin-top: 20px;">
                    <thead>
                        <tr style="background: rgba(0, 212, 255, 0.1);">
                            <th style="padding: 12px; text-align: left; color: #00d4ff;">Parameter</th>
                            <th style="padding: 12px; text-align: left; color: #00d4ff;">Loss Amount</th>
                            <th style="padding: 12px; text-align: left; color: #00d4ff;">Loss %</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${lossesHTML || '<tr><td colspan="3" style="padding: 20px; text-align: center; color: #888;">No losses detected</td></tr>'}
                    </tbody>
                </table>
            </div>
        `;
    }
    
    /**
     * Render condition scores tab
     */
    renderConditionsTab(conditionScores) {
        if (!conditionScores) return '<p>No condition data available</p>';
        
        const scoresHTML = Object.entries(conditionScores || {}).map(([param, score]) => {
            let color = '#34c759';
            let status = 'Good';
            if (score < 70) { color = '#ff3b30'; status = 'Critical'; }
            else if (score < 85) { color = '#ff9500'; status = 'Warning'; }
            
            return `
                <div style="margin-bottom: 20px;">
                    <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
                        <span style="color: #fff; font-weight: bold;">${param}</span>
                        <span style="color: ${color};">${status} (${score.toFixed(0)})</span>
                    </div>
                    <div style="background: rgba(255, 255, 255, 0.1); height: 10px; border-radius: 5px; overflow: hidden;">
                        <div style="background: ${color}; height: 100%; width: ${score}%; transition: width 0.3s;"></div>
                    </div>
                </div>
            `;
        }).join('');
        
        return `
            <div>
                <h3 style="color: #00d4ff;">🚦 Parameter Condition Scoring</h3>
                <div style="margin-top: 20px;">
                    ${scoresHTML || '<p style="color: #888;">No condition scores available</p>'}
                </div>
            </div>
        `;
    }
}

// Create global instance
window.AdvancedBIDashboard = new AdvancedBIDashboard();

console.log('✓ Advanced BI Dashboard loaded');
