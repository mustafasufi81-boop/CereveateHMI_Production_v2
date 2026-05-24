# HIGH-PERFORMANCE PARQUET IMPORTER
## Quick Reference Guide

## 🚀 Quick Start (5 Steps)

### Step 1: Setup Database Schema

```bash
cd PostgresLogger
setup_importer.bat
```

**What it does:**
- Creates 7 tables (sensor_data, tag_catalog, file_imports, etc.)
- Creates TimescaleDB hypertable (1-day chunks, compression)
- Creates indexes for performance
- Creates monitoring views and functions

**Expected output:**
```
✅ PostgreSQL connected
✅ Schema created
✅ Tables verified: sensor_data, tag_catalog, file_imports, tag_imports
```

---

### Step 2: Configure Tag Mappings

Edit `config/app_config.json`:

```json
{
  "tag_mappings": [
    {
      "parquet_column": "TURBINE_SPEED_RPM",
      "tag_name": "Turbine Speed",
      "plant": "PowerPlant_A",
      "asset": "Turbine_01",
      "subsystem": "Rotor",
      "unit": "RPM",
      "sampling_frequency_seconds": 5,
      "enabled": true
    }
  ]
}
```

**Pro tip:** Start with 2-5 tags, verify it works, then add more.

---

### Step 3: Test Configuration

```bash
python test_importer.py
```

**Expected output:**
```
✅ PASS - Database Connection
✅ PASS - Schema Verification
✅ PASS - Tag Mappings (2 tags configured)
✅ PASS - Parquet Files (150 files found)
✅ PASS - Import Queue (empty, ready)
✅ PASS - Tag Catalog (0 tags, not processed yet)
✅ PASS - Sensor Data (0 records, ready)

✅ ALL TESTS PASSED - System ready for production
```

---

### Step 4: Initial Import (One-Time)

```bash
start_importer.bat
```

**What it does:**
- Scans `D:\OpcLogs\Data` for parquet files
- Enqueues all files (idempotent)
- Processes queue (imports mapped tags only)
- Logs results to database

**Expected output:**
```
Scanning directory: D:\OpcLogs\Data
Found 150 parquet files
Enqueued 150 new files

Processing file: data_20251202_120000.parquet
  Format: WIDE
  Found 10247 unique tags
  Mapped tags in config: 2
  Tags to import: 2
  Processed 1250 records after sampling
  Inserted 1250 records to sensor_data
=== FILE COMPLETE: 1250 records, 2.34s ===

...

IMPORT STATISTICS
  files_processed: 150
  files_success: 150
  files_failed: 0
  total_records: 187,500
  total_tags: 2
```

---

### Step 5: Start Continuous Service (Production)

```bash
start_continuous_service.bat
```

**What it does:**
- Monitors directory for new files (auto-import)
- Detects config changes (auto re-import new tags)
- Processes backlog periodically
- Runs until Ctrl+C

**Expected output:**
```
✅ Initial scan complete (150 files processed)
👁️  Watching directory: D:\OpcLogs\Data
✅ SERVICE RUNNING
   Press Ctrl+C to stop

📁 New file detected: data_20251202_143000.parquet
⚙️  Processing stable file: data_20251202_143000.parquet
✅ Imported 1250 records (2 tags)

🔄 CONFIG CHANGE DETECTED
   Tag count: 2 → 3
➕ 1 new tag(s) added
⚙️  Re-processing all files for new tags...
✅ Re-import complete (150 files processed)
```

---

## 📊 Monitoring & Verification

### Check Import Queue Status

```sql
-- Via SQL
SELECT * FROM v_import_queue;

-- Output:
 status     | file_count | total_size_bytes | oldest_file | newest_file
------------+------------+------------------+-------------+-------------
 SUCCESS    |        150 |      314572800   | 09:00:00    | 14:30:00
 PENDING    |          0 |              0   | NULL        | NULL
```

### Check Tag Catalog

```sql
SELECT * FROM v_tag_statistics WHERE is_mapped = TRUE LIMIT 10;

-- Output:
 tag_id              | is_mapped | record_count | file_count | first_seen | last_seen
---------------------+-----------+--------------+------------+------------+----------
 TURBINE_SPEED_RPM  | true      |       93,750 |        150 | 09:00:00   | 14:30:00
 GENERATOR_LOAD_MW  | true      |       93,750 |        150 | 09:00:00   | 14:30:00
```

### Check Recent Imports

```sql
SELECT * FROM v_recent_imports LIMIT 5;

-- Output:
 file_path                      | status  | records | tags | time_ms | timestamp
--------------------------------+---------+---------+------+---------+----------
 data_20251202_143000.parquet  | SUCCESS |    1250 |    2 |    2340 | 14:30:15
 data_20251202_142900.parquet  | SUCCESS |    1250 |    2 |    2310 | 14:29:15
```

### Check Sensor Data

```sql
SELECT 
    tag_code,
    COUNT(*) as records,
    MIN(timestamp) as first,
    MAX(timestamp) as last
FROM sensor_data
GROUP BY tag_code
ORDER BY records DESC;
```

### Python Test Utility

```bash
python test_importer.py

# Runs 7 comprehensive tests:
# ✅ Database Connection
# ✅ Schema Verification  
# ✅ Tag Mappings
# ✅ Parquet Files
# ✅ Import Queue
# ✅ Tag Catalog
# ✅ Sensor Data
```

---

## 🔧 Common Operations

### Add New Tag Mapping

**Option 1: Edit config file**

```json
// config/app_config.json
{
  "tag_mappings": [
    // ... existing mappings ...
    {
      "parquet_column": "BEARING_TEMP_C",
      "tag_name": "Bearing Temperature",
      "plant": "PowerPlant_A",
      "asset": "Turbine_01",
      "subsystem": "Bearings",
      "unit": "°C",
      "sampling_frequency_seconds": 10,
      "enabled": true
    }
  ]
}
```

**Option 2: Via API (if web server running)**

```bash
curl -X POST http://localhost:6001/api/tags/mapping \
  -H "Content-Type: application/json" \
  -d '{
    "parquet_column": "BEARING_TEMP_C",
    "tag_name": "Bearing Temperature",
    "plant": "PowerPlant_A",
    "asset": "Turbine_01",
    "subsystem": "Bearings",
    "unit": "°C",
    "sampling_frequency_seconds": 10,
    "enabled": true
  }'
```

**What happens:**
- Continuous service detects config change (checks every 5s)
- Automatically re-processes all files
- Imports only the new tag (skips already-imported tags)
- No manual intervention needed

---

### Discover All Tags in Parquet Files

**Via API:**
```bash
curl http://localhost:6001/api/tags/discover

# Returns:
{
  "format": "long",
  "source": "tag_catalog",
  "total_tags": 10247,
  "mapped_count": 2,
  "unmapped_count": 10245,
  "tags": [
    {"tag_id": "TURBINE_SPEED_RPM", "mapped": true, "mapping": {...}},
    {"tag_id": "BEARING_TEMP_C", "mapped": false, "mapping": null},
    ...
  ]
}
```

**Via SQL:**
```sql
SELECT tag_id, is_mapped, record_count, first_seen, last_seen
FROM tag_catalog
ORDER BY last_seen DESC
LIMIT 100;
```

---

### Re-Import After Config Change

**Automatic (if continuous service running):**
- Service detects config change every 5 seconds
- Automatically re-processes all files
- No action needed

**Manual (if continuous service NOT running):**
```bash
# Option 1: Run one-time import again
start_importer.bat

# Option 2: Start continuous service
start_continuous_service.bat
```

**How it works:**
```
1. Reads config → finds 3 mapped tags (was 2)
2. Re-enqueues all 150 files (idempotent, safe)
3. For each file:
   - Checks tag_imports: TURBINE_SPEED_RPM, GENERATOR_LOAD_MW already imported
   - Only imports BEARING_TEMP_C (new tag)
4. Result: 93,750 new records (1 tag × 150 files × 625 avg records/file)
```

---

### Check Failed Imports

```sql
SELECT 
    file_path,
    error_message,
    import_timestamp
FROM file_imports
WHERE status = 'FAILED'
ORDER BY import_timestamp DESC;

-- Fix issue (e.g., invalid parquet file)
-- Then reset status to retry:
UPDATE file_imports
SET status = 'PENDING'
WHERE id = 123;  -- Replace with actual file_id
```

---

### Clear Import History (Start Fresh)

```sql
-- WARNING: Deletes all import tracking (not sensor_data)
TRUNCATE TABLE file_imports CASCADE;
TRUNCATE TABLE tag_imports CASCADE;
TRUNCATE TABLE tag_catalog CASCADE;
TRUNCATE TABLE tag_file_catalog CASCADE;

-- sensor_data is preserved
-- Re-run importer to rebuild catalogs
```

---

### Change Sampling Frequency

**Edit config:**
```json
{
  "parquet_column": "TURBINE_SPEED_RPM",
  "sampling_frequency_seconds": 10  // Changed from 5 to 10
}
```

**Effect:**
- New files: 10-second sampling applied
- Old data: Already imported, not affected
- To re-import with new frequency: Clear tag_imports for this tag

```sql
DELETE FROM tag_imports WHERE tag_id = 'TURBINE_SPEED_RPM';
UPDATE file_imports SET status = 'PENDING';  -- Re-enqueue all files
```

---

## 🐛 Troubleshooting

### Problem: "No parquet files found"

**Check:**
```bash
dir "D:\OpcLogs\Data\*.parquet"
```

**Solution:**
- Ensure OPC DA service is running
- Check `logging-config.json` → `ParquetLogsPath`
- Verify files are 2MB (rotation threshold)

---

### Problem: "Cannot connect to PostgreSQL"

**Check:**
```bash
psql -U cereveate -d Cereveate -c "SELECT 1;"
```

**Solution:**
- Ensure PostgreSQL service running
- Check `config/app_config.json` → `database` section
- Verify user `cereveate` has access

---

### Problem: "No tags mapped"

**Check:**
```bash
python -c "from utils.config_manager import get_config_manager; print(len(get_config_manager().get_enabled_tag_mappings()))"
```

**Solution:**
- Add tag mappings to `config/app_config.json`
- Ensure `"enabled": true` in each mapping

---

### Problem: "Continuous service not detecting new files"

**Check:**
1. Is service running? (Look for console output)
2. Is watchdog installed? `pip install watchdog`
3. Are files stable? (Service waits 5 seconds before processing)

**Solution:**
```bash
# Reinstall dependencies
pip install -r requirements.txt

# Restart service
start_continuous_service.bat
```

---

### Problem: "Re-import not working after adding new tag"

**Check:**
```sql
SELECT status, COUNT(*) FROM file_imports GROUP BY status;
```

**If all SUCCESS:**
```sql
-- Manual re-enqueue
UPDATE file_imports SET status = 'PENDING' WHERE status = 'SUCCESS';
```

**Then run:**
```bash
start_importer.bat
```

---

## 📈 Performance Tips

### For 10,000+ Tags

1. **Use Concurrent Workers**
   ```bash
   # Start 4 workers (separate terminals)
   python services/high_performance_importer.py  # Worker 1
   python services/high_performance_importer.py  # Worker 2
   python services/high_performance_importer.py  # Worker 3
   python services/high_performance_importer.py  # Worker 4
   
   # SKIP LOCKED ensures no conflicts
   ```

2. **Optimize Sampling Frequency**
   ```json
   // High-frequency tags (fast-changing)
   {"tag": "TURBINE_SPEED_RPM", "sampling_frequency_seconds": 1}
   
   // Medium-frequency tags (slow-changing)
   {"tag": "BEARING_TEMP_C", "sampling_frequency_seconds": 10}
   
   // Low-frequency tags (static)
   {"tag": "CONFIG_VERSION", "sampling_frequency_seconds": 300}
   ```

3. **Batch Tag Mappings**
   ```bash
   # Add 1000 tags at once (API batch endpoint - future)
   # For now: Use text editor with multi-cursor to duplicate config blocks
   ```

4. **Enable Compression**
   ```sql
   -- Already enabled in schema_complete.sql
   -- Compresses data older than 7 days
   -- 5-10x size reduction
   ```

---

## 📁 File Structure

```
PostgresLogger/
├── schema_complete.sql                    ← Database schema (run once)
├── setup_importer.bat                     ← Setup script
├── start_importer.bat                     ← One-time import
├── start_continuous_service.bat           ← Continuous monitoring
├── test_importer.py                       ← System test utility
├── HIGH_PERFORMANCE_IMPORTER_README.md    ← Full documentation
├── QUICK_REFERENCE.md                     ← This file
│
├── config/
│   └── app_config.json                    ← Tag mappings, database config
│
├── services/
│   ├── high_performance_importer.py       ← Core importer engine
│   ├── continuous_importer_service.py     ← Continuous monitoring service
│   ├── background_importer.py             ← Old importer (deprecated)
│   └── background_importer_v2.py          ← Old importer v2 (deprecated)
│
└── api/
    └── main.py                            ← FastAPI server (tag discovery, trends)
```

---

## 🎯 Summary

**Initial Setup:**
```bash
1. setup_importer.bat              # Create schema
2. Edit config/app_config.json     # Add 2-5 tag mappings
3. python test_importer.py         # Verify setup
4. start_importer.bat              # Initial import
```

**Production Use:**
```bash
start_continuous_service.bat       # Run continuously
```

**Monitoring:**
```bash
python test_importer.py            # Quick health check
psql -U cereveate -d Cereveate     # SQL queries
```

**Adding Tags:**
```
1. Edit config/app_config.json     # Add new mappings
2. Service auto-detects change     # Waits 5 seconds
3. Automatic re-import             # Only new tags imported
```

---

## 📞 Support

**Check logs:**
```
PostgresLogger/high_performance_importer.log
PostgresLogger/continuous_importer.log
```

**Run diagnostics:**
```bash
python test_importer.py
```

**Common issues:**
- Database connection → Check PostgreSQL service running
- No files → Check OPC DA service writing parquet
- No data → Check tag mappings configured
- Slow import → Enable concurrent workers
