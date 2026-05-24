namespace OpcDaWebBrowser.Services.AlarmEvaluation.Models;

/// <summary>
/// Mutable in-memory runtime state for one tag's interlock.
/// Single writer (InterlockEvaluationService evaluation loop) — no external mutation.
/// Loaded from DB on startup and refreshed every RuntimeStateRefreshIntervalSeconds.
/// </summary>
public sealed class InterlockRuntimeState
{
    /// <summary>OPC tag identifier.</summary>
    public required string TagId { get; init; }

    /// <summary>
    /// Current interlock state as stored in historian_raw.interlock_state_tracking.
    /// Null = never evaluated yet (first cycle will force an INSERT).
    /// Valid values: SATISFIED, VIOLATED, BYPASSED, DISABLED.
    /// </summary>
    public string? CurrentState { get; set; }

    /// <summary>
    /// The interlock_event_id PK of the most recent row written for this tag.
    /// Used only for diagnostics / logging — each transition is a new INSERT row.
    /// </summary>
    public long? LastEventId { get; set; }

    /// <summary>UTC timestamp when the current state was first entered.</summary>
    public DateTimeOffset? StateEnteredAt { get; set; }

    /// <summary>
    /// The interlock_type from tag_master (PERMISSIVE, CONDITIONAL, SEQUENTIAL, PROTECTIVE).
    /// Cached here so we do not hit the setpoint cache on every evaluation cycle.
    /// </summary>
    public string InterlockType { get; set; } = string.Empty;

    /// <summary>
    /// Affected equipment label from tag_master for display in MQTT payloads.
    /// </summary>
    public string? AffectedEquipment { get; set; }
}
