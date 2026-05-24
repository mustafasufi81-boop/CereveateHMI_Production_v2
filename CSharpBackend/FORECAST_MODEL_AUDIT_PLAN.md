# Forecast Model Audit Plan
## Why FFT was accurate before and why the backtest showed it as "catastrophic" — and what to fix

---

## 1. How Data Is Actually Fed Into Each Model (current code)

### Step 1 — Raw SQL query (`_get_timeseries_df`)
```sql
SELECT time, tag_id, value_num
FROM historian_raw.historian_timeseries
WHERE tag_id IN (...)
  AND time BETWEEN :start AND :end
  AND value_num IS NOT NULL
ORDER BY time ASC
```
- **Uses**: `value_num` column only. **Time is used as index.** Both value AND time matter.
- **start** = `now - 2 hours` (passed by TrendChart.tsx)
- **end** = `now` (the moment the browser calls the API)

### Step 2 — Resample to uniform 1-minute intervals
```python
df.resample("1min").mean().ffill(limit=3)
```
- Raw DB rows arrive at ~1s intervals (OPC polling)
- They are averaged into 1-minute bins → **n ≈ 120 rows for 2h window**
- Forward-fill up to 3 consecutive missing minutes (gaps allowed)
- **Output**: array `y[0..119]` — index = integer sample number (0, 1, 2…), NOT real timestamps
- **THIS IS THE KEY ISSUE** — explained below in Section 3

### Step 3 — Train/test split (holdout)
```
y[0..119]  total 120 samples
  train = y[0..89]   (75%)
  test  = y[90..119] (25% = last 30 minutes)
```

### Step 4 — Each model trains on `train`, scores against `test`

### Step 5 — Best model selected by lowest MAE on holdout

### Step 6 — Best model refit on full `y[0..119]`, forecasts steps 1..30

### Step 7 — `_shape_forecast()` applies exponential anchor correction
- Forces `pts[0] ≈ y[-1]` (last actual value) via decay curve over first 20% of horizon
- This is a **visual smoothing**, not a physical correction
- Clips all points to `[recent_min - pad, recent_max + pad]`

### Step 8 — Timestamps for forecast output
```python
future_ts[i] = anchor_ts + timedelta(minutes=i+1)
```
Where `anchor_ts = body["end"]` (the `now` passed by the caller)

---

## 2. How Each Model Uses Time and Values

| Model | What it trains on | Does it use real timestamps? | What it predicts |
|-------|------------------|------------------------------|-----------------|
| **LR** | `y` values at integer positions `[0,1,2…n]` | ❌ No — index only | Linear trend extrapolated to `[n, n+1…n+30]` |
| **FFT** | `y` values as a periodic signal sampled at **uniform 1-min grid** | ✅ Yes — assumes uniform spacing, extrapolates phase | Future 30 values at positions `[n, n+30]` |
| **HW** | `y` values + ACF-detected period (integer samples) | ✅ Partially — detects period in samples | 30 future seasonal + trend values |
| **ARIMA** | `y` values only (no time axis) — autoregressive lags | ❌ No — index only | 30 future values from recent lag pattern |

**Critical fact**: ALL models treat input as a sequence of equally-spaced samples. The 1-minute resampling step is what converts real wall-clock time into uniform integer positions. If resampling is correct, the models are implicitly time-aware.

---

## 3. Root Cause of FFT "Catastrophic" Backtest vs "Accurate" Live Demo

### Why FFT was accurate in the live demo (first observation)
When you saw `Triangle Waves.Int1` predicted correctly with timing and value:

1. The training window happened to align the triangle period with the 2-hour window cleanly
2. FFT detected the dominant frequency `k` correctly → the period in samples `P = n/k` matched the true period
3. At step 5–10 ahead, the phase error was small → looked very accurate
4. `_shape_forecast` anchor correction made the first point join perfectly

### Why FFT showed MAE=90 in the backtest
This is **not catastrophic in reality** — it is a **backtest methodology mismatch**:

| Issue | Detail |
|-------|--------|
| **The backtest used a cutoff 35 minutes in the past** | So `end = now - 35min`, meaning `anchor_ts = now - 35min` |
| **The training window was `[now-2h35min, now-35min]`** | NOT the same window that produced the original accurate forecast |
| **Triangle wave period ≈ 9.8 min** | FFT with n=119 samples has frequency resolution `Δf = 1/119` → nearest period it can represent = 9 or 10 min exactly |
| **Phase alignment sensitivity** | A 35-minute-old cutoff means the signal has gone through ~3.5 full cycles. If the frequency resolution is off by even 1 sample, the phase at step 30 inverts completely |
| **`_shape_forecast` anchor correction fights FFT** | The exponential decay pulls `pts[0]` to `y[-1]`, distorting the frequency extrapolation in the first 20% of the window |

### Why ARIMA wins the backtest (MAE=25) but FFT could win the live demo
- **ARIMA** is autoregressive — it predicts "next value ≈ weighted sum of last few values". For a clean periodic signal, this works well for 5–15 steps. At 30 steps the cumulative errors grow.
- **FFT** is phase-based extrapolation — it works perfectly when the period divides evenly into `n`. When it doesn't, it's wrong. This is **not a data quality issue**, it is a mathematical limitation of discrete Fourier analysis.

---

## 4. The `_shape_forecast` Anchor Problem — Critical Bug

```python
def _shape_forecast(pts, model_name=""):
    anchor = float(y[-1])          # last actual sample value
    gap = anchor - float(arr[0])   # difference from model's first predicted point
    if abs(gap) > 1e-6:
        decay = np.exp(-np.arange(arr.size) / max(arr.size * 0.20, 2.0))
        arr = arr + gap * decay    # ← MODIFIES the model's physics over first 6 steps
```

**The problem**: For FFT, `pts[0]` is the model's extrapolated value at position `n` (correct by design). Forcing it toward `y[-1]` via an exponential decay **permanently distorts the phase of the extrapolated signal** for the first 6 steps. This makes the graph look smooth but introduces artificial error.

**The problem for ALL models**: `y[-1]` is the last value in the **resampled** 1-minute array, not the live OPC value at the moment of the API call. If the last DB write to the historian was 45 seconds ago and the signal has moved, `y[-1]` is stale.

---

## 5. Plan to Fix — Priority Order

### Fix 1 (CRITICAL): Remove `_shape_forecast` anchor distortion for FFT
FFT computes the exact phase-correct starting value already. The anchor correction should only be applied to models that don't guarantee continuity (LR, ARIMA).

```python
# In _shape_forecast: skip anchor correction for FFT
if model_name == "FFT":
    arr = np.clip(arr, _lower, _upper)
    return [round(float(v), 4) for v in arr]
# ... rest applies to LR, ARIMA, HW
```

### Fix 2 (CRITICAL): Score FFT on OUT-OF-SAMPLE data, not reconstruction
Currently FFT holdout score uses `reconstructed[-hold_n:]` — this is **in-sample** (the model has already seen this data). It will always score artificially low.

```python
# WRONG (current):
fft_test = reconstructed[-hold_n:].tolist()  # in-sample! model already fit this

# CORRECT: extrapolate from train only, score against test
fft_coeffs_train = np.fft.rfft(train)
# ... extrapolate train+1 to train+hold_n
# score those against test
```

This single bug explains why FFT shows holdout MAE=8 but actual backtest MAE=90. **The FFT holdout score is fake.**

### Fix 3 (HIGH): Add period alignment check for FFT
Before accepting FFT as best model, verify that the detected period `P = n/k_dominant` is close to an integer number of samples within ±5% tolerance. If not, FFT prediction will drift.

```python
P = n / k_dominant
if abs(P - round(P)) / P > 0.05:
    # Period doesn't divide evenly → FFT unreliable for extrapolation
    # Use HW or ARIMA instead
```

### Fix 4 (MEDIUM): Use live OPC value as anchor instead of `y[-1]`
When the chart calls the forecast API, also pass the current live tag value:
```json
{ "tag_id": "...", "start": "...", "end": "...", "steps": 30, "anchor_value": 64.0 }
```
Then use `anchor_value` instead of `y[-1]` in `_shape_forecast`. This eliminates DB lag error.

### Fix 5 (MEDIUM): Out-of-sample holdout for HW and ARIMA
Currently both HW and ARIMA train on `train`, score on `test`, then **refit on full `y`** for the final forecast. This means the final model has seen 30 additional samples compared to the scored model. The final forecast should come from the training-data-only fit (no refit on full y).

### Fix 6 (LOW): Frequency resolution improvement for FFT
Instead of `np.fft.rfft(y)` on integer samples, use zero-padding to increase frequency resolution:
```python
n_padded = max(n * 4, 512)
fft_coeffs = np.fft.rfft(y, n=n_padded)
freqs = np.fft.rfftfreq(n_padded)
```
This allows FFT to detect period 9.8 min correctly instead of rounding to 10 or 9.

---

## 6. What "Good" Accuracy Looks Like for This Signal

| Horizon | Good MAE | Acceptable MAE | Poor MAE |
|---------|----------|---------------|---------|
| 5 min | < 8 | 8–20 | > 20 |
| 15 min | < 15 | 15–35 | > 35 |
| 30 min | < 25 | 25–50 | > 50 |

Signal range = ±91 (total span 182 units)

Current ARIMA actual backtest:
- Steps 1–10: avg error ≈ **18 units** ✅ Acceptable
- Steps 11–20: avg error ≈ **27 units** ⚠️ Borderline
- Steps 21–30: avg error ≈ **29 units** ⚠️ Borderline

After Fix 1+2 (FFT scoring corrected), FFT should win on periodic signals and reduce 30-min error to ~12–18 units based on the clean phase extrapolation it provides when the period alignment is correct.

---

## 7. Implementation Order

```
Priority 1 — Implement NOW (fixes the fake scoring that corrupts model selection):
  ✅ Fix 2: FFT out-of-sample holdout score
  ✅ Fix 1: Remove anchor distortion for FFT

Priority 2 — Implement next:
  Fix 3: Period alignment guard
  Fix 4: Live anchor value from caller

Priority 3 — Polish:
  Fix 5: No-refit ARIMA/HW
  Fix 6: Zero-padded FFT
```
