# Alarm System — Problem & Solution Proposal (for Approval)
**Date:** 2026-05-29
**Status:** PROPOSAL ONLY — no code changed. Awaiting approval.
**Scope:** PLC alarm path (OPC parked). Shared engine: `CSharpBackend/Services/AlarmEvaluation/`.
**Standard:** ISA-18.2 (Management of Alarm Systems for the Process Industries).

> Implementation order (as requested):
> **1) Priority Consistency → 2) Chatter Control → 3) Alarm Philosophy → 4) Duplicate Levels → 5) Lifecycle Review.**

---

## ITEM 1 — Priority Consistency  🔴 IMMEDIATE

### Problem
The same alarm occurrence shows **different priorities** at different lifecycle stages.
In the `PY1105B` history: every **RAISE** row shows `HIGH`, every **RTN** row shows `URGENT`.

**Root cause (verified in code):** `AlarmStateManager.cs` writes the correct priority only on RAISE.
On RTN, ACK and CLEAR it **hard-codes `severity=4, priority=4`**.

| Transition | File line(s) | Currently writes | Should write |
|------------|--------------|-------------------|--------------|
| RAISE | 229, 231, 279 | real `priority` ✅ | real priority |
| **RTN** | 415, 417 | `4` (hard-coded) ❌ | occurrence priority |
| **ACK** | 593, 598 | `4` (hard-coded) ❌ | occurrence priority |
| **CLEAR** | 848, 850 | `4` (hard-coded) ❌ | occurrence priority |

Frontend label map (`AlarmHistoryModal.tsx` L113): `[_, LOW, WARNING, HIGH, URGENT, CRITICAL]`.
PY1105B is priority **3 (HIGH)**; the hard-coded `4` renders as a false **URGENT**.

### ISA-18.2 basis
§5.2.4 / §18 — priority is a fixed **occurrence attribute**; every lifecycle record for one
occurrence must carry the same priority for correct sorting, KPIs, and audit.

### Solution
The occurrence's real priority is already in memory (`AlarmRuntimeState`) and is set at RAISE.
Replace the three hard-coded `4`s (severity + priority on RTN, ACK, CLEAR) with
`state.Priority` (the value carried by the runtime state for that occurrence).

- **Files:** `AlarmStateManager.cs` (3 methods: `MarkRtnAsync`, `AcknowledgeAsync`, `ClearAsync`).
- **Data already available:** yes — `AlarmRuntimeState` holds the raise-time priority; if a
  `Priority` field is not already stored we add it at RAISE (single assignment).
- **Effort:** XS. **Risk:** Low (value-only change, no flow change).
- **Verify:** new RTN/ACK/CLEAR rows show the same priority badge as their RAISE row.

---

## ITEM 2 — Stop Alarm Chattering / Flooding  🟠 BIGGEST OPERATIONAL WIN

### Problem
One oscillating tag (`PY1105B`, PV sweeping 0.14↔0.61) produced **14 events in ~2 minutes** and
would continue forever. This is a textbook **chattering alarm** (rapid active↔normal cycling) and
the #1 ISA-18.2 "bad actor."

**Why current controls don't stop it:**
- **On-delay** exists (`AlarmDelayTracker`) — gates *raising* only.
- **Exit deadband** exists (`EffectiveDeadband`, fixed 2026-05-29) — stops *jitter at a threshold*,
  but the PV here traverses the *entire* band, so any sane deadband is still fully crossed.
- **Off-delay** (settling time before RTN): **does NOT exist** ← the key missing control.
- **Chatter counter / auto-shelve:** does NOT exist.

### ISA-18.2 basis
§5.3.3 (delay timers & deadband), §16 (chattering/fleeting alarm management).

### Solution — two layers (recommend BOTH)

**Layer A — Off-delay (RTN settling time)** *(primary, simple, symmetric with on-delay)*
The value must remain in the normal range for **N seconds** continuously before RTN is declared.
Mirrors the existing on-delay. Implemented in `AlarmDelayTracker` (new `TryStartOrCheckRtn`) and
applied in `AlarmEvaluationService.EvaluateTagAsync` before calling `MarkRtnAsync`.
- New config: `AlarmEvaluation:RtnOffDelaySeconds` (proposed **default 5 s**), optionally
  overridable per-tag via a new `tag_master.alarm_offset_delay_s` column.

**Layer B — Chatter detection + auto-shelve** *(defense-in-depth for true oscillators)*
Count raise→RTN transitions per `alarm_key` in a rolling window. If it exceeds a threshold,
annunciate **once** as `CHATTERING` and **auto-shelve** for a cooldown (suppress re-annunciation),
then auto-unshelve when it stabilizes.
- New config (proposed defaults):
  `ChatterWindowSeconds = 60`, `ChatterCountThreshold = 5`, `ChatterShelveCooldownSeconds = 300`.
- Note: `AlarmRuntimeState` already has `ChatterCount` and a chatter-window field (scaffolding
  exists), so this builds on existing structure.

- **Files:** `AlarmDelayTracker.cs`, `AlarmEvaluationService.cs`, `AlarmEvaluationConfig.cs`
  (+ optional `tag_master` column + `AlarmSetpointCacheService`).
- **Effort:** M. **Risk:** Medium (changes RTN timing — must verify genuine RTNs still clear).

### ⚙️ Parameters needed from you
- Off-delay default seconds? (proposed **5 s**)
- Enable Layer B chatter auto-shelve? window/threshold/cooldown? (proposed **60 s / 5 / 300 s**)

---

## ITEM 3 — Alarm Philosophy: Latching vs Non-Latching  🟡

### Problem
Current behaviour is **latching by default**: after `ACTIVE_ACK`, when value returns to normal it
goes to `RTN_UNACK` and requires a **second acknowledgement** to clear.

### ISA-18.2 basis
§5.2 standard state model: an **acknowledged** alarm that returns to normal should transition to
**Normal automatically**. Manual-reset (latching) is a **per-alarm option** for safety-critical
points — not a blanket default.

### Solution — choose ONE site philosophy
- **Option A — Non-latching (ISA default, recommended):**
  `ACTIVE_ACK` + value returns → **auto-CLEAR** (row deleted). No second ACK.
  Change in `MarkRtnAsync`: if state is `ActiveAck` and value returned → CLEAR directly.
- **Option B — Latching (keep current):** require the second ACK.
- **Option C — Per-alarm flag (most flexible):** new `tag_master.latching` (default **false** =
  non-latching). Safety-critical tags set `latching=true`.

- **Files:** `AlarmStateManager.cs` (`MarkRtnAsync`), `AlarmEvaluationService` (RTN path),
  optionally `tag_master` + `AlarmSetpoint` + `AlarmSetpointCacheService` for Option C.
- **Effort:** S. **Risk:** Low.

### ⚙️ Decision needed: A, B, or C? (recommend **A** globally, or **C** with default non-latching)

---

## ITEM 4 — Prevent Duplicate Alarm Levels (H+HH / L+LL)  🟡

### Problem
On an up-sweep, `High` raises at 0.40, then `HighHigh` raises at 0.60 → operator sees **two**
active alarms for one excursion (and two RTNs on the way down).

**Why current suppression misses it:** `AlarmSuppressionEngine` suppresses a *new lower* raise only
while the higher level is *already* active. But `High` crosses **first** going up, so it's not
suppressed; when `HighHigh` later raises, the already-active `High` remains annunciated.

### ISA-18.2 basis
§5.3.4 (designed suppression) — annunciate only the **highest active** sub-alarm of a multi-level
point to reduce alarm count.

### Solution
When a higher level raises, **auto-RTN/suppress the lower level** of the same tag so only the
highest active level is presented. When the higher level clears and the condition still meets the
lower level, the lower re-annunciates (existing reflash logic handles this).
- **Files:** `AlarmEvaluationService.cs` (raise path), `AlarmSuppressionEngine.cs`.
- **Effort:** S. **Risk:** Medium (depends on site philosophy — some plants want both shown).

### ⚙️ Decision needed: suppress lower level when higher active? (recommend **Yes**)

---

## ITEM 5 — Review Alarm Lifecycle  ✅ VERIFICATION

### Target ideal sequence
`RAISE → ACK → RETURN-TO-NORMAL → CLEAR` — no repeated raises, no false clears,
no priority changes, no floods.

### Status against target
| Property | Current | After Items 1–4 |
|----------|---------|-----------------|
| No priority change mid-life | ❌ (Item 1) | ✅ |
| No alarm floods / chatter | ❌ (Item 2) | ✅ |
| Consistent latching philosophy | ⚠ blanket latching | ✅ (Item 3) |
| No duplicate H+HH clutter | ❌ (Item 4) | ✅ (if approved) |
| RTN fires correctly | ✅ (fixed 2026-05-29 deadband) | ✅ |
| Re-alarm on re-entry while RTN_UNACK | ✅ (fixed 2026-05-29) | ✅ |
| No false clears while value violating | ✅ (safety gates in place) | ✅ |

### Action
No new code — this item is the **end-to-end verification** after Items 1–4: run `PY1105B`
oscillation and confirm a clean lifecycle with consistent priority and no flood.

---

## Summary — Decision Sheet

| # | Item | ISA-18.2 | Effort | Risk | Needs your input |
|---|------|----------|--------|------|------------------|
| 1 | Priority consistency | §5.2.4, §18 | XS | Low | (none — approve) |
| 2 | Chatter / flood control | §5.3.3, §16 | M | Med | off-delay s; chatter on/off + params |
| 3 | Latching philosophy | §5.2 | S | Low | Option A / B / C |
| 4 | Duplicate level suppression | §5.3.4 | S | Med | Yes / No |
| 5 | Lifecycle verification | §5.2 | — | — | (verify after 1–4) |

### Proposed defaults (if you just say "go")
- **Item 1:** propagate real occurrence priority to RTN/ACK/CLEAR.
- **Item 2:** off-delay **5 s** + chatter auto-shelve (**60 s / 5 / 300 s**).
- **Item 3:** **Option C** — per-tag `latching` flag, default **false** (non-latching/ISA).
- **Item 4:** **Yes** — show only the highest active level per tag.

> ✅ **Awaiting your approval and the parameter choices above before any code change.**

---

# Implementation Log (live — updated as fixes land)

> Each entry: what changed, where, how it was verified. Build = `dotnet publish -c Release -r win-x86`
> for the backend; `npm run build` (in `HMI/apex-hmi`) for the frontend.

## ✅ FIX 0a — Deadband inversion (RTN never fired)
**Date:** 2026-05-29  **Status:** DONE & VERIFIED  **Layer:** C# backend
- **Problem:** blanket `alarmDeadband = 1.0` made the RTN exit threshold negative for
  small-setpoint tags (e.g. High sp=0.4 → exit at 0.4 − 1.0 = −0.6, unreachable). Diagnostics
  showed `rtnTransitions = 0` across 3 195 evaluation cycles.
- **Fix:** added `AlarmSetpoint.EffectiveDeadband(limit)` — clamps deadband to ≤ 50 % of `|limit|`
  so the RTN threshold can never invert. `AlarmEvaluationService.HasExitedAlarmZone` now uses it.
- **Files:** `AlarmSetpoint.cs`, `AlarmEvaluationService.cs`.
- **Verified:** `rtnTransitions` went 0 → 14 within minutes of restart.

## ✅ FIX 0b — Re-alarm blocked (raises stopped)
**Date:** 2026-05-29  **Status:** DONE & VERIFIED  **Layer:** C# backend
- **Problem:** `AlarmStateManager.RaiseAsync` returned early when the existing state was
  `RtnUnack`, so a tag that re-entered the alarm zone before someone ACK'd the prior RTN was
  stuck and produced no new RAISE events (192 missed raises for PY1105B).
- **Fix:** ISA-18.2 *reflash* — when state is `RtnUnack` and value re-enters the alarm zone,
  fall through and re-raise (`RtnUnack → ActiveUnack`).
- **File:** `AlarmStateManager.cs` (`RaiseAsync`).
- **Verified:** `alarmsRaised` went 0 → 192, PY1105B promoted back to `ACTIVE_UNACK`.

## ✅ FIX 1 — Priority consistency  (Proposal Item 1)
**Date:** 2026-05-29  **Status:** DONE & VERIFIED  **Layer:** C# backend
- **Problem:** RTN/ACK/CLEAR rows hard-coded `severity=4, priority=4`, rendering as a false
  **URGENT** even when the occurrence was priority 3 (`HIGH`).
- **Fix:**
  - Added `Priority` field to `AlarmRuntimeState`; set it at RAISE.
  - Replaced the three hard-coded `4`s in `AlarmStateManager` (`MarkRtnAsync`, `AcknowledgeAsync`,
    `ClearAsync`) with `state.Priority`.
  - `AlarmReconciliationService` now SELECTs `priority` from `alarm_active` and rehydrates it on
    both `RestoreActiveState` and `BulkMarkRtnAsync` restore paths so priority survives restart.
- **Files:** `AlarmRuntimeState.cs`, `AlarmStateManager.cs`, `AlarmReconciliationService.cs`.
- **Verified:** 60-event sweep — every tag + level shows a single consistent priority across
  RAISE/RTN/ACK/CLEAR (PY1105B = 3, PY1104 = 2, Random.Real4 = 1).

## ✅ FIX 2 — False "OPC REST FAIL | PLC REST FAIL" banner  (HMI bug, not a real outage)
**Date:** 2026-05-29  **Status:** DONE  **Layer:** React frontend only
- **Problem:** banner showed `OPC REST FAIL | PLC REST FAIL` even while MQTT was `LIVE`, trends
  were updating, and the C# backend was healthy (verified: C# `/api/plc/values` → 200, 128 tags,
  83 ms; `/api/opc/values` → 200, 27 tags, 16 ms).
- **Root cause:** the banner was bound **purely** to the REST poll's `opcFailed` / `plcFailed`
  flags (3 consecutive failures → sticky red). REST is only a *fallback* — its transient hiccups
  (e.g. brief 4.5 s `AbortSignal.timeout` on a busy page, IPv6/Happy-Eyeballs latency on
  `localhost` since Flask binds IPv4-only) must not panic the operator while the primary MQTT
  stream is healthy.
- **Fix:** render-side gate only — show the FAIL badge **only** when REST has tripped **AND**
  MQTT cannot compensate (`!connHealth.socketConnected || connHealth.dataIsStale`). Banner now
  auto-clears the moment MQTT recovers (reactive on `connHealth`).
- **File:** `HMI/apex-hmi/src/components/hmi/IndustrialHMIPrototype.tsx` (~ lines 1475–1485).
- **Not changed:** C# backend, Flask, alarm logic, REST polling logic, fail counters.
- **Verified:** `npm run build` succeeded → new bundle `dist/assets/index-C1jb6OJn.js`. Banner
  hides when MQTT LIVE & data fresh, even if a REST poll fails.
- **Note:** the earlier "stale tag pool" theory was wrong — pool is fine; this was purely a
  frontend display-gating defect.

---

## Still pending (in approved order)
- ⏳ **Item 2A — RTN off-delay (5 s settling)** — in progress; awaiting decision on whether to
  add per-tag override column `tag_master.alarm_offset_delay_s` now or ship global-only first.
- ⏳ **Item 3 — Non-latching philosophy** (Option C recommended).
- ⏳ **Item 4 — Suppress lower level when higher is active** (optional).
- ⏳ **Item 5 — End-to-end lifecycle verification on PY1105B.**
