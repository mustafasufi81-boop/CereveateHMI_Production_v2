using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using PlcGateway.Drivers;
using PlcGateway.Services;
using PlcGateway.Transport;

namespace PlcGateway;

/// <summary>
/// Dependency Injection Extensions for PLC Gateway
/// 
/// Usage in Program.cs:
/// 
///     builder.Services.AddPlcGateway();
/// 
/// ARCHITECTURE: SERVER-SIDE REST API ONLY
/// ┌─────────────────────────────────────────────────────────────────────┐
/// │                    PLC Gateway - API Mode Only                       │
/// ├─────────────────────────────────────────────────────────────────────┤
/// │                                                                       │
/// │   EXTERNAL CLIENTS call REST API:                                    │
/// │   - GET  /api/plc/list          → List all PLCs                     │
/// │   - POST /api/plc/add           → Add PLC configuration             │
/// │   - POST /api/plc/connect/{id}  → Connect to PLC                    │
/// │   - GET  /api/plc/values/{id}   → Read tag values                   │
/// │   - POST /api/plc/write         → Write tag values                  │
/// │   - GET  /api/plc/health        → Health check                      │
/// │                                                                       │
/// │   Server does NOT:                                                   │
/// │   - Auto-poll PLCs (client triggers reads via API)                  │
/// │   - Self-call its own API endpoints                                 │
/// │   - Start MQTT services                                              │
/// │   - Run background data logging                                      │
/// │                                                                       │
/// │   This is a PASSIVE SERVER - external clients drive all actions     │
/// │                                                                       │
/// └─────────────────────────────────────────────────────────────────────┘
/// </summary>
public static class PlcGatewayExtensions
{
    /// <summary>
    /// Add PLC Gateway services to DI container (API-only mode)
    /// No background services, no MQTT, no self-calling - just REST API
    /// </summary>
    public static IServiceCollection AddPlcGateway(this IServiceCollection services)
    {
        // ═══════════════════════════════════════════════════════════════
        // CORE SERVICES (Singletons) - For REST API Controllers
        // ═══════════════════════════════════════════════════════════════
        
        // Driver Factory (creates isolated driver instances per PLC)
        services.AddSingleton<PlcDriverFactory>();
        
        // Config Loader (loads PLC configs from PostgreSQL database)
        services.AddSingleton<PlcConfigLoaderService>();
        
        // Config Persistence (saves PLC configs to local JSON file)
        services.AddSingleton<PlcConfigPersistenceService>();
        
        // Tag Values Pool (in-memory cache for tag values - latest value per tag)
        services.AddSingleton<PlcTagValuesPoolService>();
        
        // Sample Buffer (accumulates multiple samples per tag for high-frequency scanning)
        services.AddSingleton<PlcSampleBufferService>();
        
        // Gateway Manager (manages PLC connections on-demand via API)
        services.AddSingleton<PlcGatewayManager>();
        
        // ═══════════════════════════════════════════════════════════════
        // HISTORIAN INGEST SERVICE - Reads pool → writes historian_raw.historian_timeseries
        // Registered as singleton so PlcController can call TriggerConfigReload()
        // ═══════════════════════════════════════════════════════════════
        services.AddSingleton<PlcHistorianIngestService>();
        services.AddHostedService(sp => sp.GetRequiredService<PlcHistorianIngestService>());
        
        // ═══════════════════════════════════════════════════════════════
        // TRANSPORT SERVICES - LOCAL NETWORK ONLY (NO CLOUD!)
        // ═══════════════════════════════════════════════════════════════
        
        // LOCAL TCP Broadcast - Direct TCP server on your network
        // NO external broker, NO cloud, NO internet - data stays local!
        services.AddHostedService<LocalTcpBroadcastService>();
        
        // MQTT Publisher (optional - requires local Mosquitto broker)
        // Only enable if you run your own MQTT broker on your network
        services.AddHostedService<MultiProtocolPublisherService>();
        
        // Health Publisher - Publishes PLC health metrics every 3 seconds
        // Topic: plc/health with latency, errors, scan stats
        services.AddHostedService<HealthPublisherService>();
        
        return services;
    }
    
    /// <summary>
    /// Add PLC Gateway services with custom configuration
    /// </summary>
    public static IServiceCollection AddPlcGateway(
        this IServiceCollection services,
        Action<PlcGatewayOptions>? configure = null)
    {
        var options = new PlcGatewayOptions();
        configure?.Invoke(options);
        
        services.AddSingleton(options);
        
        return services.AddPlcGateway();
    }
    
    /// <summary>
    /// Add PLC Gateway with connection string (backward compatibility)
    /// </summary>
    [Obsolete("Use AddPlcGateway() without connectionString - connection string is now read from IConfiguration")]
    public static IServiceCollection AddPlcGateway(
        this IServiceCollection services, 
        string connectionString)
    {
        return services.AddPlcGateway();
    }
}

/// <summary>
/// PLC Gateway configuration options
/// </summary>
public class PlcGatewayOptions
{
    /// <summary>
    /// Config refresh interval (default 5 minutes)
    /// </summary>
    public TimeSpan ConfigRefreshInterval { get; set; } = TimeSpan.FromMinutes(5);
    
    /// <summary>
    /// Default polling interval if not specified per-PLC (default 1000ms)
    /// </summary>
    public int DefaultPollingIntervalMs { get; set; } = 1000;
    
    /// <summary>
    /// Default scan rate for tags if not specified per-tag (default 1000ms)
    /// This is how often to READ from PLC. Configure in appsettings.json PlcGateway:DefaultScanRateMs
    /// </summary>
    public int DefaultScanRateMs { get; set; } = 1000;
    
    /// <summary>
    /// Default reconnect delay (default 5000ms)
    /// </summary>
    public int DefaultReconnectDelayMs { get; set; } = 5000;
    
    /// <summary>
    /// Default transmission interval for buffered values (default 1000ms)
    /// This is how often to send buffered values via MQTT/API
    /// </summary>
    public int DefaultTransmissionIntervalMs { get; set; } = 1000;
    
    /// <summary>
    /// Enable detailed logging
    /// </summary>
    public bool EnableDetailedLogging { get; set; } = false;
}
