using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using PlcGateway.Drivers;
using PlcGateway.Interfaces;
using PlcGateway.Models;

namespace PlcGateway.Services;

/// <summary>
/// PLC Gateway Hosted Service
/// 
/// Runs as background service in ASP.NET Core
/// Loads PLC configurations from database and starts workers
/// 
/// LIFECYCLE:
/// 1. StartAsync: Load configs, create workers, start polling
/// 2. Running: Workers poll independently
/// 3. StopAsync: Stop all workers gracefully
/// </summary>
public class PlcGatewayHostedService : BackgroundService
{
    private readonly PlcGatewayManager _gateway;
    private readonly PlcConfigLoaderService _configLoader;
    private readonly ILogger<PlcGatewayHostedService> _logger;
    
    private readonly TimeSpan _configRefreshInterval = TimeSpan.FromMinutes(5);

    public PlcGatewayHostedService(
        PlcGatewayManager gateway,
        PlcConfigLoaderService configLoader,
        ILogger<PlcGatewayHostedService> logger)
    {
        _gateway = gateway;
        _configLoader = configLoader;
        _logger = logger;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        _logger.LogInformation("[PLC SERVICE] Starting PLC Gateway Service...");

        try
        {
            // Initial load of PLC configurations
            await LoadAndStartPlcsAsync();

            // Periodic config refresh loop
            while (!stoppingToken.IsCancellationRequested)
            {
                await Task.Delay(_configRefreshInterval, stoppingToken);
                
                // Check for config changes (new PLCs, disabled PLCs)
                await RefreshConfigAsync();
            }
        }
        catch (OperationCanceledException)
        {
            // Normal shutdown
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "[PLC SERVICE] Fatal error in PLC Gateway Service");
        }
    }

    private async Task LoadAndStartPlcsAsync()
    {
        _logger.LogWarning("========================================");
        _logger.LogWarning("[PLC SERVICE] Loading PLC configs from DB...");
        _logger.LogWarning("========================================");
        _logger.LogInformation("[PLC SERVICE] Loading PLC configurations from database...");

        try
        {
            var configs = await _configLoader.LoadAllEnabledPlcsAsync();
            
            _logger.LogWarning("[PLC SERVICE] Found {Count} PLC configurations", configs.Count);
            _logger.LogInformation("[PLC SERVICE] Found {Count} PLC configurations", configs.Count);

            // FOR TESTING: If no configs found, add hardcoded test PLC
            if (!configs.Any())
            {
                _logger.LogInformation("[PLC SERVICE] No database configs found, using hardcoded test PLC");
                
                var testConfig = new PlcDriverConfig
                {
                    PlcId = "ROCKWELL_001",
                    PlcName = "Test Rockwell PLC",
                    Protocol = PlcProtocol.EtherNetIP,
                    IpAddress = "192.168.0.20",
                    Port = 44818,
                    PollingIntervalMs = 1000,
                    ReconnectDelayMs = 5000,
                    RetryCount = 3,
                    TimeoutMs = 5000,
                    PlantId = "PLANT_001"
                };

                var testTags = new List<PlcTagDefinition>
                {
                    new PlcTagDefinition { Address = "Cooling_FAN_SPEED", TagName = "Cooling_FAN_SPEED", DataType = "REAL" },
                    new PlcTagDefinition { Address = "High_Temp_Limit", TagName = "High_Temp_Limit", DataType = "REAL" },
                    new PlcTagDefinition { Address = "Tank_Level", TagName = "Tank_Level", DataType = "REAL" },
                    new PlcTagDefinition { Address = "Pump_Status", TagName = "Pump_Status", DataType = "BOOL" },
                    new PlcTagDefinition { Address = "Motor_RPM", TagName = "Motor_RPM", DataType = "REAL" }
                };

                var success = await _gateway.AddPlcAsync(testConfig, testTags);
                
                if (success)
                {
                    _logger.LogInformation(
                        "[PLC SERVICE] Started TEST PLC: {PlcId} - {TagCount} tags",
                        testConfig.PlcId, testTags.Count);
                }
                else
                {
                    _logger.LogError("[PLC SERVICE] Failed to start TEST PLC");
                }
                
                return; // Skip database loading
            }

            foreach (var config in configs)
            {
                try
                {
                    var driverConfig = config.ToDriverConfig();
                    var success = await _gateway.AddPlcAsync(driverConfig, config.Tags);
                    
                    if (success)
                    {
                        _logger.LogInformation(
                            "[PLC SERVICE] Started PLC: {PlcId} ({Protocol}) - {TagCount} tags",
                            config.PlcId, config.Protocol, config.Tags.Count);
                    }
                    else
                    {
                        _logger.LogWarning(
                            "[PLC SERVICE] Failed to start PLC: {PlcId}",
                            config.PlcId);
                    }
                }
                catch (Exception ex)
                {
                    _logger.LogError(ex,
                        "[PLC SERVICE] Error starting PLC: {PlcId}",
                        config.PlcId);
                }
            }

            var summary = _gateway.GetSummary();
            _logger.LogInformation(
                "[PLC SERVICE] Gateway started: {Total} PLCs, {Connected} connected, {Tags} total tags",
                summary.TotalPlcs, summary.ConnectedPlcs, summary.TotalTags);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "[PLC SERVICE] Error loading PLC configurations");
        }
    }

    private async Task RefreshConfigAsync()
    {
        try
        {
            var configs = await _configLoader.LoadAllEnabledPlcsAsync();
            var currentPlcIds = _gateway.PlcIds.ToHashSet();
            var newPlcIds = configs.Select(c => c.PlcId).ToHashSet();

            // Find PLCs to add (new in DB)
            var toAdd = configs.Where(c => !currentPlcIds.Contains(c.PlcId));
            
            // Find PLCs to remove (disabled/deleted in DB)
            var toRemove = currentPlcIds.Except(newPlcIds);

            foreach (var config in toAdd)
            {
                _logger.LogInformation("[PLC SERVICE] Adding new PLC: {PlcId}", config.PlcId);
                var driverConfig = config.ToDriverConfig();
                await _gateway.AddPlcAsync(driverConfig, config.Tags);
            }

            foreach (var plcId in toRemove)
            {
                _logger.LogInformation("[PLC SERVICE] Removing PLC: {PlcId}", plcId);
                await _gateway.RemovePlcAsync(plcId);
            }
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "[PLC SERVICE] Error refreshing PLC configurations");
        }
    }

    public override async Task StopAsync(CancellationToken cancellationToken)
    {
        _logger.LogInformation("[PLC SERVICE] Stopping PLC Gateway Service...");
        
        await _gateway.StopAllAsync();
        await base.StopAsync(cancellationToken);
        
        _logger.LogInformation("[PLC SERVICE] PLC Gateway Service stopped");
    }
}
