"""
Admin Controller - Admin-only endpoints for user and role management
"""

from flask import Blueprint, request, jsonify
from container import container
from utils.decorators import token_required

admin_bp = Blueprint('admin', __name__, url_prefix='/api/admin')


def admin_required(f):
    """Decorator to require admin role"""
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'message': 'Token required'}), 401
        
        try:
            token = token.split(' ')[1]
            data = container.auth_service.decode_token(token)
            if not data or data.get('partial'):
                return jsonify({'message': 'Invalid token'}), 401
            
            user_id = data['user_id']
            if not container.rbac_service.is_user_admin(user_id):
                return jsonify({'message': 'Admin access required'}), 403
            
            request.current_user = data
            return f(*args, **kwargs)
        except Exception as e:
            return jsonify({'message': str(e)}), 401
    return decorated


# ==================== User Management ====================

@admin_bp.route('/users', methods=['GET'])
@admin_required
def get_users():
    """Get all users"""
    try:
        users = container.rbac_service.get_all_users()
        return jsonify({'users': users})
    except Exception as e:
        return jsonify({'message': str(e)}), 500


@admin_bp.route('/users/<int:user_id>', methods=['GET'])
@admin_required
def get_user(user_id):
    """Get user by ID"""
    try:
        user = container.rbac_service.get_user_by_id(user_id)
        if not user:
            return jsonify({'message': 'User not found'}), 404
        return jsonify({'user': user})
    except Exception as e:
        return jsonify({'message': str(e)}), 500


@admin_bp.route('/users/<int:user_id>/approve', methods=['POST'])
@admin_required
def approve_user(user_id):
    """Approve a pending user"""
    data = request.json or {}
    role_id = data.get('roleId')
    
    try:
        # Get target user info before approval
        target_user = container.rbac_service.get_user_by_id(user_id)
        
        if container.rbac_service.approve_user(user_id, role_id):
            # Log user approval
            container.audit_service.log_admin_action(
                user_id=request.current_user['user_id'],
                username=request.current_user['username'],
                action='USER_APPROVED',
                target_user_id=user_id,
                target_username=target_user.get('username') if target_user else None,
                additional_data={'role_id': role_id},
                ip_address=request.remote_addr
            )
            return jsonify({'message': 'User approved successfully'})
        return jsonify({'message': 'User not found'}), 404
    except Exception as e:
        return jsonify({'message': str(e)}), 500


@admin_bp.route('/users/<int:user_id>/revoke', methods=['POST'])
@admin_required
def revoke_user(user_id):
    """Revoke user access"""
    try:
        # Prevent self-revoke
        if request.current_user['user_id'] == user_id:
            return jsonify({'message': 'Cannot revoke your own access'}), 400
        
        # Get target user info before revocation
        target_user = container.rbac_service.get_user_by_id(user_id)
        
        if container.rbac_service.revoke_user(user_id):
            # Log user revocation
            container.audit_service.log_admin_action(
                user_id=request.current_user['user_id'],
                username=request.current_user['username'],
                action='USER_REVOKED',
                target_user_id=user_id,
                target_username=target_user.get('username') if target_user else None,
                ip_address=request.remote_addr
            )
            
            # Terminate all user sessions
            try:
                terminated = container.session_service.terminate_user_sessions(
                    user_id, reason='admin_revoke'
                )
                if terminated > 0:
                    container.audit_service.log_admin_action(
                        user_id=request.current_user['user_id'],
                        username=request.current_user['username'],
                        action='SESSION_TERMINATED',
                        target_user_id=user_id,
                        target_username=target_user.get('username') if target_user else None,
                        additional_data={'terminated_sessions': terminated},
                        ip_address=request.remote_addr
                    )
            except:
                pass
            
            return jsonify({'message': 'User revoked successfully'})
        return jsonify({'message': 'User not found'}), 404
    except Exception as e:
        return jsonify({'message': str(e)}), 500


@admin_bp.route('/users/<int:user_id>/reset-password', methods=['POST'])
@admin_required
def reset_user_password(user_id):
    """Admin action: force the target user to change their password on next login."""
    try:
        # Prevent admin resetting their own password via this flow
        if request.current_user['user_id'] == user_id:
            return jsonify({'message': 'Use the profile page to change your own password.'}), 400

        target_user = container.rbac_service.get_user_by_id(user_id)
        if not target_user:
            return jsonify({'message': 'User not found'}), 404

        container.auth_service.reset_password_by_admin(user_id)

        container.audit_service.log_admin_action(
            user_id=request.current_user['user_id'],
            username=request.current_user['username'],
            action='PASSWORD_RESET_BY_ADMIN',
            target_user_id=user_id,
            target_username=target_user.get('username'),
            ip_address=request.remote_addr
        )

        return jsonify({'message': f"Password reset for {target_user.get('username')}. They will be prompted on next login."})
    except Exception as e:
        return jsonify({'message': str(e)}), 500


@admin_bp.route('/users/<int:user_id>/role', methods=['POST'])
@admin_required
def assign_user_role(user_id):
    """Assign role to user"""
    data = request.json
    role_id = data.get('roleId')
    
    if not role_id:
        return jsonify({'message': 'roleId required'}), 400
    
    try:
        # Get target user info
        target_user = container.rbac_service.get_user_by_id(user_id)
        old_role = target_user.get('role_name') if target_user else None
        
        # Get new role info
        roles = container.rbac_service.get_all_roles()
        new_role = next((r.get('name') for r in roles if r.get('id') == role_id), None)
        
        if container.rbac_service.assign_role(user_id, role_id):
            # Log role assignment
            container.audit_service.log_admin_action(
                user_id=request.current_user['user_id'],
                username=request.current_user['username'],
                action='ROLE_ASSIGNED',
                target_user_id=user_id,
                target_username=target_user.get('username') if target_user else None,
                additional_data={
                    'old_role': old_role,
                    'new_role': new_role,
                    'role_id': role_id
                },
                ip_address=request.remote_addr
            )
            return jsonify({'message': 'Role assigned successfully'})
        return jsonify({'message': 'User not found'}), 404
    except Exception as e:
        return jsonify({'message': str(e)}), 500


# ==================== Role Management ====================

@admin_bp.route('/roles', methods=['GET'])
@admin_required
def get_roles():
    """Get all roles"""
    try:
        roles = container.rbac_service.get_all_roles()
        return jsonify({'roles': roles})
    except Exception as e:
        return jsonify({'message': str(e)}), 500


@admin_bp.route('/roles', methods=['POST'])
@admin_required
def create_role():
    """Create a new role"""
    data = request.json
    name = data.get('name')
    description = data.get('description')
    is_admin = data.get('isAdmin', False)
    
    if not name:
        return jsonify({'message': 'Role name required'}), 400
    
    try:
        role_id = container.rbac_service.create_role(name, description, is_admin)
        
        # Log role creation
        container.audit_service.log_admin_action(
            user_id=request.current_user['user_id'],
            username=request.current_user['username'],
            action='ROLE_CREATED',
            target_user_id=role_id,
            target_username=name,
            additional_data={
                'description': description,
                'is_admin': is_admin
            },
            ip_address=request.remote_addr
        )
        
        return jsonify({'message': 'Role created', 'roleId': role_id}), 201
    except Exception as e:
        return jsonify({'message': str(e)}), 500


@admin_bp.route('/roles/<int:role_id>', methods=['PUT'])
@admin_required
def update_role(role_id):
    """Update a role"""
    data = request.json
    
    try:
        if container.rbac_service.update_role(
            role_id,
            name=data.get('name'),
            description=data.get('description'),
            is_admin=data.get('isAdmin')
        ):
            return jsonify({'message': 'Role updated'})
        return jsonify({'message': 'Role not found'}), 404
    except Exception as e:
        return jsonify({'message': str(e)}), 500


@admin_bp.route('/roles/<int:role_id>', methods=['DELETE'])
@admin_required
def delete_role(role_id):
    """Delete a role"""
    try:
        # Get role info before deletion
        roles = container.rbac_service.get_all_roles()
        role_info = next((r for r in roles if r.get('id') == role_id), None)
        
        if container.rbac_service.delete_role(role_id):
            # Log role deletion
            container.audit_service.log_admin_action(
                user_id=request.current_user['user_id'],
                username=request.current_user['username'],
                action='ROLE_DELETED',
                target_user_id=role_id,
                target_username=role_info.get('name') if role_info else None,
                ip_address=request.remote_addr
            )
            return jsonify({'message': 'Role deleted'})
        return jsonify({'message': 'Role not found'}), 404
    except Exception as e:
        return jsonify({'message': str(e)}), 500


# ==================== Tag Permissions ====================

@admin_bp.route('/roles/<int:role_id>/tag-permissions', methods=['GET'])
@admin_required
def get_tag_permissions(role_id):
    """Get tag permissions for a role"""
    try:
        permissions = container.rbac_service.get_role_tag_permissions(role_id)
        return jsonify({'permissions': permissions})
    except Exception as e:
        return jsonify({'message': str(e)}), 500


@admin_bp.route('/roles/<int:role_id>/tag-permissions', methods=['POST'])
@admin_required
def add_tag_permission(role_id):
    """Add tag permission to a role"""
    data = request.json
    plant = data.get('plant')
    area = data.get('area')
    can_view = data.get('canView', True)
    can_write = data.get('canWrite', False)
    
    try:
        perm_id = container.rbac_service.add_tag_permission(
            role_id, plant, area, can_view, can_write
        )
        
        # Log permission grant
        container.audit_service.log_admin_action(
            user_id=request.current_user['user_id'],
            username=request.current_user['username'],
            action='PERMISSION_GRANTED',
            additional_data={
                'role_id': role_id,
                'permission_type': 'tag',
                'plant': plant,
                'area': area,
                'can_view': can_view,
                'can_write': can_write
            },
            ip_address=request.remote_addr
        )
        
        return jsonify({'message': 'Permission added', 'permissionId': perm_id}), 201
    except Exception as e:
        return jsonify({'message': str(e)}), 500


@admin_bp.route('/tag-permissions/<int:permission_id>', methods=['DELETE'])
@admin_required
def remove_tag_permission(permission_id):
    """Remove a tag permission"""
    try:
        if container.rbac_service.remove_tag_permission(permission_id):
            # Log permission revocation
            container.audit_service.log_admin_action(
                user_id=request.current_user['user_id'],
                username=request.current_user['username'],
                action='PERMISSION_REVOKED',
                additional_data={
                    'permission_id': permission_id,
                    'permission_type': 'tag'
                },
                ip_address=request.remote_addr
            )
            return jsonify({'message': 'Permission removed'})
        return jsonify({'message': 'Permission not found'}), 404
    except Exception as e:
        return jsonify({'message': str(e)}), 500


# ==================== Alarm Permissions ====================

@admin_bp.route('/roles/<int:role_id>/alarm-permissions', methods=['GET'])
@admin_required
def get_alarm_permissions(role_id):
    """Get alarm permissions for a role"""
    try:
        permissions = container.rbac_service.get_role_alarm_permissions(role_id)
        return jsonify({'permissions': permissions})
    except Exception as e:
        return jsonify({'message': str(e)}), 500


@admin_bp.route('/roles/<int:role_id>/alarm-permissions', methods=['POST'])
@admin_required
def add_alarm_permission(role_id):
    """Add alarm permission to a role"""
    data = request.json
    category = data.get('alarmCategory')
    can_view = data.get('canView', True)
    can_acknowledge = data.get('canAcknowledge', False)
    can_silence = data.get('canSilence', False)
    can_clear = data.get('canClear', False)
    requires_approval_to_clear = data.get('requiresApprovalToClear', False)
    
    if not category:
        return jsonify({'message': 'alarmCategory required'}), 400
    
    try:
        perm_id = container.rbac_service.add_alarm_permission(
            role_id, category, can_view, can_acknowledge, can_silence, 
            can_clear, requires_approval_to_clear
        )
        return jsonify({'message': 'Permission added', 'permissionId': perm_id}), 201
    except Exception as e:
        return jsonify({'message': str(e)}), 500


@admin_bp.route('/alarm-permissions/<int:permission_id>', methods=['DELETE'])
@admin_required
def remove_alarm_permission(permission_id):
    """Remove an alarm permission"""
    try:
        if container.rbac_service.remove_alarm_permission(permission_id):
            return jsonify({'message': 'Permission removed'})
        return jsonify({'message': 'Permission not found'}), 404
    except Exception as e:
        return jsonify({'message': str(e)}), 500


# ==================== Specific Tag Permissions ====================

@admin_bp.route('/available-tags', methods=['GET'])
@admin_required
def get_available_tags():
    """Get all available tags for selection"""
    try:
        tags = container.rbac_service.get_available_tags()
        return jsonify({'tags': tags})
    except Exception as e:
        return jsonify({'message': str(e)}), 500


@admin_bp.route('/roles/<int:role_id>/specific-tag-permissions', methods=['GET'])
@admin_required
def get_specific_tag_permissions(role_id):
    """Get specific tag permissions for a role"""
    try:
        permissions = container.rbac_service.get_role_specific_tag_permissions(role_id)
        return jsonify({'permissions': permissions})
    except Exception as e:
        return jsonify({'message': str(e)}), 500


@admin_bp.route('/roles/<int:role_id>/specific-tag-permissions', methods=['POST'])
@admin_required
def add_specific_tag_permission(role_id):
    """Add specific tag permission to a role"""
    data = request.json
    tag_id = data.get('tagId')
    can_view = data.get('canView', True)
    can_write = data.get('canWrite', False)
    
    if not tag_id:
        return jsonify({'message': 'tagId required'}), 400
    
    try:
        perm_id = container.rbac_service.add_specific_tag_permission(
            role_id, tag_id, can_view, can_write
        )
        return jsonify({'message': 'Permission added', 'permissionId': perm_id}), 201
    except Exception as e:
        return jsonify({'message': str(e)}), 500


@admin_bp.route('/specific-tag-permissions/<int:permission_id>', methods=['DELETE'])
@admin_required
def remove_specific_tag_permission(permission_id):
    """Remove a specific tag permission"""
    try:
        if container.rbac_service.remove_specific_tag_permission(permission_id):
            return jsonify({'message': 'Permission removed'})
        return jsonify({'message': 'Permission not found'}), 404
    except Exception as e:
        return jsonify({'message': str(e)}), 500


# ==================== Module Permissions ====================

@admin_bp.route('/roles/<int:role_id>/module-permissions', methods=['GET'])
@admin_required
def get_role_module_permissions(role_id):
    """Get all module permissions for a role (admin UI)."""
    try:
        perms = container.rbac_service.get_role_module_permissions(role_id)
        return jsonify({'permissions': perms})
    except Exception as e:
        return jsonify({'message': str(e)}), 500


@admin_bp.route('/roles/<int:role_id>/module-permissions', methods=['PUT'])
@admin_required
def update_role_module_permissions(role_id):
    """Update module permissions for a role. Body: [{module, can_view, can_operate, can_generate, can_configure}]"""
    try:
        data = request.get_json()
        rows = data.get('permissions', [])
        for row in rows:
            container.rbac_service.update_role_module_permission(
                role_id,
                row['module'],
                bool(row.get('can_view', False)),
                bool(row.get('can_operate', False)),
                bool(row.get('can_generate', False)),
                bool(row.get('can_configure', False)),
            )
        return jsonify({'message': 'Module permissions updated successfully'})
    except Exception as e:
        return jsonify({'message': str(e)}), 500


# ==================== System Alerts ====================

@admin_bp.route('/alerts', methods=['GET'])
@admin_required
def get_system_alerts():
    """Get system alerts (e.g. lockouts)"""
    try:
        alerts = container.auth_service.get_system_alerts()
        return jsonify({'alerts': alerts})
    except Exception as e:
        return jsonify({'message': str(e)}), 500

@admin_bp.route('/users/<int:user_id>/unlock', methods=['POST'])
@admin_required
def unlock_user_account(user_id):
    """Unlock a locked user account"""
    try:
        container.auth_service.unlock_user_account(user_id)
        return jsonify({'message': 'User account unlocked successfully'})
    except Exception as e:
        return jsonify({'message': str(e)}), 500


# ==================== Plant/Area Access Control ====================

@admin_bp.route('/plants-areas', methods=['GET'])
@admin_required
def get_plants_areas():
    """
    Get all plant/area combinations from the registry.
    Query param: ?active_only=true (default) | false
    """
    try:
        active_only = request.args.get('active_only', 'true').lower() != 'false'
        items = container.area_access_service.get_all_plants_areas(active_only=active_only)
        return jsonify({'plants_areas': items, 'count': len(items)})
    except Exception as e:
        return jsonify({'message': str(e)}), 500


@admin_bp.route('/plants-areas/sync', methods=['POST'])
@admin_required
def sync_plants_areas():
    """Sync plants_areas registry from tag_master (picks up new plant/area values)."""
    try:
        inserted = container.area_access_service.sync_from_tag_master()
        return jsonify({'message': f'Sync complete. {inserted} new entries added.'})
    except Exception as e:
        return jsonify({'message': str(e)}), 500


@admin_bp.route('/plants-areas', methods=['POST'])
@admin_required
def create_plant_area():
    """Create a new plant/area entry manually."""
    data = request.json or {}
    plant = data.get('plant', '').strip()
    area = data.get('area', '').strip()
    display_name = data.get('display_name', '').strip() or None
    description = data.get('description', '').strip() or None

    if not plant or not area:
        return jsonify({'message': 'plant and area are required'}), 400

    try:
        entry = container.area_access_service.create_plant_area(
            plant=plant, area=area,
            display_name=display_name, description=description
        )
        return jsonify({'message': 'Plant/Area created', 'plant_area': entry}), 201
    except ValueError as e:
        return jsonify({'message': str(e)}), 409
    except Exception as e:
        return jsonify({'message': str(e)}), 500


@admin_bp.route('/plants-areas/<int:plant_area_id>/toggle', methods=['POST'])
@admin_required
def toggle_plant_area(plant_area_id):
    """Activate or deactivate a plant/area entry."""
    data = request.json or {}
    is_active = data.get('is_active')
    if is_active is None:
        return jsonify({'message': 'is_active required'}), 400
    try:
        container.area_access_service.set_plant_area_active(plant_area_id, bool(is_active))
        state = 'activated' if is_active else 'deactivated'
        return jsonify({'message': f'Plant/Area {state} successfully'})
    except Exception as e:
        return jsonify({'message': str(e)}), 500


@admin_bp.route('/users/<int:user_id>/areas', methods=['GET'])
@admin_required
def get_user_areas(user_id):
    """Get the plant/area assignments for a user."""
    try:
        assigned_ids = container.area_access_service.get_user_assigned_area_ids(user_id)
        # Also return full area objects for the UI
        all_areas = container.area_access_service.get_all_plants_areas(active_only=False)
        return jsonify({
            'assigned_plant_area_ids': assigned_ids,
            'all_plants_areas': all_areas,
        })
    except Exception as e:
        return jsonify({'message': str(e)}), 500


@admin_bp.route('/users/<int:user_id>/areas', methods=['PUT'])
@admin_required
def set_user_areas(user_id):
    """
    Full replace of a user's area assignments.
    Body: { "plant_area_ids": [1, 3, 5], "notes": "..." }
    Writes audit log. Invalidates cache immediately.
    """
    data = request.json or {}
    plant_area_ids = data.get('plant_area_ids', [])
    notes = data.get('notes', '').strip() or None

    if not isinstance(plant_area_ids, list):
        return jsonify({'message': 'plant_area_ids must be an array'}), 400

    # Prevent admin from removing their own areas (admins bypass filters anyway)
    # but still allow the call so the UI can reflect the state
    try:
        target_user = container.rbac_service.get_user_by_id(user_id)
        if not target_user:
            return jsonify({'message': 'User not found'}), 404

        container.area_access_service.set_user_areas(
            user_id=user_id,
            plant_area_ids=[int(x) for x in plant_area_ids],
            admin_user_id=request.current_user['user_id'],
            admin_username=request.current_user['username'],
            admin_ip=request.remote_addr,
            notes=notes
        )
        return jsonify({
            'message': f'Area assignments updated for {target_user["username"]}',
            'assigned_count': len(plant_area_ids)
        })
    except Exception as e:
        return jsonify({'message': str(e)}), 500


@admin_bp.route('/access-matrix', methods=['GET'])
@admin_required
def get_access_matrix():
    """Returns full user→role→areas overview for admin console."""
    try:
        matrix = container.area_access_service.get_access_matrix()
        return jsonify({'matrix': matrix, 'count': len(matrix)})
    except Exception as e:
        return jsonify({'message': str(e)}), 500


# ==================== License Management (§16 / §27.1) ====================

@admin_bp.route('/license/status', methods=['GET'])
@admin_required
def get_license_status():
    """
    GET /api/admin/license/status
    Returns license banner data for the Admin Console.
    Never exposes the raw signed_payload to the frontend.
    """
    try:
        status = container.license_service.get_status()
        return jsonify(status)
    except Exception as e:
        return jsonify({'message': str(e)}), 500


@admin_bp.route('/license/activate', methods=['POST'])
@admin_required
def activate_license_key():
    """
    POST /api/admin/license/activate
    Body: { "activation_key": "<raw key string>" }

    Validates ECDSA signature, deactivates any prior active key,
    inserts new key, returns verified seat count.
    Only one key can be active at any time.
    """
    data = request.json or {}
    raw_key = data.get('activation_key', '').strip()
    if not raw_key:
        return jsonify({'success': False, 'message': 'activation_key is required'}), 400

    try:
        result = container.license_service.activate_key(
            raw_key=raw_key,
            admin_user_id=request.current_user['user_id']
        )
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({'success': False, 'message': str(e)}), 422
    except Exception as e:
        return jsonify({'success': False, 'message': 'License activation failed.'}), 500
