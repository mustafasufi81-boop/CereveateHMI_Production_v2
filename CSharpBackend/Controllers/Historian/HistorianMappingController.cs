using Microsoft.AspNetCore.Mvc;
using Npgsql;
using OpcDaWebBrowser.Services.HistorianIngest.Config;
using OpcDaWebBrowser.Services.HistorianIngest.Models;
using OpcDaWebBrowser.Services.HistorianIngest.Services;
using OpcDaWebBrowser.Services;

namespace OpcDaWebBrowser.Controllers.Historian;

[ApiController]
[Route("api/historian/mapping")]
public class HistorianMappingController : ControllerBase
{
    private readonly HistorianConfig _config;
    private readonly MappingCacheService _mappingCache;
    private readonly DbWriterService _dbWriter;
    private readonly OpcDaService _opcService;
    private readonly LoggingConfigService _loggingConfigService;
    private readonly ILogger<HistorianMappingController> _logger;

    public HistorianMappingController(
        HistorianConfig config,
        MappingCacheService mappingCache,
        DbWriterService dbWriter,
        OpcDaService opcService,
        LoggingConfigService loggingConfigService,
        ILogger<HistorianMappingController> logger)
    {
        _config = config;
        _mappingCache = mappingCache;
        _dbWriter = dbWriter;
        _opcService = opcService;
        _loggingConfigService = loggingConfigService;
        _logger = logger;
    }

    /// <summary>
    /// Get all tag mappings
    /// </summary>
    [HttpGet]
    public IActionResult GetAllMappings()
    {
        var mappings = _mappingCache.GetAllEnabledMappings();
        return Ok(new
        {
            count = mappings.Count,
            mapping_version = _mappingCache.CurrentMappingVersion,
            mappings
        });
    }

    /// <summary>
    /// Get specific tag mapping
    /// </summary>
    [HttpGet("{tagId}")]
    public IActionResult GetMapping(string tagId)
    {
        var mapping = _mappingCache.GetMapping(tagId);
        if (mapping == null)
            return NotFound(new { error = $"Tag '{tagId}' not found" });

        return Ok(mapping);
    }

    /// <summary>
    /// Create or update tag mapping
    /// </summary>
    [HttpPost]
    public async Task<IActionResult> UpsertMapping([FromBody] TagMapping mapping)
    {
        try
        {
            static string NormalizeRequired(string? value, string fallback)
                => string.IsNullOrWhiteSpace(value) ? fallback : value.Trim();

            static string? NormalizeOptional(string? value)
                => string.IsNullOrWhiteSpace(value) ? null : value.Trim();

            mapping.TagId = mapping.TagId?.Trim() ?? string.Empty;

            // Validate
            if (string.IsNullOrWhiteSpace(mapping.TagId))
                return BadRequest(new { error = "tag_id is required" });

            var normalizedTagName = NormalizeRequired(mapping.TagName, mapping.TagId);
            var normalizedPlant = NormalizeRequired(mapping.Plant, "Plant1");
            var normalizedArea = NormalizeRequired(mapping.Area, "Area1");
            var normalizedEquipment = NormalizeRequired(mapping.Equipment, "Equipment1");
            var normalizedTable = NormalizeRequired(mapping.DbTableName, "historian_raw.historian_timeseries");
            var normalizedDescription = NormalizeOptional(mapping.Description);
            var normalizedEngUnit = NormalizeOptional(mapping.EngUnit);
            var normalizedCreatedBy = NormalizeOptional(mapping.CreatedBy) ?? "API";

            if (mapping.DbLoggingIntervalMs < 1000 || mapping.DbLoggingIntervalMs > 60000)
                return BadRequest(new { error = "db_logging_interval_ms must be between 1000 and 60000" });

            var loggingConfig = _loggingConfigService.GetConfig();
            string? serverProgId = loggingConfig.ServerProgId;
            string? serverHost = loggingConfig.ServerHost;

            // Fallback to the currently active OPC connection when config is missing values
            if (string.IsNullOrWhiteSpace(serverProgId) || string.IsNullOrWhiteSpace(serverHost))
            {
                var activeConnection = _opcService.GetActiveConnection();
                if (activeConnection != null)
                {
                    if (string.IsNullOrWhiteSpace(serverProgId))
                    {
                        serverProgId = activeConnection.ServerProgID;
                    }

                    if (string.IsNullOrWhiteSpace(serverHost))
                    {
                        // Persist "localhost" for clarity when host string is empty
                        serverHost = string.IsNullOrWhiteSpace(activeConnection.Host)
                            ? "localhost"
                            : activeConnection.Host;
                    }
                }
            }

            serverProgId = string.IsNullOrWhiteSpace(serverProgId) ? null : serverProgId.Trim();
            serverHost = string.IsNullOrWhiteSpace(serverHost) ? null : serverHost.Trim();

            using var connection = new NpgsqlConnection(_config.Database.ConnectionString);
            await connection.OpenAsync();

            var sql = @"
                INSERT INTO historian_meta.tag_master 
                    (tag_id, tag_name, description, plant, area, equipment, data_type, eng_unit, 
                     db_logging_interval_ms, enabled, db_table_name, created_by, server_progid, server_host)
                VALUES 
                    (@tag_id, @tag_name, @description, @plant, @area, @equipment, @data_type, @eng_unit,
                     @db_logging_interval_ms, @enabled, @db_table_name, @created_by, @server_progid, @server_host)
                ON CONFLICT (tag_id) DO UPDATE SET
                    tag_name = EXCLUDED.tag_name,
                    description = EXCLUDED.description,
                    plant = EXCLUDED.plant,
                    area = EXCLUDED.area,
                    equipment = EXCLUDED.equipment,
                    data_type = EXCLUDED.data_type,
                    eng_unit = EXCLUDED.eng_unit,
                    db_logging_interval_ms = EXCLUDED.db_logging_interval_ms,
                    enabled = EXCLUDED.enabled,
                    db_table_name = EXCLUDED.db_table_name,
                    server_progid = EXCLUDED.server_progid,
                    server_host = EXCLUDED.server_host,
                    config_updated_at = now(),
                    mapping_version = historian_meta.tag_master.mapping_version + 1
                RETURNING mapping_version";

            using var cmd = new NpgsqlCommand(sql, connection);
            cmd.Parameters.AddWithValue("tag_id", mapping.TagId);
            cmd.Parameters.AddWithValue("tag_name", normalizedTagName);
            cmd.Parameters.AddWithValue("description", (object?)normalizedDescription ?? DBNull.Value);
            cmd.Parameters.AddWithValue("plant", normalizedPlant);
            cmd.Parameters.AddWithValue("area", normalizedArea);
            cmd.Parameters.AddWithValue("equipment", normalizedEquipment);
            cmd.Parameters.AddWithValue("data_type", mapping.DataType.ToString().ToLower());
            cmd.Parameters.AddWithValue("eng_unit", (object?)normalizedEngUnit ?? DBNull.Value);
            cmd.Parameters.AddWithValue("db_logging_interval_ms", mapping.DbLoggingIntervalMs);
            cmd.Parameters.AddWithValue("enabled", mapping.Enabled);
            cmd.Parameters.AddWithValue("db_table_name", normalizedTable);
            cmd.Parameters.AddWithValue("created_by", normalizedCreatedBy);
            cmd.Parameters.AddWithValue("server_progid", (object?)serverProgId ?? DBNull.Value);
            cmd.Parameters.AddWithValue("server_host", (object?)serverHost ?? DBNull.Value);

            var newVersion = (long)(await cmd.ExecuteScalarAsync() ?? 0L);

            // Log event
            await _dbWriter.LogEventAsync(new HistorianEvent
            {
                EventType = HistorianEventTypes.MappingUpdate,
                TagId = mapping.TagId,
                Severity = EventSeverity.INFO,
                Message = $"Tag mapping updated via API",
                Details = new Dictionary<string, object>
                {
                    ["new_version"] = newVersion,
                    ["interval_ms"] = mapping.DbLoggingIntervalMs
                }
            }, CancellationToken.None);

            return Ok(new
            {
                success = true,
                tag_id = mapping.TagId,
                mapping_version = newVersion,
                message = "Mapping saved successfully (cache will refresh automatically)"
            });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, $"Failed to upsert mapping for tag {mapping?.TagId ?? "NULL"}");
            return StatusCode(500, new { 
                error = ex.Message,
                details = ex.InnerException?.Message,
                stackTrace = ex.StackTrace?.Split('\n').Take(3).ToArray()
            });
        }
    }

    /// <summary>
    /// Delete tag mapping
    /// </summary>
    [HttpDelete("{tagId}")]
    public async Task<IActionResult> DeleteMapping(string tagId)
    {
        try
        {
            using var connection = new NpgsqlConnection(_config.Database.ConnectionString);
            await connection.OpenAsync();

            var sql = "DELETE FROM historian_meta.tag_master WHERE tag_id = @tag_id";
            using var cmd = new NpgsqlCommand(sql, connection);
            cmd.Parameters.AddWithValue("tag_id", tagId);

            var rowsAffected = await cmd.ExecuteNonQueryAsync();

            if (rowsAffected == 0)
                return NotFound(new { error = $"Tag '{tagId}' not found" });

            return Ok(new { success = true, message = "Mapping deleted" });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, $"Failed to delete mapping for tag {tagId}");
            return StatusCode(500, new { error = ex.Message });
        }
    }

    /// <summary>
    /// Refresh cache manually
    /// </summary>
    [HttpPost("refresh")]
    public async Task<IActionResult> RefreshCache()
    {
        try
        {
            await _mappingCache.RefreshCacheAsync();
            return Ok(new
            {
                success = true,
                count = _mappingCache.Count,
                version = _mappingCache.CurrentMappingVersion
            });
        }
        catch (Exception ex)
        {
            return StatusCode(500, new { error = ex.Message });
        }
    }

    /// <summary>
    /// Toggle tag enabled/disabled for database logging
    /// </summary>
    [HttpPost("{tagId}/toggle")]
    public async Task<IActionResult> ToggleTagEnabled(string tagId, [FromBody] ToggleTagRequest request)
    {
        try
        {
            using var connection = new NpgsqlConnection(_config.Database.ConnectionString);
            await connection.OpenAsync();

            var sql = @"
                UPDATE historian_meta.tag_master 
                SET enabled = @enabled,
                    config_updated_at = now(),
                    mapping_version = mapping_version + 1
                WHERE tag_id = @tag_id
                RETURNING mapping_version";

            using var cmd = new NpgsqlCommand(sql, connection);
            cmd.Parameters.AddWithValue("tag_id", tagId);
            cmd.Parameters.AddWithValue("enabled", request.Enabled);

            var result = await cmd.ExecuteScalarAsync();
            if (result == null)
                return NotFound(new { error = $"Tag '{tagId}' not found" });

            var newVersion = (long)result;

            // Log event
            await _dbWriter.LogEventAsync(new HistorianEvent
            {
                EventType = HistorianEventTypes.MappingUpdate,
                TagId = tagId,
                Severity = EventSeverity.INFO,
                Message = $"Tag logging {(request.Enabled ? "enabled" : "disabled")} via API"
            }, CancellationToken.None);

            return Ok(new
            {
                success = true,
                tag_id = tagId,
                enabled = request.Enabled,
                mapping_version = newVersion,
                message = $"Tag logging {(request.Enabled ? "enabled" : "disabled")} successfully"
            });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, $"Failed to toggle tag {tagId}");
            return StatusCode(500, new { error = ex.Message });
        }
    }

    /// <summary>
    /// Get events log
    /// </summary>
    [HttpGet("~/api/historian/events")]
    public async Task<IActionResult> GetEvents(
        [FromQuery] string? eventType = null,
        [FromQuery] string? tagId = null,
        [FromQuery] int limit = 100)
    {
        try
        {
            using var connection = new NpgsqlConnection(_config.Database.ConnectionString);
            await connection.OpenAsync();

            var sql = @"
                SELECT event_time, event_type, tag_id, severity, message, details
                FROM historian_admin.historian_events
                WHERE (@event_type IS NULL OR event_type = @event_type)
                  AND (@tag_id IS NULL OR tag_id = @tag_id)
                ORDER BY event_time DESC
                LIMIT @limit";

            using var cmd = new NpgsqlCommand(sql, connection);
            cmd.Parameters.AddWithValue("event_type", (object?)eventType ?? DBNull.Value);
            cmd.Parameters.AddWithValue("tag_id", (object?)tagId ?? DBNull.Value);
            cmd.Parameters.AddWithValue("limit", limit);

            var events = new List<object>();
            using var reader = await cmd.ExecuteReaderAsync();
            while (await reader.ReadAsync())
            {
                events.Add(new
                {
                    event_time = reader.GetFieldValue<DateTimeOffset>(0),
                    event_type = reader.GetString(1),
                    tag_id = reader.IsDBNull(2) ? null : reader.GetString(2),
                    severity = reader.GetString(3),
                    message = reader.GetString(4),
                    details = reader.IsDBNull(5) ? null : reader.GetString(5)
                });
            }

            return Ok(new { count = events.Count, events });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to get events");
            return StatusCode(500, new { error = ex.Message });
        }
    }

    /// <summary>
    /// Get available OPC tags with their mapping status.
    /// ✅ Works if OPC is offline (falls back to historian DB values)
    /// ✅ Includes tags that are mapped but currently not exposed by OPC
    /// ✅ Keeps unmapped OPC tags visible for discovery
    /// </summary>
    [HttpGet("available-tags")]
    public async Task<IActionResult> GetAvailableTags()
    {
        try
        {
            // Load mapping + latest DB snapshot in parallel so UI always has state
            var allMappings = _mappingCache.GetAllMappings();
            var mappingDict = allMappings.ToDictionary(m => m.TagId, m => m, StringComparer.OrdinalIgnoreCase);

            var latestValues = await _dbWriter.GetLatestTagValuesAsync();
            var valueDict = latestValues.ToDictionary(v => v.TagId, v => v, StringComparer.OrdinalIgnoreCase);

            // Get active OPC connection ProgID to populate server name for unmapped tags
            var activeConn = _opcService.GetActiveConnection();
            var activeProgId = activeConn?.ServerProgID;
            var activeHost = string.IsNullOrWhiteSpace(activeConn?.Host) ? "localhost" : activeConn?.Host;

            List<TagValue> opcTags;
            try
            {
                opcTags = _opcService.ReadAllTagValues();
                _logger.LogInformation("OPC returned {Count} tags", opcTags.Count);
            }
            catch (Exception opcEx)
            {
                _logger.LogWarning(opcEx, "OPC read failed; continuing with database snapshot only");
                opcTags = new List<TagValue>();
            }

            var opcDict = opcTags.ToDictionary(t => t.ItemID, t => t, StringComparer.OrdinalIgnoreCase);
            var result = new List<object>(opcTags.Count + allMappings.Count);

            foreach (var opcTag in opcTags)
            {
                mappingDict.TryGetValue(opcTag.ItemID, out var mapping);
                valueDict.TryGetValue(opcTag.ItemID, out var latest);

                // For unmapped tags use active connection ProgID so UI shows server name
                var displayProgId = mapping?.ServerProgId ?? activeProgId;
                var displayHost = mapping?.ServerHost ?? activeHost;

                result.Add(new
                {
                    tagId = opcTag.ItemID,
                    currentValue = latest?.Value ?? opcTag.Value,
                    quality = opcTag.Quality ?? latest?.Quality ?? "U",
                    timestamp = latest?.Timestamp ?? opcTag.Timestamp,
                    opcAvailable = true,
                    isMapped = mapping is not null,
                    mapping = new
                    {
                        tagName = mapping?.TagName ?? opcTag.ItemID,
                        dataType = mapping?.DataType,
                        interval = mapping?.DbLoggingIntervalMs ?? 1000,
                        enabled = mapping?.Enabled ?? false,
                        serverProgId = displayProgId,
                        serverHost = displayHost
                    }
                });
            }

            // Include mapped tags even if OPC is down (so UI still shows state)
            foreach (var mapping in allMappings)
            {
                if (opcDict.ContainsKey(mapping.TagId))
                    continue;

                valueDict.TryGetValue(mapping.TagId, out var latest);

                result.Add(new
                {
                    tagId = mapping.TagId,
                    currentValue = latest?.Value,
                    quality = latest?.Quality ?? "U",
                    timestamp = latest?.Timestamp,
                    opcAvailable = false,
                    isMapped = true,
                    mapping = new
                    {
                        tagName = mapping.TagName,
                        dataType = mapping.DataType,
                        interval = mapping.DbLoggingIntervalMs,
                        enabled = mapping.Enabled,
                        serverProgId = mapping.ServerProgId,
                        serverHost = mapping.ServerHost
                    }
                });
            }

            _logger.LogInformation("Returning {Count} tags (OPC {OpcCount}, mapped {MappedCount}, db snapshots {DbCount})",
                result.Count, opcTags.Count, allMappings.Count, latestValues.Count);

            return Ok(new { count = result.Count, tags = result });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to get available tags");
            return StatusCode(500, new { error = ex.Message, stack = ex.StackTrace });
        }
    }
}

/// <summary>
/// Request model for toggling tag enabled status
/// </summary>
public class ToggleTagRequest
{
    public bool Enabled { get; set; }
}
