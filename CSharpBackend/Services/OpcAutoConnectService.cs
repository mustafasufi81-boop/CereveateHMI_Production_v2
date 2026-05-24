using System.Diagnostics;

namespace OpcDaWebBrowser.Services;

/// <summary>
/// Background service that automatically restores OPC server connection and monitored tags on startup
/// </summary>
public class OpcAutoConnectService : BackgroundService
{
    private readonly OpcDaService _opcDaService;
    private readonly LoggingConfigService _configService;
    private readonly ILogger<OpcAutoConnectService> _logger;
    private readonly HashSet<string> _restoredTags = new(StringComparer.OrdinalIgnoreCase);
    private string? _lastAppliedConnectionSignature;
    private int _consecutiveFailures;

    private static readonly TimeSpan InitialDelay = TimeSpan.FromSeconds(3);
    private static readonly TimeSpan SteadyStateDelay = TimeSpan.FromSeconds(15);
    private static readonly TimeSpan MinimumRetryDelay = TimeSpan.FromSeconds(5);
    private const int MaxRetryDelaySeconds = 60;
    private const int RestoreBatchSize = 500;

    public OpcAutoConnectService(
        OpcDaService opcDaService,
        LoggingConfigService configService,
        ILogger<OpcAutoConnectService> logger)
    {
        _opcDaService = opcDaService;
        _configService = configService;
        _logger = logger;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        _logger.LogInformation("OpcAutoConnectService starting background auto-connect loop");

        try
        {
            await Task.Delay(InitialDelay, stoppingToken);
        }
        catch (OperationCanceledException)
        {
            return;
        }

        while (!stoppingToken.IsCancellationRequested)
        {
            bool healthyCycle = false;

            try
            {
                healthyCycle = await RunAutoConnectCycleAsync(stoppingToken);
                _consecutiveFailures = healthyCycle ? 0 : _consecutiveFailures + 1;
            }
            catch (OperationCanceledException)
            {
                break;
            }
            catch (Exception ex)
            {
                _consecutiveFailures++;
                _logger.LogWarning(ex, "Unexpected error in auto-connect cycle; will retry");
            }

            var delay = healthyCycle
                ? SteadyStateDelay
                : TimeSpan.FromSeconds(Math.Min(MaxRetryDelaySeconds, MinimumRetryDelay.TotalSeconds + (_consecutiveFailures * 5)));

            try
            {
                await Task.Delay(delay, stoppingToken);
            }
            catch (OperationCanceledException)
            {
                break;
            }
        }

        _logger.LogInformation("OpcAutoConnectService stopping; clearing restored tag cache");
        _restoredTags.Clear();
        _lastAppliedConnectionSignature = null;
    }

    private async Task<bool> RunAutoConnectCycleAsync(CancellationToken stoppingToken)
    {
        var config = _configService.GetConfig();

        if (string.IsNullOrWhiteSpace(config.ServerProgId))
        {
            if (_opcDaService.IsConnected)
            {
                _logger.LogInformation("Auto-connect: no server configured, disconnecting active OPC session");
                _opcDaService.Disconnect();
                _restoredTags.Clear();
                _lastAppliedConnectionSignature = null;
            }

            return false;
        }

        var desiredSignature = BuildConnectionSignature(config);

        if (_lastAppliedConnectionSignature != null && !_lastAppliedConnectionSignature.Equals(desiredSignature, StringComparison.Ordinal))
        {
            _logger.LogInformation("Auto-connect: server settings changed; reconnecting to new endpoint");
            _opcDaService.Disconnect();
            _restoredTags.Clear();
            _lastAppliedConnectionSignature = null;
        }

        if (!_opcDaService.IsConnected)
        {
            var connected = await TryConnectAsync(config, stoppingToken);
            if (!connected)
            {
                return false;
            }

            _lastAppliedConnectionSignature = desiredSignature;
        }

        await SyncMonitoredTagsAsync(config, stoppingToken);
        return true;
    }

    private async Task<bool> TryConnectAsync(LoggingConfig config, CancellationToken stoppingToken)
    {
        var progId = _configService.GetDecryptedProgId();
        var host = _configService.GetDecryptedHost();
        var clsid = _configService.GetDecryptedClsid();
        var maskedHost = _configService.GetMaskedHost();

        if (string.IsNullOrWhiteSpace(clsid))
        {
            _logger.LogInformation("Auto-connect: attempting OPC connection to {ProgId} on {Host}", progId, maskedHost);
        }
        else
        {
            _logger.LogInformation("Auto-connect: attempting OPC connection to {ProgId} on {Host} using CLSID {Clsid}", progId, maskedHost, clsid);
        }

        try
        {
            await Task.Run(() => _opcDaService.Connect(progId, host, clsid), stoppingToken);
            _logger.LogInformation("Auto-connect: OPC server connected successfully");
            return true;
        }
        catch (OperationCanceledException)
        {
            throw;
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Auto-connect: failed to connect to OPC server {ProgId} on {Host}", progId, maskedHost);
            return false;
        }
    }

    private async Task SyncMonitoredTagsAsync(LoggingConfig config, CancellationToken stoppingToken)
    {
        var desiredTags = config.MonitoredTags
            .Where(tag => !string.IsNullOrWhiteSpace(tag))
            .Select(tag => tag.Trim())
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToList();

        if (desiredTags.Count == 0)
        {
            if (_restoredTags.Count > 0)
            {
                _logger.LogInformation("Auto-connect: no monitored tags configured, clearing {Count} previously restored tags", _restoredTags.Count);
                foreach (var tag in _restoredTags.ToList())
                {
                    _opcDaService.RemoveTagFromMonitor(tag);
                }
                _restoredTags.Clear();
            }
            return;
        }

        // Remove tags that are no longer desired
        if (_restoredTags.Count > 0)
        {
            var desiredSet = new HashSet<string>(desiredTags, StringComparer.OrdinalIgnoreCase);
            var tagsToRemove = _restoredTags.Where(tag => !desiredSet.Contains(tag)).ToList();

            if (tagsToRemove.Count > 0)
            {
                foreach (var tag in tagsToRemove)
                {
                    try
                    {
                        _opcDaService.RemoveTagFromMonitor(tag);
                    }
                    catch (Exception ex)
                    {
                        _logger.LogDebug(ex, "Auto-connect: failed to remove tag {Tag} during sync", tag);
                    }
                    finally
                    {
                        _restoredTags.Remove(tag);
                    }
                }

                _logger.LogInformation("Auto-connect: removed {RemovedCount} monitored tags no longer configured (active: {ActiveCount})", tagsToRemove.Count, _restoredTags.Count);
            }
        }

        var tagsToAdd = desiredTags.Where(tag => !_restoredTags.Contains(tag)).ToList();
        if (tagsToAdd.Count == 0)
        {
            return;
        }

        var sw = Stopwatch.StartNew();
        int processed = 0;

        foreach (var batch in tagsToAdd.Chunk(RestoreBatchSize))
        {
            stoppingToken.ThrowIfCancellationRequested();

            foreach (var tag in batch)
            {
                try
                {
                    var displayName = GetDisplayName(tag);
                    _opcDaService.AddTagToMonitor(tag, displayName);
                    _restoredTags.Add(tag);
                }
                catch (Exception ex)
                {
                    _logger.LogWarning(ex, "Auto-connect: failed to restore monitored tag {Tag}", tag);
                }
            }

            processed += batch.Length;

            if (processed == tagsToAdd.Count || processed % 5000 == 0)
            {
                _logger.LogInformation("Auto-connect: restored {Processed}/{Total} monitored tags (active total: {Active})", processed, tagsToAdd.Count, _restoredTags.Count);
            }

            if (tagsToAdd.Count > RestoreBatchSize)
            {
                await Task.Delay(TimeSpan.FromMilliseconds(10), stoppingToken);
            }
        }

        sw.Stop();
        _logger.LogInformation("Auto-connect: finished restoring {AddedCount} monitored tags in {ElapsedMs} ms (active total: {ActiveTotal})", tagsToAdd.Count, sw.ElapsedMilliseconds, _restoredTags.Count);
    }

    private static string BuildConnectionSignature(LoggingConfig config)
    {
        var host = string.IsNullOrWhiteSpace(config.ServerHost) ? "localhost" : config.ServerHost.Trim();
        var clsid = string.IsNullOrWhiteSpace(config.ServerClsid) ? string.Empty : config.ServerClsid.Trim();
        return $"{config.ServerProgId?.Trim()}|{host}|{clsid}";
    }

    private static string GetDisplayName(string tagId)
    {
        var trimmed = tagId.Trim();
        if (string.IsNullOrEmpty(trimmed))
        {
            return tagId;
        }

        var lastDot = trimmed.LastIndexOf('.');
        return lastDot >= 0 && lastDot < trimmed.Length - 1
            ? trimmed[(lastDot + 1)..]
            : trimmed;
    }
}
