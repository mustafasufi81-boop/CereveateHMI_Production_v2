namespace OpcDaWebBrowser.Services.HistorianIngest.Models;

/// <summary>
/// In-memory representation of a single tag's mapping configuration.
/// Loaded from historian_meta.tag_master.
/// Immutable after load for thread-safety.
/// </summary>
public sealed class TagMapping
{
    // ---------------------------
    // Identification
    // ---------------------------
    public string TagId { get; set; } = string.Empty;
    public string TagName { get; init; } = string.Empty;
    public string? Description { get; init; }

    // ---------------------------
    // Logical grouping (UI / menu)
    // ---------------------------
    public string? Plant { get; init; }
    public string? Area { get; init; }
    public string? Equipment { get; init; }

    // ---------------------------
    // Data type + conversion rules
    // ---------------------------
    public TagDataType DataType { get; init; }
    public string? EngUnit { get; init; }

    // ---------------------------
    // Logging configuration
    // ---------------------------
    public int DbLoggingIntervalMs { get; init; } = 1000;

    /// <summary>
    /// Numeric deadband.
    /// Used only for Double/Int tags.
    /// </summary>
    public double DeadbandValue { get; init; } = 0.0;

    /// <summary>
    /// Enable/disable historical logging.
    /// </summary>
    public bool Enabled { get; init; } = true;

    /// <summary>
    /// Destination hypertable name:
    /// Default: historian_raw.historian_timeseries
    /// </summary>
    public string DbTableName { get; init; } = "historian_raw.historian_timeseries";

    /// <summary>
    /// Auto-incremented on each tag update.
    /// Ensures consistency across pipeline stages.
    /// </summary>
    public int MappingVersion { get; init; } = 1;

    /// <summary>
    /// OPC server identity used when this tag was configured.
    /// Helps restore the correct source after restarts.
    /// </summary>
    public string? ServerProgId { get; init; }

    /// <summary>
    /// Hostname or machine where the OPC server resides.
    /// </summary>
    public string? ServerHost { get; init; }

    // ---------------------------
    // Audit
    // ---------------------------
    public DateTimeOffset ConfigUpdatedAt { get; init; }
    public DateTimeOffset CreatedAt { get; init; }
    public string? CreatedBy { get; init; }
}

/// <summary>
/// Supported data types for historian logging.
/// MUST match:
///  - OPC type conversion logic
///  - PostgreSQL schema fields
///  - UI dropdown values
/// </summary>
public enum TagDataType
{
    Double,
    Int,
    Bool,
    String
}
