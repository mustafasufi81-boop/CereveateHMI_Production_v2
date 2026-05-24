namespace OpcDaWebBrowser.Services.HistorianIngest.Config;

/// <summary>
/// Configuration for Historian Ingest System
/// </summary>
public class HistorianConfig
{
    public DatabaseConfig Database { get; set; } = new();
    public WriterConfig Writer { get; set; } = new();
    public SpoolConfig Spool { get; set; } = new();
    public BatchConfig Batch { get; set; } = new();
    public RateControlConfig RateControl { get; set; } = new();
}

public class DatabaseConfig
{
    public string ConnectionString { get; set; } = string.Empty;
    public int CommandTimeout { get; set; } = 30;
    public int MaxRetries { get; set; } = 3;
    public int RetryDelayMs { get; set; } = 1000;
    public bool UseConnectionPooling { get; set; } = true;
    public int MaxPoolSize { get; set; } = 100;
    /// <summary>
    /// Fallback polling interval (seconds) to re-read tag_master from DB.
    /// pg_notify fires instantly on any UPDATE; this timer is the safety net.
    /// Default 30s for dev; set to 300-600 for production.
    /// </summary>
    public int MappingRefreshIntervalSeconds { get; set; } = 30;
}

public class WriterConfig
{
    public string WriterName { get; set; } = "HistorianWriter01";
    public int ShardCount { get; set; } = 8;
    public bool EnableCheckpointing { get; set; } = true;
    public int CheckpointIntervalSeconds { get; set; } = 30;
}

public class SpoolConfig
{
    public bool Enabled { get; set; } = true;
    public string SpoolDirectory { get; set; } = "D:\\HistorianSpool";
    public int MaxSpoolSizeMB { get; set; } = 10240; // 10GB
    public int ReplayIntervalSeconds { get; set; } = 60;
    public bool AutoReplay { get; set; } = true;
}

public class BatchConfig
{
    public int MaxRows { get; set; } = 10000;
    public int MaxBytes { get; set; } = 5242880; // 5MB
    public int MaxWaitMs { get; set; } = 500; // CRITICAL: Must be < minimum tag interval (1000ms)
    public bool UseBinaryCopy { get; set; } = true;
}

public class RateControlConfig
{
    public bool Enabled { get; set; } = true;
    public bool UseChangeDetection { get; set; } = true;
    public double DefaultDeadband { get; set; } = 0.1; // FIXED: 0.1% default for analog tags
    public int MinIntervalMs { get; set; } = 1000;
    public int MaxIntervalMs { get; set; } = 60000;
}
