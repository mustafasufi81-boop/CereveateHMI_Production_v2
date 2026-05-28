"""
Alarm Controller - Fetches active alarms from historian_raw.historian_events table
"""
from flask import Blueprint, jsonify, request
from container import container
from utils.decorators import token_required
import logging
import sys
import os
import db_pool

logger = logging.getLogger(__name__)

# C# OpcDaWebBrowser base URL — AlarmStateManager is sole authority over alarm state
# All ACK/CLEAR mutations are proxied here; Flask only owns audit trail writes.
import requests as _requests
_OPC_BASE = 'http://localhost:5001'
_OPC_CONNECT_TIMEOUT = 3   # seconds to establish TCP connection to C#
_OPC_READ_TIMEOUT    = 5   # seconds to wait for C# response body
_OPC_TIMEOUT = (_OPC_CONNECT_TIMEOUT, _OPC_READ_TIMEOUT)  # (connect, read) tuple

# Add mqtt_subscriber_service to path to import AlarmAuditDAO
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'mqtt_subscriber_service'))

# Try to import RealDictCursor, fallback if not available
try:
    from psycopg2.extras import RealDictCursor
    HAS_REAL_DICT_CURSOR = True
except ImportError:
    HAS_REAL_DICT_CURSOR = False
    RealDictCursor = None

# Try to import AlarmAuditDAO for audit trail logging
try:
    from src.database.alarm_audit_dao import AlarmAuditDAO
    HAS_ALARM_AUDIT = True
    logger.info("✅ AlarmAuditDAO imported successfully")
except ImportError as e:
    logger.warning(f"Could not import AlarmAuditDAO: {e}")
    HAS_ALARM_AUDIT = False
    AlarmAuditDAO = None

alarm_bp = Blueprint('alarm', __name__, url_prefix='/api/alarms')


def _priority_label(priority):
    if priority == 5:
        return "CRITICAL"
    if priority == 4:
        return "URGENT"
    if priority == 3:
        return "HIGH"
    if priority == 2:
        return "WARNING"
    return "LOW"


def _audit_action_rank(action_type):
    order = {
        "RAISED": 1,
        "ACKNOWLEDGED": 2,
        "CLEARED": 3,
        "SUPPRESSED": 4,
    }
    return order.get((action_type or "").upper(), 99)


def _map_lifecycle_state(state):
    """
    Map internal state to ISA-18.2 lifecycle state labels
    ACTIVE_UNACK → ACTIVE_UNACKED
    ACTIVE_ACK → ACTIVE_ACKED
    RTN_UNACK → RTN_UNACKED  
    CLEARED → CLEARED
    """
    if not state:
        return None
    
    state_upper = state.upper()
    
    # ISA-18.2 4-state model mappings
    mapping = {
        'ACTIVE_UNACK': 'ACTIVE_UNACKED',
        'ACTIVE_UNACKED': 'ACTIVE_UNACKED',
        'ACTIVE_ACK': 'ACTIVE_ACKED',
        'ACTIVE_ACKED': 'ACTIVE_ACKED',
        'RTN_UNACK': 'RTN_UNACKED',
        'RTN_UNACKED': 'RTN_UNACKED',
        'CLEARED': 'CLEARED',
        'ACTIVE': 'ACTIVE_UNACKED',  # Default ACTIVE to UNACKED
        'ACKNOWLEDGED': 'ACTIVE_ACKED',  # Legacy mapping
        'RETURNED': 'RTN_UNACKED',  # Legacy mapping
        'SUPPRESSED': 'SUPPRESSED'
    }
    
    return mapping.get(state_upper, state)

@alarm_bp.route('/active', methods=['GET'])
def get_active_alarms():
    """
    Get active alarms from historian_raw.historian_events table
    Returns alarms with ACTIVE or ACKNOWLEDGED state (per DB design)
    
    CRITICAL: Database is the SOURCE OF TRUTH for alarms, NOT MQTT!
    - MQTT provides real-time updates when NEW alarms occur
    - Database stores ALL alarms with persistent state
    - This endpoint returns ALL active alarms from DB regardless of MQTT status
    
    Per ISA-18.2: 
    - ALL active alarms must be displayed continuously until acknowledged/cleared
    - Alarms persist through MQTT disconnections, system restarts, etc.
    - Operator must see alarms even if MQTT publisher stopped hours ago
    
    Limit parameter is for pagination/performance, NOT for hiding alarms.
    Default: 50 alarms, Max: 200 (to handle upset conditions per EEMUA 191)
    """
    try:
        limit = request.args.get('limit', 50, type=int)
        # Ensure limit is safe integer - increased max to 200 for alarm floods
        limit = max(1, min(limit, 200))  # Between 1 and 200
        
        # ISA-18.2 Phase 1 state names:
        #   ACTIVE_UNACK  — alarm active, operator has NOT acknowledged
        #   ACTIVE_ACK    — alarm active, operator acknowledged
        #   RTN_UNACK     — value returned to normal, operator has NOT acknowledged the return
        # alarm_active is the runtime operational table (C# AlarmStateManager owns it).
        # historian_events is the immutable append-only transition journal (never read here).
        query = f"""
            SELECT
                aa.current_event_id               AS id,
                aa.alarm_key,
                aa.tag_id,
                COALESCE(tm.tag_name, aa.tag_id)  AS tag_name,
                aa.level                          AS alarm_level,
                aa.alarm_state,
                aa.priority                       AS alarm_priority,
                aa.raised_value                   AS alarm_actual_value,
                aa.setpoint_value                 AS alarm_setpoint,
                aa.raised_at,
                aa.ack_at                         AS acknowledged_at,
                aa.ack_by                         AS acknowledged_by,
                aa.rtn_at,
                aa.updated_at,
                EXTRACT(EPOCH FROM (COALESCE(aa.rtn_at, NOW()) - aa.raised_at))/60 AS duration_minutes,
                CASE
                    WHEN aa.alarm_state = 'ACTIVE_UNACK' THEN 'ACTIVE_UNACKNOWLEDGED'
                    WHEN aa.alarm_state = 'ACTIVE_ACK'   THEN 'ACTIVE_ACKNOWLEDGED'
                    WHEN aa.alarm_state = 'RTN_UNACK'    THEN 'RETURNED_UNACKNOWLEDGED'
                    ELSE aa.alarm_state
                END AS status,
                COALESCE(he.message, '')          AS message,
                COALESCE(he.event_type, 'ALARM')  AS event_type,
                aa.instance_seq,
                aa.transition_seq,
                -- Count how many times this limit has been hit since the card was raised
                (
                    SELECT COUNT(*)
                    FROM historian_raw.historian_events he2
                    WHERE he2.tag_id = aa.tag_id
                      AND UPPER(he2.alarm_level) = UPPER(aa.level)
                      AND he2."time" >= aa.raised_at
                      AND he2.event_type NOT IN ('RTN_UNACK', 'CLEARED')
                ) AS occurrence_count,
                -- Last 3 times this alarm was raised (pipe-separated ISO timestamps, newest first)
                (
                    SELECT STRING_AGG(sub.t::text, '|' ORDER BY sub.t DESC)
                    FROM (
                        SELECT he3."time" AS t
                        FROM historian_raw.historian_events he3
                        WHERE he3.tag_id = aa.tag_id
                          AND UPPER(COALESCE(he3.alarm_level, '')) = UPPER(aa.level)
                          AND he3.event_type = 'ALARM_RAISED'
                        ORDER BY he3."time" DESC
                        LIMIT 3
                    ) sub
                ) AS recent_raise_times,
                -- Last operator who cleared this alarm key
                (
                    SELECT aat.action_timestamp
                    FROM historian_raw.alarm_audit_trail aat
                    WHERE aat.metadata->>'alarm_key' = aa.alarm_key
                      AND aat.action_type = 'CLEARED'
                    ORDER BY aat.action_timestamp DESC
                    LIMIT 1
                ) AS last_cleared_at,
                (
                    SELECT aat.performed_by
                    FROM historian_raw.alarm_audit_trail aat
                    WHERE aat.metadata->>'alarm_key' = aa.alarm_key
                      AND aat.action_type = 'CLEARED'
                    ORDER BY aat.action_timestamp DESC
                    LIMIT 1
                ) AS last_cleared_by
            FROM historian_raw.alarm_active aa
            LEFT JOIN historian_meta.tag_master tm ON aa.tag_id = tm.tag_id
            LEFT JOIN historian_raw.historian_events he ON he.event_id = aa.current_event_id
            WHERE aa.alarm_state IN ('ACTIVE_UNACK', 'ACTIVE_ACK', 'RTN_UNACK')
              AND NOT EXISTS (
                  -- Exclude suppressed alarms (active suppression in audit trail)
                  SELECT 1 FROM historian_raw.alarm_audit_trail sup
                  WHERE sup.action_type = 'SUPPRESSED'
                    AND sup.metadata->>'alarm_key' = aa.alarm_key
                    AND (
                        sup.metadata->>'suppress_until' IS NULL
                        OR (sup.metadata->>'suppress_until')::timestamptz > NOW()
                    )
                    AND NOT EXISTS (
                        SELECT 1 FROM historian_raw.alarm_audit_trail uns
                        WHERE uns.action_type = 'UNSUPPRESSED'
                          AND uns.metadata->>'alarm_key' = sup.metadata->>'alarm_key'
                          AND uns.action_timestamp > sup.action_timestamp
                    )
              )
            ORDER BY
                CASE aa.alarm_state
                    WHEN 'ACTIVE_UNACK' THEN 1
                    WHEN 'ACTIVE_ACK'   THEN 2
                    WHEN 'RTN_UNACK'    THEN 3
                    ELSE 4
                END,
                COALESCE(aa.priority, 3) DESC,
                aa.raised_at DESC
            LIMIT {limit}
        """
        
        logger.info(f"Executing alarm query with limit={limit}")
        use_dict_cursor = HAS_REAL_DICT_CURSOR and RealDictCursor is not None
        with db_pool.get_conn() as conn:
            if use_dict_cursor:
                cursor = conn.cursor(cursor_factory=RealDictCursor)
            else:
                cursor = conn.cursor()
            cursor.execute(query)
            rows = cursor.fetchall()
            cursor.close()
        logger.info(f"Query returned {len(rows)} rows, use_dict_cursor={use_dict_cursor}")
        
        alarms = []
        for idx, row in enumerate(rows):
            try:
                # Handle both dict (RealDictCursor) and tuple (regular cursor)
                if use_dict_cursor and isinstance(row, dict):
                    alarm = dict(row)
                else:
                    # Map tuple to dict - must match alarm_active SELECT column order exactly
                    if len(row) < 18:
                        logger.error(f"Row {idx} has only {len(row)} columns, expected 18")
                        continue
                    alarm = {
                        'id':               row[0],
                        'alarm_key':        row[1],
                        'tag_id':           row[2],
                        'tag_name':         row[3],
                        'alarm_level':      row[4],
                        'alarm_state':      row[5],
                        'alarm_priority':   row[6],
                        'alarm_actual_value': row[7],
                        'alarm_setpoint':   row[8],
                        'raised_at':        row[9],
                        'acknowledged_at':  row[10],
                        'acknowledged_by':  row[11],
                        'rtn_at':           row[12],
                        'updated_at':       row[13],
                        'duration_minutes': row[14],
                        'status':           row[15],
                        'message':          row[16],
                        'event_type':       row[17],
                        'instance_seq':     row[18] if len(row) > 18 else None,
                        'transition_seq':   row[19] if len(row) > 19 else None,
                        'occurrence_count':   int(row[20]) if len(row) > 20 and row[20] else 1,
                        'recent_raise_times': row[21] if len(row) > 21 else None,
                        'last_cleared_at':    row[22] if len(row) > 22 else None,
                        'last_cleared_by':    row[23] if len(row) > 23 else None,
                    }
                
                # Convert timestamp fields to ISO format
                for field in ['raised_at', 'acknowledged_at', 'rtn_at', 'updated_at', 'last_cleared_at']:
                    if alarm.get(field):
                        if hasattr(alarm[field], 'isoformat'):
                            alarm[field] = alarm[field].isoformat()
                        else:
                            alarm[field] = str(alarm[field])
                # recent_raise_times: pipe-separated string from STRING_AGG → list of ISO strings
                rrt = alarm.get('recent_raise_times')
                if rrt and isinstance(rrt, str):
                    alarm['recent_raise_times'] = [t.strip() for t in rrt.split('|') if t.strip()]
                elif not rrt:
                    alarm['recent_raise_times'] = []
                alarms.append(alarm)
                logger.debug(f"Alarm: {alarm.get('tag_name')} - {alarm.get('severity')} - {alarm.get('alarm_state')}")
            except Exception as row_error:
                logger.error(f"Error processing row {idx}: {row_error}, row type: {type(row)}, row: {row}")
                continue
        
        logger.info(f"Retrieved {len(alarms)} active alarms")
        
        return jsonify({
            'success': True,
            'alarms': alarms,
            'count': len(alarms)
        })
        
    except Exception as e:
        # db_pool.get_conn() handles rollback automatically on exception
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"Error fetching alarms: {str(e)}")
        logger.error(f"Traceback: {error_trace}")
        return jsonify({
            'success': False,
            'error': str(e),
            'alarms': []
        }), 500


@alarm_bp.route('/acknowledge/<int:alarm_id>', methods=['POST'])
def acknowledge_alarm(alarm_id):
    """
    Acknowledge an alarm by alarm_active.id.

    Flow:
      1. Authenticate operator (Bearer token preferred, ?user= fallback).
      2. Read alarm_active by id — get alarm_key + current state.
         (alarm_active is the runtime table; C# AlarmStateManager is the authority.)
      3. State guard:
           ACTIVE_ACK  → idempotent 200 (already done)
           ACTIVE_UNACK / RTN_UNACK → proceed
           anything else → 400
      4. Proxy POST to C# /api/alarms/{key}/ack.
         C# writes historian_events (ACK journal row) and updates alarm_active.
      5. Write alarm_audit_trail + RBAC audit (Flask owns both of those tables).
    """
    db_service = None
    try:
        # ── Auth ────────────────────────────────────────────────────────────
        token = request.headers.get('Authorization')
        authenticated_user = None
        if token and token.startswith('Bearer '):
            try:
                authenticated_user = container.auth_service.decode_token(token.split(' ')[1])
            except Exception:
                pass

        if authenticated_user:
            user_id  = authenticated_user.get('user_id', 0)
            username = authenticated_user.get('username', 'unknown')
            logger.info(f"Authenticated: {username} (ID: {user_id})")
        else:
            username = request.args.get('user', 'operator')
            try:
                users = container.rbac_service.get_all_users()
                match = next((u for u in users if u['username'] == username), None)
                user_id = match['id'] if match else 0
            except Exception:
                user_id = 0
            logger.warning(f"Legacy auth: user={username} — send Authorization: Bearer <token>")

        notes      = request.json.get('notes', '') if request.is_json else ''
        session_id = request.headers.get('X-Session-ID')
        client_ip  = request.remote_addr

        # ── Read current state from alarm_active ────────────────────────────
        use_dict = HAS_REAL_DICT_CURSOR and RealDictCursor is not None
        with db_pool.get_conn() as conn:
            if use_dict:
                cursor = conn.cursor(cursor_factory=RealDictCursor)
            else:
                cursor = conn.cursor()
            cursor.execute("""
                SELECT aa.alarm_key, aa.alarm_state, aa.tag_id,
                       aa.priority, aa.raised_value, aa.setpoint_value, aa.occurrence_id
                FROM historian_raw.alarm_active aa
                WHERE aa.current_event_id = %s
            """, (alarm_id,))
            result = cursor.fetchone()
            cursor.close()

        if not result:
            return jsonify({'success': False, 'error': 'Alarm not found'}), 404

        if use_dict and isinstance(result, dict):
            alarm_key          = result['alarm_key']
            alarm_state        = result['alarm_state']
            tag_id             = result['tag_id']
            alarm_priority     = result.get('priority')
            alarm_actual_value = result.get('raised_value')
            alarm_setpoint     = result.get('setpoint_value')
            occurrence_id      = str(result.get('occurrence_id')) if result.get('occurrence_id') else None
        else:
            alarm_key          = result[0]
            alarm_state        = result[1]
            tag_id             = result[2]
            alarm_priority     = result[3]
            alarm_actual_value = result[4]
            alarm_setpoint     = result[5]
            occurrence_id      = str(result[6]) if result[6] else None

        # ── State guard ─────────────────────────────────────────────────────
        if alarm_state == 'ACTIVE_ACK':
            logger.info(f"Alarm {alarm_id} (key={alarm_key}) already ACTIVE_ACK")
            return jsonify({
                'success': True, 'alarm_id': alarm_id, 'alarm_key': alarm_key,
                'acknowledged_by': username, 'notes': notes, 'already_acknowledged': True
            })

        if alarm_state not in ('ACTIVE_UNACK', 'RTN_UNACK'):
            logger.warning(f"Alarm {alarm_id} cannot ACK (state={alarm_state})")
            return jsonify({
                'success': False,
                'error': f"Alarm is in {alarm_state} state, cannot acknowledge"
            }), 400

        # ── Proxy to C# AlarmStateManager ───────────────────────────────────
        import urllib.parse
        encoded_key = urllib.parse.quote(alarm_key, safe='')
        try:
            resp = _requests.post(
                f"{_OPC_BASE}/api/alarms/{encoded_key}/ack",
                json={'operator': username, 'notes': notes},
                timeout=_OPC_TIMEOUT
            )
            if resp.status_code not in (200, 201):
                # Pass through C# structured error body so React gets reason/current_state
                try:
                    err_body    = resp.json()
                    reason      = err_body.get('error', f'HTTP {resp.status_code}')
                    cs_state    = err_body.get('current_state')
                except Exception:
                    reason      = resp.text or f'HTTP {resp.status_code}'
                    cs_state    = None
                logger.error(f"C# ACK proxy failed {resp.status_code}: {reason}")
                error_resp = {'success': False, 'reason': reason, 'error': reason}
                if cs_state:
                    error_resp['current_state'] = cs_state
                return jsonify(error_resp), resp.status_code
            logger.info(f"Alarm {alarm_id} (key={alarm_key}) ACK by {username} via C# state manager")
        except _requests.exceptions.Timeout:
            logger.error(f"C# ACK proxy timed out after {_OPC_READ_TIMEOUT}s for alarm {alarm_id}")
            return jsonify({
                'success': False,
                'reason': 'PROXY_TIMEOUT',
                'error': f'C# state manager did not respond within {_OPC_READ_TIMEOUT}s — try again'
            }), 503
        except _requests.exceptions.ConnectionError:
            logger.error(f"C# ACK proxy connection refused (C# down?) for alarm {alarm_id}")
            return jsonify({
                'success': False,
                'reason': 'PROXY_UNAVAILABLE',
                'error': 'C# OPC service is not reachable — alarm state not changed'
            }), 503
        except _requests.exceptions.RequestException as proxy_err:
            logger.error(f"C# proxy error for ACK: {proxy_err}")
            return jsonify({
                'success': False,
                'reason': 'PROXY_ERROR',
                'error': str(proxy_err)
            }), 503

        # ISA-18.2: RTN_UNACK + ACK → CLEARED (lifecycle complete); ACTIVE_UNACK + ACK → ACTIVE_ACK
        new_state  = 'CLEARED'       if alarm_state == 'RTN_UNACK' else 'ACTIVE_ACK'
        event_type = 'ALARM_CLEARED' if alarm_state == 'RTN_UNACK' else 'ALARM_ACKNOWLEDGED'

        # ── Audit trail (Flask owns alarm_audit_trail) ───────────────────────
        if HAS_ALARM_AUDIT and AlarmAuditDAO:
            try:
                db_service = container.historical_service
                audit_dao = AlarmAuditDAO(db_service)
                audit_dao.insert_audit_record(
                    event_id=alarm_id,
                    tag_id=tag_id,
                    event_type=event_type,
                    action_type='ACKNOWLEDGED',
                    performed_by=username,
                    previous_state=alarm_state,
                    new_state=new_state,
                    alarm_priority=alarm_priority,
                    alarm_actual_value=alarm_actual_value,
                    alarm_setpoint=alarm_setpoint,
                    action_notes=notes,
                    session_id=session_id,
                    client_ip=client_ip,
                    occurrence_id=occurrence_id
                )
            except Exception as audit_err:
                logger.error(f"Alarm audit trail write failed (ACK): {audit_err}")

        try:
            container.audit_service.log_alarm_action(
                user_id=user_id, username=username, alarm_id=str(alarm_id),
                action='acknowledge', ip_address=client_ip, session_id=session_id
            )
        except Exception as rbac_err:
            logger.error(f"RBAC audit write failed: {rbac_err}")

        return jsonify({
            'success': True,
            'alarm_id': alarm_id,
            'alarm_key': alarm_key,
            'event_type': event_type,
            'new_state': new_state,
            'acknowledged_by': username,
            'notes': notes
        })

    except Exception as e:
        try:
            if db_service and db_service.connection:
                db_service.connection.rollback()
        except Exception:
            pass
        logger.error(f"Error acknowledging alarm {alarm_id}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@alarm_bp.route('/clear/<int:alarm_id>', methods=['POST'])
def clear_alarm(alarm_id):
    """
    Clear an acknowledged alarm by ID (updates alarm_state to CLEARED)
    Only ACKNOWLEDGED alarms can be cleared
    Requires ALARM_CLEAR permission in RBAC
    
    AUTHENTICATION:
    - Preferred: Use @token_required with Authorization: Bearer <token>
    - Fallback: Legacy query param ?user=username (DEPRECATED - for backward compatibility)
    """
    db_service = None
    try:
        # Try to get authenticated user from token first
        token = request.headers.get('Authorization')
        authenticated_user = None
        
        if token and token.startswith('Bearer '):
            token_value = token.split(' ')[1]
            try:
                authenticated_user = container.auth_service.decode_token(token_value)
            except:
                pass
        
        # Get user info from token OR fallback to query param (deprecated)
        if authenticated_user:
            user_id = authenticated_user.get('user_id', 0)
            username = authenticated_user.get('username', 'unknown')
            logger.info(f"✅ Authenticated user: {username} (ID: {user_id})")
        else:
            # FALLBACK: Legacy query param (backward compatibility)
            username = request.args.get('user', 'operator')
            
            # Try to get user_id from username
            try:
                user_info = container.rbac_service.get_all_users()
                matching_user = next((u for u in user_info if u['username'] == username), None)
                user_id = matching_user['id'] if matching_user else 0
            except:
                user_id = 0
            
            logger.warning(f"⚠️ Using legacy authentication: user={username}, user_id={user_id}")
        
        # ========== RBAC CHECK: Can user clear alarms? ==========
        try:
            can_clear = container.rbac_service.can_user_clear_alarm(user_id)
            if not can_clear:
                logger.warning(f"❌ User {username} (ID: {user_id}) does NOT have ALARM_CLEAR permission")
                return jsonify({
                    'success': False,
                    'error': 'You do not have permission to clear alarms'
                }), 403
            
            # Check if approval is required for this user
            requires_approval = container.rbac_service.requires_approval_to_clear_alarm(user_id)
            if requires_approval:
                logger.info(f"⚠️ Alarm clear for {username} requires approval (approval workflow not implemented yet)")
                # For now, we'll just log the requirement but allow the operation
                # In production, implement approval workflow
        except Exception as rbac_error:
            logger.error(f"RBAC check failed: {rbac_error}")
            # Default to deny if RBAC check fails (fail-safe)
            return jsonify({
                'success': False,
                'error': 'Permission verification failed'
            }), 500
        
        db_service = container.historical_service
        
        # Get clearing information from request
        clear_reason = ''
        clear_notes = ''
        
        # Try to get clearing details from JSON body
        try:
            if request.is_json and request.json:
                clear_reason = request.json.get('reason', '')
                clear_notes = request.json.get('notes', '')
                logger.info(f"Clear alarm {alarm_id} - Reason: {clear_reason}, Notes: {clear_notes}")
        except Exception as e:
            logger.warning(f"Could not parse JSON body: {e}")
        
        logger.info(f"Attempting to clear alarm {alarm_id} by user {username}")
        session_id = request.headers.get('X-Session-ID', None)
        client_ip = request.remote_addr
        
        # Check current state from alarm_active — C# is the authority on state
        check_query = """
            SELECT aa.alarm_state, aa.alarm_key,
                   aa.tag_id, aa.priority,
                   aa.raised_value, aa.setpoint_value, aa.occurrence_id
            FROM historian_raw.alarm_active aa
            WHERE aa.current_event_id = %s
        """
        if HAS_REAL_DICT_CURSOR and RealDictCursor:
            try:
                cursor = db_service.connection.cursor(cursor_factory=RealDictCursor)
                use_dict = True
            except Exception:
                cursor = db_service.connection.cursor()
                use_dict = False
        else:
            cursor = db_service.connection.cursor()
            use_dict = False

        cursor.execute(check_query, (alarm_id,))
        result = cursor.fetchone()

        if not result:
            cursor.close()
            logger.error(f"Alarm {alarm_id} not found in alarm_active")
            return jsonify({'success': False, 'error': 'Alarm not found'}), 404

        if use_dict and isinstance(result, dict):
            alarm_state        = result['alarm_state']
            alarm_key          = result['alarm_key']
            tag_id             = result['tag_id']
            alarm_priority     = result.get('priority')
            alarm_actual_value = result.get('raised_value')
            alarm_setpoint     = result.get('setpoint_value')
            occurrence_id      = str(result.get('occurrence_id')) if result.get('occurrence_id') else None
            event_type         = 'ALARM_RAISED'
        else:
            alarm_state        = result[0]
            alarm_key          = result[1]
            tag_id             = result[2]
            alarm_priority     = result[3]
            alarm_actual_value = result[4]
            alarm_setpoint     = result[5]
            occurrence_id      = str(result[6]) if result[6] else None
            event_type         = 'ALARM_RAISED'

        cursor.close()
        logger.info(f"Current alarm state: {alarm_state} key: {alarm_key}")

        # ── State validation before proxying CLEAR to C# ──────────────────────
        # ISA-18.2: operator MUST acknowledge before clearing.
        # Allowing ACTIVE_UNACK clears causes auto-ACK+clear even when value is still high,
        # generating phantom CLEARED rows + immediate re-raise as new ACTIVE_UNACK.
        if alarm_state == 'ACTIVE_UNACK':
            logger.warning(f"Alarm {alarm_id} is ACTIVE_UNACK — must ACK first before clear (ISA-18.2)")
            return jsonify({
                'success': False,
                'error': 'Alarm must be acknowledged before it can be cleared. Please ACK first.',
                'reason': 'MUST_ACK_FIRST',
                'current_state': alarm_state
            }), 400
        elif alarm_state == 'ACTIVE_ACK':
            logger.info(f"Alarm {alarm_id} is ACTIVE_ACK — proceeding to clear")
        else:
            # Any other state (e.g. RTN_UNACK, already CLEARED) — reject
            logger.warning(f"Alarm {alarm_id} cannot be cleared (current state: {alarm_state})")
            return jsonify({
                'success': False,
                'error': f"Alarm is in {alarm_state} state, cannot be cleared"
            }), 400

        # ── Proxy CLEAR to C# AlarmStateManager ────────────────────────────
        # C# owns historian_events (append-only journal) and alarm_active (runtime state).
        try:
            import urllib.parse
            encoded_key = urllib.parse.quote(alarm_key, safe='')
            resp = _requests.post(
                f"{_OPC_BASE}/api/alarms/{encoded_key}/clear",
                json={'operator': username, 'reason': clear_reason, 'notes': clear_notes},
                timeout=_OPC_TIMEOUT
            )
            if resp.status_code == 422:
                # C# blocked the clear because process value is still violating the setpoint.
                try:
                    err_body = resp.json()
                except Exception:
                    err_body = {'success': False, 'error': resp.text, 'reason': 'VALUE_STILL_VIOLATING'}
                live_val  = err_body.get('live_value')
                sp_val    = err_body.get('setpoint')
                is_high   = err_body.get('is_high_alarm', True)
                direction = 'above' if is_high else 'below'
                block_msg = (
                    f"Clear BLOCKED by ISA-18.2 safety gate — "
                    f"PV {live_val} still {direction} setpoint {sp_val}. "
                    f"Alarm state unchanged."
                )
                logger.warning(f"C# CLEAR blocked (value still {direction} setpoint) for alarm {alarm_id}: PV={live_val} SP={sp_val}")
                # Write a CLEAR_BLOCKED record to the audit trail so operators can see the attempt
                if HAS_ALARM_AUDIT and AlarmAuditDAO:
                    try:
                        audit_dao = AlarmAuditDAO(db_service)
                        audit_dao.insert_audit_record(
                            event_id=alarm_id,
                            tag_id=tag_id,
                            event_type='ALARM_CLEAR_BLOCKED',
                            action_type='CLEAR_BLOCKED',
                            performed_by=username,
                            previous_state=alarm_state,
                            new_state=alarm_state,   # state did NOT change
                            alarm_priority=alarm_priority,
                            alarm_actual_value=live_val if live_val is not None else alarm_actual_value,
                            alarm_setpoint=sp_val if sp_val is not None else alarm_setpoint,
                            action_reason='VALUE_STILL_VIOLATING',
                            action_notes=block_msg,
                            session_id=session_id,
                            client_ip=client_ip,
                            occurrence_id=occurrence_id
                        )
                    except Exception as audit_err:
                        logger.error(f"Alarm audit trail write failed (CLEAR_BLOCKED): {audit_err}")
                return jsonify(err_body), 422
            if resp.status_code not in (200, 201):
                try:
                    err_body = resp.json()
                    reason   = err_body.get('error', f'HTTP {resp.status_code}')
                    cs_state = err_body.get('current_state')
                except Exception:
                    reason   = resp.text or f'HTTP {resp.status_code}'
                    cs_state = None
                logger.error(f"C# CLEAR proxy failed {resp.status_code}: {reason}")
                error_resp = {'success': False, 'reason': reason, 'error': reason}
                if cs_state:
                    error_resp['current_state'] = cs_state
                return jsonify(error_resp), resp.status_code
            logger.info(f"Alarm {alarm_id} (key={alarm_key}) cleared by {username} via C# state manager")
        except _requests.exceptions.Timeout:
            logger.error(f"C# CLEAR proxy timed out after {_OPC_READ_TIMEOUT}s for alarm {alarm_id}")
            return jsonify({
                'success': False,
                'reason': 'PROXY_TIMEOUT',
                'error': f'C# state manager did not respond within {_OPC_READ_TIMEOUT}s — try again'
            }), 503
        except _requests.exceptions.ConnectionError:
            logger.error(f"C# CLEAR proxy connection refused for alarm {alarm_id}")
            return jsonify({
                'success': False,
                'reason': 'PROXY_UNAVAILABLE',
                'error': 'C# OPC service is not reachable — alarm state not changed'
            }), 503
        except _requests.exceptions.RequestException as proxy_err:
            logger.error(f"C# proxy error for CLEAR: {proxy_err}")
            return jsonify({'success': False, 'reason': 'PROXY_ERROR', 'error': str(proxy_err)}), 503

        # ── Audit trail (Flask owns alarm_audit_trail) ───────────────────────
        if HAS_ALARM_AUDIT and AlarmAuditDAO:
            try:
                audit_dao = AlarmAuditDAO(db_service)
                audit_dao.insert_audit_record(
                    event_id=alarm_id,
                    tag_id=tag_id,
                    event_type='ALARM_CLEARED',
                    action_type='CLEARED',
                    performed_by=username,
                    previous_state='ACTIVE_ACK',
                    new_state='CLEARED',
                    alarm_priority=alarm_priority,
                    alarm_actual_value=alarm_actual_value,
                    alarm_setpoint=alarm_setpoint,
                    action_reason=clear_reason,
                    action_notes=clear_notes,
                    session_id=session_id,
                    client_ip=client_ip,
                    occurrence_id=occurrence_id
                )
            except Exception as audit_err:
                logger.error(f"Alarm audit trail write failed (CLEAR): {audit_err}")

        try:
            container.audit_service.log_alarm_action(
                user_id=user_id, username=username, alarm_id=str(alarm_id),
                action='clear', ip_address=client_ip, session_id=session_id
            )
        except Exception as rbac_err:
            logger.error(f"RBAC audit write failed: {rbac_err}")

        return jsonify({
            'success': True,
            'alarm_id': alarm_id,
            'alarm_key': alarm_key,
            'event_type': 'ALARM_CLEARED',
            'new_state': 'CLEARED',
            'cleared_by': username,
            'clear_reason': clear_reason,
            'clear_notes': clear_notes
        })
            
    except Exception as e:
        # Rollback transaction on error
        try:
            if db_service and db_service.connection:
                db_service.connection.rollback()
                logger.warning("Transaction rolled back after clear error")
        except Exception as rollback_error:
            logger.error(f"Failed to rollback transaction: {rollback_error}")
        
        logger.error(f"Error clearing alarm {alarm_id}: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@alarm_bp.route('/acknowledge/by-tag', methods=['POST'])
def acknowledge_by_tag():
    """
    Acknowledge an alarm identified by tag_id (no DB integer ID required).
    Used when the caller knows the tag but not the historian_events row ID —
    e.g. external integrations or MQTT-sourced payloads.
    Payload: {tagId, user, message (optional)}
    Proxies to C# AlarmStateManager; writes alarm audit trail on success.
    """
    try:
        if not request.is_json:
            return jsonify({
                'success': False,
                'error': 'Content-Type must be application/json'
            }), 400
        
        alarm_data = request.json
        alarm_id = alarm_data.get('id')
        tag_id = alarm_data.get('tagId')
        message = alarm_data.get('message', '')
        priority = alarm_data.get('priority', 2)
        user = alarm_data.get('user', 'operator')
        timestamp = alarm_data.get('timestamp')
        
        if not alarm_id or not tag_id:
            return jsonify({
                'success': False,
                'error': 'alarm_id and tagId are required'
            }), 400
        
        db_service = container.historical_service
        if not db_service or not db_service.connection:
            return jsonify({
                'success': False,
                'error': 'Database not available'
            }), 503
        
        cursor = db_service.connection.cursor()
        
        # Check if alarm exists in alarm_active (runtime operational table)
        check_query = """
            SELECT aa.alarm_key, aa.alarm_state, aa.tag_id
            FROM historian_raw.alarm_active aa
            WHERE aa.tag_id = %s
              AND aa.alarm_state IN ('ACTIVE_UNACK', 'ACTIVE_ACK', 'RTN_UNACK')
            ORDER BY aa.raised_at DESC
            LIMIT 1
        """
        cursor.execute(check_query, (tag_id,))
        existing = cursor.fetchone()
        cursor.close()
        
        if existing:
            alarm_key   = existing[0]
            alarm_state = existing[1]

            # Proxy ACK to C# AlarmStateManager — sole authority over alarm state
            try:
                import urllib.parse
                encoded_key = urllib.parse.quote(alarm_key, safe='')
                resp = _requests.post(
                    f"{_OPC_BASE}/api/alarms/{encoded_key}/ack",
                    json={'operator': user, 'notes': message},
                    timeout=_OPC_TIMEOUT
                )
                if resp.status_code not in (200, 201):
                    logger.error(f"C# ACK proxy failed {resp.status_code}: {resp.text}")
                    return jsonify({'success': False, 'error': f'State manager rejected ACK: {resp.text}'}), resp.status_code
            except _requests.exceptions.RequestException as proxy_err:
                logger.error(f"C# proxy unreachable for ACK by-tag: {proxy_err}")
                return jsonify({'success': False, 'error': 'OPC service unreachable'}), 503

            # Write audit trail after successful C# proxy
            if HAS_ALARM_AUDIT and AlarmAuditDAO:
                try:
                    audit_dao = AlarmAuditDAO(db_service)
                    audit_dao.insert_audit_record(
                        event_id=None,
                        tag_id=tag_id,
                        event_type='ALARM_RAISED',
                        action_type='ACKNOWLEDGED',
                        performed_by=user,
                        previous_state=alarm_state,
                        new_state='ACTIVE_ACK',
                        alarm_priority=priority,
                        action_notes=message,
                    )
                except Exception as audit_err:
                    logger.error(f"Failed to write audit trail for ack-by-tag: {audit_err}")

            logger.info(f"Alarm tag={tag_id} (key={alarm_key}) acknowledged by {user} via by-tag route")
            return jsonify({
                'success': True,
                'alarm_key': alarm_key,
                'acknowledged_by': user
            })
        else:
            # Alarm not found — C# has not raised it yet or it was already cleared.
            # HMI must NOT insert alarm rows. Return 404 so the UI can inform the operator.
            logger.warning(
                f"acknowledge_mqtt_alarm: alarm_id={alarm_id} tag_id={tag_id} not found "
                f"in historian_events (last 1h). C# evaluator may not have raised it yet."
            )
            return jsonify({
                'success': False,
                'error': 'Alarm not found. The alarm may not have been raised yet or has already been cleared.'
            }), 404
            
    except Exception as e:
        import traceback
        logger.error(f"Error acknowledging MQTT alarm: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@alarm_bp.route('/stats', methods=['GET'])
def get_alarm_stats():
    """
    Get alarm statistics by priority and state
    """
    try:
        # Read stats from alarm_active (runtime operational table — fast, tiny dataset)
        query = """
            SELECT 
                COUNT(*) FILTER (WHERE alarm_state = 'ACTIVE_UNACK')                       AS active_unack_count,
                COUNT(*) FILTER (WHERE alarm_state = 'ACTIVE_ACK')                         AS active_ack_count,
                COUNT(*) FILTER (WHERE alarm_state = 'RTN_UNACK')                          AS rtn_unack_count,
                COUNT(*) FILTER (WHERE alarm_state IN ('ACTIVE_UNACK','ACTIVE_ACK'))        AS active_count,
                COUNT(*) FILTER (WHERE priority = 5)                                        AS critical_count,
                COUNT(*) FILTER (WHERE priority = 4)                                        AS urgent_count,
                COUNT(*) FILTER (WHERE priority = 3)                                        AS high_count,
                COUNT(*) FILTER (WHERE priority IN (1,2))                                   AS warning_count
            FROM historian_raw.alarm_active
            WHERE alarm_state IN ('ACTIVE_UNACK', 'ACTIVE_ACK', 'RTN_UNACK')
        """

        use_dict = HAS_REAL_DICT_CURSOR and RealDictCursor is not None
        with db_pool.get_conn() as conn:
            if use_dict:
                cursor = conn.cursor(cursor_factory=RealDictCursor)
            else:
                cursor = conn.cursor()
            cursor.execute(query)
            row = cursor.fetchone()
            cols = [d[0] for d in cursor.description]
            cursor.close()

        if use_dict and isinstance(row, dict):
            stats = dict(row)
        elif row:
            stats = dict(zip(cols, row))
        else:
            stats = {}

        return jsonify({
            'success': True,
            'stats': stats
        })
        
    except Exception as e:
        logger.error(f"Error fetching alarm stats: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@alarm_bp.route('/trips', methods=['GET'])
def get_trip_events():
    """
    Get trip events with complete causality chain and production metrics.
    
    PHASE 1 FEATURES (ISA-18.2 & EEMUA 191 Compliant):
    - Root cause analysis (alarm → trip causality)
    - Production loss calculation (MWh)
    - Revenue impact assessment
    - Causality chain (sequence of events)
    - Operator action tracking
    """
    try:
        limit = request.args.get('limit', 20, type=int)
        
        db_service = container.historical_service
        if not db_service or not db_service.connection:
            return jsonify({
                'success': False,
                'error': 'Database not available',
                'trips': []
            }), 503
        
        # Main trip query with all Phase 1 fields
        query = """
            SELECT 
                t.trip_event_id,
                t.trip_time,
                t.trip_tag_id,
                tm.tag_name as trip_tag_name,
                t.trip_category,
                t.equipment_affected,
                t.trip_duration_seconds,
                t.trip_cleared_at,
                t.root_cause_tag_id,
                rtm.tag_name as root_cause_tag_name,
                t.operator_notes,
                t.automated_diagnosis,
                t.rated_capacity_mw,
                t.revenue_per_mwh,
                t.acknowledged_at,
                t.acknowledged_by,
                t.cleared_by,
                -- Initiating alarm details
                e.event_type as initiating_alarm_type,
                e.severity as initiating_alarm_severity,
                e.time as alarm_raised_at,
                e.alarm_actual_value as initiating_alarm_value,
                e.alarm_setpoint as initiating_alarm_setpoint,
                EXTRACT(EPOCH FROM (t.trip_time - e.time)) as alarm_to_trip_seconds,
                e.alarm_priority,
                -- Calculate production loss in MWh if duration and capacity are available
                CASE 
                    WHEN t.trip_duration_seconds IS NOT NULL AND t.rated_capacity_mw IS NOT NULL THEN
                        (t.rated_capacity_mw * (t.trip_duration_seconds::DOUBLE PRECISION / 3600.0))
                    ELSE NULL
                END as production_loss_mwh,
                -- Calculate revenue impact
                CASE 
                    WHEN t.trip_duration_seconds IS NOT NULL AND t.rated_capacity_mw IS NOT NULL AND t.revenue_per_mwh IS NOT NULL THEN
                        (t.rated_capacity_mw * (t.trip_duration_seconds::DOUBLE PRECISION / 3600.0) * t.revenue_per_mwh)
                    ELSE NULL
                END as revenue_impact
            FROM historian_raw.trip_event_tracking t
            LEFT JOIN historian_meta.tag_master tm ON t.trip_tag_id = tm.tag_id
            LEFT JOIN historian_meta.tag_master rtm ON t.root_cause_tag_id = rtm.tag_id
            LEFT JOIN historian_raw.historian_events e ON t.initiating_alarm_id = e.event_id
            ORDER BY t.trip_time DESC
            LIMIT %s
        """
        
        cursor = db_service.connection.cursor(cursor_factory=RealDictCursor)
        cursor.execute(query, (limit,))
        rows = cursor.fetchall()
        
        trips = []
        for row in rows:
            trip = dict(row)
            
            # Convert timestamps to ISO format
            for field in ['trip_time', 'trip_cleared_at', 'alarm_raised_at', 'acknowledged_at']:
                if trip.get(field):
                    if hasattr(trip[field], 'isoformat'):
                        trip[field] = trip[field].isoformat()
            
            # Round numeric values to 2 decimal places
            for field in ['production_loss_mwh', 'revenue_impact', 'rated_capacity_mw', 'revenue_per_mwh']:
                if trip.get(field) is not None:
                    trip[field] = round(float(trip[field]), 2)
            
            # Get causality chain for this trip (related alarms)
            causality_chain = get_causality_chain(
                db_service, 
                trip['trip_time'], 
                trip['trip_tag_id'],
                seconds_before=10,
                seconds_after=5
            )
            trip['causality_chain'] = causality_chain
            
            # Get interlock status at time of trip
            interlock_status = get_interlock_status_at_time(
                db_service,
                trip['trip_time']
            )
            trip['interlock_status_at_trip'] = interlock_status
            
            trips.append(trip)
        
        cursor.close()
        
        logger.info(f"Retrieved {len(trips)} trip events with Phase 1 enrichment")
        
        return jsonify({
            'success': True,
            'trips': trips,
            'count': len(trips)
        })
        
    except Exception as e:
        logger.error(f"Error fetching trips: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': str(e),
            'trips': []
        }), 500


def get_causality_chain(db_service, trip_time, trip_tag_id, seconds_before=10, seconds_after=5):
    """
    Get all alarms that occurred around trip time for causality analysis.
    
    Looks for alarms:
    - Up to `seconds_before` seconds before trip
    - Up to `seconds_after` seconds after trip (interlock response)
    """
    try:
        query = """
            SELECT 
                he.event_id,
                he.event_type,
                he.time as event_time,
                he.severity,
                he.alarm_priority,
                he.alarm_actual_value,
                he.alarm_setpoint,
                COALESCE(tm.tag_name, he.tag_id) as tag_name,
                he.tag_id,
                he.message,
                EXTRACT(EPOCH FROM (he.time - %s::TIMESTAMP WITH TIME ZONE)) as seconds_from_trip
            FROM historian_raw.historian_events he
            LEFT JOIN historian_meta.tag_master tm ON he.tag_id = tm.tag_id
            WHERE he.time >= %s::TIMESTAMP WITH TIME ZONE - INTERVAL '%s seconds'
              AND he.time <= %s::TIMESTAMP WITH TIME ZONE + INTERVAL '%s seconds'
              AND he.event_type LIKE 'ALARM_%%'
            ORDER BY ABS(EXTRACT(EPOCH FROM (he.time - %s::TIMESTAMP WITH TIME ZONE)))
        """
        
        cursor = db_service.connection.cursor(cursor_factory=RealDictCursor)
        cursor.execute(query, (trip_time, trip_time, seconds_before, trip_time, seconds_after, trip_time))
        rows = cursor.fetchall()
        cursor.close()
        
        chain = []
        for row in rows:
            event = dict(row)
            if event.get('event_time') and hasattr(event['event_time'], 'isoformat'):
                event['event_time'] = event['event_time'].isoformat()
            event['seconds_from_trip'] = round(float(event['seconds_from_trip']), 2) if event.get('seconds_from_trip') else None
            chain.append(event)
        
        return chain
    except Exception as e:
        logger.warning(f"Could not retrieve causality chain: {e}")
        return []


def get_interlock_status_at_time(db_service, trip_time):
    """
    Get interlock states that were active at time of trip.
    """
    try:
        query = """
            SELECT 
                ist.interlock_tag_id,
                COALESCE(tm.tag_name, ist.interlock_tag_id) as interlock_tag_name,
                ist.interlock_type,
                ist.interlock_state,
                ist.affected_equipment,
                ist.event_time,
                EXTRACT(EPOCH FROM (%s::TIMESTAMP WITH TIME ZONE - ist.event_time)) as seconds_before_trip
            FROM historian_raw.interlock_state_tracking ist
            LEFT JOIN historian_meta.tag_master tm ON ist.interlock_tag_id = tm.tag_id
            WHERE ist.event_time <= %s::TIMESTAMP WITH TIME ZONE
              AND ist.interlock_state IN ('VIOLATED', 'BYPASSED')
            ORDER BY ist.event_time DESC
            LIMIT 5
        """
        
        cursor = db_service.connection.cursor(cursor_factory=RealDictCursor)
        cursor.execute(query, (trip_time, trip_time))
        rows = cursor.fetchall()
        cursor.close()
        
        status = []
        for row in rows:
            item = dict(row)
            if item.get('event_time') and hasattr(item['event_time'], 'isoformat'):
                item['event_time'] = item['event_time'].isoformat()
            item['seconds_before_trip'] = round(float(item['seconds_before_trip']), 2) if item.get('seconds_before_trip') else None
            status.append(item)
        
        return status
    except Exception as e:
        logger.warning(f"Could not retrieve interlock status: {e}")
        return []


@alarm_bp.route('/interlocks', methods=['GET'])
def get_interlock_states():
    """
    Get interlock state violations and bypasses (from interlock_state_tracking table)
    """
    try:
        limit = request.args.get('limit', 20, type=int)
        show_all = request.args.get('show_all', 'false').lower() == 'true'
        
        db_service = container.historical_service
        if not db_service or not db_service.connection:
            return jsonify({
                'success': False,
                'error': 'Database not available',
                'interlocks': []
            }), 503
        
        # Filter for violations and bypasses unless show_all is true
        where_clause = "" if show_all else "WHERE ist.interlock_state IN ('VIOLATED', 'BYPASSED')"
        
        query = f"""
            SELECT 
                ist.interlock_event_id,
                ist.event_time,
                ist.interlock_tag_id,
                tm.tag_name as interlock_tag_name,
                ist.interlock_type,
                ist.interlock_state,
                ist.previous_state,
                ist.state_duration_seconds,
                ist.affected_equipment,
                ist.bypass_reason,
                ist.bypass_authorized_by,
                ist.bypass_expires_at,
                ist.related_trip_event_id,
                CASE 
                    WHEN ist.interlock_state = 'BYPASSED' AND ist.bypass_expires_at < NOW() THEN 'EXPIRED_BYPASS'
                    WHEN ist.interlock_state = 'BYPASSED' THEN 'ACTIVE_BYPASS'
                    WHEN ist.interlock_state = 'VIOLATED' THEN 'VIOLATION'
                    ELSE 'NORMAL'
                END as status,
                CASE 
                    WHEN ist.bypass_expires_at IS NOT NULL AND ist.bypass_expires_at > NOW() THEN
                        EXTRACT(EPOCH FROM (ist.bypass_expires_at - NOW()))
                    ELSE NULL
                END as bypass_remaining_seconds
            FROM historian_raw.interlock_state_tracking ist
            LEFT JOIN historian_meta.tag_master tm ON ist.interlock_tag_id = tm.tag_id
            {where_clause}
            ORDER BY ist.event_time DESC
            LIMIT %s
        """
        
        cursor = db_service.connection.cursor(cursor_factory=RealDictCursor)
        cursor.execute(query, (limit,))
        rows = cursor.fetchall()
        
        interlocks = []
        for row in rows:
            interlock = dict(row)
            # Convert timestamps
            for field in ['event_time', 'bypass_expires_at']:
                if interlock.get(field):
                    if hasattr(interlock[field], 'isoformat'):
                        interlock[field] = interlock[field].isoformat()
            interlocks.append(interlock)
        
        cursor.close()
        
        logger.info(f"Retrieved {len(interlocks)} interlock states")
        
        return jsonify({
            'success': True,
            'interlocks': interlocks,
            'count': len(interlocks)
        })
        
    except Exception as e:
        logger.error(f"Error fetching interlocks: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e),
            'interlocks': []
        }), 500


@alarm_bp.route('/audit/<int:alarm_id>', methods=['GET'])
def get_alarm_audit_trail(alarm_id):
    """
    Get complete audit trail for a specific alarm with pagination
    Returns all state changes (RAISED, ACKNOWLEDGED, CLEARED, etc.)
    Query params: page (default 1), page_size (default 20), sort (desc/asc)
    """
    try:
        # Get pagination parameters
        page = max(1, int(request.args.get('page', 1)))
        page_size = max(1, min(100, int(request.args.get('page_size', 20))))  # Max 100
        sort_order = request.args.get('sort', 'desc').lower()  # desc=newest first (default - current state first)
        
        offset = (page - 1) * page_size
        
        db_service = container.historical_service
        if not db_service or not db_service.connection:
            return jsonify({
                'success': False,
                'error': 'Database not available',
                'audit_trail': []
            }), 503
        
        if not HAS_ALARM_AUDIT or not AlarmAuditDAO:
            return jsonify({
                'success': False,
                'error': 'Alarm audit trail module not available',
                'audit_trail': []
            }), 503
        
        try:
            audit_dao = AlarmAuditDAO(db_service)
            
            # Get total count for pagination
            total_count = audit_dao.count_audit_records(event_id=alarm_id)
            
            # Get paginated audit records
            audit_records = audit_dao.get_audit_trail_enhanced(
                event_id=alarm_id,
                limit=page_size,
                offset=offset,
                sort_order=sort_order
            )
            
            # Calculate has_more flag
            has_more = (offset + len(audit_records)) < total_count
            
            # Get current alarm info from alarm_active
            alarm_info = None
            with db_service.connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        aa.occurrence_id,
                        aa.alarm_state,
                        aa.raised_value,
                        aa.setpoint_value,
                        aa.priority,
                        aa.tag_id,
                        COALESCE(tm.tag_name, aa.tag_id) AS tag_name
                    FROM historian_raw.alarm_active aa
                    LEFT JOIN historian_meta.tag_master tm ON aa.tag_id = tm.tag_id
                    WHERE aa.current_event_id = %s
                    LIMIT 1
                    """,
                    (alarm_id,),
                )
                row = cursor.fetchone()
                
                if row:
                    if isinstance(row, dict):
                        alarm_info = {
                            'occurrence_id': str(row.get('occurrence_id')) if row.get('occurrence_id') else None,
                            'current_state': row.get('alarm_state'),
                            'lifecycle_state': _map_lifecycle_state(row.get('alarm_state')),
                            'alarm_value': row.get('raised_value'),
                            'setpoint': row.get('setpoint_value'),
                            'priority': row.get('priority'),
                            'priority_label': _priority_label(row.get('priority')),
                            'tag_id': row.get('tag_id'),
                            'tag_name': row.get('tag_name')
                        }
                    else:
                        alarm_info = {
                            'occurrence_id': str(row[0]) if row[0] else None,
                            'current_state': row[1],
                            'lifecycle_state': _map_lifecycle_state(row[1]),
                            'alarm_value': row[2],
                            'setpoint': row[3],
                            'priority': row[4],
                            'priority_label': _priority_label(row[4]),
                            'tag_id': row[5],
                            'tag_name': row[6]
                        }

            # Map lifecycle states for all audit records
            for record in audit_records:
                if record.get('new_state'):
                    record['lifecycle_state'] = _map_lifecycle_state(record['new_state'])

            # Sort: RAISED always first, then all others by timestamp DESC (newest first)
            # Use negative timestamp for DESC order (newer timestamps are larger, so -timestamp makes them sort first)
            def sort_key(r):
                if r.get('action_type') == 'RAISED':
                    return (0, '')  # RAISED always first
                else:
                    # Sort DESC by timestamp - reverse the string for comparison
                    ts = r.get('action_timestamp') or ''
                    return (1, ts)
            
            audit_records.sort(key=sort_key, reverse=False)
            # After sorting with (1, ts), reverse the non-RAISED group
            raised = [r for r in audit_records if r.get('action_type') == 'RAISED']
            others = [r for r in audit_records if r.get('action_type') != 'RAISED']
            others.reverse()  # Reverse to get DESC order
            audit_records = raised + others

            # Some legacy/current flows may miss explicit RAISED audit insertion.
            # Backfill from historian_events so UI always shows raised timestamp/value context.
            has_raised = any((rec.get('action_type') or '').upper() == 'RAISED' for rec in audit_records)
            if not has_raised and offset == 0:  # Only backfill on first page
                with db_service.connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT
                            he.event_id,
                            he.tag_id,
                            COALESCE(tm.tag_name, he.tag_id) AS tag_name,
                            tm.plant,
                            tm.area,
                            tm.equipment,
                            he.event_type,
                            he.time,
                            he.alarm_priority,
                            he.alarm_actual_value,
                            he.alarm_setpoint
                        FROM historian_raw.historian_events he
                        LEFT JOIN historian_meta.tag_master tm ON he.tag_id = tm.tag_id
                        WHERE he.event_id = %s
                        """,
                        (alarm_id,),
                    )
                    row = cursor.fetchone()

                if row:
                    if isinstance(row, dict):
                        raised_record = {
                            'audit_id': None,
                            'event_id': row.get('event_id'),
                            'tag_id': row.get('tag_id'),
                            'tag_name': row.get('tag_name'),
                            'tag_description': None,
                            'plant': row.get('plant'),
                            'area': row.get('area'),
                            'equipment': row.get('equipment'),
                            'event_type': row.get('event_type'),
                            'action_type': 'RAISED',
                            'action_timestamp': row.get('time').isoformat() if row.get('time') else None,
                            'performed_by': 'system',
                            'previous_state': None,
                            'new_state': 'ACTIVE',
                            'lifecycle_state': 'ACTIVE_UNACKED',
                            'alarm_priority': row.get('alarm_priority'),
                            'priority_label': _priority_label(row.get('alarm_priority')),
                            'alarm_actual_value': row.get('alarm_actual_value'),
                            'alarm_setpoint': row.get('alarm_setpoint'),
                            'action_reason': 'Backfilled from historian_events',
                            'action_notes': None,
                            'session_id': None,
                            'client_ip': None,
                            'metadata': None,
                            'created_at': row.get('time').isoformat() if row.get('time') else None,
                            'minutes_since_previous_action': None,
                            'minutes_since_raised': 0,
                            'response_time_seconds': None,
                            'occurrence_id': None,
                            'sequence_number': None,
                            'performed_by_display_name': 'System',
                            'performed_by_user_id': None
                        }
                    else:
                        raised_record = {
                            'audit_id': None,
                            'event_id': row[0],
                            'tag_id': row[1],
                            'tag_name': row[2],
                            'tag_description': None,
                            'plant': row[3],
                            'area': row[4],
                            'equipment': row[5],
                            'event_type': row[6],
                            'action_type': 'RAISED',
                            'action_timestamp': row[7].isoformat() if row[7] else None,
                            'performed_by': 'system',
                            'previous_state': None,
                            'new_state': 'ACTIVE',
                            'lifecycle_state': 'ACTIVE_UNACKED',
                            'alarm_priority': row[8],
                            'priority_label': _priority_label(row[8]),
                            'alarm_actual_value': row[9],
                            'alarm_setpoint': row[10],
                            'action_reason': 'Backfilled from historian_events',
                            'action_notes': None,
                            'session_id': None,
                            'client_ip': None,
                            'metadata': None,
                            'created_at': row[7].isoformat() if row[7] else None,
                            'minutes_since_previous_action': None,
                            'minutes_since_raised': 0,
                            'response_time_seconds': None,
                            'occurrence_id': None,
                            'sequence_number': None,
                            'performed_by_display_name': 'System',
                            'performed_by_user_id': None
                        }

                    audit_records.append(raised_record)
                    # Sort: RAISED first, then all others by timestamp DESC (newest first)
                    raised = [r for r in audit_records if r.get('action_type') == 'RAISED']
                    others = [r for r in audit_records if r.get('action_type') != 'RAISED']
                    others.sort(key=lambda r: r.get('action_timestamp') or '', reverse=True)  # DESC
                    audit_records = raised + others
                    logger.info("Backfilled missing RAISED audit record for alarm %s", alarm_id)
            
            logger.info(f"Retrieved {len(audit_records)} audit records for alarm {alarm_id} (page {page}, total {total_count})")
            
            return jsonify({
                'success': True,
                'alarm_id': alarm_id,
                'alarm_info': alarm_info,
                'audit_trail': audit_records,
                'count': len(audit_records),
                'pagination': {
                    'page': page,
                    'page_size': page_size,
                    'total_count': total_count,
                    'total_pages': (total_count + page_size - 1) // page_size,
                    'has_more': has_more,
                    'sort_order': sort_order
                }
            })
            
        except Exception as e:
            # Rollback transaction on error
            try:
                if db_service and db_service.connection:
                    db_service.connection.rollback()
                    logger.warning("Transaction rolled back after audit trail error")
            except Exception as rollback_error:
                logger.error(f"Failed to rollback transaction: {rollback_error}")
            
            logger.error(f"Error retrieving audit trail for alarm {alarm_id}: {e}")
            return jsonify({
                'success': False,
                'error': str(e),
                'audit_trail': []
            }), 500
            
    except Exception as e:
        # Rollback transaction on error
        try:
            if 'db_service' in locals() and db_service and db_service.connection:
                db_service.connection.rollback()
                logger.warning("Transaction rolled back after outer error")
        except Exception as rollback_error:
            logger.error(f"Failed to rollback transaction: {rollback_error}")
        
        logger.error(f"Error in get_alarm_audit_trail: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e),
            'audit_trail': []
        }), 500


@alarm_bp.route('/audit/tag/<tag_id>', methods=['GET'])
def get_tag_audit_trail(tag_id):
    """
    Get all audit trail records for a specific tag
    Shows all alarm actions for that tag
    """
    try:
        limit = request.args.get('limit', 100, type=int)
        
        db_service = container.historical_service
        if not db_service or not db_service.connection:
            return jsonify({
                'success': False,
                'error': 'Database not available',
                'audit_trail': []
            }), 503
        
        if not HAS_ALARM_AUDIT or not AlarmAuditDAO:
            return jsonify({
                'success': False,
                'error': 'Alarm audit trail module not available',
                'audit_trail': []
            }), 503
        
        try:
            audit_dao = AlarmAuditDAO(db_service)
            audit_records = audit_dao.get_audit_trail_enhanced(tag_id=tag_id, limit=limit)
            
            logger.info(f"Retrieved {len(audit_records)} audit records for tag {tag_id}")
            
            return jsonify({
                'success': True,
                'tag_id': tag_id,
                'audit_trail': audit_records,
                'count': len(audit_records)
            })
            
        except Exception as e:
            logger.error(f"Error retrieving audit trail for tag {tag_id}: {e}")
            return jsonify({
                'success': False,
                'error': str(e),
                'audit_trail': []
            }), 500
            
    except Exception as e:
        logger.error(f"Error in get_tag_audit_trail: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e),
            'audit_trail': []
        }), 500


@alarm_bp.route('/audit/operator/<operator_name>/stats', methods=['GET'])
def get_operator_audit_stats(operator_name):
    """
    Get alarm action statistics for a specific operator
    Includes acknowledgment response times, number of actions, etc.
    """
    try:
        days = request.args.get('days', 7, type=int)
        
        db_service = container.historical_service
        if not db_service or not db_service.connection:
            return jsonify({
                'success': False,
                'error': 'Database not available',
                'stats': {}
            }), 503
        
        if not HAS_ALARM_AUDIT or not AlarmAuditDAO:
            return jsonify({
                'success': False,
                'error': 'Alarm audit trail module not available',
                'stats': {}
            }), 503
        
        try:
            audit_dao = AlarmAuditDAO(db_service)
            stats = audit_dao.get_operator_statistics(performed_by=operator_name, days=days)
            
            logger.info(f"Retrieved operator statistics for {operator_name}")
            
            return jsonify({
                'success': True,
                'operator': operator_name,
                'days': days,
                'stats': stats
            })
            
        except Exception as e:
            logger.error(f"Error retrieving operator stats for {operator_name}: {e}")
            return jsonify({
                'success': False,
                'error': str(e),
                'stats': {}
            }), 500
            
    except Exception as e:
        logger.error(f"Error in get_operator_audit_stats: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e),
            'stats': {}
        }), 500


@alarm_bp.route('/audit/unacknowledged', methods=['GET'])
def get_unacknowledged_alarms_audit():
    """
    Get alarms that were raised but never acknowledged
    Critical for ISA-18.2 compliance monitoring
    """
    try:
        hours = request.args.get('hours', 24, type=int)
        
        db_service = container.historical_service
        if not db_service or not db_service.connection:
            return jsonify({
                'success': False,
                'error': 'Database not available',
                'unacknowledged_alarms': []
            }), 503
        
        if not HAS_ALARM_AUDIT or not AlarmAuditDAO:
            return jsonify({
                'success': False,
                'error': 'Alarm audit trail module not available',
                'unacknowledged_alarms': []
            }), 503
        
        try:
            audit_dao = AlarmAuditDAO(db_service)
            unacked = audit_dao.get_unacknowledged_alarms(hours=hours)
            
            logger.info(f"Found {len(unacked)} unacknowledged alarms in last {hours} hours")
            
            return jsonify({
                'success': True,
                'hours': hours,
                'unacknowledged_alarms': unacked,
                'count': len(unacked)
            })
            
        except Exception as e:
            logger.error(f"Error retrieving unacknowledged alarms: {e}")
            return jsonify({
                'success': False,
                'error': str(e),
                'unacknowledged_alarms': []
            }), 500
            
    except Exception as e:
        logger.error(f"Error in get_unacknowledged_alarms_audit: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e),
            'unacknowledged_alarms': []
        }), 500

@alarm_bp.route('/trips/<int:trip_id>/notes', methods=['POST'])
def add_trip_operator_notes(trip_id):
    """
    Add operator notes to a trip event
    """
    try:
        db_service = container.historical_service
        if not db_service or not db_service.connection:
            return jsonify({
                'success': False,
                'error': 'Database not available'
            }), 503
        
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': 'No data provided'
            }), 400
        
        operator_notes = data.get('notes', '')
        operator = data.get('operator', 'Unknown')
        
        if not operator_notes:
            return jsonify({
                'success': False,
                'error': 'Notes cannot be empty'
            }), 400
        
        # Update trip with operator notes
        update_query = """
            UPDATE historian_raw.trip_event_tracking
            SET operator_notes = %s
            WHERE trip_event_id = %s
        """
        
        cursor = db_service.connection.cursor()
        cursor.execute(update_query, (f"[{operator}]: {operator_notes}", trip_id))
        db_service.connection.commit()
        cursor.close()
        
        logger.info(f"Operator notes added to trip {trip_id} by {operator}")
        
        return jsonify({
            'success': True,
            'message': 'Notes added successfully'
        })
        
    except Exception as e:
        if db_service and db_service.connection:
            db_service.connection.rollback()
        logger.error(f"Error adding operator notes: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@alarm_bp.route('/trips/analytics', methods=['GET'])
def get_trip_analytics():
    """
    Get aggregated trip analytics and statistics
    """
    try:
        days = request.args.get('days', 30, type=int)
        
        db_service = container.historical_service
        if not db_service or not db_service.connection:
            return jsonify({
                'success': False,
                'error': 'Database not available'
            }), 503
        
        # Get overall statistics
        stats_query = """
            SELECT 
                COUNT(*) as total_trips,
                COUNT(*) FILTER (WHERE trip_category = 'EMERGENCY_TRIP') as emergency_trips,
                COUNT(*) FILTER (WHERE trip_category = 'SAFETY_TRIP') as safety_trips,
                COUNT(*) FILTER (WHERE trip_category = 'PROCESS_TRIP') as process_trips,
                COUNT(*) FILTER (WHERE trip_cleared_at IS NULL) as ongoing_trips,
                SUM(production_loss_mw) as total_production_loss_mw,
                AVG(trip_duration_seconds) as avg_duration_seconds,
                MAX(trip_duration_seconds) as max_duration_seconds,
                MIN(trip_duration_seconds) as min_duration_seconds
            FROM historian_raw.trip_event_tracking
            WHERE trip_time > NOW() - make_interval(days => %s)
        """
        
        cursor = db_service.connection.cursor()
        cursor.execute(stats_query, (days,))
        stats_row = cursor.fetchone()
        
        stats = {
            'total_trips': stats_row[0] or 0,
            'emergency_trips': stats_row[1] or 0,
            'safety_trips': stats_row[2] or 0,
            'process_trips': stats_row[3] or 0,
            'ongoing_trips': stats_row[4] or 0,
            'total_production_loss_mw': float(stats_row[5]) if stats_row[5] else 0.0,
            'avg_duration_seconds': float(stats_row[6]) if stats_row[6] else 0.0,
            'max_duration_seconds': stats_row[7] or 0,
            'min_duration_seconds': stats_row[8] or 0
        }
        
        # Get trips by equipment
        equipment_query = """
            SELECT 
                equipment_affected,
                COUNT(*) as trip_count,
                AVG(trip_duration_seconds) as avg_duration,
                SUM(production_loss_mw) as total_loss
            FROM historian_raw.trip_event_tracking
            WHERE trip_time > NOW() - make_interval(days => %s)
            GROUP BY equipment_affected
            ORDER BY trip_count DESC
        """
        
        cursor.execute(equipment_query, (days,))
        equipment_rows = cursor.fetchall()
        
        equipment_stats = []
        for row in equipment_rows:
            equipment_stats.append({
                'equipment': row[0],
                'trip_count': row[1],
                'avg_duration_seconds': float(row[2]) if row[2] else 0.0,
                'total_production_loss_mw': float(row[3]) if row[3] else 0.0
            })
        
        # Get trend data (trips per day)
        trend_query = """
            SELECT 
                DATE(trip_time) as date,
                COUNT(*) as trip_count,
                SUM(production_loss_mw) as production_loss
            FROM historian_raw.trip_event_tracking
            WHERE trip_time > NOW() - make_interval(days => %s)
            GROUP BY DATE(trip_time)
            ORDER BY date DESC
        """
        
        cursor.execute(trend_query, (days,))
        trend_rows = cursor.fetchall()
        
        trends = []
        for row in trend_rows:
            trends.append({
                'date': row[0].isoformat() if row[0] else None,
                'trip_count': row[1],
                'production_loss_mw': float(row[2]) if row[2] else 0.0
            })
        
        cursor.close()
        
        logger.info(f"Retrieved trip analytics for {days} days")
        
        return jsonify({
            'success': True,
            'period_days': days,
            'stats': stats,
            'by_equipment': equipment_stats,
            'trends': trends
        })
        
    except Exception as e:
        logger.error(f"Error fetching trip analytics: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ─────────────────────────────────────────────────────────────────────────────
#  ALARM HISTORY  –  ISA-18.2 full lifecycle, all cleared + active records
# ─────────────────────────────────────────────────────────────────────────────
def _get_db_conn():
    """Return a pooled connection context manager (shared pool, no raw connect)."""
    import db_pool
    return db_pool.get_conn()


@alarm_bp.route('/history', methods=['GET'])
def get_alarm_history():
    """
    Paginated alarm history from historian_raw.historian_events
    joined with alarm_audit_trail for ACK/CLEAR operator details.
    Query params: page, page_size, date_from, date_to, tag_id,
                  search, alarm_level, alarm_state, alarm_priority,
                  sort_by (time|tag_id|alarm_level|alarm_priority), sort_dir (asc|desc)
    """
    try:
        page      = max(1, int(request.args.get('page', 1)))
        page_size = min(200, max(1, int(request.args.get('page_size', 50))))
        offset    = (page - 1) * page_size

        date_from      = request.args.get('date_from')
        date_to        = request.args.get('date_to')
        tag_id_filter  = request.args.get('tag_id')
        search         = request.args.get('search', '').strip()
        alarm_level    = request.args.get('alarm_level', '').strip().upper()
        alarm_state    = request.args.get('alarm_state', '').strip().upper()
        alarm_priority = request.args.get('alarm_priority')

        sort_col_map = {
            'time':           'he."time"',
            'tag_id':         'he.tag_id',
            'alarm_level':    'he.alarm_level',
            'alarm_priority': 'he.alarm_priority',
        }
        sort_by  = sort_col_map.get(request.args.get('sort_by', 'time'), 'he."time"')
        sort_dir = 'ASC' if request.args.get('sort_dir', 'desc').lower() == 'asc' else 'DESC'

        conditions, params = [], []
        if date_from:
            conditions.append('he."time" >= %s'); params.append(date_from)
        if date_to:
            conditions.append('he."time" <= %s'); params.append(date_to)
        if tag_id_filter:
            conditions.append('he.tag_id = %s'); params.append(tag_id_filter)
        if search:
            conditions.append('(he.tag_id ILIKE %s OR he.message ILIKE %s)')
            params.extend([f'%{search}%', f'%{search}%'])
        if alarm_level:
            conditions.append('he.alarm_level = %s'); params.append(alarm_level)
        if alarm_state:
            # Filter on effective state (derived), not raw stale he.alarm_state
            if alarm_state == 'SUPPRESSED':
                conditions.append("""
                    EXISTS(
                        SELECT 1 FROM historian_raw.alarm_audit_trail sup
                        WHERE sup.metadata->>'alarm_key' = (he.tag_id || ':' || he.alarm_level)
                          AND sup.action_type = 'SUPPRESSED'
                          AND (
                              sup.metadata->>'suppress_until' IS NULL
                              OR (sup.metadata->>'suppress_until')::timestamptz > NOW()
                          )
                          AND NOT EXISTS (
                              SELECT 1 FROM historian_raw.alarm_audit_trail uns
                              WHERE uns.action_type = 'UNSUPPRESSED'
                                AND uns.metadata->>'alarm_key' = sup.metadata->>'alarm_key'
                                AND uns.action_timestamp > sup.action_timestamp
                          )
                    )
                """)
            elif alarm_state == 'CLEARED':
                conditions.append("""
                    (he.alarm_state = 'CLEARED' OR EXISTS(
                        SELECT 1 FROM historian_raw.alarm_audit_trail
                        WHERE event_id = he.event_id AND action_type = 'CLEARED'
                    ))
                """)
            elif alarm_state == 'ACTIVE_ACK':
                conditions.append("""
                    (he.alarm_state = 'ACTIVE_ACK' OR (
                        he.alarm_state NOT IN ('RTN_UNACK','CLEARED') AND
                        EXISTS(SELECT 1 FROM historian_raw.alarm_audit_trail
                               WHERE event_id = he.event_id AND action_type = 'ACKNOWLEDGED')
                        AND NOT EXISTS(SELECT 1 FROM historian_raw.alarm_audit_trail
                               WHERE event_id = he.event_id AND action_type = 'CLEARED')
                    ))
                """)
            else:
                conditions.append('he.alarm_state = %s'); params.append(alarm_state)
        if alarm_priority:
            conditions.append('he.alarm_priority = %s'); params.append(int(alarm_priority))

        where_sql = ('WHERE ' + ' AND '.join(conditions)) if conditions else ''

        count_sql = f'SELECT COUNT(*) FROM historian_raw.historian_events he {where_sql}'

        data_sql = f"""
            SELECT
                he.event_id,
                he.tag_id,
                he."time"                    AS raised_at,
                he.event_type,
                -- Effective state: derive from audit trail because C# writes audit but
                -- does NOT update historian_events.alarm_state after creation.
                CASE
                    WHEN sup_at.performed_by IS NOT NULL THEN 'SUPPRESSED'
                    WHEN clr_at.action_timestamp IS NOT NULL THEN 'CLEARED'
                    WHEN ack_at.action_timestamp IS NOT NULL AND he.alarm_state NOT IN ('RTN_UNACK','CLEARED')
                         THEN 'ACTIVE_ACK'
                    ELSE he.alarm_state
                END                          AS alarm_state,
                he.alarm_state               AS raw_alarm_state,
                he.alarm_priority,
                he.alarm_level,
                he.message,
                -- Use values from this event, but fall back to the originating alarm event
                COALESCE(he.alarm_setpoint, orig_event.alarm_setpoint) AS alarm_setpoint,
                COALESCE(he.alarm_actual_value, orig_event.alarm_actual_value) AS alarm_actual_value,
                he.severity,
                he.acknowledged_by,
                he.acknowledged_at,
                he.cleared_by,
                he.cleared_at,
                he.clear_reason,
                he.clear_notes,
                ack_at.performed_by          AS ack_operator,
                ack_at.action_timestamp      AS ack_timestamp,
                ack_at.action_notes          AS ack_notes,
                clr_at.performed_by          AS clear_operator,
                sup_at.performed_by          AS suppressed_by,
                sup_at.action_timestamp      AS suppressed_at,
                sup_at.suppress_until        AS suppress_until,
                clr_at.action_timestamp      AS clear_timestamp,
                clr_at.action_reason         AS clear_reason_audit,
                clr_at.action_notes          AS clear_notes_audit,
                CASE
                    WHEN clr_at.action_timestamp IS NOT NULL
                    THEN ROUND(EXTRACT(EPOCH FROM (clr_at.action_timestamp - he."time"))/60.0, 1)
                    WHEN he.cleared_at IS NOT NULL
                    THEN ROUND(EXTRACT(EPOCH FROM (he.cleared_at - he."time"))/60.0, 1)
                    ELSE ROUND(EXTRACT(EPOCH FROM (NOW() - he."time"))/60.0, 1)
                END AS duration_minutes
            FROM historian_raw.historian_events he
            LEFT JOIN LATERAL (
                SELECT performed_by, action_timestamp, action_notes
                FROM historian_raw.alarm_audit_trail
                WHERE event_id = he.event_id
                  AND action_type = 'ACKNOWLEDGED'
                ORDER BY action_timestamp ASC LIMIT 1
            ) ack_at ON TRUE
            LEFT JOIN LATERAL (
                SELECT performed_by, action_timestamp, action_reason, action_notes
                FROM historian_raw.alarm_audit_trail
                WHERE event_id = he.event_id
                  AND action_type = 'CLEARED'
                ORDER BY action_timestamp ASC LIMIT 1
            ) clr_at ON TRUE
            -- Active suppression check (not yet unsuppressed and not yet expired)
            LEFT JOIN LATERAL (
                SELECT sup.performed_by,
                       sup.action_timestamp,
                       (sup.metadata->>'suppress_until')::timestamptz AS suppress_until
                FROM historian_raw.alarm_audit_trail sup
                WHERE sup.metadata->>'alarm_key' = (he.tag_id || ':' || he.alarm_level)
                  AND sup.action_type = 'SUPPRESSED'
                  AND (
                      sup.metadata->>'suppress_until' IS NULL
                      OR (sup.metadata->>'suppress_until')::timestamptz > NOW()
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM historian_raw.alarm_audit_trail uns
                      WHERE uns.action_type = 'UNSUPPRESSED'
                        AND uns.metadata->>'alarm_key' = sup.metadata->>'alarm_key'
                        AND uns.action_timestamp > sup.action_timestamp
                  )
                ORDER BY sup.action_timestamp DESC LIMIT 1
            ) sup_at ON TRUE
                        -- Lateral subquery to locate the originating alarm event for this tag/level
                        LEFT JOIN LATERAL (
                                SELECT he2.alarm_setpoint, he2.alarm_actual_value, he2.event_id
                                FROM historian_raw.historian_events he2
                                WHERE he2.tag_id = he.tag_id
                                    AND he2."time" <= he."time"
                                    AND (he2.event_type = 'ALARM' OR he2.alarm_state IN ('ACTIVE_UNACK','ACTIVE_ACK'))
                                ORDER BY he2."time" DESC
                                LIMIT 1
                        ) orig_event ON TRUE
            {where_sql}
            ORDER BY {sort_by} {sort_dir}
            LIMIT %s OFFSET %s
        """

        with _get_db_conn() as conn:
            cur = conn.cursor()
            cur.execute(count_sql, params)
            total_count = cur.fetchone()[0]
            cur.execute(data_sql, params + [page_size, offset])
            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()
            cur.close()

        def _fmt(v):
            if v is None: return None
            return v.isoformat() if hasattr(v, 'isoformat') else v

        def _extract_operator_from_message(msg, action):
            """Parse 'Tag:Level <action> by OperatorName' from C# message field."""
            if not msg:
                return None
            import re
            m = re.search(r'(?:acknowledged|cleared)\s+by\s+(.+?)(?:\s+—|\s*$|\s*:)', msg, re.IGNORECASE)
            return m.group(1).strip() if m else None

        records = []
        for row in rows:
            r = dict(zip(cols, row))
            msg = r.get('message', '') or ''
            # Fallback: if audit trail has no operator, parse from C# message field
            ack_by  = r['ack_operator']  or r['acknowledged_by']  or (_extract_operator_from_message(msg, 'ack')   if r['event_type'] == 'ALARM_ACK'     else None)
            clr_by  = r['clear_operator'] or r['cleared_by']       or (_extract_operator_from_message(msg, 'clear') if r['event_type'] == 'ALARM_CLEARED' else None)
            records.append({
                'event_id':           r['event_id'],
                'tag_id':             r['tag_id'],
                'raised_at':          _fmt(r['raised_at']),
                'event_type':         r['event_type'],
                'alarm_state':        r['alarm_state'],
                'alarm_priority':     r['alarm_priority'],
                'alarm_level':        r['alarm_level'],
                'message':            r['message'],
                'alarm_setpoint':     r['alarm_setpoint'],
                'alarm_actual_value': r['alarm_actual_value'],
                'severity':           r['severity'],
                'acknowledged_by':    ack_by,
                'acknowledged_at':    _fmt(r['ack_timestamp'] or r['acknowledged_at']),
                'ack_notes':          r['ack_notes'],
                'cleared_by':         clr_by,
                'cleared_at':         _fmt(r['clear_timestamp'] or r['cleared_at']),
                'clear_reason':       r['clear_reason_audit'] or r['clear_reason'],
                'clear_notes':        r['clear_notes_audit'] or r['clear_notes'],
                'duration_minutes':   float(r['duration_minutes']) if r['duration_minutes'] is not None else None,
                'suppressed_by':      r.get('suppressed_by'),
                'suppressed_at':      _fmt(r.get('suppressed_at')),
                'suppress_until':     _fmt(r.get('suppress_until')),
            })

        return jsonify({
            'success':     True,
            'records':     records,
            'total_count': total_count,
            'page':        page,
            'page_size':   page_size,
            'total_pages': max(1, (total_count + page_size - 1) // page_size),
        })

    except Exception as e:
        logger.error(f"Error fetching alarm history: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@alarm_bp.route('/history/tags', methods=['GET'])
def get_history_tag_list():
    """Distinct tag_ids in historian_events — for filter dropdown."""
    try:
        with _get_db_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT DISTINCT tag_id FROM historian_raw.historian_events ORDER BY tag_id")
            tags = [r[0] for r in cur.fetchall()]
            cur.close()
        return jsonify({'success': True, 'tags': tags})
    except Exception as e:
        logger.error(f"Error fetching tag list: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
#  SUPPRESSION  —  uses alarm_audit_trail (no new table needed)
#  action_type='SUPPRESSED' / 'UNSUPPRESSED'
#  metadata jsonb: { alarm_key, alarm_level, suppress_until (ISO or null=indefinite) }
# ─────────────────────────────────────────────────────────────────────────────

def _is_suppressed_sql():
    """SQL fragment: TRUE if the alarm_key has an active suppression in audit trail."""
    return """
        EXISTS (
            SELECT 1 FROM historian_raw.alarm_audit_trail sup
            WHERE sup.action_type = 'SUPPRESSED'
              AND sup.metadata->>'alarm_key' = aa.alarm_key
              AND (
                  sup.metadata->>'suppress_until' IS NULL
                  OR (sup.metadata->>'suppress_until')::timestamptz > NOW()
              )
              AND NOT EXISTS (
                  SELECT 1 FROM historian_raw.alarm_audit_trail uns
                  WHERE uns.action_type = 'UNSUPPRESSED'
                    AND uns.metadata->>'alarm_key' = sup.metadata->>'alarm_key'
                    AND uns.action_timestamp > sup.action_timestamp
              )
        )
    """


@alarm_bp.route('/suppress/<int:alarm_id>', methods=['POST'])
def suppress_alarm(alarm_id):
    """
    Suppress an active alarm card.
    Body: { duration_hours: 1|4|8|24|null (null=indefinite), reason: str, notes: str }
    Writes action_type='SUPPRESSED' into alarm_audit_trail.
    """
    try:
        token = request.headers.get('Authorization', '')
        username = 'operator'
        user_id = 0
        if token.startswith('Bearer '):
            try:
                u = container.auth_service.decode_token(token.split(' ')[1])
                username = u.get('username', 'operator')
                user_id  = u.get('user_id', 0)
            except Exception:
                pass
        if username == 'operator':
            username = request.args.get('user', 'operator')

        body          = request.get_json(silent=True) or {}
        duration_hours = body.get('duration_hours')   # None = indefinite
        reason         = body.get('reason', '')
        notes          = body.get('notes', '')

        if not reason:
            return jsonify({'success': False, 'error': 'reason is required'}), 400

        db_service = container.historical_service
        if not db_service or not db_service.connection:
            return jsonify({'success': False, 'error': 'Database not available'}), 503

        # Get alarm_key + level from alarm_active
        cur = db_service.connection.cursor()
        cur.execute(
            "SELECT alarm_key, level, tag_id, priority, alarm_state, occurrence_id FROM historian_raw.alarm_active WHERE current_event_id = %s",
            (alarm_id,)
        )
        row = cur.fetchone()
        cur.close()

        if not row:
            return jsonify({'success': False, 'error': 'Alarm not found'}), 404

        # Safe for both dict (RealDictCursor) and tuple (regular cursor)
        # Unpacking a dict gives KEYS not values — must access by key
        if isinstance(row, dict):
            alarm_key    = row['alarm_key']
            alarm_level  = row['level']
            tag_id       = row['tag_id']
            priority     = row.get('priority')
            actual_state = row.get('alarm_state', 'ACTIVE_UNACK')
            occurrence_id = str(row.get('occurrence_id')) if row.get('occurrence_id') else None
        else:
            alarm_key, alarm_level, tag_id, priority, actual_state, occ_id = row
            occurrence_id = str(occ_id) if occ_id else None

        import json as _json
        from datetime import datetime, timezone, timedelta

        # Bug IV — Idempotency: reject if alarm is already actively suppressed
        cur = db_service.connection.cursor()
        cur.execute("""
            SELECT 1 FROM historian_raw.alarm_audit_trail sup
            WHERE sup.action_type = 'SUPPRESSED'
              AND sup.metadata->>'alarm_key' = %s
              AND (
                  sup.metadata->>'suppress_until' IS NULL
                  OR (sup.metadata->>'suppress_until')::timestamptz > NOW()
              )
              AND NOT EXISTS (
                  SELECT 1 FROM historian_raw.alarm_audit_trail uns
                  WHERE uns.action_type = 'UNSUPPRESSED'
                    AND uns.metadata->>'alarm_key' = sup.metadata->>'alarm_key'
                    AND uns.action_timestamp > sup.action_timestamp
              )
            LIMIT 1
        """, (alarm_key,))
        already_suppressed = cur.fetchone() is not None
        cur.close()
        if already_suppressed:
            return jsonify({'success': False, 'error': 'Alarm is already suppressed'}), 409

        suppress_until = None
        if duration_hours is not None:
            suppress_until = (datetime.now(timezone.utc) + timedelta(hours=float(duration_hours))).isoformat()

        metadata = _json.dumps({
            'alarm_key':     alarm_key,
            'alarm_level':   alarm_level,
            'suppress_until': suppress_until,
            'duration_hours': duration_hours,
        })

        cur = db_service.connection.cursor()
        cur.execute("""
            INSERT INTO historian_raw.alarm_audit_trail
                (event_id, tag_id, event_type, action_type, action_timestamp,
                 performed_by, previous_state, new_state, alarm_priority,
                 action_reason, action_notes, client_ip, occurrence_id, metadata)
            VALUES (%s, %s, 'ALARM', 'SUPPRESSED', NOW(),
                    %s, %s, 'SUPPRESSED', %s,
                    %s, %s, %s, %s, %s::jsonb)
        """, (
            alarm_id, tag_id, username, actual_state, priority,
            reason, notes, request.remote_addr, occurrence_id, metadata
        ))
        db_service.connection.commit()
        cur.close()

        logger.info(f"Alarm {alarm_id} (key={alarm_key}) suppressed by {username} until {suppress_until or 'indefinite'}")
        return jsonify({
            'success': True,
            'alarm_id': alarm_id,
            'alarm_key': alarm_key,
            'suppressed_by': username,
            'suppress_until': suppress_until,
            'reason': reason,
        })

    except Exception as e:
        try:
            db_service.connection.rollback()
        except Exception:
            pass
        logger.error(f"Error suppressing alarm {alarm_id}: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@alarm_bp.route('/unsuppress/<int:alarm_id>', methods=['POST'])
def unsuppress_alarm(alarm_id):
    """
    Lift suppression for an alarm card.
    Writes action_type='UNSUPPRESSED' into alarm_audit_trail.
    """
    try:
        token = request.headers.get('Authorization', '')
        username = 'operator'
        if token.startswith('Bearer '):
            try:
                u = container.auth_service.decode_token(token.split(' ')[1])
                username = u.get('username', 'operator')
            except Exception:
                pass
        if username == 'operator':
            username = request.args.get('user', 'operator')

        db_service = container.historical_service
        if not db_service or not db_service.connection:
            return jsonify({'success': False, 'error': 'Database not available'}), 503

        cur = db_service.connection.cursor()
        cur.execute(
            "SELECT alarm_key, level, tag_id, priority, occurrence_id FROM historian_raw.alarm_active WHERE current_event_id = %s",
            (alarm_id,)
        )
        row = cur.fetchone()
        cur.close()

        if not row:
            return jsonify({'success': False, 'error': 'Alarm not found'}), 404

        # Safe for both dict (RealDictCursor) and tuple (regular cursor)
        if isinstance(row, dict):
            alarm_key   = row['alarm_key']
            alarm_level = row['level']
            tag_id      = row['tag_id']
            priority    = row.get('priority')
            occurrence_id = str(row.get('occurrence_id')) if row.get('occurrence_id') else None
        else:
            alarm_key, alarm_level, tag_id, priority, occ_id = row
            occurrence_id = str(occ_id) if occ_id else None

        import json as _json
        metadata = _json.dumps({'alarm_key': alarm_key, 'alarm_level': alarm_level})

        cur = db_service.connection.cursor()
        cur.execute("""
            INSERT INTO historian_raw.alarm_audit_trail
                (event_id, tag_id, event_type, action_type, action_timestamp,
                 performed_by, previous_state, new_state, alarm_priority,
                 action_reason, client_ip, occurrence_id, metadata)
            VALUES (%s, %s, 'ALARM', 'UNSUPPRESSED', NOW(),
                    %s, 'SUPPRESSED', 'ACTIVE_UNACK', %s,
                    'Operator lifted suppression', %s, %s, %s::jsonb)
        """, (alarm_id, tag_id, username, priority, request.remote_addr, occurrence_id, metadata))
        db_service.connection.commit()
        cur.close()

        logger.info(f"Alarm {alarm_id} (key={alarm_key}) unsuppressed by {username}")
        return jsonify({'success': True, 'alarm_id': alarm_id, 'alarm_key': alarm_key, 'unsuppressed_by': username})

    except Exception as e:
        try:
            db_service.connection.rollback()
        except Exception:
            pass
        logger.error(f"Error unsuppressing alarm {alarm_id}: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@alarm_bp.route('/suppressed', methods=['GET'])
def get_suppressed_alarms():
    """
    List all currently suppressed alarms (active suppressions from audit trail).
    """
    try:
        with _get_db_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT DISTINCT ON (sup.metadata->>'alarm_key')
                    sup.audit_id,
                    sup.event_id,
                    sup.tag_id,
                    COALESCE(tm.tag_name, sup.tag_id)   AS tag_name,
                    sup.metadata->>'alarm_key'           AS alarm_key,
                    sup.metadata->>'alarm_level'         AS alarm_level,
                    sup.performed_by                     AS suppressed_by,
                    sup.action_timestamp                 AS suppressed_at,
                    sup.metadata->>'suppress_until'      AS suppress_until,
                    sup.metadata->>'duration_hours'      AS duration_hours,
                    sup.action_reason                    AS reason,
                    sup.action_notes                     AS notes
                FROM historian_raw.alarm_audit_trail sup
                LEFT JOIN historian_meta.tag_master tm ON sup.tag_id = tm.tag_id
                WHERE sup.action_type = 'SUPPRESSED'
                  AND (
                      sup.metadata->>'suppress_until' IS NULL
                      OR (sup.metadata->>'suppress_until')::timestamptz > NOW()
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM historian_raw.alarm_audit_trail uns
                      WHERE uns.action_type = 'UNSUPPRESSED'
                        AND uns.metadata->>'alarm_key' = sup.metadata->>'alarm_key'
                        AND uns.action_timestamp > sup.action_timestamp
                  )
                ORDER BY sup.metadata->>'alarm_key', sup.action_timestamp DESC
            """)
            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()
            cur.close()

        def _fmt(v):
            return v.isoformat() if hasattr(v, 'isoformat') else v

        records = []
        for row in rows:
            r = dict(zip(cols, row))
            r['suppressed_at'] = _fmt(r.get('suppressed_at'))
            records.append(r)

        return jsonify({'success': True, 'suppressed': records, 'count': len(records)})

    except Exception as e:
        logger.error(f"Error fetching suppressed alarms: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e), 'suppressed': []}), 500
