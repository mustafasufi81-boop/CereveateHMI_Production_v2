# PLC Historian Ingest — Structural Changes (May 22–23, 2026)

---

## Current Status (Session 5 — May 23, 2026)

> ⚠️ **OPC historian data source changed** — see `OPC_HISTORIAN_FIX_PLAN.md` for full root cause and plan.

### PLC Historian Pipeline
| Layer | Status |
|---|---|
| `PlcHistorianIngestService.cs` | ✅ Fully rewritten — all 11 fixes applied, zero compile errors |
| `Program.cs` | ✅ `NpgsqlDataSource` singleton registered |
| `PlcGatewayExtensions.cs` | ✅ Service registered as singleton + hosted service |
| Both `appsettings.json` files | ✅ Pool settings + config keys updated |
| **DB writes** | ✅ CONFIRMED WORKING — `[PLC HISTORIAN] Wrote 10 records via COPY in 1ms` in live log |

### OPC Historian Pipeline
| Layer | Status |
|---|---|
| `HistorianIngestHostedService.cs` | ⚠️ **CHANGED (Session 5)** — now injects `OpcDaService` directly, removed `TagValuesPoolService` dependency. See `OPC_HISTORIAN_FIX_PLAN.md` |
| `DbWriterService.cs` | ✅ `NpgsqlDataSource` injected — all 5 `new NpgsqlConnection` calls replaced |
| `MappingCacheService.cs` | ✅ `NpgsqlDataSource` injected — cache refresh query now uses pool |
| **DB writes** | ❌ NOT YET VERIFIED — pending rebuild and redeploy |

### Why OPC Was Broken (Root Cause — Session 5)
`HistorianIngestHostedService` previously read from `TagValuesPoolService`, which is populated **only** by `DataLoggingService`. `DataLoggingService` has a hard guard: if `GetDecryptedProgId()` is empty it loops silently forever — pool never populated → historian wrote nothing. Main OPC connection (`OpcDaService`) was live and working the entire time. Fix: historian now calls `_opcDaService.ReadAllTagValues()` directly — no intermediary. See `OPC_HISTORIAN_FIX_PLAN.md`.

### Overall
| Item | Status |
|---|---|
| **Rebuild** | ❌ NOT done yet — code changed but exe not rebuilt |
| **PLC writes to DB** | ✅ CONFIRMED — live log shows writes every 6s |
| **OPC writes to DB** | ❌ PENDING rebuild + verification |
| Flask `_persist_mqtt_samples()` | ⚠️ Still writing to DB — remove after OPC C# write confirmed |

**Next action: approve `OPC_HISTORIAN_FIX_PLAN.md` → run `build.bat` → restart exe → verify both PLC and OPC writing → remove Flask dual-write.**

---

## Goal
Move PLC tag writes to `historian_raw.historian_timeseries` **entirely inside the C# backend** (port 5001),
independent of Flask HMI or the Python MQTT subscriber service.
Use a **shared Npgsql connection pool** — no per-write TCP connection creation.

---

## Problem Before This Change

| Issue | Detail |
|---|---|
| **Wrong writer** | Flask `app.py` (`_persist_mqtt_samples`) was writing PLC tags to DB with zero rate control — every MQTT message = one DB write (~2s) |
| **Wrong table** | `PlcHistorianIngestService` was writing to `plc_gateway.plc_timeseries` (non-existent / wrong table) |
| **Not registered** | `PlcHistorianIngestService` was never registered as a `HostedService` — it never ran |
| **No connection pool** | `WriteToDbAsync` created `new NpgsqlConnection(_connectionString)` on every write cycle — new TCP connection each time |
| **Wrong default interval** | `DefaultWriteIntervalMs` defaulted to 1000ms — no rate control effect |
| **No batch guard** | No `.Take(_batchSize)` — PLC reconnect burst could create huge COPY transactions |
| **Hardcoded quality `'G'`** | Quality never derived from PLC communication state — always wrote Good even when PLC was offline |
| **No per-row COPY isolation** | One bad record aborted entire COPY batch |
| **No DB failure backoff** | DB outage caused tight reconnect loop → CPU spike + log spam |
| **No write metrics** | No visibility into writes/sec, deadband skips, COPY duration |
| **No pool settings** | Default Npgsql pool behaviour unpredictable under reconnect storms |
| **Poll too fast** | `HistorianPollIntervalMs = 1000ms` — historian scanned all tags every second unnecessarily |

---

## All Files Changed

| # | File | Changes |
|---|---|---|
| 1 | `Program.cs` | `using Npgsql;` + register `NpgsqlDataSource` singleton (shared pool) |
| 2 | `Services/PlcGateway/PlcGatewayExtensions.cs` | Register `PlcHistorianIngestService` as singleton + hosted service |
| 3 | `Services/PlcGateway/Services/PlcHistorianIngestService.cs` | Full hardening — all fixes below |
| 4 | `appsettings.json` (source) | Pool settings in connection string + new `PlcGateway` config keys |
| 5 | `bin\Release\net8.0\win-x86\appsettings.json` | Same — **this is the file the running exe reads** |

---

## Session 1 Changes (May 22) — Foundation

### `Program.cs`
- Added `using Npgsql;`
- Registered `NpgsqlDataSource` as a singleton before `AddPlcGateway()`:
```csharp
builder.Services.AddSingleton(sp =>
{
    var cs = builder.Configuration.GetConnectionString("PlcGateway")
              ?? builder.Configuration.GetConnectionString("Historian")
              ?? throw new InvalidOperationException("No PlcGateway connection string found");
    return NpgsqlDataSource.Create(cs);
});
```

### `PlcGatewayExtensions.cs`
- Registered `PlcHistorianIngestService` as singleton + hosted service:
```csharp
services.AddSingleton<PlcHistorianIngestService>();
services.AddHostedService(sp => sp.GetRequiredService<PlcHistorianIngestService>());
```

### `PlcHistorianIngestService.cs` — Phase 1
- Added `using NpgsqlTypes;`
- Replaced `string _connectionString` → `NpgsqlDataSource _dataSource` (injected from DI)
- `WriteToDbAsync` changed from `new NpgsqlConnection(...)` → `_dataSource.OpenConnectionAsync(ct)`
- COPY target changed: `plc_gateway.plc_timeseries` → `historian_raw.historian_timeseries`
- Column mapping corrected to match actual hypertable schema (9 columns)
- `DefaultWriteIntervalMs` default: 1000ms → 5000ms

### `appsettings.json` (both files)
- Added to `PlcGateway` section:
```json
"HistorianPollIntervalMs": 1000,
"HistorianBatchSize": 200,
"DefaultWriteIntervalMs": 5000
```

---

## Session 2 Changes (May 23) — Production Hardening

### Fix 1 — Historian Poll Interval Raised to 2000ms
**Why:** Scanning all tags every 1000ms doubles historian CPU pressure with no benefit — tag write intervals are 5000ms anyway.
```json
"HistorianPollIntervalMs": 2000
```

### Fix 2 — Batch Size Guard with `.Take()`
**Why:** PLC reconnect burst can create a backlog of thousands of pending records. Without a cap, one COPY transaction could be enormous.
```csharp
if (toWrite.Count > _batchSize)
{
    _logger.LogWarning("[PLC HISTORIAN] Batch capped {Actual} → {Max} records (burst protection)",
        toWrite.Count, _batchSize);
    toWrite = toWrite.Take(_batchSize).ToList();
}
```

### Fix 3 — Per-Row COPY Isolation + Fallback INSERT
**Why:** A single bad record (null TagId, default Timestamp) aborts the entire COPY stream rolling back all rows.

**Two-layer protection:**
1. Pre-validation loop — filters invalid records before entering COPY stream (keeps stream clean)
2. `FallbackInsertAsync()` — if COPY fails entirely, falls back to individual INSERTs per record, each in its own try/catch so one bad row cannot kill the others

### Fix 4 — Explicit Connection Pool Settings
**Why:** Default Npgsql pool behaviour is unpredictable under reconnect storms.

Added to connection string in both `appsettings.json` files:
```
Maximum Pool Size=30;Minimum Pool Size=5;Connection Timeout=15;Command Timeout=60;Keepalive=30
```

### Fix 5 — DB Failure Retry Backoff (5s)
**Why:** Without a delay, a DB outage causes a tight reconnect loop — CPU spike + thousands of log lines per second.
```csharp
catch (NpgsqlException ex)
{
    _totalDbFailures++;
    _logger.LogError(ex, "[PLC HISTORIAN] DB error — backing off 5s");
    await Task.Delay(5000, stoppingToken);  // always pass ct
}
```

### Fix 6 — Write Metrics (separated interval vs deadband)
**Why:** Without metrics there is no way to tune rate control or detect misconfigured tags.

New counters exposed via `GetConfigStatus()`:
| Metric | Meaning |
|---|---|
| `TotalWrites` | Total rows inserted to DB |
| `FilteredByInterval` | Rows skipped because interval not elapsed |
| `FilteredByDeadband` | Rows skipped because value did not change beyond deadband |
| `DbFailures` | COPY failures (triggers fallback INSERT path) |
| `FallbackInserts` | Rows written via fallback INSERT (not COPY) |
| `LastCopyDurationMs` | Time for last successful BINARY COPY (ms) |

Logged automatically every 500 writes.

### Fix 7 — CancellationToken on Every Task.Delay
**Why:** `Task.Delay(ms)` without `ct` hangs shutdown for the full delay duration.

All delays now use `await Task.Delay(ms, stoppingToken)`.

### Fix 8 — Quality Derived from PLC Communication State
**Why:** Hardcoded `'G'` means historian shows Good quality even when PLC is offline.

```csharp
var qualityChar = tagValue.Quality switch
{
    PlcTagQuality.Good          => "G",
    PlcTagQuality.Bad           => "B",
    PlcTagQuality.Uncertain     => "U",
    PlcTagQuality.CommError     => "B",
    PlcTagQuality.NotConfigured => "U",
    _                           => "U"
};
```

`PlcTagQuality` is set by `PlcTagValuesPoolService.MarkPlcDisconnected()` (marks all tags `Uncertain`) and by `PlcWorker.ConvertQuality()` (maps driver quality on each read).

### `PlcTimeseriesRecord` simplified
Removed unused fields (`PlcId`, `RawValue`, `DataType`, `Quality` as int).
Now only carries what is written to DB:
```csharp
internal class PlcTimeseriesRecord
{
    public string TagId    { get; set; } = "";
    public DateTime Timestamp { get; set; }
    public double Value    { get; set; }
    public string Quality  { get; set; } = "G"; // G=Good, B=Bad, U=Uncertain
}
```

### `FilterReason` enum replaces `ShouldWriteValue` bool
Replaced `bool ShouldWriteValue(...)` with `FilterReason GetFilterReason(...)` returning `Write / Interval / Deadband`.
This enables separate metric counters for each skip reason.

---

## Files NOT Changed (Confirmed Safe)

| File | Reason |
|---|---|
| `PlcWorker.cs` | Already fills `PlcTagValuesPoolService` + sets quality correctly |
| `PlcTagValuesPoolService.cs` | Already thread-safe ConcurrentDictionary — no hidden List buffering |
| `PlcGatewayHostedService.cs` | Already loads PLC configs from DB + auto-refresh every 5min |
| `PlcConfigLoaderService.cs` | Already loads `DbLoggingIntervalMs`, `DeadbandValue` per tag |

---

## Final Data Flow

```
PLC (192.168.0.20) ← libplctag TCP
    ↓
PlcWorker  (polls per tag scan rate, sets PlcTagQuality)
    ↓ UpdateFromPlc()
PlcTagValuesPoolService  (ConcurrentDictionary — no hidden List, bounded by tag count)
    ↓ GetAllTagValues()  every 2000ms
PlcHistorianIngestService  (BackgroundService)
    ↓ GetFilterReason()
    Rate control (per tag, from tag_master):
      ├─ Interval not elapsed  → FilteredByInterval++, skip
      ├─ Deadband not exceeded → FilteredByDeadband++, skip
      └─ Write approved        → add to batch
    ↓ .Take(_batchSize)  [max 200 per cycle — burst protection]
    ↓ Pre-validation (skip null TagId / default Timestamp)
    ↓ _dataSource.OpenConnectionAsync(ct)  [pool borrow — no TCP handshake]
    ↓ BeginBinaryImportAsync() BINARY COPY
       → on COPY failure → FallbackInsertAsync() (per-row, isolated)
    ↓ CompleteAsync()
historian_raw.historian_timeseries  ✅

On DB failure:
    → _totalDbFailures++
    → await Task.Delay(5000, ct)  [5s backoff — no tight loop]
```

---

## Configuration Reference (both appsettings.json files)

```json
"ConnectionStrings": {
  "PlcGateway": "Host=localhost;Port=5432;Database=Automation_DB;Username=cereveate;Password=cereveate@222;Maximum Pool Size=30;Minimum Pool Size=5;Connection Timeout=15;Command Timeout=60;Keepalive=30"
},
"PlcGateway": {
  "HistorianPollIntervalMs": 2000,
  "HistorianBatchSize": 200,
  "DefaultWriteIntervalMs": 5000
}
```

---

## What Still Needs to Be Done

1. **Rebuild** — run `build.bat` to compile into `bin\Release\net8.0\win-x86\OpcDaWebBrowser.exe`
2. **Restart exe** — kill PID on port 5001, start new exe
3. **Reconnect OPC** — go to `http://localhost:5001` → connect to Matrikon OPC server
4. **Verify PLC writes** — query DB after 30s:
   ```sql
   SELECT time, tag_id, value_num, quality, sample_source
   FROM historian_raw.historian_timeseries
   WHERE tag_id = 'TY1101A' AND sample_source = 'PLC'
   ORDER BY time DESC LIMIT 10;
   ```
   Expected: rows ~5s apart, `quality = 'G'`, `sample_source = 'PLC'`
5. **Disconnect Flask writer** — once C# writes verified stable, remove `_persist_mqtt_samples()` call from `WEB_HMI_MFA/HMI/app.py`

---

## Session 3 Changes (May 23) — Compile Fix + Isolation + Log Visibility

### Fix 9 — Compile Error on Shutdown Log
**What:** `_totalFiltered` field did not exist — compiler error on service stop.
**Fix:** Replaced with explicit 4-field shutdown log using the two real counters:
```csharp
_logger.LogInformation(
    "[PLC HISTORIAN] Service stopped. TotalWrites: {W} | SkippedInterval: {SI} | SkippedDeadband: {SD} | DbFailures: {DF}",
    _totalWrites, _totalFilteredByInterval, _totalFilteredByDeadband, _totalDbFailures);
```

### Fix 10 — COPY Batch Log Upgraded from Debug → Information
**Why:** `LogDebug` is suppressed in production by default. Every COPY write was invisible.
**Fix:** Changed to `LogInformation` so every write cycle is always visible:
```
[PLC HISTORIAN] Wrote 12 records via COPY in 3ms
```

### Fix 11 — Per-Tag Exception Isolation in Evaluation Loop
**Why:** If one tag has a malformed value, null `PlcId`, or unexpected enum state, the entire `foreach` would throw — stopping evaluation of ALL remaining tags that cycle. Industrial systems must isolate bad points.
**Fix:** Entire per-tag evaluation body wrapped in `try/catch`:
```csharp
foreach (var tagValue in allValues)
{
    try
    {
        // rate control + quality derivation + add to batch
    }
    catch (Exception ex)
    {
        _logger.LogWarning(ex,
            "[PLC HISTORIAN] Per-tag evaluation error — PlcId={PlcId} Tag={Tag} — skipped this cycle",
            tagValue.PlcId, tagValue.TagName);
    }
}
```
One bad tag logs a warning and skips. The rest of the batch is unaffected.

---

## Session 4 Changes (May 23) — OPC Historian Connection Pool

### Context: Two parallel historian pipelines in the same exe

| Pipeline | Source | Writer |
|---|---|---|
| **OPC** | `TagValuesPoolService` (OPC DA tags) | `DbWriterService` via `HistorianIngestHostedService` |
| **PLC** | `PlcTagValuesPoolService` (PLC tags) | `PlcHistorianIngestService` |

Both write to `historian_raw.historian_timeseries`. Both now share the **same `NpgsqlDataSource` singleton** — registered once in `Program.cs`, injected into all services.

---

### `DbWriterService.cs` — 5 connection fixes

**Problem:** Every DB operation created `new NpgsqlConnection(_config.Database.ConnectionString)` — a new TCP handshake each time. The main write path also used sync `connection.Open()` instead of async.

**Fix:** `NpgsqlDataSource _dataSource` field added, injected via constructor. All `new NpgsqlConnection(...)` calls replaced with `await _dataSource.OpenConnectionAsync(ct)`.

| Location | Old | Fixed |
|---|---|---|
| `WriteBatchWithRetryAsync` (hot write path) | `new NpgsqlConnection` + sync `Open()` | `await _dataSource.OpenConnectionAsync(ct)` |
| `SaveCheckpointAsync` | `new NpgsqlConnection` + `OpenAsync()` | pool borrow |
| `LogEventAsync` | `new NpgsqlConnection` + `OpenAsync()` | pool borrow |
| `GetLatestTagValuesAsync` | `new NpgsqlConnection` + `OpenAsync()` | pool borrow |
| `CheckHealthAsync` | `new NpgsqlConnection` + `OpenAsync()` | pool borrow |

The `GetAllTagStatisticsFromPoolAsync`, `GetAllTagStatisticsAsync`, `GetTagStatisticsAsync`, `GetTrendsDataAsync` methods (monitor/UI queries) still use `new NpgsqlConnection` — these are **intentionally not changed** because they are low-frequency UI queries (not in the write hot path) and fixing them in a later pass is lower risk.

### `MappingCacheService.cs` — 1 connection fix + 1 intentionally left

**Fix:** `NpgsqlDataSource _dataSource` field added. The `RefreshCacheAsync` query (loads all tags from `historian_meta.tag_master`) now uses pool borrow instead of `new NpgsqlConnection`.

**Left unchanged — correct by design:** `_notifyConn` (the `LISTEN mapping_updated` connection at line 348) is a **dedicated persistent connection**. PostgreSQL LISTEN/NOTIFY requires keeping the connection open indefinitely to receive notifications. This must NOT be pooled — it is correct as-is.

```
_notifyConn = new NpgsqlConnection(...)  ← CORRECT — persistent LISTEN connection
RefreshCacheAsync conn = pool borrow      ← FIXED — short-lived query
```

### Constructor changes (both files)

```csharp
// DbWriterService — was:
public DbWriterService(HistorianConfig config, ILogger<DbWriterService> logger)

// DbWriterService — now:
public DbWriterService(HistorianConfig config, NpgsqlDataSource dataSource, ILogger<DbWriterService> logger)

// MappingCacheService — was:
public MappingCacheService(HistorianConfig config, ILogger<MappingCacheService> logger)

// MappingCacheService — now:
public MappingCacheService(HistorianConfig config, NpgsqlDataSource dataSource, ILogger<MappingCacheService> logger)
```

DI auto-injects the `NpgsqlDataSource` singleton already registered in `Program.cs`. No `Program.cs` changes needed.

---

## Files Changed — Complete List (All Sessions)

| # | File | Session | Changes |
|---|---|---|---|
| 1 | `Program.cs` | 1 | `using Npgsql;` + `NpgsqlDataSource` singleton registered |
| 2 | `Services/PlcGateway/PlcGatewayExtensions.cs` | 1 | `PlcHistorianIngestService` registered as singleton + hosted service |
| 3 | `Services/PlcGateway/Services/PlcHistorianIngestService.cs` | 1–3 | Full rewrite: pool, correct table, rate control, 11 fixes |
| 4 | `appsettings.json` (source) | 1–2 | Pool settings in connection string + `PlcGateway` config keys |
| 5 | `bin\Release\net8.0\win-x86\appsettings.json` | 1–2 | Same as above — this is the file the running exe reads |
| 6 | `Services/HistorianIngest/Services/DbWriterService.cs` | 4 | `NpgsqlDataSource` injected + 5 connection fixes |
| 7 | `Services/HistorianIngest/Services/MappingCacheService.cs` | 4 | `NpgsqlDataSource` injected + cache refresh connection fixed |

---

## Architectural Review — Strengths, Risks & Roadmap

---

### ✅ Confirmed Strengths

**1. Pool-first architecture is the most important correct decision**

```
OPC → TagValuesPoolService      → HistorianIngestHostedService → DB
PLC → PlcTagValuesPoolService   → PlcHistorianIngestService    → DB
```

This gives: DB isolation, burst absorption, acquisition resilience, future scaling.
Without this: DB latency affects acquisition, historian stalls affect control visibility, reconnect storms kill stability.

**2. `mapping_version` field already present**
Most systems forget this. When deadband, engineering units, or scaling changes later — every historical row is traceable to the config version that produced it. Critical for forensic analysis.

**3. Circuit breaker correctly differentiates error types**
Duplicate key (23505) ≠ system failure. Connection failure (08xxx) = system failure.
Most developers trip the breaker on ALL exceptions. This system correctly separates business/data errors from infrastructure failures. Production-grade thinking.

**4. `SpoolManagerService` already exists**
Spool-to-disk is what separates an industrial historian from a normal app.
DB outage must NOT equal data loss. This is already architecturally present — needs maturity.

**5. `opc_timestamp` column preserved alongside ingest time**
Both source device time and acquisition time stored separately. This becomes essential for time sync audits.

**6. Two-gate rate control (interval + deadband combined)**
Most bad historians implement only one gate. Both together massively reduce DB writes while preserving all meaningful process events.

---

### ⚠️ Current Risks to Watch

**Risk 1 — Two independent historian engines competing for the same DB pool**

Right now there are two separate schedulers, two retry systems, two batchers, two COPY loops — all writing to the same table:

| Resource | Contention |
|---|---|
| DB connection pool | Both draw from same 30-connection pool |
| WAL | Two COPY streams compete |
| `historian_latest_value` upserts | Hot table — constant UPSERT contention |
| CPU | Two scheduling loops, two rate controllers |

This is acceptable at current scale (1 PLC, ~50 OPC tags). Becomes critical above ~500 active tags or when adding more PLC sources.

**Risk 2 — `historian_latest_value` write amplification**

Every successful timeseries write also UPSERTs `historian_latest_value`. At scale this table becomes extremely hot — constant index pressure, row locking, autovacuum pressure — before the timeseries table itself becomes a bottleneck.

**Risk 3 — Random jitter in retry logic**

`Random.Shared.Next()` inside `WriteBatchWithRetryAsync` can synchronize retry storms across services when both historians fail at the same time (e.g., DB restart). All retries align and hit the DB simultaneously.

**Risk 4 — Unbounded memory if samples are retained**

The OPC batcher uses a bounded channel — good. The PLC pool uses a ConcurrentDictionary (latest value only) — good. The system philosophy must remain **latest value wins**, not **every sample must survive in RAM**. Industrial historians never guarantee infinite in-memory retention.

---

### 🔮 Future Roadmap (Priority Order)

**Priority 1 — Unified Historian Writer (most important evolution)**

Move from two independent pipelines to one unified engine:

```
OPC Pool ─┐
          ├── UnifiedRateController (per tag, source-agnostic)
PLC Pool ─┘         ↓
               UnifiedBatcher (single bounded channel)
                    ↓
             UnifiedCopyWriter (one COPY loop, one pool draw)
                    ↓
         historian_raw.historian_timeseries
```

Benefits: one retry system, one metrics system, one scheduler, one DB pool draw, linear scaling as sources are added. This is how enterprise historians (OSIsoft PI, AVEVA, Ignition) work — many acquisition sources, ONE historian engine.

**Priority 2 — Latest Value Separation**

Move `historian_latest_value` out of the write hot path:

```
Current:  every DB write → UPSERT historian_latest_value (hot, contended)
Future:   in-memory snapshot service → periodic checkpoint to DB (cold, batched)
```

Latest values ≠ historical archive. They serve different consumers at different frequencies. HMI needs latest values at 1s; the DB write path should not be burdened by it.

**Priority 3 — Tag Priority Queue**

Not all tags are equal:

| Tag Type | Priority |
|---|---|
| PLC heartbeat, safety interlock | Critical — never drop |
| Batch start/end transitions | Critical — never drop |
| Temperature, pressure trends | Medium |
| Vibration RMS, flow | Medium |
| Ambient sensors, diagnostics | Low — drop first under overload |

Under overload: low-value telemetry drops first. Critical events survive. The current `GetFilterReason()` structure supports adding a priority override before Gate 1.

**Priority 4 — Decorrelated Retry Jitter (replace `Random.Shared`)**

Replace current exponential backoff with decorrelated jitter (AWS/Netflix pattern) to prevent synchronized retry storms:
```csharp
// Instead of: Random.Shared.Next(0, delayMs / 2)
// Use Polly with decorrelated jitter policy
```

**Priority 5 — TimescaleDB Hypertable (if not already)**

`historian_raw.historian_timeseries` must be a hypertable with proper chunk sizing, compression policy, and retention policy before row counts reach tens of millions. Query performance degrades sharply on a plain PostgreSQL table at that scale.

```sql
SELECT create_hypertable('historian_raw.historian_timeseries', 'time',
    chunk_time_interval => INTERVAL '1 day');
SELECT add_compression_policy('historian_raw.historian_timeseries',
    INTERVAL '7 days');
```

**Priority 6 — Historian Modes per Tag**

```
Normal         → interval + deadband (current)
AlwaysOnChange → write on any change regardless of interval
CriticalEvent  → force immediate write (alarms, trips, shutdowns)
```

The current `GetFilterReason()` + `FilterReason` enum supports this — add a priority check before Gate 1 with no structural changes.

**Priority 7 — Workload Separation**

| DB Role | Purpose | Frequency |
|---|---|---|
| Realtime cache (Redis/memory) | Latest values for HMI | 1s |
| Historian DB (TimescaleDB) | Compressed process history | 5s+ |
| Analytics DB | BI/ML queries | Minutes/hours |
| Archive DB | Long-term retention | Months/years |

Currently: UI reads, trend queries, ingestion, and latest values all hit the same DB. This is acceptable now. Separation becomes necessary above ~1000 tags or when BI queries begin competing with ingest for connections.

---

### Current Scale vs Future Thresholds

| Metric | Current | Watch point | Action needed |
|---|---|---|---|
| Active tags | ~50 OPC + few PLC | 500 | Unified writer |
| DB writes/sec | <1 (rate controlled) | 50+ | Pool tuning |
| `historian_latest_value` UPSERTs | <1/s | 20+/s | Move to memory |
| Timeseries rows | Unknown | 100M+ | Hypertable + compression |
| Historian sources | 2 (OPC + 1 PLC) | 5+ | Priority queue |

---

```
Acquisition frequency  ≠  Storage frequency
```

This is the most important concept in historian design. The PLC is polled fast because control systems need fresh data. The database stores only what is **meaningful for historical analysis**.

| Layer | Frequency | Purpose |
|---|---|---|
| PLC polling (PlcWorker) | 1000ms | Control system freshness |
| UI refresh (API reads pool) | 1000ms | HMI operator view |
| Historian storage | 5000ms + change detection | Process history |
| KPI aggregation | 1 minute | Shift reporting |
| Management reports | 1 hour | Plant performance |

Each layer serves a different consumer. They must not be coupled.

### Why NOT write every poll to DB

If PLC polls every 1000ms with 50 tags → **50 writes/second = 180,000 writes/hour per tag set**. Most of those values are:
- Identical (sensor stable)
- Noise (±0.001 fluctuation)
- Meaningless (no process event occurred)

Every raw write stresses: WAL, indexes, autovacuum, disk IO, compression, backup window, query planner. You accumulate millions of rows of garbage that slow down every trend query.

### Why filtering BEFORE insert is correct

Filtering after insert is too late — disk is consumed, WAL is written, indexes are updated. The application must decide **before** the insert whether the value is worth storing. The database's job is to store valuable process history efficiently, not to be a raw data dump.

### The 2-Gate Model (implemented)

```
For every tag, every 2000ms:

Gate 1 — Time Gate
  ├─ Less than 5000ms since last write? → SKIP
  └─ 5000ms+ elapsed → proceed to Gate 2

Gate 2 — Value Gate
  ├─ Value unchanged (or within deadband)? → SKIP
  └─ Value changed → WRITE
```

Gate 1 prevents high-frequency spam. Gate 2 prevents noise pollution. Both gates together mean the historian only stores **events** — moments when the process actually changed.

**Example — temperature sensor without deadband:**
```
Raw values arriving every 1s:   72.201, 72.203, 72.205, 72.202, 72.204
Historian stores (5s interval): 72.201  (next write only if value changed)
```
Without deadband, slight noise still triggers writes. With deadband=0.5, none of those fluctuations reach the DB.

### Memory Pool Separation Is Critical

```
DB outage      → PLC polling continues unaffected
Historian lag  → Pool holds latest value, no data lost
HMI slowness   → Pool reads are in-memory, zero DB load
```

The `PlcTagValuesPoolService` (ConcurrentDictionary) acts as a decoupling buffer. Acquisition and persistence are completely independent. This is the same pattern used by OSIsoft PI, AVEVA, Ignition, and Canary Labs — all industrial historians use memory buffering + compression filtering before persistence.

### Future Extension — Critical Event Override

Current design filters all tags equally. A future `HistorianMode` per tag could add:
```
Normal           → interval + deadband (current behaviour)
AlwaysOnChange   → write on any change regardless of interval
CriticalEvent    → force immediate write (alarms, trips, shutdowns)
```
The current `GetFilterReason()` structure supports this — add a third check before Gate 1.

---

## Rate Control Summary

`TY1101A` in `historian_meta.tag_master`:
- `db_logging_interval_ms = 5000` → writes every ~5 seconds
- `deadband_value = NULL` → exact comparison (any value change triggers write)
- Before: Flask writing every ~2s, no rate control, quality always `'G'`
- After: C# writes every ~5s, only on value change, quality reflects real PLC state
