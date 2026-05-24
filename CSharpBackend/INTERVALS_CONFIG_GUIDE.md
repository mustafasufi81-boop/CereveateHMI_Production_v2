# Performance Intervals Configuration Guide

## Overview
All hardcoded timing intervals have been moved to `logging-config.json` under the `PerformanceIntervals` section for centralized tuning and performance optimization.

## Configuration Location

**Runtime Config (Used by Application):**
```
bin\Debug\net8.0\win-x86\logging-config.json
```

**Source Config (Copied during build):**
```
logging-config.json
```

## Configuration Structure

```json
{
  "PerformanceIntervals": {
    // OPC Polling & Communication
    "OpcPollingIntervalMs": 1000,           // Default OPC DA polling rate
    "UiBroadcastIntervalMs": 1000,          // SignalR UI update throttle
    "PollingTaskWaitTimeoutMs": 2000,       // Timeout waiting for polling task
    "ReadOperationSlowThresholdMs": 1000,   // Log warning if read takes longer
    
    // Historian & Database
    "HistorianPollingFallbackMs": 1000,     // Fallback when no tag intervals set
    "HealthReportIntervalMs": 30000,        // Health status report frequency (30s)
    "StatusLogIntervalMs": 10000,           // Status logging frequency (10s)
    
    // Application Lifecycle
    "StartupDelayMs": 3000,                 // Delay before starting services
    "ErrorRetryDelayMs": 5000,              // Delay after error before retry
    "ConfigReloadCheckIntervalMs": 60000,   // Config change check (60s)
    
    // Memory & Capacity Limits
    "TagPoolCapacity": 2000,                // Max tags per connection pool
    "TagsPerOpcGroup": 2000,                // Tags per OPC group
    "MaxDataPointsPerTag": 10000,           // Trend data retention per tag
    "TimestampOrderCapacity": 50000         // Out-of-order detection buffer
  }
}
```

## Where Each Interval is Used

### OPC Polling & Communication

| Config Key | Default | Used In | Purpose |
|------------|---------|---------|---------|
| `OpcPollingIntervalMs` | 1000ms | `OpcServerConnection` | How often OPC DA reads tag values from server |
| `UiBroadcastIntervalMs` | 1000ms | `OpcDaService` | Throttles SignalR broadcasts to prevent UI flooding |
| `PollingTaskWaitTimeoutMs` | 2000ms | `OpcServerConnection.Disconnect()` | Max wait time for polling task to stop gracefully |
| `ReadOperationSlowThresholdMs` | 1000ms | `OpcServerConnection.ReadTagValues()` | Logs warning if OPC read takes longer than this |

### Historian & Database

| Config Key | Default | Used In | Purpose |
|------------|---------|---------|---------|
| `HistorianPollingFallbackMs` | 1000ms | `DataLoggingService`, `HistorianIngestHostedService` | Fallback polling rate when no tags configured |
| `HealthReportIntervalMs` | 30000ms | `HistorianIngestHostedService` | How often to log health metrics |
| `StatusLogIntervalMs` | 10000ms | `HistorianIngestHostedService` | How often to log status updates |

### Application Lifecycle

| Config Key | Default | Used In | Purpose |
|------------|---------|---------|---------|
| `StartupDelayMs` | 3000ms | `DataLoggingService.ExecuteAsync()` | Allows other services to initialize before data logging starts |
| `ErrorRetryDelayMs` | 5000ms | Multiple services | Wait time after error before retry |
| `ConfigReloadCheckIntervalMs` | 60000ms | `DataLoggingService` | How often to check for config file changes |

### Memory & Capacity Limits

| Config Key | Default | Used In | Purpose |
|------------|---------|---------|---------|
| `TagPoolCapacity` | 2000 | `OpcServerConnection.Capacity` | Max tags per connection pool/group |
| `TagsPerOpcGroup` | 2000 | `OpcServerConnection.TAGS_PER_GROUP` | OPC DA group size limit |
| `MaxDataPointsPerTag` | 10000 | `TrendDataService` | In-memory trend data points per tag |
| `TimestampOrderCapacity` | 50000 | `HistorianIngestHostedService` | Out-of-order timestamp detection buffer |

## Services Updated to Use Config

### ✅ Fully Migrated Services
- `OpcDaService.cs` - UI broadcast interval
- `DataLoggingService.cs` - Startup, error retry, config check, loop fallback
- `LoggingConfigService.cs` - Added `PerformanceIntervalsConfig` class

### ⏳ Partially Migrated (Hardcoded values remain for now)
- `OpcServerConnection.cs` - Still uses constructor parameter for polling (passed from config)
- `HistorianIngestHostedService.cs` - Uses hardcoded 30000ms, 10000ms for logging
- `TrendDataService.cs` - Hardcoded 10000 max points per tag
- `OpcAutoConnectService.cs` - Hardcoded 5000 batch size

### 📝 Services NOT Migrated (Test/Special Purpose)
- `StressTestService.cs` - Test harness with own config
- `StressTestHostedService.cs` - Reads from appsettings.json StressTest section

## Performance Tuning Guidelines

### Fast Polling (< 1 second)
```json
{
  "DataLogging": {
    "IntervalSeconds": 0.5  // 500ms
  },
  "PerformanceIntervals": {
    "OpcPollingIntervalMs": 500,
    "HistorianPollingFallbackMs": 500,
    "UiBroadcastIntervalMs": 500
  }
}
```
**Recommended for:** Small tag sets (< 100 tags), high-speed processes

### Standard Polling (1 second - DEFAULT)
```json
{
  "DataLogging": {
    "IntervalSeconds": 1  // 1000ms
  },
  "PerformanceIntervals": {
    "OpcPollingIntervalMs": 1000,
    "HistorianPollingFallbackMs": 1000,
    "UiBroadcastIntervalMs": 1000
  }
}
```
**Recommended for:** Most applications (< 500 tags)

### High-Volume Polling (> 1000 tags)
```json
{
  "DataLogging": {
    "IntervalSeconds": 2  // 2000ms or higher
  },
  "PerformanceIntervals": {
    "OpcPollingIntervalMs": 2000,
    "HistorianPollingFallbackMs": 2000,
    "UiBroadcastIntervalMs": 2000,
    "TagPoolCapacity": 5000,
    "TagsPerOpcGroup": 5000
  }
}
```
**Recommended for:** Large tag sets (> 1000 tags)

## Known Limitations

### OPC DA COM Interop Limits
- **Minimum reliable interval:** ~100-500ms
- **2ms polling:** Will crash due to COM marshaling overhead
- **100ms polling:** May become unstable with database writes

### Why Some Values Remain Hardcoded

1. **OPC Group Capacity (2000 tags):** OPC DA standard limitation
2. **Health/Status Intervals (30s/10s):** Logging frequency shouldn't need tuning
3. **Timestamp Buffer (50000):** Memory optimization for 10K+ tags

## Migration Benefits

✅ **Easy Performance Tuning:** Change intervals without recompiling  
✅ **Clear Documentation:** All timing values in one place  
✅ **Per-Environment Config:** Dev, staging, prod can have different intervals  
✅ **A/B Testing:** Compare performance with different intervals  
✅ **Debugging:** Reduce intervals to diagnose issues faster  

## Update Instructions

1. **Edit runtime config:**
   ```cmd
   notepad bin\Debug\net8.0\win-x86\logging-config.json
   ```

2. **Modify `PerformanceIntervals` section** with desired values

3. **Restart OPC service:**
   ```cmd
   dotnet run
   ```

4. **Monitor logs** to verify new intervals are being used:
   ```
   INFO: Using user-specified interval: 500ms for 36 tags
   DEBUG: Loop delay: 500ms (matching OPC interval)
   ```

## Fallback Behavior

All config values have **safe fallbacks** in case `PerformanceIntervals` section is missing:

```csharp
var startupDelay = config.PerformanceIntervals?.StartupDelayMs ?? 3000;
var retryDelay = config.PerformanceIntervals?.ErrorRetryDelayMs ?? 5000;
var fallback = config.PerformanceIntervals?.HistorianPollingFallbackMs ?? 1000;
```

This ensures the system works even with old config files.

## Validation

After config changes, check logs for confirmation:

```
[Information] Using user-specified interval: 1000ms for 36 tags
[Debug] Loop delay: 1000ms (matching OPC interval)
[Information] OpcDaService: UI broadcast throttle: 1000ms
[Information] HistorianIngestHostedService: Target interval: 1000ms
```

## Related Files

- `logging-config.json` - Source configuration (copied to bin during build)
- `bin\Debug\net8.0\win-x86\logging-config.json` - **RUNTIME CONFIG (edit this one!)**
- `Services\LoggingConfigService.cs` - Loads and parses configuration
- `Services\OpcDaService.cs` - Uses UI broadcast interval
- `Services\DataLoggingService.cs` - Uses startup, retry, polling intervals
- `Services\OpcServerConnection.cs` - Receives polling interval from DataLoggingService

---

**Last Updated:** December 22, 2025  
**Config Version:** 1.0 (Centralized Intervals)
