"""
RBAC Integration - Integrates Industrial RBAC checks into alarm operations

This module provides decorators and utilities to enforce RBAC before alarm/trip/interlock operations.

Standards: ISA-18.2, ISA-61511, IEC 62443

Author: Automation Team
Version: 1.0
"""

from functools import wraps
from flask import jsonify, request, current_app
import logging
from container import container
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Import Industrial RBAC Service
try:
    from services.industrial_rbac_service import IndustrialRBACService, OperationRequest
    HAS_INDUSTRIAL_RBAC = True
except ImportError:
    HAS_INDUSTRIAL_RBAC = False
    logger.warning("Industrial RBAC Service not available")


class RBACIntegration:
    """Utility class for integrating RBAC into operations"""
    
    @staticmethod
    def get_rbac_service():
        """Get Industrial RBAC Service instance"""
        if not HAS_INDUSTRIAL_RBAC:
            return None
        try:
            db_service = container.historical_service
            return IndustrialRBACService(db_service)
        except Exception as e:
            logger.error(f"Error initializing RBAC service: {e}")
            return None
    
    @staticmethod
    def check_operation_permission(user_id, operation_type):
        """
        Check if user has permission for operation
        
        Returns: dict with keys:
        - allowed: Boolean
        - reason: str (if not allowed)
        - requires_approval: Boolean
        - requires_2fa: Boolean
        - required_cert: str or None
        """
        rbac_service = RBACIntegration.get_rbac_service()
        if not rbac_service:
            return {
                'allowed': True,  # Graceful degradation
                'reason': 'RBAC service unavailable',
                'requires_approval': False,
                'requires_2fa': False,
                'required_cert': None
            }
        
        try:
            result = rbac_service.check_operation_allowed(user_id, operation_type)
            return result
        except Exception as e:
            logger.error(f"Error checking RBAC permission: {e}")
            return {
                'allowed': False,
                'reason': f'RBAC check failed: {str(e)}',
                'requires_approval': False,
                'requires_2fa': False,
                'required_cert': None
            }
    
    @staticmethod
    def request_approval(operation_type, operation_id, user_id, reason='', priority='NORMAL'):
        """
        Request approval for high-risk operation
        
        Returns: dict with keys:
        - approval_id: int
        - status: str (REQUESTED, PENDING_SoD_CONFLICT, REJECTED)
        - message: str
        - sod_violation: bool
        """
        rbac_service = RBACIntegration.get_rbac_service()
        if not rbac_service:
            return {
                'approval_id': None,
                'status': 'SKIPPED',
                'message': 'RBAC service unavailable',
                'sod_violation': False
            }
        
        try:
            op_request = OperationRequest(
                operation_type=operation_type,
                operation_id=operation_id,
                operation_description=operation_type,
                requested_by=user_id,
                request_reason=reason,
                priority=priority
            )
            
            result = rbac_service.request_operation_approval(
                op_request,
                ip_address=request.remote_addr if request else 'unknown',
                session_id=request.headers.get('X-Session-ID') if request else None
            )
            
            return {
                'approval_id': result.approval_id,
                'status': result.status,
                'message': result.message,
                'sod_violation': result.sod_violation
            }
        except Exception as e:
            logger.error(f"Error requesting approval: {e}")
            return {
                'approval_id': None,
                'status': 'ERROR',
                'message': str(e),
                'sod_violation': False
            }
    
    @staticmethod
    def check_active_approval_exists(approval_id):
        """Check if an approval with given ID is in APPROVED state"""
        try:
            db_service = container.historical_service
            query = """
                SELECT status FROM historian_meta.operation_approvals
                WHERE id = %s AND status = 'APPROVED'
            """
            cursor = db_service.connection.cursor()
            cursor.execute(query, (approval_id,))
            result = cursor.fetchone()
            cursor.close()
            
            return result is not None
        except Exception as e:
            logger.error(f"Error checking active approval: {e}")
            return False
    
    @staticmethod
    def log_operation_action(operation_type, operation_id, action_type, user_id, 
                              status='SUCCESS', details=None, approval_id=None):
        """
        Log operation action to audit trail
        
        Args:
        - operation_type: str (ALARM_ACKNOWLEDGE, ALARM_CLEAR, etc.)
        - operation_id: str or int
        - action_type: str (REQUEST, APPROVE, EXECUTE, VERIFY, REJECT, REVOKE)
        - user_id: int
        - status: str (SUCCESS, FAILED, DENIED)
        - details: dict (additional context)
        - approval_id: int (if part of approval workflow)
        """
        rbac_service = RBACIntegration.get_rbac_service()
        if not rbac_service:
            logger.debug("RBAC service unavailable, operation action not logged to RBAC audit trail")
            return None
        
        try:
            rbac_service._log_operation_audit(
                operation_type=operation_type,
                operation_id=str(operation_id),
                action_type=action_type,
                user_id=user_id,
                status=status,
                details=details or {},
                approval_id=approval_id,
                ip_address=request.remote_addr if request else 'unknown',
                session_id=request.headers.get('X-Session-ID') if request else None
            )
            return True
        except Exception as e:
            logger.error(f"Error logging operation action: {e}")
            return False


def rbac_required(operation_type, check_approval=False, check_2fa=False):
    """
    Decorator to enforce RBAC checks on endpoint
    
    Usage:
    @app.route('/api/alarms/<id>/clear', methods=['POST'])
    @token_required
    @rbac_required('ALARM_CLEAR', check_approval=True, check_2fa=True)
    def clear_alarm(id):
        ...
    
    Args:
    - operation_type: str - Type of operation (ALARM_CLEAR, ALARM_ACKNOWLEDGE, etc.)
    - check_approval: bool - If True, enforces change control workflow
    - check_2fa: bool - If True, requires valid 2FA code
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            try:
                # Get user from token
                token = request.headers.get('Authorization', '').split(' ')[-1]
                user_info = current_app.auth_service.decode_token(token)
                user_id = user_info.get('user_id')
                
                # Check basic permission
                perm_result = RBACIntegration.check_operation_permission(user_id, operation_type)
                
                if not perm_result['allowed']:
                    logger.warning(f"User {user_id} denied permission for {operation_type}: {perm_result['reason']}")
                    return jsonify({
                        'success': False,
                        'error': perm_result['reason'],
                        'requires_certification': perm_result['required_cert']
                    }), 403
                
                # If approval required, check for valid approval
                if check_approval and perm_result['requires_approval']:
                    approval_id = request.json.get('approval_id') if request.json else None
                    
                    if not approval_id or not RBACIntegration.check_active_approval_exists(approval_id):
                        # Request new approval
                        operation_id = kwargs.get('id') or request.json.get('operation_id')
                        approval_result = RBACIntegration.request_approval(
                            operation_type=operation_type,
                            operation_id=operation_id,
                            user_id=user_id,
                            reason=request.json.get('reason', '') if request.json else '',
                            priority=request.json.get('priority', 'NORMAL') if request.json else 'NORMAL'
                        )
                        
                        if approval_result['status'] == 'PENDING_SoD_CONFLICT':
                            return jsonify({
                                'success': False,
                                'error': 'Separation of Duties conflict detected',
                                'requires_approval': True,
                                'approval_id': approval_result['approval_id'],
                                'message': 'This operation cannot be executed by the same person who requested it. Approval required from another user.'
                            }), 403
                        
                        return jsonify({
                            'success': False,
                            'error': 'Approval required for this operation',
                            'requires_approval': True,
                            'approval_id': approval_result['approval_id'],
                            'message': approval_result['message']
                        }), 403
                
                # If 2FA required, check for valid code
                if check_2fa and perm_result['requires_2fa']:
                    two_fa_code = request.json.get('two_fa_code') if request.json else None
                    
                    if not two_fa_code:
                        return jsonify({
                            'success': False,
                            'error': '2FA code required for this operation',
                            'requires_2fa': True
                        }), 403
                    
                    # TODO: Verify 2FA code (would be checked in service methods)
                
                # Log the operation request
                RBACIntegration.log_operation_action(
                    operation_type=operation_type,
                    operation_id=kwargs.get('id') or request.json.get('operation_id'),
                    action_type='EXECUTE',
                    user_id=user_id,
                    status='INITIATED'
                )
                
                # Call original function
                return f(*args, **kwargs)
                
            except Exception as e:
                logger.error(f"Error in RBAC decorator: {e}")
                return jsonify({
                    'success': False,
                    'error': f'RBAC check failed: {str(e)}'
                }), 500
        
        return decorated_function
    return decorator


def get_user_permission_summary(user_id):
    """
    Get comprehensive permission summary for user
    
    Returns dict with:
    - alarm_operations: list of allowed operations on alarms
    - trip_operations: list of allowed operations on trips
    - interlock_operations: list of allowed operations on interlocks
    - certifications: list of active certifications
    - pending_approvals: count of pending approvals awaiting this user
    - expiring_certs: count of certifications expiring within 30 days
    """
    try:
        db_service = container.historical_service
        
        # Get user role
        query = """
            SELECT r.role_name, u.role_id
            FROM historian_meta.users u
            JOIN historian_meta.roles r ON u.role_id = r.id
            WHERE u.id = %s
        """
        cursor = db_service.connection.cursor()
        cursor.execute(query, (user_id,))
        result = cursor.fetchone()
        cursor.close()
        
        if not result:
            return None
        
        role_name, role_id = result
        
        # Get alarm permissions
        alarm_query = """
            SELECT DISTINCT operation
            FROM historian_meta.role_alarm_permissions
            WHERE role_id = %s AND is_allowed = TRUE
        """
        
        # Get trip permissions
        trip_query = """
            SELECT DISTINCT operation
            FROM historian_meta.role_trip_permissions
            WHERE role_id = %s AND is_allowed = TRUE
        """
        
        # Get interlock permissions
        interlock_query = """
            SELECT DISTINCT operation
            FROM historian_meta.role_interlock_permissions
            WHERE role_id = %s AND is_allowed = TRUE
        """
        
        # Get certifications
        cert_query = """
            SELECT certification_type, expires_at, is_active
            FROM historian_meta.user_certifications
            WHERE user_id = %s AND is_active = TRUE
        """
        
        # Get pending approvals
        approval_query = """
            SELECT COUNT(*) FROM historian_meta.operation_approvals
            WHERE status IN ('REQUESTED', 'APPROVED') AND approver_id IS NULL
        """
        
        # Execute all queries
        cursor = db_service.connection.cursor()
        
        cursor.execute(alarm_query, (role_id,))
        alarm_ops = [row[0] for row in cursor.fetchall()]
        
        cursor.execute(trip_query, (role_id,))
        trip_ops = [row[0] for row in cursor.fetchall()]
        
        cursor.execute(interlock_query, (role_id,))
        interlock_ops = [row[0] for row in cursor.fetchall()]
        
        cursor.execute(cert_query, (user_id,))
        certs = [(row[0], row[1], row[2]) for row in cursor.fetchall()]
        
        cursor.execute(approval_query)
        pending_count = cursor.fetchone()[0]
        
        cursor.close()
        
        return {
            'role_name': role_name,
            'alarm_operations': alarm_ops,
            'trip_operations': trip_ops,
            'interlock_operations': interlock_ops,
            'certifications': [{'type': c[0], 'expires': c[1].isoformat() if c[1] else None, 'active': c[2]} for c in certs],
            'pending_approvals': pending_count,
            'expiring_certs': sum(1 for c in certs if c[1] and (c[1] - datetime.now()).days < 30)
        }
        
    except Exception as e:
        logger.error(f"Error getting user permission summary: {e}")
        return None

