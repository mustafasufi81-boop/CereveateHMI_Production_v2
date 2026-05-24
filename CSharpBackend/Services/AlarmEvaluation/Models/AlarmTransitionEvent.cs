namespace OpcDaWebBrowser.Services.AlarmEvaluation.Models;

/// <summary>
/// Immutable record of one alarm state transition.
/// Emitted by AlarmStateManager after every successful state change + DB write.
/// Used by AlarmEvaluationService for MQTT publishing and by the diagnostics API.
/// </summary>
public sealed record AlarmTransitionEvent
{
    public required string        AlarmKey      { get; init; }
    public required string        TagId         { get; init; }
    public required AlarmLevel    Level         { get; init; }
    public required AlarmState4   ToState       { get; init; }
    public required Guid          OccurrenceId  { get; init; }
    public required int           InstanceSeq   { get; init; }
    public required long          EventId       { get; init; }
    public required DateTimeOffset Timestamp    { get; init; }
    public double?                Value         { get; init; }
    public double?                SetpointValue { get; init; }

    /// <summary>Null for system-generated transitions; the operator's name for ACK actions.</summary>
    public string? Operator { get; init; }

    /// <summary>
    /// Global monotonic sequence number from historian_raw.alarm_transition_seq.
    /// Enables HMI to detect missed transitions on WebSocket reconnect (Issue 1).
    /// </summary>
    public long TransitionSeq { get; init; }

    /// <summary>Human-readable event type string derived from ToState (Issue 7).</summary>
    public string EventType => ToState switch
    {
        AlarmState4.ActiveUnack => "ALARM_RAISED",
        AlarmState4.ActiveAck   => "ALARM_ACKNOWLEDGED",
        AlarmState4.RtnUnack    => "ALARM_RTN",
        AlarmState4.None        => "ALARM_CLEARED",
        _                       => "ALARM_UNKNOWN",
    };
}
