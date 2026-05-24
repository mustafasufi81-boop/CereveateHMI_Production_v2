"""
Temporary Permission Service - Time-based access control
Handles temporary and time-limited permissions.
"""

import logging
import psycopg2
import db_pool
from psycopg2.extras import RealDictCursor, Json

logger = logging.getLogger(__name__)


class TemporaryPermissionService:
    def __init__(self, db_config):
        self.db_config = db_config  # kept for reference only
    
    def _get_conn(self):
        return db_pool.get_conn()
    
    # ==================== Grant/Revoke Permissions ====================
    
    def grant_permission(self, user_id, granted_by, permission_type,
                        permission_target, permission_action, duration_hours,
                        reason, additional_data=None):
        """
        Grant a temporary permission to a user.
        
        Args:
            user_id: User receiving permission
            granted_by: User granting permission (must be admin/supervisor)
            permission_type: 'tag', 'equipment', 'alarm', 'role_temporary'
            permission_target: Target ID (tag_id, equipment_id, etc.)
            permission_action: Action allowed ('view', 'write', 'start', 'stop', etc.)
            duration_hours: How long permission lasts
            reason: Justification for temporary access
            additional_data: Optional additional context
        
        Returns:
            int: Permission ID
        """
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT historian_meta.grant_temporary_permission(
                            %s, %s, %s, %s, %s, %s, %s, %s
                        )
                    """, (
                        user_id, granted_by, permission_type, permission_target,
                        permission_action, duration_hours, reason,
                        Json(additional_data) if additional_data else None
                    ))
                    permission_id = cur.fetchone()[0]
                    conn.commit()
                    return permission_id
        except Exception as e:
            logger.error(f"Grant temporary permission error: {e}")
            raise
    
    def revoke_permission(self, permission_id, revoked_by, revoke_reason):
        """Revoke a temporary permission before it expires."""
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT historian_meta.revoke_temporary_permission(
                            %s, %s, %s
                        )
                    """, (permission_id, revoked_by, revoke_reason))
                    result = cur.fetchone()[0]
                    conn.commit()
                    return result
        except Exception as e:
            logger.error(f"Revoke temporary permission error: {e}")
            return False
    
    def extend_permission(self, permission_id, extended_by, additional_hours, reason):
        """Extend a temporary permission."""
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT historian_meta.extend_temporary_permission(
                            %s, %s, %s, %s
                        )
                    """, (permission_id, extended_by, additional_hours, reason))
                    new_expires_at = cur.fetchone()[0]
                    conn.commit()
                    return new_expires_at
        except Exception as e:
            logger.error(f"Extend temporary permission error: {e}")
            raise
    
    # ==================== Check Permissions ====================
    
    def check_permission(self, user_id, permission_type, permission_target, 
                        permission_action):
        """Check if user has a specific temporary permission."""
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT historian_meta.check_temporary_permission(
                            %s, %s, %s, %s
                        )
                    """, (user_id, permission_type, permission_target, permission_action))
                    return cur.fetchone()[0]
        except Exception as e:
            logger.error(f"Check temporary permission error: {e}")
            return False
    
    # ==================== Query Permissions ====================
    
    def get_active_permissions(self, user_id=None):
        """Get active temporary permissions."""
        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    if user_id:
                        cur.execute("""
                            SELECT * FROM historian_meta.active_temporary_permissions
                            WHERE user_id = %s
                            ORDER BY expires_at ASC
                        """, (user_id,))
                    else:
                        cur.execute("""
                            SELECT * FROM historian_meta.active_temporary_permissions
                            ORDER BY expires_at ASC
                        """)
                    return cur.fetchall()
        except Exception as e:
            logger.error(f"Get active permissions error: {e}")
            return []
    
    def get_user_permission_summary(self, user_id=None):
        """Get comprehensive permission summary for user(s)."""
        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    if user_id:
                        cur.execute("""
                            SELECT * FROM historian_meta.user_permission_summary
                            WHERE user_id = %s
                        """, (user_id,))
                    else:
                        cur.execute("""
                            SELECT * FROM historian_meta.user_permission_summary
                            ORDER BY username
                        """)
                    return cur.fetchall()
        except Exception as e:
            logger.error(f"Get permission summary error: {e}")
            return []
    
    def get_expiring_soon(self, hours=4):
        """Get permissions expiring soon."""
        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT * FROM historian_meta.active_temporary_permissions
                        WHERE status = 'expiring_soon'
                        AND hours_until_expiry <= %s
                        ORDER BY expires_at ASC
                    """, (hours,))
                    return cur.fetchall()
        except Exception as e:
            logger.error(f"Get expiring permissions error: {e}")
            return []
    
    # ==================== Permission Templates ====================
    
    def get_templates(self, template_type=None):
        """Get permission templates."""
        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    if template_type:
                        cur.execute("""
                            SELECT * FROM historian_meta.permission_templates
                            WHERE template_type = %s AND is_active = TRUE
                            ORDER BY template_name
                        """, (template_type,))
                    else:
                        cur.execute("""
                            SELECT * FROM historian_meta.permission_templates
                            WHERE is_active = TRUE
                            ORDER BY template_type, template_name
                        """)
                    return cur.fetchall()
        except Exception as e:
            logger.error(f"Get templates error: {e}")
            return []
    
    def apply_template(self, user_id, template_code, granted_by, 
                      duration_hours=None, reason=None):
        """
        Apply a permission template to a user.
        
        Returns:
            dict: {permission_ids: [int], expires_at: timestamp}
        """
        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT * FROM historian_meta.apply_permission_template(
                            %s, %s, %s, %s, %s
                        )
                    """, (user_id, template_code, granted_by, duration_hours, reason))
                    result = cur.fetchone()
                    conn.commit()
                    return dict(result) if result else None
        except Exception as e:
            logger.error(f"Apply template error: {e}")
            raise
    
    # ==================== Access Requests ====================
    
    def create_access_request(self, user_id, requested_by, template_id,
                             requested_start, requested_end, justification,
                             business_need=None):
        """Create a temporary access request (may require approval)."""
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO historian_meta.temporary_access_requests (
                            user_id, requested_by, template_id,
                            requested_start, requested_end,
                            justification, business_need
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                    """, (
                        user_id, requested_by, template_id,
                        requested_start, requested_end,
                        justification, business_need
                    ))
                    request_id = cur.fetchone()[0]
                    conn.commit()
                    return request_id
        except Exception as e:
            logger.error(f"Create access request error: {e}")
            raise
    
    def get_pending_access_requests(self):
        """Get pending temporary access requests."""
        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT tar.*, u.username, pt.template_name,
                               ru.username as requested_by_username
                        FROM historian_meta.temporary_access_requests tar
                        JOIN historian_meta.users u ON tar.user_id = u.id
                        JOIN historian_meta.users ru ON tar.requested_by = ru.id
                        LEFT JOIN historian_meta.permission_templates pt ON tar.template_id = pt.id
                        WHERE tar.status = 'pending'
                        ORDER BY tar.requested_at DESC
                    """)
                    return cur.fetchall()
        except Exception as e:
            logger.error(f"Get pending access requests error: {e}")
            return []
    
    def approve_access_request(self, request_id, approved_by):
        """Approve a temporary access request and grant permissions."""
        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    # Get request details
                    cur.execute("""
                        SELECT * FROM historian_meta.temporary_access_requests
                        WHERE id = %s AND status = 'pending'
                    """, (request_id,))
                    request = cur.fetchone()
                    
                    if not request:
                        return False
                    
                    # Update request status
                    cur.execute("""
                        UPDATE historian_meta.temporary_access_requests
                        SET status = 'approved',
                            approved_by = %s,
                            approved_at = CURRENT_TIMESTAMP,
                            activated_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                    """, (approved_by, request_id))
                    
                    # Apply template if specified
                    if request['template_id']:
                        duration_hours = request['requested_duration_hours']
                        cur.execute("""
                            SELECT * FROM historian_meta.apply_permission_template(
                                %s, 
                                (SELECT template_code FROM historian_meta.permission_templates WHERE id = %s),
                                %s, %s, %s
                            )
                        """, (
                            request['user_id'],
                            request['template_id'],
                            approved_by,
                            duration_hours,
                            request['justification']
                        ))
                        result = cur.fetchone()
                        
                        # Update with granted permission IDs
                        if result:
                            cur.execute("""
                                UPDATE historian_meta.temporary_access_requests
                                SET granted_permissions_ids = %s
                                WHERE id = %s
                            """, (result['permission_ids'], request_id))
                    
                    conn.commit()
                    return True
        except Exception as e:
            logger.error(f"Approve access request error: {e}")
            raise
    
    def deny_access_request(self, request_id, denied_by, denial_reason):
        """Deny a temporary access request."""
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE historian_meta.temporary_access_requests
                        SET status = 'denied',
                            denied_by = %s,
                            denied_at = CURRENT_TIMESTAMP,
                            denial_reason = %s
                        WHERE id = %s AND status = 'pending'
                    """, (denied_by, denial_reason, request_id))
                    conn.commit()
                    return cur.rowcount > 0
        except Exception as e:
            logger.error(f"Deny access request error: {e}")
            return False
    
    # ==================== Cleanup ====================
    
    def cleanup_expired(self):
        """Cleanup expired permissions."""
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT historian_meta.cleanup_expired_permissions()
                    """)
                    count = cur.fetchone()[0]
                    conn.commit()
                    return count
        except Exception as e:
            logger.error(f"Cleanup expired permissions error: {e}")
            return 0
    
    def check_expiry_notifications(self):
        """Check for permissions needing expiry notifications."""
        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT * FROM historian_meta.check_permission_expiry_notifications()
                    """)
                    return cur.fetchall()
        except Exception as e:
            logger.error(f"Check expiry notifications error: {e}")
            return []
