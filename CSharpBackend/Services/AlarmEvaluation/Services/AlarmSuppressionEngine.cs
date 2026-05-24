using OpcDaWebBrowser.Services.AlarmEvaluation.Models;

namespace OpcDaWebBrowser.Services.AlarmEvaluation.Services;

/// <summary>
/// Phase 1 ISA-18.2 alarm suppression: HH suppresses H, LL suppresses L (same tag only).
/// Pure static logic — no DB, no MQTT, no state mutation.
/// Called during evaluation BEFORE attempting to raise a new alarm.
///
/// Rules:
///   H  is suppressed when HH is ACTIVE_UNACK or ACTIVE_ACK for the same tag.
///   L  is suppressed when LL is ACTIVE_UNACK or ACTIVE_ACK for the same tag.
///   HH and LL are never suppressed.
///
/// When HH clears → if H condition still valid → H raises immediately (unsuppressed).
/// </summary>
public static class AlarmSuppressionEngine
{
    /// <summary>
    /// Returns true if the candidate alarm level should be suppressed because a
    /// higher-severity alarm is already active (ACTIVE_UNACK or ACTIVE_ACK) for the same tag.
    /// </summary>
    public static bool IsSuppressed(
        AlarmLevel candidateLevel,
        string tagId,
        IReadOnlyDictionary<string, AlarmRuntimeState> runtimeStates)
    {
        return candidateLevel switch
        {
            AlarmLevel.High => IsAlarmActive(AlarmRuntimeState.BuildKey(tagId, AlarmLevel.HighHigh), runtimeStates),
            AlarmLevel.Low  => IsAlarmActive(AlarmRuntimeState.BuildKey(tagId, AlarmLevel.LowLow),   runtimeStates),
            _               => false,  // HH, LL, None are never suppressed
        };
    }

    private static bool IsAlarmActive(string alarmKey, IReadOnlyDictionary<string, AlarmRuntimeState> states) =>
        states.TryGetValue(alarmKey, out var s) &&
        s.State is AlarmState4.ActiveUnack or AlarmState4.ActiveAck;
}
