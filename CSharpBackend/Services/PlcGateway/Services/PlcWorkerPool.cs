using System.Collections.Concurrent;
using PlcGateway.Interfaces;

namespace PlcGateway.Services;

/// <summary>
/// ISOLATED Worker Pool - Each PLC worker has its own pool
/// 
/// DESIGN:
/// - NO shared state with other pools
/// - Thread-safe for concurrent read/write
/// - Lock-free reads using ConcurrentDictionary
/// - Atomic updates
/// </summary>
public sealed class PlcWorkerPool
{
    private readonly ConcurrentDictionary<string, PlcTagValue> _values = new();
    private readonly object _updateLock = new();
    
    public string PlcId { get; }
    public string PlcName { get; }
    public int TagCount => _values.Count;
    public DateTime LastUpdateTime { get; private set; }
    public long LastReadDurationMs { get; private set; }
    public bool IsStale { get; private set; }

    // Staleness threshold (30 seconds)
    private const int StaleThresholdSeconds = 30;

    public PlcWorkerPool(string plcId, string plcName)
    {
        PlcId = plcId;
        PlcName = plcName;
    }

    /// <summary>
    /// Update pool with new values (atomic operation)
    /// </summary>
    public void Update(List<PlcTagValue> values, long readDurationMs)
    {
        if (values == null || values.Count == 0) return;

        var timestamp = DateTime.UtcNow;

        // Update each value
        foreach (var value in values)
        {
            _values[value.Address] = value;
        }

        // Update metadata atomically
        lock (_updateLock)
        {
            LastUpdateTime = timestamp;
            LastReadDurationMs = readDurationMs;
            IsStale = false;
        }
    }

    /// <summary>
    /// Get all values (lock-free read)
    /// </summary>
    public List<PlcTagValue> GetAllValues()
    {
        // Check staleness
        CheckStaleness();
        
        return _values.Values.ToList();
    }

    /// <summary>
    /// Get specific value by address
    /// </summary>
    public PlcTagValue? GetValue(string address)
    {
        CheckStaleness();
        return _values.TryGetValue(address, out var value) ? value : null;
    }

    /// <summary>
    /// Get multiple values by addresses
    /// </summary>
    public List<PlcTagValue> GetValues(IEnumerable<string> addresses)
    {
        CheckStaleness();
        var results = new List<PlcTagValue>();
        
        foreach (var addr in addresses)
        {
            if (_values.TryGetValue(addr, out var value))
            {
                results.Add(value);
            }
        }
        
        return results;
    }

    /// <summary>
    /// Mark pool as stale (on failure)
    /// </summary>
    public void MarkStale()
    {
        lock (_updateLock)
        {
            IsStale = true;
        }

        // Update quality of all values
        foreach (var kvp in _values)
        {
            var value = kvp.Value;
            if (value.Quality == PlcQuality.Good)
            {
                _values[kvp.Key] = value with { Quality = PlcQuality.Uncertain };
            }
        }
    }

    /// <summary>
    /// Clear all values
    /// </summary>
    public void Clear()
    {
        _values.Clear();
        lock (_updateLock)
        {
            LastUpdateTime = default;
            IsStale = true;
        }
    }

    private void CheckStaleness()
    {
        var timeSinceUpdate = (DateTime.UtcNow - LastUpdateTime).TotalSeconds;
        if (timeSinceUpdate > StaleThresholdSeconds && !IsStale)
        {
            MarkStale();
        }
    }
}
