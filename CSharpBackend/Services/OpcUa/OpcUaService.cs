using System.Collections.Concurrent;
using Npgsql;
using Opc.UaFx;
using Opc.UaFx.Client;
using OpcDaWebBrowser.Services.HistorianIngest.Config;

namespace OpcDaWebBrowser.Services.OpcUa;

/// <summary>
/// Industrial-grade OPC UA client service
/// Completely independent from OPC DA pipeline
/// Follows same patterns as HistorianIngestHostedService for reliability
/// </summary>
public class OpcUaService : IDisposable
{
    private readonly ILogger<OpcUaService> _logger;
    private readonly HistorianConfig _config;
    
    private OpcClient? _client;
    private Timer? _pollTimer;
    private CancellationTokenSource? _pollingCts;
    
    private readonly ConcurrentDictionary<string, OpcValue> _tagValues = new();
    private readonly List<string> _monitoredTags = new();
    
    private bool _isConnected;
    private string _endpoint = "";
    private DateTime _connectedAt;
    
    // Performance tracking
    private long _totalSamplesRead;
    private long _totalSamplesWritten;
    private long _totalErrors;
    
    public OpcUaService(ILogger<OpcUaService> logger, HistorianConfig config)
    {
        _logger = logger;
        _config = config;
    }

    public bool IsConnected => _isConnected;
    public int MonitoredTagCount => _monitoredTags.Count;
    public string Endpoint => _endpoint;
    public DateTime ConnectedAt => _connectedAt;

    /// <summary>
    /// Connect to OPC UA server with proper error handling
    /// </summary>
    public async Task<bool> ConnectAsync(string endpoint, CancellationToken ct = default)
    {
        try
        {
            _logger.LogInformation("🔵 [OPC UA] Connecting to {Endpoint}...", endpoint);
            _endpoint = endpoint;

            _client = new OpcClient(endpoint);
            
            // Security settings for industrial environments
            _client.Security.AutoAcceptUntrustedCertificates = true;
            
            await Task.Run(() => _client.Connect(), ct);
            
            _isConnected = true;
            _connectedAt = DateTime.UtcNow;
            
            _logger.LogInformation("✅ [OPC UA] Connected successfully to {Endpoint}", endpoint);
            
            return true;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "❌ [OPC UA] Failed to connect to {Endpoint}", endpoint);
            _totalErrors++;
            return false;
        }
    }

    /// <summary>
    /// Browse all available tags from UA server
    /// Simplified version - recursively browses and collects all node IDs
    /// </summary>
    public List<string> BrowseTags()
    {
        if (_client == null || !_isConnected)
        {
            _logger.LogWarning("⚠️ [OPC UA] Not connected - cannot browse tags");
            return new List<string>();
        }

        try
        {
            var tags = new List<string>();
            var rootNode = _client.BrowseNode(OpcObjectTypes.ObjectsFolder);

            BrowseNodeRecursive(rootNode, tags);

            // Prefer non-system namespaces first (ns != 0/1)
            var ordered = tags
                .Distinct()
                .OrderBy(id => IsSystemNamespace(id) ? 1 : 0)
                .ThenBy(id => id)
                .ToList();

            if (ordered.Count == 0)
            {
                _logger.LogWarning("⚠️ [OPC UA] Browse returned 0 tags");
            }
            _logger.LogInformation("📋 [OPC UA] Discovered {Count} tags (non-system first)", ordered.Count);
            return ordered;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "❌ [OPC UA] Browse failed");
            _totalErrors++;
            return new List<string>();
        }
    }

    /// <summary>
    /// Browse with display names for UI selection (returns NodeId + DisplayName)
    /// </summary>
    public List<TagInfo> BrowseTagsWithNames()
    {
        if (_client == null || !_isConnected)
        {
            _logger.LogWarning("⚠️ [OPC UA] Not connected - cannot browse tags");
            return new List<TagInfo>();
        }

        try
        {
            var tags = new List<TagInfo>();
            var rootNode = _client.BrowseNode(OpcObjectTypes.ObjectsFolder);

            BrowseNodeRecursiveWithNames(rootNode, tags);

            var ordered = tags
                .GroupBy(t => t.NodeId)
                .Select(g => g.First())
                .OrderBy(t => IsSystemNamespace(t.NodeId) ? 1 : 0)
                .ThenBy(t => t.DisplayName)
                .ToList();

            if (ordered.Count == 0)
            {
                _logger.LogWarning("⚠️ [OPC UA] Browse-with-names returned 0 tags");
            }
            _logger.LogInformation("📋 [OPC UA] Discovered {Count} tags (with names, non-system first)", ordered.Count);
            return ordered;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "❌ [OPC UA] Browse-with-names failed");
            _totalErrors++;
            return new List<TagInfo>();
        }
    }

    private void BrowseNodeRecursive(OpcNodeInfo node, List<string> tags, int depth = 0)
    {
        if (depth > 15) return;

        try
        {
            foreach (var child in node.Children())
            {
                var nodeId = child.NodeId.ToString();
                tags.Add(nodeId);
                BrowseNodeRecursive(child, tags, depth + 1);
            }
        }
        catch (Exception ex)
        {
            _logger.LogDebug("Browse node {NodeId} failed: {Error}", node.NodeId, ex.Message);
        }
    }

    private void BrowseNodeRecursiveWithNames(OpcNodeInfo node, List<TagInfo> tags, int depth = 0)
    {
        if (depth > 15) return;

        try
        {
            foreach (var child in node.Children())
            {
                var nodeId = child.NodeId.ToString();
                var displayName = child.DisplayName?.ToString() ?? nodeId;
                
                tags.Add(new TagInfo
                {
                    NodeId = nodeId,
                    DisplayName = displayName
                });
                
                BrowseNodeRecursiveWithNames(child, tags, depth + 1);
            }
        }
        catch (Exception ex)
        {
            _logger.LogDebug("Browse node {NodeId} failed: {Error}", node.NodeId, ex.Message);
        }
    }

    private static bool IsSystemNamespace(string nodeId)
    {
        // Fast check: ns=0 or ns=1 are standard namespaces
        // Patterns: "ns=0;i=2253" or "i=2253" (defaults to ns=0)
        if (nodeId.StartsWith("ns=0", StringComparison.OrdinalIgnoreCase) || nodeId.StartsWith("ns=1", StringComparison.OrdinalIgnoreCase))
            return true;
        if (nodeId.StartsWith("i=", StringComparison.OrdinalIgnoreCase))
            return true; // implicit namespace 0
        return false;
    }

    /// <summary>
    /// Start monitoring tags with timer-based polling (same pattern as OPC DA)
    /// </summary>
    public void StartMonitoring(List<string> tagIds, int intervalMs = 1000)
    {
        lock (_monitoredTags)
        {
            _monitoredTags.Clear();
            _monitoredTags.AddRange(tagIds);
        }
        
        _logger.LogInformation("🔄 [OPC UA] Monitoring {Count} tags @ {Interval}ms", tagIds.Count, intervalMs);

        _pollingCts = new CancellationTokenSource();
        _pollTimer = new Timer(OnPollTimerCallback, null, TimeSpan.Zero, TimeSpan.FromMilliseconds(intervalMs));
    }

    /// <summary>
    /// Timer callback - reads tags and writes to historian DB
    /// Follows same pattern as HistorianIngestHostedService polling loop
    /// </summary>
    private void OnPollTimerCallback(object? state)
    {
        if (_client == null || !_isConnected || _pollingCts == null || _pollingCts.Token.IsCancellationRequested)
            return;

        List<string> currentTags;
        lock (_monitoredTags)
        {
            if (_monitoredTags.Count == 0) return;
            currentTags = new List<string>(_monitoredTags);
        }

        try
        {
            var samples = new List<TagSample>();

            foreach (var tagId in currentTags)
            {
                try
                {
                    var value = _client.ReadNode(tagId);
                    var timestamp = DateTime.UtcNow; // Use current time since value.Timestamp may not be available
                    
                    samples.Add(new TagSample
                    {
                        TagId = tagId,
                        Value = value.Value,
                        Timestamp = timestamp,
                        Quality = (int)value.Status.Code
                    });
                    
                    // Cache in memory
                    _tagValues[tagId] = value;
                    _totalSamplesRead++;
                }
                catch (Exception ex)
                {
                    _logger.LogDebug("[OPC UA] Read failed for {TagId}: {Error}", tagId, ex.Message);
                    _totalErrors++;
                }
            }

            // Write to historian DB
            if (samples.Count > 0)
            {
                _ = WriteToHistorianAsync(samples, _pollingCts.Token);
            }
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "❌ [OPC UA] Poll timer error");
            _totalErrors++;
        }
    }

    /// <summary>
    /// Write samples to historian DB using COPY BINARY (same as historian pipeline)
    /// </summary>
    private async Task WriteToHistorianAsync(List<TagSample> samples, CancellationToken ct)
    {
        try
        {
            await using var conn = new NpgsqlConnection(_config.Database.ConnectionString);
            await conn.OpenAsync(ct);

            await using var writer = conn.BeginBinaryImport(
                "COPY historian_raw.historian_timeseries (time, tag_id, value_num, value_text, value_bool, quality, sample_source, mapping_version) FROM STDIN BINARY");

            foreach (var sample in samples)
            {
                await writer.StartRowAsync(ct);
                
                // time
                await writer.WriteAsync(sample.Timestamp, NpgsqlTypes.NpgsqlDbType.TimestampTz, ct);
                
                // tag_id
                await writer.WriteAsync(sample.TagId, NpgsqlTypes.NpgsqlDbType.Text, ct);
                
                // value columns (value_num, value_text, value_bool)
                if (sample.Value is double or float or decimal or int or long or short)
                {
                    await writer.WriteAsync(Convert.ToDouble(sample.Value), NpgsqlTypes.NpgsqlDbType.Double, ct);
                    await writer.WriteAsync(DBNull.Value, NpgsqlTypes.NpgsqlDbType.Text, ct);
                    await writer.WriteAsync(DBNull.Value, NpgsqlTypes.NpgsqlDbType.Boolean, ct);
                }
                else if (sample.Value is bool boolValue)
                {
                    await writer.WriteAsync(DBNull.Value, NpgsqlTypes.NpgsqlDbType.Double, ct);
                    await writer.WriteAsync(DBNull.Value, NpgsqlTypes.NpgsqlDbType.Text, ct);
                    await writer.WriteAsync(boolValue, NpgsqlTypes.NpgsqlDbType.Boolean, ct);
                }
                else
                {
                    await writer.WriteAsync(DBNull.Value, NpgsqlTypes.NpgsqlDbType.Double, ct);
                    await writer.WriteAsync(sample.Value?.ToString() ?? "", NpgsqlTypes.NpgsqlDbType.Text, ct);
                    await writer.WriteAsync(DBNull.Value, NpgsqlTypes.NpgsqlDbType.Boolean, ct);
                }
                
                // quality
                await writer.WriteAsync(sample.Quality, NpgsqlTypes.NpgsqlDbType.Integer, ct);
                
                // sample_source
                await writer.WriteAsync("OPC_UA", NpgsqlTypes.NpgsqlDbType.Text, ct);
                
                // mapping_version
                await writer.WriteAsync(1, NpgsqlTypes.NpgsqlDbType.Integer, ct);
            }

            await writer.CompleteAsync(ct);
            
            _totalSamplesWritten += samples.Count;
            
            _logger.LogDebug("✅ [OPC UA] Wrote {Count} samples to historian (Total: {Total})", 
                samples.Count, _totalSamplesWritten);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "❌ [OPC UA] Historian write failed");
            _totalErrors++;
        }
    }

    /// <summary>
    /// Get current tag values for API endpoints
    /// </summary>
    public Dictionary<string, object?> GetTagValues(List<string>? tagIds = null)
    {
        var result = new Dictionary<string, object?>();
        
        var tags = tagIds ?? _monitoredTags.ToList();
        
        foreach (var tagId in tags)
        {
            if (_tagValues.TryGetValue(tagId, out var value))
            {
                result[tagId] = value.Value;
            }
        }
        
        return result;
    }

    /// <summary>
    /// Get service statistics
    /// </summary>
    public ServiceStats GetStats()
    {
        return new ServiceStats
        {
            IsConnected = _isConnected,
            Endpoint = _endpoint,
            ConnectedAt = _connectedAt,
            MonitoredTagCount = _monitoredTags.Count,
            TotalSamplesRead = _totalSamplesRead,
            TotalSamplesWritten = _totalSamplesWritten,
            TotalErrors = _totalErrors
        };
    }

    /// <summary>
    /// Disconnect gracefully
    /// </summary>
    public void Disconnect()
    {
        try
        {
            _logger.LogInformation("🔴 [OPC UA] Disconnecting from {Endpoint}...", _endpoint);
            
            _pollingCts?.Cancel();
            _pollTimer?.Dispose();
            _pollTimer = null;
            
            _client?.Disconnect();
            _client?.Dispose();
            _client = null;
            
            _isConnected = false;
            _tagValues.Clear();
            
            lock (_monitoredTags)
            {
                _monitoredTags.Clear();
            }
            
            _logger.LogInformation("✅ [OPC UA] Disconnected successfully");
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "❌ [OPC UA] Disconnect error");
        }
    }

    public void Dispose()
    {
        Disconnect();
        _pollingCts?.Dispose();
        GC.SuppressFinalize(this);
    }
}

/// <summary>
/// Tag sample structure
/// </summary>
public class TagSample
{
    public required string TagId { get; init; }
    public object? Value { get; init; }
    public DateTime Timestamp { get; init; }
    public int Quality { get; init; }
}

/// <summary>
/// Service statistics
/// </summary>
public class ServiceStats
{
    public bool IsConnected { get; init; }
    public string Endpoint { get; init; } = "";
    public DateTime ConnectedAt { get; init; }
    public int MonitoredTagCount { get; init; }
    public long TotalSamplesRead { get; init; }
    public long TotalSamplesWritten { get; init; }
    public long TotalErrors { get; init; }
}

/// <summary>
/// Tag info with display name for UI selection
/// </summary>
public class TagInfo
{
    public string NodeId { get; init; } = "";
    public string DisplayName { get; init; } = "";
}
