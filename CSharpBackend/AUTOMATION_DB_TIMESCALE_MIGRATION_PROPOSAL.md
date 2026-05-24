# Automation_DB TimescaleDB Migration Proposal

## Purpose
Enable TimescaleDB in `Automation_DB` and convert the core historian tables to hypertables using the correct `time` column.

This proposal is for approval only. No database changes are applied by this document.

## Scope
### In Scope
- `historian_raw.historian_timeseries`
- `historian_raw.historian_events`
- `historian_raw.historian_calc_values`
- `historian_mon.system_metrics`

### Out of Scope
- `public.sensor_data` / PostgresLogger legacy path
- old `opc_timestamp`-based migration scripts
- alarm redesign or schema refactors unrelated to hypertable conversion
- cross-database consolidation between `Automation_DB` and `Cereveate`

## Why this is needed
`Automation_DB` is the active operational database for the system. It contains the real historian, alarms, audit, and trip data.

Current live state shows:
- `historian_raw.historian_timeseries`: `14,849,397` rows
- `historian_raw.historian_events`: `58,338` rows
- `historian_raw.historian_calc_values`: `0` rows
- `historian_mon.system_metrics`: `0` rows
- `TimescaleDB installed in Automation_DB`: **No**
- `Hypertables in Automation_DB`: **None**

Result: the system is running on plain PostgreSQL tables, so it is missing:
- hypertable partitioning
- Timescale compression
- Timescale background jobs
- future continuous aggregate capability
- better large-range performance on historian queries

## Relevant gap: `Automation_DB` vs `Cereveate`
This comparison is limited to objects that matter to the current OPC historian system.

### What is missing in `Automation_DB`
- `TimescaleDB` extension is **not installed/enabled**
- no active hypertables for:
    - `historian_raw.historian_timeseries`
    - `historian_raw.historian_events`
    - `historian_raw.historian_calc_values`
    - `historian_mon.system_metrics`
- no Timescale compression policies
- no Timescale background jobs
- no continuous aggregates for historian reporting

This is the main functional gap that affects the current production system.

### What exists extra in `Cereveate`
- `TimescaleDB` extension is installed there
- `public.sensor_data` exists as a real hypertable
- Timescale jobs exist there (compression / maintenance jobs)
- `public.file_imports` and `public.tag_catalog` are populated and aligned with the `PostgresLogger` / parquet-import path

These are useful, but they belong to the older or parallel `PostgresLogger` path, not the core live historian runtime path currently centered on `Automation_DB`.

### What `Cereveate` is missing compared with `Automation_DB`
- `historian_raw.alarm_active` is missing
- `historian_raw.alarm_audit_trail` is missing
- `historian_raw.historian_events` has no live event data there
- `historian_raw.trip_event_tracking` has no live trip data there

So `Cereveate` is **not** the right database to treat as the complete current production source of truth.

### Practical conclusion
- Keep `Automation_DB` as the operational database
- bring the TimescaleDB capability into `Automation_DB`
- do **not** try to migrate the system to `Cereveate`
- do **not** copy unrelated `sensor_data` / `PostgresLogger` legacy objects into the current runtime scope unless explicitly approved later

## Live schema facts already verified
### 1) `historian_raw.historian_timeseries`
- Has correct time column: `time TIMESTAMPTZ NOT NULL`
- Has `opc_timestamp TIMESTAMPTZ NULL`, but this is not the partition key we should use
- Current primary key: `(time, tag_id)`
- Also has duplicate unique index on `(time, tag_id)`
- Row count: `14,849,397`
- Approximate total relation size: `2.688 GB`
    - table heap: `1.378 GB`
    - indexes: `1.309 GB`
- Recent ingest visibility from live query:
    - last 24h: `256,033` rows
    - last 1h: `12,075` rows
    - observed average from last 24h: ~`2.96 rows/sec`
    - observed average from last 1h: ~`3.35 rows/sec`

### 2) `historian_raw.historian_events`
- Has `time TIMESTAMPTZ NOT NULL`
- No primary key constraint currently shown on `event_id`
- Only normal btree indexes exist
- Row count: `58,338`

### 3) `historian_raw.historian_calc_values`
- Primary key: `(time, metric_name)`
- Row count: `0`

### 4) `historian_mon.system_metrics`
- Primary key: `(time, metric_name, instance_id)`
- Row count: `0`

## Migration timing estimate
The current document previously said only that conversion "can take significant time". For production approval, a practical estimate is required.

### Known live conditions
- `historian_raw.historian_timeseries`: `14.8M` rows
- total relation size: ~`2.7 GB`
- active write path exists in the application architecture
- duplicate indexes already exist on `(time, tag_id)`
- no active replication sessions were observed at inspection time

### Practical estimate for `historian_timeseries` conversion
Estimated duration depends heavily on storage and WAL throughput, not row count alone.

| Hardware profile | Estimated conversion window |
|---|---:|
| HDD + low RAM | 1–4 hours |
| SSD + mid-tier server | 20–90 minutes |
| NVMe + tuned PostgreSQL | 10–40 minutes |

### Most likely delays
- WAL generation during `migrate_data => TRUE`
- lock acquisition and writer pause coordination
- existing index maintenance overhead
- autovacuum interaction if not controlled
- post-conversion verification time

### Production planning guidance
- expected write pause duration: **plan for full maintenance-window suspension of historian writes during `historian_timeseries` conversion**
- expected CPU usage: **moderate to high spike during chunk migration**
- expected disk pressure: **temporary WAL growth and transient extra I/O**
- expected overall downtime: **size the window for the slowest-case infrastructure, not the optimistic case**

## How Timescale compression works
TimescaleDB compression is **not ZIP-style file compression**.

It changes storage from ordinary PostgreSQL row-oriented storage into a compressed columnar representation inside Timescale chunks.

### Normal row-oriented shape
- row 1: `time`, `tag_id`, `value_num`, `quality`
- row 2: `time`, `tag_id`, `value_num`, `quality`
- row 3: `time`, `tag_id`, `value_num`, `quality`

### Compressed chunk shape
- timestamps stored together
- numeric values stored together
- qualities stored together
- rows grouped by segment key and ordered by the order key

### Proposed historian compression settings
```sql
timescaledb.compress_segmentby = 'tag_id'
timescaledb.compress_orderby   = 'time DESC'
```

This means:
- `segmentby = tag_id`
    - each tag’s data is grouped together
    - good fit for historian workloads because most trends are queried per tag or tag-set
- `orderby = time DESC`
    - data is ordered by latest timestamp first inside compressed storage
    - good fit for recent-history reads and decompression locality

### Why this is good for this system
- repeated tag-based history compresses efficiently
- long-range historical queries become cheaper on disk I/O
- recent uncompressed data can remain fast for operational dashboards

## Expected compression ratio
Exact savings depend on signal patterns, tag cardinality, float variability, and quality changes.

Typical historian expectations:

| Data type | Expected reduction |
|---|---:|
| Analog trend data | 80–95% |
| Repeating boolean signals | 90–98% |
| Sparse event-like series | 40–70% |

For this system, a reasonable planning assumption is:
- raw historian storage may shrink to roughly **10–30%** of current size after chunks age into compression
- example planning range: `500 GB` raw may compress toward roughly `30–100 GB`, depending on signal behavior

## WAL and disk growth risk
This is one of the most important production risks.

During `migrate_data => TRUE`:
- PostgreSQL can generate large WAL volume
- `pg_wal` disk usage can spike sharply
- replication lag can increase if replication exists later
- storage pressure can become the real limiting factor, not CPU

### Required operational precautions
- monitor `pg_wal` during migration
- ensure free disk space comfortably exceeds normal operating headroom
- plan for temporary disk growth during migration activity
- avoid running the migration when disk pressure is already high

## Pre-migration health checks
Run these checks before approval execution.

### Recommended checks
```sql
VACUUM (ANALYZE) historian_raw.historian_timeseries;
```

Then verify:
- dead tuples / table bloat
- long-running transactions
- autovacuum status
- current free disk space
- WAL directory headroom
- extension privilege for `CREATE EXTENSION timescaledb`

### Live observations already seen
- no replication sessions were visible at inspection time
- no long-running transactions > 5 minutes were visible at inspection time
- planner statistics appear stale or under-updated relative to true row count
- autovacuum/analyze counters on `historian_timeseries` did not show healthy recent maintenance activity

That means a fresh `VACUUM ANALYZE` should be considered part of preparation.

## Why `4 hours` chunk interval was selected
Chunk size directly affects:
- query planning overhead
- number of chunks per day
- compression batch behavior
- chunk exclusion effectiveness

### Why `4 hours` is a good fit here
- high-frequency historian writes benefit from avoiding too many tiny chunks
- 4-hour chunks give `6` chunks/day, which is manageable
- recent-window queries still benefit from effective time pruning
- compression later works on meaningful chunk sizes instead of tiny fragments
- it is a balanced choice between very small chunks (`1 hour`) and oversized chunks (`1 day`)

### Future tuning note
If ingest rate grows substantially, chunk interval should be reviewed using actual chunk sizes and query patterns, not changed arbitrarily.

## Insert-rate analysis
Timescale tuning should follow observed ingest, not guesswork.

### Live measured historian rate
- last 24 hours: `256,033` rows/day
- last 1 hour: `12,075` rows/hour
- approximate sustained rate observed: ~`3 rows/sec`

### What this means
- current ingest is not extreme by Timescale standards
- the migration is still sensitive because of existing data volume and maintenance window constraints
- future tuning should continue to monitor rows/day and total retained days to adjust chunk and compression policy if load increases

## Query pattern rationale for indexing
The proposed indexing strategy is based on the expected historian access pattern:

Typical queries are of the form:
```sql
WHERE tag_id = ?
    AND time BETWEEN ? AND ?
ORDER BY time DESC
```

This justifies:
- BRIN on `time` for broad time-range pruning
- btree on `(tag_id, time DESC)` for common per-tag trend queries

### Note on `hist_ts_tag_only_idx`
This index may be optional.

Because `(tag_id, time DESC)` already starts with `tag_id`, the extra `tag_id`-only index may add write overhead without enough benefit.

Recommendation:
- keep it under review
- do not prioritize it above the composite index
- if write overhead becomes a concern, test whether it is truly needed before finalizing

## Post-migration monitoring
Validation queries alone are not enough. The system needs operational monitoring after migration.

### Monitor after execution
- chunk creation behavior
- insert latency on historian writes
- WAL growth during and after migration
- autovacuum behavior
- CPU and disk I/O spikes
- query plans for 5-minute, 24-hour, and multi-tag historian requests
- compression job duration and backlog once compression activates
- decompression frequency on recent-user queries

### Recommended observation window
- monitor closely during the maintenance window
- continue observation for at least `24–48 hours` after `historian_timeseries` conversion

## Retention clarification
Retention is destructive.

If enabled:
- old chunks are permanently dropped
- this is not archival compression; it is deletion
- business approval is mandatory before enabling automatic retention

Therefore retention should remain optional unless a formal retention policy is approved.

## Replication / HA impact
No active replication sessions were observed at inspection time.

However, if replication is introduced later or exists intermittently:
- WAL shipping volume may spike during migration
- replicas may lag significantly
- failover readiness can be affected during heavy migration activity

If replication is confirmed later, reassess migration timing and WAL headroom before execution.

## Continuous aggregate strategy (deferred design)
Continuous aggregates are intentionally deferred from the initial core migration.

When introduced later, they should follow a clear design:
- hourly aggregate for operator and daily reporting
- daily rollup derived from hourly aggregates where useful
- explicit refresh window design
- explicit late-arrival policy and refresh offsets
- index strategy aligned with historian API query shapes

This avoids mixing core storage correction with reporting optimization in one risky step.

## Important design decision
### Correct partition column
Use **`time`** for all hypertables.

Do **not** use `opc_timestamp` as the hypertable partition key.

Reason:
- `time` is the real canonical event/sample timestamp column used by the current schema
- current keys and indexes are already aligned to `time`
- newer corrected scripts in the repo moved away from `opc_timestamp`

## Preconditions before execution
These checks must pass before we run the migration.

### A. Extension availability
Because `Cereveate` already has TimescaleDB enabled, the PostgreSQL instance likely has the extension binaries available.

Still required:
- verify `CREATE EXTENSION timescaledb` is allowed in `Automation_DB`
- if not allowed for `cereveate`, run the extension step as `postgres` or another privileged role

### B. Maintenance window
`historian_raw.historian_timeseries` has ~14.8 million rows.

Converting an existing populated table with `migrate_data => TRUE` can:
- take significant time
- acquire locks
- impact writes during conversion

So this should be scheduled in a maintenance window.

### C. Application coordination
Before conversion of `historian_raw.historian_timeseries`, stop or pause components that write continuously to the historian:
- C# historian ingest pipeline
- Flask/MQTT persistence path if writing to the same tables
- any importer or replay/spool process targeting `historian_raw`

### D. Backup
Before migration:
- full backup of `Automation_DB`
- at minimum schema backup plus data backup for:
  - `historian_raw.historian_timeseries`
  - `historian_raw.historian_events`
  - `historian_raw.historian_calc_values`
  - `historian_mon.system_metrics`

## Recommended migration strategy
## Phase 1 — Minimum safe core migration
This is the recommended first approval scope.

### Step 1: Enable TimescaleDB in `Automation_DB`
```sql
CREATE EXTENSION IF NOT EXISTS timescaledb;
```

### Step 2: Convert `historian_raw.historian_timeseries` to hypertable
Use the existing `time` column.

Recommended parameters:
- partition column: `time`
- chunk interval: `4 hours`
- migrate existing data: `TRUE`
- do not change the application schema beyond hypertable conversion

Proposed SQL:
```sql
SELECT create_hypertable(
    'historian_raw.historian_timeseries',
    'time',
    if_not_exists => TRUE,
    migrate_data => TRUE,
    chunk_time_interval => INTERVAL '4 hours'
);
```

### Step 3: Add/normalize core performance indexes
Keep the current query-friendly structure and avoid unnecessary index sprawl.

Proposed indexes:
```sql
CREATE INDEX IF NOT EXISTS hist_ts_time_brin_idx
ON historian_raw.historian_timeseries
USING BRIN (time) WITH (pages_per_range = 32);

CREATE INDEX IF NOT EXISTS hist_ts_tag_time_idx
ON historian_raw.historian_timeseries (tag_id, time DESC)
INCLUDE (value_num, value_bool, quality);

CREATE INDEX IF NOT EXISTS hist_ts_tag_only_idx
ON historian_raw.historian_timeseries (tag_id);
```

### Step 4: Enable compression on `historian_timeseries`
Recommended for large historian tables.

Proposed SQL:
```sql
ALTER TABLE historian_raw.historian_timeseries
SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'tag_id',
    timescaledb.compress_orderby = 'time DESC'
);
```

### Step 5: Add compression policy
Recommended initial setting:
- compress data older than `2 days`

Why start with `2 days`:
- keeps the newest operational data uncompressed for fast recent troubleshooting and operator views
- avoids immediate decompression churn on data that is still actively queried soon after insertion
- is conservative enough for the current observed ingest rate while still giving quick storage savings
- should be reviewed after real query observation; if most queries stay within recent hours, `2 days` is a safe first value

Proposed SQL:
```sql
SELECT add_compression_policy(
    'historian_raw.historian_timeseries',
    compress_after => INTERVAL '2 days',
    if_not_exists => TRUE
);
```

### Step 6: Optional retention policy
Recommended only if business has approved data lifecycle retention.

Proposed SQL:
```sql
SELECT add_retention_policy(
    'historian_raw.historian_timeseries',
    drop_after => INTERVAL '730 days',
    if_not_exists => TRUE
);
```

If retention is not yet approved, skip this in first execution.

## Phase 2 — Secondary core hypertables
These are lower risk because they are small or empty.

### A. `historian_raw.historian_events`
Recommended chunk interval: `7 days`

```sql
SELECT create_hypertable(
    'historian_raw.historian_events',
    'time',
    if_not_exists => TRUE,
    migrate_data => TRUE,
    chunk_time_interval => INTERVAL '7 days'
);
```

Recommended indexes after conversion:
```sql
CREATE INDEX IF NOT EXISTS idx_historian_events_tag_time
ON historian_raw.historian_events (tag_id, time DESC);

CREATE INDEX IF NOT EXISTS idx_historian_events_type_time
ON historian_raw.historian_events (event_type, time DESC);

CREATE INDEX IF NOT EXISTS idx_historian_events_transition_seq
ON historian_raw.historian_events (transition_seq);
```

Compression for events is optional. I recommend **skip compression in first pass** unless event growth becomes large.

### B. `historian_raw.historian_calc_values`
Recommended chunk interval: `1 day`

```sql
SELECT create_hypertable(
    'historian_raw.historian_calc_values',
    'time',
    if_not_exists => TRUE,
    migrate_data => TRUE,
    chunk_time_interval => INTERVAL '1 day'
);
```

### C. `historian_mon.system_metrics`
Recommended chunk interval: `1 hour` or `1 day`.

Because this table is currently empty, either is safe. To match the repo’s production DDL intent, `1 hour` is acceptable.

```sql
SELECT create_hypertable(
    'historian_mon.system_metrics',
    'time',
    if_not_exists => TRUE,
    migrate_data => TRUE,
    chunk_time_interval => INTERVAL '1 hour'
);
```

Optional compression:
```sql
SELECT add_compression_policy(
    'historian_mon.system_metrics',
    compress_after => INTERVAL '3 days',
    if_not_exists => TRUE
);
```

## Phase 3 — Reporting optimization (only after core hypertables are stable)
This phase is **not required for initial correction**, but can be added later.

Potential additions:
- continuous aggregate for hourly historian summaries
- daily rollups from hourly aggregates
- report-specific indexes
- controlled refresh policies

This should be done only after:
- core hypertable conversion is successful
- write path is validated
- historian query behavior is stable

## Proposed execution order
1. Take backup
2. Stop/pause historian writers
3. Enable TimescaleDB extension in `Automation_DB`
4. Convert `historian_raw.historian_timeseries`
5. Add Timescale-friendly indexes
6. Restart writers and validate insert/read path
7. Observe for `24–48 hours`
8. Enable compression + compression policy on `historian_timeseries`
9. Observe compression behavior
10. Convert `historian_events`
11. Convert `historian_calc_values`
12. Convert `historian_mon.system_metrics`
13. Run validation queries
14. Re-enable normal service monitoring

## Validation checklist after migration
### Extension
```sql
SELECT extname, extversion
FROM pg_extension
WHERE extname = 'timescaledb';
```

### Hypertables
```sql
SELECT hypertable_schema, hypertable_name, num_chunks, compression_enabled
FROM timescaledb_information.hypertables
WHERE hypertable_schema IN ('historian_raw', 'historian_mon')
ORDER BY hypertable_schema, hypertable_name;
```

### Compression settings
```sql
SELECT hypertable_schema, hypertable_name, segmentby, orderby
FROM timescaledb_information.compression_settings
WHERE hypertable_schema IN ('historian_raw', 'historian_mon');
```

### Jobs
```sql
SELECT job_id, application_name, schedule_interval, next_start
FROM timescaledb_information.jobs
ORDER BY job_id;
```

### Write-path verification
- confirm new rows continue inserting into `historian_raw.historian_timeseries`
- confirm historian API still reads recent 5-minute data
- confirm alarms/events continue writing
- confirm no duplicate ingestion behavior is introduced

### Performance verification
Run before/after comparison on:
- last 5 minutes per tag
- last 24 hours per tag
- multi-tag window trend queries
- alarm/event time-range queries

## Risks
### 1. Locking during `migrate_data`
Main risk is on `historian_raw.historian_timeseries` because of row count.

Mitigation:
- maintenance window
- pause writers
- execute largest table first under supervision

### 2. Extension permission failure
`cereveate` may not have sufficient privilege to create extensions.

Mitigation:
- run only the extension step as `postgres`
- then run hypertable conversion as permitted role

### 3. Duplicate indexes on `historian_timeseries`
Current live schema already has both:
- primary key `(time, tag_id)`
- unique index `(time, tag_id)`

This is redundant.

Mitigation:
- do **not** drop during first migration window
- keep migration focused on Timescale conversion
- remove redundant index later in a separate cleanup window if desired

### 4. `historian_events` identity expectations
Some tooling may implicitly expect `event_id` to behave like a classic standalone relational key.

Mitigation:
- do not add unique constraints that conflict with hypertable rules
- keep existing event query indexes and validate application reads after conversion

## Rollback strategy
### If extension creation fails
- no schema change beyond failed statement
- stop and fix permissions

### If hypertable conversion of `historian_timeseries` fails before completion
- restore from backup if table state is inconsistent
- do not proceed to secondary tables

### If conversion succeeds but application behavior regresses
- disable writers
- inspect query plans / indexes / insert errors
- if necessary restore from pre-migration backup

Because hypertable conversion changes storage layout, true rollback should be treated as **restore-based**, not “simple undo SQL”.

## Recommendation for approval
### Approve now
Approve the concept and use a staged production rollout:

#### Window 1
- enable TimescaleDB in `Automation_DB`
- convert `historian_raw.historian_timeseries`
- validate write/read behavior
- observe for `24–48 hours`

#### Window 2
- enable compression policy on `historian_timeseries`
- monitor job behavior and query impact

#### Window 3
- convert `historian_raw.historian_events`
- convert `historian_raw.historian_calc_values`
- convert `historian_mon.system_metrics`

#### Later phase
- add continuous aggregates only after the core migration is proven stable

### Do not approve yet
Do not include in first execution:
- `opc_timestamp`-based scripts
- migration of legacy `public.sensor_data`
- any cross-database merge from `Cereveate`
- aggressive retention deletion if business retention is not approved

## Proposed deliverable after approval
After approval, the next step should be creation of a single idempotent SQL file, for example:
- `migrations/automation_db_timescaledb_core_migration.sql`

That file will contain only the approved steps for `Automation_DB`, with no legacy `Cereveate` or `sensor_data` objects mixed in.

## Final conclusion
The correction needed for the current system is not to copy all of `Cereveate`.

The correct action is:
- keep `Automation_DB` as the operational database
- enable TimescaleDB there
- convert the four core historian tables using the `time` column
- add compression to `historian_timeseries`
- postpone reporting aggregates until the core migration is validated
