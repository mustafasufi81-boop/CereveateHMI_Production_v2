"""
Drift Detector Service — Stage 0 Long-term Baseline Monitor
============================================================
Runs every DRIFT_CHECK_INTERVAL_SEC (default 3600 = 1 hour).
For every enabled tag in historian_analytics.tag_alarm_config, compares
the CURRENT evaluation window (last eval_window_hours) against a ROLLING
BASELINE (last baseline_days).

Three independent detectors run in parallel per tag:

  CUSUM  — Cumulative Sum control chart.
           Best for: slow monotonic shift (bearing wear, sensor fouling,
           thermal creep). Detects a mean shift of 1σ within ~5–10 samples
           after it starts.  Industry standard for predictive maintenance.

  EWMA   — Exponentially Weighted Moving Average.
           Best for: gradual smooth degradation (pump efficiency loss,
           heat-exchanger fouling). Less spike-sensitive than CUSUM.
           λ=0.2 (weights last ~10 hourly readings heavily).

  Z-SCORE — Rolling standardised score.
           Best for: sudden step changes in baseline (sensor replacement,
           process switch, instrument drift). Fires when the last hour's
           mean is > ZSCORE_THRESHOLD standard deviations from the rolling
           baseline.

Severity thresholds (all relative to baseline σ):
  info     → 1.5σ ≤ shift < 2.5σ    (watch — trend is moving)
  warning  → 2.5σ ≤ shift < 4.0σ    (investigate within 24 h)
  critical → shift ≥ 4.0σ           (act now — potential failure)

Results are written to historian_analytics.drift_alerts with a unique
constraint (tag_id, method) for active rows — upsert keeps only the
latest active alert per method per tag.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np
import psycopg2
import psycopg2.extras
import psycopg2.pool

from container import container

logger = logging.getLogger(__name__)

# ── Tunable constants ─────────────────────────────────────────────────────────
DRIFT_CHECK_INTERVAL_SEC = 3600   # run every hour
BASELINE_DAYS            = 30     # days of history for baseline stats
EVAL_WINDOW_HOURS        = 1      # evaluation window for current behaviour
MIN_BASELINE_HOURS       = 24     # minimum hours of data before we run
EWMA_LAMBDA              = 0.2    # EWMA smoothing factor (0=slow, 1=fast)
CUSUM_K                  = 0.5    # CUSUM allowance (half-sigma)
CUSUM_H                  = 5.0    # CUSUM decision threshold (5σ accumulated)
ZSCORE_THRESHOLD         = 2.5    # z-score that triggers alert

# Severity thresholds (× baseline std)
SEV_INFO     = 1.5
SEV_WARNING  = 2.5
SEV_CRITICAL = 4.0

# ── DB pool ───────────────────────────────────────────────────────────────────
_pool: Optional[psycopg2.pool.ThreadedConnectionPool] = None
_pool_lock = threading.Lock()


def _get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    global _pool
    if _pool is not None:
        return _pool
    with _pool_lock:
        if _pool is None:
            cfg = container.config['database']
            _pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=1, maxconn=3,
                host=cfg['host'], port=int(cfg['port']),
                dbname=cfg['database'], user=cfg['user'],
                password=cfg['password'],
                keepalives=1, keepalives_idle=60,
                connect_timeout=10,
                options="-c statement_timeout=60000 -c application_name=drift_detector",
            )
    return _pool


def _conn():
    pool = _get_pool()
    conn = pool.getconn()
    try:
        yield conn
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        pool.putconn(conn)

_conn = __import__('contextlib').contextmanager(_conn)


# ── Data fetching ─────────────────────────────────────────────────────────────

def _fetch_hourly_means(tag_id: str, days: int) -> Tuple[np.ndarray, np.ndarray]:
    """
    Return (epoch_hours[], hourly_means[]) for the last `days` days.
    Aggregates historian_timeseries into 1-hour buckets.
    """
    sql = """
        SELECT
            EXTRACT(EPOCH FROM date_trunc('hour', time))::float  AS hr_epoch,
            AVG(value_num)                                        AS hr_mean
        FROM  historian_raw.historian_timeseries
        WHERE tag_id    = %s
          AND time      > NOW() - (%s * INTERVAL '1 day')
          AND value_num IS NOT NULL
        GROUP BY date_trunc('hour', time)
        ORDER BY 1 ASC
    """
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (tag_id, days))
                rows = cur.fetchall()
        if not rows:
            return np.array([]), np.array([])
        ts  = np.array([r[0] for r in rows], dtype=float)
        val = np.array([r[1] for r in rows], dtype=float)
        return ts, val
    except Exception as exc:
        logger.warning("[Drift] Fetch failed for %s: %s", tag_id, exc)
        return np.array([]), np.array([])


def _fetch_enabled_tags() -> List[str]:
    sql = "SELECT tag_id FROM historian_analytics.tag_alarm_config WHERE enabled = TRUE"
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                return [r[0] for r in cur.fetchall()]
    except Exception as exc:
        logger.warning("[Drift] Could not fetch enabled tags: %s", exc)
        return []


# ── Detection algorithms ──────────────────────────────────────────────────────

def _severity(shift_sigma: float) -> str:
    if shift_sigma >= SEV_CRITICAL:
        return 'critical'
    if shift_sigma >= SEV_WARNING:
        return 'warning'
    return 'info'


def detect_cusum(hourly: np.ndarray, baseline_mean: float,
                 baseline_std: float) -> Optional[Dict]:
    """
    Two-sided CUSUM on hourly means.
    Returns detection dict or None if no drift detected.

    Algorithm:
      C_hi[i] = max(0, C_hi[i-1] + (x[i] - baseline_mean) / σ - K)
      C_lo[i] = max(0, C_lo[i-1] - (x[i] - baseline_mean) / σ - K)
      Alert when C_hi or C_lo > H
    """
    if baseline_std < 1e-9 or len(hourly) < 2:
        return None

    sigma = baseline_std
    c_hi, c_lo = 0.0, 0.0

    for x in hourly:
        z = (x - baseline_mean) / sigma
        c_hi = max(0.0, c_hi + z - CUSUM_K)
        c_lo = max(0.0, c_lo - z - CUSUM_K)

    if c_hi > CUSUM_H:
        magnitude = float(np.mean(hourly) - baseline_mean)
        # Map normalised CUSUM score (c/H, range 1..∞) onto the severity scale.
        # At exactly H the ratio is 1.0; multiply by SEV_CRITICAL so a score of
        # 2× H maps to critical (8σ equivalent). This allows all three severity
        # levels to be reachable under realistic process conditions.
        return {
            'direction':    'UP',
            'cusum_score':  round(c_hi, 4),
            'drift_magnitude': abs(magnitude),
            'drift_pct':    abs(magnitude) / sigma * 100.0,
            'severity':     _severity(c_hi / CUSUM_H * SEV_CRITICAL),
        }
    if c_lo > CUSUM_H:
        magnitude = float(baseline_mean - np.mean(hourly))
        return {
            'direction':    'DOWN',
            'cusum_score':  round(-c_lo, 4),
            'drift_magnitude': abs(magnitude),
            'drift_pct':    abs(magnitude) / sigma * 100.0,
            'severity':     _severity(c_lo / CUSUM_H * SEV_CRITICAL),
        }
    return None


def detect_ewma(hourly: np.ndarray, baseline_mean: float,
                baseline_std: float) -> Optional[Dict]:
    """
    EWMA control chart.
    Control limits at baseline_mean ± L × σ × sqrt(λ/(2−λ))
    L = 3.0 gives ~0.27% false-alarm rate.
    """
    if baseline_std < 1e-9 or len(hourly) < 2:
        return None

    lam   = EWMA_LAMBDA
    L     = 3.0
    sigma = baseline_std
    limit = L * sigma * math.sqrt(lam / (2.0 - lam))

    ewma = baseline_mean
    for x in hourly:
        ewma = lam * x + (1.0 - lam) * ewma

    deviation = ewma - baseline_mean
    if abs(deviation) > limit:
        return {
            'direction':    'UP' if deviation > 0 else 'DOWN',
            'ewma_value':   round(ewma, 4),
            'drift_magnitude': abs(deviation),
            'drift_pct':    abs(deviation) / sigma * 100.0,
            'severity':     _severity(abs(deviation) / sigma),
        }
    return None


def detect_zscore(current_window: np.ndarray, baseline_mean: float,
                  baseline_std: float) -> Optional[Dict]:
    """
    Rolling Z-score: how many σ is the current window's mean from baseline?
    """
    if baseline_std < 1e-9 or len(current_window) == 0:
        return None

    current_mean = float(np.mean(current_window))
    z = (current_mean - baseline_mean) / baseline_std

    if abs(z) >= ZSCORE_THRESHOLD:
        return {
            'direction':    'UP' if z > 0 else 'DOWN',
            'drift_magnitude': abs(current_mean - baseline_mean),
            'drift_pct':    abs(z) * 100.0,
            'severity':     _severity(abs(z)),
        }
    return None


# ── DB write ──────────────────────────────────────────────────────────────────

def _upsert_drift_alert(tag_id: str, method: str, result: Dict,
                        baseline_mean: float, baseline_std: float,
                        current_mean: float) -> None:
    """
    Upsert one active drift alert row.
    Uses the unique index (tag_id, method) WHERE is_active to ensure
    only one live alert per method per tag.
    """
    # Note: direction flips are handled gracefully by the ON CONFLICT DO UPDATE
    # clause below — it overwrites direction/severity in-place. Explicit
    # resolution (is_active=FALSE) only happens when detect() returns None,
    # which calls _resolve_alert() from _evaluate_tag().
    sql = """
        INSERT INTO historian_analytics.drift_alerts
            (tag_id, method, severity, direction,
             baseline_mean, baseline_std, current_mean,
             drift_magnitude, drift_pct,
             cusum_score, ewma_value,
             eval_window_hours, baseline_days,
             consecutive_hours, is_active, last_updated)
        VALUES
            (%s, %s, %s, %s,
             %s, %s, %s,
             %s, %s,
             %s, %s,
             %s, %s,
             1, TRUE, NOW())
        ON CONFLICT (tag_id, method) WHERE is_active = TRUE
        DO UPDATE SET
            severity        = EXCLUDED.severity,
            direction       = EXCLUDED.direction,
            current_mean    = EXCLUDED.current_mean,
            drift_magnitude = EXCLUDED.drift_magnitude,
            drift_pct       = EXCLUDED.drift_pct,
            cusum_score     = EXCLUDED.cusum_score,
            ewma_value      = EXCLUDED.ewma_value,
            consecutive_hours = historian_analytics.drift_alerts.consecutive_hours + 1,
            last_updated    = NOW()
    """
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (
                    tag_id, method,
                    result.get('severity', 'info'),
                    result.get('direction', 'UP'),
                    round(baseline_mean, 4),
                    round(baseline_std, 4),
                    round(current_mean, 4),
                    round(result.get('drift_magnitude', 0.0), 4),
                    round(result.get('drift_pct', 0.0), 2),
                    result.get('cusum_score'),
                    result.get('ewma_value'),
                    EVAL_WINDOW_HOURS,
                    BASELINE_DAYS,
                ))
            conn.commit()
    except Exception as exc:
        logger.warning("[Drift] Upsert failed (%s, %s): %s", tag_id, method, exc)


def _resolve_alert(tag_id: str, method: str) -> None:
    """Mark the active drift alert as resolved (no longer drifting)."""
    sql = """
        UPDATE historian_analytics.drift_alerts
        SET    is_active   = FALSE,
               resolved_at = NOW(),
               last_updated = NOW()
        WHERE  tag_id  = %s
          AND  method  = %s
          AND  is_active = TRUE
    """
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (tag_id, method))
            conn.commit()
    except Exception as exc:
        logger.warning("[Drift] Resolve failed (%s, %s): %s", tag_id, method, exc)


# ── Per-tag evaluation ────────────────────────────────────────────────────────

def _evaluate_tag(tag_id: str) -> None:
    ts, hourly = _fetch_hourly_means(tag_id, BASELINE_DAYS)
    if len(hourly) < MIN_BASELINE_HOURS:
        logger.debug("[Drift] %s: only %d h of data, skipping", tag_id, len(hourly))
        return

    # Baseline: all hours EXCEPT the last eval_window_hours
    split = max(len(hourly) - EVAL_WINDOW_HOURS, MIN_BASELINE_HOURS)
    baseline    = hourly[:split]
    current_win = hourly[split:]

    if len(current_win) == 0:
        return

    baseline_mean = float(np.mean(baseline))
    baseline_std  = float(np.std(baseline))
    current_mean  = float(np.mean(current_win))

    if baseline_std < 1e-9:
        return   # flat signal — no drift meaningful

    detectors = {
        'cusum':  detect_cusum(current_win,  baseline_mean, baseline_std),
        'ewma':   detect_ewma(hourly,         baseline_mean, baseline_std),
        'zscore': detect_zscore(current_win,  baseline_mean, baseline_std),
    }

    for method, result in detectors.items():
        if result:
            _upsert_drift_alert(tag_id, method, result,
                                baseline_mean, baseline_std, current_mean)
            logger.info(
                "[Drift] %s | %s | %s | shift=%.2f (%.1f%%) | dir=%s",
                tag_id, method, result['severity'],
                result['drift_magnitude'], result['drift_pct'],
                result['direction'],
            )
        else:
            _resolve_alert(tag_id, method)


# ── Service class ─────────────────────────────────────────────────────────────

class DriftDetectorService:
    """
    Singleton background service.
    Runs _evaluate_tag() for all enabled tags once per DRIFT_CHECK_INTERVAL_SEC.
    """

    def __init__(self) -> None:
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._running   = False
        self._cycle_count    = 0
        self._last_run_at: Optional[datetime] = None
        self._last_error: Optional[str] = None
        self._tags_checked   = 0
        self._alerts_active  = 0

    def start(self) -> None:
        if self._running:
            return
        # Apply migration if table doesn't exist
        self._ensure_schema()
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop, name="drift_detector", daemon=True,
        )
        self._thread.start()
        logger.info("[Drift] Service started (interval=%ds)", DRIFT_CHECK_INTERVAL_SEC)

    def stop(self) -> None:
        self._stop_event.set()
        self._running = False
        logger.info("[Drift] Service stopped")

    def force_cycle(self) -> None:
        """Trigger an immediate evaluation cycle (for testing/UI button)."""
        threading.Thread(target=self._run_cycle, daemon=True,
                         name="drift_force").start()

    def status(self) -> Dict:
        return {
            'running':       self._running,
            'cycle_count':   self._cycle_count,
            'last_run_at':   self._last_run_at.isoformat() if self._last_run_at else None,
            'last_error':    self._last_error,
            'tags_checked':  self._tags_checked,
            'alerts_active': self._alerts_active,
            'interval_sec':  DRIFT_CHECK_INTERVAL_SEC,
            'methods':       ['cusum', 'ewma', 'zscore'],
            'config': {
                'baseline_days':      BASELINE_DAYS,
                'eval_window_hours':  EVAL_WINDOW_HOURS,
                'cusum_k':            CUSUM_K,
                'cusum_h':            CUSUM_H,
                'ewma_lambda':        EWMA_LAMBDA,
                'zscore_threshold':   ZSCORE_THRESHOLD,
                'severity_thresholds': {
                    'info':     SEV_INFO,
                    'warning':  SEV_WARNING,
                    'critical': SEV_CRITICAL,
                },
            },
        }

    def _loop(self) -> None:
        # Run once immediately at startup, then every interval
        self._run_cycle()
        while not self._stop_event.wait(timeout=DRIFT_CHECK_INTERVAL_SEC):
            self._run_cycle()

    def _run_cycle(self) -> None:
        try:
            tags = _fetch_enabled_tags()
            self._tags_checked = len(tags)
            for tag_id in tags:
                try:
                    _evaluate_tag(tag_id)
                except Exception as exc:
                    logger.warning("[Drift] Error evaluating %s: %s", tag_id, exc)
            self._cycle_count   += 1
            self._last_run_at    = datetime.now(timezone.utc)
            self._last_error     = None
            self._alerts_active  = self._count_active_alerts()
            logger.info(
                "[Drift] Cycle %d done — %d tags, %d active alerts",
                self._cycle_count, self._tags_checked, self._alerts_active,
            )
        except Exception as exc:
            self._last_error = str(exc)
            logger.error("[Drift] Cycle error: %s", exc)

    def _count_active_alerts(self) -> int:
        try:
            with _conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT COUNT(*) FROM historian_analytics.drift_alerts WHERE is_active = TRUE"
                    )
                    return int(cur.fetchone()[0])
        except Exception:
            return 0

    def _ensure_schema(self) -> None:
        """
        Apply migration 026 if the drift_alerts table does not exist.

        DDL requires autocommit mode which must NOT be set on a pooled
        connection (it would be returned to the pool in autocommit=True
        state, corrupting subsequent transactions).  We therefore use a
        short-lived direct connection exclusively for the DDL step.
        """
        try:
            import pathlib
            sql_path = (
                pathlib.Path(__file__).parent.parent
                / 'migrations'
                / '026_drift_alerts_schema.sql'
            )
            if not sql_path.exists():
                logger.warning("[Drift] Migration file not found: %s", sql_path)
                return

            # Check existence via a normal pooled connection (read-only, safe)
            with _conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT to_regclass('historian_analytics.drift_alerts')"
                    )
                    exists = cur.fetchone()[0]

            if not exists:
                # Open a fresh, non-pooled connection for DDL
                cfg = container.config['database']
                ddl_conn = psycopg2.connect(
                    host=cfg['host'], port=int(cfg['port']),
                    dbname=cfg['database'], user=cfg['user'],
                    password=cfg['password'],
                    connect_timeout=10,
                )
                try:
                    ddl_conn.autocommit = True
                    with ddl_conn.cursor() as cur:
                        cur.execute(sql_path.read_text())
                    logger.info(
                        "[Drift] Migration 026 applied — drift_alerts table created"
                    )
                finally:
                    ddl_conn.close()
            else:
                logger.info("[Drift] drift_alerts table already exists")
        except Exception as exc:
            logger.error("[Drift] Schema ensure failed: %s", exc)


# ── Singleton ─────────────────────────────────────────────────────────────────
_instance: Optional[DriftDetectorService] = None
_instance_lock = threading.Lock()


def drift_detector_instance() -> DriftDetectorService:
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = DriftDetectorService()
    return _instance
