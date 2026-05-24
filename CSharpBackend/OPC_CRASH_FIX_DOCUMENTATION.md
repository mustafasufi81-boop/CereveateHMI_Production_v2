# OPC DA Backend Crash Fix Documentation
**Date**: May 20, 2026  
**System**: Cereveate OPC DA / Analytics Platform  
**Affected Binary**: `OpcDaWebBrowser.exe` (C# .NET 8, win-x86 self-contained)

---

## Crash Summary

The OPC DA backend (`OpcDaWebBrowser.exe`) was repeatedly crashing with:

```
Exception code: 0xc0000374  (STATUS_HEAP_CORRUPTION)
Faulting module: ntdll.dll
```

Windows Event Log ID **1000** was generated on every crash. The process would die silently within ~2 minutes of startup whenever the Rockwell PLC at `192.168.1.11` was offline or unreachable.

---

## Root Causes Found (Two Separate Bugs)

---

### Bug #1 — Double-Free in `OpcServerConnection.cs` `AddItem()` ✅ FIXED

**File**: `Services/OpcServerConnection.cs`  
**Method**: `AddItem()` (around line 696)

#### What Was Wrong

The COM-allocated buffers `resultsPtr` and `errorsPtr` returned by `ItemMgt.AddItems()` were freed **twice**:

```csharp
// First free — always executed
Marshal.FreeCoTaskMem(resultsPtr);
Marshal.FreeCoTaskMem(errorsPtr);

if (errors[0] != 0)
{
    // ... logging ...
    Marshal.FreeCoTaskMem(resultsPtr);  // ← SECOND FREE = HEAP CORRUPTION
    Marshal.FreeCoTaskMem(errorsPtr);   // ← SECOND FREE = HEAP CORRUPTION
    return;
}
```

Every time a tag was **rejected** by the OPC server (e.g., `OPC_E_INVALIDITEMID 0xC0040008`), both pointers were freed twice. On reconnect, 300+ tags were being rejected in rapid succession (all mapped to wrong `server_progid`), causing hundreds of double-frees in milliseconds → `ntdll.dll` heap corruption detector triggered → process killed.

#### The Fix Applied

```csharp
// Read result and errors BEFORE freeing the COM-allocated buffers
OPCITEMRESULT result = default;
int[] errors = new int[1];
try
{
    result = (OPCITEMRESULT)Marshal.PtrToStructure(resultsPtr, typeof(OPCITEMRESULT))!;
    Marshal.Copy(errorsPtr, errors, 0, 1);
}
finally
{
    // Free exactly ONCE — guaranteed by finally block
    if (resultsPtr != IntPtr.Zero) Marshal.FreeCoTaskMem(resultsPtr);
    if (errorsPtr != IntPtr.Zero) Marshal.FreeCoTaskMem(errorsPtr);
}

if (errors[0] != 0)
{
    // ... logging ...
    return;  // Buffers already freed above — do NOT free again
}
```

**Key changes**:
- Wrapped frees in a `finally` block → guaranteed exactly one free regardless of code path
- Null-checked pointers before freeing
- Removed the duplicate `FreeCoTaskMem` calls from the error branch

---

### Bug #2 — Missing `DestroyStructure` in `ReadGroupValues()` ✅ FIXED

**File**: `Services/OpcServerConnection.cs`  
**Method**: `ReadGroupValues()` (around line 958)

#### What Was Wrong

The `OPCITEMSTATE` struct contains an embedded `VARIANT` field (`vDataValue`). When an OPC read returns string (`BSTR`) or array (`SAFEARRAY`) values, the `VARIANT` holds an inner COM-allocated pointer. Calling `FreeCoTaskMem` on the outer buffer **does not** release these inner allocations:

```csharp
// OLD CODE — WRONG:
Marshal.FreeCoTaskMem(valuesPtr);  // Leaks BSTR/SAFEARRAY inside each VARIANT
```

Over time (especially during PLC offline when reads cycle rapidly) this leak degrades into heap corruption.

#### The Fix Applied

```csharp
// Correct: destroy each OPCITEMSTATE element first (invokes VariantClear internally)
for (int i = 0; i < count; i++)
{
    IntPtr itemPtr = IntPtr.Add(valuesPtr, i * opcItemStateSize);
    try { Marshal.DestroyStructure(itemPtr, typeof(OPCITEMSTATE)); }
    catch { /* ignore — best effort cleanup */ }
}
Marshal.FreeCoTaskMem(valuesPtr);  // Now safe — inner allocations already cleared
```

`Marshal.DestroyStructure` calls the equivalent of `VariantClear` on the embedded `VARIANT`, properly releasing any `BSTR` or `SAFEARRAY` allocated by the OPC server before the outer buffer is freed.

---

### Bug #3 — PLC Offline Flooding Logs and Accelerating Crashes ✅ FIXED

**Files**: `Services/PlcGateway/Drivers/RockwellDriver.cs`, `Services/PlcGateway/Services/PlcWorker.cs`

#### What Was Wrong

When the Rockwell PLC at `192.168.1.11` was offline:
- `RockwellDriver` attempted to read all 128 tags per poll cycle
- Each failed tag logged a `WARNING` → 128 warnings × every second = **~6 million log lines/day** (232 MB log files observed)
- `PlcWorker` logged `"not connected, attempting connection..."` every second indefinitely
- The constant error-path COM calls during offline state stressed the heap, accelerating Bug #1 and #2

#### Fixes Applied

**`RockwellDriver.cs`**:
- **Ping-first probe**: Before reading all 128 tags, attempt single-tag read as a connectivity probe
- If probe fails → apply **exponential backoff** (30s → 60s → 120s cap), abort immediately, skip all 128 reads
- On success → reset backoff, clear known-bad-tag set
- **Per-tag fault suppression**: First failure on a tag → log `WARNING` once, add to `_knownBadTags`; subsequent failures are **silent**; on recovery → log `INFO` once, remove from set

**`PlcWorker.cs`**:
- **Log-once pattern**: First PLC offline detection logs `"PLC OFFLINE"` once; no repeat logs until reconnect
- **Worker-level backoff**: Respects the same backoff window, sleeps in 5s slices (so it remains cancellable)
- On successful reconnect → resets backoff, logs `"back ONLINE"` once

---

## Files Modified

| File | Change |
|------|--------|
| `Services/OpcServerConnection.cs` | Fixed double-free in `AddItem()` (Bug #1) + `DestroyStructure` before `FreeCoTaskMem` in `ReadGroupValues()` (Bug #2) |
| `Services/PlcGateway/Drivers/RockwellDriver.cs` | Ping-first probe, exponential backoff, per-tag fault suppression (Bug #3) |
| `Services/PlcGateway/Services/PlcWorker.cs` | Log-once + worker backoff (Bug #3) |
| `START_OPC_WITH_WATCHDOG.bat` | NEW — external watchdog that auto-restarts exe on non-zero exit |

---

## Build & Deploy Commands

```powershell
$ROOT = "c:\MQTT_Implemented_OPC\Copied_MQTT\BACKUP_BEFORE_HISTORICAL_20251117_225747 - Copy_backup_20251206"

# Build + publish (run from project root)
cd $ROOT
dotnet publish -c Release -r win-x86 --self-contained true -o "bin\Release\net8.0\win-x86"

# Restart OPC backend
Stop-Process -Name "OpcDaWebBrowser" -Force -ErrorAction SilentlyContinue
Start-Sleep 2
Start-Process -FilePath "$ROOT\bin\Release\net8.0\win-x86\OpcDaWebBrowser.exe" `
              -WorkingDirectory "$ROOT\bin\Release\net8.0\win-x86" `
              -WindowStyle Minimized

# Verify running
Start-Sleep 8
netstat -ano | findstr ":5001" | findstr LISTENING
```

---

## Verification After Fix

After applying all three fixes and publishing:

- ✅ Port 5001 stays **LISTENING** (no more crashes after 2 minutes)
- ✅ Historian data flowing: `Triangle Waves.UInt2` writing to `historian_raw.historian_timeseries`
- ✅ Log file stays small (no more 232 MB/day flood)
- ✅ Windows Event Log ID 1000 no longer appearing

---

## Remaining Known Issues (Not Crash-Related)

| Issue | Description | Fix |
|-------|-------------|-----|
| 300+ tags skipped each cycle | `historian_meta.tag_master` rows have `server_progid = 'Rockwel_PLC_001'` / `'PLC_SENSORS_01'` / `'PLC_GATEWAY_01'` but active server is `'Matrikon.OPC.Simulation.1'` | Run SQL: `UPDATE historian_meta.tag_master SET server_progid='Matrikon.OPC.Simulation.1' WHERE server_progid IN ('Rockwel_PLC_001','PLC_SENSORS_01','PLC_GATEWAY_01');` |
| `historian_admin.spool_applied` missing | Spool idempotency check fails on startup | `CREATE TABLE historian_admin.spool_applied (file_hash TEXT PRIMARY KEY, applied_at TIMESTAMPTZ DEFAULT now());` |
| `TEST_TAG_001` rejected | Tag exists in `tag_master` but not in Matrikon OPC address space | Delete or correct the tag entry |

---

## Quick Diagnostic Commands

```powershell
# Check if OPC backend is alive
netstat -ano | findstr ":5001" | findstr LISTENING

# Check for new crashes in Windows Event Log
Get-WinEvent -LogName Application -MaxEvents 10 | Where-Object { $_.Id -eq 1000 } | Select-Object TimeCreated, Message

# Tail live log
Get-Content "D:\OpcLogs\AppLogs\app-$(Get-Date -Format 'yyyyMMdd').log" -Tail 20 -Wait

# Check historian is writing
# (should show recent timestamps)
# psql -U postgres -d historian -c "SELECT tag_id, MAX(ts) FROM historian_raw.historian_timeseries GROUP BY tag_id ORDER BY 2 DESC LIMIT 10;"
```
