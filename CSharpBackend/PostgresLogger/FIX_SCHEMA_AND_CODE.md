# COMPLETE FIX FOR 10K TAG SYSTEM

## Problem Summary

The high-performance importer for 10K+ tags exists but has 2 bugs:

### Bug #1: Database Schema Missing Columns
- `tag_catalog` missing: `record_count`, `is_mapped`, `last_updated`
- `file_imports` missing: `worker_id`, `lock_acquired_at`, `started_at`, `completed_at`, `processing_time_ms`, `tags_imported`, `tags_skipped`, `file_format`, `total_tags_in_file`, `total_rows_in_file`, `enqueued_at`

### Bug #2: Quality Code Parsing
- Code expects INTEGER quality codes (192 = Good)
- Parquet files have STRING quality codes ("GOOD", "BAD")
- Line 424 in `high_performance_importer.py`: `int(quality_code)` fails

## Solution

### Step 1: Fix Database Schema

Run this SQL file (already created): `fix_all_schemas.sql`

```bash
cd PostgresLogger
$env:PGPASSWORD='cereveate@222'
psql -h localhost -U cereveate -d Cereveate -f fix_all_schemas.sql
```

### Step 2: Fix Quality Code Parsing

The code at line 420-424 in `high_performance_importer.py` needs to handle STRING quality codes.

**Current code (BROKEN):**
```python
quality_code = row.get('Quality', 192)
if pd.isna(quality_code):
    quality_code = 192

records.append({
    ...
    'quality_code': int(quality_code),  # ← FAILS if quality_code = "GOOD"
    ...
})
```

**Fixed code:**
```python
# Extract quality code (handle both integer and string)
quality_raw = row.get('Quality', 192)
if pd.isna(quality_raw):
    quality_code = 192
elif isinstance(quality_raw, str):
    # Map string quality codes to OPC integers
    quality_map = {
        'GOOD': 192,
        'BAD': 0,
        'UNCERTAIN': 64,
        'OK': 192
    }
    quality_code = quality_map.get(quality_raw.upper(), 192)
else:
    quality_code = int(quality_raw)

records.append({
    ...
    'quality_code': quality_code,
    'status_flag': 'OK' if quality_code == 192 else 'BAD',
    ...
})
```

### Step 3: Verify Fix

```bash
# Run importer
cd PostgresLogger
.\venv\Scripts\activate
python services\high_performance_importer.py

# Expected: NO MORE ERRORS
# Should see tags being cataloged and imported successfully
```

### Step 4: Check Results

```sql
-- Check tag catalog (should have all 10K+ tags)
SELECT COUNT(*) FROM tag_catalog;

-- Check imported data
SELECT COUNT(*) FROM sensor_data;

-- Check import status
SELECT * FROM v_import_queue;
```

## What Will Happen After Fix

1. **All 10,003 tags** will be cataloged in `tag_catalog`
2. **Only mapped tags** (currently 6) will be imported to `sensor_data`  
3. **Web UI** will show all 10,003 tags in "Discover Tags"
4. **User can add more mappings** → system auto-imports just those tags
5. **No duplicate imports** → tag-level idempotency working

## Files to Modify

1. `fix_all_schemas.sql` - Already created (fixes database)
2. `services/high_performance_importer.py` - Line 418-430 (fix quality code parsing)
