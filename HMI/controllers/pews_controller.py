"""
PEWS Flask Blueprint
====================
Serves PEWS data to the React HMI.
Reads directly from PostgreSQL historian_analytics schema via the shared
Flask container DB connection — no coupling to the PEWS FastAPI service.

Routes
------
GET  /api/pews/warnings          Active (unacknowledged) warnings, newest first
GET  /api/pews/warnings/history  Last 200 warnings (ack + unack, last 24 h)
GET  /api/pews/status            Baseline table summary + warning level counts
POST /api/pews/warnings/<id>/ack Acknowledge a specific warning
"""
from flask import Blueprint, jsonify, request
from container import container
from utils.decorators import token_required
import logging
import psycopg2

try:
    from psycopg2.extras import RealDictCursor
except ImportError:
    RealDictCursor = None

logger = logging.getLogger(__name__)

pews_bp = Blueprint("pews", __name__, url_prefix="/api/pews")


def _get_conn():
    """Return a pooled connection context manager (shared pool)."""
    import db_pool
    return db_pool.get_conn()


# ── Active warnings ───────────────────────────────────────────────────────────

@pews_bp.route("/warnings", methods=["GET"])
@token_required
def get_active_warnings(current_user):
    """
    Return up to 100 unacknowledged warnings, newest first.
    Optional query params: ?level=3  (filter by warning_level)
                           ?tag_id=Random.Real4  (filter by tag)
    """
    level_filter = request.args.get("level", type=int)
    tag_id_filter = request.args.get("tag_id")
    try:
        conn = _get_conn()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            conditions = ["acknowledged = FALSE"]
            params = []
            if level_filter:
                conditions.append("warning_level = %s")
                params.append(level_filter)
            if tag_id_filter:
                conditions.append("tag_id = %s")
                params.append(tag_id_filter)
            where = " AND ".join(conditions)
            cur.execute(f"""
                SELECT id, time, tag_id, warning_level, warning_type,
                       current_value, avg_value, deviation_pct,
                       threshold_value, message,
                       acknowledged AS is_acknowledged
                FROM historian_analytics.early_warnings
                WHERE {where}
                ORDER BY time DESC
                LIMIT 100
            """, params if params else None)
            rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return jsonify({"success": True, "count": len(rows), "warnings": rows})
    except Exception as e:
        logger.error(f"[PEWS] get_active_warnings error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ── Warning history ───────────────────────────────────────────────────────────

@pews_bp.route("/warnings/history", methods=["GET"])
@token_required
def get_warning_history(current_user):
    """Last 200 warnings (any ack state) from the past 24 hours."""
    try:
        conn = _get_conn()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT id, time, tag_id, warning_level, warning_type,
                       current_value, avg_value, deviation_pct,
                       threshold_value, message,
                       acknowledged, ack_by, ack_time
                FROM historian_analytics.early_warnings
                WHERE time > NOW() - INTERVAL '24 hours'
                ORDER BY time DESC
                LIMIT 200
            """)
            rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return jsonify({"success": True, "count": len(rows), "warnings": rows})
    except Exception as e:
        logger.error(f"[PEWS] get_warning_history error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ── Status / summary ──────────────────────────────────────────────────────────

@pews_bp.route("/status", methods=["GET"])
@token_required
def get_status(current_user):
    """
    Returns:
      - baseline_count  : how many tags have a computed baseline
      - warning_summary : count per level for unacknowledged warnings
      - oldest_baseline : timestamp of oldest baseline (data freshness indicator)
    """
    try:
        conn = _get_conn()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT COUNT(*)           AS baseline_count,
                       MIN(last_computed) AS oldest_baseline,
                       MAX(last_computed) AS newest_baseline
                FROM historian_analytics.tag_baselines
            """)
            baseline_row = dict(cur.fetchone())

            cur.execute("""
                SELECT warning_level, COUNT(*) AS cnt
                FROM historian_analytics.early_warnings
                WHERE acknowledged = FALSE
                GROUP BY warning_level
                ORDER BY warning_level DESC
            """)
            level_rows = cur.fetchall()
            warning_summary = {r["warning_level"]: r["cnt"] for r in level_rows}
            total_active = sum(warning_summary.values())

        return jsonify({
            "success": True,
            "baseline_count":  baseline_row["baseline_count"],
            "oldest_baseline": str(baseline_row["oldest_baseline"]) if baseline_row["oldest_baseline"] else None,
            "newest_baseline": str(baseline_row["newest_baseline"]) if baseline_row["newest_baseline"] else None,
            "warning_summary": warning_summary,
            "total_active_warnings": total_active,
        })
    except Exception as e:
        logger.error(f"[PEWS] get_status error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ── Acknowledge ───────────────────────────────────────────────────────────────

@pews_bp.route("/warnings/<int:warning_id>/ack", methods=["POST"])
@token_required
def acknowledge_warning(current_user, warning_id: int):
    """Mark a warning as acknowledged by the current user."""
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE historian_analytics.early_warnings
                SET acknowledged = TRUE,
                    ack_by       = %s,
                    ack_time     = NOW()
                WHERE id = %s AND acknowledged = FALSE
            """, (current_user, warning_id))
            updated = cur.rowcount
        conn.commit()
        if updated == 0:
            return jsonify({"success": False, "error": "Warning not found or already acknowledged"}), 404
        logger.info(f"[PEWS] Warning {warning_id} acknowledged by {current_user}")
        return jsonify({"success": True, "warning_id": warning_id, "ack_by": current_user})
    except Exception as e:
        logger.error(f"[PEWS] acknowledge_warning error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
