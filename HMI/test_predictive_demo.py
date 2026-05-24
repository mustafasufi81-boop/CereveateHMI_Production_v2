"""
Predictive Alarm Demo
=====================
Uses live historian data for Triangle Waves.Int1.
  - Fetches last 60 minutes of real data
  - Derives HiHi / LoLo from actual signal min / max
  - Runs all 4 forecast models (LR, HW, FFT, ARIMA)
  - Prints ETA-to-alarm for each model

Run:  python test_predictive_demo.py
      python test_predictive_demo.py Random.Real4    (any other tag)
"""

import sys, json
sys.path.insert(0, '.')

import numpy as np
import psycopg2
from container import container
from datetime import datetime, timezone

TAG = sys.argv[1] if len(sys.argv) > 1 else "Triangle Waves.Int1"
LOOKBACK_MIN   = 60     # minutes of history to fetch
HORIZON_MIN    = 30     # how far ahead to forecast
HIHI_MARGIN    = 0.05   # HiHi = max - 5% of range  (so alarm fires near the top)
LOLO_MARGIN    = 0.05   # LoLo = min + 5% of range

# ─── 1. Fetch data ────────────────────────────────────────────────────────────
cfg  = container.config['database']
conn = psycopg2.connect(
    host=cfg['host'], port=int(cfg['port']),
    dbname=cfg['database'], user=cfg['user'], password=cfg['password']
)
cur = conn.cursor()
cur.execute("""
    SELECT EXTRACT(EPOCH FROM time)::float, value_num
    FROM   historian_raw.historian_timeseries
    WHERE  tag_id = %s
      AND  time > NOW() - (%s || ' minutes')::INTERVAL
      AND  value_num IS NOT NULL
    ORDER  BY time ASC
    LIMIT  6000
""", (TAG, str(LOOKBACK_MIN)))
rows = cur.fetchall()
cur.close(); conn.close()

if len(rows) < 30:
    print(f"[ERROR] Only {len(rows)} rows for '{TAG}' in last {LOOKBACK_MIN} min.")
    print("        Is the historian writing? Check OPC connection.")
    sys.exit(1)

ts_arr  = np.array([r[0] for r in rows], dtype=float)
val_arr = np.array([r[1] for r in rows], dtype=float)

sig_min, sig_max = float(val_arr.min()), float(val_arr.max())
sig_range = sig_max - sig_min

hihi = sig_max - HIHI_MARGIN * sig_range
lolo = sig_min + LOLO_MARGIN * sig_range
current_val = float(val_arr[-1])

print("=" * 62)
print(f"  Tag          : {TAG}")
print(f"  History      : {len(val_arr)} points over last {LOOKBACK_MIN} min")
print(f"  Current value: {current_val:.2f}")
print(f"  Signal range : {sig_min:.2f}  →  {sig_max:.2f}")
print(f"  HiHi limit   : {hihi:.2f}  (= max - {HIHI_MARGIN*100:.0f}% range)")
print(f"  LoLo limit   : {lolo:.2f}  (= min + {LOLO_MARGIN*100:.0f}% range)")
print("=" * 62)

# ─── 2. Forecast helpers ──────────────────────────────────────────────────────
span_sec = float(ts_arr[-1] - ts_arr[0])
ppm      = len(val_arr) / max(span_sec / 60.0, 1.0)   # points per minute
horizon_pts = max(int(round(HORIZON_MIN * ppm)), 10)

print(f"\n  Points/min   : {ppm:.1f}")
print(f"  Forecast pts : {horizon_pts}  ({HORIZON_MIN} min ahead)")


def eta_to_breach(forecast: np.ndarray, limit: float, direction: str) -> float | None:
    """Return minutes to first breach, or None if no breach in horizon."""
    for i, v in enumerate(forecast):
        if direction == "HIGH" and v >= limit:
            return round((i + 1) / max(ppm, 0.01), 2)
        if direction == "LOW" and v <= limit:
            return round((i + 1) / max(ppm, 0.01), 2)
    return None


def run_lr(vals, pts):
    x = np.arange(len(vals), dtype=float)
    c = np.polyfit(x, vals, 1)
    return np.polyval(c, np.arange(len(vals), len(vals) + pts, dtype=float))


def run_hw(vals, pts):
    try:
        from statsmodels.tsa.holtwinters import ExponentialSmoothing
        fit = ExponentialSmoothing(vals, trend='add', seasonal=None).fit(optimized=True, disp=False)
        return fit.forecast(pts)
    except Exception as e:
        return None


def run_fft(vals, pts, top_k=5):
    n     = len(vals)
    freqs = np.fft.rfft(vals)
    idx   = np.argsort(np.abs(freqs))[-top_k:]
    t_fut = np.arange(n, n + pts)
    result = np.zeros(pts)
    for k in idx:
        if k == 0:
            result += freqs[0].real / n
        else:
            amp   = 2 * np.abs(freqs[k]) / n
            phase = np.angle(freqs[k])
            result += amp * np.cos(2 * np.pi * k * t_fut / n + phase)
    return result


def run_arima(vals, pts):
    try:
        from statsmodels.tsa.arima.model import ARIMA
        best_fit, best_aic = None, float('inf')
        for order in [(1,0,1),(1,1,1),(2,1,1)]:
            try:
                fit = ARIMA(vals, order=order).fit()
                if fit.aic < best_aic:
                    best_aic, best_fit = fit.aic, fit
            except Exception:
                continue
        return best_fit.forecast(pts) if best_fit else None
    except Exception as e:
        return None


# ─── 3. Run models + check limits ────────────────────────────────────────────
models = {
    "LR":    run_lr(val_arr, horizon_pts),
    "HW":    run_hw(val_arr, horizon_pts),
    "FFT":   run_fft(val_arr, horizon_pts),
    "ARIMA": run_arima(val_arr, horizon_pts),
}

print("\n" + "-" * 62)
print(f"  {'Model':<8}  {'Status':<10}  {'HiHi breach':<18}  {'LoLo breach'}")
print("-" * 62)

results = {}
for name, fc in models.items():
    if fc is None:
        print(f"  {name:<8}  {'FAILED':<10}  {'—':<18}  —")
        continue
    fc = np.array(fc, dtype=float)
    eta_hi = eta_to_breach(fc, hihi, "HIGH")
    eta_lo = eta_to_breach(fc, lolo, "LOW")
    hi_str = f"{eta_hi:.1f} min" if eta_hi is not None else "not in horizon"
    lo_str = f"{eta_lo:.1f} min" if eta_lo is not None else "not in horizon"
    print(f"  {name:<8}  {'OK':<10}  {hi_str:<18}  {lo_str}")
    results[name] = {'fc': fc, 'eta_hi': eta_hi, 'eta_lo': eta_lo}

print("-" * 62)

# ─── 4. Best prediction summary ──────────────────────────────────────────────
all_hi = {k: v['eta_hi'] for k, v in results.items() if v['eta_hi'] is not None}
all_lo = {k: v['eta_lo'] for k, v in results.items() if v['eta_lo'] is not None}

print()
if all_hi:
    best_hi_model = min(all_hi, key=all_hi.get)
    print(f"  ⚠  EARLIEST HiHi alarm: {all_hi[best_hi_model]:.1f} min  (model: {best_hi_model})")
    breach_ts = datetime.now(timezone.utc)
    from datetime import timedelta
    breach_ts += timedelta(minutes=all_hi[best_hi_model])
    print(f"     Projected breach at : {breach_ts.strftime('%H:%M:%S')} UTC")
else:
    print(f"  ✓  No HiHi breach predicted in next {HORIZON_MIN} min")

if all_lo:
    best_lo_model = min(all_lo, key=all_lo.get)
    print(f"  ⚠  EARLIEST LoLo alarm: {all_lo[best_lo_model]:.1f} min  (model: {best_lo_model})")
    breach_ts = datetime.now(timezone.utc)
    breach_ts += timedelta(minutes=all_lo[best_lo_model])
    print(f"     Projected breach at : {breach_ts.strftime('%H:%M:%S')} UTC")
else:
    print(f"  ✓  No LoLo breach predicted in next {HORIZON_MIN} min")

print()
print("  To adopt best model permanently:")
print(f"    UPDATE historian_analytics.tag_alarm_config")
print(f"    SET preferred_model = '<model>' WHERE tag_id = '{TAG}';")
print("=" * 62)
