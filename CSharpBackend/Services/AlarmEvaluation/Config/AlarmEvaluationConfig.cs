namespace OpcDaWebBrowser.Services.AlarmEvaluation.Config;

/// <summary>
/// Configuration for the Alarm Evaluation subsystem.
/// Bound from appsettings.json section "AlarmEvaluation".
/// All values have safe defaults so the service starts even if the section is missing.
/// </summary>
public sealed class AlarmEvaluationConfig
{
    public const string SectionName = "AlarmEvaluation";

    /// <summary>Master switch — set to false to disable evaluation without removing code.</summary>
    public bool Enabled { get; set; } = true;

    /// <summary>
    /// How often the evaluation loop runs (milliseconds).
    /// Should match or be a multiple of OpcPollingIntervalMs (1000ms).
    /// </summary>
    public int EvaluationIntervalMs { get; set; } = 1000;

    /// <summary>
    /// How often the setpoint cache refreshes from historian_meta.tag_master (seconds).
    /// Allows operators to change setpoints without restarting the service.
    /// </summary>
    public int SetpointCacheRefreshIntervalSeconds { get; set; } = 60;

    /// <summary>
    /// How often the in-memory runtime state is reconciled against the DB (seconds).
    /// Picks up operator ACK/CLEAR actions so re-raise logic works correctly.
    /// </summary>
    public int RuntimeStateRefreshIntervalSeconds { get; set; } = 30;

    /// <summary>
    /// Full MQTT topic for alarm events published by this service.
    /// Example: "opc/alarms/events"
    /// </summary>
    public string MqttAlarmTopic { get; set; } = "opc/alarms/events";

    /// <summary>
    /// Number of consecutive DB write failures before the circuit breaker opens.
    /// When open, DB writes are skipped until the timeout expires.
    /// </summary>
    public int MaxConsecutiveDbFailures { get; set; } = 5;

    /// <summary>Circuit breaker reset timeout (minutes) after it trips.</summary>
    public int DbCircuitBreakerTimeoutMinutes { get; set; } = 2;

    /// <summary>
    /// Off-delay (RTN settling time) in seconds — ISA-18.2 §5.3.3 / §16 chatter control.
    /// After value returns to the normal range, it must STAY normal for this many
    /// continuous seconds before RTN is declared. Mirrors the existing onset delay
    /// but on the exit side. Collapses fleeting oscillations into a single event.
    /// Default 5 s. Set to 0 to disable (immediate RTN, legacy behaviour).
    /// </summary>
    public int RtnOffDelaySeconds { get; set; } = 5;

    /// <summary>
    /// Name written to alarm_audit_trail.performed_by for system-raised alarms.
    /// Distinguishes automatic alarms from operator actions.
    /// </summary>
    public string SystemActorName { get; set; } = "OPC_SYSTEM";

    /// <summary>
    /// MQTT client ID suffix for the alarm publisher connection.
    /// Full ID is built as: "cereveate-alarm-eval-{suffix}"
    /// </summary>
    public string MqttClientIdSuffix { get; set; } = "alarm-eval";

    // =========================================================
    // INTERLOCK EVALUATION — mirrors alarm config properties
    // =========================================================

    /// <summary>
    /// Master switch for interlock evaluation.
    /// Set to false to disable without removing code.
    /// </summary>
    public bool InterlockEnabled { get; set; } = true;

    /// <summary>
    /// Full MQTT topic for interlock state events published by InterlockEvaluationService.
    /// Example: "opc/interlocks/events"
    /// </summary>
    public string MqttInterlockTopic { get; set; } = "opc/interlocks/events";

    /// <summary>
    /// MQTT client ID suffix for the interlock publisher connection.
    /// Full ID is built as: "cereveate-{suffix}-{MachineName}"
    /// </summary>
    public string MqttInterlockClientIdSuffix { get; set; } = "interlock-eval";
}
