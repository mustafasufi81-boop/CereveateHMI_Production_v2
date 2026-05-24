using Microsoft.AspNetCore.Mvc;
using Npgsql;
using OpcDaWebBrowser.Services.HistorianIngest.Config;
using OpcDaWebBrowser.Services.HistorianIngest.Services;

namespace OpcDaWebBrowser.Controllers.Historian;

[ApiController]
[Route("api/historian")]
public class HistorianHealthController : ControllerBase
{
    private readonly MappingCacheService _mappingCache;
    private readonly RateControllerService _rateController;
    private readonly BatcherService _batcher;
    private readonly DbWriterService _dbWriter;
    private readonly SpoolManagerService _spoolManager;
    private readonly HistorianConfig _historianConfig;
    private readonly ILogger<HistorianHealthController> _logger;

    public HistorianHealthController(
        MappingCacheService mappingCache,
        RateControllerService rateController,
        BatcherService batcher,
        DbWriterService dbWriter,
        SpoolManagerService spoolManager,
        HistorianConfig historianConfig,
        ILogger<HistorianHealthController> logger)
    {
        _mappingCache = mappingCache;
        _rateController = rateController;
        _batcher = batcher;
        _dbWriter = dbWriter;
        _spoolManager = spoolManager;
        _historianConfig = historianConfig;
        _logger = logger;
    }

    /// <summary>
    /// Liveness probe - always returns 200 if service is running
    /// </summary>
    [HttpGet("health/live")]
    public IActionResult Liveness()
    {
        return Ok(new
        {
            status = "alive",
            timestamp = DateTimeOffset.Now
        });
    }

    /// <summary>
    /// Readiness probe - checks DB connectivity and cache initialization
    /// </summary>
    [HttpGet("health/ready")]
    public async Task<IActionResult> Readiness()
    {
        var isDbHealthy = await _dbWriter.CheckHealthAsync(CancellationToken.None);
        var isCacheInitialized = _mappingCache.IsInitialized;
        var spoolQueueDepth = _spoolManager.GetSpoolFileCount();

        var isReady = (isDbHealthy || (spoolQueueDepth < 1000)) && isCacheInitialized;

        var response = new
        {
            status = isReady ? "ready" : "not_ready",
            timestamp = DateTimeOffset.Now,
            checks = new
            {
                database = isDbHealthy ? "healthy" : "unhealthy",
                cache = isCacheInitialized ? "initialized" : "not_initialized",
                spool_queue = spoolQueueDepth
            }
        };

        return isReady ? Ok(response) : StatusCode(503, response);
    }

    /// <summary>
    /// Metrics endpoint (Prometheus-compatible)
    /// </summary>
    [HttpGet("metrics")]
    public IActionResult Metrics()
    {
        var rateStats = _rateController.GetStats();
        
        var metrics = new
        {
            // Rate controller metrics
            historian_rate_control_samples_received_total = _rateController.SamplesReceived,
            historian_rate_control_samples_filtered_total = _rateController.SamplesFiltered,
            historian_rate_control_samples_passed_total = _rateController.SamplesPassed,
            historian_rate_control_filter_ratio = rateStats.FilterRatio,
            historian_rate_control_active_tags = rateStats.ActiveTags,

            // Batcher metrics
            historian_batcher_samples_received_total = _batcher.TotalSamplesReceived,
            historian_batcher_batches_created_total = _batcher.TotalBatchesCreated,

            // Writer metrics
            historian_writer_rows_written_total = _dbWriter.TotalRowsWritten,
            historian_writer_batches_written_total = _dbWriter.TotalBatchesWritten,
            historian_writer_errors_total = _dbWriter.TotalErrors,

            // Spool metrics
            historian_spool_batches_spooled_total = _spoolManager.TotalSpooled,
            historian_spool_batches_replayed_total = _spoolManager.TotalReplayed,
            historian_spool_queue_depth = _spoolManager.GetSpoolFileCount(),
            historian_spool_size_mb = _spoolManager.GetSpoolSizeMB(),

            // Cache metrics
            historian_cache_tag_count = _mappingCache.Count,
            historian_cache_mapping_version = _mappingCache.CurrentMappingVersion,
            historian_cache_initialized = _mappingCache.IsInitialized ? 1 : 0
        };

        return Ok(metrics);
    }

    /// <summary>
    /// Dashboard summary (for UI)
    /// </summary>
    [HttpGet("dashboard")]
    public IActionResult Dashboard()
    {
        var rateStats = _rateController.GetStats();

        var dashboard = new
        {
            timestamp = DateTimeOffset.Now,
            cache = new
            {
                tag_count = _mappingCache.Count,
                mapping_version = _mappingCache.CurrentMappingVersion,
                initialized = _mappingCache.IsInitialized
            },
            rate_control = new
            {
                samples_received = _rateController.SamplesReceived,
                samples_passed = _rateController.SamplesPassed,
                samples_filtered = _rateController.SamplesFiltered,
                filter_ratio = rateStats.FilterRatio,
                active_tags = rateStats.ActiveTags
            },
            batcher = new
            {
                samples_received = _batcher.TotalSamplesReceived,
                batches_created = _batcher.TotalBatchesCreated
            },
            writer = new
            {
                rows_written = _dbWriter.TotalRowsWritten,
                batches_written = _dbWriter.TotalBatchesWritten,
                errors = _dbWriter.TotalErrors
            },
            spool = new
            {
                batches_spooled = _spoolManager.TotalSpooled,
                batches_replayed = _spoolManager.TotalReplayed,
                queue_depth = _spoolManager.GetSpoolFileCount(),
                size_mb = _spoolManager.GetSpoolSizeMB()
            }
        };

        return Ok(dashboard);
    }

    /// <summary>
    /// Tag status — how many enabled tags are live vs missing in DB
    /// </summary>
    [HttpGet("tag-status")]
    public async Task<IActionResult> TagStatus()
    {
        try
        {
            await using var conn = new NpgsqlConnection(_historianConfig.Database.ConnectionString);
            await conn.OpenAsync();

            // All enabled tags in tag_master
            var enabledTags = new List<string>();
            await using (var cmd = new NpgsqlCommand(
                "SELECT tag_id FROM historian_meta.tag_master WHERE enabled = true ORDER BY tag_id", conn))
            await using (var reader = await cmd.ExecuteReaderAsync())
                while (await reader.ReadAsync())
                    enabledTags.Add(reader.GetString(0));

            // Tags with data in last 10 minutes (live)
            var liveSet = new HashSet<string>();
            await using (var cmd = new NpgsqlCommand(
                "SELECT DISTINCT tag_id FROM historian_raw.historian_timeseries WHERE time > NOW() - INTERVAL '10 minutes'", conn))
            await using (var reader = await cmd.ExecuteReaderAsync())
                while (await reader.ReadAsync())
                    liveSet.Add(reader.GetString(0));

            // Tags with data in last 24 hours
            var recentSet = new HashSet<string>();
            await using (var cmd = new NpgsqlCommand(
                "SELECT DISTINCT tag_id FROM historian_raw.historian_timeseries WHERE time > NOW() - INTERVAL '24 hours'", conn))
            await using (var reader = await cmd.ExecuteReaderAsync())
                while (await reader.ReadAsync())
                    recentSet.Add(reader.GetString(0));

            var enabledSet   = enabledTags.ToHashSet();
            var liveMapped   = enabledSet.Intersect(liveSet).OrderBy(t => t).ToList();
            var staleMapped  = enabledSet.Intersect(recentSet).Except(liveSet).OrderBy(t => t).ToList();
            var missingTags  = enabledSet.Except(recentSet).OrderBy(t => t).ToList();

            return Ok(new
            {
                enabled_count = enabledSet.Count,
                live_count    = liveMapped.Count,
                stale_count   = staleMapped.Count,
                missing_count = missingTags.Count,
                live_tags     = liveMapped,
                stale_tags    = staleMapped,
                missing_tags  = missingTags
            });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "tag-status query failed");
            return StatusCode(500, new { error = ex.Message });
        }
    }
}
