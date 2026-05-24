using System.Collections.Concurrent;
using Microsoft.Extensions.Logging;
using PlcGateway.Interfaces;

namespace PlcGateway.Services;

/// <summary>
/// Per-PLC Tag Value Pool
/// Each PLC has its own isolated pool for thread-safety and fault isolation
/// </summary>
public class PlcTagPool
{
    private readonly ConcurrentDictionary<string, PlcTagValue> _values = new();
    private readonly ILogger<PlcTagPool> _logger;
    
    public string PlcId { get; }
    public string PlcName { get; }
    public string PlantId { get; }
    public DateTime LastUpdate { get; private set; }
    public int TagCount => _values.Count;
    public bool IsStale => (DateTime.UtcNow - LastUpdate).TotalSeconds > 30;

    public PlcTagPool(string plcId, string plcName, string plantId, ILogger<PlcTagPool> logger)
    {
        PlcId = plcId;
        PlcName = plcName;
        PlantId = plantId;
        _logger = logger;
    }

    /// <summary>
    /// Update pool with batch read result
    /// Called after each successful PLC read cycle
    /// </summary>
    public void UpdateFromReadResult(PlcReadResult result)
    {
        if (!result.Success || result.Values.Count == 0)
        {
            _logger.LogWarning("[POOL] {PlcId}: Read failed or empty, pool not updated", PlcId);
            return;
        }

        var timestamp = DateTime.UtcNow;
        
        foreach (var value in result.Values)
        {
            // Key: just use address (unique within PLC)
            _values[value.Address] = value;
        }

        LastUpdate = timestamp;
        
        _logger.LogDebug("[POOL] {PlcId}: Updated {Count} tags at {Time:HH:mm:ss.fff}",
            PlcId, result.Values.Count, timestamp);
    }

    /// <summary>
    /// Get all values in this pool
    /// </summary>
    public List<PlcTagValue> GetAllValues()
    {
        return _values.Values.ToList();
    }

    /// <summary>
    /// Get specific tag value by address
    /// </summary>
    public PlcTagValue? GetValue(string address)
    {
        return _values.TryGetValue(address, out var value) ? value : null;
    }

    /// <summary>
    /// Get multiple values by addresses
    /// </summary>
    public List<PlcTagValue> GetValues(IEnumerable<string> addresses)
    {
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
    /// Clear pool (on disconnect or reconfigure)
    /// </summary>
    public void Clear()
    {
        _values.Clear();
        _logger.LogInformation("[POOL] {PlcId}: Pool cleared", PlcId);
    }

    /// <summary>
    /// Get pool health summary
    /// </summary>
    public PlcPoolHealth GetHealth()
    {
        return new PlcPoolHealth
        {
            PlcId = PlcId,
            PlcName = PlcName,
            PlantId = PlantId,
            TagCount = TagCount,
            LastUpdate = LastUpdate,
            IsStale = IsStale,
            StalenessSeconds = (DateTime.UtcNow - LastUpdate).TotalSeconds
        };
    }
}

/// <summary>
/// Pool health information
/// </summary>
public class PlcPoolHealth
{
    public string PlcId { get; set; } = "";
    public string PlcName { get; set; } = "";
    public string PlantId { get; set; } = "";
    public int TagCount { get; set; }
    public DateTime LastUpdate { get; set; }
    public bool IsStale { get; set; }
    public double StalenessSeconds { get; set; }
}

/// <summary>
/// Manages all PLC pools - one pool per PLC
/// </summary>
public class PlcPoolManager
{
    private readonly ConcurrentDictionary<string, PlcTagPool> _pools = new();
    private readonly ILoggerFactory _loggerFactory;
    private readonly ILogger<PlcPoolManager> _logger;

    public PlcPoolManager(ILoggerFactory loggerFactory, ILogger<PlcPoolManager> logger)
    {
        _loggerFactory = loggerFactory;
        _logger = logger;
    }

    /// <summary>
    /// Get or create pool for a PLC
    /// </summary>
    public PlcTagPool GetOrCreatePool(string plcId, string plcName, string plantId)
    {
        return _pools.GetOrAdd(plcId, _ =>
        {
            var pool = new PlcTagPool(plcId, plcName, plantId, 
                _loggerFactory.CreateLogger<PlcTagPool>());
            _logger.LogInformation("[POOL MANAGER] Created pool for {PlcId}", plcId);
            return pool;
        });
    }

    /// <summary>
    /// Get pool by PLC ID
    /// </summary>
    public PlcTagPool? GetPool(string plcId)
    {
        return _pools.TryGetValue(plcId, out var pool) ? pool : null;
    }

    /// <summary>
    /// Get all pools
    /// </summary>
    public List<PlcTagPool> GetAllPools()
    {
        return _pools.Values.ToList();
    }

    /// <summary>
    /// Get all values from all pools (unified view)
    /// </summary>
    public List<PlcTagValue> GetAllValues()
    {
        var allValues = new List<PlcTagValue>();
        foreach (var pool in _pools.Values)
        {
            allValues.AddRange(pool.GetAllValues());
        }
        return allValues;
    }

    /// <summary>
    /// Get values from specific plant (may have multiple PLCs)
    /// </summary>
    public List<PlcTagValue> GetValuesByPlant(string plantId)
    {
        var values = new List<PlcTagValue>();
        foreach (var pool in _pools.Values.Where(p => p.PlantId == plantId))
        {
            values.AddRange(pool.GetAllValues());
        }
        return values;
    }

    /// <summary>
    /// Get values from specific PLC
    /// </summary>
    public List<PlcTagValue> GetValuesByPlc(string plcId)
    {
        return _pools.TryGetValue(plcId, out var pool) 
            ? pool.GetAllValues() 
            : new List<PlcTagValue>();
    }

    /// <summary>
    /// Get health of all pools
    /// </summary>
    public List<PlcPoolHealth> GetAllPoolsHealth()
    {
        return _pools.Values.Select(p => p.GetHealth()).ToList();
    }

    /// <summary>
    /// Remove pool (when PLC is disabled)
    /// </summary>
    public void RemovePool(string plcId)
    {
        if (_pools.TryRemove(plcId, out var pool))
        {
            pool.Clear();
            _logger.LogInformation("[POOL MANAGER] Removed pool for {PlcId}", plcId);
        }
    }
}
