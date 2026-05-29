namespace OpcDaWebBrowser.Services.AlarmEvaluation.Models;

/// <summary>
/// Immutable alarm setpoint configuration for a single tag.
/// Loaded from historian_meta.tag_master. Never written to.
/// Replaces any hardcoded threshold values in evaluation logic.
/// </summary>
public sealed class AlarmSetpoint
{
    /// <summary>OPC tag identifier — primary key in tag_master.</summary>
    public required string TagId { get; init; }

    /// <summary>High-High limit (alarm_hh_limit). Null = not configured for this tag.</summary>
    public double? HhLimit { get; init; }

    /// <summary>High limit (alarm_h_limit). Null = not configured.</summary>
    public double? HLimit { get; init; }

    /// <summary>Low limit (alarm_l_limit). Null = not configured.</summary>
    public double? LLimit { get; init; }

    /// <summary>Low-Low limit (alarm_ll_limit). Null = not configured.</summary>
    public double? LlLimit { get; init; }

    /// <summary>
    /// Deadband applied when exiting an alarm zone (alarm_deadband).
    /// Prevents oscillation at the setpoint boundary.
    /// Default 0 = no deadband (immediate exit on return to normal).
    /// </summary>
    public double AlarmDeadband { get; init; }

    /// <summary>
    /// Maximum fraction of |limit| that the deadband is allowed to consume.
    /// A deadband wider than this is treated as a misconfiguration and clamped.
    /// </summary>
    private const double MaxDeadbandFraction = 0.5;

    /// <summary>
    /// Returns the effective deadband to use for a given alarm limit, clamped so the
    /// return-to-normal (RTN) threshold can NEVER become unreachable.
    ///
    /// Why this exists:
    ///   A blanket default deadband (e.g. 1.0) applied to a small-range tag whose
    ///   setpoint is &lt; 1.0 pushes the RTN exit threshold to the wrong side of zero.
    ///   Example — High alarm, limit = 0.4, deadband = 1.0:
    ///       exit threshold = 0.4 - 1.0 = -0.6
    ///   A positive process value can never drop below -0.6, so the alarm is stuck
    ///   ACTIVE forever (raise still works because IsInAlarmZone ignores deadband).
    ///
    /// Fix: clamp the deadband to at most MaxDeadbandFraction (50%) of |limit|.
    ///   • Well-configured small deadbands (&lt; cap) are used unchanged → hysteresis preserved.
    ///   • Pathological deadbands (≥ cap) are neutralised → RTN threshold stays reachable.
    /// </summary>
    public double EffectiveDeadband(double limit)
    {
        if (AlarmDeadband <= 0) return 0;
        var cap = Math.Abs(limit) * MaxDeadbandFraction;
        return Math.Min(AlarmDeadband, cap);
    }

    /// <summary>Alarm priority 1-5 (alarm_priority). Maps to severity column in historian_events.</summary>
    public int AlarmPriority { get; init; }

    /// <summary>Interlock type string from tag_master. Null if no interlock configured.</summary>
    public string? InterlockType { get; init; }

    /// <summary>Whether this tag initiates a trip event.</summary>
    public bool IsTripInitiator { get; init; }

    /// <summary>Tag ID of the trip tag this tag causes (causes_trip_on_tag). Null if not a trip initiator.</summary>
    public string? CausesTripOnTag { get; init; }

    /// <summary>Trip category label from tag_master (e.g. "OVERSPEED_TRIP", "LOAD_SHEDDING").</summary>
    public string? TripCategory { get; init; }

    /// <summary>
    /// Onset delay before raising an alarm (alarm_onset_delay_s).
    /// 0 = immediate raise (default). >0 = value must stay in alarm zone for this many seconds.
    /// Prevents false alarms from short-lived spikes.
    /// </summary>
    public int OnsetDelaySeconds { get; init; }
}
