using Npgsql;

var connStr = "Host=localhost;Port=5432;Database=Cereveate;Username=cereveate;Password=cereveate@222";

Console.WriteLine("Recreating historian_timeseries table with correct schema...");

using var conn = new NpgsqlConnection(connStr);
await conn.OpenAsync();

// Drop the table
var dropSql = "DROP TABLE IF EXISTS historian_raw.historian_timeseries CASCADE";
using var dropCmd = new NpgsqlCommand(dropSql, conn);
await dropCmd.ExecuteNonQueryAsync();
Console.WriteLine("✅ Dropped old table");

// Recreate with correct schema
var createSql = @"
CREATE TABLE historian_raw.historian_timeseries (
    time TIMESTAMPTZ NOT NULL,
    tag_id TEXT NOT NULL,
    value_num DOUBLE PRECISION NULL,
    value_text TEXT NULL,
    value_bool BOOLEAN NULL,
    quality CHAR(1) CHECK (quality IN ('G', 'B', 'U')),
    sample_source CHAR(3) DEFAULT 'OPC',
    mapping_version BIGINT NOT NULL DEFAULT 1
) WITH (fillfactor = 90)";

using var createCmd = new NpgsqlCommand(createSql, conn);
await createCmd.ExecuteNonQueryAsync();
Console.WriteLine("✅ Created table");

// Convert to hypertable
var hypertableSql = @"
SELECT create_hypertable(
    'historian_raw.historian_timeseries',
    'time',
    if_not_exists => TRUE,
    chunk_time_interval => INTERVAL '4 hours'
)";

using var hypertableCmd = new NpgsqlCommand(hypertableSql, conn);
await hypertableCmd.ExecuteNonQueryAsync();
Console.WriteLine("✅ Converted to hypertable");

Console.WriteLine("\n✅ Done! Table recreated with CHAR(3) for sample_source");
