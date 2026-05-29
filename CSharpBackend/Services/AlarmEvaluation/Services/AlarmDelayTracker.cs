using System.Collections.Concurrent;
using OpcDaWebBrowser.Services.AlarmEvaluation.Models;

namespace OpcDaWebBrowser.Services.AlarmEvaluation.Services;

/// <summary>
/// Tracks per-alarm-key onset delay timers (anti-spike / anti-noise protection).
///
/// When a tag first crosses a threshold, the delay tracker starts a timer.
/// If the condition is STILL true when the timer expires → AlarmStateManager raises the alarm.
/// If the value returns to normal before expiry → timer is cancelled, no alarm raised.
///
/// Onset delay is zero by default (immediate raise).
/// Configured per-tag via historian_meta.tag_master.alarm_onset_delay_s.
///
/// Thread-safe: ConcurrentDictionary ensures safe concurrent access.
/// </summary>
public sealed class AlarmDelayTracker
{
    private sealed class PendingOnset
    {
        public required string     AlarmKey  { get; init; }
        public required AlarmLevel Level     { get; init; }
        public required double     Value     { get; init; }
        public required DateTimeOffset StartedAt { get; init; }
        public required int        DelaySeconds { get; init; }
    }

    private readonly ConcurrentDictionary<string, PendingOnset> _pending =
        new(StringComparer.OrdinalIgnoreCase);

    // Separate dictionary for OFF-delay (RTN settling) timers — ISA-18.2 §5.3.3/§16.
    // Kept distinct from onset timers so the two states never interfere.
    private readonly ConcurrentDictionary<string, PendingOnset> _pendingRtn =
        new(StringComparer.OrdinalIgnoreCase);

    private readonly ILogger<AlarmDelayTracker> _logger;

    public AlarmDelayTracker(ILogger<AlarmDelayTracker> logger)
    {
        _logger = logger ?? throw new ArgumentNullException(nameof(logger));
    }

    // =========================================================
    // PUBLIC API
    // =========================================================

    /// <summary>
    /// Called on each evaluation cycle when a tag's value is in an alarm zone.
    ///
    /// If onsetDelaySeconds == 0  → returns true immediately (raise now).
    /// If no pending timer yet    → starts the timer, returns false.
    /// If timer already started   → checks if elapsed; returns true if expired, false if still waiting.
    /// </summary>
    public bool TryStartOrCheck(string alarmKey, AlarmLevel level, double value, int onsetDelaySeconds)
    {
        if (onsetDelaySeconds <= 0)
            return true;  // Immediate raise — no delay needed

        if (_pending.TryGetValue(alarmKey, out var existing))
        {
            // Timer already running — check if delay has elapsed
            var elapsed = DateTimeOffset.UtcNow - existing.StartedAt;
            if (elapsed.TotalSeconds >= onsetDelaySeconds)
            {
                _pending.TryRemove(alarmKey, out _);
                _logger.LogDebug("AlarmDelayTracker: onset delay expired for {Key} — raising alarm", alarmKey);
                return true;
            }
            return false;  // Still waiting
        }

        // Start new onset timer
        _pending[alarmKey] = new PendingOnset
        {
            AlarmKey     = alarmKey,
            Level        = level,
            Value        = value,
            StartedAt    = DateTimeOffset.UtcNow,
            DelaySeconds = onsetDelaySeconds,
        };
        _logger.LogDebug("AlarmDelayTracker: onset delay started for {Key} ({Sec}s)", alarmKey, onsetDelaySeconds);
        return false;
    }

    /// <summary>
    /// Called when the alarm condition clears BEFORE the onset delay expires.
    /// Cancels the pending timer — no alarm will be raised for this occurrence.
    /// </summary>
    public void Cancel(string alarmKey)
    {
        if (_pending.TryRemove(alarmKey, out _))
            _logger.LogDebug("AlarmDelayTracker: onset delay cancelled for {Key} (value returned to normal before delay expired)", alarmKey);
    }

    /// <summary>Returns true if there is a pending onset timer for the given alarm key.</summary>
    public bool IsPending(string alarmKey) => _pending.ContainsKey(alarmKey);

    /// <summary>Count of currently pending onset timers (diagnostics).</summary>
    public int PendingCount => _pending.Count;

    // =========================================================
    // RTN OFF-DELAY (settling time before clearing) — ISA-18.2 §5.3.3 / §16
    // Mirrors the onset-delay API symmetrically. Value must remain in the NORMAL
    // range for the configured seconds continuously before RTN is declared.
    // Collapses chattering oscillations into a single event.
    // =========================================================

    /// <summary>
    /// Called on each evaluation cycle when an active alarm's value has returned to normal
    /// (HasExitedAlarmZone is true).
    ///
    /// If offDelaySeconds == 0   → returns true immediately (RTN now — legacy behaviour).
    /// If no pending timer yet   → starts the timer, returns false.
    /// If timer already started  → returns true if elapsed, false if still settling.
    /// </summary>
    public bool TryStartOrCheckRtn(string alarmKey, AlarmLevel level, double value, int offDelaySeconds)
    {
        if (offDelaySeconds <= 0)
            return true;  // Immediate RTN — no settling required

        if (_pendingRtn.TryGetValue(alarmKey, out var existing))
        {
            var elapsed = DateTimeOffset.UtcNow - existing.StartedAt;
            if (elapsed.TotalSeconds >= offDelaySeconds)
            {
                _pendingRtn.TryRemove(alarmKey, out _);
                _logger.LogDebug("AlarmDelayTracker: RTN off-delay expired for {Key} — clearing alarm", alarmKey);
                return true;
            }
            return false;  // Still settling
        }

        _pendingRtn[alarmKey] = new PendingOnset
        {
            AlarmKey     = alarmKey,
            Level        = level,
            Value        = value,
            StartedAt    = DateTimeOffset.UtcNow,
            DelaySeconds = offDelaySeconds,
        };
        _logger.LogDebug("AlarmDelayTracker: RTN off-delay started for {Key} ({Sec}s)", alarmKey, offDelaySeconds);
        return false;
    }

    /// <summary>
    /// Called when the value re-enters the alarm zone BEFORE the RTN off-delay expires.
    /// Cancels the pending RTN timer — the alarm stays active, no RTN is fired.
    /// </summary>
    public void CancelRtn(string alarmKey)
    {
        if (_pendingRtn.TryRemove(alarmKey, out _))
            _logger.LogDebug("AlarmDelayTracker: RTN off-delay cancelled for {Key} (value re-entered alarm zone before settling)", alarmKey);
    }

    /// <summary>Returns true if there is a pending RTN off-delay timer for the given alarm key.</summary>
    public bool IsRtnPending(string alarmKey) => _pendingRtn.ContainsKey(alarmKey);

    /// <summary>Count of currently pending RTN off-delay timers (diagnostics).</summary>
    public int PendingRtnCount => _pendingRtn.Count;
}
