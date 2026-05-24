using Microsoft.AspNetCore.Mvc;
using OpcDaWebBrowser.Services;

namespace OpcDaWebBrowser.Controllers;

[ApiController]
[Route("api/[controller]")]
public class OpcController : ControllerBase
{
    private readonly OpcDaService _opcService;

    // TagValuesPoolService intentionally NOT injected here.
    // The HMI reads directly from OpcDaService.ReadAllTagValues() — the single source of truth
    // used by historian and MQTT. This guarantees the HMI sees ALL DB-enabled tags, not just
    // those that happened to be subscribed when DataLoggingService last created its connection.
    public OpcController(OpcDaService opcService)
    {
        _opcService = opcService;
    }

    [HttpGet("servers")]
    public ActionResult<List<string>> GetServers()
    {
        try
        {
            // Hardcoded list - no COM calls that crash
            var servers = new List<string>
            {
                "Matrikon.OPC.Simulation.1",
                "Kepware.KEPServerEX.V6", 
                "RSLinx OPC Server"
            };
            return Ok(servers);
        }
        catch (Exception ex)
        {
            return StatusCode(500, $"Error: {ex.Message}");
        }
    }

    /// <summary>
    /// Get ALL current tag values directly from OpcDaService — the single source of truth.
    /// This is the same snapshot read by the historian and MQTT publisher.
    /// Tags returned = all tags currently subscribed on the main OPC connection,
    /// which is driven by historian_meta.tag_master (DB-driven, no manual JSON config needed).
    /// </summary>
    [HttpGet("values")]
    [ResponseCache(Duration = 1, Location = ResponseCacheLocation.Any, NoStore = false)]
    public ActionResult GetAllTagValues()
    {
        try
        {
            var allValues = _opcService.ReadAllTagValues();

            return Ok(new
            {
                count = allValues.Count,
                lastUpdate = DateTime.UtcNow,
                timestamp = DateTime.Now,
                tags = allValues.Select(v => new
                {
                    tagId = v.ItemID,
                    value = v.Value,
                    quality = v.Quality,
                    timestamp = v.Timestamp
                }).ToList()
            });
        }
        catch (Exception ex)
        {
            return StatusCode(500, new { error = ex.Message });
        }
    }

    /// <summary>
    /// Get OPC connection status
    /// </summary>
    [HttpGet("status")]
    public ActionResult GetStatus()
    {
        try
        {
            var connection = _opcService.GetActiveConnection();
            var isConnected = connection != null && connection.IsConnected;
            var tagCount = _opcService.ReadAllTagValues().Count;

            return Ok(new
            {
                connected = isConnected,
                serverName = connection?.ServerProgID ?? "Not connected",
                tagCount = tagCount,
                lastUpdate = DateTime.UtcNow
            });
        }
        catch (Exception ex)
        {
            return StatusCode(500, new { error = ex.Message });
        }
    }
}