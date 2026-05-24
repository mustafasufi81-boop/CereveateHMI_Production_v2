namespace OpcDaWebBrowser.Services.HistorianIngest.Models;

/// <summary>
/// Fully mapped historian sample (post-mapping, pre-batching)
/// Ready for COPY BINARY ingestion to TimescaleDB.
/// </summary>
public sealed class MappedSample
{
    /// <summary>
    /// Timestamp when the sample was captured (ALWAYS UTC)
    /// Poll timestamp for historian (respects DbLoggingIntervalMs)
    /// </summary>
    public DateTimeOffset Time { get; set; } = DateTimeOffset.UtcNow;

    /// <summary>
    /// Original OPC server timestamp (for audit trail)
    /// Preserved from OPC DA server, stored separately from poll timestamp
    /// </summary>
    public DateTimeOffset? OpcTimestamp { get; set; }

    /// <summary>
    /// Unique tag identifier (FK to tag_master)
    /// </summary>
    public string TagId { get; set; } = string.Empty;

    /// <summary>
    /// Numeric value (FLOAT8) if applicable
    /// </summary>
    public double? ValueNum { get; set; }

    /// <summary>
    /// Boolean value if applicable
    /// </summary>
    public bool? ValueBool { get; set; }

    /// <summary>
    /// String value if applicable
    /// </summary>
    public string? ValueText { get; set; }

    /// <summary>
    /// Quality code (CHAR): G=Good, B=Bad, U=Uncertain, or extended statuses
    /// </summary>
    public string Quality { get; set; } = "G";

    /// <summary>
    /// Sample source code (CHAR(3)): OPC, HIS, EVT etc.
    /// </summary>
    public string Source { get; set; } = "OPC";

    /// <summary>
    /// Mapping version for reprocessing, schema evolution, and replay
    /// </summary>
    public int MappingVersion { get; set; } = 1;

    /// <summary>
    /// Database table to write to (dynamic routing)
    /// </summary>
    public string DbTableName { get; set; } = "historian_raw.historian_timeseries";

    // Additional fields populated from TagMapping for full database schema

    /// <summary>
    /// Plant name (from tag mapping)
    /// </summary>
    public string? PlantName { get; set; }

    /// <summary>
    /// Asset name (from tag mapping)
    /// </summary>
    public string? AssetName { get; set; }

    /// <summary>
    /// Subsystem name (from tag mapping)
    /// </summary>
    public string? SubsystemName { get; set; }

    /// <summary>
    /// Unit of measure (from tag mapping)
    /// </summary>
    public string? UnitOfMeasure { get; set; }

    /// <summary>
    /// Tag description (from tag mapping)
    /// </summary>
    public string? Description { get; set; }
}
