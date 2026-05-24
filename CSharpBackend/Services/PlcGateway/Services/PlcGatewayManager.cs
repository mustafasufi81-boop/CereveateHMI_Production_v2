using System.Collections.Concurrent;
using Microsoft.Extensions.Logging;
using PlcGateway.Drivers;
using PlcGateway.Interfaces;

namespace PlcGateway.Services;

/// <summary>
/// PLC GATEWAY MANAGER
/// 
/// Manages multiple ISOLATED PLC workers
/// 
/// KEY PRINCIPLES:
/// 1. Each PLC = One Worker = Complete Isolation
/// 2. Workers run in parallel (Task per worker)
/// 3. No shared connections or data
/// 4. Add/Remove PLCs at runtime without affecting others
/// 5. Same manufacturer PLCs work independently
/// 6. Different manufacturers work together
/// 
/// EXAMPLE:
/// - Siemens PLC #1 (192.168.1.10) → Worker A
/// - Siemens PLC #2 (192.168.1.11) → Worker B (INDEPENDENT!)
/// - Allen Bradley PLC (192.168.1.20) → Worker C
/// - Modbus RTU (192.168.1.30) → Worker D
/// 
/// All 4 workers poll simultaneously, no interference!
/// </summary>
public sealed class PlcGatewayManager : IAsyncDisposable
{
    private readonly ConcurrentDictionary<string, PlcWorker> _workers = new();
    private readonly PlcDriverFactory _driverFactory;
    private readonly PlcTagValuesPoolService _tagPool;
    private readonly PlcSampleBufferService _sampleBuffer;
    private readonly ILoggerFactory _loggerFactory;
    private readonly ILogger<PlcGatewayManager> _logger;
    private bool _disposed;

    public int WorkerCount => _workers.Count;
    public IEnumerable<string> PlcIds => _workers.Keys;

    public PlcGatewayManager(
        PlcDriverFactory driverFactory,
        PlcTagValuesPoolService tagPool,
        PlcSampleBufferService sampleBuffer,
        ILoggerFactory loggerFactory)
    {
        _driverFactory = driverFactory;
        _tagPool = tagPool;
        _sampleBuffer = sampleBuffer;
        _loggerFactory = loggerFactory;
        _logger = loggerFactory.CreateLogger<PlcGatewayManager>();
        
        _logger.LogInformation("[GATEWAY] PlcGatewayManager initialized");
    }

    // ═══════════════════════════════════════════════════════════════════
    // WORKER MANAGEMENT
    // ═══════════════════════════════════════════════════════════════════

    /// <summary>
    /// Add and start a new PLC worker
    /// </summary>
    public async Task<bool> AddPlcAsync(PlcDriverConfig config, List<PlcTagDefinition> tags)
    {
        _logger.LogWarning("[GATEWAY] AddPlcAsync called for {PlcId} | Protocol: {Protocol} | IP: {Ip}", config.PlcId, config.Protocol, config.IpAddress);
        
        if (_workers.ContainsKey(config.PlcId))
        {
            _logger.LogWarning("[GATEWAY] PLC {PlcId} already exists", config.PlcId);
            return false;
        }

        try
        {
            _logger.LogWarning("[GATEWAY] Creating driver for {PlcId}...", config.PlcId);
            // Create driver instance (unique per worker)
            var driver = _driverFactory.CreateDriver(config.Protocol);
            
            // Initialize driver with config
            if (!await driver.InitializeAsync(config, tags))
            {
                _logger.LogError("[GATEWAY] Failed to initialize driver for {PlcId}", config.PlcId);
                driver.Dispose();
                return false;
            }

            // Create worker config
            var workerConfig = new PlcWorkerConfig
            {
                IpAddress = config.IpAddress,
                Port = config.Port,
                PollingIntervalMs = config.PollingIntervalMs,
                ReconnectDelayMs = config.ReconnectDelayMs,
                MaxConnectRetries = config.RetryCount,
                ReadTimeoutMs = config.TimeoutMs
            };

            // Create isolated worker with shared pool for API access
            // Pass tag definitions for PlcScanRateScheduler deadband filtering
            var worker = new PlcWorker(
                config.PlcId,
                config.PlcName,
                config.PlantId,
                driver,
                workerConfig,
                _tagPool,
                _sampleBuffer,
                _loggerFactory.CreateLogger<PlcWorker>(),
                tags);

            // Add to dictionary
            if (!_workers.TryAdd(config.PlcId, worker))
            {
                await worker.DisposeAsync();
                return false;
            }

            // Start worker (polling loop begins)
            _logger.LogWarning("[GATEWAY] Starting worker for {PlcId}...", config.PlcId);
            await worker.StartAsync();

            _logger.LogWarning("[GATEWAY] Worker started for {PlcId} | Tags: {Count}", config.PlcId, tags.Count);
            _logger.LogInformation(
                "[GATEWAY] Added PLC {PlcId} ({Name}) - Protocol: {Protocol}, IP: {Ip}:{Port}",
                config.PlcId, config.PlcName, config.Protocol, config.IpAddress, config.Port);

            return true;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "[GATEWAY] Failed to add PLC {PlcId}", config.PlcId);
            return false;
        }
    }

    /// <summary>
    /// Remove and stop a PLC worker
    /// </summary>
    public async Task<bool> RemovePlcAsync(string plcId)
    {
        if (!_workers.TryRemove(plcId, out var worker))
        {
            _logger.LogWarning("[GATEWAY] PLC {PlcId} not found", plcId);
            return false;
        }

        try
        {
            await worker.DisposeAsync();
            _logger.LogInformation("[GATEWAY] Removed PLC {PlcId}", plcId);
            return true;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "[GATEWAY] Error removing PLC {PlcId}", plcId);
            return false;
        }
    }

    /// <summary>
    /// Stop and restart a PLC worker
    /// </summary>
    public async Task<bool> RestartPlcAsync(string plcId)
    {
        if (!_workers.TryGetValue(plcId, out var worker))
        {
            _logger.LogWarning("[GATEWAY] PLC {PlcId} not found for restart", plcId);
            return false;
        }

        try
        {
            await worker.StopAsync();
            await Task.Delay(1000); // Brief pause
            await worker.StartAsync();
            
            _logger.LogInformation("[GATEWAY] Restarted PLC {PlcId}", plcId);
            return true;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "[GATEWAY] Error restarting PLC {PlcId}", plcId);
            return false;
        }
    }

    /// <summary>
    /// Start/Connect a PLC worker (begin polling)
    /// </summary>
    public async Task<bool> StartPlcAsync(string plcId)
    {
        if (!_workers.TryGetValue(plcId, out var worker))
        {
            _logger.LogWarning("[GATEWAY] PLC {PlcId} not found for start", plcId);
            return false;
        }

        try
        {
            await worker.StartAsync();
            _logger.LogInformation("[GATEWAY] Started PLC {PlcId}", plcId);
            return true;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "[GATEWAY] Error starting PLC {PlcId}", plcId);
            return false;
        }
    }

    /// <summary>
    /// Stop/Disconnect a PLC worker (stop polling)
    /// </summary>
    public async Task<bool> StopPlcAsync(string plcId)
    {
        if (!_workers.TryGetValue(plcId, out var worker))
        {
            _logger.LogWarning("[GATEWAY] PLC {PlcId} not found for stop", plcId);
            return false;
        }

        try
        {
            await worker.StopAsync();
            _logger.LogInformation("[GATEWAY] Stopped PLC {PlcId}", plcId);
            return true;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "[GATEWAY] Error stopping PLC {PlcId}", plcId);
            return false;
        }
    }

    // ═══════════════════════════════════════════════════════════════════
    // DATA ACCESS
    // ═══════════════════════════════════════════════════════════════════

    /// <summary>
    /// Get all values from all PLCs
    /// </summary>
    public List<PlcTagValue> GetAllValues()
    {
        var allValues = new List<PlcTagValue>();
        
        foreach (var worker in _workers.Values)
        {
            allValues.AddRange(worker.GetValues());
        }
        
        return allValues;
    }

    /// <summary>
    /// Get values from specific PLC
    /// </summary>
    public List<PlcTagValue> GetPlcValues(string plcId)
    {
        return _workers.TryGetValue(plcId, out var worker) 
            ? worker.GetValues() 
            : new List<PlcTagValue>();
    }

    /// <summary>
    /// Get values from specific plant (multiple PLCs)
    /// </summary>
    public List<PlcTagValue> GetPlantValues(string plantId)
    {
        var values = new List<PlcTagValue>();
        
        foreach (var worker in _workers.Values.Where(w => w.PlantId == plantId))
        {
            values.AddRange(worker.GetValues());
        }
        
        return values;
    }

    /// <summary>
    /// Get specific tag value from specific PLC
    /// </summary>
    public PlcTagValue? GetValue(string plcId, string address)
    {
        return _workers.TryGetValue(plcId, out var worker) 
            ? worker.GetValue(address) 
            : null;
    }

    // ═══════════════════════════════════════════════════════════════════
    // STATUS & MONITORING
    // ═══════════════════════════════════════════════════════════════════

    /// <summary>
    /// Get status of all workers
    /// </summary>
    public List<PlcWorkerStatus> GetAllStatus()
    {
        return _workers.Values.Select(w => w.GetStatus()).ToList();
    }

    /// <summary>
    /// Get status of specific worker
    /// </summary>
    public PlcWorkerStatus? GetStatus(string plcId)
    {
        return _workers.TryGetValue(plcId, out var worker) 
            ? worker.GetStatus() 
            : null;
    }

    /// <summary>
    /// Get summary statistics
    /// </summary>
    public GatewaySummary GetSummary()
    {
        var workers = _workers.Values.ToList();
        
        return new GatewaySummary
        {
            TotalPlcs = workers.Count,
            ConnectedPlcs = workers.Count(w => w.GetStatus().IsConnected),
            DisconnectedPlcs = workers.Count(w => !w.GetStatus().IsConnected),
            TotalTags = workers.Sum(w => w.GetStatus().TagCount),
            HealthyPlcs = workers.Count(w => w.GetStatus().ConsecutiveFailures == 0),
            FaultedPlcs = workers.Count(w => w.GetStatus().ConsecutiveFailures > 0),
            PlcsByProtocol = workers.GroupBy(w => w.Protocol)
                .ToDictionary(g => g.Key, g => g.Count()),
            PlcsByPlant = workers.GroupBy(w => w.PlantId)
                .ToDictionary(g => g.Key, g => g.Count())
        };
    }

    // ═══════════════════════════════════════════════════════════════════
    // BULK OPERATIONS
    // ═══════════════════════════════════════════════════════════════════

    /// <summary>
    /// Start all workers
    /// </summary>
    public async Task StartAllAsync()
    {
        var tasks = _workers.Values.Select(w => w.StartAsync());
        await Task.WhenAll(tasks);
        _logger.LogInformation("[GATEWAY] Started all {Count} workers", _workers.Count);
    }

    /// <summary>
    /// Stop all workers
    /// </summary>
    public async Task StopAllAsync()
    {
        var tasks = _workers.Values.Select(w => w.StopAsync());
        await Task.WhenAll(tasks);
        _logger.LogInformation("[GATEWAY] Stopped all workers");
    }

    // ═══════════════════════════════════════════════════════════════════
    // CLEANUP
    // ═══════════════════════════════════════════════════════════════════

    public async ValueTask DisposeAsync()
    {
        if (_disposed) return;
        _disposed = true;

        _logger.LogInformation("[GATEWAY] Disposing - stopping {Count} workers", _workers.Count);

        // Dispose all workers in parallel
        var tasks = _workers.Values.Select(w => w.DisposeAsync().AsTask());
        await Task.WhenAll(tasks);
        
        _workers.Clear();
        
        _logger.LogInformation("[GATEWAY] Disposed");
    }
}

/// <summary>
/// Gateway summary statistics
/// </summary>
public class GatewaySummary
{
    public int TotalPlcs { get; set; }
    public int ConnectedPlcs { get; set; }
    public int DisconnectedPlcs { get; set; }
    public int TotalTags { get; set; }
    public int HealthyPlcs { get; set; }
    public int FaultedPlcs { get; set; }
    public Dictionary<string, int> PlcsByProtocol { get; set; } = new();
    public Dictionary<string, int> PlcsByPlant { get; set; } = new();
}
