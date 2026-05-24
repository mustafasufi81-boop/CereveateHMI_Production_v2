using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using Microsoft.Extensions.Hosting; // Added for hosting
using Microsoft.Extensions.Logging; // Added for logging
using System.Threading.Channels;
using System.Threading;
using System.Threading.Tasks;
using Parquet;
using Parquet.Data;
using Parquet.Schema;
using OpcDaWebBrowser.Services.HistorianIngest.Services;

namespace OpcDaWebBrowser.Services;

/// <summary>
/// Background service for continuous data logging to Parquet files with dedicated OPC connection
/// </summary>
public class DataLoggingService : BackgroundService
{
    private readonly LoggingConfigService _configService;
    private readonly MappingCacheService _mappingCache;
    private readonly TagValuesPoolService _tagPool;
    private readonly ILogger<DataLoggingService> _logger;
    private readonly ILoggerFactory _loggerFactory;
    private readonly string _logsFolder;
    private readonly long _maxFileSizeBytes = 10 * 1024 * 1024; // 10 MB for 10K tags (was 2MB)
    private readonly string _walFolder;
    private readonly Channel<string> _walChannel;
    private readonly int _walChannelCapacity;
    private readonly long _maxWalSizeBytes;
    private volatile bool _walOverflowActive;
    private static readonly Encoding Utf8EncodingNoBom = new UTF8Encoding(false, true);
    private static readonly ParquetSchema _logSchema = new(
        new DataField<long>("RowId"),
        new DataField<string>("TagId"),
        new DataField<DateTime>("Timestamp"),
        new DataField<string>("Value"),
        new DataField<string>("Quality")
    );
    
    private string? _currentFilePath;
    private long _currentFileSize;
    private long _rowId = 0;
    private readonly object _fileLock = new();
    private Task? _walWriterTask;
    private CancellationTokenSource? _walWriterCts;
    private Task? _stressConsumerTask;
    private CancellationTokenSource? _stressConsumerCts;
    
    // Track last parquet write time to control write frequency
    private DateTime _lastParquetWrite = DateTime.MinValue;
    
    // Dedicated OPC connection for logging
    private OpcServerConnection? _loggingConnection;
    private readonly object _connectionLock = new(); // Thread-safe OPC access
    
    // Track current tag list to detect changes
    private List<string> _currentTags = new();
    
    // Track current PARQUET interval to detect changes
    private int _currentIntervalMs = 0;
    
    // Fast config change detection
    private volatile bool _configChanged = false;

    public Channel<List<LogRecord>> StressChannel { get; }

    public DataLoggingService(
        LoggingConfigService configService,
        MappingCacheService mappingCache,
        TagValuesPoolService tagPool,
        ILogger<DataLoggingService> logger,
        ILoggerFactory loggerFactory,
        IConfiguration configuration)
    {
        _configService = configService;
        _mappingCache = mappingCache;
        _tagPool = tagPool;
        _logger = logger;
        _loggerFactory = loggerFactory;
        
        // Read log directory from configuration
        var configuredPath = configuration["LoggingPaths:DataLogDirectory"] ?? "Logs";
        
        // If path is relative, make it relative to the application directory
        _logsFolder = Path.IsPathRooted(configuredPath)
            ? configuredPath
            : Path.Combine(AppDomain.CurrentDomain.BaseDirectory, configuredPath);
        
        if (!Directory.Exists(_logsFolder))
        {
            Directory.CreateDirectory(_logsFolder);
            _logger.LogInformation($"Created log directory: {_logsFolder}");
        }

        _walFolder = Path.Combine(_logsFolder, "wal");
        Directory.CreateDirectory(_walFolder);

        if (!int.TryParse(configuration["Logging:WalChannelCapacity"], out _walChannelCapacity))
        {
            _walChannelCapacity = 512; // default capacity tuned for 10K tags
        }

        _walChannel = Channel.CreateBounded<string>(new BoundedChannelOptions(Math.Max(1, _walChannelCapacity))
        {
            FullMode = BoundedChannelFullMode.Wait
        });

        if (!long.TryParse(configuration["Logging:MaxWalSizeBytes"], out _maxWalSizeBytes))
        {
            _maxWalSizeBytes = 20L * 1024 * 1024 * 1024; // 20 GB default
        }
        
        _walOverflowActive = false;
        var maxWalSizeGb = _maxWalSizeBytes / (1024d * 1024 * 1024);

        if (!int.TryParse(configuration["StressTest:ChannelCapacity"], out var stressCapacity))
        {
            stressCapacity = 256;
        }

        StressChannel = Channel.CreateBounded<List<LogRecord>>(new BoundedChannelOptions(Math.Max(1, stressCapacity))
        {
            FullMode = BoundedChannelFullMode.Wait
        });
        
        _logger.LogInformation($"Data log files will be saved to: {_logsFolder}");
        _logger.LogInformation($"WAL directory: {_walFolder} (channel capacity {_walChannelCapacity}, max size {maxWalSizeGb:F2} GB)");
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        _logger.LogInformation("Data Logging Service started");

        // Clean up any orphaned .tmp files from previous crashes
        CleanupOrphanedTempFiles();

        // Wait for application to fully start
        await Task.Delay(3000, stoppingToken);

        _walWriterCts = CancellationTokenSource.CreateLinkedTokenSource(stoppingToken);
        StartWalWriter(_walWriterCts.Token);
        await EnqueueExistingWalFilesAsync(stoppingToken);

        _stressConsumerCts = CancellationTokenSource.CreateLinkedTokenSource(stoppingToken);
        StartStressConsumer(_stressConsumerCts.Token);

        try
        {
            // Main logging loop - always run to allow dynamic enable/disable
            while (!stoppingToken.IsCancellationRequested)
            {
                try
                {
                    // Snapshot config at start of loop for consistency
                    var config = _configService.GetConfig();
                    _configChanged = false;
                    
                    // CRITICAL FIX: Always enable if config enabled, even if ServerProgId null
                    // ServerProgId gets populated when user connects via UI
                    // Without this, tag pool never populates and historian can't write to DB
                    if (config.IsEnabled)
                    {
                        // Decrypt credentials for connection (may be null/empty initially)
                        var decryptedProgId = _configService.GetDecryptedProgId();
                        var decryptedHost = _configService.GetDecryptedHost();
                        var maskedHost = _configService.GetMaskedHost();
                        
                        // If no ServerProgId yet, wait for user to connect via UI
                        if (string.IsNullOrEmpty(decryptedProgId))
                        {
                            // Dispose connection if exists (config cleared)
                            lock (_connectionLock)
                            {
                                if (_loggingConnection != null)
                                {
                                    _logger.LogInformation("ServerProgId cleared - disposing OPC connection, waiting for new connection");
                                    _loggingConnection.Dispose();
                                    _loggingConnection = null;
                                    _currentTags.Clear();
                                }
                            }
                            
                            // Don't log warning every cycle - log once per minute
                            var nowTicks = Environment.TickCount64;
                            var checkInterval = config.PerformanceIntervals?.ConfigReloadCheckIntervalMs ?? 60000;
                            if (nowTicks % checkInterval < 1000) // ~once per check interval
                            {
                                _logger.LogInformation("⏳ Waiting for OPC server connection (connect via UI to start logging & historian)");
                            }
                            
                            var retryDelay = config.PerformanceIntervals?.ErrorRetryDelayMs ?? 1000;
                            await Task.Delay(retryDelay, stoppingToken);
                            continue;
                        }
                        
                        // ServerProgId exists - proceed with connection
                        if (config.SelectedTags.Count == 0)
                        {
                            _logger.LogWarning("No SelectedTags configured - parquet logging disabled, but historian may still run");
                            // Don't skip - historian might have mappings even if parquet has no tags
                        }
                        
                        // SEPARATION: OPC polling interval (fast) vs Parquet logging interval (configurable)
                        // OPC connection polls at OpcPollingIntervalMs to keep tag pool fresh
                        var opcPollingMs = config.PerformanceIntervals?.OpcPollingIntervalMs ?? 1000;
                        
                        // Parquet logging writes files at DataLogging.IntervalSeconds rate
                        var parquetIntervalMs = CalculateOptimalInterval(config);
                        
                        // If no connection exists, create one
                        if (_loggingConnection == null)
                        {
                            lock (_connectionLock)
                            {
                                // Double-check inside lock
                                if (_loggingConnection == null)
                                {
                                    _logger.LogInformation($"Creating dedicated OPC connection for logging: {decryptedProgId} on {maskedHost}");
                                    
                                    var connectionLogger = _loggerFactory.CreateLogger<OpcServerConnection>();
                                    _loggingConnection = new OpcServerConnection(
                                        decryptedProgId,
                                        decryptedHost,
                                        "",
                                        opcPollingMs,  // Use fast OPC polling interval
                                        connectionLogger
                                    );

                                    // Connect to OPC server
                                    _loggingConnection.Connect();
                                    _logger.LogInformation("Logging OPC connection established");

                                    // Add UNION of tags (Parquet SelectedTags + DB enabled mappings)
                                    var unionTags = GetUnionTagList(config.SelectedTags);
                                    foreach (var tagId in unionTags)
                                    {
                                        var displayName = tagId.Contains('.') ? tagId.Substring(tagId.LastIndexOf('.') + 1) : tagId;
                                        _loggingConnection.AddTag(tagId, displayName);
                                        _logger.LogDebug($"Added tag to logging connection: {tagId}");
                                    }

                                    _logger.LogInformation($"Logging ready - OPC polling: {opcPollingMs}ms, Parquet writes: {parquetIntervalMs}ms, Tags: {unionTags.Count} (Selected: {config.SelectedTags.Count})");
                                    
                                    // Force new file creation on startup
                                    _currentFilePath = null;

                                    // Store initial tags and parquet logging interval
                                    _currentTags = new List<string>(config.SelectedTags);
                                    _currentIntervalMs = parquetIntervalMs;  // This controls parquet file writes
                                    
                                    // Allow OPC connection to stabilize
                                    _logger.LogDebug("Allowing 100ms for OPC connection stabilization");
                                }
                            }
                            
                            // Stabilization delay outside lock to avoid blocking
                            await Task.Delay(100, stoppingToken);
                        }
                        // Check if tag list changed OR parquet interval changed
                        // Note: Changing OPC polling interval requires service restart
                        else if (!TagsMatch(_currentTags, config.SelectedTags) || _currentIntervalMs != parquetIntervalMs)
                        {
                            lock (_connectionLock)
                            {
                                // Double-check inside lock
                                if (_loggingConnection != null && 
                                    (!TagsMatch(_currentTags, config.SelectedTags) || _currentIntervalMs != parquetIntervalMs))
                                {
                                    var tagsChanged = !TagsMatch(_currentTags, config.SelectedTags);
                                    var intervalChanged = _currentIntervalMs != parquetIntervalMs;
                                    
                                    // If ONLY parquet interval changed, just update it (no reconnection needed)
                                    if (intervalChanged && !tagsChanged)
                                    {
                                        _currentIntervalMs = parquetIntervalMs;
                                        _logger.LogInformation($"Parquet logging interval changed to {parquetIntervalMs}ms (OPC polling unchanged at {opcPollingMs}ms)");
                                        _configChanged = true; // Signal immediate logging cycle
                                        // No reconnection needed - just continue
                                    }
                                    // If tags changed, must recreate connection
                                    else if (tagsChanged)
                                    {
                                        _logger.LogInformation($"Tag list changed ({_currentTags.Count}→{config.SelectedTags.Count}) - recreating OPC connection");
                                        
                                        // Dispose old connection
                                        _loggingConnection.Dispose();
                                        _loggingConnection = null;
                                        
                                        // Force new file creation
                                        _currentFilePath = null;
                                        
                                        // Create new OPC connection with updated tags
                                        var connectionLogger = _loggerFactory.CreateLogger<OpcServerConnection>();
                                        _loggingConnection = new OpcServerConnection(
                                            decryptedProgId,
                                            decryptedHost,
                                            "",
                                            opcPollingMs,  // OPC polling stays fast
                                            connectionLogger
                                        );
                                        _loggingConnection.Connect();
                                        
                                        // Add UNION of tags (Parquet SelectedTags + DB enabled mappings)
                                        var unionTags = GetUnionTagList(config.SelectedTags);
                                        foreach (var tagId in unionTags)
                                        {
                                            var displayName = tagId.Contains('.') ? tagId.Substring(tagId.LastIndexOf('.') + 1) : tagId;
                                            _loggingConnection.AddTag(tagId, displayName);
                                        }
                                        
                                        _logger.LogInformation($"Recreated OPC connection - OPC polling: {opcPollingMs}ms, Parquet writes: {parquetIntervalMs}ms, Tags: {unionTags.Count}");
                                        
                                        // Update current tag list and interval
                                        _currentTags = new List<string>(config.SelectedTags);
                                        _currentIntervalMs = parquetIntervalMs;
                                        _configChanged = true; // Signal immediate logging cycle
                                        
                                        _logger.LogDebug("Allowing 100ms for OPC reconnection stabilization");
                                    }
                                }
                            }
                            
                            // Stabilization delay outside lock (only if tags changed - reconnection happened)
                            if (!TagsMatch(_currentTags, config.SelectedTags))
                            {
                                await Task.Delay(100, stoppingToken);
                            }
                        }
                        
                        // Log data
                        await LogData(config, stoppingToken);
                    }
                    else
                    {
                        // Logging is disabled - dispose connection if exists
                        lock (_connectionLock)
                        {
                            if (_loggingConnection != null)
                            {
                                _logger.LogInformation("Logging disabled - disposing OPC connection");
                                _loggingConnection.Dispose();
                                _loggingConnection = null;
                                _currentTags.Clear();
                            }
                        }
                    }
                    
                    // Fast interval change: skip delay if config just changed
                    if (_configChanged)
                    {
                        _logger.LogDebug("Config changed - skipping delay for immediate logging cycle");
                        continue;
                    }
                    
                    // CRITICAL: Loop at OPC polling rate to keep TagPool fresh (500ms)
                    // Parquet file writes only happen when counter reaches the parquet interval
                    var fallback = config.PerformanceIntervals?.HistorianPollingFallbackMs ?? 1000;
                    var loopDelayMs = config.PerformanceIntervals?.OpcPollingIntervalMs ?? fallback;
                    _logger.LogDebug($"Loop delay: {loopDelayMs}ms (OPC polling rate - TagPool refresh)");
                    
                    await Task.Delay(loopDelayMs, stoppingToken);
                }
                catch (Exception ex)
                {
                    _logger.LogError(ex, "Error in data logging loop");
                    var currentConfig = _configService.GetConfig();
                    var errorDelay = currentConfig.PerformanceIntervals?.ErrorRetryDelayMs ?? 5000;
                    await Task.Delay(errorDelay, stoppingToken);
                }
            }
        }
        finally
        {
            // Cleanup
            lock (_connectionLock)
            {
                if (_loggingConnection != null)
                {
                    _loggingConnection.Dispose();
                    _loggingConnection = null;
                    _logger.LogInformation("Logging OPC connection disposed");
                }
            }

            _walChannel.Writer.TryComplete();

            if (_walWriterCts != null)
            {
                _walWriterCts.Cancel();
            }

            if (_walWriterTask != null)
            {
                try
                {
                    await _walWriterTask;
                }
                catch (OperationCanceledException)
                {
                    // Expected during shutdown
                }
                catch (Exception ex)
                {
                    _logger.LogError(ex, "Error shutting down WAL writer");
                }
            }

            StressChannel.Writer.TryComplete();

            if (_stressConsumerCts != null)
            {
                _stressConsumerCts.Cancel();
            }

            if (_stressConsumerTask != null)
            {
                try
                {
                    await _stressConsumerTask;
                }
                catch (OperationCanceledException)
                {
                    // Expected during shutdown
                }
                catch (Exception ex)
                {
                    _logger.LogError(ex, "Error shutting down stress consumer");
                }
            }
        }

        _logger.LogInformation("Data Logging Service stopped");
    }

    private async Task LogData(LoggingConfig config, CancellationToken stoppingToken)
    {
        try
        {
            if (_walOverflowActive)
            {
                var walSize = CalculateWalDirectorySize();
                if (walSize >= _maxWalSizeBytes)
                {
                    _logger.LogWarning(
                        "Skipping logging cycle because WAL directory usage remains above limit ({CurrentSizeGb:F2} GB)",
                        walSize / (1024d * 1024 * 1024));
                    return;
                }
            }

            // Thread-safe snapshot of OPC connection for reading
            OpcServerConnection? connectionSnapshot;
            lock (_connectionLock)
            {
                connectionSnapshot = _loggingConnection;
            }
            
            if (connectionSnapshot == null)
            {
                _logger.LogDebug("No OPC connection available for logging cycle");
                return;
            }

            // Capture system timestamp at exact moment of read - this ensures perfect intervals
            // Use this SAME timestamp for all tags in this batch for consistency
            var batchTimestamp = DateTime.Now;
            
            // CRITICAL: Read from OPC connection's internal cache (_cachedValues)
            // The connection's polling loop runs at OpcPollingIntervalMs (500ms) and keeps cache fresh
            // We just grab the latest cached values here (no OPC device read!)
            var allValues = connectionSnapshot.GetCachedValues();
            
            if (allValues.Count == 0)
            {
                _logger.LogDebug("No cached tag values available yet (connection may be initializing)");
                return;
            }

            // UPDATE SHARED TAG POOL: Store ALL tag values (UNION of Parquet + DB tags) in cache
            // HistorianIngestHostedService pulls from pool and filters by tag_master mappings
            // DataLoggingService pulls from pool and filters by SelectedTags for Parquet
            // THIS HAPPENS EVERY OPC POLLING CYCLE (500ms) - keeps pool fresh!
            _tagPool.UpdatePool(allValues, batchTimestamp);

            // PARQUET WRITE: Only write to files at the parquet logging interval (_currentIntervalMs)
            var timeSinceLastWrite = (DateTime.Now - _lastParquetWrite).TotalMilliseconds;
            if (timeSinceLastWrite < _currentIntervalMs)
            {
                // Not time to write yet - just updated TagPool, skip parquet write
                _logger.LogDebug($"TagPool updated (next parquet write in {_currentIntervalMs - timeSinceLastWrite:F0}ms)");
                return;
            }
            
            // Time to write parquet file!
            _lastParquetWrite = DateTime.Now;
            _logger.LogDebug($"Writing parquet file ({_currentIntervalMs}ms interval reached)");

            // Pre-allocate list capacity for 10K tags
            var logRecords = new List<LogRecord>(allValues.Count);
            
            foreach (var v in allValues)
            {
                logRecords.Add(new LogRecord
                {
                    RowId = Interlocked.Increment(ref _rowId),
                    TagId = v.ItemID,
                    Timestamp = batchTimestamp, // Use our system timestamp, not OPC timestamp
                    Value = ValidateValue(v.Value),
                    Quality = ValidateQuality(v.Value, v.Quality)
                });
            }

            await PersistBatchAsync(logRecords, stoppingToken);
            
            _logger.LogDebug($"Logged {logRecords.Count} records");
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error logging data");
        }
    }

    private string ValidateValue(string value)
    {
        if (string.IsNullOrWhiteSpace(value) || 
            value.Equals("null", StringComparison.OrdinalIgnoreCase) ||
            value.Contains("ERROR", StringComparison.OrdinalIgnoreCase))
        {
            return "NULL";
        }
        return value;
    }

    private string ValidateQuality(string value, string quality)
    {
        // Mark as BAD if value is null, empty, or garbage
        if (string.IsNullOrWhiteSpace(value) || 
            value.Equals("null", StringComparison.OrdinalIgnoreCase) ||
            value.Contains("ERROR", StringComparison.OrdinalIgnoreCase))
        {
            return "BAD";
        }

        // Return original quality if value is valid
        return quality ?? "UNKNOWN";
    }

    private async Task PersistBatchAsync(List<LogRecord> records, CancellationToken stoppingToken)
    {
        if (records.Count == 0)
            return;

        var walFileName = $"{DateTime.UtcNow:yyyyMMdd_HHmmss_fff}_{Guid.NewGuid():N}";
        var walTempPath = Path.Combine(_walFolder, walFileName + ".tmp");
        var walReadyPath = Path.Combine(_walFolder, walFileName + ".ready");

        var currentWalSize = CalculateWalDirectorySize();

        if (currentWalSize >= _maxWalSizeBytes)
        {
            if (!_walOverflowActive)
            {
                _walOverflowActive = true;
                _logger.LogCritical(
                    "WAL directory size {CurrentSizeGb:F2} GB exceeded limit {MaxSizeGb:F2} GB; suspending new logging batches",
                    currentWalSize / (1024d * 1024 * 1024),
                    _maxWalSizeBytes / (1024d * 1024 * 1024));
            }

            throw new InvalidOperationException("WAL directory size limit exceeded");
        }

        if (_walOverflowActive && currentWalSize < _maxWalSizeBytes * 0.8)
        {
            _walOverflowActive = false;
            _logger.LogInformation("WAL directory usage recovered below 80% of limit; resuming logging");
        }

        try
        {
            using (var stream = new FileStream(
                walTempPath,
                FileMode.CreateNew,
                FileAccess.Write,
                FileShare.None,
                bufferSize: 8192,
                FileOptions.WriteThrough | FileOptions.Asynchronous))
            using (var writer = new BinaryWriter(stream, Encoding.UTF8, leaveOpen: true))
            {
                writer.Write(records.Count);
                foreach (var record in records)
                {
                    writer.Write(record.RowId);
                    writer.Write(record.Timestamp.ToBinary());
                    WriteUtf8String(writer, record.TagId);
                    WriteUtf8String(writer, record.Value);
                    WriteUtf8String(writer, record.Quality);
                }

                await stream.FlushAsync(stoppingToken);
                stream.Flush(true);
            }

            File.Move(walTempPath, walReadyPath, overwrite: false);
            await EnqueueWalFilePathAsync(walReadyPath, stoppingToken);
        }
        catch (OperationCanceledException)
        {
            throw;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, $"Failed to persist WAL batch '{walFileName}'");
            try
            {
                if (File.Exists(walTempPath))
                    File.Delete(walTempPath);
            }
            catch { }
            throw;
        }
    }

    private void CreateNewFile()
    {
        var timestamp = DateTime.Now.ToString("yyyyMMdd_HHmmss");
        var newPath = Path.Combine(_logsFolder, $"OpcData_{timestamp}.parquet");
        
        // Ensure unique filename if file already exists
        int counter = 1;
        while (File.Exists(newPath))
        {
            newPath = Path.Combine(_logsFolder, $"OpcData_{timestamp}_{counter}.parquet");
            counter++;
        }
        
        _currentFilePath = newPath;
        _currentFileSize = 0;
        _logger.LogInformation($"Created new log file: {_currentFilePath}");
    }

    private async Task AppendToParquetFileAsync(List<LogRecord> records, CancellationToken token)
    {
        if (records.Count == 0)
        {
            return;
        }

        string targetPath;
        bool fileHasContent;

        lock (_fileLock)
        {
            if (_currentFilePath == null || _currentFileSize >= _maxFileSizeBytes)
            {
                CreateNewFile();
            }

            targetPath = _currentFilePath!;
            fileHasContent = _currentFileSize > 0;
        }

        var rowIds = records.Select(r => r.RowId).ToArray();
        var tagIds = records.Select(r => r.TagId).ToArray();
        var timestamps = records.Select(r => r.Timestamp).ToArray();
        var values = records.Select(r => r.Value).ToArray();
        var qualities = records.Select(r => r.Quality).ToArray();

        var directory = Path.GetDirectoryName(targetPath)!;
        var tempPath = Path.Combine(directory, Path.GetFileName(targetPath) + ".tmpwrite");
        var backupPath = Path.Combine(directory, Path.GetFileName(targetPath) + ".bak");

        try
        {
            if (File.Exists(tempPath))
            {
                _logger.LogWarning("Found leftover temp parquet {TempPath}, removing before write", tempPath);
                File.Delete(tempPath);
            }

            bool targetExists = File.Exists(targetPath);
            if (!targetExists)
            {
                fileHasContent = false;
            }

            _logger.LogDebug("Parquet append start | target={Target} exists={TargetExists} hasContent={HasContent} records={Count}", targetPath, targetExists, fileHasContent, records.Count);

            if (fileHasContent && targetExists)
            {
                File.Copy(targetPath, tempPath, overwrite: true);
            }

            using (var stream = new FileStream(
                tempPath,
                fileHasContent ? FileMode.Open : FileMode.CreateNew,
                FileAccess.ReadWrite,
                FileShare.None))
            {
                if (fileHasContent)
                {
                    stream.Seek(0, SeekOrigin.End);
                }
                else
                {
                    stream.SetLength(0);
                }

                await using var writer = await ParquetWriter.CreateAsync(
                    _logSchema,
                    stream,
                    append: fileHasContent,
                    cancellationToken: token);

                using var groupWriter = writer.CreateRowGroup();

                await groupWriter.WriteColumnAsync(new DataColumn(_logSchema.DataFields[0], rowIds), token);
                await groupWriter.WriteColumnAsync(new DataColumn(_logSchema.DataFields[1], tagIds), token);
                await groupWriter.WriteColumnAsync(new DataColumn(_logSchema.DataFields[2], timestamps), token);
                await groupWriter.WriteColumnAsync(new DataColumn(_logSchema.DataFields[3], values), token);
                await groupWriter.WriteColumnAsync(new DataColumn(_logSchema.DataFields[4], qualities), token);

                await stream.FlushAsync(token);
                stream.Flush(true);
            }

            if (File.Exists(backupPath))
            {
                File.Delete(backupPath);
            }

            if (File.Exists(targetPath))
            {
                File.Replace(tempPath, targetPath, backupPath, ignoreMetadataErrors: true);
                File.Delete(backupPath);
            }
            else
            {
                File.Move(tempPath, targetPath);
            }

            var newSize = new FileInfo(targetPath).Length;

            lock (_fileLock)
            {
                _currentFileSize = newSize;
                _currentFilePath = targetPath;
            }

            _logger.LogDebug($"Appended {records.Count} records to {Path.GetFileName(targetPath)} (size {newSize} bytes)");
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error writing parquet | target={Target} temp={Temp} backup={Backup} records={Count} hasContent={HasContent}", targetPath, tempPath, backupPath, records.Count, fileHasContent);
            lock (_fileLock)
            {
                _currentFilePath = null;
                _currentFileSize = 0;
            }
            try
            {
                if (File.Exists(tempPath))
                {
                    File.Delete(tempPath);
                }
                if (File.Exists(backupPath))
                {
                    File.Delete(backupPath);
                }
            }
            catch
            {
                // ignore cleanup errors
            }

            throw;
        }
    }

    /// <summary>
    /// Calculate optimal polling interval based on tag count
    /// For 10K+ tags, slower polling prevents system overload
    /// </summary>
    private int CalculateOptimalInterval(LoggingConfig config)
    {
        int tagCount = config.SelectedTags.Count;
        
        // User-specified interval takes priority if set
        if (config.DataLogging?.IntervalSeconds > 0)
        {
            int userInterval = config.DataLogging.IntervalSeconds * 1000;
            _logger.LogInformation($"Using user-specified interval: {userInterval}ms for {tagCount} tags");
            return userInterval;
        }
        
        // Auto-scale interval based on tag count
        int interval = tagCount switch
        {
            <= 500 => 1000,      // 1 second for small sets
            <= 1000 => 1500,     // 1.5 seconds for medium
            <= 2000 => 2000,     // 2 seconds for large
            <= 5000 => 3000,     // 3 seconds for very large
            <= 10000 => 5000,    // 5 seconds for 10K tags
            _ => 10000           // 10 seconds for >10K tags
        };
        
        _logger.LogInformation($"Auto-calculated interval: {interval}ms for {tagCount} tags");
        return interval;
    }

    /// <summary>
    /// Clean up any .tmp files left from previous crashes
    /// </summary>
    private void CleanupOrphanedTempFiles()
    {
        try
        {
            var tempFiles = Directory.GetFiles(_logsFolder, "*.tmp");
            foreach (var tmpFile in tempFiles)
            {
                try
                {
                    File.Delete(tmpFile);
                    _logger.LogInformation($"Deleted orphaned temp file: {Path.GetFileName(tmpFile)}");
                }
                catch (Exception ex)
                {
                    _logger.LogWarning(ex, $"Could not delete temp file: {Path.GetFileName(tmpFile)}");
                }
            }
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Error during temp file cleanup");
        }
    }

    /// <summary>
    /// Check if two tag lists match (same tags, order doesn't matter)
    /// </summary>
    private bool TagsMatch(List<string> list1, List<string> list2)
    {
        if (list1.Count != list2.Count)
            return false;
        
        var set1 = new HashSet<string>(list1);
        var set2 = new HashSet<string>(list2);
        
        return set1.SetEquals(set2);
    }

    private void StartWalWriter(CancellationToken token)
    {
        _walWriterTask = Task.Run(() => WalWriterLoopAsync(token), CancellationToken.None);
    }

    private void StartStressConsumer(CancellationToken token)
    {
        _stressConsumerTask = Task.Run(() => StressConsumerLoopAsync(token), CancellationToken.None);
    }

    private async Task StressConsumerLoopAsync(CancellationToken token)
    {
        _logger.LogInformation("Stress channel consumer started");
        while (await StressChannel.Reader.WaitToReadAsync(token))
        {
            while (StressChannel.Reader.TryRead(out var batch))
            {
                try
                {
                    await PersistBatchAsync(batch, token);
                }
                catch (OperationCanceledException)
                {
                    throw;
                }
                catch (Exception ex)
                {
                    _logger.LogError(ex, "Error processing stress test batch");
                }
            }
        }
        _logger.LogInformation("Stress channel consumer exiting");
    }

    private async Task WalWriterLoopAsync(CancellationToken token)
    {
        _logger.LogInformation("WAL writer loop started");
        while (await _walChannel.Reader.WaitToReadAsync(token))
        {
            while (_walChannel.Reader.TryRead(out var walPath))
            {
                await ProcessWalFileAsync(walPath, token);
            }
        }
        _logger.LogInformation("WAL writer loop exiting");
    }

    private async Task ProcessWalFileAsync(string walPath, CancellationToken token)
    {
        for (int attempt = 1; attempt <= 5; attempt++)
        {
            try
            {
                var records = ReadWalFile(walPath);
                await AppendToParquetFileAsync(records, token);
                File.Delete(walPath);
                _logger.LogDebug($"Processed WAL {Path.GetFileName(walPath)} with {records.Count} records");
                return;
            }
            catch (OperationCanceledException)
            {
                throw;
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, $"Failed to process WAL {Path.GetFileName(walPath)} (attempt {attempt})");
                await Task.Delay(TimeSpan.FromSeconds(Math.Min(5, attempt * 2)), token);
            }
        }

        _logger.LogWarning($"WAL {Path.GetFileName(walPath)} could not be processed after retries; re-queuing");
        await EnqueueWalFilePathAsync(walPath, token);
    }

    private List<LogRecord> ReadWalFile(string walPath)
    {
        using var stream = new FileStream(walPath, FileMode.Open, FileAccess.Read, FileShare.Read);
        using var reader = new BinaryReader(stream, Encoding.UTF8);
        int count = reader.ReadInt32();
        var records = new List<LogRecord>(count);

        for (int i = 0; i < count; i++)
        {
            long rowId = reader.ReadInt64();
            long timestampBinary = reader.ReadInt64();
            string tagId = ReadUtf8String(reader);
            string value = ReadUtf8String(reader);
            string quality = ReadUtf8String(reader);

            records.Add(new LogRecord
            {
                RowId = rowId,
                Timestamp = DateTime.FromBinary(timestampBinary),
                TagId = tagId,
                Value = value,
                Quality = quality
            });
        }

        return records;
    }

    private async Task EnqueueWalFilePathAsync(string walPath, CancellationToken token)
    {
        while (await _walChannel.Writer.WaitToWriteAsync(token))
        {
            if (_walChannel.Writer.TryWrite(walPath))
            {
                _logger.LogDebug($"Enqueued WAL file {Path.GetFileName(walPath)}");
                return;
            }
        }

        throw new InvalidOperationException("WAL channel is completed; cannot enqueue new work");
    }

    private async Task EnqueueExistingWalFilesAsync(CancellationToken token)
    {
        var existing = Directory.GetFiles(_walFolder, "*.ready")
            .OrderBy(f => f)
            .ToList();

        if (existing.Count == 0)
            return;

        _logger.LogInformation($"Found {existing.Count} WAL file(s) from previous run; enqueuing for processing");

        foreach (var walPath in existing)
        {
            await EnqueueWalFilePathAsync(walPath, token);
        }
    }

    private static void WriteUtf8String(BinaryWriter writer, string value)
    {
        var bytes = Utf8EncodingNoBom.GetBytes(value ?? string.Empty);
        Write7BitEncodedInt(writer, bytes.Length);
        writer.Write(bytes);
    }

    private static string ReadUtf8String(BinaryReader reader)
    {
        int length = Read7BitEncodedInt(reader);
        if (length == 0)
        {
            return string.Empty;
        }

        var bytes = reader.ReadBytes(length);
        if (bytes.Length != length)
        {
            throw new EndOfStreamException("Unexpected end of WAL file while reading string payload");
        }
        return Utf8EncodingNoBom.GetString(bytes);
    }

    private static void Write7BitEncodedInt(BinaryWriter writer, int value)
    {
        uint v = (uint)value;
        while (v >= 0x80)
        {
            writer.Write((byte)(v | 0x80));
            v >>= 7;
        }
        writer.Write((byte)v);
    }

    private static int Read7BitEncodedInt(BinaryReader reader)
    {
        int count = 0;
        int shift = 0;
        while (true)
        {
            if (shift >= 5 * 7)
            {
                throw new FormatException("7-bit encoded int is too large");
            }

            byte b = reader.ReadByte();
            count |= (b & 0x7F) << shift;

            if ((b & 0x80) == 0)
            {
                break;
            }

            shift += 7;
        }

        return count;
    }

    /// <summary>
    /// Compute UNION of Parquet SelectedTags and PostgreSQL enabled tag mappings
    /// OPC connection monitors this union, each service filters what it needs
    /// </summary>
    private HashSet<string> GetUnionTagList(List<string> selectedTags)
    {
        var unionTags = new HashSet<string>(selectedTags, StringComparer.OrdinalIgnoreCase);
        
        // Add enabled DB tags to union
        var dbMappings = _mappingCache.GetAllMappings();
        foreach (var mapping in dbMappings.Where(m => m.Enabled))
        {
            unionTags.Add(mapping.TagId);
        }
        
        _logger.LogDebug($"Tag UNION: Parquet={selectedTags.Count}, DB={dbMappings.Count(m => m.Enabled)}, Total={unionTags.Count}");
        return unionTags;
    }

    private long CalculateWalDirectorySize()
    {
        try
        {
            return Directory.EnumerateFiles(_walFolder, "*", SearchOption.TopDirectoryOnly)
                .Select(path => new FileInfo(path))
                .Where(info => info.Exists)
                .Sum(info => info.Length);
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Failed to calculate WAL directory size; assuming limit exceeded to stay safe");
            return long.MaxValue;
        }
    }
}

public class LogRecord
{
    public long RowId { get; set; }
    public required string TagId { get; set; }
    public DateTime Timestamp { get; set; }
    public required string Value { get; set; }
    public required string Quality { get; set; }
}
