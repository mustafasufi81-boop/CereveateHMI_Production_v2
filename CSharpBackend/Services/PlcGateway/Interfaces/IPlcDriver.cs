using PlcGateway.Models;

namespace PlcGateway.Interfaces;

/// <summary>
/// Universal PLC Driver Interface
/// Implement this for each PLC brand/protocol
/// 
/// CRITICAL: Each driver instance is ISOLATED - one per PLC connection
/// Do NOT share driver instances between PLCs!
/// 
/// Supports: Siemens S7, Allen Bradley, Modbus TCP, ABB, Mitsubishi, Omron
/// </summary>
public interface IPlcDriver : IDisposable
{
    // ═══════════════════════════════════════════════════════════════════
    // IDENTITY
    // ═══════════════════════════════════════════════════════════════════
    string DriverName { get; }     // "SiemensS7", "ModbusTcp", etc.
    string Protocol { get; }       // "S7Comm", "Modbus TCP", etc.

    // ═══════════════════════════════════════════════════════════════════
    // STATE
    // ═══════════════════════════════════════════════════════════════════
    bool IsConnected { get; }
    DateTime LastReadTime { get; }
    int FailureCount { get; }

    // ═══════════════════════════════════════════════════════════════════
    // LIFECYCLE
    // ═══════════════════════════════════════════════════════════════════
    
    /// <summary>
    /// Initialize driver with configuration and tags
    /// Called ONCE before Connect
    /// </summary>
    Task<bool> InitializeAsync(PlcDriverConfig config, List<PlcTagDefinition> tags);
    
    /// <summary>
    /// Connect to PLC
    /// </summary>
    Task<bool> ConnectAsync();
    
    /// <summary>
    /// Disconnect from PLC
    /// </summary>
    Task DisconnectAsync();

    // ═══════════════════════════════════════════════════════════════════
    // DATA
    // ═══════════════════════════════════════════════════════════════════
    
    /// <summary>
    /// Read ALL configured tags in ONE batch operation
    /// This is the main polling method - called every cycle
    /// </summary>
    Task<PlcReadResult> ReadAllTagsAsync();
    
    /// <summary>
    /// Read SPECIFIC tags by address (for per-tag scan rate scheduling)
    /// </summary>
    Task<PlcReadResult> ReadTagsAsync(IEnumerable<string> tagAddresses);
    
    /// <summary>
    /// Health check - lightweight connectivity test
    /// </summary>
    Task<PlcHealthStatus> CheckHealthAsync();
}

// ═══════════════════════════════════════════════════════════════════════════
// UNIFIED TAG DEFINITION (Used by Drivers and Services)
// ═══════════════════════════════════════════════════════════════════════════

/// <summary>
/// Tag definition - UNIFIED across all services
/// </summary>
public class PlcTagDefinition
{
    public string TagId { get; set; } = "";         // Unique identifier
    public string PlcId { get; set; } = "";         // Parent PLC
    public string Address { get; set; } = "";       // PLC address (e.g., "DB100.DBD0", "HR100")
    public string TagName { get; set; } = "";       // Human-readable name
    public string DataType { get; set; } = "Float"; // Data type as string for flexibility
    public string Description { get; set; } = "";   // Tag description
    public string Unit { get; set; } = "";          // Engineering unit ("°C", "bar", "RPM")
    public double ScaleFactor { get; set; } = 1.0;  // Raw * Scale = Engineering value
    public double OffsetValue { get; set; } = 0.0;  // (Raw * Scale) + Offset
    public double DeadbandValue { get; set; } = 0.0; // Change threshold (0 = no deadband, cache all values)
    public bool DbLoggingEnabled { get; set; } = true;
    public int DbLoggingIntervalMs { get; set; } = 1000; // DB write interval (different from scan rate)
    public int ScanRateMs { get; set; } = 1000;      // PLC scan rate - how often to READ from PLC (default 1000ms)
    public bool ParquetLoggingEnabled { get; set; } = false;
    public bool Enabled { get; set; } = true;
}

// ═══════════════════════════════════════════════════════════════════════════
// DRIVER CONFIGURATION (Passed to driver.InitializeAsync)
// ═══════════════════════════════════════════════════════════════════════════

/// <summary>
/// Driver configuration - passed to IPlcDriver.InitializeAsync
/// </summary>
public class PlcDriverConfig
{
    public string PlcId { get; set; } = "";
    public string PlcName { get; set; } = "";
    public string PlantId { get; set; } = "";
    public PlcProtocol Protocol { get; set; }
    public string IpAddress { get; set; } = "";
    public int Port { get; set; }
    public bool Enabled { get; set; } = true;
    
    // Timing
    public int PollingIntervalMs { get; set; } = 1000;
    public int TimeoutMs { get; set; } = 3000;
    public int RetryCount { get; set; } = 3;
    public int ReconnectDelayMs { get; set; } = 5000;

    // Protocol-specific configurations
    public S7DriverConfig? S7Config { get; set; }
    public ModbusDriverConfig? ModbusConfig { get; set; }
    public EtherNetIpDriverConfig? EtherNetIpConfig { get; set; }
    public RockwellDriverConfig? RockwellConfig { get; set; }
    public AbbDriverConfig? AbbConfig { get; set; }
    public MitsubishiDriverConfig? MitsubishiConfig { get; set; }
    public OmronDriverConfig? OmronConfig { get; set; }
}

// ═══════════════════════════════════════════════════════════════════════════
// PROTOCOL-SPECIFIC DRIVER CONFIGS
// ═══════════════════════════════════════════════════════════════════════════

/// <summary>
/// Siemens S7 driver config
/// </summary>
public class S7DriverConfig
{
    public string CpuType { get; set; } = "S71200";
    public short Rack { get; set; } = 0;
    public short Slot { get; set; } = 1;
}

/// <summary>
/// Modbus TCP driver config
/// </summary>
public class ModbusDriverConfig
{
    public byte SlaveId { get; set; } = 1;
    public int RegisterStartAddress { get; set; } = 0;
    public bool BigEndian { get; set; } = true;
}

/// <summary>
/// EtherNet/IP driver config
/// </summary>
public class EtherNetIpDriverConfig
{
    public string Path { get; set; } = "1,0";
    public string PlcType { get; set; } = "ControlLogix";
    public int ConnectionSize { get; set; } = 4000;
    public bool UseConnectedMessaging { get; set; } = true;
}

/// <summary>
/// Rockwell/Allen Bradley driver config
/// </summary>
public class RockwellDriverConfig
{
    public string PlcType { get; set; } = "ControlLogix";
    public string Path { get; set; } = "1,0";
    public int ConnectionSize { get; set; } = 4000;
    public bool AllowPacking { get; set; } = true;
    public bool UseConnectedMessaging { get; set; } = true;
}

/// <summary>
/// ABB driver config
/// </summary>
public class AbbDriverConfig
{
    public string PlcModel { get; set; } = "AC500";
    public string Protocol { get; set; } = "ModbusTcp";
    public byte SlaveId { get; set; } = 1;
}

/// <summary>
/// Mitsubishi driver config (MC Protocol / SLMP)
/// </summary>
public class MitsubishiDriverConfig
{
    public string PlcType { get; set; } = "Q";
    public string Protocol { get; set; } = "MC3E";
    public int NetworkNumber { get; set; } = 0;
    public int StationNumber { get; set; } = 0xFF;
}

/// <summary>
/// Omron driver config (FINS)
/// </summary>
public class OmronDriverConfig
{
    public string PlcType { get; set; } = "CJ2";
    public byte DestinationNetworkAddress { get; set; } = 0;
    public byte DestinationNodeNumber { get; set; } = 0;
    public byte DestinationUnitAddress { get; set; } = 0;
    public byte SourceNetworkAddress { get; set; } = 0;
    public byte SourceNodeNumber { get; set; } = 0;
    public byte SourceUnitAddress { get; set; } = 0;
}

// ═══════════════════════════════════════════════════════════════════════════
// READ RESULTS
// ═══════════════════════════════════════════════════════════════════════════

/// <summary>
/// Result of batch read operation
/// </summary>
public class PlcReadResult
{
    public string PlcId { get; set; } = "";
    public bool Success { get; set; }
    public DateTime Timestamp { get; set; }
    public long ReadDurationMs { get; set; }
    public int TagsRequested { get; set; }
    public int TagsRead { get; set; }
    public int TagsFailed { get; set; }
    public string? ErrorMessage { get; set; }
    public List<PlcTagValue> Values { get; set; } = new();
}

/// <summary>
/// Single tag value after read (record for with-expression support)
/// </summary>
public record PlcTagValue
{
    public string TagId { get; init; } = "";
    public string PlcId { get; init; } = "";
    public string Address { get; init; } = "";
    public string TagName { get; init; } = "";
    public object? Value { get; init; }
    public double? NumericValue { get; init; }
    public string StringValue { get; init; } = "";
    public string DataType { get; init; } = "";
    public PlcQuality Quality { get; init; }
    public DateTime Timestamp { get; init; }
    public DateTime CachedAt { get; init; }
    public string Unit { get; init; } = "";
}

/// <summary>
/// Quality indicator
/// </summary>
public enum PlcQuality
{
    Good,
    Bad,
    Uncertain,
    CommError,
    NotConnected,
    NotConfigured
}

// ═══════════════════════════════════════════════════════════════════════════
// HEALTH STATUS
// ═══════════════════════════════════════════════════════════════════════════

/// <summary>
/// Health check result
/// </summary>
public class PlcHealthStatus
{
    public string PlcId { get; set; } = "";
    public string PlcName { get; set; } = "";
    public string Protocol { get; set; } = "";
    public string IpAddress { get; set; } = "";
    public bool IsConnected { get; set; }
    public bool IsHealthy { get; set; }
    public DateTime CheckTime { get; set; }
    public long ResponseTimeMs { get; set; }
    public int ConsecutiveFailures { get; set; }
    public DateTime? LastSuccessfulRead { get; set; }
    public string? StatusMessage { get; set; }
    public int ConfiguredTags { get; set; }
    public int ActiveTags { get; set; }
}
