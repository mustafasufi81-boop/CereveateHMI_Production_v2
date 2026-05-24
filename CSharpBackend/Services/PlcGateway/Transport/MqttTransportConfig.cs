namespace PlcGateway.Transport;

/// <summary>
/// MQTT Transport Configuration
/// 
/// Configure in appsettings.json:
/// {
///   "PlcGateway": {
///     "Mqtt": {
///       "Enabled": true,
///       "BrokerHost": "localhost",
///       "BrokerPort": 1883,
///       "ClientId": "PlcGateway_Server1",
///       "TopicPrefix": "factory1",
///       "PublishMode": "PerTag",
///       "QualityOfService": 1,
///       "RetainMessages": true
///     }
///   }
/// }
/// </summary>
public class MqttTransportConfig
{
    /// <summary>
    /// Enable MQTT publishing
    /// </summary>
    public bool Enabled { get; set; } = false;

    /// <summary>
    /// MQTT Broker hostname (e.g., localhost, broker.hivemq.com)
    /// </summary>
    public string BrokerHost { get; set; } = "localhost";

    /// <summary>
    /// MQTT Broker port (1883 = plain, 8883 = TLS)
    /// </summary>
    public int BrokerPort { get; set; } = 1883;

    /// <summary>
    /// Unique client ID for this server
    /// </summary>
    public string ClientId { get; set; } = $"PlcGateway_{Environment.MachineName}_{Guid.NewGuid():N}";

    /// <summary>
    /// Username for broker authentication (optional)
    /// </summary>
    public string? Username { get; set; }

    /// <summary>
    /// Password for broker authentication (optional)
    /// </summary>
    public string? Password { get; set; }

    /// <summary>
    /// Topic prefix (e.g., "factory1" → factory1/plc/all)
    /// </summary>
    public string? TopicPrefix { get; set; }

    /// <summary>
    /// HOW TO PUBLISH MESSAGES:
    /// 
    /// Bulk   = All tags in ONE message   → plc/all
    /// PerPlc = One message per PLC       → plc/{plcId}/bulk
    /// </summary>
    public MqttPublishMode PublishMode { get; set; } = MqttPublishMode.PerPlc;

    /// <summary>
    /// QoS level: 0=AtMostOnce, 1=AtLeastOnce, 2=ExactlyOnce
    /// Recommended: 1 for reliable delivery without overhead of 2
    /// </summary>
    public int QualityOfService { get; set; } = 1;

    /// <summary>
    /// Retain messages - broker stores latest value for new subscribers
    /// </summary>
    public bool RetainMessages { get; set; } = true;

    /// <summary>
    /// Keep alive interval in seconds
    /// </summary>
    public ushort KeepAliveSeconds { get; set; } = 60;

    /// <summary>
    /// Reconnect delay after disconnect (milliseconds)
    /// </summary>
    public int ReconnectDelayMs { get; set; } = 5000;
}

/// <summary>
/// ITEM 13: Publish mode for OPC DA tag values.
/// CHANGED_ONLY (default) — only publishes tags where IsChanged=true (AF-05 fix).
/// Full — publishes every tag every cycle regardless of change (diagnostics only).
/// </summary>
public enum OpcPublishMode
{
    /// <summary>Only publish tags whose value crossed the deadband. Recommended for production.</summary>
    ChangedOnly,
    /// <summary>Publish all tags every cycle. Use only for diagnostics/testing.</summary>
    Full
}

/// <summary>
/// ITEM 13: Lightweight DTO used by PublishOpcBulkAsync.
/// Mapped from TagValueCacheEntry — keeps MqttPublisher independent of OpcDaWebBrowser types.
/// </summary>
public class OpcTagPublishEntry
{
    public required string TagId      { get; init; }
    public required string Value      { get; init; }
    public required string Quality    { get; init; }
    public DateTime        Timestamp  { get; init; }
    public long            SequenceId { get; init; }
    public bool            IsChanged  { get; init; }
    public bool            IsStale    { get; init; }
}

/// <summary>
/// Configuration for the OPC → EMQX MQTT bridge (separate from PLC transport).
/// Bound from appsettings.json → OpcMqttTransport section.
/// </summary>
public class OpcMqttTransportConfig
{
    public bool            Enabled         { get; set; } = false;
    public string          BrokerHost      { get; set; } = "localhost";
    public int             BrokerPort      { get; set; } = 1883;
    public string          ClientId        { get; set; } = "cereveate_central_opc";
    public string?         Username        { get; set; }
    public string?         Password        { get; set; }
    public string?         TopicPrefix     { get; set; }
    public int             QualityOfService{ get; set; } = 1;
    public bool            RetainMessages  { get; set; } = false;
    public ushort          KeepAliveSeconds{ get; set; } = 60;
    public int             ReconnectDelayMs{ get; set; } = 5000;
    /// <summary>AF-05: CHANGED_ONLY (default) or Full.</summary>
    public OpcPublishMode  PublishMode     { get; set; } = OpcPublishMode.ChangedOnly;
    /// <summary>AF-06: max tags per MQTT message; payloads are chunked above this.</summary>
    public int             MaxTagsPerBatch { get; set; } = 500;
}

/// <summary>
/// MQTT Publish Mode — how to organize PLC messages.
/// </summary>
public enum MqttPublishMode
{
    /// <summary>
    /// ALL tags from ALL PLCs in ONE message
    /// Topic: plc/all
    /// Best for: Small systems, simple clients
    /// </summary>
    Bulk,
    
    /// <summary>
    /// All tags from EACH PLC in separate messages
    /// Topic: plc/{plcId}/bulk
    /// Best for: Client subscribes to specific PLCs only
    /// </summary>
    PerPlc
}

/// <summary>
/// Transport types supported by the server
/// Client can consume from any of these
/// </summary>
public enum TransportType
{
    /// <summary>
    /// REST API - Client polls GET /api/plc/values
    /// </summary>
    RestApi,
    
    /// <summary>
    /// MQTT - Client subscribes to topics
    /// </summary>
    Mqtt,
    
    /// <summary>
    /// SignalR/WebSocket - Real-time push (if implemented)
    /// </summary>
    WebSocket
}
