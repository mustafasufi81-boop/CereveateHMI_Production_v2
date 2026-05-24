using System.Collections.Concurrent;
using OpcDaWebBrowser.Services.HistorianIngest.Config;
using OpcDaWebBrowser.Services.HistorianIngest.Models;

namespace OpcDaWebBrowser.Services.HistorianIngest.Services;

/// <summary>
/// Per-tag rate controller with change detection and frequency filtering
/// Ensures samples are logged at user-configured intervals (1s-60s) and only on value change
/// </summary>
public class RateControllerService
{
    private readonly HistorianConfig _config;
    private readonly MappingCacheService _mappingCache;
    private readonly ILogger<RateControllerService> _logger;
    
    // Per-tag state tracking (thread-safe for high concurrency)
    private readonly ConcurrentDictionary<string, TagRateState> _tagStates = new(StringComparer.OrdinalIgnoreCase);
    
    private long _samplesReceived = 0;
    private long _samplesFiltered = 0;
    private long _samplesPassed = 0;

    public long SamplesReceived => _samplesReceived;
    public long SamplesFiltered => _samplesFiltered;
    public long SamplesPassed => _samplesPassed;

    public RateControllerService(
        HistorianConfig config,
        MappingCacheService mappingCache,
        ILogger<RateControllerService> logger)
    {
        _config = config;
        _mappingCache = mappingCache;
        _logger = logger;
    }

    /// <summary>
    /// Process raw sample through rate control logic
    /// Returns null if sample should be filtered, otherwise returns the sample to write
    /// </summary>
    public RawSample? ProcessSample(RawSample sample)
    {
        Interlocked.Increment(ref _samplesReceived);

        if (!_config.RateControl.Enabled)
        {
            Interlocked.Increment(ref _samplesPassed);
            return sample;
        }

        // Get tag mapping
        var mapping = _mappingCache.GetMapping(sample.TagId);
        if (mapping == null || !mapping.Enabled)
        {
            Interlocked.Increment(ref _samplesFiltered);
            return null; // Unmapped or disabled tag
        }

        // Get or create tag state
        var state = _tagStates.GetOrAdd(sample.TagId, _ => new TagRateState());

        lock (state.Lock)
        {
            var now = DateTimeOffset.Now;
            var intervalMs = mapping.DbLoggingIntervalMs;

            // RULE 1: First sample always passes
            if (!state.LastWrittenTime.HasValue)
            {
                state.LastWrittenTime = now;
                state.LastWrittenValue = sample.RawValue;
                state.PendingSample = null;
                Interlocked.Increment(ref _samplesPassed);
                return sample;
            }

            var timeSinceLastWrite = (now - state.LastWrittenTime.Value).TotalMilliseconds;

            // RULE 2: Change detection (if enabled)
            bool valueChanged = false;
            if (_config.RateControl.UseChangeDetection)
            {
                valueChanged = HasValueChanged(
                    state.LastWrittenValue,
                    sample.RawValue,
                    mapping.DataType,
                    mapping.DeadbandValue
                );
            }

            // RULE 3: Minimum interval elapsed
            bool intervalElapsed = timeSinceLastWrite >= intervalMs;

            // Decision logic
            if (valueChanged && intervalElapsed)
            {
                // Value changed AND interval elapsed → WRITE
                state.LastWrittenTime = now;
                state.LastWrittenValue = sample.RawValue;
                state.PendingSample = null;
                Interlocked.Increment(ref _samplesPassed);
                return sample;
            }
            else if (valueChanged && !intervalElapsed)
            {
                // Value changed but interval NOT elapsed → HOLD as pending
                state.PendingSample = sample;
                Interlocked.Increment(ref _samplesFiltered);
                return null;
            }
            else if (!valueChanged && intervalElapsed && state.PendingSample != null)
            {
                // No change but interval elapsed AND we have pending → WRITE pending
                var pendingSample = state.PendingSample;
                state.LastWrittenTime = now;
                state.LastWrittenValue = pendingSample.RawValue;
                state.PendingSample = null;
                Interlocked.Increment(ref _samplesPassed);
                return pendingSample;
            }
            else if (intervalElapsed && !valueChanged)
            {
                // Interval elapsed but no change since last write → FILTER (no spam)
                Interlocked.Increment(ref _samplesFiltered);
                return null;
            }
            else
            {
                // All other cases → FILTER
                Interlocked.Increment(ref _samplesFiltered);
                return null;
            }
        }
    }

    /// <summary>
    /// Detect if value changed beyond deadband threshold
    /// </summary>
    private bool HasValueChanged(object? oldValue, object? newValue, TagDataType dataType, double deadband)
    {
        if (oldValue == null && newValue == null) return false;
        if (oldValue == null || newValue == null) return true;

        try
        {
            switch (dataType)
            {
                case TagDataType.Double:
                    var oldDouble = Convert.ToDouble(oldValue);
                    var newDouble = Convert.ToDouble(newValue);
                    return Math.Abs(newDouble - oldDouble) > deadband;

                case TagDataType.Int:
                    var oldInt = Convert.ToInt64(oldValue);
                    var newInt = Convert.ToInt64(newValue);
                    return Math.Abs(newInt - oldInt) > (long)deadband;

                case TagDataType.Bool:
                    return Convert.ToBoolean(oldValue) != Convert.ToBoolean(newValue);

                case TagDataType.String:
                    return oldValue.ToString() != newValue.ToString();

                default:
                    return true; // Unknown type, assume changed
            }
        }
        catch
        {
            return true; // Conversion error, assume changed
        }
    }

    /// <summary>
    /// Clear state for specific tag (useful for testing or reset)
    /// </summary>
    public void ClearTagState(string tagId)
    {
        _tagStates.TryRemove(tagId, out _);
    }

    /// <summary>
    /// Get rate control statistics
    /// </summary>
    public RateControlStats GetStats()
    {
        return new RateControlStats
        {
            TotalReceived = _samplesReceived,
            TotalFiltered = _samplesFiltered,
            TotalPassed = _samplesPassed,
            FilterRatio = _samplesReceived > 0 ? (double)_samplesFiltered / _samplesReceived : 0,
            ActiveTags = _tagStates.Count
        };
    }
}

/// <summary>
/// Per-tag state for rate control
/// </summary>
internal class TagRateState
{
    public object Lock { get; } = new object();
    public DateTimeOffset? LastWrittenTime { get; set; }
    public object? LastWrittenValue { get; set; }
    public RawSample? PendingSample { get; set; }
}

public class RateControlStats
{
    public long TotalReceived { get; set; }
    public long TotalFiltered { get; set; }
    public long TotalPassed { get; set; }
    public double FilterRatio { get; set; }
    public int ActiveTags { get; set; }
}
