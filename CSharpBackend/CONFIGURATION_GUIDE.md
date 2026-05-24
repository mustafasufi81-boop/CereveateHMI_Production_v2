# OPC DA System Configuration Guide

## Overview
This system is now **fully configurable** with NO hardcoded values. All limits, defaults, and UI parameters are dynamically loaded from `logging-config.json`.

## Configuration File: logging-config.json

### TrendViewerSettings Section
Controls all aspects of the Log Viewer trend visualization:

```json
"TrendViewerSettings": {
  "DefaultPointsPerTag": 500,        // Number of data points loaded per tag by default
  "MaxPointsPerTag": 2000,           // Maximum data points that can be requested per tag
  "DefaultTrendCount": 20,           // Number of trends shown by default when loading a file
  "MaxTrendCount": 20,               // Maximum number of trends that can be displayed at once
  "ChartContainerMaxHeight": 8000,   // Maximum height (pixels) of scrollable trend container
  "ChartHeight": 350,                // Individual chart height (pixels)
  "TableMaxRecords": 100             // Number of records shown in data table
}
```

### How It Works

#### Backend (C# Hub)
1. **OpcDaHub.cs** exposes `GetTrendViewerSettings()` method
2. Reads configuration from `logging-config.json` via `IConfiguration`
3. Returns settings object to frontend on request
4. Provides fallback defaults if config values are missing

```csharp
public object GetTrendViewerSettings()
{
    return new
    {
        DefaultPointsPerTag = _configuration.GetValue<int>("TrendViewerSettings:DefaultPointsPerTag", 500),
        MaxPointsPerTag = _configuration.GetValue<int>("TrendViewerSettings:MaxPointsPerTag", 2000),
        // ... other settings
    };
}
```

#### Frontend (JavaScript)
1. **On page load**: `loadTrendViewerConfig()` calls backend via SignalR
2. **Stores configuration** in `trendViewerConfig` global variable
3. **Applies settings** dynamically:
   - Container max-height set via DOM manipulation
   - Chart heights created from config value
   - Trend limits enforced using config values
   - All UI messages reflect current config

```javascript
// Configuration loaded on SignalR connection
await loadTrendViewerConfig();

// Usage throughout the code
const maxTrends = trendViewerConfig?.maxTrendCount || 20;
const chartHeight = trendViewerConfig?.chartHeight || 350;
```

## Configuration Parameters Explained

### DefaultPointsPerTag (500)
- **Purpose**: Number of data points retrieved per tag when loading trends
- **Impact**: Performance vs. granularity tradeoff
- **Recommendation**: 
  - 500-1000: Good balance for most cases
  - 100-300: Faster loading for large datasets
  - 1000-2000: High detail for analysis

### MaxPointsPerTag (2000)
- **Purpose**: Upper limit for data points that can be requested
- **Impact**: Prevents excessive memory usage
- **Recommendation**: Set to 2-4x DefaultPointsPerTag

### DefaultTrendCount (20)
- **Purpose**: Number of trends auto-selected when loading a file
- **Impact**: Initial load time and UI responsiveness
- **Recommendation**: 
  - 10-20: Standard for most screens
  - 5-10: For slower systems or many tags
  - 20-50: For high-res displays (adjust MaxTrendCount too)

### MaxTrendCount (20)
- **Purpose**: Maximum trends that can be displayed simultaneously
- **Impact**: Browser performance and scrolling UX
- **Recommendation**: 
  - Match or exceed DefaultTrendCount
  - Consider screen resolution (more trends = more scrolling)
  - 20-30: Typical range for 1080p displays
  - 50+: Only for high-res displays with powerful browsers

### ChartContainerMaxHeight (8000)
- **Purpose**: Maximum pixel height of scrollable trend container
- **Impact**: Scrollbar behavior and rendering
- **Calculation**: Should be >= `MaxTrendCount × ChartHeight`
- **Recommendation**:
  - Formula: `MaxTrendCount × ChartHeight × 1.2` (20% buffer)
  - Example: 20 trends × 350px × 1.2 = 8400px
  - Minimum: `MaxTrendCount × ChartHeight`

### ChartHeight (350)
- **Purpose**: Individual chart/trend canvas height
- **Impact**: Data visibility and total page height
- **Recommendation**: 
  - 250-300px: Compact view, more trends visible
  - 350-400px: Balanced (default)
  - 500+px: Detailed analysis mode

### TableMaxRecords (100)
- **Purpose**: Rows displayed in the data table view
- **Impact**: Page load performance
- **Recommendation**: 
  - 50-100: Fast loading
  - 100-200: Standard
  - 500+: Only if needed (paginate instead)

## Performance Tuning Examples

### High-Performance Configuration (Fast Loading)
```json
"TrendViewerSettings": {
  "DefaultPointsPerTag": 200,
  "MaxPointsPerTag": 1000,
  "DefaultTrendCount": 10,
  "MaxTrendCount": 15,
  "ChartContainerMaxHeight": 5500,
  "ChartHeight": 300,
  "TableMaxRecords": 50
}
```

### High-Detail Configuration (Analysis Focus)
```json
"TrendViewerSettings": {
  "DefaultPointsPerTag": 1000,
  "MaxPointsPerTag": 5000,
  "DefaultTrendCount": 30,
  "MaxTrendCount": 50,
  "ChartContainerMaxHeight": 20000,
  "ChartHeight": 400,
  "TableMaxRecords": 200
}
```

### Balanced Configuration (Recommended Default)
```json
"TrendViewerSettings": {
  "DefaultPointsPerTag": 500,
  "MaxPointsPerTag": 2000,
  "DefaultTrendCount": 20,
  "MaxTrendCount": 20,
  "ChartContainerMaxHeight": 8000,
  "ChartHeight": 350,
  "TableMaxRecords": 100
}
```

## Dynamic Behavior

### What Happens When Configuration Changes

1. **Edit `logging-config.json`**
2. **Restart the application** (configuration loaded on startup)
3. **Frontend automatically adapts**:
   - New limits enforced
   - UI messages updated
   - Container sizes adjusted
   - No code changes needed

### File-Agnostic Operation

The system now handles **ANY parquet file** with the following structure:
- **Required Columns**: RowId, TagId, Timestamp, Value, Quality
- **Flexible Types**: 
  - RowId: `long[]` or `long?[]`
  - Timestamp: `DateTime[]`, `DateTime?[]`, or `DateTimeOffset[]`
  - TagId, Value, Quality: `string[]`
- **Any Tag Count**: Automatically discovers and lists all tags
- **Any Record Count**: Processes files of any size (streams data)
- **Any Row Group Structure**: Handles single or multiple row groups

### Validation

The system validates configurations with fallback defaults:
```csharp
// If config value is missing or invalid, uses default
_configuration.GetValue<int>("TrendViewerSettings:DefaultPointsPerTag", 500)
```

## Troubleshooting

### Charts Not Showing Correct Number
**Check**: `DefaultTrendCount` in config
**Verify**: Browser console shows `[CONFIG] Loaded: {...}`

### Scrollbar Not Appearing
**Check**: `ChartContainerMaxHeight` >= `MaxTrendCount × ChartHeight`
**Fix**: Increase `ChartContainerMaxHeight` value

### Performance Issues
**Check**: `DefaultPointsPerTag` and `DefaultTrendCount`
**Fix**: Reduce both values for faster loading

### "Maximum X trends" Alert
**Check**: `MaxTrendCount` setting
**Adjust**: Increase if you need more simultaneous trends

## Architecture Benefits

✅ **Zero Hardcoded Values**: All parameters in configuration file
✅ **File-Agnostic**: Works with any valid parquet structure
✅ **Runtime Configurable**: Change settings without code modification
✅ **Type-Safe Fallbacks**: Default values prevent crashes
✅ **Centralized Control**: Single source of truth for all limits
✅ **User-Friendly**: Settings reflected in UI messages automatically

## Migration Notes

### Previous Hardcoded Values (v2.0 and earlier)
- ❌ 500 points per tag (hardcoded in JavaScript)
- ❌ 20 trends max (hardcoded in multiple functions)
- ❌ 8000px container height (hardcoded in CSS)
- ❌ 350px chart height (hardcoded in DOM creation)
- ❌ 100 table records (hardcoded in Hub call)

### Current Dynamic Values (v3.0+)
- ✅ All values loaded from `logging-config.json`
- ✅ Frontend calls `GetTrendViewerSettings()` on startup
- ✅ Configuration applied throughout application
- ✅ Single source of truth for all limits
