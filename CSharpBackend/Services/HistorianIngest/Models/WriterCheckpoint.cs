namespace OpcDaWebBrowser.Services.HistorianIngest.Models;

/// <summary>
/// Durable checkpoint stored in historian_admin.writer_checkpoint.
/// Used for clean restart and writer crash recovery.
/// </summary>
public sealed class WriterCheckpoint
{
    /// <summary>
    /// Writer identity. (Primary key in DB)
    /// </summary>
    public string WriterName { get; init; } = string.Empty;

    /// <summary>
    /// Last time the writer finished a successful batch write.
    /// Used to resume from correct position after restart.
    /// </summary>
    public DateTimeOffset LastProcessedAt { get; init; }

    /// <summary>
    /// Latest known tag mapping version at the time of checkpoint.
    /// Used to detect schema or mapping updates mid-run.
    /// </summary>
    public int? LastMappingVersion { get; init; }

    /// <summary>
    /// Last WAL LSN previously committed (optional).
    /// Mostly for future replication or WAL-based recovery extension.
    /// </summary>
    public string? LastWalLsn { get; init; }

    /// <summary>
    /// JSONB diagnostic info from the writer:
    /// {
    ///   "opc_received": ...,
    ///   "batches_written": ...,
    ///   "spool_files": ...
    /// }
    ///
    /// Useful for monitoring, debugging, and health checks.
    /// </summary>
    public Dictionary<string, object>? Info { get; init; }

    /// <summary>
    /// When this checkpoint row was last updated.
    /// Auto-set in DB by UPDATE statement.
    /// </summary>
    public DateTimeOffset UpdatedAt { get; init; }
}
