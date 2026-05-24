using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using System.Collections.Concurrent;

namespace PlcGateway.Services;

/// <summary>
/// PLC Parquet Logging Service
/// 
/// DESIGN (Mirrors OPC DataLoggingService parquet functionality):
/// - Reads from PlcTagValuesPoolService (same as historian)
/// - Writes rotating parquet files (size/time based)
/// - Only logs tags with parquet_logging_enabled = true
/// 
/// OUTPUT FORMAT:
/// - Path: D:\PlcLogs\Data\{plcId}\{date}\{timestamp}.parquet
/// - Schema: Timestamp, TagName, Value, Quality, DataType
/// - Rotation: By size (10MB) or time (1 hour)
/// </summary>
public class PlcParquetLoggingService : BackgroundService
{
    private readonly PlcTagValuesPoolService _tagPool;
    private readonly PlcConfigLoaderService _configLoader;
    private readonly ILogger<PlcParquetLoggingService> _logger;

    // Configuration
    private readonly string _outputBasePath;
    private readonly int _writeIntervalMs;
    private readonly long _maxFileSizeBytes;
    private readonly bool _enabled;

    // State tracking
    private readonly ConcurrentDictionary<string, ParquetFileState> _fileStates = new();
    private readonly ConcurrentDictionary<string, List<string>> _parquetEnabledTags = new();
    private DateTime _lastTagRefresh = DateTime.MinValue;
    private readonly object _writeLock = new();

    // Statistics
    private long _totalRecordsWritten;
    private int _filesCreated;

    public PlcParquetLoggingService(
        PlcTagValuesPoolService tagPool,
        PlcConfigLoaderService configLoader,
        IConfiguration configuration,
        ILogger<PlcParquetLoggingService> logger)
    {
        _tagPool = tagPool;
        _configLoader = configLoader;
        _logger = logger;

        _enabled = configuration.GetValue<bool>("PlcGateway:EnableParquetLogging", false);
        _outputBasePath = configuration.GetValue<string>("PlcGateway:ParquetOutputPath", "D:\\PlcLogs\\Data") ?? "D:\\PlcLogs\\Data";
        _writeIntervalMs = configuration.GetValue<int>("PlcGateway:ParquetWriteIntervalMs", 5000);
        _maxFileSizeBytes = configuration.GetValue<long>("PlcGateway:ParquetMaxFileSizeBytes", 10 * 1024 * 1024); // 10MB

        _logger.LogInformation(
            "[PLC PARQUET] Initialized - Enabled: {Enabled}, Path: {Path}, Interval: {Interval}ms, MaxSize: {Size}MB",
            _enabled, _outputBasePath, _writeIntervalMs, _maxFileSizeBytes / 1024 / 1024);
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        if (!_enabled)
        {
            _logger.LogInformation("[PLC PARQUET] Parquet logging is disabled");
            return;
        }

        _logger.LogInformation("[PLC PARQUET] Service starting...");

        // Wait for pool to be populated
        await Task.Delay(4000, stoppingToken);

        // Ensure output directory exists
        if (!Directory.Exists(_outputBasePath))
        {
            Directory.CreateDirectory(_outputBasePath);
            _logger.LogInformation("[PLC PARQUET] Created output directory: {Path}", _outputBasePath);
        }

        try
        {
            // Load which tags should be logged to parquet
            await RefreshParquetTagsAsync();

            var lastWriteTime = DateTime.UtcNow;

            while (!stoppingToken.IsCancellationRequested)
            {
                try
                {
                    // Check if it's time to write
                    var timeSinceLastWrite = (DateTime.UtcNow - lastWriteTime).TotalMilliseconds;

                    if (timeSinceLastWrite >= _writeIntervalMs)
                    {
                        await WriteParquetDataAsync();
                        lastWriteTime = DateTime.UtcNow;
                    }

                    // Periodically refresh tag list (every 5 minutes)
                    if ((DateTime.UtcNow - _lastTagRefresh).TotalMinutes > 5)
                    {
                        await RefreshParquetTagsAsync();
                    }

                    await Task.Delay(100, stoppingToken); // Small delay to prevent busy loop
                }
                catch (Exception ex)
                {
                    _logger.LogError(ex, "[PLC PARQUET] Error in write cycle");
                }
            }
        }
        catch (OperationCanceledException)
        {
            // Normal shutdown
        }

        // Flush remaining data
        await FlushAllFilesAsync();

        _logger.LogInformation("[PLC PARQUET] Service stopped. Records: {Records}, Files: {Files}",
            _totalRecordsWritten, _filesCreated);
    }

    // ═══════════════════════════════════════════════════════════════════
    // TAG CONFIGURATION
    // ═══════════════════════════════════════════════════════════════════

    private async Task RefreshParquetTagsAsync()
    {
        try
        {
            var configs = await _configLoader.LoadAllEnabledPlcsAsync();
            _parquetEnabledTags.Clear();

            foreach (var plc in configs)
            {
                var parquetTags = plc.Tags
                    .Where(t => t.ParquetLoggingEnabled)
                    .Select(t => t.TagId)
                    .ToList();

                if (parquetTags.Count > 0)
                {
                    _parquetEnabledTags[plc.PlcId] = parquetTags;
                }
            }

            _lastTagRefresh = DateTime.UtcNow;
            _logger.LogInformation("[PLC PARQUET] Loaded {PlcCount} PLCs with {TagCount} total parquet tags",
                _parquetEnabledTags.Count, _parquetEnabledTags.Values.Sum(t => t.Count));
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "[PLC PARQUET] Failed to refresh parquet tags");
        }
    }

    // ═══════════════════════════════════════════════════════════════════
    // PARQUET WRITING
    // ═══════════════════════════════════════════════════════════════════

    private async Task WriteParquetDataAsync()
    {
        if (_parquetEnabledTags.IsEmpty)
        {
            return; // No tags configured for parquet
        }

        var timestamp = DateTime.UtcNow;

        // Process each PLC separately (isolated files)
        foreach (var (plcId, tagList) in _parquetEnabledTags)
        {
            try
            {
                await WriteParquetForPlcAsync(plcId, tagList, timestamp);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "[PLC PARQUET] Write error for PLC {PlcId}", plcId);
            }
        }
    }

    private async Task WriteParquetForPlcAsync(string plcId, List<string> tagList, DateTime timestamp)
    {
        // Get values from pool for these tags
        var values = _tagPool.GetPlcValues(plcId)
            .Where(v => tagList.Contains(v.TagName))
            .ToList();

        if (values.Count == 0)
        {
            return; // No data to write
        }

        // Get or create file state
        var fileState = GetOrCreateFileState(plcId, timestamp);

        // Check if we need to rotate
        if (ShouldRotateFile(fileState))
        {
            await RotateFileAsync(fileState, plcId, timestamp);
        }

        // Write data (using simple CSV format as parquet needs Parquet.NET)
        // In production, replace with actual parquet writer
        await WriteDataToFileAsync(fileState, values, timestamp);

        _totalRecordsWritten += values.Count;
    }

    private ParquetFileState GetOrCreateFileState(string plcId, DateTime timestamp)
    {
        return _fileStates.GetOrAdd(plcId, _ => CreateNewFileState(plcId, timestamp));
    }

    private ParquetFileState CreateNewFileState(string plcId, DateTime timestamp)
    {
        // Create directory structure: {base}/{plcId}/{date}/
        var dateDir = timestamp.ToString("yyyy-MM-dd");
        var plcDir = Path.Combine(_outputBasePath, plcId, dateDir);

        if (!Directory.Exists(plcDir))
        {
            Directory.CreateDirectory(plcDir);
        }

        var fileName = $"{timestamp:HHmmss}_{Guid.NewGuid():N}.csv"; // Use .csv for now, .parquet in production
        var filePath = Path.Combine(plcDir, fileName);

        _filesCreated++;

        return new ParquetFileState
        {
            FilePath = filePath,
            PlcId = plcId,
            CreatedAt = timestamp,
            CurrentSize = 0,
            RecordCount = 0
        };
    }

    private bool ShouldRotateFile(ParquetFileState state)
    {
        // Rotate if:
        // 1. File exceeds max size
        // 2. Date changed (new day)
        // 3. File older than 1 hour
        
        if (state.CurrentSize >= _maxFileSizeBytes) return true;
        if (state.CreatedAt.Date != DateTime.UtcNow.Date) return true;
        if ((DateTime.UtcNow - state.CreatedAt).TotalHours >= 1) return true;
        
        return false;
    }

    private async Task RotateFileAsync(ParquetFileState oldState, string plcId, DateTime timestamp)
    {
        _logger.LogInformation("[PLC PARQUET] Rotating file for PLC {PlcId}: {OldFile} ({Size}KB, {Records} records)",
            plcId, Path.GetFileName(oldState.FilePath), oldState.CurrentSize / 1024, oldState.RecordCount);

        // Create new file state
        var newState = CreateNewFileState(plcId, timestamp);
        _fileStates[plcId] = newState;
    }

    private async Task WriteDataToFileAsync(ParquetFileState state, List<PlcTagValueCacheEntry> values, DateTime timestamp)
    {
        lock (_writeLock)
        {
            try
            {
                // Write header if new file
                if (state.RecordCount == 0)
                {
                    File.WriteAllText(state.FilePath, "Timestamp,PlcId,TagName,Value,Quality,DataType\n");
                }

                // Append data
                using var writer = new StreamWriter(state.FilePath, append: true);
                foreach (var value in values)
                {
                    var line = $"{timestamp:O},{state.PlcId},{value.TagName},{value.Value},{value.Quality},{value.DataType}";
                    writer.WriteLine(line);
                    state.RecordCount++;
                }
                
                // Update file size
                state.CurrentSize = new FileInfo(state.FilePath).Length;
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "[PLC PARQUET] File write error: {Path}", state.FilePath);
            }
        }
    }

    private async Task FlushAllFilesAsync()
    {
        _logger.LogInformation("[PLC PARQUET] Flushing {Count} open files", _fileStates.Count);
        // Files are automatically closed by FileStream - no action needed for CSV
    }

    public override async Task StopAsync(CancellationToken cancellationToken)
    {
        _logger.LogInformation("[PLC PARQUET] Service stopping...");
        await base.StopAsync(cancellationToken);
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// SUPPORTING TYPES
// ═══════════════════════════════════════════════════════════════════════════

internal class ParquetFileState
{
    public string FilePath { get; set; } = "";
    public string PlcId { get; set; } = "";
    public DateTime CreatedAt { get; set; }
    public long CurrentSize { get; set; }
    public long RecordCount { get; set; }
}
