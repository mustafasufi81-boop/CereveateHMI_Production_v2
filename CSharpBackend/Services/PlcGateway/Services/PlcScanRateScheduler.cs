using System.Collections.Concurrent;
using Microsoft.Extensions.Logging;
using PlcGateway.Interfaces;

namespace PlcGateway.Services;

/// <summary>
/// PLC Scan Rate Scheduler - Per-Tag Scan Rate with Deadband Control
/// 
/// LOGIC:
/// 1. Each tag has its own SCAN RATE (e.g., 100ms, 200ms, 500ms)
/// 2. Each tag can have DEADBAND (0 = no deadband, cache ALL values at scan rate)
/// 3. If deadband defined: Only cache value when |new - old| > deadband
/// 4. If NO deadband: Cache ALL values at scan rate
/// 5. Transmission: Send ALL buffered values via MQTT/API at configured interval (e.g., 1 second)
/// 
/// ARCHITECTURE:
/// - _tagSchedules: Tracks next scan time for each tag
/// - _lastValues: Tracks last value for deadband comparison
/// - _valueBuffer: Accumulated values for transmission (cleared after send)
/// 
/// BUFFER CONTROL STRATEGY:
/// - Hard cap on buffer size (default 10,000 samples)
/// - When cap exceeded: Drop oldest samples (FIFO)
/// - Track dropped samples for diagnostics
/// - Adaptive throttling: Skip caching if buffer growing too fast
/// </summary>
public class PlcScanRateScheduler
{
    private readonly ILogger _logger;
    private readonly ScanSchedulerConfig _config;
    
    // Per-tag scheduling state
    private readonly ConcurrentDictionary<string, TagScheduleState> _tagSchedules = new();
    
    // Buffered values for transmission (accumulated between transmit cycles)
    private readonly ConcurrentQueue<BufferedTagValue> _valueBuffer = new();
    
    // BUFFER CONTROL: Hard limits to prevent memory growth
    private const int DEFAULT_MAX_BUFFER_SIZE = 10000;  // Max samples in buffer
    private const int BUFFER_TRIM_THRESHOLD = 8000;     // Start trimming at 80%
    private const int BUFFER_TRIM_TARGET = 5000;        // Trim down to 50%
    private long _totalDropped;                          // Samples dropped due to overflow
    private DateTime _lastTrimTime = DateTime.MinValue;
    
    // Statistics
    private long _totalScans;
    private long _totalCached;
    private long _totalFiltered;
    private long _totalTransmitted;
    private DateTime _lastTransmitTime = DateTime.MinValue;

    public PlcScanRateScheduler(ILogger logger, ScanSchedulerConfig? config = null)
    {
        _logger = logger;
        _config = config ?? new ScanSchedulerConfig();
    }

    /// <summary>
    /// Initialize scheduler with tag definitions
    /// </summary>
    public void Initialize(IEnumerable<PlcTagDefinition> tags)
    {
        foreach (var tag in tags.Where(t => t.Enabled))
        {
            var key = tag.Address;
            _tagSchedules[key] = new TagScheduleState
            {
                Address = tag.Address,
                TagName = tag.TagName,
                ScanRateMs = tag.ScanRateMs > 0 ? tag.ScanRateMs : _config.DefaultScanRateMs,
                DeadbandValue = tag.DeadbandValue,
                HasDeadband = tag.DeadbandValue > 0,
                NextScanTime = DateTime.UtcNow,
                LastValue = null,
                LastScanTime = DateTime.MinValue
            };
        }

        _logger.LogInformation(
            "[SCAN SCHEDULER] Initialized with {Count} tags, scan rates: {Rates}",
            _tagSchedules.Count,
            string.Join(", ", _tagSchedules.Values
                .GroupBy(t => t.ScanRateMs)
                .Select(g => $"{g.Count()}@{g.Key}ms")));
    }

    /// <summary>
    /// Get tags that are DUE for scanning (based on their individual scan rates)
    /// </summary>
    public List<string> GetTagsDueForScan()
    {
        var now = DateTime.UtcNow;
        var dueTags = new List<string>();

        foreach (var kvp in _tagSchedules)
        {
            if (now >= kvp.Value.NextScanTime)
            {
                dueTags.Add(kvp.Key);
            }
        }

        return dueTags;
    }

    /// <summary>
    /// Get the scan rate for a specific tag
    /// </summary>
    public int GetTagScanRate(string address)
    {
        if (_tagSchedules.TryGetValue(address, out var schedule))
            return schedule.ScanRateMs;
        return _config.DefaultScanRateMs;
    }

    /// <summary>
    /// Get the minimum time until next scan is due (for optimal sleep calculation)
    /// </summary>
    public int GetMinimumScanIntervalMs()
    {
        if (_tagSchedules.IsEmpty) return _config.DefaultScanRateMs;
        return _tagSchedules.Values.Min(t => t.ScanRateMs);
    }

    /// <summary>
    /// Get milliseconds until the next tag is due for scanning.
    /// This allows precise timing without drift from PLC read latency.
    /// </summary>
    public int GetMsUntilNextTagDue()
    {
        if (_tagSchedules.IsEmpty) return _config.DefaultScanRateMs;
        
        var now = DateTime.UtcNow;
        int? minMs = null;
        
        foreach (var schedule in _tagSchedules.Values)
        {
            var msUntilDue = (int)(schedule.NextScanTime - now).TotalMilliseconds;
            if (!minMs.HasValue || msUntilDue < minMs.Value)
            {
                minMs = msUntilDue;
            }
        }
        
        // If no tags found, use default scan rate
        if (!minMs.HasValue) return _config.DefaultScanRateMs;
        
        // If already past due (negative), return 1ms to process immediately
        // Otherwise return the actual time until next due (min 1ms to prevent busy loop)
        return Math.Max(1, minMs.Value);
    }

    /// <summary>
    /// Process scanned values - apply deadband, buffer for transmission
    /// </summary>
    public void ProcessScannedValues(IEnumerable<PlcTagValue> values)
    {
        var now = DateTime.UtcNow;

        foreach (var value in values)
        {
            if (!_tagSchedules.TryGetValue(value.Address, out var schedule))
                continue;

            _totalScans++;

            // Update schedule for next scan
            schedule.LastScanTime = now;
            schedule.NextScanTime = now.AddMilliseconds(schedule.ScanRateMs);

            // Apply deadband logic
            bool shouldCache;

            if (!schedule.HasDeadband)
            {
                // NO DEADBAND: Cache ALL values at scan rate
                shouldCache = true;
            }
            else
            {
                // HAS DEADBAND: Only cache if value changed beyond threshold
                shouldCache = ShouldCacheWithDeadband(value, schedule);
            }

            // BUFFER CONTROL: Skip caching if buffer is at hard limit
            if (shouldCache && _valueBuffer.Count >= DEFAULT_MAX_BUFFER_SIZE)
            {
                shouldCache = false;
                _totalDropped++;
                _totalFiltered++;
                
                _logger.LogTrace(
                    "[SCAN] Buffer FULL ({Count}/{Max}) - skipping {Tag}",
                    _valueBuffer.Count, DEFAULT_MAX_BUFFER_SIZE, value.Address);
            }

            if (shouldCache)
            {
                // Update last value for deadband comparison
                schedule.LastValue = value.Value;
                schedule.LastCachedTime = now;

                // Add to transmission buffer
                _valueBuffer.Enqueue(new BufferedTagValue
                {
                    PlcId = value.PlcId,
                    Address = value.Address,
                    TagName = value.TagName,
                    Value = value.Value,
                    DataType = value.DataType,
                    Quality = value.Quality,
                    Timestamp = value.Timestamp,
                    BufferedAt = now,
                    ScanRateMs = schedule.ScanRateMs,
                    DeadbandApplied = schedule.HasDeadband
                });

                _totalCached++;
                
                _logger.LogTrace(
                    "[SCAN] Cached {Tag} = {Value} (deadband={HasDb}, rate={Rate}ms)",
                    value.Address, value.Value, schedule.HasDeadband, schedule.ScanRateMs);
            }
            else
            {
                _totalFiltered++;
                
                _logger.LogTrace(
                    "[SCAN] Filtered {Tag} (deadband not exceeded)",
                    value.Address);
            }
        }
    }

    /// <summary>
    /// Check if value should be cached based on deadband
    /// </summary>
    private bool ShouldCacheWithDeadband(PlcTagValue value, TagScheduleState schedule)
    {
        // First value always cached
        if (schedule.LastValue == null)
            return true;

        // Non-numeric values: compare directly
        if (value.Value is bool newBool && schedule.LastValue is bool oldBool)
            return newBool != oldBool;

        if (value.Value is string newStr && schedule.LastValue is string oldStr)
            return newStr != oldStr;

        // Numeric values: check deadband
        if (TryGetNumericValue(value.Value, out var newNumeric) &&
            TryGetNumericValue(schedule.LastValue, out var oldNumeric))
        {
            var change = Math.Abs(newNumeric - oldNumeric);
            return change > schedule.DeadbandValue;
        }

        // Unknown type: always cache
        return true;
    }

    private bool TryGetNumericValue(object? value, out double result)
    {
        result = 0;
        if (value == null) return false;

        return value switch
        {
            double d => (result = d) == d,
            float f => (result = f) == f,
            int i => (result = i) == i,
            long l => (result = l) == l,
            short s => (result = s) == s,
            byte b => (result = b) == b,
            decimal dec => (result = (double)dec) == (double)dec,
            _ => double.TryParse(value.ToString(), out result)
        };
    }

    /// <summary>
    /// Get ALL buffered values for transmission (clears buffer)
    /// Call this at transmission interval (e.g., every 1 second)
    /// </summary>
    public List<BufferedTagValue> GetBufferedValuesForTransmission()
    {
        var values = new List<BufferedTagValue>();

        while (_valueBuffer.TryDequeue(out var value))
        {
            values.Add(value);
        }

        if (values.Count > 0)
        {
            _totalTransmitted += values.Count;
            _lastTransmitTime = DateTime.UtcNow;

            _logger.LogDebug(
                "[SCAN] Transmitting {Count} buffered values (total transmitted: {Total})",
                values.Count, _totalTransmitted);
        }

        return values;
    }

    /// <summary>
    /// Get buffered values GROUPED BY TAG (multiple samples per tag)
    /// For 200ms scan rate with 1000ms publish = 5 samples per tag
    /// Call this at transmission interval (e.g., every 1 second)
    /// </summary>
    public Dictionary<string, TagSampleBatch> GetBufferedValuesGroupedByTag()
    {
        var allValues = new List<BufferedTagValue>();
        while (_valueBuffer.TryDequeue(out var value))
        {
            allValues.Add(value);
        }

        if (allValues.Count == 0)
            return new Dictionary<string, TagSampleBatch>();

        _totalTransmitted += allValues.Count;
        _lastTransmitTime = DateTime.UtcNow;

        // Group by tag address - each tag gets ALL its samples
        var grouped = allValues
            .GroupBy(v => v.Address)
            .ToDictionary(
                g => g.Key,
                g => new TagSampleBatch
                {
                    PlcId = g.First().PlcId,
                    Address = g.Key,
                    TagName = g.First().TagName,
                    DataType = g.First().DataType,
                    ScanRateMs = g.First().ScanRateMs,
                    Samples = g.OrderBy(v => v.Timestamp)
                               .Select(v => new TagSample
                               {
                                   Value = v.Value,
                                   Quality = v.Quality,
                                   Timestamp = v.Timestamp
                               }).ToList()
                });

        _logger.LogInformation(
            "[SCAN] Transmitting {TagCount} tags with {TotalSamples} total samples (avg {Avg:F1} samples/tag)",
            grouped.Count, allValues.Count, 
            grouped.Count > 0 ? (double)allValues.Count / grouped.Count : 0);

        return grouped;
    }

    /// <summary>
    /// Get current statistics
    /// </summary>
    public ScanSchedulerStats GetStats()
    {
        // BUFFER CONTROL: Periodically trim buffer if above threshold
        TrimBufferIfNeeded();
        
        return new ScanSchedulerStats
        {
            TotalTags = _tagSchedules.Count,
            TotalScans = _totalScans,
            TotalCached = _totalCached,
            TotalFiltered = _totalFiltered,
            TotalTransmitted = _totalTransmitted,
            TotalDropped = _totalDropped,
            BufferedCount = _valueBuffer.Count,
            MaxBufferSize = DEFAULT_MAX_BUFFER_SIZE,
            BufferUtilizationPercent = _valueBuffer.Count * 100.0 / DEFAULT_MAX_BUFFER_SIZE,
            LastTransmitTime = _lastTransmitTime,
            TagsByRate = _tagSchedules.Values
                .GroupBy(t => t.ScanRateMs)
                .ToDictionary(g => g.Key, g => g.Count()),
            TagsWithDeadband = _tagSchedules.Values.Count(t => t.HasDeadband),
            TagsWithoutDeadband = _tagSchedules.Values.Count(t => !t.HasDeadband)
        };
    }
    
    /// <summary>
    /// BUFFER CONTROL: Clear buffer completely (call when samples consumed by MQTT/DB)
    /// This is the KEY method that must be called to prevent buffer growth!
    /// </summary>
    public int ClearBuffer()
    {
        var count = 0;
        while (_valueBuffer.TryDequeue(out _))
        {
            count++;
        }
        
        if (count > 0)
        {
            _logger.LogInformation(
                "[SCAN] Buffer CLEARED: {Count} samples removed",
                count);
        }
        
        return count;
    }
    
    /// <summary>
    /// BUFFER CONTROL: Trim buffer when it exceeds threshold
    /// Removes oldest samples (FIFO) to bring buffer back to target size
    /// </summary>
    private void TrimBufferIfNeeded()
    {
        var bufferSize = _valueBuffer.Count;
        
        // Only trim every 5 seconds max (avoid excessive CPU usage)
        if ((DateTime.UtcNow - _lastTrimTime).TotalSeconds < 5)
            return;
            
        if (bufferSize > BUFFER_TRIM_THRESHOLD)
        {
            var toRemove = bufferSize - BUFFER_TRIM_TARGET;
            var removed = 0;
            
            while (removed < toRemove && _valueBuffer.TryDequeue(out _))
            {
                removed++;
            }
            
            _totalDropped += removed;
            _lastTrimTime = DateTime.UtcNow;
            
            _logger.LogWarning(
                "[SCAN] Buffer TRIMMED: {Removed} oldest samples dropped (was {Before}, now {After}, target {Target})",
                removed, bufferSize, _valueBuffer.Count, BUFFER_TRIM_TARGET);
        }
    }
}

/// <summary>
/// Configuration for scan rate scheduler (loaded from appsettings.json PlcGateway section)
/// </summary>
public class ScanSchedulerConfig
{
    /// <summary>
    /// Default scan rate if not specified per-tag (from PlcGateway:DefaultScanRateMs)
    /// </summary>
    public int DefaultScanRateMs { get; set; } = 1000;
    
    /// <summary>
    /// Transmission interval for buffered values (from PlcGateway:DefaultTransmissionIntervalMs)
    /// </summary>
    public int TransmissionIntervalMs { get; set; } = 1000;
}

/// <summary>
/// Per-tag scheduling state
/// </summary>
public class TagScheduleState
{
    public string Address { get; set; } = "";
    public string TagName { get; set; } = "";
    public int ScanRateMs { get; set; }  // Loaded from database, no hardcoded default
    public double DeadbandValue { get; set; }
    public bool HasDeadband { get; set; }
    public DateTime NextScanTime { get; set; }
    public DateTime LastScanTime { get; set; }
    public DateTime LastCachedTime { get; set; }
    public object? LastValue { get; set; }
}

/// <summary>
/// Buffered tag value ready for transmission
/// </summary>
public class BufferedTagValue
{
    public string PlcId { get; set; } = "";
    public string Address { get; set; } = "";
    public string TagName { get; set; } = "";
    public object? Value { get; set; }
    public string DataType { get; set; } = "";
    public PlcQuality Quality { get; set; }
    public DateTime Timestamp { get; set; }       // When read from PLC
    public DateTime BufferedAt { get; set; }      // When added to buffer
    public int ScanRateMs { get; set; }
    public bool DeadbandApplied { get; set; }
}

/// <summary>
/// Scheduler statistics
/// </summary>
public class ScanSchedulerStats
{
    public int TotalTags { get; set; }
    public long TotalScans { get; set; }
    public long TotalCached { get; set; }
    public long TotalFiltered { get; set; }
    public long TotalTransmitted { get; set; }
    public long TotalDropped { get; set; }         // NEW: Samples dropped due to buffer overflow
    public int BufferedCount { get; set; }
    public int MaxBufferSize { get; set; }          // NEW: Hard cap on buffer
    public double BufferUtilizationPercent { get; set; } // NEW: Buffer fullness %
    public DateTime LastTransmitTime { get; set; }
    public Dictionary<int, int> TagsByRate { get; set; } = new();
    public int TagsWithDeadband { get; set; }
    public int TagsWithoutDeadband { get; set; }
}

/// <summary>
/// Batch of samples for a single tag (multiple readings at scan rate)
/// E.g., 200ms scan rate = 5 samples per 1000ms publish interval
/// </summary>
public class TagSampleBatch
{
    public string PlcId { get; set; } = "";
    public string Address { get; set; } = "";
    public string TagName { get; set; } = "";
    public string DataType { get; set; } = "";
    public int ScanRateMs { get; set; }
    public List<TagSample> Samples { get; set; } = new();
}

/// <summary>
/// Single sample within a batch
/// </summary>
public class TagSample
{
    public object? Value { get; set; }
    public PlcQuality Quality { get; set; }
    public DateTime Timestamp { get; set; }
}
