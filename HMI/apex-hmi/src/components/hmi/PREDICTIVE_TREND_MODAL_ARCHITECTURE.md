# PredictiveTrendModal — Architecture & Per-Second Divergence Tracking

## File
`src/components/hmi/PredictiveTrendModal.tsx`

---

## Core Concept

The modal runs two completely independent tracks in parallel:

| Track | What it does | How often |
|-------|-------------|-----------|
| **Actual line** | Fetches live historian data (2h window, 1-min resample) | Every 1 second |
| **Forecast** | Computed once by Python, frozen for 30 minutes | Once on open, regenerates only when horizon expires |
| **Divergence log** | Fetches raw 2-min actuals (no resampling), interpolates frozen forecast to each second, records error | Every 1 second (inside the same poll) |

---

## Why Freeze the Forecast

The forecast is a Python statistical computation (LR, HW, FFT, ARIMA). It predicts what values should be at future timestamps.

**If we kept recomputing the forecast every second:**
- we would never see whether the original prediction was right or wrong
- we would be comparing a freshly fitted line to itself, not to reality
- it defeats the purpose of forecasting

**Freezing it means:**
- at T=0 Python says "at T+5min the value will be X"
- at T=5min the actual value arrives
- we measure `|actual − X|` → this is real forecast accuracy

---

## Data Flow Diagram

```
Every second (setInterval 1000ms):
│
├─ ACTUAL TRACK
│   POST /api/bi/trends
│   { start: now-2h, end: now, resample_minutes: 1 }
│   → setTrendData()  → chart actual line moves forward
│
├─ ACCURACY LOG TRACK (minute-bucket)
│   Compares minute-averaged actuals to forecast[i] for resolved slots
│   → accuracyLogRef  → logTick triggers re-render
│
└─ DIVERGENCE TRACK (per-second, new)
    POST /api/bi/trends
    { start: now-2min, end: now }   ← NO resample_minutes → raw seconds
    For each raw row:
      epoch  = row.Timestamp
      secKey = round(epoch / 1000) * 1000   ← dedup key
      if trackedSecsRef.has(secKey) → skip
      for each model (LR, HW, FFT, ARIMA):
        fv = interpolateForecast(frozenForecast, epoch, model)
        errAbs = |actual - fv|
        errPct = errAbs / |actual| * 100
        cumErrRef[model] += errAbs        ← running loss accumulator
      push SecondRecord → liveErrRef (newest first, max 300)
      setErrTick() → forces panel re-render


Forecast track (separate timer):
  Fires ONLY when Date.now() > last forecast timestamp
  → doFetchForecast() → POST /api/bi/forecast → forecastRef updated
  → re-arms itself for the next 30-min horizon
```

---

## interpolateForecast()

Linear interpolation between two consecutive forecast minute-marks.

```ts
function interpolateForecast(
  fc: ForecastResponse,
  epochMs: number,
  model: ModelKey
): number | null
```

- Finds the two forecast timestamps `t0 ≤ epochMs ≤ t1`
- Returns `v0 + (v1 - v0) * (epochMs - t0) / (t1 - t0)`
- Returns `null` if the epoch is outside the forecast window

This means every raw second (e.g. `09:05:33`) gets a precise interpolated forecast value even though the Python model only emits one value per minute.

---

## Divergence Log Panel (⚡ LIVE DIVERGENCE LOG)

### What is shown

1. **ΣLOSS row** — cumulative absolute error per model since the modal was opened. Grows every second. Models with lower cumulative loss are more accurate over time.

2. **Per-second rows** — newest first:
   - `TIME` — second-level timestamp
   - `ACTUAL` — raw sensor value at that second
   - `LR Δ%` / `HW Δ%` / `FFT Δ%` / `ARIMA Δ%` — percentage divergence from frozen forecast at that exact second

### Color coding

| Color | Meaning |
|-------|---------|
| 🟢 Green | `< 1%` divergence — forecast is tracking well |
| 🟡 Yellow | `1–3%` — minor drift |
| 🟠 Orange | `3–8%` — notable divergence |
| 🔴 Red | `≥ 8%` — forecast has lost accuracy |

### Hover
Hovering a `Δ%` cell shows the raw interpolated forecast value (`forecast: 16528.xxx`) as a tooltip title.

---

## State / Refs Used

| Name | Type | Purpose |
|------|------|---------|
| `liveErrRef` | `useRef<SecondRecord[]>` | Divergence log entries, newest first, max 300 |
| `trackedSecsRef` | `useRef<Set<string>>` | Dedup — prevents logging the same second twice |
| `cumErrRef` | `useRef<Partial<Record<ModelKey,number>>>` | Running loss per model |
| `errTick` | `useState<number>` | Incremented when `liveErrRef` changes, forces React re-render |
| `forecastRef` | `useRef<ForecastResponse>` | Frozen forecast — read by divergence tracker but never mutated by it |

All divergence state is reset when `tagId` changes (inside the `dataEndRef` init `useEffect`).

---

## SecondRecord Type

```ts
interface SecondRecord {
  ts:      string;                              // ISO timestamp (raw second)
  actual:  number;                              // raw sensor value
  fcVals:  Partial<Record<ModelKey, number>>;   // interpolated forecast per model
  errAbs:  Partial<Record<ModelKey, number>>;   // |actual - forecast|
  errPct:  Partial<Record<ModelKey, number>>;   // % divergence
}
```

---

## Key Design Decisions

### 1. Two separate API calls per second
The main actuals call uses `resample_minutes: 1` — it gives one averaged value per minute, good for the chart. The divergence call omits `resample_minutes` to get raw second-level data — needed to measure forecast accuracy at second resolution.

### 2. Never mutate the forecast
`forecastRef.current` is written only by `doFetchForecast()`. The divergence tracker and chart builder read it but never write to it. This is enforced by the ref pattern — no state setter involved.

### 3. Dedup by second key
`trackedSecsRef` holds every second timestamp that has already been logged. On each poll cycle, raw rows that already exist in this set are skipped immediately. This prevents the same second from appearing twice if the API returns overlapping time ranges.

### 4. Non-blocking divergence fetch
The raw 2-min fetch is wrapped in its own `try/catch` inside `refreshActuals`. If it fails (e.g. network blip), the divergence log simply stops growing for that cycle — the main actual chart and the accuracy log are unaffected.

### 5. ΣLOSS accumulator
`cumErrRef[model]` accumulates raw absolute error (not %). This gives a sense of total forecast loss over time:
- A model with low `Δ%` per second but many seconds will eventually have a high `ΣLOSS`
- A model that diverges sharply in a short burst also shows high `ΣLOSS`
- It is the most honest long-run accuracy signal visible without running a full evaluation

---

## Forecast Regeneration Logic

```
On modal open:
  1. Fetch tag metadata → determine dataEndRef (last_seen if > 5 min ago, else now)
  2. doFetchForecast() fires once → forecastRef set → setForecast() for chart

Every second:
  refreshActuals() runs
  → if real time > last forecast timestamp:
      NOT triggered here. Separate scheduleHorizonCheck() timer handles this.

scheduleHorizonCheck():
  delay = max(60s, lastForecastTimestamp - now)
  setTimeout → doFetchForecast() → scheduleHorizonCheck() (re-arms)
```

This means forecast is regenerated at most once every 30 minutes, only when the horizon actually expires. It never happens on every second poll.

---

## Files Changed (May 2026)

| File | Change |
|------|--------|
| `PredictiveTrendModal.tsx` | Fixed actual window end to use `new Date()` (was frozen to modal-open time) |
| `PredictiveTrendModal.tsx` | Added `SecondRecord` type |
| `PredictiveTrendModal.tsx` | Added `interpolateForecast()` helper |
| `PredictiveTrendModal.tsx` | Added `liveErrRef`, `trackedSecsRef`, `cumErrRef`, `errTick` state |
| `PredictiveTrendModal.tsx` | Reset divergence state on tag change |
| `PredictiveTrendModal.tsx` | Added raw 2-min fetch + per-second error calculation inside `refreshActuals` |
| `PredictiveTrendModal.tsx` | Replaced `FORECAST vs REAL LOG` panel with `⚡ LIVE DIVERGENCE LOG` panel |
| `PredictiveTrendModal.tsx` | Updated header subtitle |
