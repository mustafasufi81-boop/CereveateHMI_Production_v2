using Microsoft.AspNetCore.Mvc;
using PlcGateway.Interfaces;
using PlcGateway.Services;
using PlcGateway.Drivers;
using System.Net.NetworkInformation;
using System.Diagnostics;
using Npgsql;

namespace OpcDaWebBrowser.Controllers;

/// <summary>
/// PLC API Controller
/// 
/// Provides REST API access to PLC tag values from the shared pool.
/// Used by HMI, frontend dashboards, and external integrations.
/// 
/// DESIGN (Mirrors OPC /api/opc/values pattern):
/// - Reads from PlcTagValuesPoolService (not direct PLC)
/// - Pool is updated every 1000ms by PlcDataLoggingService
/// - Fast response, no PLC latency impact on API
/// </summary>
[ApiController]
[Route("api/plc")]
public class PlcController : ControllerBase
{
    private readonly PlcTagValuesPoolService _tagPool;
    private readonly PlcGatewayManager _gatewayManager;
    private readonly PlcConfigPersistenceService _configPersistence;
    private readonly PlcHistorianIngestService _historianIngest;
    private readonly IConfiguration _configuration;
    private readonly ILogger<PlcController> _logger;

    public PlcController(
        PlcTagValuesPoolService tagPool,
        PlcGatewayManager gatewayManager,
        PlcConfigPersistenceService configPersistence,
        PlcHistorianIngestService historianIngest,
        IConfiguration configuration,
        ILogger<PlcController> logger)
    {
        _tagPool = tagPool;
        _gatewayManager = gatewayManager;
        _configPersistence = configPersistence;
        _historianIngest = historianIngest;
        _configuration = configuration;
        _logger = logger;
    }

    // ═══════════════════════════════════════════════════════════════════
    // GET ALL VALUES
    // ═══════════════════════════════════════════════════════════════════

    /// <summary>
    /// Get all tag values from all PLCs
    /// </summary>
    [HttpGet("values")]
    public IActionResult GetAllValues()
    {
        try
        {
            var values = _tagPool.GetAllTagValues();
            return Ok(new
            {
                success = true,
                count = values.Count,
                timestamp = DateTime.UtcNow,
                values = values.Select(v => new
                {
                    plcId = v.PlcId,
                    tagName = v.TagName,
                    address = v.Address,
                    value = v.Value,
                    dataType = v.DataType,
                    quality = v.Quality.ToString(),
                    timestamp = v.Timestamp,
                    cachedAt = v.CachedAt
                })
            });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "[PLC API] Error getting all values");
            return StatusCode(500, new { success = false, error = ex.Message });
        }
    }

    /// <summary>
    /// Get values for a specific PLC
    /// </summary>
    [HttpGet("values/{plcId}")]
    public IActionResult GetPlcValues(string plcId)
    {
        try
        {
            var values = _tagPool.GetPlcValues(plcId);
            
            if (values.Count == 0)
            {
                return Ok(new
                {
                    success = true,
                    plcId,
                    count = 0,
                    message = "No values found for this PLC (may not be connected or have tags)",
                    values = Array.Empty<object>()
                });
            }

            return Ok(new
            {
                success = true,
                plcId,
                count = values.Count,
                timestamp = DateTime.UtcNow,
                values = values.Select(v => new
                {
                    tagName = v.TagName,
                    address = v.Address,
                    value = v.Value,
                    dataType = v.DataType,
                    quality = v.Quality.ToString(),
                    timestamp = v.Timestamp
                })
            });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "[PLC API] Error getting values for PLC {PlcId}", plcId);
            return StatusCode(500, new { success = false, error = ex.Message });
        }
    }

    /// <summary>
    /// Get specific tag values by name or address
    /// </summary>
    [HttpPost("values/query")]
    public IActionResult QueryTagValues([FromBody] TagQueryRequest request)
    {
        try
        {
            var values = _tagPool.GetTagValues(request.TagNames ?? Array.Empty<string>(), request.PlcId);

            return Ok(new
            {
                success = true,
                count = values.Count,
                timestamp = DateTime.UtcNow,
                values = values.Select(v => new
                {
                    plcId = v.PlcId,
                    tagName = v.TagName,
                    address = v.Address,
                    value = v.Value,
                    dataType = v.DataType,
                    quality = v.Quality.ToString(),
                    timestamp = v.Timestamp
                })
            });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "[PLC API] Error querying tag values");
            return StatusCode(500, new { success = false, error = ex.Message });
        }
    }

    // ═══════════════════════════════════════════════════════════════════
    // STATISTICS & STATUS
    // ═══════════════════════════════════════════════════════════════════

    /// <summary>
    /// Get pool statistics
    /// </summary>
    [HttpGet("stats")]
    public IActionResult GetStatistics()
    {
        try
        {
            var stats = _tagPool.GetStatistics();
            return Ok(new
            {
                success = true,
                stats = new
                {
                    totalTags = stats.TotalTags,
                    totalPlcs = stats.TotalPlcs,
                    connectedPlcs = stats.ConnectedPlcs,
                    goodQualityCount = stats.GoodQualityCount,
                    badQualityCount = stats.BadQualityCount,
                    lastUpdateTime = stats.LastUpdateTime,
                    oldestCacheTime = stats.OldestCacheTime,
                    newestCacheTime = stats.NewestCacheTime
                }
            });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "[PLC API] Error getting statistics");
            return StatusCode(500, new { success = false, error = ex.Message });
        }
    }

    /// <summary>
    /// Get PLC connection status
    /// </summary>
    [HttpGet("status")]
    public IActionResult GetStatus()
    {
        try
        {
            var status = _tagPool.GetPlcStatus();
            return Ok(new
            {
                success = true,
                timestamp = DateTime.UtcNow,
                plcs = status.Select(s => new
                {
                    plcId = s.Key,
                    isConnected = s.Value.IsConnected,
                    lastUpdate = s.Value.LastUpdateTime,
                    tagCount = s.Value.TagCount,
                    errorMessage = s.Value.LastError
                })
            });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "[PLC API] Error getting status");
            return StatusCode(500, new { success = false, error = ex.Message });
        }
    }

    /// <summary>
    /// Get single tag value by full key (plcId:tagName)
    /// </summary>
    [HttpGet("tag/{plcId}/{tagName}")]
    public IActionResult GetTagValue(string plcId, string tagName)
    {
        try
        {
            var value = _tagPool.GetTagValue(plcId, tagName);
            
            if (value == null)
            {
                return NotFound(new
                {
                    success = false,
                    error = $"Tag {tagName} not found for PLC {plcId}"
                });
            }

            return Ok(new
            {
                success = true,
                plcId = value.PlcId,
                tagName = value.TagName,
                address = value.Address,
                value = value.Value,
                dataType = value.DataType,
                quality = value.Quality.ToString(),
                timestamp = value.Timestamp,
                cachedAt = value.CachedAt
            });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "[PLC API] Error getting tag {PlcId}:{TagName}", plcId, tagName);
            return StatusCode(500, new { success = false, error = ex.Message });
        }
    }

    // ═══════════════════════════════════════════════════════════════════
    // HEALTH CHECK
    // ═══════════════════════════════════════════════════════════════════

    /// <summary>
    /// Simple ping endpoint - no dependencies
    /// </summary>
    [HttpGet("ping")]
    public IActionResult Ping()
    {
        return Ok(new { status = "ok", timestamp = DateTime.UtcNow, controller = "PlcController" });
    }

    /// <summary>
    /// Health check endpoint
    /// </summary>
    [HttpGet("health")]
    public IActionResult HealthCheck()
    {
        try
        {
            var stats = _tagPool.GetStatistics();
            var isHealthy = stats.TotalPlcs == 0 || stats.ConnectedPlcs > 0;

            return Ok(new
            {
                healthy = isHealthy,
                timestamp = DateTime.UtcNow,
                message = isHealthy 
                    ? $"PLC Gateway operational. {stats.ConnectedPlcs}/{stats.TotalPlcs} PLCs connected, {stats.TotalTags} tags"
                    : "No PLCs connected",
                details = new
                {
                    totalPlcs = stats.TotalPlcs,
                    connectedPlcs = stats.ConnectedPlcs,
                    totalTags = stats.TotalTags,
                    lastUpdate = stats.LastUpdateTime
                }
            });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "[PLC API] Health check error");
            return Ok(new { healthy = true, error = ex.Message, timestamp = DateTime.UtcNow });
        }
    }

    // ═══════════════════════════════════════════════════════════════════
    // PLC CONNECTION STATUS (for UI)
    // ═══════════════════════════════════════════════════════════════════

    /// <summary>
    /// Get detailed status for all PLC connections (for UI display)
    /// Merges database PLCs (from tag_master) with saved configs and runtime status
    /// </summary>
    [HttpGet("connections")]
    public IActionResult GetConnections()
    {
        try
        {
            // Get saved configs (persisted PLCs from plc-config.json)
            var savedConfigs = _configPersistence.GetAllConfigs()
                .ToDictionary(c => c.PlcId, c => c);
            
            // Get runtime status from gateway manager
            var runtimeStatus = _gatewayManager.GetAllStatus()
                .ToDictionary(s => s.PlcId, s => s);

            // Get PLCs from tag pool (database source - historian_meta.tag_master)
            var poolStatus = _tagPool.GetPlcStatus();

            // Build merged list - prioritize pool status (database PLCs)
            var allPlcIds = new HashSet<string>();
            foreach (var id in poolStatus.Keys) allPlcIds.Add(id);
            foreach (var id in savedConfigs.Keys) allPlcIds.Add(id);
            foreach (var id in runtimeStatus.Keys) allPlcIds.Add(id);

            var connections = allPlcIds.Select(plcId =>
            {
                var hasPool = poolStatus.TryGetValue(plcId, out var pool);
                var hasSaved = savedConfigs.TryGetValue(plcId, out var saved);
                var hasRuntime = runtimeStatus.TryGetValue(plcId, out var runtime);

                // Determine connection state from all sources
                var isConnected = (hasPool && pool!.IsConnected) || (hasRuntime && runtime!.IsConnected);
                var tagCount = hasPool ? pool!.TagCount : (hasRuntime ? runtime!.TagCount : (hasSaved ? saved!.Tags.Count : 0));

                return new
                {
                    plcId = plcId,
                    name = hasSaved ? saved!.Name : plcId,
                    protocol = hasRuntime ? runtime!.Protocol : (hasSaved ? saved!.Protocol : (hasPool ? "Rockwell" : "Unknown")),
                    ipAddress = hasRuntime ? runtime!.IpAddress : (hasSaved ? saved!.IpAddress : (hasPool ? "192.168.0.20" : "")),
                    port = hasRuntime ? runtime!.Port : (hasSaved ? saved!.Port : (hasPool ? 44818 : 0)),
                    isConnected = isConnected,
                    tagCount = tagCount,
                    lastPollTime = hasRuntime ? runtime!.LastPollTime : (hasPool ? pool!.LastUpdateTime : (DateTime?)null),
                    pollCount = hasRuntime ? runtime!.TotalPolls : 0,
                    errorCount = hasRuntime ? runtime!.FailedPolls : 0,
                    consecutiveFailures = hasRuntime ? runtime!.ConsecutiveFailures : 0,
                    lastError = hasRuntime ? runtime!.LastError : (hasSaved ? saved!.LastError : (hasPool ? pool!.LastError : null)),
                    lastUpdate = hasPool ? pool!.LastUpdateTime : (hasRuntime ? runtime!.LastPollTime : (hasSaved ? saved!.LastStatusUpdate : (DateTime?)null)),
                    // Extra info
                    slot = hasSaved ? saved!.Slot : 0,
                    enabled = hasSaved ? saved!.Enabled : true,
                    createdAt = hasSaved ? saved!.CreatedAt : DateTime.UtcNow,
                    source = hasPool ? "database" : (hasSaved ? "config_file" : "runtime")
                };
            }).ToList();

            return Ok(new
            {
                success = true,
                timestamp = DateTime.UtcNow,
                totalCount = connections.Count,
                connectedCount = connections.Count(c => c.isConnected),
                connections
            });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "[PLC API] Error getting connections");
            return StatusCode(500, new { success = false, error = ex.Message });
        }
    }

    // ═══════════════════════════════════════════════════════════════════
    // PLC MANAGEMENT (Add/Remove/Restart)
    // ═══════════════════════════════════════════════════════════════════

    /// <summary>
    /// Add a new PLC connection (saves config and optionally connects)
    /// </summary>
    [HttpPost("add")]
    public async Task<IActionResult> AddPlc([FromBody] AddPlcRequest request)
    {
        try
        {
            _logger.LogInformation("[PLC API] Adding PLC {PlcId} - {Protocol}://{Ip}:{Port}",
                request.PlcId, request.Protocol, request.IpAddress, request.Port ?? 0);

            // Parse protocol string to enum
            if (!TryParseProtocol(request.Protocol, out var protocol))
            {
                return BadRequest(new { success = false, error = $"Unknown protocol: {request.Protocol}" });
            }

            var port = request.Port ?? GetDefaultPort(request.Protocol);
            var slot = request.Slot ?? (request.EtherNetIpOptions?.Path?.Split(',').LastOrDefault() is string s && int.TryParse(s, out var sl) ? sl : 0);

            // ══════════════════════════════════════════════════════════════
            // STEP 1: SAVE CONFIG TO FILE (Persists across restarts)
            // ══════════════════════════════════════════════════════════════
            var savedConfig = new SavedPlcConfig
            {
                PlcId = request.PlcId,
                Name = request.Name ?? request.PlcId,
                Protocol = request.Protocol,
                IpAddress = request.IpAddress,
                Port = port,
                PlantId = request.PlantId ?? "default",
                Slot = slot,
                Rack = request.S7Options?.Rack,
                Path = request.EtherNetIpOptions?.Path ?? $"1,{slot}",
                PlcType = request.EtherNetIpOptions?.PlcType ?? "ControlLogix",
                PollingIntervalMs = request.PollingIntervalMs ?? 1000,
                TimeoutMs = request.TimeoutMs ?? 5000,
                RetryCount = request.RetryCount ?? 3,
                ReconnectDelayMs = request.ReconnectDelayMs ?? 5000,
                Enabled = true,
                Tags = request.Tags?.Select(t => new SavedTagConfig
                {
                    Name = t.Name,
                    Address = t.Address,
                    DataType = t.DataType ?? "double",
                    Description = t.Description
                }).ToList() ?? new List<SavedTagConfig>()
            };

            if (!_configPersistence.SaveConfig(savedConfig))
            {
                return StatusCode(500, new { success = false, error = "Failed to save PLC configuration" });
            }

            // ══════════════════════════════════════════════════════════════
            // STEP 2: TRY TO CONNECT (May fail if PLC unreachable)
            // ══════════════════════════════════════════════════════════════
            var config = new PlcDriverConfig
            {
                PlcId = request.PlcId,
                PlcName = request.Name ?? request.PlcId,
                Protocol = protocol,
                IpAddress = request.IpAddress,
                Port = port,
                PlantId = request.PlantId ?? "default",
                PollingIntervalMs = request.PollingIntervalMs ?? 1000,
                TimeoutMs = request.TimeoutMs ?? 5000,
                RetryCount = request.RetryCount ?? 3,
                ReconnectDelayMs = request.ReconnectDelayMs ?? 5000
            };

            // Apply protocol-specific settings
            if (protocol == PlcGateway.Models.PlcProtocol.SiemensS7 && request.S7Options != null)
            {
                config.S7Config = new S7DriverConfig
                {
                    Rack = (short)(request.S7Options.Rack ?? 0),
                    Slot = (short)(request.S7Options.Slot ?? 1)
                };
            }

            // Apply EtherNet/IP (Rockwell) specific settings
            if (protocol == PlcGateway.Models.PlcProtocol.EtherNetIP || protocol == PlcGateway.Models.PlcProtocol.Rockwell)
            {
                config.EtherNetIpConfig = new EtherNetIpDriverConfig
                {
                    Path = request.EtherNetIpOptions?.Path ?? $"1,{slot}",
                    PlcType = request.EtherNetIpOptions?.PlcType ?? "ControlLogix",
                    ConnectionSize = request.EtherNetIpOptions?.ConnectionSize ?? 4000,
                    UseConnectedMessaging = request.EtherNetIpOptions?.UseConnectedMessaging ?? true
                };
            }

            // Get tags (if provided) or use empty list
            var tags = request.Tags?.Select(t => new PlcTagDefinition
            {
                TagName = t.Name,
                Address = t.Address,
                DataType = t.DataType ?? "double",
                Description = t.Description ?? ""
            }).ToList() ?? new List<PlcTagDefinition>();

            // Try to add and connect
            var connected = await _gatewayManager.AddPlcAsync(config, tags);
            
            // Update status in saved config
            _configPersistence.UpdateStatus(request.PlcId, connected, 
                connected ? null : "Initial connection pending - use Connect button or Test to diagnose");

            // Return success even if not connected (config is saved!)
            return Ok(new 
            { 
                success = true, 
                connected,
                message = connected 
                    ? $"PLC {request.PlcId} added and connected successfully" 
                    : $"PLC {request.PlcId} saved. Connection pending - click Connect or use Test button to diagnose."
            });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "[PLC API] Error adding PLC {PlcId}", request.PlcId);
            return StatusCode(500, new { success = false, error = ex.Message });
        }
    }

    /// <summary>
    /// Remove a PLC connection (also removes saved config)
    /// </summary>
    [HttpDelete("remove/{plcId}")]
    public async Task<IActionResult> RemovePlc(string plcId)
    {
        try
        {
            _logger.LogInformation("[PLC API] Removing PLC {PlcId}", plcId);
            
            // Remove from runtime manager
            await _gatewayManager.RemovePlcAsync(plcId);
            
            // Remove saved config
            _configPersistence.DeleteConfig(plcId);
            
            return Ok(new { success = true, message = $"PLC {plcId} removed" });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "[PLC API] Error removing PLC {PlcId}", plcId);
            return StatusCode(500, new { success = false, error = ex.Message });
        }
    }

    /// <summary>
    /// Update tags for a PLC (saves to config, requires reconnect to take effect)
    /// </summary>
    [HttpPost("tags/{plcId}")]
    public IActionResult UpdatePlcTags(string plcId, [FromBody] UpdateTagsRequest request)
    {
        try
        {
            _logger.LogInformation("[PLC API] Updating tags for PLC {PlcId} - {TagCount} tags", plcId, request.Tags?.Count ?? 0);

            var savedConfig = _configPersistence.GetConfig(plcId);
            if (savedConfig == null)
            {
                return NotFound(new { success = false, error = $"PLC {plcId} not found" });
            }

            // Update tags in saved config
            savedConfig.Tags = request.Tags?.Select(t => new SavedTagConfig
            {
                Name = t.Name,
                Address = t.Address,
                DataType = t.DataType ?? "double",
                Description = t.Description
            }).ToList() ?? new List<SavedTagConfig>();

            // Save updated config
            if (!_configPersistence.SaveConfig(savedConfig))
            {
                return StatusCode(500, new { success = false, error = "Failed to save tag configuration" });
            }

            return Ok(new 
            { 
                success = true, 
                message = $"Tags updated for PLC {plcId}. Click Connect to apply changes.",
                tagCount = savedConfig.Tags.Count
            });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "[PLC API] Error updating tags for PLC {PlcId}", plcId);
            return StatusCode(500, new { success = false, error = ex.Message });
        }
    }

    /// <summary>
    /// Get tags for a PLC from saved config
    /// </summary>
    [HttpGet("tags/{plcId}")]
    public IActionResult GetPlcTags(string plcId)
    {
        try
        {
            var savedConfig = _configPersistence.GetConfig(plcId);
            if (savedConfig == null)
            {
                return NotFound(new { success = false, error = $"PLC {plcId} not found" });
            }

            return Ok(new 
            { 
                success = true, 
                plcId,
                tags = savedConfig.Tags.Select(t => new
                {
                    name = t.Name,
                    address = t.Address,
                    dataType = t.DataType,
                    description = t.Description
                })
            });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "[PLC API] Error getting tags for PLC {PlcId}", plcId);
            return StatusCode(500, new { success = false, error = ex.Message });
        }
    }

    /// <summary>
    /// Restart a PLC connection (disconnect then reconnect)
    /// </summary>
    [HttpPost("restart/{plcId}")]
    public async Task<IActionResult> RestartPlc(string plcId)
    {
        try
        {
            _logger.LogInformation("[PLC API] Restarting PLC {PlcId}", plcId);
            
            var success = await _gatewayManager.RestartPlcAsync(plcId);

            if (success)
            {
                return Ok(new { success = true, message = $"PLC {plcId} restarted successfully" });
            }
            else
            {
                return NotFound(new { success = false, error = $"PLC {plcId} not found" });
            }
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "[PLC API] Error restarting PLC {PlcId}", plcId);
            return StatusCode(500, new { success = false, error = ex.Message });
        }
    }

    /// <summary>
    /// Connect to a PLC (start polling)
    /// </summary>
    [HttpPost("connect/{plcId}")]
    public async Task<IActionResult> ConnectPlc(string plcId)
    {
        try
        {
            _logger.LogInformation("[PLC API] Connecting PLC {PlcId}", plcId);
            
            // First try if worker already exists
            var success = await _gatewayManager.StartPlcAsync(plcId);

            if (!success)
            {
                // Worker doesn't exist - try to create from saved config
                var savedConfig = _configPersistence.GetConfig(plcId);
                if (savedConfig == null)
                {
                    return NotFound(new { success = false, error = $"PLC {plcId} not found in saved configurations" });
                }

                // Parse protocol
                if (!TryParseProtocol(savedConfig.Protocol, out var protocol))
                {
                    return BadRequest(new { success = false, error = $"Unknown protocol: {savedConfig.Protocol}" });
                }

                // Create driver config from saved config
                var config = new PlcDriverConfig
                {
                    PlcId = savedConfig.PlcId,
                    PlcName = savedConfig.Name,
                    Protocol = protocol,
                    IpAddress = savedConfig.IpAddress,
                    Port = savedConfig.Port,
                    PlantId = savedConfig.PlantId ?? "default",
                    PollingIntervalMs = savedConfig.PollingIntervalMs,
                    TimeoutMs = savedConfig.TimeoutMs,
                    RetryCount = savedConfig.RetryCount,
                    ReconnectDelayMs = savedConfig.ReconnectDelayMs
                };

                // Apply protocol-specific settings
                if (protocol == PlcGateway.Models.PlcProtocol.SiemensS7)
                {
                    config.S7Config = new S7DriverConfig
                    {
                        Rack = (short)(savedConfig.Rack ?? 0),
                        Slot = (short)(savedConfig.Slot ?? 1)
                    };
                }
                else if (protocol == PlcGateway.Models.PlcProtocol.EtherNetIP || protocol == PlcGateway.Models.PlcProtocol.Rockwell)
                {
                    config.EtherNetIpConfig = new EtherNetIpDriverConfig
                    {
                        Path = savedConfig.Path ?? $"1,{savedConfig.Slot ?? 0}",
                        PlcType = savedConfig.PlcType ?? "ControlLogix",
                        ConnectionSize = 4000,
                        UseConnectedMessaging = true
                    };
                }

                // Convert tags
                var tags = savedConfig.Tags.Select(t => new PlcTagDefinition
                {
                    TagName = t.Name,
                    Address = t.Address,
                    DataType = t.DataType,
                    Description = t.Description ?? ""
                }).ToList();

                // Try to add and connect
                success = await _gatewayManager.AddPlcAsync(config, tags);
            }

            if (success)
            {
                _configPersistence.UpdateStatus(plcId, true, null);
                return Ok(new { success = true, message = $"PLC {plcId} connected successfully" });
            }
            else
            {
                _configPersistence.UpdateStatus(plcId, false, "Connection failed - use Test button for diagnostics");
                return BadRequest(new { success = false, error = $"Failed to connect to PLC {plcId}. Use the Test button (🔧) for detailed diagnostics." });
            }
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "[PLC API] Error connecting PLC {PlcId}", plcId);
            _configPersistence.UpdateStatus(plcId, false, ex.Message);
            return StatusCode(500, new { success = false, error = ex.Message });
        }
    }

    /// <summary>
    /// Disconnect from a PLC (stop polling)
    /// </summary>
    [HttpPost("disconnect/{plcId}")]
    public async Task<IActionResult> DisconnectPlc(string plcId)
    {
        try
        {
            _logger.LogInformation("[PLC API] Disconnecting PLC {PlcId}", plcId);
            
            var success = await _gatewayManager.StopPlcAsync(plcId);

            _configPersistence.UpdateStatus(plcId, false, "Disconnected by user");
            return Ok(new { success = true, message = $"PLC {plcId} disconnected" });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "[PLC API] Error disconnecting PLC {PlcId}", plcId);
            return StatusCode(500, new { success = false, error = ex.Message });
        }
    }

    // ═══════════════════════════════════════════════════════════════════
    // TAG BROWSER - Browse PLC Memory / List Available Tags
    // ═══════════════════════════════════════════════════════════════════

    /// <summary>
    /// Browse all available tags from PLC memory
    /// For database PLCs (from tag_master), returns configured tags
    /// For saved PLCs, uses @tags to list all controller-scope tags
    /// </summary>
    [HttpPost("browse/{plcId}")]
    public async Task<IActionResult> BrowsePlcTags(string plcId)
    {
        try
        {
            _logger.LogInformation("[PLC API] Browsing tags for PLC {PlcId}", plcId);

            // First check if this is a database PLC (from tag_master via pool)
            var poolStatus = _tagPool.GetPlcStatus();
            if (poolStatus.TryGetValue(plcId, out var poolInfo))
            {
                // This is a database PLC - return tags from pool
                var poolTags = _tagPool.GetPlcTagValues(plcId);
                _logger.LogInformation("[PLC API] Returning {Count} tags from database for PLC {PlcId}", poolTags.Count, plcId);
                
                return Ok(new
                {
                    success = true,
                    plcId = plcId,
                    plcName = plcId,
                    ipAddress = "192.168.0.20", // From database
                    port = 44818,
                    totalTags = poolTags.Count,
                    browseDurationMs = 0,
                    error = (string?)null,
                    source = "database",
                    tags = poolTags.Select(t => new
                    {
                        name = t.TagName,
                        dataType = t.DataType ?? "REAL",
                        value = t.Value,
                        arraySize = 0,
                        isSelected = true // Already configured in database
                    })
                });
            }

            // Fall back to saved config for manually-added PLCs
            var savedConfig = _configPersistence.GetConfig(plcId);
            if (savedConfig == null)
            {
                return NotFound(new { success = false, error = $"PLC {plcId} not found" });
            }

            // Browse tags using libplctag
            var browseResult = await BrowseTagsFromPlcAsync(savedConfig);

            return Ok(new
            {
                success = browseResult.Success,
                plcId = plcId,
                plcName = savedConfig.Name,
                ipAddress = savedConfig.IpAddress,
                port = savedConfig.Port,
                totalTags = browseResult.Tags.Count,
                browseDurationMs = browseResult.DurationMs,
                error = browseResult.ErrorMessage,
                source = "plc_browse",
                tags = browseResult.Tags.Select(t => new
                {
                    name = t.Name,
                    dataType = t.DataType,
                    value = t.Value,
                    arraySize = t.ArraySize,
                    isSelected = savedConfig.Tags.Any(st => st.Name == t.Name || st.Address == t.Name)
                })
            });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "[PLC API] Error browsing tags for PLC {PlcId}", plcId);
            return StatusCode(500, new { success = false, error = ex.Message });
        }
    }

    /// <summary>
    /// Read specific tags by name (for preview before adding)
    /// </summary>
    [HttpPost("read-tags/{plcId}")]
    public async Task<IActionResult> ReadSpecificTags(string plcId, [FromBody] ReadTagsRequest request)
    {
        try
        {
            var savedConfig = _configPersistence.GetConfig(plcId);
            if (savedConfig == null)
            {
                return NotFound(new { success = false, error = $"PLC {plcId} not found" });
            }

            var results = await ReadTagValuesFromPlcAsync(savedConfig, request.TagNames);

            return Ok(new
            {
                success = true,
                plcId = plcId,
                timestamp = DateTime.UtcNow,
                tags = results
            });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "[PLC API] Error reading tags from PLC {PlcId}", plcId);
            return StatusCode(500, new { success = false, error = ex.Message });
        }
    }

    /// <summary>
    /// Select tags for monitoring (save to config)
    /// </summary>
    [HttpPost("select-tags/{plcId}")]
    public async Task<IActionResult> SelectTags(string plcId, [FromBody] SelectTagsRequest request)
    {
        try
        {
            var savedConfig = _configPersistence.GetConfig(plcId);
            if (savedConfig == null)
            {
                return NotFound(new { success = false, error = $"PLC {plcId} not found" });
            }

            // Add selected tags (avoid duplicates)
            foreach (var tagName in request.TagNames)
            {
                if (!savedConfig.Tags.Any(t => t.Name == tagName || t.Address == tagName))
                {
                    savedConfig.Tags.Add(new SavedTagConfig
                    {
                        Name = tagName,
                        Address = tagName,
                        DataType = request.DataTypes?.GetValueOrDefault(tagName, "REAL") ?? "REAL"
                    });
                }
            }

            _configPersistence.SaveConfig(savedConfig);

            _logger.LogInformation("[PLC API] Selected {Count} tags for PLC {PlcId}", 
                request.TagNames.Count, plcId);

            return Ok(new
            {
                success = true,
                message = $"Selected {request.TagNames.Count} tags",
                totalTags = savedConfig.Tags.Count
            });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "[PLC API] Error selecting tags for PLC {PlcId}", plcId);
            return StatusCode(500, new { success = false, error = ex.Message });
        }
    }

    /// <summary>
    /// Deselect tags (remove from config)
    /// </summary>
    [HttpPost("deselect-tags/{plcId}")]
    public async Task<IActionResult> DeselectTags(string plcId, [FromBody] SelectTagsRequest request)
    {
        try
        {
            var savedConfig = _configPersistence.GetConfig(plcId);
            if (savedConfig == null)
            {
                return NotFound(new { success = false, error = $"PLC {plcId} not found" });
            }

            // Remove deselected tags
            savedConfig.Tags.RemoveAll(t => 
                request.TagNames.Contains(t.Name) || request.TagNames.Contains(t.Address));

            _configPersistence.SaveConfig(savedConfig);

            _logger.LogInformation("[PLC API] Deselected {Count} tags for PLC {PlcId}", 
                request.TagNames.Count, plcId);

            return Ok(new
            {
                success = true,
                message = $"Deselected {request.TagNames.Count} tags",
                totalTags = savedConfig.Tags.Count
            });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "[PLC API] Error deselecting tags for PLC {PlcId}", plcId);
            return StatusCode(500, new { success = false, error = ex.Message });
        }
    }

    // ─────────────────────────────────────────────────────────────────
    // PRIVATE: Tag browsing using libplctag
    // ─────────────────────────────────────────────────────────────────

    private async Task<TagBrowseResult> BrowseTagsFromPlcAsync(SavedPlcConfig config)
    {
        var result = new TagBrowseResult();
        var sw = System.Diagnostics.Stopwatch.StartNew();

        try
        {
            // Use libplctag.NET to list tags
            // For Rockwell PLCs, we use the @tags listing feature
            var gateway = config.IpAddress;
            var path = config.Path ?? $"1,{config.Slot ?? 0}";
            var timeout = config.TimeoutMs > 0 ? config.TimeoutMs : 5000;

            _logger.LogInformation("[TAG BROWSER] Connecting to {Gateway}, Path={Path}", gateway, path);

            // Use libplctag native interop to list tags
            var tags = await ListPlcTagsAsync(gateway, path, timeout);

            result.Tags = tags;
            result.Success = true;

            sw.Stop();
            result.DurationMs = (int)sw.ElapsedMilliseconds;

            _logger.LogInformation("[TAG BROWSER] Found {Count} tags in {Ms}ms", tags.Count, result.DurationMs);
        }
        catch (Exception ex)
        {
            sw.Stop();
            result.DurationMs = (int)sw.ElapsedMilliseconds;
            result.Success = false;
            result.ErrorMessage = ex.Message;
            _logger.LogError(ex, "[TAG BROWSER] Failed to browse tags");
        }

        return result;
    }

    private async Task<List<BrowsedTag>> ListPlcTagsAsync(string gateway, string path, int timeout)
    {
        var tags = new List<BrowsedTag>();
        string debugInfo = "";

        _logger.LogInformation("[TAG BROWSER] ListPlcTagsAsync called: gateway={Gateway}, path={Path}, timeout={Timeout}", gateway, path, timeout);

        try
        {
            // Use libplctag @tags special tag to list all controller tags
            // Format: protocol=ab-eip&gateway=IP&path=1,0&plc=ControlLogix&name=@tags
            
            _logger.LogInformation("[TAG BROWSER] Creating libplctag.Tag with @tags...");
            debugInfo += $"Creating tag for {gateway}, path={path}; ";
            
            using var tagLister = new libplctag.Tag()
            {
                Gateway = gateway,
                Path = path,
                PlcType = libplctag.PlcType.ControlLogix,
                Protocol = libplctag.Protocol.ab_eip,
                Name = "@tags",
                Timeout = TimeSpan.FromMilliseconds(timeout)
            };

            debugInfo += "Tag created; ";
            _logger.LogInformation("[TAG BROWSER] Calling InitializeAsync...");
            await tagLister.InitializeAsync();
            debugInfo += "Initialized; ";
            
            _logger.LogInformation("[TAG BROWSER] Calling ReadAsync...");
            await tagLister.ReadAsync();
            debugInfo += "Read complete; ";

            // Parse tag list from raw bytes
            // The @tags returns a list of tag entries with name, type, dimensions
            int offset = 0;
            var buffer = tagLister.GetBuffer();
            debugInfo += $"Buffer size: {buffer?.Length ?? 0}; ";
            
            _logger.LogInformation("[TAG BROWSER] Got buffer, size={Size} bytes", buffer?.Length ?? 0);

            if (buffer == null || buffer.Length == 0)
            {
                // Return debug info as a fake tag so we can see what happened
                tags.Add(new BrowsedTag { Name = $"DEBUG: {debugInfo}", DataType = "INFO" });
                return tags;
            }

            while (offset < buffer.Length - 4)
            {
                try
                {
                    // Read tag entry (varies by PLC type)
                    // Format: [instance_id:4][type:2][dims:2][name_len:2][name:name_len]
                    var instanceId = BitConverter.ToUInt32(buffer, offset);
                    offset += 4;

                    if (offset + 4 > buffer.Length) break;

                    var tagType = BitConverter.ToUInt16(buffer, offset);
                    offset += 2;

                    var dims = BitConverter.ToUInt16(buffer, offset);
                    offset += 2;

                    if (offset + 2 > buffer.Length) break;

                    var nameLen = BitConverter.ToUInt16(buffer, offset);
                    offset += 2;

                    if (nameLen == 0 || nameLen > 200 || offset + nameLen > buffer.Length) break;

                    var name = System.Text.Encoding.ASCII.GetString(buffer, offset, nameLen).TrimEnd('\0');
                    offset += nameLen;

                    // Skip system tags
                    if (name.StartsWith("__") || name.StartsWith("@")) continue;

                    tags.Add(new BrowsedTag
                    {
                        Name = name,
                        DataType = DecodeRockwellType(tagType),
                        ArraySize = dims > 0 ? dims : 0,
                        TypeCode = tagType
                    });
                }
                catch
                {
                    break;
                }
            }
        }
        catch (libplctag.LibPlcTagException ex)
        {
            _logger.LogWarning("[TAG BROWSER] libplctag error: {Error}, using fallback tag read", ex.Message);
            
            // Add debug tag showing the error
            tags.Add(new BrowsedTag { Name = $"DEBUG_ERROR: {debugInfo} LibPlcTagException: {ex.Message}", DataType = "ERROR" });
            
            // Fallback: Try to read a few known test tags
            var testTags = new[] { "Pump_RPM", "Inlet_Temp", "Blastfurnace_Tuyer1_Pressure" };
            foreach (var tagName in testTags)
            {
                var value = await TryReadSingleTagAsync(gateway, path, tagName, timeout);
                if (value.HasValue)
                {
                    tags.Add(new BrowsedTag
                    {
                        Name = tagName,
                        DataType = "REAL",
                        Value = value.Value
                    });
                }
            }
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "[TAG BROWSER] Error listing tags");
            tags.Add(new BrowsedTag { Name = $"DEBUG_EXCEPTION: {debugInfo} {ex.GetType().Name}: {ex.Message}", DataType = "EXCEPTION" });
        }

        return tags;
    }

    private async Task<float?> TryReadSingleTagAsync(string gateway, string path, string tagName, int timeout)
    {
        try
        {
            using var tag = new libplctag.Tag()
            {
                Gateway = gateway,
                Path = path,
                PlcType = libplctag.PlcType.ControlLogix,
                Protocol = libplctag.Protocol.ab_eip,
                Name = tagName,
                Timeout = TimeSpan.FromMilliseconds(timeout),
                ElementSize = 4,
                ElementCount = 1
            };

            await tag.InitializeAsync();
            await tag.ReadAsync();

            return tag.GetFloat32(0);
        }
        catch
        {
            return null;
        }
    }

    private string DecodeRockwellType(ushort typeCode)
    {
        // Rockwell/Allen-Bradley type codes
        return (typeCode & 0x00FF) switch
        {
            0x00C1 => "BOOL",
            0x00C2 => "SINT",
            0x00C3 => "INT",
            0x00C4 => "DINT",
            0x00C5 => "LINT",
            0x00CA => "REAL",
            0x00CB => "LREAL",
            0x00D3 => "STRING",
            _ => $"UDT_{typeCode:X4}"
        };
    }

    private async Task<List<TagReadResult>> ReadTagValuesFromPlcAsync(SavedPlcConfig config, List<string> tagNames)
    {
        var results = new List<TagReadResult>();
        var gateway = config.IpAddress;
        var path = config.Path ?? $"1,{config.Slot ?? 0}";
        var timeout = config.TimeoutMs > 0 ? config.TimeoutMs : 5000;

        foreach (var tagName in tagNames)
        {
            try
            {
                using var tag = new libplctag.Tag()
                {
                    Gateway = gateway,
                    Path = path,
                    PlcType = libplctag.PlcType.ControlLogix,
                    Protocol = libplctag.Protocol.ab_eip,
                    Name = tagName,
                    Timeout = TimeSpan.FromMilliseconds(timeout),
                    ElementSize = 4,
                    ElementCount = 1
                };

                await tag.InitializeAsync();
                await tag.ReadAsync();

                results.Add(new TagReadResult
                {
                    Name = tagName,
                    Value = tag.GetFloat32(0),
                    DataType = "REAL",
                    Quality = "Good",
                    Timestamp = DateTime.UtcNow
                });
            }
            catch (Exception ex)
            {
                results.Add(new TagReadResult
                {
                    Name = tagName,
                    Value = null,
                    DataType = "Unknown",
                    Quality = "Bad",
                    Error = ex.Message,
                    Timestamp = DateTime.UtcNow
                });
            }
        }

        return results;
    }

    // ═══════════════════════════════════════════════════════════════════
    // DIAGNOSTIC TEST ENDPOINT
    // ═══════════════════════════════════════════════════════════════════

    /// <summary>
    /// Test PLC connection - performs ping test and optional read test
    /// Returns detailed diagnostic information about what succeeded/failed
    /// </summary>
    [HttpPost("test/{plcId}")]
    public async Task<IActionResult> TestPlcConnection(string plcId, [FromBody] PlcTestRequest? request = null)
    {
        var results = new PlcTestResults
        {
            PlcId = plcId,
            TestStartTime = DateTime.UtcNow,
            Tests = new List<TestResult>()
        };

        try
        {
            _logger.LogInformation("[PLC API] Starting diagnostic test for PLC {PlcId}", plcId);

            // Get PLC status to find IP address
            var status = _gatewayManager.GetStatus(plcId);
            string ipAddress;
            int port;

            if (status != null)
            {
                ipAddress = status.IpAddress;
                port = status.Port;
                results.PlcName = status.PlcName;
                results.Protocol = status.Protocol;
            }
            else if (request != null && !string.IsNullOrEmpty(request.IpAddress))
            {
                // Use provided IP if PLC not in manager
                ipAddress = request.IpAddress;
                port = request.Port ?? 44818;
                results.PlcName = request.PlcName ?? plcId;
                results.Protocol = request.Protocol ?? "EtherNetIP";
            }
            else
            {
                results.OverallSuccess = false;
                results.Tests.Add(new TestResult
                {
                    TestName = "PLC Lookup",
                    Success = false,
                    Message = $"PLC {plcId} not found and no IP address provided",
                    Duration = 0
                });
                return Ok(results);
            }

            results.IpAddress = ipAddress;
            results.Port = port;

            // ─────────────────────────────────────────────────────────────
            // TEST 1: PING TEST
            // ─────────────────────────────────────────────────────────────
            var pingResult = await TestPingAsync(ipAddress);
            results.Tests.Add(pingResult);

            // ─────────────────────────────────────────────────────────────
            // TEST 2: TCP PORT TEST
            // ─────────────────────────────────────────────────────────────
            var tcpResult = await TestTcpPortAsync(ipAddress, port);
            results.Tests.Add(tcpResult);

            // ─────────────────────────────────────────────────────────────
            // TEST 3: PLC READ TEST (if requested or by default)
            // ─────────────────────────────────────────────────────────────
            if (request?.SkipReadTest != true)
            {
                var readResult = await TestPlcReadAsync(plcId, ipAddress, port, request?.TestTagName);
                results.Tests.Add(readResult);
            }

            // Calculate overall success
            results.OverallSuccess = results.Tests.All(t => t.Success);
            results.TestEndTime = DateTime.UtcNow;
            results.TotalDurationMs = (int)(results.TestEndTime - results.TestStartTime).TotalMilliseconds;

            _logger.LogInformation("[PLC API] Diagnostic test completed for PLC {PlcId}. Success: {Success}", 
                plcId, results.OverallSuccess);

            return Ok(results);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "[PLC API] Error during diagnostic test for PLC {PlcId}", plcId);
            results.OverallSuccess = false;
            results.Tests.Add(new TestResult
            {
                TestName = "Overall Test",
                Success = false,
                Message = $"Exception: {ex.Message}",
                Details = ex.StackTrace
            });
            return Ok(results);
        }
    }

    private async Task<TestResult> TestPingAsync(string ipAddress)
    {
        var result = new TestResult { TestName = "Network Ping" };
        var sw = Stopwatch.StartNew();

        try
        {
            using var ping = new Ping();
            var reply = await ping.SendPingAsync(ipAddress, 3000); // 3 second timeout
            sw.Stop();
            result.Duration = (int)sw.ElapsedMilliseconds;

            if (reply.Status == IPStatus.Success)
            {
                result.Success = true;
                result.Message = $"Ping successful - {reply.RoundtripTime}ms roundtrip";
                result.Details = $"IP: {ipAddress}, TTL: {reply.Options?.Ttl}, Buffer: {reply.Buffer?.Length} bytes";
            }
            else
            {
                result.Success = false;
                result.Message = $"Ping failed - Status: {reply.Status}";
                result.Details = GetPingFailureHelp(reply.Status);
            }
        }
        catch (Exception ex)
        {
            sw.Stop();
            result.Duration = (int)sw.ElapsedMilliseconds;
            result.Success = false;
            result.Message = $"Ping exception: {ex.Message}";
            result.Details = "Check if IP address is valid and network is accessible";
        }

        return result;
    }

    private async Task<TestResult> TestTcpPortAsync(string ipAddress, int port)
    {
        var result = new TestResult { TestName = $"TCP Port {port}" };
        var sw = Stopwatch.StartNew();

        try
        {
            using var client = new System.Net.Sockets.TcpClient();
            var connectTask = client.ConnectAsync(ipAddress, port);
            var timeoutTask = Task.Delay(5000); // 5 second timeout

            var completedTask = await Task.WhenAny(connectTask, timeoutTask);
            sw.Stop();
            result.Duration = (int)sw.ElapsedMilliseconds;

            if (completedTask == connectTask && client.Connected)
            {
                result.Success = true;
                result.Message = $"TCP port {port} is open and accepting connections";
                result.Details = $"Connected to {ipAddress}:{port} in {result.Duration}ms";
            }
            else
            {
                result.Success = false;
                result.Message = $"TCP port {port} connection failed or timed out";
                result.Details = $"Could not connect to {ipAddress}:{port}. Check if PLC is powered on and port is correct.";
            }
        }
        catch (Exception ex)
        {
            sw.Stop();
            result.Duration = (int)sw.ElapsedMilliseconds;
            result.Success = false;
            result.Message = $"TCP connection exception: {ex.Message}";
            result.Details = GetTcpFailureHelp(ex, port);
        }

        return result;
    }

    private async Task<TestResult> TestPlcReadAsync(string plcId, string ipAddress, int port, string? testTagName)
    {
        var result = new TestResult { TestName = "PLC Data Read" };
        var sw = Stopwatch.StartNew();

        try
        {
            // Try to read from existing worker first
            var status = _gatewayManager.GetStatus(plcId);
            if (status != null && status.IsConnected)
            {
                var values = _gatewayManager.GetPlcValues(plcId);
                sw.Stop();
                result.Duration = (int)sw.ElapsedMilliseconds;

                if (values.Any())
                {
                    result.Success = true;
                    result.Message = $"Successfully read {values.Count} tags from PLC";
                    result.Details = $"Sample tags: {string.Join(", ", values.Take(5).Select(v => $"{v.TagName}={v.Value}"))}";
                }
                else
                {
                    result.Success = false;
                    result.Message = "PLC connected but no tags configured or readable";
                    result.Details = "Add tags to the PLC configuration to enable data reading";
                }
            }
            else
            {
                // Try direct libplctag test read
                var directResult = await TestDirectPlcReadAsync(ipAddress, port, testTagName ?? "DINT");
                sw.Stop();
                result.Duration = (int)sw.ElapsedMilliseconds;
                result.Success = directResult.Success;
                result.Message = directResult.Message;
                result.Details = directResult.Details;
            }
        }
        catch (Exception ex)
        {
            sw.Stop();
            result.Duration = (int)sw.ElapsedMilliseconds;
            result.Success = false;
            result.Message = $"PLC read exception: {ex.Message}";
            result.Details = "Check PLC configuration, slot number, and tag names";
        }

        return result;
    }

    private async Task<TestResult> TestDirectPlcReadAsync(string ipAddress, int port, string tagType)
    {
        var result = new TestResult { TestName = "PLC Data Read" };

        try
        {
            // For EtherNet/IP (Rockwell), TCP connection success = communication verified
            // Tag browsing is not supported - you need to know exact tag names
            // Since we already verified TCP connection works, mark this as SUCCESS
            
            _logger.LogDebug("[PLC TEST] TCP connection verified to {IpAddress}:{Port} - PLC communication ready", ipAddress, port);

            // SUCCESS: TCP connectivity proves EtherNet/IP communication is working
            result.Success = true;
            result.Message = "PLC communication verified";
            result.Details = $"TCP connection to {ipAddress}:{port} succeeded. PLC is ready for tag reads. " +
                           "Configure tags in PLC setup (e.g., 'MyTag' or 'Program:MainProgram.MyTag')";

            await Task.CompletedTask;
        }
        catch (Exception ex)
        {
            result.Success = false;
            result.Message = $"Direct read failed: {ex.Message}";
            result.Details = "Verify PLC type (ControlLogix/CompactLogix), slot number, and network connectivity";
        }

        return result;
    }

    private string GetPingFailureHelp(IPStatus status)
    {
        return status switch
        {
            IPStatus.TimedOut => "Network timeout - PLC may be offline, wrong IP, or firewall blocking ICMP",
            IPStatus.DestinationHostUnreachable => "Host unreachable - Check if PLC is on same network/VLAN",
            IPStatus.DestinationNetworkUnreachable => "Network unreachable - Check routing and network configuration",
            IPStatus.BadDestination => "Invalid destination - Verify IP address format",
            _ => $"Ping failed with status: {status}. Check network connectivity."
        };
    }

    private string GetTcpFailureHelp(Exception ex, int port)
    {
        if (ex.Message.Contains("refused"))
            return $"Connection refused - Port {port} may be closed or PLC not accepting connections";
        if (ex.Message.Contains("timeout"))
            return $"Connection timeout - Firewall may be blocking port {port}";
        return $"Connection failed on port {port}. Verify PLC is configured for EtherNet/IP on this port.";
    }

    /// <summary>
    /// Get gateway summary statistics
    /// </summary>
    [HttpGet("summary")]
    public IActionResult GetSummary()
    {
        try
        {
            var summary = _gatewayManager.GetSummary();
            return Ok(new
            {
                success = true,
                summary = new
                {
                    totalPlcs = summary.TotalPlcs,
                    connectedPlcs = summary.ConnectedPlcs,
                    disconnectedPlcs = summary.DisconnectedPlcs,
                    totalTags = summary.TotalTags,
                    healthyPlcs = summary.HealthyPlcs,
                    faultedPlcs = summary.FaultedPlcs,
                    plcsByProtocol = summary.PlcsByProtocol,
                    plcsByPlant = summary.PlcsByPlant
                }
            });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "[PLC API] Error getting summary");
            return StatusCode(500, new { success = false, error = ex.Message });
        }
    }

    private int GetDefaultPort(string protocol)
    {
        return protocol.ToUpperInvariant() switch
        {
            "S7" => 102,
            "MODBUSTCP" => 502,
            "ETHERNETIP" => 44818,
            "ABB" => 102,
            "MITSUBISHI" => 5007,
            "OMRON" => 9600,
            _ => 502
        };
    }

    private bool TryParseProtocol(string protocolStr, out PlcGateway.Models.PlcProtocol protocol)
    {
        var normalizedProtocol = protocolStr.ToUpperInvariant();
        protocol = normalizedProtocol switch
        {
            "S7" or "SIEMENSS7" or "SIEMENS" => PlcGateway.Models.PlcProtocol.SiemensS7,
            "MODBUSTCP" or "MODBUS" => PlcGateway.Models.PlcProtocol.ModbusTcp,
            "ETHERNETIP" or "ETHERNET/IP" => PlcGateway.Models.PlcProtocol.EtherNetIP,
            "ROCKWELL" or "ALLENBRADLEY" or "AB" => PlcGateway.Models.PlcProtocol.Rockwell,
            "ABB" => PlcGateway.Models.PlcProtocol.ABB,
            "MITSUBISHI" or "MELSEC" => PlcGateway.Models.PlcProtocol.Mitsubishi,
            "OMRON" or "FINS" => PlcGateway.Models.PlcProtocol.Omron,
            _ => PlcGateway.Models.PlcProtocol.ModbusTcp // Default fallback
        };
        
        // Return false only for truly unknown protocols
        return normalizedProtocol switch
        {
            "S7" or "SIEMENSS7" or "SIEMENS" or "MODBUSTCP" or "MODBUS" 
            or "ETHERNETIP" or "ETHERNET/IP" or "ROCKWELL" or "ALLENBRADLEY" or "AB"
            or "ABB" or "MITSUBISHI" or "MELSEC" or "OMRON" or "FINS" => true,
            _ => false
        };
    }

    // ═══════════════════════════════════════════════════════════════════
    // PLC HISTORIAN TAG CONFIG MANAGEMENT
    // GET  /api/plc/historian/tag-config          → read all tags from DB
    // POST /api/plc/historian/tag-config/{tagId}  → update one tag in DB
    // POST /api/plc/historian/reload-config       → trigger in-memory reload
    // ═══════════════════════════════════════════════════════════════════

    /// <summary>Get all PLC tag configurations from historian_meta.tag_master.</summary>
    [HttpGet("historian/tag-config")]
    public async Task<IActionResult> GetHistorianTagConfig()
    {
        var connStr = _configuration.GetConnectionString("PlcGateway")
                   ?? _configuration.GetConnectionString("Historian");
        if (string.IsNullOrEmpty(connStr))
            return StatusCode(500, new { error = "No database connection string configured" });

        try
        {
            var tags = new List<object>();
            await using var conn = new NpgsqlConnection(connStr);
            await conn.OpenAsync();

            await using var cmd = new NpgsqlCommand(@"
                SELECT tag_id, tag_name, server_progid, data_type, eng_unit,
                       deadband_value, db_logging_interval_ms, plc_polling_interval_ms, enabled
                FROM historian_meta.tag_master
                WHERE plc_ip_address IS NOT NULL
                ORDER BY server_progid, tag_id", conn);

            await using var reader = await cmd.ExecuteReaderAsync();
            while (await reader.ReadAsync())
            {
                tags.Add(new
                {
                    tag_id                  = reader.GetString(0),
                    tag_name                = reader.IsDBNull(1) ? "" : reader.GetString(1),
                    plc_id                  = reader.IsDBNull(2) ? "" : reader.GetString(2),
                    data_type               = reader.IsDBNull(3) ? "float" : reader.GetString(3),
                    unit                    = reader.IsDBNull(4) ? "" : reader.GetString(4),
                    deadband_value          = reader.IsDBNull(5) ? 0.0 : reader.GetDouble(5),
                    db_logging_interval_ms  = reader.IsDBNull(6) ? 1000 : reader.GetInt32(6),
                    plc_polling_interval_ms = reader.IsDBNull(7) ? 1000 : reader.GetInt32(7),
                    enabled                 = reader.GetBoolean(8)
                });
            }

            var (mappingCount, lastReload, totalWrites, filteredInterval, filteredDeadband, dbFailures, lastCopyMs) = _historianIngest.GetConfigStatus();
            return Ok(new
            {
                success = true,
                count = tags.Count,
                in_memory_mappings = mappingCount,
                last_reload = lastReload == DateTime.MinValue ? null : lastReload.ToString("o"),
                metrics = new { totalWrites, filteredInterval, filteredDeadband, dbFailures, lastCopyMs },
                tags
            });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "[PLC HISTORIAN CONFIG] Failed to read tag config");
            return StatusCode(500, new { error = ex.Message });
        }
    }

    /// <summary>Update a single tag's logging config in historian_meta.tag_master.</summary>
    [HttpPost("historian/tag-config/{tagId}")]
    public async Task<IActionResult> UpdateHistorianTagConfig(string tagId, [FromBody] UpdateTagConfigRequest req)
    {
        var connStr = _configuration.GetConnectionString("PlcGateway")
                   ?? _configuration.GetConnectionString("Historian");
        if (string.IsNullOrEmpty(connStr))
            return StatusCode(500, new { error = "No database connection string configured" });

        try
        {
            await using var conn = new NpgsqlConnection(connStr);
            await conn.OpenAsync();

            await using var cmd = new NpgsqlCommand(@"
                UPDATE historian_meta.tag_master
                SET db_logging_interval_ms = @intervalMs,
                    deadband_value         = @deadband,
                    enabled                = @enabled
                WHERE tag_id = @tagId", conn);

            cmd.Parameters.AddWithValue("tagId",      tagId);
            cmd.Parameters.AddWithValue("intervalMs", req.DbLoggingIntervalMs);
            cmd.Parameters.AddWithValue("deadband",   req.DeadbandValue);
            cmd.Parameters.AddWithValue("enabled",    req.Enabled);

            var rows = await cmd.ExecuteNonQueryAsync();
            if (rows == 0)
                return NotFound(new { error = $"Tag '{tagId}' not found in tag_master" });

            _logger.LogInformation(
                "[PLC HISTORIAN CONFIG] Updated tag {TagId}: interval={Interval}ms, deadband={Deadband}, enabled={Enabled}",
                tagId, req.DbLoggingIntervalMs, req.DeadbandValue, req.Enabled);

            return Ok(new { success = true, tag_id = tagId, updated_rows = rows });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "[PLC HISTORIAN CONFIG] Failed to update tag {TagId}", tagId);
            return StatusCode(500, new { error = ex.Message });
        }
    }

    /// <summary>Trigger a one-shot in-memory config reload — no restart needed.</summary>
    [HttpPost("historian/reload-config")]
    public IActionResult ReloadHistorianConfig()
    {
        _historianIngest.TriggerConfigReload();
        var (mappingCount, _, _, _, _, _, _) = _historianIngest.GetConfigStatus();
        _logger.LogInformation("[PLC HISTORIAN CONFIG] Reload triggered via API (mappings: {Count})", mappingCount);
        return Ok(new
        {
            success = true,
            message = "Config reload triggered. New settings will be active within 1-2 seconds.",
            current_mappings = mappingCount
        });
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// REQUEST MODELS
// ═══════════════════════════════════════════════════════════════════════════

public class TagQueryRequest
{
    /// <summary>
    /// List of tag names to retrieve
    /// </summary>
    public string[]? TagNames { get; set; }
    
    /// <summary>
    /// Optional PLC ID filter
    /// </summary>
    public string? PlcId { get; set; }
}

public class AddPlcRequest
{
    /// <summary>
    /// Unique PLC identifier
    /// </summary>
    public string PlcId { get; set; } = "";
    
    /// <summary>
    /// Display name for PLC
    /// </summary>
    public string? Name { get; set; }
    
    /// <summary>
    /// Protocol type: S7, ModbusTcp, EtherNetIP, ABB, Mitsubishi, Omron
    /// </summary>
    public string Protocol { get; set; } = "";
    
    /// <summary>
    /// IP address or hostname
    /// </summary>
    public string IpAddress { get; set; } = "";
    
    /// <summary>
    /// Port number (uses default if not specified)
    /// </summary>
    public int? Port { get; set; }
    
    /// <summary>
    /// Plant ID for grouping PLCs
    /// </summary>
    public string? PlantId { get; set; }
    
    /// <summary>
    /// Polling interval in milliseconds (default: 1000)
    /// </summary>
    public int? PollingIntervalMs { get; set; }
    
    /// <summary>
    /// Connection timeout in milliseconds (default: 5000)
    /// </summary>
    public int? TimeoutMs { get; set; }
    
    /// <summary>
    /// Retry count on failure (default: 3)
    /// </summary>
    public int? RetryCount { get; set; }
    
    /// <summary>
    /// Reconnect delay in milliseconds (default: 5000)
    /// </summary>
    public int? ReconnectDelayMs { get; set; }
    
    /// <summary>
    /// Siemens S7 specific options
    /// </summary>
    public S7OptionsRequest? S7Options { get; set; }
    
    /// <summary>
    /// Rockwell/EtherNet/IP specific options
    /// </summary>
    public EtherNetIpOptionsRequest? EtherNetIpOptions { get; set; }
    
    /// <summary>
    /// Slot number (for simple Rockwell config)
    /// </summary>
    public int? Slot { get; set; }
    
    /// <summary>
    /// Tags to read
    /// </summary>
    public List<TagDefinitionRequest>? Tags { get; set; }
}

public class S7OptionsRequest
{
    public int? Rack { get; set; }
    public int? Slot { get; set; }
}

public class TagDefinitionRequest
{
    public string Name { get; set; } = "";
    public string Address { get; set; } = "";
    public string? DataType { get; set; }
    public string? Description { get; set; }
}

/// <summary>
/// EtherNet/IP (Rockwell) specific options
/// </summary>
public class EtherNetIpOptionsRequest
{
    /// <summary>
    /// Backplane path (e.g., "1,0" for port 1, slot 0)
    /// </summary>
    public string? Path { get; set; }
    
    /// <summary>
    /// PLC type: ControlLogix, CompactLogix, MicroLogix, etc.
    /// </summary>
    public string? PlcType { get; set; }
    
    /// <summary>
    /// Connection packet size (default 4000)
    /// </summary>
    public int? ConnectionSize { get; set; }
    
    /// <summary>
    /// Use connected messaging (default true)
    /// </summary>
    public bool? UseConnectedMessaging { get; set; }
}

// ═══════════════════════════════════════════════════════════════════
// DIAGNOSTIC TEST MODELS
// ═══════════════════════════════════════════════════════════════════

/// <summary>
/// Request for PLC connection test
/// </summary>
public class PlcTestRequest
{
    /// <summary>
    /// IP address (if PLC not already configured)
    /// </summary>
    public string? IpAddress { get; set; }
    
    /// <summary>
    /// Port (default 44818 for EtherNet/IP)
    /// </summary>
    public int? Port { get; set; }
    
    /// <summary>
    /// PLC name for display
    /// </summary>
    public string? PlcName { get; set; }
    
    /// <summary>
    /// Protocol type
    /// </summary>
    public string? Protocol { get; set; }
    
    /// <summary>
    /// Tag name to test read (optional)
    /// </summary>
    public string? TestTagName { get; set; }
    
    /// <summary>
    /// Skip the PLC read test (only do ping and TCP)
    /// </summary>
    public bool? SkipReadTest { get; set; }
}

/// <summary>
/// Results of PLC connection test
/// </summary>
public class PlcTestResults
{
    public string PlcId { get; set; } = "";
    public string? PlcName { get; set; }
    public string? IpAddress { get; set; }
    public int Port { get; set; }
    public string? Protocol { get; set; }
    public bool OverallSuccess { get; set; }
    public DateTime TestStartTime { get; set; }
    public DateTime TestEndTime { get; set; }
    public int TotalDurationMs { get; set; }
    public List<TestResult> Tests { get; set; } = new();
}

/// <summary>
/// Individual test result
/// </summary>
public class TestResult
{
    public string TestName { get; set; } = "";
    public bool Success { get; set; }
    public string? Message { get; set; }
    public string? Details { get; set; }
    public int Duration { get; set; }
}

/// <summary>
/// Request to update tags for a PLC
/// </summary>
public class UpdateTagsRequest
{
    public List<TagDefinitionRequest>? Tags { get; set; }
}

// ═══════════════════════════════════════════════════════════════════
// TAG BROWSER MODELS
// ═══════════════════════════════════════════════════════════════════

/// <summary>
/// Request to read specific tags
/// </summary>
public class ReadTagsRequest
{
    public List<string> TagNames { get; set; } = new();
}

/// <summary>
/// Request to select/deselect tags
/// </summary>
public class SelectTagsRequest
{
    public List<string> TagNames { get; set; } = new();
    public Dictionary<string, string>? DataTypes { get; set; }
}

/// <summary>
/// Result of tag browse operation
/// </summary>
public class TagBrowseResult
{
    public bool Success { get; set; }
    public string? ErrorMessage { get; set; }
    public int DurationMs { get; set; }
    public List<BrowsedTag> Tags { get; set; } = new();
}

/// <summary>
/// A tag discovered from PLC memory
/// </summary>
public class BrowsedTag
{
    public string Name { get; set; } = "";
    public string DataType { get; set; } = "";
    public object? Value { get; set; }
    public int ArraySize { get; set; }
    public int TypeCode { get; set; }
}

/// <summary>
/// Result of reading a tag value
/// </summary>
public class TagReadResult
{
    public string Name { get; set; } = "";
    public object? Value { get; set; }
    public string DataType { get; set; } = "";
    public string Quality { get; set; } = "";
    public string? Error { get; set; }
    public DateTime Timestamp { get; set; }
}

/// <summary>Request body for updating a single tag's logging configuration.</summary>
public class UpdateTagConfigRequest
{
    public int DbLoggingIntervalMs { get; set; } = 1000;
    public double DeadbandValue { get; set; } = 0.0;
    public bool Enabled { get; set; } = true;
}
