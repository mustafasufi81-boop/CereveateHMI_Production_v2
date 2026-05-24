using OpcDaWebBrowser.Hubs;
using OpcDaWebBrowser.Services;
using Microsoft.Extensions.Logging;
using Serilog;

var builder = WebApplication.CreateBuilder(args);

// Configure for silent background operation - NO CONSOLE OUTPUT
builder.Logging.ClearProviders();

// File-only logging
Log.Logger = new LoggerConfiguration()
    .MinimumLevel.Information()
    .WriteTo.File("Logs/app-.log", rollingInterval: RollingInterval.Day)
    .CreateLogger();

builder.Logging.AddSerilog();

// Add services to the container
builder.Services.AddRazorPages();
builder.Services.AddControllers();
builder.Services.AddSignalR();

// ===== LICENSE VALIDATION (Silent) =====
builder.Services.AddSingleton<LicenseService>();
var tempServiceProvider = builder.Services.BuildServiceProvider();
var licenseService = tempServiceProvider.GetRequiredService<LicenseService>();

if (!licenseService.ValidateLicense(out string errorMessage))
{
    var logger = tempServiceProvider.GetRequiredService<ILogger<Program>>();
    logger.LogCritical("License validation failed: {ErrorMessage}", errorMessage);
    Environment.Exit(1);
    return;
}

// Register OPC services
builder.Services.AddSingleton<OpcDaService>();
builder.Services.AddSingleton<OpcServerDiscovery>();
builder.Services.AddSingleton<LoggingConfigService>();
builder.Services.AddSingleton<LogFileReaderService>();
builder.Services.AddHostedService<OpcAutoConnectService>();
builder.Services.AddHostedService<DataLoggingService>();

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
    options.ListenAnyIP(6300); // HTTP
});

var app = builder.Build();

// Configure the HTTP request pipeline
if (!app.Environment.IsDevelopment())
{
    app.UseExceptionHandler("/Error");
}

app.UseStaticFiles();
app.UseRouting();
app.UseCors("AllowAll");
app.UseAuthorization();

app.MapHub<OpcDaHub>("/opcHub");
app.MapControllers();
app.MapRazorPages();

// Log startup silently to file only
var appLogger = app.Services.GetRequiredService<ILogger<Program>>();
appLogger.LogInformation("Cereveate_Praxis OPC Server Started");
appLogger.LogInformation("Web UI: http://localhost:6300");
appLogger.LogInformation("Network Access: http://{IP}:6300", GetLocalIPAddress());

app.Run();

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
