using Npgsql;
using System.Collections.Concurrent;
using System.Text.Json;
using OpcDaWebBrowser.Services.HistorianIngest.Config;
using OpcDaWebBrowser.Services.HistorianIngest.Models;

namespace OpcDaWebBrowser.Services.HistorianIngest.Services;

/// <summary>
/// Thread-safe in-memory cache of tag mappings from historian_meta.tag_master
/// Listens to PostgreSQL NOTIFY for instant refresh on mapping changes
/// </summary>
public class MappingCacheService : IDisposable
{
    private readonly HistorianConfig _config;
    private readonly ILogger<MappingCacheService> _logger;
    private readonly ConcurrentDictionary<string, TagMapping> _cache = new(StringComparer.OrdinalIgnoreCase);
    private readonly SemaphoreSlim _refreshLock = new(1, 1);
    private NpgsqlConnection? _notificationConnection;
    private Timer? _fallbackRefreshTimer;
    private int _currentMappingVersion = 0;
    private bool _isInitialized = false;

    public event EventHandler<TagMapping>? MappingUpdated;
    public event EventHandler<string>? MappingDeleted;

    public int Count => _cache.Count;
    public int CurrentMappingVersion => _currentMappingVersion;
    public bool IsInitialized => _isInitialized;

    public MappingCacheService(HistorianConfig config, ILogger<MappingCacheService> logger)
    {
        _config = config;
        _logger = logger;
    }

    /// <summary>
    /// Initialize cache and start notification listener
    /// </summary>
    public async Task InitializeAsync(CancellationToken cancellationToken = default)
    {
        _logger.LogInformation("Initializing MappingCacheService...");

        // Load all mappings
        await RefreshCacheAsync(cancellationToken);

        // Start PostgreSQL notification listener
        await StartNotificationListenerAsync(cancellationToken);

        // Start fallback refresh timer (every 30 seconds)
        _fallbackRefreshTimer = new Timer(
            async _ => await RefreshCacheAsync(CancellationToken.None),
            null,
            TimeSpan.FromSeconds(30),
            TimeSpan.FromSeconds(30)
        );

        _isInitialized = true;
        _logger.LogInformation($"MappingCacheService initialized with {_cache.Count} tags, version {_currentMappingVersion}");
    }

    /// <summary>
    /// Get tag mapping from cache (thread-safe)
    /// </summary>
    public TagMapping? GetMapping(string tagId)
    {
        _cache.TryGetValue(tagId, out var mapping);
        return mapping;
    }

    /// <summary>
    /// Check if tag exists and is enabled
    /// </summary>
    public bool IsTagEnabled(string tagId)
    {
        return _cache.TryGetValue(tagId, out var mapping) && mapping.Enabled;
    }

    /// <summary>
    /// Get all enabled mappings (snapshot)
    /// </summary>
    public List<TagMapping> GetAllEnabledMappings()
    {
        return _cache.Values.Where(m => m.Enabled).ToList();
    }

    /// <summary>
    /// Refresh entire cache from database
    /// </summary>
    public async Task RefreshCacheAsync(CancellationToken cancellationToken = default)
    {
        await _refreshLock.WaitAsync(cancellationToken);
        try
        {
            using var connection = new NpgsqlConnection(_config.Database.ConnectionString);
            await connection.OpenAsync(cancellationToken);

            var sql = @"
                SELECT tag_id, tag_name, description, plant, area, equipment, 
                       data_type, eng_unit, db_logging_interval_ms, 
                       enabled, db_table_name, mapping_version, 
                       config_updated_at, created_at, created_by
                FROM historian_meta.tag_master
                ORDER BY tag_id";

            using var cmd = new NpgsqlCommand(sql, connection);
            using var reader = await cmd.ExecuteReaderAsync(cancellationToken);

            var newCache = new Dictionary<string, TagMapping>(StringComparer.OrdinalIgnoreCase);
            int maxVersion = 0;

            while (await reader.ReadAsync(cancellationToken))
            {
                var mapping = new TagMapping
                {
                    TagId = reader.GetString(0),
                    TagName = reader.GetString(1),
                    Description = reader.IsDBNull(2) ? null : reader.GetString(2),
                    Plant = reader.IsDBNull(3) ? null : reader.GetString(3),
                    Area = reader.IsDBNull(4) ? null : reader.GetString(4),
                    Equipment = reader.IsDBNull(5) ? null : reader.GetString(5),
                    DataType = Enum.Parse<TagDataType>(reader.GetString(6), true),
                    EngUnit = reader.IsDBNull(7) ? null : reader.GetString(7),
                    DbLoggingIntervalMs = reader.GetInt32(8),
                    DeadbandValue = 0.0, // Not stored in production schema
                    Enabled = reader.GetBoolean(9),
                    DbTableName = reader.GetString(10),
                    MappingVersion = reader.IsDBNull(11) ? 1 : (int)reader.GetInt64(11), // BIGINT → int cast
                    ConfigUpdatedAt = reader.GetFieldValue<DateTimeOffset>(12),
                    CreatedAt = reader.GetFieldValue<DateTimeOffset>(13),
                    CreatedBy = reader.IsDBNull(14) ? null : reader.GetString(14)
                };

                newCache[mapping.TagId] = mapping;
                if (mapping.MappingVersion > maxVersion)
                    maxVersion = mapping.MappingVersion;
            }

            // Replace cache atomically
            _cache.Clear();
            foreach (var kvp in newCache)
            {
                _cache[kvp.Key] = kvp.Value;
            }

            _currentMappingVersion = maxVersion;
            _logger.LogInformation($"Cache refreshed: {_cache.Count} tags loaded, max version {_currentMappingVersion}");
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to refresh mapping cache");
            throw;
        }
        finally
        {
            _refreshLock.Release();
        }
    }

    /// <summary>
    /// Start listening to PostgreSQL NOTIFY for instant cache updates
    /// </summary>
    private async Task StartNotificationListenerAsync(CancellationToken cancellationToken)
    {
        try
        {
            _notificationConnection = new NpgsqlConnection(_config.Database.ConnectionString);
            await _notificationConnection.OpenAsync(cancellationToken);

            _notificationConnection.Notification += async (sender, args) =>
            {
                try
                {
                    _logger.LogDebug($"Received mapping notification: {args.Payload}");
                    
                    var notification = JsonSerializer.Deserialize<MappingNotification>(args.Payload);
                    if (notification != null)
                    {
                        // Refresh specific tag or entire cache
                        await RefreshCacheAsync(CancellationToken.None);
                    }
                }
                catch (Exception ex)
                {
                    _logger.LogError(ex, "Error processing mapping notification");
                }
            };

            using var cmd = new NpgsqlCommand("LISTEN mapping_updated", _notificationConnection);
            await cmd.ExecuteNonQueryAsync(cancellationToken);

            _logger.LogInformation("PostgreSQL notification listener started on channel 'mapping_updated'");

            // Keep connection alive
            _ = Task.Run(async () =>
            {
                while (!cancellationToken.IsCancellationRequested && _notificationConnection.State == System.Data.ConnectionState.Open)
                {
                    try
                    {
                        await _notificationConnection.WaitAsync(cancellationToken);
                    }
                    catch (Exception ex)
                    {
                        _logger.LogWarning(ex, "Notification listener interrupted, reconnecting...");
                        await Task.Delay(5000, cancellationToken);
                        await StartNotificationListenerAsync(cancellationToken);
                        break;
                    }
                }
            }, cancellationToken);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to start notification listener");
        }
    }

    public void Dispose()
    {
        _fallbackRefreshTimer?.Dispose();
        _notificationConnection?.Dispose();
        _refreshLock?.Dispose();
    }

    private class MappingNotification
    {
        public string? tag_id { get; set; }
        public string? operation { get; set; }
        public int mapping_version { get; set; }
    }
}
