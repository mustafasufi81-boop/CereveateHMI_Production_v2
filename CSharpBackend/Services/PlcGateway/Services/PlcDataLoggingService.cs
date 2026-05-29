using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using PlcGateway.Drivers;
using PlcGateway.Interfaces;
using PlcGateway.Models;
using System.Collections.Concurrent;

namespace PlcGateway.Services;

/// <summary>
/// PLC Data Logging Service - BACKGROUND POLLING
/// 
/// DESIGN (Mirrors OPC DataLoggingService):
/// - Runs continuously in background
/// - Polls ALL configured PLCs every 1000ms
/// - Updates PlcTagValuesPoolService with fresh values
/// - Optionally writes to Parquet files (selected tags)
/// 
/// KEY PRINCIPLES:
/// 1. Single background service manages all PLC polling
/// 2. Each PLC has isolated worker (no interference)
/// 3. Pool is updated every cycle (1000ms)
/// 4. Parquet writes at configurable interval (e.g., 5000ms)
/// 5. Errors in one PLC don't affect others
/// 
/// CONFIG SOURCES (in priority order):
/// 1. Local JSON file (plc-config.json) - Added via Web UI
/// 2. PostgreSQL database (plc_gateway.plc_connections) - For enterprise
/// </summary>
public class PlcDataLoggingService : BackgroundService
{
    private readonly PlcTagValuesPoolService _tagPool;
    private readonly PlcConfigLoaderService _configLoader;
    private readonly PlcConfigPersistenceService _configPersistence;
    private readonly PlcDriverFactory _driverFactory;
    private readonly ILogger<PlcDataLoggingService> _logger;
    private readonly ILoggerFactory _loggerFactory;

    // Isolated workers per PLC
    private readonly ConcurrentDictionary<string, PlcPollingWorker> _workers = new();
    
    // Configuration
    private readonly int _pollingIntervalMs;
    private readonly int _parquetWriteIntervalMs;
    private readonly string _parquetOutputPath;
    private readonly bool _enableParquetLogging;

    // Statistics
    private int _totalPollCycles;
    private DateTime _serviceStartTime;

    public PlcDataLoggingService(
        PlcTagValuesPoolService tagPool,
        PlcConfigLoaderService configLoader,
        PlcConfigPersistenceService configPersistence,
        PlcDriverFactory driverFactory,
        ILogger<PlcDataLoggingService> logger,
        ILoggerFactory loggerFactory,
        IConfiguration configuration)
    {
        _tagPool = tagPool;
        _configLoader = configLoader;
        _configPersistence = configPersistence;
        _driverFactory = driverFactory;
        _logger = logger;
        _loggerFactory = loggerFactory;

        // Load configuration
        _pollingIntervalMs = configuration.GetValue<int>("PlcGateway:PollingIntervalMs", 1000);
        _parquetWriteIntervalMs = configuration.GetValue<int>("PlcGateway:ParquetWriteIntervalMs", 5000);
        _parquetOutputPath = configuration.GetValue<string>("PlcGateway:ParquetOutputPath", "D:\\PlcLogs\\Data") ?? "D:\\PlcLogs\\Data";
        _enableParquetLogging = configuration.GetValue<bool>("PlcGateway:EnableParquetLogging", false);

        _logger.LogInformation(
            "[PLC LOGGING] Initialized - Polling: {Poll}ms, Parquet: {Parquet}ms, Path: {Path}, Enabled: {Enabled}",
            _pollingIntervalMs, _parquetWriteIntervalMs, _parquetOutputPath, _enableParquetLogging);
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        _logger.LogInformation("[PLC LOGGING] Service starting...");
        _serviceStartTime = DateTime.UtcNow;

        // Wait for application startup
        await Task.Delay(2000, stoppingToken);

        // Ensure parquet directory exists
        if (_enableParquetLogging && !Directory.Exists(_parquetOutputPath))
        {
            Directory.CreateDirectory(_parquetOutputPath);
            _logger.LogInformation("[PLC LOGGING] Created parquet output directory: {Path}", _parquetOutputPath);
        }

        try
        {
            // Initial load of PLC configurations
            await LoadPlcConfigurationsAsync(stoppingToken);

            // Main polling loop
            while (!stoppingToken.IsCancellationRequested)
            {
                var cycleStart = DateTime.UtcNow;

                try
                {
                    // Poll all PLCs in parallel
                    await PollAllPlcsAsync(stoppingToken);
                    
                    _totalPollCycles++;

                    // Log statistics periodically (every 60 seconds)
                    if (_totalPollCycles % 60 == 0)
                    {
                        LogStatistics();
                    }
                }
                catch (Exception ex)
                {
                    _logger.LogError(ex, "[PLC LOGGING] Error in poll cycle");
                }

                // Calculate delay to maintain consistent interval
                var elapsed = (DateTime.UtcNow - cycleStart).TotalMilliseconds;
                var delay = Math.Max(0, _pollingIntervalMs - (int)elapsed);

                if (delay > 0)
                {
                    await Task.Delay(delay, stoppingToken);
                }
                else
                {
                    _logger.LogWarning("[PLC LOGGING] Poll cycle exceeded interval: {Elapsed}ms > {Interval}ms",
                        elapsed, _pollingIntervalMs);
                }
            }
        }
        catch (OperationCanceledException)
        {
            // Normal shutdown
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "[PLC LOGGING] Fatal error in service");
        }
        finally
        {
            await StopAllWorkersAsync();
        }

        _logger.LogInformation("[PLC LOGGING] Service stopped");
    }

    // ═══════════════════════════════════════════════════════════════════
    // CONFIGURATION LOADING (from JSON file AND database)
    // ═══════════════════════════════════════════════════════════════════

    private async Task LoadPlcConfigurationsAsync(CancellationToken ct)
    {
        _logger.LogInformation("[PLC LOGGING] Loading PLC configurations...");

        var loadedPlcIds = new HashSet<string>();

        // PRIORITY 1: Load from local JSON file (Web UI added PLCs)
        try
        {
            var localConfigs = _configPersistence.GetAllConfigs();
            _logger.LogInformation("[PLC LOGGING] Found {Count} PLCs in local config file", localConfigs.Count);

            foreach (var savedConfig in localConfigs.Where(c => c.Tags.Count > 0))
            {
                try
                {
                    var config = ConvertSavedConfigToEntry(savedConfig);
                    await CreateWorkerAsync(config, ct);
                    loadedPlcIds.Add(config.PlcId);
                }
                catch (Exception ex)
                {
                    _logger.LogError(ex, "[PLC LOGGING] Failed to create worker for local PLC {PlcId}", savedConfig.PlcId);
                }
            }
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "[PLC LOGGING] Error loading local config file");
        }

        // PRIORITY 2: Load from database (enterprise mode)
        try
        {
            var dbConfigs = await _configLoader.LoadAllEnabledPlcsAsync();
            _logger.LogInformation("[PLC LOGGING] Found {Count} PLCs in database", dbConfigs.Count);

            foreach (var config in dbConfigs)
            {
                if (loadedPlcIds.Contains(config.PlcId))
                {
                    _logger.LogDebug("[PLC LOGGING] Skipping DB PLC {PlcId} - already loaded from local config", config.PlcId);
                    continue;
                }

                try
                {
                    await CreateWorkerAsync(config, ct);
                    loadedPlcIds.Add(config.PlcId);
                }
                catch (Exception ex)
                {
                    _logger.LogError(ex, "[PLC LOGGING] Failed to create worker for DB PLC {PlcId}", config.PlcId);
                }
            }
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "[PLC LOGGING] Error loading from database (may not be configured)");
        }

        _logger.LogInformation("[PLC LOGGING] Created {Count} polling workers total", _workers.Count);

        // Gap 7: Startup invariant — CRITICAL log if zero PLCs configured
        if (_workers.Count == 0)
        {
            _logger.LogCritical("⚠️ STARTUP INVARIANT VIOLATION: Zero PLCs configured. No data will be collected. Check plc-config.json and database.");
            // Note: HealthStatusService is not injected here. PlcController already exposes noPlcConfigured via /api/plc/connections.
            // Health endpoint consumers should query /api/plc/connections to detect this condition.
        }
    }

    /// <summary>
    /// Convert SavedPlcConfig (from JSON) to PlcConfigEntry (for driver)
    /// </summary>
    private PlcConfigEntry ConvertSavedConfigToEntry(SavedPlcConfig saved)
    {
        var entry = new PlcConfigEntry
        {
            PlcId = saved.PlcId,
            PlcName = saved.Name,
            PlantId = saved.PlantId ?? "DEFAULT",
            Protocol = Enum.TryParse<PlcProtocol>(saved.Protocol, true, out var proto) ? proto : PlcProtocol.EtherNetIP,
            IpAddress = saved.IpAddress,
            Port = saved.Port,
            TimeoutMs = saved.TimeoutMs > 0 ? saved.TimeoutMs : 5000,
            RetryCount = 3,
            ReconnectDelayMs = 5000,
            Enabled = true,
            Tags = saved.Tags.Select(t => new PlcTagDefinition
            {
                TagName = t.Name,
                Address = t.Address,
                DataType = t.DataType ?? "Real",
                Description = t.Name,
                Unit = "",
                Enabled = true
            }).ToList()
        };

        // Set protocol-specific config
        if (entry.Protocol == PlcProtocol.EtherNetIP)
        {
            entry.RockwellConfig = new RockwellDriverConfig
            {
                Path = saved.Path ?? $"1,{saved.Slot ?? 0}",
                PlcType = "ControlLogix"
            };
        }

        return entry;
    }

    private async Task CreateWorkerAsync(PlcConfigEntry config, CancellationToken ct)
    {
        if (_workers.ContainsKey(config.PlcId))
        {
            _logger.LogWarning("[PLC LOGGING] Worker already exists for PLC {PlcId}", config.PlcId);
            return;
        }

        // Create driver instance
        var driver = _driverFactory.CreateDriver(config.Protocol);

        // Create driver config
        var driverConfig = new PlcDriverConfig
        {
            PlcId = config.PlcId,
            PlcName = config.PlcName,
            PlantId = config.PlantId,
            Protocol = config.Protocol,
            IpAddress = config.IpAddress,
            Port = config.Port,
            PollingIntervalMs = _pollingIntervalMs,
            TimeoutMs = config.TimeoutMs,
            RetryCount = config.RetryCount,
            ReconnectDelayMs = config.ReconnectDelayMs,
            S7Config = config.S7Config,
            ModbusConfig = config.ModbusConfig,
            RockwellConfig = config.RockwellConfig,
            AbbConfig = config.AbbConfig
        };

        // Initialize driver
        if (!await driver.InitializeAsync(driverConfig, config.Tags))
        {
            _logger.LogError("[PLC LOGGING] Failed to initialize driver for PLC {PlcId}", config.PlcId);
            driver.Dispose();
            return;
        }

        // Create worker
        var worker = new PlcPollingWorker(
            config.PlcId,
            config.PlcName,
            driver,
            config.Tags,
            _loggerFactory.CreateLogger<PlcPollingWorker>());

        if (_workers.TryAdd(config.PlcId, worker))
        {
            _logger.LogInformation(
                "[PLC LOGGING] Created worker for PLC {PlcId} ({Protocol}) with {TagCount} tags",
                config.PlcId, config.Protocol, config.Tags.Count);
        }
    }

    // ═══════════════════════════════════════════════════════════════════
    // POLLING
    // ═══════════════════════════════════════════════════════════════════

    private async Task PollAllPlcsAsync(CancellationToken ct)
    {
        if (_workers.IsEmpty)
        {
            return;
        }

        var timestamp = DateTime.UtcNow;
        var pollTasks = new List<Task>();

        // Start all polls in parallel
        foreach (var worker in _workers.Values)
        {
            pollTasks.Add(PollSinglePlcAsync(worker, timestamp, ct));
        }

        // Wait for all to complete (with timeout)
        try
        {
            await Task.WhenAll(pollTasks).WaitAsync(TimeSpan.FromMilliseconds(_pollingIntervalMs * 2), ct);
        }
        catch (TimeoutException)
        {
            _logger.LogWarning("[PLC LOGGING] Some PLC polls timed out");
        }
    }

    private async Task PollSinglePlcAsync(PlcPollingWorker worker, DateTime timestamp, CancellationToken ct)
    {
        try
        {
            // Ensure connected
            if (!worker.IsConnected)
            {
                var connected = await worker.ConnectAsync();
                if (!connected)
                {
                    _tagPool.MarkPlcDisconnected(worker.PlcId, "Connection failed");
                    return;
                }
            }

            // Read all tags
            var result = await worker.ReadAllTagsAsync();

            if (result.Success && result.Values.Count > 0)
            {
                // Convert to cache entries
                var cacheEntries = result.Values.Select(v => new PlcTagValueCacheEntry
                {
                    PlcId = worker.PlcId,
                    Address = v.Address,
                    TagName = v.TagName,
                    Value = v.Value,
                    DataType = v.DataType,
                    Quality = ConvertQuality(v.Quality),
                    Timestamp = v.Timestamp,
                    CachedAt = DateTime.UtcNow
                }).ToList();

                // Update shared pool
                _tagPool.UpdateFromPlc(worker.PlcId, cacheEntries, timestamp);

                worker.RecordSuccess(result.ReadDurationMs);
            }
            else
            {
                worker.RecordFailure(result.ErrorMessage);
                
                if (worker.ConsecutiveFailures >= 3)
                {
                    _tagPool.MarkPlcDisconnected(worker.PlcId, result.ErrorMessage);
                    await worker.DisconnectAsync();
                }
            }
        }
        catch (Exception ex)
        {
            worker.RecordFailure(ex.Message);
            _tagPool.MarkPlcDisconnected(worker.PlcId, ex.Message);
            _logger.LogError(ex, "[PLC LOGGING] Poll error for PLC {PlcId}", worker.PlcId);
        }
    }

    private PlcTagQuality ConvertQuality(Interfaces.PlcQuality quality)
    {
        return quality switch
        {
            Interfaces.PlcQuality.Good => PlcTagQuality.Good,
            Interfaces.PlcQuality.Bad => PlcTagQuality.Bad,
            Interfaces.PlcQuality.Uncertain => PlcTagQuality.Uncertain,
            Interfaces.PlcQuality.CommError => PlcTagQuality.CommError,
            _ => PlcTagQuality.NotConfigured
        };
    }

    // ═══════════════════════════════════════════════════════════════════
    // STATISTICS & MANAGEMENT
    // ═══════════════════════════════════════════════════════════════════

    private void LogStatistics()
    {
        var stats = _tagPool.GetStatistics();
        var uptime = DateTime.UtcNow - _serviceStartTime;

        _logger.LogInformation(
            "[PLC LOGGING] Stats: Cycles={Cycles}, Tags={Tags}, PLCs={Connected}/{Total}, Uptime={Uptime:hh\\:mm\\:ss}",
            _totalPollCycles,
            stats.TotalTags,
            stats.ConnectedPlcs,
            stats.TotalPlcs,
            uptime);
    }

    private async Task StopAllWorkersAsync()
    {
        _logger.LogInformation("[PLC LOGGING] Stopping all workers...");

        foreach (var worker in _workers.Values)
        {
            try
            {
                await worker.DisconnectAsync();
                worker.Dispose();
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "[PLC LOGGING] Error stopping worker {PlcId}", worker.PlcId);
            }
        }

        _workers.Clear();
    }

    public override async Task StopAsync(CancellationToken cancellationToken)
    {
        _logger.LogInformation("[PLC LOGGING] Service stopping...");
        await base.StopAsync(cancellationToken);
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// POLLING WORKER (Isolated per PLC)
// ═══════════════════════════════════════════════════════════════════════════

/// <summary>
/// Isolated polling worker for a single PLC
/// </summary>
public class PlcPollingWorker : IDisposable
{
    public string PlcId { get; }
    public string PlcName { get; }
    public bool IsConnected => _driver.IsConnected;
    public int ConsecutiveFailures { get; private set; }
    public DateTime LastSuccessTime { get; private set; }
    public long AverageReadTimeMs { get; private set; }

    private readonly IPlcDriver _driver;
    private readonly List<PlcTagDefinition> _tags;
    private readonly ILogger<PlcPollingWorker> _logger;
    private int _totalReads;
    private long _totalReadTimeMs;
    private bool _disposed;

    public PlcPollingWorker(
        string plcId,
        string plcName,
        IPlcDriver driver,
        List<PlcTagDefinition> tags,
        ILogger<PlcPollingWorker> logger)
    {
        PlcId = plcId;
        PlcName = plcName;
        _driver = driver;
        _tags = tags;
        _logger = logger;
    }

    public async Task<bool> ConnectAsync()
    {
        try
        {
            return await _driver.ConnectAsync();
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "[WORKER {PlcId}] Connection error", PlcId);
            return false;
        }
    }

    public async Task<PlcReadResult> ReadAllTagsAsync()
    {
        return await _driver.ReadAllTagsAsync();
    }

    public async Task DisconnectAsync()
    {
        try
        {
            await _driver.DisconnectAsync();
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "[WORKER {PlcId}] Disconnect error", PlcId);
        }
    }

    public void RecordSuccess(long readTimeMs)
    {
        ConsecutiveFailures = 0;
        LastSuccessTime = DateTime.UtcNow;
        _totalReads++;
        _totalReadTimeMs += readTimeMs;
        AverageReadTimeMs = _totalReadTimeMs / _totalReads;
    }

    public void RecordFailure(string? error)
    {
        ConsecutiveFailures++;
        _logger.LogWarning("[WORKER {PlcId}] Read failure ({Count}x): {Error}",
            PlcId, ConsecutiveFailures, error ?? "Unknown");
    }

    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true;
        _driver.Dispose();
    }
}
