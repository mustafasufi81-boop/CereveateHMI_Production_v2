# OPC DA Auto-Connect Fix — Technical Analysis
**Date:** 2026-05-25  
**Status:** ✅ FIXED — tagCount: 27 confirmed on startup

---

## The Problem

After C# backend (`OpcDaWebBrowser.exe`) starts:

```
GET /api/opc/status → {"connected": false, "serverName": "Not connected", "tagCount": 0}
GET /api/opc/values → {"count": 0, "tags": []}
```

**But** — opening the OPC Browser page in the React UI and clicking **CONNECT** manually connects to `Matrikon.OPC.Simulation.1` and immediately shows 113 tags with live values.

So the OPC server IS running and IS reachable. The problem is auto-connect on startup.

---

## What Should Happen

`OpcDaWebBrowser.exe` has a `OpcAutoConnectService` (a .NET `BackgroundService`) that runs in the background. Its job:

1. Reads `logging-config.json` → finds `ServerProgId = "Matrikon.OPC.Simulation.1"`
2. Calls `_opcDaService.Connect(progId, host, clsid)` to establish the connection
3. Calls `_opcDaService.AddTagToMonitor(tag, displayName)` for each of the 27 tags in `MonitoredTags`
4. Every 15 seconds checks the connection is still alive, reconnects if dropped

This was designed so the system works headlessly — no browser needed to start data flowing.

---

## Root Cause: COM STA Threading + Orphaned Apartment

### Background: OPC DA uses COM (Component Object Model)

OPC DA is a Windows technology built on COM. COM objects have **apartment** rules:

| Apartment Type | Thread Type | Rule |
|---|---|---|
| **STA** (Single-Threaded Apartment) | One specific thread owns the object | ALL calls to that COM object MUST come from the same STA thread that CREATED it |
| **MTA** (Multi-Threaded Apartment) | Thread pool threads | COM objects created here can be called from any MTA thread |

The most important COM rule — more important than "use STA" — is:

> **The apartment that CREATES the COM object must remain alive and continue processing messages.**

### What `OpcAutoConnectService` was originally doing

```csharp
// ORIGINAL — MTA thread pool = COM STA violation → silent failure
await Task.Run(() => _opcDaService.Connect(progId, host, clsid), stoppingToken);
```

`Task.Run()` runs on the **.NET thread pool** which is **MTA**. This violated OPC DA apartment rules entirely.

### The partial fix applied (⚠️ UNSAFE — orphaned apartment)

```csharp
// PARTIAL FIX — correct apartment type, but thread DIES after Connect()
var staThread = new Thread(() =>
{
    _opcDaService.Connect(progId, host, clsid);
    tcs.SetResult(true);
});
staThread.SetApartmentState(ApartmentState.STA);
staThread.Start();
await tcs.Task;
// ← STA thread exits here. COM apartment is DESTROYED. Objects are ORPHANED.
```

**Result after partial fix:**
```
GET /api/opc/status → {"connected": true, "serverName": "Matrikon.OPC.Simulation.1", "tagCount": 0}
```

`connected: true` is a **false positive**. The .NET boolean flag is set, but the COM objects are dead.

### Why the partial fix creates orphaned COM objects

```
1. Connect() runs on STA thread
   → IOPCServer, IOPCItemMgt, IOPCSyncIO created in that STA apartment
2. STA thread exits → apartment is DESTROYED
3. COM proxies/groups/interfaces are now disconnected
4. Later MTA calls from async background loop hit dead apartment
   → silent failure, RPC_E_DISCONNECTED, or CO_E_OBJNOTCONNECTED
5. tagCount = 0, no hard exceptions, system appears "connected"
```

This is **classic orphaned STA COM ownership**. This is the confirmed root cause.

### Why the browser UI (SignalR) works

The SignalR hub does `Connect → AddTag → Read` **all synchronously within the same call stack** on the same thread, before returning. COM objects never outlive their creating thread because the whole operation completes before any thread switch. The background service breaks this because `Connect()` and `AddTagToMonitor()` run on different threads separated by async continuations.

---

## Agreed Architecture: Persistent OPC STA Dispatcher

### The only correct solution — Option A

**One permanent dedicated STA thread with a message pump and a work queue.** This is the standard architecture for every professional OPC DA .NET integration. Not a workaround — the correct design.

```
ASP.NET / SignalR / BackgroundServices
            ↓
     async wrappers (Task<T>)
            ↓
     OpcStaDispatcher  ←  work queue (BlockingCollection<Action>)
            ↓
     Single Dedicated STA Thread
     - permanent (never exits)
     - message pump (Application.Run / MSG loop)
     - owns ALL COM objects for the process lifetime
            ↓
     IOPCServer  |  IOPCItemMgt  |  IOPCSyncIO  |  IOPCBrowseServerAddressSpace
```

### Non-negotiable rules

1. **The STA thread never exits.** It runs for the entire process lifetime.
2. **The STA thread runs a message pump.** Without `Application.Run()` or equivalent, OPC DA callbacks deadlock and connection point events never fire.
3. **No raw COM interfaces leak outside the dispatcher.** Callers receive only DTOs, snapshots, and `Task<T>` results.
4. **Every COM call goes through the dispatcher** — Connect, AddTag, Read, Write, Browse, Disconnect. No exceptions.
5. **No mixing of polling thread / callback thread / COM owner thread.** One owner, all calls serialized.

### Options ruled out

| Option | Verdict | Reason |
|--------|---------|--------|
| **Transient STA threads** | ❌ Dangerous | Orphaned apartment — current broken state |
| **Task.Run (MTA)** | ❌ Wrong | MTA violation — original broken state |
| **B — IGlobalInterfaceTable** | ❌ Rejected | Overengineering. Does not solve message pump. Debugging nightmare. |
| **C — Full STA from Program.cs** | ❌ Rejected | ASP.NET Core is MTA. Bridge complexity extreme. |
| **D — HTTP trigger script** | ❌ Not a fix | Breaks on reconnect/restart/async continuation. Race-condition prone. |

---

## Implementation Plan

### Phase 1 — Registry Verification ⏳ PENDING

Confirm COM activation model before writing code:

```
reg query "HKCR\Matrikon.OPC.Simulation.1\CLSID"
→ note CLSID value
→ reg query "HKCR\CLSID\{<clsid>}"
→ look for: LocalServer32  vs  InprocServer32
```

| Result | Meaning | Impact |
|--------|---------|--------|
| **LocalServer32** | EXE COM server, out-of-process | COM auto-marshals cross-thread calls, but message pump + apartment lifetime STILL required for callbacks |
| **InprocServer32** | DLL COM server, in-process | Strict STA rules — dispatcher is mandatory, no exceptions |

Expected: `LocalServer32` (most OPC DA servers are EXE-based).

---

### Phase 2 — Thread/Apartment/HRESULT Logging ⏳ PENDING

Add diagnostics everywhere COM is touched. Get evidence before writing the dispatcher.

**Thread + apartment log pattern:**
```csharp
_logger.LogInformation(
    "[OPC] {Operation} | Thread={ThreadId} | Apartment={Apartment}",
    operationName,
    Thread.CurrentThread.ManagedThreadId,
    Thread.CurrentThread.GetApartmentState());
```

**COM exception log pattern:**
```csharp
catch (COMException ex)
{
    _logger.LogError(
        ex,
        "[OPC COM ERROR] HRESULT=0x{HResult:X8} | Thread={ThreadId} | Apartment={Apartment}",
        ex.ErrorCode,
        Thread.CurrentThread.ManagedThreadId,
        Thread.CurrentThread.GetApartmentState());
}
```

**Locations to instrument:**

| Location | File |
|----------|------|
| `Connect()` entry/exit | `OpcServerConnection.cs` |
| `AddTag()` entry/exit | `OpcServerConnection.cs` |
| `ReadTagValues()` entry/exit | `OpcServerConnection.cs` |
| `AddTagToMonitor()` | `OpcDaService.cs` |
| `ReadAllTagValues()` | `OpcDaService.cs` |
| SignalR `ConnectToServer()` | `OpcDaHub.cs` |

This will expose: `RPC_E_WRONG_THREAD`, `RPC_E_DISCONNECTED`, `CO_E_OBJNOTCONNECTED`, `E_FAIL`.

---

### Phase 3 — Build `OpcStaDispatcher` (minimal, isolated) ⏳ PENDING

Build as a standalone component only. Do NOT refactor the broader service layer yet.

```csharp
public sealed class OpcStaDispatcher : IDisposable
{
    private readonly BlockingCollection<Action> _queue = new();
    private readonly Thread _thread;

    public OpcStaDispatcher()
    {
        _thread = new Thread(Run);
        _thread.SetApartmentState(ApartmentState.STA);
        _thread.IsBackground = false; // must NOT be background — owns COM objects
        _thread.Name = "OPC-STA-Dispatcher";
        _thread.Start();
    }

    private void Run()
    {
        // Message pump keeps apartment alive for OPC DA callbacks
        System.Windows.Forms.Application.Idle += (_, _) =>
        {
            while (_queue.TryTake(out var action))
                action();
        };
        System.Windows.Forms.Application.Run(); // blocks — STA apartment alive for process lifetime
    }

    public Task<T> InvokeAsync<T>(Func<T> func)
    {
        var tcs = new TaskCompletionSource<T>(TaskCreationOptions.RunContinuationsAsynchronously);
        _queue.Add(() =>
        {
            try { tcs.SetResult(func()); }
            catch (Exception ex) { tcs.SetException(ex); }
        });
        return tcs.Task;
    }

    public Task InvokeAsync(Action action) =>
        InvokeAsync<bool>(() => { action(); return true; });

    public void Dispose() =>
        System.Windows.Forms.Application.ExitThread();
}
```

---

### Phase 4 — Route Connect / AddTag / Read Through Dispatcher ⏳ PENDING

Validate by routing ONLY the three core operations through the dispatcher first, without changing the rest of the architecture:

```csharp
await _dispatcher.InvokeAsync(() => _opcServerConnection.Connect(progId, host, clsid));
await _dispatcher.InvokeAsync(() => _opcServerConnection.AddTag(groupName, tagId, displayName));
var values = await _dispatcher.InvokeAsync(() => _opcServerConnection.ReadTagValues());
```

Success criteria: `tagCount > 0`, values updating, no COM errors in logs.

---

### Phase 5 — Full Architecture Audit ⏳ PENDING

After Phase 4 is validated:

- Audit all locations where COM interfaces could be cached as fields and accessed from wrong threads:
  ```csharp
  // DANGEROUS PATTERN — COM interface stored as field
  private IOPCItemMgt _itemMgt;  // → accessed from MTA = instant violation
  ```
- Verify `Marshal.IsComObject(obj)` for `IOPCServer`, `IOPCItemMgt`, `IOPCSyncIO`
- Ensure no raw COM interfaces are exposed to ASP.NET layer
- Refactor SignalR hub + background service to use dispatcher wrappers exclusively

---

## Files Status

| File | Change | Status |
|------|--------|--------|
| `CSharpBackend/Services/OpcStaDispatcher.cs` | Created — permanent STA thread + work queue | ✅ Done |
| `CSharpBackend/Services/OpcAutoConnectService.cs` | Removed transient STA thread — now calls `OpcDaService.Connect()` directly | ✅ Done |
| `CSharpBackend/Services/OpcDaService.cs` | Injected `OpcStaDispatcher`; `Connect()` and `AddTagToMonitor()` route through dispatcher | ✅ Done |
| `CSharpBackend/Services/OpcServerConnection.cs` | Added `dispatcher` param; polling loop routes `PollOnce()` through dispatcher | ✅ Done |
| `CSharpBackend/Program.cs` | Registered `OpcStaDispatcher` as singleton before `OpcDaService` | ✅ Done |

## Confirmed Results

```
[OPC DISPATCHER] Permanent STA thread started | Thread=11 | Apartment=STA
Connect()  → Thread=11 | Apartment=STA  ✅
AddItems() → Thread=11 | Apartment=STA  ✅  (all 26 tags)
GET /api/opc/status → {"connected": true, "tagCount": 27}  ✅
```

## Remaining Known Issue — Wrong Tag-to-Server Mapping in `tag_master`

Several PLC tag names (`TURBINE_SPEED_RPM`, `VIB_LP_FRONT_X_UM`, `HZ1103A`, etc.) are mapped to
`Matrikon.OPC.Simulation.1` in `tag_master`. These are real PLC tags that do not exist in the
Matrikon simulator. They produce `HRESULT=0xC0040008` (`OPC_E_UNKNOWNITEMID`) on the
`DataLoggingService` connection. This is a **data configuration issue** — the tags need to be
remapped to the correct PLC OPC server in `tag_master`, not a code bug.
