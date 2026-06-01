using System.Collections.Concurrent;
using Microsoft.Extensions.Logging;

namespace OpcDaWebBrowser.Services;

/// <summary>
/// Shared tag values pool/cache populated by DataLoggingService OPC connection
/// Both Parquet and PostgreSQL services pull from this cache independently
/// Thread-safe, dynamically updated based on UNION of subscribed tags
/// </summary>
public class TagValuesPoolService
{
    private readonly ILogger<TagValuesPoolService> _logger;
    private readonly ConcurrentDictionary<string, TagValueCacheEntry> _tagValuesCache;
    private DateTime _lastUpdateTimestamp = DateTime.MinValue;
    private readonly object _updateLock = new();

    public TagValuesPoolService(ILogger<TagValuesPoolService> logger)
    {
        _logger = logger;
        _tagValuesCache = new ConcurrentDictionary<string, TagValueCacheEntry>(StringComparer.OrdinalIgnoreCase);
    }

    /// <summary>
    /// Update cache with latest tag values from OPC connection
    /// Called by DataLoggingService on each poll cycle
    /// </summary>
    public void UpdatePool(List<TagValue> tagValues, DateTime timestamp)
    {
        lock (_updateLock)
        {
            _lastUpdateTimestamp = timestamp;
            
            foreach (var tagValue in tagValues)
            {
                _tagValuesCache[tagValue.ItemID] = new TagValueCacheEntry
                {
                    TagId = tagValue.ItemID,
                    Value = tagValue.Value,
                    Quality = tagValue.Quality,
                    Timestamp = timestamp,
                    UpdatedAt = DateTime.Now
                };
            }
        }

        _logger.LogDebug($"Tag pool updated: {tagValues.Count} tags at {timestamp:HH:mm:ss.fff}");
    }

    /// <summary>
    /// Get current values for specific tags (filtered by caller's mapping list)
    /// Returns only tags that exist in the pool
    /// </summary>
    public List<TagValueCacheEntry> GetTagValues(IEnumerable<string> tagIds)
    {
        var results = new List<TagValueCacheEntry>();
        
        foreach (var tagId in tagIds)
        {
            if (_tagValuesCache.TryGetValue(tagId, out var entry))
            {
                results.Add(entry);
            }
        }

        return results;
    }

    /// <summary>
    /// Get ALL cached tag values (useful for diagnostics)
    /// </summary>
    public List<TagValueCacheEntry> GetAllTagValues()
    {
        return _tagValuesCache.Values.ToList();
    }

    /// <summary>
    /// Get timestamp of last cache update
    /// </summary>
    public DateTime GetLastUpdateTimestamp() => _lastUpdateTimestamp;

    /// <summary>
    /// Get count of tags currently in cache
    /// </summary>
    public int GetCachedTagCount() => _tagValuesCache.Count;

    /// <summary>
    /// Check if cache contains a specific tag
    /// </summary>
    public bool ContainsTag(string tagId) => _tagValuesCache.ContainsKey(tagId);

    /// <summary>
    /// Clear the entire cache (useful for reconnections)
    /// </summary>
    public void ClearPool()
    {
        _tagValuesCache.Clear();
        _lastUpdateTimestamp = DateTime.MinValue;
        _logger.LogInformation("Tag pool cleared");
    }
}

/// <summary>
/// Cached tag value entry with metadata
/// </summary>
public class TagValueCacheEntry
{
    public required string TagId { get; set; }
    public required string Value { get; set; }
    public required string Quality { get; set; }
    public DateTime Timestamp { get; set; }      // OPC read timestamp (same for all tags in batch)
    public DateTime UpdatedAt { get; set; }      // When this entry was cached
    
    /// <summary>
    /// True when:
    /// 1. Quality is Bad/Stale/Uncertain (immediate staleness) OR
    /// 2. No update received for more than 30 seconds (time-based staleness)
    /// 
    /// FIX: Previously only checked time — caused ghost alarm values during PLC disconnect.
    /// Now checks quality FIRST so bad-quality values don't get evaluated as alarms.
    /// </summary>
    public bool IsStale =>
        !IsGoodQuality(Quality) || (DateTime.UtcNow - UpdatedAt).TotalSeconds > 30;
    
    private static bool IsGoodQuality(string quality) =>
        quality is "Good" or "G" or "GOOD";
}
