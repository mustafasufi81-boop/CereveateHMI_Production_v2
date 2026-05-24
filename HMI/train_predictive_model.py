"""
Model Training & Walk-Forward Validation
==========================================
Fetches ALL available historian data for a tag,
trains each model on a rolling window,
tests on the next window (walk-forward CV),
reports RMSE / MAE / alarm-prediction accuracy,
and saves the best model params to historian_analytics.model_cache.

Models compared
---------------
Classic:
  lr       Linear Regression extrapolation (numpy polyfit)
  hw       Holt-Winters double exponential smoothing
  fft      FFT cycle reconstruction (top-k frequencies)
  arima    Auto-ARIMA (adaptive order search)

Advanced:
  kalman   Kalman Filter (state=[value, velocity])
           - Best for: noisy sensors, drifting signals
           - Online: updates with every new reading
           - Predicts n steps ahead analytically
           - No retraining needed; Q/R tuned from data noise

  seasonal_fft  FFT with auto-detected dominant period
           - Best for: known-periodic signals (pumps, turbines, waves)
           - Locks onto the dominant cycle frequency from training data
           - Outperforms plain FFT when period is stable

  lgbm     LightGBM on lag features (lags 1,2,3,5,10,20 + time index)
           - Best for: complex aperiodic industrial signals
           - Learns non-linear patterns from raw lag windows
           - Fast inference; tuned max_depth=4, n_estimators=100
           - Requires lgbm: pip install lightgbm

Run:
    python train_predictive_model.py
    python train_predictive_model.py "Triangle Waves.Int1"
    python train_predictive_model.py "Random.Real4"
"""

import sys, json, time, warnings
warnings.filterwarnings('ignore')
sys.path.insert(0, '.')

import numpy as np
import psycopg2, psycopg2.extras
from container import container
from datetime import datetime, timezone

TAG           = sys.argv[1] if len(sys.argv) > 1 else "Triangle Waves.Int1"
TRAIN_MINUTES = 60    # each training window (minutes of history)
TEST_MINUTES  = 10    # each test window  (minutes ahead to predict)
N_FOLDS       = 8     # number of walk-forward folds
HIHI_MARGIN   = 0.05
LOLO_MARGIN   = 0.05

# ─── 1. Load full history ─────────────────────────────────────────────────────
print(f"\n{'='*64}")
print(f"  Training: {TAG}")
print(f"  Walk-forward CV: {N_FOLDS} folds × {TRAIN_MINUTES}min train / {TEST_MINUTES}min test")
print(f"{'='*64}")

cfg  = container.config['database']
conn = psycopg2.connect(
    host=cfg['host'], port=int(cfg['port']),
    dbname=cfg['database'], user=cfg['user'], password=cfg['password']
)
cur = conn.cursor()

# Fetch enough data for all folds + some buffer
needed_min = (TRAIN_MINUTES + TEST_MINUTES) * (N_FOLDS + 2)
cur.execute("""
    SELECT EXTRACT(EPOCH FROM time)::float, value_num
    FROM   historian_raw.historian_timeseries
    WHERE  tag_id = %s
      AND  time > NOW() - (%s * INTERVAL '1 minute')
      AND  value_num IS NOT NULL
    ORDER  BY time ASC
""", (TAG, str(needed_min)))
rows = cur.fetchall()
cur.close()

if len(rows) < 200:
    print(f"[ERROR] Only {len(rows)} rows — need at least 200.")
    sys.exit(1)

ts_full  = np.array([r[0] for r in rows], dtype=float)
val_full = np.array([r[1] for r in rows], dtype=float)

sig_min, sig_max = float(val_full.min()), float(val_full.max())
sig_range = sig_max - sig_min
hihi = sig_max - HIHI_MARGIN * sig_range
lolo = sig_min + LOLO_MARGIN * sig_range

span_sec = float(ts_full[-1] - ts_full[0])
ppm = len(val_full) / max(span_sec / 60.0, 1.0)

print(f"\n  Loaded   : {len(val_full):,} points  ({span_sec/60:.0f} min of history)")
print(f"  Range    : {sig_min:.2f} → {sig_max:.2f}")
print(f"  HiHi     : {hihi:.2f}   LoLo: {lolo:.2f}")
print(f"  Rate     : {ppm:.1f} pts/min")

train_pts = int(round(TRAIN_MINUTES * ppm))
test_pts  = int(round(TEST_MINUTES  * ppm))

# Auto-detect dominant period from the full series via FFT
def _detect_period_pts(vals):
    """Return dominant cycle length in samples (0 = no clear period)."""
    n = len(vals)
    freqs = np.fft.rfft(vals - vals.mean())
    mags  = np.abs(freqs)
    mags[0] = 0   # suppress DC
    k = int(np.argmax(mags))
    return int(round(n / k)) if k > 0 else 0

PERIOD_PTS = _detect_period_pts(val_full)
period_min = PERIOD_PTS / max(ppm, 1.0)
print(f"  Train pts: {train_pts}   Test pts: {test_pts} per fold")
print(f"  Detected period: {PERIOD_PTS} pts = {period_min:.1f} min")

# ─── 2. Model functions ───────────────────────────────────────────────────────

def _downsample(arr, max_pts=300):
    if len(arr) <= max_pts:
        return arr
    idx = np.round(np.linspace(0, len(arr)-1, max_pts)).astype(int)
    return arr[idx]

def _resample_fc(fc, n_pts):
    """Stretch/shrink a forecast array to exactly n_pts."""
    fc = np.asarray(fc, dtype=float)
    if len(fc) == n_pts:
        return fc
    if len(fc) == 0:
        return np.zeros(n_pts)
    idx = np.round(np.linspace(0, len(fc)-1, n_pts)).astype(int)
    return fc[idx]

# ── LR ──────────────────────────────────────────────────────────────────────
def fit_predict_lr(train, n_pts):
    x = np.arange(len(train), dtype=float)
    c = np.polyfit(x, train, 1)
    x_fut = np.arange(len(train), len(train) + n_pts, dtype=float)
    return np.polyval(c, x_fut)

# ── HW ──────────────────────────────────────────────────────────────────────
def fit_predict_hw(train, n_pts):
    try:
        from statsmodels.tsa.holtwinters import ExponentialSmoothing
        t   = _downsample(train, 300)
        fit = ExponentialSmoothing(t, trend='add', seasonal=None).fit(optimized=True)
        fc_pts = max(int(round(n_pts * len(t) / len(train))), n_pts)
        return _resample_fc(fit.forecast(fc_pts), n_pts)
    except Exception:
        return None

# ── FFT (plain) ──────────────────────────────────────────────────────────────
def fit_predict_fft(train, n_pts, top_k=5):
    n     = len(train)
    freqs = np.fft.rfft(train)
    idx   = np.argsort(np.abs(freqs))[-top_k:]
    t_fut = np.arange(n, n + n_pts)
    result = np.zeros(n_pts)
    for k in idx:
        if k == 0:
            result += freqs[0].real / n
        else:
            amp   = 2 * np.abs(freqs[k]) / n
            phase = np.angle(freqs[k])
            result += amp * np.cos(2 * np.pi * k * t_fut / n + phase)
    return result

# ── ARIMA ────────────────────────────────────────────────────────────────────
def fit_predict_arima(train, n_pts):
    try:
        from statsmodels.tsa.arima.model import ARIMA
        t = _downsample(train, 200)
        best_fit, best_aic = None, float('inf')
        for order in [(1,0,1),(1,1,1),(2,1,1),(0,1,1)]:
            try:
                fit = ARIMA(t, order=order).fit()
                if fit.aic < best_aic:
                    best_aic, best_fit = fit.aic, fit
            except Exception:
                continue
        if best_fit is None:
            return None, None
        n_pts_ds = max(int(round(n_pts * len(t) / len(train))), 10)
        return _resample_fc(best_fit.forecast(n_pts_ds), n_pts), best_fit.order
    except Exception:
        return None, None

# ── KALMAN FILTER ────────────────────────────────────────────────────────────
# State vector: [value, velocity]
# Transition:   x(t+1) = F·x(t) + w   (constant velocity model)
# Observation:  z(t)   = H·x(t) + v
# Q (process noise) and R (measurement noise) tuned from data.
# This is optimal for: noisy sensors, drift, ramp failures.
# It naturally produces a confidence band from the error covariance P.
def fit_predict_kalman(train, n_pts):
    dt = 1.0   # 1 sample timestep
    F  = np.array([[1, dt], [0, 1]])    # constant-velocity transition
    H  = np.array([[1, 0]])             # we observe position only
    # Tune Q (process noise) from variance of 2nd differences
    acc_var = float(np.var(np.diff(np.diff(train)))) if len(train) > 2 else 1.0
    Q  = np.array([[0.25*dt**4, 0.5*dt**3],
                   [0.5*dt**3,  dt**2    ]]) * max(acc_var, 1e-6)
    # Tune R (measurement noise) from residual of linear fit
    x  = np.arange(len(train), dtype=float)
    c  = np.polyfit(x, train, 1)
    res_var = float(np.var(train - np.polyval(c, x)))
    R  = np.array([[max(res_var, 1e-6)]])

    # Initial state: [last value, average slope]
    slope  = float(c[0])
    state  = np.array([[train[-1]], [slope]])
    P      = np.eye(2) * res_var

    # Forward Kalman update on training data (warm-up pass)
    for z in train[-min(len(train), 200):]:
        state = F @ state
        P     = F @ P @ F.T + Q
        S     = H @ P @ H.T + R
        K     = P @ H.T @ np.linalg.inv(S)
        inn   = np.array([[z]]) - H @ state
        state = state + K @ inn
        P     = (np.eye(2) - K @ H) @ P

    # Predict n_pts steps ahead
    forecast = np.zeros(n_pts)
    conf_half = np.zeros(n_pts)    # 1-sigma half-width (for confidence band)
    s, Ps = state.copy(), P.copy()
    for i in range(n_pts):
        s  = F @ s
        Ps = F @ Ps @ F.T + Q
        forecast[i]   = float(s[0, 0])
        conf_half[i]  = float(np.sqrt(max((H @ Ps @ H.T)[0,0], 0)))

    return forecast, conf_half

# ── SEASONAL FFT (period-locked) ─────────────────────────────────────────────
# Same as FFT but only keeps harmonics of the dominant detected period.
# For a 5-min triangle wave: k=1 (fundamental) + k=3,5,7 (odd harmonics).
# Eliminates noise from non-periodic frequency leakage.
def fit_predict_seasonal_fft(train, n_pts, period_pts=None):
    if period_pts is None or period_pts < 4:
        return fit_predict_fft(train, n_pts, top_k=5)   # fallback to plain FFT
    n     = len(train)
    freqs = np.fft.rfft(train)
    # Keep only harmonics of the fundamental period
    fundamental_k = max(round(n / period_pts), 1)
    harmonic_ks   = [fundamental_k * h for h in range(1, 8)
                     if fundamental_k * h < len(freqs)]
    # Always keep DC (k=0)
    mask = np.zeros(len(freqs), dtype=complex)
    mask[0]          = freqs[0]
    for k in harmonic_ks:
        mask[k] = freqs[k]
    t_fut  = np.arange(n, n + n_pts)
    result = np.full(n_pts, freqs[0].real / n)
    for k in harmonic_ks:
        amp   = 2 * np.abs(freqs[k]) / n
        phase = np.angle(freqs[k])
        result += amp * np.cos(2 * np.pi * k * t_fut / n + phase)
    return result

# ── LightGBM on lag features ─────────────────────────────────────────────────
# Converts the time series into a supervised learning problem.
# Features: lags [1,2,3,5,10,20,50], time index.
# Best for: complex aperiodic signals, multi-modal distributions.
# Limitation: can't extrapolate beyond training range; predicts 1-step, iterated.
LGBM_LAGS = [1, 2, 3, 5, 10, 20, 50]

def _make_lag_features(vals, lags):
    max_lag = max(lags)
    X, y = [], []
    for i in range(max_lag, len(vals)):
        row = [vals[i - l] for l in lags] + [i]
        X.append(row)
        y.append(vals[i])
    return np.array(X), np.array(y)

def fit_predict_lgbm(train, n_pts):
    try:
        import lightgbm as lgb
        max_lag = max(LGBM_LAGS)
        if len(train) < max_lag + 20:
            return None
        X_tr, y_tr = _make_lag_features(train, LGBM_LAGS)
        model = lgb.LGBMRegressor(
            n_estimators=100, max_depth=4, learning_rate=0.1,
            num_leaves=15, min_child_samples=10, verbose=-1,
        )
        model.fit(X_tr, y_tr)
        # Iterated 1-step forecast
        history = list(train[-max_lag:])
        forecast = []
        for i in range(n_pts):
            row = np.array([[history[-l] for l in LGBM_LAGS] + [len(train) + i]])
            pred = float(model.predict(row)[0])
            forecast.append(pred)
            history.append(pred)
        return np.array(forecast)
    except ImportError:
        return None   # lgbm not installed
    except Exception:
        return None

# ─── 3. Walk-forward CV ───────────────────────────────────────────────────────

ALL_MODELS = ['lr', 'hw', 'fft', 'arima', 'kalman', 'seasonal_fft', 'lgbm']
total     = len(val_full)
fold_size = max((total - train_pts) // N_FOLDS, 1)

metrics = {m: {'rmse': [], 'mae': [], 'alarm_correct': []} for m in ALL_MODELS}
best_arima_order   = None
kalman_conf_final  = None

col_w = 11
header = f"  {'Fold':<5}" + "".join(f"{m.upper():>{col_w}}" for m in ALL_MODELS)
print(f"\n  Running {N_FOLDS} walk-forward folds...")
print(header)
print(f"  {'-'*(5 + col_w*len(ALL_MODELS))}")

for fold in range(N_FOLDS):
    start     = fold * fold_size
    end_train = start + train_pts
    end_test  = end_train + test_pts
    if end_test > total:
        break

    train = val_full[start:end_train]
    test  = val_full[end_train:end_test]
    n_pts = len(test)

    actual_hihi = any(v >= hihi for v in test)
    actual_lolo = any(v <= lolo for v in test)

    def _record(name, fc):
        if fc is None:
            return float('inf')
        fc = np.asarray(fc, dtype=float)
        rmse = float(np.sqrt(np.mean((fc - test)**2)))
        mae  = float(np.mean(np.abs(fc - test)))
        pred_hi = any(v >= hihi for v in fc)
        pred_lo = any(v <= lolo for v in fc)
        metrics[name]['rmse'].append(rmse)
        metrics[name]['mae'].append(mae)
        metrics[name]['alarm_correct'].append(
            (actual_hihi == pred_hi) and (actual_lolo == pred_lo))
        return rmse

    fold_r = {}
    fold_r['lr']           = _record('lr',           fit_predict_lr(train, n_pts))
    fold_r['hw']           = _record('hw',           fit_predict_hw(train, n_pts))
    fold_r['fft']          = _record('fft',          fit_predict_fft(train, n_pts))
    fc_ar, ar_ord          = fit_predict_arima(train, n_pts)
    fold_r['arima']        = _record('arima',        fc_ar)
    if ar_ord and not best_arima_order:
        best_arima_order = list(ar_ord)
    fc_kal, kal_conf       = fit_predict_kalman(train, n_pts)
    fold_r['kalman']       = _record('kalman',       fc_kal)
    if fold == N_FOLDS - 1:
        kalman_conf_final = kal_conf
    fold_r['seasonal_fft'] = _record('seasonal_fft', fit_predict_seasonal_fft(train, n_pts, PERIOD_PTS))
    fold_r['lgbm']         = _record('lgbm',         fit_predict_lgbm(train, n_pts))

    def _fmt(v):
        return f"{v:>{col_w}.2f}" if v != float('inf') else f"{'FAILED':>{col_w}}"
    row = f"  {fold+1:<5}" + "".join(_fmt(fold_r[m]) for m in ALL_MODELS)
    print(row)

# ─── 4. Summary ───────────────────────────────────────────────────────────────

print(f"\n{'='*75}")
print(f"  WALK-FORWARD CV RESULTS  ({N_FOLDS} folds × {TEST_MINUTES}min test window)")
print(f"{'='*75}")
print(f"  {'Model':<14}  {'Avg RMSE':>10}  {'Avg MAE':>10}  {'RMSE/range':>11}  {'Alarm Acc':>10}  {'Folds':>6}")
print(f"  {'-'*65}")

best_model = None
best_rmse  = float('inf')
summary    = {}

# Model explanations for the printout
MODEL_WHY = {
    'lr':           'linear slope extrapolation',
    'hw':           'double exponential smoothing',
    'fft':          'FFT top-5 frequency reconstruction',
    'arima':        'auto ARIMA (adaptive order)',
    'kalman':       'Kalman filter [value, velocity] state',
    'seasonal_fft': f'FFT locked to detected period ({period_min:.1f} min)',
    'lgbm':         'LightGBM on lag features',
}

for model in ALL_MODELS:
    m = metrics[model]
    if not m['rmse']:
        print(f"  {model.upper():<14}  {'NO DATA / not installed':>10}")
        continue
    avg_rmse  = float(np.mean(m['rmse']))
    avg_mae   = float(np.mean(m['mae']))
    pct_range = avg_rmse / sig_range * 100
    alarm_acc = float(np.mean(m['alarm_correct'])) * 100 if m['alarm_correct'] else 0.0
    folds_ok  = len(m['rmse'])
    flag = ' ◄' if (best_model is None or avg_rmse < best_rmse) else ''
    print(f"  {model.upper():<14}  {avg_rmse:>10.2f}  {avg_mae:>10.2f}  {pct_range:>10.1f}%  {alarm_acc:>9.0f}%  {folds_ok:>6}{flag}")
    summary[model] = {
        'avg_rmse': avg_rmse, 'avg_mae': avg_mae,
        'alarm_accuracy_pct': alarm_acc, 'folds': folds_ok,
        'why': MODEL_WHY.get(model, ''),
    }
    if avg_rmse < best_rmse:
        best_rmse, best_model = avg_rmse, model

print(f"\n  ✅ BEST MODEL : {best_model.upper()}  —  {MODEL_WHY.get(best_model,'')}")
print(f"     Avg RMSE  : {best_rmse:.2f}  ({best_rmse/sig_range*100:.1f}% of signal range)")
if best_model == 'kalman':
    print(f"     Confidence: Kalman provides ±1σ confidence bands for free")
if best_model == 'seasonal_fft':
    print(f"     Period     : {period_min:.1f} min detected and locked in")
if kalman_conf_final is not None:
    print(f"     Kalman ±1σ (last fold, pt 1): ±{kalman_conf_final[0]:.2f}")

# ─── 5. Save to model_cache ───────────────────────────────────────────────────

print(f"\n  Saving results to historian_analytics.model_cache ...")
cur2 = conn.cursor()
cur2.execute("SELECT to_regclass('historian_analytics.model_cache')")
schema_exists = cur2.fetchone()[0] is not None

if schema_exists:
    for model, s in summary.items():
        params: dict = {}
        if model == 'arima' and best_arima_order:
            params = {'order': best_arima_order}
        elif model in ('fft', 'seasonal_fft'):
            params = {'top_k': 5, 'period_pts': int(PERIOD_PTS)}
        elif model == 'kalman':
            params = {'period_pts': int(PERIOD_PTS)}
        elif model == 'lgbm':
            params = {'lags': LGBM_LAGS}

        cur2.execute("""
            INSERT INTO historian_analytics.model_cache
                (tag_id, model, rmse, mae, drift_score, tuned_params_json, fitted_at)
            VALUES (%s, %s, %s, %s, 0.0, %s, NOW())
            ON CONFLICT (tag_id, model) DO UPDATE SET
                rmse              = EXCLUDED.rmse,
                mae               = EXCLUDED.mae,
                drift_score       = 0.0,
                tuned_params_json = EXCLUDED.tuned_params_json,
                fitted_at         = EXCLUDED.fitted_at
        """, (TAG, model, s['avg_rmse'], s['avg_mae'],
              json.dumps(params) if params else None))
    conn.commit()
    print(f"  ✅ Saved {len(summary)} model metrics to model_cache")

    cur2.execute("SELECT to_regclass('historian_analytics.tag_alarm_config')")
    if cur2.fetchone()[0]:
        cur2.execute("""
            UPDATE historian_analytics.tag_alarm_config
            SET    preferred_model = %s
            WHERE  tag_id = %s
              AND  preferred_model = 'auto'
        """, (best_model, TAG))
        if cur2.rowcount:
            conn.commit()
            print(f"  ✅ preferred_model set to '{best_model}' for {TAG}")
        else:
            conn.commit()
            print(f"  ℹ  Tag not in tag_alarm_config yet (or preferred_model already set)")
else:
    print("  ⚠  historian_analytics schema not found — run migration 025 first")
    print("     Results not saved. Run:")
    print("     psql -f migrations/025_predictive_alarms_schema.sql")

cur2.close(); conn.close()

print(f"\n  SQL to apply manually if needed:")
print(f"    UPDATE historian_analytics.tag_alarm_config")
print(f"    SET preferred_model = '{best_model}'")
print(f"    WHERE tag_id = '{TAG}';")
print(f"{'='*64}\n")
