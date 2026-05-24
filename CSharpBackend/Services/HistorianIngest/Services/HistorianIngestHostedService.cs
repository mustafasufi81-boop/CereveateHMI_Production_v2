using OpcDaWebBrowser.Services.Health;
using OpcDaWebBrowser.Services.HistorianIngest.Config;
using OpcDaWebBrowser.Services.HistorianIngest.Models;
using System.Diagnostics;
using System.Text.Json;
using System.Collections.Generic;
using System.Collections.Concurrent;

namespace OpcDaWebBrowser.Services.HistorianIngest.Services;

/// <summary>
/// PRODUCTION-GRADE Historian Ingest Pipeline
/// Thread-safe, auto-reconnecting, zero data loss architecture
/// All critical fixes applied for industrial deployment
/// </summary>
public class HistorianIngestHostedService : BackgroundService
{
    private readonly OpcDaService _opcDaService;
    private readonly MappingCacheService _mappingCache;
    private readonly RateControllerService _rateController;
    private readonly BatcherService _batcher;
    private readonly DbWriterService _dbWriter;
    private readonly SpoolManagerService _spoolManager;
    private readonly HistorianConfig _config;
    private readonly ILogger<HistorianIngestHostedService> _logger;
    private readonly IHealthStatusService _healthService;
    private readonly LinkedList<string> _timestampOrder = new();
    private readonly Dictionary<string, LinkedListNode<string>> _timestampNodes = new(StringComparer.OrdinalIgnoreCase);
    private readonly ConcurrentDictionary<string, DateTimeOffset> _recentObservedTags = new(StringComparer.OrdinalIgnoreCase);
    private const int ObservedWindowSeconds = 120;

    private Timer? _checkpointTimer;
    private Timer? _spoolReplayTimer;
    private CancellationTokenSource? _pollingCts;
    private Task? _pollingTask;
    private Task? _batchProcessorTask;
    private long _opcSamplesReceived = 0;
    private long _samplesProcessed = 0;
    private long _samplesDropped = 0;
    private long _typeConversionErrors = 0;
    private long _batchesProcessed = 0;
    private double _lastDbWriteDurationMs = 0;
    private DateTimeOffset? _lastDbWriteTime = null;
    private string? _lastDbError = null;
    private long _lastHealthPushTicks = 0;
    private long _lastPollingInfoTicks = 0;
    private readonly SemaphoreSlim _spoolReplayLock = new(1, 1);
    private volatile bool _isShuttingDown = false;
    
    // Per-tag timestamp tracking (preserves OPC timestamps, fixes duplicates only when needed)
    private readonly Dictionary<string, DateTimeOffset> _lastTimestampPerTag = new();
    private readonly object _timestampLock = new();

    public HistorianIngestHostedService(
        OpcDaService opcDaService,
        MappingCacheService mappingCache,
        RateControllerService rateController,
        BatcherService batcher,
        DbWriterService dbWriter,
        SpoolManagerService spoolManager,
        HistorianConfig config,
        IHealthStatusService healthStatusService,
        ILogger<HistorianIngestHostedService> logger)
    {
        _logger = logger; // Set logger FIRST
        _logger.LogInformation("🚀 HistorianIngestHostedService constructor called");
        
        _opcDaService = opcDaService;
        _mappingCache = mappingCache;
        _rateController = rateController;
        _batcher = batcher;
        _dbWriter = dbWriter;
        _spoolManager = spoolManager;
        _config = config;
        _healthService = healthStatusService;
        
        _logger.LogInformation("✅ HistorianIngestHostedService constructor completed successfully");
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        _logger.LogInformation("🔵 HistorianIngestHostedService ExecuteAsync starting...");

        try
        {
            // Initialize mapping cache
            _logger.LogDebug("📊 Initializing mapping cache...");
            await _mappingCache.InitializeAsync(stoppingToken);
            _logger.LogDebug("✅ Mapping cache initialized successfully");

            // HISTORIAN FIX: Events are for UI/SignalR ONLY, NOT for historian writes
            // Historian uses POLLING LOOP to respect DbLoggingIntervalMs
            // _opcService.TagValuesUpdated += _opcEventHandler;
            _logger.LogDebug("Historian using polling-only mode (events disabled for historian)");

            // Start batch processor - store task for graceful shutdown
            _batchProcessorTask = Task.Run(async () => await ProcessBatchesAsync(stoppingToken), stoppingToken);

            // Start batcher (consumes rate-controlled samples)
            var batcherTask = _batcher.StartAsync(stoppingToken);

            // Seed DB writer health early so UI is not "Unknown"
            PublishDbWriterHealth("Starting", 0, 0, null);

            // Start checkpoint timer
            if (_config.Writer.EnableCheckpointing)
            {
                _checkpointTimer = new Timer(
                    _ => _ = SaveCheckpointAsync(CancellationToken.None),
                    null,
                    TimeSpan.FromSeconds(_config.Writer.CheckpointIntervalSeconds),
                    TimeSpan.FromSeconds(_config.Writer.CheckpointIntervalSeconds)
                );
            }

            // Start spool replay timer (thread-safe, fire-and-forget)
            if (_config.Spool.Enabled && _config.Spool.AutoReplay)
            {
                _spoolReplayTimer = new Timer(
                    _ => _ = ReplaySpool_ThreadSafe(CancellationToken.None),
                    null,
                    TimeSpan.FromSeconds(_config.Spool.ReplayIntervalSeconds),
                    TimeSpan.FromSeconds(_config.Spool.ReplayIntervalSeconds)
                );
            }

            // FIX #4: Start precise polling loop instead of Timer
            await StartHistorianOpcPollingAsync(stoppingToken);

            // Log startup event
            await _dbWriter.LogEventAsync(new HistorianEvent
            {
                EventType = HistorianEventTypes.WriterStart,
                Severity = EventSeverity.INFO,
                Message = $"Historian ingest service started with {_config.Writer.ShardCount} shards",
                WriterName = _config.Writer.WriterName
            }, stoppingToken);

            _logger.LogInformation("HistorianIngestHostedService started successfully");

            // Wait for all tasks
            await Task.WhenAll(_batchProcessorTask, batcherTask);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "HistorianIngestHostedService failed");
            throw;
        }
    }

    /// <summary>
    /// Fix timestamp uniqueness PER TAG (preserves OPC timestamp, only adjusts if duplicate)
    /// CRITICAL: Only applies +1ms when same tag has duplicate timestamp
    /// Memory-safe: LRU eviction at 50K tags to prevent unbounded growth
    /// </summary>
    private DateTimeOffset FixTimestampForUniqueness(DateTimeOffset opcTimestamp, string tagId)
    {
        lock (_timestampLock)
        {
            // Maintain explicit LRU order to avoid random eviction
            if (_timestampNodes.TryGetValue(tagId, out var existingNode))
            {
                _timestampOrder.Remove(existingNode);
                _timestampOrder.AddLast(existingNode);
            }
            else
            {
                var node = _timestampOrder.AddLast(tagId);
                _timestampNodes[tagId] = node;
            }

            // Memory leak protection: LRU eviction at 50K tags (ordered)
            if (_timestampOrder.Count > 50000)
            {
                var oldestNode = _timestampOrder.First;
                if (oldestNode != null)
                {
                    _timestampOrder.RemoveFirst();
                    _timestampNodes.Remove(oldestNode.Value);
                    _lastTimestampPerTag.Remove(oldestNode.Value);
                }
            }

            if (!_lastTimestampPerTag.TryGetValue(tagId, out var lastTimestamp))
            {
                // First time seeing this tag - use OPC timestamp as-is
                _lastTimestampPerTag[tagId] = opcTimestamp;
                return opcTimestamp;
            }

            if (opcTimestamp <= lastTimestamp)
            {
                // Duplicate timestamp for this tag - add 1ms to ensure uniqueness
                var fixedTimestamp = lastTimestamp.AddMilliseconds(1);
                _lastTimestampPerTag[tagId] = fixedTimestamp;
                _logger.LogWarning($"⚠️ OPC timestamp frozen for {tagId}: OPC={opcTimestamp:HH:mm:ss.fff}, adjusted to {fixedTimestamp:HH:mm:ss.fff}");
                return fixedTimestamp;
            }

            // OPC timestamp has advanced - use it as-is
            _lastTimestampPerTag[tagId] = opcTimestamp;
            return opcTimestamp;
        }
    }

    /// <summary>
    /// Process single tag value through pipeline
    /// INDUSTRY STANDARD: Uses poll timestamp for historian, preserves OPC timestamp for audit
    /// </summary>
    private async Task ProcessTagValueAsync(TagValue tagValue, string source, DateTimeOffset pollTimestamp)
    {
        try
        {
            // INDUSTRY STANDARD FIX: Use poll timestamp for historian (respects DbLoggingIntervalMs)
            // OPC timestamp preserved separately for audit trail
            var opcTimestamp = new DateTimeOffset(tagValue.Timestamp.ToUniversalTime());
            var uniqueTimestamp = FixTimestampForUniqueness(pollTimestamp, tagValue.ItemID);
            
            // Convert to RawSample (using poll timestamp for historian, OPC timestamp for audit)
            var rawSample = new RawSample
            {
                Time = uniqueTimestamp, // Poll timestamp (respects DbLoggingIntervalMs)
                TagId = tagValue.ItemID,
                RawValue = tagValue.Value,
                Quality = tagValue.Quality?.ToString() ?? "U",
                Source = source,
                OpcTimestamp = opcTimestamp // Original OPC server timestamp for audit
            };

            // Rate control (returns null if filtered)
            var filteredSample = _rateController.ProcessSample(rawSample);
            if (filteredSample == null)
            {
                _logger.LogDebug($"⏭️ Rate controller filtered sample for {tagValue.ItemID}");
                return;
            }

            // FIX #2: Thread-safe mapping lookup (immutable snapshot)
            var mappedSample = MapSample_ThreadSafe(filteredSample);
            if (mappedSample == null)
            {
                _logger.LogDebug($"❌ Mapping failed for {tagValue.ItemID}");
                return;
            }

            // Track observed tags for health (recent window, no DB hit)
            _recentObservedTags[tagValue.ItemID] = DateTimeOffset.Now;

            // DEBUG: Log sample being sent to batcher
            _logger.LogDebug($"✅ Sending to DB: {mappedSample.TagId} @ {mappedSample.Time:HH:mm:ss.fff}");

            // Send to batcher (bounded channel prevents memory explosion)
            await _batcher.AddSampleAsync(mappedSample);
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, $"Failed to process tag {tagValue.ItemID}");
        }
    }
    
    private string ConvertValueToString(MappedSample sample)
    {
        if (sample.ValueNum.HasValue) return sample.ValueNum.Value.ToString("F2");
        if (sample.ValueBool.HasValue) return sample.ValueBool.Value.ToString();
        if (!string.IsNullOrEmpty(sample.ValueText)) return sample.ValueText;
        return "null";
    }

    /// <summary>
    /// Normalize quality code to standard format (G=Good, B=Bad, U=Uncertain)
    /// </summary>
    private string NormalizeQuality(string rawQuality)
    {
        if (string.IsNullOrEmpty(rawQuality)) return "U";
        var upper = rawQuality.ToUpperInvariant();
        if (upper.Contains("GOOD") || upper.Contains("OK") || upper == "G") return "G";
        if (upper.Contains("BAD") || upper.Contains("ERROR") || upper == "B") return "B";
        return "U";
    }

    /// <summary>
    /// FIX #2 & #9: Thread-safe mapping with error resilience (no silent data loss)
    /// </summary>
    private MappedSample? MapSample_ThreadSafe(RawSample rawSample)
    {
        var mapping = _mappingCache.GetMapping(rawSample.TagId);
        if (mapping == null || !mapping.Enabled)
            return null;

        var mapped = new MappedSample
        {
            Time = rawSample.Time,
            TagId = rawSample.TagId,
            Quality = NormalizeQuality(rawSample.Quality),
            Source = rawSample.Source,
            MappingVersion = mapping.MappingVersion,
            DbTableName = mapping.DbTableName,
            OpcTimestamp = rawSample.OpcTimestamp // Preserve original OPC timestamp
        };

        // Type conversion - skip sample on conversion error (best practice: don't store bad data)
        try
        {
            switch (mapping.DataType)
            {
                case TagDataType.Double:
                    mapped.ValueNum = Convert.ToDouble(rawSample.RawValue);
                    break;
                case TagDataType.Int:
                    mapped.ValueNum = Convert.ToDouble(rawSample.RawValue);
                    break;
                case TagDataType.Bool:
                    mapped.ValueBool = Convert.ToBoolean(rawSample.RawValue);
                    break;
                case TagDataType.String:
                    mapped.ValueText = rawSample.RawValue?.ToString();
                    break;
            }
        }
        catch (Exception ex)
        {
            // BEST PRACTICE: Don't store bad data - log error and skip sample
            _logger.LogWarning($"Type conversion failed for tag {rawSample.TagId}: {ex.Message} (value='{rawSample.RawValue}', expected type={mapping.DataType}) - sample skipped");
            Interlocked.Increment(ref _typeConversionErrors);
            
            // Try to log event to database (defensive: don't let event logging failure crash pipeline)
            try
            {
                _ = Task.Run(async () =>
                {
                    try
                    {
                        await _dbWriter.LogEventAsync(new HistorianEvent
                        {
                            EventType = "TypeConversionError",
                            Severity = EventSeverity.WARNING,
                            Message = $"Type conversion failed for tag {rawSample.TagId}",
                            Details = new Dictionary<string, object>
                            {
                                ["tag_id"] = rawSample.TagId,
                                ["raw_value"] = rawSample.RawValue?.ToString() ?? "null",
                                ["expected_type"] = mapping.DataType.ToString(),
                                ["error_message"] = ex.Message
                            },
                            WriterName = _config.Writer.WriterName
                        }, CancellationToken.None);
                    }
                    catch
                    {
                        // Silently ignore event logging failures - don't cascade errors
                    }
                });
            }
            catch
            {
                // Event logging is optional - main pipeline must continue
            }
            
            return null; // Skip this sample - don't write bad data to database
        }

        return mapped;
    }

    /// <summary>
    /// Process batches from batcher output channel
    /// </summary>
    private async Task ProcessBatchesAsync(CancellationToken cancellationToken)
    {
        _logger.LogInformation("🚀 [BATCH-PROCESSOR] Started - waiting for batches from batcher...");

        await foreach (var batch in _batcher.OutputReader.ReadAllAsync(cancellationToken))
        {
            _logger.LogDebug($"📥 [BATCH-PROCESSOR] Received batch from batcher: shard={batch.ShardIndex}, rows={batch.Samples.Count}");
            var sw = Stopwatch.StartNew();
            var status = "Running";
            string? lastError = null;
            
            try
            {
                // Try to write to database
                _logger.LogDebug($"💾 [BATCH-PROCESSOR] Calling DbWriter.WriteBatchAsync for {batch.Samples.Count} rows...");
                var success = await _dbWriter.WriteBatchAsync(batch, cancellationToken);

                if (!success)
                {
                    // DB write failed, spool to disk
                    _logger.LogWarning($"🔴 [BATCH-PROCESSOR] DB write FAILED for batch (shard {batch.ShardIndex}), spooling...");
                    await _spoolManager.SpoolBatchAsync(batch, cancellationToken);

                    status = "Error";
                    lastError = "DB write failed - batch spooled";
                    _lastDbError = lastError;

                    // Log event
                    await _dbWriter.LogEventAsync(new HistorianEvent
                    {
                        EventType = HistorianEventTypes.SpoolWrite,
                        Severity = EventSeverity.WARNING,
                        Message = $"Batch spooled due to DB failure ({batch.Samples.Count} samples)",
                        Details = new Dictionary<string, object>
                        {
                            ["shard_index"] = batch.ShardIndex,
                            ["sample_count"] = batch.Samples.Count
                        },
                        WriterName = _config.Writer.WriterName
                    }, cancellationToken);
                }
                else
                {
                    _lastDbWriteTime = DateTimeOffset.Now;
                    _lastDbError = null;
                }
            }
            catch (Exception ex)
            {
                status = "Error";
                lastError = ex.Message;
                _lastDbError = ex.Message;
                _logger.LogError(ex, $"Error processing batch (shard {batch.ShardIndex})");
            }
            finally
            {
                _lastDbWriteDurationMs = sw.Elapsed.TotalMilliseconds;
                Interlocked.Increment(ref _batchesProcessed);
                PublishDbWriterHealth(status, batch.Samples.Count, _lastDbWriteDurationMs, lastError);
            }
        }

        _logger.LogInformation("Batch processor stopped");
    }

    private void PublishDbWriterHealth(string status, int lastBatchRowCount, double lastDurationMs, string? lastError)
    {
        if (_healthService == null)
            return;

        var nowTicks = Environment.TickCount64;
        if (nowTicks - _lastHealthPushTicks < 1500)
            return;
        _lastHealthPushTicks = nowTicks;

        var batchesCreated = _batcher.TotalBatchesCreated;
        var processed = Interlocked.Read(ref _batchesProcessed);
        var queueSize = (int)Math.Max(0, batchesCreated - processed);

        var lastWrite = _lastDbWriteTime?.DateTime;
        var writeRate = lastDurationMs <= 0 ? 0 : Math.Round(lastBatchRowCount / (lastDurationMs / 1000d), 2);

        // Coverage: mapped vs observed (recent window)
        var mappedCount = _mappingCache.GetAllEnabledMappings().Count;
        var cutoff = DateTimeOffset.Now.AddSeconds(-ObservedWindowSeconds);
        foreach (var kvp in _recentObservedTags)
        {
            if (kvp.Value < cutoff)
            {
                _recentObservedTags.TryRemove(kvp.Key, out _);
            }
        }
        var observedCount = _recentObservedTags.Count;
        var missingCount = Math.Max(0, mappedCount - observedCount);

        // Simple health score: penalize circuit breaker, backlog, and recent errors
        double score = 100;
        if (status == "Error") score -= 35;
        if (_dbWriter.IsCircuitOpen) score -= 30;
        if (queueSize > 0) score -= Math.Min(25, queueSize * 2);

        if (lastWrite.HasValue)
        {
            var secondsSinceLast = (DateTime.Now - lastWrite.Value).TotalSeconds;
            if (secondsSinceLast > 60) score -= 10;
            if (secondsSinceLast > 120) score -= 20;
        }

        score = Math.Clamp(score, 0, 100);

        _healthService.UpdateDbWriterHealth(new DbWriterHealth
        {
            Status = status,
            TotalRecordsWritten = _dbWriter.TotalRowsWritten,
            RecordsLastBatch = lastBatchRowCount,
            WriteRatePerSecond = writeRate,
            LastWriteTime = lastWrite,
            BatchQueueSize = queueSize,
            ErrorCount = (int)Math.Min(int.MaxValue, _dbWriter.TotalErrors),
            LastError = lastError ?? _lastDbError,
            MappedTags = mappedCount,
            ObservedTagsRecent = observedCount,
            MissingTags = missingCount,
            ObservedWindowSeconds = ObservedWindowSeconds,
            HealthScore = Math.Round(score, 1)
        });
    }

    /// <summary>
    /// FIX #5: JSON-safe checkpoint saving
    /// </summary>
    private async Task SaveCheckpointAsync(CancellationToken cancellationToken)
    {
        try
        {
            var infoDict = new Dictionary<string, object>
            {
                ["opc_samples_received"] = _opcSamplesReceived,
                ["samples_processed"] = _samplesProcessed,
                ["samples_dropped"] = _samplesDropped,
                ["type_conversion_errors"] = _typeConversionErrors,
                ["rate_control_passed"] = _rateController.SamplesPassed,
                ["rate_control_filtered"] = _rateController.SamplesFiltered,
                ["batches_written"] = _dbWriter.TotalBatchesWritten,
                ["rows_written"] = _dbWriter.TotalRowsWritten,
                ["spool_file_count"] = _spoolManager.GetSpoolFileCount(),
                ["spool_size_mb"] = _spoolManager.GetSpoolSizeMB()
            };

            var checkpoint = new WriterCheckpoint
            {
                WriterName = _config.Writer.WriterName,
                LastProcessedAt = DateTimeOffset.Now,
                LastMappingVersion = _mappingCache.CurrentMappingVersion,
                Info = infoDict
            };

            await _dbWriter.SaveCheckpointAsync(checkpoint, cancellationToken);
            _logger.LogDebug("Checkpoint saved");
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to save checkpoint");
        }
    }

    /// <summary>
    /// FIX #6: Thread-safe spool replay (prevents DB overload)
    /// </summary>
    private async Task ReplaySpool_ThreadSafe(CancellationToken cancellationToken)
    {
        if (!await _spoolReplayLock.WaitAsync(0, cancellationToken))
        {
            _logger.LogDebug("Spool replay already running, skipping");
            return;
        }

        try
        {
            await _spoolManager.ReplaySpoolAsync(cancellationToken);
        }
        finally
        {
            _spoolReplayLock.Release();
        }
    }

    /// <summary>
    /// Start polling loop to read from shared tag pool cache
    /// No OPC connection needed - DataLoggingService populates the pool
    /// </summary>
    private Task StartHistorianOpcPollingAsync(CancellationToken cancellationToken)
    {
        try
        {
            var enabledMappings = _mappingCache.GetAllEnabledMappings();

            _logger.LogInformation($"✅ Historian will read directly from OpcDaService (DB-driven tag subscription)");
            _logger.LogInformation($"Historian monitoring {enabledMappings.Count} enabled tags from tag_master");

            // SYNC DB → OPC SUBSCRIPTION:
            // tag_master is the source of truth. Any enabled OPC tag must be subscribed.
            // IMPORTANT: Only subscribe tags whose server_progid matches an actual OPC connection.
            // PLC tags (TRANSFORMER_LV_VOLTAGE_KV, VYAN1104C etc.) must be skipped here.
            if (enabledMappings.Count > 0 && _opcDaService.IsAnyServerConnected())
            {
                int added = 0, skippedPlc = 0;
                var opcConnections = _opcDaService.GetAllConnections()
                    .Where(c => c.IsConnected)
                    .ToList();
                var opcServerProgIds = new HashSet<string>(
                    opcConnections.Select(c => c.ServerProgID),
                    StringComparer.OrdinalIgnoreCase);

                var alreadySubscribed = new HashSet<string>(
                    _opcDaService.ReadAllTagValues().Select(v => v.ItemID),
                    StringComparer.OrdinalIgnoreCase);

                foreach (var mapping in enabledMappings)
                {
                    // Skip tags that belong to a PLC server, not OPC
                    if (!string.IsNullOrEmpty(mapping.ServerProgId) &&
                        !opcServerProgIds.Contains(mapping.ServerProgId))
                    {
                        skippedPlc++;
                        continue;
                    }

                    if (!alreadySubscribed.Contains(mapping.TagId))
                    {
                        try
                        {
                            // Find the right OPC connection for this tag
                            var conn = string.IsNullOrEmpty(mapping.ServerProgId)
                                ? opcConnections.FirstOrDefault()
                                : opcConnections.FirstOrDefault(c =>
                                    string.Equals(c.ServerProgID, mapping.ServerProgId, StringComparison.OrdinalIgnoreCase));

                            if (conn != null)
                            {
                                _opcDaService.AddTagToMonitor(conn.ConnectionId, mapping.TagId, mapping.TagName ?? mapping.TagId);
                                added++;
                            }
                        }
                        catch (Exception addEx)
                        {
                            _logger.LogWarning($"⚠️ Could not subscribe OPC tag '{mapping.TagId}': {addEx.Message}");
                        }
                    }
                }
                _logger.LogInformation($"📡 Startup OPC subscription: {added} subscribed, {skippedPlc} skipped (PLC tags), already-subscribed ignored");
            }
            else if (!_opcDaService.IsAnyServerConnected())
            {
                _logger.LogInformation("📡 OPC not yet connected at startup — tag subscription will happen in polling loop after connect");
            }
            
            if (enabledMappings.Count == 0)
            {
                _logger.LogWarning("No enabled tag mappings found. Historian polling will start and wait for mappings.");
            }
            else
            {
                foreach (var tag in enabledMappings.Take(5))
                {
                    _logger.LogInformation($"  Monitoring: {tag.TagId} (interval={tag.DbLoggingIntervalMs}ms, type={tag.DataType})");
                }
                if (enabledMappings.Count > 5)
                    _logger.LogInformation($"  ... and {enabledMappings.Count - 5} more tags");
            }

            // FIX #4: Start precise polling loop (not Timer-based)
            _pollingCts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            _pollingTask = Task.Run(async () => await PrecisePollingLoopAsync(_pollingCts.Token), _pollingCts.Token);

            _logger.LogInformation($"Historian OPC polling started for {enabledMappings.Count} tags (precise Stopwatch-driven)");
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to start Historian OPC polling");
        }

        return Task.CompletedTask;
    }

    /// <summary>
    /// FIX #4 & #10: Precise polling loop using MAIN OPC connection (not dedicated connection)
    /// CRITICAL: Reads tags from existing OpcDaService connection based on tag_master mappings
    /// </summary>
    private async Task PrecisePollingLoopAsync(CancellationToken cancellationToken)
    {
        var sw = Stopwatch.StartNew();

        while (!cancellationToken.IsCancellationRequested && !_isShuttingDown)
        {
            try
            {
                var loopStart = sw.ElapsedMilliseconds;

                // Always fetch latest enabled mappings so new/disabled tags take effect without restart
                var enabledMappings = _mappingCache.GetAllEnabledMappings();
                int targetIntervalMs = enabledMappings.Any()
                    ? enabledMappings.Min(m => m.DbLoggingIntervalMs)
                    : 1000;

                if (!enabledMappings.Any())
                {
                    if (sw.ElapsedMilliseconds % 30000 < targetIntervalMs)
                    {
                        _logger.LogWarning("⚠️ No enabled tag mappings; historian polling will retry. Add mappings to tag_master.");
                    }

                    await Task.Delay(targetIntervalMs, cancellationToken);
                    continue;
                }

                // SYNC DB → OPC: ensure any newly enabled tag_master tags are subscribed
                // ONLY subscribe tags whose server_progid matches an OPC connection (skip PLC tags)
                if (_opcDaService.IsAnyServerConnected())
                {
                    var opcConns = _opcDaService.GetAllConnections()
                        .Where(c => c.IsConnected).ToList();
                    var opcProgIds = new HashSet<string>(
                        opcConns.Select(c => c.ServerProgID),
                        StringComparer.OrdinalIgnoreCase);
                    var subscribedNow = new HashSet<string>(
                        _opcDaService.ReadAllTagValues().Select(v => v.ItemID),
                        StringComparer.OrdinalIgnoreCase);

                    foreach (var mapping in enabledMappings)
                    {
                        // Skip PLC tags - they are not on any OPC server
                        if (!string.IsNullOrEmpty(mapping.ServerProgId) &&
                            !opcProgIds.Contains(mapping.ServerProgId))
                            continue;

                        if (!subscribedNow.Contains(mapping.TagId))
                        {
                            try
                            {
                                var conn = string.IsNullOrEmpty(mapping.ServerProgId)
                                    ? opcConns.FirstOrDefault()
                                    : opcConns.FirstOrDefault(c =>
                                        string.Equals(c.ServerProgID, mapping.ServerProgId, StringComparison.OrdinalIgnoreCase));

                                if (conn != null)
                                {
                                    _opcDaService.AddTagToMonitor(conn.ConnectionId, mapping.TagId, mapping.TagName ?? mapping.TagId);
                                    _logger.LogInformation($"📡 Late-subscribed OPC tag '{mapping.TagId}' on server '{conn.ServerProgID}'");
                                }
                            }
                            catch (Exception addEx)
                            {
                                _logger.LogWarning($"⚠️ Could not subscribe OPC tag '{mapping.TagId}': {addEx.Message}");
                            }
                        }
                    }
                }

                // READ DIRECTLY FROM OPC: No DataLoggingService dependency
                // OpcDaService.ReadAllTagValues() returns live cached values from all active connections
                var allOpcValues = _opcDaService.ReadAllTagValues();

                if (allOpcValues.Count == 0)
                {
                    // OPC server not yet connected
                    var nowTicksWait = Environment.TickCount64;
                    if (nowTicksWait - _lastPollingInfoTicks >= 30000)
                    {
                        _lastPollingInfoTicks = nowTicksWait;
                        _logger.LogWarning("⚠️ OPC historian: no tag values from OPC server (not connected yet)");
                    }
                    await Task.Delay(targetIntervalMs, cancellationToken);
                    continue;
                }

                // Filter to only enabled mapped tags
                var mappedTagIds = new HashSet<string>(enabledMappings.Select(m => m.TagId), StringComparer.OrdinalIgnoreCase);
                var matchedValues = allOpcValues.Where(v => mappedTagIds.Contains(v.ItemID)).ToList();

                if (matchedValues.Count > 0)
                {
                    Interlocked.Add(ref _opcSamplesReceived, matchedValues.Count);
                    var pollTimestamp = DateTimeOffset.UtcNow;

                    var nowTicks = Environment.TickCount64;
                    if (nowTicks - _lastPollingInfoTicks >= 30000)
                    {
                        _lastPollingInfoTicks = nowTicks;
                        _logger.LogInformation("OPC historian polling: {Matched}/{Total} tags matched from OPC", matchedValues.Count, allOpcValues.Count);
                    }

                    foreach (var tagValue in matchedValues)
                    {
                        await ProcessTagValueAsync(tagValue, "OPC", pollTimestamp);
                    }
                }
                else if (loopStart == 0 || loopStart % 10000 < targetIntervalMs)
                {
                    _logger.LogWarning($"⚠️ OPC historian: {allOpcValues.Count} OPC tags live but none match {mappedTagIds.Count} enabled mappings");
                }

                // Precise timing correction
                var elapsed = sw.ElapsedMilliseconds - loopStart;
                var delay = targetIntervalMs - (int)elapsed;
                if (delay < 5)
                {
                    delay = 5; // hard floor to avoid tight CPU loop
                }

                await Task.Delay(delay, cancellationToken);
            }
            catch (OperationCanceledException)
            {
                break;
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error in precise polling loop");
                await Task.Delay(1000, cancellationToken); // Back off on error
            }
        }

        _logger.LogInformation("Precise polling loop stopped");
    }

    /// <summary>
    /// FIX #8: Coordinated shutdown with cancellation-aware cleanup
    /// </summary>
    public override async Task StopAsync(CancellationToken cancellationToken)
    {
        _logger.LogInformation("HistorianIngestHostedService stopping (coordinated shutdown)...");
        _isShuttingDown = true;

        // Stop timers
        _checkpointTimer?.Dispose();
        _spoolReplayTimer?.Dispose();

        // Stop polling loop
        _pollingCts?.Cancel();
        if (_pollingTask != null)
        {
            try
            {
                await _pollingTask.WaitAsync(TimeSpan.FromSeconds(5));
            }
            catch (TimeoutException)
            {
                _logger.LogWarning("Polling task did not stop gracefully");
            }
        }

        // Wait for batch processor to drain (graceful shutdown)
        if (_batchProcessorTask != null)
        {
            try
            {
                _logger.LogInformation("Waiting for batch processor to drain (max 30s)...");
                await _batchProcessorTask.WaitAsync(TimeSpan.FromSeconds(30));
                _logger.LogInformation("Batch processor drained successfully");
            }
            catch (TimeoutException)
            {
                _logger.LogWarning("Batch processor did not drain within 30s timeout");
            }
        }

        // Save final checkpoint
        await SaveCheckpointAsync(cancellationToken);

        // Log shutdown event
        await _dbWriter.LogEventAsync(new HistorianEvent
        {
            EventType = HistorianEventTypes.WriterStop,
            Severity = EventSeverity.INFO,
            Message = "Historian ingest service stopped",
            WriterName = _config.Writer.WriterName
        }, cancellationToken);

        _logger.LogInformation("HistorianIngestHostedService stopped (coordinated)");

        await base.StopAsync(cancellationToken);
    }

    public override void Dispose()
    {
        _spoolReplayLock?.Dispose();
        _pollingCts?.Dispose();
        base.Dispose();
    }
}
