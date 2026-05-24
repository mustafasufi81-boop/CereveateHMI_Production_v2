"""
Predictive Alarm Controller
============================
Flask blueprint exposing the predictive pre-alarm engine over REST.

Routes
------
GET  /api/predictive/status            Engine health + cycle stats
POST /api/predictive/engine/start      Start background engine
POST /api/predictive/engine/stop       Stop background engine
POST /api/predictive/engine/cycle      Force one immediate cycle (testing)

GET  /api/predictive/alarms            List active pre-alarms (paginated)
GET  /api/predictive/alarms/history    Historical alarms (date range)
POST /api/predictive/alarms/<id>/ack   Acknowledge a pre-alarm

GET  /api/predictive/tags              List all configured tags
POST /api/predictive/tags              Create / upsert a tag config
PUT  /api/predictive/tags/<tag_id>     Update a tag config
DELETE /api/predictive/tags/<tag_id>   Disable (soft-delete) a tag config

GET  /api/predictive/screener          Current screener state for all tags

Drift Detection (Stage 0):
GET  /api/predictive/drift/status               Drift service health
POST /api/predictive/drift/engine/start         Start drift detector
POST /api/predictive/drift/engine/stop          Stop drift detector
POST /api/predictive/drift/engine/cycle         Force immediate cycle
GET  /api/predictive/drift/alerts               All active drift alerts
GET  /api/predictive/drift/alerts/<tag_id>      Drift history for one tag
POST /api/predictive/drift/alerts/<id>/ack      Acknowledge drift alert
"""

import logging
from datetime import datetime, timezone
from flask import Blueprint, jsonify, request
from utils.decorators import token_required
from services.predictive_alarm_engine import engine_instance, _conn
from services.drift_detector_service import drift_detector_instance
import psycopg2.extras

logger = logging.getLogger(__name__)

predictive_bp = Blueprint("predictive", __name__, url_prefix="/api/predictive")


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _ok(data=None, **kwargs):
    payload = {"success": True}
    if data is not None:
        payload["data"] = data
    payload.update(kwargs)
    return jsonify(payload), 200


def _err(msg: str, code: int = 400):
    return jsonify({"success": False, "error": msg}), code


# ─── Engine control ───────────────────────────────────────────────────────────

@predictive_bp.route("/status", methods=["GET"])
@token_required
def engine_status(current_user):
    """Return engine running state, cycle count, suspicious tag list."""
    try:
        status = engine_instance().status()
        # Also count active alarms
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM historian_analytics.predictive_alarms "
                    "WHERE active = TRUE"
                )
                active_count = cur.fetchone()[0]
        status["active_alarm_count"] = active_count
        return _ok(status)
    except Exception as exc:
        logger.exception("[PredCtrl] status error: %s", exc)
        return _err(str(exc), 500)


@predictive_bp.route("/engine/start", methods=["POST"])
@token_required
def engine_start(current_user):
    try:
        engine_instance().start()
        return _ok(message="Engine started")
    except Exception as exc:
        return _err(str(exc), 500)


@predictive_bp.route("/engine/stop", methods=["POST"])
@token_required
def engine_stop(current_user):
    try:
        engine_instance().stop()
        return _ok(message="Engine stopped")
    except Exception as exc:
        return _err(str(exc), 500)


@predictive_bp.route("/engine/cycle", methods=["POST"])
@token_required
def engine_cycle(current_user):
    """Force one immediate full cycle — useful for testing without waiting 60s."""
    try:
        engine_instance().force_cycle()
        return _ok(message="Cycle complete", status=engine_instance().status())
    except Exception as exc:
        logger.exception("[PredCtrl] force cycle error: %s", exc)
        return _err(str(exc), 500)


# ─── Active alarms ────────────────────────────────────────────────────────────

@predictive_bp.route("/alarms", methods=["GET"])
@token_required
def list_active_alarms(current_user):
    """
    GET /api/predictive/alarms
    Query params: tag_id, active (true/false/all), page (default 1), page_size (default 50)
    """
    try:
        tag_id    = request.args.get("tag_id")
        active_q  = request.args.get("active", "true").lower()
        page      = max(1, int(request.args.get("page", 1)))
        page_size = min(200, max(1, int(request.args.get("page_size", 50))))
        offset    = (page - 1) * page_size

        filters = []
        params  = []

        if active_q == "false":
            filters.append("active = FALSE")
        elif active_q != "all":
            filters.append("active = TRUE")

        if tag_id:
            filters.append("tag_id = %s")
            params.append(tag_id)

        where = ("WHERE " + " AND ".join(filters)) if filters else ""

        sql = f"""
            SELECT id, tag_id, direction, confidence,
                   predicted_value, limit_value, eta_minutes,
                   predicted_breach_at, model_used,
                   raised_at, active, resolved_at, resolution_reason,
                   acknowledged, acknowledged_at, acknowledged_by, notes,
                   suppressed_until
            FROM   historian_analytics.predictive_alarms
            {where}
            ORDER  BY raised_at DESC
            LIMIT  %s OFFSET %s
        """
        count_sql = f"SELECT COUNT(*) FROM historian_analytics.predictive_alarms {where}"

        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, params + [page_size, offset])
                rows = [dict(r) for r in cur.fetchall()]
                cur.execute(count_sql, params)
                total = cur.fetchone()['count']

        # Serialize datetime fields
        for r in rows:
            for k, v in r.items():
                if isinstance(v, datetime):
                    r[k] = v.isoformat()

        return _ok(rows, total=total, page=page, page_size=page_size)
    except Exception as exc:
        logger.exception("[PredCtrl] list_active_alarms: %s", exc)
        return _err(str(exc), 500)


@predictive_bp.route("/alarms/history", methods=["GET"])
@token_required
def alarm_history(current_user):
    """
    GET /api/predictive/alarms/history
    Query params: tag_id, start, end (ISO), page, page_size
    """
    try:
        tag_id    = request.args.get("tag_id")
        start_str = request.args.get("start")
        end_str   = request.args.get("end")
        page      = max(1, int(request.args.get("page", 1)))
        page_size = min(500, max(1, int(request.args.get("page_size", 100))))
        offset    = (page - 1) * page_size

        filters = ["1=1"]
        params  = []
        if tag_id:
            filters.append("tag_id = %s"); params.append(tag_id)
        if start_str:
            filters.append("raised_at >= %s"); params.append(start_str)
        if end_str:
            filters.append("raised_at <= %s"); params.append(end_str)

        where = " AND ".join(filters)
        sql = f"""
            SELECT id, tag_id, direction, confidence,
                   predicted_value, limit_value, eta_minutes,
                   predicted_breach_at, model_used,
                   raised_at, active, resolved_at, resolution_reason,
                   acknowledged, acknowledged_at, acknowledged_by
            FROM   historian_analytics.predictive_alarms
            WHERE  {where}
            ORDER  BY raised_at DESC
            LIMIT  %s OFFSET %s
        """
        count_sql = f"SELECT COUNT(*) FROM historian_analytics.predictive_alarms WHERE {where}"

        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, params + [page_size, offset])
                rows = [dict(r) for r in cur.fetchall()]
                cur.execute(count_sql, params)
                total = cur.fetchone()['count']

        for r in rows:
            for k, v in r.items():
                if isinstance(v, datetime):
                    r[k] = v.isoformat()

        return _ok(rows, total=total, page=page, page_size=page_size)
    except Exception as exc:
        logger.exception("[PredCtrl] alarm_history: %s", exc)
        return _err(str(exc), 500)


@predictive_bp.route("/alarms/<int:alarm_id>/ack", methods=["POST"])
@token_required
def acknowledge_alarm(current_user, alarm_id):
    """
    POST /api/predictive/alarms/<id>/ack
    Body: { "notes": "optional text" }
    """
    try:
        body   = request.get_json(silent=True) or {}
        notes  = body.get("notes", "")
        user   = current_user.get("username", "unknown") if isinstance(current_user, dict) else str(current_user)

        sql = """
            UPDATE historian_analytics.predictive_alarms
            SET    acknowledged    = TRUE,
                   acknowledged_at = NOW(),
                   acknowledged_by = %s,
                   notes           = %s,
                   active          = FALSE,
                   resolved_at     = NOW(),
                   resolution_reason = 'operator_ack'
            WHERE  id = %s
              AND  acknowledged = FALSE
            RETURNING id, tag_id, direction
        """
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (user, notes, alarm_id))
                row = cur.fetchone()
            conn.commit()

        if not row:
            return _err("Alarm not found or already acknowledged", 404)

        logger.info("[PredCtrl] Alarm %d acknowledged by %s", alarm_id, user)
        return _ok({"id": row[0], "tag_id": row[1], "direction": row[2]},
                   message="Acknowledged")
    except Exception as exc:
        logger.exception("[PredCtrl] ack alarm %d: %s", alarm_id, exc)
        return _err(str(exc), 500)


# ─── Tag configuration CRUD ───────────────────────────────────────────────────

@predictive_bp.route("/tags", methods=["GET"])
@token_required
def list_tags(current_user):
    """GET /api/predictive/tags — list all (including disabled)."""
    try:
        sql = """
            SELECT tag_id, tag_description, unit,
                   hi_hi_limit, hi_limit, lo_limit, lo_lo_limit, deadband,
                   preferred_model, forecast_horizon_minutes,
                   suppression_window_minutes, priority, enabled,
                   created_at, updated_at, created_by
            FROM   historian_analytics.tag_alarm_config
            ORDER  BY priority ASC, tag_id ASC
        """
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql)
                rows = [dict(r) for r in cur.fetchall()]

        for r in rows:
            for k, v in r.items():
                if isinstance(v, datetime):
                    r[k] = v.isoformat()

        return _ok(rows, count=len(rows))
    except Exception as exc:
        logger.exception("[PredCtrl] list_tags: %s", exc)
        return _err(str(exc), 500)


@predictive_bp.route("/tags", methods=["POST"])
@token_required
def create_tag(current_user):
    """
    POST /api/predictive/tags
    Body: { tag_id*, tag_description, unit, hi_limit, lo_limit, hi_hi_limit,
            lo_lo_limit, deadband, preferred_model, forecast_horizon_minutes,
            suppression_window_minutes, priority, enabled }
    * required
    """
    try:
        body   = request.get_json(silent=True) or {}
        tag_id = (body.get("tag_id") or "").strip()
        if not tag_id:
            return _err("tag_id is required")

        user = current_user.get("username", "system") if isinstance(current_user, dict) else str(current_user)

        sql = """
            INSERT INTO historian_analytics.tag_alarm_config
                (tag_id, tag_description, unit,
                 hi_hi_limit, hi_limit, lo_limit, lo_lo_limit, deadband,
                 preferred_model, forecast_horizon_minutes,
                 suppression_window_minutes, priority, enabled, created_by)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (tag_id) DO UPDATE SET
                tag_description           = EXCLUDED.tag_description,
                unit                      = EXCLUDED.unit,
                hi_hi_limit               = EXCLUDED.hi_hi_limit,
                hi_limit                  = EXCLUDED.hi_limit,
                lo_limit                  = EXCLUDED.lo_limit,
                lo_lo_limit               = EXCLUDED.lo_lo_limit,
                deadband                  = EXCLUDED.deadband,
                preferred_model           = EXCLUDED.preferred_model,
                forecast_horizon_minutes  = EXCLUDED.forecast_horizon_minutes,
                suppression_window_minutes= EXCLUDED.suppression_window_minutes,
                priority                  = EXCLUDED.priority,
                enabled                   = EXCLUDED.enabled
            RETURNING tag_id, enabled
        """
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (
                    tag_id,
                    body.get("tag_description"),
                    body.get("unit"),
                    body.get("hi_hi_limit"),
                    body.get("hi_limit"),
                    body.get("lo_limit"),
                    body.get("lo_lo_limit"),
                    float(body.get("deadband", 0.0)),
                    body.get("preferred_model", "auto"),
                    int(body.get("forecast_horizon_minutes", 30)),
                    int(body.get("suppression_window_minutes", 60)),
                    int(body.get("priority", 3)),
                    bool(body.get("enabled", True)),
                    user,
                ))
                row = cur.fetchone()
            conn.commit()

        return _ok({"tag_id": row[0], "enabled": row[1]}, message="Saved"), 200
    except Exception as exc:
        logger.exception("[PredCtrl] create_tag: %s", exc)
        return _err(str(exc), 500)


@predictive_bp.route("/tags/<path:tag_id>", methods=["PUT"])
@token_required
def update_tag(current_user, tag_id):
    """
    PUT /api/predictive/tags/<tag_id>
    Partial update — only provided fields are changed.
    """
    try:
        body = request.get_json(silent=True) or {}
        allowed = {
            "tag_description", "unit", "hi_hi_limit", "hi_limit",
            "lo_limit", "lo_lo_limit", "deadband", "preferred_model",
            "forecast_horizon_minutes", "suppression_window_minutes",
            "priority", "enabled",
        }
        updates = {k: v for k, v in body.items() if k in allowed}
        if not updates:
            return _err("No valid fields provided")

        set_clause = ", ".join(f"{k} = %s" for k in updates)
        values     = list(updates.values()) + [tag_id]

        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE historian_analytics.tag_alarm_config "
                    f"SET {set_clause} WHERE tag_id = %s RETURNING tag_id",
                    values,
                )
                row = cur.fetchone()
            conn.commit()

        if not row:
            return _err("Tag not found", 404)
        return _ok({"tag_id": row[0]}, message="Updated")
    except Exception as exc:
        logger.exception("[PredCtrl] update_tag %s: %s", tag_id, exc)
        return _err(str(exc), 500)


@predictive_bp.route("/tags/<path:tag_id>", methods=["DELETE"])
@token_required
def delete_tag(current_user, tag_id):
    """Soft-delete: set enabled=FALSE."""
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE historian_analytics.tag_alarm_config "
                    "SET enabled = FALSE WHERE tag_id = %s RETURNING tag_id",
                    (tag_id,),
                )
                row = cur.fetchone()
            conn.commit()

        if not row:
            return _err("Tag not found", 404)
        return _ok({"tag_id": row[0]}, message="Disabled")
    except Exception as exc:
        logger.exception("[PredCtrl] delete_tag %s: %s", tag_id, exc)
        return _err(str(exc), 500)


# ─── Screener state ───────────────────────────────────────────────────────────

@predictive_bp.route("/screener", methods=["GET"])
@token_required
def screener_state(current_user):
    """
    GET /api/predictive/screener
    Returns last screener result for every tag.
    """
    try:
        sql = """
            SELECT tag_id, is_suspicious, reason, slope,
                   quality_score, n_points, last_screened
            FROM   historian_analytics.screener_state
            ORDER  BY is_suspicious DESC, tag_id ASC
        """
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql)
                rows = [dict(r) for r in cur.fetchall()]

        for r in rows:
            for k, v in r.items():
                if isinstance(v, datetime):
                    r[k] = v.isoformat()

        return _ok(rows, count=len(rows))
    except Exception as exc:
        logger.exception("[PredCtrl] screener_state: %s", exc)
        return _err(str(exc), 500)


# ═══════════════════════════════════════════════════════════════════════════════
# DRIFT DETECTION  (Stage 0 — long-term baseline monitor)
# ═══════════════════════════════════════════════════════════════════════════════

@predictive_bp.route('/drift/status', methods=['GET'])
@token_required
def drift_status():
    """Drift detector service health and config."""
    return _ok(drift_detector_instance().status())


@predictive_bp.route('/drift/engine/start', methods=['POST'])
@token_required
def drift_engine_start():
    drift_detector_instance().start()
    return _ok({'message': 'Drift detector started'})


@predictive_bp.route('/drift/engine/stop', methods=['POST'])
@token_required
def drift_engine_stop():
    drift_detector_instance().stop()
    return _ok({'message': 'Drift detector stopped'})


@predictive_bp.route('/drift/engine/cycle', methods=['POST'])
@token_required
def drift_engine_cycle():
    """Force one immediate drift evaluation cycle (useful for testing)."""
    drift_detector_instance().force_cycle()
    return _ok({'message': 'Drift cycle triggered'})


@predictive_bp.route('/drift/alerts', methods=['GET'])
@token_required
def drift_alerts():
    """
    Return all active drift alerts.
    Query params:
      tag_id  — filter by tag
      method  — filter by method (cusum/ewma/zscore)
      severity — filter by severity (info/warning/critical)
      include_resolved — include resolved alerts (default false)
    """
    try:
        tag_id   = request.args.get('tag_id')
        method   = request.args.get('method')
        severity = request.args.get('severity')
        include_resolved = request.args.get('include_resolved', 'false').lower() == 'true'

        conditions = []
        params     = []
        if not include_resolved:
            conditions.append('is_active = TRUE')
        if tag_id:
            conditions.append('tag_id = %s');    params.append(tag_id)
        if method:
            conditions.append('method = %s');    params.append(method)
        if severity:
            conditions.append('severity = %s');  params.append(severity)

        where = ('WHERE ' + ' AND '.join(conditions)) if conditions else ''
        sql = f"""
            SELECT id, tag_id, method, severity, direction,
                   baseline_mean, baseline_std, current_mean,
                   drift_magnitude, drift_pct,
                   cusum_score, ewma_value,
                   consecutive_hours, is_active, acknowledged,
                   acknowledged_by, acknowledged_at,
                   started_at, last_updated, resolved_at,
                   eval_window_hours, baseline_days
            FROM   historian_analytics.drift_alerts
            {where}
            ORDER  BY
                CASE severity WHEN 'critical' THEN 1
                              WHEN 'warning'  THEN 2
                              ELSE 3 END,
                last_updated DESC
            LIMIT 200
        """
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, params)
                rows = [dict(r) for r in cur.fetchall()]

        for r in rows:
            for k, v in r.items():
                if isinstance(v, datetime):
                    r[k] = v.isoformat()

        return _ok(rows, count=len(rows))
    except Exception as exc:
        logger.exception("[PredCtrl] drift_alerts: %s", exc)
        return _err(str(exc), 500)


@predictive_bp.route('/drift/alerts/<tag_id>', methods=['GET'])
@token_required
def drift_alert_history(tag_id: str):
    """Drift history for a specific tag — last 90 days, all methods."""
    try:
        sql = """
            SELECT id, method, severity, direction,
                   baseline_mean, baseline_std, current_mean,
                   drift_magnitude, drift_pct, consecutive_hours,
                   is_active, acknowledged, started_at, last_updated, resolved_at
            FROM   historian_analytics.drift_alerts
            WHERE  tag_id = %s
              AND  started_at > NOW() - INTERVAL '90 days'
            ORDER  BY started_at DESC
            LIMIT  500
        """
        with _conn() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, (tag_id,))
                rows = [dict(r) for r in cur.fetchall()]

        for r in rows:
            for k, v in r.items():
                if isinstance(v, datetime):
                    r[k] = v.isoformat()

        return _ok(rows, count=len(rows))
    except Exception as exc:
        logger.exception("[PredCtrl] drift_alert_history: %s", exc)
        return _err(str(exc), 500)


@predictive_bp.route('/drift/alerts/<int:alert_id>/ack', methods=['POST'])
@token_required
def drift_alert_ack(alert_id: int):
    """Acknowledge a drift alert."""
    try:
        from flask import g
        user = getattr(g, 'current_user', {}).get('username', 'operator')
        sql = """
            UPDATE historian_analytics.drift_alerts
            SET    acknowledged    = TRUE,
                   acknowledged_at = NOW(),
                   acknowledged_by = %s,
                   last_updated    = NOW()
            WHERE  id = %s
        """
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (user, alert_id))
                updated = cur.rowcount
            conn.commit()

        if updated == 0:
            return _err('Alert not found', 404)
        return _ok({'message': f'Acknowledged by {user}', 'alert_id': alert_id})
    except Exception as exc:
        logger.exception("[PredCtrl] drift_ack: %s", exc)
        return _err(str(exc), 500)
