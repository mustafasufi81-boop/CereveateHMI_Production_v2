using Npgsql;
using OpcDaWebBrowser.Hubs;
using OpcDaWebBrowser.Services;
using OpcDaWebBrowser.Services.Health;
using OpcDaWebBrowser.Services.HistorianIngest.Config;
using OpcDaWebBrowser.Services.HistorianIngest.Services;
using OpcDaWebBrowser.Services.Logging;
using PlcGateway;
using PlcGateway.Services;
using Serilog;
using Serilog.Events;
using System.Diagnostics;
using System.Reflection;

try
{
    Console.WriteLine("=== Cereveate OPC DA Web Browser Starting ===");
    Console.WriteLine($"Time: {DateTime.Now:yyyy-MM-dd HH:mm:ss}");
    Console.WriteLine($"Directory: {AppDomain.CurrentDomain.BaseDirectory}");
    Console.WriteLine();

// Single instance protection — only ONE OpcDaWebBrowser may run at a time.
// A second instance will print an error and exit immediately (no ReadKey — safe for headless/service use).
var mutexName = "Global\\CereveateOPCWebBrowser_SingleInstance";
bool createdNew = true;
Mutex? singleInstanceMutex = null;
try
{
    singleInstanceMutex = new Mutex(true, mutexName, out createdNew);
}
catch (Exception mutexEx)
{
    Console.WriteLine($"[SINGLE-INSTANCE] Mutex error (allowing startup): {mutexEx.Message}");
    createdNew = true;
}

if (!createdNew)
{
    Console.Error.WriteLine("[SINGLE-INSTANCE] FATAL: Another instance of OpcDaWebBrowser is already running.");
    Console.Error.WriteLine("[SINGLE-INSTANCE] Kill the existing process first, then restart.");
    Console.Error.WriteLine($"[SINGLE-INSTANCE] Mutex: {mutexName}");
    Environment.Exit(1);
}

var builder = WebApplication.CreateBuilder(args);

// Load configuration (optional: true so app doesn't crash if file missing)
builder.Configuration.AddJsonFile("logging-config.json", optional: true, reloadOnChange: true);

// Configure Serilog from configuration
var logDirectory = builder.Configuration["LoggingPaths:ApplicationLogDirectory"] ?? "Logs";
var logPath = Path.IsPathRooted(logDirectory)
    ? Path.Combine(logDirectory, "app-.log")
    : Path.Combine(AppDomain.CurrentDomain.BaseDirectory, logDirectory, "app-.log");

var minimumLevel = Enum.TryParse<LogEventLevel>(builder.Configuration["Serilog:MinimumLevel"], out var level)
    ? level
    : LogEventLevel.Information;

var outputTemplate = builder.Configuration["Serilog:OutputTemplate"] 
    ?? "{Timestamp:yyyy-MM-dd HH:mm:ss.fff} [{Level}] {Message}{NewLine}{Exception}";

Log.Logger = new LoggerConfiguration()
    .MinimumLevel.Is(minimumLevel)
    .WriteTo.Console(outputTemplate: outputTemplate)
    .WriteTo.File(
        logPath,
        rollingInterval: RollingInterval.Day,
        fileSizeLimitBytes: 7 * 1024 * 1024,   // 7 MB max per file
        rollOnFileSizeLimit: true,               // roll to new file when 7MB reached
        retainedFileCountLimit: 14,              // keep last 14 files (2 weeks)
        outputTemplate: outputTemplate)
    .CreateLogger();

builder.Host.UseSerilog();
builder.Host.UseConsoleLifetime(); // CRITICAL: Enable Ctrl+C shutdown

// Add services to the container
builder.Services.AddRazorPages();
builder.Services.AddControllers(); // Controllers in OpcDaWebBrowser.Controllers namespace auto-discovered
builder.Services.AddSignalR();

// Add session support for authentication
builder.Services.AddDistributedMemoryCache();
builder.Services.AddSession(options =>
{
    options.IdleTimeout = TimeSpan.FromHours(24);
    options.Cookie.HttpOnly = true;
    options.Cookie.IsEssential = true;
});

// Register OPC services
builder.Services.AddSingleton<CredentialEncryptionService>();
builder.Services.AddSingleton<OpcDaService>();
builder.Services.AddSingleton<OpcServerDiscovery>();
builder.Services.AddSingleton<LoggingConfigService>();
builder.Services.AddSingleton<LogFileReaderService>();
builder.Services.AddSingleton<TrendDataService>();
builder.Services.AddSingleton<AuthenticationService>();
builder.Services.AddSingleton<LogBackupService>(); // Register as singleton for API access
builder.Services.AddSingleton<DataLoggingService>();
// builder.Services.AddSingleton<ArchiveMonitoringService>(); // SAFE monitoring service (read-only)

// ===== HEALTH MONITORING SYSTEM =====
builder.Services.AddSingleton<IHealthStatusService, HealthStatusService>();
builder.Services.AddHostedService<ResourceMonitor>();
// ===== END HEALTH MONITORING SYSTEM =====

// Tag Values Pool Service (shared cache for Parquet + PostgreSQL)
builder.Services.AddSingleton<TagValuesPoolService>();

// Seed ServerProgId + MonitoredTags from tag_master on first boot (runs before OpcAutoConnectService)
builder.Services.AddHostedService<StartupTagSeedService>();
builder.Services.AddHostedService<OpcAutoConnectService>();
builder.Services.AddHostedService(provider => provider.GetRequiredService<LogBackupService>()); // Use same instance
builder.Services.AddHostedService(provider => provider.GetRequiredService<DataLoggingService>());
// builder.Services.AddHostedService<StressTestHostedService>();

// ===== HISTORIAN INGEST SYSTEM =====
// Register Historian configuration
builder.Services.AddSingleton(sp =>
{
    var config = new HistorianConfig();
    builder.Configuration.GetSection("Historian").Bind(config);
    
    // CRITICAL: Log loaded config to verify binding worked
    Console.WriteLine($"[CONFIG] MaxWaitMs loaded: {config.Batch.MaxWaitMs}ms");
    Console.WriteLine($"[CONFIG] MaxRows: {config.Batch.MaxRows}, MaxBytes: {config.Batch.MaxBytes}");
    Console.WriteLine($"[CONFIG] ShardCount: {config.Writer.ShardCount}");
    
    return config;
});

// Register Historian services (SIMPLIFIED for 10K+ tags)
builder.Services.AddSingleton<MappingCacheService>();
builder.Services.AddSingleton<RateControllerService>();
builder.Services.AddSingleton<BatcherService>();
builder.Services.AddSingleton<DbWriterService>();
builder.Services.AddSingleton<SpoolManagerService>();
builder.Services.AddHostedService<HistorianIngestHostedService>();
builder.Services.AddHostedService<OpcMqttPublisherService>(); // OPC DA → MQTT bridge (topic: opc/{serverProgId}/tags/bulk)
// ===== END HISTORIAN INGEST SYSTEM =====

// ===== OPC UA SYSTEM (INDEPENDENT PIPELINE - Zero impact on OPC DA) =====
builder.Services.AddSingleton<OpcDaWebBrowser.Services.OpcUa.OpcUaDiscovery>();
builder.Services.AddSingleton<OpcDaWebBrowser.Services.OpcUa.OpcUaService>();
// Note: OpcUaService manually controlled via API, not auto-started as HostedService
// ===== END OPC UA SYSTEM =====

// ===== PLC GATEWAY SYSTEM - FULL MODE WITH BACKGROUND SERVICES =====
// Shared Npgsql connection pool — ALL PLC services reuse this (no per-write connection creation)
builder.Services.AddSingleton(sp =>
{
    var cs = builder.Configuration.GetConnectionString("PlcGateway")
              ?? builder.Configuration.GetConnectionString("Historian")
              ?? throw new InvalidOperationException("No PlcGateway connection string found");
    return NpgsqlDataSource.Create(cs);
});

// Registers REST API controllers, background services, and data polling
builder.Services.AddPlcGateway();
builder.Services.AddHostedService<PlcGatewayHostedService>(); // Load PLC configs from DB
Console.WriteLine("[STARTUP] PLC Gateway enabled (full mode with background services)");
// ===== END PLC GATEWAY SYSTEM =====

// Add CORS for SignalR
builder.Services.AddCors(options =>
{
    options.AddPolicy("AllowAll", policy =>
    {
        policy.AllowAnyOrigin()
              .AllowAnyMethod()
              .AllowAnyHeader();
    });
});

// Configure Kestrel to listen on all network interfaces
builder.WebHost.ConfigureKestrel(options =>
{
    options.ListenAnyIP(5001); // HTTP
});

var app = builder.Build();

// Configure the HTTP request pipeline
if (!app.Environment.IsDevelopment())
{
    app.UseExceptionHandler("/Error");
}

app.UseStaticFiles();
app.UseRouting();
app.UseSession();
app.UseCors("AllowAll");
app.UseAuthorization();

// Authentication middleware - redirect to login if not authenticated
app.Use(async (context, next) =>
{
    var path = context.Request.Path.Value?.ToLower() ?? "";
    var isAuthenticated = context.Session.GetString("IsAuthenticated") == "true";
    
    // Allow access to login page, static files, API endpoints, and SignalR hub
    if (path.StartsWith("/login") || 
        path.StartsWith("/css") || 
        path.StartsWith("/js") || 
        path.StartsWith("/lib") ||
        path.StartsWith("/api") ||
        path.StartsWith("/opchub"))
    {
        await next();
        return;
    }
    
    // Redirect to login if not authenticated (block access to main page)
    if (!isAuthenticated)
    {
        context.Response.Redirect("/Login");
        return;
    }
    
    await next();
});

app.MapHub<OpcDaHub>("/opcHub");
app.MapControllers();
app.MapRazorPages();

// Test endpoint to verify server is running
app.MapGet("/api/test", () => new { status = "OK", message = "Server is running", timestamp = DateTime.Now });

// ===== SYSTEM STARTUP SUMMARY (Industrial Standard - AVEVA/Honeywell pattern) =====
var logger = app.Services.GetRequiredService<ILogger<Program>>();
var version = Assembly.GetExecutingAssembly().GetName().Version?.ToString() ?? "Unknown";
var buildDate = File.GetLastWriteTime(Assembly.GetExecutingAssembly().Location).ToString("yyyy-MM-dd HH:mm");

logger.LogInformation("=".PadRight(80, '='));
logger.LogInformation("[{EventType}] Cereveate OPC DA Historian System", LogEventType.SYSTEM_STARTUP);
logger.LogInformation("   Version: {Version} | Build: {BuildDate}", version, buildDate);
logger.LogInformation("   Platform: {Platform} | Runtime: {Runtime}", 
    Environment.OSVersion.Platform, Environment.Version);
logger.LogInformation("   Directory: {BaseDir}", AppDomain.CurrentDomain.BaseDirectory);

var historianConfig = app.Services.GetService<HistorianConfig>();
if (historianConfig != null)
{
    logger.LogInformation("   Historian: Enabled (shards={Shards}, batch={BatchSize})", 
        historianConfig.Writer.ShardCount, historianConfig.Batch.MaxRows);
}

var archiveConfig = builder.Configuration.GetSection("ArchiveSettings");
if (archiveConfig.GetValue<bool>("Enabled", true))
{
    logger.LogInformation("   Archiver: Enabled (interval={Interval}min)", 
        archiveConfig.GetValue<int>("ArchiveIntervalMinutes", 60));
}

var perfConfig = builder.Configuration.GetSection("Performance");
logger.LogInformation("   Performance: OpcDiag={OpcDiag} | HistDebug={HistDebug} | BatchSummary={Interval}", 
    perfConfig.GetValue<bool>("EnableOpcDiagnostics", true) ? "ON" : "OFF",
    perfConfig.GetValue<bool>("EnableHistorianDebug", false) ? "ON" : "OFF",
    perfConfig.GetValue<int>("BatchSummaryInterval", 100));
logger.LogInformation("=".PadRight(80, '='));
// ===== END STARTUP SUMMARY =====

Console.WriteLine("=".PadRight(80, '='));
Console.WriteLine("OPC DA Web Browser Started");
Console.WriteLine("=".PadRight(80, '='));
Console.WriteLine($"Web UI:          http://localhost:5001");
Console.WriteLine($"Network Access:  http://{GetLocalIPAddress()}:5001");
Console.WriteLine();
Console.WriteLine("REST API Endpoints:");
Console.WriteLine($"  GET  /api/opc/servers       - List OPC servers");
Console.WriteLine($"  GET  /api/opc/status        - Connection status");
Console.WriteLine($"  POST /api/opc/connect       - Connect to server");
Console.WriteLine($"  GET  /api/opc/tags          - Browse tags");
Console.WriteLine($"  GET  /api/opc/values        - Get all tag values");
Console.WriteLine($"  GET  /api/opc/trend/{{tag}}   - Get trend data");
Console.WriteLine("=".PadRight(80, '='));
Console.WriteLine();

try
{
    Console.WriteLine("▶ Starting web host...");
    app.Run();
}
finally
{
    // Mutex cleanup disabled - mutex is completely removed
}

}
catch (Exception ex)
{
    Console.ForegroundColor = ConsoleColor.Red;
    Console.WriteLine();
    Console.WriteLine("██████████████████████████████████████████");
    Console.WriteLine("█                                         █");
    Console.WriteLine("█  FATAL ERROR - APPLICATION CRASHED      █");
    Console.WriteLine("█                                         █");
    Console.WriteLine("██████████████████████████████████████████");
    Console.WriteLine();
    Console.WriteLine($"ERROR: {ex.Message}");
    Console.WriteLine();
    Console.WriteLine("STACK TRACE:");
    Console.WriteLine(ex.StackTrace);
    Console.WriteLine();
    if (ex.InnerException != null)
    {
        Console.WriteLine("INNER EXCEPTION:");
        Console.WriteLine(ex.InnerException.Message);
        Console.WriteLine(ex.InnerException.StackTrace);
    }
    Console.ResetColor();
    Console.WriteLine();
    Console.WriteLine("Application will exit in 5 seconds...");
    await Task.Delay(5000);
    return 1;
}

return 0;

static string GetLocalIPAddress()
{
    var host = System.Net.Dns.GetHostEntry(System.Net.Dns.GetHostName());
    foreach (var ip in host.AddressList)
    {
        if (ip.AddressFamily == System.Net.Sockets.AddressFamily.InterNetwork)
        {
            return ip.ToString();
        }
    }
    return "127.0.0.1";
}
