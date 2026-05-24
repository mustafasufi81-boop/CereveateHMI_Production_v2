namespace OpcDaWebBrowser.Services.HistorianIngest.Models;

/// <summary>
/// Event stored in historian_admin.historian_events table.
/// Production-grade version with safe defaults,
/// null-protected fields, and strong typing.
/// </summary>
public sealed class HistorianEvent
{
    /// <summary>Server time when event was generated.</summary>
    public DateTimeOffset EventTime { get; set; } = DateTimeOffset.UtcNow;

    /// <summary>Event type (string identifier). Always required.</summary>
    public string EventType { get; set; } = string.Empty;

    /// <summary>Optional tag ID if event relates to a specific tag.</summary>
    public string? TagId { get; set; }

    /// <summary>Severity level.</summary>
    public EventSeverity Severity { get; set; } = EventSeverity.INFO;

    /// <summary>Short description of event.</summary>
    public string Message { get; set; } = string.Empty;

    /// <summary>Optional JSON details. Safe for JSONB in PostgreSQL.</summary>
    public Dictionary<string, object>? Details { get; set; }

    /// <summary>Which writer instance generated this event.</summary>
    public string? WriterName { get; set; }

    public HistorianEvent() { }

    /// <summary>
    /// Convenience constructor for quick logging.
    /// </summary>
    public HistorianEvent(string eventType, string message, EventSeverity severity = EventSeverity.INFO)
    {
        EventType = eventType;
        Message = message;
        Severity = severity;
    }
}

/// <summary>
/// Severity levels for historian events.
/// </summary>
public enum EventSeverity
{
    DEBUG = 1,
    INFO = 2,
    WARNING = 3,
    ERROR = 4,
    CRITICAL = 5
}

/// <summary>
/// Strongly typed event names for consistency.
/// </summary>
public static class HistorianEventTypes
{
    public const string UnmappedTag            = "unmapped_tag";
    public const string MappingConflict        = "mapping_conflict";
    public const string TypeMismatch           = "type_mismatch";

    public const string DbRetry                = "db_retry";
    public const string DbConnectionLost       = "db_connection_lost";
    public const string DbConnectionRestored   = "db_connection_restored";

    public const string SpoolWrite             = "spool_write";
    public const string SpoolReplay            = "spool_replay";
    public const string SpoolOverflow          = "spool_overflow";

    public const string MappingUpdate          = "mapping_update";
    public const string ExcelImport            = "excel_import";

    public const string WriterStart            = "writer_start";
    public const string WriterStop             = "writer_stop";
}
