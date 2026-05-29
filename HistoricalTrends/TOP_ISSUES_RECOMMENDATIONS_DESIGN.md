# TOP ISSUES & RECOMMENDATIONS DESIGN

## 3. TOP ISSUES - Current Implementation

### Logic (master_calculation_engine.js lines 553-614):

```javascript
identifyTopIssues(data) {
    const issues = [];
    
    // 1. Check Condition Scores - ONLY RED (critical) conditions
    if (data.conditionScores) {
        Object.entries(data.conditionScores).forEach(([param, score]) => {
            const scoreValue = typeof score === 'object' ? score.value : score;
            const scoreColor = typeof score === 'object' ? score.color : 
                (scoreValue < 70 ? 'red' : scoreValue < 85 ? 'yellow' : 'green');
            
            // ONLY flag RED (critical) conditions, NOT yellow warnings
            if (scoreColor === 'red') {
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
    
    // 2. Check Loss Attribution - ONLY significant losses > 10%
    const lossAttr = data.lossAttribution.attribution || data.lossAttribution.lossBreakdown;
    if (lossAttr) {
        Object.entries(lossAttr).forEach(([param, loss]) => {
            const lossPercentage = (loss.loss_percentage || loss.lossPercentage || 0) * 100;
            
            // Only flag if loss > 10%
            if (lossPercentage > 10) {
                issues.push({
                    type: 'Production Loss',
                    parameter: param,
                    severity: 'High',
                    lossAmount: lossAmount,
                    lossPercentage: lossPercentage
                });
            }
        });
    }
    
    return issues.sort((a, b) => severityOrder[b.severity] - severityOrder[a.severity]);
}
```

### Current Problem:
- Python condition scoring API is returning YELLOW (warning) scores for TOTAL_COAL_FLOW and TURBINE_LOADMW
- These are being displayed as "Warning" even though I removed yellow flagging
- The Python API `/api/v1/condition/score` is calculating scores between 70-85 (yellow range)

### Why Yellow Scores?
Looking at condition scoring logic, parameters get yellow score if:
- Score between 70-85
- Some minor deviation from normal range
- Not critical but flagged as "warning"

### Solution Options:
**Option A**: Fix Python condition scoring to not return yellow for normal parameters
**Option B**: Increase threshold - only flag scores < 50 as critical
**Option C**: Remove condition scoring from Top Issues entirely, only show production losses

---

## 4. RECOMMENDATIONS - Current Implementation

### Logic (master_calculation_engine.js lines 616-663):

```javascript
generateRecommendations(data) {
    const recommendations = [];
    
    // 1. Stability recommendation
    const stabilityIndex = data.stability.stabilityIndex || data.stability.stability_index || 1;
    if (stabilityIndex < 0.7) {
        recommendations.push({
            priority: 'High',
            category: 'Stability',
            recommendation: 'Improve load stability - high fluctuations detected',
            expectedImpact: 'Reduce wear, improve efficiency'
        });
    }
    
    // 2. Efficiency recommendation
    const totalLossFactor = data.efficiencyAdjustment.totalLossFactor || 
                           data.efficiencyAdjustment.total_loss_factor || 0;
    if (totalLossFactor > 0.15) {
        recommendations.push({
            priority: 'High',
            category: 'Efficiency',
            recommendation: 'Address efficiency losses - operating significantly below baseline',
            expectedImpact: `Recover ${(totalLossFactor * 100).toFixed(1)}% efficiency`
        });
    }
    
    // 3. Availability recommendation
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
```

### Current Problem:
- Stability recommendation shows even when data is perfectly stable
- Python stability API is returning "Poor" rating for flat data (CV = 0%)
- This triggers false recommendation: "Improve load stability - high fluctuations detected"
- But there are NO fluctuations! Data is perfectly flat at 105.58 MW

### Why "Poor" Stability?
The Python stability engine might be:
- Interpreting CV = 0% as suspicious (too perfect = bad sensor?)
- Using different thresholds than expected
- Returning wrong rating for flat data

### Solution Options:
**Option A**: Fix Python stability calculation to handle flat data correctly
**Option B**: Don't recommend stability improvements if CV < 1% (very stable)
**Option C**: Remove stability recommendations entirely
**Option D**: Only recommend if stability < 0.5 (more strict threshold)

---

## SUMMARY OF CHANGES MADE:

✅ **Completed:**
1. Removed Performance Score card from top summary
2. Fixed Utilization = (actual / rated capacity) × 100
3. Removed yellow/warning conditions from Top Issues (only show red/critical)

⚠️ **Still Need Decision:**
3. Top Issues - Python is returning yellow scores for normal parameters
4. Recommendations - Python stability shows "Poor" for perfectly stable data

## YOUR REVIEW NEEDED:

Please check the code above and tell me:
1. For **Top Issues**: Should I fix Python condition scoring, or change the threshold?
2. For **Recommendations**: Should I fix Python stability rating, or remove/adjust the recommendation logic?
