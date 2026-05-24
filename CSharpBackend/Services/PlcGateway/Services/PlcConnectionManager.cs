using Microsoft.Extensions.Logging;
using PlcGateway.Drivers;
using PlcGateway.Interfaces;
using System.Collections.Concurrent;

namespace PlcGateway.Services;

/// <summary>
/// PLC Connection Manager - manages lifecycle of all PLC connections
/// Each PLC runs in its own polling loop (Task)
/// </summary>
public class PlcConnectionManager : IDisposable
{
    private readonly PlcDriverFactory _driverFactory;
    private readonly PlcPoolManager _poolManager;
    private readonly ILogger<PlcConnectionManager> _logger;
    
    private readonly ConcurrentDictionary<string, PlcConnection> _connections = new();
    private readonly CancellationTokenSource _globalCts = new();
    private bool _disposed;

    public PlcConnectionManager(
        PlcDriverFactory driverFactory,
        PlcPoolManager poolManager,
        ILogger<PlcConnectionManager> logger)
    {
        _driverFactory = driverFactory;
        _poolManager = poolManager;
        _logger = logger;
    }

    /// <summary>
    /// Add and start a PLC connection
    /// </summary>
    public async Task<bool> AddConnectionAsync(PlcDriverConfig config, List<PlcTagDefinition> tags)
    {
        if (_connections.ContainsKey(config.PlcId))
        {
            _logger.LogWarning("[CONN MGR] PLC {PlcId} already exists", config.PlcId);
            return false;
        }

        try
        {
            // Create driver
            var driver = _driverFactory.CreateDriver(config.Protocol);
            
            // Initialize with config and tags
            if (!await driver.InitializeAsync(config, tags))
            {
                _logger.LogError("[CONN MGR] Failed to initialize driver for {PlcId}", config.PlcId);
                return false;
            }

            // Get/create pool for this PLC
            var pool = _poolManager.GetOrCreatePool(config.PlcId, config.PlcName, config.PlantId);

            // Create connection wrapper
            var connection = new PlcConnection
            {
                Config = config,
                Driver = driver,
                Pool = pool,
                Tags = tags
            };

            if (!_connections.TryAdd(config.PlcId, connection))
            {
                driver.Dispose();
                return false;
            }

            // Start polling loop
            connection.PollingTask = Task.Run(() => PollingLoopAsync(connection, _globalCts.Token));

            _logger.LogInformation("[CONN MGR] Added PLC {PlcId} ({Protocol}) with {TagCount} tags",
                config.PlcId, config.Protocol, tags.Count);

            return true;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "[CONN MGR] Failed to add PLC {PlcId}", config.PlcId);
            return false;
        }
    }

    /// <summary>
    /// Remove and stop a PLC connection
    /// </summary>
    public async Task<bool> RemoveConnectionAsync(string plcId)
    {
        if (!_connections.TryRemove(plcId, out var connection))
        {
            return false;
        }

        try
        {
            // Cancel polling
            connection.Cts.Cancel();
            
            // Wait for polling to stop (with timeout)
            if (connection.PollingTask != null)
            {
                await Task.WhenAny(connection.PollingTask, Task.Delay(5000));
            }

            // Disconnect
            await connection.Driver.DisconnectAsync();
            connection.Driver.Dispose();

            // Remove pool
            _poolManager.RemovePool(plcId);

            _logger.LogInformation("[CONN MGR] Removed PLC {PlcId}", plcId);
            return true;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "[CONN MGR] Error removing PLC {PlcId}", plcId);
            return false;
        }
    }

    /// <summary>
    /// Polling loop for a single PLC - runs in dedicated Task
    /// </summary>
    private async Task PollingLoopAsync(PlcConnection connection, CancellationToken globalToken)
    {
        var config = connection.Config;
        var driver = connection.Driver;
        var pool = connection.Pool;
        var localCts = connection.Cts;

        using var linkedCts = CancellationTokenSource.CreateLinkedTokenSource(globalToken, localCts.Token);
        var token = linkedCts.Token;

        _logger.LogInformation("[POLL] {PlcId}: Starting polling loop, interval={Interval}ms",
            config.PlcId, config.PollingIntervalMs);

        while (!token.IsCancellationRequested)
        {
            try
            {
                // Connect if needed
                if (!driver.IsConnected)
                {
                    _logger.LogInformation("[POLL] {PlcId}: Attempting connection...", config.PlcId);
                    
                    if (await driver.ConnectAsync())
                    {
                        connection.LastConnectTime = DateTime.UtcNow;
                        connection.ReconnectCount++;
                    }
                    else
                    {
                        // Wait before retry
                        await Task.Delay(config.ReconnectDelayMs, token);
                        continue;
                    }
                }

                // Read all tags
                var readResult = await driver.ReadAllTagsAsync();

                if (readResult.Success)
                {
                    // Update pool with values
                    pool.UpdateFromReadResult(readResult);
                    connection.LastSuccessfulRead = DateTime.UtcNow;
                    connection.ConsecutiveFailures = 0;
                }
                else
                {
                    connection.ConsecutiveFailures++;
                    _logger.LogWarning("[POLL] {PlcId}: Read failed ({Failures}x): {Error}",
                        config.PlcId, connection.ConsecutiveFailures, readResult.ErrorMessage);

                    // Disconnect after too many failures
                    if (connection.ConsecutiveFailures >= config.RetryCount)
                    {
                        _logger.LogError("[POLL] {PlcId}: Too many failures, disconnecting", config.PlcId);
                        await driver.DisconnectAsync();
                    }
                }

                // Wait for next poll
                await Task.Delay(config.PollingIntervalMs, token);
            }
            catch (OperationCanceledException)
            {
                break;
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "[POLL] {PlcId}: Unhandled error in polling loop", config.PlcId);
                connection.ConsecutiveFailures++;
                
                // Disconnect on critical error
                try { await driver.DisconnectAsync(); } catch { }
                
                await Task.Delay(config.ReconnectDelayMs, token);
            }
        }

        _logger.LogInformation("[POLL] {PlcId}: Polling loop stopped", config.PlcId);
    }

    /// <summary>
    /// Get connection status for all PLCs
    /// </summary>
    public List<PlcConnectionStatus> GetAllConnectionStatus()
    {
        return _connections.Values.Select(c => new PlcConnectionStatus
        {
            PlcId = c.Config.PlcId,
            PlcName = c.Config.PlcName,
            Protocol = c.Config.Protocol.ToString(),
            IpAddress = c.Config.IpAddress,
            Port = c.Config.Port,
            IsConnected = c.Driver.IsConnected,
            LastConnectTime = c.LastConnectTime,
            LastSuccessfulRead = c.LastSuccessfulRead,
            ConsecutiveFailures = c.ConsecutiveFailures,
            ReconnectCount = c.ReconnectCount,
            TagCount = c.Tags.Count,
            PoolTagCount = c.Pool.TagCount
        }).ToList();
    }

    /// <summary>
    /// Get connection status for specific PLC
    /// </summary>
    public PlcConnectionStatus? GetConnectionStatus(string plcId)
    {
        if (!_connections.TryGetValue(plcId, out var c))
            return null;

        return new PlcConnectionStatus
        {
            PlcId = c.Config.PlcId,
            PlcName = c.Config.PlcName,
            Protocol = c.Config.Protocol.ToString(),
            IpAddress = c.Config.IpAddress,
            Port = c.Config.Port,
            IsConnected = c.Driver.IsConnected,
            LastConnectTime = c.LastConnectTime,
            LastSuccessfulRead = c.LastSuccessfulRead,
            ConsecutiveFailures = c.ConsecutiveFailures,
            ReconnectCount = c.ReconnectCount,
            TagCount = c.Tags.Count,
            PoolTagCount = c.Pool.TagCount
        };
    }

    /// <summary>
    /// Force reconnect for a PLC
    /// </summary>
    public async Task<bool> ReconnectAsync(string plcId)
    {
        if (!_connections.TryGetValue(plcId, out var connection))
            return false;

        try
        {
            await connection.Driver.DisconnectAsync();
            // Connection will auto-reconnect in next polling cycle
            _logger.LogInformation("[CONN MGR] Triggered reconnect for {PlcId}", plcId);
            return true;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "[CONN MGR] Reconnect error for {PlcId}", plcId);
            return false;
        }
    }

    /// <summary>
    /// Get health status for all PLCs
    /// </summary>
    public async Task<List<PlcHealthStatus>> GetAllHealthStatusAsync()
    {
        var tasks = _connections.Values.Select(c => c.Driver.CheckHealthAsync());
        var results = await Task.WhenAll(tasks);
        return results.ToList();
    }

    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true;

        _globalCts.Cancel();

        foreach (var conn in _connections.Values)
        {
            conn.Cts.Cancel();
            conn.Driver.Dispose();
        }
        _connections.Clear();

        _globalCts.Dispose();
    }
}

/// <summary>
/// Internal connection wrapper
/// </summary>
internal class PlcConnection
{
    public required PlcDriverConfig Config { get; init; }
    public required IPlcDriver Driver { get; init; }
    public required PlcTagPool Pool { get; init; }
    public required List<PlcTagDefinition> Tags { get; init; }
    
    public CancellationTokenSource Cts { get; } = new();
    public Task? PollingTask { get; set; }
    
    public DateTime LastConnectTime { get; set; }
    public DateTime LastSuccessfulRead { get; set; }
    public int ConsecutiveFailures { get; set; }
    public int ReconnectCount { get; set; }
}

/// <summary>
/// PLC connection status for API/UI
/// </summary>
public class PlcConnectionStatus
{
    public string PlcId { get; set; } = "";
    public string PlcName { get; set; } = "";
    public string Protocol { get; set; } = "";
    public string IpAddress { get; set; } = "";
    public int Port { get; set; }
    public bool IsConnected { get; set; }
    public DateTime LastConnectTime { get; set; }
    public DateTime LastSuccessfulRead { get; set; }
    public int ConsecutiveFailures { get; set; }
    public int ReconnectCount { get; set; }
    public int TagCount { get; set; }
    public int PoolTagCount { get; set; }
}
