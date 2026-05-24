using Npgsql;

var connStr = "Host=localhost;Port=5432;Database=Cereveate;Username=cereveate;Password=cereveate@222";

using var conn = new NpgsqlConnection(connStr);
await conn.OpenAsync();

// Delete the tag
var deleteSql = "DELETE FROM historian_meta.tag_master WHERE tag_id = '@Client0'";
using var deleteCmd = new NpgsqlCommand(deleteSql, conn);
var rowsDeleted = await deleteCmd.ExecuteNonQueryAsync();

Console.WriteLine($"✅ Deleted {rowsDeleted} row(s) for tag '@Client0'");

// Verify it's gone
var verifySql = "SELECT COUNT(*) FROM historian_meta.tag_master WHERE tag_id = '@Client0'";
using var verifyCmd = new NpgsqlCommand(verifySql, conn);
var count = (long)(await verifyCmd.ExecuteScalarAsync() ?? 0L);

Console.WriteLine($"Verification: {count} row(s) found (should be 0)");
Console.WriteLine();
Console.WriteLine("✅ Tag deleted. Now try saving from the UI!");
