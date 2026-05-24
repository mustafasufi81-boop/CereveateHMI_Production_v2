using Microsoft.Extensions.Logging;
using PlcGateway.Interfaces;
using System.Net.Sockets;

namespace PlcGateway.Drivers;

/// <summary>
/// Omron PLC Driver using FINS (Factory Interface Network Service) protocol
/// 
/// FINS TCP Port: 9600 (default)
/// FINS UDP Port: 9600 (default)
/// 
/// Supported PLCs:
/// - CJ1/CJ2 series
/// - CP1 series (with Ethernet option)
/// - CS1 series
/// - NJ/NX series (also support EtherNet/IP)
/// 
/// FINS Address Format:
/// - D100 (Data Memory)
/// - CIO100 (Core I/O)
/// - W100 (Work Area)
/// - H100 (Holding Area)
/// - A100 (Auxiliary Area)
/// - T100 (Timer PV)
/// - C100 (Counter PV)
/// - E0_100 (Extended Memory Bank 0)
/// 
/// Note: This is a simplified implementation
/// For production use, consider: OmronFins.NET or similar library
/// </summary>
public class OmronDriver : IPlcDriver
{
    private TcpClient? _tcpClient;
    private NetworkStream? _stream;
    private PlcDriverConfig? _config;
    private List<PlcTagDefinition> _tags = new();
    private readonly ILogger<OmronDriver> _logger;
    private bool _disposed;
    private bool _isConnected;
    private DateTime _lastSuccessfulRead = DateTime.MinValue;
    private int _consecutiveFailures;

    // FINS protocol constants
    private const byte FINS_ICF = 0x80;      // Information Control Field
    private const byte FINS_RSV = 0x00;      // Reserved
    private const byte FINS_GCT = 0x02;      // Permissible Gateway Count
    private const byte FINS_DNA = 0x00;      // Destination Network Address
    private const byte FINS_SNA = 0x00;      // Source Network Address
    private const byte FINS_SID = 0x00;      // Service ID

    // Memory area codes
    private const byte CIO_BIT = 0x30;
    private const byte CIO_WORD = 0x31;
    private const byte WR_BIT = 0x31;
    private const byte WR_WORD = 0x31;
    private const byte HR_BIT = 0x32;
    private const byte HR_WORD = 0x33;
    private const byte AR_BIT = 0xB0;
    private const byte AR_WORD = 0xB1;
    private const byte DM_BIT = 0x02;
    private const byte DM_WORD = 0x82;

    public string DriverName => "Omron";
    public string Protocol => "FINS TCP";
    public bool IsConnected => _isConnected;
    public DateTime LastReadTime => _lastSuccessfulRead;
    public int FailureCount => _consecutiveFailures;

    public OmronDriver(ILogger<OmronDriver> logger)
    {
        _logger = logger;
    }

    public Task<bool> InitializeAsync(PlcDriverConfig config, List<PlcTagDefinition> tags)
    {
        _config = config;
        _tags = tags;

        // Default port for FINS TCP
        if (config.Port == 0)
        {
            config.Port = 9600;
        }

        _logger.LogInformation("[OMRON] {PlcId}: Initialized with {Count} tags, FINS TCP on port {Port}",
            config.PlcId, tags.Count, config.Port);

        return Task.FromResult(true);
    }

    public async Task<bool> ConnectAsync()
    {
        if (_config == null)
        {
            _logger.LogError("[OMRON] Driver not initialized");
            return false;
        }

        try
        {
            _tcpClient = new TcpClient();
            await _tcpClient.ConnectAsync(_config.IpAddress, _config.Port);
            _stream = _tcpClient.GetStream();
            _stream.ReadTimeout = _config.TimeoutMs;
            _stream.WriteTimeout = _config.TimeoutMs;

            // FINS TCP requires initial handshake (NODE ADDRESS DATA SEND)
            if (await SendFinsHandshakeAsync())
            {
                _isConnected = true;
                _consecutiveFailures = 0;
                _logger.LogInformation("[OMRON] {PlcId}: Connected to {Ip}:{Port}",
                    _config.PlcId, _config.IpAddress, _config.Port);
                return true;
            }
            else
            {
                _logger.LogWarning("[OMRON] {PlcId}: FINS handshake failed", _config.PlcId);
                return false;
            }
        }
        catch (Exception ex)
        {
            _consecutiveFailures++;
            _logger.LogError(ex, "[OMRON] {PlcId}: Connection error", _config?.PlcId);
            return false;
        }
    }

    private async Task<bool> SendFinsHandshakeAsync()
    {
        if (_stream == null) return false;

        try
        {
            // FINS TCP header for handshake
            // Command: NODE ADDRESS DATA SEND (0x00000000)
            var handshake = new byte[]
            {
                0x46, 0x49, 0x4E, 0x53,  // "FINS"
                0x00, 0x00, 0x00, 0x0C,  // Length (12 bytes)
                0x00, 0x00, 0x00, 0x00,  // Command: NODE ADDRESS DATA SEND
                0x00, 0x00, 0x00, 0x00,  // Error code
                0x00, 0x00, 0x00, 0x00   // Client node address (auto)
            };

            await _stream.WriteAsync(handshake, 0, handshake.Length);
            await _stream.FlushAsync();

            // Read response
            var response = new byte[24];
            var bytesRead = await _stream.ReadAsync(response, 0, response.Length);

            // Check for valid response
            if (bytesRead >= 16 && 
                response[0] == 0x46 && response[1] == 0x49 && 
                response[2] == 0x4E && response[3] == 0x53) // "FINS"
            {
                _logger.LogDebug("[OMRON] FINS handshake successful");
                return true;
            }

            return false;
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "[OMRON] FINS handshake error");
            return false;
        }
    }

    public async Task<PlcReadResult> ReadAllTagsAsync()
    {
        if (!_isConnected || _config == null || _stream == null)
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
            // Group tags by memory area for batch reads
            var groupedTags = _tags.GroupBy(t => GetMemoryArea(t.Address));

            foreach (var group in groupedTags)
            {
                var areaCode = group.Key;
                var tagList = group.ToList();

                foreach (var tag in tagList)
                {
                    var (address, bit) = ParseOmronAddress(tag.Address);
                    var value = await ReadFinsMemoryAsync(areaCode, address, 1);

                    values.Add(new PlcTagValue
                    {
                        Address = tag.Address,
                        TagName = tag.TagName,
                        Value = value,
                        DataType = tag.DataType,
                        Quality = value != null ? PlcQuality.Good : PlcQuality.Bad,
                        Timestamp = timestamp,
                        PlcId = _config.PlcId
                    });
                }
            }

            sw.Stop();
            _lastSuccessfulRead = timestamp;
            _consecutiveFailures = 0;

            _logger.LogDebug("[OMRON] {PlcId}: Read {Count} tags in {Ms}ms",
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
            _logger.LogError(ex, "[OMRON] {PlcId}: Read error", _config.PlcId);

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

    private async Task<object?> ReadFinsMemoryAsync(byte areaCode, ushort address, ushort count)
    {
        if (_stream == null) return null;

        try
        {
            // Build FINS TCP frame with MEMORY AREA READ command (0x0101)
            var finsHeader = new byte[]
            {
                0x46, 0x49, 0x4E, 0x53,  // "FINS"
                0x00, 0x00, 0x00, 0x1A,  // Length (26 bytes for this command)
                0x00, 0x00, 0x00, 0x02,  // Command: FINS FRAME SEND
                0x00, 0x00, 0x00, 0x00   // Error code
            };

            var finsFrame = new byte[]
            {
                FINS_ICF, FINS_RSV, FINS_GCT,
                FINS_DNA, 0x00, 0x00,         // Destination (node address from handshake)
                FINS_SNA, 0x00, FINS_SID,     // Source
                0x01, 0x01,                   // Command: MEMORY AREA READ
                areaCode,                     // Memory area
                (byte)(address >> 8),         // Address high
                (byte)(address & 0xFF),       // Address low
                0x00,                         // Bit address
                (byte)(count >> 8),           // Count high
                (byte)(count & 0xFF)          // Count low
            };

            // Combine header and frame
            var request = finsHeader.Concat(finsFrame).ToArray();
            
            await _stream.WriteAsync(request, 0, request.Length);
            await _stream.FlushAsync();

            // Read response
            var response = new byte[256];
            var bytesRead = await _stream.ReadAsync(response, 0, response.Length);

            // Parse response (skip headers, extract data)
            if (bytesRead > 30) // Minimum valid response
            {
                // Check for errors in FINS response
                var endCode = (response[28] << 8) | response[29];
                if (endCode == 0x0000)
                {
                    // Extract data (starts at offset 30)
                    var dataHigh = response[30];
                    var dataLow = response[31];
                    return (ushort)((dataHigh << 8) | dataLow);
                }
                else
                {
                    _logger.LogWarning("[OMRON] FINS error code: 0x{Code:X4}", endCode);
                }
            }

            return null;
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "[OMRON] FINS read error for area 0x{Area:X2} address {Address}", 
                areaCode, address);
            return null;
        }
    }

    private byte GetMemoryArea(string address)
    {
        address = address.ToUpperInvariant();
        
        if (address.StartsWith("D")) return DM_WORD;
        if (address.StartsWith("CIO")) return CIO_WORD;
        if (address.StartsWith("W")) return WR_WORD;
        if (address.StartsWith("H")) return HR_WORD;
        if (address.StartsWith("A")) return AR_WORD;
        
        return DM_WORD; // Default to Data Memory
    }

    private (ushort address, byte bit) ParseOmronAddress(string address)
    {
        address = address.ToUpperInvariant().Trim();
        
        // Strip prefix
        var prefixes = new[] { "CIO", "DM", "D", "W", "H", "A", "T", "C", "E" };
        foreach (var prefix in prefixes)
        {
            if (address.StartsWith(prefix))
            {
                address = address.Substring(prefix.Length);
                break;
            }
        }

        // Check for bit address (D100.5)
        if (address.Contains('.'))
        {
            var parts = address.Split('.');
            return (ushort.Parse(parts[0]), byte.Parse(parts[1]));
        }

        return (ushort.Parse(address), 0);
    }

    /// <summary>
    /// Read specific tags by address (for per-tag scan rate scheduling)
    /// </summary>
    public async Task<PlcReadResult> ReadTagsAsync(IEnumerable<string> tagAddresses)
    {
        if (!_isConnected || _config == null)
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

            foreach (var tag in requestedTags)
            {
                try
                {
                    var memoryArea = GetMemoryArea(tag.Address);
                    var (addr, bit) = ParseOmronAddress(tag.Address);

                    var data = await ReadFinsMemoryAsync(memoryArea, addr, 1);

                    values.Add(new PlcTagValue
                    {
                        Address = tag.Address,
                        TagName = tag.TagName,
                        Value = data,
                        DataType = tag.DataType,
                        Quality = data != null ? PlcQuality.Good : PlcQuality.Bad,
                        Timestamp = timestamp,
                        PlcId = _config.PlcId
                    });
                }
                catch (Exception ex)
                {
                    _logger.LogWarning(ex, "[OMRON] Failed to read {Address}", tag.Address);
                    values.Add(new PlcTagValue
                    {
                        Address = tag.Address,
                        TagName = tag.TagName,
                        Value = null,
                        DataType = tag.DataType,
                        Quality = PlcQuality.Bad,
                        Timestamp = timestamp,
                        PlcId = _config.PlcId
                    });
                }
            }

            sw.Stop();
            _lastSuccessfulRead = timestamp;
            _consecutiveFailures = 0;

            _logger.LogDebug("[OMRON] {PlcId}: ReadTags {Count}/{Requested} tags in {Ms}ms",
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
            _logger.LogError(ex, "[OMRON] {PlcId}: ReadTags error after {Ms}ms", _config.PlcId, sw.ElapsedMilliseconds);

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
            IsConnected = _isConnected,
            LastSuccessfulRead = _lastSuccessfulRead,
            ConsecutiveFailures = _consecutiveFailures
        };

        if (!_isConnected)
        {
            status.StatusMessage = "Disconnected";
            return status;
        }

        try
        {
            // Read D0 as health check
            var value = await ReadFinsMemoryAsync(DM_WORD, 0, 1);
            status.StatusMessage = value != null ? "OK" : "Read failed";
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
            _stream?.Close();
            _tcpClient?.Close();
            _stream = null;
            _tcpClient = null;
            _isConnected = false;
            
            _logger.LogInformation("[OMRON] {PlcId}: Disconnected", _config?.PlcId);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "[OMRON] {PlcId}: Disconnect error", _config?.PlcId);
        }
        
        return Task.CompletedTask;
    }

    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true;

        _stream?.Close();
        _tcpClient?.Close();
        
        GC.SuppressFinalize(this);
    }
}
