// =====================================================
// MASTER CALCULATION ENGINE
// Orchestrates all BI + AI components
// =====================================================

class MasterCalculationEngine {
    constructor(config = {}) {
        // Verify all engine classes are loaded
        const requiredClasses = [
            'AdaptiveBaselineEngine',
            'EfficiencyAdjustmentEngine',
            'WeightedDeltaScorer',
            'AvailabilityProductionEngine',
            'InfluenceMapEngine',
            'StabilityIndexEngine',
            'ConditionScoringEngine',
            'LossAttributionEngine'
        ];
        
        const missing = requiredClasses.filter(className => !window[className]);
        if (missing.length > 0) {
            throw new Error(`Missing required engine classes: ${missing.join(', ')}. Ensure advanced_bi_engine.js is loaded before master_calculation_engine.js`);
        }
        
        // Initialize all sub-engines with optional configuration
        this.baselineEngine = new window.AdaptiveBaselineEngine(config.baseline || {});
        this.efficiencyEngine = new window.EfficiencyAdjustmentEngine(config.efficiency || {});
        this.deltaScorer = new window.WeightedDeltaScorer(config.deltaScorer || {});
        this.availabilityEngine = new window.AvailabilityProductionEngine(config.availability || {});
        this.influenceEngine = new window.InfluenceMapEngine(config.influence || {});
        this.stabilityEngine = new window.StabilityIndexEngine(config.stability || {});
        this.conditionEngine = new window.ConditionScoringEngine(config.condition || {});
        this.lossAttributionEngine = new window.LossAttributionEngine(config.lossAttribution || {});
        
        console.log('🚀 Master Calculation Engine initialized with dynamic configuration');
    }
    
    /**
     * MAIN CALCULATION PIPELINE
     * Executes all calculations in correct sequence
     */
    async executeFullAnalysis(data, config) {
        console.log('═══════════════════════════════════════════════════');
        console.log('   SIMPLIFIED BASELINE ANALYSIS (Complex BI Disabled)');
        console.log('═══════════════════════════════════════════════════');
        
        const results = {
            timestamp: new Date().toISOString(),
            config: config,
            data: {}
        };
        
        try {
            // STEP 1: Baseline Generation ONLY
            console.log('\n📊 STEP 1: Baseline Calculation');
            results.data.baseline = await this.step1_BaselineGeneration(data, config);
            
            // Skip all complex calculations (2-8) - not needed for plant operations
            console.log('\n⏭️  SKIPPED: Influence mapping, efficiency, availability, performance, stability, conditions, loss attribution');
            console.log('   (Complex BI calculations disabled - focus on baseline vs current production)');
            
            // Provide minimal placeholders so UI doesn't crash
            results.data.influenceMap = { influences: [], topPositive: [], topNegative: [] };
            results.data.efficiencyAdjustment = { adjustedExpected: results.data.baseline.baselineValue };
            results.data.availability = { availability: 100, cumulative_production: 0 };
            results.data.performance = { score: 0 };
            results.data.stability = { index: 0 };
            results.data.conditionScores = {};
            results.data.lossAttribution = { total_loss: 0, attributed_losses: [] };
            
            // Simple summary
            results.summary = {
                baseline: results.data.baseline.baselineValue,
                current: results.data.baseline.targetProduction || 0,
                difference: (results.data.baseline.targetProduction || 0) - results.data.baseline.baselineValue,
                percentChange: results.data.baseline.baselineValue > 0 
                    ? (((results.data.baseline.targetProduction || 0) - results.data.baseline.baselineValue) / results.data.baseline.baselineValue * 100)
                    : 0
            };
            
            console.log('\n═══════════════════════════════════════════════════');
            console.log('   ✅ BASELINE ANALYSIS COMPLETE');
            console.log('═══════════════════════════════════════════════════');
            
            return results;
            
        } catch (error) {
            console.error('❌ Analysis failed:', error);
            throw error;
        }
    }
    
    /**
     * STEP 1: Baseline Generation
     */
    async step1_BaselineGeneration(data, config) {
        const productionTag = config.productionTag || 'Load_MW';
        
        // Get target production and rated capacity from backend config
        let targetProduction = null;
        let ratedCapacity = config.ratedCapacity || 270;
        
        try {
            const configResponse = await fetch('/api/baseline/config?tag=' + encodeURIComponent(productionTag));
            if (configResponse.ok) {
                const configData = await configResponse.json();
                if (configData.target_production) {
                    targetProduction = configData.target_production.value;
                }
                if (configData.rated_capacity) {
                    ratedCapacity = configData.rated_capacity;
                }
            }
        } catch (error) {
            console.warn('⚠️ Could not load baseline config:', error);
        }
        
        // Calculate baseline based on mode
        let baselineValue = ratedCapacity;  // Default to rated capacity
        let targetDateAverage = 0;
        
        // Always use range mode now - baseline = average of baselineData range
        if (config.baselineData && config.baselineData.length > 0) {
            const baselineValues = config.baselineData
                .map(d => parseFloat(d[productionTag]))
                .filter(v => v !== null && v !== undefined && !isNaN(v));
            
            if (baselineValues.length > 0) {
                baselineValue = baselineValues.reduce((sum, v) => sum + v, 0) / baselineValues.length;
                
                // DEBUG: Log first 10 and last 10 baseline values
                console.log('🔍 BASELINE DEBUG:');
                console.log('   Production Tag:', productionTag);
                console.log('   Total baseline values:', baselineValues.length);
                console.log('   First 10 values:', baselineValues.slice(0, 10));
                console.log('   Last 10 values:', baselineValues.slice(-10));
                console.log('   Min:', Math.min(...baselineValues).toFixed(3));
                console.log('   Max:', Math.max(...baselineValues).toFixed(3));
                console.log('   Sum:', baselineValues.reduce((sum, v) => sum + v, 0).toFixed(3));
                console.log('   Average:', baselineValue.toFixed(3));
                
                // Check first timestamp in baseline data
                if (config.baselineData.length > 0) {
                    console.log('   First baseline timestamp:', config.baselineData[0].Timestamp);
                    console.log('   Last baseline timestamp:', config.baselineData[config.baselineData.length - 1].Timestamp);
                }
            }
        }
        
        // Calculate target date average (current production)
        if (config.targetDateData && config.targetDateData.length > 0) {
            const targetValues = config.targetDateData
                .map(d => parseFloat(d[productionTag]))
                .filter(v => v !== null && v !== undefined && !isNaN(v));
            if (targetValues.length > 0) {
                targetDateAverage = targetValues.reduce((sum, v) => sum + v, 0) / targetValues.length;
            }
        }
        
        console.log('📊 BASELINE CALCULATION:');
        console.log('   Baseline Range:', config.dateRange?.baselineStart, 'to', config.dateRange?.baselineEnd);
        console.log('   Baseline Data Points:', config.baselineData ? config.baselineData.length : 0);
        console.log('   ✅ BASELINE VALUE:', baselineValue.toFixed(3), 'MW');
        console.log('   Target Date:', config.dateRange?.targetDate);
        console.log('   Target Date Data Points:', config.targetDateData ? config.targetDateData.length : 0);
        console.log('   ✅ TARGET DATE AVG:', targetDateAverage.toFixed(3), 'MW');
        console.log('   Rated Capacity:', ratedCapacity, 'MW');
        
        return {
            tag: productionTag,
            value: baselineValue,
            baselineValue: baselineValue,
            targetProduction: targetProduction || ratedCapacity,
            ratedCapacity: ratedCapacity,
            sampleSize: config.baselineData ? config.baselineData.length : 0
        };
    }
    
    /**
     * Get default baseline when data is unavailable
     */
    getDefaultBaseline(tag, targetProduction = null, ratedCapacity = 270) {
        return {
            tag: tag,
            baselineValue: 0,
            targetProduction: targetProduction,
            ratedCapacity: ratedCapacity,
            confidence: 0,
            validUntil: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString(),
            statistics: {
                min: 0,
                max: 0,
                stdDev: 0,
                sampleSize: 0
            },
            isDefault: true,
            message: 'Insufficient data for baseline calculation'
        };
    }
    
    /**
     * STEP 2: Influence Mapping
     */
    async step2_InfluenceMapping(data, config) {
        const productionTag = config.productionTag || 'Load_MW';
        
        // Get only tags that exist in the data
        const availableTags = data && data.length > 0 ? Object.keys(data[0]).filter(k => k !== 'Timestamp') : [];
        const requestedInfluencingTags = config.influencingTags || [];
        const influencingTags = requestedInfluencingTags.filter(tag => availableTags.includes(tag));
        
        if (influencingTags.length === 0) {
            console.warn('⚠️ No influencing tags available in data');
            return {
                productionTag: productionTag,
                influences: [],
                topPositive: [],
                topNegative: [],
                message: 'No influencing parameters found in data'
            };
        }
        
        // Pre-clean data: remove rows with nulls for production or influencing tags
        const cleanedData = data.filter(row => {
            const prodVal = parseFloat(row[productionTag]);
            if (isNaN(prodVal)) return false;
            return influencingTags.every(t => {
                const v = parseFloat(row[t]);
                return !isNaN(v);
            });
        });

        // Detect constant series to avoid regression errors
        const constantTags = [];
        const variableTags = influencingTags.filter(tag => {
            const vals = cleanedData.map(r => parseFloat(r[tag])).filter(v => !isNaN(v));
            const unique = [...new Set(vals.map(v => v.toFixed(6)))];
            if (unique.length <= 1) {
                constantTags.push(tag);
                return false; // exclude from correlation request
            }
            return true;
        });

        if (constantTags.length > 0) {
            console.warn('⚠️ Skipping constant influencing tags (no variance):', constantTags);
        }

        let influenceMap = {};
        try {
            influenceMap = await this.influenceEngine.computeInfluenceMap(
                productionTag,
                variableTags,
                cleanedData
            );
        } catch (err) {
            console.error('❌ Influence map API failed:', err.message);
            // Fall back to empty influence map so analysis can continue
            influenceMap = {};
        }

        // Inject placeholder entries for skipped constant tags
        constantTags.forEach(tag => {
            influenceMap[tag] = {
                pearson: 0,
                impact_percentage: 0,
                lag_minutes: 0,
                relationship: 'constant_series'
            };
        });
        
        // Rank by impact
        const rankedInfluences = Object.entries(influenceMap)
            .sort((a, b) => Math.abs(b[1].impact_percentage) - Math.abs(a[1].impact_percentage))
            .map(([tag, influence]) => ({
                parameter: tag,
                correlation: influence.pearson,
                impact: influence.impact_percentage,
                lag: influence.lag_minutes,
                relationship: influence.relationship || (constantTags.includes(tag) ? 'constant_series' : 'unknown')
            }));
        
        return {
            productionTag: productionTag,
            influences: rankedInfluences,
            topPositive: rankedInfluences.filter(i => i.impact > 0).slice(0, 3),
            topNegative: rankedInfluences.filter(i => i.impact < 0).slice(0, 3)
        };
    }
    
    /**
     * STEP 3: Efficiency Adjustment
     */
    async step3_EfficiencyAdjustment(baseline, data, config) {
        // Get current conditions (average of data)
        const currentConditions = this.extractCurrentConditions(data, config);
        
        const adjustment = await this.efficiencyEngine.calculateAdjustedExpected(
            baseline.value,
            currentConditions,
            config.parameterConfigs || {}
        );
        
        return {
            baseline: adjustment.baseline,
            adjustedExpected: adjustment.adjusted_expected,
            totalLossFactor: adjustment.total_loss_factor,
            lossBreakdown: adjustment.loss_breakdown
        };
    }
    
    /**
     * STEP 4: Availability & Production
     */
    async step4_AvailabilityProduction(data, config) {
        if (!data || data.length === 0) {
            console.warn('⚠️ No data for availability calculation');
            return {
                availability: 0,
                productionLoss: 0,
                timeRange: { start: null, end: null }
            };
        }
        
        const ratedCapacity = config.ratedCapacity || 250; // MW
        const timeRange = {
            start: data[0].Timestamp,
            end: data[data.length - 1].Timestamp
        };
        
        try {
            const availability = await this.availabilityEngine.calculateAvailabilityProduction(
                data,
                ratedCapacity,
                timeRange
            );
            return availability || { availability: 0, productionLoss: 0, timeRange };
        } catch (error) {
            console.warn('⚠️ Error calculating availability:', error);
            return { availability: 0, productionLoss: 0, timeRange };
        }
    }
    
    /**
     * STEP 5: Performance Scoring
     */
    async step5_PerformanceScoring(availability, efficiencyAdjustment, data) {
        if (!data || data.length === 0) {
            return {
                deltaResult: null,
                averagePerformanceScore: 0,
                averageWeightedDelta: 0,
                conditionBreakdown: {}
            };
        }
        
        // Calculate SINGLE aggregate delta for entire time period
        const loadKey = Object.keys(data[0] || {}).find(k => k.includes('Load') || k.includes('MW')) || 'Load';
        const loadValues = data.map(d => parseFloat(d[loadKey])).filter(v => v !== null && v !== undefined && !isNaN(v));
        
        if (loadValues.length === 0) {
            console.error('❌ No valid load values found');
            return {
                deltaResult: null,
                averagePerformanceScore: 0,
                averageWeightedDelta: 0,
                conditionBreakdown: {}
            };
        }
        
        const avgActual = loadValues.reduce((sum, v) => sum + v, 0) / loadValues.length;
        const avgExpected = efficiencyAdjustment?.adjustedExpected;  // Changed from adjusted_expected
        
        console.log('📊 STEP 5 - PERFORMANCE CALCULATION:');
        console.log(`   Data points analyzed: ${loadValues.length}`);
        console.log(`   ✅ ACTUAL AVERAGE: ${avgActual.toFixed(3)} MW (from ${loadValues.length} data points)`);
        console.log(`   ✅ EXPECTED (from efficiency): ${avgExpected} MW`);
        console.log(`   Sample values:`, loadValues.slice(0, 10));
        console.log(`🔍 avgActual: ${avgActual} (type: ${typeof avgActual})`);
        console.log(`🔍 avgExpected: ${avgExpected} (type: ${typeof avgExpected})`);
        console.log(`🔍 efficiencyAdjustment:`, efficiencyAdjustment);
        console.log(`   Sample values:`, loadValues.slice(0, 10));
        console.log(`🔍 avgActual: ${avgActual} (type: ${typeof avgActual})`);
        console.log(`🔍 avgExpected: ${avgExpected} (type: ${typeof avgExpected})`);
        console.log(`🔍 efficiencyAdjustment:`, efficiencyAdjustment);
        
        // Guard: Ensure both values exist before calculation
        if (avgActual === undefined || avgActual === null || isNaN(avgActual)) {
            console.error('❌ Undefined or invalid avgActual:', avgActual);
            return {
                deltaResult: null,
                averagePerformanceScore: 0,
                averageWeightedDelta: 0,
                conditionBreakdown: {}
            };
        }
        
        if (avgExpected === undefined || avgExpected === null || isNaN(avgExpected)) {
            console.error('❌ Undefined or invalid avgExpected:', avgExpected);
            console.error('   efficiencyAdjustment was:', efficiencyAdjustment);
            return {
                deltaResult: null,
                averagePerformanceScore: 0,
                averageWeightedDelta: 0,
                conditionBreakdown: {}
            };
        }
        
        console.log(`📊 Calculating aggregate delta: ${avgActual.toFixed(2)} MW actual vs ${avgExpected.toFixed(2)} MW expected`);
        
        let deltaResult;
        try {
            deltaResult = await this.deltaScorer.calculateWeightedDelta(
                avgActual,
                avgExpected,
                { period: 'aggregate' },
                data[Math.floor(data.length / 2)]?.Timestamp || new Date().toISOString()
            );
            
            console.log(`✅ Delta result:`, deltaResult);
        } catch (error) {
            console.error('❌ Delta calculation failed:', error);
            return {
                deltaResult: null,
                averagePerformanceScore: 0,
                averageWeightedDelta: 0,
                conditionBreakdown: {}
            };
        }
        
        // Validate deltaResult has required fields
        if (!deltaResult || deltaResult.performance_score === undefined || deltaResult.weighted_delta === undefined) {
            console.error('❌ Invalid delta result structure:', deltaResult);
            return {
                deltaResult: null,
                averagePerformanceScore: 0,
                averageWeightedDelta: 0,
                conditionBreakdown: {}
            };
        }
        
        return {
            deltaResult: deltaResult,
            averagePerformanceScore: deltaResult.performance_score || 0,
            averageWeightedDelta: deltaResult.weighted_delta || 0,
            averageActual: avgActual,
            averageExpected: avgExpected,
            conditionBreakdown: { [deltaResult.condition]: 1 }
        };
    }
    
    /**
     * STEP 6: Stability Analysis
     */
    async step6_StabilityAnalysis(data, config) {
        const productionTag = config.productionTag || 'Load_MW';
        const values = data.map(d => parseFloat(d[productionTag])).filter(v => v !== null && v !== undefined && !isNaN(v));
        
        const stability = await this.stabilityEngine.calculateStabilityIndex(values);
        
        return {
            tag: productionTag,
            stabilityIndex: stability.index,
            rating: stability.rating,
            statistics: {
                mean: stability.mean,
                stdDev: stability.std_dev,
                coefficientOfVariation: stability.coefficient_of_variation
            }
        };
    }
    
    /**
     * STEP 7: Condition Scoring
     */
    async step7_ConditionScoring(data, config) {
        const parametersToScore = config.parametersToScore || [
            'Vibration', 'NOx', 'MSPressure', 'Vacuum'
        ];
        
        const scores = {};
        
        // Sequential API calls to avoid resource exhaustion
        for (const param of parametersToScore) {
            const values = data.map(d => parseFloat(d[param])).filter(v => v !== null && v !== undefined && !isNaN(v));
            if (values.length === 0) continue;
            
            const avgValue = values.reduce((sum, v) => sum + v, 0) / values.length;
            
            try {
                const score = await this.conditionEngine.scoreCondition(
                    param,
                    avgValue,
                    config.customThresholds?.[param]
                );
                scores[param] = score;
            } catch (error) {
                console.error(`Condition scoring failed for ${param}:`, error);
                scores[param] = { score: 50, status: 'Unknown' };
            }
        }
        
        return scores;
    }
    
    /**
     * STEP 8: Loss Attribution
     */
    async step8_LossAttribution(availability, efficiencyAdjustment, influenceMap, data) {
        const actualProduction = availability.cumulative_production;
        const expectedProduction = efficiencyAdjustment.adjustedExpected * (availability.total_seconds / 3600);
        
        const currentConditions = this.extractCurrentConditions(data, {});
        
        const lossAttribution = await this.lossAttributionEngine.attributeLoss(
            actualProduction,
            expectedProduction,
            influenceMap.influences.reduce((map, inf) => {
                map[inf.parameter] = {
                    pearson: inf.correlation,
                    impact_percentage: inf.impact
                };
                return map;
            }, {}),
            currentConditions
        );
        
        return lossAttribution;
    }
    
    /**
     * Extract current conditions from data
     */
    extractCurrentConditions(data, config) {
        const conditions = {};
        
        const allKeys = new Set();
        data.forEach(d => Object.keys(d).forEach(k => allKeys.add(k)));
        
        allKeys.forEach(key => {
            if (key === 'Timestamp' || key === 'RowId' || key === 'TagId') return;
            
            const values = data.map(d => parseFloat(d[key])).filter(v => v !== null && v !== undefined && !isNaN(v));
            if (values.length > 0) {
                conditions[key] = values.reduce((sum, v) => sum + v, 0) / values.length;
            }
        });
        
        return conditions;
    }
    
    /**
     * Analyze condition breakdown
     */
    analyzeConditions(scores) {
        const breakdown = {
            trip: 0,
            loadRamp: 0,
            stableRun: 0,
            startup: 0,
            shutdown: 0,
            lowLoad: 0,
            partLoad: 0
        };
        
        scores.forEach(score => {
            breakdown[score.condition]++;
        });
        
        return breakdown;
    }
    
    /**
     * Generate Executive Summary
     */
    generateExecutiveSummary(analysisData) {
        // CORRECT LOGIC:
        // 1. Current Production = Selected date average (from performance.averageActual)
        // 2. Baseline = 30-day historical average (from baseline.value)
        // 3. Target = Fixed rated capacity (from baseline.ratedCapacity)
        
        const currentProduction = analysisData.performance?.averageActual || 0;
        const baselinePerformance = analysisData.baseline?.value || 0;  // 30-day historical average
        const bestPerformance = analysisData.baseline?.targetProduction || analysisData.baseline?.ratedCapacity || 270;
        
        console.log('📋 EXECUTIVE SUMMARY GENERATION:');
        console.log('   ✅ Current Production (selected date avg):', currentProduction.toFixed(3), 'MW');
        console.log('   ✅ Baseline (30-day historical avg):', baselinePerformance.toFixed(3), 'MW');
        console.log('   ✅ Target (rated capacity):', bestPerformance, 'MW');
        console.log('   Data structure:', {
            performance: analysisData.performance,
            baseline: analysisData.baseline
        });
        
        // 4. Utilization - from Python (already as decimal, e.g., 0.391)
        const utilization = analysisData.availability.utilizationFactor || 
                           analysisData.availability.utilization_factor || 0;
        
        // 5. Deltas - Current vs Baseline vs Target
        const deltaFromBaseline = currentProduction - baselinePerformance;  // Can be + or -
        const deltaFromTarget = currentProduction - bestPerformance;  // Usually negative
        const isGainFromBaseline = deltaFromBaseline > 0;
        
        console.log('   📊 Delta from Baseline:', deltaFromBaseline.toFixed(3), 'MW', isGainFromBaseline ? '(GAIN)' : '(LOSS)');
        console.log('   📊 Delta from Target:', deltaFromTarget.toFixed(3), 'MW');
        
        const summary = {
            overall: {
                performanceScore: analysisData.performance.averagePerformanceScore || 0,
                stabilityRating: analysisData.stability.rating || 'Unknown',
                availability: analysisData.availability.availability || 0,
                utilizationFactor: utilization  // Keep as decimal (0.391 = 39.1%)
            },
            production: {
                actual: currentProduction,  // Selected date average
                baseline: baselinePerformance,  // 30-day historical average
                expected: bestPerformance,  // Rated capacity target
                delta: deltaFromTarget,  // vs Target
                deltaFromBaseline: deltaFromBaseline,  // vs Baseline
                isGainFromBaseline: isGainFromBaseline
            },
            topIssues: this.identifyTopIssues(analysisData),
            recommendations: this.generateRecommendations(analysisData)
        };
        
        return summary;
    }
    
    /**
     * Identify top issues
     * DESIGN: Intelligent diagnostics - identify WHY plant is underperforming
     * - Low load operation vs rated capacity
     * - Parameter abnormalities (vibration, temperature, pressure)
     * - Condition scores < 70 = Critical
     * - Loss percentage > 10% = High severity
     */
    identifyTopIssues(data) {
        const issues = [];
        
        // 1. Check if plant is running at low load
        const avgProduction = data.production?.actual || 0;
        const ratedCapacity = data.production?.expected || 270; // From config
        const loadPercentage = (avgProduction / ratedCapacity) * 100;
        
        if (loadPercentage < 50 && loadPercentage > 0) {
            issues.push({
                type: 'Low Load Operation',
                parameter: 'Plant Utilization',
                severity: 'Medium',
                value: loadPercentage.toFixed(1) + '%',
                status: `Plant running at ${loadPercentage.toFixed(1)}% of rated capacity (${ratedCapacity} MW). Operating in low load mode.`,
                recommendation: 'Investigate why plant is not running at optimal load. Check grid demand, fuel availability, or maintenance restrictions.'
            });
        }
        
        // 2. Check parameter abnormalities (vibration, temperature, pressure)
        if (data.conditionScores) {
            const vibrationParams = Object.keys(data.conditionScores).filter(p => p.toLowerCase().includes('vib'));
            const tempParams = Object.keys(data.conditionScores).filter(p => p.toLowerCase().includes('temp'));
            const pressureParams = Object.keys(data.conditionScores).filter(p => p.toLowerCase().includes('pressure'));
            
            // Check vibration issues
            vibrationParams.forEach(param => {
                const score = data.conditionScores[param];
                const scoreValue = typeof score === 'object' ? score.value : score;
                const scoreColor = typeof score === 'object' ? score.color : (scoreValue < 70 ? 'red' : scoreValue < 85 ? 'yellow' : 'green');
                
                if (scoreColor === 'red' || scoreColor === 'yellow') {
                    issues.push({
                        type: 'Abnormal Vibration',
                        parameter: param,
                        severity: scoreColor === 'red' ? 'High' : 'Medium',
                        value: scoreValue,
                        status: `Vibration level ${scoreColor === 'red' ? 'critical' : 'elevated'}. Potential bearing or alignment issue.`,
                        recommendation: 'Schedule vibration analysis. Check bearing condition, alignment, and rotor balance.'
                    });
                }
            });
            
            // Check temperature issues
            tempParams.forEach(param => {
                const score = data.conditionScores[param];
                const scoreValue = typeof score === 'object' ? score.value : score;
                const scoreColor = typeof score === 'object' ? score.color : (scoreValue < 70 ? 'red' : scoreValue < 85 ? 'yellow' : 'green');
                
                if (scoreColor === 'red' || scoreColor === 'yellow') {
                    issues.push({
                        type: 'Temperature Abnormality',
                        parameter: param,
                        severity: scoreColor === 'red' ? 'High' : 'Medium',
                        value: scoreValue,
                        status: `Temperature ${scoreColor === 'red' ? 'critically high' : 'elevated'}. Cooling system may be underperforming.`,
                        recommendation: 'Check cooling water flow, CT fan operation, and condenser performance.'
                    });
                }
            });
        }
        
        // 3. Check condition scores - ONLY RED (critical) conditions
        if (data.conditionScores) {
            Object.entries(data.conditionScores).forEach(([param, score]) => {
                const scoreValue = typeof score === 'object' ? score.value : score;
                const scoreColor = typeof score === 'object' ? score.color : (scoreValue < 70 ? 'red' : scoreValue < 85 ? 'yellow' : 'green');
                const scoreStatus = typeof score === 'object' ? score.status : 'Unknown';
                
                // Flag RED (critical) conditions that weren't already flagged above
                if (scoreColor === 'red' && !issues.find(i => i.parameter === param)) {
                    issues.push({
                        type: 'Critical Condition',
                        parameter: param,
                        severity: 'High',
                        value: scoreValue,
                        status: scoreStatus
                    });
                }
            });
        }
        
        // 4. Check loss attribution - ONLY significant losses > 10%
        const lossAttr = data.lossAttribution?.attribution || data.lossAttribution?.lossBreakdown;
        if (lossAttr) {
            Object.entries(lossAttr).forEach(([param, loss]) => {
                const lossPercentage = (loss.loss_percentage || loss.lossPercentage || 0) * 100;
                const lossAmount = loss.loss_amount || loss.lossAmount || 0;
                
                // Only flag if loss > 10%
                if (lossPercentage > 10) {
                    issues.push({
                        type: 'Production Loss',
                        parameter: param,
                        severity: 'High',
                        lossAmount: lossAmount,
                        lossPercentage: lossPercentage,
                        status: `Parameter causing ${lossPercentage.toFixed(1)}% production loss`,
                        recommendation: `Optimize ${param} to recover ${lossAmount.toFixed(2)} MW production`
                    });
                }
            });
        }
        
        // Sort by severity
        return issues.sort((a, b) => {
            const severityOrder = { 'High': 3, 'Medium': 2, 'Low': 1 };
            return severityOrder[b.severity] - severityOrder[a.severity];
        });
    }
    
    /**
     * Generate recommendations
     */
    generateRecommendations(data) {
        const recommendations = [];
        
        // Stability recommendation
        const stabilityIndex = data.stability.stabilityIndex || data.stability.stability_index || 1;
        if (stabilityIndex < 0.7) {
            recommendations.push({
                priority: 'High',
                category: 'Stability',
                recommendation: 'Improve load stability - high fluctuations detected',
                expectedImpact: 'Reduce wear, improve efficiency'
            });
        }
        
        // Efficiency recommendation
        const totalLossFactor = data.efficiencyAdjustment.totalLossFactor || data.efficiencyAdjustment.total_loss_factor || 0;
        if (totalLossFactor > 0.15) {
            recommendations.push({
                priority: 'High',
                category: 'Efficiency',
                recommendation: 'Address efficiency losses - operating significantly below baseline',
                expectedImpact: `Recover ${(totalLossFactor * 100).toFixed(1)}% efficiency`
            });
        }
        
        // Availability recommendation
        const availability = data.availability.availability || 100;
        if (availability < 85) {
            recommendations.push({
                priority: 'High',
                category: 'Availability',
                recommendation: 'Reduce breakdown time - availability below industry standard',
                expectedImpact: `Increase availability from ${availability.toFixed(1)}% to 90%+`
            });
        }
        
        return recommendations;
    }
}

// Create global instance
window.MasterCalculationEngine = MasterCalculationEngine;

console.log('✓ Master Calculation Engine loaded');
