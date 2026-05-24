using Npgsql;
using OpcDaWebBrowser.Services.AlarmEvaluation.Config;
using OpcDaWebBrowser.Services.AlarmEvaluation.Models;
using OpcDaWebBrowser.Services.HistorianIngest.Config;
using System.Collections.Concurrent;

namespace OpcDaWebBrowser.Services.AlarmEvaluation.Services;

/// <summary>
/// Thread-safe read-only cache of alarm setpoints loaded from historian_meta.tag_master.
///
/// Design rules:
/// ✔ Never writes to tag_master — pure read
/// ✔ Atomic cache swap — no partial state visible to consumers during refresh
/// ✔ Circuit-safe: logs error and retains stale cache on DB failure (does not crash)
/// ✔ Refresh interval driven by AlarmEvaluationConfig — no hardcoded timers
/// ✔ All DB connection config from HistorianConfig.Database.ConnectionString
/// </summary>
public sealed class AlarmSetpointCacheService : IDisposable
{
    private readonly HistorianConfig _dbConfig;
    private readonly AlarmEvaluationConfig _alarmConfig;
    private readonly ILogger<AlarmSetpointCacheService> _logger;

    // Snapshot is replaced atomically on each refresh — readers never see partial state.
    private volatile IReadOnlyDictionary<string, AlarmSetpoint> _snapshot =
        new Dictionary<string, AlarmSetpoint>(StringComparer.OrdinalIgnoreCase);

    private readonly SemaphoreSlim _refreshLock = new(1, 1);
    private Timer? _refreshTimer;
    private volatile bool _disposed;

    public bool IsInitialized { get; private set; }
    public int Count => _snapshot.Count;

    public AlarmSetpointCacheService(
        HistorianConfig dbConfig,
        AlarmEvaluationConfig alarmConfig,
        ILogger<AlarmSetpointCacheService> logger)
    {
        _dbConfig    = dbConfig    ?? throw new ArgumentNullException(nameof(dbConfig));
        _alarmConfig = alarmConfig ?? throw new ArgumentNullException(nameof(alarmConfig));
        _logger      = logger      ?? throw new ArgumentNullException(nameof(logger));
    }

    // =========================================================
    // INIT
    // =========================================================

    public async Task InitializeAsync(CancellationToken ct = default)
    {
        await RefreshAsync(ct);

        var interval = TimeSpan.FromSeconds(_alarmConfig.SetpointCacheRefreshIntervalSeconds);
        _refreshTimer = new Timer(
            _ => _ = SafeRefreshAsync(),
            null,
            interval,
            interval);

        IsInitialized = true;
        _logger.LogInformation(
            "AlarmSetpointCacheService initialized: {Count} alarm-enabled tags loaded (refresh every {Sec}s)",
            Count, _alarmConfig.SetpointCacheRefreshIntervalSeconds);
    }

    // =========================================================
    // PUBLIC READS — lock-free, safe for concurrent callers
    // =========================================================

    /// <summary>Returns alarm setpoint for a tag, or null if tag has no alarm configured.</summary>
    public AlarmSetpoint? GetSetpoint(string tagId) =>
        _snapshot.TryGetValue(tagId, out var sp) ? sp : null;

    /// <summary>Returns list of all tag IDs that have alarm evaluation enabled.</summary>
    public IReadOnlyList<string> GetAllAlarmTagIds() =>
        _snapshot.Keys.ToList();

    // =========================================================
    // REFRESH
    // =========================================================

    private async Task SafeRefreshAsync()
    {
        try
        {
            await RefreshAsync(CancellationToken.None);
        }
        catch (Exception ex)
        {
            // Log and retain stale cache — evaluation continues with last good data
            _logger.LogError(ex,
                "AlarmSetpointCacheService: background refresh failed — retaining previous cache ({Count} tags)",
                Count);
        }
    }

    private async Task RefreshAsync(CancellationToken ct)
    {
        if (!await _refreshLock.WaitAsync(TimeSpan.FromSeconds(5), ct))
        {
            _logger.LogDebug("AlarmSetpointCacheService: refresh already in progress, skipping this cycle");
            return;
        }

        try
        {
            await using var conn = new NpgsqlConnection(_dbConfig.Database.ConnectionString);
            await conn.OpenAsync(ct);

            // Columns mapped to AlarmSetpoint properties — no *, always explicit
            const string sql = """
                SELECT
                    tag_id,
                    alarm_hh_limit,
                    alarm_h_limit,
                    alarm_l_limit,
                    alarm_ll_limit,
                    COALESCE(alarm_deadband,       0.0)   AS alarm_deadband,
                    COALESCE(alarm_priority,       3)     AS alarm_priority,
                    interlock_type,
                    COALESCE(is_trip_initiator,    false) AS is_trip_initiator,
                    causes_trip_on_tag,
                    trip_category,
                    COALESCE(alarm_onset_delay_s,  0)     AS alarm_onset_delay_s
                FROM historian_meta.tag_master
                WHERE alarm_enabled = true
                  AND tag_id IS NOT NULL
                ORDER BY tag_id
                """;

            await using var cmd = new NpgsqlCommand(sql, conn)
            {
                CommandTimeout = _dbConfig.Database.CommandTimeout
            };
            await using var rdr = await cmd.ExecuteReaderAsync(ct);

            var fresh = new Dictionary<string, AlarmSetpoint>(StringComparer.OrdinalIgnoreCase);
            while (await rdr.ReadAsync(ct))
            {
                var tagId = rdr.GetString(0);
                fresh[tagId] = new AlarmSetpoint
                {
                    TagId            = tagId,
                    HhLimit          = rdr.IsDBNull(1)  ? null : rdr.GetDouble(1),
                    HLimit           = rdr.IsDBNull(2)  ? null : rdr.GetDouble(2),
                    LLimit           = rdr.IsDBNull(3)  ? null : rdr.GetDouble(3),
                    LlLimit          = rdr.IsDBNull(4)  ? null : rdr.GetDouble(4),
                    AlarmDeadband    = rdr.GetDouble(5),
                    AlarmPriority    = rdr.GetInt32(6),
                    InterlockType    = rdr.IsDBNull(7)  ? null : rdr.GetString(7),
                    IsTripInitiator  = rdr.GetBoolean(8),
                    CausesTripOnTag  = rdr.IsDBNull(9)  ? null : rdr.GetString(9),
                    TripCategory     = rdr.IsDBNull(10) ? null : rdr.GetString(10),
                    OnsetDelaySeconds= rdr.GetInt32(11),
                };
            }

            // Atomic swap — never exposes a half-built dictionary
            _snapshot = fresh;

            _logger.LogInformation(
                "AlarmSetpointCache refreshed: {Count} alarm-enabled tags",
                fresh.Count);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "AlarmSetpointCacheService.RefreshAsync failed");
            throw;
        }
        finally
        {
            _refreshLock.Release();
        }
    }

    // =========================================================
    // DISPOSE
    // =========================================================

    public void Dispose()
    {
        if (_disposed) return;
        _disposed = true;
        _refreshTimer?.Dispose();
        _refreshLock.Dispose();
    }
}
