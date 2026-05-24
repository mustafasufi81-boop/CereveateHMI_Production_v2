namespace OpcDaWebBrowser.Services.Logging;

/// <summary>
/// Lightweight correlation ID tracking using AsyncLocal (thread-safe, async-safe)
/// ONE ID per OPC read cycle, NOT per tag (performance-optimized)
/// Matches AVEVA/Honeywell industrial logging standards
/// </summary>
public static class CorrelationContext
{
    private static readonly AsyncLocal<string?> _current = new();

    /// <summary>
    /// Get current correlation ID (creates new if none exists)
    /// </summary>
    public static string Current => _current.Value ??= NewId();

    /// <summary>
    /// Start new correlation cycle (e.g., new OPC read, new batch)
    /// </summary>
    public static string NewCycle()
    {
        var newId = NewId();
        _current.Value = newId;
        return newId;
    }

    /// <summary>
    /// Set specific correlation ID (for cross-service tracing)
    /// </summary>
    public static void Set(string correlationId) => _current.Value = correlationId;

    /// <summary>
    /// Clear correlation ID (reset context)
    /// </summary>
    public static void Clear() => _current.Value = null;

    /// <summary>
    /// Generate new correlation ID (compact format: 16 chars, lowercase)
    /// </summary>
    private static string NewId() => Guid.NewGuid().ToString("N")[..16];
}
