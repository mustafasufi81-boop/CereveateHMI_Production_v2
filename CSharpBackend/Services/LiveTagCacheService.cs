using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using OpcDaWebBrowser.Services;

namespace OpcDaWebBrowser.Services;

/// <summary>
/// Polls OpcDaService every 500ms and feeds TagValuesPoolService.
/// This is the ONLY consumer of OpcDaService.ReadAllTagValues() for the alarm/interlock pipeline.
/// No OpcServerConnection is created here — OpcDaService is the single owner of the one shared connection.
/// Replaces the 1091-line DataLoggingService which created a second OPC connection (MTA, no dispatcher = COM errors).
/// </summary>
public class LiveTagCacheService : BackgroundService
{
    private readonly OpcDaService _opcDaService;
    private readonly TagValuesPoolService _tagPool;
    private readonly ILogger<LiveTagCacheService> _logger;

    private const int PollIntervalMs = 500;

    public LiveTagCacheService(
        OpcDaService opcDaService,
        TagValuesPoolService tagPool,
        ILogger<LiveTagCacheService> logger)
    {
        _opcDaService = opcDaService;
        _tagPool = tagPool;
        _logger = logger;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        _logger.LogInformation(
            "[LiveTagCache] Started — polling OpcDaService every {Interval}ms → TagValuesPoolService",
            PollIntervalMs);

        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                var values = _opcDaService.ReadAllTagValues();
                if (values.Count > 0)
                {
                    _tagPool.UpdatePool(values, DateTime.UtcNow);
                }
            }
            catch (Exception ex)
            {
                _logger.LogWarning(ex, "[LiveTagCache] Pool update cycle failed — will retry next interval");
            }

            await Task.Delay(PollIntervalMs, stoppingToken);
        }

        _logger.LogInformation("[LiveTagCache] Stopped");
    }
}
