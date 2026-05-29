"""
query_engine.py
===============
DB-side smart query routing for HistoricalTrends.

Routing table (per query, all tags combined):
  estimated rows ≤ RAW_THRESHOLD      → RAW      (fetch as-is, no aggregation)
  estimated rows ≤ BUCKET_THRESHOLD   → TIME-BUCKET (TimescaleDB time_bucket)
  estimated rows  > BUCKET_THRESHOLD  → LTTB      (Largest-Triangle-Three-Buckets
                                                    done in Python after bucket avg)

All queries go through the EXISTING pool via borrow_connection() — zero new
connections created here.

Concurrency guard: threading.Semaphore(3) — at most 3 heavy fetches run at
the same time.  If the semaphore cannot be acquired within 10 s the caller
gets an immediate 503-style RuntimeError.
"""

from __future__ import annotations

import logging
import math
import threading
import time as _time
from datetime import datetime, timezone
from typing import List, Optional, Tuple, Dict, Any

import numpy as np
import pandas as pd

# ── Reuse the EXISTING connection pool ──────────────────────────────────────
from db_pool import borrow_connection  # noqa: E402  (project-local module)

logger = logging.getLogger(__name__)

# ── Thresholds ────────────────────────────────────────────────────────────────
RAW_THRESHOLD    = 50_000       # rows → return verbatim
BUCKET_THRESHOLD = 2_000_000    # rows → time-bucket avg; above this → LTTB path
MAX_POINTS       = 5_000        # target chart points after sampling
LTTB_OVERSAMPLE  = 10           # time-bucket target = MAX_POINTS * LTTB_OVERSAMPLE
                                 # before LTTB is applied

# ── Concurrency guard ─────────────────────────────────────────────────────────
_QUERY_SEMAPHORE = threading.Semaphore(3)
_SEMAPHORE_TIMEOUT_S = 10

_TABLE = "historian_raw.historian_timeseries"


# ─────────────────────────────────────────────────────────────────────────────
# LTTB implementation (pure numpy, no extra deps)
# ─────────────────────────────────────────────────────────────────────────────

def _lttb_series(timestamps: np.ndarray, values: np.ndarray, n_out: int) -> Tuple[np.ndarray, np.ndarray]:
    """Largest-Triangle-Three-Buckets downsampling for a single series.

    timestamps: numeric (Unix ms)
    values:     float, may contain NaN
    n_out:      desired output length (>= 3)
    Returns (ts_out, val_out) numpy arrays of length ≤ n_out.
    """
    n = len(timestamps)
    if n <= n_out:
        return timestamps, values

    # Remove NaN pairs for LTTB calculation
    mask = ~np.isnan(values)
    ts_clean = timestamps[mask]
    v_clean  = values[mask]
    if len(ts_clean) <= n_out:
        return ts_clean, v_clean

    # LTTB
    bucket_size = (len(ts_clean) - 2) / (n_out - 2)
    out_idx = [0]
    a = 0
    for i in range(n_out - 2):
        avg_start = int((i + 1) * bucket_size) + 1
        avg_end   = int((i + 2) * bucket_size) + 1
        avg_ts = ts_clean[avg_start:avg_end].mean()
        avg_v  = v_clean[avg_start:avg_end].mean()

        range_start = int(i * bucket_size) + 1
        range_end   = int((i + 1) * bucket_size) + 1
        ts_r = ts_clean[range_start:range_end]
        v_r  = v_clean[range_start:range_end]

        areas = np.abs(
            (ts_clean[a] - avg_ts) * (v_r - v_clean[a])
            - (ts_r - ts_clean[a]) * (avg_v - v_clean[a])
        ) * 0.5
        best = np.argmax(areas)
        out_idx.append(range_start + best)
        a = range_start + best

    out_idx.append(len(ts_clean) - 1)
    return ts_clean[out_idx], v_clean[out_idx]


# ─────────────────────────────────────────────────────────────────────────────
# QueryEngine
# ─────────────────────────────────────────────────────────────────────────────

class QueryEngine:
    """
    Usage:
        engine = QueryEngine()
        df, meta = engine.fetch(tags, start_dt, end_dt, max_points=5000)

    df columns:  Timestamp | <tag_id_1> | <tag_id_2> | …
    meta keys:   query_mode, bucket_seconds, est_rows_db, actual_rows_fetched,
                 sampled, elapsed_ms
    """

    def fetch(
        self,
        tags: List[str],
        start_dt: datetime,
        end_dt: datetime,
        max_points: int = MAX_POINTS,
        force_raw: bool = False,
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Main entry point.  Returns (wide_df, meta_dict).
        force_raw=True bypasses row-count routing and always returns every row.
        Raises RuntimeError("busy") if semaphore times out.
        Raises RuntimeError on DB failure.
        """
        if not tags:
            return pd.DataFrame(), {"query_mode": "none", "sampled": False, "elapsed_ms": 0}

        acquired = _QUERY_SEMAPHORE.acquire(timeout=_SEMAPHORE_TIMEOUT_S)
        if not acquired:
            raise RuntimeError("busy")

        t0 = _time.time()
        meta: Dict[str, Any] = {
            "query_mode": "unknown",
            "bucket_seconds": None,
            "est_rows_db": None,
            "actual_rows_fetched": 0,
            "sampled": False,
            "elapsed_ms": 0,
        }
        try:
            est_rows = self._estimate_rows(tags, start_dt, end_dt)
            meta["est_rows_db"] = est_rows
            logger.info(
                "[QueryEngine] %d tags, %s→%s, est_rows=%d force_raw=%s",
                len(tags), start_dt, end_dt, est_rows, force_raw,
            )

            if force_raw:
                df = self._fetch_raw(tags, start_dt, end_dt)
                meta["query_mode"] = "RAW"
                meta["sampled"] = False
            elif est_rows <= RAW_THRESHOLD:
                df = self._fetch_raw(tags, start_dt, end_dt)
                meta["query_mode"] = "RAW"
                meta["sampled"] = False
            elif est_rows <= BUCKET_THRESHOLD:
                bucket_s = self._calc_bucket_seconds(est_rows, max_points)
                df = self._fetch_bucket(tags, start_dt, end_dt, bucket_s)
                meta["query_mode"] = "TIME-BUCKET"
                meta["bucket_seconds"] = bucket_s
                meta["sampled"] = True
            else:
                # Pre-aggregate with large bucket, then LTTB in Python
                bucket_s = self._calc_bucket_seconds(est_rows, max_points * LTTB_OVERSAMPLE)
                df = self._fetch_bucket(tags, start_dt, end_dt, bucket_s)
                meta["query_mode"] = "LTTB"
                meta["bucket_seconds"] = bucket_s
                meta["sampled"] = True
                df = self._apply_lttb(df, tags, max_points)

            meta["actual_rows_fetched"] = len(df)
            meta["elapsed_ms"] = round((_time.time() - t0) * 1000)
            logger.info(
                "[QueryEngine] ✅ mode=%s rows=%d elapsed=%dms",
                meta["query_mode"], len(df), meta["elapsed_ms"],
            )
            return df, meta

        except RuntimeError:
            raise
        except Exception as exc:
            logger.error("[QueryEngine] fetch failed: %s", exc, exc_info=True)
            raise RuntimeError(str(exc)) from exc
        finally:
            _QUERY_SEMAPHORE.release()

    # ──────────────────────────────────────────────────────────────────────────
    # Private helpers
    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _estimate_rows(tags: List[str], start_dt: datetime, end_dt: datetime) -> int:
        """Fast COUNT(*) using index-only scan on the hypertable."""
        placeholders = ",".join(["%s"] * len(tags))
        sql = f"""
            SELECT COUNT(*)
            FROM {_TABLE}
            WHERE tag_id IN ({placeholders})
              AND time BETWEEN %s AND %s
        """
        params = tuple(tags) + (start_dt, end_dt)
        try:
            with borrow_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, params)
                    row = cur.fetchone()
                    return int(row[0]) if row else 0
        except Exception as exc:
            logger.warning("[QueryEngine] _estimate_rows failed (%s) — defaulting to 0", exc)
            return 0

    @staticmethod
    def _calc_bucket_seconds(est_rows: int, target_points: int) -> int:
        """Calculate bucket width so output ≈ target_points rows."""
        if target_points <= 0:
            target_points = MAX_POINTS
        # rough: bucket_factor = est_rows / target_points
        # but we want at least 1 s
        factor = max(1, math.ceil(est_rows / max(target_points, 1)))
        # round up to a nice interval
        for nice in [1, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600,
                     7200, 14400, 21600, 43200, 86400]:
            if nice >= factor:
                return nice
        return factor  # fallback for very coarse data

    @staticmethod
    def _fetch_raw(tags: List[str], start_dt: datetime, end_dt: datetime) -> pd.DataFrame:
        """Fetch all rows verbatim and pivot to wide format."""
        placeholders = ",".join(["%s"] * len(tags))
        sql = f"""
            SELECT time AS "Timestamp", tag_id, value_num AS "Value"
            FROM {_TABLE}
            WHERE tag_id IN ({placeholders})
              AND time BETWEEN %s AND %s
              AND value_num IS NOT NULL
            ORDER BY time ASC
        """
        params = tuple(tags) + (start_dt, end_dt)
        with borrow_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
                cols = [d[0] for d in cur.description]
        df_raw = pd.DataFrame(rows, columns=cols)
        return QueryEngine._pivot(df_raw)

    @staticmethod
    def _fetch_bucket(
        tags: List[str],
        start_dt: datetime,
        end_dt: datetime,
        bucket_s: int,
    ) -> pd.DataFrame:
        """Use TimescaleDB time_bucket() to aggregate on the DB side."""
        placeholders = ",".join(["%s"] * len(tags))
        sql = f"""
            SELECT
                time_bucket('{bucket_s} seconds', time) AS "Timestamp",
                tag_id,
                AVG(value_num)                          AS "Value"
            FROM {_TABLE}
            WHERE tag_id IN ({placeholders})
              AND time BETWEEN %s AND %s
              AND value_num IS NOT NULL
            GROUP BY 1, tag_id
            ORDER BY 1 ASC
        """
        params = tuple(tags) + (start_dt, end_dt)
        with borrow_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
                cols = [d[0] for d in cur.description]
        df_raw = pd.DataFrame(rows, columns=cols)
        return QueryEngine._pivot(df_raw)

    @staticmethod
    def _pivot(df_raw: pd.DataFrame) -> pd.DataFrame:
        """Long → wide pivot, returns DataFrame with Timestamp column."""
        if df_raw.empty:
            return pd.DataFrame()
        df_raw["Timestamp"] = pd.to_datetime(df_raw["Timestamp"])
        result = (
            df_raw
            .pivot_table(index="Timestamp", columns="tag_id", values="Value", aggfunc="first")
            .reset_index()
        )
        result.columns.name = None
        return result.sort_values("Timestamp").reset_index(drop=True)

    @staticmethod
    def _apply_lttb(df: pd.DataFrame, tags: List[str], max_points: int) -> pd.DataFrame:
        """
        Apply LTTB independently per tag column, then merge back to a single
        wide DataFrame.  Only tags that exceed max_points rows are down-sampled.
        """
        if df.empty or len(df) <= max_points:
            return df

        ts_numeric = df["Timestamp"].astype(np.int64).values
        out_frames = []

        for tag in tags:
            if tag not in df.columns:
                continue
            vals = df[tag].to_numpy(dtype=float, na_value=np.nan)
            ts_out, v_out = _lttb_series(ts_numeric, vals, max_points)
            tag_df = pd.DataFrame({
                "Timestamp": pd.to_datetime(ts_out, unit="ns", utc=True).tz_localize(None),
                tag: v_out,
            })
            out_frames.append(tag_df.set_index("Timestamp"))

        if not out_frames:
            return df

        merged = out_frames[0]
        for frame in out_frames[1:]:
            merged = merged.join(frame, how="outer")

        return merged.reset_index().sort_values("Timestamp").reset_index(drop=True)
