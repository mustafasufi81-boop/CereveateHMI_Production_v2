"""
Backtest forecast accuracy for Triangle Waves.Int1.

Method (proper backtesting — no peeking into the future):
  1. Pick a cutoff 35 minutes in the past (so 30 forecast steps have already occurred).
  2. Call /api/bi/forecast with training window = [cutoff-2h, cutoff].
  3. The model produces 30 predicted values for (cutoff+1min … cutoff+30min).
  4. Fetch the actual DB values for that same 30-minute window.
  5. Match predicted vs actual at the same minute and compute MAE/RMSE.

This answers the exact question: "how far off is the model when predicting
the next 30 minutes from a known cutoff point?"
"""
import requests, psycopg2
from datetime import datetime, timezone, timedelta

API  = "http://localhost:6001"
TAG  = "Triangle Waves.Int1"
DB   = dict(host="localhost", dbname="Automation_DB", user="cereveate", password="cereveate@222")
# Cutoff: 35 min ago  → 30 forecast steps have already elapsed → full comparison possible
CUTOFF_OFFSET_MIN = 35
STEPS = 30

# ── Auth ──────────────────────────────────────────────────────────────────────
r = requests.post(f"{API}/api/auth/login", json={"username":"Mustafa","password":"Admin@123"})
token = r.json()["token"]
H = {"Authorization": f"Bearer {token}"}

# ── Build backtest window ──────────────────────────────────────────────────────
now    = datetime.now(timezone.utc)
cutoff = now - timedelta(minutes=CUTOFF_OFFSET_MIN)   # forecast origin (in the past)
train_start = cutoff - timedelta(hours=2)

print(f"System UTC now : {now.isoformat()}")
print(f"Forecast origin: {cutoff.isoformat()}  (= now - {CUTOFF_OFFSET_MIN} min)")
print(f"Forecast covers: {(cutoff + timedelta(minutes=1)).isoformat()}  →  {(cutoff + timedelta(minutes=STEPS)).isoformat()}")

# ── Call forecast API ──────────────────────────────────────────────────────────
body = {"tag_id": TAG, "start": train_start.isoformat(), "end": cutoff.isoformat(),
        "steps": STEPS, "resample_minutes": 1}
f = requests.post(f"{API}/api/bi/forecast", json=body, headers=H).json()

if not f.get("success"):
    print("Forecast API failed:", f); exit(1)

best    = f["best_model"]
ts_list = f["timestamps"]        # ISO strings: cutoff+1min … cutoff+30min
pts     = f["models"][best]["points"]

print(f"\nBest model : {best}")
print(f"n_history  : {f['n_history']} samples (resampled to 1-min)")
print(f"All models : { {k: round(v['mae'],2) if isinstance(v.get('mae'), float) else 'err' for k,v in f['models'].items()} }")
print()

# ── Also show FFT side-by-side if best model isn't FFT ────────────────────────
alt_model = None
if best != "FFT" and "FFT" in f["models"] and "points" in f["models"]["FFT"]:
    alt_model = "FFT"
    alt_pts   = f["models"]["FFT"]["points"]

# ── Fetch actual DB values for the forecast window ────────────────────────────
conn = psycopg2.connect(**DB)
cur  = conn.cursor()
cur.execute("""
    SELECT time AT TIME ZONE 'UTC', value_num
    FROM   historian_raw.historian_timeseries
    WHERE  tag_id  = %s
      AND  time    >= %s
      AND  time    <= %s
      AND  value_num IS NOT NULL
    ORDER  BY time ASC
""", (TAG, cutoff, cutoff + timedelta(minutes=STEPS + 2)))
actuals_raw = cur.fetchall()
conn.close()

# Build lookup: minute-truncated UTC → value (use first reading per minute)
actuals: dict[datetime, float] = {}
for ts_row, val in actuals_raw:
    minute_key = ts_row.replace(second=0, microsecond=0, tzinfo=timezone.utc)
    if minute_key not in actuals:
        actuals[minute_key] = float(val)

print(f"Actual DB rows in window: {len(actuals_raw)}  (unique minutes: {len(actuals)})")
print()

# ── Side-by-side comparison ───────────────────────────────────────────────────
print(f"{'Step':>4}  {'Forecast Timestamp (UTC)':>26}  {'Predicted':>10}  {'Actual':>10}  {'Error':>8}  {'AbsErr':>7}  {'FFT_pred':>9}  {'FFT_err':>8}")
print("-" * 95)
errors = []
fft_errors = []
for i, (ts_str, pred) in enumerate(zip(ts_list, pts)):
    fc_ts       = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    minute_key  = fc_ts.replace(second=0, microsecond=0)

    # Try exact minute, then ±1 minute tolerance
    actual = actuals.get(minute_key)
    if actual is None:
        for delta in [timedelta(minutes=1), timedelta(minutes=-1)]:
            actual = actuals.get(minute_key + delta)
            if actual is not None:
                break

    if actual is not None:
        err = actual - pred
        errors.append(abs(err))
        fft_col = ""
        if alt_model and i < len(alt_pts):
            fft_pred = alt_pts[i]
            fft_err  = actual - fft_pred
            fft_errors.append(abs(fft_err))
            fft_col  = f"{fft_pred:>9.2f}  {fft_err:>+8.2f}"
        bar = "█" * min(int(abs(err) / 5), 20)
        print(f"{i+1:>4}  {ts_str:>26}  {pred:>10.2f}  {actual:>10.2f}  {err:>+8.2f}  {abs(err):>7.2f}  {fft_col}  {bar}")
    else:
        print(f"{i+1:>4}  {ts_str:>26}  {pred:>10.2f}  {'—':>10}  {'':>8}  {'':>7}")

# ── Summary ───────────────────────────────────────────────────────────────────
print()
if errors:
    mae  = sum(errors) / len(errors)
    rmse = (sum(e**2 for e in errors) / len(errors)) ** 0.5
    pct  = mae / 182 * 100
    print(f"\n{'='*50}")
    print(f"  {best} (winner on holdout MAE)")
    print(f"  Matched  : {len(errors)}/{STEPS} steps")
    print(f"  MAE      : {mae:.2f}  ({pct:.1f}% of signal range ±91)")
    print(f"  RMSE     : {rmse:.2f}")
    print(f"  Max err  : {max(errors):.2f}")

    if fft_errors:
        fft_mae  = sum(fft_errors) / len(fft_errors)
        fft_rmse = (sum(e**2 for e in fft_errors) / len(fft_errors)) ** 0.5
        fft_pct  = fft_mae / 182 * 100
        print(f"\n  FFT (frequency extrapolation)")
        print(f"  MAE      : {fft_mae:.2f}  ({fft_pct:.1f}% of signal range)")
        print(f"  RMSE     : {fft_rmse:.2f}")
        if fft_mae < mae:
            print(f"\n  ⚠️  FFT is ACTUALLY BETTER over 30 min despite losing holdout MAE!")
            print(f"  → ARIMA overfits short-window holdout; FFT extrapolates period correctly.")
        else:
            print(f"\n  ✅  {best} correctly selected — better actual 30-min accuracy than FFT.")
    print('='*50)

    if mae < 10:
        print("\n✅  GOOD")
    elif mae < 25:
        print("\n⚠️  ACCEPTABLE — phase drift present")
    else:
        print("\n❌  POOR — model needs fix")
else:
    print(f"❌  No actual data found in forecast window.")
