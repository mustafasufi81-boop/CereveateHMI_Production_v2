# Archive Configuration Guide

## Overview
The Parquet Archive Service consolidates small parquet files into 200MB archives with fully configurable behavior through `logging-config.json`.

## Key Terminology
- **Archive** = Parquet consolidation (combining multiple small files into 200MB archives)
- **Compress** = ZIP compression (creating .zip files from archive files)

## Configuration Settings

### Location: `logging-config.json`

```json
{
  "ArchiveSettings": {
    "Enabled": true,
    "ArchiveIntervalMinutes": 5,
    "AutoCompressEnabled": false
  }
}
```

### Settings Explained

#### 1. **Enabled** (boolean, default: true)
Controls whether the archive service runs at all.

- `true`: Service runs and consolidates parquet files
- `false`: Service starts but immediately exits (logs "⏸️ Archiving is DISABLED")

**Use Cases:**
- Set to `false` during maintenance or troubleshooting
- Set to `false` if you want to accumulate small files without archiving
- Set to `true` for normal operation

#### 2. **ArchiveIntervalMinutes** (integer, default: 60)
How often the archive process runs (in minutes).

- **Minimum recommended**: 5 minutes (current setting)
- **Maximum recommended**: 1440 minutes (24 hours)
- **Production typical**: 60 minutes (1 hour)

**Current Setting:** 5 minutes (every 5 minutes the service checks for files to archive)

**Use Cases:**
- `5`: Aggressive archiving for high-volume data (current setting)
- `60`: Balanced for typical production (default)
- `1440`: Daily archiving for low-volume systems

#### 3. **AutoCompressEnabled** (boolean, default: false)
Controls automatic ZIP compression of old archive files.

- `true`: Daily background job compresses archives older than 7 days
- `false`: Compression only via manual UI button (current setting)

**Current Setting:** `false` (disabled)

**Use Cases:**
- Set to `false` if you want manual control over compression (current)
- Set to `true` for fully automated long-term storage compression

## How It Works

### Archive Flow (Parquet Consolidation)

```
Every 5 minutes (configurable):
1. Scan D:\OpcLogs\Data for parquet files
2. Sort by oldest first
3. Append files to current archive until 200MB reached
4. Create new archive when size limit hit
5. Delete original small files after successful archive
6. Log all operations to D:\OpcLogs\Backup\Logs\Archive_YYYYMMDD.log
```

**Skip Conditions:**
- File is locked by another process → skip and try next
- File is corrupted or incomplete → skip with warning
- Archive operation fails → retry next interval

### Compress Flow (ZIP Compression)

**Manual (via UI):**
1. Navigate to Archive tab
2. Select date range (max 31 days, min 1 day old)
3. Click "Compress Archives" button
4. Archives grouped by date and compressed into ZIP files
5. Download ZIP files from "Compressed Archives" section

**Automatic (when enabled):**
```
Daily at midnight:
1. Find archives older than 7 days
2. Group by date (YYYY-MM-DD)
3. Compress each day's archives into single ZIP
4. Delete original archive files after successful compression
```

## Service Behavior by Configuration

### Current Configuration (Production)
```json
{
  "Enabled": true,
  "ArchiveIntervalMinutes": 15,
  "AutoCompressEnabled": false
}
```

**Behavior:**
- ✅ Archive consolidation runs every 5 minutes
- ✅ Combines small parquet files into 200MB archives
- ✅ Logs to `D:\OpcLogs\Backup\Logs\Archive_YYYYMMDD.log`
- ❌ NO automatic ZIP compression
- ✅ Manual compression available via UI

**Log Example:**
```
[2025-01-16 10:00:00] 🗄️ Parquet Archive Service started
[2025-01-16 10:00:00] ✅ Archiving ENABLED - interval: 5 minutes, auto-compress: disabled
[2025-01-16 10:00:01] 📦 Archived 15 files (45.2 MB) → Archive_2025-01-16_001.parquet
```

### Disabled Configuration
```json
{
  "Enabled": false,
  "ArchiveIntervalMinutes": 5,
  "AutoCompressEnabled": false
}
```

**Behavior:**
- ❌ Service does NOT run
- ❌ No parquet consolidation
- ❌ No compression
- ⏸️ Service exits immediately with log: "⏸️ Archiving is DISABLED in configuration"

**Log Example:**
```
[2025-01-16 10:00:00] 🗄️ Parquet Archive Service started
[2025-01-16 10:00:00] ⏸️ Archiving is DISABLED in configuration - service will not run
```

### Hourly Archive + Auto-Compress Configuration
```json
{
  "Enabled": true,
  "ArchiveIntervalMinutes": 60,
  "AutoCompressEnabled": true
}
```

**Behavior:**
- ✅ Archive consolidation runs every 60 minutes
- ✅ Combines small parquet files into 200MB archives
- ✅ Automatic daily compression of 7+ day old archives
- ✅ Manual compression still available via UI

**Log Example:**
```
[2025-01-16 10:00:00] 🗄️ Parquet Archive Service started
[2025-01-16 10:00:00] ✅ Archiving ENABLED - interval: 60 minutes, auto-compress: enabled
[2025-01-16 10:00:01] 📦 Archived 50 files (120.5 MB) → Archive_2025-01-16_001.parquet
[2025-01-17 00:00:00] 🗜️ Auto-compress: Found 3 archives older than 7 days
[2025-01-17 00:00:15] ✅ Compressed 3 files (600 MB) → Archive_2025-01-09.zip (245 MB, 59% saved)
```

## File Structure

### Archive Files
```
D:\OpcLogs\Backup\
├── Archive_2025-01-16_001.parquet (200 MB)
├── Archive_2025-01-16_002.parquet (200 MB)
├── Archive_2025-01-16_003.parquet (150 MB)
└── Logs\
    ├── Archive_20250116.log
    └── Archive_20250117.log
```

### Compressed Archives (when compression is used)
```
D:\OpcLogs\Backup\
├── Archive_2025-01-09.zip (245 MB - contains all archives from that day)
├── Archive_2025-01-10.zip (198 MB)
└── Logs\
    ├── Archive_20250116.log
    └── Archive_20250117.log
```

## Troubleshooting

### Service Not Running
**Check:** `logging-config.json` → `ArchiveSettings:Enabled`
```json
"ArchiveSettings": {
  "Enabled": false  ← Change to true
}
```

**Log Location:** `D:\OpcLogs\Backup\Logs\Archive_YYYYMMDD.log`

**Expected Log:** "✅ Archiving ENABLED - interval: X minutes, auto-compress: enabled/disabled"

### Archive Interval Too Slow/Fast
**Check:** `logging-config.json` → `ArchiveSettings:ArchiveIntervalMinutes`
```json
"ArchiveSettings": {
  "ArchiveIntervalMinutes": 5  ← Adjust to desired minutes
}
```

**Recommendations:**
- High data volume (>1000 tags): 5-15 minutes
- Medium volume (100-1000 tags): 30-60 minutes
- Low volume (<100 tags): 60-1440 minutes

### Automatic Compression Not Running
**Check:** `logging-config.json` → `ArchiveSettings:AutoCompressEnabled`
```json
"ArchiveSettings": {
  "AutoCompressEnabled": false  ← Change to true for auto-compress
}
```

**Note:** Auto-compress runs daily at midnight and only compresses archives older than 7 days.

### Manual Compression Fails
**Common Causes:**
1. Date range too recent (min 1 day old)
2. Date range too large (max 31 days)
3. No archive files in selected range

**Solution:** Use Archive UI validation rules:
- End date must be ≥ 1 day old
- Range must be ≤ 31 days
- Check "Archive Files" table for available dates

## Performance Considerations

### Archive Interval vs System Load

| Interval | Data Volume | CPU Impact | Disk I/O | Recommendation |
|----------|-------------|------------|----------|----------------|
| 5 min    | High (10K tags) | Low | Medium | ✅ Best for high-volume |
| 30 min   | Medium (1K tags) | Very Low | Low | ✅ Balanced |
| 60 min   | Any | Very Low | Low | ✅ Default/recommended |
| 1440 min | Low (<100 tags) | Very Low | Very Low | ⚠️ Only for low volume |

### File Size Impact

**Small Files (no archiving):**
- 1000s of small files → slow directory scans
- Higher disk overhead (metadata per file)
- Slower backup/restore operations

**Archived Files (200MB each):**
- ~50-100 files per day (typical)
- Fast directory operations
- Efficient backup/restore

**Compressed Files (ZIP):**
- 1 file per day (when auto-compress enabled)
- 40-60% size reduction
- Long-term storage optimized

## Best Practices

### Production Systems (Recommended)
```json
{
  "Enabled": true,
  "ArchiveIntervalMinutes": 60,
  "AutoCompressEnabled": false
}
```
- Hourly archiving keeps file count low
- Manual compression for control over storage
- Logs provide full audit trail

### High-Volume Systems (Current Configuration)
```json
{
  "Enabled": true,
  "ArchiveIntervalMinutes": 5,
  "AutoCompressEnabled": false
}
```
- Aggressive 5-minute archiving prevents file buildup
- Manual compression for flexibility
- Monitor disk space regularly

### Long-Term Storage Systems
```json
{
  "Enabled": true,
  "ArchiveIntervalMinutes": 60,
  "AutoCompressEnabled": true
}
```
- Hourly archiving for efficiency
- Automatic compression after 7 days
- Minimal manual intervention required

### Development/Testing Systems
```json
{
  "Enabled": false,
  "ArchiveIntervalMinutes": 60,
  "AutoCompressEnabled": false
}
```
- Disable archiving during development
- Keep small files for debugging
- Enable when testing complete

## Monitoring

### Key Metrics (Available in Archive UI)

1. **Total Archive Files**: Number of archive files in backup directory
2. **Total Size**: Combined size of all archive files
3. **Average Size**: Typical archive file size (~200MB when full)
4. **Log Count**: Number of daily log files available

### Health Indicators

**Healthy System:**
- Average size ~180-200 MB (near limit)
- Logs show successful operations (✅ symbols)
- File count grows steadily but manageable (<200 files/day)

**Warning Signs:**
- Average size <50 MB (interval may be too short)
- Logs show repeated "skipped" messages (file locking issues)
- File count >500 files/day (interval may be too long)

**Critical Issues:**
- Logs show continuous errors
- No new archives created (service disabled or failing)
- Disk space running low (<10% free)

## Configuration Change Workflow

### To Change Archive Interval:

1. Edit `logging-config.json`:
   ```json
   "ArchiveIntervalMinutes": 30  ← Change value
   ```

2. Restart application (service reads config on startup)

3. Verify in logs: `D:\OpcLogs\Backup\Logs\Archive_YYYYMMDD.log`
   ```
   ✅ Archiving ENABLED - interval: 30 minutes, auto-compress: disabled
   ```

4. Monitor first few cycles to ensure smooth operation

### To Enable/Disable Archiving:

1. Edit `logging-config.json`:
   ```json
   "Enabled": false  ← Toggle true/false
   ```

2. Restart application

3. Verify in logs:
   - Enabled: "✅ Archiving ENABLED - interval: X minutes"
   - Disabled: "⏸️ Archiving is DISABLED in configuration - service will not run"

### To Enable Auto-Compression:

1. Edit `logging-config.json`:
   ```json
   "AutoCompressEnabled": true  ← Change to true
   ```

2. Restart application

3. Wait for midnight (first auto-compress run)

4. Check logs next day:
   ```
   🗜️ Auto-compress: Found X archives older than 7 days
   ✅ Compressed X files → Archive_YYYY-MM-DD.zip
   ```

## Summary

- **Archive (consolidation)**: Controlled by `Enabled` + `ArchiveIntervalMinutes`
- **Compress (ZIP)**: Controlled by `AutoCompressEnabled` or manual UI button
- **Current setting**: 5-minute aggressive archiving, no auto-compress
- **Logs**: `D:\OpcLogs\Backup\Logs\Archive_YYYYMMDD.log` for all operations
- **UI**: `/Archive` page for stats, conversion, compression, log viewing

All settings take effect after application restart. No code changes required.
