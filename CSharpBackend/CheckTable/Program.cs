using Npgsql;

var connStr = "Host=localhost;Port=5432;Database=Cereveate;Username=cereveate;Password=cereveate@222";

using var conn = new NpgsqlConnection(connStr);
await conn.OpenAsync();

// Check if historian_timeseries table exists
var checkTable = @"
SELECT EXISTS (
    SELECT FROM information_schema.tables 
    WHERE table_schema = 'historian_raw' 
    AND table_name = 'historian_timeseries'
)";

using var cmd = new NpgsqlCommand(checkTable, conn);
var exists = (bool)(await cmd.ExecuteScalarAsync() ?? false);

Console.WriteLine($"historian_raw.historian_timeseries exists: {exists}");

if (exists)
{
    // Check table structure
    var colSql = @"
    SELECT column_name, data_type 
    FROM information_schema.columns 
    WHERE table_schema = 'historian_raw' 
    AND table_name = 'historian_timeseries'
    ORDER BY ordinal_position";
    
    using var colCmd = new NpgsqlCommand(colSql, conn);
    using var reader = await colCmd.ExecuteReaderAsync();
    
    Console.WriteLine("\nColumns:");
    while (await reader.ReadAsync())
    {
        Console.WriteLine($"  {reader.GetString(0),-20} {reader.GetString(1)}");
    }
}
else
{
    Console.WriteLine("\n❌ Table does NOT exist! Need to run production_schema.sql");
}
