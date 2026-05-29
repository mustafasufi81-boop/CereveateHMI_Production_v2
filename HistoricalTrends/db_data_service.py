"""
db_data_service.py  —  Drop-in PostgreSQL replacement for ParquetDataService
=============================================================================
Implements the exact same public interface as ParquetDataService so that
HistoricalTrends/app.py needs only a 2-line change (import + instantiation).

Data source: historian_raw.historian_timeseries
  Columns used:
    time       → mapped to "Timestamp" in output DataFrames
    tag_id     → column headers after pivot
    value_num  → numeric value (NULL rows are excluded)

Connection management:
  All queries use the ThreadedConnectionPool from db_pool.borrow_connection().
  No connection is ever created directly in this file.

DataFrame contract (matches ParquetDataService exactly):
  read_parquet_data() returns a wide/pivot DataFrame:
    Timestamp | <tag_id_1> | <tag_id_2> | ...
  Rows are sorted ascending by Timestamp.
  Missing tag values at a given timestamp are NaN.
"""

import io
import logging
import time as _time
from datetime import datetime
from typing import List, Optional

import numpy as np
import pandas as pd
import psycopg2.extras

from db_pool import borrow_connection

logger = logging.getLogger(__name__)

_TABLE = "historian_raw.historian_timeseries"


class DBDataService:
    """
    PostgreSQL-backed data service with the same public interface as
    ParquetDataService.  Accepts (and ignores) the directory arguments
    so app.py instantiation is a one-liner change.
    """

    def __init__(self, data_directory=None, backup_directory=None):
        # Arguments kept for API compatibility — not used
        logger.info("[DBDataService] Initialised. Reads from PostgreSQL %s", _TABLE)

    # ──────────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _query_df(self, sql: str, params: list) -> pd.DataFrame:
        """Execute a SELECT query and return a raw DataFrame."""
        with borrow_connection() as conn:
            return pd.read_sql(sql, conn, params=params)

    def _fetch_rows(self, sql: str, params: list) -> list:
        """Execute a SELECT query and return raw rows as dicts."""
        with borrow_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, params)
                return [dict(r) for r in cur.fetchall()]

    @staticmethod
    def _parse_dt(dt_str: Optional[str]) -> Optional[datetime]:
        if not dt_str:
            return None
        # Parse to UTC-aware datetime so psycopg2 can bind to timestamptz columns
        ts = pd.to_datetime(str(dt_str), utc=True)
        return ts.to_pydatetime()  # returns datetime.datetime with tzinfo=UTC

    # ──────────────────────────────────────────────────────────────────────────
    # Public interface (same as ParquetDataService)
    # ──────────────────────────────────────────────────────────────────────────

    def get_available_tags(self) -> List[str]:
        """Return sorted list of all tag_ids that have data in the historian."""
        sql = f"""
            SELECT DISTINCT tag_id
            FROM {_TABLE}
            WHERE value_num IS NOT NULL
            ORDER BY tag_id
        """
        try:
            rows = self._fetch_rows(sql, [])
            tags = [r["tag_id"] for r in rows]
            logger.info("[DBDataService] get_available_tags → %d tags", len(tags))
            return tags
        except Exception as exc:
            logger.error("[DBDataService] get_available_tags failed: %s", exc)
            return []

    def get_available_files(self) -> List[dict]:
        """
        ParquetDataService returns a list of file metadata dicts.
        We return one virtual 'file' per calendar day that has data,
        preserving the same dict shape so UI code does not break.
        """
        sql = f"""
            SELECT
                DATE(time)          AS file_date,
                MIN(time)           AS first_ts,
                MAX(time)           AS last_ts,
                COUNT(*)            AS record_count,
                COUNT(DISTINCT tag_id) AS tag_count
            FROM {_TABLE}
            WHERE value_num IS NOT NULL
            GROUP BY DATE(time)
            ORDER BY file_date DESC
            LIMIT 365
        """
        try:
            rows = self._fetch_rows(sql, [])
            files = []
            for r in rows:
                date_str = str(r["file_date"])
                files.append({
                    "path": f"db://{date_str}",
                    "filename": f"historian_{date_str}.db",
                    "size": r["record_count"] * 40,          # approximate bytes
                    "size_mb": round(r["record_count"] * 40 / (1024 * 1024), 3),
                    "timestamp": str(r["first_ts"]),
                    "start": str(r["first_ts"]),
                    "end": str(r["last_ts"]),
                    "tags": [],                               # not pre-enumerated (costly)
                    "record_count": r["record_count"],
                    "tag_count": r["tag_count"],
                    "source": "PostgreSQL",
                })
            logger.info("[DBDataService] get_available_files → %d day-buckets", len(files))
            return files
        except Exception as exc:
            logger.error("[DBDataService] get_available_files failed: %s", exc)
            return []

    def read_parquet_data(
        self,
        start_date=None,
        end_date=None,
        tags: Optional[List[str]] = None,
        max_points: Optional[int] = None,
        force_raw: bool = False,
    ) -> pd.DataFrame:
        """
        Return a wide/pivot DataFrame for the given date range and tags.

        Delegates to QueryEngine which routes RAW / TIME-BUCKET / LTTB
        based on estimated row count — no full table scan in Python.

        Output format (identical to ParquetDataService):
            Timestamp | <tag_id_1> | <tag_id_2> | ...
        Rows sorted ascending by Timestamp, NaN where no data for a tag.
        """
        from query_engine import QueryEngine  # local import avoids circular ref

        start_dt = self._parse_dt(start_date)
        end_dt   = self._parse_dt(end_date)

        if start_dt is None or end_dt is None:
            logger.warning("[DBDataService] read_parquet_data: missing start/end date")
            return pd.DataFrame()

        # If no tags requested, fetch all (can be large — caller's responsibility)
        if not tags:
            tags = self.get_available_tags()

        if not tags:
            logger.warning("[DBDataService] read_parquet_data: no tags available")
            return pd.DataFrame()

        _max_points = max_points or 5000

        try:
            engine = QueryEngine()
            df, meta = engine.fetch(tags, start_dt, end_dt, max_points=_max_points, force_raw=force_raw)
            self._last_query_meta = meta  # expose for /api/data response
            logger.info(
                "[DBDataService] QueryEngine mode=%s rows=%d est=%s elapsed=%dms",
                meta.get("query_mode"), len(df),
                meta.get("est_rows_db"), meta.get("elapsed_ms", 0),
            )
            return df
        except RuntimeError as exc:
            if str(exc) == "busy":
                logger.warning("[DBDataService] QueryEngine semaphore timeout — server busy")
            else:
                logger.error("[DBDataService] QueryEngine failed: %s", exc)
            return pd.DataFrame()

    def get_data_summary(self, start_date=None, end_date=None) -> dict:
        """Return summary statistics for the given date range."""
        df = self.read_parquet_data(start_date, end_date)

        if df.empty:
            return {}

        summary = {
            "total_records": len(df),
            "date_range": {
                "start": df["Timestamp"].min().isoformat() if "Timestamp" in df.columns else None,
                "end":   df["Timestamp"].max().isoformat() if "Timestamp" in df.columns else None,
            },
            "tags": [],
        }

        for col in df.columns:
            if col == "Timestamp":
                continue
            try:
                col_data = pd.to_numeric(df[col], errors="coerce")
                summary["tags"].append({
                    "name":  col,
                    "min":   float(col_data.min())  if not col_data.isna().all() else None,
                    "max":   float(col_data.max())  if not col_data.isna().all() else None,
                    "avg":   float(col_data.mean()) if not col_data.isna().all() else None,
                    "count": int(col_data.count()),
                })
            except Exception:
                continue

        return summary

    def export_to_csv(self, start_date=None, end_date=None, tags=None) -> Optional[str]:
        """Export data to CSV string."""
        df = self.read_parquet_data(start_date, end_date, tags)
        if df.empty:
            return None
        buf = io.StringIO()
        df.to_csv(buf, index=False)
        return buf.getvalue()

    def export_to_excel(self, start_date=None, end_date=None, tags=None) -> Optional[bytes]:
        """Export data to Excel bytes."""
        df = self.read_parquet_data(start_date, end_date, tags)
        if df.empty:
            return None
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="Historical Data", index=False)
        buf.seek(0)
        return buf.getvalue()

    def get_files_for_date_range(self, start_date, end_date) -> List[str]:
        """
        ParquetDataService returns a list of file paths.
        We return virtual 'db://<date>' paths for each day in the range.
        """
        start_dt = self._parse_dt(start_date)
        end_dt   = self._parse_dt(end_date)

        if start_dt is None or end_dt is None:
            return []

        sql = f"""
            SELECT DISTINCT DATE(time) AS day
            FROM {_TABLE}
            WHERE time BETWEEN %s AND %s
              AND value_num IS NOT NULL
            ORDER BY day
        """
        try:
            rows = self._fetch_rows(sql, [str(start_dt), str(end_dt)])
            return [f"db://{r['day']}" for r in rows]
        except Exception as exc:
            logger.error("[DBDataService] get_files_for_date_range failed: %s", exc)
            return []
