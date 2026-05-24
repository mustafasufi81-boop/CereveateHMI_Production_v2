# DB Compression & Partitioning Strategy
## Automation_DB — Historian Timeseries

**Audit Date:** May 20, 2026  
**DB Engine:** PostgreSQL 17.6 (Windows x64)  
**TimescaleDB:** ❌ NOT INSTALLED — plain PostgreSQL  
**Auditor:** GitHub Copilot (live DB scan)  
**Rev 2:** May 20, 2026 — Expanded with advanced compression recommendations

---

## 1. Live DB Observations (Hard Facts)

### 1.1 `historian_raw.historian_timeseries` — The Core Problem Table

| Metric | Value |
|---|---|
| **Heap size** | 1,394 MB |
| **Total size (heap + indexes)** | **2,716 MB** |
| **Estimated rows** | **~13.8 million** |
| **Pages** | 163,977 |
| **Table type** | ❌ Plain table — NO partitioning, NO TimescaleDB |
| **Primary key** | `(time, tag_id)` — B-tree UNIQUE |
| **Duplicate index** | `uq_timeseries_time_tag` — exact same UNIQUE index on (time, tag_id) |
| **Index 1 size** | 661 MB |
| **Index 2 size** | 661 MB (DUPLICATE — wastes 661 MB) |
| **Sequential scans** | 1,381 |
| **Index scans** | 566,538 |
| **Live tuples** | ~1.15 M (autovacuum estimate) |
| **Dead tuples** | 14,681 |
| **Autovacuum last run** | ❌ Never ran (NULL) |
| **Autoanalyze last run** | ❌ Never ran (NULL) |
| **Modified since analyze** | 1,155,575 rows — stale statistics |

> **Critical:** autovacuum has NEVER run on this table. With 14,681 dead tuples and 1.1M
> modifications since last analyze, query planner is working on zero statistics.

---

### 1.2 Table Schema

```sql
historian_raw.historian_timeseries (
    time             TIMESTAMPTZ  NOT NULL,   -- partition key candidate
    tag_id           TEXT         NOT NULL,   -- tag identifier
    value_num        DOUBLE PRECISION,        -- numeric value
    value_text       TEXT,                    -- string value
    value_bool       BOOLEAN,                 -- boolean value
    quality          CHAR(1),                 -- quality flag
    sample_source    VARCHAR,                 -- source system
    mapping_version  BIGINT       NOT NULL,   -- config version
    opc_timestamp    TIMESTAMPTZ              -- OPC server timestamp
)
-- PK: (time, tag_id)
```

---

### 1.3 Other Large Tables

| Table | Est. Rows | Total Size | Notes |
|---|---|---|---|
| `public.tag_file_catalog` | 750,128 | 286 MB | Parquet file tracking |
| `historian_raw.mqtt_audit_history` | 570,216 | 159 MB | MQTT audit — can be pruned |
| `historian_raw.mqtt_audit_main` | 190,151 | 58 MB | MQTT audit summary |
| `historian_raw.historian_events` | 62,795 | 26 MB | Event log |

---

### 1.4 PostgreSQL Configuration (Current — Undertuned)

| Setting | Current | Recommended for 13M-row table |
|---|---|---|
| `shared_buffers` | 128 MB (16384 × 8kB) | 512 MB–1 GB |
| `effective_cache_size` | 4 GB (524288 × 8kB) | Keep (correct estimate) |
| `work_mem` | 4 MB | 32–64 MB for sort/hash queries |
| `max_wal_size` | 1024 MB | 2048–4096 MB for bulk ingest |
| `autovacuum_vacuum_scale_factor` | 0.20 (20%) | **0.01** for large tables |
| `autovacuum_analyze_scale_factor` | 0.10 (10%) | **0.005** for large tables |

> **Problem:** Default `autovacuum_vacuum_scale_factor = 0.20` means autovacuum only
> triggers after 20% of 13.8M rows = 2.76M dead rows. It will never effectively clean this table.

---

### 1.5 Tag Master — Current & Future Tag Counts

| PLC / Server | Total Tags | Enabled | Notes |
|---|---|---|---|
| `Rockwel_PLC_001` | 169 | 128 | Largest PLC — Allen-Bradley |
| `PLC_SENSORS_01` | 62 | 62 | All enabled |
| `(unmapped/NULL)` | 60 | 3 | Needs cleanup |
| `PLC_GATEWAY_01` | 40 | 40 | All enabled |
| `Matrikon.OPC.Simulation.1` | 27 | 27 | Test/OPC simulation |
| **TOTAL** | **358** | **260** | **Live enabled tags** |

---

## 2. Current Growth Rate Analysis

### 2.1 What We Know

- **Active enabled tags:** ~260 (currently writing to DB)
- **Write logic:** RateControllerService — only writes when value CHANGES (deadband/exact comparison)
- **Polling interval:** 1,000 ms (1 second per OPC poll cycle)
- **Current table:** 13.8M rows — plain unpartitioned table

### 2.2 Worst-Case Row Generation (Future 500 Tags at 1s scan)

```
500 tags × 1 write/sec (all changing) = 500 rows/sec
= 30,000 rows/min
= 1,800,000 rows/hour
= 43,200,000 rows/day (absolute max)

Realistic (50% change rate with deadband):
500 tags × 0.5 change rate × 1/sec = 250 rows/sec
= 21,600,000 rows/day
= 648,000,000 rows/month
= ~7.8 billion rows/year
```

### 2.3 Storage Estimate (plain PostgreSQL, no compression)

Each row in `historian_timeseries` ≈ **120–150 bytes** (row header + 2 timestamps + text tag_id + double + quality + etc.)

```
250 rows/sec × 130 bytes = 32.5 KB/sec
= 1.95 MB/min
= 117 MB/hour
= 2.8 GB/day
= 84 GB/month    ← CRITICAL — unsustainable on a local Windows server
= 1 TB/year
```

> **Current state already at 2.7 GB for ~13.8M rows over a few months.
> At 500 tags with 1s polling, this doubles to 5+ GB/month.**

---

## 3. Problems to Fix (Priority Order)

### P1 — IMMEDIATE (do today, zero risk)

| # | Problem | Fix |
|---|---|---|
| 1 | **Duplicate index** `uq_timeseries_time_tag` = exact copy of PK | `DROP INDEX historian_raw.uq_timeseries_time_tag` — saves **661 MB instantly** |
| 2 | **autovacuum never runs** — stale stats | Per-table autovacuum override (see SQL below) |
| 3 | **work_mem too low** — 4 MB causes disk spills on any range query | Set `work_mem = '32MB'` in `postgresql.conf` |
| 4 | **shared_buffers too small** — 128 MB for 2.7 GB table | Set `shared_buffers = '512MB'`, restart PG |

### P2 — SHORT TERM (this week, requires brief downtime)

| # | Problem | Fix |
|---|---|---|
| 5 | **No time-based partitioning** — full table scans on time range queries | Convert to declarative range partitions by month |
| 6 | **No tag_id index** — queries filtered by tag scan the whole table | Add index on `(tag_id, time)` |
| 7 | **`tag_id` stored as TEXT per row** — 30-40 bytes per row wasted | Replace with integer FK to a tag dimension table |

### P3 — STRATEGIC (before 500-tag scale-up)

| # | Problem | Fix |
|---|---|---|
| 8 | **No compression** — plain heap storage | Either install TimescaleDB OR use pg_partman + BRIN + TOAST |
| 9 | **No data retention policy** | Implement rolling window: keep 3 months raw, summarize older |
| 10 | **No aggregated rollup tables** — reports scan raw data | Create hourly/daily rollup materialized views |

---

## 4. Advanced Compression Design Principles

These principles apply regardless of whether TimescaleDB or native partitioning is chosen.
They are especially critical at the 500-tag, billion-row scale.

---

### 4.1 Separate Numeric vs Text/Event Data

**Why:** Text values compress poorly. TimescaleDB columnar compression achieves 8–20x on
numeric columns but only 2–4x on variable-length text. Mixing them in one table forces
every chunk to include text storage even when 95% of rows are pure numeric.

**Current problem:** `historian_timeseries` has `value_num`, `value_text`, and `value_bool`
all in one row. Most rows are numeric — `value_text` is almost always NULL. Every
row still pays the NULL bitmap overhead.

**Target design — three separate hypertables:**

```sql
-- TABLE 1: Fast numeric tags (PLC analog values — 95% of traffic)
CREATE TABLE historian_raw.ts_numeric (
    "time"          TIMESTAMPTZ  NOT NULL,
    tag_id          INTEGER      NOT NULL,   -- FK to tag_dim.id
    value_num       DOUBLE PRECISION,
    quality         SMALLINT,               -- see section 4.5
    opc_timestamp   TIMESTAMPTZ
) PARTITION BY RANGE ("time");
-- Compression: 10–20x expected

-- TABLE 2: Text/string tags (status strings, mode strings — low frequency)
CREATE TABLE historian_raw.ts_text (
    "time"          TIMESTAMPTZ  NOT NULL,
    tag_id          INTEGER      NOT NULL,
    value_text      TEXT,
    quality         SMALLINT,
    opc_timestamp   TIMESTAMPTZ
) PARTITION BY RANGE ("time");
-- Compression: 3–5x expected

-- TABLE 3: Boolean/discrete tags (valve open/close, motor on/off)
CREATE TABLE historian_raw.ts_bool (
    "time"          TIMESTAMPTZ  NOT NULL,
    tag_id          INTEGER      NOT NULL,
    value_bool      BOOLEAN,
    quality         SMALLINT,
    opc_timestamp   TIMESTAMPTZ
) PARTITION BY RANGE ("time");
-- Compression: 8–12x expected (boolean runs compress extremely well)

-- TABLE 4: Alarms / Events (separate, low volume, different retention)
CREATE TABLE historian_raw.ts_events (
    "time"          TIMESTAMPTZ  NOT NULL,
    tag_id          INTEGER,
    event_type      SMALLINT,
    message         TEXT,
    severity        SMALLINT,
    acknowledged    BOOLEAN,
    ack_time        TIMESTAMPTZ
) PARTITION BY RANGE ("time");
-- Retention: keep 3 years (compliance); numeric raw: keep 1 year
```

**Routing in `HistorianIngestHostedService.cs`:** check `tag_master.data_type` before INSERT
and route to the appropriate table. `TagValuesPoolService` already carries the value object —
just branch on type.

---

### 4.2 Replace TEXT tag_id with INTEGER FK

> **Original suggestion:** _"Use INTEGER tag_id instead of TEXT — huge compression improvement, very important at billion-row scale."_
>
> **Accepted with correction:** The storage saving is real and significant, but the suggestion
> treats this as a DB-only change. It is actually a **full-stack migration** affecting every
> layer — C# services, Python APIs, and React UI. It must be planned as Phase 4, not Phase 3.
> Treating it as simple will break the running system.

**Why the storage saving is real:** At billion-row scale, storing `'Rockwel_PLC_001.Tank1.Level'`
(30–50 chars) per row costs 30–50 bytes × 1B rows = **30–50 GB wasted** on a string that maps
to a small integer. Compression also works better on low-cardinality integers.

**Full-stack impact — every layer must be updated before cutting over:**

| Layer | Impact |
|---|---|
| `HistorianIngestHostedService.cs` | Must look up INTEGER id from `tag_dim` before every INSERT |
| `TagValuesPoolService.cs` | Keyed by string tag_id — needs dual-key support during transition |
| `RateControllerService.cs` | References string tag_id in all mappings |
| `report_service.py` | All SQL uses string tag_id — needs JOIN to tag_dim |
| Every API endpoint | Returns string tag_id to UI — must keep backward compat |
| React HMI | Displays tag_id as string — must not break |

**Tag dimension table (create now, populate now, migrate historian later):**

```sql
CREATE TABLE historian_meta.tag_dim (
    id              SERIAL PRIMARY KEY,
    tag_id_text     TEXT UNIQUE NOT NULL,   -- original string key — keep this forever
    server_progid   TEXT,
    data_type       TEXT,                   -- 'numeric' | 'text' | 'bool'
    eng_unit        TEXT,                   -- engineering unit (store ONCE here)
    description     TEXT,                   -- tag description (store ONCE here)
    plc_name        TEXT,                   -- PLC / source name (store ONCE here)
    scaling_min     DOUBLE PRECISION,
    scaling_max     DOUBLE PRECISION,
    active          BOOLEAN DEFAULT TRUE
);

-- Populate from existing tag_master:
INSERT INTO historian_meta.tag_dim (tag_id_text, server_progid, data_type)
SELECT tag_id, server_progid, 'numeric'
FROM historian_meta.tag_master
ON CONFLICT DO NOTHING;
```

**Storage saving at 1B rows:**
- TEXT tag_id average 35 chars = 35 B/row × 1B = 35 GB
- INTEGER tag_id = 4 B/row × 1B = **4 GB → saves 31 GB**

> **Phase assignment corrected to Phase 4** (after system is stable at 500 tags).
> Do NOT attempt this during Phase 3 scale-up — too much risk in parallel.

---

### 4.3 Eliminate NULL-Heavy Columns (Avoid Sparse Tables)

**Current waste in `historian_timeseries`:**

| Column | NULL rate (estimated) | Waste |
|---|---|---|
| `value_text` | ~98% NULL | Null bitmap + TOAST overhead for nothing |
| `value_bool` | ~90% NULL | Same |
| `opc_timestamp` | ~40% NULL | Moderate |

**Solution:** Split to separate tables (section 4.1 above). Each table only has columns
relevant to its data type — zero NULL columns. TimescaleDB compression benefits maximally
when there are no NULL-heavy sparse columns.

---

### 4.4 Optimal Column Order (Entropy Management)

> **Original suggestion:** _"Column order matters slightly — keep frequently changing / high entropy
> columns later. Recommended: time, tag_id, quality, value_num, opc_timestamp, text columns last."_
>
> **Partially corrected:** The suggestion is valid for TimescaleDB columnar compression,
> but the mechanism is **NOT DDL column order** — PostgreSQL heap storage ignores DDL order
> entirely for physical layout. The actual control is `compress_segmentby` and `compress_orderby`
> in the TimescaleDB compression settings. Changing DDL column order on a plain heap table
> makes **zero difference**. The right DDL order below is for human readability and future
> TimescaleDB alignment, not for immediate heap compression.

**What actually controls compression grouping — TimescaleDB settings:**

```sql
-- THIS is what determines compression efficiency, not DDL order:
ALTER TABLE historian_raw.ts_numeric
SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'tag_id',      -- group all rows for a tag together
    timescaledb.compress_orderby   = '"time" DESC'  -- within segment, time is sorted
);
-- Result: quality is nearly constant per segment → run-length compressed to 1 value
--         time is monotonic per segment → delta encoded to tiny integers
--         value_num is the only column with real entropy
```

**Recommended DDL column order for `ts_numeric` (readability + future alignment):**

```
1. "time"        TIMESTAMPTZ — partition key, always first for clarity
2. tag_id        INTEGER     — low entropy (500 distinct values only)
3. quality       SMALLINT    — very low entropy (3–4 distinct values: G/B/U/C)
4. value_num     DOUBLE      — high entropy (actual sensor readings)
5. opc_timestamp TIMESTAMPTZ — high entropy, often same as time
```

> Bottom line: spend zero time reordering DDL columns on the current plain heap table.
> Focus effort on `compress_segmentby` and `compress_orderby` after TimescaleDB is installed.

---

### 4.5 Quality Code as SMALLINT (not CHAR)

**Current:** `quality CHAR(1)` — stores a single character with full text overhead.

**Problem:** CHAR(1) in PostgreSQL is stored as a varlena (variable-length) type with
a 1–4 byte header. It also does not compress as well as a fixed integer type.

**Proposed mapping:**

```sql
-- quality_code mapping table (store once, reference everywhere)
CREATE TABLE historian_meta.quality_codes (
    code        SMALLINT PRIMARY KEY,
    symbol      CHAR(1),
    description TEXT
);
INSERT INTO historian_meta.quality_codes VALUES
    (192, 'G', 'Good'),
    (0,   'B', 'Bad'),
    (64,  'U', 'Uncertain'),
    (8,   'C', 'CommError');

-- In ts_numeric:
quality  SMALLINT NOT NULL DEFAULT 192   -- 2 bytes fixed, compresses perfectly
```

**Compression benefit:** SMALLINT is 2 bytes fixed-width. With `segmentby = 'tag_id'`,
most rows for a given tag have the same quality (192=Good). The columnar compressor
will store this as a single run-length value for the entire chunk segment.

---

### 4.6 Store Metadata in tag_dim — Never in Historian Rows

**NEVER repeat these in every historian row:**
- Engineering unit (`°C`, `bar`, `RPM`)
- Tag description (`Feed Water Tank Level`)
- PLC name / source
- Scaling min/max
- Equipment hierarchy

All of these belong in `historian_meta.tag_dim` joined at query time.

**Why this matters:**
- `'degrees Celsius'` = 15 bytes × 1B rows = 15 GB wasted if stored per row
- The join to `tag_dim` is a tiny lookup on a 500-row table — essentially free
- Compression ratio on the historian table improves because fewer text columns

---

### 4.7 Compression Timing — Compress After 3–7 Days (Not Immediately)

**Rule:** Recent chunks must stay uncompressed for fast INSERT and point-in-time queries.

```
Age 0–3 days   : UNCOMPRESSED — active writes, live trend queries
Age 3–7 days   : UNCOMPRESSED — recent analysis, shift report lookups
Age 7+ days    : COMPRESSED   — historical reads only, no more inserts
Age 12+ months : DROP chunk   — or archive to cold storage (optional)
```

```sql
-- TimescaleDB policy
SELECT add_compression_policy(
    'historian_raw.ts_numeric',
    compress_after => INTERVAL '7 days'
);
```

**Why not compress immediately?**
- TimescaleDB cannot INSERT into compressed chunks — it would decompress first (expensive)
- Queries on the last 24h (live trend, shift report) need raw page speed
- 7 days is the sweet spot: covers 1 full week's shift reporting window uncompressed

---

### 4.8 BRIN Index on time (Replace B-tree Where Possible)

> **Original suggestion:** _"Use BRIN index on time — very lightweight and perfect for large chunks."_
>
> **Accepted with an important caveat:** BRIN works perfectly **only when rows are inserted
> in strict physical time order**. This system has TWO timestamp columns — `time` (system
> wall clock) and `opc_timestamp` (OPC server clock). These can diverge:
> - `time` = when the C# service wrote the row — **always monotonically increasing** ✅
> - `opc_timestamp` = when the OPC server stamped the value — **can arrive slightly out of order** ❌
>
> **Rule: ALWAYS partition and BRIN-index on `time` (system clock), NEVER on `opc_timestamp`.**
> If `opc_timestamp` is used as the BRIN/partition key, out-of-order arrivals destroy
> the correlation between page blocks and time ranges, making BRIN useless.

**B-tree index on `time`:** 661 MB (current, confirmed live)  
**BRIN index on `time`:** ~128 KB — **5,000x smaller**

```sql
-- CORRECT: BRIN on system 'time' column (always monotonic)
CREATE INDEX CONCURRENTLY idx_ts_numeric_time_brin
    ON historian_raw.ts_numeric
    USING BRIN ("time")
    WITH (pages_per_range = 128);

-- CORRECT: B-tree only on (tag_id, time) for tag-specific lookups
CREATE INDEX CONCURRENTLY idx_ts_numeric_tagid_time
    ON historian_raw.ts_numeric (tag_id, "time" DESC);

-- WRONG: Never use opc_timestamp as partition or BRIN key
-- PARTITION BY RANGE (opc_timestamp)  ← DO NOT DO THIS
```

> TimescaleDB automatically creates a BRIN-like index per chunk on the hypertable time column.
> With native partitioning, add BRIN manually. Either way, the key is always system `time`.

---

### 4.9 Chunk Size Target

**Target:** Each compressed chunk should be **500 MB – 2 GB compressed**.

At 500 tags, 250 rows/sec:
```
Rows per day       = 21,600,000
Bytes per row      = ~50 bytes (after INTEGER tag_id + SMALLINT quality + no nulls)
Raw bytes per day  = 21,600,000 × 50 = 1.08 GB/day
Compressed (10x)  = 108 MB/day

→ 7-day chunk compressed = 756 MB  ← fits the 500MB–2GB target perfectly
```

If tags grow to 1000 or scan rate drops to 5s:
```
1000 tags × 0.5 change rate × 0.2/sec = 100 rows/sec
= 8,640,000 rows/day × 50 bytes = 432 MB/day
Compressed (10x) = 43 MB/day
→ 7-day chunk = 300 MB  → slightly under target, OK

→ Could use 14-day chunks at that point
```

---

### 4.10 Indexing Rules — Do NOT Over-Index

**Maximum 2 indexes per historian table:**

| Index | Type | Purpose |
|---|---|---|
| `(tag_id, "time" DESC)` | B-tree | Tag-specific range queries (trend charts, reports) |
| `("time")` | BRIN | Full time-range scans (bulk export, purge) |

**Do NOT add indexes on:** `quality`, `value_num`, `sample_source`, `mapping_version`

**Why over-indexing hurts compression:**
- Each index is a separate B-tree that must also be updated on every INSERT
- At 250 rows/sec × 4 indexes = 1,000 index page writes/sec — I/O bound quickly
- TimescaleDB per-chunk indexes are already small — no need for global indexes

---

### 4.11 Separate Hypertables by Tag Scan Rate

At 4-PLC scale, group tags by their natural scan frequency into separate hypertables:

```
ts_fast_numeric     — tags scanned every 1s  (critical process values)
                      chunk_interval = 1 day
                      compress_after = 3 days

ts_slow_numeric     — tags scanned every 5s  (non-critical, utility meters)
                      chunk_interval = 7 days
                      compress_after = 7 days

ts_events           — alarms, trips, state changes  (event-driven, low volume)
                      chunk_interval = 30 days
                      compress_after = 7 days
                      retention = 3 years (compliance)

ts_audit_logs       — MQTT audit, user actions  (append-only, drop after 90 days)
                      chunk_interval = 7 days
                      compress_after = 3 days
                      retention = 90 days
```

**Why this matters:**
- Fast tags need smaller chunks (more frequent compression cycles)
- Event/audit logs have completely different retention rules
- Queries on fast tags never touch the slow-tag table (zero cross-contamination)

---

### 4.12 Append-Only Discipline — No UPDATE/DELETE on Raw History

TimescaleDB columnar compression is **append-only optimized**. Any UPDATE or DELETE
on a compressed chunk forces full chunk decompression → rewrite → recompression.

**Rules for `HistorianIngestHostedService.cs`:**
- ✅ INSERT only — never UPDATE a past historian row
- ✅ Use `ON CONFLICT DO NOTHING` for duplicate protection (already in place)
- ❌ Never run `DELETE FROM historian_timeseries WHERE ...` for cleanup — use `drop_chunks()` instead
- ❌ Never backfill corrections — insert a new row with a corrected `value_num` and a `quality=corrected` code

```sql
-- Correct way to drop old data:
SELECT drop_chunks('historian_raw.ts_numeric', older_than => INTERVAL '1 year');

-- WRONG (destroys compression):
DELETE FROM historian_raw.ts_numeric WHERE "time" < NOW() - INTERVAL '1 year';
```

---

### 4.13 Compression Monitoring Dashboard Queries

Run these weekly to track health:

```sql
-- Chunk sizes and compression ratio (TimescaleDB)
SELECT
    chunk_name,
    range_start::date,
    range_end::date,
    pg_size_pretty(before_compression_total_bytes) AS before,
    pg_size_pretty(after_compression_total_bytes)  AS after,
    ROUND(before_compression_total_bytes::numeric /
          NULLIF(after_compression_total_bytes, 0), 1) AS ratio
FROM timescaledb_information.chunk_compression_stats
ORDER BY range_start DESC;

-- Query latency by chunk age (detect if old chunks are being queried)
SELECT
    DATE("time") as day,
    COUNT(*) as row_count
FROM historian_raw.ts_numeric
WHERE "time" >= NOW() - INTERVAL '30 days'
GROUP BY DATE("time")
ORDER BY day DESC;

-- Index usage — confirm BRIN is being used
SELECT indexrelname, idx_scan, idx_tup_read, idx_tup_fetch
FROM pg_stat_user_indexes
WHERE relname LIKE 'ts_%'
ORDER BY idx_scan DESC;

-- Dead tuple ratio — confirm autovacuum is keeping up
SELECT relname, n_live_tup, n_dead_tup,
       ROUND(n_dead_tup::numeric / NULLIF(n_live_tup + n_dead_tup, 0) * 100, 2) as dead_pct,
       last_autovacuum
FROM pg_stat_user_tables
WHERE relname LIKE 'ts_%'
ORDER BY dead_pct DESC;
```

---

### 4.14 Delta Compression Logic (Future Optimization)

> **Original suggestion:** _"Consider delta compression logic later — for slowly changing analogs,
> store timestamp + delta difference. Advanced optimization."_
>
> **Accepted as future-only, with an important clarification:** This system already implements
> the **logical equivalent of delta compression at the write layer** via `RateControllerService`:
> - If `deadband_value > 0`: only writes when `|current - last| > deadband` (threshold filter)
> - If `deadband_value = 0`: only writes when `current != last` (exact change filter)
>
> This means rows that haven't changed are **never written at all** — which is more aggressive
> than delta storage (delta storage would still write a 0-delta row every second).
> The RateControllerService approach achieves 60–80% of the storage reduction without any
> schema complexity. Delta storage on top of this would give marginal additional benefit.
>
> **Do NOT implement delta storage until:**
> 1. The system is at 1B+ rows AND
> 2. Storage cost is still a problem after TimescaleDB compression is enabled AND
> 3. The RateControllerService deadband has been tuned for all tags

For reference, future delta schema if ever needed:

```sql
-- Future only — do not implement now
CREATE TABLE historian_raw.ts_numeric_delta (
    "time"     TIMESTAMPTZ NOT NULL,
    tag_id     INTEGER     NOT NULL,
    delta      REAL,           -- difference from previous value (4 bytes vs 8)
    quality    SMALLINT
);
-- Requires: application-side state tracking of last written value per tag
-- Requires: reconstruction query to get absolute values (sum of deltas)
-- Added complexity is NOT worth it while RateControllerService + TimescaleDB cover the use case
```

---

## 5. Proposed Architecture

### 5.1 Option A — Install TimescaleDB (RECOMMENDED)

TimescaleDB is a PostgreSQL extension. On PostgreSQL 17 + Windows, use the
[TimescaleDB installer](https://docs.timescale.com/self-hosted/latest/install/installation-windows/).

```
Benefits:
  - Automatic time-based chunking (1 day or 1 week chunks)
  - Native columnar compression (8–20x compression ratio)
  - Built-in continuous aggregates (replaces manual rollup views)
  - Built-in data retention policies (drop old chunks in one command)
  - Zero application code change (same SQL INSERT/SELECT)
  - Chunks are regular PG tables — no vendor lock-in
```

After install, migration is a single command:
```sql
SELECT create_hypertable(
    'historian_raw.historian_timeseries',
    'time',
    chunk_time_interval => INTERVAL '7 days',
    migrate_data => true
);
```

### 5.2 Option B — Native PostgreSQL Partitioning (No extension needed)

If TimescaleDB cannot be installed (licensing/approval), use native declarative partitioning:

```sql
-- Step 1: Rename existing table
ALTER TABLE historian_raw.historian_timeseries
    RENAME TO historian_timeseries_old;

-- Step 2: Create partitioned parent
CREATE TABLE historian_raw.historian_timeseries (
    "time"           TIMESTAMPTZ NOT NULL,
    tag_id           TEXT        NOT NULL,
    value_num        DOUBLE PRECISION,
    value_text       TEXT,
    value_bool       BOOLEAN,
    quality          CHAR(1),
    sample_source    VARCHAR,
    mapping_version  BIGINT NOT NULL,
    opc_timestamp    TIMESTAMPTZ
) PARTITION BY RANGE ("time");

-- Step 3: Create monthly partitions
CREATE TABLE historian_raw.ts_2025_01 PARTITION OF historian_raw.historian_timeseries
    FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');
CREATE TABLE historian_raw.ts_2025_02 PARTITION OF historian_raw.historian_timeseries
    FOR VALUES FROM ('2025-02-01') TO ('2025-03-01');
-- ... one per month going forward

-- Step 4: Each partition gets its own PK + index (automatically scoped)
-- Step 5: Use pg_partman extension to auto-create future monthly partitions

-- Step 6: Copy data
INSERT INTO historian_raw.historian_timeseries SELECT * FROM historian_raw.historian_timeseries_old;

-- Step 7: Drop old table
DROP TABLE historian_raw.historian_timeseries_old;
```

---

## 6. Immediate Fixes — Ready to Apply SQL

### 6.1 Drop Duplicate Index (saves 661 MB NOW)

```sql
-- Safe to run at any time — PK still enforces uniqueness
DROP INDEX IF EXISTS historian_raw.uq_timeseries_time_tag;
```

### 6.2 Fix Autovacuum Per-Table (no restart needed)

```sql
ALTER TABLE historian_raw.historian_timeseries
SET (
    autovacuum_vacuum_scale_factor    = 0.01,   -- vacuum after 1% dead rows
    autovacuum_analyze_scale_factor   = 0.005,  -- analyze after 0.5% change
    autovacuum_vacuum_cost_delay      = 2,      -- less throttling
    toast.autovacuum_vacuum_scale_factor = 0.01
);

-- Force immediate analyze to fix stale planner stats:
ANALYZE historian_raw.historian_timeseries;
```

### 6.3 Add Missing Index on tag_id (critical for tag-based queries)

```sql
-- This index lets queries like:
-- WHERE tag_id = 'SomeTag' AND "time" BETWEEN x AND y
-- use an index scan instead of full table scan
CREATE INDEX CONCURRENTLY IF NOT EXISTS
    idx_historian_ts_tagid_time
    ON historian_raw.historian_timeseries (tag_id, "time" DESC);
```

> `CONCURRENTLY` means it builds in the background without locking writes.
> Takes longer but zero downtime.

### 6.4 postgresql.conf Tuning (requires PG restart)

```ini
# Add to postgresql.conf (find with: SHOW config_file;)
shared_buffers        = 512MB      # was 128MB
work_mem              = 32MB       # was 4MB  (per sort/hash operation)
max_wal_size          = 2048MB     # was 1024MB
checkpoint_completion_target = 0.9
effective_cache_size  = 3GB        # tell planner how much OS cache is available
```

---

## 7. TimescaleDB Compression Design (After Install)

Once TimescaleDB is installed, enable compression on the hypertable:

```sql
-- Enable compression, ordered by tag_id then time
-- (groups all values for a tag together — very important for compression ratio)
ALTER TABLE historian_raw.historian_timeseries
SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'tag_id',
    timescaledb.compress_orderby   = '"time" DESC'
);

-- Auto-compress chunks older than 7 days
SELECT add_compression_policy(
    'historian_raw.historian_timeseries',
    compress_after => INTERVAL '7 days'
);

-- Auto-drop chunks older than 1 year (adjust as needed)
SELECT add_retention_policy(
    'historian_raw.historian_timeseries',
    drop_after => INTERVAL '1 year'
);
```

**Expected compression ratio for OPC/PLC data:** 8x–15x
- Raw row: ~130 bytes → compressed: ~9–16 bytes per row
- 500 tags × 250 writes/sec × 1 year = ~7.8B rows
- Uncompressed: ~975 GB
- Compressed: **65–120 GB** — manageable on a local server

---

## 8. Rollup / Aggregation Strategy

For reports (daily/shift/monthly), scanning 13M+ raw rows is slow.
Create continuous aggregates or materialized views:

```sql
-- Option A: TimescaleDB continuous aggregate (auto-refreshing)
CREATE MATERIALIZED VIEW historian_raw.ts_hourly_agg
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', "time") AS bucket,
    tag_id,
    AVG(value_num)   AS avg_val,
    MAX(value_num)   AS max_val,
    MIN(value_num)   AS min_val,
    COUNT(*)         AS sample_count,
    LAST(value_num, "time") AS last_val
FROM historian_raw.historian_timeseries
GROUP BY bucket, tag_id
WITH NO DATA;

SELECT add_continuous_aggregate_policy(
    'historian_raw.ts_hourly_agg',
    start_offset => INTERVAL '3 hours',
    end_offset   => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour'
);

-- Option B: Plain PostgreSQL materialized view (manual refresh)
CREATE MATERIALIZED VIEW historian_raw.ts_daily_agg AS
SELECT
    DATE_TRUNC('day', "time") AS day,
    tag_id,
    AVG(value_num)  AS avg_val,
    MAX(value_num)  AS max_val,
    MIN(value_num)  AS min_val,
    COUNT(*)        AS sample_count
FROM historian_raw.historian_timeseries
GROUP BY DATE_TRUNC('day', "time"), tag_id;

CREATE UNIQUE INDEX ON historian_raw.ts_daily_agg (day, tag_id);

-- Refresh daily at midnight (call from pg_cron or a scheduled Python job)
REFRESH MATERIALIZED VIEW CONCURRENTLY historian_raw.ts_daily_agg;
```

**Impact on report_service.py:**  
Daily/Shift/Monthly reports query the rollup view instead of raw data.
Query time drops from **seconds to milliseconds**.

> **Original suggestion:** _"Use continuous aggregates aggressively — raw data should mostly
> be for trends/investigation. Reports should almost never scan raw chunks."_
>
> **Accepted with a staleness risk warning:** Continuous aggregates refresh on a background
> schedule. If the refresh job falls behind (server restart, maintenance window, PostgreSQL
> crash), reports will silently return **stale aggregated data** — no error, no warning to
> the user. This is especially dangerous for shift reports where operators make decisions
> based on the numbers.
>
> **Mandatory safeguards before using aggregates for reports:**
>
> ```sql
> -- 1. Always check aggregate freshness before serving a report:
> SELECT materialization_hypertable_schema,
>        materialization_hypertable_name,
>        completed_threshold,       -- data is fresh up to this time
>        invalidation_threshold
> FROM timescaledb_information.continuous_aggregates
> WHERE view_name = 'ts_daily_agg';
>
> -- 2. If completed_threshold is more than 2 hours behind NOW(), fall back to raw:
> -- report_service.py should check this before choosing the query path
> ```
>
> ```python
> # In report_service.py — add freshness check before using rollup:
> def _agg_is_fresh(cur, view_name: str, max_lag_hours: int = 2) -> bool:
>     cur.execute("""
>         SELECT completed_threshold FROM timescaledb_information.continuous_aggregates
>         WHERE view_name = %s
>     """, (view_name,))
>     row = cur.fetchone()
>     if not row or row['completed_threshold'] is None:
>         return False
>     lag = datetime.utcnow() - row['completed_threshold'].replace(tzinfo=None)
>     return lag.total_seconds() < max_lag_hours * 3600
>
> # Use: if _agg_is_fresh(cur, 'ts_daily_agg'): query agg else: query raw
> ```
>
> **Plain PostgreSQL materialized view fallback (Option B):** add `last_refresh` timestamp
> tracking and check it in `report_service.py` before using the view.

---

## 9. Full Future Architecture (500 Tags)

```
500 PLC Tags (4 PLCs)
    ↓ 1–5 sec scan via OpcDaService / PLC drivers
    ↓
RateControllerService (deadband + change detection)
    ↓ only changed values
    ↓
historian_raw.historian_timeseries  ← TimescaleDB hypertable
    ├── 7-day chunks (auto-created)
    ├── Compression: ON for chunks > 7 days old  (8-15x ratio)
    ├── Retention: DROP chunks > 1 year
    └── Indexes: (tag_id, time DESC) per chunk — BRIN on time
    ↓
Continuous Aggregate: ts_hourly_agg (auto-refresh every hour)
    ↓
Continuous Aggregate: ts_daily_agg  (auto-refresh every day)
    ↓
report_service.py reads from daily_agg (fast) not raw data
    ↓
React HMI / Reports / Trends
```

---

## 10. Action Plan (Phased)

### Phase 1 — Today (zero risk, no downtime)

- [ ] `DROP INDEX historian_raw.uq_timeseries_time_tag` → free 661 MB
- [ ] `ALTER TABLE ... SET (autovacuum_...)` → fix vacuum settings
- [ ] `ANALYZE historian_raw.historian_timeseries` → fix planner stats
- [ ] `CREATE INDEX CONCURRENTLY idx_historian_ts_tagid_time ...` → fix tag queries

### Phase 2 — This Week (brief maintenance window, ~30 min)

- [ ] Update `postgresql.conf` → `shared_buffers=512MB`, `work_mem=32MB`, `max_wal_size=2048MB`
- [ ] Restart PostgreSQL service
- [ ] Verify autovacuum is now running: `SELECT last_autovacuum FROM pg_stat_user_tables WHERE relname='historian_timeseries'`

### Phase 3 — Before 500-tag Scale-Up (requires planning + 2h downtime)

- [ ] **Install TimescaleDB** on PostgreSQL 17 (Windows installer)
- [ ] Convert `historian_timeseries` to hypertable (`chunk_time_interval = '7 days'`)
- [ ] Enable compression with `segmentby = 'tag_id'`
- [ ] Set `compress_after = '7 days'`
- [ ] Set `drop_after = '1 year'` (or `'2 years'` per business requirement)
- [ ] Create continuous aggregate `ts_hourly_agg`
- [ ] Update `report_service.py` to query `ts_daily_agg` for report builders

### Phase 4 — Ongoing

- [ ] Monitor chunk sizes weekly: `SELECT * FROM timescaledb_information.chunks ORDER BY total_bytes DESC`
- [ ] Monitor compression ratio: `SELECT * FROM timescaledb_information.chunk_compression_stats`
- [ ] Review retention policy annually

---

## 11. Summary Table

| What | Current State | After Phase 1 | After Phase 3 (500 tags) |
|---|---|---|---|
| Table type | Plain heap | Plain heap | TimescaleDB hypertable |
| Table size | 2,716 MB | ~2,055 MB (−661 MB) | ~400 MB/month raw |
| Compression | None | None | 8–15x → ~30–50 MB/month |
| Partitioning | None | None | 7-day auto chunks |
| Query speed (tag range) | Slow (full scan) | Fast (new index) | Fast (chunk pruning) |
| Report query speed | Slow (13M raw rows) | Medium | Fast (rollup view) |
| Autovacuum | Never ran | Running properly | Running per chunk |
| Annual storage (500 tags) | N/A | N/A | ~600 MB–1.2 GB/year |
| TimescaleDB | NOT installed | NOT installed | Installed |

---

*Document approved by: ___________________  Date: ___________*
