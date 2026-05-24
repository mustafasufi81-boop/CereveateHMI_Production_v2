# PostgresLogger Implementation Summary

## Tables Created

### 1. file_imports
Tracks all parquet file processing attempts.
```sql
CREATE TABLE file_imports (
    id SERIAL PRIMARY KEY,
    file_path TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    file_size BIGINT,
    import_timestamp TIMESTAMPTZ DEFAULT NOW(),
    records_imported INTEGER DEFAULT 0,
    status TEXT DEFAULT 'PENDING',  -- SUCCESS, FAILED, SKIPPED
    error_message TEXT,
    UNIQUE(file_path, file_hash)
);
```

**Status meanings**:
- `SUCCESS`: File had mapped tags and data was imported
- `SKIPPED`: File had no mapped tags (catalog still updated)
- `FAILED`: Error during processing

### 2. tag_catalog
Fast lookup for all discovered TagIds across all files.
```sql
CREATE TABLE tag_catalog (
    tag_id TEXT PRIMARY KEY,
    first_seen TIMESTAMPTZ NOT NULL,
    last_seen TIMESTAMPTZ NOT NULL,
    last_file TEXT
);
```

## Key Features Implemented

### 1. Smart File Processing
- Detects long-format (`TagId, Timestamp, Value, Quality`) vs wide-format parquet
- Skips files already imported (checks `file_imports` by path+hash)
- Updates `tag_catalog` with ALL tags (mapped or not)
- Only imports data for mapped tags (from `config/app_config.json`)
- Logs files with no mapped tags as SKIPPED

### 2. Tag Catalog Auto-Update
- Every parquet import: extracts distinct TagIds → upserts to `tag_catalog`
- Every 60 seconds: scans latest parquet file → updates catalog with new tags
- API `/api/tags/discover` reads from catalog (instant response)

### 3. Sampling Frequency
- Respects `sampling_frequency_seconds` from tag mapping
- Tracks last timestamp per tag to filter out high-frequency duplicates
- 0 = import all data points

### 4. Re-import on New Mapping
When user maps a previously unmapped tag:
- System finds files with `status='SKIPPED'`
- Re-reads those files
- Imports data for newly mapped tag
- Updates `file_imports.records_imported` and status

## File Flow

```
New parquet file arrives
    ↓
Check file_imports (skip if SUCCESS)
    ↓
Read parquet → extract distinct TagIds
    ↓
Update tag_catalog (all tags)
    ↓
Check which tags are mapped
    ↓
Has mapped tags? ──NO──→ file_imports.status=SKIPPED
    ↓ YES
Import data for mapped tags only
    ↓
file_imports.status=SUCCESS, records_imported=N
```

## Next Steps

1. Run importer: `python services/background_importer.py`
2. Start API: `python api/main.py`
3. Open UI: http://localhost:6001
4. Click "Auto-Discover Tags" → should list all tags from catalog instantly
5. Map tags → data starts importing from old files too

## Configuration

All settings in `config/app_config.json`:
- `parquet_source.data_directory`: Where to watch for parquet files
- `parquet_source.check_interval_seconds`: How often to check for new files (default 10s)
- `parquet_source.stability_wait_seconds`: How long to wait before reading file (default 5s)
- `tag_mappings[]`: Array of tag configurations with sampling_frequency_seconds

