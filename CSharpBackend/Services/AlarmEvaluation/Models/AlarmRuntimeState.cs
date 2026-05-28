namespace OpcDaWebBrowser.Services.AlarmEvaluation.Models;

/// <summary>
/// Identifies which data pool a tag's live value comes from.
/// Set at raise-time from the evaluation cycle, which already knows the source.
/// Used by AlarmStateManager to do a DIRECTED (non-blind) pool lookup in guards.
/// </summary>
public enum TagSource
{
    /// <summary>Source unknown — guards will try both pools (safe fallback).</summary>
    Unknown = 0,
    /// <summary>Tag is served by OPC DA — TagValuesPoolService.</summary>
    OpcDa = 1,
    /// <summary>Tag is served by a PLC worker — PlcTagValuesPoolService.</summary>
    Plc = 2,
}

/// <summary>
/// ISA-18.2 4-state alarm lifecycle (Phase 1).
/// CLEARED is terminal — when CLEARED the AlarmRuntimeState is removed from memory and the
/// alarm_active row is deleted from the DB. No 'Cleared' enum value needed here.
/// </summary>
public enum AlarmState4
{
    /// <summary>Tag is in normal range — no alarm active for this key.</summary>
    None = 0,

    /// <summary>Alarm condition is active. Operator has not acknowledged.</summary>
    ActiveUnack = 1,

    /// <summary>Alarm condition is active. Operator has acknowledged.</summary>
    ActiveAck = 2,

    /// <summary>Value has returned to normal. Operator has not yet acknowledged the return.</summary>
    RtnUnack = 3,
}

/// <summary>
/// Ordered alarm severity levels.
/// Numeric ordering enables higher/lower comparisons: HighHigh > High > None.
/// </summary>
public enum AlarmLevel
{
    None     = 0,
    Low      = 1,
    LowLow   = 2,
    High     = 3,
    HighHigh = 4,
}

/// <summary>
/// In-memory runtime state for ONE alarm instance, keyed by alarm_key = "{tag_id}:{level}".
/// AlarmStateManager is the ONLY writer of this record.
/// Mutable fields (State, AckAt, AckBy, RtnAt) are updated inside the per-key SemaphoreSlim lock.
/// </summary>
public sealed class AlarmRuntimeState
{
    /// <summary>Composite key — "{tag_id}:{level}" e.g. "Random.Real4:High"</summary>
    public required string AlarmKey { get; init; }

    public required string TagId { get; init; }
    public required AlarmLevel Level { get; init; }

    /// <summary>
    /// Which data pool this tag's live value comes from.
    /// Populated by AlarmEvaluationService.RaiseAsync() so that state-transition guards
    /// (AcknowledgeAsync, ClearAsync, MarkRtnAsync) can do a directed pool lookup
    /// instead of a blind dual-pool search.
    /// </summary>
    public TagSource Source { get; set; } = TagSource.Unknown;

    /// <summary>Current ISA-18.2 4-state value.</summary>
    public AlarmState4 State { get; set; } = AlarmState4.None;

    /// <summary>Unique UUID per alarm occurrence. Reset on each fresh raise.</summary>
    public Guid OccurrenceId { get; set; }

    /// <summary>Monotonically incrementing instance count for this tag+level pair.</summary>
    public int InstanceSeq { get; set; }

    /// <summary>event_id from historian_raw.historian_events for the RAISE transition of this occurrence.</summary>
    public long? CurrentEventId { get; set; }

    /// <summary>Global transition_seq from historian_raw.alarm_transition_seq at last state change.</summary>
    public long TransitionSeq { get; set; }

    /// <summary>Number of times this alarm key has been raised in the current chatter window.</summary>
    public int ChatterCount { get; set; }

    /// <summary>Start of the current chatter detection window.</summary>
    public DateTime ChatterWindowStart { get; set; } = DateTime.UtcNow;

    public DateTimeOffset  RaisedAt      { get; set; }
    public double?         RaisedValue   { get; set; }
    public double?         SetpointValue { get; set; }
    public DateTimeOffset? AckAt         { get; set; }
    public string?         AckBy         { get; set; }
    public DateTimeOffset? RtnAt         { get; set; }

    /// <summary>Builds the composite alarm key for a tag + level combination.</summary>
    public static string BuildKey(string tagId, AlarmLevel level) => $"{tagId}:{level}";
}
