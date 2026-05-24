# Architectural Audit Report — Cereveate OPC DA Central Module
**Date**: December 2025  
**Scope**: Full data path from OPC server poll → TagValuesPoolService → HistorianIngest → PostgreSQL → MQTT (planned)  
**Method**: Static code analysis of all production service files  
**Standard**: IEC 62443 (Industrial Cyber Security), IEC 61511 (Functional Safety), general software reliability

---

## Executive Summary

The platform's core data path is fundamentally sound. The OPC polling loop, shared pool cache, rate-controlled historian ingest, and two-tier WAL (Parquet + Spool) are well-architected. However, **11 discrete failure points** were identified during code review. Three are **CRITICAL** severity and would cause silent data loss or security exposure in production. The remaining are medium/low but compound under fault conditions. All are fixable with targeted changes — no architectural redesign is required.

---

## Audit Findings

---

### FINDING 001 — CRITICAL: API Authentication Bypass Is Total, Not Partial

**Severity**: 🔴 CRITICAL  
**File**: `Program.cs` lines ~185–195  
**Category**: Security / Access Control

**What the code actually does:**
```csharp
if (path.StartsWith("/api") || path.StartsWith("/opchub"))
{
    await next();  // ← Skips ALL auth checks for every API endpoint
    return;
}
```

The custom session-based auth middleware **explicitly exempts every route beginning with `/api`**. This is not a missing `[Authorize]` attribute on one controller — it is a blanket policy that permits any unauthenticated HTTP client on the network to:

- `GET /api/opc/values` → receive all 10K+ live tag values with engineering values and quality codes
- `GET /api/historian/...` → query the historian
- `POST /api/plc/...` → potentially write to PLCs (if any write endpoints exist)
- All future API routes added by any developer — automatically unauthenticated

**Why this is critical:**
- The application is bound to `0.0.0.0:5001` (all network interfaces, `ListenAnyIP`). Any machine that can reach port 5001 on the network can read all process values in real-time.
- Industrial networks often have jump hosts, vendor laptops, or compromised endpoints. This requires no credential.
- The session auth protecting the web UI gives a **false sense of security** — the actual data APIs are wide open.

**Questions for the team:**
1. Was this intentional (e.g., trusted-network-only assumption)?
2. Does any external client (Python analytics, HMI, MQTT publisher) rely on unauthenticated API access?
3. Is there a network firewall rule that compensates (e.g., port 5001 blocked at switch level)?

**Recommended Fix:**
Replace the blanket `/api` bypass with a token-based API key or JWT middleware. Add `[Authorize]` to all API controllers. If a subset of endpoints must be public (e.g., for HMI polling), whitelist those specific routes only.

---

### FINDING 002 — CRITICAL: Pool-Level Deadband Is Never Applied — IsChanged Always Compares Strings

**Severity**: 🔴 CRITICAL  
**File**: `Services/DataLoggingService.cs` line ~507  
**Category**: Data Integrity / Correctness

**What the code actually does:**
```csharp
_tagPool.UpdatePool(allValues, batchTimestamp);  // ← No deadbandMap argument
```

`TagValuesPoolService.UpdatePool()` accepts an optional `deadbandMap` parameter to decide whether a new value constitutes a real change. This parameter is **never passed** by `DataLoggingService`. The method signature is:

```csharp
public void UpdatePool(IEnumerable<OpcTagValue> values, DateTime timestamp, Dictionary<string, double>? deadbandMap = null)
```

With `deadbandMap = null`, the pool's `IsChanged()` method falls back to `string.Equals(oldValue?.ToString(), newValue?.ToString())` for ALL tags, including `double` and `float` process values.

**Impact:**
- The pool's `PoolUpdated` event fires correctly, but change detection for analog tags is based on string equality (e.g., `"23.14159265358979"` vs `"23.14159265358978"`) — IEEE 754 floating-point string representation differences can cause phantom "changes" or "non-changes" depending on formatting precision.
- The documentation (PHASE1_SERVER_RELIABILITY.md) describes pool-level deadband as "the one authoritative location for change detection." This is not yet true. The deadband in `tag_master` only applies inside `RateControllerService`, not at the pool level.
- This creates **two separate change detection mechanisms** that can disagree on whether a value has changed:
  - Pool: String comparison → fires `PoolUpdated` on every floating-point string difference
  - RateController: Numeric deadband threshold → may filter what pool considered a change

**Questions for the team:**
1. Is the deadband-at-pool-level feature intentionally deferred, or is this an oversight?
2. Does any consumer of `PoolUpdated` event (planned MQTT publisher) rely on pool-level change detection being correct?

**Recommended Fix:**
In `DataLoggingService.LogData()`, load the deadband map from `MappingCacheService` and pass it to `UpdatePool()`:
```csharp
var deadbandMap = _mappingCache.GetDeadbandMap(); // add this method
_tagPool.UpdatePool(allValues, batchTimestamp, deadbandMap);
```

---

### FINDING 003 — CRITICAL: Spool AutoReplay Is Disabled by Default — DB Backlog Accumulates Silently

**Severity**: 🔴 CRITICAL  
**File**: `appsettings.json` → `Historian.Spool.AutoReplay = false`; `SpoolManagerService.cs`  
**Category**: Data Durability / Operational Safety

**What the code actually does:**

The Spool is the historian's second-level WAL — when PostgreSQL is unavailable, batches are written as JSON `.ready` files to `D:\HistorianSpool`. `SpoolManagerService` has a replay loop that re-reads and re-submits these files.

**However**, `AutoReplay` is set to `false` in the default configuration:
```json
"Spool": {
    "AutoReplay": false,
    ...
}
```

With `AutoReplay = false`, the replay loop **never runs**. Spool files written during a DB outage accumulate indefinitely. When DB comes back, they are NOT automatically replayed. The data remains in the spool directory until either:
1. An operator manually changes `AutoReplay` to `true` and restarts the service
2. A manual replay API endpoint (if one exists) is called

**Compound failure scenario:**
1. DB goes offline at 02:00 during a night shift
2. Spool accumulates 6 hours of data (potentially hundreds of files)
3. DB comes back at 08:00
4. **No data is ever replayed** — the gap in historian is permanent
5. Operators see a 6-hour hole in trend data and investigate a process event that caused no alarm because the data was lost

**Questions for the team:**
1. Why was `AutoReplay` set to `false`? Was there a specific operational reason (e.g., spool files were causing duplicate inserts during testing)?
2. Is there an operator-facing UI or API endpoint to manually trigger replay?
3. Does the health dashboard surface "spool files pending replay" as an alert?

**Recommended Fix:**
Set `AutoReplay: true` in `appsettings.json`. Ensure idempotency on replay (duplicate detection) is working before enabling. Add a health check metric: `spool_pending_file_count` exposed on `/health` endpoint.

---

### FINDING 004 — HIGH: WAL Channel `BoundedChannelFullMode.Wait` Can Block the OPC Poll Loop

**Severity**: 🟠 HIGH  
**File**: `Services/DataLoggingService.cs` — WAL channel construction  
**Category**: Reliability / Back-pressure

**What the code does:**

The DataLoggingService Parquet WAL uses a `Channel<T>` to queue write operations. If the channel's bounded capacity is reached, the producer (the OPC poll loop) blocks because the channel is created with `BoundedChannelFullMode.Wait`.

**Failure chain:**
1. Disk I/O slows (e.g., antivirus scan, disk nearly full, NAS latency spike)
2. WAL writer cannot consume the channel fast enough → channel fills up
3. `_tagPool.UpdatePool()` call, which comes BEFORE the WAL write, is on the same thread as the channel write
4. The OPC poll loop stalls — ALL tag value updates pause
5. `TagValuesPoolService` stops being refreshed — staleness timer may trigger `MarkAllStale()`
6. SignalR clients see stale data; historian ingest sees repeated last-known values

**Why this matters:**
The OPC poll loop is the heartbeat of the entire system. Any blocking operation on that path directly affects real-time visibility for operators.

**Recommended Fix:**
Switch the channel to `BoundedChannelFullMode.DropOldest` (for WAL, losing oldest queued writes is acceptable because they will be superseded by newer values). Alternatively, decouple `UpdatePool()` from the WAL path entirely — run WAL write as a fully independent `Task.Run()` with a `CancellationToken`.

---

### FINDING 005 — HIGH: Two Completely Separate WAL Systems Create Operational Confusion

**Severity**: 🟠 HIGH  
**File**: `DataLoggingService.cs` (binary WAL), `SpoolManagerService.cs` (JSON spool)  
**Category**: Operability / Incident Response

**What exists:**

| System | Owner | Format | Location | Purpose | Replay |
|--------|-------|--------|----------|---------|--------|
| Parquet WAL | `DataLoggingService` | Binary (`BinaryWriter`) | `_walFolder` in config | Crash-safe parquet file rotation | Built into service restart |
| Historian Spool | `SpoolManagerService` | JSON `.ready` files | `D:\HistorianSpool` | DB outage buffer for historian ingest | `AutoReplay` flag |

These are **not the same system**. They serve different consumers and have different replay mechanisms, file formats, and failure modes. Documentation and team communication must not conflate them.

**Risk scenarios:**
- An operator sees files accumulating in `D:\HistorianSpool` and deletes them thinking they are "already processed WAL files" — silent data loss
- A support engineer checks the Parquet WAL folder looking for missing historian data — wrong WAL, wrong consumer
- Neither WAL is surfaced on the health dashboard in a differentiated way

**Recommended Fix:**
1. Document both systems explicitly (this report starts that work)
2. Add distinct health metrics: `parquet_wal_pending_count` and `historian_spool_pending_count`
3. Add log prefixes: `[PARQUET-WAL]` vs `[HISTORIAN-SPOOL]` to all related log entries
4. Never allow the `_walFolder` and spool folder to share the same directory

---

### FINDING 006 — HIGH: `connection.Open()` Synchronous Call Inside `async` DB Writer

**Severity**: 🟠 HIGH  
**File**: `Services/HistorianIngest/Services/DbWriterService.cs`  
**Category**: Performance / Thread-pool starvation

**What the code does:**
```csharp
// Inside WriteBatchWithRetryAsync (an async Task method):
connection.Open();   // ← Synchronous, blocks calling thread
// Should be:
await connection.OpenAsync();
```

`connection.Open()` on Npgsql (PostgreSQL .NET driver) is a synchronous blocking call. When called inside an `async` method:
1. The thread-pool thread executing the `async` method blocks for the duration of the TCP handshake + PostgreSQL authentication (typically 5–50ms, but up to seconds on network congestion)
2. Under load (10K tags, many concurrent batch writes), this exhausts thread-pool threads
3. .NET's thread-pool reacts by injecting new threads (rate-limited at ~1 thread/500ms), causing latency spikes across all async operations in the process — including OPC polling, SignalR, and API responses

**This is especially dangerous** in x86 mode (which this process requires for COM interop) because x86 processes have a lower maximum thread-pool size than x64.

**Recommended Fix:**
```csharp
await connection.OpenAsync(cancellationToken);
```
Apply the same fix to every synchronous ADO.NET call in `DbWriterService.cs`: `ExecuteNonQueryAsync()`, `ExecuteReaderAsync()`, etc.

---

### FINDING 007 — MEDIUM: DB Write Semaphore Has a 30-Second Hard Block

**Severity**: 🟡 MEDIUM  
**File**: `Services/HistorianIngest/Services/DbWriterService.cs`  
**Category**: Reliability / Latency

**What the code does:**
```csharp
await _writeSemaphore.WaitAsync(TimeSpan.FromSeconds(30));
```

Under extreme DB backpressure (all writer shards busy for >30 seconds), the semaphore times out. The behavior after timeout must be verified — if it throws and the batch is dropped without spooling, data is silently lost.

**Scenarios that trigger this:**
- DB server CPU-bound on indexing after a long outage (catch-up writes)
- Network partition causes every write attempt to wait full TCP timeout (~21s) before failing
- Hypertable compression job running — write contention on TimescaleDB

**Questions for the team:**
1. What happens when the semaphore times out? Is the batch spooled or dropped?
2. Is there an alert/metric for "semaphore timeout count"?

**Recommended Fix:**
Log a `LogCritical` on semaphore timeout with batch size and tag IDs. Ensure the timed-out batch is handed to `SpoolManagerService` rather than discarded.

---

### FINDING 008 — MEDIUM: `LogData()` Inner Catch Only Logs `LogError` — No Stale-Mark Triggered

**Severity**: 🟡 MEDIUM  
**File**: `Services/DataLoggingService.cs` — inner `try/catch` in `LogData()`  
**Category**: Observability / Safety

**What the code does:**

The outer `ExecuteAsync` loop has watchdog behavior that calls `_tagPool.MarkAllStale()` and waits before restarting. However, the inner `LogData()` method has its own `try/catch` that only calls `_logger.LogError(...)` and returns. If an exception occurs inside `LogData()` (e.g., OPC COM call throws, or pool update fails):

- The outer watchdog does **not** fire
- `MarkAllStale()` is **not** called
- The HMI continues showing the last-known values **without any staleness indicator**
- Operators may act on stale process values believing they are fresh

**Recommended Fix:**
Re-throw the exception from the inner catch (after logging) OR explicitly call `_tagPool.MarkAllStale()` in the inner catch. The watchdog pattern is already in place — just ensure it is reachable.

---

### FINDING 009 — MEDIUM: Spool Replay Is Capped at 500 Files Per Cycle — Large Backlog Takes Hours to Clear

**Severity**: 🟡 MEDIUM  
**File**: `Services/HistorianIngest/Services/SpoolManagerService.cs`  
**Category**: Recovery Time / Data Timeliness

**What the code does:**
```csharp
var filesToReplay = pendingFiles.Take(500).ToList();
```

With a 50ms inter-file throttle and 500 files per cycle, one replay cycle can process at most 500 files in ~25 seconds. If a 4-hour DB outage spooled 10,000 files (assuming 1 batch/second → 14,400 files), clearing the backlog takes:
- 10,000 ÷ 500 = **20 replay cycles**
- Plus cycle restart delays
- Total estimated catch-up time: **10–15 minutes minimum after DB recovery**

During catch-up, the historian is writing old data with increasing lag. If any downstream system relies on "latest historian value" for control decisions, this lag is undetected.

**Recommended Fix:**
Make the per-cycle limit configurable (`Spool.MaxFilesPerCycle`). After major outages, allow operators to set a higher limit temporarily. Add a metric: `spool_estimated_catchup_minutes`.

---

### FINDING 010 — MEDIUM: `seq_state.json` 30-Second Persist Interval — Hard Crash Loses Up to 30 Seconds of Sequence IDs

**Severity**: 🟡 MEDIUM  
**File**: `Services/TagValuesPoolService.cs`  
**Category**: Data Integrity / Crash Recovery

**What the code does:**
```csharp
// Persists seq_state.json every 30 seconds
```

`seq_state.json` tracks the last-written sequence ID per tag for change detection. On a hard power-off or process kill (`SIGKILL`/Task Manager), up to 30 seconds of state is lost. After restart:
- Sequence IDs reset to the last persisted state
- Tags that changed in the last 30s before crash appear as "new changes" on restart
- `RateControllerService` will re-write their current values to the DB — this is mostly harmless (idempotent upsert) but generates unnecessary DB write traffic
- More critically: if a tag was stable before the crash but `seq_state.json` shows a stale sequence ID, the first-sample rule in `RateControllerService` treats it as a first write, bypassing deadband for one cycle

**Recommended Fix:**
Reduce persist interval to 5 seconds or persist on-demand when a batch exceeds a configurable count threshold. This is a low-cost I/O operation.

---

### FINDING 011 — LOW: Single-Instance Mutex Is Commented Out — Multiple Process Instances Possible

**Severity**: 🟢 LOW  
**File**: `Program.cs` lines ~21–42  
**Category**: Operational Safety

**What the code does:**
```csharp
// Single instance protection using Mutex - COMPLETELY DISABLED
// var mutexName = "Global\\CereveateOPCWebBrowser_SingleInstance";
```

The global mutex that prevents running two instances of the process simultaneously is disabled. In a Windows service environment, if a service restart is attempted while the old process is still shutting down (e.g., slow COM teardown), two instances can coexist momentarily or indefinitely:
- Both instances poll OPC → duplicate events
- Both instances attempt to write to the same Parquet WAL folder → file lock collisions
- Both instances attempt to insert to PostgreSQL → duplicate rows in `historian_timeseries`

**Questions for the team:**
1. Was the mutex disabled because it was causing issues on Windows service restart (common issue with Global\\ named mutexes and service accounts)?
2. Is there a service manager (e.g., NSSM, Windows Services) that guarantees sequential start/stop?

**Recommended Fix:**
Re-enable the mutex or implement a lock file approach using a PID file in the application directory. Log clearly on startup if another instance is detected rather than silently exiting.

---

## Summary Matrix

| # | Finding | Severity | Category | File(s) |
|---|---------|----------|----------|---------|
| 001 | All `/api` routes unauthenticated by middleware policy | 🔴 CRITICAL | Security | `Program.cs` |
| 002 | `deadbandMap` never passed to `UpdatePool()` — string comparison only | 🔴 CRITICAL | Data Integrity | `DataLoggingService.cs` |
| 003 | `Spool.AutoReplay = false` — DB backlog accumulates silently forever | 🔴 CRITICAL | Data Durability | `appsettings.json`, `SpoolManagerService.cs` |
| 004 | WAL channel `BoundedChannelFullMode.Wait` can block OPC poll loop | 🟠 HIGH | Reliability | `DataLoggingService.cs` |
| 005 | Two separate WAL systems not documented — operational confusion risk | 🟠 HIGH | Operability | `DataLoggingService.cs`, `SpoolManagerService.cs` |
| 006 | `connection.Open()` sync call in async DB writer — thread-pool risk | 🟠 HIGH | Performance | `DbWriterService.cs` |
| 007 | 30s semaphore hard block — potential silent batch drop on timeout | 🟡 MEDIUM | Reliability | `DbWriterService.cs` |
| 008 | Inner `LogData()` catch only logs — `MarkAllStale()` not triggered | 🟡 MEDIUM | Observability | `DataLoggingService.cs` |
| 009 | Spool replay capped at 500 files/cycle — 10K+ backlog takes 15+ min | 🟡 MEDIUM | Recovery Time | `SpoolManagerService.cs` |
| 010 | `seq_state.json` persists every 30s — crash loses up to 30s of state | 🟡 MEDIUM | Data Integrity | `TagValuesPoolService.cs` |
| 011 | Single-instance mutex disabled — duplicate process instances possible | 🟢 LOW | Operational Safety | `Program.cs` |

---

## Open Architectural Questions

These require team input before resolving:

1. **Authentication strategy**: Is session-based auth (current) the correct model for API consumers (Python, HMI, MQTT)? Or is API key / JWT needed? If yes, which endpoints must remain public and for which clients?

2. **Pool-level deadband ownership**: Should `TagValuesPoolService` be the single authority for change detection (requiring `MappingCacheService` as a dependency of `DataLoggingService`)? Or should `RateControllerService` remain the sole deadband enforcer and pool-level `IsChanged` be removed entirely?

3. **Spool AutoReplay production policy**: What is the operational procedure for DB outage + recovery? Is manual replay acceptable, or must it be automatic? Who is responsible for monitoring the spool directory?

4. **MQTT publish path dependency**: The planned `MqttPublisher` (Phase 1 items 14–15) subscribes to `TagValuesPoolService.PoolUpdated`. Since pool change detection currently uses string comparison (Finding 002), the MQTT publisher will fire on floating-point string noise. Is this acceptable for the HMI use case or will it saturate the broker?

5. **x86 platform constraint lifetime**: How long will this service remain x86 (required for OPC DA COM interop)? x86 thread-pool limits compound Finding 006. If OPC DA is eventually replaced by OPC UA, x64 migration resolves Finding 006 naturally.

6. **Duplicate DB inserts on spool replay**: Is there a UNIQUE constraint or `ON CONFLICT DO NOTHING` on `historian_raw.historian_timeseries` that makes spool replay idempotent? If not, a replay after a crash-with-partial-write will create duplicate rows.

---

*End of Architectural Audit Report — Cereveate OPC DA Central Module*
