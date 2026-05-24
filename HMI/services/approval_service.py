"""
Approval Service - Two-person rule workflow
Handles critical operation approval requests and workflow.
"""

import logging
import psycopg2
import db_pool
from psycopg2.extras import RealDictCursor, Json

logger = logging.getLogger(__name__)


class ApprovalService:
    def __init__(self, db_config):
        self.db_config = db_config  # kept for reference only
    
    def _get_conn(self):
        return db_pool.get_conn()
    
    # ==================== Request Approval ====================
    
    def request_critical_operation(self, user_id, username, operation_code,
                                   target_equipment, target_tag, target_value,
                                   current_value, justification, priority='normal',
                                   ip_address=None, session_id=None):
        """
        Request approval for a critical operation.
        
        Args:
            user_id: Requesting user ID
            username: Requesting username
            operation_code: Code of critical operation
            target_equipment: Equipment ID
            target_tag: Tag ID
            target_value: Proposed new value
            current_value: Current value
            justification: Reason for operation
            priority: 'low', 'normal', 'high', 'urgent'
            ip_address: Client IP
            session_id: Session ID
        
        Returns:
            dict: Approval request info {approval_id, operation_id, expires_at, timeout_minutes}
        """
        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT * FROM historian_meta.request_critical_operation_approval(
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                        )
                    """, (
                        operation_code,
                        user_id,
                        target_equipment,
                        target_tag,
                        Json(target_value) if isinstance(target_value, (dict, list)) else target_value,
                        Json(current_value) if isinstance(current_value, (dict, list)) else current_value,
                        justification,
                        priority,
                        ip_address,
                        session_id
                    ))
                    result = cur.fetchone()
                    conn.commit()
                    
                    if result:
                        return dict(result)
                    return None
        except Exception as e:
            logger.error(f"Request critical operation error: {e}")
            raise
    
    # ==================== Approve/Deny ====================
    
    def approve_operation(self, operation_id, approver_id, approver_username,
                         ip_address=None, session_id=None):
        """
        Approve a pending critical operation.
        
        Returns:
            dict: {success: bool, message: str, approval_id: int}
        """
        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT * FROM historian_meta.approve_critical_operation(
                            %s, %s, %s, %s
                        )
                    """, (operation_id, approver_id, ip_address, session_id))
                    result = cur.fetchone()
                    conn.commit()
                    
                    return dict(result) if result else {
                        'success': False,
                        'message': 'Approval failed'
                    }
        except Exception as e:
            logger.error(f"Approve operation error: {e}")
            return {'success': False, 'message': str(e)}
    
    def deny_operation(self, operation_id, approver_id, denial_reason):
        """Deny a pending critical operation."""
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT historian_meta.deny_critical_operation(%s, %s, %s)
                    """, (operation_id, approver_id, denial_reason))
                    result = cur.fetchone()[0]
                    conn.commit()
                    return result
        except Exception as e:
            logger.error(f"Deny operation error: {e}")
            return False
    
    def cancel_operation(self, operation_id, user_id):
        """Cancel a pending operation request."""
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    # Only requester can cancel
                    cur.execute("""
                        UPDATE historian_meta.operation_approvals
                        SET status = 'cancelled'
                        WHERE operation_id = %s
                        AND requested_by = %s
                        AND status = 'pending'
                    """, (operation_id, user_id))
                    conn.commit()
                    return cur.rowcount > 0
        except Exception as e:
            logger.error(f"Cancel operation error: {e}")
            return False
    
    # ==================== Execute Tracking ====================
    
    def mark_operation_executed(self, operation_id, execution_result, 
                               execution_success=True):
        """Mark an approved operation as executed."""
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT historian_meta.mark_operation_executed(%s, %s, %s)
                    """, (
                        operation_id,
                        Json(execution_result) if isinstance(execution_result, (dict, list)) else execution_result,
                        execution_success
                    ))
                    result = cur.fetchone()[0]
                    conn.commit()
                    return result
        except Exception as e:
            logger.error(f"Mark operation executed error: {e}")
            return False
    
    # ==================== Query Approvals ====================
    
    def get_pending_approvals(self, user_id=None, role_id=None):
        """
        Get pending approvals (optionally filtered for specific user/role).
        
        Args:
            user_id: If provided, only returns approvals this user can approve
            role_id: If provided, filters by required approver role
        
        Returns:
            list: Pending approval requests
        """
        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    if user_id:
                        cur.execute("""
                            SELECT * FROM historian_meta.user_pending_approvals
                            WHERE user_id = %s
                            ORDER BY priority DESC, requested_at ASC
                        """, (user_id,))
                    else:
                        cur.execute("""
                            SELECT * FROM historian_meta.pending_approvals
                            ORDER BY priority DESC, requested_at ASC
                        """)
                    return cur.fetchall()
        except Exception as e:
            logger.error(f"Get pending approvals error: {e}")
            return []
    
    def get_user_approval_requests(self, user_id, status=None, days=30):
        """Get approval requests made by a user."""
        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    query = """
                        SELECT oa.*, co.operation_name, co.severity,
                               au.username as approver_username
                        FROM historian_meta.operation_approvals oa
                        LEFT JOIN historian_meta.critical_operations co ON oa.critical_operation_id = co.id
                        LEFT JOIN historian_meta.users au ON oa.approver_id = au.id
                        WHERE oa.requested_by = %s
                        AND oa.requested_at >= CURRENT_TIMESTAMP - %s * INTERVAL '1 day'
                    """
                    params = [user_id, days]
                    
                    if status:
                        query += " AND oa.status = %s"
                        params.append(status)
                    
                    query += " ORDER BY oa.requested_at DESC"
                    
                    cur.execute(query, params)
                    return cur.fetchall()
        except Exception as e:
            logger.error(f"Get user approval requests error: {e}")
            return []
    
    def get_approval_by_operation_id(self, operation_id):
        """Get approval details by operation ID."""
        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT oa.*, co.operation_name, co.severity,
                               ru.username as requester_username,
                               au.username as approver_username
                        FROM historian_meta.operation_approvals oa
                        LEFT JOIN historian_meta.critical_operations co ON oa.critical_operation_id = co.id
                        JOIN historian_meta.users ru ON oa.requested_by = ru.id
                        LEFT JOIN historian_meta.users au ON oa.approver_id = au.id
                        WHERE oa.operation_id = %s
                    """, (operation_id,))
                    return cur.fetchone()
        except Exception as e:
            logger.error(f"Get approval by operation ID error: {e}")
            return None
    
    # ==================== Cleanup ====================
    
    def expire_old_approvals(self):
        """Expire old pending approvals that have timed out."""
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT historian_meta.expire_old_approvals()
                    """)
                    count = cur.fetchone()[0]
                    conn.commit()
                    return count
        except Exception as e:
            logger.error(f"Expire old approvals error: {e}")
            return 0
    
    # ==================== Statistics ====================
    
    def get_approval_statistics(self, days=30):
        """Get approval statistics."""
        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT * FROM historian_meta.approval_statistics
                        WHERE approval_date >= CURRENT_DATE - %s * INTERVAL '1 day'
                        ORDER BY approval_date DESC
                    """, (days,))
                    return cur.fetchall()
        except Exception as e:
            logger.error(f"Get approval statistics error: {e}")
            return []
    
    # ==================== Critical Operations ====================
    
    def get_critical_operations(self):
        """Get all defined critical operations."""
        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT * FROM historian_meta.critical_operations
                        WHERE is_active = TRUE
                        ORDER BY severity DESC, operation_name
                    """)
                    return cur.fetchall()
        except Exception as e:
            logger.error(f"Get critical operations error: {e}")
            return []
    
    def check_if_operation_is_critical(self, operation_code):
        """Check if an operation requires approval."""
        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT * FROM historian_meta.critical_operations
                        WHERE operation_code = %s AND is_active = TRUE
                    """, (operation_code,))
                    return cur.fetchone()
        except Exception as e:
            logger.error(f"Check if operation critical error: {e}")
            return None
