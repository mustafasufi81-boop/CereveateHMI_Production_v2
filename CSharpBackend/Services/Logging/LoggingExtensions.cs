using Microsoft.Extensions.Logging;

namespace OpcDaWebBrowser.Services.Logging;

/// <summary>
/// Structured logging extension methods matching industrial historian standards
/// Provides consistent log format: [Service] [EventType] message | property=value
/// </summary>
public static class LoggingExtensions
{
    /// <summary>
    /// Log with event type and correlation ID (standard format)
    /// </summary>
    public static void LogEvent(
        this ILogger logger,
        LogLevel level,
        string eventType,
        string message,
        params object[] args)
    {
        if (!logger.IsEnabled(level)) return;

        var correlationId = CorrelationContext.Current;
        var formattedMessage = $"[{eventType}] {message} | trace={correlationId}";

        logger.Log(level, formattedMessage, args);
    }

    /// <summary>
    /// Log OPC operation with timing
    /// </summary>
    public static void LogOpcOperation(
        this ILogger logger,
        string eventType,
        string message,
        long? durationMs = null,
        params object[] args)
    {
        var correlationId = CorrelationContext.Current;
        var formattedMessage = durationMs.HasValue
            ? $"[{eventType}] {message} | duration={durationMs}ms | trace={correlationId}"
            : $"[{eventType}] {message} | trace={correlationId}";

        logger.LogInformation(formattedMessage, args);
    }

    /// <summary>
    /// Log database operation with batch stats
    /// </summary>
    public static void LogDbOperation(
        this ILogger logger,
        string eventType,
        int rows,
        long durationMs,
        int retries = 0)
    {
        var correlationId = CorrelationContext.Current;
        logger.LogInformation(
            "[{EventType}] rows={Rows} | time={Duration}ms | retries={Retries} | trace={TraceId}",
            eventType, rows, durationMs, retries, correlationId);
    }

    /// <summary>
    /// Log user action (audit trail)
    /// </summary>
    public static void LogUserAction(
        this ILogger logger,
        string username,
        string action,
        string? details = null)
    {
        var correlationId = CorrelationContext.Current;
        logger.LogInformation(
            "[{EventType}] user={User} | action={Action} | details={Details} | trace={TraceId}",
            LogEventType.USER_ACTION, username, action, details ?? "N/A", correlationId);
    }

    /// <summary>
    /// Log context-rich exception (who, what, where, when, error type)
    /// </summary>
    public static void LogContextualError(
        this ILogger logger,
        Exception ex,
        string eventType,
        string context,
        Dictionary<string, object>? additionalData = null)
    {
        var correlationId = CorrelationContext.Current;
        var message = $"[{eventType}] {context} | error={ex.GetType().Name} | trace={correlationId}";

        if (additionalData != null && additionalData.Count > 0)
        {
            var dataStr = string.Join(" | ", additionalData.Select(kv => $"{kv.Key}={kv.Value}"));
            message += $" | {dataStr}";
        }

        logger.LogError(ex, message);
    }

    /// <summary>
    /// Log batch summary (aggregate metrics every N batches)
    /// </summary>
    public static void LogBatchSummary(
        this ILogger logger,
        int batchCount,
        long totalRows,
        double avgTimeMs,
        int retryCount = 0)
    {
        var correlationId = CorrelationContext.Current;
        logger.LogInformation(
            "[{EventType}] batches={Batches} | totalRows={Rows} | avgTime={AvgMs:F1}ms | retries={Retries} | trace={TraceId}",
            LogEventType.HIST_BATCH_SUMMARY, batchCount, totalRows, avgTimeMs, retryCount, correlationId);
    }

    /// <summary>
    /// Log health check summary (every 5 minutes)
    /// </summary>
    public static void LogHealthSummary(
        this ILogger logger,
        string opcStatus,
        string writerStatus,
        string spoolStatus,
        int diskFreePercent,
        long memoryMB)
    {
        logger.LogInformation(
            "[{EventType}] OPC={Opc} | Writer={Writer} | Spool={Spool} | Disk={Disk}% | Memory={Memory}MB",
            LogEventType.HEALTH_CHECK, opcStatus, writerStatus, spoolStatus, diskFreePercent, memoryMB);
    }

    /// <summary>
    /// Log disk space warning/critical
    /// </summary>
    public static void LogDiskAlert(
        this ILogger logger,
        string drivePath,
        long freeGB,
        int freePercent,
        bool isCritical)
    {
        var eventType = isCritical ? LogEventType.DISK_CRITICAL : LogEventType.DISK_WARNING;
        var level = isCritical ? LogLevel.Error : LogLevel.Warning;

        logger.Log(level,
            "[{EventType}] drive={Drive} | free={FreeGB}GB ({FreePercent}%)",
            eventType, drivePath, freeGB, freePercent);
    }
}
