using System.Text.Json;
using Npgsql;

static string? GetArg(string[] args, string key)
{
    foreach (var arg in args)
    {
        if (!arg.StartsWith("--", StringComparison.Ordinal))
            continue;

        var parts = arg[2..].Split('=', 2);
        if (parts.Length == 2 && parts[0].Equals(key, StringComparison.OrdinalIgnoreCase))
            return parts[1];
    }

    return null;
}

static string FindAppSettings()
{
    var dir = AppContext.BaseDirectory;
    while (!string.IsNullOrEmpty(dir))
    {
        var candidate = Path.Combine(dir, "appsettings.json");
        if (File.Exists(candidate))
            return candidate;

        dir = Directory.GetParent(dir)?.FullName ?? string.Empty;
    }

    throw new FileNotFoundException("Unable to locate appsettings.json in parent directories.");
}

var tagId = GetArg(args, "tagId") ?? "MANUAL_TAG_DEMO";
var tagName = GetArg(args, "tagName") ?? tagId;
var dataType = (GetArg(args, "dataType") ?? "double").ToLowerInvariant();
var intervalMs = int.TryParse(GetArg(args, "interval"), out var parsedInterval) ? parsedInterval : 1000;
var plant = GetArg(args, "plant") ?? "Plant1";
var area = GetArg(args, "area") ?? "Area1";
var equipment = GetArg(args, "equipment") ?? "Equipment1";
var enabled = !(GetArg(args, "enabled") is { } enabledArg && enabledArg.Equals("false", StringComparison.OrdinalIgnoreCase));
var engUnit = GetArg(args, "unit");
var description = GetArg(args, "description");

if (intervalMs < 1000 || intervalMs > 60000)
{
    Console.WriteLine("Interval must be between 1000 and 60000 ms. Aborting.");
    return;
}

var appSettingsPath = FindAppSettings();
using var json = JsonDocument.Parse(await File.ReadAllTextAsync(appSettingsPath));
var connectionString = json
    .RootElement
    .GetProperty("Historian")
    .GetProperty("Database")
    .GetProperty("ConnectionString")
    .GetString() ?? throw new InvalidOperationException("Connection string missing in appsettings.json");

await using var connection = new NpgsqlConnection(connectionString);
await connection.OpenAsync();

var sql = @"
    INSERT INTO historian_meta.tag_master
        (tag_id, tag_name, description, plant, area, equipment, data_type, eng_unit,
         db_logging_interval_ms, enabled, db_table_name, created_by)
    VALUES
        (@tag_id, @tag_name, @description, @plant, @area, @equipment, @data_type, @eng_unit,
         @db_logging_interval_ms, @enabled, 'historian_raw.historian_timeseries', 'ManualScript')
    ON CONFLICT (tag_id) DO UPDATE SET
        tag_name = EXCLUDED.tag_name,
        description = EXCLUDED.description,
        plant = EXCLUDED.plant,
        area = EXCLUDED.area,
        equipment = EXCLUDED.equipment,
        data_type = EXCLUDED.data_type,
        eng_unit = EXCLUDED.eng_unit,
        db_logging_interval_ms = EXCLUDED.db_logging_interval_ms,
        enabled = EXCLUDED.enabled,
        db_table_name = EXCLUDED.db_table_name,
        config_updated_at = now(),
        mapping_version = historian_meta.tag_master.mapping_version + 1
    RETURNING mapping_version;";

await using (var cmd = new NpgsqlCommand(sql, connection))
{
    cmd.Parameters.AddWithValue("tag_id", tagId);
    cmd.Parameters.AddWithValue("tag_name", tagName);
    cmd.Parameters.AddWithValue("description", (object?)description ?? DBNull.Value);
    cmd.Parameters.AddWithValue("plant", plant);
    cmd.Parameters.AddWithValue("area", area);
    cmd.Parameters.AddWithValue("equipment", equipment);
    cmd.Parameters.AddWithValue("data_type", dataType);
    cmd.Parameters.AddWithValue("eng_unit", (object?)engUnit ?? DBNull.Value);
    cmd.Parameters.AddWithValue("db_logging_interval_ms", intervalMs);
    cmd.Parameters.AddWithValue("enabled", enabled);

    var newVersion = (long)(await cmd.ExecuteScalarAsync() ?? 0L);
    Console.WriteLine($"Tag '{tagId}' upserted successfully. New mapping version: {newVersion}");
}

var verifySql = @"
    SELECT tag_id, tag_name, plant, area, equipment, db_logging_interval_ms, enabled, mapping_version
    FROM historian_meta.tag_master WHERE tag_id = @tag_id";

await using (var verifyCmd = new NpgsqlCommand(verifySql, connection))
{
    verifyCmd.Parameters.AddWithValue("tag_id", tagId);
    await using var reader = await verifyCmd.ExecuteReaderAsync();

    if (await reader.ReadAsync())
    {
        Console.WriteLine("Persisted mapping:");
        Console.WriteLine($"  Tag ID: {reader.GetString(0)}");
        Console.WriteLine($"  Tag Name: {reader.GetString(1)}");
        Console.WriteLine($"  Plant/Area/Equipment: {reader.GetString(2)}/{reader.GetString(3)}/{reader.GetString(4)}");
        Console.WriteLine($"  Interval (ms): {reader.GetInt32(5)}");
        Console.WriteLine($"  Enabled: {reader.GetBoolean(6)}");
        Console.WriteLine($"  Mapping Version: {reader.GetInt64(7)}");
    }
    else
    {
        Console.WriteLine("No row found after upsert, please verify database connectivity.");
    }
}
