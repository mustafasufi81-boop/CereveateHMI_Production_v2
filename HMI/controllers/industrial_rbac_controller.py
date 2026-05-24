"""
Industrial RBAC Controller
Integrates Industrial RBAC with alarm, trip, and interlock operations

Standards: ISA-18.2, ISA-61511, IEC 62443

Author: Automation Team
Version: 1.0
"""

from flask import Blueprint, jsonify, request
from container import container
from utils.decorators import token_required
import logging
import sys
import os

logger = logging.getLogger(__name__)

# Import Industrial RBAC Service
try:
    from services.industrial_rbac_service import IndustrialRBACService, OperationRequest
    HAS_INDUSTRIAL_RBAC = True
    logger.info("✅ Industrial RBAC Service imported successfully")
except ImportError as e:
    logger.warning(f"Could not import Industrial RBAC Service: {e}")
    HAS_INDUSTRIAL_RBAC = False

industrial_rbac_bp = Blueprint('industrial_rbac', __name__, url_prefix='/api/rbac')


# =========================================================================
# CERTIFICATION MANAGEMENT ENDPOINTS
# =========================================================================

@industrial_rbac_bp.route('/certifications/user/<int:user_id>', methods=['GET'])
@token_required
def get_user_certifications(user_id):
    """Get user's certifications and their status"""
    try:
        if not HAS_INDUSTRIAL_RBAC:
            return jsonify({'success': False, 'error': 'RBAC service not available'}), 503
        
        db_service = container.historical_service
        rbac_service = IndustrialRBACService(db_service)
        
        # Get all certifications for user
        query = """
            SELECT id, certification_type, certified_at, expires_at,
                   is_active, EXTRACT(DAY FROM expires_at - NOW())::INTEGER as days_remaining
            FROM historian_meta.user_certifications
            WHERE user_id = %s
            ORDER BY certification_type
        """
        
        cursor = db_service.connection.cursor()
        cursor.execute(query, (user_id,))
        results = cursor.fetchall()
        cursor.close()
        
        certifications = []
        for row in results:
            certifications.append({
                'id': row[0],
                'type': row[1],
                'certified_at': row[2].isoformat() if row[2] else None,
                'expires_at': row[3].isoformat() if row[3] else None,
                'is_active': row[4],
                'days_remaining': row[5],
                'status': 'CRITICAL' if row[5] and row[5] < 7 else 'WARNING' if row[5] and row[5] < 30 else 'OK'
            })
        
        return jsonify({
            'success': True,
            'user_id': user_id,
            'certifications': certifications,
            'count': len(certifications)
        })
        
    except Exception as e:
        logger.error(f"Error getting user certifications: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@industrial_rbac_bp.route('/certifications/grant', methods=['POST'])
@token_required
def grant_certification():
    """Grant certification to user (admin only)"""
    try:
        if not HAS_INDUSTRIAL_RBAC:
            return jsonify({'success': False, 'error': 'RBAC service not available'}), 503
        
        # Verify admin
        token = request.headers.get('Authorization', '').split(' ')[-1]
        user_info = container.auth_service.decode_token(token)
        user_id = user_info.get('user_id')
        
        # Check if admin
        is_admin_query = "SELECT is_admin FROM historian_meta.roles WHERE id = (SELECT role_id FROM historian_meta.users WHERE id = %s)"
        db_service = container.historical_service
        cursor = db_service.connection.cursor()
        cursor.execute(is_admin_query, (user_id,))
        result = cursor.fetchone()
        cursor.close()
        
        if not result or not result[0]:
            return jsonify({'success': False, 'error': 'Admin permission required'}), 403
        
        # Get request data
        data = request.json or {}
        target_user_id = data.get('user_id')
        certification_type = data.get('certification_type')
        validity_months = data.get('validity_months', 12)
        training_url = data.get('training_record_url')
        test_score = data.get('test_score')
        notes = data.get('notes')
        
        if not target_user_id or not certification_type:
            return jsonify({'success': False, 'error': 'Missing required fields'}), 400
        
        # Grant certification
        rbac_service = IndustrialRBACService(db_service)
        cert_id = rbac_service.grant_certification(
            user_id=target_user_id,
            certification_type=certification_type,
            certified_by=user_id,
            validity_months=validity_months,
            training_record_url=training_url,
            test_score=test_score,
            notes=notes
        )
        
        return jsonify({
            'success': True,
            'certification_id': cert_id,
            'message': 'Certification granted successfully'
        })
        
    except Exception as e:
        logger.error(f"Error granting certification: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# =========================================================================
# OPERATION APPROVAL ENDPOINTS
# =========================================================================

@industrial_rbac_bp.route('/approvals/pending', methods=['GET'])
@token_required
def get_pending_approvals():
    """Get pending approval requests"""
    try:
        db_service = container.historical_service
        
        query = """
            SELECT id, operation_type, operation_id, requested_by,
                   (SELECT username FROM historian_meta.users WHERE id = requested_by),
                   requested_at, status, priority, execution_deadline
            FROM historian_meta.operation_approvals
            WHERE status IN ('REQUESTED', 'APPROVED', 'SCHEDULED')
            ORDER BY priority DESC, created_at ASC
            LIMIT 100
        """
        
        cursor = db_service.connection.cursor()
        cursor.execute(query)
        results = cursor.fetchall()
        cursor.close()
        
        approvals = []
        for row in results:
            approvals.append({
                'id': row[0],
                'operation_type': row[1],
                'operation_id': row[2],
                'requested_by': row[3],
                'requested_by_name': row[4],
                'requested_at': row[5].isoformat() if row[5] else None,
                'status': row[6],
                'priority': row[7],
                'execution_deadline': row[8].isoformat() if row[8] else None
            })
        
        return jsonify({
            'success': True,
            'approvals': approvals,
            'count': len(approvals)
        })
        
    except Exception as e:
        logger.error(f"Error getting pending approvals: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@industrial_rbac_bp.route('/approvals/request', methods=['POST'])
@token_required
def request_approval():
    """Request approval for high-risk operation"""
    try:
        if not HAS_INDUSTRIAL_RBAC:
            return jsonify({'success': False, 'error': 'RBAC service not available'}), 503
        
        # Get authenticated user
        token = request.headers.get('Authorization', '').split(' ')[-1]
        user_info = container.auth_service.decode_token(token)
        user_id = user_info.get('user_id')
        
        # Get request data
        data = request.json or {}
        operation_type = data.get('operation_type')
        operation_id = data.get('operation_id')
        reason = data.get('reason', '')
        priority = data.get('priority', 'NORMAL')
        
        if not operation_type or not operation_id:
            return jsonify({'success': False, 'error': 'Missing operation details'}), 400
        
        # Create approval request
        op_request = OperationRequest(
            operation_type=operation_type,
            operation_id=operation_id,
            operation_description=operation_type,
            requested_by=user_id,
            request_reason=reason,
            priority=priority
        )
        
        db_service = container.historical_service
        rbac_service = IndustrialRBACService(db_service)
        
        result = rbac_service.request_operation_approval(
            op_request,
            ip_address=request.remote_addr,
            session_id=request.headers.get('X-Session-ID')
        )
        
        return jsonify({
            'success': result.status == 'REQUESTED',
            'approval_id': result.approval_id,
            'status': result.status,
            'message': result.message,
            'sod_violation': result.sod_violation
        }), 201 if result.status == 'REQUESTED' else 400
        
    except Exception as e:
        logger.error(f"Error requesting approval: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@industrial_rbac_bp.route('/approvals/<int:approval_id>/approve', methods=['POST'])
@token_required
def approve_operation(approval_id):
    """Approve pending operation (supervisor/admin only)"""
    try:
        if not HAS_INDUSTRIAL_RBAC:
            return jsonify({'success': False, 'error': 'RBAC service not available'}), 503
        
        # Get authenticated user
        token = request.headers.get('Authorization', '').split(' ')[-1]
        user_info = container.auth_service.decode_token(token)
        approver_id = user_info.get('user_id')
        
        # Get request data
        data = request.json or {}
        approval_reason = data.get('reason', '')
        
        # Create RBAC service
        db_service = container.historical_service
        rbac_service = IndustrialRBACService(db_service)
        
        # Approve operation
        result = rbac_service.approve_operation(
            approval_id=approval_id,
            approved_by=approver_id,
            approval_reason=approval_reason,
            requires_2fa=data.get('requires_2fa', False),
            ip_address=request.remote_addr,
            session_id=request.headers.get('X-Session-ID')
        )
        
        return jsonify({
            'success': result.status == 'APPROVED',
            'approval_id': result.approval_id,
            'status': result.status,
            'approval_code': result.approval_code,
            'message': result.message,
            'sod_violation': result.sod_violation
        })
        
    except Exception as e:
        logger.error(f"Error approving operation: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@industrial_rbac_bp.route('/approvals/<int:approval_id>/execute', methods=['POST'])
@token_required
def execute_operation(approval_id):
    """Execute approved operation"""
    try:
        if not HAS_INDUSTRIAL_RBAC:
            return jsonify({'success': False, 'error': 'RBAC service not available'}), 503
        
        # Get authenticated user
        token = request.headers.get('Authorization', '').split(' ')[-1]
        user_info = container.auth_service.decode_token(token)
        executor_id = user_info.get('user_id')
        
        # Get request data
        data = request.json or {}
        approval_code = data.get('approval_code')
        
        # Create RBAC service
        db_service = container.historical_service
        rbac_service = IndustrialRBACService(db_service)
        
        # Execute operation
        success = rbac_service.execute_approved_operation(
            approval_id=approval_id,
            executed_by=executor_id,
            approval_code=approval_code,
            ip_address=request.remote_addr,
            session_id=request.headers.get('X-Session-ID')
        )
        
        return jsonify({
            'success': success,
            'approval_id': approval_id,
            'message': 'Operation executed successfully' if success else 'Failed to execute operation'
        })
        
    except Exception as e:
        logger.error(f"Error executing operation: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# =========================================================================
# RBAC COMPLIANCE REPORTING ENDPOINTS
# =========================================================================

@industrial_rbac_bp.route('/compliance/expiring-certifications', methods=['GET'])
@token_required
def get_expiring_certifications():
    """Get list of expiring certifications"""
    try:
        db_service = container.historical_service
        
        # Use the view we created
        query = """
            SELECT user_id, username, role_name, certification_type,
                   expires_at, days_remaining, status
            FROM historian_meta.expiring_certifications_view
            ORDER BY days_remaining ASC
            LIMIT 100
        """
        
        cursor = db_service.connection.cursor()
        cursor.execute(query)
        results = cursor.fetchall()
        cursor.close()
        
        certifications = []
        for row in results:
            certifications.append({
                'user_id': row[0],
                'username': row[1],
                'role_name': row[2],
                'type': row[3],
                'expires_at': row[4].isoformat() if row[4] else None,
                'days_remaining': row[5],
                'status': row[6]
            })
        
        return jsonify({
            'success': True,
            'certifications': certifications,
            'count': len(certifications)
        })
        
    except Exception as e:
        logger.error(f"Error getting expiring certifications: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@industrial_rbac_bp.route('/compliance/audit-trail', methods=['GET'])
@token_required
def get_audit_trail():
    """Get operation audit trail for compliance"""
    try:
        db_service = container.historical_service
        rbac_service = IndustrialRBACService(db_service)
        
        # Get query parameters
        operation_type = request.args.get('operation_type')
        operation_id = request.args.get('operation_id')
        user_id = request.args.get('user_id', type=int)
        days = request.args.get('days', 30, type=int)
        limit = request.args.get('limit', 100, type=int)
        
        # Get audit trail
        records = rbac_service.get_operation_audit_trail(
            operation_type=operation_type,
            operation_id=operation_id,
            user_id=user_id,
            days=days,
            limit=limit
        )
        
        return jsonify({
            'success': True,
            'records': records,
            'count': len(records)
        })
        
    except Exception as e:
        logger.error(f"Error getting audit trail: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# =========================================================================
# PERMISSION CHECKING ENDPOINTS (For UI)
# =========================================================================

@industrial_rbac_bp.route('/check-permission', methods=['POST'])
@token_required
def check_permission():
    """Check if user has permission for operation"""
    try:
        if not HAS_INDUSTRIAL_RBAC:
            return jsonify({'success': False, 'error': 'RBAC service not available'}), 503
        
        # Get authenticated user
        token = request.headers.get('Authorization', '').split(' ')[-1]
        user_info = container.auth_service.decode_token(token)
        user_id = user_info.get('user_id')
        
        # Get request data
        data = request.json or {}
        operation_type = data.get('operation_type')
        
        if not operation_type:
            return jsonify({'success': False, 'error': 'Missing operation_type'}), 400
        
        # Check permission
        db_service = container.historical_service
        rbac_service = IndustrialRBACService(db_service)
        
        result = rbac_service.check_operation_allowed(user_id, operation_type)
        
        return jsonify({
            'success': True,
            'operation_allowed': result['operation_allowed'],
            'reason': result['reason'],
            'requires_approval': result['requires_approval'],
            'requires_2fa': result['requires_2fa'],
            'required_certification': result['required_certification']
        })
        
    except Exception as e:
        logger.error(f"Error checking permission: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

