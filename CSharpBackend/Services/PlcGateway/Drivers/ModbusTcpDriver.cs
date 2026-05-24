using Microsoft.Extensions.Logging;
using NModbus;
using PlcGateway.Interfaces;
using System.Net.Sockets;

namespace PlcGateway.Drivers;

/// <summary>
/// Modbus TCP Driver for generic PLC/RTU communication
/// Uses NModbus library (standard Modbus TCP port 502)
/// 
/// NuGet: Install-Package NModbus
/// 
/// Supports:
/// - Holding Registers (4xxxxx) - Read/Write
/// - Input Registers (3xxxxx) - Read only
/// - Coils (0xxxxx) - Read/Write bits
/// - Discrete Inputs (1xxxxx) - Read only bits
/// 
/// Address Format:
/// - HR100 or 400100 (Holding Register 100)
/// - IR100 or 300100 (Input Register 100)
/// - C100 or 000100 (Coil 100)
/// - DI100 or 100100 (Discrete Input 100)
/// </summary>
public class ModbusTcpDriver : IPlcDriver
{
    private TcpClient? _tcpClient;
    private IModbusMaster? _master;
    private ModbusFactory? _factory;
    private PlcDriverConfig? _config;
    private List<PlcTagDefinition> _tags = new();
    private readonly ILogger<ModbusTcpDriver> _logger;
    private bool _disposed;
    private DateTime _lastSuccessfulRead = DateTime.MinValue;
    private int _consecutiveFailures;

    public string DriverName => "ModbusTcp";
    public string Protocol => "Modbus TCP";
    public bool IsConnected => _tcpClient?.Connected ?? false;
    public DateTime LastReadTime => _lastSuccessfulRead;
    public int FailureCount => _consecutiveFailures;

    public ModbusTcpDriver(ILogger<ModbusTcpDriver> logger)
    {
        _logger = logger;
    }

    public Task<bool> InitializeAsync(PlcDriverConfig config, List<PlcTagDefinition> tags)
    {
        _config = config;
        _tags = tags;

        if (config.ModbusConfig == null)
        {
            _logger.LogError("[MODBUS] {PlcId}: Missing ModbusConfig section", config.PlcId);
            return Task.FromResult(false);
        }

        _factory = new ModbusFactory();

        _logger.LogInformation("[MODBUS] {PlcId}: Initialized with {Count} tags, SlaveId={SlaveId}",
            config.PlcId, tags.Count, config.ModbusConfig.SlaveId);

        return Task.FromResult(true);
    }

    public async Task<bool> ConnectAsync()
    {
        if (_config == null || _config.ModbusConfig == null || _factory == null)
        {
            _logger.LogError("[MODBUS] Driver not initialized");
            return false;
        }

        try
        {
            _tcpClient = new TcpClient();
            await _tcpClient.ConnectAsync(_config.IpAddress, _config.Port);
            
            _master = _factory.CreateMaster(_tcpClient);
            _master.Transport.ReadTimeout = _config.TimeoutMs;
            _master.Transport.WriteTimeout = _config.TimeoutMs;
            _master.Transport.Retries = _config.RetryCount;

            _consecutiveFailures = 0;
            _logger.LogInformation("[MODBUS] {PlcId}: Connected to {Ip}:{Port}, SlaveId={SlaveId}",
                _config.PlcId, _config.IpAddress, _config.Port, _config.ModbusConfig.SlaveId);
            
            return true;
        }
        catch (Exception ex)
        {
            _consecutiveFailures++;
            _logger.LogError(ex, "[MODBUS] {PlcId}: Connection error", _config?.PlcId);
            return false;
        }
    }

    public async Task<PlcReadResult> ReadAllTagsAsync()
    {
        if (_master == null || _config == null || !IsConnected)
        {
            return new PlcReadResult
            {
                Success = false,
                ErrorMessage = "Not connected",
                ReadDurationMs = 0
            };
        }

        var sw = System.Diagnostics.Stopwatch.StartNew();
        var values = new List<PlcTagValue>();
        var timestamp = DateTime.UtcNow;
        var slaveId = (byte)(_config.ModbusConfig?.SlaveId ?? 1);

        try
        {
            // Group tags by register type for optimized batch reads
            var holdingRegs = _tags.Where(t => IsHoldingRegister(t.Address)).ToList();
            var inputRegs = _tags.Where(t => IsInputRegister(t.Address)).ToList();
            var coils = _tags.Where(t => IsCoil(t.Address)).ToList();
            var discreteInputs = _tags.Where(t => IsDiscreteInput(t.Address)).ToList();

            // Read Holding Registers (batch by contiguous ranges)
            if (holdingRegs.Count > 0)
            {
                await ReadRegisterBatch(slaveId, holdingRegs, values, timestamp, 
                    async (slave, start, count) => await _master.ReadHoldingRegistersAsync(slave, start, count),
                    "HR");
            }

            // Read Input Registers
            if (inputRegs.Count > 0)
            {
                await ReadRegisterBatch(slaveId, inputRegs, values, timestamp,
                    async (slave, start, count) => await _master.ReadInputRegistersAsync(slave, start, count),
                    "IR");
            }

            // Read Coils
            if (coils.Count > 0)
            {
                await ReadBoolBatch(slaveId, coils, values, timestamp,
                    async (slave, start, count) => await _master.ReadCoilsAsync(slave, start, count),
                    "Coil");
            }

            // Read Discrete Inputs
            if (discreteInputs.Count > 0)
            {
                await ReadBoolBatch(slaveId, discreteInputs, values, timestamp,
                    async (slave, start, count) => await _master.ReadInputsAsync(slave, start, count),
                    "DI");
            }

            sw.Stop();
            _lastSuccessfulRead = timestamp;
            _consecutiveFailures = 0;

            _logger.LogDebug("[MODBUS] {PlcId}: Read {Count} tags in {Ms}ms",
                _config.PlcId, values.Count, sw.ElapsedMilliseconds);

            return new PlcReadResult
            {
                Success = true,
                Values = values,
                ReadDurationMs = sw.ElapsedMilliseconds,
                TagsRead = values.Count
            };
        }
        catch (Exception ex)
        {
            sw.Stop();
            _consecutiveFailures++;
            _logger.LogError(ex, "[MODBUS] {PlcId}: Read error after {Ms}ms", _config.PlcId, sw.ElapsedMilliseconds);

            // Mark all tags as bad quality
            foreach (var tag in _tags)
            {
                values.Add(new PlcTagValue
                {
                    Address = tag.Address,
                    TagName = tag.TagName,
                    Value = null,
                    DataType = tag.DataType,
                    Quality = PlcQuality.CommError,
                    Timestamp = timestamp,
                    PlcId = _config.PlcId
                });
            }

            return new PlcReadResult
            {
                Success = false,
                ErrorMessage = ex.Message,
                Values = values,
                ReadDurationMs = sw.ElapsedMilliseconds,
                TagsRead = 0
            };
        }
    }

    private async Task ReadRegisterBatch(
        byte slaveId,
        List<PlcTagDefinition> tags,
        List<PlcTagValue> results,
        DateTime timestamp,
        Func<byte, ushort, ushort, Task<ushort[]>> readFunc,
        string regType)
    {
        // Sort by address and find contiguous ranges
        var sorted = tags.OrderBy(t => ParseRegisterAddress(t.Address)).ToList();
        
        foreach (var tag in sorted)
        {
            try
            {
                var address = ParseRegisterAddress(tag.Address);
                var registerCount = GetRegisterCount(tag.DataType);
                
                // Read registers for this tag
                var registers = await readFunc(slaveId, address, registerCount);
                
                // Convert to value
                var value = ConvertRegistersToValue(registers, tag.DataType);
                
                results.Add(new PlcTagValue
                {
                    Address = tag.Address,
                    TagName = tag.TagName,
                    Value = value,
                    DataType = tag.DataType,
                    Quality = PlcQuality.Good,
                    Timestamp = timestamp,
                    PlcId = _config!.PlcId
                });
            }
            catch (Exception ex)
            {
                _logger.LogWarning(ex, "[MODBUS] Failed to read {RegType} {Address}", regType, tag.Address);
                results.Add(new PlcTagValue
                {
                    Address = tag.Address,
                    TagName = tag.TagName,
                    Value = null,
                    DataType = tag.DataType,
                    Quality = PlcQuality.Bad,
                    Timestamp = timestamp,
                    PlcId = _config!.PlcId
                });
            }
        }
    }

    private async Task ReadBoolBatch(
        byte slaveId,
        List<PlcTagDefinition> tags,
        List<PlcTagValue> results,
        DateTime timestamp,
        Func<byte, ushort, ushort, Task<bool[]>> readFunc,
        string regType)
    {
        foreach (var tag in tags)
        {
            try
            {
                var address = ParseBoolAddress(tag.Address);
                var bits = await readFunc(slaveId, address, 1);
                
                results.Add(new PlcTagValue
                {
                    Address = tag.Address,
                    TagName = tag.TagName,
                    Value = bits[0],
                    DataType = "bool",
                    Quality = PlcQuality.Good,
                    Timestamp = timestamp,
                    PlcId = _config!.PlcId
                });
            }
            catch (Exception ex)
            {
                _logger.LogWarning(ex, "[MODBUS] Failed to read {RegType} {Address}", regType, tag.Address);
                results.Add(new PlcTagValue
                {
                    Address = tag.Address,
                    TagName = tag.TagName,
                    Value = null,
                    DataType = "bool",
                    Quality = PlcQuality.Bad,
                    Timestamp = timestamp,
                    PlcId = _config!.PlcId
                });
            }
        }
    }

    /// <summary>
    /// Read specific tags by address (for per-tag scan rate scheduling)
    /// </summary>
    public async Task<PlcReadResult> ReadTagsAsync(IEnumerable<string> tagAddresses)
    {
        if (_master == null || !IsConnected || _config == null)
        {
            return new PlcReadResult
            {
                Success = false,
                ErrorMessage = "Not connected",
                ReadDurationMs = 0
            };
        }

        var sw = System.Diagnostics.Stopwatch.StartNew();
        var values = new List<PlcTagValue>();
        var timestamp = DateTime.UtcNow;
        var addressSet = new HashSet<string>(tagAddresses);
        var slaveId = (byte)(_config.ModbusConfig?.SlaveId ?? 1);

        try
        {
            // Filter tags to only requested addresses
            var requestedTags = _tags.Where(t => addressSet.Contains(t.Address)).ToList();
            
            // Group by register type for efficient batch reads
            var holdingRegs = requestedTags.Where(t => IsHoldingRegister(t.Address)).ToList();
            var inputRegs = requestedTags.Where(t => IsInputRegister(t.Address)).ToList();
            var coils = requestedTags.Where(t => IsCoil(t.Address)).ToList();
            var discreteInputs = requestedTags.Where(t => IsDiscreteInput(t.Address)).ToList();

            // Read Holding Registers (batch by contiguous ranges)
            if (holdingRegs.Count > 0)
            {
                await ReadRegisterBatch(slaveId, holdingRegs, values, timestamp, 
                    async (slave, start, count) => await _master.ReadHoldingRegistersAsync(slave, start, count),
                    "HR");
            }

            // Read Input Registers
            if (inputRegs.Count > 0)
            {
                await ReadRegisterBatch(slaveId, inputRegs, values, timestamp,
                    async (slave, start, count) => await _master.ReadInputRegistersAsync(slave, start, count),
                    "IR");
            }

            // Read Coils
            if (coils.Count > 0)
            {
                await ReadBoolBatch(slaveId, coils, values, timestamp,
                    async (slave, start, count) => await _master.ReadCoilsAsync(slave, start, count),
                    "Coil");
            }

            // Read Discrete Inputs
            if (discreteInputs.Count > 0)
            {
                await ReadBoolBatch(slaveId, discreteInputs, values, timestamp,
                    async (slave, start, count) => await _master.ReadInputsAsync(slave, start, count),
                    "DI");
            }

            sw.Stop();
            _lastSuccessfulRead = timestamp;
            _consecutiveFailures = 0;

            _logger.LogDebug("[MODBUS] {PlcId}: ReadTags {Count}/{Requested} tags in {Ms}ms",
                _config.PlcId, values.Count, addressSet.Count, sw.ElapsedMilliseconds);

            return new PlcReadResult
            {
                Success = true,
                Values = values,
                ReadDurationMs = sw.ElapsedMilliseconds,
                TagsRead = values.Count
            };
        }
        catch (Exception ex)
        {
            sw.Stop();
            _consecutiveFailures++;
            _logger.LogError(ex, "[MODBUS] {PlcId}: ReadTags error after {Ms}ms", _config.PlcId, sw.ElapsedMilliseconds);

            return new PlcReadResult
            {
                Success = false,
                ErrorMessage = ex.Message,
                Values = values,
                ReadDurationMs = sw.ElapsedMilliseconds,
                TagsRead = 0
            };
        }
    }

    public async Task<PlcHealthStatus> CheckHealthAsync()
    {
        var status = new PlcHealthStatus
        {
            PlcId = _config?.PlcId ?? "unknown",
            IsConnected = IsConnected,
            LastSuccessfulRead = _lastSuccessfulRead,
            ConsecutiveFailures = _consecutiveFailures
        };

        if (!IsConnected || _master == null || _config == null)
        {
            status.StatusMessage = "Disconnected";
            return status;
        }

        try
        {
            // Quick health check - read a single holding register
            var slaveId = (byte)(_config.ModbusConfig?.SlaveId ?? 1);
            var sw = System.Diagnostics.Stopwatch.StartNew();
            
            // Read register 0 (usually exists)
            await _master.ReadHoldingRegistersAsync(slaveId, 0, 1);
            
            sw.Stop();
            status.ResponseTimeMs = sw.ElapsedMilliseconds;
            status.StatusMessage = "OK";
        }
        catch (Exception ex)
        {
            status.IsConnected = false;
            status.StatusMessage = $"Health check failed: {ex.Message}";
        }

        return status;
    }

    public Task DisconnectAsync()
    {
        try
        {
            _master?.Dispose();
            _tcpClient?.Close();
            _tcpClient?.Dispose();
            
            _master = null;
            _tcpClient = null;
            
            _logger.LogInformation("[MODBUS] {PlcId}: Disconnected", _config?.PlcId);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "[MODBUS] {PlcId}: Disconnect error", _config?.PlcId);
        }
        
        return Task.CompletedTask;
    }

    // Address type detection
    private bool IsHoldingRegister(string address)
    {
        address = address.ToUpperInvariant();
        return address.StartsWith("HR") || address.StartsWith("4") || address.StartsWith("MW") || address.StartsWith("D");
    }

    private bool IsInputRegister(string address)
    {
        address = address.ToUpperInvariant();
        return address.StartsWith("IR") || address.StartsWith("3");
    }

    private bool IsCoil(string address)
    {
        address = address.ToUpperInvariant();
        return address.StartsWith("C") || address.StartsWith("0") || address.StartsWith("M.") || address.StartsWith("Y");
    }

    private bool IsDiscreteInput(string address)
    {
        address = address.ToUpperInvariant();
        return address.StartsWith("DI") || address.StartsWith("1") || address.StartsWith("X");
    }

    private ushort ParseRegisterAddress(string address)
    {
        address = address.ToUpperInvariant().Trim();
        
        // HR100 format
        if (address.StartsWith("HR"))
            return ushort.Parse(address.Substring(2));
        
        // IR100 format
        if (address.StartsWith("IR"))
            return ushort.Parse(address.Substring(2));
        
        // Modbus standard format: 400001 (holding), 300001 (input)
        if (address.Length >= 5 && char.IsDigit(address[0]))
        {
            var full = int.Parse(address);
            return (ushort)((full % 100000) - 1); // Modbus addresses are 1-based
        }
        
        // MW100 (Mitsubishi/generic)
        if (address.StartsWith("MW") || address.StartsWith("D"))
        {
            var offset = address.StartsWith("MW") ? 2 : 1;
            return ushort.Parse(address.Substring(offset));
        }
        
        return ushort.Parse(address);
    }

    private ushort ParseBoolAddress(string address)
    {
        address = address.ToUpperInvariant().Trim();
        
        // C100 format (coil)
        if (address.StartsWith("C"))
            return ushort.Parse(address.Substring(1));
        
        // DI100 format (discrete input)
        if (address.StartsWith("DI"))
            return ushort.Parse(address.Substring(2));
        
        // Standard format: 000001, 100001
        if (address.Length >= 5 && char.IsDigit(address[0]))
        {
            var full = int.Parse(address);
            return (ushort)((full % 100000) - 1);
        }
        
        // M.100 (Mitsubishi)
        if (address.StartsWith("M."))
            return ushort.Parse(address.Substring(2));
        
        // X100, Y100
        if (address.StartsWith("X") || address.StartsWith("Y"))
            return ushort.Parse(address.Substring(1));
        
        return ushort.Parse(address);
    }

    private ushort GetRegisterCount(string dataType)
    {
        return dataType.ToLowerInvariant() switch
        {
            "float" or "real" or "single" or "int32" or "uint32" or "dword" => 2, // 32-bit = 2 registers
            "double" or "int64" or "uint64" => 4, // 64-bit = 4 registers
            _ => 1 // 16-bit types = 1 register
        };
    }

    private object? ConvertRegistersToValue(ushort[] registers, string dataType)
    {
        if (registers.Length == 0) return null;

        try
        {
            return dataType.ToLowerInvariant() switch
            {
                "int" or "int16" or "short" => (short)registers[0],
                "uint" or "uint16" or "ushort" or "word" => registers[0],
                "int32" or "integer" when registers.Length >= 2 => 
                    (registers[0] << 16) | registers[1], // Big-endian
                "uint32" or "dword" when registers.Length >= 2 =>
                    (uint)((registers[0] << 16) | registers[1]),
                "float" or "real" or "single" when registers.Length >= 2 =>
                    ConvertToFloat(registers),
                "double" when registers.Length >= 4 =>
                    ConvertToDouble(registers),
                _ => registers[0]
            };
        }
        catch
        {
            return registers[0];
        }
    }

    private float ConvertToFloat(ushort[] registers)
    {
        // Big-endian float (common in PLCs)
        var bytes = new byte[4];
        bytes[0] = (byte)(registers[0] >> 8);
        bytes[1] = (byte)(registers[0] & 0xFF);
        bytes[2] = (byte)(registers[1] >> 8);
        bytes[3] = (byte)(registers[1] & 0xFF);
        
        // Check if system is little-endian and reverse if needed
        if (BitConverter.IsLittleEndian)
            Array.Reverse(bytes);
        
        return BitConverter.ToSingle(bytes, 0);
    }

    private double ConvertToDouble(ushort[] registers)
    {
        var bytes = new byte[8];
        for (int i = 0; i < 4; i++)
        {
            bytes[i * 2] = (byte)(registers[i] >> 8);
            bytes[i * 2 + 1] = (byte)(registers[i] & 0xFF);
        }
        
        if (BitConverter.IsLittleEndian)
            Array.Reverse(bytes);
        
        return BitConverter.ToDouble(bytes, 0);
    }

    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true;

        _master?.Dispose();
        _tcpClient?.Close();
        _tcpClient?.Dispose();
        
        GC.SuppressFinalize(this);
    }
}
