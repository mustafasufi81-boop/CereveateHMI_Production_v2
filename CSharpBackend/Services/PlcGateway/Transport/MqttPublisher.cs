using Microsoft.Extensions.Logging;
using System.Collections.Concurrent;
using System.Net.Sockets;
using System.Text;
using System.Text.Json;
using PlcGateway.Services;

namespace PlcGateway.Transport;

/// <summary>
/// Simple MQTT Publisher (Server-Side)
/// 
/// FUNCTION:
/// - Connects to MQTT broker
/// - Publishes PLC tag values
/// - Auto-reconnect on disconnect
/// - QoS 1 for reliable delivery
/// 
/// TOPIC STRUCTURE:
/// - {plcId}                    - All tags for that PLC (topic = server_progid exactly)
/// - plc/{plcId}/tags/{tagName} - Individual tag values
/// - plc/{plcId}/bulk           - All tags for a PLC (PerPlc mode)
/// - plc/all                    - All PLCs in one message (Bulk mode, legacy)
/// 
/// CLIENT RESPONSIBILITY:
/// - Subscribe to topics
/// - Handle failover to REST if MQTT unavailable
/// </summary>
public class MqttPublisher : IDisposable
{
    private readonly MqttTransportConfig _config;
    private readonly ILogger _logger;
    
    // Simple TCP connection to MQTT broker
    private TcpClient? _tcpClient;
    private NetworkStream? _stream;
    private readonly SemaphoreSlim _connectLock = new(1, 1);
    private readonly SemaphoreSlim _publishLock = new(1, 1);
    
    // State
    private bool _isConnected;
    private DateTime _lastPublishTime;
    private long _messagesPublished;
    private ushort _packetId;

    // Reconnect backoff (500ms → 1s → 2s → 4s → ... → 30s max)
    // Prevents tight retry loop when broker is down
    private DateTime _nextRetryTime = DateTime.MinValue;
    private int _backoffMs = 500;
    private const int MaxBackoffMs = 30_000;

    public bool IsConnected => _isConnected && _tcpClient?.Connected == true;

    public MqttPublisher(MqttTransportConfig config, ILogger logger)
    {
        _config = config;
        _logger = logger;
    }

    // ═══════════════════════════════════════════════════════════════════
    // CONNECTION
    // ═══════════════════════════════════════════════════════════════════

    public async Task<bool> ConnectAsync(CancellationToken ct = default)
    {
        await _connectLock.WaitAsync(ct);
        try
        {
            if (IsConnected) return true;

            // Retry guard — do NOT attempt reconnect until backoff window expires
            if (DateTime.UtcNow < _nextRetryTime)
            {
                _logger.LogDebug("[MQTT PUB] Reconnect suppressed by backoff (next attempt in {Sec:F1}s)",
                    (_nextRetryTime - DateTime.UtcNow).TotalSeconds);
                return false;
            }

            _logger.LogInformation("[MQTT PUB] Connecting to {Host}:{Port}...", 
                _config.BrokerHost, _config.BrokerPort);

            // TCP connection
            _tcpClient = new TcpClient();
            await _tcpClient.ConnectAsync(_config.BrokerHost, _config.BrokerPort, ct);
            _stream = _tcpClient.GetStream();

            // MQTT CONNECT packet
            var connectPacket = BuildConnectPacket();
            await _stream.WriteAsync(connectPacket, ct);

            // Read CONNACK
            var response = new byte[4];
            var bytesRead = await _stream.ReadAsync(response.AsMemory(0, 4), ct);
            
            if (bytesRead >= 2 && response[0] == 0x20 && response[3] == 0x00)
            {
                _isConnected = true;
                _backoffMs = 500;   // Reset backoff on success
                _logger.LogInformation("[MQTT PUB] Connected to broker successfully");
                return true;
            }

            // Broker rejected — apply backoff
            _backoffMs = Math.Min(_backoffMs * 2, MaxBackoffMs);
            _nextRetryTime = DateTime.UtcNow.AddMilliseconds(_backoffMs);
            _logger.LogWarning("[MQTT PUB] Connection rejected by broker — next retry in {Ms}ms", _backoffMs);
            return false;
        }
        catch (Exception ex)
        {
            // Apply backoff on exception
            _backoffMs = Math.Min(_backoffMs * 2, MaxBackoffMs);
            _nextRetryTime = DateTime.UtcNow.AddMilliseconds(_backoffMs);
            _logger.LogError(ex, "[MQTT PUB] Connection failed — next retry in {Ms}ms", _backoffMs);
            return false;
        }
        finally
        {
            _connectLock.Release();
        }
    }

    public async Task DisconnectAsync()
    {
        try
        {
            if (_stream != null && _isConnected)
            {
                // MQTT DISCONNECT packet
                await _stream.WriteAsync(new byte[] { 0xE0, 0x00 });
            }
        }
        catch { }
        finally
        {
            _isConnected = false;
            _stream?.Dispose();
            _tcpClient?.Dispose();
            _logger.LogInformation("[MQTT PUB] Disconnected");
        }
    }

    // ═══════════════════════════════════════════════════════════════════
    // PUBLISHING
    // ═══════════════════════════════════════════════════════════════════

    /// <summary>
    /// Publish tag values based on configured mode:
    /// - Bulk: All tags in ONE message → plc/all
    /// - PerPlc: One message per PLC → plc/{plcId}/bulk
    /// </summary>
    public async Task<bool> PublishAsync(IReadOnlyList<PlcTagValueCacheEntry> values, CancellationToken ct = default)
    {
        if (!IsConnected)
        {
            if (!await ConnectAsync(ct))
            {
                return false;
            }
        }

        return _config.PublishMode switch
        {
            MqttPublishMode.Bulk => await PublishBulkAsync(values, ct),
            MqttPublishMode.PerPlc => await PublishPerPlcAsync(values, ct),
            _ => await PublishBulkAsync(values, ct)
        };
    }

    /// <summary>
    /// BULK MODE: All tags in ONE message
    /// Topic: plc/all
    /// </summary>
    private async Task<bool> PublishBulkAsync(IReadOnlyList<PlcTagValueCacheEntry> values, CancellationToken ct)
    {
        await _publishLock.WaitAsync(ct);
        try
        {
            var payload = new
            {
                timestamp = DateTime.UtcNow,
                count = values.Count,
                values = values.Select(v => new
                {
                    plcId = v.PlcId,
                    tag = v.TagName,
                    address = v.Address,
                    value = v.Value,
                    quality = v.Quality.ToString(),
                    dataType = v.DataType,
                    timestamp = v.Timestamp
                })
            };

            var json = JsonSerializer.Serialize(payload, _jsonOptions);
            var topic = BuildTopic("plc/all");

            // IMPORTANT: Do NOT retain value messages - prevents stale data on broker!
            return await PublishToTopicAsync(topic, json, ct, retain: false);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "[MQTT PUB] Bulk publish failed");
            _isConnected = false;
            return false;
        }
        finally
        {
            _publishLock.Release();
        }
    }

    /// <summary>
    /// DYNAMIC PUBLISH: Publish tags with multiple samples per tag.
    /// 
    /// TOPIC STRATEGY (NO HARDCODING):
    /// Tags are grouped by their PlcId. Each PLC group is published to its own
    /// dedicated topic: {plcId}  (the server_progid value itself, e.g. "Rockwel_PLC_001")
    /// 
    /// This means the topic is always derived from the actual PLC identifier
    /// stored in the database (tag_master.server_progid / mqtt_topic_config.plc_name).
    /// Adding a new PLC automatically gets its own topic without any code change.
    /// 
    /// PAYLOAD FORMAT (per PLC):
    /// {
    ///   "timestamp": "2025-01-01T00:00:00Z",
    ///   "publishIntervalMs": 1000,
    ///   "tagCount": 32,
    ///   "totalSamples": 160,
    ///   "values": [
    ///     {
    ///       "plcId": "Rockwel_PLC_001",
    ///       "tag": "Pump_RPM",
    ///       "address": "Pump_RPM",
    ///       "dataType": "float",
    ///       "scanRateMs": 200,
    ///       "sampleCount": 5,
    ///       "samples": [
    ///         { "value": 74.5, "quality": "Good", "timestamp": "..." },
    ///         ...
    ///       ],
    ///       "value": 74.6,
    ///       "quality": "Good",
    ///       "timestamp": "..."
    ///     }
    ///   ]
    /// }
    /// </summary>
    public async Task<bool> PublishWithSamplesAsync(
        Dictionary<string, TagWithSamples> tagSamples, 
        int publishIntervalMs,
        CancellationToken ct = default)
    {
        if (!IsConnected)
        {
            if (!await ConnectAsync(ct))
            {
                return false;
            }
        }

        await _publishLock.WaitAsync(ct);
        try
        {
            // Group tags by PlcId — each PLC publishes to its own topic
            var byPlc = tagSamples.Values.GroupBy(t => t.PlcId);
            var allSuccess = true;

            foreach (var plcGroup in byPlc)
            {
                var plcId = plcGroup.Key;
                var plcTags = plcGroup.ToList();
                var totalSamples = plcTags.Sum(t => t.SampleCount);

                var payload = new
                {
                    timestamp = DateTime.UtcNow,
                    publishIntervalMs = publishIntervalMs,
                    tagCount = plcTags.Count,
                    totalSamples = totalSamples,
                    values = plcTags.Select(t => new
                    {
                        plcId = t.PlcId,
                        tag = t.TagName,
                        address = t.Address,
                        dataType = t.DataType,
                        scanRateMs = t.ScanRateMs,
                        sampleCount = t.SampleCount,
                        samples = t.Samples.Select(s => new
                        {
                            value = s.Value,
                            quality = s.Quality,
                            timestamp = s.Timestamp
                        }),
                        // Latest value for backward compatibility
                        value = t.Samples.LastOrDefault()?.Value,
                        quality = t.Samples.LastOrDefault()?.Quality ?? "Unknown",
                        timestamp = t.Samples.LastOrDefault()?.Timestamp ?? DateTime.UtcNow
                    })
                };

                var json = JsonSerializer.Serialize(payload, _jsonOptions);

                // Topic IS the server_progid (plcId) exactly — no prefix, no suffix.
                // e.g. PlcId "Rockwel_PLC_001" → topic "Rockwel_PLC_001"
                // mqtt_topic_config.topic_name must equal plc_name (the server_progid) exactly.
                var topic = BuildTopic(plcId);

                // IMPORTANT: Do NOT retain value messages - prevents stale data on broker!
                var success = await PublishToTopicAsync(topic, json, ct, retain: false);

                if (success)
                {
                    _logger.LogDebug(
                        "[MQTT PUB] [{PlcId}] → {Topic} | {Tags} tags, {Samples} samples (NO RETAIN)",
                        plcId, topic, plcTags.Count, totalSamples);
                }
                else
                {
                    allSuccess = false;
                }
            }

            return allSuccess;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "[MQTT PUB] Samples publish failed");
            _isConnected = false;
            return false;
        }
        finally
        {
            _publishLock.Release();
        }
    }

    /// <summary>
    /// PER-PLC MODE: One message per PLC
    /// Topic: plc/{plcId}/bulk
    /// </summary>
    private async Task<bool> PublishPerPlcAsync(IReadOnlyList<PlcTagValueCacheEntry> values, CancellationToken ct)
    {
        await _publishLock.WaitAsync(ct);
        try
        {
            // Group by PLC
            var byPlc = values.GroupBy(v => v.PlcId);
            var allSuccess = true;

            foreach (var plcGroup in byPlc)
            {
                var plcId = plcGroup.Key;
                var plcValues = plcGroup.ToList();

                var payload = new
                {
                    plcId = plcId,
                    timestamp = DateTime.UtcNow,
                    count = plcValues.Count,
                    values = plcValues.Select(v => new
                    {
                        tag = v.TagName,
                        address = v.Address,
                        value = v.Value,
                        quality = v.Quality.ToString(),
                        dataType = v.DataType,
                        timestamp = v.Timestamp
                    })
                };

                var json = JsonSerializer.Serialize(payload, _jsonOptions);
                var topic = BuildTopic($"plc/{plcId}/bulk");

                // IMPORTANT: Do NOT retain value messages - prevents stale data on broker!
                if (!await PublishToTopicAsync(topic, json, ct, retain: false))
                {
                    allSuccess = false;
                }
            }

            return allSuccess;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "[MQTT PUB] Per-PLC publish failed");
            _isConnected = false;
            return false;
        }
        finally
        {
            _publishLock.Release();
        }
    }

    private string BuildTopic(string baseTopic)
    {
        return string.IsNullOrEmpty(_config.TopicPrefix) 
            ? baseTopic 
            : $"{_config.TopicPrefix}/{baseTopic}";
    }

    private static readonly JsonSerializerOptions _jsonOptions = new() 
    { 
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase 
    };

    /// <summary>
    /// Publish an arbitrary JSON string to a fully-qualified MQTT topic.
    /// TopicPrefix is NOT applied — caller provides the complete topic path.
    /// Used by alarm and interlock evaluation services for event notifications.
    /// Does NOT retain (event messages must never be stale).
    /// </summary>
    public async Task<bool> PublishJsonAsync(string topic, string json, CancellationToken ct = default)
    {
        if (!IsConnected && !await ConnectAsync(ct))
            return false;

        return await PublishToTopicAsync(topic, json, ct, retain: false);
    }

    /// <summary>
    /// Publish to a specific topic
    /// </summary>
    /// <param name="topic">MQTT topic</param>
    /// <param name="payload">JSON payload</param>
    /// <param name="ct">Cancellation token</param>
    /// <param name="retain">Override retain flag (null = use config default)</param>
    private async Task<bool> PublishToTopicAsync(string topic, string payload, CancellationToken ct, bool? retain = null)
    {
        if (_stream == null || !IsConnected)
        {
            return false;
        }

        try
        {
            var packet = BuildPublishPacket(topic, payload, retain);
            await _stream.WriteAsync(packet, ct);

            // For QoS 1, wait for PUBACK
            if (_config.QualityOfService >= 1)
            {
                var ack = new byte[4];
                var timeout = Task.Delay(5000, ct);
                var read = _stream.ReadAsync(ack, 0, 4, ct);

                if (await Task.WhenAny(read, timeout) == timeout)
                {
                    _logger.LogWarning("[MQTT PUB] PUBACK timeout for topic: {Topic}", topic);
                    return false;
                }

                if (ack[0] != 0x40) // PUBACK
                {
                    return false;
                }
            }

            _messagesPublished++;
            _lastPublishTime = DateTime.UtcNow;
            return true;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "[MQTT PUB] Publish failed to topic: {Topic}", topic);
            _isConnected = false;
            return false;
        }
    }

    // ═══════════════════════════════════════════════════════════════════
    // MQTT PACKET BUILDERS
    // ═══════════════════════════════════════════════════════════════════

    private byte[] BuildConnectPacket()
    {
        var packet = new List<byte>();
        
        // Variable header
        var variableHeader = new List<byte>();
        
        // Protocol name "MQTT"
        variableHeader.Add(0x00); variableHeader.Add(0x04);
        variableHeader.AddRange(Encoding.UTF8.GetBytes("MQTT"));
        
        // Protocol level (4 = MQTT 3.1.1)
        variableHeader.Add(0x04);
        
        // Connect flags
        byte connectFlags = 0x02; // Clean session
        if (!string.IsNullOrEmpty(_config.Username))
        {
            connectFlags |= 0x80; // Username flag
            if (!string.IsNullOrEmpty(_config.Password))
            {
                connectFlags |= 0x40; // Password flag
            }
        }
        variableHeader.Add(connectFlags);
        
        // Keep alive (60 seconds)
        variableHeader.Add((byte)(_config.KeepAliveSeconds >> 8));
        variableHeader.Add((byte)(_config.KeepAliveSeconds & 0xFF));
        
        // Payload
        var payload = new List<byte>();
        
        // Client ID
        var clientIdBytes = Encoding.UTF8.GetBytes(_config.ClientId);
        payload.Add((byte)(clientIdBytes.Length >> 8));
        payload.Add((byte)(clientIdBytes.Length & 0xFF));
        payload.AddRange(clientIdBytes);
        
        // Username
        if (!string.IsNullOrEmpty(_config.Username))
        {
            var userBytes = Encoding.UTF8.GetBytes(_config.Username);
            payload.Add((byte)(userBytes.Length >> 8));
            payload.Add((byte)(userBytes.Length & 0xFF));
            payload.AddRange(userBytes);
            
            // Password
            if (!string.IsNullOrEmpty(_config.Password))
            {
                var passBytes = Encoding.UTF8.GetBytes(_config.Password);
                payload.Add((byte)(passBytes.Length >> 8));
                payload.Add((byte)(passBytes.Length & 0xFF));
                payload.AddRange(passBytes);
            }
        }
        
        // Fixed header
        var remainingLength = variableHeader.Count + payload.Count;
        packet.Add(0x10); // CONNECT
        packet.AddRange(EncodeRemainingLength(remainingLength));
        packet.AddRange(variableHeader);
        packet.AddRange(payload);
        
        return packet.ToArray();
    }

    private byte[] BuildPublishPacket(string topic, string payload, bool? retainOverride = null)
    {
        var packet = new List<byte>();
        
        // Variable header
        var variableHeader = new List<byte>();
        
        // Topic
        var topicBytes = Encoding.UTF8.GetBytes(topic);
        variableHeader.Add((byte)(topicBytes.Length >> 8));
        variableHeader.Add((byte)(topicBytes.Length & 0xFF));
        variableHeader.AddRange(topicBytes);
        
        // Packet ID (for QoS > 0)
        if (_config.QualityOfService > 0)
        {
            _packetId++;
            variableHeader.Add((byte)(_packetId >> 8));
            variableHeader.Add((byte)(_packetId & 0xFF));
        }
        
        // Payload
        var payloadBytes = Encoding.UTF8.GetBytes(payload);
        
        // Fixed header
        // IMPORTANT: For VALUE topics, DO NOT retain - prevents stale data on broker!
        // Only health/status topics should be retained
        bool shouldRetain = retainOverride ?? _config.RetainMessages;
        
        byte fixedHeader = 0x30; // PUBLISH
        if (_config.QualityOfService == 1) fixedHeader |= 0x02;
        if (_config.QualityOfService == 2) fixedHeader |= 0x04;
        if (shouldRetain) fixedHeader |= 0x01;
        
        var remainingLength = variableHeader.Count + payloadBytes.Length;
        packet.Add(fixedHeader);
        packet.AddRange(EncodeRemainingLength(remainingLength));
        packet.AddRange(variableHeader);
        packet.AddRange(payloadBytes);
        
        return packet.ToArray();
    }

    private static byte[] EncodeRemainingLength(int length)
    {
        var result = new List<byte>();
        do
        {
            var encodedByte = (byte)(length % 128);
            length /= 128;
            if (length > 0)
            {
                encodedByte |= 0x80;
            }
            result.Add(encodedByte);
        } while (length > 0);
        
        return result.ToArray();
    }

    // ═══════════════════════════════════════════════════════════════════
    // HEALTH METRICS PUBLISHING
    // ═══════════════════════════════════════════════════════════════════

    /// <summary>
    /// Publish PLC health metrics to plc/health topic
    /// Called every 3 seconds by HealthPublisherService
    /// </summary>
    public async Task<bool> PublishHealthAsync(AllPlcHealthMetrics healthMetrics, CancellationToken ct = default)
    {
        if (!IsConnected)
        {
            if (!await ConnectAsync(ct))
            {
                return false;
            }
        }

        await _publishLock.WaitAsync(ct);
        try
        {
            var json = JsonSerializer.Serialize(healthMetrics, _jsonOptions);
            var topic = BuildTopic("plc/health");

            var success = await PublishToTopicAsync(topic, json, ct);
            
            if (success)
            {
                _logger.LogDebug(
                    "[MQTT PUB] Published health for {PlcCount} PLCs ({Connected} connected)",
                    healthMetrics.PlcCount, healthMetrics.ConnectedCount);
            }

            return success;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "[MQTT PUB] Health publish failed");
            _isConnected = false;
            return false;
        }
        finally
        {
            _publishLock.Release();
        }
    }

    // ═══════════════════════════════════════════════════════════════
    // ITEM 13 — OPC DA PUBLISHING
    // Publishes OPC DA tag values to topic: opc/tags/bulk
    // Called by DataLoggingService every OPC poll cycle (item 15).
    // Respects OpcPublishMode:
    //   CHANGED_ONLY → only sends tags where IsChanged=true (default, AF-05 fix)
    //   FULL         → sends all tags every cycle (diagnostics only)
    // Payload is chunked to MaxTagsPerBatch to avoid EMQX message-size limits (AF-06).
    // Publish is wrapped in a 2-second timeout guard (AF-13).
    // ═══════════════════════════════════════════════════════════════

    /// <summary>
    /// ITEM 13: Publish OPC DA tag values to EMQX.
    /// Caller passes ALL pool values; this method filters by mode internally.
    /// Fire-and-forget from DataLoggingService — never awaited on the poll loop.
    /// Topic: opc/tags/bulk (or opc/tags/bulk/{batchIndex} for chunked payloads)
    /// </summary>
    /// <param name="allPoolValues">Full pool snapshot from TagValuesPoolService</param>
    /// <param name="publishMode">CHANGED_ONLY or FULL (from OpcMqttTransport config)</param>
    /// <param name="maxTagsPerBatch">Max tags per MQTT message — chunked above this (AF-06)</param>
    /// <param name="serverProgId">OPC server ProgID embedded in topic — e.g. Matrikon.OPC.Simulation.1.
    /// Allows HMI to subscribe per-server: opc/{progId}/tags/bulk</param>
    public async Task PublishOpcBulkAsync(
        IReadOnlyList<OpcTagPublishEntry> allPoolValues,
        OpcPublishMode publishMode = OpcPublishMode.ChangedOnly,
        int maxTagsPerBatch = 500,
        string? serverProgId = null)
    {
        if (allPoolValues == null || allPoolValues.Count == 0)
            return;

        // Ensure connected — backoff guard is inside ConnectAsync
        if (!IsConnected)
        {
            using var connectCts = new CancellationTokenSource(TimeSpan.FromSeconds(2));
            try { await ConnectAsync(connectCts.Token); }
            catch (OperationCanceledException) { return; } // broker unreachable, skip cycle
            if (!IsConnected) return;
        }

        // AF-05: filter to changed-only unless full mode requested
        var tagsToPublish = publishMode == OpcPublishMode.Full
            ? allPoolValues
            : allPoolValues.Where(t => t.IsChanged).ToList();

        if (tagsToPublish.Count == 0)
        {
            _logger.LogDebug("[MQTT OPC] CHANGED_ONLY: no changed tags this cycle — skipping publish");
            return;
        }

        // AF-06: chunk into batches to avoid exceeding EMQX max message size
        var chunks = tagsToPublish
            .Select((t, i) => (t, i))
            .GroupBy(x => x.i / maxTagsPerBatch)
            .Select(g => g.Select(x => x.t).ToList())
            .ToList();

        // Topic embeds ProgID so HMI can subscribe per-source:
        //   opc/Matrikon.OPC.Simulation.1/tags/bulk
        //   opc/SomeOther.OPC.Server/tags/bulk
        // HMI subscribes: opc/+/tags/bulk  (wildcard) or opc/{progId}/tags/bulk (specific)
        var safeProgId = string.IsNullOrWhiteSpace(serverProgId)
            ? "unknown"
            : serverProgId.Replace(' ', '_');
        var topicBase = $"opc/{safeProgId}/tags/bulk";

        var batchIndex = 0;
        foreach (var chunk in chunks)
        {
            var topic = chunks.Count == 1
                ? BuildTopic(topicBase)
                : BuildTopic($"{topicBase}/{batchIndex}");

            var payload = new
            {
                timestamp = DateTime.UtcNow,
                source = "opc_da",
                serverProgId = serverProgId,          // HMI uses this to know which OPC server
                mode = publishMode.ToString(),
                tagCount = chunk.Count,
                batchIndex = batchIndex,
                totalBatches = chunks.Count,
                values = chunk.Select(v => new
                {
                    tagId      = v.TagId,
                    value      = v.Value,
                    quality    = v.Quality,
                    timestamp  = v.Timestamp,
                    sequenceId = v.SequenceId,
                    isChanged  = v.IsChanged,
                    isStale    = v.IsStale
                })
            };

            var json = JsonSerializer.Serialize(payload, _jsonOptions);

            // AF-13: 2-second timeout guard — never hang the caller
            using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(2));
            try
            {
                await _publishLock.WaitAsync(cts.Token);
                try
                {
                    // retain: false — OPC value topics must NEVER be retained (stale data rule)
                    await PublishToTopicAsync(topic, json, cts.Token, retain: false);
                    _logger.LogDebug(
                        "[MQTT OPC] Published {Tags} tags (batch {B}/{T}) to {Topic}",
                        chunk.Count, batchIndex + 1, chunks.Count, topic);
                }
                finally
                {
                    _publishLock.Release();
                }
            }
            catch (OperationCanceledException)
            {
                _logger.LogWarning("[MQTT OPC] Publish batch {B} timed out after 2s — skipping cycle", batchIndex);
                _isConnected = false;
                return;
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "[MQTT OPC] Publish batch {B} failed", batchIndex);
                _isConnected = false;
                return;
            }

            batchIndex++;
        }
    }

    public void Dispose()
    {
        _stream?.Dispose();
        _tcpClient?.Dispose();
        _connectLock.Dispose();
        _publishLock.Dispose();
    }
}
