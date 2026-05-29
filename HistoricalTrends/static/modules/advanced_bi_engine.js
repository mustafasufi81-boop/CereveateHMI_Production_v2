// =====================================================
// ADVANCED BI + AI CALCULATION ENGINE
// Python Backend Integration
// =====================================================

const BI_API_URL = `${window.location.origin}/api/v1`;

/**
 * A. Adaptive Performance Baseline Generator
 * Calls Python backend via REST API
 */
window.AdaptiveBaselineEngine = class AdaptiveBaselineEngine {
    constructor(config = {}) {
        this.baselineWindow = config.baselineWindow || 30;
        this.topPercentile = config.topPercentile || 10;
        this.outlierThreshold = config.outlierThreshold || 3;
        this.outlierMethod = config.outlierMethod || 'sigma';
        this.minDataPoints = config.minDataPoints || 50;
    }
    
    /**
     * Calculate adaptive baseline with outlier removal
     */
    async calculateAdaptiveBaseline(data, tag) {
        console.log(`📊 Calling Python API for baseline: ${tag}...`);
        
        try {
            const response = await fetch(`${BI_API_URL}/baseline/calculate`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    data: data,
                    tag: tag,
                    config: {
                        baseline_window: this.baselineWindow,
                        top_percentile: this.topPercentile,
                        outlier_threshold: this.outlierThreshold,
                        outlier_method: this.outlierMethod,
                        min_data_points: this.minDataPoints
                    }
                })
            });
            
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || `API Error: ${response.status}`);
            }
            
            const result = await response.json();
            console.log(`  ✓ Baseline: ${result.value.toFixed(2)} (Python)`);
            return result;
            
        } catch (error) {
            console.error('❌ Python API error:', error.message);
            throw error;
        }
    }
};

/**
 * B. Efficiency-Adjusted Expected Production Engine
 * Calls Python backend via REST API
 */
window.EfficiencyAdjustmentEngine = class EfficiencyAdjustmentEngine {
    constructor(config = {}) {
        this.influencingParameters = config.influencingParameters || {};
    }
    
    async calculateAdjustedExpected(baselineProduction, currentConditions, configuredParams) {
        console.log('⚙️ Calling Python API for efficiency adjustment...');
        
        try {
            const response = await fetch(`${BI_API_URL}/efficiency/calculate`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    baseline_production: baselineProduction,
                    current_conditions: currentConditions,
                    parameters: this.influencingParameters
                })
            });
            
            if (!response.ok) throw new Error(`API Error: ${response.status}`);
            return await response.json();
        } catch (error) {
            console.error('❌ Python API error:', error.message);
            throw error;
        }
    }
}

/**
 * C. Weighted Production Delta Scorer - Python API
 */
window.WeightedDeltaScorer = class WeightedDeltaScorer {
    constructor(config = {}) {
        this.eventWeights = config.eventWeights || {};
        this.rampThreshold = config.rampThreshold || 0.20;
    }
    
    /**
     * Calculate weighted delta score via Python API
     */
    async calculateWeightedDelta(actual, expected, operatingCondition, timestamp) {
        console.log('⚖️ Calling Python API for weighted delta...');
        
        try {
            const response = await fetch(`${BI_API_URL}/delta/calculate`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    actual: actual,
                    expected: expected,
                    operating_condition: operatingCondition,
                    timestamp: timestamp,
                    config: {
                        event_weights: this.eventWeights,
                        ramp_threshold: this.rampThreshold
                    }
                })
            });
            
            if (!response.ok) throw new Error(`API Error: ${response.status}`);
            const result = await response.json();
            const delta = result.weighted_delta !== undefined ? result.weighted_delta : 0;
            console.log(`  ✓ Weighted Delta: ${delta.toFixed(2)} (Python)`);
            return result;
        } catch (error) {
            console.error('❌ Python API error:', error.message);
            throw error;
        }
    }
};

/**
 * D. Cumulative Availability-Based Production Calculator - Python API
 */
window.AvailabilityProductionEngine = class AvailabilityProductionEngine {
    constructor() {
        this.lowLoadThreshold = 0.3;
    }
    
    /**
     * Calculate availability-corrected production via Python API
     */
    async calculateAvailabilityProduction(data, ratedCapacity, timeRange) {
        console.log('📈 Calling Python API for availability production...');
        
        try {
            const response = await fetch(`${BI_API_URL}/availability/calculate`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    data: data,
                    rated_capacity: ratedCapacity,
                    time_range: timeRange
                })
            });
            
            if (!response.ok) throw new Error(`API Error: ${response.status}`);
            const result = await response.json();
            console.log(`  ✓ Availability: ${result.availability.toFixed(2)}% (Python)`);
            return result;
        } catch (error) {
            console.error('❌ Python API error:', error.message);
            throw error;
        }
    }
};

/**
 * E. Multi-Parameter Influence Map (Correlation Engine) - Python API
 */
window.InfluenceMapEngine = class InfluenceMapEngine {
    constructor() {
        this.rollingWindow = 24;
    }
    
    /**
     * Compute comprehensive correlations via Python API
     */
    async computeInfluenceMap(primaryTag, influencingTags, data) {
        console.log(`🔗 Calling Python API for influence map: ${primaryTag}...`);
        
        try {
            const response = await fetch(`${BI_API_URL}/influence/calculate`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    primary_tag: primaryTag,
                    influencing_tags: influencingTags,
                    data: data
                })
            });
            
            if (!response.ok) throw new Error(`API Error: ${response.status}`);
            const result = await response.json();
            console.log(`  ✓ Influence map computed (Python)`);
            return result;
        } catch (error) {
            console.error('❌ Python API error:', error.message);
            throw error;
        }
    }

};

/**
 * F. Performance Stability Index Engine - Python API
 */
window.StabilityIndexEngine = class StabilityIndexEngine {
    /**
     * Calculate stability index via Python API
     */
    async calculateStabilityIndex(values) {
        console.log('📊 Calling Python API for stability index...');
        
        try {
            const response = await fetch(`${BI_API_URL}/stability/calculate`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ values: values })
            });
            
            if (!response.ok) throw new Error(`API Error: ${response.status}`);
            const result = await response.json();
            console.log(`  ✓ Stability: ${result.rating} (${result.index.toFixed(3)}) (Python)`);
            return result;
        } catch (error) {
            console.error('❌ Python API error:', error.message);
            throw error;
        }
    }
};

/**
 * G. Condition Scoring Engine - Python API
 */
window.ConditionScoringEngine = class ConditionScoringEngine {
    constructor() {}
    
    /**
     * Score parameter condition via Python API
     */
    async scoreCondition(parameter, value, customThresholds = null) {
        console.log(`🎯 Calling Python API for condition scoring: ${parameter}...`);
        
        try {
            const response = await fetch(`${BI_API_URL}/condition/score`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    parameter: parameter,
                    value: value,
                    custom_thresholds: customThresholds
                })
            });
            
            if (!response.ok) throw new Error(`API Error: ${response.status}`);
            const result = await response.json();
            console.log(`  ✓ Condition: ${result.status} (${result.score}) (Python)`);
            return result;
        } catch (error) {
            console.error('❌ Python API error:', error.message);
            throw error;
        }
    }
};

/**
 * H. Production Loss Attribution Engine - Python API
 */
window.LossAttributionEngine = class LossAttributionEngine {
    /**
     * Attribute production loss via Python API
     */
    async attributeLoss(actualProduction, expectedProduction, influenceMap, currentConditions) {
        console.log('🔍 Calling Python API for loss attribution...');
        
        try {
            const response = await fetch(`${BI_API_URL}/loss/attribute`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    actual_production: actualProduction,
                    expected_production: expectedProduction,
                    influence_map: influenceMap,
                    current_conditions: currentConditions
                })
            });
            
            if (!response.ok) throw new Error(`API Error: ${response.status}`);
            const result = await response.json();
            const totalLoss = result.total_loss !== undefined ? result.total_loss : 0;
            console.log(`  ✓ Total Loss: ${totalLoss.toFixed(2)} MW (Python)`);
            return result;
        } catch (error) {
            console.error('❌ Python API error:', error.message);
            throw error;
        }
    }
};

console.log('✓ Advanced BI + AI Calculation Engines loaded');
