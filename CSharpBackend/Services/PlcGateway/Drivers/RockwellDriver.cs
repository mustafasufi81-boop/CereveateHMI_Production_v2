using Microsoft.Extensions.Logging;
using PlcGateway.Interfaces;
using libplctag;
using libplctag.DataTypes;

namespace PlcGateway.Drivers;

/// <summary>
/// Rockwell Automation / Allen Bradley PLC Driver
/// Uses libplctag library for EtherNet/IP CIP protocol
/// 
/// NuGet: Install-Package libplctag
/// 
/// Supported PLCs:
/// - ControlLogix (L6x, L7x, L8x series)
/// - CompactLogix (L1x, L2x, L3x series)
/// - Micro800 series (820, 850, 870)
/// - MicroLogix (limited support)
/// - SLC 500 (limited support)
/// - PLC-5 (legacy)
/// 
/// Connection Path Examples:
/// - ControlLogix in slot 0: "1,0" (backplane, slot)
/// - CompactLogix: "" (empty, direct connection)
/// - Via EN2T module in slot 2 to PLC in slot 0: "1,2,2,192.168.1.100,1,0"
/// 
/// Tag Name Format:
/// - Simple: "MyTag"
/// - Array element: "MyArray[0]"
/// - UDT member: "MyUDT.Member"
/// - Program scope: "Program:MainProgram.LocalTag"
/// - Bit access: "MyDINT.5" (bit 5 of DINT)
/// 
/// Data Types (Rockwell):
/// - BOOL (1 bit)
/// - SINT (8-bit signed)
/// - INT (16-bit signed)
/// - DINT (32-bit signed)
/// - LINT (64-bit signed)
/// - REAL (32-bit float)
/// - LREAL (64-bit float)
/// - STRING (82 bytes max)
/// </summary>
public class RockwellDriver : IPlcDriver
{
    private PlcDriverConfig? _config;
    private List<PlcTagDefinition> _tags = new();
    private readonly ILogger<RockwellDriver> _logger;
    private bool _disposed;
    private bool _isConnected;
    private DateTime _lastSuccessfulRead = DateTime.MinValue;
    private int _consecutiveFailures;

    // Real libplctag Tag objects
    private readonly Dictionary<string, Tag> _libplcTags = new();
    // Legacy handle tracking (for compatibility)
    private readonly Dictionary<string, PlcTagHandle> _tagHandles = new();

    // ── Per-tag fault suppression ────────────────────────────────────────
    // Tracks tags that have already been logged as bad so we don't flood
    // the log with the same warning every second for every faulty I/O card.
    private readonly HashSet<string> _knownBadTags = new(StringComparer.OrdinalIgnoreCase);
    private readonly Dictionary<string, int> _tagFailCounts = new(StringComparer.OrdinalIgnoreCase);

    // ── PLC-offline exponential backoff ──────────────────────────────────
    // When PLC is unreachable we stop the rapid connect-probe loop and
    // progressively back off: 30 s → 60 s → 120 s (capped).
    private int  _offlineBackoffSeconds = 0;          // current wait (0 = first attempt)
    private DateTime _nextConnectAttempt = DateTime.MinValue;

    public string DriverName => "Rockwell";
    public string Protocol => "EtherNet/IP CIP";
    public bool IsConnected => _isConnected;
    public DateTime LastReadTime => _lastSuccessfulRead;
    public int FailureCount => _consecutiveFailures;

    public RockwellDriver(ILogger<RockwellDriver> logger)
    {
        _logger = logger;
    }

    public Task<bool> InitializeAsync(PlcDriverConfig config, List<PlcTagDefinition> tags)
    {
        _config = config;
        
        // FOR TESTING: Add hardcoded tags if none provided
        if (!tags.Any())
        {
            _logger.LogInformation("[ROCKWELL] No tags provided, using hardcoded test tags");
            tags = new List<PlcTagDefinition>
            {
                new PlcTagDefinition { Address = "Cooling_FAN_SPEED", TagName = "Cooling_FAN_SPEED", DataType = "REAL" },
                new PlcTagDefinition { Address = "High_Temp_Limit", TagName = "High_Temp_Limit", DataType = "REAL" },
                new PlcTagDefinition { Address = "Tank_Level", TagName = "Tank_Level", DataType = "REAL" },
                new PlcTagDefinition { Address = "Pump_Status", TagName = "Pump_Status", DataType = "BOOL" },
                new PlcTagDefinition { Address = "Motor_RPM", TagName = "Motor_RPM", DataType = "REAL" }
            };
        }

        _tags = tags;        if (config.RockwellConfig == null)
        {
            // Use defaults for ControlLogix
            config.RockwellConfig = new RockwellDriverConfig
            {
                PlcType = "ControlLogix",
                Path = "1,0",  // Use exact working configuration
                UseConnectedMessaging = true
            };
        }

        _logger.LogInformation(
            "[ROCKWELL] {PlcId}: Initialized with {Count} tags, Type={PlcType}, Path={Path}",
            config.PlcId, tags.Count,
            config.RockwellConfig.PlcType,
            config.RockwellConfig.Path);

        return Task.FromResult(true);
    }

    public async Task<bool> ConnectAsync()
    {
        if (_config == null)
        {
            _logger.LogError("[ROCKWELL] Driver not initialized");
            return false;
        }

        // ── Backoff guard ────────────────────────────────────────────────
        // If we already know the PLC is offline, honour the backoff window
        // so we don't hammer ntdll with 128 × 2-second timeouts every tick.
        if (_offlineBackoffSeconds > 0 && DateTime.UtcNow < _nextConnectAttempt)
        {
            _logger.LogTrace("[ROCKWELL] {PlcId}: PLC offline backoff active, next attempt at {Next}",
                _config.PlcId, _nextConnectAttempt.ToLocalTime().ToString("HH:mm:ss"));
            return false;
        }

        try
        {
            // ── PING: probe ONE tag first ────────────────────────────────
            // Use the first available tag as a connectivity probe.
            // If this single tag times out the PLC is unreachable — abort
            // immediately instead of iterating all 128 tags × 2 s each.
            var probeTag = _tags.FirstOrDefault();
            if (probeTag == null)
            {
                _logger.LogWarning("[ROCKWELL] {PlcId}: No tags configured", _config.PlcId);
                return false;
            }

            _logger.LogInformation("[ROCKWELL] {PlcId}: Probing {Ip} with tag '{Tag}'…",
                _config.PlcId, _config.IpAddress, probeTag.Address);

            var probeHandle = await CreateTagHandleAsync(probeTag);
            if (probeHandle == null)
            {
                // Probe failed → PLC is offline, apply backoff
                _offlineBackoffSeconds = Math.Min(
                    _offlineBackoffSeconds == 0 ? 30 : _offlineBackoffSeconds * 2,
                    120);  // cap at 2 minutes
                _nextConnectAttempt = DateTime.UtcNow.AddSeconds(_offlineBackoffSeconds);
                _logger.LogWarning(
                    "[ROCKWELL] {PlcId}: PLC unreachable at {Ip}. " +
                    "Next attempt in {Sec}s ({Next}).",
                    _config.PlcId, _config.IpAddress,
                    _offlineBackoffSeconds,
                    _nextConnectAttempt.ToLocalTime().ToString("HH:mm:ss"));
                return false;
            }

            // Probe succeeded → PLC is alive, reset backoff
            _offlineBackoffSeconds = 0;
            _tagHandles[probeTag.Address] = probeHandle;

            // ── Connect remaining tags ───────────────────────────────────
            // Only reach here when network is confirmed reachable.
            _logger.LogInformation("[ROCKWELL] {PlcId}: Probe OK — initialising remaining {Count} tags",
                _config.PlcId, _tags.Count - 1);

            foreach (var tag in _tags.Where(t => t.Address != probeTag.Address))
            {
                var handle = await CreateTagHandleAsync(tag);
                if (handle != null)
                    _tagHandles[tag.Address] = handle;
                // Individual tag failures are non-fatal — logged inside CreateTagHandleAsync
            }

            var createdCount = _tagHandles.Count;
            if (createdCount > 0)
            {
                _isConnected = true;
                _consecutiveFailures = 0;
                _knownBadTags.Clear();   // fresh slate on reconnect
                _tagFailCounts.Clear();
                _logger.LogInformation(
                    "[ROCKWELL] {PlcId}: Connected to {Ip} — {Count}/{Total} tag handles ready",
                    _config.PlcId, _config.IpAddress, createdCount, _tags.Count);
                return true;
            }
            else
            {
                _logger.LogWarning("[ROCKWELL] {PlcId}: No tag handles created", _config.PlcId);
                return false;
            }
        }
        catch (Exception ex)
        {
            _consecutiveFailures++;
            _logger.LogError(ex, "[ROCKWELL] {PlcId}: Connection error", _config?.PlcId);
            return false;
        }
    }

    private Task<PlcTagHandle?> CreateTagHandleAsync(PlcTagDefinition tag)
    {
        if (_config?.RockwellConfig == null) return Task.FromResult<PlcTagHandle?>(null);

        try
        {
            var elemSize = GetElementSize(tag.DataType);
            
            // Create REAL libplctag Tag object - MATCHING WORKING TagPoolCache.cs
            var libTag = new Tag()
            {
                Name = tag.Address,
                Gateway = _config.IpAddress,
                Path = $"1,{_config.RockwellConfig.Path?.Replace("1,", "") ?? "0"}",
                PlcType = PlcType.ControlLogix,
                Protocol = libplctag.Protocol.ab_eip,
                Timeout = TimeSpan.FromSeconds(2),
                ElementSize = elemSize
            };

            _logger.LogInformation("[ROCKWELL] Initializing tag {Address} -> Gateway={Gateway}, Path={Path}, ElementSize={Size}", 
                tag.Address, _config.IpAddress, libTag.Path, elemSize);

            // Initialize the tag (connects to PLC)
            libTag.Initialize();
            
            // CHECK IF INITIALIZATION ACTUALLY WORKED
            if (libTag.GetStatus() != libplctag.Status.Ok)
            {
                var status = libTag.GetStatus();
                var error = $"Tag initialization failed: {status}";
                _logger.LogError("[ROCKWELL] {Error} for tag {Address} - Gateway={Gateway}, Path={Path}", 
                    error, tag.Address, _config.IpAddress, libTag.Path);
                libTag.Dispose();
                return Task.FromResult<PlcTagHandle?>(null);
            }
            
            _logger.LogInformation("[ROCKWELL] Tag {Address} initialized successfully - Status: {Status}", 
                tag.Address, libTag.GetStatus());
            
            // Store the real tag object
            _libplcTags[tag.Address] = libTag;
            
            var handle = new PlcTagHandle
            {
                Address = tag.Address,
                TagName = tag.TagName,
                DataType = tag.DataType,
                ElementSize = elemSize,
                AttributeString = $"gateway={_config.IpAddress}&path={libTag.Path}&name={tag.Address}",
                Handle = _libplcTags.Count
            };

            _logger.LogInformation("[ROCKWELL] Created tag: {Address} (type={DataType}, size={Size})", 
                tag.Address, tag.DataType, elemSize);

            return Task.FromResult<PlcTagHandle?>(handle);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "[ROCKWELL] Failed to create tag handle for {Address}: {Message}", tag.Address, ex.Message);
            return Task.FromResult<PlcTagHandle?>(null);
        }
    }
    
    private PlcType MapToLibPlcType(string plcType)
    {
        return plcType?.ToLowerInvariant() switch
        {
            "controllogix" => PlcType.ControlLogix,
            "compactlogix" => PlcType.ControlLogix, // Same protocol
            "micro800" => PlcType.Micro800,
            "micrologix" => PlcType.MicroLogix,
            "slc500" => PlcType.Slc500,
            "plc5" => PlcType.Plc5,
            _ => PlcType.ControlLogix
        };
    }

    public async Task<PlcReadResult> ReadAllTagsAsync()
    {
        _logger.LogInformation("[ROCKWELL] *** ReadAllTagsAsync CALLED *** Connected: {Connected}, Tags: {Count}", _isConnected, _tagHandles.Count);
        
        if (!_isConnected || _config == null)
        {
            _logger.LogWarning("[ROCKWELL] *** ReadAllTagsAsync FAILED *** Not connected or no config");
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

        // Each tag is read independently — a faulty tag never aborts the whole batch.
        // Bad tags are silently skipped (logged once inside ReadTagValue).
        // Success = true as long as at least one tag returns a good value.
        var readTasks = _tags.Select(tag => Task.Run(() =>
        {
            if (!_tagHandles.TryGetValue(tag.Address, out var handle))
                return null;   // handle missing — already logged once in ReadTagValue

            object? value = null;
            try { value = ReadTagValue(handle); }
            catch { /* ReadTagValue handles its own logging */ }

            if (value == null)
                return null;   // bad tag — exclude from results, don't break loop

            return new PlcTagValue
            {
                Address   = tag.Address,
                TagName   = tag.TagName,
                Value     = value,
                DataType  = tag.DataType,
                Quality   = PlcQuality.Good,
                Timestamp = timestamp,
                PlcId     = _config.PlcId
            };
        })).ToArray();

        try
        {
            var results = await Task.WhenAll(readTasks);
            values.AddRange(results.Where(v => v != null)!);
        }
        catch (Exception ex)
        {
            // Task.WhenAll itself threw — extremely unlikely but handle gracefully
            _logger.LogError(ex, "[ROCKWELL] {PlcId}: Unexpected error awaiting read tasks", _config.PlcId);
        }

        sw.Stop();

        if (values.Count > 0)
        {
            _lastSuccessfulRead = timestamp;
            _consecutiveFailures = 0;
            _logger.LogDebug("[ROCKWELL] {PlcId}: Read {Good}/{Total} tags in {Ms}ms",
                _config.PlcId, values.Count, _tags.Count, sw.ElapsedMilliseconds);
            return new PlcReadResult
            {
                Success       = true,
                Values        = values,
                ReadDurationMs = sw.ElapsedMilliseconds,
                TagsRead      = values.Count
            };
        }
        else
        {
            // No tags returned any value — treat as a full read failure
            _consecutiveFailures++;
            _logger.LogWarning("[ROCKWELL] {PlcId}: All {Total} tag reads returned null — possible PLC comms issue",
                _config.PlcId, _tags.Count);
            return new PlcReadResult
            {
                Success        = false,
                ErrorMessage   = "All tags returned null",
                Values         = values,
                ReadDurationMs = sw.ElapsedMilliseconds,
                TagsRead       = 0
            };
        }
    }

    /// <summary>
    /// Read SPECIFIC tags by address (for per-tag scan rate scheduling)
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
        var addressSet = tagAddresses.ToHashSet(StringComparer.OrdinalIgnoreCase);

        try
        {
            // Small delay to allow async reads
            await Task.Delay(10);

            // Read only requested tags — each independently, bad tag never aborts batch
            foreach (var tag in _tags.Where(t => addressSet.Contains(t.Address)))
            {
                if (!_tagHandles.TryGetValue(tag.Address, out var handle))
                    continue;

                object? value = null;
                try { value = ReadTagValue(handle); }
                catch { /* ReadTagValue handles its own suppressed logging */ }

                if (value == null)
                    continue;  // faulty tag — skip silently, already logged once

                values.Add(new PlcTagValue
                {
                    Address   = tag.Address,
                    TagName   = tag.TagName,
                    Value     = value,
                    DataType  = tag.DataType,
                    Quality   = PlcQuality.Good,
                    Timestamp = timestamp,
                    PlcId     = _config.PlcId
                });
            }

            sw.Stop();

            if (values.Count > 0)
            {
                _lastSuccessfulRead = timestamp;
                return new PlcReadResult
                {
                    Success        = true,
                    Values         = values,
                    ReadDurationMs = sw.ElapsedMilliseconds,
                    TagsRead       = values.Count
                };
            }
            else
            {
                _consecutiveFailures++;
                return new PlcReadResult
                {
                    Success        = false,
                    ErrorMessage   = "All requested tags returned null",
                    Values         = values,
                    ReadDurationMs = sw.ElapsedMilliseconds,
                    TagsRead       = 0
                };
            }
        }
        catch (Exception ex)
        {
            sw.Stop();
            _logger.LogError(ex, "[ROCKWELL] {PlcId}: Unexpected read exception", _config.PlcId);
            return new PlcReadResult
            {
                Success        = false,
                ErrorMessage   = ex.Message,
                Values         = values,
                ReadDurationMs = sw.ElapsedMilliseconds,
                TagsRead       = 0
            };
        }
    }

    private object? ReadTagValue(PlcTagHandle handle)
    {
        // Get the REAL libplctag Tag object
        if (!_libplcTags.TryGetValue(handle.Address, out var libTag))
        {
            // Log missing handle only once per tag
            if (_knownBadTags.Add(handle.Address))
                _logger.LogWarning("[ROCKWELL] Tag handle missing (will not repeat): {Address}", handle.Address);
            return null;
        }

        try
        {
            libTag.Read();

            var status = libTag.GetStatus();
            if (status != libplctag.Status.Ok)
            {
                // ── Fault suppression ────────────────────────────────────
                // Only log the first time a tag goes bad.  Subsequent bad
                // reads on the same tag are silently skipped to avoid
                // filling gigabytes of logs with repeated ErrorTimeout lines.
                _tagFailCounts.TryGetValue(handle.Address, out var prev);
                _tagFailCounts[handle.Address] = prev + 1;

                if (_knownBadTags.Add(handle.Address))
                {
                    _logger.LogWarning(
                        "[ROCKWELL] Tag '{Address}' read failed — Status={Status}. " +
                        "Further failures for this tag will be SUPPRESSED until it recovers.",
                        handle.Address, status);
                }
                return null;
            }

            // ── Tag recovered ────────────────────────────────────────────
            if (_knownBadTags.Remove(handle.Address))
            {
                _tagFailCounts.TryGetValue(handle.Address, out var failCount);
                _tagFailCounts.Remove(handle.Address);
                _logger.LogInformation(
                    "[ROCKWELL] Tag '{Address}' RECOVERED after {Count} failed read(s).",
                    handle.Address, failCount);
            }

            // Get value based on data type
            return handle.DataType.ToUpperInvariant() switch
            {
                "BOOL"  => libTag.GetUInt8(0) != 0,
                "SINT"  => (sbyte)libTag.GetInt8(0),
                "INT"   => libTag.GetInt16(0),
                "DINT"  => libTag.GetInt32(0),
                "LINT"  => libTag.GetInt64(0),
                "REAL"  => libTag.GetFloat32(0),
                "LREAL" => libTag.GetFloat64(0),
                _       => libTag.GetFloat32(0)
            };
        }
        catch (Exception ex)
        {
            // Same suppression for exception-based failures
            _tagFailCounts.TryGetValue(handle.Address, out var prev);
            _tagFailCounts[handle.Address] = prev + 1;
            if (_knownBadTags.Add(handle.Address))
                _logger.LogWarning(
                    "[ROCKWELL] Tag '{Address}' exception — {Message}. " +
                    "Further failures suppressed until recovery.",
                    handle.Address, ex.Message);
            return null;
        }
    }

    public Task<PlcHealthStatus> CheckHealthAsync()
    {
        var status = new PlcHealthStatus
        {
            PlcId = _config?.PlcId ?? "unknown",
            IsConnected = _isConnected,
            LastSuccessfulRead = _lastSuccessfulRead,
            ConsecutiveFailures = _consecutiveFailures,
            StatusMessage = _isConnected 
                ? $"OK - {_tagHandles.Count} tags" 
                : "Disconnected"
        };

        return Task.FromResult(status);
    }

    /// <summary>
    /// Read the actual Rockwell ControlLogix controller mode via CIP.
    ///
    /// libplctag exposes the Rockwell "controller program status" byte via the
    /// special tag name "@PROGRAM_STATUS".  The byte encodes the keyswitch position:
    ///   0 = PROGRAM    1 = RUN       2 = TEST
    ///   3 = REM_RUN    4 = REM_PROGRAM  5 = REM_TEST
    ///
    /// If the tag read fails for any reason (older firmware, wrong path, etc.)
    /// the method returns "UNKNOWN" so the caller can fall back to the heuristic.
    /// </summary>
    public async Task<string> ReadControllerModeAsync()
    {
        if (!_isConnected || _config?.RockwellConfig == null)
            return "UNKNOWN";

        // Candidates — tried in order; first successful read wins.
        // "@PROGRAM_STATUS" is the libplctag special tag for Rockwell controller mode.
        // "@CTRL_STATUS" is an older/alternative name used by some firmware versions.
        var candidates = new[] { "@PROGRAM_STATUS", "@CTRL_STATUS" };

        foreach (var tagName in candidates)
        {
            Tag? modeTag = null;
            try
            {
                modeTag = new Tag()
                {
                    Name         = tagName,
                    Gateway      = _config.IpAddress,
                    Path         = $"1,{_config.RockwellConfig.Path?.Replace("1,", "") ?? "0"}",
                    PlcType      = PlcType.ControlLogix,
                    Protocol     = libplctag.Protocol.ab_eip,
                    Timeout      = TimeSpan.FromSeconds(2),
                    ElementCount = 1,
                    ElementSize  = 4
                };

                modeTag.Initialize();
                if (modeTag.GetStatus() != libplctag.Status.Ok)
                    continue;

                modeTag.Read();
                if (modeTag.GetStatus() != libplctag.Status.Ok)
                    continue;

                var modeInt = modeTag.GetInt32(0);
                _logger.LogDebug("[ROCKWELL] {PlcId}: Controller mode byte = {Val} (tag={Tag})",
                    _config.PlcId, modeInt, tagName);

                return modeInt switch
                {
                    0 => "PROGRAM",
                    1 => "RUN",
                    2 => "TEST",
                    3 => "REM_RUN",
                    4 => "REM_PROGRAM",
                    5 => "REM_TEST",
                    _ => "UNKNOWN"
                };
            }
            catch
            {
                // This candidate tag is not supported — try the next one.
            }
            finally
            {
                modeTag?.Dispose();
            }
        }

        // No candidate worked — caller will use the value-change heuristic.
        return "UNKNOWN";
    }

    public Task DisconnectAsync()
    {
        try
        {
            // Dispose all REAL libplctag Tag objects
            foreach (var tag in _libplcTags.Values)
            {
                try { tag.Dispose(); } catch { }
            }
            _libplcTags.Clear();
            _tagHandles.Clear();
            
            _isConnected = false;
            _logger.LogInformation("[ROCKWELL] {PlcId}: Disconnected", _config?.PlcId);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "[ROCKWELL] {PlcId}: Disconnect error", _config?.PlcId);
        }
        
        return Task.CompletedTask;
    }

    private string MapPlcType(string plcType)
    {
        return plcType.ToUpperInvariant() switch
        {
            "CONTROLLOGIX" or "CLX" or "L8" or "L7" or "L6" => "controllogix",
            "COMPACTLOGIX" or "CPLX" or "L3" or "L2" or "L1" => "compactlogix",
            "MICRO800" or "M820" or "M850" or "M870" => "micro800",
            "MICROLOGIX" or "ML" => "micrologix",
            "SLC500" or "SLC" => "slc500",
            "PLC5" or "PLC-5" => "plc5",
            "LOGIXPCCC" => "logixpccc", // ControlLogix in PCCC mode
            _ => "controllogix"
        };
    }

    private int GetElementSize(string dataType)
    {
        return dataType.ToUpperInvariant() switch
        {
            "BOOL" => 1,
            "SINT" or "BYTE" => 1,
            "INT" or "UINT" => 2,
            "DINT" or "UDINT" or "REAL" => 4,
            "LINT" or "ULINT" or "LREAL" => 8,
            "STRING" => 88, // Rockwell STRING is 82 chars + header
            _ => 4
        };
    }

    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true;

        // Dispose all REAL libplctag Tag objects
        foreach (var tag in _libplcTags.Values)
        {
            try { tag.Dispose(); } catch { }
        }
        _libplcTags.Clear();
        _tagHandles.Clear();
        
        GC.SuppressFinalize(this);
    }
}

/// <summary>
/// Internal tag handle wrapper for libplctag
/// </summary>
internal class PlcTagHandle
{
    public string Address { get; set; } = "";
    public string TagName { get; set; } = "";
    public string DataType { get; set; } = "";
    public int ElementSize { get; set; }
    public string AttributeString { get; set; } = "";
    public int Handle { get; set; } // libplctag handle (int32)
}
// RockwellDriverConfig is defined in PlcGateway.Interfaces.IPlcDriver.cs
