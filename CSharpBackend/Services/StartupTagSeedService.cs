using Npgsql;

namespace OpcDaWebBrowser.Services;

/// <summary>
/// Runs once at startup: if logging-config.json has no ServerProgId or no MonitoredTags,
/// queries historian_meta.tag_master for enabled OPC tags and auto-populates the config.
/// This means you never need to manually edit logging-config.json after a fresh deploy.
/// </summary>
public class StartupTagSeedService : IHostedService
{
    private readonly LoggingConfigService _configService;
    private readonly IConfiguration _appConfig;
    private readonly ILogger<StartupTagSeedService> _logger;

    public StartupTagSeedService(
        LoggingConfigService configService,
        IConfiguration appConfig,
        ILogger<StartupTagSeedService> logger)
    {
        _configService = configService;
        _appConfig = appConfig;
        _logger = logger;
    }

    public async Task StartAsync(CancellationToken cancellationToken)
    {
        try
        {
            var config = _configService.GetConfig();

            bool missingServer = string.IsNullOrWhiteSpace(config.ServerProgId);
            bool missingTags   = config.MonitoredTags == null || config.MonitoredTags.Count == 0;

            if (!missingServer && !missingTags)
            {
                _logger.LogInformation("[TagSeed] logging-config.json already has ServerProgId='{ProgId}' and {Count} monitored tags — skipping DB seed.",
                    config.ServerProgId, config.MonitoredTags!.Count);
                return;
            }

            _logger.LogInformation("[TagSeed] ServerProgId or MonitoredTags missing — querying tag_master to auto-populate...");

            var connStr = _appConfig.GetConnectionString("PlcGateway")
                       ?? _appConfig["Historian:ConnectionString"]
                       ?? _appConfig["Database:ConnectionString"];

            if (string.IsNullOrWhiteSpace(connStr))
            {
                _logger.LogWarning("[TagSeed] No DB connection string found — cannot seed tags from tag_master.");
                return;
            }

            await using var conn = new NpgsqlConnection(connStr);
            await conn.OpenAsync(cancellationToken);

            // ── 1. Get distinct OPC server ProgIDs ───────────────────────────────────
            string? progId = null;
            if (missingServer)
            {
                await using var cmd = new NpgsqlCommand(@"
                    SELECT DISTINCT server_progid
                    FROM historian_meta.tag_master
                    WHERE enabled = true
                      AND server_progid IS NOT NULL
                      AND server_progid <> ''
                      AND (plc_ip_address IS NULL OR plc_ip_address = '')
                    ORDER BY server_progid
                    LIMIT 1", conn);

                var result = await cmd.ExecuteScalarAsync(cancellationToken);
                progId = result as string;

                if (string.IsNullOrWhiteSpace(progId))
                {
                    _logger.LogWarning("[TagSeed] No enabled OPC server found in tag_master — cannot set ServerProgId.");
                }
                else
                {
                    _logger.LogInformation("[TagSeed] Found OPC server from tag_master: '{ProgId}'", progId);
                }
            }

            // ── 2. Get all enabled OPC tag IDs ───────────────────────────────────────
            var tags = new List<string>();
            if (missingTags)
            {
                var filterProgId = progId ?? config.ServerProgId;
                string sql;
                NpgsqlCommand tagCmd;

                if (!string.IsNullOrWhiteSpace(filterProgId))
                {
                    sql = @"
                        SELECT tag_id FROM historian_meta.tag_master
                        WHERE enabled = true
                          AND server_progid = @progId
                          AND (plc_ip_address IS NULL OR plc_ip_address = '')
                        ORDER BY tag_id";
                    tagCmd = new NpgsqlCommand(sql, conn);
                    tagCmd.Parameters.AddWithValue("progId", filterProgId);
                }
                else
                {
                    sql = @"
                        SELECT tag_id FROM historian_meta.tag_master
                        WHERE enabled = true
                          AND server_progid IS NOT NULL
                          AND server_progid <> ''
                          AND (plc_ip_address IS NULL OR plc_ip_address = '')
                        ORDER BY tag_id";
                    tagCmd = new NpgsqlCommand(sql, conn);
                }

                await using var _ = tagCmd;
                await using var reader = await tagCmd.ExecuteReaderAsync(cancellationToken);
                while (await reader.ReadAsync(cancellationToken))
                {
                    var tagId = reader.GetString(0);
                    if (!string.IsNullOrWhiteSpace(tagId))
                        tags.Add(tagId.Trim());
                }

                _logger.LogInformation("[TagSeed] Found {Count} enabled OPC tags in tag_master.", tags.Count);
            }

            // ── 3. Apply to config and save ──────────────────────────────────────────
            bool changed = false;

            if (missingServer && !string.IsNullOrWhiteSpace(progId))
            {
                _configService.SetServerConnection(progId, "localhost");
                _logger.LogInformation("[TagSeed] Auto-set ServerProgId='{ProgId}' from tag_master.", progId);
                changed = true;
            }

            if (missingTags && tags.Count > 0)
            {
                // Re-read config after possible SetServerConnection save
                var freshConfig = _configService.GetConfig();
                foreach (var tag in tags)
                {
                    if (!freshConfig.MonitoredTags.Contains(tag))
                        _configService.AddMonitoredTag(tag);
                }
                _logger.LogInformation("[TagSeed] Auto-added {Count} monitored tags from tag_master.", tags.Count);
                changed = true;
            }

            if (!changed)
            {
                _logger.LogWarning("[TagSeed] No OPC data found in tag_master to seed — logging-config.json unchanged.");
            }
            else
            {
                _logger.LogInformation("[TagSeed] logging-config.json successfully seeded from tag_master. OpcAutoConnectService will pick up the new config.");
            }
        }
        catch (Exception ex)
        {
            // Never crash startup — just log and continue
            _logger.LogError(ex, "[TagSeed] Failed to seed tags from tag_master — system will continue without auto-seed.");
        }
    }

    public Task StopAsync(CancellationToken cancellationToken) => Task.CompletedTask;
}
