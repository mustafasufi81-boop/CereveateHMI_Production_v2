using Microsoft.Extensions.Logging;
using Npgsql;
using PlcGateway.Interfaces;
using PlcGateway.Models;
using System.Text.Json;

namespace PlcGateway.Services;

/// <summary>
/// Loads PLC configurations from historian_meta.tag_master (primary)
/// with fallback to appsettings.json PlcGateway:Connections section
/// </summary>
public class PlcConfigLoaderService
{
    private readonly string? _connectionString;
    private readonly IConfiguration _configuration;
    private readonly ILogger<PlcConfigLoaderService> _logger;
    private bool _databaseAvailable = true;

    public PlcConfigLoaderService(
        IConfiguration configuration,
        ILogger<PlcConfigLoaderService> logger)
    {
        _configuration = configuration;
        _connectionString = configuration.GetConnectionString("PlcGateway") 
            ?? configuration.GetConnectionString("Historian");
        _logger = logger;
        
        if (string.IsNullOrEmpty(_connectionString))
        {
            _logger.LogWarning("[PLC Config] No database connection string found, will use appsettings.json fallback");
            _databaseAvailable = false;
        }
    }

    /// <summary>
    /// Load all enabled PLCs - tries database first, falls back to appsettings.json
    /// </summary>
    public async Task<List<PlcConfigEntry>> LoadAllEnabledPlcsAsync()
    {
        // Try database first
        var configs = await LoadFromDatabaseAsync();
        
        if (configs.Count > 0)
        {
            _logger.LogInformation("[CONFIG LOADER] ✅ Loaded {PlcCount} PLCs with {TagCount} tags from DATABASE",
                configs.Count, configs.Sum(c => c.Tags.Count));

            // Auto-register MQTT topics: topic_name = server_progid (PlcId) exactly.
            // Ensures adding a PLC to tag_master automatically creates its MQTT subscription
            // without any manual DB step or code change.
            await EnsureMqttTopicsRegisteredAsync(configs.Select(c => c.PlcId).ToList());

            return configs;
        }

        // Fallback to appsettings.json
        _logger.LogWarning("[CONFIG LOADER] Database returned no PLCs, trying appsettings.json fallback...");
        configs = LoadFromAppSettings();
        
        if (configs.Count > 0)
        {
            _logger.LogInformation("[CONFIG LOADER] ✅ Loaded {PlcCount} PLCs with {TagCount} tags from APPSETTINGS.JSON",
                configs.Count, configs.Sum(c => c.Tags.Count));

            await EnsureMqttTopicsRegisteredAsync(configs.Select(c => c.PlcId).ToList());
        }
        else
        {
            _logger.LogError("[CONFIG LOADER] ❌ No PLC configuration found in database OR appsettings.json!");
        }

        return configs;
    }

    /// <summary>
    /// Auto-registers MQTT topic entries for each PLC.
    /// Rule: topic_name = PlcId (the server_progid) exactly — no prefix, no suffix.
    /// 
    /// Called every time PLCs are loaded so that:
    ///  - New PLCs get their topic automatically on first start
    ///  - Existing topics are left untouched (ON CONFLICT DO NOTHING)
    ///  - No manual DB insert or code change needed when adding a PLC
    /// </summary>
    private async Task EnsureMqttTopicsRegisteredAsync(List<string> plcIds)
    {
        if (!_databaseAvailable || string.IsNullOrEmpty(_connectionString) || plcIds.Count == 0)
            return;

        try
        {
            await using var conn = new NpgsqlConnection(_connectionString);
            await conn.OpenAsync();

            foreach (var plcId in plcIds)
            {
                // topic_name IS the server_progid — the single source of truth
                await using var cmd = new NpgsqlCommand(@"
                    INSERT INTO historian_raw.mqtt_topic_config
                        (topic_name, plc_name, qos, is_active, thread_group, created_time, updated_time)
                    VALUES
                        (@topic, @plcId, 1, true, 1, NOW(), NOW())
                    ON CONFLICT (topic_name) DO NOTHING", conn);

                cmd.Parameters.AddWithValue("topic", plcId);
                cmd.Parameters.AddWithValue("plcId", plcId);
                await cmd.ExecuteNonQueryAsync();

                _logger.LogInformation(
                    "[CONFIG LOADER] MQTT topic auto-registered: '{Topic}' → plc_name='{PlcId}'",
                    plcId, plcId);
            }
        }
        catch (Exception ex)
        {
            // Non-fatal — publisher still works, HMI subscription may be missing
            _logger.LogWarning(ex,
                "[CONFIG LOADER] Could not auto-register MQTT topics (non-fatal): {Message}", ex.Message);
        }
    }

    /// <summary>
    /// Load PLCs from appsettings.json PlcGateway:Connections section
    /// </summary>
    private List<PlcConfigEntry> LoadFromAppSettings()
    {
        var configs = new List<PlcConfigEntry>();

        try
        {
            var connectionsSection = _configuration.GetSection("PlcGateway:Connections");
            if (!connectionsSection.Exists())
            {
                _logger.LogWarning("[CONFIG LOADER] No PlcGateway:Connections section in appsettings.json");
                return configs;
            }

            var connectionConfigs = connectionsSection.Get<List<JsonPlcConnection>>() ?? new();

            foreach (var jsonConfig in connectionConfigs.Where(c => c.Enabled))
            {
                var config = new PlcConfigEntry
                {
                    PlcId = jsonConfig.PlcId ?? "PLC_001",
                    PlcName = jsonConfig.PlcName ?? jsonConfig.PlcId ?? "Unknown PLC",
                    PlantId = jsonConfig.PlantId ?? "DEFAULT",
                    Protocol = ParseProtocol(jsonConfig.Protocol ?? "Rockwell"),
                    IpAddress = jsonConfig.IpAddress ?? "",
                    Port = jsonConfig.Port > 0 ? jsonConfig.Port : 44818,
                    PollingIntervalMs = jsonConfig.PollingIntervalMs > 0 ? jsonConfig.PollingIntervalMs : 1000,  // USE FROM JSON!
                    TimeoutMs = jsonConfig.TimeoutMs > 0 ? jsonConfig.TimeoutMs : 3000,
                    ReconnectDelayMs = 5000,
                    RetryCount = 3,
                    Enabled = jsonConfig.Enabled,
                    RockwellConfig = jsonConfig.RockwellConfig != null ? new RockwellDriverConfig
                    {
                        PlcType = jsonConfig.RockwellConfig.PlcType ?? "ControlLogix",
                        Path = jsonConfig.RockwellConfig.Path ?? "1,0",
                        UseConnectedMessaging = jsonConfig.RockwellConfig.UseConnectedMessaging
                    } : new RockwellDriverConfig(),
                    Tags = jsonConfig.Tags?.Select(t => new PlcTagDefinition
                    {
                        TagId = t.TagId ?? t.Address ?? "",
                        PlcId = jsonConfig.PlcId ?? "PLC_001",
                        TagName = t.TagName ?? t.TagId ?? "",
                        Address = t.Address ?? t.TagId ?? "",
                        DataType = MapDataType(t.DataType ?? "float"),
                        Description = t.Description ?? "",
                        Unit = t.Unit ?? "",
                        ScaleFactor = t.ScaleFactor ?? 1.0,
                        OffsetValue = t.OffsetValue ?? 0.0,
                        DeadbandValue = t.DeadbandValue ?? 0.0,
                        DbLoggingEnabled = t.DbLoggingEnabled,
                        DbLoggingIntervalMs = t.DbLoggingIntervalMs > 0 ? t.DbLoggingIntervalMs : 1000,
                        ParquetLoggingEnabled = t.ParquetLoggingEnabled,
                        Enabled = t.Enabled
                    }).ToList() ?? new List<PlcTagDefinition>()
                };

                if (!string.IsNullOrEmpty(config.IpAddress))
                {
                    configs.Add(config);
                    _logger.LogInformation("[CONFIG LOADER] Loaded PLC from appsettings: {PlcId} @ {Ip}:{Port}, PollingInterval={PollMs}ms, {TagCount} tags",
                        config.PlcId, config.IpAddress, config.Port, config.PollingIntervalMs, config.Tags.Count);
                }
            }
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "[CONFIG LOADER] Failed to load from appsettings.json: {Message}", ex.Message);
        }

        return configs;
    }

    /// <summary>
    /// Load PLCs from historian_meta.tag_master database
    /// </summary>
    private async Task<List<PlcConfigEntry>> LoadFromDatabaseAsync()
    {
        var configs = new List<PlcConfigEntry>();

        if (!_databaseAvailable || string.IsNullOrEmpty(_connectionString))
        {
            return configs;
        }

        try
        {
            var connBuilder = new NpgsqlConnectionStringBuilder(_connectionString)
            {
                Timeout = 5,
                CommandTimeout = 5
            };
            
            await using var conn = new NpgsqlConnection(connBuilder.ToString());
            await conn.OpenAsync();

            var plcQuery = @"
                SELECT DISTINCT 
                    server_progid, plc_protocol, plc_ip_address, plc_port,
                    plc_type, plc_path, plc_timeout_ms, plc_polling_interval_ms,
                    use_connected_messaging
                FROM historian_meta.tag_master
                WHERE server_progid IS NOT NULL AND enabled = true
                AND plc_ip_address IS NOT NULL
                ORDER BY server_progid";

            await using var cmd = new NpgsqlCommand(plcQuery, conn);
            await using var reader = await cmd.ExecuteReaderAsync();

            while (await reader.ReadAsync())
            {
                var plcId = reader.GetString(0);
                // Get the minimum polling interval from database (column 7)
                var pollingIntervalMs = reader.IsDBNull(7) ? 1000 : reader.GetInt32(7);
                
                var config = new PlcConfigEntry
                {
                    PlcId = plcId,
                    PlcName = plcId,
                    PlantId = "DEFAULT",
                    Protocol = ParseProtocol(reader.IsDBNull(1) ? "Rockwell" : reader.GetString(1)),
                    IpAddress = reader.GetString(2),
                    Port = reader.GetInt32(3),
                    TimeoutMs = reader.IsDBNull(6) ? 3000 : reader.GetInt32(6),
                    PollingIntervalMs = pollingIntervalMs,  // Use database value
                    ReconnectDelayMs = 5000,
                    RetryCount = 3,
                    Enabled = true,
                    RockwellConfig = new RockwellDriverConfig
                    {
                        PlcType = reader.IsDBNull(4) ? "ControlLogix" : reader.GetString(4),
                        Path = reader.IsDBNull(5) ? "1,0" : reader.GetString(5),
                        UseConnectedMessaging = reader.IsDBNull(8) ? true : reader.GetBoolean(8)
                    }
                };
                
                _logger.LogInformation("[CONFIG] PLC {PlcId}: PollingInterval={Interval}ms from database",
                    plcId, pollingIntervalMs);
                    
                configs.Add(config);
            }

            await reader.CloseAsync();

            foreach (var config in configs)
            {
                config.Tags = await LoadTagsFromDatabaseAsync(config.PlcId);
            }
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "[CONFIG LOADER] Database load failed: {Message}", ex.Message);
            _databaseAvailable = false;
        }

        return configs;
    }

    /// <summary>
    /// Load tags for PLC from historian_meta.tag_master
    /// </summary>
    private async Task<List<PlcTagDefinition>> LoadTagsFromDatabaseAsync(string plcId)
    {
        var tags = new List<PlcTagDefinition>();

        if (string.IsNullOrEmpty(_connectionString)) return tags;

        try
        {
            await using var conn = new NpgsqlConnection(_connectionString);
            await conn.OpenAsync();

            var tagQuery = @"
                SELECT tag_id, tag_name, data_type, eng_unit,
                    deadband_enabled, deadband_value, db_logging_interval_ms, enabled,
                    plc_polling_interval_ms
                FROM historian_meta.tag_master
                WHERE server_progid = @plcId AND enabled = true
                ORDER BY tag_id";

            await using var cmd = new NpgsqlCommand(tagQuery, conn);
            cmd.Parameters.AddWithValue("plcId", plcId);
            await using var reader = await cmd.ExecuteReaderAsync();

            while (await reader.ReadAsync())
            {
                var tag = new PlcTagDefinition
                {
                    TagId = reader.GetString(0),
                    PlcId = plcId,
                    TagName = reader.GetString(1),
                    Address = reader.GetString(0),
                    DataType = MapDataType(reader.GetString(2)),
                    Description = "",
                    Unit = reader.IsDBNull(3) ? "" : reader.GetString(3),
                    ScaleFactor = 1.0,
                    OffsetValue = 0.0,
                    // Respect deadband_enabled flag — same logic as OPC MappingCacheService
                    DeadbandValue = (!reader.IsDBNull(4) && reader.GetBoolean(4) && !reader.IsDBNull(5))
                        ? reader.GetDouble(5)
                        : 0.0,
                    DbLoggingEnabled = true,
                    DbLoggingIntervalMs = reader.IsDBNull(6) ? 1000 : reader.GetInt32(6),
                    ParquetLoggingEnabled = false,
                    Enabled = reader.GetBoolean(7),
                    // CRITICAL: Load ScanRateMs from plc_polling_interval_ms column
                    ScanRateMs = reader.IsDBNull(8) ? 1000 : reader.GetInt32(8)
                };
                tags.Add(tag);
                
                _logger.LogDebug("[CONFIG] Loaded tag {TagId}: ScanRate={ScanMs}ms, Deadband={Deadband}",
                    tag.TagId, tag.ScanRateMs, tag.DeadbandValue);
            }
            
            _logger.LogInformation("[CONFIG] Loaded {Count} tags for PLC {PlcId} from database", tags.Count, plcId);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "[PLC Config] Failed to load tags for {PlcId}", plcId);
        }

        return tags;
    }

    private string MapDataType(string dbDataType)
    {
        // DB stores a controlled vocabulary (CHECK constraint allows only:
        // double / integer / boolean / string). Translate each to its
        // Rockwell-native CIP type so the driver decodes it correctly:
        //   double  -> REAL  (32-bit IEEE-754 float, GetFloat32)
        //   integer -> DINT  (32-bit signed int,      GetInt32)
        //   boolean -> BOOL  (1-bit/byte,             GetUInt8)
        //   string  -> STRING
        return dbDataType?.ToLowerInvariant() switch
        {
            "boolean" or "bool" => "BOOL",
            "integer" or "int"  => "DINT",
            "double" or "float" => "REAL",
            "string"            => "STRING",
            // Constraint guarantees one of the above; default to REAL as the
            // safest analog default (matches the overwhelmingly common case).
            _ => "REAL"
        };
    }

    private PlcProtocol ParseProtocol(string protocol)
    {
        return protocol.ToLowerInvariant() switch
        {
            "siemenss7" or "s7" => PlcProtocol.SiemensS7,
            "modbustcp" or "modbus" => PlcProtocol.ModbusTcp,
            "ethernetip" or "cip" => PlcProtocol.EtherNetIP,
            "rockwell" or "ab" => PlcProtocol.Rockwell,
            "abb" => PlcProtocol.ABB,
            "mitsubishi" or "melsec" => PlcProtocol.Mitsubishi,
            "omron" or "fins" => PlcProtocol.Omron,
            "opcua" => PlcProtocol.OpcUa,
            _ => PlcProtocol.Rockwell
        };
    }

    private T? DeserializeConfig<T>(string? json) where T : class
    {
        if (string.IsNullOrEmpty(json)) return null;
        try
        {
            return JsonSerializer.Deserialize<T>(json, new JsonSerializerOptions { PropertyNameCaseInsensitive = true });
        }
        catch
        {
            return null;
        }
    }
}

/// <summary>
/// PLC configuration entry
/// </summary>
public class PlcConfigEntry
{
    public string PlcId { get; set; } = "";
    public string PlcName { get; set; } = "";
    public string PlantId { get; set; } = "DEFAULT";
    public PlcProtocol Protocol { get; set; }
    public string IpAddress { get; set; } = "";
    public int Port { get; set; }
    public int TimeoutMs { get; set; } = 3000;
    public int PollingIntervalMs { get; set; } = 1000;  // From database plc_polling_interval_ms
    public int RetryCount { get; set; } = 3;
    public int ReconnectDelayMs { get; set; } = 5000;
    public bool Enabled { get; set; } = true;
    
    public S7DriverConfig? S7Config { get; set; }
    public ModbusDriverConfig? ModbusConfig { get; set; }
    public RockwellDriverConfig? RockwellConfig { get; set; }
    public AbbDriverConfig? AbbConfig { get; set; }
    
    public List<PlcTagDefinition> Tags { get; set; } = new();

    public PlcDriverConfig ToDriverConfig()
    {
        return new PlcDriverConfig
        {
            PlcId = PlcId,
            PlcName = PlcName,
            PlantId = PlantId,
            Protocol = Protocol,
            IpAddress = IpAddress,
            Port = Port,
            Enabled = Enabled,
            PollingIntervalMs = PollingIntervalMs,  // Use instance property from database
            TimeoutMs = TimeoutMs,
            RetryCount = RetryCount,
            ReconnectDelayMs = ReconnectDelayMs,
            S7Config = S7Config,
            ModbusConfig = ModbusConfig,
            RockwellConfig = RockwellConfig,
            AbbConfig = AbbConfig
        };
    }
}

/// <summary>
/// JSON model for PlcGateway:Connections in appsettings.json
/// </summary>
public class JsonPlcConnection
{
    public string? PlcId { get; set; }
    public string? PlcName { get; set; }
    public string? PlantId { get; set; }
    public string? Protocol { get; set; }
    public string? IpAddress { get; set; }
    public int Port { get; set; } = 44818;
    public int PollingIntervalMs { get; set; } = 1000;
    public int TimeoutMs { get; set; } = 3000;
    public bool Enabled { get; set; } = true;
    public JsonRockwellConfig? RockwellConfig { get; set; }
    public List<JsonTagDefinition>? Tags { get; set; }
}

/// <summary>
/// JSON model for Rockwell config in appsettings.json
/// </summary>
public class JsonRockwellConfig
{
    public string? PlcType { get; set; } = "ControlLogix";
    public string? Path { get; set; } = "1,0";
    public bool UseConnectedMessaging { get; set; } = true;
}

/// <summary>
/// JSON model for tag definitions in appsettings.json
/// </summary>
public class JsonTagDefinition
{
    public string? TagId { get; set; }
    public string? TagName { get; set; }
    public string? Address { get; set; }
    public string? DataType { get; set; } = "float";
    public string? Description { get; set; }
    public string? Unit { get; set; }
    public double? ScaleFactor { get; set; } = 1.0;
    public double? OffsetValue { get; set; } = 0.0;
    public double? DeadbandValue { get; set; } = 0.0;
    public bool DbLoggingEnabled { get; set; } = true;
    public int DbLoggingIntervalMs { get; set; } = 1000;
    public bool ParquetLoggingEnabled { get; set; } = false;
    public bool Enabled { get; set; } = true;
}
