"""
Equipment Permission Controller - API endpoints for equipment-level permissions
"""
from flask import Blueprint, request, jsonify
from container import container
from utils.decorators import token_required
import logging

logger = logging.getLogger(__name__)

equipment_bp = Blueprint('equipment', __name__, url_prefix='/api/equipment')


@equipment_bp.route('/permission/check', methods=['POST'])
@token_required
def check_permission(current_user):
    """Check if user has permission for equipment action."""
    try:
        data = request.json
        equipment_id = data.get('equipment_id')
        permission_level = data.get('permission_level')
        
        if not equipment_id or not permission_level:
            return jsonify({'message': 'Missing parameters'}), 400
        
        has_permission = container.equipment_permission_service.check_permission(
            user_id=current_user['user_id'],
            equipment_id=equipment_id,
            permission_level=permission_level
        )
        
        return jsonify({'has_permission': has_permission}), 200
    except Exception as e:
        logger.error(f"Check permission error: {e}")
        return jsonify({'message': str(e)}), 500


@equipment_bp.route('/permissions/user', methods=['GET'])
@token_required
def get_user_permissions(current_user):
    """Get equipment permissions for current user."""
    try:
        equipment_type = request.args.get('equipment_type')
        include_hierarchy = request.args.get('include_hierarchy', default='true').lower() == 'true'
        
        permissions = container.equipment_permission_service.get_user_equipment_permissions(
            user_id=current_user['user_id'],
            equipment_type=equipment_type,
            include_hierarchy=include_hierarchy
        )
        
        return jsonify({'permissions': permissions}), 200
    except Exception as e:
        logger.error(f"Get user permissions error: {e}")
        return jsonify({'message': str(e)}), 500


@equipment_bp.route('/permissions/role/<int:role_id>', methods=['GET'])
@token_required
def get_role_permissions(current_user, role_id):
    """Get equipment permissions for a role (admin only)."""
    user_info = container.rbac_service.get_user_by_id(current_user['user_id'])
    if not user_info or not user_info.get('is_admin'):
        return jsonify({'message': 'Unauthorized'}), 403
    
    try:
        permissions = container.equipment_permission_service.get_role_equipment_permissions(role_id)
        return jsonify({'permissions': permissions}), 200
    except Exception as e:
        logger.error(f"Get role permissions error: {e}")
        return jsonify({'message': str(e)}), 500


@equipment_bp.route('/permissions/role/<int:role_id>', methods=['POST'])
@token_required
def add_role_permission(current_user, role_id):
    """Add equipment permission to role (admin only)."""
    user_info = container.rbac_service.get_user_by_id(current_user['user_id'])
    if not user_info or not user_info.get('is_admin'):
        return jsonify({'message': 'Unauthorized'}), 403
    
    try:
        data = request.json
        equipment_id = data.get('equipment_id')
        permission_level = data.get('permission_level')
        
        success = container.equipment_permission_service.add_role_permission(
            role_id=role_id,
            equipment_id=equipment_id,
            permission_level=permission_level
        )
        
        if success:
            # Log action
            container.audit_service.log_permission_change(
                user_id=current_user['user_id'],
                username=current_user['username'],
                action=f"Added equipment permission: role={role_id}, equipment={equipment_id}, level={permission_level}",
                target_user_id=None,
                ip_address=request.remote_addr
            )
            return jsonify({'message': 'Permission added'}), 200
        else:
            return jsonify({'message': 'Failed to add permission'}), 500
    except Exception as e:
        logger.error(f"Add role permission error: {e}")
        return jsonify({'message': str(e)}), 500


@equipment_bp.route('/permissions/role/<int:role_id>', methods=['DELETE'])
@token_required
def remove_role_permission(current_user, role_id):
    """Remove equipment permission from role (admin only)."""
    user_info = container.rbac_service.get_user_by_id(current_user['user_id'])
    if not user_info or not user_info.get('is_admin'):
        return jsonify({'message': 'Unauthorized'}), 403
    
    try:
        data = request.json
        equipment_id = data.get('equipment_id')
        permission_level = data.get('permission_level')
        
        success = container.equipment_permission_service.remove_role_permission(
            role_id=role_id,
            equipment_id=equipment_id,
            permission_level=permission_level
        )
        
        if success:
            # Log action
            container.audit_service.log_permission_change(
                user_id=current_user['user_id'],
                username=current_user['username'],
                action=f"Removed equipment permission: role={role_id}, equipment={equipment_id}, level={permission_level}",
                target_user_id=None,
                ip_address=request.remote_addr
            )
            return jsonify({'message': 'Permission removed'}), 200
        else:
            return jsonify({'message': 'Failed to remove permission'}), 500
    except Exception as e:
        logger.error(f"Remove role permission error: {e}")
        return jsonify({'message': str(e)}), 500


@equipment_bp.route('/registry', methods=['GET'])
@token_required
def get_equipment_registry(current_user):
    """Get equipment registry."""
    try:
        equipment_type = request.args.get('equipment_type')
        parent_id = request.args.get('parent_id', type=int)
        
        equipment = container.equipment_permission_service.get_equipment_registry(
            equipment_type=equipment_type,
            parent_id=parent_id
        )
        
        return jsonify({'equipment': equipment}), 200
    except Exception as e:
        logger.error(f"Get equipment registry error: {e}")
        return jsonify({'message': str(e)}), 500


@equipment_bp.route('/registry', methods=['POST'])
@token_required
def register_equipment(current_user):
    """Register new equipment (admin only)."""
    user_info = container.rbac_service.get_user_by_id(current_user['user_id'])
    if not user_info or not user_info.get('is_admin'):
        return jsonify({'message': 'Unauthorized'}), 403
    
    try:
        data = request.json
        equipment_id = container.equipment_permission_service.register_equipment(
            equipment_code=data['equipment_code'],
            equipment_name=data['equipment_name'],
            equipment_type=data['equipment_type'],
            parent_equipment_id=data.get('parent_equipment_id'),
            description=data.get('description'),
            metadata=data.get('metadata')
        )
        
        # Log action
        container.audit_service.log_action(
            user_id=current_user['user_id'],
            username=current_user['username'],
            action_type='register_equipment',
            description=f"Registered equipment: {data['equipment_name']} ({data['equipment_code']})",
            ip_address=request.remote_addr
        )
        
        return jsonify({
            'message': 'Equipment registered',
            'equipment_id': equipment_id
        }), 201
    except Exception as e:
        logger.error(f"Register equipment error: {e}")
        return jsonify({'message': str(e)}), 500


@equipment_bp.route('/types', methods=['GET'])
@token_required
def get_equipment_types(current_user):
    """Get all equipment types."""
    try:
        types = container.equipment_permission_service.get_equipment_types()
        return jsonify({'equipment_types': types}), 200
    except Exception as e:
        logger.error(f"Get equipment types error: {e}")
        return jsonify({'message': str(e)}), 500


@equipment_bp.route('/permissions/summary', methods=['GET'])
@token_required
def get_permissions_summary(current_user):
    """Get equipment permissions summary (admin only)."""
    user_info = container.rbac_service.get_user_by_id(current_user['user_id'])
    if not user_info or not user_info.get('is_admin'):
        return jsonify({'message': 'Unauthorized'}), 403
    
    try:
        summary = container.equipment_permission_service.get_equipment_permissions_summary()
        return jsonify({'summary': summary}), 200
    except Exception as e:
        logger.error(f"Get permissions summary error: {e}")
        return jsonify({'message': str(e)}), 500
