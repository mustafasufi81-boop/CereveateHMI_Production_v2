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
