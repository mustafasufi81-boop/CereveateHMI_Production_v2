# OPC Historian DB Write Fix — Plan & Status

> **Reference Architecture**: `.github/copilot-instructions.md`
> **Last Updated**: May 23, 2026
> **Status**: ✅ FULLY WORKING — OPC + all DB-mapped tags (Triangle Waves, Bucket Brigade etc.) flowing to DB

---

## ⚡ QUICK REFERENCE — NEXT SESSION START

### Correct Exe Path (DO NOT USE OLD PATH)
```
CORRECT:  bin\x86\Release\net8.0\win-x86\OpcDaWebBrowser.exe   ← NEW BUILD OUTPUT
WRONG:    bin\Release\net8.0\win-x86\OpcDaWebBrowser.exe        ← OLD, STALE, DO NOT USE
WRONG:    bin\Release\net8.0\publish\OpcDaWebBrowser.exe        ← EVEN OLDER
```

### Kill → Build → Start (EXACT SEQUENCE — ALWAYS IN THIS ORDER)
```powershell
# STEP 1: Kill running exe FIRST (cannot overwrite a running exe on Windows)
$p = Get-Process | Where-Object {$_.Name -like "*OpcDa*"} | Select-Object -First 1
Stop-Process -Id $p.Id -Force
Start-Sleep 2

# STEP 2: Build (exe is now free to be written)
Set-Location 'c:\MQTT_Implemented_OPC\Copied_MQTT\BACKUP_BEFORE_HISTORICAL_20251117_225747 - Copy_backup_20251206'
dotnet build -c Release -p:Platform=x86 --nologo -v quiet 2>&1 | Select-Object -Last 5
# Verify output says: OpcDaWebBrowser -> ...\bin\x86\Release\net8.0\win-x86\OpcDaWebBrowser.dll

# STEP 3: Copy configs to new bin (ONLY NEEDED FIRST TIME or after adding new config keys)
$ROOT = 'c:\MQTT_Implemented_OPC\Copied_MQTT\BACKUP_BEFORE_HISTORICAL_20251117_225747 - Copy_backup_20251206'
$NEWBIN = "$ROOT\bin\x86\Release\net8.0\win-x86"
$OLDBIN = "$ROOT\bin\Release\net8.0\win-x86"
Copy-Item "$OLDBIN\logging-config.json" "$NEWBIN\" -Force
Copy-Item "$OLDBIN\appsettings.json"    "$NEWBIN\" -Force

# STEP 4: Start new exe with log redirect
Start-Process -FilePath "$NEWBIN\OpcDaWebBrowser.exe" `
              -WorkingDirectory $NEWBIN `
              -RedirectStandardOutput "C:\Temp\opc_outN.log" `
              -RedirectStandardError  "C:\Temp\opc_errN.log" `
              -WindowStyle Minimized
Start-Sleep 15

# STEP 5: Verify
Get-Process | Where-Object {$_.Name -like "*OpcDa*"} | Select-Object Id, StartTime
netstat -ano | findstr ":5001" | findstr LISTENING
```

### Verify OPC + All Tags Writing to DB
```sql
-- Run in pgAdmin to confirm all sources writing
SELECT sample_source, COUNT(*), MAX(time) as latest
FROM historian_raw.historian_timeseries
WHERE time > NOW() - INTERVAL '2 minutes'
GROUP BY sample_source;
-- Expected: OPC row with recent timestamp, PLC row with recent timestamp

-- Confirm specific OPC tags flowing
SELECT tag_id, COUNT(*), MAX(time)
FROM historian_raw.historian_timeseries
WHERE sample_source = 'OPC' AND time > NOW() - INTERVAL '10 minutes'
GROUP BY tag_id ORDER BY MAX(time) DESC;
-- Expected: Random.Real8, Random.Int8 (5s), Triangle Waves.*, Bucket Brigade.* (300s)
```

### Check Log for Issues
```powershell
Get-Content "C:\Temp\opc_outN.log" | Select-String "Late-subscribed|Startup OPC|DB-WRITER|SUCCESS|ERROR|failed" | Select-Object -Last 30
```

---

## 0. Full Existing Architecture (Before This Fix)

### How the system was wired BEFORE this fix

```
OPC Server (Matrikon.OPC.Simulation.1)
         │
         │  [Connection A — Main]
         ▼
OpcDaService (singleton)
  • Managed by OpcAutoConnectService
  • Polls tags via OpcServerConnection at 1000ms
  • Raises TagValuesUpdated event
  • Method: ReadAllTagValues() — returns snapshot of all cached tag values
         │
         ├──────────────────────────────────────────────────────────┐
         │  TagValuesUpdated event                                  │
         ▼                                                          ▼
OpcDaHub (SignalR)                                     [NOT CONNECTED to historian]
  • Broadcasts to HMI WebSocket clients
  • No DB writes — UI only


         │  [Connection B — Separate, owned by DataLoggingService]
OPC Server (Matrikon.OPC.Simulation.1)
         │
         ▼
DataLoggingService  (BackgroundService)
  • Creates and owns its OWN OpcServerConnection
  • GUARD: if GetDecryptedProgId() == null → skip entire loop → NEVER RUNS
  • If running: calls connectionSnapshot.GetCachedValues()
  • Calls _tagPool.UpdatePool(allValues, timestamp)   ← populates shared cache
  • Writes Parquet files for SelectedTags (logging-config.json) every 5000ms
         │
         ▼
TagValuesPoolService  (Singleton, in-memory cache)
  • Updated by DataLoggingService every 1000ms (IF DataLoggingService is running)
  • Read by: HMI API (/api/opc/values) — always
  • Read by: HistorianIngestHostedService — THIS IS THE BROKEN DEPENDENCY
         │
         ├──────────────────────────────────────────┐
         │  HMI API                                 │  Historian (BROKEN PATH)
         ▼                                          ▼
OpcController.GetValues()             HistorianIngestHostedService
  → _tagPool.GetAllTagValues()          PrecisePollingLoopAsync():
  → Returns to dashboard.js              var poolTimestamp = _tagPool.GetLastUpdateTimestamp()
                                         if (poolTimestamp == DateTime.MinValue) → WAIT FOREVER
                                         var cachedTagValues = _tagPool.GetTagValues(mappedTagIds)
                                         if (cachedTagValues.Count == 0) → NOTHING TO WRITE
                                                   │
                                                   ▼
                                         DbWriterService.WriteBatchAsync()
                                         → WriteSamplesBinaryCopyAsync()
                                         → historian_raw.historian_timeseries
```

### Why It Failed in Practice

```
Log shows:
  01:54:19  Data Logging Service started
  01:54:19  OpcAutoConnectService starting background auto-connect loop
  01:54:22  Auto-connect: OPC server connected (main OpcDaService connection)
  ...
  [SILENCE — no "Creating dedicated OPC connection", no "TagPool updated"]

Reason:
  DataLoggingService loop:
    config.IsEnabled = true  ✓
    GetDecryptedProgId()     → returned "" or null  ✗
    → hit the guard → continue → slept 1000ms → repeated forever

  Result:
    TagValuesPoolService.GetLastUpdateTimestamp() = DateTime.MinValue
    HistorianIngestHostedService polling loop → waited forever → 0 DB writes
```

### PLC Path (Working — for comparison)

```
PLC Device (Modbus/Rockwell/etc.)
         │
         ▼
PlcGatewayService  (BackgroundService)
  • Owns its PLC driver connections directly
  • Calls driver.ReadAll() on timer
         │
         ▼
PlcHistorianIngestService  (NO intermediary)
  • Receives PlcTagValue list directly from PlcGatewayService callback
  • Applies deadband/interval check
  • Calls own COPY SQL directly:
      COPY historian_raw.historian_timeseries (...) FROM STDIN BINARY
  • Logs: [PLC HISTORIAN] Wrote 10 records via COPY in 1ms  ✓
```

**Key difference**: PLC historian has NO intermediary service.
OPC historian had `DataLoggingService` + `TagValuesPoolService` as a two-layer intermediary — both of which could silently fail.

---

## 1. Root Cause (Confirmed by Code Trace)

### The Bug
`HistorianIngestHostedService` (OPC → DB pipeline) was reading from **`TagValuesPoolService`**, which is only populated by **`DataLoggingService`**.

`DataLoggingService` has a hard startup guard:
```csharp
// DataLoggingService.cs ~line 172
var decryptedProgId = _configService.GetDecryptedProgId();
if (string.IsNullOrEmpty(decryptedProgId))
{
    await Task.Delay(retryDelay, stoppingToken);
    continue;   // ← pool never populated, historian gets zero data
}
```

It also creates its **own separate OPC connection** (independent of the main `OpcDaService` connection that `OpcAutoConnectService` manages).

### Why PLC Works But OPC Does Not
| | OPC Historian | PLC Historian |
|---|---|---|
| Service | `HistorianIngestHostedService` | `PlcHistorianIngestService` |
| Data source | `TagValuesPoolService` ← `DataLoggingService` | Direct PLC driver read |
| Single point of failure | ✅ YES — `DataLoggingService` must connect | ❌ No intermediary |
| DB writer | `DbWriterService.WriteBatchAsync` (COPY) | Own COPY in `PlcHistorianIngestService` |

### Confirmed in Log
```
2026-05-23 01:54:19.388 [Information] Data Logging Service started
# ← That's it. No "Creating dedicated OPC connection", no "TagPool updated"
# DataLoggingService looped forever on: if (string.IsNullOrEmpty(decryptedProgId)) continue;
```

The main OPC connection **was** established (log shows `OPC_CONNECT Connection established | server=Matrikon.OPC.Simulation.1`) but `DataLoggingService` never populated the pool — so historian had nothing to write.

---

## 2. The Fix

**Remove `DataLoggingService` from the historian write path entirely.**

`HistorianIngestHostedService` should inject `OpcDaService` directly and call `ReadAllTagValues()` — exactly the same approach `PlcHistorianIngestService` uses for PLC data.

### Change Summary (single file)

**File**: `Services/HistorianIngest/Services/HistorianIngestHostedService.cs`

| | Before (broken) | After (fix) |
|---|---|---|
| Constructor param | `TagValuesPoolService tagPool` | `OpcDaService opcDaService` |
| Field | `private readonly TagValuesPoolService _tagPool` | `private readonly OpcDaService _opcDaService` |
| Data read in polling loop | `_tagPool.GetTagValues(mappedTagIds)` | `_opcDaService.ReadAllTagValues()` then filter by `tag_master` |
| Pool timestamp guard | `if (poolTimestamp == DateTime.MinValue) continue` | Removed — no longer needed |
| Source label written to DB | `"OPC_Pool"` | `"OPC"` |

**No other files change.** `Program.cs` DI auto-resolves `OpcDaService` (already registered as singleton at line 96).

### New Architecture After Fix

```
OPC Server (Matrikon.OPC.Simulation.1)
         │
         │  [Connection A — Main, only connection for historian]
         ▼
OpcDaService (singleton)
  • Managed by OpcAutoConnectService
  • Polls tags via OpcServerConnection at 1000ms
  • ReadAllTagValues() → returns live snapshot
         │
         ├──────────────────────────────────────────────────────────┐
         │                                                          │
         ▼                                                          ▼
HistorianIngestHostedService                          DataLoggingService
  PrecisePollingLoopAsync():                           [PARQUET ONLY — independent]
  var allOpcValues =                                   • Still has its own OPC connection
      _opcDaService.ReadAllTagValues()  ← DIRECT       • Still writes Parquet files
  filter by tag_master enabled mappings                • Still updates TagValuesPoolService
  → ProcessTagValueAsync() per tag                     • DataLoggingService failure does NOT
  → RateControllerService (deadband/interval)            affect historian anymore
  → BatcherService
  → DbWriterService.WriteBatchAsync()
  → historian_raw.historian_timeseries  ✓
         │
         ▼
TagValuesPoolService  (still exists, for HMI only)
  • Updated by DataLoggingService (unchanged)
  • Read by OpcController → /api/opc/values → HMI dashboard
  • NO LONGER read by historian
```

---

## 3. What Is NOT Changed

- `DataLoggingService` is untouched — it continues to write Parquet files
- `TagValuesPoolService` is untouched — HMI API still reads from it
- `DbWriterService` is untouched — same COPY pipeline
- `RateControllerService` is untouched — deadband/interval logic unchanged
- `SpoolManagerService` is untouched
- `PlcHistorianIngestService` is untouched

---

## 4. Status of Code Change

> ✅ **APPROVED AND READY TO BUILD**
>
> `HistorianIngestHostedService.cs` edited: `TagValuesPoolService` → `OpcDaService` (direct read).
> `historian_admin.events` and `historian_admin.spool_applied` tables **created in `Automation_DB`** (May 23, 2026).
> Project has **NOT been rebuilt or deployed yet** — `build.bat` run is the next step.
>
> `PLC_HISTORIAN_INGEST_CHANGES.md` updated to reflect OPC pipeline change.

---

## 5. Deployment Steps (after approval)

1. `build.bat` (self-contained x86 publish to `bin\Release\net8.0\publish\`)
2. Kill running `OpcDaWebBrowser.exe`
3. Start new exe, redirect output to `C:\Temp\opc_out3.log`
4. Wait 30 seconds
5. Verify in log: `OPC historian polling: N/M tags matched from OPC`
6. Verify in DB:
   ```sql
   SELECT sample_source, COUNT(*), MAX(time)
   FROM historian_raw.historian_timeseries
   WHERE time > NOW() - INTERVAL '2 minutes'
   GROUP BY sample_source;
   -- Expected: both 'PLC' and 'OPC' rows with recent timestamps
   ```

---

## 6. Risk Assessment

| Risk | Severity | Mitigation |
|---|---|---|
| OpcDaService not connected at startup | Low | `ReadAllTagValues()` returns empty list → polling loop logs warning and retries next cycle |
| Multiple historian service instances reading OpcDaService simultaneously | Low | `ReadAllTagValues()` is thread-safe (reads from ConcurrentDictionary snapshot per connection) |
| DataLoggingService pool no longer updated (HMI impact) | None | `DataLoggingService` still updates `TagValuesPoolService` independently via its own OPC connection. HMI reads from pool — unchanged |
| Spool files from old runs replaying | None | Already cleared 9,849 stale files from May 18. New spool dir is empty |

---

## 7. Outstanding Issues (immediate — fix in next sessions)

| # | Issue | Impact | Priority | Status |
|---|-------|--------|----------|--------|
| 1 | `historian_admin.events` table missing | Noisy logs — `LogEventAsync` fire-and-forget failures | High | ✅ FIXED — created May 23, 2026 |
| 2 | `historian_admin.spool_applied` table missing | Spool idempotency check fails silently | High | ✅ FIXED — created May 23, 2026 |
| 3 | Flask dual-write (`_persist_mqtt_samples()` in `app.py`) | Duplicate/inconsistent writes to DB | High | ❌ Remove after OPC writes confirmed in DB |
| 4 | Extra OPC connection in `DataLoggingService` | Two OPC connections to same server — wastes resources, violates one-truth-source rule | Medium | ❌ Long-term: migrate HMI + analytics to `OpcDaService`, then remove DataLoggingService OPC conn |
| 5 | No stale-tag detection | Tag stops updating → quality stays `"G"` forever, misleads operators | Medium | ❌ Add: if tag not updated > `StaleTagThresholdSeconds` → quality = `"U"` |
| 6 | No hard spool disk limit | Disk can fill during long DB outage — crash risk | Medium | ❌ Add `Spool.MaxSpoolSizeMB` + drop-oldest enforcement in `SpoolManagerService` |
| 7 | Timescale hypertable not verified | If `historian_timeseries` is not a hypertable, performance degrades at scale | High | ❌ Verify before data volume grows |
| 8 | Flask HMI (port 6001) not running | HMI inaccessible | Low | ❌ Start as per restart guide |

---

## 8. Long-Term Roadmap (from Architecture Decisions — May 2026)

> Full decisions recorded in `.github/copilot-instructions.md` → **Long-Term Architecture Decisions** section.
> This section is a checklist view only.

### ✅ What Is Good Now (Post-Fix)
- OPC acquisition fully separated from historian — `DataLoggingService` failure no longer kills DB writes
- Direct snapshot read via `OpcDaService.ReadAllTagValues()` — no hidden intermediary
- Fewer hidden dependencies — architecture now mirrors PLC flow
- One failure in logging/parquet path no longer blocks historian writes
- `historian_admin.events` + `historian_admin.spool_applied` tables created

---

### Phase 1 — Immediate (this session)
- [ ] Build + deploy fix from Section 2
- [ ] Verify OPC writes in DB (`sample_source = 'OPC'`)
- [x] ~~Create `historian_admin.events` table~~ ✅ Done
- [x] ~~Create `historian_admin.spool_applied` table~~ ✅ Done

### Phase 2 — Short Term (next 1–2 sessions)
- [ ] **Remove Flask dual-write** (`_persist_mqtt_samples()` in `WEB_HMI_MFA/HMI/app.py`) — prevents duplicate/inconsistent writes
- [ ] **Verify Timescale hypertable** — `SELECT * FROM timescaledb_information.hypertables` → confirm `historian_timeseries` is listed before data volume grows
- [ ] Add config validation at startup (DB tables exist, `tag_master` has enabled rows, spool dir writable)
- [ ] Add hard max spool disk size (`Spool.MaxSpoolSizeMB` in `appsettings.json`) + drop-oldest enforcement in `SpoolManagerService`
- [ ] Add spool replay throttling (`Spool.ReplayBatchSize`, `Spool.ReplayIntervalMs` config keys)
- [ ] **Add stale-tag detection**: tag not updated for `StaleTagThresholdSeconds` (default 30s) → quality = `"U"` automatically

### Phase 3 — Medium Term
- [ ] Watchdog for all polling loops — heartbeat timestamp per source, 15s timeout → Error log + restart attempt
- [ ] Per-source metrics: writes/sec, skipped/sec, COPY duration, queue depth, spool count, DB latency
- [ ] Health dashboard endpoint (`/historian/dashboard`) — all sources + DB status + spool state in real time
- [ ] Source isolation: wrap each polling loop iteration in `try/catch` — one source failure cannot propagate
- [ ] Replace string quality codes (`"G"/"B"/"U"`) with internal `TagQuality` enum

### Phase 4 — Long Term (architectural refactor)
> **Most important future direction: OPC + PLC → one unified historian pipeline**

- [ ] **Unify OPC + PLC into one historian pipeline**: both produce `RawSample` → shared `BatcherService` + `DbWriterService`
  - Today: PLC has its own COPY, OPC has its own batcher/writer — two separate pipelines
  - Target: one pipeline, per-source adapters, one shared rate controller + DB writer
- [ ] **`OpcDaService` as sole OPC truth source** for ALL consumers (HMI, historian, analytics)
  - Remove `DataLoggingService` OPC connection entirely once analytics are migrated off it
  - One OPC connection feeds HMI + historian + analytics — no duplication
- [ ] Latest-value cache enforcement: no consumer holds unbounded raw sample lists in RAM
- [ ] Per-source circuit breaker isolation confirmed in unified engine

---

## 9. Fixes Applied This Session (May 23, 2026)

### Fix 1 — DB Save Error: `updated_at` column does not exist
- **File**: `Services/PlcGateway/Controllers/PlcController.cs` line ~1676
- **Problem**: SQL UPDATE on `historian_meta.tag_master` had `updated_at = NOW()` — that column does not exist → every "Save" button on the PLC Tag Config UI failed with error `X 42703`
- **Fix**: Removed `updated_at = NOW()` from the UPDATE statement
- **Status**: ✅ Fixed + built + deployed

### Fix 2 — UI Minimum Interval Validation
- **File**: `wwwroot/historian/plc-tag-config.html`
- **Problem**: Input field had `min="100"` — user could set interval to 100ms causing excessive DB writes
- **Fix**:
  - Changed `min="100" step="100"` → `min="1000" step="1000"` on the HTML input
  - Added JS clamp in `saveTag()` and `saveTagSilent()`: if value < 1000 → reset to 1000 + show warning toast
- **Status**: ✅ Fixed. Copy HTML to `bin\x86\Release\net8.0\win-x86\wwwroot\historian\` after build

### Fix 3 — OPC Tags from DB Not Subscribed (Triangle Waves, Bucket Brigade missing)
- **File**: `Services/HistorianIngest/Services/HistorianIngestHostedService.cs`
- **Problem**: Tags like `Triangle Waves.Int1`, `Bucket Brigade.Real8` were in `historian_meta.tag_master` (enabled=true, server_progid=Matrikon.OPC.Simulation.1) but were NEVER subscribed in OpcDaService → never returned by `ReadAllTagValues()` → never written to DB
- **Root cause**: The subscription attempt at startup was before OPC connected, and the polling loop retry was trying ALL 260 tags (including PLC tags like `TRANSFORMER_LV_VOLTAGE_KV`) against the OPC server, causing failures that were partially swallowed
- **Fix**:
  - Filter by `mapping.ServerProgId` matching an actual OPC connection's `ServerProgID` — skip PLC tags
  - Use `connectionId`-specific `AddTagToMonitor(connectionId, tagId, displayName)` instead of the generic overload
  - Both startup path and polling loop retry path fixed
  - If OPC not connected at startup → log "will subscribe in polling loop" and skip (no throw)
- **Status**: ✅ Fixed + built + deployed. Triangle Waves + Bucket Brigade confirmed in batcher log

### Fix 4 — Wrong Exe Being Started (Critical Discovery)
- **Problem**: `dotnet build -c Release -p:Platform=x86` outputs to `bin\x86\Release\net8.0\win-x86\` NOT `bin\Release\net8.0\win-x86\`
- **Result**: Every restart was starting the OLD stale exe — new code changes were never running
- **Discovery**: Build output line shows: `OpcDaWebBrowser -> ...\bin\x86\Release\net8.0\win-x86\OpcDaWebBrowser.dll`
- **Fix**: Always start from `bin\x86\Release\net8.0\win-x86\OpcDaWebBrowser.exe`
- **Config copy needed**: `logging-config.json` and `appsettings.json` must be copied from `bin\Release\net8.0\win-x86\` to `bin\x86\Release\net8.0\win-x86\` (done once on May 23)
- **Status**: ✅ Resolved. See QUICK REFERENCE at top of this doc

### Fix 6 — Disable HMI Dual-Write of Tag Values to historian_timeseries
- **Problem**: `WEB_HMI_MFA/HMI/app.py` was calling `_persist_mqtt_samples()` inside `on_mqtt_message()` (line 526), inserting every tag value into `historian_raw.historian_timeseries` with `sample_source='MQTT'`. This duplicated every OPC and PLC row already written by the C# historian.
- **Fix**: Commented out the single call at line 526. The function definition `_persist_mqtt_samples()` is kept intact (commented header) for reference.
- **DB writes KEPT untouched in app.py / controllers**:
  - `alarm_controller.py` → `historian_raw.alarm_audit_trail` (alarm ACK, state changes)
  - `report_controller.py` → `historian_meta.report_gen_log`
  - `predictive_alarm_controller.py` → `historian_analytics.tag_alarm_config`
  - All `latest_tag_values` in-memory cache updates
  - All SocketIO alarm/event emits
- **Verify after Flask restart**:
  ```sql
  SELECT sample_source, COUNT(*), MAX(time)
  FROM historian_raw.historian_timeseries
  WHERE time > NOW() - INTERVAL '5 minutes'
  GROUP BY sample_source;
  -- Expected: OPC + PLC only. No MQTT rows.
  ```
- **Status**: ✅ Applied

---

### Fix 5 — Cannot Overwrite Running Exe (Windows Lock)
- **Problem**: `dotnet build` says "Build succeeded 0 errors" but exe timestamp never updates — because the old exe was still running and Windows locks it
- **Rule**: **ALWAYS kill the process BEFORE building**, not after
- **Correct sequence**: Kill → Build → Start (see QUICK REFERENCE above)
- **Status**: ✅ Documented

---

## 10. Current Working State (as of May 23, 2026 ~03:55 AM)

| Component | Status | Details |
|-----------|--------|---------|
| OPC Connection | ✅ Connected | Matrikon.OPC.Simulation.1 @ localhost, groups=5 |
| OPC → DB (Random tags) | ✅ Writing | Random.Real8, Random.Int8 every 5s |
| OPC → DB (Wave tags) | ✅ Writing | Triangle Waves.*, Bucket Brigade.* auto-subscribed from DB mapping |
| PLC → DB | ✅ Writing | Rockwel_PLC_001, 128 tags, COPY in ~2ms |
| DB-Writer | ✅ SUCCESS | Multiple batches confirmed |
| Spool | ✅ Empty | D:\HistorianSpool — 0 files |
| MQTT (OPC) | ✅ Connected | OpcMqttPublisherService publishing to broker 127.0.0.1:1883 |
| MQTT (PLC) | ✅ Connected | MultiProtocolPublisherService publishing |
| Single-instance guard | ✅ Active | Mutex prevents two OpcDaWebBrowser instances |
| UI Save error (X 42703) | ✅ Fixed | updated_at removed from SQL |
| Min interval 1000ms | ✅ Fixed | HTML + JS validation |
| Flask HMI (6001) | ❌ Not running | Start manually if needed |
