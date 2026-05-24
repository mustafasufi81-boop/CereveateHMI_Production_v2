namespace PlcGateway.Models;

/// <summary>
/// PLC Configuration loaded from database
/// </summary>
public class PlcConfig
{
    public int Id { get; set; }
    public string PlcId { get; set; } = "";         // Unique identifier (e.g., "PLC_PlantA_01")
    public string PlcName { get; set; } = "";       // Display name
    public string PlantId { get; set; } = "";       // Plant/Area grouping
    public string Protocol { get; set; } = "";      // "S7", "ModbusTCP", "EtherNetIP", "ABB", "Mitsubishi"
    public string IpAddress { get; set; } = "";
    public int Port { get; set; } = 102;            // Default for S7
    public bool Enabled { get; set; } = true;

    // ═══════════════════════════════════════════════════════════════════
    // POLLING CONFIGURATION
    // ═══════════════════════════════════════════════════════════════════
    public int PollingIntervalMs { get; set; } = 1000;      // Data read interval
    public int HealthCheckIntervalMs { get; set; } = 5000;  // Health check interval
    public int ConnectionTimeoutMs { get; set; } = 5000;    // Connection timeout
    public int ReadTimeoutMs { get; set; } = 3000;          // Read operation timeout

    // ═══════════════════════════════════════════════════════════════════
    // SIEMENS S7 SPECIFIC
    // ═══════════════════════════════════════════════════════════════════
    public int Rack { get; set; } = 0;
    public int Slot { get; set; } = 1;
    public string CpuType { get; set; } = "S7-1200";  // S7-300, S7-400, S7-1200, S7-1500

    // ═══════════════════════════════════════════════════════════════════
    // MODBUS SPECIFIC
    // ═══════════════════════════════════════════════════════════════════
    public byte SlaveId { get; set; } = 1;

    // ═══════════════════════════════════════════════════════════════════
    // ALLEN BRADLEY SPECIFIC
    // ═══════════════════════════════════════════════════════════════════
    public string PlcPath { get; set; } = "";  // e.g., "1,0" for backplane

    // ═══════════════════════════════════════════════════════════════════
    // ABB SPECIFIC
    // ═══════════════════════════════════════════════════════════════════
    public string AbbControllerType { get; set; } = "AC500";  // AC500, AC800M, etc.

    // ═══════════════════════════════════════════════════════════════════
    // ROCKWELL / ALLEN BRADLEY SPECIFIC
    // ═══════════════════════════════════════════════════════════════════
    public string RockwellPlcType { get; set; } = "ControlLogix";  // ControlLogix, CompactLogix, Micro800
    public bool UseConnectedMessaging { get; set; } = true;
    public int ConnectionSize { get; set; } = 4000;
    public bool AllowPacking { get; set; } = true;
    
    // ═══════════════════════════════════════════════════════════════════
    // RESILIENCE
    // ═══════════════════════════════════════════════════════════════════
    public int MaxRetries { get; set; } = 3;
    public int RetryDelayMs { get; set; } = 1000;
    public bool AutoReconnect { get; set; } = true;

    // ═══════════════════════════════════════════════════════════════════
    // METADATA
    // ═══════════════════════════════════════════════════════════════════
    public string Description { get; set; } = "";
    public string Location { get; set; } = "";
    public DateTime CreatedAt { get; set; }
    public DateTime? UpdatedAt { get; set; }
}

/// <summary>
/// Supported PLC protocol types (enum for type safety)
/// </summary>
public enum PlcProtocol
{
    SiemensS7,
    ModbusTcp,
    EtherNetIP,
    Rockwell,
    ABB,
    Mitsubishi,
    Omron,
    OpcUa
}

/// <summary>
/// Supported PLC protocols (string constants for database/config)
/// </summary>
public static class PlcProtocols
{
    public const string SiemensS7 = "S7";
    public const string ModbusTcp = "ModbusTCP";
    public const string EtherNetIp = "EtherNetIP";
    public const string Rockwell = "Rockwell";      // Allen Bradley / Rockwell
    public const string ABB = "ABB";
    public const string Mitsubishi = "Mitsubishi";
    public const string Omron = "Omron";
    public const string OpcUa = "OpcUA";
}

/// <summary>
/// Siemens CPU types
/// </summary>
public static class SiemensCpuTypes
{
    public const string S7_300 = "S7-300";
    public const string S7_400 = "S7-400";
    public const string S7_1200 = "S7-1200";
    public const string S7_1500 = "S7-1500";
}
