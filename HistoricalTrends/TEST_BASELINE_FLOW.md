# Baseline Calculation Flow Test

## Expected Flow for Dec 8, 2024

### Input:
- User selects: Dec 8, 2024 (single date)
- Production tag: TURBINE_LOADMW
- Rated capacity: 270 MW

### Step-by-Step Execution:

1. **Date Selection** (trends.js line 2729)
   - `startDate = "2024-12-08"`
   - `endDate = "2024-12-08"`
   - `isSingleDate = true` ✓

2. **Data Filtering** (trends.js line 2795)
   - Mode: SINGLE DATE
   - Target Date: 2024-12-08
   - Baseline Period: 2024-11-08 to 2024-12-07 (30 days before)

3. **Baseline Data Calculation** (trends.js line 2805)
   ```javascript
   baselineData = currentData.filter(row => {
       const rowDate = new Date(row.Timestamp).toISOString().split('T')[0];
       return rowDate >= "2024-11-08" && rowDate <= "2024-12-07";
   });
   ```

4. **Config Creation** (trends.js line 2917)
   ```javascript
   config = {
       productionTag: "TURBINE_LOADMW",
       ratedCapacity: 270,
       dateRange: {
           mode: 'single',
           baselineStart: "2024-11-08",
           baselineEnd: "2024-12-07",
           targetDate: "2024-12-08"
       },
       baselineData: [...],  // 30 days data
       targetDateData: [...]  // Dec 8 data
   }
   ```

5. **Dashboard Call** (trends.js line 2940)
   ```javascript
   window.AdvancedBIDashboard.showDashboard(targetDateData, config, startDate, endDate);
   ```

6. **Master Engine Execution** (advanced_bi_dashboard.js line 54)
   ```javascript
   this.currentAnalysis = await this.masterEngine.executeFullAnalysis(targetDateData, config);
   ```

7. **Step 1: Baseline Generation** (master_calculation_engine.js line 119)
   ```javascript
   // Mode = 'single'
   // config.baselineData = 30 days data (Nov 8 - Dec 7)
   // config.targetDateData = Dec 8 data
   
   baselineValues = config.baselineData
       .map(d => d.TURBINE_LOADMW)
       .filter(v => !isNaN(v));
   
   baselineValue = average(baselineValues);  // Should be ~143.68 MW (30-day avg)
   
   targetDateAverage = average(config.targetDateData[TURBINE_LOADMW]);  // Should be 238.29 MW
   ```

8. **Step 5: Performance Calculation** (master_calculation_engine.js line 323)
   ```javascript
   // data = targetDateData (Dec 8)
   avgActual = average(Dec 8 data);  // 238.29 MW
   avgExpected = baselineValue;  // 143.68 MW from step 1
   ```

9. **Executive Summary** (master_calculation_engine.js line 528)
   ```javascript
   currentProduction = analysisData.performance.averageActual;  // 238.29 MW
   baselinePerformance = analysisData.baseline.value;  // 143.68 MW
   bestPerformance = analysisData.baseline.ratedCapacity;  // 270 MW
   ```

### Expected Display:
- **Current Avg Production**: 238.29 MW (Dec 8 average)
- **Baseline (Top 100%)**: 143.68 MW (Nov 8 - Dec 7 average)
- **Best/Target**: 270 MW (rated capacity)
- **Loss from Baseline**: +94.61 MW (GAIN)
- **Loss from Best**: -31.71 MW (below target)

## Test Cases:

### Test 1: Single Date (Dec 8, 2024)
- ✓ Baseline = 30 days before average
- ✓ Current = Selected date average
- ✓ Target = Rated capacity (270 MW)

### Test 2: Date Range (Dec 1-15, 2024)
- ✓ Baseline = Entire range average
- ✓ Current = Last date (Dec 15) average
- ✓ Target = Rated capacity (270 MW)

### Test 3: No Historical Data
- ✓ Go back further (60, 90 days) to find data
- ✓ Show error if still no data found

## Potential Issues to Check:

1. ✓ `baselineData` is defined before use
2. ✓ `targetDateData` is defined before use
3. ✓ `baseline.confidence` removed (not needed)
4. ✓ Date format is yyyy-MM-dd
5. ✓ Config passed correctly to all steps
6. ⚠️ Need to verify `data` parameter in executeFullAnalysis is `targetDateData`
