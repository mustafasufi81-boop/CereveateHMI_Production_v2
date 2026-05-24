namespace OpcDaWebBrowser.Services.HistorianIngest.Models;

/// <summary>
/// Raw incoming sample from OPC (pre-mapping, pre-filtering)
/// Lightweight carrier object optimized for rate control.
/// </summary>
public sealed class RawSample
{
    /// <summary>
    /// Timestamp when the value was READ (always UTC).
    /// Poll timestamp for historian (respects DbLoggingIntervalMs).
    /// </summary>
    public DateTimeOffset Time { get; set; } = DateTimeOffset.UtcNow;

    /// <summary>
    /// Original OPC server timestamp (for audit trail).
    /// Preserved from OPC DA server, may differ from poll timestamp.
    /// </summary>
    public DateTimeOffset? OpcTimestamp { get; set; }

    /// <summary>
    /// Tag ID exactly as received from OPC ItemID.
    /// </summary>
    public string TagId { get; set; } = string.Empty;

    /// <summary>
    /// Raw OPC value (untyped). Will be converted during mapping.
    /// </summary>
    public object? RawValue { get; set; }

    /// <summary>
    /// OPC quality flag:
    /// G = Good  
    /// B = Bad  
    /// U = Uncertain  
    /// (Or extended Quality flags)
    /// </summary>
    public string Quality { get; set; } = "G";

    /// <summary>
    /// Data source: OPC event, OPC poll, HISTORIAN replay, etc.
    /// 3-char format mandatory for DB: "OPC", "POL", "HIS"
    /// </summary>
    public string Source { get; set; } = "OPC";
}
