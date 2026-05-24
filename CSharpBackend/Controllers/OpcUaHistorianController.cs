using Microsoft.AspNetCore.Mvc;
using Npgsql;
using OpcDaWebBrowser.Services.HistorianIngest.Config;

namespace OpcDaWebBrowser.Controllers;

/// <summary>
/// OPC UA Historian data retrieval
/// </summary>
[ApiController]
[Route("api/opcua-historian")]
public class OpcUaHistorianController : ControllerBase
{
    private readonly ILogger<OpcUaHistorianController> _logger;
    private readonly HistorianConfig _config;

    public OpcUaHistorianController(ILogger<OpcUaHistorianController> logger, HistorianConfig config)
    {
        _logger = logger;
        _config = config;
    }

    /// <summary>
    /// Get trend data for tags from historian DB (OPC_UA source)
    /// </summary>
    [HttpPost("trends")]
    public async Task<IActionResult> GetTrends([FromBody] TrendRequest request)
    {
        try
        {
            await using var conn = new NpgsqlConnection(_config.Database.ConnectionString);
            await conn.OpenAsync();

            var results = new Dictionary<string, List<TrendPoint>>();

            foreach (var tagId in request.TagIds)
            {
                var sql = @"
                    SELECT time, value_num, value_text, value_bool, quality
                    FROM historian_raw.historian_timeseries
                    WHERE tag_id = @tagId 
                      AND sample_source = 'OPC_UA'
                      AND time BETWEEN @startTime AND @endTime
                    ORDER BY time ASC
                    LIMIT @maxPoints";

                await using var cmd = new NpgsqlCommand(sql, conn);
                cmd.Parameters.AddWithValue("tagId", tagId);
                cmd.Parameters.AddWithValue("startTime", request.StartTime);
                cmd.Parameters.AddWithValue("endTime", request.EndTime);
                cmd.Parameters.AddWithValue("maxPoints", request.MaxPoints);

                var points = new List<TrendPoint>();
                await using var reader = await cmd.ExecuteReaderAsync();
                
                while (await reader.ReadAsync())
                {
                    var time = reader.GetDateTime(0);

                    object? rawNum = reader.IsDBNull(1) ? null : reader.GetValue(1);
                    object? rawText = reader.IsDBNull(2) ? null : reader.GetValue(2);
                    object? rawBool = reader.IsDBNull(3) ? null : reader.GetValue(3);
                    object? rawQuality = reader.IsDBNull(4) ? null : reader.GetValue(4);

                    object? value = null;
                    if (rawNum != null)
                    {
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

                    points.Add(new TrendPoint
                    {
                        Time = time,
                        Value = value,
                        Quality = quality
                    });
                }

                results[tagId] = points;
            }

            return Ok(new
            {
                success = true,
                data = results,
                count = results.Sum(r => r.Value.Count)
            });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to get OPC UA trends");
            return StatusCode(500, new { success = false, error = ex.Message });
        }
    }

    /// <summary>
    /// Get latest values for tags from historian
    /// </summary>
    [HttpPost("latest")]
    public async Task<IActionResult> GetLatest([FromBody] LatestRequest request)
    {
        try
        {
            await using var conn = new NpgsqlConnection(_config.Database.ConnectionString);
            await conn.OpenAsync();

            var results = new Dictionary<string, LatestValue>();

            foreach (var tagId in request.TagIds)
            {
                var sql = @"
                    SELECT time, value_num, value_text, value_bool, quality
                    FROM historian_raw.historian_timeseries
                    WHERE tag_id = @tagId AND sample_source = 'OPC_UA'
                    ORDER BY time DESC
                    LIMIT 1";

                await using var cmd = new NpgsqlCommand(sql, conn);
                cmd.Parameters.AddWithValue("tagId", tagId);

                await using var reader = await cmd.ExecuteReaderAsync();
                
                if (await reader.ReadAsync())
                {
                    var time = reader.GetDateTime(0);

                    object? rawNum = reader.IsDBNull(1) ? null : reader.GetValue(1);
                    object? rawText = reader.IsDBNull(2) ? null : reader.GetValue(2);
                    object? rawBool = reader.IsDBNull(3) ? null : reader.GetValue(3);
                    object? rawQuality = reader.IsDBNull(4) ? null : reader.GetValue(4);

                    object? value = null;
                    if (rawNum != null)
                    {
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

                    results[tagId] = new LatestValue
                    {
                        Time = time,
                        Value = value,
                        Quality = quality
                    };
                }
            }

            return Ok(new
            {
                success = true,
                data = results
            });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to get latest OPC UA values");
            return StatusCode(500, new { success = false, error = ex.Message });
        }
    }
}

public class TrendRequest
{
    public List<string> TagIds { get; set; } = new();
    public DateTime StartTime { get; set; }
    public DateTime EndTime { get; set; }
    public int MaxPoints { get; set; } = 1000;
}

public class TrendPoint
{
    public DateTime Time { get; set; }
    public object? Value { get; set; }
    public int Quality { get; set; }
}

public class LatestRequest
{
    public List<string> TagIds { get; set; } = new();
}

public class LatestValue
{
    public DateTime Time { get; set; }
    public object? Value { get; set; }
    public int Quality { get; set; }
}
