// =====================================================
// ADVANCED BI + AI CALCULATION ENGINE
// Power Plant Intelligence Platform
// =====================================================

/**
 * A. Adaptive Performance Baseline Generator
 * Dynamic baseline that recalculates every 30 days
 */
class AdaptiveBaselineEngine {
    constructor(config = {}) {
        this.baselineWindow = config.baselineWindow || 30;
        this.topPercentile = config.topPercentile || 10;
        this.outlierThreshold = config.outlierThreshold || 3;
        this.outlierMethod = config.outlierMethod || 'sigma';
        this.minDataPoints = config.minDataPoints || 50;
    }
    
    calculateAdaptiveBaseline(data, tag) {
        console.log(`📊 Calculating adaptive baseline for ${tag}...`);
        const filteredData = this.applyRollingWindow(data, this.baselineWindow);
        
        if (filteredData.length < this.minDataPoints) {
            console.warn(`⚠️ Insufficient data points`);
            return null;
        }
        
        const cleanData = this.removeOutliers(filteredData, tag);
        const sortedValues = cleanData
            .map(d => d[tag] || d[tag.toLowerCase()])
            .filter(v => v !== null && v !== undefined && !isNaN(v))
            .sort((a, b) => b - a);
        
        if (sortedValues.length === 0) return null;
        
        const topPercentileCount = Math.max(1, Math.ceil(sortedValues.length * (this.topPercentile / 100)));
        const topPerformance = sortedValues.slice(0, topPercentileCount);
        
        const baseline = {
            value: this.calculateMean(topPerformance),
            min: Math.min(...topPerformance),
            max: Math.max(...topPerformance),
            stdDev: this.calculateStdDev(topPerformance),
            sampleSize: topPerformance.length,
            confidence: this.calculateConfidence(topPerformance.length, sortedValues.length),
            calculatedAt: new Date().toISOString(),
            validUntil: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString()
        };
        
        return baseline;
    }
    
    applyRollingWindow(data, windowDays) {
        if (!data || data.length === 0) return [];
        const cutoffTime = new Date();
        cutoffTime.setDate(cutoffTime.getDate() - windowDays);
        return data.filter(d => {
            const ts = d.Timestamp || d.timestamp;
            if (!ts) return false;
            return new Date(ts) >= cutoffTime;
        });
    }
    
    removeOutliers(data, tag) {
        const values = data.map(d => d[tag] || d[tag.toLowerCase()]).filter(v => v !== null && v !== undefined && !isNaN(v));
        if (values.length === 0) return [];
        
        const mean = this.calculateMean(values);
        const stdDev = this.calculateStdDev(values);
        if (stdDev === 0) return data;
        
        const threshold = this.outlierThreshold * stdDev;
        return data.filter(d => {
            const value = d[tag] || d[tag.toLowerCase()];
            if (value === null || value === undefined || isNaN(value)) return false;
            return Math.abs(value - mean) <= threshold;
        });
    }
    
    calculateMean(values) {
        if (!values || values.length === 0) return 0;
        return values.reduce((sum, v) => sum + v, 0) / values.length;
    }
    
    calculateMedian(values) {
        if (!values || values.length === 0) return 0;
        const sorted = [...values].sort((a, b) => a - b);
        const mid = Math.floor(sorted.length / 2);
        return sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid];
    }
    
    calculateStdDev(values) {
        const mean = this.calculateMean(values);
        const squaredDiffs = values.map(v => Math.pow(v - mean, 2));
        return Math.sqrt(this.calculateMean(squaredDiffs));
    }
    
    calculateConfidence(sampleSize, totalSize) {
        return (sampleSize / totalSize) * 100;
    }
}

class EfficiencyAdjustmentEngine {
    constructor(config = {}) {
        this.influencingParameters = config.influencingParameters || {};
    }
    
    calculateAdjustedExpected(baselineProduction, currentConditions, configuredParams) {
        return { baseline: baselineProduction, adjustedExpected: baselineProduction, totalLossFactor: 0, lossBreakdown: {} };
    }
}

class WeightedDeltaScorer {
    constructor(config = {}) {
        this.eventWeights = config.eventWeights || { 'stableRun': 1.0 };
        this.rampThreshold = config.rampThreshold || 0.20;
    }
    
    calculateWeightedDelta(actual, expected, operatingCondition, timestamp) {
        const rawDelta = actual - expected;
        return { rawDelta, weightedDelta: rawDelta, condition: 'stableRun', weight: 1.0, performanceScore: 100, timestamp };
    }
}

class AvailabilityProductionEngine {
    constructor() {
        this.lowLoadThreshold = 0.3;
    }
    
    calculateAvailabilityProduction(data, ratedCapacity, timeRange) {
        return { availability: 0, cumulativeProduction: 0 };
    }
}

class InfluenceMapEngine {
    constructor() {
        this.rollingWindow = 24;
    }
    
    computeInfluenceMap(primaryTag, influencingTags, data) {
        const influenceMap = {};
        influencingTags.forEach(tag => {
            influenceMap[tag] = { pearson: 0, impactPercentage: 0 };
        });
        return influenceMap;
    }
}

class StabilityIndexEngine {
    calculateStabilityIndex(values) {
        if (!values || values.length < 2) return { index: 0, rating: 'Unknown' };
        const mean = values.reduce((sum, v) => sum + v, 0) / values.length;
        return { index: 0.5, rating: 'Fair', mean };
    }
}

class ConditionScoringEngine {
    constructor() {
        this.defaultThresholds = {};
    }
    
    scoreCondition(parameter, value, customThresholds = null) {
        return { score: 50, color: 'yellow', status: 'Unknown' };
    }
}

class LossAttributionEngine {
    attributeLoss(actualProduction, expectedProduction, influenceMap, currentConditions) {
        const totalDelta = expectedProduction - actualProduction;
        return { totalLoss: totalDelta, attribution: {}, unattributedLoss: totalDelta };
    }
}

// Export to window
window.AdaptiveBaselineEngine = AdaptiveBaselineEngine;
window.EfficiencyAdjustmentEngine = EfficiencyAdjustmentEngine;
window.WeightedDeltaScorer = WeightedDeltaScorer;
window.AvailabilityProductionEngine = AvailabilityProductionEngine;
window.InfluenceMapEngine = InfluenceMapEngine;
window.StabilityIndexEngine = StabilityIndexEngine;
window.ConditionScoringEngine = ConditionScoringEngine;
window.LossAttributionEngine = LossAttributionEngine;

console.log('✓ Advanced BI + AI Calculation Engines loaded');
