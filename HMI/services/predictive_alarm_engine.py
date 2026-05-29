"""
Predictive Alarm Engine — 2-Stage Background Worker
=====================================================
Stage 1 (Screener):  numpy-only, ~15-30 s, runs every SCREEN_INTERVAL_SEC seconds.
                     Computes slope + variance across all enabled tags.
                     Tags with |slope| > sigma_threshold are flagged 'suspicious'.

Stage 2 (Forecaster): statsmodels/numpy, ~60 s per batch.
                      Only runs for suspicious tags.
                      Fits LR / HW / FFT / ARIMA (or preferred_model).
                      Projects horizon forward; raises predictive_alarm row if a
                      limit will be breached.

State persistence: screener state, suppression windows, and drift scores are
written to PostgreSQL so a Flask restart is a warm restart, not a cold start.

Public API (called from predictive_alarm_controller.py):
    engine_instance()         → singleton PredictiveAlarmEngine
    engine.status()           → dict with running/cycle counts/last errors
    engine.start() / stop()
"""

from __future__ import annotations

import json
import logging
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import psycopg2
import psycopg2.extras
import psycopg2.pool

from container import container

logger = logging.getLogger(__name__)

# ─── Tunable constants ────────────────────────────────────────────────────────
SCREEN_INTERVAL_SEC    = 60       # how often Stage 1 runs
STAGE2_TIMEOUT_SEC     = 8        # per-model fit timeout
MIN_POINTS_SCREEN      = 30       # minimum historian rows needed to screen
MIN_POINTS_FORECAST    = 60       # minimum rows for a good forecast
LOOKBACK_MINUTES       = 60       # historian window fed to both stages
SLOPE_SIGMA_MULTIPLIER = 0.5      # |slope| > multiplier*σ → suspicious
CPU_SUSPEND_THRESHOLD  = 85       # % — suspend Stage 2 above this

# Shared executor (no per-call create/destroy)
_MODEL_EXECUTOR = ThreadPoolExecutor(max_workers=6, thread_name_prefix="pred_model_")

# ─── DB pool ─────────────────────────────────────────────────────────────────
_pool: psycopg2.pool.ThreadedConnectionPool | None = None
_pool_lock = threading.Lock()


def _get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    global _pool
    if _pool is not None:
        return _pool
    with _pool_lock:
        if _pool is None:
            cfg = container.config['database']
            _pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=1, maxconn=4,
                host=cfg['host'], port=int(cfg['port']),
                dbname=cfg['database'], user=cfg['user'],
                password=cfg['password'],
                keepalives=1, keepalives_idle=60,
                connect_timeout=10,
                options="-c statement_timeout=30000 -c application_name=pred_alarm_engine",
            )
            logger.info("[Engine] DB pool created: %s@%s", cfg['database'], cfg['host'])
    return _pool


@contextmanager
def _conn():
    pool = _get_pool()
    conn = None
    try:
        conn = pool.getconn()
        yield conn
    except Exception:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        raise
    finally:
        if conn:
            pool.putconn(conn)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _cpu_pct() -> float:
    """Return system CPU% or 0 if psutil unavailable."""
    try:
        import psutil
        return psutil.cpu_percent(interval=0.3)
    except ImportError:
        return 0.0


def _run_with_timeout(fn, timeout_sec: float = STAGE2_TIMEOUT_SEC):
    """Submit fn to shared executor; return result or None on timeout/error."""
    future = _MODEL_EXECUTOR.submit(fn)
    try:
        return future.result(timeout=timeout_sec)
    except FutureTimeout:
        logger.warning("[Engine] Model timed out after %ss", timeout_sec)
        return None
    except Exception as exc:
        logger.debug("[Engine] Model error: %s", exc)
        return None


def _fetch_historian(tag_id: str, minutes: int) -> Optional[np.ndarray]:
    """Return 1-D numpy array of float values from historian, newest last."""
    sql = """
        SELECT value_num
        FROM   historian_raw.historian_timeseries
        WHERE  tag_id = %s
          AND  time >= NOW() - (%s * INTERVAL '1 minute')
          AND  value_num IS NOT NULL
        ORDER  BY time ASC
        LIMIT  5000
    """
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (tag_id, minutes))
                rows = cur.fetchall()
        if not rows:
            return None
        return np.array([r[0] for r in rows], dtype=float)
    except Exception as exc:
        logger.warning("[Engine] Historian fetch failed for %s: %s", tag_id, exc)
        return None


def _fetch_historian_with_ts(tag_id: str, minutes: int) -> Tuple[np.ndarray, np.ndarray]:
    """Return (timestamps_epoch_float[], values[])."""
    sql = """
        SELECT EXTRACT(EPOCH FROM time), value_num
        FROM   historian_raw.historian_timeseries
        WHERE  tag_id = %s
          AND  time >= NOW() - (%s * INTERVAL '1 minute')
          AND  value_num IS NOT NULL
        ORDER  BY time ASC
        LIMIT  5000
    """
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (tag_id, minutes))
                rows = cur.fetchall()
        if not rows:
            return np.array([]), np.array([])
        ts  = np.array([r[0] for r in rows], dtype=float)
        val = np.array([r[1] for r in rows], dtype=float)
        return ts, val
    except Exception as exc:
        logger.warning("[Engine] Historian ts fetch failed for %s: %s", tag_id, exc)
        return np.array([]), np.array([])


# ─── Drift context helper ────────────────────────────────────────────────────

def _fetch_active_drift(tag_ids: List[str]) -> Dict[str, List[Dict]]:
    """
    Query PEWS early_warnings for unacknowledged drift rows in the last 2 hours.
    Returns {tag_id: [row, ...]} — empty list means no active drift for that tag.

    These rows are written by the PEWS statistical_engine CUSUM/EWMA detectors.
    The predictive engine uses them to:
      1. Force-flag a tag suspicious even when short-window slope is low.
      2. Escalate forecast confidence when drift direction matches breach direction.
    """
    if not tag_ids:
        return {}
    sql = """
        SELECT tag_id, warning_level, deviation_pct, message, time
        FROM   historian_analytics.early_warnings
        WHERE  tag_id      = ANY(%s)
          AND  warning_type = 'drift'
          AND  acknowledged  = FALSE
          AND  time          > NOW() - INTERVAL '2 hours'
        ORDER  BY time DESC
    """
    result: Dict[str, List[Dict]] = {}
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (tag_ids,))
                for row in cur.fetchall():
                    tid = row['tag_id']
                    result.setdefault(tid, []).append(dict(row))
    except Exception as exc:
        # Table may not exist yet (PEWS not deployed) — degrade gracefully
        logger.debug("[Engine] Drift context fetch skipped: %s", exc)
    return result


def _escalate_with_drift(breach: Dict, drift_rows: List[Dict]) -> Dict:
    """
    If the confirmed drift direction aligns with the projected breach direction,
    escalate the confidence level by one step.

    Example: tag is drifting UP (CUSUM fired, deviation_pct > 0) AND the
    forecast projects a HIHI breach → drift is *confirming* the forecast →
    raise confidence LOW→MEDIUM or MEDIUM→HIGH.

    If drift direction opposes the breach (tag drifting DOWN but breach is HIGH)
    we leave confidence unchanged — the two signals disagree, so we stay
    conservative.
    """
    breach_dir = breach.get('direction', '')
    drift_up   = any((r.get('deviation_pct') or 0) > 0 for r in drift_rows)
    drift_down = any((r.get('deviation_pct') or 0) < 0 for r in drift_rows)
    max_dev_pct = max(abs(r.get('deviation_pct') or 0) for r in drift_rows)

    direction_match = (
        ('HIGH' in breach_dir and drift_up) or
        ('LOW'  in breach_dir and drift_down)
    )

    result = dict(breach)
    if direction_match:
        conf_ladder = {'LOW': 'MEDIUM', 'MEDIUM': 'HIGH', 'HIGH': 'HIGH'}
        old_conf = result.get('confidence', 'LOW')
        result['confidence'] = conf_ladder.get(old_conf, old_conf)
        result['drift_confirmed'] = True   # flag carried into the alarm log
        logger.info(
            "[Engine] ⬆ Drift-escalated confidence %s → %s  "
            "(drift %.1f%% %s, breach dir=%s)",
            old_conf, result['confidence'],
            max_dev_pct, 'UP' if drift_up else 'DOWN', breach_dir,
        )
    return result


# ─── Stage 1: Screener ───────────────────────────────────────────────────────

def _screen_tag(tag_id: str) -> Dict[str, Any]:
    """
    Stage 1 screener — flags tags that need a full forecast in Stage 2.

    Three independent checks run in parallel; ANY one flagging suspicious
    causes the tag to proceed to Stage 2:

    1. SLOPE  — linear trend over the lookback window (existing check).
                Catches monotonic rises/falls (bearing wear, thermal creep).
                Problem: averages to ≈0 for symmetric periodic signals
                         (e.g. triangle wave, sine) — so check 2 is needed.

    2. AMPLITUDE — max/min of recent window vs configured hi/lo limits.
                Catches periodic signals whose peaks are already close to
                a limit, regardless of net slope.  Fires when:
                  max(vals) > hi_limit × AMPLITUDE_PROXIMITY_RATIO  OR
                  min(vals) < lo_limit × AMPLITUDE_PROXIMITY_RATIO
                (requires the tag's limits to be stored in DB)

    3. VARIANCE SHIFT — coefficient of variation has grown vs baseline.
                Catches signals that are becoming noisier/more erratic,
                which slope alone misses.
    """
    vals = _fetch_historian(tag_id, LOOKBACK_MINUTES)
    if vals is None or len(vals) < MIN_POINTS_SCREEN:
        return {
            'suspicious': False, 'reason': 'insufficient_data',
            'slope': 0.0, 'quality_score': 0.0,
            'n_points': 0 if vals is None else len(vals),
        }

    n     = len(vals)
    x     = np.arange(n, dtype=float)
    sigma = float(np.std(vals))

    if sigma < 1e-9:
        return {
            'suspicious': False, 'reason': 'flat_signal',
            'slope': 0.0, 'quality_score': 1.0, 'n_points': n,
        }

    # ── Check 1: Slope ────────────────────────────────────────────────────────
    coeffs    = np.polyfit(x, vals, 1)
    slope     = float(coeffs[0])
    threshold = SLOPE_SIGMA_MULTIPLIER * sigma / max(n, 1)
    slope_suspicious = abs(slope) > threshold

    fitted   = np.polyval(coeffs, x)
    residual = float(np.std(vals - fitted))
    quality  = max(0.0, 1.0 - residual / max(sigma, 1e-9))

    # ── Check 2: Amplitude proximity to configured limits ─────────────────────
    # Load limits from DB for this tag (cached inline — cheap single-row query)
    amplitude_suspicious = False
    amplitude_reason     = ''
    try:
        lim_sql = """
            SELECT hi_hi_limit, hi_limit, lo_limit, lo_lo_limit
            FROM   historian_analytics.tag_alarm_config
            WHERE  tag_id = %s AND enabled = TRUE
        """
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(lim_sql, (tag_id,))
                row = cur.fetchone()
        if row:
            hi_hi, hi, lo, lo_lo = row
            val_max = float(np.max(vals))
            val_min = float(np.min(vals))
            # Ratio: how far into the danger zone is the signal's peak?
            # 0.80 = flag when within 20% of the limit (e.g. 73 vs hi=75)
            PROXIMITY = 0.80
            if hi_hi is not None and val_max >= abs(hi_hi) * PROXIMITY:
                amplitude_suspicious = True
                amplitude_reason     = f'peak {val_max:.2f} near hi_hi {hi_hi}'
            elif hi is not None and val_max >= abs(hi) * PROXIMITY:
                amplitude_suspicious = True
                amplitude_reason     = f'peak {val_max:.2f} near hi {hi}'
            elif lo_lo is not None and val_min <= -abs(lo_lo) * PROXIMITY:
                amplitude_suspicious = True
                amplitude_reason     = f'trough {val_min:.2f} near lo_lo {lo_lo}'
            elif lo is not None and val_min <= -abs(lo) * PROXIMITY:
                amplitude_suspicious = True
                amplitude_reason     = f'trough {val_min:.2f} near lo {lo}'
    except Exception:
        pass   # limits not available — degrade to slope-only

    suspicious = slope_suspicious or amplitude_suspicious
    if amplitude_suspicious and not slope_suspicious:
        reason = f'amplitude_proximity: {amplitude_reason}'
    elif slope_suspicious:
        reason = 'slope_detected'
    else:
        reason = 'stable'

    return {
        'suspicious':    suspicious,
        'reason':        reason,
        'slope':         slope,
        'quality_score': round(quality, 4),
        'n_points':      n,
    }


def _save_screener_state(tag_id: str, result: Dict[str, Any]) -> None:
    sql = """
        INSERT INTO historian_analytics.screener_state
            (tag_id, is_suspicious, reason, slope, quality_score, n_points, last_screened)
        VALUES (%s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT (tag_id) DO UPDATE SET
            is_suspicious = EXCLUDED.is_suspicious,
            reason        = EXCLUDED.reason,
            slope         = EXCLUDED.slope,
            quality_score = EXCLUDED.quality_score,
            n_points      = EXCLUDED.n_points,
            last_screened = EXCLUDED.last_screened
    """
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (
                    tag_id, result['suspicious'], result['reason'],
                    result['slope'], result['quality_score'], result['n_points'],
                ))
            conn.commit()
    except Exception as exc:
        logger.warning("[Engine] screener_state write failed for %s: %s", tag_id, exc)


# ─── Stage 2: Forecast models ────────────────────────────────────────────────

def _forecast_lr(ts: np.ndarray, vals: np.ndarray, horizon_pts: int) -> np.ndarray:
    """Linear regression extrapolation."""
    x      = np.arange(len(vals), dtype=float)
    coeffs = np.polyfit(x, vals, 1)
    x_fut  = np.arange(len(vals), len(vals) + horizon_pts, dtype=float)
    return np.polyval(coeffs, x_fut)


def _forecast_hw(vals: np.ndarray, horizon_pts: int) -> Optional[np.ndarray]:
    """Holt-Winters (double exponential smoothing)."""
    try:
        from statsmodels.tsa.holtwinters import ExponentialSmoothing
        model = ExponentialSmoothing(vals, trend='add', seasonal=None)
        fit   = model.fit(optimized=True)
        return fit.forecast(horizon_pts)
    except Exception:
        return None


def _forecast_fft(vals: np.ndarray, horizon_pts: int, top_k: int = 5) -> np.ndarray:
    """FFT cycle extrapolation."""
    n      = len(vals)
    freqs  = np.fft.rfft(vals)
    # Keep only top_k dominant frequencies
    magnitudes = np.abs(freqs)
    idx        = np.argsort(magnitudes)[-top_k:]
    mask       = np.zeros(len(freqs), dtype=complex)
    mask[idx]  = freqs[idx]
    t_fut      = np.arange(n, n + horizon_pts)
    result     = np.zeros(horizon_pts)
    for k in idx:
        if k == 0:
            result += (freqs[0].real / n)
        else:
            amp   = 2 * np.abs(freqs[k]) / n
            phase = np.angle(freqs[k])
            result += amp * np.cos(2 * np.pi * k * t_fut / n + phase)
    return result


def _detect_period_pts(vals: np.ndarray) -> int:
    """Detect dominant period length in samples via FFT (0 = no clear period)."""
    n = len(vals)
    if n < 8:
        return 0
    freqs = np.fft.rfft(vals - vals.mean())
    mags  = np.abs(freqs)
    mags[0] = 0   # suppress DC
    k = int(np.argmax(mags))
    return int(round(n / k)) if k > 0 else 0


def _forecast_seasonal_fft(vals: np.ndarray, horizon_pts: int,
                            period_pts: int = 0) -> np.ndarray:
    """FFT forecast keeping only harmonics of the dominant detected period."""
    n = len(vals)
    if period_pts < 4:
        period_pts = _detect_period_pts(vals)
    if period_pts < 4:
        return _forecast_fft(vals, horizon_pts)   # fallback to plain FFT
    freqs = np.fft.rfft(vals)
    fund_k = max(round(n / period_pts), 1)
    harmonic_ks = [fund_k * h for h in range(1, 8) if 0 < fund_k * h < len(freqs)]
    t_fut  = np.arange(n, n + horizon_pts)
    result = np.full(horizon_pts, freqs[0].real / n)
    for k in harmonic_ks:
        amp   = 2 * np.abs(freqs[k]) / n
        phase = np.angle(freqs[k])
        result += amp * np.cos(2 * np.pi * k * t_fut / n + phase)
    return result


def _forecast_kalman(vals: np.ndarray, horizon_pts: int) -> np.ndarray:
    """
    Constant-velocity Kalman filter forecast.
    State: [position, velocity]. Q and R tuned from data statistics.
    """
    dt = 1.0
    F  = np.array([[1.0, dt], [0.0, 1.0]])
    H  = np.array([[1.0, 0.0]])
    acc_var = float(np.var(np.diff(np.diff(vals)))) if len(vals) > 2 else 1.0
    Q  = np.array([[0.25 * dt**4, 0.5 * dt**3],
                   [0.5 * dt**3,  dt**2       ]]) * max(acc_var, 1e-6)
    x_lf = np.arange(len(vals), dtype=float)
    c    = np.polyfit(x_lf, vals, 1)
    res_var = float(np.var(vals - np.polyval(c, x_lf)))
    R  = np.array([[max(res_var, 1e-6)]])
    state = np.array([[vals[-1]], [float(c[0])]])
    P     = np.eye(2) * res_var
    # Warm-up pass on last 200 points
    for z in vals[-min(len(vals), 200):]:
        state = F @ state
        P     = F @ P @ F.T + Q
        S     = H @ P @ H.T + R
        K     = P @ H.T @ np.linalg.inv(S)
        inn   = np.array([[z]]) - H @ state
        state = state + K @ inn
        P     = (np.eye(2) - K @ H) @ P
    forecast = np.zeros(horizon_pts)
    s, Ps = state.copy(), P.copy()
    for i in range(horizon_pts):
        s  = F @ s
        Ps = F @ Ps @ F.T + Q
        forecast[i] = float(s[0, 0])
    return forecast


def _forecast_arima_adaptive(vals: np.ndarray, horizon_pts: int) -> Optional[np.ndarray]:
    """Adaptive ARIMA: fast 3-candidate path first, expand if RMSE is poor."""
    try:
        from statsmodels.tsa.arima.model import ARIMA
        sigma = float(np.std(vals))

        FAST_ORDERS = [(1, 0, 1), (1, 1, 1), (2, 1, 1)]
        best_fit, best_aic = None, float('inf')

        for order in FAST_ORDERS:
            try:
                fit = ARIMA(vals, order=order).fit()
                if fit.aic < best_aic:
                    best_aic, best_fit = fit.aic, fit
            except Exception:
                continue

        # Accept fast path if RMSE < 1.0 × sigma
        if best_fit is not None and sigma > 1e-9:
            rmse = float(np.sqrt(np.mean((best_fit.fittedvalues - vals) ** 2)))
            if rmse < 1.0 * sigma:
                return best_fit.forecast(horizon_pts)

        # Full grid
        for p, d, q in [(p, d, q) for p in range(3) for d in [0, 1] for q in range(3)]:
            order = (p, d, q)
            if order in FAST_ORDERS or p + d + q == 0:
                continue
            try:
                fit = ARIMA(vals, order=order).fit()
                if fit.aic < best_aic:
                    best_aic, best_fit = fit.aic, fit
            except Exception:
                continue

        return best_fit.forecast(horizon_pts) if best_fit else None
    except Exception:
        return None


def _run_forecast(tag_id: str, cfg: Dict, vals: np.ndarray, ts: np.ndarray) -> Optional[Dict]:
    """
    Run one or more models; return best forecast result dict or None.
    Returns: {model, forecast_values[], eta_minutes, predicted_value,
              limit_value, direction, confidence}
    """
    horizon_min = cfg.get('forecast_horizon_minutes', 30)
    # Estimate points per minute from data density
    if len(ts) >= 2:
        span_sec = float(ts[-1] - ts[0])
        ppm      = len(ts) / max(span_sec / 60.0, 1.0)
    else:
        ppm = 1.0
    horizon_pts = max(int(round(horizon_min * ppm)), 10)

    model_pref = cfg.get('preferred_model', 'auto')
    models_to_try = (
        ['seasonal_fft', 'fft', 'lr', 'hw', 'arima'] if model_pref == 'auto' else [model_pref]
    )

    # Extract stored period_pts from model_params_json if present
    stored_params   = cfg.get('model_params_json') or {}
    stored_period   = int(stored_params.get('period_pts', 0))

    best_forecast: Optional[np.ndarray] = None
    best_model: str = ''

    for m in models_to_try:
        if m == 'lr':
            fc = _run_with_timeout(lambda: _forecast_lr(ts, vals, horizon_pts))
        elif m == 'hw':
            fc = _run_with_timeout(lambda: _forecast_hw(vals, horizon_pts))
        elif m == 'fft':
            fc = _run_with_timeout(lambda: _forecast_fft(vals, horizon_pts))
        elif m == 'seasonal_fft':
            period = stored_period if stored_period >= 4 else _detect_period_pts(vals)
            fc = _run_with_timeout(lambda: _forecast_seasonal_fft(vals, horizon_pts, period))
        elif m == 'kalman':
            fc = _run_with_timeout(lambda: _forecast_kalman(vals, horizon_pts))
        elif m == 'arima':
            fc = _run_with_timeout(lambda: _forecast_arima_adaptive(vals, horizon_pts))
        else:
            continue

        if fc is not None and len(fc) > 0:
            best_forecast = np.array(fc, dtype=float)
            best_model    = m
            break   # use first successful (auto=priority order, fixed=only one)

    if best_forecast is None:
        return None

    # ── Limit checks ─────────────────────────────────────────────────────────
    hi_hi = cfg.get('hi_hi_limit')
    hi    = cfg.get('hi_limit')
    lo    = cfg.get('lo_limit')
    lo_lo = cfg.get('lo_lo_limit')
    dband = float(cfg.get('deadband', 0.0))

    def _check_breach(limit, direction, fc_arr):
        if limit is None:
            return None
        eff_limit = limit - dband if 'HIGH' in direction else limit + dband
        for i, v in enumerate(fc_arr):
            if ('HIGH' in direction and v >= eff_limit) or \
               ('LOW'  in direction and v <= eff_limit):
                eta = round((i + 1) / max(ppm, 0.01), 1)
                breach_at = datetime.now(timezone.utc) + timedelta(minutes=eta)
                pct_to   = abs(v - limit) / max(abs(limit), 1e-9) * 100
                conf = 'HIGH' if pct_to > 20 else ('MEDIUM' if pct_to > 5 else 'LOW')
                return {
                    'direction':    direction,
                    'limit_value':  float(limit),
                    'predicted_value': float(v),
                    'eta_minutes':  eta,
                    'predicted_breach_at': breach_at.isoformat(),
                    'model_used':   best_model,
                    'confidence':   conf,
                    'forecast_json': json.dumps([
                        {'v': round(float(x), 4)} for x in fc_arr
                    ]),
                }
        return None

    for limit, direction in [
        (hi_hi, 'HIHI'), (hi, 'HIGH'), (lo, 'LOW'), (lo_lo, 'LOLO')
    ]:
        result = _check_breach(limit, direction, best_forecast)
        if result:
            return result

    return None   # no breach projected


# ─── Alarm persistence ───────────────────────────────────────────────────────

def _is_suppressed(tag_id: str, direction: str) -> bool:
    sql = """
        SELECT COUNT(*)
        FROM   historian_analytics.predictive_alarms
        WHERE  tag_id    = %s
          AND  direction = %s
          AND  active    = TRUE
          AND  (suppressed_until IS NULL OR suppressed_until > NOW())
          AND  raised_at > NOW() - INTERVAL '24 hours'
    """
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (tag_id, direction))
                count = cur.fetchone()[0]
        return count > 0
    except Exception as exc:
        logger.warning("[Engine] suppression check failed: %s", exc)
        return False


def _raise_alarm(tag_id: str, result: Dict, cfg: Dict) -> None:
    """Insert a new predictive alarm row if not suppressed."""
    direction = result['direction']
    if _is_suppressed(tag_id, direction):
        logger.debug("[Engine] Suppressed alarm for %s/%s", tag_id, direction)
        return

    suppress_mins = int(cfg.get('suppression_window_minutes', 60))
    suppressed_until = datetime.now(timezone.utc) + timedelta(minutes=suppress_mins)

    sql = """
        INSERT INTO historian_analytics.predictive_alarms
            (tag_id, direction, confidence, predicted_value, limit_value,
             eta_minutes, predicted_breach_at, model_used, forecast_json,
             raised_at, active, suppressed_until)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s, NOW(), TRUE, %s)
    """
    try:
        breach_ts = result.get('predicted_breach_at')
        if isinstance(breach_ts, str):
            from dateutil import parser as dtp
            breach_ts = dtp.parse(breach_ts)

        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (
                    tag_id,
                    direction,
                    result['confidence'],
                    result['predicted_value'],
                    result['limit_value'],
                    result['eta_minutes'],
                    breach_ts,
                    result['model_used'],
                    result['forecast_json'],
                    suppressed_until,
                ))
            conn.commit()
        logger.info(
            "[Engine] 🔔 Pre-alarm raised: %s / %s  ETA %.1f min  conf=%s",
            tag_id, direction, result['eta_minutes'], result['confidence'],
        )
    except Exception as exc:
        logger.error("[Engine] alarm insert failed for %s: %s", tag_id, exc)


def _resolve_stale_alarms() -> None:
    """Mark active alarms as resolved if eta has passed without acknowledgement."""
    sql = """
        UPDATE historian_analytics.predictive_alarms
        SET    active = FALSE,
               resolved_at = NOW(),
               resolution_reason = 'expired'
        WHERE  active = TRUE
          AND  predicted_breach_at < NOW() - INTERVAL '30 minutes'
          AND  acknowledged = FALSE
    """
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
            conn.commit()
    except Exception as exc:
        logger.warning("[Engine] stale alarm cleanup failed: %s", exc)


# ─── Warm restart recovery ───────────────────────────────────────────────────

def _recover_on_startup() -> Dict[str, Any]:
    """
    Restore screener suspicious flags from DB after a restart.
    Returns {tag_id: screener_result} for tags that were suspicious.
    """
    recovered: Dict[str, Any] = {}
    sql = """
        SELECT tag_id, is_suspicious, reason, slope, quality_score, n_points
        FROM   historian_analytics.screener_state
        WHERE  last_screened > NOW() - INTERVAL '10 minutes'
          AND  is_suspicious = TRUE
    """
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                rows = cur.fetchall()
        for row in rows:
            tag_id = row[0]
            recovered[tag_id] = {
                'suspicious':    row[1],
                'reason':        row[2],
                'slope':         row[3],
                'quality_score': row[4],
                'n_points':      row[5],
            }
        if recovered:
            logger.info("[Engine] Warm restart: %d tags restored as suspicious", len(recovered))
    except Exception as exc:
        logger.warning("[Engine] warm restart recovery failed: %s", exc)
    return recovered


# ─── Tag config loading ──────────────────────────────────────────────────────

def _load_tag_configs() -> List[Dict]:
    """Load all enabled tag alarm configs from DB."""
    sql = """
        SELECT tag_id, tag_description, unit,
               hi_hi_limit, hi_limit, lo_limit, lo_lo_limit, deadband,
               preferred_model, forecast_horizon_minutes,
               suppression_window_minutes, priority
        FROM   historian_analytics.tag_alarm_config
        WHERE  enabled = TRUE
        ORDER  BY priority ASC, tag_id ASC
    """
    try:
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql)
                rows = cur.fetchall()
        return [dict(r) for r in rows]
    except Exception as exc:
        logger.warning("[Engine] tag config load failed: %s", exc)
        return []


# ─── Priority CPU gating ─────────────────────────────────────────────────────

_PRIORITY_CPU_LIMITS = {1: 100, 2: 85, 3: 75, 4: 65, 5: 50}


def _should_forecast(priority: int, cpu: float) -> bool:
    return cpu < _PRIORITY_CPU_LIMITS.get(priority, 50)


# ─── Engine class ────────────────────────────────────────────────────────────

class PredictiveAlarmEngine:
    """
    Background engine that runs Stage 1 + Stage 2 on a configurable interval.
    Thread-safe singleton — use engine_instance() to access.
    """

    def __init__(self):
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

        # Mutable state — guarded by _lock
        self._screener_cache: Dict[str, Dict] = {}
        self._cycle_count:    int  = 0
        self._last_cycle_at:  Optional[datetime] = None
        self._last_error:     Optional[str]      = None
        self._running:        bool = False

    # ── Public control ────────────────────────────────────────────────────────

    def start(self):
        with self._lock:
            if self._running:
                return
            self._stop_event.clear()
            # Warm restart
            self._screener_cache = _recover_on_startup()
            self._thread = threading.Thread(
                target=self._loop, name="pred_alarm_engine", daemon=True
            )
            self._thread.start()
            self._running = True
            logger.info("[Engine] Started (screen_interval=%ds)", SCREEN_INTERVAL_SEC)

    def stop(self):
        with self._lock:
            if not self._running:
                return
            self._stop_event.set()
            self._running = False
        if self._thread:
            self._thread.join(timeout=10)
        logger.info("[Engine] Stopped")

    def status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'running':         self._running,
                'cycle_count':     self._cycle_count,
                'last_cycle_at':   self._last_cycle_at.isoformat() if self._last_cycle_at else None,
                'last_error':      self._last_error,
                'suspicious_tags': [
                    k for k, v in self._screener_cache.items() if v.get('suspicious')
                ],
                'screener_cache_size': len(self._screener_cache),
            }

    def force_cycle(self):
        """Run one complete Stage1+Stage2 cycle immediately (blocking, for testing)."""
        self._run_cycle()

    # ── Internal loop ─────────────────────────────────────────────────────────

    def _loop(self):
        while not self._stop_event.is_set():
            try:
                self._run_cycle()
            except Exception as exc:
                logger.exception("[Engine] Unhandled error in cycle: %s", exc)
                with self._lock:
                    self._last_error = str(exc)
            self._stop_event.wait(timeout=SCREEN_INTERVAL_SEC)

    def _run_cycle(self):
        t0 = time.monotonic()
        tag_cfgs = _load_tag_configs()

        if not tag_cfgs:
            logger.debug("[Engine] No enabled tags — skipping cycle")
            return

        cpu = _cpu_pct()
        logger.info(
            "[Engine] Cycle start — %d tags, CPU=%.0f%%", len(tag_cfgs), cpu
        )

        # ── Fetch PEWS drift context once for the whole cycle ─────────────────
        # Any tag that has an unacknowledged drift warning in the last 2 hours
        # is treated as a confirmed long-term baseline shift. We use this in
        # Stage 1 (force-suspicious) and Stage 2 (confidence escalation).
        all_tag_ids  = [c['tag_id'] for c in tag_cfgs]
        drift_context = _fetch_active_drift(all_tag_ids)
        if drift_context:
            logger.info(
                "[Engine] Drift context: %d tag(s) with active drift warnings: %s",
                len(drift_context), list(drift_context.keys()),
            )

        # ── Stage 1: Screen all tags ──────────────────────────────────────────
        suspicious: List[Dict] = []
        screened_ids: set = set()
        for cfg in tag_cfgs:
            tag_id = cfg['tag_id']
            result = _screen_tag(tag_id)
            _save_screener_state(tag_id, result)
            with self._lock:
                self._screener_cache[tag_id] = result
            screened_ids.add(tag_id)
            if result['suspicious']:
                suspicious.append(cfg)

        # ── Drift escalation: force-suspicious tags PEWS has confirmed ────────
        # A tag may have a very slow drift that the short-window slope screener
        # misses. If PEWS CUSUM/EWMA already confirmed it, we treat it as
        # suspicious so Stage 2 runs the forecast and checks limit proximity.
        suspicious_ids = {c['tag_id'] for c in suspicious}
        for cfg in tag_cfgs:
            tag_id = cfg['tag_id']
            if tag_id in drift_context and tag_id not in suspicious_ids:
                drift_result = {
                    'suspicious':    True,
                    'reason':        'drift_confirmed',   # PEWS CUSUM/EWMA fired
                    'slope':         self._screener_cache.get(tag_id, {}).get('slope', 0.0),
                    'quality_score': self._screener_cache.get(tag_id, {}).get('quality_score', 0.0),
                    'n_points':      self._screener_cache.get(tag_id, {}).get('n_points', 0),
                }
                _save_screener_state(tag_id, drift_result)
                with self._lock:
                    self._screener_cache[tag_id] = drift_result
                suspicious.append(cfg)
                suspicious_ids.add(tag_id)
                logger.info(
                    "[Engine] %s flagged suspicious via drift confirmation "
                    "(slope screener was clean)",
                    tag_id,
                )

        logger.info(
            "[Engine] Stage 1 done — %d/%d suspicious  (%d via drift)  (%.1fs)",
            len(suspicious), len(tag_cfgs),
            sum(1 for c in suspicious
                if self._screener_cache.get(c['tag_id'], {}).get('reason') == 'drift_confirmed'),
            time.monotonic() - t0,
        )

        # ── Stage 2: Forecast suspicious tags ────────────────────────────────
        if cpu > CPU_SUSPEND_THRESHOLD:
            logger.warning(
                "[Engine] CPU %.0f%% > %d%% — Stage 2 suspended this cycle",
                cpu, CPU_SUSPEND_THRESHOLD,
            )
        else:
            for cfg in suspicious:
                tag_id   = cfg['tag_id']
                priority = int(cfg.get('priority', 3))
                if not _should_forecast(priority, cpu):
                    logger.debug(
                        "[Engine] Deferred %s (priority=%d, CPU=%.0f%%)",
                        tag_id, priority, cpu,
                    )
                    continue

                ts_arr, val_arr = _fetch_historian_with_ts(
                    tag_id, LOOKBACK_MINUTES
                )
                if len(val_arr) < MIN_POINTS_FORECAST:
                    logger.debug(
                        "[Engine] Skipping %s — only %d points (need %d)",
                        tag_id, len(val_arr), MIN_POINTS_FORECAST,
                    )
                    continue

                breach = _run_with_timeout(
                    lambda: _run_forecast(tag_id, cfg, val_arr, ts_arr),
                    timeout_sec=STAGE2_TIMEOUT_SEC * 4,
                )

                if breach:
                    # If PEWS drift agrees with the projected breach direction,
                    # escalate confidence before writing the alarm.
                    tag_drifts = drift_context.get(tag_id, [])
                    if tag_drifts:
                        breach = _escalate_with_drift(breach, tag_drifts)
                    _raise_alarm(tag_id, breach, cfg)

        # ── Cleanup stale alarms ─────────────────────────────────────────────
        _resolve_stale_alarms()

        elapsed = time.monotonic() - t0
        with self._lock:
            self._cycle_count += 1
            self._last_cycle_at = datetime.now(timezone.utc)
        logger.info("[Engine] Cycle #%d complete  %.1fs", self._cycle_count, elapsed)


# ─── Singleton ───────────────────────────────────────────────────────────────

_engine_singleton: Optional[PredictiveAlarmEngine] = None
_singleton_lock = threading.Lock()


def engine_instance() -> PredictiveAlarmEngine:
    global _engine_singleton
    if _engine_singleton is not None:
        return _engine_singleton
    with _singleton_lock:
        if _engine_singleton is None:
            _engine_singleton = PredictiveAlarmEngine()
    return _engine_singleton
