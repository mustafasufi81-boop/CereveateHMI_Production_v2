# PLC Data Integrity — End-to-End Code Study, Defect Register & Phased Correction Plan

**Document status:** DRAFT for PLC / SCADA expert review
**Scope:** Allen-Bradley (Rockwell, EtherNet/IP CIP via libplctag) data path only — from PLC TCP connection through value acquisition, pool, and into the three consumers (HMI live, Historian DB, Alarm/Interlock engine).
**Date:** 2026-05-31
**Author:** Engineering (assisted)
**Reviewers:** _________________ (PLC), _________________ (SCADA), _________________ (QA)

> **Mission of this document:** Establish ONE clear, hard rule set for how a tag value is allowed to travel from the PLC to the database, the trend, the HMI and the alarm engine — so that **no false value, garbage value, type-mismatched value, or stale value can ever be presented as trustworthy or be acted upon**. No hardcoding. No silent substitution. The system must always tell the truth about the validity of every number it shows.

---

## 0. Guiding Principles (the "constitution")

These principles are the acceptance criteria for every fix in this document.

| # | Principle | Plain-language meaning |
|---|-----------|------------------------|
| P1 | **Quality describes the VALUE, not just the link** | "Good" must mean *the number is trustworthy*, not merely *the socket is open*. |
| P2 | **No false truth in the pool** | The live cache must never hold a value flagged `Good` that the driver did not actually validate this scan. |
| P3 | **No silent substitution** | We never replace a bad/garbage reading with the last good value and call it `Good`. Garbage is shown **as-is, flagged Bad**. |
| P4 | **Bad data is quarantined at the earliest point** | Validation happens at the moment of capture (driver), so every downstream consumer inherits the verdict automatically. |
| P5 | **Garbage must never reach DB, trend, or alarms** | A value that fails validation cannot be written to the historian, cannot move a trend, and cannot raise/clear/escalate an alarm. |
| P6 | **A value is bound to a valid source state** | Mirrors the existing DB protection (value bound to a valid source *timestamp*). Live path binds value to a valid *connection + validity* verdict. |
| P7 | **No hardcoding** | No fabricated tags, no magic constants in business logic, no fixed IPs in the data path. All limits/types come from `tag_master`. |
| P8 | **Operator always sees the truth** | A non-Good value is visibly degraded on the HMI (greyed + quality badge). Never displayed as a normal live number. |

---

## 1. CURRENT FLOW — As-Built (verbatim from code)

This section documents what the code does **today**, with file/line anchors, so the reviewer can verify independently.

### 1.1 Connection establishment
**File:** `Services/PlcGateway/Drivers/RockwellDriver.cs`

1. `InitializeAsync(config, tags)` (line ~83)
   - Stores config + tag list.
   - **If `tags` is empty → injects 5 hardcoded test tags** (`Cooling_FAN_SPEED`, `Tank_Level`, …) — lines ~88–96.
   - If `RockwellConfig` is null → defaults `Path="1,0"`, `PlcType=ControlLogix`.
2. `ConnectAsync()` (line ~120)
   - **Offline backoff guard:** if previously unreachable, wait 30→60→120 s (capped) before retry.
   - **Single-tag probe:** creates a handle for the first tag only. If probe fails → mark offline, apply backoff, return false.
   - On probe success → resets backoff, creates handles for remaining tags (individual failures non-fatal).
   - Sets `_isConnected = true` if **at least one** handle was created.
3. `CreateTagHandleAsync(tag)` (line ~250)
   - Builds a libplctag `Tag` with `Gateway=Ip`, `Path="1,<n>"`, `PlcType=ControlLogix`, `Protocol=ab_eip`, `Timeout=2s`, `ElementSize=GetElementSize(dataType)`.
   - `libTag.Initialize()`; if status ≠ Ok → dispose + return null.

### 1.2 Value acquisition (the scan)
**File:** `RockwellDriver.cs`

4. `ReadAllTagsAsync()` (line ~287)
   - Parallel `Task.Run` per tag → `ReadTagValue(handle)`.
   - Null results are **filtered out** (`results.Where(v => v != null)`).
   - For every non-null value, constructs `PlcTagValue { Quality = PlcQuality.Good, … }` — **Quality is HARDCODED `Good`** (line ~333).
   - `Success = (values.Count > 0)`. If all null → `Success=false`, `_consecutiveFailures++`.
5. `ReadTagValue(handle)` (line ~474)
   - `libTag.Read()`; if `GetStatus() != Ok` → suppress-log once, return null (excluded).
   - On Ok, returns the typed value via a switch:
     ```
     BOOL→GetUInt8≠0, SINT→Int8, INT→Int16, DINT→Int32,
     LINT→Int64, REAL→Float32, LREAL→Float64,
     _ (DEFAULT) → GetFloat32(0)      // unknown type read as REAL
     ```
   - **No value sanity check** (no NaN/Infinity/denormal/range test).
6. `GetElementSize(dataType)` (line ~675)
   - Maps type→bytes; **unknown type → default `4`** (REAL-sized).

### 1.3 Pool population
**Files:** `Services/PlcGateway/Services/PlcWorker.cs`, `PlcDataLoggingService.cs`, `PlcTagValuesPoolService.cs`

7. `PlcWorker` read loop (line ~428) and `PlcDataLoggingService.PollSinglePlcAsync` (line ~370) both:
   - Map driver `PlcTagValue` → `PlcTagValueCacheEntry` with `Quality = ConvertQuality(v.Quality)`, `CachedAt = UtcNow`.
   - Call `_sharedPool.UpdateFromPlc(plcId, entries, timestamp, mode)`.
8. `ConvertQuality(PlcQuality)` — **duplicated** in both files (PlcWorker line ~603, PlcDataLoggingService line ~412): `Good→Good, Bad→Bad, Uncertain→Uncertain, CommError→CommError, _→NotConfigured`.
9. `PlcTagValuesPoolService.UpdateFromPlc` (line ~66)
   - Stores entry verbatim (`with { CachedAt = UtcNow }`). **No independent validation** — it trusts the driver's `Good`.
   - Runs the RUN/FROZEN value-change heuristic (≥15 % tags must change).
10. `MarkPlcDisconnected(plcId)` (line ~173)
    - Sets `IsConnected=false`, and rewrites every tag of that PLC to `Quality = Uncertain` (value & timestamp preserved → frozen).
    - Triggered by `PlcDataLoggingService` after **≥3 consecutive failures** (line ~397).
11. `PlcTagValueCacheEntry.ComputedQuality` (record, line ~470)
    - On read access: Good/Uncertain older than 10 s → escalates to `Stale`; hard-bad qualities preserved.

### 1.4 Consumers

**(A) HMI live** — `IndustrialHMIPrototype.tsx`
- Greys value + shows STALE badge when `quality ∈ {Stale, Uncertain}` (lines ~1915–1925).

**(B) Historian DB** — `PlcHistorianIngestService.cs`
- `ProcessPoolDataAsync` (line ~200): for each mapped tag, applies **only** `Interval` and `Deadband` filters (`GetFilterReason`, line ~310). **No quality filter.**
- Derives `qualityChar` (`Good→G, Bad→B, Uncertain→U, CommError→B, NotConfigured→U`) and writes via BINARY COPY into `historian_raw.historian_timeseries` with columns `(time, tag_id, value_num, …, quality, …, opc_timestamp, ingest_timestamp)` (line ~352).
- `time` / `opc_timestamp` = `record.Timestamp` = **the PLC/source timestamp** (frozen on disconnect). PK `(time, tag_id)` blocks duplicate frozen rows.

**(C) Alarm / Interlock** — `AlarmEvaluation/Services/AlarmEvaluationService.cs`
- `EvaluateCycleAsync` (line ~148): pulls OPC pool values; for alarm tags missing from OPC, pulls from PLC pool (`_plcTagPool.GetTagValues(missingIds)`), converting `Quality = Good ? "Good" : "Bad"` and forcing `UpdatedAt = UtcNow-60s` when not Good (to force `IsStale`).
- Per-tag gate (line ~192): `if (entry.IsStale || !IsGoodQuality(entry.Quality)) continue;` — skips non-Good / stale.
- `IsGoodQuality` = `"Good" | "G" | "GOOD"`.
- `TagValuesPoolService.TagValueCacheEntry.IsStale` (OPC pool) **was hardened** to: `!IsGoodQuality(Quality) || age>30s`.

### 1.5 Current flow diagram

```
                       ┌──────────────────────────────────────────────┐
   PLC (192.168.0.20)  │  RockwellDriver                              │
   EtherNet/IP CIP     │  ReadTagValue → typed switch (REAL default)  │
        │  libplctag   │     • status≠Ok → null (dropped)             │
        ▼              │     • status=Ok → raw number                 │
   [ raw bytes ]  ───► │  PlcTagValue { Quality = Good }  ◄── HARDCODED│
                       │     ✗ no NaN/Inf/denormal/range/type check    │
                       └───────────────┬──────────────────────────────┘
                                       ▼
                       ┌──────────────────────────────────────────────┐
                       │  PlcTagValuesPoolService (live cache)         │
                       │  UpdateFromPlc → stores verbatim (trusts Good)│
                       │  MarkPlcDisconnected (≥3 fails) → Uncertain   │
                       │  ComputedQuality → Stale if age>10s           │
                       └───────┬───────────────┬───────────────┬──────┘
                               ▼               ▼               ▼
                       (A) HMI live      (B) Historian DB   (C) Alarm engine
                       greys non-Good    NO quality filter   skips non-Good /
                                         (Interval/Deadband  IsStale; relies on
                                          only); writes B/U   per-tag quality +
                                          value as-is         3-fail lag
```

---

## 2. DEFECT REGISTER — Issues & Risks

Each defect lists: **what**, **where**, **why it is dangerous**, **principle violated**.

### 🔴 D1 — Quality is hardcoded `Good` regardless of value validity
- **Where:** `RockwellDriver.ReadAllTagsAsync` line ~333; `ReadTagsAsync` line ~427.
- **What:** Any read with libplctag `Status.Ok` is stamped `PlcQuality.Good`, even if the decoded number is NaN, ±Infinity, a denormal (e.g. `1.22e-43`), or a type-mismatch bit pattern.
- **Danger:** A faulty sensor / corrupt register / wrong UDT offset is presented to operators and the alarm engine as a **trustworthy live value**. Can raise **false alarms** or, worse, **mask a real condition**.
- **Violates:** P1, P2, P4.
- **Evidence:** Pool poll showed `TY1102F = 1.22e-43` (classic denormal/uninitialised float) flagged Good.

### 🔴 D2 — No value sanity validation anywhere in the path
- **Where:** `ReadTagValue` (driver) → `UpdateFromPlc` (pool) → consumers. None perform `double.IsNaN/IsInfinity`, denormal, or engineering-range checks.
- **What:** There is **no point** where a numerically insane value is caught.
- **Danger:** Garbage flows to DB (corrupts AVG/SUM in reports), trend (false spikes), and alarms (false trips).
- **Violates:** P1, P5.

### 🔴 D3 — Historian has NO quality gate
- **Where:** `PlcHistorianIngestService.ProcessPoolDataAsync` line ~200; `GetFilterReason` line ~310 (only Interval + Deadband).
- **What:** A **connected** PLC delivering a garbage-but-`Good` value with a **fresh timestamp** will be **written to `historian_timeseries`** (the disconnect/frozen-PK protection does NOT apply because the timestamp is current).
- **Danger:** Permanent false data in trends & reports. This is the user's exact concern: *"garbage should not go to db / trend."*
- **Violates:** P5.
- **Note:** The disconnect case is already safe (frozen timestamp + PK). The **connected-garbage** case is NOT.

### 🔴 D4 — NaN / Infinity can be written to `value_num`
- **Where:** Historian COPY writer line ~390 (`WriteAsync(record.Value, Double)`), `ConvertToDouble` line ~331 returns the raw double.
- **What:** PostgreSQL `double precision` accepts `NaN`/`Infinity`. Once stored, **every aggregate over that window returns NaN/Infinity**, poisoning reports irreversibly.
- **Danger:** Silent, permanent report corruption.
- **Violates:** P5.

### 🟠 D5 — Unknown data type silently decoded as REAL
- **Where:** `ReadTagValue` default arm `_ => GetFloat32(0)`; `GetElementSize` default `_ => 4`.
- **What:** A tag whose `data_type` is mis-configured (or a UDT/STRING mis-tagged) is read as a 4-byte float. The bit pattern of a DINT/packed value decoded as REAL **is** the garbage we keep seeing (`1.22e-43`).
- **Danger:** Type-mismatch garbage that is **indistinguishable from a real reading** downstream — and flagged Good (see D1). This is the user's *"is it actually garbage or data-type mismatch"* question: **today we cannot tell, because we force the type.**
- **Violates:** P1, P7.

### 🟠 D6 — Alarm engine trusts per-tag quality only; 3-scan lag
- **Where:** `AlarmEvaluationService` line ~165–192; disconnect detection in `PlcDataLoggingService` needs **≥3 consecutive failures** before `MarkPlcDisconnected`.
- **What:** During the 3-scan window after a real disconnect, tags still read `Good` (frozen), so alarms can still evaluate. Also, the engine never consults the authoritative `IsConnected` flag directly.
- **Danger:** Brief window of alarm evaluation on frozen data after disconnect.
- **Violates:** P6.

### 🟠 D7 — Pool stores "false truth" (no independent validation)
- **Where:** `PlcTagValuesPoolService.UpdateFromPlc` line ~66.
- **What:** The pool faithfully stores whatever the driver says. Because the driver hardcodes `Good` (D1), the **pool becomes a cache of false-Good values**.
- **Danger:** Every consumer that trusts the pool inherits the lie.
- **Violates:** P2.

### 🟡 D8 — Hardcoded fabricated tags in `InitializeAsync`
- **Where:** `RockwellDriver.InitializeAsync` lines ~88–96.
- **What:** If no tags supplied, 5 fake tags are injected.
- **Danger:** Phantom tags in production; masks a real config-load failure.
- **Violates:** P7.

### ⚪ D9 — `ConvertQuality` duplicated in two files *(DEFERRED — see §4.1)*
- **Where:** `PlcWorker.cs` line ~603 and `PlcDataLoggingService.cs` line ~412 — two copies of the same 5-line switch.
- **Status:** Cosmetic maintainability item, not a data-integrity risk. **Not in this round** — rationale in §4.1.

### ⚪ D10 — Two parallel `PlcQuality` / `PlcTagQuality` enums *(DEFERRED — see §4.1)*
- **Where:** `Interfaces/IPlcDriver.cs` `PlcQuality { Good,Bad,Uncertain,CommError,NotConnected,NotConfigured }` vs pool `PlcTagQuality { …, Stale }`.
- **What:** Only the `NotConnected → NotConfigured` mapping is meaningfully wrong (link-down mislabelled “tag not set up”).
- **Status:** A single correct mapping line is all that’s ever needed — **no enum redesign**. **Not in this round** — rationale in §4.1.

### 🟡 D11 — `ConvertToDouble` masks parse failures as `0.0`
- **Where:** `PlcHistorianIngestService.ConvertToDouble` line ~331 (`string str => TryParse ? d : 0.0`).
- **What:** An unparseable value becomes **0.0** — a *plausible* number — and is written as `Good`-quality data.
- **Danger:** Silent substitution of 0 for "unknown" — a false reading that can itself trip Low alarms or skew sums.
- **Violates:** P3, P5.

---

## 3. THE RULE SET (normative — what "correct" means)

> These are the **hard rules** the corrected system must obey. Written so a PLC expert can sign off line-by-line.

### R1 — Quality is a function of (link state) **AND** (value validity)
```
Quality(tag) =
    NotConnected   if PLC link is down
    Bad            if read status ≠ Ok
    Bad            if decoded value fails validity (see R3)
    Uncertain      if connection lost → last value frozen (set by MarkPlcDisconnected)
    Stale          if last good update age > staleness window
    Good           ONLY if status=Ok AND value passes ALL validity checks
```
> No “range-suspect” state — out-of-range *process* values are the existing **alarm limits’** job, not a quality state (see R3 note).

### R2 — Value is always carried truthfully; never substituted
- The **actual** decoded number is always propagated (even when Bad), so engineers can diagnose.
- **Never** replace a Bad/garbage value with last-good and relabel it Good (kills D11-style 0.0 masking too).

### R3 — Validity check (applied at capture, per numeric type)
A floating value (`REAL`/`LREAL`) is **invalid** if ANY of:
- `double.IsNaN(v)`
- `double.IsInfinity(v)`
- **Denormal/sub-normal:** `v != 0 && Math.Abs(v) < MinNormal` (catches `1.22e-43`). `MinNormal(REAL)=1.18e-38`, `MinNormal(LREAL)=2.225e-308`.

Integer/BOOL types: validity = read status Ok (no NaN concept).

> **NOTE — min/max range check is intentionally NOT included.** Out-of-range *process* values (too hot, too low, sensor over/under-range like `99999`) are already handled by the **existing alarm limits** (HH/H/L/LL). Adding a second `min_value`/`max_value` gate here would duplicate alarm logic — so it is **excluded** to avoid over-engineering. The validator answers only *"is the number itself sane?"* (NaN/Inf/denormal/type), never *"is the process in range?"*.

### R4 — Type integrity (detect mismatch, do not force REAL)
- The decode switch **must not** silently default unknown types to `GetFloat32`. An unknown/empty `data_type` ⇒ **`Quality=Bad`, reason="TYPE_UNCONFIGURED"`** — not a fabricated float.
- Optional R4b: when libplctag exposes the element type, compare against configured `data_type`; mismatch ⇒ `Bad`, reason="TYPE_MISMATCH".

### R5 — Garbage cannot reach DB / trend / alarms
- **DB:** Historian must **skip** writing `value_num` for non-Good readings; instead write `value_num = NULL, quality ∈ {B,U}` so the **event of bad quality is recorded truthfully** without polluting aggregates. NaN/Infinity ⇒ NULL always.
- **Trend:** follows DB (NULL renders as a gap, not a spike).
- **Alarms:** evaluation **must** skip any reading that is not `Good` (already partly done; reinforce with connection gate R6).

### R6 — Connection gate for live/alarm reads
- Alarm/live evaluation must read via a method that **omits tags whose owning PLC is `IsConnected=false`** (authoritative), in addition to the per-tag quality gate. Two independent gates, same verdict.

### R7 — No hardcoding
- Remove fabricated test tags (D8). A missing tag list ⇒ log error + no tags (fail visibly).
- All limits/types/staleness windows come from `tag_master` / config, not literals in business logic.

### R8 — *(Deferred — see §4.1)*
- The system only needs **two truths**: (1) is the link up? (2) is the value trustworthy (Good vs Bad)? Everything else (Stale, reason labels) derives from those.
- **No `QualityMapper` abstraction and no canonical-enum redesign this round.** The only concrete hygiene items (don’t duplicate the switch; don’t mislabel `NotConnected`) are deferred with rationale in §4.1.

### R9 — Operator visibility
- HMI must visibly degrade any non-Good value (grey + badge) — extend current logic to also cover `Bad`, `NotConnected`, `TYPE_*` reasons, not just Stale/Uncertain.

---

## 4. PHASED CORRECTION PLAN

Phases are ordered so the **base** (truthful quality at capture) is fixed first; later phases build on it. Each phase is independently buildable, reviewable, and testable.

### ▶ PHASE 1 — Fix the BASE: truthful quality at capture *(driver)*
**Goal:** Quality stops being a lie. (D1, D2, D3-source, D5, D8)
**Changes (RockwellDriver.cs):**
1. Introduce `TagValueValidator.Validate(object? raw, PlcTagDefinition tag) → (bool ok, PlcQuality quality, string? reason)` implementing **R3 + R4** (NaN/Inf/denormal + type integrity; **no** min/max range — alarms own range).
2. In `ReadTagValue`: keep typed decode, but **remove the REAL default** — unknown type ⇒ return a sentinel "bad" outcome (R4).
3. In `ReadAllTagsAsync`/`ReadTagsAsync`: replace `Quality = PlcQuality.Good` with the **validator verdict**; **carry the actual value** even when Bad (R2). Do not drop Bad values silently — propagate them flagged Bad (so HMI/diagnostics see them) **except** hard read failures (status≠Ok) which remain null/dropped as today.
4. Remove fabricated test-tag block (D8 / R7).
**Acceptance:** Unit tests feed NaN/Inf/denormal/type-mismatch → expect `Quality=Bad` with correct reason; valid in-range → `Good`.
**Risk:** Low (additive validation; value still carried).

### ▶ PHASE 2 — Protect the HISTORIAN *(DB integrity)*
**Goal:** Garbage/NaN can never enter `value_num`. (D3, D4, D11)
**Changes (PlcHistorianIngestService.cs):**
1. In `ProcessPoolDataAsync`, **before** building the record: if `ComputedQuality` is not Good ⇒ write `value_num = NULL`, `quality = B/U` (still honour Interval heartbeat so the *bad-quality event* is recorded). (R5)
2. In `ConvertToDouble`: unparseable ⇒ return **NULL marker**, not `0.0` (R2/R3). Caller writes NULL + quality B.
3. Sanitise: `double.IsNaN || IsInfinity` ⇒ NULL + quality B (R5/D4).
**Acceptance:** With a forced Bad/NaN tag, DB row shows `value_num IS NULL, quality='B'`; aggregates over the window ignore it; trend shows a gap.
**Risk:** Low. Pure write-path guard.

### ▶ PHASE 3 — Harden ALARM/LIVE reads *(connection + quality gate)*
**Goal:** No evaluation on disconnected or non-Good tags; close the 3-scan lag. (D6, D7)
**Changes:**
1. Add `PlcTagValuesPoolService.GetTagValuesFromConnectedPlcs(tags)` — omits tags of `IsConnected=false` PLCs (R6).
2. `AlarmEvaluationService.EvaluateCycleAsync` uses it for the PLC merge; keep the existing per-tag `IsStale/!Good` gate as second gate.
3. **Pool invariant guard (not re-validation):** `UpdateFromPlc` enforces the single invariant *“Quality=Good ⇒ value is finite”*. If violated, demote to `Bad` + log (signals a driver regression). The pool does **no** denormal/range/type checks — the driver (Phase 1) is the **sole validation authority** (defence-in-depth for P2/D7).
**Acceptance:** With PLC physically down, **zero** new PLC alarm events; with a connected garbage tag, **zero** alarm raises (quality gate).
**Risk:** Low/additive. New method only removes data.

### ▶ PHASE 4 — Operator visibility & telemetry *(HMI + diagnostics)*
**Goal:** Truth is visible. (R9)
**Changes:**
1. HMI: extend the grey/badge logic to `Bad`, `NotConnected`, `TYPE_MISMATCH`, `TYPE_UNCONFIGURED`, with a short reason tooltip.
2. Expose per-tag last validity reason via the existing PLC status/diagnostics endpoint for engineering.
**Acceptance:** Forcing each bad-reason shows the correct badge + reason on the HMI.
**Risk:** Low (presentation only).

### Phase dependency / sequence
```
Phase 1 (base: truthful quality)  ─┬─► Phase 2 (DB guard)
                                   ├─► Phase 3 (alarm/live gate)
                                   └─► Phase 4 (HMI/telemetry, optional)
```
Phases 2, 3 and 4 depend only on Phase 1 and can proceed in parallel after it. **The reported problems are fully solved by Phases 1–3; Phase 4 is presentation only.**

---

## 4.1 DEFERRED — not in this round (with rationale)

These items were considered and **deliberately deferred** to avoid over-engineering. They are recorded here (not deleted) so the decision is auditable. **None is a data-integrity risk** once Phases 1–3 are in place.

| Item | What it was | Why deferred (reason for skipping) | Pre-condition to revisit |
|------|-------------|-------------------------------------|--------------------------|
| **Range check (min/max)** — old R3b / Q1 | Flag values outside `tag_master.min_value/max_value`. | **Duplicates existing alarm limits** (HH/H/L/LL already catch out-of-range process values). The validator only judges numeric *sanity*, not process range. | Only if a need arises that alarms cannot cover. |
| **Phase 4 (old) — Consolidate quality model** | Extract a shared `QualityMapper`; make `PlcQuality`↔`PlcTagQuality` a total/loss-less map. | **Maintainability polish, not a safety fix.** System only needs two truths (*link up? / value trustworthy?*), both delivered by Phases 1–3. A new abstraction adds a second source of authority. | If a future driver (Siemens/Modbus) forces a shared mapping. |
| **R8 — single-source QualityMapper** | The rule mandating the above abstraction. | Same as above — abstraction not justified for the current single (Rockwell) driver. | With multi-driver rollout. |
| **D9 — duplicate `ConvertQuality`** | Two copies of a 5-line switch. | **Cosmetic.** Low risk; no behavioural defect. If ever touched, simply share one copy — no framework. | Opportunistically, when either file is edited. |
| **D10 — two quality enums** | `NotConnected` can map to `NotConfigured`. | The only real flaw is one mapping line; **no enum redesign warranted**. Not currently operator-visible. | If it produces a wrong operator message. |
| **R4b — libplctag element-type compare** | Compare configured `data_type` vs the PLC’s actual element type. | Needs a **libplctag capability check** first; R4 (fail unknown type to `Bad`) already removes the garbage source. | After confirming libplctag exposes element type. |

> **Net effect:** this round implements **Phases 1–3** (the actual fix for the reported false/garbage/stale values) plus optional **Phase 4** (HMI visibility). Everything in this table is intentionally **out of scope now**.

---

## 4.2 MODULE / FILE INVENTORY — exactly what we will touch

> Verified against the real source on 2026-05-31 (paths and line anchors confirmed by reading each file). **Anything not listed here is NOT modified.** Implementation proceeds top-down, one module at a time, build-verified after each.

### New file (added)
| # | File (to create) | Phase | Responsibility | Risk |
|---|------------------|-------|----------------|------|
| N1 | `CSharpBackend/Services/PlcGateway/Validation/TagValueValidator.cs` | 1 | Pure, stateless `Validate(raw, tag) → (ok, PlcQuality, reason)` implementing **R3** (NaN/Inf/denormal) + **R4** (type integrity). No I/O, no wiring. | **None** (isolated; nothing calls it yet). |

### Existing files (modified)
| # | File (verified path) | Phase | Exact change | Confirmed anchor |
|---|----------------------|-------|--------------|------------------|
| M1 | `…/PlcGateway/Drivers/RockwellDriver.cs` | 1 | (a) Remove fabricated test-tag block; (b) remove REAL `default` in `ReadTagValue` decode switch; (c) replace hardcoded `Quality = PlcQuality.Good` with validator verdict, carry value even when Bad. | ✅ tags @88–96; switch `_ => GetFloat32(0)` @~528; `Quality = PlcQuality.Good` @~333 |
| M2 | `…/PlcGateway/Services/PlcHistorianIngestService.cs` | 2 | (a) Non-Good ⇒ `value_num = NULL` + quality flag; (b) `ConvertToDouble` parse-fail ⇒ NULL (not `0.0`); (c) NaN/Inf ⇒ NULL. | ✅ `ProcessPoolDataAsync` ~200; `ConvertToDouble` ~331; COPY writer ~390 |
| M3 | `…/PlcGateway/Services/PlcTagValuesPoolService.cs` | 3 | (a) Add `GetTagValuesFromConnectedPlcs(tags)`; (b) `UpdateFromPlc` invariant guard *“Good ⇒ finite”* (demote+log only). | ✅ `UpdateFromPlc` ~66; `MarkPlcDisconnected` ~173 |
| M4 | `…/Services/AlarmEvaluation/Services/AlarmEvaluationService.cs` | 3 | Use `GetTagValuesFromConnectedPlcs` for the PLC merge; keep existing per-tag `IsStale/!Good` gate as second gate. | ✅ `EvaluateCycleAsync` ~148; per-tag gate ~192 |
| M5 | `…/frontend/.../IndustrialHMIPrototype.tsx` | 4 (optional) | Extend grey/badge to `Bad`/`NotConnected`/`TYPE_*` + reason tooltip. | ✅ badge logic ~1915–1925 |

### Read-only reference (NOT modified)
| File | Why referenced |
|------|----------------|
| `…/PlcGateway/Interfaces/IPlcDriver.cs` | Source of truth for `PlcQuality { Good,Bad,Uncertain,CommError,NotConnected,NotConfigured }`, `PlcTagValue`, `PlcTagDefinition`. Validator returns these existing members — **no enum change**. |
| `…/PlcGateway/Services/PlcWorker.cs`, `PlcDataLoggingService.cs` | Carry the driver verdict into the pool unchanged (their `ConvertQuality` is in §4.1 Deferred). |

> **Cautious-implementation order:** N1 (isolated, build) → M1 (wire, build, regression) → M2 (build) → M3+M4 (build) → M5 (optional). No module advances until the previous one builds clean and passes its Acceptance check in §4.

---

## 5. Decisions required from the PLC expert (please annotate)

| Q | Question | Default proposal |
|---|----------|------------------|
| Q1 | ~~Range check via `tag_master.min_value/max_value`?~~ **DECIDED — dropped.** Out-of-range process values are handled by **existing alarm limits**; the validator does not duplicate them (see R3 note). | n/a (rely on existing alarms). |
| Q2 | For **denormal floats**, is treating sub-normal as Bad acceptable for all REAL tags, or are there legitimately tiny-magnitude process values? | Treat sub-normal as Bad (configurable per tag if needed). |
| Q3 | On **unknown/empty data_type**, fail to `Bad` (proposed) vs. attempt REAL? | Fail to `Bad` (R4). |
| Q4 | Historian on non-Good: write **NULL value + quality flag** (proposed) vs. skip the row entirely? | Write NULL + quality (keeps the bad-quality event on record). |
| Q5 | Staleness windows (live 10 s, alarm/OPC 30 s, frozen-heuristic 8 s) — confirm or set per site. | Keep current defaults. |
| Q6 | Type-mismatch detection (R4b) via libplctag element type — in scope now or later? | **Deferred** (see §4.1) — needs libplctag capability check. |

---

## 6. Out-of-scope (explicitly, for this round)
- OPC-DA path correctness (already follows quality-byte model; only referenced for comparison).
- Non-Rockwell drivers (Siemens/Modbus/etc.) — same rules to be ported in a follow-up once Rockwell is signed off.
- Alarm state-machine semantics (ISA-18.2) — unchanged; we only stop **feeding** it bad data.

---

## 7. Test strategy (high level — detailed cases after sign-off)
1. **Unit (driver/validator):** NaN, +Inf, −Inf, denormal `1.22e-43`, type-mismatch bit pattern, valid mid-range → assert quality+reason.
2. **DB guard:** force each bad class → assert `value_num IS NULL`, `quality∈{B,U}`, aggregates clean, trend gap.
3. **Alarm gate:** (a) PLC down → no new events; (b) connected garbage → no raise; (c) connected valid breach → correct raise.
4. **Pool defence-in-depth:** inject Good-NaN at pool boundary → pool rejects/keeps as gap (never Good-NaN).
5. **HMI:** each bad-reason renders greyed + correct badge/tooltip.
6. **Regression:** healthy PLC, normal operation → identical behaviour to today (no false degradation).

---

## 8. Sign-off

| Role | Name | Verdict (Approve / Changes) | Date |
|------|------|------------------------------|------|
| PLC Engineer | | | |
| SCADA/Historian | | | |
| QA | | | |
| Product Owner | | | |

> **On approval**, implementation proceeds strictly phase-by-phase; each phase is built, reviewed against its Acceptance criteria, and tested before the next begins. No phase is merged that violates any Principle in §0 or Rule in §3.
