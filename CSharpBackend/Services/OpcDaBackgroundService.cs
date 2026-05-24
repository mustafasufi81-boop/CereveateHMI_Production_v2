using Microsoft.AspNetCore.SignalR;
using OpcDaWebBrowser.Hubs;

namespace OpcDaWebBrowser.Services;

public class OpcDaBackgroundService : BackgroundService
{
    private readonly OpcDaService _opcDaService;
    private readonly TrendDataService _trendDataService;
    private readonly IHubContext<OpcDaHub> _hubContext;
    private readonly ILogger<OpcDaBackgroundService> _logger;

    public OpcDaBackgroundService(
        OpcDaService opcDaService,
        TrendDataService trendDataService,
        IHubContext<OpcDaHub> hubContext,
        ILogger<OpcDaBackgroundService> logger)
    {
        _opcDaService = opcDaService;
        _trendDataService = trendDataService;
        _hubContext = hubContext;
        _logger = logger;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        _logger.LogInformation("OPC DA Background Service started");

        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                if (_opcDaService.IsConnected && _opcDaService.MonitoredTagCount > 0)
                {
                    var values = _opcDaService.ReadTagValues();
                    
                    if (values.Any())
                    {
                        // Send to SignalR clients
                        await _hubContext.Clients.All.SendAsync("ReceiveTagValues", values, stoppingToken);
                        
                        // Store in trend data service
                        foreach (var value in values)
                        {
                            _trendDataService.AddDataPoint(value.ItemID, value.Value, value.Quality, value.Timestamp);
                        }
                    }
                }
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error reading tag values");
            }

            await Task.Delay(1000, stoppingToken);
        }

        _logger.LogInformation("OPC DA Background Service stopped");
    }
}
