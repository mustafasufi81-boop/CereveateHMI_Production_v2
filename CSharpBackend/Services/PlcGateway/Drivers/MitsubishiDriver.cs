using Microsoft.Extensions.Logging;
using PlcGateway.Interfaces;

namespace PlcGateway.Drivers;

/// <summary>
/// Mitsubishi MELSEC PLC Driver
/// 
/// Protocol Options:
/// 1. MC Protocol (MELSEC Communication) - Native, fastest
/// 2. Modbus TCP - Widely compatible
/// 3. SLMP (Seamless Message Protocol) - Q/L/iQ-R series
/// 
/// This driver uses Modbus TCP for maximum compatibility
/// For MC Protocol, consider: McProtocol.NET or ActUtlType library
/// 
/// Supported PLCs:
/// - FX3U, FX5U (with Ethernet module)
/// - Q series (QJ71E71)
/// - iQ-R series
/// 
/// Modbus Address Mapping for Mitsubishi:
/// - D0 → Holding Register 0 (Data Register)
/// - M0 → Coil 0 (Internal Relay)
/// - X0 → Discrete Input 0 (Input)
/// - Y0 → Coil 100+ (Output)
/// - W0 → Holding Register 1000+ (Link Register)
/// 
/// NuGet: Install-Package NModbus
/// </summary>
public class MitsubishiDriver : IPlcDriver
{
    private readonly ModbusTcpDriver _modbusDriver;
    private PlcDriverConfig? _config;
    private readonly ILogger<MitsubishiDriver> _logger;
    private bool _disposed;

    public string DriverName => "Mitsubishi";
    public string Protocol => "Modbus TCP (Mitsubishi)";
    public bool IsConnected => _modbusDriver.IsConnected;
    public DateTime LastReadTime => _modbusDriver.LastReadTime;
    public int FailureCount => _modbusDriver.FailureCount;

    public MitsubishiDriver(ILogger<MitsubishiDriver> logger, ILogger<ModbusTcpDriver> modbusLogger)
    {
        _logger = logger;
        _modbusDriver = new ModbusTcpDriver(modbusLogger);
    }

    public async Task<bool> InitializeAsync(PlcDriverConfig config, List<PlcTagDefinition> tags)
    {
        _config = config;

        // Convert Mitsubishi addresses to standard Modbus addresses
        var convertedTags = tags.Select(t => new PlcTagDefinition
        {
            Address = ConvertMitsubishiAddressToModbus(t.Address),
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
            config.ModbusConfig = new ModbusDriverConfig { SlaveId = 1 };
        }

        _logger.LogInformation("[MITS] {PlcId}: Initialized with {Count} tags",
            config.PlcId, tags.Count);

        return await _modbusDriver.InitializeAsync(config, convertedTags);
    }

    public Task<bool> ConnectAsync()
    {
        _logger.LogInformation("[MITS] {PlcId}: Connecting via Modbus TCP", _config?.PlcId);
        return _modbusDriver.ConnectAsync();
    }

    public async Task<PlcReadResult> ReadAllTagsAsync()
    {
        var result = await _modbusDriver.ReadAllTagsAsync();
        
        if (result.Success)
        {
            _logger.LogDebug("[MITS] {PlcId}: Read {Count} tags in {Ms}ms",
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
            _logger.LogDebug("[MITS] {PlcId}: ReadTags {Count} tags in {Ms}ms",
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
        _logger.LogInformation("[MITS] {PlcId}: Disconnecting", _config?.PlcId);
        return _modbusDriver.DisconnectAsync();
    }

    /// <summary>
    /// Convert Mitsubishi addresses to standard Modbus addresses
    /// </summary>
    private string ConvertMitsubishiAddressToModbus(string mitsAddress)
    {
        mitsAddress = mitsAddress.ToUpperInvariant().Trim();
        
        // D100 → HR100 (Data Register → Holding Register)
        if (mitsAddress.StartsWith("D"))
        {
            return "HR" + mitsAddress.Substring(1);
        }
        
        // W100 → HR1100 (Link Register, offset by 1000)
        if (mitsAddress.StartsWith("W"))
        {
            var num = int.Parse(mitsAddress.Substring(1));
            return "HR" + (num + 1000);
        }
        
        // R100 → IR100 (File Register → Input Register)
        if (mitsAddress.StartsWith("R"))
        {
            return "IR" + mitsAddress.Substring(1);
        }
        
        // M100 → C100 (Internal Relay → Coil)
        if (mitsAddress.StartsWith("M"))
        {
            return "C" + mitsAddress.Substring(1);
        }
        
        // X0 → DI0 (Input → Discrete Input)
        // Note: Mitsubishi X addresses are typically octal
        if (mitsAddress.StartsWith("X"))
        {
            var octalAddr = mitsAddress.Substring(1);
            var decimalAddr = ConvertOctalToDecimal(octalAddr);
            return "DI" + decimalAddr;
        }
        
        // Y0 → C1000 (Output → Coil, offset)
        // Note: Mitsubishi Y addresses are typically octal
        if (mitsAddress.StartsWith("Y"))
        {
            var octalAddr = mitsAddress.Substring(1);
            var decimalAddr = ConvertOctalToDecimal(octalAddr);
            return "C" + (decimalAddr + 1000);
        }
        
        // SD100 → IR2100 (Special Register, offset by 2000)
        if (mitsAddress.StartsWith("SD"))
        {
            var num = int.Parse(mitsAddress.Substring(2));
            return "IR" + (num + 2000);
        }
        
        // SM100 → DI2100 (Special Relay, offset by 2000)
        if (mitsAddress.StartsWith("SM"))
        {
            var num = int.Parse(mitsAddress.Substring(2));
            return "DI" + (num + 2000);
        }
        
        // Already in standard format
        if (mitsAddress.StartsWith("HR") || mitsAddress.StartsWith("IR") || 
            mitsAddress.StartsWith("C") || mitsAddress.StartsWith("DI"))
        {
            return mitsAddress;
        }
        
        _logger.LogWarning("[MITS] Unknown address format: {Address}, treating as HR", mitsAddress);
        return "HR" + mitsAddress.TrimStart('D', 'W', 'R', 'M', 'X', 'Y', 'S');
    }

    /// <summary>
    /// Convert octal string to decimal (for X/Y addresses)
    /// </summary>
    private int ConvertOctalToDecimal(string octalStr)
    {
        try
        {
            return Convert.ToInt32(octalStr, 8);
        }
        catch
        {
            // If not valid octal, treat as decimal
            return int.Parse(octalStr);
        }
    }

    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true;

        _modbusDriver.Dispose();
        
        GC.SuppressFinalize(this);
    }
}
