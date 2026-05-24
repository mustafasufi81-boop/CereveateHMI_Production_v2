using Microsoft.Extensions.Logging;
using PlcGateway.Interfaces;
using S7.Net;
using S7.Net.Types;

// Resolve ambiguity between S7.Net.Types.DateTime and System.DateTime
using DateTime = System.DateTime;

namespace PlcGateway.Drivers;

/// <summary>
/// Siemens S7 PLC Driver (S7-300, S7-400, S7-1200, S7-1500)
/// Uses S7.Net library for native S7Comm protocol (port 102)
/// 
/// NuGet: Install-Package S7netplus
/// 
/// Address Format Examples:
/// - DB10.DBD0 (REAL at DB10, offset 0)
/// - DB10.DBW4 (INT/WORD at DB10, offset 4)
/// - DB10.DBX0.0 (BOOL at DB10, byte 0, bit 0)
/// - M0.0 (Merker bit)
/// - MW10 (Merker word)
/// - I0.0 (Input bit)
/// - Q0.0 (Output bit)
/// </summary>
public class SiemensS7Driver : IPlcDriver
{
    private Plc? _plc;
    private PlcDriverConfig? _config;
    private List<PlcTagDefinition> _tags = new();
    private readonly ILogger<SiemensS7Driver> _logger;
    private bool _disposed;
    private DateTime _lastSuccessfulRead = DateTime.MinValue;
    private int _consecutiveFailures;

    public string DriverName => "SiemensS7";
    public string Protocol => "S7Comm";
    public bool IsConnected => _plc?.IsConnected ?? false;
    public DateTime LastReadTime => _lastSuccessfulRead;
    public int FailureCount => _consecutiveFailures;

    public SiemensS7Driver(ILogger<SiemensS7Driver> logger)
    {
        _logger = logger;
    }

    public Task<bool> InitializeAsync(PlcDriverConfig config, List<PlcTagDefinition> tags)
    {
        _config = config;
        _tags = tags;

        // Validate S7 config
        if (config.S7Config == null)
        {
            _logger.LogError("[S7] {PlcId}: Missing S7Config section", config.PlcId);
            return Task.FromResult(false);
        }

        _logger.LogInformation("[S7] {PlcId}: Initialized with {Count} tags, CpuType={Cpu}, Rack={Rack}, Slot={Slot}",
            config.PlcId, tags.Count, config.S7Config.CpuType, config.S7Config.Rack, config.S7Config.Slot);

        return Task.FromResult(true);
    }

    public async Task<bool> ConnectAsync()
    {
        if (_config == null || _config.S7Config == null)
        {
            _logger.LogError("[S7] Driver not initialized");
            return false;
        }

        try
        {
            // Parse CPU type
            var cpuType = ParseCpuType(_config.S7Config.CpuType);
            
            _plc = new Plc(cpuType, _config.IpAddress, _config.S7Config.Rack, _config.S7Config.Slot);
            
            // S7.Net Open is synchronous, wrap in Task.Run
            await Task.Run(() => _plc.Open());

            if (_plc.IsConnected)
            {
                _consecutiveFailures = 0;
                _logger.LogInformation("[S7] {PlcId}: Connected to {Ip}:{Port}",
                    _config.PlcId, _config.IpAddress, _config.Port);
                return true;
            }
            else
            {
                _logger.LogWarning("[S7] {PlcId}: Failed to connect", _config.PlcId);
                return false;
            }
        }
        catch (Exception ex)
        {
            _consecutiveFailures++;
            _logger.LogError(ex, "[S7] {PlcId}: Connection error", _config?.PlcId);
            return false;
        }
    }

    public async Task<PlcReadResult> ReadAllTagsAsync()
    {
        if (_plc == null || !_plc.IsConnected || _config == null)
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

        try
        {
            // Build batch read list
            var dataItems = new List<DataItem>();
            
            foreach (var tag in _tags)
            {
                var dataItem = ParseAddress(tag.Address, tag.DataType);
                if (dataItem != null)
                {
                    dataItem.Value = null; // Will be filled by read
                    dataItems.Add(dataItem);
                }
            }

            if (dataItems.Count == 0)
            {
                return new PlcReadResult
                {
                    Success = true,
                    Values = values,
                    ReadDurationMs = sw.ElapsedMilliseconds,
                    TagsRead = 0
                };
            }

            // S7.Net ReadMultipleVars - single request for all tags
            await Task.Run(() => _plc.ReadMultipleVars(dataItems));

            // Map results back to tag values
            for (int i = 0; i < _tags.Count && i < dataItems.Count; i++)
            {
                var tag = _tags[i];
                var dataItem = dataItems[i];

                var value = ConvertValue(dataItem.Value, tag.DataType);
                
                values.Add(new PlcTagValue
                {
                    Address = tag.Address,
                    TagName = tag.TagName,
                    Value = value,
                    DataType = tag.DataType,
                    Quality = dataItem.Value != null ? PlcQuality.Good : PlcQuality.Bad,
                    Timestamp = timestamp,
                    PlcId = _config.PlcId
                });
            }

            sw.Stop();
            _lastSuccessfulRead = timestamp;
            _consecutiveFailures = 0;

            _logger.LogDebug("[S7] {PlcId}: Read {Count} tags in {Ms}ms",
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
            _logger.LogError(ex, "[S7] {PlcId}: Read error after {Ms}ms", _config.PlcId, sw.ElapsedMilliseconds);

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

    /// <summary>
    /// Read specific tags by address (for per-tag scan rate scheduling)
    /// </summary>
    public async Task<PlcReadResult> ReadTagsAsync(IEnumerable<string> tagAddresses)
    {
        if (_plc == null || !_plc.IsConnected || _config == null)
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

        try
        {
            // Filter tags to only requested addresses
            var requestedTags = _tags.Where(t => addressSet.Contains(t.Address)).ToList();
            
            if (requestedTags.Count == 0)
            {
                return new PlcReadResult
                {
                    Success = true,
                    Values = values,
                    ReadDurationMs = sw.ElapsedMilliseconds,
                    TagsRead = 0
                };
            }

            // Build batch read list
            var dataItems = new List<DataItem>();
            foreach (var tag in requestedTags)
            {
                var dataItem = ParseAddress(tag.Address, tag.DataType);
                if (dataItem != null)
                {
                    dataItem.Value = null;
                    dataItems.Add(dataItem);
                }
            }

            // S7.Net ReadMultipleVars - single request
            await Task.Run(() => _plc.ReadMultipleVars(dataItems));

            // Map results back to tag values
            for (int i = 0; i < requestedTags.Count && i < dataItems.Count; i++)
            {
                var tag = requestedTags[i];
                var dataItem = dataItems[i];

                var value = ConvertValue(dataItem.Value, tag.DataType);
                
                values.Add(new PlcTagValue
                {
                    Address = tag.Address,
                    TagName = tag.TagName,
                    Value = value,
                    DataType = tag.DataType,
                    Quality = dataItem.Value != null ? PlcQuality.Good : PlcQuality.Bad,
                    Timestamp = timestamp,
                    PlcId = _config.PlcId
                });
            }

            sw.Stop();
            _lastSuccessfulRead = timestamp;
            _consecutiveFailures = 0;

            _logger.LogDebug("[S7] {PlcId}: ReadTags {Count}/{Requested} tags in {Ms}ms",
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
            _logger.LogError(ex, "[S7] {PlcId}: ReadTags error after {Ms}ms", _config.PlcId, sw.ElapsedMilliseconds);

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

        if (!IsConnected)
        {
            status.StatusMessage = "Disconnected";
            return status;
        }

        try
        {
            // Quick health check - read first tag only
            if (_tags.Count > 0)
            {
                var tag = _tags[0];
                var dataItem = ParseAddress(tag.Address, tag.DataType);
                if (dataItem != null && _plc != null)
                {
                    await Task.Run(() => _plc.ReadMultipleVars(new List<DataItem> { dataItem }));
                    status.StatusMessage = "OK";
                    status.ResponseTimeMs = 0; // S7.Net doesn't expose timing
                }
            }
            else
            {
                status.StatusMessage = "No tags configured";
            }
        }
        catch (Exception ex)
        {
            status.IsConnected = false;
            status.StatusMessage = $"Health check failed: {ex.Message}";
        }

        return status;
    }

    public async Task DisconnectAsync()
    {
        if (_plc != null)
        {
            try
            {
                await Task.Run(() => _plc.Close());
                _logger.LogInformation("[S7] {PlcId}: Disconnected", _config?.PlcId);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "[S7] {PlcId}: Disconnect error", _config?.PlcId);
            }
        }
    }

    private CpuType ParseCpuType(string cpuTypeStr)
    {
        return cpuTypeStr.ToUpperInvariant() switch
        {
            "S7300" or "S7-300" or "300" => CpuType.S7300,
            "S7400" or "S7-400" or "400" => CpuType.S7400,
            "S71200" or "S7-1200" or "1200" => CpuType.S71200,
            "S71500" or "S7-1500" or "1500" => CpuType.S71500,
            _ => CpuType.S71200 // Default to S7-1200
        };
    }

    private DataItem? ParseAddress(string address, string dataType)
    {
        // Parse S7 address format
        // DB10.DBD0, DB10.DBW4, DB10.DBX0.0, MW10, M0.0, I0.0, Q0.0
        
        try
        {
            address = address.ToUpperInvariant();
            
            // Data Block addresses
            if (address.StartsWith("DB"))
            {
                return ParseDbAddress(address, dataType);
            }
            
            // Merker (Memory)
            if (address.StartsWith("M"))
            {
                return ParseMerkerAddress(address, dataType);
            }
            
            // Input
            if (address.StartsWith("I") || address.StartsWith("E"))
            {
                return ParseIoAddress(address, DataType.Input, dataType);
            }
            
            // Output
            if (address.StartsWith("Q") || address.StartsWith("A"))
            {
                return ParseIoAddress(address, DataType.Output, dataType);
            }

            _logger.LogWarning("[S7] Unknown address format: {Address}", address);
            return null;
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "[S7] Failed to parse address: {Address}", address);
            return null;
        }
    }

    private DataItem ParseDbAddress(string address, string dataType)
    {
        // Format: DB10.DBD0 or DB10.DBW4 or DB10.DBX0.0
        var parts = address.Split('.');
        var dbNumber = int.Parse(parts[0].Substring(2)); // DB10 -> 10
        var offsetPart = parts[1]; // DBD0, DBW4, DBX0 etc.

        var varType = ParseVarType(offsetPart, dataType);
        var startByte = ParseOffset(offsetPart);
        var bitAdr = 0;

        // Check for bit address (DBX0.0)
        if (offsetPart.StartsWith("DBX") && parts.Length > 2)
        {
            bitAdr = int.Parse(parts[2]);
            varType = VarType.Bit;
        }

        return new DataItem
        {
            DataType = DataType.DataBlock,
            DB = dbNumber,
            StartByteAdr = startByte,
            BitAdr = (byte)bitAdr,
            VarType = varType,
            Count = 1
        };
    }

    private DataItem ParseMerkerAddress(string address, string dataType)
    {
        // MW10 (word), MD10 (dword), MB10 (byte), M0.0 (bit)
        address = address.Substring(1); // Remove 'M'

        if (address.Contains('.'))
        {
            // Bit address M0.0
            var parts = address.Split('.');
            return new DataItem
            {
                DataType = DataType.Memory,
                StartByteAdr = int.Parse(parts[0]),
                BitAdr = byte.Parse(parts[1]),
                VarType = VarType.Bit,
                Count = 1
            };
        }
        else
        {
            var varType = ParseVarTypeFromPrefix(address[0], dataType);
            var offset = int.Parse(address.Substring(1));
            return new DataItem
            {
                DataType = DataType.Memory,
                StartByteAdr = offset,
                VarType = varType,
                Count = 1
            };
        }
    }

    private DataItem ParseIoAddress(string address, DataType areaType, string dataType)
    {
        address = address.Substring(1); // Remove I/E/Q/A

        if (address.Contains('.'))
        {
            // Bit address I0.0
            var parts = address.Split('.');
            return new DataItem
            {
                DataType = areaType,
                StartByteAdr = int.Parse(parts[0]),
                BitAdr = byte.Parse(parts[1]),
                VarType = VarType.Bit,
                Count = 1
            };
        }
        else
        {
            var varType = ParseVarTypeFromPrefix(address[0], dataType);
            var offset = int.Parse(address.Substring(1));
            return new DataItem
            {
                DataType = areaType,
                StartByteAdr = offset,
                VarType = varType,
                Count = 1
            };
        }
    }

    private VarType ParseVarType(string offsetPart, string dataType)
    {
        // DBD = DWord/Real, DBW = Word/Int, DBB = Byte, DBX = Bit
        if (offsetPart.Length < 3) return VarType.Word;
        
        var typeChar = offsetPart[2]; // D, W, B, X
        return typeChar switch
        {
            'D' => dataType.ToLowerInvariant() switch
            {
                "float" or "real" or "single" => VarType.Real,
                _ => VarType.DWord
            },
            'W' => dataType.ToLowerInvariant() switch
            {
                "int" or "int16" or "short" => VarType.Int,
                _ => VarType.Word
            },
            'B' => VarType.Byte,
            'X' => VarType.Bit,
            _ => VarType.Word
        };
    }

    private VarType ParseVarTypeFromPrefix(char prefix, string dataType)
    {
        return prefix switch
        {
            'D' => dataType.ToLowerInvariant() switch
            {
                "float" or "real" => VarType.Real,
                _ => VarType.DWord
            },
            'W' => VarType.Word,
            'B' => VarType.Byte,
            _ => VarType.Word
        };
    }

    private int ParseOffset(string offsetPart)
    {
        // DBD0 -> 0, DBW4 -> 4
        var numStart = 3; // After "DBD", "DBW", "DBB", "DBX"
        if (offsetPart.Length > numStart)
        {
            return int.Parse(offsetPart.Substring(numStart));
        }
        return 0;
    }

    private object? ConvertValue(object? rawValue, string targetType)
    {
        if (rawValue == null) return null;

        try
        {
            return targetType.ToLowerInvariant() switch
            {
                "bool" or "boolean" => Convert.ToBoolean(rawValue),
                "int" or "int16" or "short" => Convert.ToInt16(rawValue),
                "int32" or "integer" => Convert.ToInt32(rawValue),
                "uint" or "uint16" or "ushort" or "word" => Convert.ToUInt16(rawValue),
                "uint32" or "dword" => Convert.ToUInt32(rawValue),
                "float" or "real" or "single" => Convert.ToSingle(rawValue),
                "double" => Convert.ToDouble(rawValue),
                "byte" => Convert.ToByte(rawValue),
                "string" => rawValue.ToString(),
                _ => rawValue
            };
        }
        catch
        {
            return rawValue;
        }
    }

    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true;

        _plc?.Close();
        _plc = null;
        
        GC.SuppressFinalize(this);
    }
}
