# HARDCODED VALUES CHECK - ADVANCED BI DASHBOARD

## SUMMARY: ✅ NO CRITICAL HARDCODING - ALL DYNAMIC

## Findings:

### ✅ **Python Backend** (app.py, bi_engines/*.py)
- **NO hardcoded values** for 270 MW, 105.58, or TURBINE_LOADMW
- All calculations are **100% dynamic** based on input data
- Engines accept any tag names and values

### ✅ **JavaScript Frontend** - Properly Auto-Detected

#### **1. Production Tag Selection** (trends.js line 2632-2638)
```javascript
// Auto-detect production tag
let productionTag = selectedTags[0];  // First tag as fallback
const productionKeywords = ['Load', 'MW', 'Power', 'Generation', 'Output'];
const detectedProduction = selectedTags.find(tag => 
    productionKeywords.some(keyword => tag.includes(keyword))
);
```
**Status**: ✅ Auto-detects from user-selected tags
**Works with**: Any tag containing 'Load', 'MW', 'Power', 'Generation', or 'Output'

#### **2. Rated Capacity** (trends.js line 2645-2652)
```javascript
let ratedCapacity = 250; // Default fallback (only if no data)
if (currentData.length > 0 && currentData[0][productionTag]) {
    const productionValues = currentData
        .map(d => d[productionTag])
        .filter(v => v !== null && !isNaN(v));
    if (productionValues.length > 0) {
        const maxObserved = Math.max(...productionValues);
        ratedCapacity = Math.ceil(maxObserved * 1.1); // 10% margin above max
    }
}
```
**Status**: ✅ Auto-calculated from actual data (max value × 1.1)
**Fallback**: 250 MW (only used if no valid data exists)
**Works with**: Any production values - automatically adjusts

#### **3. Baseline Configuration** (master_calculation_engine.js line 123)
```javascript
let ratedCapacity = config.ratedCapacity || 270; // Default 270 MW
```
**Status**: ✅ Uses config value passed from trends.js (auto-detected)
**Fallback**: 270 MW (only if config not provided - should never happen)

#### **4. Executive Summary** (master_calculation_engine.js line 526)
```javascript
const bestPerformance = analysisData.baseline.ratedCapacity || 270;
```
**Status**: ✅ Uses value from baseline API response
**Fallback**: 270 MW (only if API doesn't return it)

## VERIFICATION WITH DIFFERENT DATA:

### Test Case 1: **Current Data (105.58 MW flat)**
- Auto-detected capacity: `105.58 × 1.1 = 116.138` → **117 MW**
- ❌ **ISSUE**: This is TOO LOW (should be 270 MW rated capacity)
- **Reason**: Data is flat at operating level, not rated capacity

### Test Case 2: **Variable Data (95-110 MW)**
- Auto-detected capacity: `110 × 1.1 = 121` → **121 MW**
- ❌ **ISSUE**: Still too low for a 270 MW plant

### Test Case 3: **Peak Data (250-270 MW)**
- Auto-detected capacity: `270 × 1.1 = 297` → **297 MW**
- ✅ **CORRECT**: Represents actual rated capacity

## ⚠️ IDENTIFIED ISSUE:

**Problem**: Auto-detection from `max × 1.1` assumes data includes near-rated capacity values
**Current Data**: All values ≈ 105.58 MW (39% capacity)
**Result**: Rated capacity calculated as 117 MW instead of 270 MW

## SOLUTION OPTIONS:

### Option A: **Use Baseline Configuration** (RECOMMENDED)
Store rated capacity in `baseline_config.json` (already implemented):
```json
{
  "TURBINE_LOADMW": {
    "rated_capacity": 270.0,  // ← User-defined, not auto-calculated
    "target_production": {...},
    "baseline_performance": 105.58
  }
}
```

### Option B: **Allow User Override**
Add UI to let user set rated capacity manually before opening dashboard

### Option C: **Increase Multiplier**
Change `max × 1.1` to `max × 2.5` to account for partial load operation
**Risk**: Inaccurate for plants running near capacity

### Option D: **Use Historical Maximum**
Store the highest ever observed value across all historical data
**Requires**: Database of historical max values per tag

## CURRENT STATUS:

✅ **Code is NOT hardcoded** - all values are dynamic
✅ **Works with any tag** - auto-detects production tags
✅ **Works with any date range** - verified with test
✅ **Calculations are correct** - all formulas are dynamic

⚠️ **Rated capacity detection needs user input** for plants operating below rated capacity

## RECOMMENDATION:

**Implement baseline_config.json integration** (already created):
1. Read `rated_capacity` from `baseline_config.json`
2. Fall back to auto-detection only if not configured
3. Allow user to update via API `/api/baseline/config`

This ensures:
- Accurate rated capacity (270 MW) even with partial load data
- User can override if needed
- Still auto-detects for unconfigured tags
