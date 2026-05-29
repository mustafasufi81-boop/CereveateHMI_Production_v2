# ALARM CLEAR BUG — Root Cause Analysis & Fix Plan

**Date:** 2026-05-28  
**Severity:** CRITICAL — ISA-18.2 Violation  
**Status:** IN PROGRESS

---

## THE BUG (What You See)

In the alarm history, you see this sequence for `VYAN1101F` with value **6.49 / SP 5.00**:

```
07:11:13  CLEARED    6.49 / 5.00   ← WRONG! Value is still HIGH!
07:11:12  UNACK      6.49 / 5.00   ← New alarm immediately raised again
07:11:07  ACK        6.49 / 5.00
07:10:56  CLEARED    6.49 / 5.00   ← WRONG again!
07:10:54  CLEARED    6.49 / 5.00   ← WRONG again!
07:10:51  ACK        6.49 / 5.00
```

**The alarm keeps getting CLEARED even though the live value (6.49) is still ABOVE the setpoint (5.00).**  
This creates phantom CLEARED rows and immediately a new UNACK row — an infinite loop.

---

## ROOT CAUSE (Why It Happens)

There are **TWO separate paths** that can auto-clear an alarm. My previous fix only blocked Path 1.

### Path 1 — Manual Clear button (FIXED ✅)
Operator clicks Clear → Flask → `AlarmsController.Clear` → `ClearAsync()`  
→ **My fix added live-value check here. This path is now blocked.**

### Path 2 — ACK of an RTN_UNACK alarm (NOT YET FIXED ❌)
This is the path causing the screenshot above:

```
Step 1: value = 6.49  → evaluator sees value > 5.0 → raises ACTIVE_UNACK
Step 2: value dips to 4.98 for ONE poll tick (500ms) → evaluator calls MarkRtnAsync()
        → state becomes RTN_UNACK
        (NOTE: the stored raised_value stays 6.49 from Step 1 — that's why history shows 6.49)
Step 3: Operator clicks ACK
        → AcknowledgeAsync() sees RTN_UNACK state
        → ISA-18.2 rule: RTN_UNACK + ACK = CLEARED  ← auto-clears here, NO live value check
        → Deletes row from alarm_active, writes ALARM_CLEARED to historian_events
Step 4: value bounces back to 6.49 → evaluator raises ACTIVE_UNACK again immediately
Step 5: GOTO Step 2
```

The `6.49 / 5.00` shown in CLEARED rows is the **raised_value stored at raise-time (Step 1)**, not the live value at clear time. The system thinks the alarm is resolved because it briefly saw the value dip, but the value recovered instantly.

### Why does value dip briefly?
- Signal noise / measurement jitter
- `AlarmDeadband = 0` in `tag_master` → zero hysteresis → any tiny dip below 5.0 triggers RTN
- The evaluation cycle runs every 500ms — one bad reading causes RTN_UNACK

---

## THE CORRECT FIX

### Fix A — Add deadband to tag_master (MOST IMPORTANT)
The `alarm_deadband` column in `historian_meta.tag_master` controls how far below the setpoint the value must go before RTN is declared. Currently it is **0** for VYAN tags.

**Set a proper deadband**, e.g. 5% of setpoint:
```sql
UPDATE historian_meta.tag_master
SET alarm_deadband = 0.25   -- 5% of SP=5.0 → value must reach 4.75 before RTN
WHERE tag_id LIKE 'VYAN%';
```

This alone will stop the jitter-induced RTN. Value must genuinely reach 4.75 (not just 4.99) before the alarm is considered returned to normal.

### Fix B — Live-value check in AcknowledgeAsync before auto-clear (CODE FIX)
In `AlarmStateManager.AcknowledgeAsync`, when `isRtn = true` (RTN_UNACK → auto-CLEAR path):

**Before writing CLEARED to DB**, check the live value from `TagValuesPoolService`:
- If live value is **still violating the setpoint** → do NOT auto-clear
- Instead → treat as `ACTIVE_ACK` (the value bounced back; alarm is active again)
- Log: `"AcknowledgeAsync: RTN_UNACK bounce-back detected for {Key} — treating as ACTIVE_ACK instead of CLEARED"`

This prevents phantom clears even if deadband is not set properly.

### Fix C — Add minimum RTN hold time (DEFENSE IN DEPTH)
Before calling `MarkRtnAsync`, the evaluator should confirm the value has been below the setpoint for **N consecutive cycles** (e.g. 3 cycles = 1.5 seconds) before declaring RTN_UNACK. This prevents a single noisy reading from triggering RTN.

---

## FILES TO CHANGE

| File | Change |
|------|--------|
| `historian_meta.tag_master` (DB) | Set `alarm_deadband` to a non-zero value for VYAN tags |
| `AlarmStateManager.cs` — `AcknowledgeAsync()` | Fix B: check live value before auto-clear on RTN_UNACK path |
| `AlarmEvaluationService.cs` — `EvaluateTagAsync()` | Fix C: require N consecutive readings below SP before MarkRtnAsync |

---

## TASK LIST

- [ ] **TASK 1** — Check current `alarm_deadband` values in `historian_meta.tag_master` for VYAN tags
- [ ] **TASK 2** — Set `alarm_deadband` to 5% of setpoint for all oscillating tags (SQL UPDATE)
- [ ] **TASK 3** — In `AcknowledgeAsync`: add live-value check before auto-clear on RTN_UNACK path
- [ ] **TASK 4** — In `AlarmEvaluationService`: add RTN confirmation counter (min 2 consecutive readings below SP+deadband)
- [ ] **TASK 5** — Rebuild C# with `--self-contained true`, restart, verify no more phantom CLEARs

---

## HOW TO VERIFY THE FIX IS WORKING

After fix is deployed, in DB run:
```sql
-- Should show NO rows where CLEARED rows have live value still above setpoint
-- (Check history for VYAN1101F — should not see CLEARED followed by UNACK within 1 second)
SELECT time, tag_id, event_type, alarm_state, alarm_actual_value, alarm_setpoint
FROM historian_raw.historian_events
WHERE tag_id = 'VYAN1101F'
  AND alarm_state IN ('CLEARED','ACTIVE_UNACK')
ORDER BY time DESC
LIMIT 30;
```

**Expected after fix:** CLEARED rows only appear when alarm_actual_value < alarm_setpoint (value genuinely returned to normal). No CLEARED → ACTIVE_UNACK pairs within 1-2 seconds of each other.
