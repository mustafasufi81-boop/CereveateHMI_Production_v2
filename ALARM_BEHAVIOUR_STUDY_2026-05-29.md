# Alarm Behaviour Study — Sequence Analysis vs ISA-18.2
**Date:** 2026-05-29
**Author:** GitHub Copilot (analysis only — NO code changes made)
**Scope:** PLC alarm path (OPC parked). Single-tag oscillation case `PY1105B`.
**Purpose:** Compare observed alarm-history behaviour against ISA-18.2 and the project's own
`ALARM_SYSTEM_REFERENCE.md`, list every visible bug, and propose fixes for operator decision.

---

## 1. The Observed Sequence (from history screenshot)

Single tag **`PY1105B`** with 4 configured limits:

| Level    | Limit  |
|----------|--------|
| LowLow   | 0.15   |
| Low      | 0.30   |
| High     | 0.40   |
| HighHigh | 0.60   |

PV is a **sine-like signal sweeping ≈0.14 ↔ 0.61**, crossing every limit each cycle.
In ~2 minutes it generated **14 events** (newest first):

```
10:39:36  HIGHHIGH  [HIGH]    UNACK  0.60/0.60  exceeded High-High limit 0.600213
10:39:26  LOW       [URGENT]  RTN    0.46/0.40  returned to normal from Low (0.461644)
10:39:20  HIGH      [HIGH]    UNACK  0.41/0.40  exceeded High limit 0.409367
10:39:14  LOWLOW    [URGENT]  RTN    0.23/0.15  returned to normal from LowLow (0.229257)
10:39:02  LOWLOW    [HIGH]    UNACK  0.14/0.15  exceeded Low-Low limit 0.140963
10:38:56  HIGH      [URGENT]  RTN    0.19/0.30  returned to normal from High (0.186166)
10:38:52  HIGHHIGH  [URGENT]  RTN    0.26/0.30  returned to normal from HighHigh (0.263085)
10:38:52  LOW       [HIGH]    UNACK  0.26/0.30  exceeded Low limit 0.263085
10:38:18  HIGHHIGH  [HIGH]    UNACK  0.61/0.60  exceeded High-High limit 0.609928
10:38:12  LOW       [URGENT]  RTN    0.48/0.40  returned to normal from Low (0.478519)
10:38:08  HIGH      [HIGH]    UNACK  0.44/0.40  exceeded High limit 0.444438
10:38:00  LOWLOW    [URGENT]  RTN    0.23/0.15  returned to normal from LowLow (0.229257)
10:37:28  LOWLOW    [HIGH]    UNACK  0.15/0.15  exceeded Low-Low limit 0.145338
10:37:22  HIGH      [URGENT]  RTN    0.20/0.30  returned to normal from High (0.196773)
```

---

## 2. THE ONE BEHAVIOUR THAT, IF FIXED, FIXES THE MOST  ⭐

### BUG #1 — Priority/Severity is HARD-CODED to `4` on every RTN / ACK / CLEAR event

**This is the single root behaviour behind the most visible anomaly in the screenshot.**

Notice the **Priority column flips** for the SAME alarm occurrence:
- Every **RAISE (UNACK)** row → `HIGH`
- Every **RTN** row → `URGENT`

An alarm's priority is a fixed attribute of the occurrence — it must **not** change when the
alarm returns to normal or is acknowledged.

**Proof (code):** `CSharpBackend/Services/AlarmEvaluation/Services/AlarmStateManager.cs`

| Transition | Line(s) | Value written | Correct? |
|------------|---------|---------------|----------|
| RAISE      | 229, 231 | `priority` (real, from setpoint) | ✅ |
| alarm_active upsert | 279 | `priority` (real) | ✅ |
| **RTN**    | 415, 417 | **`4` (hard-coded)** | ❌ |
| **ACK**    | 593, 598 | **`4` (hard-coded)** | ❌ |
| **CLEAR**  | 848, 850 | **`4` (hard-coded)** | ❌ |

**Proof (label mapping):** `AlarmHistoryModal.tsx` line 113
`["", "LOW", "WARNING", "HIGH", "URGENT", "CRITICAL"][p]` → `3 = HIGH`, `4 = URGENT`.
PY1105B is configured priority **3 (HIGH)**; the hard-coded `4` renders as **URGENT** on every
RTN/ACK/CLEAR row.

**ISA-18.2 reference:** §5.2.4 (alarm attributes) / §18 (alarm records) — priority and severity
are occurrence attributes; all lifecycle records (raise, RTN, ack, clear) for one occurrence must
carry the **same** priority for correct analytics, sorting, KPIs and audit.

**Impact:** Wrong priority on >50% of history rows; corrupts priority-based filtering, alarm-rate
KPIs by priority, and any "URGENT count" reporting. Operators see false URGENTs.

**Proposed fix (small, low-risk):** Replace the three hard-coded `4`s (severity + priority on RTN,
ACK, CLEAR) with the occurrence's real priority taken from the in-memory
`AlarmRuntimeState` (already holds the value used at RAISE). One concept — "propagate the
occurrence priority to every transition" — fixes all three event types at once.

---

## 3. ISA-18.2 Behavioural Gaps (design-level)

### BUG #2 — Chattering / fleeting alarms: no chatter filter, no off-delay  ⚠ HIGH
**Observed:** One oscillating tag produced 14 events in ~2 min and would continue indefinitely.
This is a textbook **chattering alarm** (repeatedly transitions between active and normal in a
short period).

**Current controls:**
- On-delay (onset) ✅ — `AlarmDelayTracker`
- Exit deadband ✅ — `HasExitedAlarmZone` + `EffectiveDeadband` (fixed 2026-05-29)
- Off-delay ❌ — none
- Chatter counter / auto-shelve ❌ — none

**Why deadband alone doesn't help here:** the PV amplitude (0.14–0.61) *fully* traverses each band,
so any reasonable deadband is still crossed every cycle. Deadband stops *jitter at a threshold*,
not *large oscillations across the whole range*.

**ISA-18.2 reference:** §5.3.3 (alarm attributes incl. delay timers & deadband), §16 (monitoring &
assessment — chattering/fleeting alarms are top "bad actors" to be managed).

**Proposed options (pick per philosophy):**
- (a) **Off-delay** on RTN (value must stay normal for N s before RTN) — pairs with existing on-delay.
- (b) **Chattering detection**: count transitions per alarm_key in a rolling window; when it exceeds
  a threshold (e.g. ≥5 in 60 s), raise **once**, tag it `CHATTERING`, and **auto-shelve** for a
  cooldown instead of re-annunciating each cycle.
- (c) **Minimum on-time** before an alarm is eligible to RTN.

### BUG #3 — Double annunciation of H+HH (and L+LL) for one excursion  ⚠ MEDIUM
**Observed:** On an up-sweep, `High` raises at 0.40 *then* `HighHigh` raises at 0.60 — operator
sees **two** alarms for one high event; on the way down, two RTNs.

**Current logic:** `AlarmSuppressionEngine` suppresses a *new* lower-level raise only while the
higher level is *already* active. But the lower level (`High`) crosses **first** on the way up, so
it is **not** suppressed; when `HighHigh` later raises, the already-active `High` is left annunciated.

**ISA-18.2 reference:** §5.3.4 (designed suppression) / common alarm philosophy: annunciate only the
**highest active** sub-alarm of a multi-level point to reduce alarm count.

**Proposed fix (design decision):** When a higher level raises, auto-suppress/auto-RTN the lower
level of the same tag so only the highest active level is presented. (Optional — some sites prefer
to keep both. Needs operator/philosophy sign-off.)

### BUG #4 — Latching by default: ACK + Return-to-Normal needs a 2nd ACK  ⚠ MEDIUM
**Behaviour:** `ActiveAck` + value returns → `RTN_UNACK`, requiring a **second** acknowledgement to
clear (manual reset).

**ISA-18.2 reference:** §5.2 standard state model — an **acknowledged** alarm that returns to normal
should transition to **Normal automatically**. Manual-reset (latching) is a **per-alarm option**
reserved for safety-critical points, not a blanket default.

**Proposed fix (config):** Add a per-alarm `latching`/`manual_reset` flag in `tag_master`
(default **false** = ISA standard auto-return). Latching alarms keep current behaviour.

---

## 4. Items Checked and Found OK (no action)

- **RTN value correctness:** RTN rows correctly store the *return* value (e.g. 0.461644), not the
  trip value — message and Value column agree. ✅
- **RTN now fires** (deadband-inversion bug fixed 2026-05-29). ✅
- **Re-alarm/reflash** (RTN_UNACK → ACTIVE_UNACK on re-entry) now works (fixed 2026-05-29). ✅
- **Pool freshness:** all 128 PLC tags fresh (~2 s), quality Good — earlier "stale" report was a
  buggy diagnostic script reading the wrong JSON key. ✅

---

## 5. Summary Table — For Decision

| # | Bug / Gap | Severity | ISA-18.2 | Type | Effort | Risk |
|---|-----------|----------|----------|------|--------|------|
| 1 | Priority hard-coded `4` on RTN/ACK/CLEAR | **HIGH (visible)** | §5.2.4, §18 | Code (3 spots) | XS | Low |
| 2 | No chatter filter / off-delay (alarm flood) | **HIGH** | §5.3.3, §16 | Code + config | M | Med |
| 3 | Double annunciation H+HH / L+LL | MEDIUM | §5.3.4 | Code (design) | S | Med |
| 4 | Latching ACK+RTN by default | MEDIUM | §5.2 | Config + code | S | Low |

### Recommended order
1. **BUG #1 first** — tiny, low-risk, fixes the most visible per-row anomaly across all event types
   ("fix one behaviour → all event types consistent"). **Do this immediately.**
2. **BUG #2** — biggest operational/ISA win (kills alarm floods). Requires a philosophy choice on
   off-delay vs chatter-shelve.
3. **BUG #4** — make latching configurable (ISA default = auto-return).
4. **BUG #3** — optional, depends on site philosophy.

> No code has been changed. Awaiting your decision on which item(s) to implement and, for #2/#4,
> the philosophy parameters (off-delay seconds, chatter window/threshold, default latching).
