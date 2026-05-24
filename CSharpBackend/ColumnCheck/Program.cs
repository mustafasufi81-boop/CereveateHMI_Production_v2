using Npgsql;

var connStr = "Host=localhost;Port=5432;Database=Cereveate;Username=cereveate;Password=cereveate@222";

Console.WriteLine("Connecting to database...");
using var conn = new NpgsqlConnection(connStr);
await conn.OpenAsync();

var sql = @"
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'historian_meta'
AND table_name = 'tag_master'
ORDER BY ordinal_position";

using var cmd = new NpgsqlCommand(sql, conn);
using var reader = await cmd.ExecuteReaderAsync();

Console.WriteLine("\n✅ Columns in historian_meta.tag_master:");
Console.WriteLine("==========================================");
var actualColumns = new List<string>();
while (await reader.ReadAsync())
{
    var colName = reader.GetString(0);
    actualColumns.Add(colName);
    Console.WriteLine($"  {colName,-35} {reader.GetString(1),-20} nullable={reader.GetString(2)}");
}

Console.WriteLine("\n📋 Columns required by Controller INSERT:");
Console.WriteLine("==========================================");
var requiredColumns = new[] {
    "tag_id", "tag_name", "description", "plant", "area", "equipment", 
    "data_type", "eng_unit", "db_logging_interval_ms", "enabled", 
    "db_table_name", "created_by"
};

foreach (var col in requiredColumns)
{
    var exists = actualColumns.Contains(col);
    var icon = exists ? "✅" : "❌";
    Console.WriteLine($"  {icon} {col}");
}

Console.WriteLine("\n🔄 Columns used in ON CONFLICT UPDATE:");
Console.WriteLine("=======================================");
var updateColumns = new[] { "config_updated_at", "mapping_version" };
foreach (var col in updateColumns)
{
    var exists = actualColumns.Contains(col);
    var icon = exists ? "✅" : "❌";
    Console.WriteLine($"  {icon} {col}");
}

Console.WriteLine("\n✅ Done!");
