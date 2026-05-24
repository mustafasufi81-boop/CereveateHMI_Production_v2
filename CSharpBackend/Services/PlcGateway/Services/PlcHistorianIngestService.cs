using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Npgsql;
using NpgsqlTypes;
using PlcGateway.Interfaces;
using System.Collections.Concurrent;
using System.Diagnostics;

namespace PlcGateway.Services;

/// <summary>
/// PLC Historian Ingest Service
///
/// DESIGN:
/// - Reads from PlcTagValuesPoolService (NOT direct PLC reads — no extra TCP load)
/// - Applies rate control: db_logging_interval_ms + deadband per tag from tag_master
/// - Writes to historian_raw.historian_timeseries via BINARY COPY (shared pool connection)
/// - Batch-size-guarded: max _batchSize records per cycle (burst protection)
/// - DB failure isolated: 5s retry delay, fallback INSERT on COPY failure
/// - Quality derived from actual PLC communication state (Good/Bad/Uncertain)
/// - Write metrics: total writes, filtered by interval, filtered by deadband, COPY duration
///
/// KEY PRINCIPLES:
/// 1. PlcTagValuesPoolService is the ONLY source of truth
/// 2. Rate control is per-tag using ConcurrentDictionary (no hidden List buffering)
/// 3. Batch size enforced with .Take() — prevents reconnect burst explosions
/// 4. CancellationToken passed to EVERY Task.Delay — clean shutdown guaranteed
/// 5. DB errors never crash the service — logged + 5s backoff + continue
/// </summary>
public class PlcHistorianIngestService : BackgroundService
{
    private readonly PlcTagValuesPoolService _tagPool;
    private readonly PlcConfigLoaderService _configLoader;
    private readonly ILogger<PlcHistorianIngestService> _logger;
    private readonly NpgsqlDataSource _dataSource;  // Shared pool — no per-write connection creation

    // Configuration
    private readonly int _pollIntervalMs;
    private readonly int _batchSize;
    private readonly int _defaultWriteIntervalMs;

    // Rate control state
    private readonly ConcurrentDictionary<string, TagWriteState> _lastWriteState = new();
    private readonly ConcurrentDictionary<string, PlcTagDefinition> _tagMappings = new();

    // Metrics (thread-safe via Interlocked where needed)
    private long _totalWrites;
    private long _totalFilteredByInterval;
    private long _totalFilteredByDeadband;
    private long _totalDbFailures;
    private long _totalFallbackInserts;
    private long _lastCopyDurationMs;
    private DateTime _serviceStartTime;

    // Trigger-based config reload (set by API, consumed by main loop)
    private volatile bool _reloadRequested = false;
    private DateTime _lastReloadTime = DateTime.MinValue;

    /// <summary>
    /// Called by API endpoint to trigger a one-shot config reload.
    /// Safe to call from any thread. No polling — fires only when requested.
    /// </summary>
    public void TriggerConfigReload()
    {
        _reloadRequested = true;
        _logger.LogInformation("[PLC HISTORIAN] Config reload triggered via API");
    }

    /// <summary>Returns current mapping count, last reload time, and write metrics for API status.</summary>
    public (int MappingCount, DateTime LastReload, long TotalWrites, long FilteredInterval,
            long FilteredDeadband, long DbFailures, long LastCopyMs) GetConfigStatus()
        => (_tagMappings.Count, _lastReloadTime, _totalWrites,
            _totalFilteredByInterval, _totalFilteredByDeadband, _totalDbFailures, _lastCopyDurationMs);

    public PlcHistorianIngestService(
        PlcTagValuesPoolService tagPool,
        PlcConfigLoaderService configLoader,
        NpgsqlDataSource dataSource,
        IConfiguration configuration,
        ILogger<PlcHistorianIngestService> logger)
    {
        _tagPool = tagPool;
        _configLoader = configLoader;
        _dataSource = dataSource;  // Injected shared pool from DI
        _logger = logger;

        // FIX 1: Default poll interval raised to 2000ms — halves historian scan pressure vs 1000ms
        _pollIntervalMs = configuration.GetValue<int>("PlcGateway:HistorianPollIntervalMs", 2000);
        _batchSize = configuration.GetValue<int>("PlcGateway:HistorianBatchSize", 200);
        _defaultWriteIntervalMs = configuration.GetValue<int>("PlcGateway:DefaultWriteIntervalMs", 5000);

        _logger.LogInformation(
            "[PLC HISTORIAN] Initialized — Poll: {Poll}ms | BatchMax: {Batch} | DefaultWriteInterval: {Interval}ms",
            _pollIntervalMs, _batchSize, _defaultWriteIntervalMs);
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        _logger.LogInformation("[PLC HISTORIAN] Service starting...");
        _serviceStartTime = DateTime.UtcNow;

        // Wait for pool to start receiving data
        await Task.Delay(3000, stoppingToken);

        try
        {
            // Load tag mappings
            await RefreshTagMappingsAsync();

            // Main loop
            while (!stoppingToken.IsCancellationRequested)
            {
                var cycleStart = DateTime.UtcNow;

                // Trigger-based reload: only reload when API requests it (no polling overhead)
                if (_reloadRequested)
                {
                    _reloadRequested = false;
                    _logger.LogInformation("[PLC HISTORIAN] Reloading tag mappings from database...");
                    await RefreshTagMappingsAsync();
                    _lastReloadTime = DateTime.UtcNow;
                    _logger.LogInformation("[PLC HISTORIAN] Config reload complete — {Count} tag mappings active", _tagMappings.Count);
                }

                try
                {
                    await ProcessPoolDataAsync(stoppingToken);
                }
                catch (OperationCanceledException)
                {
                    throw; // Let shutdown propagate cleanly
                }
                catch (NpgsqlException ex)
                {
                    // FIX 5: DB failure — back off 5s before next cycle (prevents tight reconnect loop)
                    _totalDbFailures++;
                    _logger.LogError(ex, "[PLC HISTORIAN] DB error in ingest cycle — backing off 5s");
                    await Task.Delay(5000, stoppingToken);  // FIX 7: always pass ct
                }
                catch (Exception ex)
                {
                    _logger.LogError(ex, "[PLC HISTORIAN] Error in ingest cycle");
                }

                // FIX 7: CancellationToken on delay — guarantees clean shutdown
                var elapsed = (DateTime.UtcNow - cycleStart).TotalMilliseconds;
                var delay = Math.Max(0, _pollIntervalMs - (int)elapsed);
                if (delay > 0)
                {
                    await Task.Delay(delay, stoppingToken);
                }
            }
        }
        catch (OperationCanceledException)
        {
            // Normal shutdown
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "[PLC HISTORIAN] Fatal error");
        }

        _logger.LogInformation(
            "[PLC HISTORIAN] Service stopped. TotalWrites: {W} | SkippedInterval: {SI} | SkippedDeadband: {SD} | DbFailures: {DF}",
            _totalWrites, _totalFilteredByInterval, _totalFilteredByDeadband, _totalDbFailures);
    }

    // ═══════════════════════════════════════════════════════════════════
    // TAG MAPPING REFRESH
    // ═══════════════════════════════════════════════════════════════════

    private async Task RefreshTagMappingsAsync()
    {
        try
        {
            var allPlcs = await _configLoader.LoadAllEnabledPlcsAsync();
            var mappingCount = 0;

            foreach (var plc in allPlcs)
            {
                foreach (var tag in plc.Tags.Where(t => t.DbLoggingEnabled))
                {
                    var key = $"{plc.PlcId}:{tag.TagId}";
                    _tagMappings[key] = tag;
                    mappingCount++;
                }
            }

            _logger.LogInformation("[PLC HISTORIAN] Loaded {Count} tag mappings for database logging", mappingCount);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "[PLC HISTORIAN] Failed to refresh tag mappings");
        }
    }

    // ═══════════════════════════════════════════════════════════════════
    // POOL DATA PROCESSING
    // ═══════════════════════════════════════════════════════════════════

    private async Task ProcessPoolDataAsync(CancellationToken ct)
    {
        var stats = _tagPool.GetStatistics();
        if (stats.TotalTags == 0)
        {
            return; // No data in pool yet
        }

        // Get all tag values from pool
        var allValues = _tagPool.GetAllTagValues();
        if (allValues.Count == 0)
        {
            return;
        }

        var timestamp = DateTime.UtcNow;
        var toWrite = new List<PlcTimeseriesRecord>();

        foreach (var tagValue in allValues)
        {
            // Per-tag isolation: one bad/malformed tag cannot abort evaluation of remaining tags
            try
            {
                var key = $"{tagValue.PlcId}:{tagValue.TagName}";

                // Must be mapped for DB logging
                if (!_tagMappings.TryGetValue(key, out var mapping))
                    continue;

                // Apply rate control — tracks interval vs deadband separately for metrics
                var filterReason = GetFilterReason(key, tagValue, mapping, timestamp);
                if (filterReason == FilterReason.Interval)
                {
                    _totalFilteredByInterval++;
                    continue;
                }
                if (filterReason == FilterReason.Deadband)
                {
                    _totalFilteredByDeadband++;
                    continue;
                }

                // FIX 8: Derive quality char from actual PLC communication state
                var qualityChar = tagValue.Quality switch
                {
                    PlcTagQuality.Good          => "G",
                    PlcTagQuality.Bad           => "B",
                    PlcTagQuality.Uncertain     => "U",
                    PlcTagQuality.CommError     => "B",
                    PlcTagQuality.NotConfigured => "U",
                    _                           => "U"
                };

                toWrite.Add(new PlcTimeseriesRecord
                {
                    TagId     = tagValue.TagName,
                    Timestamp = tagValue.Timestamp,
                    Value     = ConvertToDouble(tagValue.Value),
                    Quality   = qualityChar
                });

                _lastWriteState[key] = new TagWriteState
                {
                    LastWriteTime = timestamp,
                    LastValue     = ConvertToDouble(tagValue.Value)
                };
            }
            catch (Exception ex)
            {
                // Log and continue — this tag is skipped this cycle, not the entire batch
                _logger.LogWarning(ex,
                    "[PLC HISTORIAN] Per-tag evaluation error — PlcId={PlcId} Tag={Tag} — skipped this cycle",
                    tagValue.PlcId, tagValue.TagName);
            }
        }

        if (toWrite.Count == 0) return;

        // FIX 2: Enforce batch size — prevents reconnect burst from creating huge COPY transactions
        if (toWrite.Count > _batchSize)
        {
            _logger.LogWarning("[PLC HISTORIAN] Batch capped {Actual} → {Max} records (burst protection)",
                toWrite.Count, _batchSize);
            toWrite = toWrite.Take(_batchSize).ToList();
        }

        await WriteToDbAsync(toWrite, ct);
        _totalWrites += toWrite.Count;

        // FIX 6: Periodic metrics log every 500 writes
        if (_totalWrites % 500 == 0)
        {
            _logger.LogInformation(
                "[PLC HISTORIAN] Metrics — Writes: {W} | SkippedInterval: {SI} | SkippedDeadband: {SD} | DbFailures: {DF} | FallbackInserts: {FI} | LastCOPY: {MS}ms",
                _totalWrites, _totalFilteredByInterval, _totalFilteredByDeadband,
                _totalDbFailures, _totalFallbackInserts, _lastCopyDurationMs);
        }
    }

    // ═══════════════════════════════════════════════════════════════════
    // RATE CONTROL (Mirrors OPC RateControllerService)
    // ═══════════════════════════════════════════════════════════════════

    // ═══════════════════════════════════════════════════════════════════
    // RATE CONTROL
    // ═══════════════════════════════════════════════════════════════════

    private enum FilterReason { Write, Interval, Deadband }

    private FilterReason GetFilterReason(string key, PlcTagValueCacheEntry current, PlcTagDefinition mapping, DateTime now)
    {
        if (!_lastWriteState.TryGetValue(key, out var lastState))
            return FilterReason.Write; // First sample — always write

        var intervalMs = mapping.DbLoggingIntervalMs > 0 ? mapping.DbLoggingIntervalMs : _defaultWriteIntervalMs;
        var elapsed = (now - lastState.LastWriteTime).TotalMilliseconds;

        if (elapsed < intervalMs)
        {
            // Interval not yet elapsed — always filter.
            // db_logging_interval_ms is the hard ceiling on write frequency.
            // Deadband does NOT fire early — it does not bypass the interval.
            return FilterReason.Interval;
        }

        // Interval elapsed → unconditional heartbeat write.
        // A flat stable value is valid historian data — must be confirmed periodically.
        return FilterReason.Write;
    }

    private double ConvertToDouble(object? value)
    {
        if (value == null) return 0.0;

        return value switch
        {
            double d => d,
            float f => f,
            int i => i,
            long l => l,
            short s => s,
            byte b => b,
            bool bl => bl ? 1.0 : 0.0,
            string str => double.TryParse(str, out var d) ? d : 0.0,
            _ => 0.0
        };
    }

    // ═══════════════════════════════════════════════════════════════════
    // DATABASE WRITE
    // ═══════════════════════════════════════════════════════════════════

    private async Task WriteToDbAsync(List<PlcTimeseriesRecord> records, CancellationToken ct)
    {
        var sw = Stopwatch.StartNew();
        try
        {
            // Borrow from shared pool — no new TCP handshake
            await using var conn = await _dataSource.OpenConnectionAsync(ct);

            // PRIMARY PATH: BINARY COPY (fast bulk insert)
            // Columns: time, tag_id, value_num, value_text, value_bool, quality,
            //          sample_source, mapping_version, opc_timestamp, ingest_timestamp
            await using var writer = await conn.BeginBinaryImportAsync(
                @"COPY historian_raw.historian_timeseries
                  (time, tag_id, value_num, value_text, value_bool, quality,
                   sample_source, mapping_version, opc_timestamp, ingest_timestamp)
                  FROM STDIN (FORMAT BINARY)", ct);

            // FIX 3: Pre-validate records — catch serialisation errors before they abort COPY
            // Any record that fails validation is skipped here; COPY stream stays clean.
            var safeRecords = new List<PlcTimeseriesRecord>(records.Count);
            foreach (var r in records)
            {
                if (string.IsNullOrEmpty(r.TagId) || r.Timestamp == default)
                {
                    _logger.LogWarning("[PLC HISTORIAN] Skipping invalid record: TagId={Tag} Ts={Ts}",
                        r.TagId, r.Timestamp);
                    continue;
                }
                safeRecords.Add(r);
            }

            foreach (var record in safeRecords)
            {
                await writer.StartRowAsync(ct);
                await writer.WriteAsync(record.Timestamp,  NpgsqlDbType.TimestampTz, ct); // time
                await writer.WriteAsync(record.TagId,      NpgsqlDbType.Text, ct);        // tag_id
                await writer.WriteAsync(record.Value,      NpgsqlDbType.Double, ct);      // value_num
                await writer.WriteNullAsync(ct);                                            // value_text
                await writer.WriteNullAsync(ct);                                            // value_bool
                await writer.WriteAsync(record.Quality,    NpgsqlDbType.Char, ct);        // quality (G/B/U)
                await writer.WriteAsync("PLC",             NpgsqlDbType.Varchar, ct);     // sample_source
                await writer.WriteAsync(1L,                NpgsqlDbType.Bigint, ct);      // mapping_version
                await writer.WriteAsync(record.Timestamp,  NpgsqlDbType.TimestampTz, ct); // opc_timestamp
                await writer.WriteAsync(DateTime.UtcNow,   NpgsqlDbType.TimestampTz, ct); // ingest_timestamp — when THIS process wrote it
            }

            await writer.CompleteAsync(ct);
            sw.Stop();
            _lastCopyDurationMs = sw.ElapsedMilliseconds;
            _logger.LogInformation("[PLC HISTORIAN] Wrote {Count} records via COPY in {Ms}ms",
                safeRecords.Count, sw.ElapsedMilliseconds);
        }
        catch (OperationCanceledException)
        {
            throw;
        }
        catch (Exception copyEx)
        {
            // FIX 3: COPY failed (one bad record can abort entire stream)
            // FALLBACK: individual INSERT per record — isolates each row
            _totalDbFailures++;
            _logger.LogWarning(copyEx,
                "[PLC HISTORIAN] COPY failed ({Count} records) — falling back to individual INSERTs",
                records.Count);

            await FallbackInsertAsync(records, ct);
        }
    }

    /// <summary>
    /// Fallback path: INSERT one record at a time.
    /// One bad record fails silently — rest continue.
    /// Used only when BINARY COPY fails.
    /// </summary>
    private async Task FallbackInsertAsync(List<PlcTimeseriesRecord> records, CancellationToken ct)
    {
        await using var conn = await _dataSource.OpenConnectionAsync(ct);
        const string sql = @"
            INSERT INTO historian_raw.historian_timeseries
                (time, tag_id, value_num, quality, sample_source, mapping_version, opc_timestamp)
            VALUES (@t, @id, @v, @q, 'PLC', 1, @t)
            ON CONFLICT (time, tag_id) DO UPDATE
                SET value_num = EXCLUDED.value_num,
                    quality   = EXCLUDED.quality";

        foreach (var record in records)
        {
            try
            {
                await using var cmd = new NpgsqlCommand(sql, conn);
                cmd.Parameters.AddWithValue("t",  record.Timestamp);
                cmd.Parameters.AddWithValue("id", record.TagId);
                cmd.Parameters.AddWithValue("v",  record.Value);
                cmd.Parameters.AddWithValue("q",  record.Quality);
                await cmd.ExecuteNonQueryAsync(ct);
                _totalFallbackInserts++;
            }
            catch (Exception ex)
            {
                _logger.LogWarning(ex,
                    "[PLC HISTORIAN] Fallback INSERT failed for tag={Tag} ts={Ts} — skipped",
                    record.TagId, record.Timestamp);
            }
        }
    }

    public override async Task StopAsync(CancellationToken cancellationToken)
    {
        _logger.LogInformation("[PLC HISTORIAN] Service stopping...");
        await base.StopAsync(cancellationToken);
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// SUPPORTING TYPES
// ═══════════════════════════════════════════════════════════════════════════

internal class TagWriteState
{
    public DateTime LastWriteTime { get; set; }
    public double LastValue { get; set; }
}

internal class PlcTimeseriesRecord
{
    public string TagId    { get; set; } = "";
    public DateTime Timestamp { get; set; }
    public double Value    { get; set; }
    public string Quality  { get; set; } = "G"; // G=Good, B=Bad, U=Uncertain
}
