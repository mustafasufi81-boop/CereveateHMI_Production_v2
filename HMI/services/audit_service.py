"""
Audit Service - Comprehensive Audit Logging
Handles logging of all user actions for security, compliance, and troubleshooting.
"""

import logging
import psycopg2
import db_pool
from psycopg2.extras import RealDictCursor
import json
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class AuditService:
    def __init__(self, db_config):
        self.db_config = db_config  # kept for reference only
    
    def _get_conn(self):
        return db_pool.get_conn()
    
    # ==================== Core Audit Logging ====================
    
    def log_action(self, user_id, username, action_type, action_category,
                   target_entity=None, target_id=None, target_name=None,
                   old_value=None, new_value=None, success=True,
                   failure_reason=None, ip_address=None, session_id=None,
                   user_agent=None, additional_data=None):
        """
        Log a user action to the audit trail.
        
        Args:
            user_id: User ID performing the action
            username: Username (denormalized for immutability)
            action_type: Type of action (LOGIN, SETPOINT_CHANGE, etc.)
            action_category: Category (authentication, control, alarm, admin, data)
            target_entity: Entity type being affected (tag, equipment, user, role, alarm)
            target_id: ID of the target entity
            target_name: Name of the target entity
            old_value: Previous value (for changes)
            new_value: New value (for changes)
            success: Whether the action succeeded
            failure_reason: Reason for failure if applicable
            ip_address: Client IP address
            session_id: Session ID
            user_agent: User agent string
            additional_data: Additional context as JSON
        
        Returns:
            Audit log ID
        """
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT historian_meta.log_user_action(
                            %s::INTEGER,
                            %s::VARCHAR,
                            %s::VARCHAR,
                            %s::VARCHAR,
                            %s::VARCHAR,
                            %s::VARCHAR,
                            %s::VARCHAR,
                            %s::TEXT,
                            %s::TEXT,
                            %s::BOOLEAN,
                            %s::TEXT,
                            %s::VARCHAR,
                            %s::VARCHAR,
                            %s::TEXT,
                            %s::JSONB
                        )
                    """, (
                        user_id, username, action_type, action_category,
                        target_entity, target_id, target_name,
                        old_value, new_value, success, failure_reason,
                        ip_address, session_id, user_agent,
                        json.dumps(additional_data) if additional_data else None
                    ))
                    audit_id = cur.fetchone()[0]
                    conn.commit()
                    return audit_id
        except Exception as e:
            logger.error(f"Audit logging error: {e}")
            # Don't fail the main operation if audit fails
            return None
    
    # ==================== Convenience Methods ====================
    
    def log_login(self, user_id, username, success=True, ip_address=None, 
                  session_id=None, user_agent=None, failure_reason=None):
        """Log a login attempt."""
        return self.log_action(
            user_id, username,
            'LOGIN' if success else 'LOGIN_FAILED',
            'authentication',
            success=success,
            failure_reason=failure_reason,
            ip_address=ip_address,
            session_id=session_id,
            user_agent=user_agent
        )
    
    def log_logout(self, user_id, username, forced=False, session_id=None):
        """Log a logout."""
        return self.log_action(
            user_id, username,
            'LOGOUT_FORCED' if forced else 'LOGOUT',
            'authentication',
            session_id=session_id
        )
    
    def log_setpoint_change(self, user_id, username, tag_id, tag_name, 
                           old_value, new_value, ip_address=None, session_id=None):
        """Log a setpoint change."""
        return self.log_action(
            user_id, username,
            'SETPOINT_CHANGE',
            'control',
            target_entity='tag',
            target_id=tag_id,
            target_name=tag_name,
            old_value=str(old_value),
            new_value=str(new_value),
            ip_address=ip_address,
            session_id=session_id
        )
    
    def log_equipment_operation(self, user_id, username, equipment_id, 
                               equipment_name, operation, success=True,
                               failure_reason=None, ip_address=None, session_id=None):
        """Log an equipment operation (start, stop, mode change)."""
        action_map = {
            'start': 'EQUIPMENT_START',
            'stop': 'EQUIPMENT_STOP',
            'emergency_stop': 'EMERGENCY_STOP',
            'mode_change': 'MODE_CHANGE'
        }
        return self.log_action(
            user_id, username,
            action_map.get(operation, 'COMMAND_EXECUTE'),
            'control',
            target_entity='equipment',
            target_id=equipment_id,
            target_name=equipment_name,
            success=success,
            failure_reason=failure_reason,
            ip_address=ip_address,
            session_id=session_id
        )
    
    def log_alarm_action(self, user_id, username, alarm_id, action, 
                        ip_address=None, session_id=None, additional_data=None):
        """Log an alarm action (acknowledge, clear, silence, etc.)."""
        action_map = {
            'acknowledge': 'ALARM_ACKNOWLEDGE',
            'clear': 'ALARM_CLEARED',
            'silence': 'ALARM_SILENCE',
            'shelve': 'ALARM_SHELVE',
            'unshelve': 'ALARM_UNSHELVE'
        }
        return self.log_action(
            user_id, username,
            action_map.get(action, 'ALARM_ACKNOWLEDGE'),
            'alarm',
            target_entity='alarm',
            target_id=alarm_id,
            ip_address=ip_address,
            session_id=session_id,
            additional_data=additional_data
        )
    
    def log_admin_action(self, user_id, username, action, target_user_id=None,
                        target_username=None, additional_data=None, 
                        ip_address=None, session_id=None):
        """Log an administrative action."""
        return self.log_action(
            user_id, username,
            action,
            'admin',
            target_entity='user',
            target_id=str(target_user_id) if target_user_id else None,
            target_name=target_username,
            additional_data=additional_data,
            ip_address=ip_address,
            session_id=session_id
        )
    
    # ==================== Audit Query Methods ====================
    
    def get_user_audit_trail(self, user_id, start_date=None, end_date=None, 
                            action_types=None, limit=100):
        """Get audit trail for a specific user."""
        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    query = """
                        SELECT id, timestamp, action_type, action_category,
                               target_entity, target_name, old_value, new_value,
                               success, ip_address
                        FROM historian_meta.user_actions_audit
                        WHERE user_id = %s
                    """
                    params = [user_id]
                    
                    if start_date:
                        query += " AND timestamp >= %s"
                        params.append(start_date)
                    
                    if end_date:
                        query += " AND timestamp <= %s"
                        params.append(end_date)
                    
                    if action_types:
                        query += " AND action_type = ANY(%s)"
                        params.append(action_types)
                    
                    query += " ORDER BY timestamp DESC LIMIT %s"
                    params.append(limit)
                    
                    cur.execute(query, params)
                    return cur.fetchall()
        except Exception as e:
            logger.error(f"Get audit trail error: {e}")
            return []
    
    def get_recent_critical_actions(self, hours=24, limit=100):
        """Get recent critical actions."""
        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT * FROM historian_meta.recent_critical_actions
                        LIMIT %s
                    """, (limit,))
                    return cur.fetchall()
        except Exception as e:
            logger.error(f"Get critical actions error: {e}")
            return []
    
    def get_audit_statistics(self, days=30):
        """Get audit statistics for the last N days."""
        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT * FROM historian_meta.audit_statistics
                        WHERE audit_date >= CURRENT_DATE - %s * INTERVAL '1 day'
                        ORDER BY audit_date DESC
                    """, (days,))
                    return cur.fetchall()
        except Exception as e:
            logger.error(f"Get audit statistics error: {e}")
            return []
    
    def get_user_activity_summary(self, user_id=None):
        """Get user activity summary."""
        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    if user_id:
                        cur.execute("""
                            SELECT * FROM historian_meta.user_activity_summary
                            WHERE user_id = %s
                        """, (user_id,))
                    else:
                        cur.execute("SELECT * FROM historian_meta.user_activity_summary")
                    return cur.fetchall()
        except Exception as e:
            logger.error(f"Get activity summary error: {e}")
            return []
    
    def search_audit_logs(self, search_term=None, action_category=None,
                         start_date=None, end_date=None, success_only=None,
                         limit=100, offset=0, user_id=None, username=None, action_type=None, days=None):
        """Search audit logs with filters."""
        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    query = """
                        SELECT 
                            id, 
                            user_id,
                            username, 
                            action_type, 
                            action_category,
                            target_entity, 
                            target_name, 
                            old_value, 
                            new_value,
                            success,
                            failure_reason,
                            ip_address,
                            session_id as session_token,
                            timestamp as created_at,
                            additional_data as details,
                            CASE 
                                WHEN target_name IS NOT NULL THEN 
                                    action_type || ' on ' || target_name
                                WHEN old_value IS NOT NULL AND new_value IS NOT NULL THEN
                                    action_type || ': ' || old_value || ' → ' || new_value
                                ELSE 
                                    action_type
                            END as description
                        FROM historian_meta.user_actions_audit
                        WHERE 1=1
                    """
                    params = []
                    
                    if search_term:
                        query += """ AND (
                            username ILIKE %s OR
                            action_type ILIKE %s OR
                            target_name ILIKE %s OR
                            new_value ILIKE %s
                        )"""
                        search_pattern = f'%{search_term}%'
                        params.extend([search_pattern] * 4)
                    
                    if user_id:
                        query += " AND user_id = %s"
                        params.append(user_id)
                    
                    if username:
                        query += " AND username ILIKE %s"
                        params.append(f'%{username}%')
                    
                    if action_type:
                        query += " AND action_type = %s"
                        params.append(action_type)
                    
                    if action_category:
                        query += " AND action_category = %s"
                        params.append(action_category)
                    
                    if days:
                        query += " AND timestamp >= CURRENT_TIMESTAMP - %s * INTERVAL '1 day'"
                        params.append(days)
                    
                    if start_date:
                        query += " AND timestamp >= %s"
                        params.append(start_date)
                    
                    if end_date:
                        query += " AND timestamp <= %s"
                        params.append(end_date)
                    
                    if success_only is not None:
                        query += " AND success = %s"
                        params.append(success_only)
                    
                    query += " ORDER BY timestamp DESC LIMIT %s OFFSET %s"
                    params.extend([limit, offset])
                    
                    cur.execute(query, params)
                    return cur.fetchall()
        except Exception as e:
            logger.error(f"Search audit logs error: {e}")
            return []
    
    def get_failed_actions(self, days=7, limit=100):
        """Get failed actions in the last N days."""
        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT id, timestamp, username, action_type, 
                               target_entity, target_name, failure_reason, ip_address
                        FROM historian_meta.user_actions_audit
                        WHERE success = FALSE
                        AND timestamp >= CURRENT_TIMESTAMP - %s * INTERVAL '1 day'
                        ORDER BY timestamp DESC
                        LIMIT %s
                    """, (days, limit))
                    return cur.fetchall()
        except Exception as e:
            logger.error(f"Get failed actions error: {e}")
            return []
    
    # ==================== Audit Action Types ====================
    
    def get_action_types(self, category=None):
        """Get supported audit action types."""
        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    if category:
                        cur.execute("""
                            SELECT * FROM historian_meta.audit_action_types
                            WHERE action_category = %s AND is_active = TRUE
                            ORDER BY action_type
                        """, (category,))
                    else:
                        cur.execute("""
                            SELECT * FROM historian_meta.audit_action_types
                            WHERE is_active = TRUE
                            ORDER BY action_category, action_type
                        """)
                    return cur.fetchall()
        except Exception as e:
            logger.error(f"Get action types error: {e}")
            return []
