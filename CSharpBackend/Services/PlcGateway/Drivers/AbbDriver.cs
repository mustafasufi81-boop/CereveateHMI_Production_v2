using Microsoft.Extensions.Logging;
using PlcGateway.Interfaces;

namespace PlcGateway.Drivers;

/// <summary>
/// ABB PLC Driver - supports multiple ABB protocols
/// 
/// ABB Options:
/// 1. Modbus TCP (most common for AC500, PM5xx)
/// 2. OPC UA (AC500-eCo V3, AC500 V3)
/// 3. ABB Comli (legacy serial)
/// 
/// This driver uses Modbus TCP as primary (most widely compatible)
/// For OPC UA, use the generic OpcUaDriver or ABB-specific OPC UA client
/// 
/// ABB AC500 Modbus Address Mapping:
/// - %MW0 → Holding Register 0 (function 3/6/16)
/// - %IW0 → Input Register 0 (function 4)
/// - %M0.0 → Coil 0 (function 1/5/15)
/// - %I0.0 → Discrete Input 0 (function 2)
/// 
/// NuGet: Install-Package NModbus (reuses ModbusTcpDriver internally)
/// </summary>
public class AbbDriver : IPlcDriver
{
    private readonly ModbusTcpDriver _modbusDriver;
    private PlcDriverConfig? _config;
    private readonly ILogger<AbbDriver> _logger;
    private bool _disposed;

    public string DriverName => "ABB";
    public string Protocol => "Modbus TCP (ABB)";
    public bool IsConnected => _modbusDriver.IsConnected;
    public DateTime LastReadTime => _modbusDriver.LastReadTime;
    public int FailureCount => _modbusDriver.FailureCount;

    public AbbDriver(ILogger<AbbDriver> logger, ILogger<ModbusTcpDriver> modbusLogger)
    {
        _logger = logger;
        _modbusDriver = new ModbusTcpDriver(modbusLogger);
    }

    public async Task<bool> InitializeAsync(PlcDriverConfig config, List<PlcTagDefinition> tags)
    {
        _config = config;

        // Validate ABB config
        if (config.AbbConfig == null)
        {
            _logger.LogWarning("[ABB] {PlcId}: Missing AbbConfig section, using defaults", config.PlcId);
            config.AbbConfig = new AbbDriverConfig();
        }

        // Convert ABB addresses to standard Modbus addresses
        var convertedTags = tags.Select(t => new PlcTagDefinition
        {
            Address = ConvertAbbAddressToModbus(t.Address),
            TagName = t.TagName,
            DataType = t.DataType,
            Description = t.Description,
            ScaleFactor = t.ScaleFactor,
            OffsetValue = t.OffsetValue,
            Unit = t.Unit
        }).ToList();

        // Ensure ModbusConfig exists
        if (config.ModbusConfig == null)
        {
            config.ModbusConfig = new ModbusDriverConfig
            {
                SlaveId = config.AbbConfig.SlaveId
            };
        }

        _logger.LogInformation("[ABB] {PlcId}: Initialized with {Count} tags, Protocol={Protocol}, Model={Model}",
            config.PlcId, tags.Count, 
            config.AbbConfig.Protocol,
            config.AbbConfig.PlcModel);

        return await _modbusDriver.InitializeAsync(config, convertedTags);
    }

    public Task<bool> ConnectAsync()
    {
        _logger.LogInformation("[ABB] {PlcId}: Connecting via Modbus TCP", _config?.PlcId);
        return _modbusDriver.ConnectAsync();
    }

    public async Task<PlcReadResult> ReadAllTagsAsync()
    {
        var result = await _modbusDriver.ReadAllTagsAsync();
        
        // Log ABB-specific metrics if needed
        if (result.Success)
        {
            _logger.LogDebug("[ABB] {PlcId}: Read {Count} tags in {Ms}ms",
                _config?.PlcId, result.TagsRead, result.ReadDurationMs);
        }
        
        return result;
    }

    /// <summary>
    /// Read specific tags by address (for per-tag scan rate scheduling)
    /// Delegates to underlying Modbus driver
    /// </summary>
    public async Task<PlcReadResult> ReadTagsAsync(IEnumerable<string> tagAddresses)
    {
        var result = await _modbusDriver.ReadTagsAsync(tagAddresses);
        
        if (result.Success)
        {
            _logger.LogDebug("[ABB] {PlcId}: ReadTags {Count} tags in {Ms}ms",
                _config?.PlcId, result.TagsRead, result.ReadDurationMs);
        }
        
        return result;
    }

    public Task<PlcHealthStatus> CheckHealthAsync()
    {
        return _modbusDriver.CheckHealthAsync();
    }

    public Task DisconnectAsync()
    {
        _logger.LogInformation("[ABB] {PlcId}: Disconnecting", _config?.PlcId);
        return _modbusDriver.DisconnectAsync();
    }

    /// <summary>
    /// Convert ABB IEC 61131-3 addresses to standard Modbus addresses
    /// </summary>
    private string ConvertAbbAddressToModbus(string abbAddress)
    {
        abbAddress = abbAddress.ToUpperInvariant().Trim();
        
        // %MW100 → HR100 (Holding Register)
        if (abbAddress.StartsWith("%MW"))
        {
            return "HR" + abbAddress.Substring(3);
        }
        
        // %IW100 → IR100 (Input Register)
        if (abbAddress.StartsWith("%IW"))
        {
            return "IR" + abbAddress.Substring(3);
        }
        
        // %M0.0 → C0 (Coil)
        if (abbAddress.StartsWith("%M") && abbAddress.Contains('.'))
        {
            var parts = abbAddress.Substring(2).Split('.');
            var byteNum = int.Parse(parts[0]);
            var bitNum = int.Parse(parts[1]);
            return "C" + (byteNum * 8 + bitNum);
        }
        
        // %I0.0 → DI0 (Discrete Input)
        if (abbAddress.StartsWith("%I") && abbAddress.Contains('.'))
        {
            var parts = abbAddress.Substring(2).Split('.');
            var byteNum = int.Parse(parts[0]);
            var bitNum = int.Parse(parts[1]);
            return "DI" + (byteNum * 8 + bitNum);
        }
        
        // %Q0.0 → C1000 (Output Coil - offset by 1000 convention)
        if (abbAddress.StartsWith("%Q") && abbAddress.Contains('.'))
        {
            var parts = abbAddress.Substring(2).Split('.');
            var byteNum = int.Parse(parts[0]);
            var bitNum = int.Parse(parts[1]);
            return "C" + (1000 + byteNum * 8 + bitNum);
        }
        
        // %MD100 → HR100 (Double word in holding registers - uses 2 registers)
        if (abbAddress.StartsWith("%MD"))
        {
            return "HR" + abbAddress.Substring(3);
        }
        
        // Already in standard format, pass through
        if (abbAddress.StartsWith("HR") || abbAddress.StartsWith("IR") || 
            abbAddress.StartsWith("C") || abbAddress.StartsWith("DI"))
        {
            return abbAddress;
        }
        
        // Default: treat as holding register
        _logger.LogWarning("[ABB] Unknown address format: {Address}, treating as HR", abbAddress);
        return "HR" + abbAddress.TrimStart('%', 'M', 'W', 'D', 'I', 'Q');
    }

    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true;

        _modbusDriver.Dispose();
        
        GC.SuppressFinalize(this);
    }
}
