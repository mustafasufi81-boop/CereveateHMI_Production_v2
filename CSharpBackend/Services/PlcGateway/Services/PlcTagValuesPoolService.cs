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

    // ── Gap 8: Per-PLC value-change tracking for PLC mode detection ─────
    // Primary:  driver's ReadControllerModeAsync() returns actual CIP mode.
    // Fallback: value-change heuristic — requires ≥15% of tags to change per scan
    //           (physical I/O noise alone is typically <5% of tags, so this
    //           correctly ignores noise and only stays RUN when user program runs).
    private readonly ConcurrentDictionary<string, DateTime> _plcLastValueChange = new(StringComparer.OrdinalIgnoreCase);

    // Threshold: if <15% of tags changed in a scan AND no actual mode known
    //            → that scan does NOT reset the last-change timer.
    private const double RunChangeThresholdPct = 0.15;

    // If no significant change for this long while connected → FROZEN
    // (reduced from 30 s to 8 s so the badge flips fast after mode change)
    private const long FrozenThresholdMs = 8_000;

    // Minimum tag count required for the percentage-based freeze heuristic to be
    // statistically meaningful. With fewer tags (e.g. a PLC carrying only a single
    // setpoint), a static value would falsely flag the PLC as FROZEN even though
    // the controller is healthy and in RUN. Below this threshold we trust the
    // connection state instead of the heuristic.
    private const int MinTagsForFreezeHeuristic = 7;

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
    public void UpdateFromPlc(string plcId, List<PlcTagValueCacheEntry> tagValues, DateTime timestamp,
                               string? plcMode = null)
    {
        if (tagValues == null || tagValues.Count == 0) return;

        var updateCount = 0;
        var changedCount = 0;
        var hadPriorCache = false;

        foreach (var tagValue in tagValues)
        {
            // Key format: "PlcId::Address" for uniqueness across PLCs
            var cacheKey = $"{plcId}::{tagValue.Address}";

            // Gap 8: count value changes for the heuristic
            if (_cache.TryGetValue(cacheKey, out var prev))
            {
                hadPriorCache = true;
                if (!Equals(prev.Value, tagValue.Value))
                    changedCount++;
            }

            // R6 / defence-in-depth — enforce the SINGLE pool invariant: "Good ⇒ finite".
            // The driver (Phase 1 validator) is the sole validation authority; the pool does
            // NOT re-run denormal/range/type checks. It only guards against a value that is
            // flagged Good yet non-finite (NaN/Inf) — which can only mean a driver regression.
            // On violation: demote to Bad + log (value is still carried truthfully — R2).
            var entryToCache = tagValue;
            if (entryToCache.Quality == PlcTagQuality.Good && !IsFinite(entryToCache.Value))
            {
                _logger.LogWarning(
                    "[PLC POOL] Invariant violation — {Plc}::{Addr} flagged Good but non-finite ({Val}); demoting to Bad",
                    plcId, tagValue.Address, tagValue.Value);
                entryToCache = entryToCache with { Quality = PlcTagQuality.Bad };
            }

            _cache[cacheKey] = entryToCache with
            {
                PlcId = plcId,
                CacheKey = cacheKey,
                CachedAt = DateTime.UtcNow
            };
            updateCount++;
        }

        // First scan ever counts as activity (seed timestamp)
        if (!hadPriorCache) changedCount = tagValues.Count;

        // Heuristic: require ≥15% of tags to change to count as "significant activity".
        // Physical I/O noise is typically <5% of tags; real program execution moves 20-100%.
        var significantActivity = hadPriorCache
            ? ((double)changedCount / tagValues.Count) >= RunChangeThresholdPct
            : true;

        if (significantActivity)
            _plcLastValueChange[plcId] = DateTime.UtcNow;

        // Compute mode/freeze metrics for the heuristic fallback
        var lastChange = _plcLastValueChange.TryGetValue(plcId, out var lc) ? (DateTime?)lc : null;
        var frozenForMs = lastChange.HasValue
            ? (long)(DateTime.UtcNow - lastChange.Value).TotalMilliseconds
            : 0L;

        // ── Choose authoritative mode ───────────────────────────────────────
        // Priority 1: actual CIP mode read from the driver (non-null, non-UNKNOWN)
        // Priority 2: heuristic — FROZEN if no significant value change for >8 s, else RUN
        //             Skipped when the tag count is too small for the percentage rule
        //             to be statistically meaningful (avoids false FROZEN on PLCs that
        //             only host a handful of static setpoints).
        string mode;
        if (!string.IsNullOrEmpty(plcMode) && plcMode != "UNKNOWN")
        {
            // Real mode from the PLC; always trust it.
            // Still update frozenForMs so the badge can show how long it's been in this mode.
            mode = plcMode;
        }
        else if (tagValues.Count < MinTagsForFreezeHeuristic)
        {
            // Not enough tags for the heuristic to be reliable — if we're reading
            // values at all, the PLC is alive. Report RUN and zero the freeze timer.
            mode = "RUN";
            frozenForMs = 0L;
            _plcLastValueChange[plcId] = DateTime.UtcNow;
            lastChange = _plcLastValueChange[plcId];
        }
        else
        {
            // Heuristic fallback
            mode = frozenForMs > FrozenThresholdMs ? "FROZEN" : "RUN";
        }

        // Update connection status - preserve total tag count across batches
        var totalTagsForPlc = _cache.Values.Count(v => v.PlcId == plcId);
        _connectionStatus[plcId] = new PlcPoolConnectionStatus
        {
            PlcId = plcId,
            IsConnected = true,
            LastUpdateTime = timestamp,
            TagCount = totalTagsForPlc, // Use TOTAL tags in cache for this PLC, not batch size
            LastError = null,
            LastValueChangeTime = lastChange,
            FrozenForMs = frozenForMs,
            Mode = mode
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
            LastError = error,
            Mode = "UNKNOWN"
        };

        // Mark all tags from this PLC as stale
        foreach (var kvp in _cache.Where(c => c.Value.PlcId == plcId))
        {
            _cache[kvp.Key] = kvp.Value with { Quality = PlcTagQuality.Uncertain };
        }

        _logger.LogWarning("[PLC POOL] Marked {PlcId} as disconnected: {Error}", plcId, error ?? "Unknown");
    }

    /// <summary>
    /// Gap 7: Register a sentinel entry indicating no PLCs are configured in the database.
    /// This makes the "no PLC" state visible via /api/plc/connections instead of silently empty.
    /// </summary>
    public void MarkNoPlcConfigured(string reason = "No PLC configurations found in database")
    {
        const string sentinelId = "__NONE__";
        _connectionStatus[sentinelId] = new PlcPoolConnectionStatus
        {
            PlcId = sentinelId,
            IsConnected = false,
            LastUpdateTime = DateTime.UtcNow,
            TagCount = 0,
            LastError = reason,
            Mode = "UNKNOWN"
        };
        _logger.LogError("[PLC POOL] {Reason} — backend has no PLC to poll", reason);
    }

    /// <summary>
    /// Clear the no-PLC sentinel (called once configs are loaded)
    /// </summary>
    public void ClearNoPlcConfiguredSentinel()
    {
        _connectionStatus.TryRemove("__NONE__", out _);
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
    /// R6 — CONNECTION-GATED read for alarm/live evaluation.
    /// Identical matching to GetTagValues, but OMITS any tag whose owning PLC is
    /// currently NotConnected (pool IsConnected=false). This is an authoritative
    /// gate, independent of and in addition to the per-tag quality gate: two gates,
    /// same verdict. A physically-down PLC therefore contributes ZERO tags to the
    /// alarm engine, regardless of any stale value still sitting in the cache.
    /// </summary>
    public List<PlcTagValueCacheEntry> GetTagValuesFromConnectedPlcs(
        IEnumerable<string> tagNamesOrAddresses, string? plcId = null)
    {
        var results = new List<PlcTagValueCacheEntry>();
        var lookupSet = new HashSet<string>(tagNamesOrAddresses, StringComparer.OrdinalIgnoreCase);

        foreach (var entry in _cache.Values)
        {
            if (plcId != null && entry.PlcId != plcId) continue;

            if (!lookupSet.Contains(entry.TagName) && !lookupSet.Contains(entry.Address))
                continue;

            // R6 connection gate: skip tags whose owning PLC is not connected.
            if (!_connectionStatus.TryGetValue(entry.PlcId, out var status) || !status.IsConnected)
                continue;

            results.Add(entry);
        }

        return results;
    }

    /// <summary>
    /// Finiteness check for the pool's "Good ⇒ finite" invariant guard.
    /// Only floating types can be non-finite; all other types are finite by definition.
    /// </summary>
    private static bool IsFinite(object? value) => value switch
    {
        double d => !(double.IsNaN(d) || double.IsInfinity(d)),
        float f  => !(float.IsNaN(f)  || float.IsInfinity(f)),
        _        => true
    };

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
    // S2-6: SCAN SEQUENCE TRACKING
    // ═══════════════════════════════════════════════════════════════════
    
    /// <summary>
    /// Scan sequence ID - increments per scan cycle. Allows UI to detect
    /// partial/mixed-cycle data. All tags from same scan have identical SequenceId.
    /// S2-6: Added for scan cycle correlation (mirrors OPC _sequenceId pattern)
    /// </summary>
    public long SequenceId { get; init; }
    
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
    /// Gap 1: Also escalate Uncertain → Stale once age exceeds threshold so that
    /// values from a disconnected PLC (MarkPlcDisconnected sets Uncertain) are
    /// visibly stale to downstream consumers. Hard-bad qualities (Bad/CommError/
    /// NotConfigured) are preserved as-is — they carry stronger meaning than Stale.
    /// </summary>
    public PlcTagQuality ComputedQuality
    {
        get
        {
            // Preserve hard-bad qualities (stronger signal than Stale)
            if (Quality == PlcTagQuality.Bad
                || Quality == PlcTagQuality.CommError
                || Quality == PlcTagQuality.NotConfigured
                || Quality == PlcTagQuality.Stale)
                return Quality;

            // Good or Uncertain → upgrade to Stale once age > 10 seconds
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

    // Gap 8: PLC mode detection (RUN | FROZEN | UNKNOWN)
    // FROZEN = reads are succeeding but no tag value has changed for >30s.
    // Most common cause is Rockwell PROGRAM mode (controller halted user logic
    // but still serves CIP reads), or a PLC scan/I/O fault.
    public string Mode { get; set; } = "UNKNOWN";
    public DateTime? LastValueChangeTime { get; set; }
    public long FrozenForMs { get; set; }
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
