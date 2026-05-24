using Npgsql;

var connStr = "Host=localhost;Port=5432;Database=Cereveate;Username=cereveate;Password=cereveate@222";

Console.WriteLine("Fixing historian_timeseries table...");

using var conn = new NpgsqlConnection(connStr);
await conn.OpenAsync();

// Drop
Console.WriteLine("Dropping table...");
var dropSql = "DROP TABLE IF EXISTS historian_raw.historian_timeseries CASCADE";
using var dropCmd = new NpgsqlCommand(dropSql, conn);
await dropCmd.ExecuteNonQueryAsync();

// Recreate with explicit CHAR(3)
Console.WriteLine("Creating table...");
var createSql = @"
CREATE TABLE historian_raw.historian_timeseries (
    time TIMESTAMPTZ NOT NULL,
    tag_id TEXT NOT NULL,
    value_num DOUBLE PRECISION,
    value_text TEXT,
    value_bool BOOLEAN,
    quality CHAR(1),
    sample_source CHAR(3),
    mapping_version BIGINT NOT NULL DEFAULT 1
)";

using var createCmd = new NpgsqlCommand(createSql, conn);
await createCmd.ExecuteNonQueryAsync();

// Make it a hypertable
Console.WriteLine("Converting to hypertable...");
var hyperSql = "SELECT create_hypertable('historian_raw.historian_timeseries', 'time', chunk_time_interval => INTERVAL '4 hours', if_not_exists => TRUE)";
using var hyperCmd = new NpgsqlCommand(hyperSql, conn);
await hyperCmd.ExecuteNonQueryAsync();

// Verify
var verifySql = "SELECT data_type FROM information_schema.columns WHERE table_schema='historian_raw' AND table_name='historian_timeseries' AND column_name='sample_source'";
using var verifyCmd = new NpgsqlCommand(verifySql, conn);
var dataType = await verifyCmd.ExecuteScalarAsync();

Console.WriteLine($"\n✅ Done! sample_source type: {dataType}");
