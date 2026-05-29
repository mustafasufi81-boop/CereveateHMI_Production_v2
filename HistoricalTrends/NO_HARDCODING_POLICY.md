# NO HARDCODING POLICY - CONFIGURATION-DRIVEN SYSTEM

## ⚠️ CRITICAL RULE: ZERO HARDCODED VALUES

All operational parameters, thresholds, limits, and business logic values **MUST** be configurable through `trends-config.json`. This ensures system flexibility and maintainability.

---

## ✅ CORRECT APPROACH - Configuration-Driven

### Example 1: Design Values for Grouped Bar Chart
```javascript
// ❌ WRONG - Hardcoded
const designValue = 270;  // NEVER DO THIS!

// ✅ CORRECT - Read from config
const config = await fetch('/api/config').then(r => r.json());
const tagLimits = config.GroupedBarSettings?.TagSpecificLimits?.TURBINE_LOADMW || {};
const designValue = tagLimits.DesignValue || (maxValue * 1.05);  // Fallback to calculated
```

### Example 2: Thresholds and Limits
```python
# ❌ WRONG - Hardcoded
MAX_BOXPLOT_SAMPLES = 5000  # NEVER DO THIS!

# ✅ CORRECT - Read from config
perf_config = trends_config.get('Performance', {})
MAX_BOXPLOT_SAMPLES = perf_config.get('MaxBoxPlotSamples', 5000)  # 5000 is fallback default
```

### Example 3: Default Tag Names
```python
# ❌ WRONG - Hardcoded
production_tag = 'TURBINE_LOADMW'  # NEVER DO THIS!

# ✅ CORRECT - Read from config or request parameter
production_tag = data.get('production_tag') or config.get('DefaultProductionTag', 'TURBINE_LOADMW')
```

---

## 📋 CONFIGURATION HIERARCHY

All values follow this priority order:

1. **User-provided runtime value** (API request parameter)
2. **Tag-specific configuration** (`TagSpecificLimits[tagName]`)
3. **Global configuration** (`GroupedBarSettings.DesignFactor`)
4. **System default** (last resort fallback in code)

### Example Implementation:
```javascript
// Priority 1: User input
const userValue = apiRequest.customValue;

// Priority 2: Tag-specific config
const tagConfig = config.GroupedBarSettings?.TagSpecificLimits?.[tagName];
const tagDesignValue = tagConfig?.DesignValue;

// Priority 3: Global config
const globalDesignValue = config.GroupedBarSettings?.DesignValue;
const globalDesignFactor = config.GroupedBarSettings?.DesignFactor;

// Priority 4: System default (only if everything else is null)
const DEFAULT_FACTOR = 1.05;

// Final value determination
const finalValue = userValue ?? tagDesignValue ?? globalDesignValue ?? (maxValue * (globalDesignFactor ?? DEFAULT_FACTOR));
```

---

## 🔧 TRENDS-CONFIG.JSON STRUCTURE

All configurable values live here:

```json
{
  "GroupedBarSettings": {
    "DesignFactor": 1.05,           // Global multiplier (5% margin)
    "DesignValue": null,            // Global fixed target (optional)
    "LastPeriodPercentile": 0.75,   // 75th percentile for comparison
    "TagSpecificLimits": {
      "TURBINE_LOADMW": {
        "DesignValue": 270,         // Fixed target for this tag
        "MinOperating": 50,          // Minimum operating point
        "MaxOperating": 270          // Maximum capacity
      },
      "BEARING_VIB_HP_FRONT-Y": {
        "DesignValue": null,         // Use calculated design
        "MinOperating": 0,
        "MaxOperating": 150
      }
    }
  },
  
  "Performance": {
    "MaxBoxPlotSamples": 5000,
    "MaxDistributionSamples": 10000,
    "MaxChartDataPoints": 50000
  },
  
  "OperatingBands": {
    "DefaultBandWidth": 2,           // ±2σ for operating bands
    "ShowBands": false,
    "BandMethod": "stddev"
  },
  
  "DataQualitySettings": {
    "DowntimeThreshold": {
      "ConsecutiveMissing": 5,
      "DurationMinutes": 5
    },
    "GarbageDetection": {
      "Enabled": true,
      "UnrealisticRangeMultiplier": 5,
      "ConstantValueDuration": 10
    }
  }
}
```

---

## 🚫 COMMON VIOLATIONS TO AVOID

### 1. Magic Numbers
```javascript
// ❌ WRONG
if (value > 270) { /* ... */ }

// ✅ CORRECT
const maxOperating = config.GroupedBarSettings?.TagSpecificLimits?.[tag]?.MaxOperating || Infinity;
if (value > maxOperating) { /* ... */ }
```

### 2. Hardcoded Percentiles
```javascript
// ❌ WRONG
const lastPeriodValue = sortedValues[Math.floor(sortedValues.length * 0.75)];

// ✅ CORRECT
const percentile = config.GroupedBarSettings?.LastPeriodPercentile || 0.75;
const lastPeriodValue = sortedValues[Math.floor(sortedValues.length * percentile)];
```

### 3. Hardcoded Tag Names
```python
# ❌ WRONG
production_tag = 'TURBINE_LOADMW'

# ✅ CORRECT
default_tags = trends_config.get('DefaultTags', {})
production_tag = data.get('production_tag') or default_tags.get('Production', 'TURBINE_LOADMW')
```

### 4. Hardcoded Time Windows
```javascript
// ❌ WRONG
const baselineWindow = 30;  // days

// ✅ CORRECT
const baselineWindow = config.BIAnalyticsSettings?.BaselineWindow || 30;
```

### 5. Hardcoded Thresholds
```python
# ❌ WRONG
if load > 5:  # 5% threshold

# ✅ CORRECT
threshold_config = trends_config.get('AvailabilitySettings', {})
threshold_percent = threshold_config.get('MinLoadThresholdPercent', 5)
if load > threshold_percent:
```

---

## 📝 CODE REVIEW CHECKLIST

Before committing code, verify:

- [ ] **No magic numbers** - All numeric constants come from config
- [ ] **No hardcoded strings** - Tag names, file paths from config
- [ ] **Fallback defaults present** - System works even if config missing
- [ ] **Config priority respected** - User > Tag > Global > Default
- [ ] **Documentation updated** - Config options documented in JSON
- [ ] **Per-tag support** - Different settings per parameter supported
- [ ] **Runtime flexibility** - Values can be changed without code redeployment

---

## 🔄 MIGRATION GUIDE

If you find hardcoded values in existing code:

### Step 1: Identify the Hardcoded Value
```javascript
const designValue = 270;  // Found hardcoded value
```

### Step 2: Add to Configuration
```json
{
  "GroupedBarSettings": {
    "TagSpecificLimits": {
      "TURBINE_LOADMW": {
        "DesignValue": 270
      }
    }
  }
}
```

### Step 3: Update Code to Read Config
```javascript
const tagLimits = config.GroupedBarSettings?.TagSpecificLimits?.[tag] || {};
const designValue = tagLimits.DesignValue || (maxValue * 1.05);
```

### Step 4: Test Both Modes
- Test with config value present
- Test with config value missing (should use calculated fallback)
- Test with tag not in TagSpecificLimits (should use global settings)

---

## 🎯 BENEFITS OF THIS APPROACH

1. **Flexibility**: Change behavior without code redeployment
2. **Per-Tag Customization**: Different settings for each parameter
3. **Runtime Adaptation**: System adapts to different plants/equipment
4. **Maintainability**: All business logic values in one place
5. **Testing**: Easy to test different scenarios via config changes
6. **Documentation**: Config file serves as operational manual
7. **Auditability**: Configuration changes are version-controlled

---

## 📊 CURRENT SYSTEM STATUS

### ✅ Properly Configured (No Hardcoding)
- Design values (per-tag support)
- Operating limits (min/max per tag)
- Performance thresholds (boxplot, distribution limits)
- Time windows (baseline, percentile calculations)
- Data quality rules (downtime detection, garbage filtering)
- Band widths (operating band calculations)

### ⚠️ Review Required
- Default tag names (should come from config)
- File path defaults (partially configurable)
- API timeout values
- Retry limits for services

---

## 🔍 EXAMPLE: How to Add New Configurable Parameter

### 1. Add to trends-config.json
```json
{
  "NewFeature": {
    "ThresholdValue": 100,
    "EnableAutoAdjust": true,
    "TagSpecificSettings": {
      "TURBINE_LOADMW": {
        "ThresholdValue": 150
      }
    }
  }
}
```

### 2. Read in Backend (app.py)
```python
new_feature_config = trends_config.get('NewFeature', {})
threshold = new_feature_config.get('ThresholdValue', 100)  # 100 is fallback
auto_adjust = new_feature_config.get('EnableAutoAdjust', True)
```

### 3. Use in Frontend (bi_analytics.js)
```javascript
async loadConfig() {
    const response = await fetch('/api/config');
    const config = await response.json();
    
    this.newFeatureConfig = config.NewFeature || {};
    this.threshold = this.newFeatureConfig.ThresholdValue || 100;
}

processTag(tag) {
    // Per-tag override
    const tagSettings = this.newFeatureConfig.TagSpecificSettings?.[tag] || {};
    const threshold = tagSettings.ThresholdValue || this.threshold;
    
    // Use threshold in logic
    if (value > threshold) { /* ... */ }
}
```

---

## 🎓 TRAINING EXAMPLES

### Example 1: Configurable Time-Series Grouping
```javascript
// Configuration
{
  "TimeSeriesBarSettings": {
    "AutoTimeGrouping": true,
    "HourlyThresholdHours": 48,
    "DailyThresholdDays": 30
  }
}

// Code
const tsConfig = config.TimeSeriesBarSettings || {};
const autoGrouping = tsConfig.AutoTimeGrouping !== false;
const hourlyThreshold = tsConfig.HourlyThresholdHours || 48;
const dailyThreshold = tsConfig.DailyThresholdDays || 30;

const hoursSpan = (endDate - startDate) / (1000 * 60 * 60);
const groupBy = autoGrouping
    ? (hoursSpan <= hourlyThreshold ? 'hour' : hoursSpan <= dailyThreshold * 24 ? 'day' : 'week')
    : 'day';
```

### Example 2: Configurable Outlier Detection
```javascript
// Configuration
{
  "BIAnalyticsSettings": {
    "OutlierMethod": "sigma",
    "OutlierThreshold": 3,
    "UseMAD": false
  }
}

// Code
const biConfig = config.BIAnalyticsSettings || {};
const method = biConfig.OutlierMethod || 'sigma';
const threshold = biConfig.OutlierThreshold || 3;

const outliers = method === 'sigma'
    ? values.filter(v => Math.abs(v - mean) > threshold * stdDev)
    : values.filter(v => Math.abs(v - median) > threshold * mad);
```

---

## 📅 MAINTENANCE

- **Weekly**: Review new code for hardcoded values
- **Monthly**: Audit config file for completeness
- **Quarterly**: Update this document with new patterns
- **Annual**: Refactor legacy hardcoded values

---

## 🆘 TROUBLESHOOTING

### Issue: "Config value not being read"
**Solution**: Check configuration hierarchy
1. Verify config file has no JSON syntax errors
2. Check for duplicate keys (JSON keeps last occurrence)
3. Verify API endpoint returns full config
4. Check browser console for config loading errors
5. Ensure fallback defaults are in place

### Issue: "Chart shows wrong values"
**Solution**: Debug configuration chain
1. Log config object in browser console
2. Log per-tag limits extraction
3. Verify priority order (tag > global > default)
4. Check for null vs undefined handling
5. Hard refresh browser (Ctrl+Shift+R)

---

## 📖 RELATED DOCUMENTATION

- `trends-config.json` - Main configuration file
- `API_DOCUMENTATION.md` - API endpoints serving config
- `BI_ENGINE_PYTHON_BACKEND_README.md` - Python engine configuration
- `DEPLOYMENT_README.md` - Configuration deployment notes

---

**Last Updated**: 2025-11-24
**Status**: ✅ Active Policy - All New Code Must Comply
**Violations**: Report to code review / Create issue
