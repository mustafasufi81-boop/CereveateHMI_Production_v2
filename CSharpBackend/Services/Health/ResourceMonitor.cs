using System.Diagnostics;

namespace OpcDaWebBrowser.Services.Health;

/// <summary>
/// Background service monitoring system resources (CPU, memory, disk)
/// Runs every 10 seconds, pushes metrics to HealthStatusService
/// Zero impact on OPC/DB operations (separate thread, low priority)
/// </summary>
public class ResourceMonitor : BackgroundService
{
    private readonly IHealthStatusService _healthService;
    private readonly IConfiguration _configuration;
    private readonly ILogger<ResourceMonitor> _logger;
    private readonly TimeSpan _sampleInterval;
    private readonly bool _diskMonitoringEnabled;
    private readonly string _monitoredDrive;
    
    private readonly PerformanceCounter? _cpuCounter;
    private readonly Process _currentProcess;

    public ResourceMonitor(
        IHealthStatusService healthService,
        IConfiguration configuration,
        ILogger<ResourceMonitor> logger)
    {
        _healthService = healthService;
        _configuration = configuration;
        _logger = logger;

        _sampleInterval = TimeSpan.FromSeconds(
            configuration.GetValue<int>("HealthMonitor:ResourceSampleIntervalSeconds", 10));
        
        _diskMonitoringEnabled = configuration.GetValue<bool>("HealthMonitor:DiskMonitoringEnabled", true);
        
        // Determine monitored drive from DataLogDirectory
        var dataLogPath = configuration["LoggingPaths:DataLogDirectory"] ?? "D:\\OpcLogs\\Data";
        _monitoredDrive = Path.GetPathRoot(dataLogPath) ?? "D:\\";

        _currentProcess = Process.GetCurrentProcess();

        // Initialize CPU counter (Windows only)
        try
        {
            _cpuCounter = new PerformanceCounter("Processor", "% Processor Time", "_Total", true);
            _cpuCounter.NextValue(); // Prime the counter
        }
        catch (Exception ex)
        {
            _logger.LogWarning($"CPU counter initialization failed (non-Windows?): {ex.Message}");
        }

        _logger.LogInformation($"📊 Resource Monitor initialized (interval: {_sampleInterval.TotalSeconds}s, drive: {_monitoredDrive})");
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        _logger.LogInformation("📊 Resource Monitor started");

        // Initial sample after 2 seconds (allow services to initialize)
        await Task.Delay(TimeSpan.FromSeconds(2), stoppingToken);

        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                var health = CollectResourceMetrics();
                _healthService.UpdateResourceHealth(health);

                await Task.Delay(_sampleInterval, stoppingToken);
            }
            catch (OperationCanceledException)
            {
                break;
            }
            catch (Exception ex)
            {
                _logger.LogError($"❌ Resource monitoring error: {ex.Message}");
                await Task.Delay(TimeSpan.FromSeconds(30), stoppingToken);
            }
        }

        _logger.LogInformation("📊 Resource Monitor stopped");
    }

    /// <summary>
    /// Collect current resource metrics
    /// </summary>
    private ResourceHealth CollectResourceMetrics()
    {
        try
        {
            // CPU usage (system-wide)
            var cpuUsage = _cpuCounter?.NextValue() ?? 0;

            // Memory usage (current process)
            _currentProcess.Refresh();
            var memoryUsageMB = _currentProcess.WorkingSet64 / (1024 * 1024);
            var totalMemoryMB = GC.GetGCMemoryInfo().TotalAvailableMemoryBytes / (1024 * 1024);
            var memoryUsagePercent = totalMemoryMB > 0 
                ? (double)memoryUsageMB / totalMemoryMB * 100 
                : 0;

            // Disk usage (monitored drive)
            long diskFreeMB = 0;
            double diskUsagePercent = 0;

            if (_diskMonitoringEnabled)
            {
                try
                {
                    var driveInfo = new DriveInfo(_monitoredDrive);
                    if (driveInfo.IsReady)
                    {
                        diskFreeMB = driveInfo.AvailableFreeSpace / (1024 * 1024);
                        var totalDiskMB = driveInfo.TotalSize / (1024 * 1024);
                        diskUsagePercent = totalDiskMB > 0 
                            ? (double)(totalDiskMB - diskFreeMB) / totalDiskMB * 100 
                            : 0;
                    }
                }
                catch (Exception ex)
                {
                    _logger.LogDebug($"Disk monitoring error: {ex.Message}");
                }
            }

            // Thread count (current process)
            var threadCount = _currentProcess.Threads.Count;

            // Calculate health score (0-100)
            var healthScore = CalculateResourceHealthScore(cpuUsage, memoryUsagePercent, diskUsagePercent);

            return new ResourceHealth
            {
                CpuUsagePercent = Math.Round(cpuUsage, 1),
                MemoryUsageMB = memoryUsageMB,
                MemoryUsagePercent = Math.Round(memoryUsagePercent, 1),
                DiskFreeMB = diskFreeMB,
                DiskUsagePercent = Math.Round(diskUsagePercent, 1),
                ThreadCount = threadCount,
                SampleTime = DateTime.Now,
                HealthScore = healthScore
            };
        }
        catch (Exception ex)
        {
            _logger.LogError($"❌ Resource collection error: {ex.Message}");
            return new ResourceHealth { HealthScore = 50, SampleTime = DateTime.Now };
        }
    }

    /// <summary>
    /// Calculate resource health score based on thresholds
    /// </summary>
    private double CalculateResourceHealthScore(double cpu, double memory, double disk)
    {
        double score = 100;

        // CPU penalty
        if (cpu > 95) score -= 40;
        else if (cpu > 80) score -= 20;
        else if (cpu > 60) score -= 10;

        // Memory penalty
        if (memory > 95) score -= 30;
        else if (memory > 80) score -= 15;
        else if (memory > 60) score -= 5;

        // Disk penalty
        if (disk > 95) score -= 30;
        else if (disk > 90) score -= 15;
        else if (disk > 80) score -= 5;

        return Math.Max(0, Math.Round(score, 1));
    }

    public override void Dispose()
    {
        _cpuCounter?.Dispose();
        base.Dispose();
    }
}
