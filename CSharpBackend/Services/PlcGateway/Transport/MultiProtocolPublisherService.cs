using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using PlcGateway.Services;

namespace PlcGateway.Transport;

/// <summary>
/// Multi-Protocol Publisher Service
/// 
/// DESIGN (SERVER-SIDE):
/// - Reads from PlcTagValuesPoolService
/// - Publishes SAME DATA to ALL enabled protocols SIMULTANEOUSLY
/// - MQTT, REST API, WebSocket - all get the same data
/// - Client chooses which protocol to consume
/// - Client handles failover (not server)
/// 
/// WHY THIS IS CORRECT:
/// ✅ Server transmits on ALL channels
/// ✅ Client connects to preferred channel
/// ✅ If MQTT fails, client switches to REST API
/// ✅ No data loss - data available on both
/// ✅ Simple server logic - just broadcast everywhere
/// 
/// DATA FLOW:
/// 
///     PlcTagValuesPoolService (shared cache)
///                 ↓
///     MultiProtocolPublisherService
///                 ↓
///     ┌───────────┼───────────┐
///     ↓           ↓           ↓
///   MQTT      REST API    WebSocket
///  (broker)   (/api/plc)   (SignalR)
///     ↓           ↓           ↓
///   ════════════════════════════════
///         CLIENT CHOOSES ONE
///      (with failover to another)
/// </summary>
public class MultiProtocolPublisherService : BackgroundService
{
    private readonly PlcTagValuesPoolService _tagPool;
    private readonly PlcSampleBufferService _sampleBuffer;
    private readonly ILogger<MultiProtocolPublisherService> _logger;
    
    // Protocol publishers (all run in parallel)
    private MqttPublisher? _mqttPublisher;
    private readonly bool _mqttEnabled;
    private readonly MqttTransportConfig _mqttConfig;
    
    // Configuration (dynamic from appsettings.json)
    private readonly int _publishIntervalMs;
    private readonly bool _enabled;
    private readonly bool _useSampleBuffer;  // Use new sample-based publishing
    
    // Statistics
    private long _publishCycles;
    private DateTime _serviceStartTime;

    public MultiProtocolPublisherService(
        PlcTagValuesPoolService tagPool,
        PlcSampleBufferService sampleBuffer,
        IConfiguration configuration,
        ILogger<MultiProtocolPublisherService> logger)
    {
        _tagPool = tagPool;
        _sampleBuffer = sampleBuffer;
        _logger = logger;

        _enabled = configuration.GetValue<bool>("PlcGateway:Transport:Enabled", true);
        _publishIntervalMs = configuration.GetValue<int>("PlcGateway:Transport:PublishIntervalMs", 1000);
        _useSampleBuffer = configuration.GetValue<bool>("PlcGateway:Transport:UseSampleBuffer", true);
        
        // MQTT configuration
        _mqttEnabled = configuration.GetValue<bool>("PlcGateway:Mqtt:Enabled", false);
        _mqttConfig = new MqttTransportConfig();
        configuration.GetSection("PlcGateway:Mqtt").Bind(_mqttConfig);

        _logger.LogInformation(
            "[MULTI-PROTOCOL] Initialized - MQTT: {Mqtt}, REST: Always, Interval: {Interval}ms, SampleBuffer: {Buffer}",
            _mqttEnabled ? "Enabled" : "Disabled",
            _publishIntervalMs,
            _useSampleBuffer ? "Enabled" : "Disabled");
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        if (!_enabled)
        {
            _logger.LogInformation("[MULTI-PROTOCOL] Service is disabled");
            return;
        }

        _logger.LogInformation("[MULTI-PROTOCOL] Service starting...");
        _serviceStartTime = DateTime.UtcNow;

        // Wait for pool to be populated
        await Task.Delay(3000, stoppingToken);

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
                    await PublishToAllProtocolsAsync(stoppingToken);
                    _publishCycles++;

                    if (_publishCycles % 60 == 0)
                    {
                        LogStatistics();
                    }
                }
                catch (Exception ex)
                {
                    _logger.LogError(ex, "[MULTI-PROTOCOL] Error in publish cycle");
                }

                // Maintain interval
                var elapsed = (DateTime.UtcNow - cycleStart).TotalMilliseconds;
                var delay = Math.Max(0, _publishIntervalMs - (int)elapsed);

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

        _logger.LogInformation("[MULTI-PROTOCOL] Service stopped");
    }

    /// <summary>
    /// Publish to ALL protocols simultaneously
    /// REST API: Data is already available via PlcController (reads from pool)
    /// MQTT: Actively publish to broker
    /// </summary>
    private async Task PublishToAllProtocolsAsync(CancellationToken ct)
    {
        // MQTT: Actively push to broker
        if (_mqttEnabled && _mqttPublisher != null)
        {
            if (_useSampleBuffer)
            {
                // NEW: Publish with sample buffer (multiple samples per tag)
                var tagSamples = _sampleBuffer.GetAndClearBuffer();
                if (tagSamples.Count > 0)
                {
                    // LOG: Show buffer contents before transmit
                    var totalSamples = tagSamples.Values.Sum(t => t.Samples.Count);
                    _logger.LogWarning("[MQTT TRANSMIT] {Time} | {TagCount} tags | {TotalSamples} total samples",
                        DateTime.Now.ToString("HH:mm:ss.fff"), tagSamples.Count, totalSamples);
                    
                    // Show first 3 tags with their sample counts
                    foreach (var kvp in tagSamples.Take(3))
                    {
                        var tag = kvp.Value;
                        var lastSample = tag.Samples.LastOrDefault();
                        _logger.LogWarning("  {TagName}: {SampleCount} samples | Latest={Value}",
                            tag.TagName, tag.Samples.Count, lastSample?.Value);
                    }
                    if (tagSamples.Count > 3)
                        _logger.LogWarning("  ... and {More} more tags", tagSamples.Count - 3);
                    
                    await _mqttPublisher.PublishWithSamplesAsync(tagSamples, _publishIntervalMs, ct);
                }
            }
            else
            {
                // LEGACY: Publish latest values only (single value per tag)
                var allValues = _tagPool.GetAllTagValues();
                if (allValues.Count > 0)
                {
                    await _mqttPublisher.PublishAsync(allValues, ct);
                }
            }
        }

        // REST API: No action needed!
        // Data is already in PlcTagValuesPoolService
        // Clients call GET /api/plc/values to fetch it
        // REST API is "pull" based - client polls

        // WebSocket/SignalR: Would broadcast here too if needed
        // await _signalRHub.BroadcastValues(allValues);
    }

    private void LogStatistics()
    {
        var uptime = DateTime.UtcNow - _serviceStartTime;
        var poolStats = _tagPool.GetStatistics();

        _logger.LogInformation(
            "[MULTI-PROTOCOL] Stats: Cycles={Cycles}, Tags={Tags}, MQTT={MqttStatus}, Mode={Mode}, Uptime={Uptime:hh\\:mm\\:ss}",
            _publishCycles,
            poolStats.TotalTags,
            _mqttPublisher?.IsConnected == true ? "Connected" : "Disabled",
            _mqttConfig.PublishMode,
            uptime);
    }

    public override async Task StopAsync(CancellationToken cancellationToken)
    {
        _logger.LogInformation("[MULTI-PROTOCOL] Service stopping...");
        await base.StopAsync(cancellationToken);
    }
}
