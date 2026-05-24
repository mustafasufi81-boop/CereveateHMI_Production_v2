using Microsoft.AspNetCore.Mvc;
using PlcGateway.Services;

namespace OpcDaWebBrowser.Controllers;

/// <summary>
/// PLC Gateway REST API - Worker Management
/// 
/// Endpoints for managing PLC workers (start/stop/status)
/// NOTE: Data endpoints are in PlcController.cs
/// </summary>
[ApiController]
[Route("api/plc-gateway")]
public class PlcGatewayController : ControllerBase
{
    private readonly PlcGatewayManager _gateway;
    private readonly ILogger<PlcGatewayController> _logger;

    public PlcGatewayController(
        PlcGatewayManager gateway,
        ILogger<PlcGatewayController> logger)
    {
        _gateway = gateway;
        _logger = logger;
    }

    // ═══════════════════════════════════════════════════════════════════
    // DATA ENDPOINTS
    // ═══════════════════════════════════════════════════════════════════

    /// <summary>
    /// Get all values from all PLCs
    /// </summary>
    [HttpGet("values")]
    public IActionResult GetAllValues()
    {
        var values = _gateway.GetAllValues();
        return Ok(new
        {
            timestamp = DateTime.UtcNow,
            count = values.Count,
            values
        });
    }

    /// <summary>
    /// Get values from specific PLC
    /// </summary>
    [HttpGet("values/{plcId}")]
    public IActionResult GetPlcValues(string plcId)
    {
        var values = _gateway.GetPlcValues(plcId);
        
        if (values.Count == 0)
        {
            var status = _gateway.GetStatus(plcId);
            if (status == null)
            {
                return NotFound(new { error = $"PLC '{plcId}' not found" });
            }
        }
        
        return Ok(new
        {
            plcId,
            timestamp = DateTime.UtcNow,
            count = values.Count,
            values
        });
    }

    /// <summary>
    /// Get values from specific plant (all PLCs in plant)
    /// </summary>
    [HttpGet("values/plant/{plantId}")]
    public IActionResult GetPlantValues(string plantId)
    {
        var values = _gateway.GetPlantValues(plantId);
        return Ok(new
        {
            plantId,
            timestamp = DateTime.UtcNow,
            count = values.Count,
            values
        });
    }

    /// <summary>
    /// Get specific tag value
    /// </summary>
    [HttpGet("values/{plcId}/{address}")]
    public IActionResult GetTagValue(string plcId, string address)
    {
        // Decode URL-encoded address (e.g., DB10.DBD0)
        address = Uri.UnescapeDataString(address);
        
        var value = _gateway.GetValue(plcId, address);
        
        if (value == null)
        {
            return NotFound(new { error = $"Tag '{address}' not found in PLC '{plcId}'" });
        }
        
        return Ok(value);
    }

    // ═══════════════════════════════════════════════════════════════════
    // STATUS ENDPOINTS
    // ═══════════════════════════════════════════════════════════════════

    /// <summary>
    /// Get gateway summary
    /// </summary>
    [HttpGet("status")]
    public IActionResult GetGatewayStatus()
    {
        var summary = _gateway.GetSummary();
        var workers = _gateway.GetAllStatus();
        
        return Ok(new
        {
            timestamp = DateTime.UtcNow,
            summary,
            workers
        });
    }

    /// <summary>
    /// Get all worker status
    /// </summary>
    [HttpGet("workers")]
    public IActionResult GetAllWorkerStatus()
    {
        var workers = _gateway.GetAllStatus();
        return Ok(new
        {
            timestamp = DateTime.UtcNow,
            count = workers.Count,
            workers
        });
    }

    /// <summary>
    /// Get specific worker status
    /// </summary>
    [HttpGet("workers/{plcId}")]
    public IActionResult GetWorkerStatus(string plcId)
    {
        var status = _gateway.GetStatus(plcId);
        
        if (status == null)
        {
            return NotFound(new { error = $"PLC '{plcId}' not found" });
        }
        
        return Ok(status);
    }

    // ═══════════════════════════════════════════════════════════════════
    // CONTROL ENDPOINTS
    // ═══════════════════════════════════════════════════════════════════

    /// <summary>
    /// Restart specific PLC worker
    /// </summary>
    [HttpPost("workers/{plcId}/restart")]
    public async Task<IActionResult> RestartWorker(string plcId)
    {
        var success = await _gateway.RestartPlcAsync(plcId);
        
        if (!success)
        {
            return NotFound(new { error = $"PLC '{plcId}' not found or restart failed" });
        }
        
        _logger.LogInformation("[API] Restarted PLC worker: {PlcId}", plcId);
        return Ok(new { message = $"PLC '{plcId}' restarted" });
    }

    /// <summary>
    /// Remove specific PLC worker
    /// </summary>
    [HttpDelete("workers/{plcId}")]
    public async Task<IActionResult> RemoveWorker(string plcId)
    {
        var success = await _gateway.RemovePlcAsync(plcId);
        
        if (!success)
        {
            return NotFound(new { error = $"PLC '{plcId}' not found" });
        }
        
        _logger.LogInformation("[API] Removed PLC worker: {PlcId}", plcId);
        return Ok(new { message = $"PLC '{plcId}' removed" });
    }

    // ═══════════════════════════════════════════════════════════════════
    // HEALTH CHECK
    // ═══════════════════════════════════════════════════════════════════

    /// <summary>
    /// Health check endpoint
    /// </summary>
    [HttpGet("health")]
    public IActionResult HealthCheck()
    {
        var summary = _gateway.GetSummary();
        var isHealthy = summary.ConnectedPlcs > 0 || summary.TotalPlcs == 0;
        
        return Ok(new
        {
            status = isHealthy ? "healthy" : "degraded",
            timestamp = DateTime.UtcNow,
            totalPlcs = summary.TotalPlcs,
            connectedPlcs = summary.ConnectedPlcs,
            healthyPlcs = summary.HealthyPlcs,
            faultedPlcs = summary.FaultedPlcs
        });
    }
}
