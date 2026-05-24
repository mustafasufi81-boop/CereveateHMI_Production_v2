"""
Session Controller - API endpoints for session management
"""
from flask import Blueprint, request, jsonify, g
from container import container
from utils.decorators import token_required
import logging

logger = logging.getLogger(__name__)

session_bp = Blueprint('session', __name__, url_prefix='/api/session')


@session_bp.route('/active', methods=['GET'])
@token_required
def get_active_sessions(current_user):
    """Get all active sessions (admin only) or user's own sessions."""
    try:
        is_admin = getattr(g, 'is_admin', False)
        user_id = getattr(g, 'user_id', None)
        
        if is_admin:
            # Admin can see all sessions
            sessions = container.session_service.get_active_sessions()
        else:
            # Regular users see only their sessions
            sessions = container.session_service.get_active_sessions(
                user_id=user_id
            )
        
        return jsonify({'sessions': sessions}), 200
    except Exception as e:
        logger.error(f"Get active sessions error: {e}")
        return jsonify({'message': str(e)}), 500


@session_bp.route('/my-sessions', methods=['GET'])
@token_required
def get_my_sessions(current_user):
    """Get current user's active sessions."""
    try:
        user_id = getattr(g, 'user_id', None)
        sessions = container.session_service.get_active_sessions(
            user_id=user_id
        )
        return jsonify({'sessions': sessions}), 200
    except Exception as e:
        logger.error(f"Get my sessions error: {e}")
        return jsonify({'message': str(e)}), 500


@session_bp.route('/end/<session_token>', methods=['POST'])
@token_required
def end_session(current_user, session_token):
    """End a specific session."""
    try:
        user_id = getattr(g, 'user_id', None)
        username = getattr(g, 'username', None)
        is_admin = getattr(g, 'is_admin', False)
        
        # Verify user owns this session or is admin
        session_info = container.session_service.get_session_by_token(session_token)
        if not session_info:
            return jsonify({'message': 'Session not found'}), 404
        
        if session_info['user_id'] != user_id and not is_admin:
            return jsonify({'message': 'Unauthorized'}), 403
        
        success = container.session_service.end_session(session_token)
        
        if success:
            # Log session termination
            container.audit_service.log_logout(
                user_id=user_id,
                username=username,
                forced=False,
                session_id=session_info.get('id') if session_info else None
            )
            return jsonify({'message': 'Session ended'}), 200
        else:
            return jsonify({'message': 'Failed to end session'}), 500
    except Exception as e:
        logger.error(f"End session error: {e}")
        return jsonify({'message': str(e)}), 500


@session_bp.route('/end-by-id/<int:session_id>', methods=['POST'])
@token_required
def end_session_by_id(current_user, session_id):
    """End a specific session by ID (admin only)."""
    try:
        user_id = getattr(g, 'user_id', None)
        username = getattr(g, 'username', None)
        is_admin = getattr(g, 'is_admin', False)
        
        if not is_admin:
            return jsonify({'message': 'Unauthorized - Admin only'}), 403
        
        success = container.session_service.end_session_by_id(
            session_id=session_id,
            reason='admin_terminate',
            forced=True
        )
        
        if success:
            # Log action
            container.audit_service.log_action(
                user_id=user_id,
                username=username,
                action_type='TERMINATE_SESSION',
                action_category='admin',
                target_entity='session',
                target_id=session_id,
                target_name=f"Session {session_id}",
                ip_address=request.remote_addr
            )
            return jsonify({'message': 'Session ended'}), 200
        else:
            return jsonify({'message': 'Failed to end session or session not found'}), 500
    except Exception as e:
        logger.error(f"End session by ID error: {e}")
        return jsonify({'message': str(e)}), 500


@session_bp.route('/end-all', methods=['POST'])
@token_required
def end_all_sessions(current_user):
    """End all active sessions for current user (except current one)."""
    try:
        user_id = getattr(g, 'user_id', None)
        username = getattr(g, 'username', None)
        
        current_token = request.headers.get('Authorization', '').replace('Bearer ', '')
        count = container.session_service.end_all_user_sessions(
            user_id=user_id,
            except_token=current_token
        )
        
        # Log action
        container.audit_service.log_action(
            user_id=user_id,
            username=username,
            action_type='END_ALL_SESSIONS',
            action_category='admin',
            target_entity='session',
            target_name=f"Ended {count} sessions",
            ip_address=request.remote_addr
        )
        
        return jsonify({
            'message': f'Ended {count} sessions',
            'count': count
        }), 200
    except Exception as e:
        logger.error(f"End all sessions error: {e}")
        return jsonify({'message': str(e)}), 500


@session_bp.route('/activity', methods=['POST'])
@token_required
def update_activity(current_user):
    """Update session activity (heartbeat). Never returns 5xx — failures are silent."""
    try:
        session_token = request.headers.get('X-Session-Token')
        if not session_token:
            # No session token — harmless, just return ok so UI doesn't flood console
            return jsonify({'success': True, 'note': 'no session token'}), 200

        try:
            container.session_service.update_activity(session_token)
        except Exception as svc_err:
            # DB / function errors are non-critical for heartbeat — log and swallow
            logger.warning(f"Session activity update swallowed: {svc_err}")

        return jsonify({'success': True}), 200
    except Exception as e:
        logger.warning(f"Update activity outer error (swallowed): {e}")
        return jsonify({'success': True}), 200


@session_bp.route('/cleanup', methods=['POST'])
@token_required
def cleanup_expired(current_user):
    """Cleanup expired sessions (admin only)."""
    user_id = getattr(g, 'user_id', None)
    username = getattr(g, 'username', None)
    is_admin = getattr(g, 'is_admin', False)
    
    if not is_admin:
        return jsonify({'message': 'Unauthorized'}), 403
    
    try:
        count = container.session_service.cleanup_expired_sessions()
        
        # Log action
        container.audit_service.log_action(
            user_id=user_id,
            username=username,
            action_type='CLEANUP_EXPIRED_SESSIONS',
            action_category='admin',
            target_entity='session',
            target_name=f"Cleaned up {count} sessions",
            ip_address=request.remote_addr
        )
        
        return jsonify({
            'message': f'Cleaned up {count} expired sessions',
            'count': count
        }), 200
    except Exception as e:
        logger.error(f"Cleanup expired error: {e}")
        return jsonify({'message': str(e)}), 500


@session_bp.route('/statistics', methods=['GET'])
@token_required
def get_session_statistics(current_user):
    """Get session statistics (admin only)."""
    is_admin = getattr(g, 'is_admin', False)
    
    if not is_admin:
        return jsonify({'message': 'Unauthorized'}), 403
    
    try:
        stats = container.session_service.get_session_statistics()
        return jsonify({'statistics': stats}), 200
    except Exception as e:
        logger.error(f"Get session statistics error: {e}")
        return jsonify({'message': str(e)}), 500
