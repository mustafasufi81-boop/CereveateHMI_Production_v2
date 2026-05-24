# Historian Tag Mapping & Value Logging Flow

## Issue Analysis: Why UI Save May Fail

### Root Cause Found
The UI `saveMapping()` JavaScript sends a payload with **camelCase** property names:
```javascript
{
    tagId: "...",
    tagName: "...",
    dataType: "...",
    dbLoggingIntervalMs: 1000,
    ...
}
```

BUT C# controller expects **PascalCase** (`TagMapping` model):
```csharp
public class TagMapping {
    public string TagId { get; set; }
    public string TagName { get; set; }
    public TagDataType DataType { get; set; }
    public int DbLoggingIntervalMs { get; set; }
    ...
}
```

**ASP.NET Core** by default uses camelCase JSON serialization, so the binding SHOULD work... UNLESS:
- The enum `TagDataType` fails to parse (UI sends "double" → enum expects `Double/double`)
- The response parsing fails if server returns 500 error before reaching the `Ok()` result

### Actual Data Flow (When Working)

## 1. UI → Controller Save Path
```
User clicks "Enable Logging" button
  ↓
quickEnableTag("TAG_ID") auto-fills modal form
  ↓
User clicks "Save" → saveMapping(e)
  ↓
Payload built: { tagId, tagName, dataType: "double", dbLoggingIntervalMs: 1000, plant, area, equipment, enabled: true }
  ↓
POST /api/historian/mapping
  ↓
HistorianMappingController.UpsertMapping([FromBody] TagMapping mapping)
  ↓
Normalization logic fills missing fields (Plant1/Area1/Equipment1)
  ↓
INSERT INTO historian_meta.tag_master ... ON CONFLICT ... RETURNING mapping_version
  ↓
LogEventAsync(MappingUpdate event) → historian_admin.historian_events
  ↓
Return Ok({ success: true, tag_id, mapping_version, message })
```

**✅ Test confirmed this path works** (standalone script saved TEST_TAG_001)

## 2. Tag Values Logging Path

### Startup Sequence
```
Program.cs
  ↓
AddSingleton<HistorianConfig> (binds appsettings.json "Historian" section)
  ↓
AddSingleton<MappingCacheService>
AddSingleton<RateControllerService>
AddSingleton<BatcherService>
AddSingleton<DbWriterService>
AddSingleton<SpoolManagerService>
  ↓
AddHostedService<HistorianIngestHostedService>
  ↓
HistorianIngestHostedService.ExecuteAsync(CancellationToken)
```

### Runtime Data Pipeline

```
OPC DA Server sends tag updates
  ↓
OpcDaService.TagValuesUpdated event fires
  ↓
HistorianIngestHostedService.OnOpcTagValuesUpdated(sender, TagValuesEventArgs e)
  ↓
For each tag:
  1. Convert to RawSample { Time, TagId, RawValue, Quality, Source="OPC" }
  2. RateControllerService.ProcessSample(rawSample)
     - Checks if tag exists in _mappingCache (via GetMapping(tagId))
     - Applies frequency filter (db_logging_interval_ms)
     - Applies deadband filter (if configured)
     - Returns null if filtered out
  3. MapSample(filteredSample)
     - Gets mapping from MappingCacheService.GetMapping(tagId)
     - IF mapping == null OR !mapping.Enabled → return null (SKIP)
     - Convert value by DataType (Double/Int/Bool/String)
     - Build MappedSample { Time, TagId, ValueNum, ValueBool, ValueText, Quality, MappingVersion, DbTableName }
  4. BatcherService.AddSampleAsync(mappedSample)
     - Adds to channel
  5. BatcherService groups samples into batches by:
     - Shard (hash of TagId % ShardCount)
     - MaxRows (10k default) or MaxWaitMs (2s default)
  6. HistorianIngestHostedService.ProcessBatchesAsync reads batches
  7. DbWriterService.WriteBatchAsync(batch)
     - Opens NpgsqlConnection
     - Begins transaction
     - COPY BINARY → historian_raw.historian_timeseries
       Columns: time, tag_id, value_num, value_text, value_bool, quality, sample_source, mapping_version
     - Calls update_latest_values_batch() stored procedure
       Updates: historian_raw.historian_latest_value
     - Commits transaction
  8. IF DB write fails:
     - SpoolManagerService.SpoolBatchAsync(batch) → disk file
     - Later replayed via timer
```

## 3. Key Tables & Schema

### historian_meta.tag_master (configuration)
- **Purpose**: Stores tag mappings (which OPC tags to log, at what interval)
- **Key Columns**:
  - `tag_id` (PK)
  - `enabled` (BOOLEAN) ← **CRITICAL**: if false, tag values are DROPPED
  - `db_logging_interval_ms` (1000-60000) ← controls sampling rate
  - `mapping_version` (auto-incremented on update) ← triggers cache refresh
- **Triggers**:
  - `trg_increment_mapping_version` → auto-bumps version on UPDATE
  - `trg_notify_mapping_change` → sends pg_notify('mapping_updated') → MappingCacheService listens

### historian_raw.historian_timeseries (hypertable)
- **Purpose**: Main timeseries storage (compressed after 2 days)
- **Columns**: time, tag_id, value_num, value_text, value_bool, quality, sample_source, mapping_version
- **Indexes**: (tag_id, time DESC), BRIN on time

### historian_raw.historian_latest_value (cache)
- **Purpose**: Fast lookup of most recent value per tag
- **Updated by**: `update_latest_values_batch()` stored function

### historian_admin.historian_events (audit log)
- **Stores**: MappingUpdate, WriterStart, SpoolWrite, UnmappedTag events
- **Used for**: troubleshooting, monitoring

## 4. Why Tag Values Might NOT Be Logged

### Checklist:
1. ✅ Tag exists in `historian_meta.tag_master`?
   ```sql
   SELECT * FROM historian_meta.tag_master WHERE tag_id = 'YOUR_TAG';
   ```

2. ✅ Tag is **enabled**?
   ```sql
   SELECT enabled FROM historian_meta.tag_master WHERE tag_id = 'YOUR_TAG';
   ```

3. ✅ MappingCacheService initialized?
   - Check logs for: `MappingCacheService initialized with X tags`
   - If missing → HistorianIngestHostedService not started

4. ✅ OPC connection active?
   - Tag must appear in `OpcDaService.ReadAllTagValues()` output
   - Check existing OPC UI for live values

5. ✅ OPC TagValuesUpdated event subscribed?
   - Check logs for: `Subscribed to OPC TagValuesUpdated events`

6. ✅ Rate controller not filtering out all samples?
   - If OPC sends values every 100ms but `db_logging_interval_ms = 60000` (1 min)
   - Only 1 in 600 samples will pass through

7. ✅ Database connection working?
   - Connection string in `appsettings.json` → `Host=localhost;Port=5432;Database=Cereveate;Username=cereveate;Password=cereveate@222`
   - Test with standalone script (✅ passed)

8. ✅ Spool directory exists?
   - `D:\HistorianSpool` must exist if `Spool.Enabled = true`

## 5. Debugging Commands

### Check if tags are mapped & enabled
```sql
SELECT tag_id, tag_name, enabled, db_logging_interval_ms, mapping_version
FROM historian_meta.tag_master
WHERE enabled = true
ORDER BY tag_id;
```

### Check recent data inserts
```sql
SELECT time, tag_id, value_num, quality
FROM historian_raw.historian_timeseries
ORDER BY time DESC
LIMIT 100;
```

### Check latest values cache
```sql
SELECT tag_id, time, value_num, updated_at
FROM historian_raw.historian_latest_value
ORDER BY updated_at DESC
LIMIT 50;
```

### Check events log
```sql
SELECT event_time, event_type, tag_id, message
FROM historian_admin.historian_events
ORDER BY event_time DESC
LIMIT 50;
```

### Verify mapping cache version
```http
GET http://localhost:5001/api/historian/mapping
```

## 6. Expected Normal Operation

After clicking "Enable Logging" for a tag:
1. POST saves tag to `tag_master` with `enabled = true`
2. pg_notify triggers MappingCacheService refresh (~30s max)
3. Next OPC update for that tag:
   - Passes rate control check
   - Gets mapped (not filtered)
   - Batched
   - Written to `historian_timeseries`
4. Within 2 seconds, value appears in database

## 7. Current Status

✅ **Database schema**: Working (test script proved INSERT succeeds)
✅ **Controller logic**: Normalizes missing fields, should handle UI payloads
❓ **UI save failure**: Need to verify:
   - Is server running when clicking Save?
   - Does browser console show network error?
   - What HTTP status code is returned?

⚠️ **Tag value logging**: Depends on:
   - HistorianIngestHostedService actually starting (check logs)
   - OPC service emitting TagValuesUpdated events
   - MappingCacheService having loaded the enabled tag

## Next Steps

1. **Start the ASP.NET server** (`dotnet run`)
2. **Check startup logs** for:
   ```
   HistorianIngestHostedService starting...
   MappingCacheService initialized with X tags
   Subscribed to OPC TagValuesUpdated events
   HistorianIngestHostedService started successfully
   ```
3. **Test UI save again** and capture:
   - Browser console errors
   - Network tab: HTTP status + response body
   - Server console: any exception stack traces
4. **Enable one tag**, wait 30s, then query:
   ```sql
   SELECT * FROM historian_raw.historian_timeseries WHERE tag_id = 'THE_TAG' ORDER BY time DESC LIMIT 10;
   ```
