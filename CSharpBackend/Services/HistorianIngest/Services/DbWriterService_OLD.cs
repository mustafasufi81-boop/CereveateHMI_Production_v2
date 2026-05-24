using Npgsql;
using NpgsqlTypes;
using OpcDaWebBrowser.Services.HistorianIngest.Config;
using OpcDaWebBrowser.Services.HistorianIngest.Models;

namespace OpcDaWebBrowser.Services.HistorianIngest.Services;

/// <summary>
/// High-performance database writer using PostgreSQL COPY binary format
/// Handles checkpoint persistence and latest_values update
/// </summary>
public class DbWriterService_OLD
{
    private readonly HistorianConfig _config;
    private readonly ILogger<DbWriterService> _logger;
    
    private long _totalRowsWritten = 0;
    private long _totalBatchesWritten = 0;
    private long _totalErrors = 0;

    public long TotalRowsWritten => _totalRowsWritten;
    public long TotalBatchesWritten => _totalBatchesWritten;
    public long TotalErrors => _totalErrors;

    public DbWriterService(
        HistorianConfig config,
        ILogger<DbWriterService> logger)
    {
        _config = config;
        _logger = logger;
    }

    /// <summary>
    /// Write batch to database using COPY binary
    /// </summary>
    public async Task<bool> WriteBatchAsync(SampleBatch batch, CancellationToken cancellationToken = default)
    {
        using var connection = new NpgsqlConnection(_config.Database.ConnectionString);
        
        try
        {
            await connection.OpenAsync(cancellationToken);

            using var transaction = await connection.BeginTransactionAsync(cancellationToken);

            // COPY data to timeseries table
            var rowsWritten = await WriteSamplesBinaryCopyAsync(connection, batch, cancellationToken);

            // Update latest values
            await UpdateLatestValuesAsync(connection, batch, cancellationToken);

            await transaction.CommitAsync(cancellationToken);

            Interlocked.Add(ref _totalRowsWritten, rowsWritten);
            Interlocked.Increment(ref _totalBatchesWritten);

            _logger.LogDebug($"Batch written: {rowsWritten} rows, shard {batch.ShardIndex}");

            return true;
        }
        catch (Exception ex)
        {
            Interlocked.Increment(ref _totalErrors);
            _logger.LogError(ex, $"Failed to write batch (shard {batch.ShardIndex}, {batch.Samples.Count} samples)");
            return false;
        }
    }

    /// <summary>
    /// Write samples using PostgreSQL COPY binary (fastest method)
    /// </summary>
    private async Task<int> WriteSamplesBinaryCopyAsync(
        NpgsqlConnection connection, 
        SampleBatch batch, 
        CancellationToken cancellationToken)
    {
        var copyCommand = $@"
            COPY {batch.TableName} 
            (time, tag_id, value_num, value_text, value_bool, 
             quality, sample_source, mapping_version)
            FROM STDIN (FORMAT BINARY)";

        await using var writer = await connection.BeginBinaryImportAsync(copyCommand, cancellationToken);

        foreach (var sample in batch.Samples)
        {
            await writer.StartRowAsync(cancellationToken);
            
            await writer.WriteAsync(sample.Time.UtcDateTime, NpgsqlDbType.TimestampTz, cancellationToken);
            await writer.WriteAsync(sample.TagId, NpgsqlDbType.Text, cancellationToken);
            await writer.WriteAsync(sample.ValueNum, NpgsqlDbType.Double, cancellationToken);
            await writer.WriteAsync(sample.ValueText, NpgsqlDbType.Text, cancellationToken);
            await writer.WriteAsync(sample.ValueBool, NpgsqlDbType.Boolean, cancellationToken);
            await writer.WriteAsync(sample.Quality, NpgsqlDbType.Char, cancellationToken);
            await writer.WriteAsync(sample.Source, NpgsqlDbType.Char, cancellationToken); // CHAR(3)
            await writer.WriteAsync((long)sample.MappingVersion, NpgsqlDbType.Bigint, cancellationToken); // BIGINT
        }

        var rowsWritten = await writer.CompleteAsync(cancellationToken);
        return (int)rowsWritten;
    }

    /// <summary>
    /// Update latest values table using stored procedure
    /// </summary>
    private async Task UpdateLatestValuesAsync(
        NpgsqlConnection connection, 
        SampleBatch batch, 
        CancellationToken cancellationToken)
    {
        var tagIds = new List<string>();
        var times = new List<DateTime>();
        var valuesNum = new List<double?>();
        var valuesText = new List<string?>();
        var valuesBool = new List<bool?>();
        var qualities = new List<string>();
        var sources = new List<string>();

        // Group by tag_id and take latest
        var latestByTag = batch.Samples
            .GroupBy(s => s.TagId)
            .Select(g => g.OrderByDescending(s => s.Time).First());

        foreach (var sample in latestByTag)
        {
            tagIds.Add(sample.TagId);
            times.Add(sample.Time.UtcDateTime);
            valuesNum.Add(sample.ValueNum);
            valuesBool.Add(sample.ValueBool);
            valuesText.Add(sample.ValueText);
            qualities.Add(sample.Quality);
            sources.Add(sample.Source);
        }

        if (tagIds.Count == 0) return;

        // Convert qualities to TEXT array (production schema uses TEXT not CHAR(1))
        var qualitiesText = qualities.Select(q => q?.ToString() ?? "U").ToList();
        
        // Convert mapping versions to BIGINT array
        var mappingVersions = latestByTag.Select(s => (long)s.MappingVersion).ToList();
        
        using var cmd = new NpgsqlCommand("SELECT update_latest_values_batch($1, $2, $3, $4, $5, $6, $7)", connection);
        cmd.Parameters.AddWithValue(tagIds.ToArray());
        cmd.Parameters.AddWithValue(times.ToArray());
        cmd.Parameters.AddWithValue(valuesNum.ToArray());
        cmd.Parameters.AddWithValue(valuesText.ToArray());
        cmd.Parameters.AddWithValue(valuesBool.ToArray());
        cmd.Parameters.AddWithValue(qualitiesText.ToArray());
        cmd.Parameters.AddWithValue(mappingVersions.ToArray());

        await cmd.ExecuteNonQueryAsync(cancellationToken);
    }

    /// <summary>
    /// Save checkpoint
    /// </summary>
    public async Task SaveCheckpointAsync(WriterCheckpoint checkpoint, CancellationToken cancellationToken = default)
    {
        using var connection = new NpgsqlConnection(_config.Database.ConnectionString);
        await connection.OpenAsync(cancellationToken);

        var sql = @"
            INSERT INTO historian_admin.writer_checkpoint 
                (writer_name, last_processed_at, last_mapping_version, last_wal_lsn, info, updated_at)
            VALUES 
                (@writer_name, @last_processed_at, @last_mapping_version, @last_wal_lsn, @info::jsonb, NOW())
            ON CONFLICT (writer_name) DO UPDATE SET
                last_processed_at = EXCLUDED.last_processed_at,
                last_mapping_version = EXCLUDED.last_mapping_version,
                last_wal_lsn = EXCLUDED.last_wal_lsn,
                info = EXCLUDED.info,
                updated_at = NOW()";

        using var cmd = new NpgsqlCommand(sql, connection);
        cmd.Parameters.AddWithValue("writer_name", checkpoint.WriterName);
        cmd.Parameters.AddWithValue("last_processed_at", checkpoint.LastProcessedAt.UtcDateTime);
        cmd.Parameters.AddWithValue("last_mapping_version", (object?)checkpoint.LastMappingVersion ?? DBNull.Value);
        cmd.Parameters.AddWithValue("last_wal_lsn", (object?)checkpoint.LastWalLsn ?? DBNull.Value);
        cmd.Parameters.AddWithValue("info", checkpoint.Info != null 
            ? System.Text.Json.JsonSerializer.Serialize(checkpoint.Info) 
            : DBNull.Value);

        await cmd.ExecuteNonQueryAsync(cancellationToken);
        
        _logger.LogDebug($"Checkpoint saved for {checkpoint.WriterName}");
    }

    /// <summary>
    /// Load checkpoint
    /// </summary>
    public async Task<WriterCheckpoint?> LoadCheckpointAsync(string writerName, CancellationToken cancellationToken = default)
    {
        using var connection = new NpgsqlConnection(_config.Database.ConnectionString);
        await connection.OpenAsync(cancellationToken);

        var sql = @"
            SELECT writer_name, last_processed_at, last_mapping_version, last_wal_lsn, info, updated_at
            FROM historian_admin.writer_checkpoint
            WHERE writer_name = @writer_name";

        using var cmd = new NpgsqlCommand(sql, connection);
        cmd.Parameters.AddWithValue("writer_name", writerName);

        using var reader = await cmd.ExecuteReaderAsync(cancellationToken);
        if (await reader.ReadAsync(cancellationToken))
        {
            return new WriterCheckpoint
            {
                WriterName = reader.GetString(0),
                LastProcessedAt = reader.GetFieldValue<DateTimeOffset>(1),
                LastMappingVersion = reader.IsDBNull(2) ? null : reader.GetInt32(2),
                LastWalLsn = reader.IsDBNull(3) ? null : reader.GetString(3),
                Info = reader.IsDBNull(4) ? null : System.Text.Json.JsonSerializer.Deserialize<Dictionary<string, object>>(reader.GetString(4)),
                UpdatedAt = reader.GetFieldValue<DateTimeOffset>(5)
            };
        }

        return null;
    }

    /// <summary>
    /// Log historian event
    /// </summary>
    public async Task LogEventAsync(HistorianEvent evt, CancellationToken cancellationToken = default)
    {
        using var connection = new NpgsqlConnection(_config.Database.ConnectionString);
        await connection.OpenAsync(cancellationToken);

        var sql = @"
            INSERT INTO historian_admin.historian_events 
                (event_time, event_type, tag_id, message, details, writer_name)
            VALUES 
                (@event_time, @event_type, @tag_id, @message, @details::jsonb, @writer_name)";

        using var cmd = new NpgsqlCommand(sql, connection);
        cmd.Parameters.AddWithValue("event_time", evt.EventTime.UtcDateTime);
        cmd.Parameters.AddWithValue("event_type", evt.EventType);
        cmd.Parameters.AddWithValue("tag_id", (object?)evt.TagId ?? DBNull.Value);
        cmd.Parameters.AddWithValue("message", evt.Message);
        cmd.Parameters.AddWithValue("details", evt.Details != null 
            ? System.Text.Json.JsonSerializer.Serialize(evt.Details) 
            : DBNull.Value);
        cmd.Parameters.AddWithValue("writer_name", (object?)evt.WriterName ?? DBNull.Value);

        await cmd.ExecuteNonQueryAsync(cancellationToken);
    }

    /// <summary>
    /// Check database health
    /// </summary>
    public async Task<bool> CheckHealthAsync(CancellationToken cancellationToken = default)
    {
        try
        {
            using var connection = new NpgsqlConnection(_config.Database.ConnectionString);
            await connection.OpenAsync(cancellationToken);
            
            using var cmd = new NpgsqlCommand("SELECT 1", connection);
            await cmd.ExecuteScalarAsync(cancellationToken);
            
            return true;
        }
        catch
        {
            return false;
        }
    }
}
