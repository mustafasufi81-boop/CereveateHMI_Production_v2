using Microsoft.AspNetCore.Mvc;
using OpcDaWebBrowser.Services.Health;

namespace OpcDaWebBrowser.Controllers;

/// <summary>
/// Health monitoring API - returns cached system health metrics
/// ZERO-LOCK architecture: Reads volatile fields only
/// Enterprise-grade: <1ms response time, supports 10,000+ tags
/// </summary>
[ApiController]
[Route("api/[controller]")]
public class HealthController : ControllerBase
{
    private readonly IHealthStatusService _healthService;
    private readonly ILogger<HealthController> _logger;

    public HealthController(
        IHealthStatusService healthService,
        ILogger<HealthController> logger)
    {
        _healthService = healthService;
        _logger = logger;
    }

    /// <summary>
    /// GET /api/health - Complete system health snapshot
    /// Returns: JSON with overall status + all subsystem metrics
    /// Response time: <1ms (lock-free volatile read)
    /// Called by JavaScript every 3 seconds when health tab active
    /// </summary>
    [HttpGet]
    public ActionResult GetHealth()
    {
        try
        {
            var snapshot = _healthService.GetCurrentSnapshot();
            return Ok(snapshot);
        }
        catch (Exception ex)
        {
            _logger.LogError($"❌ Health API error: {ex.Message}");
            return StatusCode(500, new { error = "Failed to retrieve health metrics" });
        }
    }

    /// <summary>
    /// GET /api/health/opc - OPC subsystem health only
    /// </summary>
    [HttpGet("opc")]
    public ActionResult<OpcHealth> GetOpcHealth()
    {
        try
        {
            var snapshot = _healthService.GetCurrentSnapshot();
            return Ok(snapshot.Opc);
        }
        catch (Exception ex)
        {
            _logger.LogError($"❌ OPC health API error: {ex.Message}");
            return StatusCode(500, new { error = "Failed to retrieve OPC health" });
        }
    }

    /// <summary>
    /// GET /api/health/dbwriter - Database writer health only
    /// </summary>
    [HttpGet("dbwriter")]
    public ActionResult<DbWriterHealth> GetDbWriterHealth()
    {
        try
        {
            var snapshot = _healthService.GetCurrentSnapshot();
            return Ok(snapshot.DbWriter);
        }
        catch (Exception ex)
        {
            _logger.LogError($"❌ DB writer health API error: {ex.Message}");
            return StatusCode(500, new { error = "Failed to retrieve DB writer health" });
        }
    }

    /// <summary>
    /// GET /api/health/spool - Spool manager health only
    /// </summary>
    [HttpGet("spool")]
    public ActionResult<SpoolHealth> GetSpoolHealth()
    {
        try
        {
            var snapshot = _healthService.GetCurrentSnapshot();
            return Ok(snapshot.Spool);
        }
        catch (Exception ex)
        {
            _logger.LogError($"❌ Spool health API error: {ex.Message}");
            return StatusCode(500, new { error = "Failed to retrieve spool health" });
        }
    }

    /// <summary>
    /// GET /api/health/archiver - Archiver health only
    /// </summary>
    [HttpGet("archiver")]
    public ActionResult<ArchiverHealth> GetArchiverHealth()
    {
        try
        {
            var snapshot = _healthService.GetCurrentSnapshot();
            return Ok(snapshot.Archiver);
        }
        catch (Exception ex)
        {
            _logger.LogError($"❌ Archiver health API error: {ex.Message}");
            return StatusCode(500, new { error = "Failed to retrieve archiver health" });
        }
    }

    /// <summary>
    /// GET /api/health/dispatcher — OPC STA Dispatcher metrics
    /// Returns: threadId, apartment (STA/MTA), queueDepth, maxQueueDepth,
    ///          operationsProcessed, timeoutCount, state, lastSuccess, lastHeartbeat
    /// Lock-free: <1ms response. Called by Section H tests.
    /// </summary>
    [HttpGet("dispatcher")]
    public ActionResult<DispatcherHealth> GetDispatcherHealth()
    {
        try
        {
            var snapshot = _healthService.GetCurrentSnapshot();
            return Ok(snapshot.Dispatcher);
        }
        catch (Exception ex)
        {
            _logger.LogError($"❌ Dispatcher health API error: {ex.Message}");
            return StatusCode(500, new { error = "Failed to retrieve dispatcher health" });
        }
    }

    /// <summary>
    /// GET /api/health/resources - System resources health only
    /// </summary>
    [HttpGet("resources")]
    public ActionResult<ResourceHealth> GetResourceHealth()
    {
        try
        {
            var snapshot = _healthService.GetCurrentSnapshot();
            return Ok(snapshot.Resources);
        }
        catch (Exception ex)
        {
            _logger.LogError($"❌ Resource health API error: {ex.Message}");
            return StatusCode(500, new { error = "Failed to retrieve resource health" });
        }
    }
}
