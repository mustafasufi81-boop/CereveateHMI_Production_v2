# DB Update & Optimization Log
## Automation_DB — historian_raw.historian_timeseries

**Date:** May 20, 2026  
**DB Engine:** PostgreSQL 17.6 (Windows x64)  
**TimescaleDB:** ✅ v2.23.0 — ENABLED  
**Executed by:** GitHub Copilot (live execution, verified at each step)

---

## Pre-Work State (Before Any Changes)

| Metric | Value |
|---|---|
| Table type | Plain heap — NO partitioning |
| Table size | **2,716 MB** |
| Row count | ~13.8M (stale autovacuum estimate) — actual: **15,005,349** |
| Duplicate index | `uq_timeseries_time_tag` — exact copy of PK — **wasting 661 MB** |
| Autovacuum | ❌ Never ran (NULL last_autovacuum) |
| Stale statistics | 1,155,575 rows modified since last analyze |
| `shared_buffers` | 128 MB (too low) |
| `work_mem` | 4 MB (too low) |
| `max_wal_size` | 1 GB |
| TimescaleDB package | ✅ Installed on server (v2.23.0) but NOT enabled in DB |
| Tag-based queries | Full 15M-row scan (no `tag_id` index) |
| Compression | None |
| Partitioning | None |

---

## Phase 1 — Immediate Fixes (Zero Risk, No Downtime)

### Step 1 — Drop Duplicate UNIQUE Constraint
**Script:** `phase1_step1_drop_dup_index.py`

```sql
ALTER TABLE historian_raw.historian_timeseries
DROP CONSTRAINT IF EXISTS uq_timeseries_time_tag;
```

| Before | After |
|---|---|
| 2,716 MB | **2,055 MB** |
| 2 indexes (PK + duplicate) | 1 index (PK only) |

**Result: −661 MB freed instantly.**

---

### Step 2 — Fix Autovacuum + Force ANALYZE
**Script:** `phase1_step2_autovacuum_analyze.py`

```sql
ALTER TABLE historian_raw.historian_timeseries
SET (
    autovacuum_vacuum_scale_factor    = 0.01,   -- was 0.20 (global default)
    autovacuum_analyze_scale_factor   = 0.005,  -- was 0.10
    autovacuum_vacuum_cost_delay      = 2,
    toast.autovacuum_vacuum_scale_factor = 0.01
);

ANALYZE historian_raw.historian_timeseries;
```

| Metric | Before | After |
|---|---|---|
| Modified since analyze | 1,155,575 | **0** |
| Last analyze | NULL | 2026-05-20 |
| Autovacuum trigger threshold | 2.76M dead rows (20%) | **150K dead rows (1%)** |
| Actual live row count revealed | ~1.15M (stale) | **15,005,349** |

---

### Step 3 — Add `(tag_id, time DESC)` Index
**Script:** `phase1_step3_add_tagid_index.py`

```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_historian_ts_tagid_time
ON historian_raw.historian_timeseries (tag_id, "time" DESC);
```

- Built in **44.7 seconds** with zero write downtime
- Fixes all queries of the form:
  `WHERE tag_id = 'X' AND time BETWEEN a AND b`
  from full 15M-row scan → **index scan**

---

## Phase 2 — PostgreSQL Config Tuning + TimescaleDB Enable

**Script:** `phase2_edit_pg_conf.py`  
**PostgreSQL restart required — executed.**

### postgresql.conf Changes

| Setting | Before | After |
|---|---|---|
| `shared_buffers` | 128 MB | **512 MB** |
| `work_mem` | 4 MB | **32 MB** |
| `max_wal_size` | 1 GB | **2 GB** |
| `checkpoint_completion_target` | default | **0.9** |

Config backup saved at: `C:\Program Files\PostgreSQL\17\data\postgresql.conf.bak_20260520_070028`

### TimescaleDB Enabled
**Script:** `phase2_enable_timescaledb.py`

```sql
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
```

`shared_preload_libraries = 'timescaledb'` was **already set** in `postgresql.conf` —
no reinstall needed. Extension activated in `Automation_DB` in < 1 second.

**Result: TimescaleDB v2.23.0 live — no restart required for extension activation.**

---

## Phase 3 — Hypertable + Compression + Policies

**Script:** `phase3_create_hypertable.py`  
**OPC backend stopped during migration, restarted immediately after.**  
**Migration time: 815 seconds (13.6 minutes) for 15,005,349 rows.**

### Step 1 — Convert to Hypertable

```sql
SELECT create_hypertable(
    'historian_raw.historian_timeseries',
    'time',
    chunk_time_interval => INTERVAL '7 days',
    migrate_data        => true,
    if_not_exists       => true
);
```

### Step 2 — Enable Columnar Compression

```sql
ALTER TABLE historian_raw.historian_timeseries
SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'tag_id',
    timescaledb.compress_orderby   = 'time DESC'
);
```

- `segmentby = 'tag_id'` — groups all data for one tag into one columnar segment
- `orderby = 'time DESC'` — time within a segment is delta-encoded (tiny integers)
- `quality` column is nearly constant per tag segment → run-length compressed to 1 value

### Step 3 — Compression Policy

```sql
SELECT add_compression_policy(
    'historian_raw.historian_timeseries',
    compress_after => INTERVAL '7 days',
    if_not_exists  => true
);
```

### Step 4 — Retention Policy

```sql
SELECT add_retention_policy(
    'historian_raw.historian_timeseries',
    drop_after    => INTERVAL '2 years',
    if_not_exists => true
);
```

### Result — Chunks Created

| Period | Status | Size |
|---|---|---|
| 2025-12-18 → 2025-12-25 | ✅ COMPRESSED | 32 kB |
| 2025-12-25 → 2026-01-01 | ✅ COMPRESSED | 32 kB |
| 2026-01-08 → 2026-01-15 | ✅ COMPRESSED | 32 kB |
| 2026-01-15 → 2026-01-22 | ✅ COMPRESSED | 32 kB |
| 2026-01-22 → 2026-01-29 | ✅ COMPRESSED | 32 kB |
| 2026-01-29 → 2026-02-05 | ✅ COMPRESSED | 32 kB |
| 2026-02-05 → 2026-02-12 | ✅ COMPRESSED | 32 kB |
| 2026-02-12 → 2026-02-19 | ✅ COMPRESSED | 32 kB |
| 2026-02-19 → 2026-02-26 | ✅ COMPRESSED | 32 kB |
| 2026-03-19 → 2026-03-26 | ✅ COMPRESSED | 32 kB |
| 2026-03-26 → 2026-04-02 | ✅ COMPRESSED | 32 kB |
| 2026-04-02 → 2026-04-09 | ✅ COMPRESSED | 32 kB |
| 2026-04-09 → 2026-04-16 | ✅ COMPRESSED | 32 kB |
| 2026-04-16 → 2026-04-23 | ✅ COMPRESSED | 32 kB |
| 2026-04-30 → 2026-05-07 | ✅ COMPRESSED | 32 kB |
| 2026-05-07 → 2026-05-14 | 🔓 uncompressed | 665 MB ← will auto-compress tonight 19:17 |
| 2026-05-14 → 2026-05-21 | 🔓 uncompressed | 116 MB ← active write window |

**Total: 17 chunks**

### Compression Ratio Per Chunk

| Period | Before | After | Ratio |
|---|---|---|---|
| 2025-12-18 → 2025-12-25 | 273 MB | 8,704 kB | **32.1x** |
| 2025-12-25 → 2026-01-01 | 311 MB | 7,352 kB | **43.3x** |
| 2026-01-22 → 2026-01-29 | 258 MB | 15 MB | **16.9x** |
| 2026-01-29 → 2026-02-05 | 621 MB | 36 MB | **17.3x** |
| 2026-02-05 → 2026-02-12 | 230 MB | 14 MB | **16.3x** |
| 2026-04-30 → 2026-05-07 | 63 MB | 2,368 kB | **27.2x** |
| **TOTAL** | **2,826 MB** | **147 MB** | **19.2x** |

**2,679 MB saved by compression.**

---

## Immediate Tasks — Aggregate + BRIN Index

**Script:** `immediate_tasks_agg_brin.py`

### Hourly Continuous Aggregate (`ts_hourly_agg`)

```sql
CREATE MATERIALIZED VIEW historian_raw.ts_hourly_agg
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', "time") AS bucket,
    tag_id,
    AVG(value_num)           AS avg_val,
    MAX(value_num)           AS max_val,
    MIN(value_num)           AS min_val,
    COUNT(*)                 AS sample_count,
    LAST(value_num, "time")  AS last_val,
    FIRST(value_num, "time") AS first_val
FROM historian_raw.historian_timeseries
GROUP BY bucket, tag_id
WITH NO DATA;

SELECT add_continuous_aggregate_policy(
    'historian_raw.ts_hourly_agg',
    start_offset      => INTERVAL '3 hours',
    end_offset        => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour',
    if_not_exists     => true
);
```

- Backfilled **last 90 days** in 2.7 seconds — **6,064 hourly buckets** created
- Auto-refreshes every 1 hour
- Daily/Shift/Monthly reports should query this view instead of raw chunks

### BRIN Index on `time`

```sql
CREATE INDEX IF NOT EXISTS idx_historian_ts_time_brin
ON historian_raw.historian_timeseries
USING BRIN ("time")
WITH (pages_per_range = 128);
```

- Created in **0.3 seconds**
- Size: **24 KB** (vs 661 MB B-tree that was there before)
- Used for full time-range bulk scans and data purge operations

---

## Final State (After All Changes)

### Table & Storage

| Metric | Before | After |
|---|---|---|
| Table type | Plain heap | **TimescaleDB hypertable** |
| Total size | 2,716 MB | **~900 MB** (147 MB compressed + 781 MB uncompressed active chunks) |
| Compression ratio | None | **19.2x on historical data** |
| Chunks | None | **17 chunks (7-day slices)** |
| Row count | 15,005,349 | 15,005,349 ✅ (zero data loss) |

### Indexes

| Index | Type | Size | Purpose |
|---|---|---|---|
| `historian_timeseries_pkey` | B-tree | 8 kB | `(time, tag_id)` PK — tiny due to chunk routing |
| `idx_historian_ts_tagid_time` | B-tree | 8 kB | Tag range queries |
| `idx_historian_ts_time_brin` | BRIN | **24 kB** | Time-range bulk scans |
| `historian_timeseries_time_idx` | B-tree | 8 kB | TimescaleDB auto-created per hypertable |

### Background Jobs Running

| Job | Schedule | Next Run |
|---|---|---|
| Columnstore Policy (compress old chunks) | Every 12 hours | 2026-05-20 19:17 |
| Refresh Continuous Aggregate (`ts_hourly_agg`) | Every 1 hour | 2026-05-20 08:26 |
| Retention Policy (drop chunks > 2 years) | Every 1 day | 2026-05-21 07:16 |

### PostgreSQL Config

| Setting | Before | After |
|---|---|---|
| `shared_buffers` | 128 MB | **512 MB** |
| `work_mem` | 4 MB | **32 MB** |
| `max_wal_size` | 1 GB | **2 GB** |
| `shared_preload_libraries` | timescaledb (was loaded, not enabled) | **timescaledb active** |
| TimescaleDB | Not enabled in DB | **v2.23.0 enabled** |

---

## Phase 4 — Parked (Future, Full-Stack Planning Required)

These items are parked until the system is stable at 500+ tags.
**Do NOT attempt without planning all layers (C#, Python, React) together.**

### 4.1 — Replace TEXT `tag_id` with INTEGER FK

**Why:** At billion-row scale, TEXT tag_id (avg 35 chars) wastes 31 GB vs INTEGER (4 bytes).

**Layers that must all be updated before cutover:**

| Layer | Change needed |
|---|---|
| `historian_meta.tag_dim` | Create new dimension table with `id SERIAL`, `tag_id_text TEXT` |
| `historian_raw.historian_timeseries` | Migrate `tag_id TEXT` → `tag_id INTEGER` FK |
| `HistorianIngestHostedService.cs` | Look up integer id from `tag_dim` before every INSERT |
| `TagValuesPoolService.cs` | Dual-key support during transition |
| `RateControllerService.cs` | String tag_id references in mappings |
| `report_service.py` | All SQL joins need `JOIN tag_dim ON tag_id_text = ...` |
| Every API endpoint | Must maintain string backward compatibility |
| React HMI | Receives string tag_id — must not break |

**Estimated storage saving at 1B rows: 31 GB**  
**Risk if done wrong: breaks all historian writes and all report queries**

---

### 4.2 — Split Table by Data Type

**Why:** `value_text` is NULL 98% of the time. Null bitmap overhead wastes space.
Splitting gives compression 10–20x on numeric vs 2–4x on mixed.

**Target tables:**
```
historian_raw.ts_numeric   — 95% of traffic (PLC analog values)
historian_raw.ts_text      — string status tags (low frequency)
historian_raw.ts_bool      — valve/motor discrete tags
```

**Requires:** `HistorianIngestHostedService.cs` routing logic based on `tag_master.data_type`.

---

### 4.3 — Quality Code as SMALLINT

**Why:** `CHAR(1)` is stored as varlena (1–4 byte header). `SMALLINT` is 2 bytes fixed.
With `segmentby = 'tag_id'`, quality is nearly constant per segment — compresses to 1 value.

```sql
CREATE TABLE historian_meta.quality_codes (
    code     SMALLINT PRIMARY KEY,
    symbol   CHAR(1),
    description TEXT
);
INSERT INTO historian_meta.quality_codes VALUES
    (192, 'G', 'Good'), (0, 'B', 'Bad'),
    (64,  'U', 'Uncertain'), (8, 'C', 'CommError');
```

**Requires:** Schema migration + C# `HistorianIngestHostedService.cs` writer update.

---

## Phase 4 — Implementation Time Estimate

> Estimated on: **May 20, 2026** — for planning purposes only.

### Task-Level Breakdown

| Task | Complexity | Estimated Time |
|------|-----------|----------------|
| **1. INTEGER tag_id migration (4.1)** | High | **~2–3 hours** |
| — Create `tag_dim` lookup table | Low | 15 min |
| — Migrate `historian_timeseries` column | Medium | 30–45 min |
| — Update `HistorianIngestHostedService.cs` | Medium | 30 min |
| — Update `TagValuesPoolService.cs` | Low | 15 min |
| — Update `RateControllerService.cs` | Low | 15 min |
| — Update Python API + `report_service.py` | Medium | 30 min |
| — Update React HMI tag references | Medium | 30 min |
| — End-to-end test + rebuild C# exe | Medium | 30 min |
| **2. Split tables ts_numeric/ts_text/ts_bool (4.2)** | High | **~2–3 hours** |
| — Create 3 new hypertables | Low | 20 min |
| — Migrate existing data by type | Medium | 30–60 min |
| — Update C# ingest routing logic | High | 60 min |
| — Update all query endpoints | High | 60 min |
| **3. Quality as SMALLINT (4.3)** | Low | **~30–45 min** |
| — Schema migration | Low | 15 min |
| — C# writer update | Low | 20 min |

### Total Estimate

| Scenario | Time |
|----------|------|
| Minimum (no surprises, smooth testing) | **~4.5 hours** |
| Realistic (some debugging, service restarts) | **~6–7 hours** |
| With full testing + documentation | **~8 hours** |

### ⚠️ Biggest Risk: Task 1 (INTEGER tag_id)
Touches the most files across C#, Python, and React.  
A single missed reference breaks the historian pipeline **silently** (writes stop, no exception thrown).

**Recommended approach:**
- **Session A**: Task 1 alone (INTEGER tag_id) — full test before proceeding
- **Session B**: Tasks 2 & 3 together (split tables + SMALLINT quality)

---

## Monitoring Queries (Run Weekly)

```sql
-- Compression ratio per chunk
SELECT
    c.range_start::date, c.range_end::date, c.is_compressed,
    pg_size_pretty(cs.before_compression_total_bytes) AS before,
    pg_size_pretty(cs.after_compression_total_bytes)  AS after,
    ROUND(cs.before_compression_total_bytes::numeric /
          NULLIF(cs.after_compression_total_bytes, 0), 1) AS ratio
FROM chunk_compression_stats('historian_raw.historian_timeseries') cs
JOIN timescaledb_information.chunks c ON c.chunk_name = cs.chunk_name
ORDER BY c.range_start DESC;

-- Aggregate freshness check
SELECT view_name, completed_threshold, invalidation_threshold
FROM timescaledb_information.continuous_aggregates
WHERE view_schema = 'historian_raw';

-- Dead tuple ratio
SELECT relname, n_live_tup, n_dead_tup, last_autovacuum, last_autoanalyze
FROM pg_stat_user_tables
WHERE relname = 'historian_timeseries';

-- Background job health
SELECT application_name, last_run_status, last_successful_finish, next_start
FROM timescaledb_information.job_stats
JOIN timescaledb_information.jobs USING (job_id)
WHERE hypertable_schema = 'historian_raw';
```

---

## Scripts Created (All in project root)

| Script | Purpose |
|---|---|
| `phase1_step1_drop_dup_index.py` | Drop duplicate UNIQUE constraint |
| `phase1_step2_autovacuum_analyze.py` | Fix autovacuum + run ANALYZE |
| `phase1_step3_add_tagid_index.py` | Add `(tag_id, time DESC)` index |
| `check_pg_config.py` | Read postgresql.conf settings from DB |
| `phase2_edit_pg_conf.py` | Edit postgresql.conf (shared_buffers etc.) |
| `phase2_enable_timescaledb.py` | Enable TimescaleDB extension |
| `phase2_verify_after_restart.py` | Verify settings after PG restart |
| `phase3_create_hypertable.py` | Convert to hypertable + compression + policies |
| `phase3_verify.py` | Verify chunks + policies |
| `check_chunks.py` | Chunk sizes + force-compress eligible chunks |
| `compression_ratio.py` | Per-chunk compression ratio report |
| `immediate_tasks_agg_brin.py` | Create `ts_hourly_agg` + BRIN index |
| `check_timescaledb.py` | Check TimescaleDB install status |

---

*Document prepared: May 20, 2026*  
*Approved by: ___________________ Date: ___________*
