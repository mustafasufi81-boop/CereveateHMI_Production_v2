using System.Text.Json;

namespace OpcDaWebBrowser.Services;

/// <summary>
/// Manages logging configuration persistence with auto-reload
/// </summary>
public class LoggingConfigService
{
    private readonly string _configPath;
    private readonly string _secureConfigPath;
    private readonly ILogger<LoggingConfigService> _logger;
    private readonly CredentialEncryptionService _encryption;
    private LoggingConfig _config;
    private readonly object _lock = new();
    private FileSystemWatcher? _configWatcher;

    public LoggingConfigService(
        ILogger<LoggingConfigService> logger,
        CredentialEncryptionService encryption)
    {
        _logger = logger;
        _encryption = encryption;
        _configPath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "logging-config.json");
        _secureConfigPath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, ".opcconnections");
        _config = LoadConfig();
        
        // Setup file watcher for auto-reload
        SetupConfigWatcher();
    }

    private void SetupConfigWatcher()
    {
        try
        {
            var directory = Path.GetDirectoryName(_configPath);
            if (string.IsNullOrEmpty(directory)) return;

            _configWatcher = new FileSystemWatcher(directory)
            {
                Filter = "logging-config.json",
                NotifyFilter = NotifyFilters.LastWrite | NotifyFilters.Size,
                EnableRaisingEvents = true
            };

            _configWatcher.Changed += OnConfigFileChanged;
            _logger.LogInformation("Config file watcher enabled - auto-reload active");
        }
        catch (Exception ex)
        {
            _logger.LogWarning($"Failed to setup config watcher: {ex.Message}");
        }
    }

    private void OnConfigFileChanged(object sender, FileSystemEventArgs e)
    {
        // Debounce - wait a bit for file to be fully written
        Task.Delay(500).ContinueWith(_ =>
        {
            lock (_lock)
            {
                try
                {
                    var newConfig = LoadConfig();
                    _config = newConfig;
                    _logger.LogInformation("Configuration reloaded automatically from file");
                }
                catch (Exception ex)
                {
                    _logger.LogError($"Failed to reload config: {ex.Message}");
                }
            }
        });
    }

    public LoggingConfig GetConfig()
    {
        lock (_lock)
        {
            return _config;
        }
    }

    public void UpdateConfig(LoggingConfig config)
    {
        lock (_lock)
        {
            _config = config;
            SaveConfig();
        }
    }

    public void AddTag(string tagId)
    {
        lock (_lock)
        {
            if (!_config.SelectedTags.Contains(tagId))
            {
                _config.SelectedTags.Add(tagId);
                _logger.LogInformation("Adding tag to logging: {TagId}", tagId);
                SaveConfig();
                _logger.LogDebug("Total selected tags: {Count}", _config.SelectedTags.Count);
            }
        }
    }

    public void RemoveTag(string tagId)
    {
        lock (_lock)
        {
            _config.SelectedTags.Remove(tagId);
            SaveConfig();
            _logger.LogInformation($"Removed tag from logging: {tagId}");
        }
    }

    public void SetEnabled(bool enabled)
    {
        lock (_lock)
        {
            _config.IsEnabled = enabled;
            _logger.LogInformation("Setting logging enabled: {Enabled}", enabled);
            SaveConfig();
            _logger.LogDebug("Config saved to: {ConfigPath}", _configPath);
        }
    }

    public void SetLoggingInterval(int intervalMs)
    {
        lock (_lock)
        {
            // Update both LoggingIntervalMs AND DataLogging.IntervalSeconds to keep them in sync
            _config.LoggingIntervalMs = intervalMs;
            if (_config.DataLogging != null)
            {
                _config.DataLogging.IntervalSeconds = intervalMs / 1000;
            }
            _logger.LogInformation("Setting logging interval: {IntervalMs}ms ({IntervalSec}s)",
                intervalMs, intervalMs / 1000);
            SaveConfig();
        }
    }

    public void SetServerConnection(string progId, string host, string? clsid = null)
    {
        lock (_lock)
        {
            // Store plain text (no encryption)
            _config.ServerProgId = progId;
            _config.ServerHost = host;
            _config.ServerClsid = string.IsNullOrWhiteSpace(clsid) ? null : clsid.Trim();
            SaveConfig();
            
            if (string.IsNullOrWhiteSpace(_config.ServerClsid))
            {
                _logger.LogInformation($"Saved server connection: {progId} on {host}");
            }
            else
            {
                _logger.LogInformation($"Saved server connection: {progId} on {host} (CLSID={_config.ServerClsid})");
            }
        }
    }

    public string GetDecryptedProgId()
    {
        lock (_lock)
        {
            return _config.ServerProgId ?? string.Empty;
        }
    }

    public string GetDecryptedHost()
    {
        lock (_lock)
        {
            return _config.ServerHost ?? "localhost";
        }
    }

    public string GetDecryptedClsid()
    {
        lock (_lock)
        {
            return _config.ServerClsid ?? string.Empty;
        }
    }

    public string GetMaskedHost()
    {
        lock (_lock)
        {
            var host = GetDecryptedHost();
            return _encryption.MaskForDisplay(host);
        }
    }

    public void AddMonitoredTag(string tagId)
    {
        lock (_lock)
        {
            if (!_config.MonitoredTags.Contains(tagId))
            {
                _config.MonitoredTags.Add(tagId);
                SaveConfig();
                _logger.LogInformation($"Added monitored tag: {tagId}");
            }
        }
    }

    public void RemoveMonitoredTag(string tagId)
    {
        lock (_lock)
        {
            _config.MonitoredTags.Remove(tagId);
            _config.SelectedTags.Remove(tagId); // Also remove from logging
            SaveConfig();
            _logger.LogInformation($"Removed monitored tag: {tagId}");
        }
    }

    private LoggingConfig GetDefaultConfig()
    {
        return new LoggingConfig
        {
            LoggingPaths = new LoggingPathsConfig
            {
                BaseDirectory = "D:\\OpcLogs",
                DataLogDirectory = "D:\\OpcLogs\\Data",
                ApplicationLogDirectory = "D:\\OpcLogs\\AppLogs",
                BackupDirectory = "D:\\OpcLogs\\Backup"
            },
            DataLogging = new DataLoggingConfig
            {
                Enabled = true,
                IntervalSeconds = 5,
                FileNamePrefix = "OpcData"
            },
            BackupSettings = new BackupSettingsConfig
            {
                Enabled = true,
                CheckIntervalMinutes = 5,
                AutoBackupOnWrite = true
            },
            Serilog = new SerilogConfig
            {
                MinimumLevel = "Information",
                RollingInterval = "Day",
                OutputTemplate = "{Timestamp:yyyy-MM-dd HH:mm:ss.fff} [{Level}] {Message}{NewLine}{Exception}"
            },
            IsEnabled = false,
            SelectedTags = new List<string>(),
            MonitoredTags = new List<string>(),
            LoggingIntervalMs = 1000,
            ServerProgId = null,
            ServerHost = null,
            ServerClsid = null
        };
    }

    private LoggingConfig LoadConfig()
    {
        LoggingConfig config;
        
        try
        {
            // Step 1: Try to load existing file
            if (File.Exists(_configPath))
            {
                _logger?.LogDebug("Found existing config file: {ConfigPath}", _configPath);
                
                try
                {
                    var json = File.ReadAllText(_configPath);
                    var loadedConfig = JsonSerializer.Deserialize<LoggingConfig>(json);
                    
                    if (loadedConfig != null)
                    {
                        config = loadedConfig;
                        
                        // PRESERVE USER SETTINGS - Only fill missing nested objects with defaults
                        var defaults = GetDefaultConfig();
                        config.LoggingPaths ??= defaults.LoggingPaths;
                        config.DataLogging ??= defaults.DataLogging;
                        config.BackupSettings ??= defaults.BackupSettings;
                        config.Serilog ??= defaults.Serilog;
                        config.SelectedTags ??= new List<string>();
                        config.MonitoredTags ??= new List<string>();
                        config.ServerClsid ??= null;
                        
                        _logger?.LogInformation("Loaded user settings - IsEnabled: {IsEnabled}, SelectedTags: {SelectedCount}, MonitoredTags: {MonitoredCount}",
                            config.IsEnabled, config.SelectedTags.Count, config.MonitoredTags.Count);
                    }
                    else
                    {
                        // File exists but corrupt - use defaults WITHOUT destroying file
                        _logger?.LogWarning("Config file corrupt but preserved - using defaults");
                        config = GetDefaultConfig();
                        // DON'T save here - preserve corrupt file for investigation
                    }
                }
                catch (JsonException jsonEx)
                {
                    // JSON parsing failed - preserve file, use defaults
                    _logger?.LogError(jsonEx, "JSON parse failed");
                    _logger?.LogWarning("Preserving existing file, using defaults");
                    config = GetDefaultConfig();
                    // DON'T save - keep user's file
                }
            }
            else
            {
                // File doesn't exist - create with defaults
                _logger?.LogInformation("No config file found, creating defaults: {ConfigPath}", _configPath);
                config = GetDefaultConfig();
                
                // Save new file
                try
                {
                    var json = JsonSerializer.Serialize(config, new JsonSerializerOptions { WriteIndented = true });
                    File.WriteAllText(_configPath, json);
                    _logger?.LogInformation("Created new config file with defaults");
                }
                catch (Exception saveEx)
                {
                    _logger?.LogError(saveEx, "Failed to create config file: {ConfigPath}", _configPath);
                    // Continue with in-memory defaults
                }
            }
            
            // Server credentials are now in main config (no separate encrypted file)
            
            return config;
        }
        catch (Exception ex)
        {
            // Complete catastrophic failure - use hardcoded defaults
            _logger?.LogError(ex, "Complete config load failure, using hardcoded defaults");
            return GetDefaultConfig();
        }
    }

    private void SaveConfig()
    {
        try
        {
            // Save complete config including server connection (plain text)
            var configToSave = _config;
            
            var json = JsonSerializer.Serialize(configToSave, new JsonSerializerOptions
            {
                WriteIndented = true
            });
            File.WriteAllText(_configPath, json);
            _logger.LogDebug("Saved config to: {ConfigPath}", _configPath);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error saving logging config");
        }
    }


}

public class LoggingConfig
{
    public LoggingPathsConfig LoggingPaths { get; set; } = new();
    public DataLoggingConfig DataLogging { get; set; } = new();
    public BackupSettingsConfig BackupSettings { get; set; } = new();
    public SerilogConfig Serilog { get; set; } = new();
    public PerformanceIntervalsConfig PerformanceIntervals { get; set; } = new();
    
    public bool IsEnabled { get; set; } = false;
    public List<string> SelectedTags { get; set; } = new();
    public int LoggingIntervalMs { get; set; } = 1000; // 1 second default
    
    // Computed property: Returns actual interval being used (DataLogging.IntervalSeconds takes priority)
    public int ActualIntervalMs => DataLogging?.IntervalSeconds > 0 
        ? DataLogging.IntervalSeconds * 1000 
        : LoggingIntervalMs;
    
    // OPC connection settings for auto-reconnect
    public string? ServerProgId { get; set; }
    public string? ServerHost { get; set; }
    public List<string> MonitoredTags { get; set; } = new(); // All monitored tags (for display + logging)
    public string? ServerClsid { get; set; }
}

public class LoggingPathsConfig
{
    public string BaseDirectory { get; set; } = "D:\\OpcLogs";
    public string DataLogDirectory { get; set; } = "D:\\OpcLogs\\Data";
    public string ApplicationLogDirectory { get; set; } = "D:\\OpcLogs\\AppLogs";
    public string BackupDirectory { get; set; } = "D:\\OpcLogs\\Backup";
}

public class DataLoggingConfig
{
    public bool Enabled { get; set; } = true;
    public int IntervalSeconds { get; set; } = 5;
    public string FileNamePrefix { get; set; } = "OpcData";
}

public class BackupSettingsConfig
{
    public bool Enabled { get; set; } = true;
    public int CheckIntervalMinutes { get; set; } = 5;
    public bool AutoBackupOnWrite { get; set; } = true;
}

public class SerilogConfig
{
    public string MinimumLevel { get; set; } = "Information";
    public string RollingInterval { get; set; } = "Day";
    public string OutputTemplate { get; set; } = "{Timestamp:yyyy-MM-dd HH:mm:ss.fff} [{Level}] {Message}{NewLine}{Exception}";
}

/// <summary>
/// All timing intervals in one place for easy tuning
/// Values are in milliseconds unless specified otherwise
/// </summary>
public class PerformanceIntervalsConfig
{
    // OPC Polling & Communication
    public int OpcPollingIntervalMs { get; set; } = 1000;           // Default OPC DA polling rate
    public int UiBroadcastIntervalMs { get; set; } = 1000;          // OpcDaService event throttle
    public int SignalRBroadcastThrottleMs { get; set; } = 1000;     // SignalR Hub broadcast throttle (was 200ms hardcoded)
    public int PollingTaskWaitTimeoutMs { get; set; } = 2000;       // Timeout waiting for polling task
    public int ReadOperationSlowThresholdMs { get; set; } = 1000;   // Log warning if read takes longer
    
    // Historian & Database
    public int HistorianPollingFallbackMs { get; set; } = 1000;     // Fallback when no tag intervals set
    public int HealthReportIntervalMs { get; set; } = 30000;        // Health status report frequency
    public int StatusLogIntervalMs { get; set; } = 10000;           // Status logging frequency
    
    // Application Lifecycle
    public int StartupDelayMs { get; set; } = 3000;                 // Delay before starting services
    public int ErrorRetryDelayMs { get; set; } = 5000;              // Delay after error before retry
    public int ConfigReloadCheckIntervalMs { get; set; } = 60000;   // How often to check config changes
    
    // Memory & Capacity Limits
    public int TagPoolCapacity { get; set; } = 2000;                // Max tags per connection pool
    public int TagsPerOpcGroup { get; set; } = 2000;                // Tags per OPC group
    public int MaxDataPointsPerTag { get; set; } = 10000;           // Trend data retention per tag
    public int TimestampOrderCapacity { get; set; } = 50000;        // Out-of-order detection buffer
}
