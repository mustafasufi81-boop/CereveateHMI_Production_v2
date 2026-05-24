using System;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Configuration;

namespace OpcDaWebBrowser.Services;

/// <summary>
/// Optional hosted service that drives the synthetic stress test when enabled via configuration.
/// </summary>
public class StressTestHostedService : IHostedService, IDisposable
{
    private readonly DataLoggingService _dataLoggingService;
    private readonly ILogger<StressTestHostedService> _logger;
    private readonly ILoggerFactory _loggerFactory;
    private readonly IConfiguration _configuration;
    private CancellationTokenSource? _cts;
    private Task? _runTask;
    private bool _enabled;

    public StressTestHostedService(
        DataLoggingService dataLoggingService,
        ILogger<StressTestHostedService> logger,
        ILoggerFactory loggerFactory,
        IConfiguration configuration)
    {
        _dataLoggingService = dataLoggingService;
        _logger = logger;
        _loggerFactory = loggerFactory;
        _configuration = configuration;
    }

    public Task StartAsync(CancellationToken cancellationToken)
    {
        _enabled = _configuration.GetValue("StressTest:Enabled", false);
        if (!_enabled)
        {
            _logger.LogInformation("Stress test disabled");
            return Task.CompletedTask;
        }

        var tagCount = _configuration.GetValue("StressTest:TagCount", 10000);
        var intervalMs = _configuration.GetValue("StressTest:IntervalMs", 1000);
        var durationSeconds = _configuration.GetValue("StressTest:DurationSeconds", 120);
        var startupDelayMs = _configuration.GetValue("StressTest:StartupDelayMs", 5000);

        _cts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);

        _runTask = Task.Run(async () =>
        {
            try
            {
                if (startupDelayMs > 0)
                {
                    await Task.Delay(startupDelayMs, _cts.Token);
                }

                var stressService = new StressTestService(
                    _dataLoggingService.StressChannel.Writer,
                    _loggerFactory.CreateLogger<StressTestService>());

                await stressService.RunAsync(
                    tagCount: tagCount,
                    durationSeconds: durationSeconds,
                    intervalMs: intervalMs,
                    token: _cts.Token);
            }
            catch (OperationCanceledException)
            {
                // expected on shutdown
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Stress test execution failed");
            }
        }, CancellationToken.None);

        _logger.LogInformation(
            "Stress test scheduled with {Tags} tags, {Interval}ms interval, duration {Duration}s",
            tagCount,
            intervalMs,
            durationSeconds);

        return Task.CompletedTask;
    }

    public async Task StopAsync(CancellationToken cancellationToken)
    {
        if (!_enabled)
        {
            return;
        }

        if (_cts != null)
        {
            _cts.Cancel();
        }

        if (_runTask != null)
        {
            try
            {
                await _runTask.WaitAsync(cancellationToken);
            }
            catch (OperationCanceledException)
            {
                // expected when host stops
            }
        }
    }

    public void Dispose()
    {
        _cts?.Dispose();
    }
}
