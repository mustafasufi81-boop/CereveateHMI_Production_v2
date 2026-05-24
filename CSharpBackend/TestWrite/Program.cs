using Npgsql;

var connStr = "Host=localhost;Port=5432;Database=Cereveate;Username=cereveate;Password=cereveate@222";

Console.WriteLine("Testing database write...");

using var conn = new NpgsqlConnection(connStr);
await conn.OpenAsync();

// Try to insert a test row
var testSql = @"
INSERT INTO historian_raw.historian_timeseries 
    (time, tag_id, value_num, quality, sample_source, mapping_version)
VALUES 
    (NOW(), '@ClientCount', 999.0, 'G', 'TST', 1)";

try
{
    using var cmd = new NpgsqlCommand(testSql, conn);
    var rows = await cmd.ExecuteNonQueryAsync();
    Console.WriteLine($"✅ SUCCESS! Inserted {rows} row(s)");
    
    // Verify
    var verifySql = "SELECT COUNT(*) FROM historian_raw.historian_timeseries WHERE tag_id = '@ClientCount'";
    using var verifyCmd = new NpgsqlCommand(verifySql, conn);
    var count = (long)(await verifyCmd.ExecuteScalarAsync() ?? 0L);
    Console.WriteLine($"✅ Total rows for @ClientCount: {count}");
}
catch (Exception ex)
{
    Console.WriteLine($"❌ FAILED: {ex.Message}");
    Console.WriteLine($"Stack: {ex.StackTrace}");
}
