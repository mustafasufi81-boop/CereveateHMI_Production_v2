using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using PlcGateway.Services;
using PlcGateway.Models;

namespace PlcGateway.Transport;

/// <summary>
/// PLC Health Publisher Service
/// 
/// FUNCTION:
/// - Collects health metrics from PlcGatewayManager every 3 seconds
/// - Reads ACTUAL PLC diagnostic tags from TagPool (NOT calculated values)
/// - Publishes to MQTT topic: plc/health
/// - Separate from tag value publishing (different interval)
/// 
/// DIAGNOSTIC TAGS READ FROM PLC (via GSV instructions):
/// - Controller Status (RUN/PROGRAM/FAULT mode)
/// - Major/Minor Fault codes
/// - Task:MainTask.AvgScanTime, MaxScanTime, OverrunCount
/// - Free Memory, Temperature, Connection count
/// 
/// GATEWAY-CALCULATED METRICS:
/// - Communication latency (response time)
/// - Error count, success rate
/// </summary>
public class HealthPublisherService : BackgroundService
{
    private readonly PlcGatewayManager _gatewayManager;
    private readonly PlcTagValuesPoolService _tagPool;
    private readonly ILogger<HealthPublisherService> _logger;
    
    // MQTT publisher (shared with MultiProtocolPublisherService)
    private MqttPublisher? _mqttPublisher;
    private readonly bool _mqttEnabled;
    private readonly MqttTransportConfig _mqttConfig;
    
    // Configuration
    private readonly int _healthIntervalMs;
    private readonly bool _enabled;
    
    // Statistics
    private long _publishCycles;
    private int _reconnectionCount;  // Track reconnections
    private DateTime _lastReadTime;
    private double _lastReadTimeMs;
    private DateTime _serviceStartTime;  // For uptime calculation

    public HealthPublisherService(
        PlcGatewayManager gatewayManager,
        PlcTagValuesPoolService tagPool,
        IConfiguration configuration,
        ILogger<HealthPublisherService> logger)
    {
        _gatewayManager = gatewayManager;
        _tagPool = tagPool;
        _logger = logger;

        // Read from config: PlcGateway:Health:Enabled and PlcGateway:Health:IntervalMs
        _enabled = configuration.GetValue<bool>("PlcGateway:Health:Enabled", true);
        _healthIntervalMs = configuration.GetValue<int>("PlcGateway:Health:IntervalMs", 5000);
        
        // MQTT configuration
        _mqttEnabled = configuration.GetValue<bool>("PlcGateway:Mqtt:Enabled", false);
        _mqttConfig = new MqttTransportConfig();
        configuration.GetSection("PlcGateway:Mqtt").Bind(_mqttConfig);

        _logger.LogInformation(
            "[HEALTH PUB] Initialized - Enabled: {Enabled}, MQTT: {Mqtt}, Interval: {Interval}ms (from config)",
            _enabled,
            _mqttEnabled ? "Enabled" : "Disabled",
            _healthIntervalMs);
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        if (!_enabled)
        {
            _logger.LogInformation("[HEALTH PUB] Service is disabled");
            return;
        }

        _logger.LogInformation("[HEALTH PUB] Service starting...");
        _serviceStartTime = DateTime.UtcNow;

        // Wait for gateway to initialize
        await Task.Delay(5000, stoppingToken);

        // Initialize MQTT if enabled
        if (_mqttEnabled)
        {
            _mqttPublisher = new MqttPublisher(_mqttConfig, _logger);
            await _mqttPublisher.ConnectAsync(stoppingToken);
        }

        try
        {
            while (!stoppingToken.IsCancellationRequested)
            {
                var cycleStart = DateTime.UtcNow;

                try
                {
                    await PublishHealthAsync(stoppingToken);
                    _publishCycles++;

                    if (_publishCycles % 20 == 0) // Log every minute (20 * 3s)
                    {
                        _logger.LogInformation(
                            "[HEALTH PUB] Published {Cycles} health updates",
                            _publishCycles);
                    }
                }
                catch (Exception ex)
                {
                    _logger.LogError(ex, "[HEALTH PUB] Error in health publish cycle");
                }

                // Maintain 3-second interval
                var elapsed = (DateTime.UtcNow - cycleStart).TotalMilliseconds;
                var delay = Math.Max(0, _healthIntervalMs - (int)elapsed);

                if (delay > 0)
                {
                    await Task.Delay(delay, stoppingToken);
                }
            }
        }
        catch (OperationCanceledException)
        {
            // Normal shutdown
        }

        // Cleanup
        if (_mqttPublisher != null)
        {
            await _mqttPublisher.DisconnectAsync();
        }

        _logger.LogInformation("[HEALTH PUB] Service stopped");
    }

    /// <summary>
    /// Collect and publish health metrics for all PLCs
    /// </summary>
    private async Task PublishHealthAsync(CancellationToken ct)
    {
        var readStart = DateTime.UtcNow;
        
        // Get all worker statuses
        var allStatus = _gatewayManager.GetAllStatus();
        
        _lastReadTimeMs = (DateTime.UtcNow - readStart).TotalMilliseconds;
        _lastReadTime = DateTime.UtcNow;

        var healthMetrics = new AllPlcHealthMetrics
        {
            Timestamp = DateTime.UtcNow,
            PlcCount = allStatus.Count,
            ConnectedCount = allStatus.Count(s => s.IsConnected),
            DisconnectedCount = allStatus.Count(s => !s.IsConnected),
            FaultedCount = allStatus.Count(s => s.ConsecutiveFailures > 0),
            Plcs = allStatus.Select(s => BuildPlcHealth(s)).ToList()
        };

        // Publish to MQTT
        if (_mqttEnabled && _mqttPublisher != null)
        {
            await _mqttPublisher.PublishHealthAsync(healthMetrics, ct);
        }
    }

    /// <summary>
    /// Build PlcHealthMetrics from PlcWorkerStatus
    /// </summary>
    private PlcHealthMetrics BuildPlcHealth(PlcWorkerStatus status)
    {
        var successRate = status.TotalPolls > 0 
            ? (double)status.SuccessfulPolls / status.TotalPolls * 100.0 
            : 100.0;

        var secondsSinceLastPoll = status.LastPollTime != default
            ? (DateTime.UtcNow - status.LastPollTime).TotalSeconds
            : -1;
        
        // Calculate uptime in minutes
        var uptimeMinutes = (_serviceStartTime != default)
            ? (DateTime.UtcNow - _serviceStartTime).TotalMinutes
            : 0;
        
        // Calculate health score (weighted average of key metrics)
        var healthScore = CalculateHealthScore(status, successRate);

        return new PlcHealthMetrics
        {
            Timestamp = DateTime.UtcNow,
            PlcId = status.PlcId,
            PlcName = status.PlcName,
            Protocol = status.Protocol,
            IpAddress = status.IpAddress,
            Port = status.Port,
            
            // Connection Status
            IsConnected = status.IsConnected,
            State = status.State.ToString(),
            
            // Timing Metrics
            AverageReadTimeMs = status.AverageReadTimeMs,
            LastReadTimeMs = _lastReadTimeMs,
            PollingIntervalMs = status.PollingIntervalMs,
            SecondsSinceLastPoll = secondsSinceLastPoll,
            
            // Error Metrics
            TotalPolls = status.TotalPolls,
            SuccessfulPolls = status.SuccessfulPolls,
            FailedPolls = status.FailedPolls,
            ConsecutiveFailures = status.ConsecutiveFailures,
            SuccessRatePercent = Math.Round(successRate, 2),
            LastError = status.LastError,
            
            // Tag Statistics
            TagCount = status.TagCount,
            GoodQualityTags = status.TagCount, // TODO: Calculate from pool
            BadQualityTags = 0,
            IsPoolStale = status.IsPoolStale,
            
            // Scan Rate Stats (if available)
            TotalScans = status.ScanRateStats?.TotalScans ?? 0,
            TotalCached = status.ScanRateStats?.TotalCached ?? 0,
            TotalFiltered = status.ScanRateStats?.TotalFiltered ?? 0,
            TotalTransmitted = status.ScanRateStats?.TotalTransmitted ?? 0,
            BufferedCount = status.ScanRateStats?.BufferedCount ?? 0,
            TagsByScanRate = status.ScanRateStats?.TagsByRate ?? new Dictionary<int, int>(),
            
            // ════════════════════════════════════════════════════════════════
            // 18 HEALTH METRICS (Gateway-Calculated values populated here)
            // PLC diagnostic values (from GSV) remain null until tags configured
            // ════════════════════════════════════════════════════════════════
            
            // #1: PLC Mode (from PLC - null until diagnostic tags configured)
            PlcModeCode = null,
            PlcMode = status.IsConnected ? "RUN" : "UNKNOWN",
            
            // #2: Major Fault (from PLC)
            MajorFaultActive = null,
            MajorFaultCode = null,
            
            // #3: Minor Fault (from PLC)
            MinorFaultBits = null,
            
            // #4: Avg Scan Time (from PLC - Task:MainTask.AvgScanTime)
            AvgScanTimeMs = null,
            
            // #5: Max Scan Time (from PLC - Task:MainTask.MaxScanTime)
            MaxScanTimeMs = null,
            
            // #6: Scan Load % (requires #4 and TaskPeriod from PLC)
            TaskPeriodMs = null,  // ScanLoadPercent auto-computed
            
            // #7: Task Overrun (from PLC - Task:MainTask.OverrunCount)
            TaskOverrunCount = null,
            
            // #8: Communication Latency (GATEWAY CALCULATED ✅)
            CommunicationLatencyMs = status.LastReadTimeMs,  // Raw value from last poll
            
            // #9: Comm Timeout Rate (GATEWAY CALCULATED ✅)
            TimeoutCount = status.FailedPolls,  // CommTimeoutRatePercent auto-computed
            
            // #10: Reconnect Rate (GATEWAY CALCULATED ✅)
            ReconnectionCount = _reconnectionCount,
            UptimeMinutes = uptimeMinutes,  // ReconnectRatePerMinute auto-computed
            
            // #11: Open CIP Connections (from PLC)
            OpenConnections = null,
            MaxConnections = null,  // ConnectionUsagePercent auto-computed
            
            // #12: Module Fault Count (from PLC)
            ModuleFaultCount = null,
            
            // #13: I/O Task Faulted (from PLC)
            IOTaskFaulted = null,
            
            // #14: Power Supply Status (from PLC)
            PowerSupplyStatus = null,
            
            // #15: Temperature (from PLC)
            TemperatureCelsius = null,
            
            // #16: Effective Poll Rate (GATEWAY CALCULATED ✅)
            ScheduledPolls = status.TotalPolls,  // EffectivePollRatePercent auto-computed
            
            // #17: Failed Polls (GATEWAY CALCULATED ✅)
            FailedPollCount = status.FailedPolls,
            
            // #18: Health Score (GATEWAY CALCULATED ✅)
            HealthScorePercent = healthScore
        };
    }
    
    /// <summary>
    /// Calculate overall health score (0-100%) based on weighted metrics
    /// </summary>
    private double CalculateHealthScore(PlcWorkerStatus status, double successRate)
    {
        double score = 100.0;
        
        // Connection: -50 if disconnected
        if (!status.IsConnected) score -= 50;
        
        // Success Rate: Deduct based on failure rate
        // 100% success = 0 deduction, 90% success = -10, 80% = -20
        score -= (100.0 - successRate) * 1.0;
        
        // Latency: -10 for >500ms, -5 for >200ms
        if (status.AverageReadTimeMs > 500) score -= 10;
        else if (status.AverageReadTimeMs > 200) score -= 5;
        
        // Consecutive failures: -5 per failure
        score -= status.ConsecutiveFailures * 5;
        
        // Buffer health: -10 if buffer over 80% full
        var bufferCount = status.ScanRateStats?.BufferedCount ?? 0;
        if (bufferCount > 8000) score -= 10;
        else if (bufferCount > 5000) score -= 5;
        
        // Reconnections: -2 per reconnection (indicates instability)
        score -= _reconnectionCount * 2;
        
        // Clamp to 0-100
        return Math.Round(Math.Max(0, Math.Min(100, score)), 1);
    }

    public override async Task StopAsync(CancellationToken cancellationToken)
    {
        _logger.LogInformation("[HEALTH PUB] Service stopping...");
        await base.StopAsync(cancellationToken);
    }
}
