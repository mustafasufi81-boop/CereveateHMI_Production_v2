using Npgsql;

var connStr = "Host=localhost;Port=5432;Database=Cereveate;Username=cereveate;Password=cereveate@222";

Console.WriteLine("Fixing sample_source column type...");

using var conn = new NpgsqlConnection(connStr);
await conn.OpenAsync();

var sql = "ALTER TABLE historian_raw.historian_timeseries ALTER COLUMN sample_source TYPE CHAR(3)";

try
{
    using var cmd = new NpgsqlCommand(sql, conn);
    await cmd.ExecuteNonQueryAsync();
    Console.WriteLine("✅ Column altered to CHAR(3)");
}
catch (Exception ex)
{
    Console.WriteLine($"❌ Error: {ex.Message}");
}
