# ALARM CLEAR BUG — Full Analysis & Fix Plan V2
**Date:** 2026-05-28  

---

## WHAT THE SCREENSHOT SHOWS

```
08:25:15  VYAN1101F  CLEARED   6.49/5.00  ← value STILL HIGH — should NEVER be cleared
08:25:13  VYAN1101F  UNACK     6.49/5.00  ← new alarm raised 2s after clear
08:25:03  VYAN1101F  ACK       6.49/5.00  ← operator ACK'd
07:11:13  VYAN1101F  CLEARED   6.49/5.00  ← same bug 1hr14m earlier
07:11:12  VYAN1101F  CLEARED   6.49/5.00
```

---

## ROOT CAUSE ANALYSIS — ALL PATHS

There are 3 paths that can produce a CLEARED row. ALL THREE must be blocked when value is still high.

### PATH 1: Manual Clear button  [FIXED ✅]
Operator clicks Clear → Flask → C# ClearAsync()
- Fix: ClearAsync now checks live value → blocks if still violating

### PATH 2: ACK of RTN_UNACK (bounce-back)  [PARTIALLY FIXED ⚠]
Value dips briefly → RTN_UNACK → operator ACKs → AcknowledgeAsync auto-clears
- Fix applied: bounce-back guard in AcknowledgeAsync checks live value
- BUT: The TagValuesPoolService only has OPC DA tags. VYAN tags may come from PlcTagValuesPool.
  If _tagPool returns empty (VYAN not in OPC pool), the guard silently skips → still clears.
  THIS IS WHY IT STILL HAPPENS.

### PATH 3: MarkRtnAsync called while value is still high  [NOT FIXED ❌]
The evaluation cycle itself calls MarkRtnAsync (transition to RTN_UNACK) based on a stale/noisy
single reading. Once in RTN_UNACK, the next ACK auto-clears (Path 2).
Root: MarkRtnAsync has no live-value double-check either.

---

## THE REAL PROBLEM WITH THE CURRENT BOUNCE-BACK FIX

```csharp
var liveEntries = _tagPool.GetTagValues(new[] { state.TagId });
```

`_tagPool` = `TagValuesPoolService` = OPC DA tags only.
VYAN tags live in `PlcTagValuesPoolService` (different service, different pool).
When VYAN tag is not found in OPC pool → `liveEntries` is empty → guard skips → auto-clear happens.

---

## THE COMPLETE FIX PLAN (5 changes, in order)

### CHANGE 1 — Fix the bounce-back guard to also check PlcTagValuesPool
**File:** `AlarmStateManager.cs` — `AcknowledgeAsync()`  
**What:** Also inject `PlcTagValuesPoolService` into AlarmStateManager.
Check BOTH pools: OPC pool first, then PLC pool if OPC returns nothing.
**Rule:** If live value found in EITHER pool and still violating → override isRtn=false.
If value NOT found in any pool (tag offline) → SAFE DEFAULT: do not auto-clear, treat as ACTIVE_ACK.

### CHANGE 2 — Same dual-pool check in ClearAsync
**File:** `AlarmStateManager.cs` — `ClearAsync()`  
**What:** Current check only uses OPC pool. Same bug — VYAN not found → guard skips.
Fix: check both pools. Not found → safe default = block clear.

### CHANGE 3 — MarkRtnAsync live-value double-check
**File:** `AlarmStateManager.cs` — `MarkRtnAsync()`  
**What:** Before writing RTN_UNACK to DB, re-read live value from both pools.
If value is STILL violating → reject the RTN transition, log warning, return false.
This cuts the bug at source — RTN_UNACK is never written if value is still high.

### CHANGE 4 — Alarm re-raise suppression during active clear sequence
**File:** `AlarmEvaluationService.cs` — `EvaluateTagAsync()`  
**What:** Add a short-lived in-memory "recently cleared" set (ConcurrentDictionary<alarmKey, DateTime>).
When ClearAsync or ACK→CLEARED completes, add alarmKey to this set with timestamp.
In EvaluateTagAsync: if alarmKey is in "recently cleared" set and less than 3 seconds old → skip raise.
This prevents the immediate re-raise that creates the confusing paired CLEARED+UNACK in history.
After 3s the key is removed → normal evaluation resumes.

### CHANGE 5 — Event ID deduplication guard
**File:** `AlarmStateManager.cs` — `RaiseAsync()`  
**What:** If the current `CurrentEventId` for an alarm_key is already set (alarm is live in memory),
do not re-raise. The evaluator already checks `isAlreadyActive` but a timing gap between
CLEARED (memory removed) and the next eval cycle can create a duplicate.
Add: after writing RAISE to DB, store the new event_id. Before any transition, verify
the event_id matches what is in alarm_active (DB cross-check on first transition after restart).

---

## TEST SCRIPT SCENARIOS TO VERIFY

Write `_test_alarm_clear_scenarios.py` that tests:

```
SCENARIO 1: Clear while value HIGH
  - Ensure VYAN1101F is in ACTIVE_ACK state
  - Attempt clear via API
  - Expected: HTTP 422, reason=VALUE_STILL_VIOLATING
  - Verify: No CLEARED row added to historian_events

SCENARIO 2: ACK while RTN_UNACK but value bounced back HIGH  
  - Manually SET alarm to RTN_UNACK in alarm_active
  - Ensure live value > setpoint
  - Attempt ACK via API
  - Expected: HTTP 200, new_state=ACTIVE_ACK (NOT CLEARED)
  - Verify: No CLEARED row, alarm still in alarm_active as ACTIVE_ACK

SCENARIO 3: Value genuinely returns to normal — clear should succeed
  - Ensure tag value is below setpoint (genuinely normal)
  - Alarm in ACTIVE_ACK state
  - Attempt clear via API
  - Expected: HTTP 200, new_state=CLEARED
  - Verify: CLEARED row in historian_events, row deleted from alarm_active

SCENARIO 4: No duplicate raise during clear window
  - Trigger a clear
  - Within 1 second, call raise for same alarm_key
  - Expected: raise is suppressed (recently cleared)
  - Verify: No ACTIVE_UNACK row appears within 3s of CLEARED row for same alarm_key

SCENARIO 5: Duplicate event_id — same alarm not reprocessed
  - Same occurrence_id should not produce two RAISE rows in historian_events
```

---

## IMPLEMENTATION ORDER

1. CHANGE 1 + 2 (fix dual-pool check) → rebuild → test SCENARIO 1 & 2
2. CHANGE 3 (MarkRtnAsync guard) → rebuild → test SCENARIO 2 again  
3. CHANGE 4 (re-raise suppression) → rebuild → test SCENARIO 4
4. Write test script → run all 5 scenarios
5. Monitor historian_events for 10 minutes → confirm no phantom CLEARED rows

---

## ACCEPTANCE CRITERIA

After all fixes:
- No CLEARED row in historian_events where alarm_actual_value > setpoint_value (for high alarms)
- No CLEARED row followed by ACTIVE_UNACK for the same tag within 3 seconds
- VYAN1101F with live value 6.49 / SP 5.00 cannot be cleared by any path
- Test script passes all 5 scenarios
