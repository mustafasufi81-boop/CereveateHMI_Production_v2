# Reporting Architecture Recommendation

## Purpose
This document recommends the **best reporting architecture** for the current HMI + historian system, with emphasis on:

- fast report generation
- exact reproducibility of old reports
- strong auditability
- operational safety
- compatibility with the current `Automation_DB` historian design

This recommendation is based on the actual code paths currently in use, including:

- `WEB_HMI_MFA/HMI/controllers/report_controller.py`
- `WEB_HMI_MFA/HMI/services/report_service.py`
- `WEB_HMI_MFA/HMI/migrations/009_report_tables.sql`
- `WEB_HMI_MFA/HMI/migrations/010_report_views.sql`
- `WEB_HMI_MFA/TIMESCALEDB_MIGRATION_FINAL.sql`

---

## Executive recommendation

### Best option
The best architecture for this system is a **hybrid reporting architecture**:

1. **TimescaleDB hypertable** for raw historian storage
2. **TimescaleDB continuous aggregates** for fast report query performance
3. **Immutable report snapshot storage** for audit-safe historical report retrieval
4. **Generation audit logging** for who/when/how tracking

### Why this is the best choice
This is the only option that gives all four required properties at the same time:

| Requirement | Result |
|---|---|
| Fast report generation | ✅ Yes |
| Low load on raw historian tables | ✅ Yes |
| Exact old report reproduction | ✅ Yes |
| Strong audit trail | ✅ Yes |

If the system uses only on-the-fly reporting, old reports are **recomputed**, not truly preserved.

If the system uses only saved snapshots, performance and live recalculation flexibility are reduced.

The correct production design is therefore:

> **Compute fast from Timescale aggregates, then preserve the generated result as an immutable snapshot for audit and future retrieval.**

---

## Current reporting architecture

## What the system does today

The active reporting path is currently:

```text
React UI
	-> /api/reports/daily | /shift | /monthly
	-> Flask report_controller.py
	-> ReportService
	-> historian_meta.v_report_template_tags
	-> historian_raw.v_daily_hourly_agg
	-> JSON response or in-memory XLSX export
```

### Current storage behavior
- `historian_meta.report_templates` stores report tag membership and display order
- `historian_meta.report_gen_log` stores only generation metadata
- report output rows are **not stored**
- generated XLSX files are **not persisted**
- older reports are reconstructed by re-running the query for the requested date/range
- current monthly report code still builds from `historian_raw.v_daily_hourly_agg`; `v_monthly_daily_agg` exists as a target optimization pattern, not the active runtime path today

### Current shift-definition concern
The active code correctly loads shift boundaries from `historian_meta.shifts` at runtime and does **not** hardcode them in `ReportService`.

However, repository seed/default definitions currently show:
- `SHIFT_A`: `06:00:00` -> `14:00:00`
- `SHIFT_B`: `14:00:00` -> `22:00:00`
- `SHIFT_C`: `22:00:00` -> `06:00:00`

The currently provided plant schedule is:
- `Shift-A`: `05:00` -> `13:00`
- `Shift-B`: `13:00` -> `21:00`
- `Shift-C`: `21:00` -> `05:00`

This is a critical industrial governance point:
- report logic must use **production-configured shift definitions from the database**
- seed/default examples in migrations or design docs must not be treated as authoritative plant truth
- shift definitions must be versioned for historical report reproducibility

### Current safety gap
This means the current system is **not fully audit-safe for historical reports**.

Why:
- if `report_templates` changes, old report layout can change
- if `tag_master` display labels change, old report labels can change
- if aggregation logic changes, old regenerated reports can differ
- if historical data is corrected later, the same report can produce different values

So the current design is good for **functional reporting**, but not for **immutable compliance reporting**.

---

## Option comparison

## Option 1 — Current on-the-fly view-based reporting

### Design
- raw historian data in `historian_raw.historian_timeseries`
- `historian_raw.v_daily_hourly_agg` is a normal SQL view
- reports are generated on demand for every request
- only `historian_meta.report_gen_log` is stored

### Advantages
- simple architecture
- no extra snapshot storage
- always reflects latest data corrections
- minimal implementation complexity

### Disadvantages
- slow when raw data volume grows
- repeated recalculation wastes CPU and I/O
- not audit-safe for exact historical reproduction
- old reports depend on current metadata and current query logic
- poor long-term scalability for monthly and cross-area reports

### Verdict
Good for early-stage functionality, **not the best production design**.

---

## Option 2 — Materialized view reporting

### Design
- create a materialized aggregate view such as `historian_raw.v_daily_hourly_agg`
- refresh it manually or on schedule
- reports query the materialized object instead of raw aggregation

### Advantages
- much faster than normal views
- low change footprint in application code
- easier than full Timescale migration

### Disadvantages
- refresh is manual or scheduler-dependent
- risk of stale report data
- refresh can be expensive and blocking
- no native incremental maintenance like Timescale continuous aggregates
- still does not solve immutable historical report storage

### Verdict
Better than the current view-only approach, but only an intermediate solution.

---

## Option 3 — Timescale continuous aggregates only

### Design
- `historian_raw.historian_timeseries` becomes a hypertable
- `historian_raw.v_daily_hourly_agg` becomes a continuous aggregate
- optionally `historian_raw.v_monthly_daily_agg` supports monthly reporting
- Timescale background jobs keep aggregates refreshed
- reports still generate on demand

### Advantages
- excellent query performance
- automatic incremental refresh
- better scaling with historian growth
- reduced load on raw historian table
- strong fit for time-series workloads
- easier to support daily/shift/monthly reports consistently

### Disadvantages
- old reports are still regenerated, not preserved
- metadata changes can still alter old report appearance
- auditability improves for execution telemetry but not for exact historical report reproduction

### Verdict
This is the **best performance architecture**, but still not enough for compliance-grade historical report preservation.

---

## Option 4 — Recommended hybrid: Timescale + immutable report snapshots

### Design
- Timescale hypertable for raw historian data
- Timescale continuous aggregates for report calculations
- report snapshot table for stored output payloads and exported files
- report generation log for execution telemetry
- optional checksum/versioning to prove report integrity

### Advantages
- fastest runtime query architecture
- exact historical report reproduction
- strongest auditability
- safe against later template/tag metadata changes
- supports both interactive use and compliance use

### Disadvantages
- more schema work than the other options
- additional storage required for snapshots
- requires retention/governance decisions for stored reports

### Verdict
This is the **best overall production architecture** for speed, audit, and safety.

---

## Why the hybrid option is best

## 1. Faster than current architecture

### Current design problem
Today, `v_daily_hourly_agg` is defined in `WEB_HMI_MFA/HMI/migrations/010_report_views.sql` as a normal view over `historian_raw.historian_timeseries`.

That means each report request can force PostgreSQL to aggregate from raw historian rows.

As historian volume grows:
- daily reports become slower
- monthly reports become much slower
- repeated report access causes repeated raw aggregation cost

### Timescale improvement
With Timescale continuous aggregates:
- hourly summaries are pre-materialized incrementally
- queries hit summarized storage, not full raw history
- report latency becomes far more stable as data grows

This is exactly the right pattern for:
- Daily reports
- Shift reports
- Monthly reports
- operator drill-down into recent historical windows

---

## 2. More auditable than current architecture

### Current audit limitation
The existing `historian_meta.report_gen_log` proves only:
- who generated a report
- when it was generated
- which type/date/area was requested
- how long it took
- whether it succeeded

It does **not** preserve:
- the exact rows shown to the user
- the exact column layout
- the exact labels/units used at that time
- the exported file that was delivered

### Snapshot improvement
If each generated report is stored as an immutable snapshot, the system can later prove:
- this exact report was shown/generated on this exact date
- these exact values were used
- this exact template version was used
- this exact file hash was delivered

That is much stronger for:
- compliance
- management reporting
- shift handover evidence
- incident review
- dispute resolution

---

## 3. Safer than current architecture

### Current safety risks
On-the-fly-only reporting is vulnerable to silent drift:
- renamed tags change old reports visually
- changed equipment grouping changes old report structure
- revised calculation logic changes old report values
- deleted or disabled template rows change report composition

### Hybrid safety improvement
Snapshotting removes this drift risk.

The recommended design preserves:
- exact row set
- exact value set
- exact template metadata used
- generation timestamp and actor
- optional file hash and schema version

This makes historical reporting deterministic.

---

## Recommended target architecture

```text
OPC / Historian ingest
		-> historian_raw.historian_timeseries (Timescale hypertable)
		-> Timescale aggregate hierarchy
				 -> 1-minute aggregate
				 -> hourly aggregate
				 -> daily aggregate
		-> Flask report service
				 -> builds report JSON/XLSX from aggregate data
				 -> writes execution telemetry to report_gen_log
				 -> writes immutable snapshot metadata to PostgreSQL
				 -> writes immutable XLSX/PDF artifact to archive storage
		-> UI fetches either:
				 A) live generated report
				 B) previously generated snapshot
```

---

## Recommended database design

## Keep existing objects
- `historian_meta.report_templates`
- `historian_meta.report_gen_log`
- `historian_meta.v_report_template_tags`
- `historian_raw.historian_timeseries`

## Convert / add performance objects
- convert `historian_raw.historian_timeseries` to Timescale hypertable
- replace current `historian_raw.v_daily_hourly_agg` view with a Timescale continuous aggregate or compatibility wrapper over aggregate layers
- add a hierarchical aggregate strategy:
	- minute-level aggregate for recent operational summarization
	- hourly aggregate for shift and daily reporting
	- daily aggregate for monthly and longer-range reporting
- ensure monthly reports never hit raw historian directly

## Add audit-safe snapshot objects

### Proposed header table
`historian_meta.report_snapshots`

Suggested purpose:
- one row per generated report instance
- stores immutable metadata and artifact references

### Strong recommendation: do not store full large reports in PostgreSQL forever
Small JSON payloads may be acceptable initially for preview or quick replay.

But for industrial systems, long-term storage of large report bodies directly inside PostgreSQL becomes a scaling risk, especially for:
- XLSX exports
- PDF exports
- large monthly reports
- multi-area or multi-unit reports
- multi-year retention windows

### Recommended enterprise storage model
**PostgreSQL stores searchable metadata.**

**Filesystem or object/archive storage stores large immutable artifacts.**

Example archive path:

```text
/report_archive/2026/05/shift_A_2026_05_18.xlsx
```

Recommended metadata fields in PostgreSQL:
- `artifact_uri` or `file_path`
- `artifact_type` (`XLSX`, `PDF`, `JSON`)
- `file_hash_sha256`
- `size_bytes`
- `storage_backend` (`FILESYSTEM`, `OBJECT_STORE`, `ARCHIVE_SHARE`)

Suggested fields:
- `id`
- `report_type`
- `plant`
- `area`
- `from_date`
- `to_date`
- `shift_code`
- `shift_definition_version`
- `generated_by`
- `generated_at`
- `source_mode` (`LIVE_JSON`, `LIVE_XLSX`, `SNAPSHOT_JSON`, `SNAPSHOT_XLSX`, etc.)
- `template_version`
- `query_version`
- `aggregation_logic_version`
- `timezone_version`
- `engineering_unit_version`
- `rounding_logic_version`
- `row_count`
- `preview_payload_json` (optional, small preview only)
- `artifact_uri`
- `artifact_type`
- `file_hash_sha256`
- `size_bytes`
- `status`

### Recommended snapshot lifecycle states
- `DRAFT`
- `FINAL`
- `APPROVED`
- `SUPERSEDED`
- `REVOKED`

This is important for industrial reporting workflows where reports may be generated, reviewed, approved, and later superseded if corrections are issued.

### Optional detail table
`historian_meta.report_snapshot_rows`

Suggested use:
- normalized per-row archival if JSON blob storage becomes too large
- helps row-level search and audit queries

### Why snapshot header + detail can be useful
- header supports quick lookup
- row table supports analytics and validation
- artifact metadata supports exact replay/export retrieval

## Metadata freezing requirements

To stop visual and semantic drift, each official report snapshot should preserve the tag metadata used at generation time, including at minimum:
- `tag_id`
- `tag_name`
- `display_name`
- `engineering_unit`
- `equipment_name`
- `plant_name`
- `area_name`

Without this, later renames such as `Pump_101` -> `Main Feed Pump` can change the appearance of old official reports.

## Shift-definition freezing requirements

Shift-boundary logic must be versioned and frozen for official reports.

This is required because plants may later change:
- shift start/end times
- day-boundary logic
- holiday calendars
- maintenance windows
- production calendars

For this plant, the currently provided operational schedule is:

| Shift | Start | End |
|---|---:|---:|
| `Shift-A` | `05:00` | `13:00` |
| `Shift-B` | `13:00` | `21:00` |
| `Shift-C` | `21:00` | `05:00` |

Official snapshots should preserve:
- `shift_code`
- `shift_name`
- `shift_start_time`
- `shift_end_time`
- `shift_definition_version`

This ensures old reports remain reproducible even if future shift schedules change.

## Timezone policy

Timezone handling must be standardized as follows:

- store source event/report timestamps as `TIMESTAMPTZ` in UTC
- perform official rendering into plant-local timezone at report generation time
- freeze the timezone policy/version in official snapshots

Why this matters:
- daylight saving policy changes
- server timezone changes
- plant-local timezone reinterpretation
- cross-system time normalization issues

In other words:

> raw historian truth should remain UTC-based; official report presentation may be local-time, but the rendering rule must be versioned and frozen.

## Layer separation model

The architecture should clearly separate these layers:

| Layer | Purpose |
|---|---|
| Raw historian | truth source |
| Continuous aggregates | performance layer |
| Snapshots | legal/audit layer |
| KPI tables | business/analytics layer |

This prevents future architectural confusion and uncontrolled reuse of the wrong storage layer for the wrong purpose.

## `historian_calc_values` role definition

`historian_calc_values` already exists in schema design but is currently operationally ambiguous.

Recommended role:
- store scheduled derived KPIs and calculated business metrics
- do **not** use it as a replacement for raw historian storage
- do **not** use it as a replacement for official report snapshots

Recommended examples for `historian_calc_values`:
- OEE
- runtime / downtime
- energy totals
- efficiency KPIs
- scheduled derived metrics

This table should serve as the **KPI/derived-metric layer**, not the report archive layer.

---

## Recommended application behavior

## Daily / Shift / Monthly interactive use
For normal UI usage:
- generate report from Timescale aggregate
- return JSON immediately
- log to `report_gen_log`

### Aggregate usage rules
- daily and shift reports should use hourly aggregate layers
- monthly reports should use daily aggregate layers
- monthly reports must never hit raw historian directly

## Continuous aggregate refresh policy

Refresh policies must be explicit and operationally owned.

Recommended starting policy for initial production deployment:

| Aggregate | Primary Purpose | Suggested Refresh | Suggested Start Offset | Suggested End Offset |
|---|---|---:|---:|---:|
| hourly | shift and daily reporting | every `10 minutes` | `7 days` | `5 minutes` |

**Note**: Minute and daily aggregates are deferred until after hourly aggregate stabilizes operationally.

Recommended compression policy:

| Layer | Compression After | Compression Job Cadence |
|---|---:|---:|
| raw historian | `2 days` | every `30 minutes` |

Example policy shape:

```sql
SELECT add_continuous_aggregate_policy(
		'historian_raw.ca_hourly',
		start_offset => INTERVAL '7 days',
		end_offset => INTERVAL '5 minutes',
		schedule_interval => INTERVAL '10 minutes'
);
```

The exact values should be tuned after observing real ingest rate, late-data behavior, and query demand.

## Timescale operational monitoring

**CRITICAL**: Timescale background jobs must be actively monitored in production.

### Required operational monitoring

Monitor these operational metrics:

| Metric | Purpose |
|---|---|
| job failures | detect refresh/compression failures |
| refresh lag | detect aggregate staleness |
| compression lag | detect compression backlog |
| chunk growth | detect unexpected chunk explosion |
| WAL growth | detect compression or ingest issues |
| refresh duration | detect query performance degradation |
| stale aggregates | detect policy configuration errors |

### Operational queries

**Check all background jobs:**

```sql
SELECT job_id, application_name, schedule_interval, 
       config, next_start, scheduled
FROM timescaledb_information.jobs;
```

**Check job execution history:**

```sql
SELECT job_id, last_run_status, last_successful_finish,
       total_runs, total_successes, total_failures
FROM timescaledb_information.job_stats
ORDER BY job_id;
```

**Check continuous aggregate refresh lag:**

```sql
SELECT view_name, 
       materialized_only, 
       completed_threshold,
       now() - completed_threshold AS lag
FROM timescaledb_information.continuous_aggregates;
```

**Check compression status:**

```sql
SELECT hypertable_name,
       total_chunks,
       number_compressed_chunks,
       uncompressed_heap_size,
       compressed_heap_size,
       compression_ratio
FROM timescaledb_information.compression_settings
JOIN timescaledb_information.hypertables USING (hypertable_name);
```

### Recommended operational alerts

| Alert Condition | Severity |
|---|---|
| job failure rate > 5% | HIGH |
| refresh lag > 30 minutes | MEDIUM |
| compression lag > 6 hours | MEDIUM |
| WAL size > 10 GB | HIGH |
| chunk count growth > 500/day | MEDIUM |
| uncompressed chunk age > 3 days | LOW |

These thresholds should be tuned after observing baseline operational behavior.

## Real-time overlay query strategy

Continuous aggregates usually have a small freshness lag.

For recent operational reporting and near-live views, the recommended query model is:

```text
aggregate data
	+
recent raw overlay
```

Example concept:
- aggregate covers data up to `10:55`
- raw overlay fills `10:55` -> `11:00`

This avoids the common operator complaint that the latest few minutes are missing.

Recommended use:
- operational dashboards: aggregate + recent raw overlay allowed
- official reports: finalized aggregate window only, then frozen into snapshot

### Real-time freshness expectations

**IMPORTANT**: Continuous aggregates have inherent refresh lag. This must be explicitly communicated to users.

Recommended freshness policy:

| Report Type | Expected Freshness | Acceptable Lag | Query Strategy |
|---|---|---:|---|
| Operational dashboard | near-live | 5–10 minutes | aggregate + raw overlay |
| Shift report | finalized | N/A | aggregate only |
| Daily report | finalized | N/A | aggregate only |
| Monthly report | finalized | N/A | aggregate only |
| Official snapshot | immutable | N/A | stored artifact |

This table should be included in user documentation and training materials to prevent expectation mismatch.

**Key principle**: Official reports should NEVER use real-time overlay. Only finalized aggregate windows should be frozen into snapshots.

## Load protection / backpressure policy

**CRITICAL PRINCIPLE**: Reporting workload must NEVER destabilize historian ingestion.

Historian ingestion is the highest-priority workload. Reporting is secondary.

Recommended load protection measures:

| Protection | Purpose |
|---|---|
| query timeouts | prevent runaway report queries |
| bounded live windows | prevent unrestricted time-range scans |
| aggregate-only reporting | prevent raw historian overload |
| API concurrency limits | prevent request storms |
| connection pooling | prevent connection exhaustion |
| query plan caching | reduce planner overhead |

### Recommended operational guardrails

**Maximum live query windows:**

| Report Type | Maximum Window |
|---|---:|
| Operational dashboard | 7 days |
| Shift report | 1 day |
| Daily report | 1 day |
| Monthly report | 31 days (aggregate-only) |

**API concurrency limits:**

| Endpoint | Max Concurrent Requests |
|---|---:|
| `/api/reports/daily` | 10 |
| `/api/reports/shift` | 10 |
| `/api/reports/monthly` | 5 |
| `/api/reports/history` | 20 |

These limits prevent reporting storms from impacting real-time ingestion.

### Connection pool sizing

Recommended starting pool configuration:

```python
pool_size = 10
max_overflow = 5
pool_timeout = 30
pool_recycle = 3600
```

This prevents reporting workload from exhausting available database connections.

### Recommended query timeout values

| Query Type | Timeout |
|---|---:|
| Operational dashboard | 5 seconds |
| Shift report | 30 seconds |
| Daily report | 30 seconds |
| Monthly report | 60 seconds |
| Snapshot retrieval | 10 seconds |

These timeouts should fail fast and return actionable errors to users.

## Late-arriving data / backfill policy

Industrial historians often receive delayed data due to:
- PLC reconnects
- MQTT spool flushes
- buffered gateway delivery
- temporary network loss

The architecture must therefore support late-arriving data.

Recommended policy:
- use refresh windows large enough to permit recent backfill
- run periodic historical refresh jobs for a bounded late-data window
- define acceptable late-arrival thresholds per source

Example principle:
- hourly aggregate policy refreshes the recent `7 days`
- daily aggregate policy refreshes the recent `60 days`

This ensures delayed historian rows can still be re-incorporated correctly.

### Recommended live query guardrails
- define a maximum live query window
- route medium-range queries to hourly aggregates
- route long-range queries to daily aggregates only

Example policy:
- up to `90 days`: live report can use hourly aggregate
- beyond `90 days`: live report must use daily aggregate only
- raw historian should be reserved for trend/detail use, not official long-range reports

## Query timeout and protection rules

Industrial HMIs need defensive query guardrails.

Recommended protections:
- maximum report period per endpoint
- maximum raw scan duration
- API timeout policy
- cancellation of long-running ad hoc queries
- no unrestricted raw scans from report APIs

Example operational rules:
- monthly/official reports never query raw historian
- live detailed queries should have bounded time windows
- server-side timeouts should fail fast and return actionable errors

### Recommended query timeout values

| Query Type | Timeout |
|---|---:|
| Operational dashboard | 5 seconds |
| Shift report | 30 seconds |
| Daily report | 30 seconds |
| Monthly report | 60 seconds |
| Snapshot retrieval | 10 seconds |

These timeouts should fail fast and return actionable errors to users.

## Export use
For XLSX export:
- generate from aggregate
- return file to user
- persist snapshot metadata and archived artifact reference
- compute and store `SHA-256` hash for tamper evidence

## Failure recovery policy

The architecture must define failure handling for:
- aggregate refresh job failure
- compression job failure
- snapshot metadata write failure
- archive artifact save failure
- hash generation failure

Recommended status concepts:
- `FAILED`
- `RETRY_PENDING`
- `RECOVERED`

Recommended behavior:
- report generation may return to user only after minimum required persistence succeeds for that mode
- official report generation should fail closed if snapshot + artifact archival cannot be completed
- retryable background recovery should exist for archive or snapshot reconciliation steps

## Historical retrieval use
When user requests an already generated official report:
- fetch snapshot first if the intent is “show exactly what was generated before”
- do not recompute unless user explicitly asks for a refreshed live version

This should create two clearly different modes:

1. **Live Report** — recalculated from current historian aggregate
2. **Official Snapshot** — immutable historical artifact

## Regeneration policy

This must be explicit:

| Mode | Behavior |
|---|---|
| `Live` | Recalculate from current aggregate layer |
| `Official` | Retrieve immutable stored snapshot |

This distinction must be visible in both API design and UI labels.

## Operational vs compliance reporting

The architecture should recognize two report classes:

### Operational reports
- small refresh lag acceptable
- live recalculation acceptable
- used for day-to-day operations

### Compliance / legal / official reports
- immutable snapshot required
- exact reproducibility required
- approval workflow recommended
- integrity hash required
- stronger retention and access governance required

That distinction is very important.

## Report data contract

All report layers should follow a stable report contract so live reports, snapshots, exports, and APIs remain compatible.

Suggested canonical structure:

```json
{
	"report_type": "",
	"mode": "live|official",
	"generated_at": "",
	"timezone": "",
	"template_version": "",
	"shift_definition_version": "",
	"aggregation_logic_version": "",
	"rows": []
}
```

This prevents future drift between:
- live report APIs
- snapshot retrieval APIs
- export generators
- downstream consumers

---

## Recommended API design

## Keep existing endpoints
- `GET /api/reports/daily`
- `GET /api/reports/daily/export`
- `GET /api/reports/shift`
- `GET /api/reports/shift/export`
- `GET /api/reports/monthly`
- `GET /api/reports/monthly/export`

## Add snapshot endpoints
- `GET /api/reports/history`
	- list previously generated report snapshots
- `GET /api/reports/history/{snapshot_id}`
	- get stored report snapshot metadata/preview
- `GET /api/reports/history/{snapshot_id}/export`
	- export/re-download exact stored report version

## Optional dual-mode live endpoint behavior
Current endpoints can also accept:
- `mode=live`
- `mode=snapshot`

But explicit separate endpoints are usually safer and clearer.

---

## Audit model recommendation

## Minimum acceptable audit model
- keep `historian_meta.report_gen_log`
- log all JSON and XLSX generations
- include success/failure, duration, IP, user

## Stronger audit model
Also write a snapshot record containing:
- report identity
- frozen metadata set
- template version used
- `SHA-256` hash of exported artifact
- generation code version / query version
- aggregation logic version
- rounding logic version
- timezone version
- shift definition version

## Report approval workflow

For many industrial contexts, especially shift, quality, energy, and production reports, the recommended lifecycle is:

```text
Generated
	-> Reviewed
	-> Approved
	-> Locked
```

This is why snapshot status values such as `DRAFT`, `FINAL`, `APPROVED`, `SUPERSEDED`, and `REVOKED` are important.

## Strongest audit model
Additionally write a `user_actions_audit` event such as:
- `REPORT_GENERATED`
- `REPORT_DOWNLOADED`
- `REPORT_SNAPSHOT_VIEWED`
- `REPORT_APPROVED`
- `REPORT_SUPERSEDED`

That creates a full chain of custody.

## Security model

Official reporting now becomes business-critical and must follow explicit role-based access control.

Recommended permission model:

| Role | Example Capability |
|---|---|
| Operator | generate operational report |
| Supervisor | approve/finalize official report |
| Auditor | read-only access to official snapshots |
| Admin | governance, retention, archive policy |

At minimum, approval, revocation, and governance operations should not be available to ordinary report viewers.

---

## Safety controls recommended

## 1. Immutable snapshot rule
Once stored, a report snapshot must not be edited.

If a correction is needed:
- generate a new snapshot
- link it to the prior snapshot as a superseding version

## 2. Version metadata
Store:
- template version
- calculation/query version
- export formatter version
- aggregation logic version
- timezone version
- engineering-unit version
- rounding logic version
- shift-definition version

Without this, exact reproducibility becomes weaker.

## 3. Data source label
Each report should clearly identify:
- live regenerated report
- archived official snapshot

This avoids operational confusion.

## 4. Retention policy
Snapshots should have a defined retention period separate from raw historian retention.

Example:
- operational reports: 1–2 years
- compliance reports: 5–7 years

This must be explicitly independent from historian compression/retention.

Example:

| Data Class | Example Retention |
|---|---:|
| Raw historian | 2 years |
| Official reports | 7 years |

Compressed historian and official report retention are different governance concerns and should not be coupled.

## 5. Real-time aggregate lag handling
Timescale continuous aggregates are not magically zero-lag.

They refresh according to policy windows and therefore can have refresh lag.

The architecture should explicitly define:
- refresh interval
- acceptable lag per report class
- whether real-time aggregate queries should include recent raw data overlay for operational views

Recommended policy principle:
- operational dashboards may tolerate small lag or combine aggregate + recent raw window
- official reports should use finalized aggregate windows and then be frozen as snapshots

## 6. Snapshot immutability enforcement
Immutability must be technical, not only conceptual.

Recommended enforcement measures:
- revoke ordinary `UPDATE` permissions on snapshot tables
- treat snapshot metadata tables as append-only except controlled supersede/revoke workflows
- store official artifacts in immutable or write-once archive locations where possible
- verify stored artifact `SHA-256` hash during retrieval or audit checks

## 6.1. Archive verification policy

**IMPORTANT**: SHA-256 hashes are useless unless actually verified operationally.

Recommended verification cadence:

| Verification Type | Frequency | Purpose |
|---|---:|---|
| retrieval verification | every retrieval | detect tampering |
| scheduled integrity scan | weekly | detect corruption |
| archive migration verification | during migration | prevent data loss |
| disaster recovery verification | after restore | prove backup integrity |

### Retrieval verification procedure

Whenever an official report artifact is retrieved:

```python
# 1. Fetch snapshot metadata from PostgreSQL
metadata = fetch_snapshot_metadata(snapshot_id)
expected_hash = metadata['file_hash_sha256']

# 2. Retrieve artifact from archive storage
artifact_bytes = fetch_artifact(metadata['artifact_uri'])

# 3. Compute actual hash
import hashlib
actual_hash = hashlib.sha256(artifact_bytes).hexdigest()

# 4. Verify integrity
if actual_hash != expected_hash:
    raise IntegrityError(f"Artifact corruption detected for snapshot {snapshot_id}")

# 5. Return artifact only if verification passes
return artifact_bytes
```

### Scheduled integrity scan

Recommended weekly background job:

```sql
SELECT id, artifact_uri, file_hash_sha256
FROM historian_meta.report_snapshots
WHERE status IN ('FINAL', 'APPROVED')
  AND generated_at >= now() - INTERVAL '1 year'
ORDER BY generated_at DESC;
```

For each snapshot:
- retrieve artifact from storage
- compute SHA-256 hash
- compare against stored hash
- log verification result
- alert on any mismatches

This detects silent corruption before users encounter it.

## 7. Archive storage governance
Once report artifacts move outside PostgreSQL, archive governance becomes mandatory.

Recommended governance topics:
- backup policy for archive storage
- replication or secondary copy strategy
- retention cleanup policy
- corruption/integrity verification checks
- archive migration strategy for future storage changes

Without this, filesystem/object storage becomes unmanaged operational debt.

## 8. Aggregate compression policy

Not only raw historian, but aggregate layers also grow over time.

Recommended starting policy:

| Aggregate | Suggested Compression Policy |
|---|---|
| hourly | compress after `30 days` |

Note: Minute and daily aggregate compression can be configured later after those layers are deployed.

These values should be tuned after observing real usage and retention horizons.

## 8.1. Aggregate rebuild strategy

**CRITICAL DISTINCTION**: Aggregates are rebuildable performance layers. Snapshots are immutable audit records.

This distinction is operationally very important.

### Aggregate rebuild policy

If continuous aggregates become corrupted or require rebuild:

**Aggregates can be dropped and rebuilt** because they are derived from raw historian.

Recommended rebuild procedure:

```sql
-- 1. Drop corrupted continuous aggregate
DROP MATERIALIZED VIEW historian_raw.ca_hourly;

-- 2. Recreate continuous aggregate
CREATE MATERIALIZED VIEW historian_raw.ca_hourly
WITH (timescaledb.continuous) AS
SELECT time_bucket('1 hour', opc_timestamp) AS bucket,
       tag_id,
       AVG(value) AS avg_value,
       MIN(value) AS min_value,
       MAX(value) AS max_value,
       COUNT(*) AS sample_count
FROM historian_raw.historian_timeseries
GROUP BY bucket, tag_id;

-- 3. Add refresh policy
SELECT add_continuous_aggregate_policy('historian_raw.ca_hourly',
    start_offset => INTERVAL '7 days',
    end_offset => INTERVAL '5 minutes',
    schedule_interval => INTERVAL '10 minutes');

-- 4. Optionally force immediate refresh
CALL refresh_continuous_aggregate('historian_raw.ca_hourly', 
    now() - INTERVAL '7 days', now());
```

### Snapshot preservation policy

**Snapshots must NEVER be rebuilt** because they are immutable audit records.

If snapshot storage is corrupted:
- restore from backup
- DO NOT regenerate

Regeneration would produce different timestamps, hashes, and generation metadata, violating audit integrity.

### Operational clarity

This must be explicit in operational documentation:

| Layer | Rebuild Allowed | Recovery Method |
|---|---|---|
| Raw historian | NO | restore from backup |
| Continuous aggregates | YES | drop + recreate + refresh |
| Snapshots | NO | restore from backup |
| Archive artifacts | NO | restore from backup |

This prevents operational confusion during disaster recovery.

## 9. Chunk / partition monitoring policy
After Timescale rollout, the system must monitor:
- tiny chunk explosion
- oversized chunks
- unexpected chunk growth

Target principle:
- chunk sizes should be operationally healthy, generally in the hundreds-of-MB range rather than tiny fragments or multi-GB monsters

This should be part of DBA/operations monitoring after go-live.

## 10. Cardinality and growth risk analysis
Long-term scaling is driven by:
- tag count growth
- rows/day growth
- aggregate row growth
- compression effectiveness under higher cardinality

The architecture should explicitly track:
- active tags today
- expected tag growth
- estimated rows/day
- compression expectation under larger tag populations

This is especially important if the platform later grows toward tens of thousands of tags or higher.

## 11. Backup / DR architecture
Reporting becomes business-critical once official snapshots and approvals exist.

The architecture should therefore define:
- raw historian backup strategy
- PITR / database recovery strategy
- aggregate rebuild strategy
- snapshot metadata backup
- archive artifact backup
- replica / secondary recovery approach where applicable

Important principle:
- aggregates are a performance layer and can usually be rebuilt
- official snapshots and artifacts are audit records and require stronger preservation guarantees

---

## Performance proof by architecture

## Why this is faster

### Current path
`historian_timeseries` -> normal SQL view -> report query

This forces repeated aggregation work.

### Recommended path
`historian_timeseries hypertable` -> `minute/hourly/daily aggregate hierarchy` -> report query

This reduces repeated work because aggregation is maintained incrementally in the background.

### Snapshot path benefit
For previously generated official reports:
- no historian query is needed at all for retrieval
- fetch becomes simple lookup of stored report artifact

So the hybrid design is fast in **two different ways**:

1. fast for newly generated reports because aggregates are precomputed
2. fastest for old official reports because retrieval is from snapshot storage

## KPI calculation ownership

To prevent inconsistent KPI logic, the architecture must define who computes which derived values.

Recommended ownership model:

| KPI / Metric Class | Recommended Processor |
|---|---|
| runtime / downtime | background scheduler or KPI engine |
| energy totals | aggregation / KPI engine |
| OEE | KPI engine |
| derived efficiency metrics | scheduled calculation service |

Do not allow Flask request handlers, ad hoc SQL, background workers, and report code to all compute the same KPI differently.

---

## Audit proof by architecture

## Why this is more auditable

| Capability | Current design | Recommended hybrid |
|---|---|---|
| Who generated report | Yes | Yes |
| When generated | Yes | Yes |
| Row count | Yes | Yes |
| Exact report content preserved | No | Yes |
| Exact export reproducible | No | Yes |
| Template version traceable | No | Yes |
| Shift version traceable | No | Yes |
| Metadata freeze possible | No | Yes |
| Integrity hash possible | No | Yes (`SHA-256`) |

---

## Safety proof by architecture

## Why this is safer

| Risk | Current design | Recommended hybrid |
|---|---|---|
| Old report changes after template edits | High | Eliminated for snapshots |
| Old report changes after tag metadata edits | High | Eliminated for snapshots |
| Old report changes after shift schedule changes | High | Eliminated for snapshots |
| Re-query cost on large history | High | Low |
| Report dispute investigation | Weak evidence | Strong evidence |
| Compliance readiness | Partial | Strong |

---

## Recommended rollout order

## Phase 1 — Performance foundation only
- enable TimescaleDB in `Automation_DB`
- convert `historian_raw.historian_timeseries` to hypertable
- enable raw historian compression policy
- create **ONLY hourly** continuous aggregate for report optimization
- optimize report queries to use the hourly aggregate
- validate insert stability, query latency, and compression behavior
- validate current report endpoints still function
- observe real workloads and compression effectiveness

**Important**: Do NOT deploy minute or daily aggregates in Phase 1. These can be added later after hourly aggregate stabilizes and real operational demand is understood.

This phase should stabilize first before adding archival/governance complexity.

## Phase 2 — Snapshot and archive layer
- add `historian_meta.report_snapshots`
- optionally add `historian_meta.report_snapshot_rows`
- add archive storage strategy for XLSX/PDF artifacts
- update `report_controller.py` / `report_service.py` to persist official report metadata and artifact references on generation/export
- add report history retrieval APIs

Only after Phase 1 is stable should the system add immutable report storage.

## Phase 3 — Governance and advanced reporting
- add template versioning
- add `SHA-256` artifact hashing
- add shift-definition versioning
- add metadata freezing rules
- add report approval workflow and status lifecycle
- add snapshot retention policy
- add user action audit events for report access/download
- define UTC storage + local-render timezone policy
- add minute and daily aggregate layers if still needed after operational validation
- define KPI layer ownership through `historian_calc_values` and scheduled processors

This staged rollout reduces production risk and avoids architecture overload.

---

## Pre-deployment storage sizing estimation

**CRITICAL**: Storage sizing must be estimated before production deployment.

### Current baseline metrics

Based on existing `Automation_DB` historian:

| Metric | Current Value |
|---|---:|
| Total historian rows | ~10.9 million |
| Active tags | ~1,000 (estimate) |
| Average insert rate | ~1,000 rows/second (estimate) |
| Current uncompressed size | ~2.5 GB (estimate) |

### Growth estimation assumptions

Recommended assumptions for sizing:

| Parameter | Assumption |
|---|---:|
| Tags | 1,000 active |
| Polling interval | 1 second |
| Row size (uncompressed) | ~250 bytes |
| Row size (compressed) | ~50 bytes (5:1 ratio) |
| Retention period | 2 years |

### Raw historian storage projection

**Daily growth (uncompressed)**:
```
1,000 tags × 86,400 seconds/day × 250 bytes = ~21.6 GB/day
```

**Daily growth (compressed after 2 days)**:
```
21.6 GB / 5 = ~4.3 GB/day compressed
```

**2-year retention (compressed)**:
```
4.3 GB/day × 730 days = ~3.1 TB
```

### Hourly aggregate storage projection

**Hourly aggregate row count per day**:
```
1,000 tags × 24 hours/day = 24,000 rows/day
```

**Hourly aggregate storage per day**:
```
24,000 rows × ~300 bytes/row = ~7.2 MB/day
```

**2-year retention**:
```
7.2 MB/day × 730 days = ~5.3 GB
```

This is negligible compared to raw historian.

### Snapshot storage projection

Assuming:
- 3 shifts/day × 365 days/year = 1,095 shift reports/year
- 365 daily reports/year
- 12 monthly reports/year
- Average XLSX size = 500 KB

**Annual snapshot storage**:
```
(1,095 + 365 + 12) × 500 KB = ~736 MB/year
```

**7-year retention**:
```
736 MB/year × 7 years = ~5.1 GB
```

This is also negligible compared to raw historian.

### Total storage projection summary

| Storage Layer | 2-Year Projection |
|---|---:|
| Raw historian (compressed) | ~3.1 TB |
| Hourly aggregates | ~5.3 GB |
| Snapshots (7-year) | ~5.1 GB |
| **Total** | **~3.1 TB** |

### Scaling considerations

If tag count grows:

| Tag Count | 2-Year Compressed Storage |
|---:|---:|
| 1,000 | ~3.1 TB |
| 5,000 | ~15.5 TB |
| 10,000 | ~31 TB |
| 50,000 | ~155 TB |

This is important for long-term capacity planning.

### Recommended operational monitoring

After deployment, monitor:
- actual compression ratio achieved
- actual insert rate
- actual row size
- chunk growth rate
- WAL growth during compression

These values should be compared against estimates quarterly.

---

## Final recommendation

### Best architecture decision
Adopt:

> **TimescaleDB continuous aggregates for report computation + immutable snapshot storage for official historical reports.**

### Why this is the best option
- **faster** than on-the-fly reporting because reports query pre-aggregated data
- **more scalable** than normal views and manual materialized views
- **more auditable** because exact generated output and artifact identity can be preserved
- **safer** because historical reports no longer drift after metadata or template changes
- **more governable** because approval state, regeneration policy, retention, and integrity checks can be defined cleanly
- **operationally practical** because current report code can largely stay the same while the data layer improves underneath it

### Short decision summary
- If the goal is only speed: choose Timescale continuous aggregates
- If the goal is speed + audit + compliance + safety: choose the **hybrid design**

For this production industrial system, the recommended answer is the **hybrid design**.

### Safe implementation recommendation
Implementation should not begin with the full hybrid feature set at once.

Recommended immediate scope:
- hypertable migration
- compression
- hourly continuous aggregate
- report query optimization

After that stabilizes, add:
- snapshots
- archive storage
- governance
- approvals

---

## Implementation note for this repository

The current codebase is already close to the right separation of concerns:
- controller layer already exists
- report service already exists
- report template table already exists
- generation log already exists

So the recommended change is **architectural enhancement**, not a full rewrite.

The biggest missing piece is:

> **official immutable report snapshot storage with external artifact archiving and governance controls**

That is what turns the current reporting system from functional reporting into production-grade, audit-safe reporting.
