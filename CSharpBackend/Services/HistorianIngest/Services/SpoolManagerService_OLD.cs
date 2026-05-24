using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using OpcDaWebBrowser.Services.HistorianIngest.Config;
using OpcDaWebBrowser.Services.HistorianIngest.Models;

namespace OpcDaWebBrowser.Services.HistorianIngest.Services;

/// <summary>
/// Manages disk-based spool for failed batches
/// Implements idempotent replay using file hashing
/// Pattern: .tmp → .ready → delete after success
/// </summary>
public class SpoolManagerService
{
    private readonly HistorianConfig _config;
    private readonly DbWriterService _dbWriter;
    private readonly ILogger<SpoolManagerService> _logger;
    
    private readonly string _spoolDirectory;
    private long _totalSpooled = 0;
    private long _totalReplayed = 0;

    public long TotalSpooled => _totalSpooled;
    public long TotalReplayed => _totalReplayed;

    public SpoolManagerService(
        HistorianConfig config,
        DbWriterService dbWriter,
        ILogger<SpoolManagerService> logger)
    {
        _config = config;
        _dbWriter = dbWriter;
        _logger = logger;
        
        _spoolDirectory = config.Spool.SpoolDirectory;
        
        // Ensure spool directory exists
        Directory.CreateDirectory(_spoolDirectory);
    }

    /// <summary>
    /// Write batch to spool (when DB unavailable)
    /// </summary>
    public async Task SpoolBatchAsync(SampleBatch batch, CancellationToken cancellationToken = default)
    {
        if (!_config.Spool.Enabled)
        {
            _logger.LogWarning("Spool disabled, batch will be lost!");
            return;
        }

        try
        {
            // Check spool size limit
            var currentSpoolSizeMB = GetSpoolSizeMB();
            if (currentSpoolSizeMB >= _config.Spool.MaxSpoolSizeMB)
            {
                _logger.LogError($"Spool size limit reached ({currentSpoolSizeMB}MB >= {_config.Spool.MaxSpoolSizeMB}MB), batch dropped!");
                return;
            }

            // Generate unique filename
            var timestamp = DateTimeOffset.Now.ToString("yyyyMMdd_HHmmss_fff");
            var tmpFileName = Path.Combine(_spoolDirectory, $"spool_{timestamp}_shard{batch.ShardIndex}.tmp");
            var readyFileName = tmpFileName.Replace(".tmp", ".ready");

            // Serialize batch
            var json = JsonSerializer.Serialize(batch, new JsonSerializerOptions 
            { 
                WriteIndented = false 
            });

            // Write to .tmp first
            await File.WriteAllTextAsync(tmpFileName, json, cancellationToken);

            // Atomic rename to .ready
            File.Move(tmpFileName, readyFileName, overwrite: true);

            Interlocked.Increment(ref _totalSpooled);
            _logger.LogWarning($"Batch spooled: {readyFileName} ({batch.Samples.Count} samples)");
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to spool batch");
        }
    }

    /// <summary>
    /// Replay all spooled batches (idempotent)
    /// </summary>
    public async Task ReplaySpoolAsync(CancellationToken cancellationToken = default)
    {
        if (!_config.Spool.Enabled || !_config.Spool.AutoReplay)
        {
            return;
        }

        _logger.LogInformation("Starting spool replay...");

        var readyFiles = Directory.GetFiles(_spoolDirectory, "*.ready")
            .OrderBy(f => f) // Process in chronological order
            .ToList();

        if (readyFiles.Count == 0)
        {
            _logger.LogInformation("No spooled files to replay");
            return;
        }

        _logger.LogInformation($"Found {readyFiles.Count} spooled files to replay");

        int successCount = 0;
        int failCount = 0;
        int skippedCount = 0;

        foreach (var filePath in readyFiles)
        {
            if (cancellationToken.IsCancellationRequested)
                break;

            try
            {
                // Calculate file hash for idempotency
                var fileHash = CalculateFileHash(filePath);

                // Check if already applied
                if (await IsSpoolAlreadyAppliedAsync(fileHash, cancellationToken))
                {
                    _logger.LogDebug($"Spool file already applied: {Path.GetFileName(filePath)}, deleting...");
                    File.Delete(filePath);
                    skippedCount++;
                    continue;
                }

                // Read and deserialize batch
                var json = await File.ReadAllTextAsync(filePath, cancellationToken);
                var batch = JsonSerializer.Deserialize<SampleBatch>(json);

                if (batch == null)
                {
                    _logger.LogError($"Failed to deserialize spool file: {filePath}");
                    failCount++;
                    continue;
                }

                // Try to write to database
                var success = await _dbWriter.WriteBatchAsync(batch, cancellationToken);

                if (success)
                {
                    // Mark as applied
                    await MarkSpoolAppliedAsync(fileHash, filePath, batch.Samples.Count, cancellationToken);

                    // Delete spool file
                    File.Delete(filePath);

                    Interlocked.Increment(ref _totalReplayed);
                    successCount++;
                    
                    _logger.LogInformation($"Replayed spool file: {Path.GetFileName(filePath)} ({batch.Samples.Count} samples)");
                }
                else
                {
                    failCount++;
                    _logger.LogWarning($"Failed to replay spool file: {filePath}, will retry later");
                }
            }
            catch (Exception ex)
            {
                failCount++;
                _logger.LogError(ex, $"Error replaying spool file: {filePath}");
            }
        }

        _logger.LogInformation($"Spool replay completed: {successCount} success, {failCount} failed, {skippedCount} skipped");

        // Log event
        await _dbWriter.LogEventAsync(new HistorianEvent
        {
            EventType = HistorianEventTypes.SpoolReplay,
            Severity = EventSeverity.INFO,
            Message = $"Spool replay completed: {successCount} success, {failCount} failed, {skippedCount} skipped",
            Details = new Dictionary<string, object>
            {
                ["success_count"] = successCount,
                ["fail_count"] = failCount,
                ["skipped_count"] = skippedCount
            },
            WriterName = _config.Writer.WriterName
        }, cancellationToken);
    }

    /// <summary>
    /// Check if spool file already applied (idempotency)
    /// </summary>
    private async Task<bool> IsSpoolAlreadyAppliedAsync(string fileHash, CancellationToken cancellationToken)
    {
        using var connection = new Npgsql.NpgsqlConnection(_config.Database.ConnectionString);
        await connection.OpenAsync(cancellationToken);

        var sql = "SELECT COUNT(*) FROM historian_admin.spool_applied WHERE file_hash = @file_hash";
        using var cmd = new Npgsql.NpgsqlCommand(sql, connection);
        cmd.Parameters.AddWithValue("file_hash", fileHash);

        var count = (long)(await cmd.ExecuteScalarAsync(cancellationToken) ?? 0);
        return count > 0;
    }

    /// <summary>
    /// Mark spool file as applied
    /// </summary>
    private async Task MarkSpoolAppliedAsync(string fileHash, string filePath, int recordCount, CancellationToken cancellationToken)
    {
        using var connection = new Npgsql.NpgsqlConnection(_config.Database.ConnectionString);
        await connection.OpenAsync(cancellationToken);

        var sql = @"
            INSERT INTO historian_admin.spool_applied 
                (file_hash, file_path, applied_at, record_count, writer_name)
            VALUES 
                (@file_hash, @file_path, NOW(), @record_count, @writer_name)
            ON CONFLICT (file_hash) DO NOTHING";

        using var cmd = new Npgsql.NpgsqlCommand(sql, connection);
        cmd.Parameters.AddWithValue("file_hash", fileHash);
        cmd.Parameters.AddWithValue("file_path", filePath);
        cmd.Parameters.AddWithValue("record_count", recordCount);
        cmd.Parameters.AddWithValue("writer_name", _config.Writer.WriterName);

        await cmd.ExecuteNonQueryAsync(cancellationToken);
    }

    /// <summary>
    /// Calculate SHA256 hash of file
    /// </summary>
    private string CalculateFileHash(string filePath)
    {
        using var sha256 = SHA256.Create();
        using var stream = File.OpenRead(filePath);
        var hashBytes = sha256.ComputeHash(stream);
        return BitConverter.ToString(hashBytes).Replace("-", "").ToLowerInvariant();
    }

    /// <summary>
    /// Get current spool directory size in MB
    /// </summary>
    public long GetSpoolSizeMB()
    {
        try
        {
            var files = Directory.GetFiles(_spoolDirectory, "*.ready");
            long totalBytes = files.Sum(f => new FileInfo(f).Length);
            return totalBytes / (1024 * 1024);
        }
        catch
        {
            return 0;
        }
    }

    /// <summary>
    /// Get spool file count
    /// </summary>
    public int GetSpoolFileCount()
    {
        try
        {
            return Directory.GetFiles(_spoolDirectory, "*.ready").Length;
        }
        catch
        {
            return 0;
        }
    }
}
