using System.Collections.Concurrent;
using Microsoft.Extensions.Logging;

namespace PlcGateway.Services;

/// <summary>
/// PLC Tag Values Pool Service - UNIFIED SHARED CACHE
/// 
/// DESIGN (Mirrors OPC TagValuesPoolService):
/// - Updated by PlcDataLoggingService every 1000ms
/// - Read by: API, Frontend, Historian, Parquet Logger
/// - Thread-safe using ConcurrentDictionary
/// - Lock-free reads for high performance
/// 
/// CONSUMERS:
/// 1. API Controller (/api/plc/values) - returns all/filtered values
/// 2. Frontend polling (1 second) - real-time display
/// 3. PlcHistorianIngestService - writes mapped tags to PostgreSQL
/// 4. PlcParquetLoggingService - writes selected tags to parquet files
/// </summary>
public class PlcTagValuesPoolService
{
    private readonly ILogger<PlcTagValuesPoolService> _logger;
    private readonly ConcurrentDictionary<string, PlcTagValueCacheEntry> _cache;
    private readonly ConcurrentDictionary<string, PlcPoolConnectionStatus> _connectionStatus;
    private DateTime _lastUpdateTimestamp = DateTime.MinValue;
    private readonly object _updateLock = new();
    private int _totalUpdates;
    private long _totalTagsProcessed;

    public PlcTagValuesPoolService(ILogger<PlcTagValuesPoolService> logger)
    {
        _logger = logger;
        _cache = new ConcurrentDictionary<string, PlcTagValueCacheEntry>(StringComparer.OrdinalIgnoreCase);
        _connectionStatus = new ConcurrentDictionary<string, PlcPoolConnectionStatus>(StringComparer.OrdinalIgnoreCase);
    }

    // ═══════════════════════════════════════════════════════════════════
    // UPDATE METHODS (Called by PlcDataLoggingService)
    // ═══════════════════════════════════════════════════════════════════

    /// <summary>
    /// Update cache with values from a single PLC
    /// Called by PlcDataLoggingService on each poll cycle
    /// </summary>
    public void UpdateFromPlc(string plcId, List<PlcTagValueCacheEntry> tagValues, DateTime timestamp)
    {
        if (tagValues == null || tagValues.Count == 0) return;

        var updateCount = 0;

        foreach (var tagValue in tagValues)
        {
            // Key format: "PlcId::Address" for uniqueness across PLCs
            var cacheKey = $"{plcId}::{tagValue.Address}";
            
            _cache[cacheKey] = tagValue with 
            { 
                PlcId = plcId,
                CacheKey = cacheKey,
                CachedAt = DateTime.UtcNow 
            };
            updateCount++;
        }

        // Update connection status - preserve total tag count across batches
        var totalTagsForPlc = _cache.Values.Count(v => v.PlcId == plcId);
        _connectionStatus[plcId] = new PlcPoolConnectionStatus
        {
            PlcId = plcId,
            IsConnected = true,
            LastUpdateTime = timestamp,
            TagCount = totalTagsForPlc, // Use TOTAL tags in cache for this PLC, not batch size
            LastError = null
        };

        lock (_updateLock)
        {
            _lastUpdateTimestamp = timestamp;
            _totalUpdates++;
            _totalTagsProcessed += updateCount;
        }

        _logger.LogDebug("[PLC POOL] Updated {Count} tags from {PlcId} at {Time:HH:mm:ss.fff}",
            updateCount, plcId, timestamp);
    }

    /// <summary>
    /// Mark PLC as disconnected/failed
    /// </summary>
    public void MarkPlcDisconnected(string plcId, string? error = null)
    {
        _connectionStatus[plcId] = new PlcPoolConnectionStatus
        {
            PlcId = plcId,
            IsConnected = false,
            LastUpdateTime = DateTime.UtcNow,
            LastError = error
        };

        // Mark all tags from this PLC as stale
        foreach (var kvp in _cache.Where(c => c.Value.PlcId == plcId))
        {
            _cache[kvp.Key] = kvp.Value with { Quality = PlcTagQuality.Uncertain };
        }

        _logger.LogWarning("[PLC POOL] Marked {PlcId} as disconnected: {Error}", plcId, error ?? "Unknown");
    }

    // ═══════════════════════════════════════════════════════════════════
    // READ METHODS (Called by API, Historian, Parquet)
    // ═══════════════════════════════════════════════════════════════════

    /// <summary>
    /// Get ALL cached tag values (for API /api/plc/values)
    /// </summary>
    public List<PlcTagValueCacheEntry> GetAllTagValues()
    {
        return _cache.Values.ToList();
    }

    /// <summary>
    /// Get tag values for specific PLC
    /// </summary>
    public List<PlcTagValueCacheEntry> GetPlcTagValues(string plcId)
    {
        return _cache.Values.Where(v => v.PlcId == plcId).ToList();
    }

    /// <summary>
    /// Get tag values for specific PLC (alias for API compatibility)
    /// </summary>
    public List<PlcTagValueCacheEntry> GetPlcValues(string plcId)
    {
        return GetPlcTagValues(plcId);
    }

    /// <summary>
    /// Get tag values for specific tags (by cache key or address)
    /// Used by Historian to get only mapped tags
    /// </summary>
    public List<PlcTagValueCacheEntry> GetTagValues(IEnumerable<string> cacheKeys)
    {
        var results = new List<PlcTagValueCacheEntry>();

        foreach (var key in cacheKeys)
        {
            if (_cache.TryGetValue(key, out var entry))
            {
                results.Add(entry);
            }
        }

        return results;
    }

    /// <summary>
    /// Get tag values by tag names and optional PLC filter (API query method)
    /// </summary>
    public List<PlcTagValueCacheEntry> GetTagValues(IEnumerable<string> tagNamesOrAddresses, string? plcId = null)
    {
        var results = new List<PlcTagValueCacheEntry>();
        var lookupSet = new HashSet<string>(tagNamesOrAddresses, StringComparer.OrdinalIgnoreCase);

        foreach (var entry in _cache.Values)
        {
            if (plcId != null && entry.PlcId != plcId) continue;
            
            if (lookupSet.Contains(entry.TagName) || lookupSet.Contains(entry.Address))
            {
                results.Add(entry);
            }
        }

        return results;
    }

    /// <summary>
    /// Get tag values by PLC ID and addresses
    /// </summary>
    public List<PlcTagValueCacheEntry> GetTagValuesByAddress(string plcId, IEnumerable<string> addresses)
    {
        var results = new List<PlcTagValueCacheEntry>();

        foreach (var address in addresses)
        {
            var cacheKey = $"{plcId}::{address}";
            if (_cache.TryGetValue(cacheKey, out var entry))
            {
                results.Add(entry);
            }
        }

        return results;
    }

    /// <summary>
    /// Get single tag value
    /// </summary>
    public PlcTagValueCacheEntry? GetTagValue(string plcId, string address)
    {
        var cacheKey = $"{plcId}::{address}";
        return _cache.TryGetValue(cacheKey, out var entry) ? entry : null;
    }

    // ═══════════════════════════════════════════════════════════════════
    // STATUS METHODS
    // ═══════════════════════════════════════════════════════════════════

    /// <summary>
    /// Get last update timestamp
    /// </summary>
    public DateTime GetLastUpdateTimestamp() => _lastUpdateTimestamp;

    /// <summary>
    /// Get total cached tag count
    /// </summary>
    public int GetCachedTagCount() => _cache.Count;

    /// <summary>
    /// Get connection status for all PLCs
    /// </summary>
    public List<PlcPoolConnectionStatus> GetConnectionStatus()
    {
        return _connectionStatus.Values.ToList();
    }

    /// <summary>
    /// Get connection status for specific PLC
    /// </summary>
    public PlcPoolConnectionStatus? GetPlcConnectionStatus(string plcId)
    {
        return _connectionStatus.TryGetValue(plcId, out var status) ? status : null;
    }

    /// <summary>
    /// Get PLC status dictionary (API compatibility)
    /// </summary>
    public Dictionary<string, PlcPoolConnectionStatus> GetPlcStatus()
    {
        return _connectionStatus.ToDictionary(kvp => kvp.Key, kvp => kvp.Value);
    }

    /// <summary>
    /// Get pool statistics
    /// </summary>
    public PlcPoolStatistics GetStatistics()
    {
        var connectedPlcs = _connectionStatus.Values.Count(s => s.IsConnected);
        var disconnectedPlcs = _connectionStatus.Values.Count(s => !s.IsConnected);
        var cacheValues = _cache.Values.ToList();
        var goodCount = cacheValues.Count(v => v.Quality == PlcTagQuality.Good);
        var badCount = cacheValues.Count(v => v.Quality == PlcTagQuality.Bad || v.Quality == PlcTagQuality.CommError);
        var cacheTimes = cacheValues.Where(v => v.CachedAt > DateTime.MinValue).Select(v => v.CachedAt).ToList();

        return new PlcPoolStatistics
        {
            TotalTags = _cache.Count,
            TotalPlcs = _connectionStatus.Count,
            ConnectedPlcs = connectedPlcs,
            DisconnectedPlcs = disconnectedPlcs,
            GoodQualityCount = goodCount,
            BadQualityCount = badCount,
            LastUpdateTime = _lastUpdateTimestamp,
            OldestCacheTime = cacheTimes.Count > 0 ? cacheTimes.Min() : null,
            NewestCacheTime = cacheTimes.Count > 0 ? cacheTimes.Max() : null,
            TotalUpdates = _totalUpdates,
            TotalTagsProcessed = _totalTagsProcessed,
            TagsByPlc = _cache.Values
                .GroupBy(v => v.PlcId)
                .ToDictionary(g => g.Key, g => g.Count())
        };
    }

    /// <summary>
    /// Check if pool has data (not stale)
    /// </summary>
    public bool IsHealthy()
    {
        var staleness = (DateTime.UtcNow - _lastUpdateTimestamp).TotalSeconds;
        return staleness < 30; // Consider stale after 30 seconds
    }

    // ═══════════════════════════════════════════════════════════════════
    // MANAGEMENT METHODS
    // ═══════════════════════════════════════════════════════════════════

    /// <summary>
    /// Clear all cached data (on service restart)
    /// </summary>
    public void ClearPool()
    {
        _cache.Clear();
        _connectionStatus.Clear();
        _lastUpdateTimestamp = DateTime.MinValue;
        _logger.LogInformation("[PLC POOL] Pool cleared");
    }

    /// <summary>
    /// Remove all tags for a specific PLC
    /// </summary>
    public void RemovePlcTags(string plcId)
    {
        var keysToRemove = _cache.Keys.Where(k => k.StartsWith($"{plcId}::")).ToList();
        
        foreach (var key in keysToRemove)
        {
            _cache.TryRemove(key, out _);
        }

        _connectionStatus.TryRemove(plcId, out _);
        
        _logger.LogInformation("[PLC POOL] Removed {Count} tags for PLC {PlcId}", keysToRemove.Count, plcId);
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// DATA MODELS
// ═══════════════════════════════════════════════════════════════════════════

/// <summary>
/// Cached tag value entry
/// </summary>
public record PlcTagValueCacheEntry
{
    public string CacheKey { get; init; } = "";      // "PlcId::Address"
    public string PlcId { get; init; } = "";
    public string Address { get; init; } = "";
    public string TagName { get; init; } = "";
    public object? Value { get; init; }
    public string DataType { get; init; } = "";
    public PlcTagQuality Quality { get; init; }
    public DateTime Timestamp { get; init; }         // PLC timestamp
    public DateTime CachedAt { get; init; }          // Cache update time
    public string? EngineeringUnit { get; init; }
    
    // ═══════════════════════════════════════════════════════════════════
    // S1-3: age_ms COMPUTATION
    // ═══════════════════════════════════════════════════════════════════
    
    /// <summary>
    /// Age of cached value in milliseconds (computed on access)
    /// </summary>
    public long age_ms => (long)(DateTime.UtcNow - CachedAt).TotalMilliseconds;
    
    /// <summary>
    /// Computed quality (upgrades to Stale if age > 10 seconds)
    /// S1-4: If tag is Good but older than 10s, mark as Stale
    /// </summary>
    public PlcTagQuality ComputedQuality
    {
        get
        {
            // If already Bad/CommError/Uncertain, keep original quality
            if (Quality != PlcTagQuality.Good)
                return Quality;
            
            // S1-4: If Good but age > 10 seconds, mark as Stale
            if (age_ms > 10_000)
                return PlcTagQuality.Stale;
            
            return Quality;
        }
    }
}

/// <summary>
/// Tag quality
/// </summary>
public enum PlcTagQuality
{
    Good,
    Bad,
    Uncertain,
    CommError,
    NotConfigured,
    Stale              // Added S1-4: Tag older than 10 seconds
}

/// <summary>
/// PLC connection status (simplified for pool tracking)
/// </summary>
public class PlcPoolConnectionStatus
{
    public string PlcId { get; set; } = "";
    public bool IsConnected { get; set; }
    public DateTime LastUpdateTime { get; set; }
    public int TagCount { get; set; }
    public string? LastError { get; set; }
}

/// <summary>
/// Pool statistics
/// </summary>
public class PlcPoolStatistics
{
    public int TotalTags { get; set; }
    public int TotalPlcs { get; set; }
    public int ConnectedPlcs { get; set; }
    public int DisconnectedPlcs { get; set; }
    public int GoodQualityCount { get; set; }
    public int BadQualityCount { get; set; }
    public DateTime LastUpdateTime { get; set; }
    public DateTime? OldestCacheTime { get; set; }
    public DateTime? NewestCacheTime { get; set; }
    public int TotalUpdates { get; set; }
    public long TotalTagsProcessed { get; set; }
    public Dictionary<string, int> TagsByPlc { get; set; } = new();
}
