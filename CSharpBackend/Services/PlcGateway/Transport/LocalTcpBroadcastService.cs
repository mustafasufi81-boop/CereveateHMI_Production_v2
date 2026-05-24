using System.Collections.Concurrent;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Text.Json;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using PlcGateway.Services;

namespace PlcGateway.Transport;

/// <summary>
/// LOCAL TCP Broadcast Server - NO CLOUD, NO INTERNET, NO THIRD PARTY
/// 
/// PURPOSE:
/// - Broadcasts PLC data to clients on YOUR LOCAL NETWORK ONLY
/// - No external broker required (like Mosquitto)
/// - No data leaves your network
/// - Clients connect directly to this server
/// 
/// HOW IT WORKS:
/// ┌─────────────────────────────────────────────────────────────────┐
/// │                     YOUR LOCAL NETWORK                          │
/// │                                                                 │
/// │   ┌───────────────┐        TCP Port 5050                       │
/// │   │  This Server  │◄────────────────────────────────┐          │
/// │   │  (C# App)     │                                 │          │
/// │   └───────┬───────┘                                 │          │
/// │           │                                         │          │
/// │           ▼                                         │          │
/// │   ┌───────────────┐     ┌───────────────┐    ┌─────┴─────┐   │
/// │   │  HMI Client   │     │  Python App   │    │  Browser  │   │
/// │   │  (192.168.x.x)│     │  (192.168.x.x)│    │  (local)  │   │
/// │   └───────────────┘     └───────────────┘    └───────────┘   │
/// │                                                                 │
/// │   NO DATA LEAVES THIS NETWORK!                                 │
/// └─────────────────────────────────────────────────────────────────┘
/// 
/// USAGE:
/// - Server listens on TCP port 5050 (configurable)
/// - Clients connect via TCP socket
/// - Server broadcasts JSON data to ALL connected clients
/// - Simple protocol: newline-delimited JSON
/// 
/// CLIENT EXAMPLE (Python):
/// ```python
/// import socket, json
/// sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
/// sock.connect(('192.168.1.100', 5050))  # Server IP
/// while True:
///     data = sock.recv(65536).decode()
///     for line in data.strip().split('\n'):
///         values = json.loads(line)
///         print(values)
/// ```
/// </summary>
public class LocalTcpBroadcastService : BackgroundService
{
    private readonly PlcTagValuesPoolService _tagPool;
    private readonly IConfiguration _configuration;
    private readonly ILogger<LocalTcpBroadcastService> _logger;
    
    // TCP Server
    private TcpListener? _listener;
    private readonly ConcurrentDictionary<string, TcpClient> _clients = new();
    
    // Configuration
    private readonly bool _enabled;
    private readonly int _port;
    private readonly int _broadcastIntervalMs;
    private readonly string _bindAddress;
    
    // Statistics
    private long _messagesSent;
    private long _totalBytesSent;
    private DateTime _startTime;

    public LocalTcpBroadcastService(
        PlcTagValuesPoolService tagPool,
        IConfiguration configuration,
        ILogger<LocalTcpBroadcastService> logger)
    {
        _tagPool = tagPool;
        _configuration = configuration;
        _logger = logger;
        
        // Configuration from appsettings.json
        _enabled = configuration.GetValue<bool>("PlcGateway:LocalBroadcast:Enabled", true);
        _port = configuration.GetValue<int>("PlcGateway:LocalBroadcast:Port", 5050);
        _broadcastIntervalMs = configuration.GetValue<int>("PlcGateway:LocalBroadcast:IntervalMs", 1000);
        _bindAddress = configuration.GetValue<string>("PlcGateway:LocalBroadcast:BindAddress", "0.0.0.0") ?? "0.0.0.0";
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        if (!_enabled)
        {
            _logger.LogInformation("[LOCAL TCP] Service disabled");
            return;
        }

        _startTime = DateTime.UtcNow;
        
        _logger.LogInformation(
            "[LOCAL TCP] Starting LOCAL broadcast server on {Address}:{Port} - NO CLOUD, NO INTERNET",
            _bindAddress, _port);

        // Start TCP listener
        try
        {
            var ipAddress = _bindAddress == "0.0.0.0" 
                ? IPAddress.Any 
                : IPAddress.Parse(_bindAddress);
                
            _listener = new TcpListener(ipAddress, _port);
            _listener.Start();
            
            _logger.LogInformation("[LOCAL TCP] ✅ Server listening on port {Port}", _port);
            _logger.LogInformation("[LOCAL TCP] 🔒 Data stays within your local network only!");
            
            // Log local IP addresses for clients to connect
            LogLocalAddresses();
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "[LOCAL TCP] Failed to start server on port {Port}", _port);
            return;
        }

        // Accept clients in background
        _ = AcceptClientsAsync(stoppingToken);
        
        // Wait for pool to populate
        await Task.Delay(2000, stoppingToken);

        // Main broadcast loop
        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                await BroadcastToAllClientsAsync(stoppingToken);
                
                // Log stats every 60 seconds
                if (_messagesSent % 60 == 0 && _messagesSent > 0)
                {
                    LogStatistics();
                }
            }
            catch (OperationCanceledException)
            {
                break;
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "[LOCAL TCP] Broadcast error");
            }

            await Task.Delay(_broadcastIntervalMs, stoppingToken);
        }

        // Cleanup
        CleanupAllClients();
        _listener?.Stop();
        _logger.LogInformation("[LOCAL TCP] Server stopped");
    }

    private async Task AcceptClientsAsync(CancellationToken ct)
    {
        while (!ct.IsCancellationRequested && _listener != null)
        {
            try
            {
                var client = await _listener.AcceptTcpClientAsync(ct);
                var endpoint = client.Client.RemoteEndPoint?.ToString() ?? "unknown";
                
                _clients[endpoint] = client;
                
                _logger.LogInformation("[LOCAL TCP] ✅ Client connected: {Endpoint} (Total: {Count})", 
                    endpoint, _clients.Count);
                
                // Send welcome message
                await SendToClientAsync(client, new
                {
                    type = "welcome",
                    message = "Connected to PLC Local Broadcast Server",
                    timestamp = DateTime.UtcNow,
                    server = Environment.MachineName,
                    intervalMs = _broadcastIntervalMs
                });
            }
            catch (OperationCanceledException)
            {
                break;
            }
            catch (Exception ex)
            {
                if (!ct.IsCancellationRequested)
                {
                    _logger.LogWarning(ex, "[LOCAL TCP] Error accepting client");
                }
            }
        }
    }

    private async Task BroadcastToAllClientsAsync(CancellationToken ct)
    {
        if (_clients.IsEmpty) return;

        var values = _tagPool.GetAllTagValues();
        if (values.Count == 0) return;

        // Build message
        var message = new
        {
            type = "plc_data",
            timestamp = DateTime.UtcNow,
            count = values.Count,
            values = values.Select(v => new
            {
                plcId = v.PlcId,
                tag = v.TagName,
                address = v.Address,
                value = v.Value,
                dataType = v.DataType,
                quality = v.Quality.ToString(),
                timestamp = v.Timestamp
            })
        };

        var json = JsonSerializer.Serialize(message, _jsonOptions) + "\n";
        var bytes = Encoding.UTF8.GetBytes(json);

        // Send to all clients (remove disconnected ones)
        var deadClients = new List<string>();

        foreach (var kvp in _clients)
        {
            try
            {
                if (!kvp.Value.Connected)
                {
                    deadClients.Add(kvp.Key);
                    continue;
                }

                await kvp.Value.GetStream().WriteAsync(bytes, ct);
                _totalBytesSent += bytes.Length;
            }
            catch
            {
                deadClients.Add(kvp.Key);
            }
        }

        // Cleanup dead clients
        foreach (var key in deadClients)
        {
            if (_clients.TryRemove(key, out var client))
            {
                client.Dispose();
                _logger.LogInformation("[LOCAL TCP] Client disconnected: {Endpoint} (Remaining: {Count})", 
                    key, _clients.Count);
            }
        }

        if (_clients.Count > 0)
        {
            _messagesSent++;
        }
    }

    private async Task SendToClientAsync(TcpClient client, object message)
    {
        try
        {
            var json = JsonSerializer.Serialize(message, _jsonOptions) + "\n";
            var bytes = Encoding.UTF8.GetBytes(json);
            await client.GetStream().WriteAsync(bytes);
        }
        catch { }
    }

    private void CleanupAllClients()
    {
        foreach (var kvp in _clients)
        {
            try { kvp.Value.Dispose(); } catch { }
        }
        _clients.Clear();
    }

    private void LogLocalAddresses()
    {
        try
        {
            var host = Dns.GetHostEntry(Dns.GetHostName());
            var localIps = host.AddressList
                .Where(ip => ip.AddressFamily == AddressFamily.InterNetwork)
                .Select(ip => ip.ToString())
                .ToList();

            _logger.LogInformation("[LOCAL TCP] ═══════════════════════════════════════════════════");
            _logger.LogInformation("[LOCAL TCP] Clients can connect to this server at:");
            foreach (var ip in localIps)
            {
                _logger.LogInformation("[LOCAL TCP]   → {IP}:{Port}", ip, _port);
            }
            _logger.LogInformation("[LOCAL TCP] ═══════════════════════════════════════════════════");
        }
        catch { }
    }

    private void LogStatistics()
    {
        var uptime = DateTime.UtcNow - _startTime;
        var mbSent = _totalBytesSent / (1024.0 * 1024.0);
        
        _logger.LogInformation(
            "[LOCAL TCP] Stats: Clients={Clients}, Messages={Messages}, Data={Data:F2}MB, Uptime={Uptime:hh\\:mm\\:ss}",
            _clients.Count, _messagesSent, mbSent, uptime);
    }

    private static readonly JsonSerializerOptions _jsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase
    };
}
