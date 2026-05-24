using System;
using Npgsql;

namespace TestMappingSave;

class Program
{
    static void Main()
    {
        var connectionString = "Host=localhost;Port=5432;Database=Cereveate;Username=cereveate;Password=cereveate@222";
        
        Console.WriteLine("=== Historian Mapping Save Test ===");
        Console.WriteLine($"Connection: {connectionString}\n");

        try
        {
            using var connection = new NpgsqlConnection(connectionString);
            connection.Open();
            Console.WriteLine("✓ Database connected\n");

            // Test payload (mimics UI form submission)
            var tagId = "TEST_TAG_001";
            var tagName = "Test Tag 001";
            var plant = "Plant1";
            var area = "Area1";
            var equipment = "Equipment1";
            var dataType = "double";
            var dbLoggingIntervalMs = 1000;
            var enabled = true;
            var dbTableName = "historian_raw.historian_timeseries";
            var createdBy = "TestScript";

            var sql = @"
                INSERT INTO historian_meta.tag_master 
                    (tag_id, tag_name, description, plant, area, equipment, data_type, eng_unit, 
                     db_logging_interval_ms, enabled, db_table_name, created_by)
                VALUES 
                    (@tag_id, @tag_name, @description, @plant, @area, @equipment, @data_type, @eng_unit,
                     @db_logging_interval_ms, @enabled, @db_table_name, @created_by)
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
                RETURNING mapping_version";

            using var cmd = new NpgsqlCommand(sql, connection);
            cmd.Parameters.AddWithValue("tag_id", tagId);
            cmd.Parameters.AddWithValue("tag_name", tagName);
            cmd.Parameters.AddWithValue("description", DBNull.Value);
            cmd.Parameters.AddWithValue("plant", plant);
            cmd.Parameters.AddWithValue("area", area);
            cmd.Parameters.AddWithValue("equipment", equipment);
            cmd.Parameters.AddWithValue("data_type", dataType);
            cmd.Parameters.AddWithValue("eng_unit", DBNull.Value);
            cmd.Parameters.AddWithValue("db_logging_interval_ms", dbLoggingIntervalMs);
            cmd.Parameters.AddWithValue("enabled", enabled);
            cmd.Parameters.AddWithValue("db_table_name", dbTableName);
            cmd.Parameters.AddWithValue("created_by", createdBy);

            Console.WriteLine("Executing INSERT/UPDATE...");
            var version = (long?)cmd.ExecuteScalar();

            Console.WriteLine($"\n✅ SUCCESS!");
            Console.WriteLine($"   Tag ID: {tagId}");
            Console.WriteLine($"   Mapping Version: {version}");
            Console.WriteLine($"   Plant/Area/Equipment: {plant}/{area}/{equipment}");
            Console.WriteLine($"   Logging Interval: {dbLoggingIntervalMs}ms");
            Console.WriteLine($"   Enabled: {enabled}");

            // Verify by reading back
            Console.WriteLine("\n--- Verification Query ---");
            var verifySql = "SELECT tag_id, tag_name, plant, area, equipment, enabled, mapping_version FROM historian_meta.tag_master WHERE tag_id = @tag_id";
            using var verifyCmd = new NpgsqlCommand(verifySql, connection);
            verifyCmd.Parameters.AddWithValue("tag_id", tagId);
            
            using var reader = verifyCmd.ExecuteReader();
            if (reader.Read())
            {
                Console.WriteLine($"Tag ID: {reader.GetString(0)}");
                Console.WriteLine($"Tag Name: {reader.GetString(1)}");
                Console.WriteLine($"Plant: {reader.GetString(2)}");
                Console.WriteLine($"Area: {reader.GetString(3)}");
                Console.WriteLine($"Equipment: {reader.GetString(4)}");
                Console.WriteLine($"Enabled: {reader.GetBoolean(5)}");
                Console.WriteLine($"Version: {reader.GetInt64(6)}");
            }
        }
        catch (Exception ex)
        {
            Console.WriteLine($"\n❌ FAILED: {ex.Message}");
            Console.WriteLine($"\nStack Trace:\n{ex.StackTrace}");
            Environment.Exit(1);
        }
    }
}
