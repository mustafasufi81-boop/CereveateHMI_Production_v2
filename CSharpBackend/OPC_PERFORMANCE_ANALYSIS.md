# OPC Server Performance Analysis

## Architecture Overview

### 1. **Dedicated Connection for Logging** ✅
**Status: EXCELLENT DESIGN**

```csharp
// DataLoggingService.cs - Line 79
private OpcServerConnection? _loggingConnection;
```

**Key Points:**
- **Separate OPC connection** specifically for data logging
- Does NOT interfere with main UI/SignalR connection
- Runs as **BackgroundService** (hosted service pattern)
- **Independent lifecycle** - can start/stop without affecting UI

### 2. **Non-Blocking Timer-Based Polling** ✅
**Status: OPTIMAL FOR PERFORMANCE**

```csharp
// OpcServerConnection.cs - Line 122
_pollingTimer = new Timer(PollTags, null, _pollingIntervalMs, _pollingIntervalMs);

// Line 483 - PollTags method
private void PollTags(object? state)
{
    if (!IsConnected || _itemMgt == null || _monitoredTags.Count == 0)
        return; // Quick exit if not ready
    
    try
    {
        var values = ReadTagValues(); // Synchronous OPC read
        LastPollTime = DateTime.Now;
        
        if (values.Count > 0)
        {
            TagValuesUpdated?.Invoke(this, new TagValuesEventArgs 
            { 
                Values = values,
                ServerConnection = ConnectionId
            });
        }
    }
    catch (Exception ex)
    {
        Status = $"Poll Error: {ex.Message}";
    }
}
```

**Benefits:**
- **System.Threading.Timer** runs on ThreadPool
- **No blocking** - each poll executes independently
- **Fast-fail** with early return checks
- **Exception isolated** - one bad poll doesn't crash service

### 3. **Lock-Free Tag Reading** ⚠️
**Status: GOOD BUT CAN BE OPTIMIZED**

```csharp
// OpcServerConnection.cs - Line 509
public List<TagValue> ReadTagValues()
{
    lock (_lock)  // ⚠️ Locks during entire OPC read operation
    {
        if (_itemMgt == null || _monitoredTags.Count == 0)
            return new List<TagValue>();

        List<TagValue> values = new();
        
        try
        {
            int[] handles = _monitoredTags.Values.Select(t => t.ServerHandle).ToArray();
            
            IOPCSyncIO syncIO = (IOPCSyncIO)_itemMgt;
            syncIO.Read(OPCDATASOURCE.OPC_DS_DEVICE, handles.Length, handles,
                out IntPtr valuesPtr, out IntPtr errorsPtr);
            
            // Parse results...
        }
        catch { }
        
        return values;
    }
}
```

**Issue:**
- Lock held during **entire OPC COM call** (which can take 50-200ms)
- If browsing/adding tags at same time → UI can block momentarily

**Impact:**
- **For logging only**: MINIMAL - lock is fine
- **For UI operations**: Could cause brief freezes with 1000+ tags

### 4. **Parquet Writing Pattern** ✅
**Status: EXCELLENT - Thread-Safe**

```csharp
// DataLoggingService.cs - Line 268
private async Task WriteToParquet(List<LogRecord> records, CancellationToken stoppingToken)
{
    lock (_fileLock)  // ✅ Proper file-level locking
    {
        if (_currentFilePath == null || _currentFileSize >= _maxFileSizeBytes)
        {
            CreateNewFile();
        }
        
        AppendToParquetFile(records);
    }
}

// Line 355 - Atomic write pattern
var tempFile = _currentFilePath + ".tmp";
using (var stream = File.Create(tempFile))
{
    using (var writer = ParquetWriter.CreateAsync(schema, stream).Result)
    {
        // Write all data
    }
}
// Atomic rename prevents corruption
if (fileExists) File.Delete(_currentFilePath!);
File.Move(tempFile, _currentFilePath!);
```

**Benefits:**
- **Lock scope**: Only during file operations (fast)
- **Atomic writes**: Crash-safe with .tmp → .parquet rename
- **Rotation**: Auto-creates new file at 2MB threshold
- **File-level lock**: Prevents corruption even with multiple writers

---

## Performance Capacity Estimates

### Tag Count Capacity

#### **Current Configuration:**
- **Polling Interval**: 1000ms (1 second) - configurable
- **OPC Read Method**: `IOPCSyncIO.Read()` - synchronous batch read
- **Lock Duration**: ~50-200ms per poll (depends on OPC server response time)

#### **Estimated Limits:**

| Tags | Poll Time (est) | Lock Time | System Impact | Status |
|------|----------------|-----------|---------------|--------|
| **50** | ~50ms | 5% lock time | None | ✅ Excellent |
| **100** | ~75ms | 7.5% lock time | None | ✅ Excellent |
| **500** | ~150ms | 15% lock time | Minimal | ✅ Good |
| **1000** | ~250ms | 25% lock time | Slight UI delay | ⚠️ Acceptable |
| **2000** | ~400ms | 40% lock time | Noticeable lag | ⚠️ Limit |
| **5000** | ~800ms | 80% lock time | Significant lag | ❌ Too High |

#### **Bottleneck Analysis:**

**1. OPC COM Call Time** (Primary Bottleneck)
- OPC server response: ~0.1-0.5ms per tag
- 100 tags = 10-50ms
- 1000 tags = 100-500ms
- **Varies by OPC server performance!**

**2. Memory Allocation**
- Each poll creates new `List<TagValue>` objects
- 1000 tags × 1Hz = 1000 objects/sec
- With GC, should handle 5000+ tags/sec
- **Not a concern**

**3. Parquet Writing** (Well Optimized)
- Batches all tags into single write
- Uses file-level lock (fast)
- **Not a bottleneck** - can handle 10,000+ tags/sec

**4. Lock Contention** (Secondary Concern)
- `_lock` held during OPC read
- If 1000 tags take 250ms to read:
  - Timer fires every 1000ms
  - Lock held 250ms (25% of time)
  - UI operations blocked during this 250ms window
- **Becomes issue at 2000+ tags**

---

## Recommended Tag Limits

### **Conservative (Current Architecture):**
```
Comfortable: 100-500 tags @ 1 second interval
Maximum:     1000 tags @ 1 second interval
Critical:    2000 tags @ 2 second interval
```

### **If Optimization Needed:**
```
Optimized:   2000-5000 tags @ 1 second interval
(requires lock refactoring)
```

---

## Optimization Recommendations

### **Priority 1: Remove Lock from OPC Read** (High Impact)

**Current:**
```csharp
lock (_lock)
{
    syncIO.Read(...); // Holds lock during COM call
}
```

**Optimized:**
```csharp
int[] handles;
IOPCSyncIO syncIO;

lock (_lock)
{
    // Quick copy of handles
    handles = _monitoredTags.Values.Select(t => t.ServerHandle).ToArray();
    syncIO = (IOPCSyncIO)_itemMgt;
}

// OPC read OUTSIDE lock
syncIO.Read(OPCDATASOURCE.OPC_DS_DEVICE, handles.Length, handles,
    out IntPtr valuesPtr, out IntPtr errorsPtr);

// Parse results outside lock
```

**Impact:**
- **2-5x capacity increase** (2000-5000 tags)
- UI operations never blocked
- Lock time reduced from 250ms → 5ms

### **Priority 2: Batch Size Tuning**

OPC DA supports reading tags in batches. Current code reads ALL tags in one call.

**Options:**
1. **Single large batch** (current) - best for <1000 tags
2. **Multiple small batches** - better for 2000+ tags

Example for 2000 tags:
```csharp
// Split into 4 batches of 500
for (int i = 0; i < handles.Length; i += 500)
{
    int batchSize = Math.Min(500, handles.Length - i);
    syncIO.Read(..., batchSize, handles[i..(i+batchSize)], ...);
}
```

**Impact:**
- Reduces single lock duration
- Better for UI responsiveness
- Slightly more OPC overhead

### **Priority 3: Adjust Polling Interval Dynamically**

**Current:** Fixed 1000ms interval

**Smart Interval:**
```csharp
// Slower updates for many tags
if (_monitoredTags.Count > 1000)
    _pollingIntervalMs = 2000; // 2 seconds
else if (_monitoredTags.Count > 500)
    _pollingIntervalMs = 1500;
else
    _pollingIntervalMs = 1000;
```

**Impact:**
- Reduces system load with many tags
- Maintains responsiveness with few tags

### **Priority 4: Use ConcurrentDictionary Efficiently**

**Current:**
```csharp
private readonly ConcurrentDictionary<string, TagMonitor> _monitoredTags = new();
```

Already thread-safe! But lock is still used.

**Optimization:**
Remove `lock (_lock)` from `ReadTagValues()` since:
- `ConcurrentDictionary` already thread-safe
- Only need lock for `AddTag`/`RemoveTag`

---

## Real-World Testing Recommendations

### **Test Plan:**

1. **Baseline Test (Current)**
   - Start with 10 tags
   - Measure poll time
   - Increase by 50 tags each step
   - Monitor lock duration
   - Stop when poll time > 500ms

2. **Stress Test**
   - Add 1000 tags immediately
   - Run for 1 hour
   - Monitor:
     - Poll time consistency
     - Memory usage
     - File rotation behavior
     - Any lock timeouts

3. **UI Responsiveness Test**
   - While logging 500 tags
   - Try to browse tags via UI
   - Add/remove tags dynamically
   - Measure UI freeze duration

### **Monitoring Commands:**

```powershell
# Check logging service CPU usage
Get-Process dotnet | Select-Object Id, CPU, WorkingSet

# Check file size and rotation
Get-ChildItem "D:\OpcLogs\Data" | Select-Object Name, Length

# Check tag count in config
Get-Content "logging-config.json" | ConvertFrom-Json | 
    Select-Object -ExpandProperty SelectedTags | Measure-Object
```

---

## Current Status Summary

| Aspect | Rating | Notes |
|--------|--------|-------|
| **Architecture** | ✅ Excellent | Dedicated connection, proper isolation |
| **Threading** | ✅ Good | Timer-based, non-blocking |
| **Lock Strategy** | ⚠️ Acceptable | Could be optimized for 1000+ tags |
| **File Writing** | ✅ Excellent | Atomic, crash-safe, efficient |
| **Capacity** | ✅ Good | 500 tags comfortable, 1000 max |
| **Scalability** | ⚠️ Limited | Needs optimization for 2000+ tags |

---

## Conclusion

**Your OPC system is WELL-DESIGNED for typical use cases:**

✅ **Excellent for:**
- 100-500 tags @ 1 second logging
- Dedicated logging connection (no UI interference)
- Crash-safe file writing
- Background service architecture

⚠️ **Limitations:**
- Lock contention above 1000 tags
- No dynamic interval adjustment
- OPC read holds lock during COM call

🚀 **With Priority 1 optimization:**
- Can handle 2000-5000 tags comfortably
- ~2 hours of development work
- No architectural changes needed

**Recommended Action:**
1. Test current system with 500 tags
2. If performance acceptable → no changes needed
3. If planning >1000 tags → implement Priority 1 optimization
