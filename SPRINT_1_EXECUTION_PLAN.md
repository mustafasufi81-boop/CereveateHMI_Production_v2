# SPRINT 1 — EXECUTION PLAN
## PLC GATEWAY CRITICAL STABILIZATION

**Status:** READY TO START  
**Date:** May 26, 2026  
**Priority:** CRITICAL PATH TO PRODUCTION

---

## 🚨 MANDATORY EXECUTION RULES

1. ✅ **ONE CHANGE ONLY** per implementation cycle
2. ✅ **BUILD** after EVERY change
3. ✅ **TEST** after EVERY build  
4. ✅ **VERIFY** logs after EVERY test
5. ✅ **COMMIT** only after verification
6. ✅ **NEVER** combine multiple fixes
7. ✅ **NEVER** refactor during stabilization
8. ✅ **NEVER** "improve architecture" during bug fixing
9. ✅ **EVERY** change must be reversible
10. ✅ **IF ANY REGRESSION** → STOP and rollback immediately

---

## 📋 IMPLEMENTATION CYCLE (MANDATORY FOR EVERY TASK)

```
STEP 1  → Read target code completely
STEP 2  → Understand exact issue
STEP 3  → Implement MINIMAL fix only
STEP 4  → Build solution (dotnet build)
STEP 5  → Run application
STEP 6  → Test target functionality
STEP 7  → Check logs for regressions
STEP 8  → Verify CPU/memory stable
STEP 9  → Commit with clean message
STEP 10 → Move to next task
```

**DO NOT SKIP ANY STEP.**

---

## 🎯 SPRINT 1 GOAL

**Make system operationally safe before physical PLC connection.**

**DO NOT:**
- ❌ Implement event bus
- ❌ Optimize architecture  
- ❌ Refactor code

**ONLY:**
- ✅ Fix blocking operational issues

---

## 📍 CURRENT SYSTEM STATE

### Working ✅
- PlcGatewayManager isolates workers correctly
- PlcWorker isolation architecture is sound
- PlcDriverFactory creates drivers correctly
- PlcConfigLoaderService loads from DB and appsettings.json
- PlcTagValuesPoolService shared cache works
- PlcSampleBufferService MQTT integration works

### Broken ❌
- **S1-13:** IP address mapping — `/api/plc/connections` shows empty IP/protocol
- **S1-1a:** No formal state machine validation (inline assignments, Faulted never triggered)
- **S1-2:** No circuit breaker (infinite reconnect storms possible)
- **S1-9:** No hard timeout wrapper (native DLL hang risk)
- **S1-14:** `consecutiveFailures` counter broken (not incremented in ConnectWithRetryAsync)
- **S1-3/4:** No age_ms computation or Stale quality
- **S1-7:** No PLC REST fallback
- **S1-10:** No watchdog timer
- **S1-5:** `/api/plc/diagnostics` missing
- **S1-11:** No MQTT LWT
- **S1-8:** Plaintext credentials in config

---

## 🔥 TASK S1-13 — FIX IP ADDRESS MAPPING

**PRIORITY:** #1 — START HERE  
**RISK:** CRITICAL  
**FILES:** `PlcController.cs` (line 328-380)

### Issue Analysis

**Symptom:**
```json
GET /api/plc/connections returns:
{
  "ipAddress": "",
  "protocol": "Unknown", 
  "tagCount": 0
}
```

**Root Cause:**
The `/api/plc/connections` endpoint merges data from 3 sources but has incorrect fallback priority:

```csharp
// Line 362-363 — WRONG PRIORITY ORDER
protocol = hasSaved ? saved!.Protocol : (hasPool ? "Rockwell" : "Unknown"),
ipAddress = hasSaved ? saved!.IpAddress : (hasPool ? "192.168.0.20" : ""),
```

**Problem:**
1. Prioritizes `savedConfigs` (persisted JSON file) first
2. Falls back to `poolStatus` (database tag_master) second  
3. Completely ignores `runtimeStatus` (actual PlcWorker status)

**But:**
- `PlcWorker.GetStatus()` correctly returns `_config.IpAddress` and `_config.Port` (PlcWorker.cs line 505-506)
- `PlcGatewayManager.GetAllStatus()` returns correct worker status with IP/protocol
- Controller just doesn't use it!

### Solution

**Change priority order to:**
```
1. runtimeStatus (actual worker running right now)
2. poolStatus (database source)
3. savedConfigs (persisted file)
```

**Minimal fix location:** `PlcController.cs` lines 360-365

### Implementation Steps

**STEP 1:** Read `PlcController.cs` lines 320-390 completely

**STEP 2:** Locate exact bug at lines 360-365

**STEP 3:** Change ONLY the priority order:

```csharp
// BEFORE (WRONG):
protocol = hasSaved ? saved!.Protocol : (hasPool ? "Rockwell" : "Unknown"),
ipAddress = hasSaved ? saved!.IpAddress : (hasPool ? "192.168.0.20" : ""),
port = hasSaved ? saved!.Port : (hasPool ? 44818 : 0),

// AFTER (CORRECT):
protocol = hasRuntime ? runtime!.Protocol : (hasSaved ? saved!.Protocol : (hasPool ? "Rockwell" : "Unknown")),
ipAddress = hasRuntime ? runtime!.IpAddress : (hasSaved ? saved!.IpAddress : (hasPool ? "192.168.0.20" : "")),
port = hasRuntime ? runtime!.Port : (hasSaved ? saved!.Port : (hasPool ? 44818 : 0)),
```

**STEP 4:** Build solution
```powershell
cd d:\CereveateHMI_Production\CSharpBackend
dotnet build
```

**STEP 5:** Run application
```powershell
dotnet run
```

**STEP 6:** Test endpoint
```powershell
curl http://localhost:5000/api/plc/connections
```

**STEP 7:** Verify logs show correct IP/protocol being used

**STEP 8:** Check memory/CPU stable

**STEP 9:** Commit
```bash
git add CSharpBackend/Services/PlcGateway/Controllers/PlcController.cs
git commit -m "fix(S1-13): prioritize runtime worker status in /api/plc/connections endpoint

- Changed fallback order: runtime → saved → pool (was: saved → pool → runtime)
- PlcWorker.GetStatus() already returns correct IP/port from _config
- Fixes empty ipAddress/protocol in API response
- No logic changes, only data source priority correction"
```

**STEP 10:** Proceed to S1-1a

### Success Criteria

✅ `/api/plc/connections` shows:
- `ipAddress` populated correctly
- `protocol` shows actual protocol (not "Unknown")
- `port` correct
- No null/empty config values

✅ Logs show worker attempting connection to correct IP

✅ No new warnings/errors introduced

✅ No regressions in MQTT, historian, or pool updates

---

## 🔥 TASK S1-1a — FORMAL STATE MACHINE

**PRIORITY:** #2  
**RISK:** CRITICAL  
**FILES:** `PlcWorker.cs`

### Issue Analysis

**Current Problem:**
```csharp
// PlcWorker.cs — inline state assignment, no validation
_state = PlcWorkerState.Running;  // Line 283
_state = PlcWorkerState.Connecting;  // Line 307
_state = PlcWorkerState.Disconnected;  // Line 346
```

**Issues:**
1. No validation — invalid transitions silently accepted
2. `Faulted` state defined but NEVER triggered
3. No logging of state changes
4. `HandlePollFailure()` doesn't transition to `Faulted`

**OPC Gold Standard Pattern:**
```csharp
private void TransitionTo(DispatcherState next, string reason)
{
    if (!IsValidTransition(_state, next)) {
        _logger.LogError("[STATE] Invalid transition {From} → {To} — REJECTED", _state, next);
        return;
    }
    
    var prev = _state;
    _state = next;
    _logger.LogInformation("[STATE] {From} → {To}: {Reason}", prev, next, reason);
}
```

### Solution

**Add to PlcWorker.cs:**

1. `TransitionTo()` method with validation
2. `IsValidTransition()` validation rules
3. Replace all inline `_state = X` with `TransitionTo(X, reason)`

**Valid Transitions:**
```
Created       → Starting
Starting      → Connecting, Stopped (on cancel)
Connecting    → Running, Disconnected, Faulted
Running       → Disconnected, Stopping, Faulted
Disconnected  → Connecting, Stopping, Faulted
Faulted       → Stopping (manual intervention only)
Stopping      → Stopped
Stopped       → Starting (restart)
```

### Implementation Steps

**STEP 1:** Read `PlcWorker.cs` completely (609 lines)

**STEP 2:** Locate all inline state assignments:
- Line 168: `_state = PlcWorkerState.Starting`
- Line 283: `_state = PlcWorkerState.Running`
- Line 307: `_state = PlcWorkerState.Connecting`
- Line 346: `_state = PlcWorkerState.Disconnected`
- Line 189: `_state = PlcWorkerState.Stopping`
- Line 202: `_state = PlcWorkerState.Stopped`

**STEP 3:** Add state machine methods AFTER line 555 (after `GetStatus()`, before `DisposeAsync()`):

```csharp
// ═══════════════════════════════════════════════════════════════════
// STATE MACHINE (OPC Gold Standard Pattern)
// ═══════════════════════════════════════════════════════════════════

/// <summary>
/// Validated state transition with logging
/// </summary>
private void TransitionTo(PlcWorkerState next, string reason)
{
    if (!IsValidTransition(_state, next))
    {
        _logger.LogError(
            "[WORKER {WorkerId}] Invalid state transition {From} → {To} — REJECTED: {Reason}",
            WorkerId, _state, next, reason);
        return;
    }

    var prev = _state;
    _state = next;
    
    _logger.LogInformation(
        "[WORKER {WorkerId}] State: {From} → {To} ({Reason})",
        WorkerId, prev, next, reason);
}

/// <summary>
/// Validate state transition rules
/// </summary>
private bool IsValidTransition(PlcWorkerState from, PlcWorkerState to)
{
    return (from, to) switch
    {
        // Created can only start
        (PlcWorkerState.Created, PlcWorkerState.Starting) => true,
        
        // Starting can connect or be stopped
        (PlcWorkerState.Starting, PlcWorkerState.Connecting) => true,
        (PlcWorkerState.Starting, PlcWorkerState.Stopped) => true,
        
        // Connecting outcomes
        (PlcWorkerState.Connecting, PlcWorkerState.Running) => true,
        (PlcWorkerState.Connecting, PlcWorkerState.Disconnected) => true,
        (PlcWorkerState.Connecting, PlcWorkerState.Faulted) => true,
        
        // Running can disconnect or stop
        (PlcWorkerState.Running, PlcWorkerState.Disconnected) => true,
        (PlcWorkerState.Running, PlcWorkerState.Stopping) => true,
        (PlcWorkerState.Running, PlcWorkerState.Faulted) => true,
        
        // Disconnected can retry or stop
        (PlcWorkerState.Disconnected, PlcWorkerState.Connecting) => true,
        (PlcWorkerState.Disconnected, PlcWorkerState.Stopping) => true,
        (PlcWorkerState.Disconnected, PlcWorkerState.Faulted) => true,
        
        // Faulted requires manual intervention (stop only)
        (PlcWorkerState.Faulted, PlcWorkerState.Stopping) => true,
        
        // Stopping always succeeds
        (PlcWorkerState.Stopping, PlcWorkerState.Stopped) => true,
        
        // Stopped can restart
        (PlcWorkerState.Stopped, PlcWorkerState.Starting) => true,
        
        // All other transitions invalid
        _ => false
    };
}
```

**STEP 4:** Replace inline assignments (6 locations):

```csharp
// Line 168 — BEFORE:
_state = PlcWorkerState.Starting;

// Line 168 — AFTER:
TransitionTo(PlcWorkerState.Starting, "StartAsync called");

// Line 283 — BEFORE:
_state = PlcWorkerState.Running;

// Line 283 — AFTER:
TransitionTo(PlcWorkerState.Running, "First successful read");

// Line 307 — BEFORE:
_state = PlcWorkerState.Connecting;

// Line 307 — AFTER:
TransitionTo(PlcWorkerState.Connecting, "Driver not connected, attempting connection");

// Line 346 — BEFORE:
_state = PlcWorkerState.Disconnected;

// Line 346 — AFTER:
TransitionTo(PlcWorkerState.Disconnected, $"Read failed: {readResult.ErrorMessage}");

// Line 189 — BEFORE:
_state = PlcWorkerState.Stopping;

// Line 189 — AFTER:
TransitionTo(PlcWorkerState.Stopping, "StopAsync called");

// Line 202 — BEFORE:
_state = PlcWorkerState.Stopped;

// Line 202 — AFTER:
TransitionTo(PlcWorkerState.Stopped, "Polling loop exited");
```

**STEP 5:** Modify `HandlePollFailure()` to transition to `Faulted` after threshold (around line 448):

```csharp
// ADD after line 457 (after marking shared pool disconnected):
if (_consecutiveFailures >= 5)
{
    TransitionTo(PlcWorkerState.Faulted, 
        $"Too many consecutive failures ({_consecutiveFailures})");
}
```

**STEP 6:** Build solution
```powershell
dotnet build
```

**STEP 7:** Run application and test

**STEP 8:** Verify logs show state transitions clearly:
```
[WORKER PLCWorker_Rockwel_PLC_001_...] State: Created → Starting (StartAsync called)
[WORKER PLCWorker_Rockwel_PLC_001_...] State: Starting → Connecting (Driver not connected, attempting connection)
[WORKER PLCWorker_Rockwel_PLC_001_...] State: Connecting → Running (First successful read)
```

**STEP 9:** Test invalid transition rejection:
- Manually test reconnect behavior
- Verify no deadlocks
- Check that `Faulted` state triggers after 5 failures

**STEP 10:** Commit
```bash
git add CSharpBackend/Services/PlcGateway/Services/PlcWorker.cs
git commit -m "feat(S1-1a): add formal state machine validation to PlcWorker

- Implemented TransitionTo() with validation (OPC pattern)
- Added IsValidTransition() with complete rule set
- Replaced 6 inline state assignments with validated transitions
- HandlePollFailure() now transitions to Faulted after 5 failures
- Invalid transitions logged and rejected
- No polling loop changes, only state management formalization"
```

### Success Criteria

✅ All state transitions logged clearly  
✅ Invalid transitions rejected and logged  
✅ `Faulted` state triggered after 5 consecutive failures  
✅ Reconnect behavior unchanged  
✅ No deadlocks introduced  
✅ No infinite loops

---

## 🔥 TASK S1-2 — CIRCUIT BREAKER + COOLDOWN

**PRIORITY:** #3  
**RISK:** HIGH  
**FILES:** `PlcWorker.cs`

### Issue Analysis

**Current Problem:**
- After 5 failures, worker immediately retries connection
- No exponential backoff or cooldown
- Can create infinite reconnect storm
- Logs flood with connection attempts

**Need:**
- Circuit breaker pattern
- Cooldown period after entering `Faulted` state
- Exponential backoff

### Solution

**Add cooldown escalation:**
```
First fault:   5 minutes cooldown
Second fault:  10 minutes cooldown
Third fault:   20 minutes cooldown
Max:           60 minutes cooldown
```

**Implementation:**
1. Track fault count (separate from `_consecutiveFailures`)
2. Calculate cooldown duration exponentially
3. Block connection attempts during cooldown
4. Reset fault count on successful connection

### Implementation Steps

**STEP 1:** Add fields to `PlcWorker` class (after line 79):

```csharp
// Circuit breaker
private int _faultCount = 0;
private DateTime _cooldownUntil = DateTime.MinValue;
private const int MinCooldownSeconds = 300;  // 5 minutes
private const int MaxCooldownSeconds = 3600; // 60 minutes
```

**STEP 2:** Add cooldown check in `PollingLoopAsync()` (after line 307, before connect attempt):

```csharp
// Check cooldown period
if (DateTime.UtcNow < _cooldownUntil)
{
    var remaining = (_cooldownUntil - DateTime.UtcNow).TotalSeconds;
    if (_consecutiveFailures == 1) // Log only first time
    {
        _logger.LogWarning(
            "[WORKER {WorkerId}] In cooldown period, {Remaining:F0}s remaining",
            WorkerId, remaining);
    }
    
    await Task.Delay(5000, ct); // Check every 5s
    continue;
}
```

**STEP 3:** Modify `HandlePollFailure()` to set cooldown (around line 457):

```csharp
if (_consecutiveFailures >= 5 && _state != PlcWorkerState.Faulted)
{
    _faultCount++;
    
    // Exponential cooldown: 5min, 10min, 20min, ..., max 60min
    var cooldownSeconds = Math.Min(
        MinCooldownSeconds * (int)Math.Pow(2, _faultCount - 1),
        MaxCooldownSeconds);
    
    _cooldownUntil = DateTime.UtcNow.AddSeconds(cooldownSeconds);
    
    TransitionTo(PlcWorkerState.Faulted, 
        $"Too many consecutive failures ({_consecutiveFailures}), cooldown for {cooldownSeconds}s");
}
```

**STEP 4:** Reset fault count on successful connection (around line 283):

```csharp
// After successful read (around line 340):
if (_consecutiveFailures > 0 && _state == PlcWorkerState.Disconnected)
{
    _logger.LogInformation(
        "[WORKER {WorkerId}] Recovered from fault state, resetting circuit breaker",
        WorkerId);
    _faultCount = 0;
    _cooldownUntil = DateTime.MinValue;
}
```

**STEP 5:** Add cooldown info to `GetStatus()` (around line 505):

```csharp
// Add new properties to PlcWorkerStatus class first (line 592):
public int FaultCount { get; set; }
public DateTime CooldownUntil { get; set; }
public int CooldownRemainingSeconds { get; set; }

// Then populate in GetStatus():
FaultCount = _faultCount,
CooldownUntil = _cooldownUntil,
CooldownRemainingSeconds = _cooldownUntil > DateTime.UtcNow 
    ? (int)(_cooldownUntil - DateTime.UtcNow).TotalSeconds 
    : 0,
```

**STEP 6:** Build and test

**STEP 7:** Simulate fault:
- Set invalid PLC IP
- Verify enters `Faulted` after 5 failures
- Verify cooldown period respected
- Verify retries resume after cooldown
- Verify successful connection resets circuit breaker

**STEP 8:** Commit

### Success Criteria

✅ Enters `Faulted` state after 5 consecutive failures  
✅ Cooldown period respected (no connection attempts during cooldown)  
✅ Exponential backoff: 5min → 10min → 20min  
✅ Circuit breaker resets on successful connection  
✅ No reconnect storms  
✅ Diagnostics show cooldown remaining time

---

## 🔥 REMAINING TASKS (Brief Summaries)

### TASK S1-9 — HARD DRIVER TIMEOUT
**Priority:** #4  
**Fix:** Wrap `ReadAllTagsAsync()` with `Task.WhenAny(readTask, Task.Delay(timeout))`  
**Location:** `PlcWorker.cs` line ~340  
**Risk:** Native DLL hang can freeze entire polling loop

### TASK S1-14 — FIX consecutiveFailures COUNTER
**Priority:** #5  
**Fix:** Increment `_consecutiveFailures` inside `ConnectWithRetryAsync()` (line ~420-445)  
**Current Bug:** Connection failures don't increment counter, only read failures do

### TASK S1-3 + S1-4 — age_ms + STALE QUALITY
**Priority:** #6  
**Fix:** Add `age_ms` computation in `PlcTagValue`, add `PlcTagQuality.Stale` enum  
**Rule:** > 10s old = STALE quality

### TASK S1-7 — PLC REST FALLBACK
**Priority:** #7  
**Fix:** Add `GET /api/plc/values` to Python `_rest_fallback_poller()`  
**Current:** Only OPC has REST fallback, PLC tags disappear when MQTT dies

### TASK S1-10 — WATCHDOG
**Priority:** #8  
**Fix:** Track scan duration, warn if > 2× expected interval  
**Location:** `PlcWorker.cs` polling loop

### TASK S1-5 — /api/plc/diagnostics ENDPOINT
**Priority:** #9  
**Fix:** Add detailed diagnostics endpoint exposing state, watchdog, cooldown, etc.

### TASK S1-11 — MQTT LWT
**Priority:** #10  
**Fix:** Add Last Will Testament messages for instant offline detection

### TASK S1-8 — REMOVE PLAINTEXT CREDENTIALS
**Priority:** Last before deployment  
**Fix:** Move DB/MQTT passwords to environment variables

---

## 🧪 MANDATORY SOAK TEST (AFTER ALL S1 TASKS)

**Duration:** 30-60 minutes minimum

**Test Scenarios:**
1. PLC disconnect/reconnect (unplug network)
2. MQTT restart (`docker restart mosquitto`)
3. Backend restart
4. Python HMI restart
5. Network interruption (disable/enable adapter)
6. Stale tag handling (freeze worker)
7. Circuit breaker trigger (invalid IP)
8. Cooldown escalation (multiple faults)

**RULE:** DO NOT CHANGE CODE during soak test.

**Only:** Observe, log, document failures.

---

## ✅ SPRINT 1 COMPLETION CRITERIA

**Functional:**
- [ ] `/api/plc/connections` shows correct IP/protocol
- [ ] State machine validates all transitions
- [ ] `Faulted` state triggers correctly
- [ ] Circuit breaker prevents reconnect storms
- [ ] Hard timeout protects from native DLL hangs
- [ ] `consecutiveFailures` counter accurate
- [ ] Stale tags marked with age_ms and Stale quality
- [ ] REST fallback works for PLC tags
- [ ] Watchdog detects scan degradation
- [ ] Diagnostics endpoint exposes all metrics
- [ ] MQTT LWT provides instant offline detection
- [ ] No plaintext credentials in repo

**Stability:**
- [ ] No reconnect storms
- [ ] No memory leaks
- [ ] No thread leaks
- [ ] No infinite loops
- [ ] No deadlocks
- [ ] CPU stable under load
- [ ] Logs clean (no spam)

**Only after ALL criteria pass → Proceed to Sprint 2.**

---

## 📝 COMMIT MESSAGE TEMPLATE

```
<type>(S1-<number>): <short summary>

<detailed explanation>

- Bullet point 1
- Bullet point 2

Fixes: S1-<number>
```

**Types:** `fix`, `feat`, `refactor`, `test`, `docs`

---

## 🚀 STARTING POINT

**BEGIN WITH:** TASK S1-13 (IP Address Mapping Fix)

**Why first:**
- Simplest fix (3-line change)
- Highest visibility (API returns correct data)
- Zero risk (just changes priority order)
- Validates build/test/commit workflow
- Builds confidence before complex changes

**Next:** S1-1a (State Machine) — more complex but well-defined

**Then:** S1-2 (Circuit Breaker) — builds on state machine

**Then:** Remaining tasks in priority order

---

## 📞 SUPPORT

**If stuck:**
1. STOP immediately
2. Document exact issue
3. Check logs
4. Rollback if needed
5. Request guidance before proceeding

**Never guess. Never improvise. Follow the plan.**

---

## 🎯 SUCCESS MANTRA

> "One change. Build. Test. Verify. Commit. Repeat."
> "Stability > Speed"
> "If it breaks, rollback immediately."

**LET'S BEGIN WITH S1-13.**
