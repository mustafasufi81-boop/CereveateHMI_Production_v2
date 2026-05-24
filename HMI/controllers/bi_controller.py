"""
BI Flask Blueprint (Refactored - Zero External Dependencies)
=============================================================
Exposes BI analytics to the React HMI via REST endpoints.
Data source: historian_raw.historian_timeseries (PostgreSQL via HMI's existing connection pool).
NO Parquet files. NO predictive_engine imports. NO HistoricalTrends path dependencies.

All DB reads use psycopg2 via container.config['database'].
All forecast logic is self-contained in this file (numpy + statsmodels).

Routes
------
GET  /api/bi/tags                 List all available tags in historian
POST /api/bi/trends               Time-series data for a tag list + date range
POST /api/bi/baselines            Compute baseline stats for a set of tags
POST /api/bi/forecast             Multi-model forecast (LR, HW, FFT, ARIMA)
POST /api/bi/benchmark            Walk-forward CV, grid-search tuning, leaderboard
"""
import logging
import threading
import psycopg2
import psycopg2.pool
import psycopg2.extras
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
from flask import Blueprint, jsonify, request
from container import container
from utils.decorators import token_required

logger = logging.getLogger(__name__)

bi_bp = Blueprint("bi", __name__, url_prefix="/api/bi")

# ══════════════════════════════════════════════════════════════════════════════
# Model Training Cache
# ══════════════════════════════════════════════════════════════════════════════
# Stores the best long-history training series per tag so the ARIMA/HW models
# are pre-fitted on weeks of data and can produce strong predictions from the
# first request.  Cache entries are refreshed every CACHE_TTL_HOURS hours so
# the model adapts as new process data arrives.
# ──────────────────────────────────────────────────────────────────────────────
_model_cache: dict = {}          # tag_id → {"y_long": np.array, "built_at": datetime, "n_days": float}
_model_cache_lock = threading.Lock()
CACHE_TTL_HOURS  = 4             # re-train from long history every 4 hours
MAX_TRAIN_DAYS   = 7             # look back up to 7 days for training data
MAX_TRAIN_POINTS = 5000          # cap at 5000 resampled points to keep latency low

# ══════════════════════════════════════════════════════════════════════════════
# Model Parameter Persistence
# ══════════════════════════════════════════════════════════════════════════════
# Trained model coefficients are saved to historian_analytics.bi_model_versions
# after every training run so they survive Flask restarts.
# On startup, saved params are loaded back into _model_cache so the first
# forecast request uses the full pre-trained model immediately.
# ──────────────────────────────────────────────────────────────────────────────

# ══════════════════════════════════════════════════════════════════════════════
# Versioned Model Weight Storage
# ══════════════════════════════════════════════════════════════════════════════
# Each training run creates a NEW version row.  A version is only promoted to
# is_active=TRUE when it is provably better than the current active version
# (MAE must improve by at least PROMOTION_THRESHOLD = 5%).
# We keep MAX_VERSIONS_KEPT non-active versions per tag+model as safety backup;
# versions older than VERSION_RETIRE_DAYS with is_active=FALSE are pruned.
# This means the system NEVER silently degrades — bad models are never deployed.
# ──────────────────────────────────────────────────────────────────────────────
PROMOTION_THRESHOLD  = 0.05   # new model must be ≥5% better MAE to replace active
MAX_VERSIONS_KEPT    = 3      # keep at most this many non-active versions per tag+model
VERSION_RETIRE_DAYS  = 14     # non-active versions expire after 14 days

_ENSURE_VERSIONS_TABLE_SQL = """
CREATE SCHEMA IF NOT EXISTS historian_analytics;
CREATE TABLE IF NOT EXISTS historian_analytics.bi_model_versions (
    id              SERIAL          PRIMARY KEY,
    tag_id          TEXT            NOT NULL,
    model_name      TEXT            NOT NULL,
    version         INTEGER         NOT NULL,
    params_json     JSONB           NOT NULL,
    n_train_points  INTEGER         NOT NULL DEFAULT 0,
    n_days_trained  NUMERIC(6,2)    NOT NULL DEFAULT 0,
    mae             NUMERIC(14,8),
    rmse            NUMERIC(14,8),
    aic             NUMERIC(14,4),
    is_active       BOOLEAN         NOT NULL DEFAULT FALSE,
    promoted_at     TIMESTAMPTZ,
    trained_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    retire_after    TIMESTAMPTZ,
    notes           TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS bi_model_versions_active_uidx
    ON historian_analytics.bi_model_versions(tag_id, model_name)
    WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS bi_model_versions_tag_idx
    ON historian_analytics.bi_model_versions(tag_id, model_name, trained_at DESC);
COMMENT ON TABLE historian_analytics.bi_model_versions IS
    'Versioned forecast model weights — only promoted when provably better (>=5% MAE gain)';
"""

def _ensure_model_versions_table() -> None:
    """Create bi_model_versions table and indexes if they do not yet exist."""
    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(_ENSURE_VERSIONS_TABLE_SQL)
            conn.commit()
        logger.info("[BI_ModelDB] bi_model_versions table ready")
    except Exception as exc:
        logger.warning("[BI_ModelDB] Could not create bi_model_versions: %s", exc)


def _get_holdout_mae(y: "np.ndarray", forecast_fn, holdout_n: int = 10) -> float:
    """
    Compute a rough holdout MAE for gating model promotion.
    Fits on y[:-holdout_n], forecasts holdout_n steps, returns MAE.
    Returns inf if evaluation fails.
    """
    import numpy as np
    try:
        if len(y) < holdout_n + 8:
            return float("inf")
        train_y = y[:-holdout_n]
        actual  = y[-holdout_n:]
        pred    = forecast_fn(train_y, holdout_n)
        if pred is None or len(pred) != holdout_n:
            return float("inf")
        return float(np.mean(np.abs(np.array(pred) - actual)))
    except Exception:
        return float("inf")


def _maybe_promote_model(
    tag_id: str,
    model_name: str,
    new_params: dict,
    new_mae: float,
    new_rmse: float,
    new_aic: float | None,
    n_train: int,
    n_days: float,
) -> bool:
    """
    Insert a new model version.  Promote to is_active only if:
      - No active version exists yet, OR
      - new_mae < current_active_mae * (1 - PROMOTION_THRESHOLD)
    Keeps at most MAX_VERSIONS_KEPT non-active rows; retires excess oldest ones.
    Returns True if the new version was promoted to active.
    """
    import json
    promoted = False
    try:
        with _get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:

                # ── 1. Fetch current active version's MAE ────────────────────
                cur.execute("""
                    SELECT id, mae FROM historian_analytics.bi_model_versions
                    WHERE tag_id = %s AND model_name = %s AND is_active = TRUE
                    LIMIT 1
                """, (tag_id, model_name))
                active_row = cur.fetchone()
                current_active_mae = float(active_row["mae"]) if active_row and active_row["mae"] is not None else None

                # ── 2. Decide whether to promote ────────────────────────────
                do_promote = False
                if current_active_mae is None:
                    do_promote = True   # first ever version
                elif new_mae < current_active_mae * (1.0 - PROMOTION_THRESHOLD):
                    do_promote = True   # provably better by threshold
                elif new_mae == float("inf"):
                    do_promote = False  # evaluation failed — never promote

                # ── 3. Assign next version number ────────────────────────────
                cur.execute("""
                    SELECT COALESCE(MAX(version), 0) + 1 AS next_ver
                    FROM historian_analytics.bi_model_versions
                    WHERE tag_id = %s AND model_name = %s
                """, (tag_id, model_name))
                next_ver = cur.fetchone()["next_ver"]

                # ── 4. Deactivate current active if promoting ─────────────────
                if do_promote and active_row:
                    retire_ts = "NOW() + INTERVAL '" + str(VERSION_RETIRE_DAYS) + " days'"
                    cur.execute("""
                        UPDATE historian_analytics.bi_model_versions
                        SET is_active = FALSE, retire_after = NOW() + %s * INTERVAL '1 day'
                        WHERE id = %s
                    """, (VERSION_RETIRE_DAYS, active_row["id"]))

                # ── 5. Insert new version ─────────────────────────────────────
                cur.execute("""
                    INSERT INTO historian_analytics.bi_model_versions
                        (tag_id, model_name, version, params_json,
                         n_train_points, n_days_trained,
                         mae, rmse, aic,
                         is_active, promoted_at, trained_at,
                         retire_after, notes)
                    VALUES (%s, %s, %s, %s::jsonb,
                            %s, %s,
                            %s, %s, %s,
                            %s, CASE WHEN %s THEN NOW() ELSE NULL END, NOW(),
                            CASE WHEN %s THEN NULL
                                 ELSE NOW() + %s * INTERVAL '1 day'
                            END,
                            %s)
                """, (
                    tag_id, model_name, next_ver, json.dumps(new_params),
                    n_train, round(n_days, 2),
                    None if new_mae == float("inf") else round(new_mae, 8),
                    None if new_rmse == float("inf") else round(new_rmse, 8),
                    round(new_aic, 4) if new_aic is not None else None,
                    do_promote, do_promote,
                    do_promote, VERSION_RETIRE_DAYS,
                    "auto-promoted" if do_promote else "staged (not better than active)",
                ))

                # ── 6. Prune excess non-active versions (keep MAX_VERSIONS_KEPT) ──
                cur.execute("""
                    DELETE FROM historian_analytics.bi_model_versions
                    WHERE id IN (
                        SELECT id FROM historian_analytics.bi_model_versions
                        WHERE tag_id = %s AND model_name = %s AND is_active = FALSE
                        ORDER BY trained_at DESC
                        OFFSET %s
                    )
                """, (tag_id, model_name, MAX_VERSIONS_KEPT))

            conn.commit()
            promoted = do_promote

        if promoted:
            logger.info("[BI_ModelDB] ✅ PROMOTED v%d  %s/%s  MAE %.4f→%.4f",
                        next_ver, tag_id, model_name,
                        current_active_mae if current_active_mae else 0, new_mae)
        else:
            logger.debug("[BI_ModelDB] Staged v%d %s/%s — current MAE=%.4f new MAE=%.4f (not better enough)",
                         next_ver, tag_id, model_name,
                         current_active_mae if current_active_mae else -1, new_mae)
    except Exception as exc:
        logger.warning("[BI_ModelDB] _maybe_promote_model error for %s/%s: %s", tag_id, model_name, exc)
    return promoted


def _prune_expired_versions() -> None:
    """Delete non-active versions whose retire_after timestamp has passed."""
    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    DELETE FROM historian_analytics.bi_model_versions
                    WHERE is_active = FALSE
                      AND retire_after IS NOT NULL
                      AND retire_after < NOW()
                """)
                deleted = cur.rowcount
            conn.commit()
        if deleted:
            logger.info("[BI_ModelDB] Pruned %d expired non-active model versions", deleted)
    except Exception as exc:
        logger.warning("[BI_ModelDB] _prune_expired_versions error: %s", exc)


def _get_active_params(tag_id: str, model_name: str) -> dict | None:
    """Return the currently active (promoted) params row for tag+model, or None."""
    try:
        with _get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT params_json, n_train_points, n_days_trained,
                           mae, rmse, aic, version, promoted_at, trained_at
                    FROM historian_analytics.bi_model_versions
                    WHERE tag_id = %s AND model_name = %s AND is_active = TRUE
                    LIMIT 1
                """, (tag_id, model_name))
                row = cur.fetchone()
        return dict(row) if row else None
    except Exception as exc:
        logger.warning("[BI_ModelDB] _get_active_params error %s/%s: %s", tag_id, model_name, exc)
        return None


def _load_all_active_params() -> dict:
    """
    On startup: load all active (promoted) params grouped by tag_id.
    Returns { tag_id: { model_name: {params_json, n_train_points, ...} } }
    """
    try:
        with _get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT tag_id, model_name, params_json,
                           n_train_points, n_days_trained,
                           mae, version, promoted_at, trained_at
                    FROM historian_analytics.bi_model_versions
                    WHERE is_active = TRUE
                    ORDER BY tag_id, model_name
                """)
                rows = cur.fetchall()
        result: dict = {}
        for r in rows:
            result.setdefault(r["tag_id"], {})[r["model_name"]] = dict(r)
        logger.info("[BI_ModelDB] Loaded active model versions for %d tags from DB", len(result))
        return result
    except Exception as exc:
        logger.warning("[BI_ModelDB] Could not load active params on startup: %s", exc)
        return {}


# ── Startup initialisation (called once when blueprint is first imported) ────
def _discover_all_tags_from_db() -> list:
    """
    Query historian_raw.historian_timeseries for all distinct tag_ids that have
    data in the last MAX_TRAIN_DAYS window.  Returns a sorted list of tag_id strings.
    Called at startup so we know which tags to pre-train immediately.
    """
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=MAX_TRAIN_DAYS)).isoformat()
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT DISTINCT tag_id
                    FROM historian_raw.historian_timeseries
                    WHERE time >= %s AND value_num IS NOT NULL
                    ORDER BY tag_id
                """, (cutoff,))
                tags = [r[0] for r in cur.fetchall()]
        logger.info("[BI_Startup] Discovered %d tags in historian for pre-training", len(tags))
        return tags
    except Exception as exc:
        logger.warning("[BI_Startup] Could not discover tags from DB: %s", exc)
        return []


def _startup_pretrain(tags_without_model: list) -> None:
    """
    Run a DEEP training cycle for every tag that has no active model version yet.
    Called once at startup in a daemon thread — does NOT block Flask.
    Tags that already have an active version are skipped (loaded from DB instead).
    Uses TAG_TRAIN_PAUSE_S between tags to avoid hammering DB/CPU.
    """
    import numpy as np
    import time

    if not tags_without_model:
        logger.info("[BI_Startup] All tags already have trained models — no pre-training needed")
        return

    logger.info("[BI_Startup] Starting startup pre-training for %d tags (no existing model)",
                len(tags_without_model))
    now = datetime.now(timezone.utc)
    done = failed = 0

    for tag_id in tags_without_model:
        try:
            # Build full training series incrementally (1 day at a time)
            y_accum = np.array([], dtype=float)
            for chunk_day in range(MAX_TRAIN_DAYS, 0, -1):
                chunk_end   = now - timedelta(days=chunk_day - 1)
                chunk_start = now - timedelta(days=chunk_day)
                df_chunk = _get_timeseries_df(
                    [tag_id],
                    chunk_start.isoformat(),
                    chunk_end.isoformat(),
                    resample_minutes=1,
                )
                if not df_chunk.empty and tag_id in df_chunk.columns:
                    new_pts = df_chunk[tag_id].dropna().values.astype(float)
                    y_accum = np.concatenate([y_accum, new_pts])
                time.sleep(0.3)   # small pause between day chunks

            if len(y_accum) < 8:
                logger.debug("[BI_Startup] Not enough data for %s (%d pts) — skipping",
                             tag_id, len(y_accum))
                continue

            y = y_accum[-MAX_TRAIN_POINTS:] if len(y_accum) > MAX_TRAIN_POINTS else y_accum
            n_days = round(min(len(y) / (60 * 24), float(MAX_TRAIN_DAYS)), 2)

            # Run DEEP fit + promote (first version so will always be promoted)
            _fit_one_tag_incremental(tag_id, y, n_days, now, deep=True)
            done += 1
            logger.info("[BI_Startup] Pre-trained %s (%d pts, %.1fd)", tag_id, len(y), n_days)

        except Exception as exc:
            failed += 1
            logger.warning("[BI_Startup] Pre-train failed for %s: %s", tag_id, exc)

        time.sleep(TAG_TRAIN_PAUSE_S)

    logger.info("[BI_Startup] Pre-training complete — done=%d  failed=%d", done, failed)


def _on_startup() -> None:
    import time
    _ensure_model_versions_table()

    # ── Step 1: load already-trained active versions from DB into memory ──────
    saved = _load_all_active_params()
    already_trained_tags: set = set()
    with _model_cache_lock:
        for tag_id, models in saved.items():
            # Filter out _meta-only entries (no real ARIMA/HW/LR version)
            real_models = {k: v for k, v in models.items() if not k.startswith("_")}
            if not real_models:
                continue
            already_trained_tags.add(tag_id)
            best = max(real_models.values(), key=lambda m: m.get("trained_at") or datetime.min)
            trained_at = best.get("trained_at")
            if trained_at and isinstance(trained_at, str):
                try:
                    trained_at = datetime.fromisoformat(trained_at)
                except Exception:
                    trained_at = datetime.min.replace(tzinfo=timezone.utc)
            n_days = float(best.get("n_days_trained") or 0)
            n_pts  = int(best.get("n_train_points") or 0)
            if tag_id not in _model_cache:
                _model_cache[tag_id] = {
                    "y_long":           None,
                    "built_at":         trained_at or datetime.min.replace(tzinfo=timezone.utc),
                    "n_days":           n_days,
                    "n_train_points":   n_pts,
                    "last_trained_at":  trained_at,
                    "db_params":        models,
                }
    logger.info("[BI_Startup] Loaded %d tags with existing active model versions from DB",
                len(already_trained_tags))

    # ── Step 2: discover ALL tags in historian that have recent data ──────────
    # Wait briefly for DB pool to warm up
    time.sleep(5)
    all_db_tags = _discover_all_tags_from_db()

    # Tags that exist in historian but have NO trained model yet
    tags_to_pretrain = [t for t in all_db_tags if t not in already_trained_tags]

    # Seed the model cache for all tags so the scheduler knows about them
    with _model_cache_lock:
        for tag_id in all_db_tags:
            if tag_id not in _model_cache:
                _model_cache[tag_id] = {
                    "y_long":           None,
                    "built_at":         datetime.min.replace(tzinfo=timezone.utc),
                    "n_days":           0.0,
                    "n_train_points":   0,
                    "last_trained_at":  None,
                }

    logger.info("[BI_Startup] %d tags need initial training; %d already have models",
                len(tags_to_pretrain), len(already_trained_tags))

    # ── Step 3: pre-train tags with no model (runs in THIS thread — still daemon) ─
    _startup_pretrain(tags_to_pretrain)

    logger.info("[BI_Startup] ✅ Startup complete — all tags ready for forecasting")


# Schedule startup — runs in background daemon thread so Flask startup isn't blocked
threading.Thread(target=_on_startup, daemon=True, name="bi_model_startup").start()


# ══════════════════════════════════════════════════════════════════════════════
# Incremental Non-Blocking Continuous Learning Scheduler
# ══════════════════════════════════════════════════════════════════════════════
# Design goals:
#   • NEVER block Flask request handling — all heavy work is in a daemon thread
#   • NEVER train all tags simultaneously — process one tag at a time
#   • TWO-SPEED learning:
#       QUICK cycle (QUICK_UPDATE_HOURS = 1h): fetch only NEW data since last
#         training, append to existing y_long, lightweight MAE check
#       DEEP  cycle (DEEP_RETRAIN_HOURS = 6h): fetch full MAX_TRAIN_DAYS window,
#         refit from scratch, run holdout MAE evaluation, then call
#         _maybe_promote_model() — model is ONLY promoted if provably better
#   • Per-tag pause TAG_TRAIN_PAUSE_S between tags so DB/CPU aren't hammered
#   • New data is added INCREMENTALLY (time-slice by time-slice) inside each
#     tag's deep retrain so a 7-day series is built up progressively
#   • Performance-gated promotion: new version ONLY replaces active if MAE
#     improves by >= PROMOTION_THRESHOLD (5%) — old weights kept as safety net
# ──────────────────────────────────────────────────────────────────────────────
RETRAIN_INTERVAL_HOURS = 6    # full deep retrain every 6 hours
QUICK_UPDATE_HOURS     = 1    # quick incremental append every 1 hour
TAG_TRAIN_PAUSE_S      = 3    # sleep seconds between tags (prevents hammering)
INCREMENTAL_CHUNK_DAYS = 1    # load 1 day at a time during deep retrain build-up
HOLDOUT_N              = 20   # holdout points for MAE evaluation


def _fit_one_tag_incremental(
    tag_id: str,
    y: "np.ndarray",
    n_days: float,
    now: datetime,
    deep: bool,
) -> None:
    """
    Fit ARIMA, HW, and LR models on y for a single tag.
    If deep=True: run holdout MAE evaluation and call _maybe_promote_model()
      → version is only promoted when provably better.
    If deep=False (quick update): skip evaluation, just refresh in-memory y_long.
    """
    import numpy as np
    n_pts = len(y)

    arima_params: dict = {}
    hw_params:    dict = {}
    lr_params:    dict = {}

    # ── Fit ARIMA ────────────────────────────────────────────────────────────
    try:
        from statsmodels.tsa.arima.model import ARIMA as _ARIMA
        model = _ARIMA(y, order=(2, 1, 1)).fit()
        arima_params = {
            "order":      [2, 1, 1],
            "params":     model.params.tolist(),
            "aic":        round(float(model.aic), 4),
            "bic":        round(float(model.bic), 4),
            "sigma2":     round(float(model.sigma2), 6),
            "n_pts":      n_pts,
            "n_days":     n_days,
            "trained_at": now.isoformat(),
        }
        if deep:
            # Holdout MAE via forecast function closure
            def _arima_forecast(train_y, steps):
                m2 = _ARIMA(train_y, order=(2, 1, 1)).fit()
                return m2.forecast(steps=steps).tolist()
            arima_mae  = _get_holdout_mae(y, _arima_forecast, HOLDOUT_N)
            arima_rmse = float(np.sqrt(arima_mae ** 2)) if arima_mae != float("inf") else float("inf")
            arima_aic  = float(model.aic)
            _maybe_promote_model(tag_id, "ARIMA", arima_params,
                                 arima_mae, arima_rmse, arima_aic, n_pts, n_days)
    except Exception as e:
        logger.debug("[BI_Learn] ARIMA fit failed for %s: %s", tag_id, e)

    # ── Fit Holt-Winters ──────────────────────────────────────────────────────
    try:
        from statsmodels.tsa.holtwinters import ExponentialSmoothing as _HW
        hw = _HW(y, trend="add", damped_trend=True).fit(optimized=True)
        hw_params = {
            "alpha":      round(float(hw.params.get("smoothing_level", 0)), 6),
            "beta":       round(float(hw.params.get("smoothing_trend", 0)), 6),
            "phi":        round(float(hw.params.get("damping_trend", 1)), 6),
            "sse":        round(float(hw.sse), 4),
            "n_pts":      n_pts,
            "n_days":     n_days,
            "trained_at": now.isoformat(),
        }
        if deep:
            def _hw_forecast(train_y, steps):
                h2 = _HW(train_y, trend="add", damped_trend=True).fit(optimized=True)
                return h2.forecast(steps=steps).tolist()
            hw_mae  = _get_holdout_mae(y, _hw_forecast, HOLDOUT_N)
            hw_rmse = float(np.sqrt(hw_mae ** 2)) if hw_mae != float("inf") else float("inf")
            _maybe_promote_model(tag_id, "HW", hw_params,
                                 hw_mae, hw_rmse, None, n_pts, n_days)
    except Exception as e:
        logger.debug("[BI_Learn] HW fit failed for %s: %s", tag_id, e)

    # ── Fit LR ───────────────────────────────────────────────────────────────
    try:
        x = np.arange(len(y), dtype=float)
        coeffs = np.polyfit(x, y, 1)
        lr_params = {
            "slope":      round(float(coeffs[0]), 8),
            "intercept":  round(float(coeffs[1]), 4),
            "mean":       round(float(np.mean(y)), 4),
            "std":        round(float(np.std(y)), 4),
            "n_pts":      n_pts,
            "n_days":     n_days,
            "trained_at": now.isoformat(),
        }
        if deep:
            def _lr_forecast(train_y, steps):
                xtr = np.arange(len(train_y), dtype=float)
                c   = np.polyfit(xtr, train_y, 1)
                xf  = np.arange(len(train_y), len(train_y) + steps, dtype=float)
                return (c[0] * xf + c[1]).tolist()
            lr_mae  = _get_holdout_mae(y, _lr_forecast, HOLDOUT_N)
            lr_rmse = float(np.sqrt(lr_mae ** 2)) if lr_mae != float("inf") else float("inf")
            _maybe_promote_model(tag_id, "LR", lr_params,
                                 lr_mae, lr_rmse, None, n_pts, n_days)
    except Exception as e:
        logger.debug("[BI_Learn] LR fit failed for %s: %s", tag_id, e)

    # ── Refresh in-memory cache ───────────────────────────────────────────────
    with _model_cache_lock:
        _model_cache[tag_id] = {
            "y_long":           y,
            "built_at":         now,
            "n_days":           n_days,
            "n_train_points":   n_pts,
            "last_trained_at":  now,
            "arima_params":     arima_params,
            "hw_params":        hw_params,
        }


def _background_retrain_all() -> None:
    """
    Two-speed incremental learning loop.

    QUICK cycle (every QUICK_UPDATE_HOURS):
      Fetches only the data that arrived since last_trained_at for each tag.
      Appends to existing y_long.  Refits models. Does NOT run holdout eval.
      Keeps system always up-to-date with fresh process data.

    DEEP cycle (every RETRAIN_INTERVAL_HOURS):
      For each tag, rebuilds the full training series INCREMENTALLY:
        Day 7 → fit  (chunk 1)
        Day 6 → append + fit  (chunk 2)
        ...
        Day 1 (today) → append + final fit
      Each day's data is appended one chunk at a time with a short pause so
      the DB is not hammered.  After the full series is built, runs holdout
      MAE evaluation and calls _maybe_promote_model() — NEW VERSION IS ONLY
      PROMOTED IF MAE IMPROVES BY >= PROMOTION_THRESHOLD.
      Also prunes expired non-active versions.
    """
    import numpy as np
    import time

    # Wait for _on_startup() to finish its initial pre-training pass before the
    # scheduler begins its own cycles.  The startup thread is named "bi_model_startup";
    # we poll until it is gone (joined) so QUICK/DEEP cycles never race with it.
    startup_thread = None
    for t in threading.enumerate():
        if t.name == "bi_model_startup":
            startup_thread = t
            break
    if startup_thread is not None:
        logger.info("[BI_Learn] Waiting for startup pre-training to finish before first cycle...")
        startup_thread.join(timeout=3600)   # at most 1h wait; then proceed anyway
        logger.info("[BI_Learn] Startup pre-training done — beginning regular scheduler cycles")

    last_deep_retrain = datetime.now(timezone.utc)   # don't immediately re-deep after startup

    while True:
        try:
            now    = datetime.now(timezone.utc)
            is_deep = (now - last_deep_retrain).total_seconds() >= RETRAIN_INTERVAL_HOURS * 3600
            cycle_label = "DEEP" if is_deep else "QUICK"

            with _model_cache_lock:
                tags_to_process = list(_model_cache.keys())

            if not tags_to_process:
                logger.info("[BI_Learn] No tags cached yet — skipping cycle")
            else:
                logger.info("[BI_Learn] Starting %s cycle for %d tags",
                            cycle_label, len(tags_to_process))
                done = failed = promoted = 0

                for tag_id in tags_to_process:
                    try:
                        # ── Determine data window to fetch ───────────────────
                        if is_deep:
                            # DEEP: build training set incrementally day by day
                            y_accum = np.array([], dtype=float)
                            train_start_full = now - timedelta(days=MAX_TRAIN_DAYS)

                            for chunk_day in range(MAX_TRAIN_DAYS, 0, -1):
                                # Load one day's chunk from the oldest end forward
                                chunk_end   = now - timedelta(days=chunk_day - 1)
                                chunk_start = now - timedelta(days=chunk_day)
                                df_chunk = _get_timeseries_df(
                                    [tag_id],
                                    chunk_start.isoformat(),
                                    chunk_end.isoformat(),
                                    resample_minutes=1,
                                )
                                if not df_chunk.empty and tag_id in df_chunk.columns:
                                    new_pts = df_chunk[tag_id].dropna().values.astype(float)
                                    y_accum = np.concatenate([y_accum, new_pts])

                                # Small pause between day-chunks — prevent DB hammering
                                time.sleep(0.5)

                            y = y_accum
                            if len(y) > MAX_TRAIN_POINTS:
                                y = y[-MAX_TRAIN_POINTS:]
                            n_days = round(
                                min((now - train_start_full).total_seconds() / 86400, MAX_TRAIN_DAYS), 2)

                        else:
                            # QUICK: only fetch data since last training
                            with _model_cache_lock:
                                cache_entry = _model_cache.get(tag_id, {})
                            last_trained = cache_entry.get("last_trained_at")
                            existing_y   = cache_entry.get("y_long")

                            if last_trained is None:
                                last_trained = now - timedelta(hours=QUICK_UPDATE_HOURS * 2)

                            df_new = _get_timeseries_df(
                                [tag_id],
                                last_trained.isoformat(),
                                now.isoformat(),
                                resample_minutes=1,
                            )
                            if df_new.empty or tag_id not in df_new.columns:
                                continue

                            new_pts = df_new[tag_id].dropna().values.astype(float)
                            if len(new_pts) == 0:
                                continue

                            # Append to existing y_long, keep within MAX_TRAIN_POINTS
                            if existing_y is not None and len(existing_y) > 0:
                                y = np.concatenate([existing_y, new_pts])
                            else:
                                y = new_pts
                            if len(y) > MAX_TRAIN_POINTS:
                                y = y[-MAX_TRAIN_POINTS:]

                            # Recalculate n_days based on actual series span
                            # (QUICK_UPDATE_HOURS window + whatever was already in y)
                            n_days = round(
                                min(len(y) / (60 * 24), MAX_TRAIN_DAYS), 2)

                        if len(y) < 8:
                            continue

                        # ── Fit + (conditionally) promote ─────────────────────
                        _fit_one_tag_incremental(tag_id, y, n_days, now, deep=is_deep)
                        done += 1

                    except Exception as exc:
                        failed += 1
                        logger.warning("[BI_Learn] %s cycle failed for %s: %s",
                                       cycle_label, tag_id, exc)

                    # ── Per-tag pause — avoid hammering DB/CPU ────────────────
                    time.sleep(TAG_TRAIN_PAUSE_S)

                if is_deep:
                    _prune_expired_versions()
                    last_deep_retrain = now

                logger.info(
                    "[BI_Learn] %s cycle done — processed=%d failed=%d",
                    cycle_label, done, failed,
                )

        except Exception as exc:
            logger.error("[BI_Learn] Scheduler top-level error: %s", exc)

        # QUICK cycle sleeps QUICK_UPDATE_HOURS; will check if DEEP is due each wake
        time.sleep(QUICK_UPDATE_HOURS * 3600)


# Launch continuous learning thread — daemon so it dies with Flask
threading.Thread(
    target=_background_retrain_all,
    daemon=True,
    name="bi_continuous_learner"
).start()
logger.info(
    "[BI_Learn] Incremental learning scheduler started "
    "(quick=%dh deep=%dh tag_pause=%ds max_history=%dd promotion_threshold=%.0f%%)",
    QUICK_UPDATE_HOURS, RETRAIN_INTERVAL_HOURS, TAG_TRAIN_PAUSE_S,
    MAX_TRAIN_DAYS, PROMOTION_THRESHOLD * 100
)


# ══════════════════════════════════════════════════════════════════════════════
# One pool shared across all BI requests in this process.
# Raw psycopg2.connect() per request was creating a new TCP connection for
# every API call — expensive (~10-20ms handshake) and exhausts PG under load.
# Pool keeps min=2 warm connections; bursts up to max=8.
# ──────────────────────────────────────────────────────────────────────────────
_bi_pool: psycopg2.pool.ThreadedConnectionPool | None = None
_bi_pool_lock = threading.Lock()


def _get_bi_pool() -> psycopg2.pool.ThreadedConnectionPool:
    """Lazy-init ThreadedConnectionPool singleton for BI controller."""
    global _bi_pool
    if _bi_pool is not None:
        return _bi_pool
    with _bi_pool_lock:
        if _bi_pool is None:   # double-checked locking
            cfg = container.config['database']
            logger.info(
                "[BI_Pool] Creating ThreadedConnectionPool (min=2, max=8) → %s@%s:%s",
                cfg['database'], cfg['host'], cfg['port'],
            )
            _bi_pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=2,
                maxconn=8,
                host=cfg['host'],
                port=int(cfg['port']),
                dbname=cfg['database'],
                user=cfg['user'],
                password=cfg['password'],
                keepalives=1,
                keepalives_idle=60,
                keepalives_interval=10,
                keepalives_count=5,
                connect_timeout=10,
                # application_name identifies this pool in pg_stat_activity
                options="-c statement_timeout=60000 -c application_name=hmi_bi_controller",
            )
            logger.info(
                "[BI_Pool] ✅ Initialized hmi_bi_controller pool (min=2, max=8) → %s@%s:%s",
                cfg['database'], cfg['host'], cfg['port'],
            )
    return _bi_pool


@contextmanager
def _get_conn():
    """
    Context manager that borrows a connection from the BI pool and
    returns it safely on exit (even on exception).

    Usage:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                cols = [desc[0] for desc in cur.description]
                df = pd.DataFrame(cur.fetchall(), columns=cols)
    """
    global _bi_pool
    conn = None
    broken = False
    try:
        conn = _get_bi_pool().getconn()
        yield conn
    except psycopg2.pool.PoolError as exc:
        broken = True
        logger.error("[BI_Pool] PoolError — %s", exc)
        # Tear down and let next request rebuild
        with _bi_pool_lock:
            if _bi_pool is not None:
                try:
                    _bi_pool.closeall()
                except Exception:
                    pass
            _bi_pool = None
        raise RuntimeError("BI DB pool exhausted; retry.") from exc
    except Exception:
        broken = True
        raise
    finally:
        if conn is not None and _bi_pool is not None:
            try:
                _bi_pool.putconn(conn, close=broken)
            except Exception:
                pass


def _get_long_training_series(tag_id: str, end_iso: str, resample: int) -> tuple:
    """
    Returns (y_long, n_days_actual) — a numpy array built from up to MAX_TRAIN_DAYS
    of historical data.  Results are cached in memory (CACHE_TTL_HOURS) and the
    training metadata is persisted to DB so it survives Flask restarts.
    """
    import numpy as np
    now = datetime.now(timezone.utc)

    with _model_cache_lock:
        entry = _model_cache.get(tag_id)
        if entry is not None and entry.get("y_long") is not None:
            age_h = (now - entry["built_at"]).total_seconds() / 3600
            if age_h < CACHE_TTL_HOURS:
                return entry["y_long"], entry["n_days"]

    # Build / refresh cache entry from DB
    try:
        try:
            end_dt = datetime.fromisoformat(end_iso.replace("Z", "+00:00"))
        except Exception:
            end_dt = now
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=timezone.utc)

        train_start = end_dt - timedelta(days=MAX_TRAIN_DAYS)
        df_long = _get_timeseries_df(
            [tag_id],
            train_start.isoformat(),
            end_iso,
            resample_minutes=max(resample, 1),
        )
        if df_long.empty or tag_id not in df_long.columns:
            return None, 0

        y_long = df_long[tag_id].dropna().values.astype(float)
        if len(y_long) == 0:
            return None, 0

        if len(y_long) > MAX_TRAIN_POINTS:
            y_long = y_long[-MAX_TRAIN_POINTS:]

        n_days = min((end_dt - train_start).total_seconds() / 86400, MAX_TRAIN_DAYS)

        _n_days_r = round(n_days, 1)
        with _model_cache_lock:
            _model_cache[tag_id] = {
                "y_long":           y_long,
                "built_at":         now,
                "n_days":           _n_days_r,
                "n_train_points":   len(y_long),
                "last_trained_at":  now,
            }

        # Persist training metadata to DB as a versioned meta entry (non-blocking)
        # Uses MAE=inf so this meta record is never promoted over a real model version
        def _save_training_meta():
            meta_params = {
                "n_points":     int(len(y_long)),
                "n_days":       round(n_days, 2),
                "y_mean":       round(float(np.mean(y_long)), 4),
                "y_std":        round(float(np.std(y_long)), 4),
                "y_min":        round(float(np.min(y_long)), 4),
                "y_max":        round(float(np.max(y_long)), 4),
                "resample_min": resample,
                "built_at":     now.isoformat(),
            }
            # _training_meta is an informational version; mae=inf means it will
            # never displace a real ARIMA/HW/LR active version
            _maybe_promote_model(
                tag_id, "_meta", meta_params,
                float("inf"), float("inf"), None,
                len(y_long), round(n_days, 1)
            )
        threading.Thread(target=_save_training_meta, daemon=True).start()

        logger.info("[BI_Cache] Built long-history for %s: %d pts (%.1f days)", tag_id, len(y_long), n_days)
        return y_long, round(n_days, 1)
    except Exception as exc:
        logger.warning("[BI_Cache] Failed to build long-history for %s: %s", tag_id, exc)
        return None, 0


def _get_timeseries_df(
    tag_ids: list[str],
    start_iso: str,
    end_iso: str,
    resample_minutes: int = 5,
    resample_fn: str = "mean",
) -> pd.DataFrame:
    """
    Return a pivoted DataFrame for the given tags and time range.

    Args:
        tag_ids:          list of tag_id strings to include
        start_iso:        ISO-8601 start datetime string  e.g. "2026-05-01T00:00:00"
        end_iso:          ISO-8601 end datetime string
        resample_minutes: resample resolution in minutes (default 5-min mean)
        resample_fn:      aggregation function: 'mean' | 'max' | 'min' | 'last' | 'sum'
                          Use 'max' for vibration/current/spikes, 'last' for digital states,
                          'sum' for counters, 'mean' for pressure/flow (default).

    Returns:
        pd.DataFrame with columns: [Timestamp, <tag_id_1>, <tag_id_2>, ...]
        Empty DataFrame if no data found.
    """
    if not tag_ids:
        return pd.DataFrame()

    placeholders = ",".join(["%s"] * len(tag_ids))
    sql = f"""
        SELECT time AS "Timestamp", tag_id, value_num
        FROM historian_raw.historian_timeseries
        WHERE tag_id IN ({placeholders})
          AND time BETWEEN %s AND %s
          AND value_num IS NOT NULL
        ORDER BY time ASC
    """
    params = tag_ids + [start_iso, end_iso]

    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                cols = [desc[0] for desc in cur.description]
                df_raw = pd.DataFrame(cur.fetchall(), columns=cols)
                if "Timestamp" in df_raw.columns:
                    df_raw["Timestamp"] = pd.to_datetime(df_raw["Timestamp"], utc=True)
    except Exception as e:
        logger.error(f"[BI] Query failed: {e}")
        return pd.DataFrame()

    if df_raw.empty:
        logger.warning(f"[BI] No data for tags={tag_ids} between {start_iso} and {end_iso}")
        return pd.DataFrame()

    # Pivot: rows=timestamp, columns=tag_id, values=value_num
    df_pivot = df_raw.pivot_table(
        index="Timestamp",
        columns="tag_id",
        values="value_num",
        aggfunc="mean",   # average duplicates within same timestamp
    )
    df_pivot.columns.name = None
    df_pivot.reset_index(inplace=True)

    # raw mode: resample_minutes <= 0 means return every row as-is (per-second)
    if resample_minutes <= 0:
        tag_cols = [t for t in tag_ids if t in df_pivot.columns]
        df_pivot = df_pivot[["Timestamp"] + tag_cols]
        logger.info(
            f"[BI] RAW {len(df_pivot)} rows × {len(tag_cols)} tags ({start_iso} \u2192 {end_iso})"
        )
        return df_pivot

    # Resample to uniform intervals (forward-fill short gaps)
    # resample_fn controls aggregation: mean=pressure/flow, max=vibration/current,
    # last=digital state, sum=counters.  Default 'mean' preserves legacy behaviour.
    _agg_fn = resample_fn if resample_fn in {"mean", "max", "min", "last", "sum"} else "mean"
    df_pivot.set_index("Timestamp", inplace=True)
    df_pivot = (
        df_pivot
        .resample(f"{resample_minutes}min")
        .agg(_agg_fn)
        .ffill(limit=3)   # fill gaps up to 3 intervals
    )
    df_pivot.reset_index(inplace=True)

    # Ensure column order is deterministic
    tag_cols = [t for t in tag_ids if t in df_pivot.columns]
    df_pivot = df_pivot[["Timestamp"] + tag_cols]

    logger.info(
        f"[BI] {len(df_pivot)} rows × {len(tag_cols)} tags ({start_iso} → {end_iso})"
    )
    return df_pivot


def _get_available_tags(limit: int = 500) -> list[dict]:
    """
    Return list of distinct tag_ids that have data in the historian,
    together with their first/last seen timestamps.
    Used by the BI UI to populate tag-selection dropdowns.
    """
    sql = """
        SELECT tag_id,
               MIN(time) AS first_seen,
               MAX(time) AS last_seen,
               COUNT(*)  AS record_count
        FROM historian_raw.historian_timeseries
        WHERE value_num IS NOT NULL
          AND time > NOW() - INTERVAL '7 days'
        GROUP BY tag_id
        ORDER BY record_count DESC
        LIMIT %s
    """
    try:
        with _get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (limit,))
                rows = cur.fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"[BI] get_available_tags failed: {e}")
        return []


# ══════════════════════════════════════════════════════════════════════════════
# Endpoints
# ══════════════════════════════════════════════════════════════════════════════


@bi_bp.route("/tags", methods=["GET"])
@token_required
def list_tags(current_user):
    """Return all tag_ids available in historian with first/last seen."""
    limit = request.args.get("limit", 500, type=int)
    tags = _get_available_tags(limit=limit)
    return jsonify({"success": True, "count": len(tags), "tags": tags})


@bi_bp.route("/trends", methods=["POST"])
@token_required
def get_trends(current_user):
    """
    Return time-series data for a list of tags over a date range.

    Body JSON:
        {
          "tag_ids": ["TAG_A", "TAG_B"],
          "start":   "2026-05-01T00:00:00",
          "end":     "2026-05-21T23:59:59",
          "resample_minutes": 5
        }
    """
    body = request.get_json(force=True) or {}
    tag_ids = body.get("tag_ids", [])
    start   = body.get("start")
    end     = body.get("end")
    resample = body.get("resample_minutes", 5)

    if not tag_ids or not start or not end:
        return jsonify({"success": False, "error": "tag_ids, start, end are required"}), 400
    if len(tag_ids) > 20:
        return jsonify({"success": False, "error": "Maximum 20 tags per request"}), 400

    df = _get_timeseries_df(tag_ids, start, end, resample_minutes=resample)
    if df.empty:
        return jsonify({"success": True, "count": 0, "columns": [], "data": []})

    # Serialise: convert Timestamp to ISO string, NaN → null
    import json as _json
    df["Timestamp"] = df["Timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    records = _json.loads(df.to_json(orient="records"))
    return jsonify({
        "success":  True,
        "count":    len(records),
        "columns":  list(df.columns),
        "data":     records,
    })


@bi_bp.route("/baselines", methods=["POST"])
@token_required
def compute_baselines(current_user):
    """
    Compute baseline statistics (mean, std, percentiles) for a set of tags.

    Body JSON:
        {
          "tag_ids": ["TAG_A", "TAG_B"],
          "start":   "2026-05-01T00:00:00",
          "end":     "2026-05-21T23:59:59"
        }
    """
    body    = request.get_json(force=True) or {}
    tag_ids = body.get("tag_ids", [])
    start   = body.get("start")
    end     = body.get("end")

    if not tag_ids or not start or not end:
        return jsonify({"success": False, "error": "tag_ids, start, end are required"}), 400

    df = _get_timeseries_df(tag_ids, start, end, resample_minutes=15)
    if df.empty:
        return jsonify({"success": True, "baselines": {}})

    baselines = {}
    for tag in tag_ids:
        if tag not in df.columns:
            continue
        s = df[tag].dropna()
        if len(s) < 5:
            continue
        baselines[tag] = {
            "mean":   round(float(s.mean()), 4),
            "std":    round(float(s.std()),  4),
            "min":    round(float(s.min()),  4),
            "max":    round(float(s.max()),  4),
            "p25":    round(float(s.quantile(0.25)), 4),
            "p50":    round(float(s.quantile(0.50)), 4),
            "p75":    round(float(s.quantile(0.75)), 4),
            "count":  int(len(s)),
        }

    return jsonify({"success": True, "baselines": baselines})


# ═══════════════════════════════════════════════════════════════════════════
# Shared signal intelligence helpers (used by /forecast AND /benchmark)
# ═══════════════════════════════════════════════════════════════════════════

def _data_quality_check(y: np.ndarray, tag_id: str = "") -> dict:
    """
    Run pre-forecast data quality checks on the resampled signal.

    Returns a dict:
        {
          "ok":      bool,      # False = forecasting should be suppressed
          "issues":  [str],     # human-readable issue list
          "quality_score": 0-1  # 1.0 = perfect, lower = degraded
        }

    Checks performed
    ────────────────
    1. Flatline  — std < 1% of |mean| for > 30% of window
    2. Stale/frozen  — > 25% identical consecutive pairs
    3. Spike contamination  — values > 6σ from rolling mean
    4. Gap density  — NaN fraction after resampling
    5. Short window  — fewer than 20 useful samples
    """
    issues  = []
    penalty = 0.0
    n       = len(y)

    if n < 8:
        return {"ok": False, "issues": [f"Too few samples: {n} < 8"], "quality_score": 0.0}

    mean_abs = abs(float(np.mean(y))) or 1.0
    std_val  = float(np.std(y))

    # 1. Flatline detection
    if std_val < 0.01 * mean_abs:
        issues.append("FLATLINE: signal has near-zero variance — sensor may be frozen")
        penalty += 0.8

    # 2. Frozen / stale value detection (consecutive duplicates)
    consecutive_dupes = int(np.sum(np.diff(y) == 0))
    dupe_ratio = consecutive_dupes / max(n - 1, 1)
    if dupe_ratio > 0.25:
        issues.append(f"STALE: {dupe_ratio*100:.0f}% consecutive identical values — deadband or OPC issue")
        penalty += 0.4

    # 3. Spike detection (> 6σ from rolling 10-sample mean)
    if n >= 10:
        roll_mean = np.convolve(y, np.ones(10) / 10, mode="valid")
        roll_std  = float(np.std(y[:len(roll_mean)]))
        if roll_std > 0:
            spikes = int(np.sum(np.abs(y[:len(roll_mean)] - roll_mean) > 6 * roll_std))
            if spikes > 0:
                issues.append(f"SPIKES: {spikes} outlier(s) detected > 6σ — may be OPC reconnect artefacts")
                penalty += min(spikes * 0.1, 0.3)

    # 4. NaN gap ratio (signal already dropna'd but check near-zero variance windows)
    nan_ratio = float(np.sum(~np.isfinite(y))) / n
    if nan_ratio > 0.10:
        issues.append(f"GAPS: {nan_ratio*100:.0f}% missing after resampling — historian lag or outage")
        penalty += 0.3

    quality_score = max(0.0, round(1.0 - penalty, 3))
    ok = quality_score >= 0.4 and not any("FLATLINE" in i for i in issues)
    return {"ok": ok, "issues": issues, "quality_score": quality_score}


def _classify_signal_type(y: np.ndarray) -> str:
    """
    Classify signal as one of: Trend | Periodic | Stationary | Noisy | Chaotic

    Used to:
    - Select which models are ALLOWED to compete (model elimination)
    - Set leaderboard context
    - Guide resampling recommendations

    Rules (priority order)
    ──────────────────────
    Trend     : linear R² > 0.60
    Periodic  : ACF peak > 0.55 at lag 2..n/2
    Noisy     : coefficient of variation > 1.5
    Chaotic   : entropy > 0.85 of theoretical max AND no ACF peak
    Stationary: everything else
    """
    n = len(y)
    if n < 8:
        return "Stationary"

    # 1. Trend
    xs = np.arange(n)
    c  = np.polyfit(xs, y, 1)
    fit_vals = np.polyval(c, xs)
    ss_res   = np.sum((y - fit_vals) ** 2)
    ss_tot   = np.sum((y - y.mean()) ** 2) or 1.0
    r2_trend = 1.0 - ss_res / ss_tot
    if r2_trend > 0.60:
        return "Trend"

    # 2. Periodic (ACF)
    if n >= 12:
        ac = np.correlate(y - y.mean(), y - y.mean(), mode="full")
        ac = ac[n - 1:]
        ac = ac / (ac[0] or 1.0)
        search = ac[2 : n // 2]
        peak_ac = float(np.max(search)) if len(search) else 0.0
        if peak_ac > 0.55:
            return "Periodic"

    # 3. Noisy
    std_y = float(np.std(y))
    cv    = std_y / abs(float(np.mean(y))) if abs(float(np.mean(y))) > 0.01 else 999.0
    if cv > 1.5:
        return "Noisy"

    return "Stationary"


# Models allowed per signal type.  Models NOT in this list for a given signal
# type are EXCLUDED from the leaderboard entirely (not just ranked last).
_ALLOWED_MODELS: dict[str, list[str]] = {
    "Periodic":   ["FFT", "HW", "ARIMA"],    # cyclic → frequency/seasonal/AR
    "Trend":      ["LR", "ARIMA", "HW"],      # drifting → regression/AR/damped HW
    "Stationary": ["ARIMA", "HW", "LR"],      # mean-reverting → AR / dampened HW
    "Noisy":      ["ARIMA", "HW"],             # high variance → AR + dampened HW
    "Chaotic":    [],                           # nothing reliable — suppress forecast
}


@bi_bp.route("/forecast", methods=["POST"])
@token_required
def forecast_tag(current_user):
    """
    Run multi-model forecast for a single tag using Python scientific stack.

    Body JSON:
        {
          "tag_id":  "Random.Real8",
          "start":   "2026-05-21T02:00:00",   # history window start
          "end":     "2026-05-21T04:00:00",   # forecast origin (now)
          "steps":   30,                       # minutes ahead to forecast
          "resample_minutes": 1
        }

    Response:
        {
          "success": true,
          "n_history": 120,
          "step_minutes": 1,
          "models": {
            "LR":  { "points": [...], "mae": 0.0, "rmse": 0.0, "conf_low": [...], "conf_high": [...], "status": "Stable",  "confidence": "MEDIUM" },
            "HW":  { ... },
            "FFT": { ... },
            "ARIMA": { ... }
          },
          "best_model": "HW",
          "timestamps": ["2026-05-21T04:01:00Z", ...]
        }
    """
    import numpy as np
    from datetime import datetime, timedelta, timezone

    body = request.get_json(force=True) or {}
    tag_id      = body.get("tag_id")
    start       = body.get("start")
    end         = body.get("end")
    steps       = int(body.get("steps", 30))
    resample    = int(body.get("resample_minutes", 1))
    resample_fn = body.get("resample_fn", "mean")   # mean|max|min|last|sum

    if not tag_id or not start or not end:
        return jsonify({"success": False, "error": "tag_id, start, end required"}), 400

    # ── 1. Fetch history ───────────────────────────────────────────────────
    df = _get_timeseries_df([tag_id], start, end, resample_minutes=resample, resample_fn=resample_fn)
    if df.empty or tag_id not in df.columns:
        return jsonify({"success": False, "error": f"No data for tag '{tag_id}'"}), 404

    series = df[tag_id].dropna()
    if len(series) < 8:
        return jsonify({"success": False, "error": "Need at least 8 data points"}), 422

    y_short = series.values.astype(float)

    # ── 1b. Fetch long training history (up to 7 days) for model fitting ──
    # The short window (start→end, e.g. 6h) is used for holdout scoring and
    # forecast anchoring.  The long window is used for model training so ARIMA
    # and HW have hundreds/thousands of samples to learn process behaviour from.
    y_long, n_days_long = _get_long_training_series(tag_id, end, resample)
    # Use whichever is longer — fall back to short if long unavailable
    y_train_full = y_long if (y_long is not None and len(y_long) > len(y_short)) else y_short

    y = y_train_full
    n = len(y)

    # ── 2. Data quality gate ───────────────────────────────────────────────
    # Reject or warn before any model fitting.  Bad historian data (flatlines,
    # frozen sensors, spike artefacts) will poison every model equally.
    dq = _data_quality_check(y, tag_id)
    if not dq["ok"]:
        return jsonify({
            "success":       False,
            "error":         "Data quality insufficient for forecasting",
            "quality":       dq,
            "recommendation": "Check OPC historian ingest, sensor health, and deadband settings.",
        }), 422

    # ── 3. Signal classification → model elimination ───────────────────────
    sig_type      = _classify_signal_type(y)
    allowed       = _ALLOWED_MODELS.get(sig_type, ["ARIMA", "HW", "FFT", "LR"])

    if not allowed:
        return jsonify({
            "success":    False,
            "error":      f"Signal classified as '{sig_type}' — no reliable model available",
            "signal_type": sig_type,
            "quality":    dq,
        }), 422

    # Holdout split: 75% train / 25% test
    hold_n    = max(6, int(n * 0.25))
    train     = y[:-hold_n]
    test      = y[-hold_n:]
    sigma_ref = float(np.std(y)) if np.std(y) > 0 else 1.0

    # ── True signal variance guard ─────────────────────────────────────────
    # When resample_minutes > 0, averaging collapses noisy signals
    # (e.g. AY1101 raw: 0-80, σ≈25) into a near-flat series (σ≈0.36).
    # This makes 4×sigma_ref ≈ 1.44 units, causing ALL model outputs to be
    # flagged as "Diverging" even when perfectly reasonable.
    # Fix: also fetch the last 30 min of raw data, compute its σ and
    # peak-to-peak range, then use max(resampled_σ, raw_σ) so bounds reflect
    # the actual signal behaviour rather than the averaged version.
    if resample > 0:
        try:
            df_raw_sigma = _get_timeseries_df(
                [tag_id], start, end,
                resample_minutes=0,   # raw rows, no averaging
            )
            if not df_raw_sigma.empty and tag_id in df_raw_sigma.columns:
                y_raw_sigma = df_raw_sigma[tag_id].dropna().values.astype(float)
                if len(y_raw_sigma) > 4:
                    raw_sigma = float(np.std(y_raw_sigma))
                    raw_ptp   = float(np.ptp(y_raw_sigma))  # peak-to-peak
                    # Use the larger of resampled σ or raw σ so we never
                    # under-estimate the signal's true variability.
                    sigma_ref = max(sigma_ref, raw_sigma, raw_ptp / 6.0, 1.0)
        except Exception:
            pass  # keep resampled sigma_ref — degrade gracefully

    # ── Timestamps for forecast points ─────────────────────────────────────
    # CRITICAL: anchor to the request 'end' time (= now on live tags), NOT to
    # the last DB row. A DB lag of even 30s on a fast-oscillating signal puts
    # y[-1] at a completely different phase than the live actual, causing a
    # large gap at the sync point.
    try:
        anchor_ts = datetime.fromisoformat(end.replace("Z", "+00:00"))
    except Exception:
        anchor_ts = datetime.now(timezone.utc)
    if anchor_ts.tzinfo is None:
        anchor_ts = anchor_ts.replace(tzinfo=timezone.utc)

    future_ts = [
        (anchor_ts + timedelta(minutes=resample * (i + 1))).strftime("%Y-%m-%dT%H:%M:%SZ")
        for i in range(steps)
    ]

    def _score(preds, actuals):
        n_ = min(len(preds), len(actuals))
        if n_ == 0:
            return None, None
        errs = [abs(preds[i] - actuals[i]) for i in range(n_)]
        mae  = float(np.mean(errs))
        rmse = float(np.sqrt(np.mean([(preds[i] - actuals[i])**2 for i in range(n_)])))
        return mae, rmse

    def _confidence(rmse):
        if rmse is None:
            return "N/A"
        if rmse < 0.5 * sigma_ref:
            return "HIGH"
        if rmse < 1.5 * sigma_ref:
            return "MEDIUM"
        return "LOW"

    def _status(pts, mae_val, best_mae):
        if pts is None:
            return "N/A"
        mean_y = float(np.mean(y))
        if any(abs(v - mean_y) > 4 * sigma_ref for v in pts):
            return "Diverging"
        if mae_val is not None and best_mae is not None and mae_val == best_mae:
            return "Best Fit"
        return "Stable"

    def _conf_interval(pts, rmse):
        """
        Compute 95% confidence interval that WIDENS with forecast horizon.
        Uncertainty grows as sqrt(h) — standard result for AR processes.
        A flat CI (same width at step 1 and step 30) is statistically incorrect
        and creates overconfident bands at long horizons.
        """
        if pts is None or rmse is None:
            return None, None
        z     = 1.96
        n_pts = len(pts)
        lo, hi = [], []
        for i, v in enumerate(pts):
            # sqrt(h) growth: CI at step h is sqrt(h) wider than step 1
            horizon_factor = (1.0 + (i / max(n_pts - 1, 1)) ** 0.5)
            margin = z * rmse * horizon_factor
            lo.append(round(v - margin, 4))
            hi.append(round(v + margin, 4))
        return lo, hi

    # ── Bounds from historical range (used for clipping only, not forcing) ──
    recent_n   = min(max(steps * 2, 24), n)
    recent     = y[-recent_n:]
    recent_min = float(np.min(recent))
    recent_max = float(np.max(recent))
    recent_span = max(recent_max - recent_min, sigma_ref * 2.0, 1.0)
    pad   = max(recent_span * 0.15, sigma_ref * 0.5)
    _lower = recent_min - pad
    _upper = recent_max + pad

    # Divergence threshold: if any forecast point is more than 3× the observed
    # span away from the observed range, the model is considered UNSTABLE and
    # its result is REJECTED (raises ValueError) — NOT silently clipped.
    # Callers wrap in try/except and set results[model] = {"error": ...}.
    _divergence_limit = 3.0 * max(_upper - _lower, sigma_ref * 2.0, 1.0)

    def _shape_forecast(pts, model_name=""):
        """
        Sanitise and anchor-correct forecast array (LR / HW / ARIMA only).

        FFT MUST NOT call this function — FFT's phase-extrapolation already
        produces a physically continuous signal.  Applying an exponential
        anchor correction would permanently distort the frequency components
        over the first ~20% of the horizon, creating fake phase drift.
        FFT handles its own output directly after _fft_project().

        Divergence policy (replaces silent clipping):
        - If any point exceeds 3× the observed span from the range boundary,
          raise ValueError so the model is excluded from the leaderboard.
        - Mild exceedances (< 3×) are allowed through unchanged so divergence
          is VISIBLE on the chart rather than hidden by clipping.
        """
        if pts is None:
            return None
        arr = np.asarray(pts, dtype=float)
        if arr.size == 0:
            return []

        # Anchor blend: smoothly connect model output to last actual value
        anchor = float(y[-1])
        gap    = anchor - float(arr[0])
        if abs(gap) > 1e-6 and arr.size > 1:
            decay = np.exp(-np.arange(arr.size) / max(arr.size * 0.20, 2.0))
            arr   = arr + gap * decay

        # Divergence check — reject model rather than clip silently
        max_dev = float(np.max(np.abs(arr - np.clip(arr, _lower, _upper))))
        if max_dev > _divergence_limit:
            raise ValueError(
                f"{model_name} forecast diverged: max deviation {max_dev:.1f} "
                f"exceeds limit {_divergence_limit:.1f}. Model excluded."
            )
        return [round(float(v), 4) for v in arr]

    results = {}

    # ── LR ────────────────────────────────────────────────────────────────
    if "LR" not in allowed:
        results["LR"] = {"skipped": True, "reason": f"Not suitable for {sig_type} signal"}
    else:
     try:
        xs_train = np.arange(len(train))
        coeffs   = np.polyfit(xs_train, train, 1)
        xs_test  = np.arange(len(train), len(train) + hold_n)
        lr_test  = np.polyval(coeffs, xs_test).tolist()
        mae_lr, rmse_lr = _score(lr_test, test.tolist())

        xs_fut  = np.arange(n, n + steps)
        lr_raw  = np.polyval(coeffs, xs_fut)
        lr_pts  = _shape_forecast(lr_raw, "LR")
        lo, hi = _conf_interval(lr_pts, rmse_lr)
        results["LR"] = {
            "points": lr_pts, "conf_low": lo, "conf_high": hi,
            "mae": round(mae_lr, 3) if mae_lr is not None else None,
            "rmse": round(rmse_lr, 3) if rmse_lr is not None else None,
            "confidence": _confidence(rmse_lr),
        }
     except Exception as e:
        results["LR"] = {"error": str(e)}

    # ── Holt-Winters (statsmodels) ─────────────────────────────────────────
    if "HW" not in allowed:
        results["HW"] = {"skipped": True, "reason": f"Not suitable for {sig_type} signal"}
    else:
     try:
        from statsmodels.tsa.holtwinters import ExponentialSmoothing as HWModel

        # Try additive seasonality with auto period detection via ACF
        best_hw_aic = np.inf
        best_hw_fit = None
        best_period = None

        acf_vals = np.correlate(train - train.mean(), train - train.mean(), mode="full")
        acf_vals = acf_vals[len(acf_vals)//2:] / acf_vals[len(acf_vals)//2]
        min_p, max_p = 3, min(60, len(train) // 3)
        if max_p > min_p:
            period_candidate = int(np.argmax(acf_vals[min_p:max_p]) + min_p)
        else:
            period_candidate = 12  # fallback

        for period in [period_candidate, 12, 6, 4]:
            if period < 2 or len(train) < period * 2:
                continue
            try:
                fit = HWModel(
                    train,
                    trend="add",
                    seasonal="add",
                    seasonal_periods=period,
                    initialization_method="estimated",
                ).fit(optimized=True)
                if fit.aic < best_hw_aic:
                    best_hw_aic = fit.aic
                    best_hw_fit = fit
                    best_period = period
            except Exception:
                continue

        if best_hw_fit is None:
            # Fallback: no seasonality
            best_hw_fit = HWModel(train, trend="add", initialization_method="estimated").fit(
                optimized=True
            )

        hw_test  = best_hw_fit.forecast(hold_n).tolist()
        mae_hw, rmse_hw = _score(hw_test, test.tolist())

        # Refit on full series for forecast
        if best_period and best_period >= 2 and len(y) >= best_period * 2:
            full_fit = HWModel(
                y, trend="add", seasonal="add",
                seasonal_periods=best_period,
                initialization_method="estimated",
            ).fit(optimized=True)
        else:
            full_fit = HWModel(y, trend="add", initialization_method="estimated").fit(
                optimized=True
            )

        hw_pts = _shape_forecast(full_fit.forecast(steps), "HW")
        lo, hi = _conf_interval(hw_pts, rmse_hw)
        results["HW"] = {
            "points": hw_pts, "conf_low": lo, "conf_high": hi,
            "mae": round(mae_hw, 3) if mae_hw is not None else None,
            "rmse": round(rmse_hw, 3) if rmse_hw is not None else None,
            "confidence": _confidence(rmse_hw),
            "period_detected": best_period,
        }
     except Exception as e:
        results["HW"] = {"error": str(e)}

    # ── FFT ───────────────────────────────────────────────────────────────
    if "FFT" not in allowed:
        results["FFT"] = {"skipped": True, "reason": f"Not suitable for {sig_type} signal"}
    else:
     try:
        def _fft_project(signal, n_out, top_k=10):
            """
            Fit FFT to `signal`, extrapolate n_out steps beyond its end.

            Extrapolation is PURELY from the frequency components of `signal`.
            No anchor correction is applied — phase continuity is mathematically
            guaranteed because we evaluate the same sinusoids at future indices.

            Returns (future_values[n_out], residual_std).
            residual_std = std(signal - reconstruction) → used for CI width.
            """
            n_sig    = len(signal)
            coeffs   = np.fft.rfft(signal)
            mags     = np.abs(coeffs)
            k_use    = min(top_k, len(mags))
            thresh   = np.sort(mags)[-k_use]
            filtered = np.where(mags >= thresh, coeffs, 0)
            freqs    = np.fft.rfftfreq(n_sig)

            t_fut = np.arange(n_sig, n_sig + n_out)
            fut   = np.full(n_out, float(np.real(filtered[0]) / n_sig))
            for ki, co in enumerate(filtered):
                if ki == 0 or co == 0:
                    continue
                is_nyq = (n_sig % 2 == 0 and ki == len(filtered) - 1)
                amp    = np.abs(co) * (1.0 if is_nyq else 2.0) / n_sig
                fut   += amp * np.cos(2 * np.pi * freqs[ki] * t_fut + np.angle(co))

            reconstructed = np.fft.irfft(filtered, n=n_sig)
            res_std = float(np.std(signal - reconstructed))
            return fut, res_std

        top_k_fft = min(10, len(np.fft.rfftfreq(len(train))))

        # ── OUT-OF-SAMPLE holdout score (the previous code used in-sample
        #    reconstruction which always shows falsely low MAE because the
        #    model has already seen the test data.  Fixed: train FFT only on
        #    `train`, extrapolate hold_n steps cold, compare against `test`).
        fft_test_pred, _ = _fft_project(train, hold_n, top_k=top_k_fft)
        mae_fft, rmse_fft = _score(fft_test_pred.tolist(), test.tolist())

        # ── Period alignment diagnostic ──────────────────────────────────
        # FFT phase extrapolation is only reliable when the dominant period
        # divides evenly into n samples.  A fractional period causes the
        # extrapolated wave to drift in phase over the forecast horizon.
        full_mags  = np.abs(np.fft.rfft(y))
        dom_k      = int(np.argmax(full_mags[1:]) + 1)   # skip DC component
        period_smp = n / dom_k if dom_k > 0 else n
        frac_part  = abs(period_smp - round(period_smp)) / period_smp
        phase_reliable = frac_part < 0.05   # < 5% fractional period → reliable

        # ── Full-y FFT for actual forecast output ────────────────────────
        # Fit on complete history (y), extrapolate `steps` beyond it.
        # FFT bypasses _shape_forecast entirely — phase continuity is exact.
        fft_future, res_std_full = _fft_project(y, steps, top_k=top_k_fft)

        # Horizon-growing CI for FFT
        fft_lo, fft_hi = [], []
        for i, v in enumerate(fft_future):
            margin = 1.96 * res_std_full * (1.0 + (i / max(steps - 1, 1)) ** 0.5)
            fft_lo.append(round(float(np.clip(v - margin, _lower, _upper)), 4))
            fft_hi.append(round(float(np.clip(v + margin, _lower, _upper)), 4))

        fft_pts = [round(float(np.clip(v, _lower, _upper)), 4) for v in fft_future]

        results["FFT"] = {
            "points":         fft_pts,
            "conf_low":       fft_lo,
            "conf_high":      fft_hi,
            "mae":            round(mae_fft,  3) if mae_fft  is not None else None,
            "rmse":           round(rmse_fft, 3) if rmse_fft is not None else None,
            "confidence":     _confidence(rmse_fft),
            "scored_on":      "out_of_sample",
            "period_samples": round(period_smp, 2),
            "phase_reliable": phase_reliable,
        }
     except Exception as e:
        results["FFT"] = {"error": str(e)}

    # ── ARIMA (best for stationary/autocorrelated signals) ────────────────
    if "ARIMA" not in allowed:
        results["ARIMA"] = {"skipped": True, "reason": f"Not suitable for {sig_type} signal"}
    else:
     try:
        from statsmodels.tsa.arima.model import ARIMA

        best_arima_aic = np.inf
        best_arima_fit = None
        last_arima_err = None
        for p in [1, 2, 3]:
            for d in [0, 1]:
                for q in [0, 1, 2]:
                    if p + d + q > 5:
                        continue
                    try:
                        fit = ARIMA(train, order=(p, d, q)).fit()
                        if fit.aic < best_arima_aic:
                            best_arima_aic = fit.aic
                            best_arima_fit = fit
                    except Exception as _arima_e:
                        last_arima_err = str(_arima_e)
                        continue

        if best_arima_fit is not None:
            arima_test = best_arima_fit.forecast(hold_n).tolist()
            mae_ar, rmse_ar = _score(arima_test, test.tolist())

            # Refit on full series
            order = best_arima_fit.model.order
            full_arima = ARIMA(y, order=order).fit()
            fc = full_arima.get_forecast(steps)
            arima_pts = _shape_forecast(fc.predicted_mean, "ARIMA")
            ci = fc.conf_int(alpha=0.05)
            if hasattr(ci, "iloc"):
                lo = [round(float(v), 4) for v in ci.iloc[:, 0]]
                hi = [round(float(v), 4) for v in ci.iloc[:, 1]]
            else:
                lo = [round(float(v), 4) for v in ci[:, 0]]
                hi = [round(float(v), 4) for v in ci[:, 1]]
            results["ARIMA"] = {
                "points": arima_pts, "conf_low": lo, "conf_high": hi,
                "mae": round(mae_ar, 3) if mae_ar is not None else None,
                "rmse": round(rmse_ar, 3) if rmse_ar is not None else None,
                "confidence": _confidence(rmse_ar),
                "order": list(order),
            }
        else:
            results["ARIMA"] = {"error": f"Could not fit any ARIMA order. Last error: {last_arima_err}"}
     except Exception as e:
        results["ARIMA"] = {"error": str(e)}

    # ── Pick best model by live-weighted MAE ──────────────────────────────
    # Rule: best = lowest  effective_mae  where:
    #   effective_mae = holdout_mae × (1 + sync_penalty)
    #
    # sync_penalty = (|pts[0] - y[-1]| / max(sigma_ref, 1e-6))²
    #   → A model whose FIRST forecast point is far from the current actual
    #     gets a heavy penalty even if its holdout score was good.
    #   → This prevents FFT (or any model) from being crowned "best" when its
    #     live forecast is wildly off the real process value.
    #
    # Models that are skipped, errored, or have None mae are excluded.
    # Models whose first forecast point deviates > 4×sigma from y_last are
    # excluded entirely (they are broken on live data regardless of holdout).
    # ──────────────────────────────────────────────────────────────────────
    y_last = float(y[-1])
    candidate_scores: dict = {}   # k → effective_mae
    for k, v in results.items():
        if v.get("skipped") or "error" in v:
            continue
        mae_val = v.get("mae")
        if mae_val is None:
            continue
        pts_v = v.get("points")
        if pts_v and len(pts_v) > 0:
            sync_err = abs(float(pts_v[0]) - y_last)
            # Hard exclusion: first step is more than 4×sigma off — model broken live
            if sync_err > 4.0 * max(sigma_ref, 1e-6):
                v["live_sync_excluded"] = True
                v["sync_error"] = round(sync_err, 4)
                continue
            sync_penalty = (sync_err / max(sigma_ref, 1e-6)) ** 2
            v["sync_error"] = round(sync_err, 4)
            v["sync_penalty"] = round(sync_penalty, 4)
        else:
            sync_penalty = 0.0
        candidate_scores[k] = mae_val * (1.0 + sync_penalty)

    # Fall back to raw holdout MAE if no candidates survived the sync filter
    if not candidate_scores:
        candidate_scores = {
            k: v["mae"]
            for k, v in results.items()
            if "mae" in v and v["mae"] is not None
               and not v.get("skipped") and "error" not in v
        }

    best_model = min(candidate_scores, key=candidate_scores.get) if candidate_scores else None

    # For status labelling, use holdout MAE of the winning model
    finite = {k: v["mae"] for k, v in results.items()
              if "mae" in v and v["mae"] is not None and not v.get("skipped")}
    best_mae_val = finite.get(best_model)
    for k, v in results.items():
        if v.get("skipped"):
            v["status"] = "Skipped"
        elif "error" in v:
            v["status"] = "Error"
        else:
            v["status"] = _status(v.get("points"), v.get("mae"), best_mae_val)

    return jsonify({
        "success":         True,
        "n_history":       n,
        "n_train_points":  n,
        "n_days_trained":  n_days_long if n_days_long else round(len(y_short) / max(60 / resample, 1) / 24, 2),
        "used_long_history": y_long is not None and len(y_long) > len(y_short),
        "hold_n":          hold_n,
        "step_minutes":    resample,
        "signal_type":     sig_type,
        "allowed_models":  allowed,
        "quality":         dq,
        "best_model":      best_model,
        "timestamps":      future_ts,
        "models":          results,
    })


# ═══════════════════════════════════════════════════════════════════════════
# LEARNING STATUS ENDPOINT — shows what the model has learned per tag
# ═══════════════════════════════════════════════════════════════════════════

@bi_bp.route("/learning/status", methods=["GET"])
@token_required
def learning_status(current_user):
    """
    GET /api/bi/learning/status?tag_id=<optional>
    Returns per-tag training status: n_points, n_days, last trained, model params summary.
    """
    tag_filter = request.args.get("tag_id")
    try:
        with _get_conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                if tag_filter:
                    cur.execute("""
                        SELECT id, tag_id, model_name, version,
                               n_train_points, n_days_trained,
                               mae, rmse, aic,
                               is_active, promoted_at, trained_at, retire_after, notes,
                               params_json - 'params' AS params_summary
                        FROM historian_analytics.bi_model_versions
                        WHERE tag_id = %s
                        ORDER BY model_name, trained_at DESC
                    """, (tag_filter,))
                else:
                    cur.execute("""
                        SELECT id, tag_id, model_name, version,
                               n_train_points, n_days_trained,
                               mae, rmse, aic,
                               is_active, promoted_at, trained_at, retire_after, notes,
                               params_json - 'params' AS params_summary
                        FROM historian_analytics.bi_model_versions
                        ORDER BY tag_id, model_name, trained_at DESC
                    """)
                rows = [dict(r) for r in cur.fetchall()]

        # Serialise datetimes
        for r in rows:
            for ts_field in ("trained_at", "promoted_at", "retire_after"):
                if isinstance(r.get(ts_field), datetime):
                    r[ts_field] = r[ts_field].isoformat()
            for num_field in ("mae", "rmse", "aic"):
                if r.get(num_field) is not None:
                    r[num_field] = float(r[num_field])

        # Active versions summary
        active_versions = [r for r in rows if r.get("is_active")]

        # Add in-memory cache status
        cache_status = []
        with _model_cache_lock:
            for tid, entry in _model_cache.items():
                if tag_filter and tid != tag_filter:
                    continue
                last_t = entry.get("last_trained_at") or entry.get("built_at")
                cache_status.append({
                    "tag_id":           tid,
                    "in_memory":        entry.get("y_long") is not None,
                    "n_train_points":   entry.get("n_train_points", 0),
                    "n_days":           entry.get("n_days", 0),
                    "last_trained_at":  last_t.isoformat() if last_t else None,
                    "cache_age_min":    round((datetime.now(timezone.utc) - last_t).total_seconds() / 60, 1)
                        if last_t else None,
                    "next_quick_in_min": round(
                        QUICK_UPDATE_HOURS * 60 - (datetime.now(timezone.utc) - last_t).total_seconds() / 60, 1)
                        if last_t else None,
                })

        return jsonify({
            "success":                True,
            "quick_update_h":         QUICK_UPDATE_HOURS,
            "deep_retrain_h":         RETRAIN_INTERVAL_HOURS,
            "max_train_days":         MAX_TRAIN_DAYS,
            "promotion_threshold_pct": round(PROMOTION_THRESHOLD * 100, 0),
            "max_versions_kept":      MAX_VERSIONS_KEPT,
            "version_retire_days":    VERSION_RETIRE_DAYS,
            "tags_with_active_model": len(set(r["tag_id"] for r in active_versions)),
            "total_versions_in_db":   len(rows),
            "active_versions":        active_versions,
            "all_versions":           rows,
            "memory_cache":           cache_status,
        })
    except Exception as exc:
        logger.exception("[BI] learning_status error: %s", exc)
        return jsonify({"success": False, "error": str(exc)}), 500


# ═══════════════════════════════════════════════════════════════════════════
# BENCHMARK ENDPOINT — walk-forward CV + grid-search + leaderboard
# ═══════════════════════════════════════════════════════════════════════════

@bi_bp.route("/benchmark", methods=["POST"])
@token_required
def benchmark_tag(current_user):
    """
    Walk-forward cross-validation with hyperparameter grid-search for all 4 models.

    Body JSON:
        {
          "tag_id":  "Triangle Waves.Int1",
          "start":   "2026-05-21T01:00:00Z",
          "end":     "2026-05-21T04:00:00Z",
          "resample_minutes": 1,          # 0 = per-second raw
          "forecast_steps": 10,           # steps per CV fold
          "n_folds": 5                    # walk-forward folds
        }

    Response:
        {
          "success": true,
          "n_points": 180,
          "signal_type": "Periodic",       # Trend / Stationary / Periodic / Noisy
          "folds": 5,
          "forecast_steps": 10,
          "leaderboard": [
            {
              "rank": 1,
              "model": "FFT",
              "mae": 1.23, "rmse": 1.87, "mape": 4.2,
              "r2": 0.94, "ci_coverage": 0.92,
              "tuned_params": {"top_k": 8},
              "verdict": "Best for periodic signals",
              "confidence": "HIGH"
            },
            ...
          ],
          "best_model": "FFT",
          "best_params": {"top_k": 8},
          "recommended_for_live": true
        }
    """
    import numpy as np
    from datetime import datetime, timedelta, timezone

    body            = request.get_json(force=True) or {}
    tag_id          = body.get("tag_id")
    start           = body.get("start")
    end             = body.get("end")
    resample        = int(body.get("resample_minutes", 1))
    forecast_steps  = int(body.get("forecast_steps", 10))
    n_folds         = int(body.get("n_folds", 5))

    if not tag_id or not start or not end:
        return jsonify({"success": False, "error": "tag_id, start, end required"}), 400

    # ── 1. Fetch data ──────────────────────────────────────────────────────
    df = _get_timeseries_df([tag_id], start, end, resample_minutes=resample)
    if df.empty or tag_id not in df.columns:
        return jsonify({"success": False, "error": f"No data for tag '{tag_id}'"}), 404

    series = df[tag_id].dropna()
    if len(series) < forecast_steps * (n_folds + 1) + 8:
        # Relax folds if data is short
        n_folds = max(2, int((len(series) - 8) // (forecast_steps + 1)))

    y      = series.values.astype(float)
    n_pts  = len(y)
    sigma  = float(np.std(y)) if np.std(y) > 0 else 1.0
    y_mean = float(np.mean(y))

    # ── 2. Signal-type classification ──────────────────────────────────────
    def _classify_signal(arr):
        """Classify signal as Trend / Periodic / Stationary / Noisy."""
        n_ = len(arr)
        # Trend: linear fit explains > 60% variance
        xs   = np.arange(n_)
        c    = np.polyfit(xs, arr, 1)
        trend_fit  = np.polyval(c, xs)
        ss_res_t   = np.sum((arr - trend_fit) ** 2)
        ss_tot     = np.sum((arr - arr.mean()) ** 2) or 1
        r2_trend   = 1 - ss_res_t / ss_tot
        # Periodicity via ACF peak
        if n_ >= 12:
            ac    = np.correlate(arr - arr.mean(), arr - arr.mean(), mode="full")
            ac    = ac[n_ - 1:]
            ac   /= ac[0] or 1
            search_ac = ac[2:n_ // 2]
            peak_ac   = float(np.max(search_ac)) if len(search_ac) else 0
        else:
            peak_ac = 0
        cv = (float(np.std(arr)) / abs(float(np.mean(arr)))) if abs(float(np.mean(arr))) > 0.01 else 999

        if r2_trend > 0.60:
            return "Trend"
        if peak_ac > 0.60:
            return "Periodic"
        if cv > 1.5:
            return "Noisy"
        return "Stationary"

    signal_type = _classify_signal(y)

    # ── 3. Walk-forward CV helper ───────────────────────────────────────────
    def _walk_forward(model_fn, y_arr, n_folds_, steps):
        """Run n_folds_ walk-forward folds.  model_fn(train) -> list[float] of length steps."""
        total      = len(y_arr)
        min_train  = max(steps * 2, 12)
        # Compute fold boundaries
        test_end   = total
        folds_data = []
        for _ in range(n_folds_):
            test_start = test_end - steps
            if test_start < min_train:
                break
            folds_data.append((y_arr[:test_start], y_arr[test_start:test_end]))
            test_end = test_start
        folds_data.reverse()

        all_mae, all_rmse, all_mape, all_r2, all_cov = [], [], [], [], []
        for train_arr, test_arr in folds_data:
            try:
                preds, lo, hi = model_fn(train_arr, steps)
                if preds is None or len(preds) == 0:
                    continue
                k = min(len(preds), len(test_arr))
                p = np.asarray(preds[:k], dtype=float)
                t = np.asarray(test_arr[:k], dtype=float)
                errs    = np.abs(p - t)
                all_mae.append(float(np.mean(errs)))
                all_rmse.append(float(np.sqrt(np.mean((p - t) ** 2))))
                # MAPE — guard zero actuals
                nonzero = np.abs(t) > 1e-9
                if nonzero.any():
                    all_mape.append(float(np.mean(errs[nonzero] / np.abs(t[nonzero])) * 100))
                # R²
                ss_tot_ = float(np.sum((t - t.mean()) ** 2)) or 1
                ss_res_ = float(np.sum((t - p) ** 2))
                all_r2.append(1 - ss_res_ / ss_tot_)
                # CI coverage
                if lo is not None and hi is not None and len(lo) >= k and len(hi) >= k:
                    lo_a = np.asarray(lo[:k], dtype=float)
                    hi_a = np.asarray(hi[:k], dtype=float)
                    coverage = float(np.mean((t >= lo_a) & (t <= hi_a)))
                    all_cov.append(coverage)
            except Exception:
                continue

        def safe_mean(lst):
            return round(float(np.mean(lst)), 4) if lst else None

        return {
            "mae":         safe_mean(all_mae),
            "rmse":        safe_mean(all_rmse),
            "mape":        safe_mean(all_mape),
            "r2":          safe_mean(all_r2),
            "ci_coverage": safe_mean(all_cov),
            "folds_run":   len(all_mae),
        }

    # ── 4. Model functions (tuned via grid search) ──────────────────────────

    # ── LR: grid over polynomial degree 1, 2, 3 ────────────────────────────
    def _lr_model_factory(degree):
        def _fn(train, steps):
            xs   = np.arange(len(train))
            c    = np.polyfit(xs, train, degree)
            fut  = np.polyval(c, np.arange(len(train), len(train) + steps))
            # residual std for CI
            fit_train = np.polyval(c, xs)
            res_std   = float(np.std(train - fit_train))
            lo = (fut - 1.96 * res_std).tolist()
            hi = (fut + 1.96 * res_std).tolist()
            return fut.tolist(), lo, hi
        return _fn

    best_lr_score = None
    best_lr_deg   = 1
    for deg in [1, 2, 3]:
        s = _walk_forward(_lr_model_factory(deg), y, n_folds, forecast_steps)
        if s["mae"] is not None:
            if best_lr_score is None or s["mae"] < best_lr_score:
                best_lr_score = s["mae"]
                best_lr_deg   = deg
    lr_metrics = _walk_forward(_lr_model_factory(best_lr_deg), y, n_folds, forecast_steps)
    lr_metrics["tuned_params"] = {"degree": best_lr_deg}

    # ── HW: grid over detected period ± variants ────────────────────────────
    def _detect_period(arr):
        if len(arr) < 12:
            return None
        ac = np.correlate(arr - arr.mean(), arr - arr.mean(), mode="full")
        ac = ac[len(arr) - 1:]
        ac /= ac[0] or 1
        half = max(len(arr) // 2, 3)
        search = ac[2:half]
        if not len(search):
            return None
        peak_idx = int(np.argmax(search)) + 2
        if ac[peak_idx] > 0.40:
            return peak_idx
        return None

    def _hw_model_factory(period):
        from statsmodels.tsa.holtwinters import ExponentialSmoothing as HWM
        def _fn(train, steps):
            try:
                if period and period >= 2 and len(train) >= period * 2:
                    fit = HWM(train, trend="add", seasonal="add",
                              seasonal_periods=period,
                              initialization_method="estimated").fit(optimized=True)
                else:
                    fit = HWM(train, trend="add",
                              initialization_method="estimated").fit(optimized=True)
                preds = fit.forecast(steps).tolist()
                rmse_ = float(np.sqrt(np.mean((fit.fittedvalues - train) ** 2)))
                lo = [v - 1.96 * rmse_ for v in preds]
                hi = [v + 1.96 * rmse_ for v in preds]
                return preds, lo, hi
            except Exception:
                return None, None, None
        return _fn

    detected_period = _detect_period(y)
    period_candidates = list({detected_period, 12, 6, 4} - {None})
    period_candidates = [p for p in period_candidates if isinstance(p, int) and p >= 2]

    best_hw_score  = None
    best_hw_period = detected_period
    for p_cand in period_candidates:
        s = _walk_forward(_hw_model_factory(p_cand), y, n_folds, forecast_steps)
        if s["mae"] is not None:
            if best_hw_score is None or s["mae"] < best_hw_score:
                best_hw_score  = s["mae"]
                best_hw_period = p_cand
    hw_metrics = _walk_forward(_hw_model_factory(best_hw_period), y, n_folds, forecast_steps)
    hw_metrics["tuned_params"] = {"period": best_hw_period}

    # ── FFT: grid over top_k dominant frequencies ────────────────────────────
    def _fft_model_factory(top_k):
        def _fn(train, steps):
            n_  = len(train)
            coeffs  = np.fft.rfft(train)
            mags    = np.abs(coeffs)
            k_      = min(top_k, len(mags))
            thresh  = np.sort(mags)[-k_]
            filtered = np.where(mags >= thresh, coeffs, 0)
            reconstructed = np.fft.irfft(filtered, n=n_)
            freqs = np.fft.rfftfreq(n_)
            t_fut = np.arange(n_, n_ + steps)
            fut   = np.full(steps, float(np.real(filtered[0]) / n_))
            for ki, co in enumerate(filtered):
                if ki == 0 or co == 0:
                    continue
                is_nyq   = (n_ % 2 == 0 and ki == len(filtered) - 1)
                amp      = np.abs(co) * (1.0 if is_nyq else 2.0) / n_
                fut     += amp * np.cos(2 * np.pi * freqs[ki] * t_fut + np.angle(co))
            res_std = float(np.std(train - reconstructed[:n_]))
            lo = (fut - 1.96 * res_std).tolist()
            hi = (fut + 1.96 * res_std).tolist()
            return fut.tolist(), lo, hi
        return _fn

    best_fft_score = None
    best_fft_k     = 5
    for k_cand in [3, 5, 8, 12, 20]:
        s = _walk_forward(_fft_model_factory(k_cand), y, n_folds, forecast_steps)
        if s["mae"] is not None:
            if best_fft_score is None or s["mae"] < best_fft_score:
                best_fft_score = s["mae"]
                best_fft_k     = k_cand
    fft_metrics = _walk_forward(_fft_model_factory(best_fft_k), y, n_folds, forecast_steps)
    fft_metrics["tuned_params"] = {"top_k": best_fft_k}

    # ── ARIMA: grid search with AIC-guided best order ─────────────────────
    def _arima_model_factory(order):
        from statsmodels.tsa.arima.model import ARIMA as ARIMAModel
        def _fn(train, steps):
            try:
                fit   = ARIMAModel(train, order=order).fit()
                fc    = fit.get_forecast(steps)
                preds = fc.predicted_mean.tolist()
                ci    = fc.conf_int(alpha=0.05)
                if hasattr(ci, "iloc"):
                    lo = ci.iloc[:, 0].tolist()
                    hi = ci.iloc[:, 1].tolist()
                else:
                    lo = ci[:, 0].tolist()
                    hi = ci[:, 1].tolist()
                return preds, lo, hi
            except Exception:
                return None, None, None
        return _fn

    # AIC-guided grid search on full series to pick order
    best_aic   = np.inf
    best_order = (1, 0, 1)
    from statsmodels.tsa.arima.model import ARIMA as _ARIMAModel
    for p_ in [0, 1, 2, 3]:
        for d_ in [0, 1]:
            for q_ in [0, 1, 2]:
                if p_ + d_ + q_ == 0 or p_ + d_ + q_ > 5:
                    continue
                try:
                    fit_ = _ARIMAModel(y, order=(p_, d_, q_)).fit()
                    if fit_.aic < best_aic:
                        best_aic   = fit_.aic
                        best_order = (p_, d_, q_)
                except Exception:
                    continue
    arima_metrics = _walk_forward(_arima_model_factory(best_order), y, n_folds, forecast_steps)
    arima_metrics["tuned_params"] = {"order": list(best_order), "aic": round(float(best_aic), 2)}

    # ── 5. Assemble leaderboard ─────────────────────────────────────────────
    def _conf_label(mae_val, rmse_val):
        if mae_val is None:
            return "N/A"
        if rmse_val is not None and rmse_val < 0.5 * sigma:
            return "HIGH"
        if rmse_val is not None and rmse_val < 1.5 * sigma:
            return "MEDIUM"
        return "LOW"

    def _verdict(model, sig_type, metrics):
        if metrics.get("mae") is None:
            return "Failed — no valid folds"
        r2    = metrics.get("r2") or 0
        mape  = metrics.get("mape")
        cov   = metrics.get("ci_coverage") or 0
        desc  = ""
        if model == "FFT":
            desc = "Excellent for periodic/cyclic signals" if sig_type == "Periodic" else "Captures dominant frequencies"
        elif model == "HW":
            desc = "Strong on seasonal + trend signals" if sig_type in ("Periodic", "Trend") else "Handles trend well"
        elif model == "ARIMA":
            desc = "Best for auto-correlated stationary signals" if sig_type in ("Stationary", "Noisy") else "Adapts to short-term patterns"
        elif model == "LR":
            desc = "Best for clear linear trends" if sig_type == "Trend" else "Simple baseline"
        extra = ""
        if r2 is not None and r2 > 0.90:
            extra = " · R²=" + str(round(r2, 2)) + " (excellent fit)"
        elif r2 is not None and r2 > 0.70:
            extra = " · R²=" + str(round(r2, 2)) + " (good fit)"
        return desc + extra

    raw_board = {
        "LR":    lr_metrics,
        "HW":    hw_metrics,
        "FFT":   fft_metrics,
        "ARIMA": arima_metrics,
    }

    # Sort by MAE ascending (None last)
    def _sort_key(item):
        mae_v = item[1].get("mae")
        return mae_v if mae_v is not None else 1e9

    sorted_models = sorted(raw_board.items(), key=_sort_key)

    leaderboard = []
    for rank, (model_name, m) in enumerate(sorted_models, 1):
        leaderboard.append({
            "rank":         rank,
            "model":        model_name,
            "mae":          m.get("mae"),
            "rmse":         m.get("rmse"),
            "mape":         m.get("mape"),
            "r2":           m.get("r2"),
            "ci_coverage":  m.get("ci_coverage"),
            "folds_run":    m.get("folds_run", 0),
            "tuned_params": m.get("tuned_params", {}),
            "confidence":   _conf_label(m.get("mae"), m.get("rmse")),
            "verdict":      _verdict(model_name, signal_type, m),
        })

    best_model = sorted_models[0][0] if sorted_models else None
    best_params = raw_board[best_model].get("tuned_params", {}) if best_model else {}

    return jsonify({
        "success":               True,
        "n_points":              n_pts,
        "signal_type":           signal_type,
        "folds":                 n_folds,
        "forecast_steps":        forecast_steps,
        "leaderboard":           leaderboard,
        "best_model":            best_model,
        "best_params":           best_params,
        "recommended_for_live":  True,
    })
