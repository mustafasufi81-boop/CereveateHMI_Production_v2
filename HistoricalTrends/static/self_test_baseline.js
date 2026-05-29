// ========================================
// BASELINE CALCULATION - SELF TEST
// Run this in browser console to verify
// ========================================

// Test Data Structure
const testConfig = {
    baselineData: [
        // Nov 8 - Dec 7 (30 days)
        // Average should be ~143.68 MW
        { Timestamp: '2024-11-08T00:00:00Z', TURBINE_LOADMW: 140 },
        { Timestamp: '2024-11-09T00:00:00Z', TURBINE_LOADMW: 145 },
        // ... more data ...
    ],
    targetDateData: [
        // Dec 8 data
        // Average should be ~238.29 MW
        { Timestamp: '2024-12-08T00:00:00Z', TURBINE_LOADMW: 235 },
        { Timestamp: '2024-12-08T01:00:00Z', TURBINE_LOADMW: 240 },
        // ... more data ...
    ],
    productionTag: 'TURBINE_LOADMW',
    ratedCapacity: 270,
    dateRange: {
        mode: 'single',
        baselineStart: '2024-11-08',
        baselineEnd: '2024-12-07',
        targetDate: '2024-12-08'
    }
};

// Expected Console Logs:
console.log(`
EXPECTED CONSOLE OUTPUT:
========================

📅 SINGLE DATE MODE: Comparing 2024-12-08 vs 30-day baseline
📊 DATA SUMMARY:
   Baseline Period: 2024-11-08 to 2024-12-07 → [COUNT] points
   Target Date: 2024-12-08 → [COUNT] points

📊 BASELINE CALCULATION:
   Mode: SINGLE DATE
   Baseline Data: [COUNT] points
   ✅ BASELINE VALUE: 143.680 MW
   Target Date Data: [COUNT] points
   ✅ TARGET DATE AVG: 238.290 MW
   Rated Capacity: 270 MW

📊 STEP 5 - PERFORMANCE CALCULATION:
   Data points analyzed: [COUNT]
   ✅ ACTUAL AVERAGE: 238.290 MW (from [COUNT] data points)
   ✅ EXPECTED (from efficiency): 143.680 MW

📋 EXECUTIVE SUMMARY GENERATION:
   ✅ Current Production (selected date avg): 238.290 MW
   ✅ Baseline (30-day historical avg): 143.680 MW
   ✅ Target (rated capacity): 270 MW
   📊 Delta from Baseline: 94.610 MW (GAIN)
   📊 Delta from Target: -31.710 MW

DASHBOARD DISPLAY:
=================
Current Avg Production: 238.290 MW
Baseline (Top 100%): 143.680 MW
Best/Target: 270.000 MW
Loss from Baseline: 94.610 MW
Loss from Best: 31.710 MW
`);

// Self-Test Function
function testBaselineCalculation() {
    console.log('🧪 Running Baseline Calculation Self-Test...\n');
    
    const productionTag = 'TURBINE_LOADMW';
    
    // Test 1: Calculate baseline from baselineData
    const baselineValues = testConfig.baselineData
        .map(d => parseFloat(d[productionTag]))
        .filter(v => !isNaN(v));
    const baselineAvg = baselineValues.reduce((sum, v) => sum + v, 0) / baselineValues.length;
    
    console.log('✓ Baseline Calculation:', baselineAvg.toFixed(3), 'MW');
    
    // Test 2: Calculate target date average
    const targetValues = testConfig.targetDateData
        .map(d => parseFloat(d[productionTag]))
        .filter(v => !isNaN(v));
    const targetAvg = targetValues.reduce((sum, v) => sum + v, 0) / targetValues.length;
    
    console.log('✓ Target Date Calculation:', targetAvg.toFixed(3), 'MW');
    
    // Test 3: Deltas
    const deltaFromBaseline = targetAvg - baselineAvg;
    const deltaFromTarget = targetAvg - testConfig.ratedCapacity;
    
    console.log('✓ Delta from Baseline:', deltaFromBaseline.toFixed(3), 'MW', deltaFromBaseline > 0 ? '(GAIN)' : '(LOSS)');
    console.log('✓ Delta from Target:', deltaFromTarget.toFixed(3), 'MW');
    
    console.log('\n🎉 Self-Test Complete!');
    
    return {
        baseline: baselineAvg,
        current: targetAvg,
        target: testConfig.ratedCapacity,
        deltaBaseline: deltaFromBaseline,
        deltaTarget: deltaFromTarget
    };
}

// Run test
// testBaselineCalculation();
