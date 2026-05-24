using Microsoft.AspNetCore.Mvc;
using OpcDaWebBrowser.Services.OpcUa;

namespace OpcDaWebBrowser.Controllers;

/// <summary>
/// OPC UA management API - completely independent from OPC DA
/// </summary>
[ApiController]
[Route("api/[controller]")]
public class OpcUaController : ControllerBase
{
    private readonly ILogger<OpcUaController> _logger;
    private readonly OpcUaService _uaService;
    private readonly OpcUaDiscovery _uaDiscovery;

    public OpcUaController(
        ILogger<OpcUaController> logger,
        OpcUaService uaService,
        OpcUaDiscovery uaDiscovery)
    {
        _logger = logger;
        _uaService = uaService;
        _uaDiscovery = uaDiscovery;
    }

    /// <summary>
    /// Discover available OPC UA servers
    /// </summary>
    [HttpGet("discover")]
    public IActionResult DiscoverServers([FromQuery] string? hostname = null)
    {
        try
        {
            var servers = _uaDiscovery.DiscoverServers(hostname);
            return Ok(new
            {
                success = true,
                servers,
                count = servers.Count
            });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "UA discovery failed");
            return StatusCode(500, new { success = false, error = ex.Message });
        }
    }

    /// <summary>
    /// Get connection status
    /// </summary>
    [HttpGet("status")]
    public IActionResult GetStatus()
    {
        var stats = _uaService.GetStats();
        return Ok(new
        {
            success = true,
            isConnected = stats.IsConnected,
            endpoint = stats.Endpoint,
            connectedAt = stats.ConnectedAt,
            monitoredTags = stats.MonitoredTagCount,
            performance = new
            {
                samplesRead = stats.TotalSamplesRead,
                samplesWritten = stats.TotalSamplesWritten,
                errors = stats.TotalErrors
            }
        });
    }

    /// <summary>
    /// Connect to OPC UA server
    /// </summary>
    [HttpPost("connect")]
    public async Task<IActionResult> Connect([FromBody] ConnectRequest request)
    {
        try
        {
            _logger.LogInformation("Connecting to UA server: {Endpoint}", request.Endpoint);

            var success = await _uaService.ConnectAsync(request.Endpoint, HttpContext.RequestAborted);

            if (success)
            {
                return Ok(new
                {
                    success = true,
                    message = $"Connected to {request.Endpoint}",
                    endpoint = request.Endpoint
                });
            }
            else
            {
                return BadRequest(new
                {
                    success = false,
                    error = "Connection failed - check logs for details"
                });
            }
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "UA connect failed");
            return StatusCode(500, new { success = false, error = ex.Message });
        }
    }

    /// <summary>
    /// Disconnect from OPC UA server
    /// </summary>
    [HttpPost("disconnect")]
    public IActionResult Disconnect()
    {
        try
        {
            _uaService.Disconnect();
            return Ok(new
            {
                success = true,
                message = "Disconnected successfully"
            });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "UA disconnect failed");
            return StatusCode(500, new { success = false, error = ex.Message });
        }
    }

    /// <summary>
    /// Browse available tags from connected server
    /// </summary>
    [HttpGet("browse")]
    public IActionResult BrowseTags()
    {
        try
        {
            if (!_uaService.IsConnected)
            {
                return BadRequest(new
                {
                    success = false,
                    error = "Not connected to any UA server"
                });
            }

            var tags = _uaService.BrowseTags();

            return Ok(new
            {
                success = true,
                tags,
                count = tags.Count
            });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "UA browse failed");
            return StatusCode(500, new { success = false, error = ex.Message });
        }
    }

    /// <summary>
    /// Browse available tags with display names (NodeId + DisplayName)
    /// </summary>
    [HttpGet("browse-detailed")]
    public IActionResult BrowseTagsWithNames()
    {
        try
        {
            if (!_uaService.IsConnected)
            {
                return BadRequest(new
                {
                    success = false,
                    error = "Not connected to any UA server"
                });
            }

            var tags = _uaService.BrowseTagsWithNames();

            return Ok(new
            {
                success = true,
                tags,
                count = tags.Count
            });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "UA browse-detailed failed");
            return StatusCode(500, new { success = false, error = ex.Message });
        }
    }

    /// <summary>
    /// Start monitoring specific tags (begins writing to historian DB)
    /// </summary>
    [HttpPost("monitor")]
    public IActionResult StartMonitoring([FromBody] MonitorRequest request)
    {
        try
        {
            if (!_uaService.IsConnected)
            {
                return BadRequest(new
                {
                    success = false,
                    error = "Not connected to any UA server"
                });
            }

            _uaService.StartMonitoring(request.TagIds, request.IntervalMs);

            return Ok(new
            {
                success = true,
                message = $"Monitoring {request.TagIds.Count} tags @ {request.IntervalMs}ms",
                tagCount = request.TagIds.Count,
                intervalMs = request.IntervalMs
            });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "UA monitor start failed");
            return StatusCode(500, new { success = false, error = ex.Message });
        }
    }

    /// <summary>
    /// Get current tag values
    /// </summary>
    [HttpPost("values")]
    public IActionResult GetTagValues([FromBody] ValuesRequest request)
    {
        try
        {
            var values = _uaService.GetTagValues(request.TagIds);

            return Ok(new
            {
                success = true,
                values,
                count = values.Count
            });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Get values failed");
            return StatusCode(500, new { success = false, error = ex.Message });
        }
    }

    /// <summary>
    /// Quick connect to default Rockwell bridge
    /// </summary>
    [HttpPost("quick-connect")]
    public async Task<IActionResult> QuickConnect()
    {
        try
        {
            var endpoint = _uaDiscovery.GetDefaultEndpoint();
            _logger.LogInformation("Quick connecting to {Endpoint}", endpoint);

            var success = await _uaService.ConnectAsync(endpoint, HttpContext.RequestAborted);

            if (success)
            {
                return Ok(new
                {
                    success = true,
                    message = $"Connected to Rockwell OPC Bridge",
                    endpoint
                });
            }
            else
            {
                return BadRequest(new
                {
                    success = false,
                    error = "Connection failed - ensure RockwellOpcBridge is running"
                });
            }
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Quick connect failed");
            return StatusCode(500, new { success = false, error = ex.Message });
        }
    }
}

// Request models
public class ConnectRequest
{
    public string Endpoint { get; set; } = "";
}

public class MonitorRequest
{
    public List<string> TagIds { get; set; } = new();
    public int IntervalMs { get; set; } = 1000;
}

public class ValuesRequest
{
    public List<string>? TagIds { get; set; }
}
