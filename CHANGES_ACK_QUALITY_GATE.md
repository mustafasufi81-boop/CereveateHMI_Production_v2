# ACK / CLEAR / SUPP Quality Gate — Change Log
**Date:** 2026-06-01  
**Branch:** main  
**Author:** GitHub Copilot (requested by mustafasufi81-boop)

---

## What Was Built

Block the **ACK**, **CLEAR**, and **SUPP** buttons on the alarm panel when the tag behind an alarm has bad/stale/unknown data quality. Buttons stay active when quality is `"Good"`.

---

## Files Changed

### 1. `HMI/apex-hmi/src/components/hmi/AlarmPanel.tsx`

#### State declaration (line ~169)
Replaced two old states with one:
```tsx
// REMOVED:
const [tagStale, setTagStale] = useState<Record<string, boolean>>({});
const [tagTimestamps, setTagTimestamps] = useState<Record<string, number>>({});

// ADDED:
const [tagQuality, setTagQuality] = useState<Record<string, string>>({});
```

#### Fetch loop (line ~604)
Replaced `staleMap`/`tsMap` logic with `qualityMap`:
```tsx
// REMOVED: staleMap, tsMap, setTagStale, setTagTimestamps

// ADDED:
const qualityMap: Record<string, string> = {};
if (tagInfo?.quality) qualityMap[tagId] = String(tagInfo.quality);
setTagQuality(qualityMap);
```

#### ACK button (line ~3491)
```tsx
// REMOVED:
const isTagStaleForAck = alarm.tag_id ? (tagStale[alarm.tag_id] === true) : false;

// ADDED:
const _ackQ = alarm.tag_id ? (tagQuality[alarm.tag_id] ?? 'Good') : 'Good';
const isTagBadQuality = _ackQ !== 'Good';
// disabled={... || isTagBadQuality}
// title shows quality value in tooltip
```

#### SUPP button (line ~3528)
Wrapped in IIFE to add quality gate:
```tsx
const _suppQ = alarm.tag_id ? (tagQuality[alarm.tag_id] ?? 'Good') : 'Good';
const isSuppBlocked = _suppQ !== 'Good';
// disabled={isSuppBlocked}
```

#### CLEAR button (line ~3587)
```tsx
// REMOVED:
disabled={isPending || tagStale[alarm.tag_id] === true}

// ADDED:
disabled={isPending || (tagQuality[alarm.tag_id] ?? 'Good') !== 'Good'}
```

---

### 2. `HMI/controllers/tag_controller.py`

#### OPC live overlay added (after PLC overlay)
Fetches `/api/opc/values` from C# backend (live, no DB) and overwrites quality for OPC tags.

#### Quality normalization (end of `get_latest_tags`)
```python
_q_expand = {'G': 'Good', 'B': 'Bad', 'U': 'Uncertain'}
for t in tags.values():
    t['quality'] = _q_expand.get(t.get('quality'), t.get('quality') or 'Good')
```
**Why:** DB stores quality as single char `"G"/"B"/"U"`. Frontend checks `!== 'Good'` (full word). This normalization catches any tag not matched by the live overlays.

---

## Data Flow (After Fix)

```
/api/tags/latest  (Flask)
  │
  ├─ Step 1: DB  →  historian_latest_value  →  quality = "G"/"B"/"U"/NULL
  │
  ├─ Step 2: OPC overlay  →  C# /api/opc/values  →  quality = "GOOD"/"BAD"
  │            maps: GOOD→Good, BAD→Bad, UNCERTAIN→Uncertain
  │
  ├─ Step 3: PLC overlay  →  C# /api/plc/values  →  computedQuality = "Good"/"Stale"/"Bad"
  │            (PLC disconnected = "Stale" → buttons blocked ✅ correct)
  │
  └─ Step 4: Normalize  →  G→Good, B→Bad, U→Uncertain, NULL→Good
```

---

## Quality Values & Button Behaviour

| Quality | ACK | CLEAR | SUPP |
|---------|-----|-------|------|
| `Good`  | ✅ Enabled | ✅ Enabled | ✅ Enabled |
| `Stale` | 🔴 Blocked | 🔴 Blocked | 🔴 Blocked |
| `Bad`   | 🔴 Blocked | 🔴 Blocked | 🔴 Blocked |
| `Uncertain` | 🔴 Blocked | 🔴 Blocked | 🔴 Blocked |

Tooltip shows the actual quality value e.g. `"Tag quality is Stale — ACK blocked until tag returns to Good."`

---

## Build & Deploy

```bash
cd HMI/apex-hmi
npm run build
xcopy /E /Y dist\* ..\nginx\html\
```
Built successfully — `✔ built in 13.77s`

---

## Known Issues (Deferred)

### `tag_controller.py` — OPC overlay variable shadowing (LOW RISK)
**File:** `HMI/controllers/tag_controller.py` ~line 197  
**Code:**
```python
tag_id = ov.get('tagId') or ov.get('tag_id')   # set here
if tag_id not in tags:
    tag_id = name_to_id.get(str(tag_id).upper()) # reassigned — original lost if None
```
**Risk:** If OPC `tagId` is not in `tags` AND not in `name_to_id`, `tag_id` becomes `None`. The next `if tag_id is None` guard catches it — **no crash**, no wrong data. Just slightly fragile logic.  
**Fix when ready:** Use separate variable `opc_cand` for lookup, `opc_tid` for resolved id.

---

## Pending

- **Flask must be restarted** (PID 17088 on port 6001) to activate `tag_controller.py` changes.
- After restart, `Triangle Waves.Real4` (OPC, quality=GOOD) will have ACK/CLEAR/SUPP **enabled**.
- PLC tags (AY/TY etc.) remain blocked while PLC is disconnected — **correct behaviour**.
