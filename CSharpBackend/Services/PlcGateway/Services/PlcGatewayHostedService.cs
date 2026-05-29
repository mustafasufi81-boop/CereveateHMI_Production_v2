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
    private readonly PlcTagValuesPoolService _tagPool;
    private readonly ILogger<PlcGatewayHostedService> _logger;
    
    private readonly TimeSpan _configRefreshInterval = TimeSpan.FromMinutes(5);

    public PlcGatewayHostedService(
        PlcGatewayManager gateway,
        PlcConfigLoaderService configLoader,
        PlcTagValuesPoolService tagPool,
        ILogger<PlcGatewayHostedService> logger)
    {
        _gateway = gateway;
        _configLoader = configLoader;
        _tagPool = tagPool;
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
                // Gap 7: Surface "no PLC configured" as an explicit, visible alert
                // instead of silently spinning up a hardcoded fixture. Operators must
                // see this in /api/plc/connections so it can be displayed in the HMI.
                _logger.LogError(
                    "[PLC SERVICE] No PLC configurations found in database (historian_meta.tag_master). " +
                    "The PLC gateway has nothing to poll. Configure at least one enabled PLC in the database.");
                _tagPool.MarkNoPlcConfigured(
                    "No PLC configurations found in database (historian_meta.tag_master). " +
                    "Configure at least one enabled PLC.");
                return;
            }

            // Clear the sentinel if configs are now available
            _tagPool.ClearNoPlcConfiguredSentinel();

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
