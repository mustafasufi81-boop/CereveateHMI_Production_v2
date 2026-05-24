namespace OpcDaWebBrowser.Services.OpcUa;

/// <summary>
/// OPC UA server discovery service
/// Separate from COM-based OPC DA discovery
/// </summary>
public class OpcUaDiscovery
{
    private readonly ILogger<OpcUaDiscovery> _logger;

    public OpcUaDiscovery(ILogger<OpcUaDiscovery> logger)
    {
        _logger = logger;
    }

    /// <summary>
    /// Discover OPC UA servers on the network
    /// For now returns known endpoints - can be extended with mDNS discovery
    /// </summary>
    public List<OpcUaServerInfo> DiscoverServers(string? hostname = null)
    {
        _logger.LogInformation("🔍 [OPC UA Discovery] Discovering UA servers on {Host}", hostname ?? "localhost");

        var servers = new List<OpcUaServerInfo>();

        // Known OPC UA endpoints (can be extended)
        var knownEndpoints = new[]
        {
            new OpcUaServerInfo
            {
                Endpoint = "opc.tcp://localhost:4840/OPCUniversalServer",
                Description = "OPC Universal Server (Local)",
                ServerName = "OPCUniversalServer",
                IsAvailable = true
            },
            new OpcUaServerInfo
            {
                Endpoint = "opc.tcp://localhost:4005",
                Description = "Rockwell OPC DA Server (Local)",
                ServerName = "RockwellOpcDaServer",
                IsAvailable = false
            },
            new OpcUaServerInfo
            {
                Endpoint = "opc.tcp://localhost:4840",
                Description = "Default OPC UA Server (Local)",
                ServerName = "Generic UA Server",
                IsAvailable = false
            }
        };

        servers.AddRange(knownEndpoints);

        // If hostname provided, add remote endpoints
        if (!string.IsNullOrEmpty(hostname) && hostname != "localhost" && hostname != Environment.MachineName)
        {
            servers.Add(new OpcUaServerInfo
            {
                Endpoint = $"opc.tcp://{hostname}:4840/OPCUniversalServer",
                Description = $"OPC Universal Server ({hostname})",
                ServerName = "OPCUniversalServer",
                IsAvailable = false
            });

            servers.Add(new OpcUaServerInfo
            {
                Endpoint = $"opc.tcp://{hostname}:4005",
                Description = $"Rockwell OPC DA Server ({hostname})",
                ServerName = "RockwellOpcDaServer",
                IsAvailable = false
            });

            servers.Add(new OpcUaServerInfo
            {
                Endpoint = $"opc.tcp://{hostname}:4840",
                Description = $"Generic UA Server ({hostname})",
                ServerName = "Generic UA Server",
                IsAvailable = false
            });
        }

        _logger.LogInformation("✅ [OPC UA Discovery] Found {Count} known endpoints", servers.Count);
        return servers;
    }

    /// <summary>
    /// Get default/recommended endpoint for quick connect
    /// </summary>
    public string GetDefaultEndpoint()
    {
        return "opc.tcp://localhost:4840/OPCUniversalServer";
    }
}

/// <summary>
/// OPC UA server information
/// </summary>
public class OpcUaServerInfo
{
    public string Endpoint { get; set; } = "";
    public string Description { get; set; } = "";
    public string ServerName { get; set; } = "";
    public bool IsAvailable { get; set; }
}
