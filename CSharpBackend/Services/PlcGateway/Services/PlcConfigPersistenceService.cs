using System.Text.Json;
using Microsoft.Extensions.Logging;
using PlcGateway.Interfaces;

namespace PlcGateway.Services;

/// <summary>
/// Persists PLC configurations to local JSON file
/// Ensures configs survive server restarts
/// </summary>
public class PlcConfigPersistenceService
{
    private readonly string _configPath;
    private readonly ILogger<PlcConfigPersistenceService> _logger;
    private readonly object _fileLock = new();
    private PlcConfigFile _cachedConfig;

    public PlcConfigPersistenceService(
        IConfiguration configuration,
        ILogger<PlcConfigPersistenceService> logger)
    {
        _logger = logger;
        
        // Get config path from settings or use default
        var basePath = configuration["DataLogging:BasePath"] ?? "D:\\OpcLogs";
        _configPath = Path.Combine(basePath, "plc-config.json");
        
        // Ensure directory exists
        var dir = Path.GetDirectoryName(_configPath);
        if (!string.IsNullOrEmpty(dir) && !Directory.Exists(dir))
        {
            Directory.CreateDirectory(dir);
        }
        
        // Load existing config or create empty
        _cachedConfig = LoadConfigInternal();
        
        _logger.LogInformation("[PLC CONFIG] Config file: {Path}, {Count} PLCs loaded", 
            _configPath, _cachedConfig.Plcs.Count);
    }

    /// <summary>
    /// Get all saved PLC configurations
    /// </summary>
    public List<SavedPlcConfig> GetAllConfigs()
    {
        lock (_fileLock)
        {
            return _cachedConfig.Plcs.ToList();
        }
    }

    /// <summary>
    /// Get a specific PLC configuration
    /// </summary>
    public SavedPlcConfig? GetConfig(string plcId)
    {
        lock (_fileLock)
        {
            return _cachedConfig.Plcs.FirstOrDefault(p => p.PlcId == plcId);
        }
    }

    /// <summary>
    /// Save or update a PLC configuration
    /// </summary>
    public bool SaveConfig(SavedPlcConfig config)
    {
        lock (_fileLock)
        {
            try
            {
                // Remove existing if present
                _cachedConfig.Plcs.RemoveAll(p => p.PlcId == config.PlcId);
                
                // Add new/updated config
                config.UpdatedAt = DateTime.UtcNow;
                if (config.CreatedAt == default)
                {
                    config.CreatedAt = DateTime.UtcNow;
                }
                _cachedConfig.Plcs.Add(config);
                
                // Persist to file
                SaveConfigInternal();
                
                _logger.LogInformation("[PLC CONFIG] Saved config for PLC {PlcId}", config.PlcId);
                return true;
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "[PLC CONFIG] Failed to save config for {PlcId}", config.PlcId);
                return false;
            }
        }
    }

    /// <summary>
    /// Delete a PLC configuration
    /// </summary>
    public bool DeleteConfig(string plcId)
    {
        lock (_fileLock)
        {
            try
            {
                var removed = _cachedConfig.Plcs.RemoveAll(p => p.PlcId == plcId);
                if (removed > 0)
                {
                    SaveConfigInternal();
                    _logger.LogInformation("[PLC CONFIG] Deleted config for PLC {PlcId}", plcId);
                    return true;
                }
                return false;
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "[PLC CONFIG] Failed to delete config for {PlcId}", plcId);
                return false;
            }
        }
    }

    /// <summary>
    /// Update connection status for a PLC
    /// </summary>
    public void UpdateStatus(string plcId, bool isConnected, string? lastError = null)
    {
        lock (_fileLock)
        {
            var config = _cachedConfig.Plcs.FirstOrDefault(p => p.PlcId == plcId);
            if (config != null)
            {
                config.LastKnownConnected = isConnected;
                config.LastError = lastError;
                config.LastStatusUpdate = DateTime.UtcNow;
                // Don't save to file for status updates (too frequent)
            }
        }
    }

    private PlcConfigFile LoadConfigInternal()
    {
        try
        {
            if (File.Exists(_configPath))
            {
                var json = File.ReadAllText(_configPath);
                var options = new JsonSerializerOptions 
                { 
                    PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
                    PropertyNameCaseInsensitive = true
                };
                var config = JsonSerializer.Deserialize<PlcConfigFile>(json, options);
                return config ?? new PlcConfigFile();
            }
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "[PLC CONFIG] Failed to load config file, starting fresh");
        }
        
        return new PlcConfigFile();
    }

    private void SaveConfigInternal()
    {
        try
        {
            _cachedConfig.LastModified = DateTime.UtcNow;
            
            var options = new JsonSerializerOptions 
            { 
                WriteIndented = true,
                PropertyNamingPolicy = JsonNamingPolicy.CamelCase
            };
            var json = JsonSerializer.Serialize(_cachedConfig, options);
            
            // Atomic write: temp file then rename
            var tempPath = _configPath + ".tmp";
            File.WriteAllText(tempPath, json);
            File.Move(tempPath, _configPath, true);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "[PLC CONFIG] Failed to write config file");
            throw;
        }
    }
}

/// <summary>
/// Root config file structure
/// </summary>
public class PlcConfigFile
{
    public string Version { get; set; } = "1.0";
    public DateTime LastModified { get; set; } = DateTime.UtcNow;
    public List<SavedPlcConfig> Plcs { get; set; } = new();
}

/// <summary>
/// Saved PLC configuration
/// </summary>
public class SavedPlcConfig
{
    public string PlcId { get; set; } = "";
    public string Name { get; set; } = "";
    public string Protocol { get; set; } = "";
    public string IpAddress { get; set; } = "";
    public int Port { get; set; }
    public string? PlantId { get; set; }
    
    // Protocol-specific settings
    public int? Slot { get; set; }
    public int? Rack { get; set; }
    public string? Path { get; set; }
    public string? PlcType { get; set; }
    
    // Timing settings
    public int PollingIntervalMs { get; set; } = 1000;
    public int TimeoutMs { get; set; } = 5000;
    public int RetryCount { get; set; } = 3;
    public int ReconnectDelayMs { get; set; } = 5000;
    
    // Tags
    public List<SavedTagConfig> Tags { get; set; } = new();
    
    // Status tracking (not persisted to file, runtime only)
    public bool Enabled { get; set; } = true;
    public bool LastKnownConnected { get; set; }
    public string? LastError { get; set; }
    public DateTime? LastStatusUpdate { get; set; }
    public DateTime CreatedAt { get; set; }
    public DateTime UpdatedAt { get; set; }
}

/// <summary>
/// Saved tag configuration
/// </summary>
public class SavedTagConfig
{
    public string Name { get; set; } = "";
    public string Address { get; set; } = "";
    public string DataType { get; set; } = "double";
    public string? Description { get; set; }
}
