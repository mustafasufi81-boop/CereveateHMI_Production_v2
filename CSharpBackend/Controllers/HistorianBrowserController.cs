using System;
using Microsoft.AspNetCore.Mvc;
using Npgsql;
using OpcDaWebBrowser.Services.HistorianIngest.Config;

namespace OpcDaWebBrowser.Controllers;

/// <summary>
/// Lightweight historian browser for SCADA-style multi-tag trends.
/// </summary>
[ApiController]
[Route("api/historian-browser")]
public class HistorianBrowserController : ControllerBase
{
    private readonly ILogger<HistorianBrowserController> _logger;
    private readonly HistorianConfig _config;

    public HistorianBrowserController(ILogger<HistorianBrowserController> logger, HistorianConfig config)
    {
        _logger = logger;
        _config = config;
    }

    /// <summary>
    /// List distinct historian tags with optional sample_source and text filter.
    /// </summary>
    [HttpGet("tags")]
    public async Task<IActionResult> GetTags([FromQuery] string? source = null, [FromQuery] string? search = null, [FromQuery] int limit = 200)
    {
        try
        {
            await using var conn = new NpgsqlConnection(_config.Database.ConnectionString);
            await conn.OpenAsync();

                        var baseSql = @"SELECT tag_id, sample_source, MAX(time) AS last_time, COUNT(*) AS total
FROM historian_raw.historian_timeseries
WHERE 1=1";

                        if (!string.IsNullOrWhiteSpace(source))
                                baseSql += " AND sample_source = @source";
            if (!string.IsNullOrWhiteSpace(search))
                baseSql += " AND tag_id ILIKE @search";

            baseSql += @"
GROUP BY tag_id, sample_source
ORDER BY last_time DESC
LIMIT @limit";

            await using var cmd = new NpgsqlCommand(baseSql, conn);
            cmd.Parameters.AddWithValue("limit", limit <= 0 ? 200 : Math.Min(limit, 2000));
            if (!string.IsNullOrWhiteSpace(source)) cmd.Parameters.AddWithValue("source", source);
            if (!string.IsNullOrWhiteSpace(search)) cmd.Parameters.AddWithValue("search", $"%{search}%");

            var tags = new List<HistorianTagRow>();
            await using var reader = await cmd.ExecuteReaderAsync();
            while (await reader.ReadAsync())
            {
                tags.Add(new HistorianTagRow
                {
                    TagId = reader.GetString(0),
                    SampleSource = reader.GetString(1),
                    LastTime = reader.IsDBNull(2) ? null : reader.GetDateTime(2),
                    Total = reader.IsDBNull(3) ? 0 : reader.GetInt64(3)
                });
            }

            return Ok(new { success = true, data = tags });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to list historian tags");
            return StatusCode(500, new { success = false, error = ex.Message });
        }
    }

    /// <summary>
    /// Fetch trend points for multiple tags (optionally filtered by sample_source).
    /// </summary>
    [HttpPost("trends")]
    public async Task<IActionResult> GetTrends([FromBody] HistorianBrowserTrendRequest request)
    {
        if (request.TagIds == null || request.TagIds.Count == 0)
            return BadRequest(new { success = false, error = "No tagIds supplied" });

        if (!DateTimeOffset.TryParse(request.StartTime, out var startDto))
            return BadRequest(new { success = false, error = "Invalid startTime format" });

        if (!DateTimeOffset.TryParse(request.EndTime, out var endDto))
            return BadRequest(new { success = false, error = "Invalid endTime format" });

        var startUtc = startDto.UtcDateTime;
        var endUtc = endDto.UtcDateTime;

        try
        {
            await using var conn = new NpgsqlConnection(_config.Database.ConnectionString);
            await conn.OpenAsync();

            var results = new Dictionary<string, List<HistorianBrowserTrendPoint>>();

            foreach (var tagId in request.TagIds)
            {
                var sql = @"SELECT time, value_num, value_text, value_bool, quality
                            FROM historian_raw.historian_timeseries
                            WHERE tag_id = @tagId
                              " + (string.IsNullOrWhiteSpace(request.SampleSource) ? "" : " AND sample_source = @source") + @"
                              AND time BETWEEN @startTime AND @endTime
                            ORDER BY time ASC
                            LIMIT @maxPoints";

                await using var cmd = new NpgsqlCommand(sql, conn);
                cmd.Parameters.AddWithValue("tagId", tagId);
                cmd.Parameters.AddWithValue("startTime", startUtc);
                cmd.Parameters.AddWithValue("endTime", endUtc);
                cmd.Parameters.AddWithValue("maxPoints", request.MaxPoints <= 0 ? 1000 : Math.Min(request.MaxPoints, 5000));
                if (!string.IsNullOrWhiteSpace(request.SampleSource)) cmd.Parameters.AddWithValue("source", request.SampleSource);

                var points = new List<HistorianBrowserTrendPoint>();
                await using var reader = await cmd.ExecuteReaderAsync();
                while (await reader.ReadAsync())
                {
                    object? rawNum = reader.IsDBNull(1) ? null : reader.GetValue(1);
                    object? rawText = reader.IsDBNull(2) ? null : reader.GetValue(2);
                    object? rawBool = reader.IsDBNull(3) ? null : reader.GetValue(3);
                    object? rawQuality = reader.IsDBNull(4) ? null : reader.GetValue(4);

                    object? value = null;
                    if (rawNum != null)
                    {
                        // Normalize numeric types to double (handles int/long/decimal)
                        if (rawNum is IConvertible)
                        {
                            try { value = Convert.ToDouble(rawNum); } catch { value = rawNum; }
                        }
                        else value = rawNum;
                    }
                    else if (rawText != null)
                    {
                        value = rawText.ToString();
                    }
                    else if (rawBool != null)
                    {
                        value = rawBool;
                    }

                    int quality = 0;
                    if (rawQuality is IConvertible)
                    {
                        try { quality = Convert.ToInt32(rawQuality); } catch { quality = 0; }
                    }

                    points.Add(new HistorianBrowserTrendPoint
                    {
                        Time = reader.GetDateTime(0),
                        Value = value,
                        Quality = quality
                    });
                }

                results[tagId] = points;
            }

            return Ok(new { success = true, data = results });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to fetch historian trends");
            return StatusCode(500, new { success = false, error = ex.Message });
        }
    }
}

public class HistorianTagRow
{
    public string TagId { get; set; } = string.Empty;
    public string SampleSource { get; set; } = string.Empty;
    public DateTime? LastTime { get; set; }
    public long Total { get; set; }
}

public class HistorianBrowserTrendRequest
{
    public List<string> TagIds { get; set; } = new();
    public string StartTime { get; set; } = string.Empty;
    public string EndTime { get; set; } = string.Empty;
    public int MaxPoints { get; set; } = 1000;
    public string? SampleSource { get; set; }
}

public class HistorianBrowserTrendPoint
{
    public DateTime Time { get; set; }
    public object? Value { get; set; }
    public int Quality { get; set; }
}
