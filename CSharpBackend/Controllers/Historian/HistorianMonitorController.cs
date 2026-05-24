using Microsoft.AspNetCore.Mvc;
using OpcDaWebBrowser.Services.HistorianIngest.Services;
using OpcDaWebBrowser.Services;
using System.Collections.Concurrent;

namespace OpcDaWebBrowser.Controllers.Historian;

[ApiController]
[Route("api/historian")]
public class HistorianMonitorController : ControllerBase
{
    private readonly MappingCacheService _mappingCache;
    private readonly DbWriterService _dbWriter;
    private readonly TagValuesPoolService _tagPool;
    private readonly ILogger<HistorianMonitorController> _logger;
    
    // 5-second server-side cache for matrix data
    private static readonly ConcurrentDictionary<string, CachedMatrix> _matrixCache = new();
    private static readonly TimeSpan CacheExpiry = TimeSpan.FromSeconds(5);
    
    public HistorianMonitorController(
        MappingCacheService mappingCache,
        DbWriterService dbWriter,
        TagValuesPoolService tagPool,
        ILogger<HistorianMonitorController> logger)
    {
        _mappingCache = mappingCache;
        _dbWriter = dbWriter;
        _tagPool = tagPool;
        _logger = logger;
    }
    
    /// <summary>
    /// Get tag matrix with status, last update time, row counts - cached for 5 seconds
    /// Shows ALL tags with data in last 24 hours from database
    /// </summary>
    [HttpGet("matrix")]
    public async Task<IActionResult> GetTagMatrix()
    {
        try
        {
            const string cacheKey = "tag_matrix";
            
            // Check cache first (5 second cache to reduce DB load)
            if (_matrixCache.TryGetValue(cacheKey, out var cached))
            {
                if (DateTime.UtcNow - cached.Timestamp < CacheExpiry)
                {
                    _logger.LogDebug("Returning cached matrix data");
                    return Ok(cached.Response);
                }
            }
            
            // Get ALL tags from database in a single efficient query (last 24 hours)
            var allTagStats = await _dbWriter.GetAllTagStatisticsAsync();
            
            // Get mappings to check if tags are mapped
            var mappings = _mappingCache.GetAllMappings().ToDictionary(m => m.TagId);
            
            // Build matrix entries
            var matrix = new List<TagMatrixEntry>();
            
            foreach (var stats in allTagStats)
            {
                var tagId = stats.TagId ?? "Unknown";
                var mapping = mappings.GetValueOrDefault(tagId);
                
                var entry = new TagMatrixEntry
                {
                    TagId = tagId,
                    DisplayName = mapping?.TagName ?? tagId,
                    Mapped = mapping?.Enabled ?? false,
                    LastDataTime = stats.LastTimestamp,
                    RowCount = stats.TotalRows,
                    DataSource = stats.DataSource,
                    Status = DetermineStatus(stats.LastTimestamp),
                    DbLoggingIntervalMs = mapping?.DbLoggingIntervalMs ?? 0
                };
                
                matrix.Add(entry);
            }
            
            // Build response with summary
            var response = new
            {
                tags = matrix,
                summary = new
                {
                    totalTags = matrix.Count,
                    activeTags = matrix.Count(m => m.Status == "OK"),
                    staleTags = matrix.Count(m => m.Status == "STALE"),
                    totalRows = matrix.Sum(m => m.RowCount)
                }
            };
            
            // Cache the result
            _matrixCache[cacheKey] = new CachedMatrix
            {
                Response = response,
                Timestamp = DateTime.UtcNow
            };
            
            _logger.LogInformation("Matrix refreshed: {Count} tags, {Active} active, {Stale} stale", 
                matrix.Count, response.summary.activeTags, response.summary.staleTags);
            
            return Ok(response);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error getting tag matrix");
            return StatusCode(500, new { error = "Failed to retrieve tag matrix", message = ex.Message });
        }
    }
    
    /// <summary>
    /// Get trend data for specific tags with time range and point decimation
    /// </summary>
    [HttpGet("trends")]
    public async Task<IActionResult> GetTrends(
        [FromQuery] string tags,
        [FromQuery] DateTime? start,
        [FromQuery] DateTime? end,
        [FromQuery] int maxPoints = 2000)
    {
        try
        {
            if (string.IsNullOrWhiteSpace(tags))
            {
                return BadRequest(new { error = "Tags parameter is required" });
            }
            
            var tagList = tags.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
            if (tagList.Length == 0)
            {
                return BadRequest(new { error = "At least one tag must be specified" });
            }
            
            var startTime = start ?? DateTime.UtcNow.AddHours(-24);
            var endTime = end ?? DateTime.UtcNow;
            
            if (maxPoints > 5000) maxPoints = 5000; // Hard limit
            if (maxPoints < 50) maxPoints = 50;     // Minimum for visibility
            
            var trendData = await _dbWriter.GetTrendsDataAsync(tagList, startTime, endTime, maxPoints);
            
            return Ok(new
            {
                tags = tagList,
                start = startTime,
                end = endTime,
                maxPoints,
                data = trendData
            });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error getting trend data");
            return StatusCode(500, new { error = "Failed to retrieve trend data", message = ex.Message });
        }
    }
    
    private string DetermineStatus(DateTimeOffset? lastDataTime)
    {
        if (!lastDataTime.HasValue)
        {
            return "STOPPED";
        }
        
        var elapsed = DateTimeOffset.UtcNow - lastDataTime.Value;
        
        if (elapsed.TotalMinutes > 2)
        {
            return "STALE";
        }
        
        return "OK";
    }
    
    private class CachedMatrix
    {
        public required dynamic Response { get; set; }  // Stores the full API response with tags + summary
        public DateTime Timestamp { get; set; }
    }
}

public class TagMatrixEntry
{
    public required string TagId { get; set; }
    public required string DisplayName { get; set; }
    public bool Mapped { get; set; }
    public DateTimeOffset? LastDataTime { get; set; }
    public long RowCount { get; set; }
    public required string DataSource { get; set; }
    public required string Status { get; set; }  // OK, STALE (>2min), STOPPED (no data)
    public int DbLoggingIntervalMs { get; set; }
}
