using Npgsql;

var connStr = "Host=localhost;Port=5432;Database=Cereveate;Username=cereveate;Password=cereveate@222";

Console.WriteLine("=== Checking Tag Mapping ===");
using var conn = new NpgsqlConnection(connStr);
await conn.OpenAsync();

// Check tag_master
var tagSql = "SELECT tag_id, tag_name, enabled, db_logging_interval_ms, mapping_version FROM historian_meta.tag_master";
using var tagCmd = new NpgsqlCommand(tagSql, conn);
using var tagReader = await tagCmd.ExecuteReaderAsync();

Console.WriteLine("\nTags in tag_master:");
while (await tagReader.ReadAsync())
{
    Console.WriteLine($"  Tag: {tagReader.GetString(0)}, Name: {tagReader.GetString(1)}, Enabled: {tagReader.GetBoolean(2)}, Interval: {tagReader.GetInt32(3)}ms, Version: {tagReader.GetInt64(4)}");
}
tagReader.Close();

// Check timeseries data
var dataSql = "SELECT COUNT(*) FROM historian_raw.historian_timeseries WHERE tag_id = '@Client0'";
using var dataCmd = new NpgsqlCommand(dataSql, conn);
var count = (long)(await dataCmd.ExecuteScalarAsync() ?? 0L);

Console.WriteLine($"\n✅ Total rows in timeseries for @Client0: {count}");

// Check recent data
var recentSql = @"
SELECT time, tag_id, value_num, quality 
FROM historian_raw.historian_timeseries 
WHERE tag_id = '@Client0' 
ORDER BY time DESC 
LIMIT 5";

using var recentCmd = new NpgsqlCommand(recentSql, conn);
using var recentReader = await recentCmd.ExecuteReaderAsync();

Console.WriteLine("\nRecent data:");
while (await recentReader.ReadAsync())
{
    Console.WriteLine($"  {recentReader.GetDateTime(0):yyyy-MM-dd HH:mm:ss} | {recentReader.GetString(1)} | Value: {(recentReader.IsDBNull(2) ? "NULL" : recentReader.GetDouble(2).ToString())} | Quality: {(recentReader.IsDBNull(3) ? "NULL" : recentReader.GetString(3))}");
}
