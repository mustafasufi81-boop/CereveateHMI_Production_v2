namespace OpcDaWebBrowser.Services.Health;

/// <summary>
/// OPC DA connection health metrics (real-time acquisition)
/// </summary>
public record OpcHealth
{
    public string Status { get; init; } = "Unknown"; // Connected, Disconnected, Error
    public string? ServerName { get; init; }
    public int TagsConnected { get; init; }
    public int TagsActive { get; init; }
    public double UpdateRateMs { get; init; }
    public DateTime? LastUpdate { get; init; }
    public int ErrorCount { get; init; }
    public string? LastError { get; init; }
    public double HealthScore { get; init; } // 0-100
}

/// <summary>
/// Database writer (Historian ingest) health metrics
/// </summary>
public record DbWriterHealth
{
    public string Status { get; init; } = "Unknown"; // Running, Idle, Error, Disabled
    public long TotalRecordsWritten { get; init; }
    public long RecordsLastBatch { get; init; }
    public double WriteRatePerSecond { get; init; }
    public DateTime? LastWriteTime { get; init; }
    public int BatchQueueSize { get; init; }
    public int ErrorCount { get; init; }
    public string? LastError { get; init; }
    public int MappedTags { get; init; }
    public int ObservedTagsRecent { get; init; }
    public int MissingTags { get; init; }
    public int ObservedWindowSeconds { get; init; }
    public double HealthScore { get; init; } // 0-100
}

/// <summary>
/// Spool manager health metrics (offline data buffering)
/// </summary>
public record SpoolHealth
{
    public string Status { get; init; } = "Unknown"; // Idle, Replaying, Error
    public int FilesInSpool { get; init; }
    public long SpoolSizeMB { get; init; }
    public DateTime? LastReplayTime { get; init; }
    public long RecordsReplayed { get; init; }
    public int ReplayErrorCount { get; init; }
    public string? LastError { get; init; }
    public double HealthScore { get; init; } // 0-100
}

/// <summary>
/// Parquet archiver health metrics (data consolidation)
/// </summary>
public record ArchiverHealth
{
    public string Status { get; init; } = "Unknown"; // Running, Idle, Error, Disabled
    public int UnarchivedFilesCount { get; init; }
    public int ArchiveFilesCount { get; init; }
    public double CurrentArchiveSizeMB { get; init; }
    public DateTime? LastArchiveTime { get; init; }
    public TimeSpan? NextArchiveIn { get; init; }
    public int ErrorCount { get; init; }
    public string? LastError { get; init; }
    public double HealthScore { get; init; } // 0-100
}

/// <summary>
/// System resource health metrics (CPU, memory, disk)
/// </summary>
public record ResourceHealth
{
    public double CpuUsagePercent { get; init; }
    public long MemoryUsageMB { get; init; }
    public double MemoryUsagePercent { get; init; }
    public long DiskFreeMB { get; init; }
    public double DiskUsagePercent { get; init; }
    public int ThreadCount { get; init; }
    public DateTime SampleTime { get; init; }
    public double HealthScore { get; init; } // 0-100
}

/// <summary>
/// OPC STA Dispatcher metrics (lock-free snapshot from OpcStaDispatcher.GetMetrics())
/// </summary>
public record DispatcherHealth
{
    public int    ThreadId            { get; init; }
    public string Apartment           { get; init; } = "Unknown";
    public int    QueueDepth          { get; init; }
    public int    MaxQueueDepth       { get; init; }
    public long   OperationsProcessed { get; init; }
    public int    TimeoutCount        { get; init; }
    public int    RejectedCount       { get; init; }
    public string State               { get; init; } = "Unknown";
    public DateTime  LastStateChangeUtc { get; init; }
    public string?   StateReason        { get; init; }
    public DateTime? LastSuccess      { get; init; }
    public DateTime? LastHeartbeat    { get; init; }
    public string? LastError          { get; init; }
}

/// <summary>
/// Complete system health snapshot (single API response)
/// </summary>
public record SystemHealthSnapshot
{
    public DateTime Timestamp { get; init; } = DateTime.Now;
    public string OverallStatus { get; init; } = "Unknown"; // Healthy, Degraded, Critical, Offline
    public double OverallHealthScore { get; init; } // 0-100 (weighted average)
    
    public OpcHealth Opc { get; init; } = new();
    public DbWriterHealth DbWriter { get; init; } = new();
    public SpoolHealth Spool { get; init; } = new();
    public ArchiverHealth Archiver { get; init; } = new();
    public ResourceHealth Resources { get; init; } = new();
    public DispatcherHealth Dispatcher { get; init; } = new();
    
    // Quick status indicators
    public int ActiveAlerts { get; init; }
    public int WarningCount { get; init; }
    public int ErrorCount { get; init; }
}
