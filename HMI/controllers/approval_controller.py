"""
Approval Controller - API endpoints for critical operation approvals
"""
from flask import Blueprint, request, jsonify
from container import container
from utils.decorators import token_required
import logging

logger = logging.getLogger(__name__)

approval_bp = Blueprint('approval', __name__, url_prefix='/api/approval')


@approval_bp.route('/request', methods=['POST'])
@token_required
def request_approval(current_user):
    """Request approval for a critical operation."""
    try:
        data = request.json
        
        # Validate required fields
        required = ['operation_code', 'target_equipment', 'target_tag', 
                   'target_value', 'current_value', 'justification']
        if not all(field in data for field in required):
            return jsonify({'message': 'Missing required fields'}), 400
        
        result = container.approval_service.request_critical_operation(
            user_id=current_user['user_id'],
            username=current_user['username'],
            operation_code=data['operation_code'],
            target_equipment=data['target_equipment'],
            target_tag=data['target_tag'],
            target_value=data['target_value'],
            current_value=data['current_value'],
            justification=data['justification'],
            priority=data.get('priority', 'normal'),
            ip_address=request.remote_addr,
            session_id=request.headers.get('Authorization', '').replace('Bearer ', '')
        )
        
        if result:
            # Log action
            container.audit_service.log_action(
                user_id=current_user['user_id'],
                username=current_user['username'],
                action_type='request_critical_operation_approval',
                description=f"Requested approval for {data['operation_code']}",
                details={'operation_id': result['operation_id']},
                ip_address=request.remote_addr
            )
            
            return jsonify({
                'message': 'Approval requested',
                **result
            }), 201
        else:
            return jsonify({'message': 'Failed to request approval'}), 500
    except Exception as e:
        logger.error(f"Request approval error: {e}")
        return jsonify({'message': str(e)}), 500


@approval_bp.route('/approve/<operation_id>', methods=['POST'])
@token_required
def approve_operation(current_user, operation_id):
    """Approve a pending critical operation."""
    try:
        result = container.approval_service.approve_operation(
            operation_id=operation_id,
            approver_id=current_user['user_id'],
            approver_username=current_user['username'],
            ip_address=request.remote_addr,
            session_id=request.headers.get('Authorization', '').replace('Bearer ', '')
        )
        
        if result.get('success'):
            # Log approval
            container.audit_service.log_action(
                user_id=current_user['user_id'],
                username=current_user['username'],
                action_type='approve_critical_operation',
                description=f"Approved operation {operation_id}",
                details={'approval_id': result.get('approval_id')},
                ip_address=request.remote_addr
            )
            
            return jsonify(result), 200
        else:
            return jsonify(result), 400
    except Exception as e:
        logger.error(f"Approve operation error: {e}")
        return jsonify({'message': str(e)}), 500


@approval_bp.route('/deny/<operation_id>', methods=['POST'])
@token_required
def deny_operation(current_user, operation_id):
    """Deny a pending critical operation."""
    try:
        data = request.json
        denial_reason = data.get('denial_reason', 'No reason provided')
        
        success = container.approval_service.deny_operation(
            operation_id=operation_id,
            approver_id=current_user['user_id'],
            denial_reason=denial_reason
        )
        
        if success:
            # Log denial
            container.audit_service.log_action(
                user_id=current_user['user_id'],
                username=current_user['username'],
                action_type='deny_critical_operation',
                description=f"Denied operation {operation_id}: {denial_reason}",
                ip_address=request.remote_addr
            )
            
            return jsonify({'message': 'Operation denied'}), 200
        else:
            return jsonify({'message': 'Failed to deny operation'}), 500
    except Exception as e:
        logger.error(f"Deny operation error: {e}")
        return jsonify({'message': str(e)}), 500


@approval_bp.route('/cancel/<operation_id>', methods=['POST'])
@token_required
def cancel_operation(current_user, operation_id):
    """Cancel a pending approval request."""
    try:
        success = container.approval_service.cancel_operation(
            operation_id=operation_id,
            user_id=current_user['user_id']
        )
        
        if success:
            # Log cancellation
            container.audit_service.log_action(
                user_id=current_user['user_id'],
                username=current_user['username'],
                action_type='cancel_approval_request',
                description=f"Cancelled operation {operation_id}",
                ip_address=request.remote_addr
            )
            
            return jsonify({'message': 'Approval request cancelled'}), 200
        else:
            return jsonify({'message': 'Failed to cancel or request not found'}), 404
    except Exception as e:
        logger.error(f"Cancel operation error: {e}")
        return jsonify({'message': str(e)}), 500


@approval_bp.route('/pending', methods=['GET'])
@token_required
def get_pending_approvals(current_user):
    """Get pending approvals for current user."""
    try:
        # Get user role to filter approvals
        user_info = container.rbac_service.get_user_by_id(current_user['user_id'])
        role_id = user_info.get('role_id') if user_info else None
        
        approvals = container.approval_service.get_pending_approvals(
            user_id=current_user['user_id'],
            role_id=role_id
        )
        
        return jsonify({'approvals': approvals, 'count': len(approvals)}), 200
    except Exception as e:
        logger.error(f"Get pending approvals error: {e}")
        return jsonify({'message': str(e)}), 500


@approval_bp.route('/my-requests', methods=['GET'])
@token_required
def get_my_requests(current_user):
    """Get approval requests made by current user."""
    try:
        status = request.args.get('status')
        days = request.args.get('days', default=30, type=int)
        
        requests = container.approval_service.get_user_approval_requests(
            user_id=current_user['user_id'],
            status=status,
            days=days
        )
        
        return jsonify({'requests': requests, 'count': len(requests)}), 200
    except Exception as e:
        logger.error(f"Get my requests error: {e}")
        return jsonify({'message': str(e)}), 500


@approval_bp.route('/operation/<operation_id>', methods=['GET'])
@token_required
def get_approval_details(current_user, operation_id):
    """Get approval details by operation ID."""
    try:
        approval = container.approval_service.get_approval_by_operation_id(operation_id)
        
        if not approval:
            return jsonify({'message': 'Approval not found'}), 404
        
        return jsonify({'approval': approval}), 200
    except Exception as e:
        logger.error(f"Get approval details error: {e}")
        return jsonify({'message': str(e)}), 500


@approval_bp.route('/execute/<operation_id>', methods=['POST'])
@token_required
def mark_executed(current_user, operation_id):
    """Mark an approved operation as executed."""
    try:
        data = request.json
        execution_result = data.get('execution_result', {})
        execution_success = data.get('execution_success', True)
        
        success = container.approval_service.mark_operation_executed(
            operation_id=operation_id,
            execution_result=execution_result,
            execution_success=execution_success
        )
        
        if success:
            # Log execution
            container.audit_service.log_action(
                user_id=current_user['user_id'],
                username=current_user['username'],
                action_type='execute_critical_operation',
                description=f"Executed operation {operation_id}",
                details=execution_result,
                ip_address=request.remote_addr
            )
            
            return jsonify({'message': 'Operation marked as executed'}), 200
        else:
            return jsonify({'message': 'Failed to mark operation'}), 500
    except Exception as e:
        logger.error(f"Mark executed error: {e}")
        return jsonify({'message': str(e)}), 500


@approval_bp.route('/critical-operations', methods=['GET'])
@token_required
def get_critical_operations(current_user):
    """Get all defined critical operations."""
    try:
        operations = container.approval_service.get_critical_operations()
        return jsonify({'operations': operations}), 200
    except Exception as e:
        logger.error(f"Get critical operations error: {e}")
        return jsonify({'message': str(e)}), 500


@approval_bp.route('/check/<operation_code>', methods=['GET'])
@token_required
def check_if_critical(current_user, operation_code):
    """Check if an operation requires approval."""
    try:
        operation = container.approval_service.check_if_operation_is_critical(operation_code)
        
        if operation:
            return jsonify({
                'is_critical': True,
                'operation': operation
            }), 200
        else:
            return jsonify({'is_critical': False}), 200
    except Exception as e:
        logger.error(f"Check if critical error: {e}")
        return jsonify({'message': str(e)}), 500


@approval_bp.route('/statistics', methods=['GET'])
@token_required
def get_statistics(current_user):
    """Get approval statistics (admin only)."""
    user_info = container.rbac_service.get_user_by_id(current_user['user_id'])
    if not user_info or not user_info.get('is_admin'):
        return jsonify({'message': 'Unauthorized'}), 403
    
    try:
        days = request.args.get('days', default=30, type=int)
        stats = container.approval_service.get_approval_statistics(days=days)
        return jsonify({'statistics': stats}), 200
    except Exception as e:
        logger.error(f"Get approval statistics error: {e}")
        return jsonify({'message': str(e)}), 500


@approval_bp.route('/expire-old', methods=['POST'])
@token_required
def expire_old(current_user):
    """Expire old pending approvals (admin only)."""
    user_info = container.rbac_service.get_user_by_id(current_user['user_id'])
    if not user_info or not user_info.get('is_admin'):
        return jsonify({'message': 'Unauthorized'}), 403
    
    try:
        count = container.approval_service.expire_old_approvals()
        
        # Log action
        container.audit_service.log_action(
            user_id=current_user['user_id'],
            username=current_user['username'],
            action_type='expire_old_approvals',
            description=f"Expired {count} old approvals",
            ip_address=request.remote_addr
        )
        
        return jsonify({
            'message': f'Expired {count} old approvals',
            'count': count
        }), 200
    except Exception as e:
        logger.error(f"Expire old approvals error: {e}")
        return jsonify({'message': str(e)}), 500
