namespace OpcDaWebBrowser.Services.Health;

/// <summary>
/// Central health status cache - PUSH architecture (services update cache, UI reads cache)
/// Thread-safe volatile fields for zero-lock reads
/// Industrial HMI pattern: Sub-millisecond UI reads, no service blocking
/// </summary>
public interface IHealthStatusService
{
    SystemHealthSnapshot GetCurrentSnapshot();
    void UpdateOpcHealth(OpcHealth health);
    void UpdateDbWriterHealth(DbWriterHealth health);
    void UpdateSpoolHealth(SpoolHealth health);
    void UpdateArchiverHealth(ArchiverHealth health);
    void UpdateResourceHealth(ResourceHealth health);
}

public class HealthStatusService : IHealthStatusService
{
    private readonly ILogger<HealthStatusService> _logger;
    
    // VOLATILE fields for lock-free reads (industrial real-time pattern)
    private volatile OpcHealth _opcHealth = new();
    private volatile DbWriterHealth _dbWriterHealth = new();
    private volatile SpoolHealth _spoolHealth = new();
    private volatile ArchiverHealth _archiverHealth = new();
    private volatile ResourceHealth _resourceHealth = new();
    
    private volatile int _activeAlerts = 0;
    private volatile int _warningCount = 0;
    private volatile int _errorCount = 0;

    public HealthStatusService(ILogger<HealthStatusService> logger)
    {
        _logger = logger;
        _logger.LogInformation("🏥 Health Status Service initialized (PUSH architecture)");
    }

    /// <summary>
    /// Get complete health snapshot (LOCK-FREE, <1ms read time)
    /// </summary>
    public SystemHealthSnapshot GetCurrentSnapshot()
    {
        // Capture volatile references atomically
        var opc = _opcHealth;
        var db = _dbWriterHealth;
        var spool = _spoolHealth;
        var archiver = _archiverHealth;
        var resources = _resourceHealth;

        // Gracefully handle idle/unknown subsystems so UI doesn't show errors when intentionally idle
        double normalizedOpcScore = NormalizeScore(opc.HealthScore, opc.Status);
        double normalizedDbScore = NormalizeScore(db.HealthScore, db.Status);
        double normalizedSpoolScore = NormalizeScore(spool.HealthScore, spool.Status);
        double normalizedArchiverScore = NormalizeScore(archiver.HealthScore, archiver.Status);
        double normalizedResourceScore = NormalizeScore(resources.HealthScore, "Resources");

        // Calculate weighted overall health score
        var overallScore = (
            normalizedOpcScore * 0.30 +        // OPC = 30% (critical)
            normalizedDbScore * 0.25 +         // DB Writer = 25% (critical)
            normalizedSpoolScore * 0.15 +      // Spool = 15% (important)
            normalizedArchiverScore * 0.10 +   // Archiver = 10% (maintenance)
            normalizedResourceScore * 0.20     // Resources = 20% (foundation)
        );

        // Determine overall status
        var overallStatus = overallScore switch
        {
            >= 90 => "Healthy",
            >= 70 => "Degraded",
            >= 50 => "Critical",
            _ => "Offline"
        };

        return new SystemHealthSnapshot
        {
            Timestamp = DateTime.Now,
            OverallStatus = overallStatus,
            OverallHealthScore = Math.Round(overallScore, 1),
            Opc = opc,
            DbWriter = db,
            Spool = spool,
            Archiver = archiver,
            Resources = resources,
            ActiveAlerts = _activeAlerts,
            WarningCount = _warningCount,
            ErrorCount = _errorCount
        };
    }

    /// <summary>
    /// Treat Unknown/Idle as neutral (100) so idle subsystems don't raise false alerts.
    /// </summary>
    private static double NormalizeScore(double rawScore, string status)
    {
        if (string.Equals(status, "Unknown", StringComparison.OrdinalIgnoreCase) ||
            string.Equals(status, "Idle", StringComparison.OrdinalIgnoreCase))
        {
            return 100;
        }
        return rawScore;
    }

    /// <summary>
    /// Update OPC health (called from OpcAutoConnectService or OpcDaService)
    /// </summary>
    public void UpdateOpcHealth(OpcHealth health)
    {
        _opcHealth = health;
        RecalculateAlerts();
        _logger.LogDebug($"OPC health updated: {health.Status}, Score: {health.HealthScore}");
    }

    /// <summary>
    /// Update DB writer health (called from HistorianIngestHostedService)
    /// </summary>
    public void UpdateDbWriterHealth(DbWriterHealth health)
    {
        _dbWriterHealth = health;
        RecalculateAlerts();
        _logger.LogDebug($"DB writer health updated: {health.Status}, Score: {health.HealthScore}");
    }

    /// <summary>
    /// Update spool health (called from SpoolManager)
    /// </summary>
    public void UpdateSpoolHealth(SpoolHealth health)
    {
        _spoolHealth = health;
        RecalculateAlerts();
        _logger.LogDebug($"Spool health updated: {health.Status}, Score: {health.HealthScore}");
    }

    /// <summary>
    /// Update archiver health (called from LogBackupService)
    /// </summary>
    public void UpdateArchiverHealth(ArchiverHealth health)
    {
        _archiverHealth = health;
        RecalculateAlerts();
        _logger.LogDebug($"Archiver health updated: {health.Status}, Score: {health.HealthScore}");
    }

    /// <summary>
    /// Update resource health (called from ResourceMonitor background service)
    /// </summary>
    public void UpdateResourceHealth(ResourceHealth health)
    {
        _resourceHealth = health;
        RecalculateAlerts();
    }

    /// <summary>
    /// Recalculate alert counts based on health scores and status
    /// </summary>
    private void RecalculateAlerts()
    {
        int warnings = 0;
        int errors = 0;
        int alerts = 0;

        // OPC alerts
        if (!string.Equals(_opcHealth.Status, "Unknown", StringComparison.OrdinalIgnoreCase) &&
            !string.Equals(_opcHealth.Status, "Idle", StringComparison.OrdinalIgnoreCase))
        {
            if (_opcHealth.HealthScore < 90 && _opcHealth.HealthScore >= 70) warnings++;
            if (_opcHealth.HealthScore < 70) errors++;
            if (_opcHealth.Status == "Error" || _opcHealth.Status == "Disconnected") alerts++;
        }

        // DB Writer alerts
        if (_dbWriterHealth.HealthScore < 90 && _dbWriterHealth.HealthScore >= 70) warnings++;
        if (_dbWriterHealth.HealthScore < 70) errors++;
        if (_dbWriterHealth.Status == "Error") alerts++;

        // Spool alerts
        if (_spoolHealth.HealthScore < 90 && _spoolHealth.HealthScore >= 70) warnings++;
        if (_spoolHealth.HealthScore < 70) errors++;
        if (_spoolHealth.FilesInSpool > 100) warnings++; // Backlog warning
        if (_spoolHealth.FilesInSpool > 500) errors++; // Backlog critical

        // Archiver alerts
        if (_archiverHealth.HealthScore < 90 && _archiverHealth.HealthScore >= 70) warnings++;
        if (_archiverHealth.HealthScore < 70) errors++;
        if (_archiverHealth.UnarchivedFilesCount > 1000) warnings++; // Backlog warning

        // Resource alerts
        if (_resourceHealth.HealthScore < 90 && _resourceHealth.HealthScore >= 70) warnings++;
        if (_resourceHealth.HealthScore < 70) errors++;
        if (_resourceHealth.CpuUsagePercent > 80) warnings++;
        if (_resourceHealth.CpuUsagePercent > 95) errors++;
        if (_resourceHealth.MemoryUsagePercent > 80) warnings++;
        if (_resourceHealth.MemoryUsagePercent > 95) errors++;
        if (_resourceHealth.DiskUsagePercent > 90) errors++;

        _warningCount = warnings;
        _errorCount = errors;
        _activeAlerts = alerts;
    }
}
