using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using OpcDaWebBrowser.Services.HistorianIngest.Services;
using PlcGateway.Transport;

namespace OpcDaWebBrowser.Services;

/// <summary>
/// OPC DA → MQTT Publisher Service
///
/// Reads live OPC tag values from OpcDaService (same main connection — no extra OPC conn)
/// and publishes them to MQTT broker using the same MqttPublisher used by the PLC pipeline.
///
/// TAG FILTERING (same philosophy as HistorianIngestHostedService):
///   Only tags that are ENABLED in historian_meta.tag_master AND whose server_progid
///   matches a currently-connected OPC server are published to MQTT.
///   Tags not in tag_master are silently excluded — no hard-coding, fully DB-driven.
///   MappingCacheService is already a singleton and self-refreshes via pg_notify.
///
/// TOPIC: opc/{serverProgId}/tags/bulk
///   e.g. opc/Matrikon.OPC.Simulation.1/tags/bulk
///   HMI subscribes: opc/+/tags/bulk  (wildcard) or specific server topic
///
/// PUBLISH MODE: ChangedOnly (default) — only sends tags whose value changed.
///   Full mode available via OpcMqttTransport:PublishMode config for diagnostics.
///
/// CONFIG: appsettings.json → OpcMqttTransport section
///   Must have Enabled=true and correct BrokerHost/BrokerPort.
///
/// ISOLATION: This service does NOT affect:
///   - HistorianIngestHostedService (DB writes)
///   - DataLoggingService (Parquet writes)
///   - PlcGateway MQTT (separate MqttPublisher instance)
///   An MQTT broker failure will NOT block OPC data collection or DB writes.
/// </summary>
public class OpcMqttPublisherService : BackgroundService
{
    private readonly OpcDaService _opcDaService;
    private readonly MappingCacheService _mappingCache;
    private readonly LoggingConfigService _configService;
    private readonly OpcMqttTransportConfig _mqttConfig;
    private readonly ILogger<OpcMqttPublisherService> _logger;

    private MqttPublisher? _mqttPublisher;

    // Change-detection: last published value per tagId.
    // Keys are ONLY added for tags in the current enabledOpcTagIds set.
    // Stale entries (tags later disabled in tag_master) are pruned periodically — see PruneStaleChangeDetectionEntries().
    private readonly Dictionary<string, string> _lastPublishedValue = new(StringComparer.OrdinalIgnoreCase);
    private long _sequenceId = 0;

    // Diagnostics / throttled logging state
    private int    _lastActiveTagCount   = -1;   // Detect tag-set changes between cycles
    private long   _lastInfoLogTicks     = 0;    // Throttle periodic stats log (every 30s)
    private long   _lastPurgeTicks       = 0;    // Throttle stale-entry purge (every 60s)
    private long   _totalPublishedCycles = 0;    // Cumulative cycles that sent at least 1 entry
    private long   _totalSkippedCycles   = 0;    // Cumulative cycles with nothing to publish

    public OpcMqttPublisherService(
        OpcDaService opcDaService,
        MappingCacheService mappingCache,
        LoggingConfigService configService,
        IConfiguration configuration,
        ILogger<OpcMqttPublisherService> logger)
    {
        _opcDaService = opcDaService;
        _mappingCache = mappingCache;
        _configService = configService;
        _logger = logger;

        _mqttConfig = new OpcMqttTransportConfig();
        configuration.GetSection("OpcMqttTransport").Bind(_mqttConfig);
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        if (!_mqttConfig.Enabled)
        {
            _logger.LogInformation("[OPC-MQTT] OpcMqttTransport:Enabled=false — OPC MQTT publishing disabled");
            return;
        }

        _logger.LogInformation(
            "[OPC-MQTT] Starting — broker={Host}:{Port}, mode={Mode}, maxBatch={Max}",
            _mqttConfig.BrokerHost, _mqttConfig.BrokerPort,
            _mqttConfig.PublishMode, _mqttConfig.MaxTagsPerBatch);

        // Build publisher using existing OpcMqttTransportConfig → MqttTransportConfig adapter
        var transportConfig = new MqttTransportConfig
        {
            BrokerHost      = _mqttConfig.BrokerHost,
            BrokerPort      = _mqttConfig.BrokerPort,
            ClientId        = _mqttConfig.ClientId,
            Username        = _mqttConfig.Username ?? string.Empty,
            Password        = _mqttConfig.Password ?? string.Empty,
            TopicPrefix     = _mqttConfig.TopicPrefix ?? string.Empty,
            QualityOfService = _mqttConfig.QualityOfService,
            RetainMessages  = _mqttConfig.RetainMessages,
            KeepAliveSeconds = _mqttConfig.KeepAliveSeconds,
            ReconnectDelayMs = _mqttConfig.ReconnectDelayMs,
        };

        _mqttPublisher = new MqttPublisher(transportConfig, _logger as ILogger<MqttPublisher>
            ?? Microsoft.Extensions.Logging.Abstractions.NullLogger<MqttPublisher>.Instance);

        // Get the OPC server ProgID from config (used as topic segment)
        // Falls back to "opc_server" if not yet configured — topic becomes opc/opc_server/tags/bulk
        var serverProgId = _configService.GetDecryptedProgId();
        if (string.IsNullOrEmpty(serverProgId)) serverProgId = "opc_server";

        // Initial connect attempt — non-blocking, will retry in loop
        try
        {
            await _mqttPublisher.ConnectAsync(stoppingToken);
            _logger.LogInformation("[OPC-MQTT] Connected to broker {Host}:{Port}", _mqttConfig.BrokerHost, _mqttConfig.BrokerPort);
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "[OPC-MQTT] Initial connect failed — will retry on next cycle");
        }

        const int publishIntervalMs = 1000;

        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                var allValues = _opcDaService.ReadAllTagValues();

                // ── TAG MASTER FILTER ─────────────────────────────────────────────────
                // Only publish tags that are ENABLED in historian_meta.tag_master AND
                // whose server_progid matches a currently-connected OPC server.
                // PLC tags (server_progid points to a PLC, not an OPC server) are excluded.
                // MappingCacheService self-refreshes via pg_notify + 30s fallback — no stale reads.
                var enabledMappings = _mappingCache.GetAllEnabledMappings();

                var opcProgIds = new HashSet<string>(
                    _opcDaService.GetAllConnections()
                        .Where(c => c.IsConnected)
                        .Select(c => c.ServerProgID),
                    StringComparer.OrdinalIgnoreCase);

                var enabledOpcTagIds = new HashSet<string>(
                    enabledMappings
                        .Where(m => string.IsNullOrWhiteSpace(m.ServerProgId) || opcProgIds.Contains(m.ServerProgId))
                        .Select(m => m.TagId),
                    StringComparer.OrdinalIgnoreCase);
                // ─────────────────────────────────────────────────────────────────────

                // ── STALE CHANGE-DETECTION PURGE ──────────────────────────────────────
                // When tags are disabled or removed from tag_master, their entries linger
                // in _lastPublishedValue. Purge them every 60s, or immediately when the
                // active tag set shrinks (tag disabled in DB mid-run).
                var nowTicks = Environment.TickCount64;
                bool tagSetShrunk = _lastActiveTagCount > enabledOpcTagIds.Count && _lastActiveTagCount >= 0;
                if (tagSetShrunk || (nowTicks - _lastPurgeTicks >= 60_000))
                {
                    PruneStaleChangeDetectionEntries(enabledOpcTagIds);
                    _lastPurgeTicks = nowTicks;
                }

                // ── TAG-SET CHANGE LOGGING ────────────────────────────────────────────
                if (_lastActiveTagCount != enabledOpcTagIds.Count)
                {
                    if (_lastActiveTagCount < 0)
                    {
                        // First cycle — startup info
                        _logger.LogInformation(
                            "[OPC-MQTT] Active tag set initialised: {Count} OPC tag(s) from tag_master will be published to MQTT (OPC snapshot has {Total} total tags)",
                            enabledOpcTagIds.Count, allValues.Count);
                    }
                    else if (enabledOpcTagIds.Count > _lastActiveTagCount)
                    {
                        _logger.LogInformation(
                            "[OPC-MQTT] Active tag set GREW: {Before} → {After} tags (new tag(s) enabled in tag_master)",
                            _lastActiveTagCount, enabledOpcTagIds.Count);
                    }
                    else
                    {
                        _logger.LogWarning(
                            "[OPC-MQTT] Active tag set SHRUNK: {Before} → {After} tags — tag(s) disabled or removed from tag_master. Stale change-detection entries purged.",
                            _lastActiveTagCount, enabledOpcTagIds.Count);
                    }
                    _lastActiveTagCount = enabledOpcTagIds.Count;
                }

                var filteredValues = allValues
                    .Where(v => enabledOpcTagIds.Contains(v.ItemID))
                    .ToList();

                if (filteredValues.Count > 0)
                {
                    var seq = Interlocked.Increment(ref _sequenceId);
                    _totalPublishedCycles++;

                    // Build OpcTagPublishEntry list with change detection
                    var entries = new List<OpcTagPublishEntry>(filteredValues.Count);
                    int changedCount = 0;
                    foreach (var tv in filteredValues)
                    {
                        var prevValue = _lastPublishedValue.TryGetValue(tv.ItemID, out var pv) ? pv : null;
                        var isChanged = prevValue == null || prevValue != tv.Value;

                        entries.Add(new OpcTagPublishEntry
                        {
                            TagId      = tv.ItemID,
                            Value      = tv.Value ?? string.Empty,
                            Quality    = tv.Quality ?? "U",
                            Timestamp  = tv.Timestamp,
                            SequenceId = seq,
                            IsChanged  = isChanged,
                            IsStale    = false
                        });

                        if (isChanged)
                        {
                            _lastPublishedValue[tv.ItemID] = tv.Value ?? string.Empty;
                            changedCount++;
                        }
                    }

                    // ── PERIODIC STATS LOG (every 30s) ────────────────────────────────
                    if (nowTicks - _lastInfoLogTicks >= 30_000)
                    {
                        _logger.LogInformation(
                            "[OPC-MQTT] Stats — active tags: {Active} | changed this cycle: {Changed} | publish cycles: {Published} | skipped cycles: {Skipped} | seq: {Seq}",
                            filteredValues.Count, changedCount, _totalPublishedCycles, _totalSkippedCycles, seq);
                        _lastInfoLogTicks = nowTicks;
                    }

                    // Fire-and-forget: broker failure must NEVER block this loop
                    _ = Task.Run(async () =>
                    {
                        try
                        {
                            await _mqttPublisher.PublishOpcBulkAsync(
                                entries,
                                _mqttConfig.PublishMode,
                                _mqttConfig.MaxTagsPerBatch,
                                serverProgId);
                        }
                        catch (Exception ex)
                        {
                            _logger.LogWarning(ex, "[OPC-MQTT] Publish cycle failed — broker may be unavailable");
                        }
                    }, stoppingToken);
                }
                else
                {
                    _totalSkippedCycles++;

                    // Log reason once every 30s (not every 1s cycle — would flood the log)
                    if (nowTicks - _lastInfoLogTicks >= 30_000)
                    {
                        if (allValues.Count == 0)
                            _logger.LogWarning("[OPC-MQTT] No tag values from OPC server — server not yet connected or no tags subscribed");
                        else if (enabledOpcTagIds.Count == 0)
                            _logger.LogWarning("[OPC-MQTT] No enabled OPC tags in historian_meta.tag_master — nothing to publish. Add/enable rows in tag_master to start MQTT publishing.");
                        else
                            _logger.LogWarning(
                                "[OPC-MQTT] {Total} OPC values available but 0 matched tag_master ({Active} enabled tag IDs). Check that TagId values in tag_master match OPC ItemIDs exactly.",
                                allValues.Count, enabledOpcTagIds.Count);
                        _lastInfoLogTicks = nowTicks;
                    }
                }
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "[OPC-MQTT] Error in publish loop");
            }

            await Task.Delay(publishIntervalMs, stoppingToken);
        }

        // Cleanup
        try { await _mqttPublisher.DisconnectAsync(); } catch { /* best effort */ }
        _logger.LogInformation("[OPC-MQTT] Service stopped");
    }

    /// <summary>
    /// Removes entries from the change-detection dictionary whose tag IDs are no longer
    /// in the current active (enabled, OPC-matched) tag set.
    ///
    /// This prevents unbounded growth when tags are disabled in tag_master mid-run,
    /// and prevents a re-enabled tag from skipping its first publish cycle because its
    /// stale "last value" happens to match the current live value.
    /// </summary>
    private void PruneStaleChangeDetectionEntries(HashSet<string> activeTagIds)
    {
        var staleKeys = _lastPublishedValue.Keys
            .Where(k => !activeTagIds.Contains(k))
            .ToList();

        if (staleKeys.Count == 0) return;

        foreach (var key in staleKeys)
            _lastPublishedValue.Remove(key);

        _logger.LogInformation(
            "[OPC-MQTT] Pruned {Count} stale change-detection entries for tags no longer active in tag_master: {Tags}",
            staleKeys.Count,
            string.Join(", ", staleKeys.Take(10)) + (staleKeys.Count > 10 ? $" … (+{staleKeys.Count - 10} more)" : string.Empty));
    }
}
