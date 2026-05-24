using System.Collections.Concurrent;
using Microsoft.Extensions.Logging;

namespace PlcGateway.Services;

/// <summary>
/// PLC Sample Buffer Service - Accumulates multiple samples per tag between publish intervals
/// 
/// DESIGN:
/// - PlcWorker scans at tag's scan rate (e.g., 200ms from database)
/// - Each scan adds a sample to the buffer
/// - Publisher reads and clears buffer at publish interval (e.g., 1000ms)
/// - Result: 5 samples per tag when 200ms scan / 1000ms publish
/// 
/// DYNAMIC BEHAVIOR:
/// - If scan rate = publish interval → 1 sample per tag (like before)
/// - If scan rate < publish interval → multiple samples per tag
/// - No hardcoded values - all from config/database
/// </summary>
public class PlcSampleBufferService
{
    private readonly ILogger<PlcSampleBufferService> _logger;
    
    // Buffer: PlcId::Address → List of samples since last publish
    private readonly ConcurrentDictionary<string, ConcurrentQueue<TagSampleEntry>> _sampleBuffer;
    
    // Latest value cache (for API/HMI that want just current value)
    private readonly ConcurrentDictionary<string, TagSampleEntry> _latestValues;
    
    // BUFFER CONTROL: Hard limits to prevent memory growth
    private const int MAX_SAMPLES_PER_TAG = 100;   // Max samples per tag queue
    private const int MAX_TOTAL_SAMPLES = 50000;   // Max total samples in buffer
    private long _totalSamplesDropped;              // Samples dropped due to overflow
    
    // Statistics
    private long _totalSamplesBuffered;
    private long _totalSamplesPublished;
    private DateTime _lastPublishTime = DateTime.MinValue;
    private readonly object _statsLock = new();

    public PlcSampleBufferService(ILogger<PlcSampleBufferService> logger)
    {
        _logger = logger;
        _sampleBuffer = new ConcurrentDictionary<string, ConcurrentQueue<TagSampleEntry>>();
        _latestValues = new ConcurrentDictionary<string, TagSampleEntry>();
    }
    
    /// <summary>
    /// Get current total sample count across all tag queues
    /// </summary>
    private int GetTotalSampleCount()
    {
        return _sampleBuffer.Values.Sum(q => q.Count);
    }

    /// <summary>
    /// Add a sample to the buffer (called by PlcWorker on each scan)
    /// </summary>
    public void AddSample(string plcId, string address, string tagName, object? value, 
                          string dataType, string quality, DateTime timestamp, int scanRateMs)
    {
        var key = $"{plcId}::{address}";
        
        var sample = new TagSampleEntry
        {
            PlcId = plcId,
            Address = address,
            TagName = tagName,
            Value = value,
            DataType = dataType,
            Quality = quality,
            Timestamp = timestamp,
            ScanRateMs = scanRateMs,
            BufferedAt = DateTime.UtcNow
        };

        // Add to buffer queue
        var queue = _sampleBuffer.GetOrAdd(key, _ => new ConcurrentQueue<TagSampleEntry>());
        
        // BUFFER CONTROL: Limit samples per tag
        if (queue.Count >= MAX_SAMPLES_PER_TAG)
        {
            // Drop oldest sample (FIFO)
            queue.TryDequeue(out _);
            lock (_statsLock) { _totalSamplesDropped++; }
        }
        
        queue.Enqueue(sample);

        // Update latest value
        _latestValues[key] = sample;

        lock (_statsLock)
        {
            _totalSamplesBuffered++;
        }
    }

    /// <summary>
    /// Add multiple samples at once (batch from PlcWorker)
    /// WITH BUFFER CONTROL: Limits samples per tag to prevent memory growth
    /// </summary>
    public void AddSamples(IEnumerable<TagSampleEntry> samples)
    {
        var sampleList = samples.ToList();
        var droppedCount = 0;
        
        foreach (var sample in sampleList)
        {
            var key = $"{sample.PlcId}::{sample.Address}";
            
            var queue = _sampleBuffer.GetOrAdd(key, _ => new ConcurrentQueue<TagSampleEntry>());
            
            // BUFFER CONTROL: Limit samples per tag (drop oldest if full)
            while (queue.Count >= MAX_SAMPLES_PER_TAG)
            {
                queue.TryDequeue(out _);
                droppedCount++;
            }
            
            queue.Enqueue(sample);
            _latestValues[key] = sample;
        }

        lock (_statsLock)
        {
            _totalSamplesBuffered += sampleList.Count;
            _totalSamplesDropped += droppedCount;
        }
        
        // Log if samples were dropped
        if (droppedCount > 0)
        {
            _logger.LogWarning(
                "[SAMPLE BUFFER] Dropped {Dropped} oldest samples (limit: {Limit}/tag)",
                droppedCount, MAX_SAMPLES_PER_TAG);
        }
    }

    /// <summary>
    /// Get all buffered samples grouped by tag, then clear buffer
    /// Called by publisher at publish interval
    /// Returns: Dictionary[PlcId::Address] → TagWithSamples (contains array of all samples)
    /// </summary>
    public Dictionary<string, TagWithSamples> GetAndClearBuffer()
    {
        var result = new Dictionary<string, TagWithSamples>();
        var totalSamples = 0;

        foreach (var kvp in _sampleBuffer)
        {
            var key = kvp.Key;
            var queue = kvp.Value;
            
            if (queue.IsEmpty) continue;

            var samples = new List<SampleValue>();
            while (queue.TryDequeue(out var sample))
            {
                samples.Add(new SampleValue
                {
                    Value = sample.Value,
                    Quality = sample.Quality,
                    Timestamp = sample.Timestamp
                });
                totalSamples++;
            }

            if (samples.Count > 0)
            {
                // Get metadata from latest value
                if (_latestValues.TryGetValue(key, out var latest))
                {
                    result[key] = new TagWithSamples
                    {
                        PlcId = latest.PlcId,
                        Address = latest.Address,
                        TagName = latest.TagName,
                        DataType = latest.DataType,
                        ScanRateMs = latest.ScanRateMs,
                        SampleCount = samples.Count,
                        Samples = samples
                    };
                }
            }
        }

        lock (_statsLock)
        {
            _totalSamplesPublished += totalSamples;
            _lastPublishTime = DateTime.UtcNow;
        }

        if (result.Count > 0)
        {
            _logger.LogDebug(
                "[SAMPLE BUFFER] Published {TagCount} tags with {SampleCount} total samples (avg {Avg:F1}/tag)",
                result.Count, totalSamples, 
                result.Count > 0 ? (double)totalSamples / result.Count : 0);
        }

        return result;
    }

    /// <summary>
    /// Get latest values only (for API/HMI that want just current value)
    /// Does NOT clear buffer
    /// </summary>
    public List<TagSampleEntry> GetLatestValues()
    {
        return _latestValues.Values.ToList();
    }

    /// <summary>
    /// Get statistics
    /// </summary>
    public SampleBufferStats GetStats()
    {
        var bufferedCount = _sampleBuffer.Values.Sum(q => q.Count);
        
        return new SampleBufferStats
        {
            TotalTags = _latestValues.Count,
            BufferedSamples = bufferedCount,
            MaxSamplesPerTag = MAX_SAMPLES_PER_TAG,
            MaxTotalSamples = MAX_TOTAL_SAMPLES,
            BufferUtilizationPercent = bufferedCount * 100.0 / MAX_TOTAL_SAMPLES,
            TotalSamplesBuffered = _totalSamplesBuffered,
            TotalSamplesPublished = _totalSamplesPublished,
            TotalSamplesDropped = _totalSamplesDropped,
            LastPublishTime = _lastPublishTime
        };
    }
}

/// <summary>
/// Single sample entry in the buffer
/// </summary>
public record TagSampleEntry
{
    public string PlcId { get; init; } = "";
    public string Address { get; init; } = "";
    public string TagName { get; init; } = "";
    public object? Value { get; init; }
    public string DataType { get; init; } = "";
    public string Quality { get; init; } = "Good";
    public DateTime Timestamp { get; init; }
    public int ScanRateMs { get; init; }
    public DateTime BufferedAt { get; init; }
}

/// <summary>
/// Tag with all its accumulated samples (for MQTT publish)
/// </summary>
public class TagWithSamples
{
    public string PlcId { get; set; } = "";
    public string Address { get; set; } = "";
    public string TagName { get; set; } = "";
    public string DataType { get; set; } = "";
    public int ScanRateMs { get; set; }
    public int SampleCount { get; set; }
    public List<SampleValue> Samples { get; set; } = new();
}

/// <summary>
/// Single sample value within a tag's sample array
/// </summary>
public class SampleValue
{
    public object? Value { get; set; }
    public string Quality { get; set; } = "Good";
    public DateTime Timestamp { get; set; }
}

/// <summary>
/// Buffer statistics
/// </summary>
public class SampleBufferStats
{
    public int TotalTags { get; set; }
    public int BufferedSamples { get; set; }
    public int MaxSamplesPerTag { get; set; }       // NEW: Hard limit per tag
    public int MaxTotalSamples { get; set; }        // NEW: Total hard limit
    public double BufferUtilizationPercent { get; set; } // NEW: Fullness %
    public long TotalSamplesBuffered { get; set; }
    public long TotalSamplesPublished { get; set; }
    public long TotalSamplesDropped { get; set; }   // NEW: Dropped due to overflow
    public DateTime LastPublishTime { get; set; }
}
