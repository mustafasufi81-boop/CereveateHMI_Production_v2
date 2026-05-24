using System.Collections.Concurrent;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;
using OpcRcw.Da;
using OpcRcw.Comn;
using OpcDaWebBrowser.Services.Health;

namespace OpcDaWebBrowser.Services;

/// <summary>
/// Multi-server OPC DA manager - handles multiple concurrent connections
/// Each connection has independent polling via Timer
/// </summary>
public class OpcDaService
{
    private readonly ConcurrentDictionary<string, OpcServerConnection> _connections = new();
    private readonly ILogger<OpcDaService> _logger;
    private readonly ILoggerFactory _loggerFactory;
    private readonly IHealthStatusService? _healthService;
    private readonly LoggingConfigService _configService;
    private long _lastUiBroadcastTicks = 0;

    public event EventHandler<TagValuesEventArgs>? TagValuesUpdated;

    public OpcDaService(ILogger<OpcDaService> logger, ILoggerFactory loggerFactory, LoggingConfigService configService, IHealthStatusService? healthService = null)
    {
        _logger = logger;
        _loggerFactory = loggerFactory;
        _configService = configService;
        _healthService = healthService;
    }

    public int ConnectionCount => _connections.Count;
    public int TotalMonitoredTags => _connections.Values.Sum(c => c.MonitoredTagCount);

    /// <summary>
    /// Get the preferred active OPC connection (most recently connected) for historian use
    /// </summary>
    public OpcServerConnection? GetActiveConnection()
    {
        return _connections.Values
            .Where(c => c.IsConnected)
            .OrderByDescending(c => c.ConnectedAt)
            .FirstOrDefault();
    }

    /// <summary>
    /// Get all current OPC connections (connected and disconnected)
    /// </summary>
    public List<ServerConnectionInfo> GetAllConnections()
    {
        return _connections.Values.Select(c => new ServerConnectionInfo
        {
            ConnectionId = c.ConnectionId,
            ServerProgID = c.ServerProgID,
            Host = c.Host,
            IsLocal = c.IsLocal,
            IsConnected = c.IsConnected,
            Status = c.Status,
            ConnectedAt = c.ConnectedAt,
            LastPollTime = c.LastPollTime,
            MonitoredTagCount = c.MonitoredTagCount
        }).ToList();
    }

    public List<string> DiscoverServers()
    {
        List<string> serverList = new();

        string[] knownServers = new[]
        {
            "Matrikon.OPC.Simulation.1",
            "Kepware.KEPServerEX.V6",
            "OPC.SimaticNet",
            "RSLinx OPC Server",
            "Iconics.OPCServer",
            "MCS.OPCServer.1",
            "OPC.DeltaV.1"
        };

        foreach (string server in knownServers)
        {
            try
            {
                Type? serverType = Type.GetTypeFromProgID(server);
                if (serverType != null)
                {
                    serverList.Add(server);
                }
            }
            catch { }
        }

        return serverList;
    }

    public List<RemoteServerInfo> DiscoverRemoteServers(string host)
    {
        if (string.IsNullOrWhiteSpace(host))
            throw new ArgumentException("Host cannot be empty");

        // Run discovery on a worker thread with timeout to avoid blocking request threads
        var cts = new CancellationTokenSource(TimeSpan.FromSeconds(10));
        var task = Task.Run(() => DiscoverRemoteServersInternal(host), cts.Token);

        if (task.Wait(TimeSpan.FromSeconds(10)))
            return task.Result;

        _logger.LogWarning("Remote discovery timed out on {Host}", host);
        return new List<RemoteServerInfo>();
    }

    private List<RemoteServerInfo> DiscoverRemoteServersInternal(string host)
    {
        List<RemoteServerInfo> servers = new();

        try
        {
            _logger.LogDebug("[OPC DISCOVERY] Attempting OPCEnum on {Host}...", host);
            Guid catid = new Guid("63D5F432-CFE4-11d1-B2C8-0060083BA1FB");
            Type? enumType = Type.GetTypeFromProgID("OPC.ServerList.1", host);
            _logger.LogDebug("[OPC DISCOVERY] Type.GetTypeFromProgID result: {Result}", enumType != null ? "SUCCESS" : "NULL");

            if (enumType == null)
            {
                _logger.LogWarning("OPC.ServerList.1 not found on {Host}", host);
                return servers;
            }

            object enumObj = Activator.CreateInstance(enumType)!;
            IOPCServerList serverList = (IOPCServerList)enumObj;

            _logger.LogDebug("Calling EnumClassesOfCategories on {Host}", host);
            serverList.EnumClassesOfCategories(1, new Guid[] { catid }, 0, null!, out object enumGuidObj);

            if (enumGuidObj == null)
            {
                _logger.LogWarning("EnumClassesOfCategories returned null on {Host}", host);
                Marshal.ReleaseComObject(enumObj);
                return servers;
            }

            _logger.LogDebug("Casting to IEnumGUID on {Host}", host);
            OpcRcw.Comn.IEnumGUID enumGuid = (OpcRcw.Comn.IEnumGUID)enumGuidObj;
            Guid[] clsids = new Guid[10];

            while (true)
            {
                enumGuid.Next(10, clsids, out int fetched);
                if (fetched == 0) break;

                for (int i = 0; i < fetched; i++)
                {
                    try
                    {
                        serverList.GetClassDetails(ref clsids[i], out string progID, out string description);
                        servers.Add(new RemoteServerInfo
                        {
                            ProgID = progID,
                            Description = description,
                            CLSID = clsids[i],
                            Host = host
                        });
                    }
                    catch { }
                }

                if (fetched < 10) break;
            }

            Marshal.FinalReleaseComObject(enumGuid);
            Marshal.FinalReleaseComObject(enumObj);
            
            _logger.LogInformation("Discovered {Count} servers on {Host}", servers.Count, host);
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Remote discovery failed on {Host}", host);
        }

        return servers;
    }

    public string AddServerConnection(string serverProgID, string host = "", string clsid = "", int pollingIntervalMs = 1000)
    {
        string connectionId = string.IsNullOrEmpty(host) ? serverProgID : $"{serverProgID}@{host}";

        // If connection exists, remove it first to force a fresh connection
        if (_connections.ContainsKey(connectionId))
        {
            _logger.LogInformation($"Removing existing connection: {connectionId}");
            if (_connections.TryRemove(connectionId, out var oldConnection))
            {
                oldConnection.Disconnect();
                oldConnection.Dispose();
            }

            // Encourage COM cleanup without blocking
            GC.Collect(GC.MaxGeneration, GCCollectionMode.Optimized, blocking: false, compacting: false);
        }

        var connectionLogger = _loggerFactory.CreateLogger<OpcServerConnection>();
        var connection = new OpcServerConnection(serverProgID, host, clsid, pollingIntervalMs, connectionLogger, _healthService);
        
        connection.TagValuesUpdated += (sender, args) =>
        {
            var now = Environment.TickCount64;
            var uiBroadcastInterval = _configService.GetConfig().PerformanceIntervals?.UiBroadcastIntervalMs ?? 1000;
            if (now - _lastUiBroadcastTicks >= uiBroadcastInterval)
            {
                _lastUiBroadcastTicks = now;
                TagValuesUpdated?.Invoke(this, args);
            }
        };

        _connections[connectionId] = connection;
        _logger.LogInformation($"Added server connection: {connectionId}");
        
        return connectionId;
    }

    public void ConnectServer(string connectionId)
    {
        if (_connections.TryGetValue(connectionId, out var connection))
        {
            connection.Connect();
            _logger.LogInformation($"Connected to {connectionId}");
        }
        else
        {
            throw new Exception($"Connection {connectionId} not found");
        }
    }

    public void DisconnectServer(string connectionId)
    {
        if (_connections.TryGetValue(connectionId, out var connection))
        {
            connection.Disconnect();
            _logger.LogInformation($"Disconnected from {connectionId}");
        }
    }

    public void RemoveServerConnection(string connectionId)
    {
        if (_connections.TryRemove(connectionId, out var connection))
        {
            connection.Dispose();
            _logger.LogInformation($"Removed server connection: {connectionId}");
        }
    }

    public List<TagInfo> BrowseTags(string connectionId)
    {
        if (_connections.TryGetValue(connectionId, out var connection))
        {
            return connection.BrowseTags();
        }
        throw new Exception($"Connection {connectionId} not found");
    }

    public List<TagInfo> BrowseAllTags()
    {
        var allTags = new List<TagInfo>();
        foreach (var connection in _connections.Values.Where(c => c.IsConnected))
        {
            try
            {
                allTags.AddRange(connection.BrowseTags());
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, $"Error browsing tags for {connection.ConnectionId}");
            }
        }
        return allTags;
    }

    public void AddTagToMonitor(string connectionId, string itemID, string displayName)
    {
        if (_connections.TryGetValue(connectionId, out var connection))
        {
            connection.AddTag(itemID, displayName);
        }
        else
        {
            throw new Exception($"Connection {connectionId} not found");
        }
    }

    public void RemoveTagFromMonitor(string connectionId, string itemID)
    {
        if (_connections.TryGetValue(connectionId, out var connection))
        {
            connection.RemoveTag(itemID);
        }
    }

    public List<TagValue> ReadAllTagValues()
    {
        var allValues = new List<TagValue>();

        foreach (var connection in _connections.Values.Where(c => c.IsConnected))
        {
            try
            {
                var snapshot = connection.GetCachedValues();
                if (snapshot != null && snapshot.Count > 0)
                    allValues.AddRange(snapshot);
            }
            catch (Exception ex)
            {
                _logger.LogWarning(ex, "Cached read failed for {Connection}", connection.ConnectionId);
            }
        }

        return allValues;
    }

    // Legacy compatibility methods for existing Hub/Controller code
    public bool IsConnected => _connections.Any(c => c.Value.IsConnected);
    public string? CurrentServer => _connections.FirstOrDefault(c => c.Value.IsConnected).Key;
    public int MonitoredTagCount => TotalMonitoredTags;

    public void Connect(string serverProgID, string host = "", string clsid = "")
    {
        string connectionId = AddServerConnection(serverProgID, host, clsid);
        ConnectServer(connectionId);
    }

    public void Disconnect()
    {
        // Disconnect and remove all connections
        foreach (var kvp in _connections.ToList())
        {
            kvp.Value.Disconnect();
            kvp.Value.Dispose();
        }
        _connections.Clear();
        _logger.LogInformation("Disconnected and cleared all server connections");
    }

    public List<TagInfo> BrowseTags()
    {
        return BrowseAllTags();
    }

    public bool IsAnyServerConnected()
    {
        return _connections.Any(c => c.Value.IsConnected);
    }

    public void AddTagToMonitor(string itemID, string displayName)
    {
        var firstConnected = _connections.FirstOrDefault(c => c.Value.IsConnected).Value;
        if (firstConnected != null)
        {
            firstConnected.AddTag(itemID, displayName);
        }
    }

    public void RemoveTagFromMonitor(string itemID)
    {
        foreach (var connection in _connections.Values)
        {
            connection.RemoveTag(itemID);
        }
    }

    public List<TagValue> ReadTagValues()
    {
        return ReadAllTagValues();
    }
}

public class ServerConnectionInfo
{
    public required string ConnectionId { get; set; }
    public required string ServerProgID { get; set; }
    public required string Host { get; set; }
    public required bool IsLocal { get; set; }
    public required bool IsConnected { get; set; }
    public required string Status { get; set; }
    public required DateTime ConnectedAt { get; set; }
    public required DateTime LastPollTime { get; set; }
    public required int MonitoredTagCount { get; set; }
}
