# TagValuesPoolService Architecture
**Last Updated:** December 23, 2025  
**Status:** Production Implementation

## Overview
`TagValuesPoolService` is a shared in-memory cache that serves as the central hub for all OPC tag values. It enables multiple consumers (HMI, Database, Analytics) to read tag data without creating duplicate OPC connections.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        OPC DA Server                                 │
│                   (Matrikon.OPC.Simulation.1)                       │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             │ Poll every 1000ms (OpcPollingIntervalMs)
                             ↓
┌─────────────────────────────────────────────────────────────────────┐
│                     OpcServerConnection                              │
│                  GetCachedValues() returns                           │
│                  List<TagValue> (all tags)                           │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             │ Read cached values (no OPC calls)
                             ↓
┌─────────────────────────────────────────────────────────────────────┐
│                    DataLoggingService                                │
│          ExecuteAsync() loop at OpcPollingIntervalMs                 │
│                                                                       │
│  var allValues = connectionSnapshot.GetCachedValues();              │
│  _tagPool.UpdatePool(allValues, batchTimestamp);                    │
│                                                                       │
│  • Updates pool every 1000ms (always)                               │
│  • Writes parquet every 5000ms (throttled)                          │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             │ UpdatePool() - write with lock
                             ↓
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃              TagValuesPoolService (Singleton)                       ┃
┃  ┌─────────────────────────────────────────────────────────────┐   ┃
┃  │  ConcurrentDictionary<string, TagValueCacheEntry>            │   ┃
┃  │  + lock(_updateLock) for writes                              │   ┃
┃  │  + Thread-safe reads (no lock needed)                        │   ┃
┃  └─────────────────────────────────────────────────────────────┘   ┃
┃                                                                      ┃
┃  Methods:                                                            ┃
┃  • UpdatePool(List<TagValue>, DateTime) - Write (locked)            ┃
┃  • GetAllTagValues() - Read all tags (concurrent)                   ┃
┃  • GetTagValues(IEnumerable<string>) - Read filtered (concurrent)   ┃
┃  • GetLastUpdateTimestamp() - Get last update time                  ┃
┗━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
                      │
        ┌─────────────┼─────────────┐
        │             │             │
        ↓             ↓             ↓
    HMI API    Historian DB   Future Services
                                                                      
┌─────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐
│ OpcController   │  │ HistorianIngest     │  │ ML/Analytics        │
│                 │  │ HostedService       │  │ Services            │
│ GET /api/opc/   │  │                     │  │                     │
│      values     │  │ PrecisePolling      │  │ (Future)            │
│                 │  │ LoopAsync()         │  │                     │
│ _tagPool.Get    │  │                     │  │                     │
│ AllTagValues()  │  │ _tagPool.Get        │  │                     │
│                 │  │ TagValues(          │  │                     │
│ Returns: ALL    │  │   mappedTagIds)     │  │                     │
│ tags in JSON    │  │                     │  │                     │
│                 │  │ Returns: ONLY       │  │                     │
│ ↓               │  │ mapped tags         │  │                     │
│                 │  │                     │  │                     │
│ dashboard.js    │  │ ↓                   │  │                     │
│ fetch every     │  │                     │  │                     │
│ 1 second        │  │ RateController      │  │                     │
│                 │  │ ServiceProcess      │  │                     │
│ Updates UI      │  │ Sample()            │  │                     │
│ charts/tables   │  │                     │  │                     │
│                 │  │ • Check deadband    │  │                     │
│                 │  │ • Compare previous  │  │                     │
│                 │  │ • Write ONLY if     │  │                     │
│                 │  │   value changed     │  │                     │
│                 │  │                     │  │                     │
│                 │  │ ↓                   │  │                     │
│                 │  │                     │  │                     │
│                 │  │ PostgreSQL DB       │  │                     │
│                 │  │ historian_raw.      │  │                     │
│                 │  │ historian_          │  │                     │
│                 │  │ timeseries          │  │                     │
└─────────────────┘  └─────────────────────┘  └─────────────────────┘
```

---

## Key Components

### 1. TagValuesPoolService
**File:** `Services/TagValuesPoolService.cs`

**Purpose:** Thread-safe shared cache for tag values

**Properties:**
- `ConcurrentDictionary<string, TagValueCacheEntry>` - Tag storage
- `DateTime _lastUpdateTimestamp` - Last update time
- `object _updateLock` - Write synchronization lock

**Methods:**
```csharp
// Write (locked for thread safety)
void UpdatePool(List<TagValue> tagValues, DateTime timestamp)

// Read (concurrent - no lock needed)
List<TagValueCacheEntry> GetAllTagValues()
List<TagValueCacheEntry> GetTagValues(IEnumerable<string> tagIds)
DateTime GetLastUpdateTimestamp()
int GetCachedTagCount()
bool ContainsTag(string tagId)

// Maintenance
void ClearPool()
```

**Thread Safety:**
- ✅ **Writes:** Protected by `lock(_updateLock)`
- ✅ **Reads:** ConcurrentDictionary allows lock-free reads
- ✅ **Multiple Consumers:** Safe for parallel access

---

### 2. DataLoggingService (Pool Writer)
**File:** `Services/DataLoggingService.cs`

**Responsibilities:**
1. Read OPC cached values every 1000ms
2. Update TagValuesPoolService (always)
3. Write parquet files (throttled to 5000ms)

**Key Code:**
```csharp
// Line 358-362: Loop at OPC polling rate
var loopDelayMs = config.PerformanceIntervals?.OpcPollingIntervalMs ?? 1000;

// Line 469: Read from OPC connection cache (not device)
var allValues = connectionSnapshot.GetCachedValues();

// Line 486: Update shared pool EVERY cycle
_tagPool.UpdatePool(allValues, batchTimestamp);

// Lines 487-494: Parquet write throttling
var timeSinceLastWrite = (DateTime.Now - _lastParquetWrite).TotalMilliseconds;
if (timeSinceLastWrite < _currentIntervalMs) {
    // Pool updated, skip parquet write
    return;
}
// Time to write parquet file
_lastParquetWrite = DateTime.Now;
```

**Timing:**
- OPC polling: **1000ms** (OpcPollingIntervalMs)
- Pool update: **1000ms** (every cycle)
- Parquet write: **5000ms** (throttled)

---

### 3. OpcController (HMI API Consumer)
**File:** `Controllers/OpcController.cs`

**Endpoint:** `GET /api/opc/values`

**Code:**
```csharp
[HttpGet("values")]
public ActionResult GetAllTagValues()
{
    var allValues = _tagPool.GetAllTagValues();  // Line 48
    var lastUpdate = _tagPool.GetLastUpdateTimestamp();  // Line 49
    
    return Ok(new {
        count = allValues.Count,
        lastUpdate = lastUpdate,
        timestamp = DateTime.Now,
        tags = allValues.Select(v => new {
            tagId = v.TagId,
            value = v.Value,
            quality = v.Quality,
            timestamp = v.Timestamp
        }).ToList()
    });
}
```

**Consumer:** `HMI/static/js/dashboard.js` line 1718
- Polls endpoint every 1 second
- Displays ALL tags in UI
- No filtering applied

---

### 4. HistorianIngestHostedService (Database Consumer)
**File:** `Services/HistorianIngest/Services/HistorianIngestHostedService.cs`

**Responsibilities:**
1. Read ONLY mapped tags from pool
2. Apply rate control (deadband/change detection)
3. Write to PostgreSQL when values change

**Key Code:**
```csharp
// Line 640: Read filtered tags from pool
var mappedTagIds = enabledMappings.Select(m => m.TagId).ToList();
var cachedTagValues = _tagPool.GetTagValues(mappedTagIds);

// Line 675: Process each tag
await ProcessTagValueAsync(tagValue, "OPC_Pool", pollTimestamp);

// Line 237: Rate control
var filteredSample = _rateController.ProcessSample(rawSample);
```

**Flow:**
```
Pool → GetTagValues(mappedTagIds) 
     → RateControllerService.ProcessSample()
     → IF (deadband OR value changed)
     → Write to PostgreSQL
     ELSE
     → Filter (skip write)
```

---

### 5. RateControllerService (Change Detection)
**File:** `Services/HistorianIngest/Services/RateControllerService.cs`

**Purpose:** Prevent duplicate database writes

**Logic (Lines 156-170):**
```csharp
// Check if value changed
bool valueChanged = false;

if (mapping.DeadbandValue > 0) {
    // Deadband configured → threshold check
    valueChanged = Math.Abs(current - last) > mapping.DeadbandValue;
} else {
    // No deadband → exact comparison
    valueChanged = (current != last);
}

if (valueChanged) {
    // Write to database
    return sample;
} else {
    // Filter (don't write)
    return null;
}
```

**Deadband Configuration:**
| deadband_value | Data Type | Logic                               |
|----------------|-----------|-------------------------------------|
| `0` or `NULL`  | Any       | `current != previous` (exact)       |
| `> 0`          | double    | `|current - last| > deadband`       |
| `> 0`          | int       | `|current - last| > deadband`       |
| (ignored)      | bool      | Always exact comparison             |
| (ignored)      | string    | Always exact comparison             |

---

## Configuration

### logging-config.json
```json
{
  "PerformanceIntervals": {
    "OpcPollingIntervalMs": 1000,        // Pool update rate
    "UiBroadcastIntervalMs": 1000,
    "HistorianPollingFallbackMs": 1000
  },
  "DataLogging": {
    "IntervalSeconds": 5                 // Parquet write interval
  }
}
```

### historian_meta.tag_master (PostgreSQL)
```sql
CREATE TABLE historian_meta.tag_master (
    tag_id VARCHAR(255) PRIMARY KEY,
    tag_name VARCHAR(255),
    data_type VARCHAR(20),                    -- 'double', 'int', 'bool', 'string'
    deadband_value DOUBLE PRECISION DEFAULT 0,
    db_logging_interval_ms INTEGER DEFAULT 1000,
    enabled BOOLEAN DEFAULT true
);
```

**Example Insert:**
```sql
INSERT INTO historian_meta.tag_master 
(tag_id, tag_name, data_type, deadband_value, db_logging_interval_ms, enabled, created_by)
VALUES 
('Random.Int2', 'Random Integer', 'int', 0, 1000, true, 'admin'),
('Random.Real4', 'Random Float', 'double', 0.5, 1000, true, 'admin');
```

---

## Performance Characteristics

### Timing
| Operation                  | Interval  | Notes                              |
|---------------------------|-----------|------------------------------------|
| OPC polling               | 1000ms    | OpcServerConnection timer          |
| Pool update               | 1000ms    | DataLoggingService loop            |
| Parquet write             | 5000ms    | Throttled (not every cycle)        |
| HMI API poll              | 1000ms    | dashboard.js fetch                 |
| Historian poll            | Variable  | Min of tag intervals (default 1000ms) |
| Database write            | On change | Only when value changes            |

### Throughput
- **Tags tested:** 1-10 tags (production supports 2000+)
- **Read operations:** ~11ms average (HTTP overhead)
- **DB write rate:** 8-9 writes/second (for changing values)
- **Pool update:** <1ms (in-memory cache)

### Memory
- **Pool capacity:** 2000 tags (configurable)
- **Per-tag storage:** ~100 bytes (TagValueCacheEntry)
- **Total pool size:** ~200KB for 2000 tags

---

## Thread Safety Guarantees

### Write Path (Single Writer)
```
DataLoggingService (single thread)
    ↓
lock(_updateLock) { ... }
    ↓
_tagValuesCache[tagId] = entry
```
✅ **Safe:** Only one writer, protected by lock

### Read Path (Multiple Readers)
```
OpcController.GetAllTagValues()        (Thread 1)
HistorianIngest.GetTagValues()         (Thread 2)
FutureService.GetTagValues()           (Thread 3)
    ↓
ConcurrentDictionary.Values.ToList()
```
✅ **Safe:** ConcurrentDictionary allows lock-free concurrent reads

### Write + Read (Simultaneous)
```
DataLoggingService writes             (Thread 1 - locked)
OpcController reads                   (Thread 2 - unlocked)
```
✅ **Safe:** ConcurrentDictionary guarantees consistency

---

## Testing Results

### Test: 30-Second Continuous Operation
**File:** `test_continuous_db_logging.py`

**Results:**
```
Duration:              30.1 seconds
Total OPC Reads:       269
Value Changes:         265
Database Writes:       265
Write Success Rate:    100.0%
Average Read Time:     8.64ms
Reads per Second:      8.9
DB Writes per Second:  8.8
Average Change Rate:   113.5ms between changes
```

**Verification:**
```sql
SELECT COUNT(*) FROM historian_raw.historian_timeseries 
WHERE sample_source = 'OPC_DA';
-- Result: 265 records
```

✅ **Conclusion:** System successfully handles continuous read/write operations with 100% reliability

---

## Common Issues & Solutions

### Issue 1: HMI shows stale data
**Symptom:** UI not updating every second
**Check:**
1. Is DataLoggingService running? (logs should show "TagPool updated")
2. Is OpcPollingIntervalMs = 1000ms? (check logging-config.json)
3. Is OPC server connected? (check /api/opc/status endpoint)

**Fix:**
```bash
# Restart C# service to reload config
dotnet run --project OpcDaWebBrowser.csproj
```

### Issue 2: No database writes
**Symptom:** historian_timeseries table empty
**Check:**
1. Are tags mapped in tag_master table?
   ```sql
   SELECT * FROM historian_meta.tag_master WHERE enabled = true;
   ```
2. Is deadband blocking writes? (check if values changing enough)
3. Is RateController filtering everything? (check logs for "FILTERED")

**Fix:**
```sql
-- Add tag mapping with no deadband
INSERT INTO historian_meta.tag_master 
(tag_id, tag_name, data_type, deadband_value, enabled, created_by)
VALUES ('Random.Int2', 'Test Tag', 'int', 0, true, 'admin')
ON CONFLICT (tag_id) DO UPDATE SET enabled = true, deadband_value = 0;
```

### Issue 3: Pool not updating
**Symptom:** GetLastUpdateTimestamp() returns MinValue
**Check:**
1. Is DataLoggingService enabled in logging-config.json?
2. Is OPC connection established? (check _loggingConnection != null)
3. Are there any exceptions in logs?

**Fix:**
```json
// logging-config.json
{
  "DataLogging": {
    "Enabled": true,
    "IntervalSeconds": 5
  }
}
```

---

## Future Enhancements

### Planned Features
1. **Pool statistics endpoint:** `/api/opc/pool/stats`
   - Tag count, last update time, memory usage
   
2. **Real-time pool monitoring:** WebSocket endpoint
   - Stream pool updates to clients
   
3. **Pool capacity alerts:** Health monitoring
   - Warn when approaching 2000 tag limit
   
4. **Historical pool snapshots:** Archive mechanism
   - Save pool state for replay/debugging

### Performance Optimizations
1. **Batch updates:** Group pool writes
2. **Selective updates:** Only update changed tags
3. **Compression:** Reduce memory footprint
4. **Partitioning:** Split pool for 10K+ tags

---

## Related Documentation
- `.github/copilot-instructions.md` - System architecture overview
- `HISTORIAN_SCHEMA_ANALYSIS.md` - Database schema details
- `SYSTEM_ARCHITECTURE_DOCUMENTATION.md` - Complete system design
- `Services/TagValuesPoolService.cs` - Implementation source code
- `Services/DataLoggingService.cs` - Pool writer implementation
- `Services/HistorianIngest/Services/RateControllerService.cs` - Change detection logic

---

## Change Log
| Date       | Change                                           | Author |
|------------|--------------------------------------------------|--------|
| 2025-12-23 | Initial documentation - TagPool architecture     | System |
| 2025-12-23 | Added deadband logic, thread safety, test results| System |
| 2025-12-23 | Updated polling interval 500ms → 1000ms          | System |
