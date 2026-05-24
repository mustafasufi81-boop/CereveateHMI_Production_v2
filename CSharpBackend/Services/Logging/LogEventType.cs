namespace OpcDaWebBrowser.Services.Logging;

/// <summary>
/// Standardized log event types for industrial OPC/Historian systems
/// Used by Seq, Kibana, Grafana Loki, ELK, Splunk for log filtering
/// Matches AVEVA PI Server and Honeywell Experion event categorization
/// </summary>
public static class LogEventType
{
    // OPC DA Operations
    public const string OPC_CONNECT = "OPC_CONNECT";
    public const string OPC_CONNECT_ERROR = "OPC_CONNECT_ERROR";
    public const string OPC_DISCONNECT = "OPC_DISCONNECT";
    public const string OPC_READ_CYCLE = "OPC_READ_CYCLE";
    public const string OPC_READ_ERROR = "OPC_READ_ERROR";
    public const string OPC_READ_SLOW = "OPC_READ_SLOW";
    public const string OPC_DISCOVER = "OPC_DISCOVER";
    public const string OPC_TAG_ADD = "OPC_TAG_ADD";
    public const string OPC_TAG_REMOVE = "OPC_TAG_REMOVE";

    // Database Writer Operations
    public const string DB_WRITE_BATCH = "DB_WRITE_BATCH";
    public const string DB_WRITE_SUCCESS = "DB_WRITE_SUCCESS";
    public const string DB_WRITE_ERROR = "DB_WRITE_ERROR";
    public const string DB_CIRCUIT_OPEN = "DB_CIRCUIT_OPEN";
    public const string DB_CIRCUIT_CLOSE = "DB_CIRCUIT_CLOSE";
    public const string DB_CONNECT = "DB_CONNECT";
    public const string DB_DISCONNECT = "DB_DISCONNECT";

    // Historian Batch Pipeline
    public const string HIST_BATCH_QUEUED = "HIST_BATCH_QUEUED";
    public const string HIST_BATCH_FLUSH = "HIST_BATCH_FLUSH";
    public const string HIST_BATCH_SUMMARY = "HIST_BATCH_SUMMARY";
    public const string HIST_RATE_FILTER = "HIST_RATE_FILTER";
    public const string HIST_MAPPING = "HIST_MAPPING";

    // Spool Manager Operations
    public const string SPOOL_WRITE = "SPOOL_WRITE";
    public const string SPOOL_REPLAY = "SPOOL_REPLAY";
    public const string SPOOL_OVERFLOW = "SPOOL_OVERFLOW";
    public const string SPOOL_IDEMPOTENCY = "SPOOL_IDEMPOTENCY";

    // Archive Service Operations
    public const string ARCHIVE_CYCLE = "ARCHIVE_CYCLE";
    public const string ARCHIVE_FILE_ADD = "ARCHIVE_FILE_ADD";
    public const string ARCHIVE_COMPRESS = "ARCHIVE_COMPRESS";
    public const string ARCHIVE_SCHEMA_MISMATCH = "ARCHIVE_SCHEMA_MISMATCH";

    // User Actions (Audit Trail)
    public const string USER_LOGIN = "USER_LOGIN";
    public const string USER_LOGOUT = "USER_LOGOUT";
    public const string USER_ACTION = "USER_ACTION";
    public const string USER_CONFIG_CHANGE = "USER_CONFIG_CHANGE";
    public const string USER_TAG_MAPPING = "USER_TAG_MAPPING";

    // System Health & Monitoring
    public const string HEALTH_CHECK = "HEALTH_CHECK";
    public const string DISK_WARNING = "DISK_WARNING";
    public const string DISK_CRITICAL = "DISK_CRITICAL";
    public const string MEMORY_WARNING = "MEMORY_WARNING";
    public const string PERFORMANCE_WARNING = "PERFORMANCE_WARNING";

    // System Lifecycle
    public const string SYSTEM_STARTUP = "SYSTEM_STARTUP";
    public const string SYSTEM_SHUTDOWN = "SYSTEM_SHUTDOWN";
    public const string SERVICE_START = "SERVICE_START";
    public const string SERVICE_STOP = "SERVICE_STOP";
}
