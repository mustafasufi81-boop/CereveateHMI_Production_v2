"""
Audit Controller - API endpoints for audit logging
"""
from flask import Blueprint, request, jsonify
from container import container
from utils.decorators import token_required
import logging

logger = logging.getLogger(__name__)

audit_bp = Blueprint('audit', __name__, url_prefix='/api/audit')


# DEBUG ENDPOINT - Remove in production!
@audit_bp.route('/debug/count', methods=['GET'])
def debug_audit_count():
    """Debug endpoint to check if audit records exist (NO AUTH for testing)"""
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
        
        db_config = container.db_config
        
        with psycopg2.connect(**db_config) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT COUNT(*) as count FROM historian_meta.user_actions_audit")
                result = cur.fetchone()
                
                cur.execute("""
                    SELECT id, username, action_type, timestamp 
                    FROM historian_meta.user_actions_audit 
                    ORDER BY timestamp DESC 
                    LIMIT 5
                """)
                samples = cur.fetchall()
                
                return jsonify({
                    'success': True,
                    'total_records': result['count'],
                    'sample_records': samples,
                    'message': 'Audit system is working. Records exist in database.'
                }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'message': 'Error accessing audit table'
        }), 500


@audit_bp.route('/search', methods=['GET'])
@token_required
def search_audit_logs(current_user):
    """Search audit logs with filters."""
    logger.info("=" * 80)
    logger.info("🔍 AUDIT LOG SEARCH REQUEST")
    logger.info(f"   User: {current_user.get('username')} (ID: {current_user.get('user_id')})")
    logger.info(f"   Query Params: {dict(request.args)}")
    
    try:
        user_id = request.args.get('user_id', type=int)
        username = request.args.get('username')
        action_type = request.args.get('action_type')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        limit = request.args.get('limit', default=100, type=int)
        
        logger.info(f"   Filters: user_id={user_id}, username={username}, action_type={action_type}")
        logger.info(f"   Date Range: {start_date} to {end_date}, Limit: {limit}")
        
        logs = container.audit_service.search_audit_logs(
            user_id=user_id,
            username=username,
            action_type=action_type,
            start_date=start_date,
            end_date=end_date,
            limit=limit
        )
        
        logger.info(f"✅ Found {len(logs)} audit logs")
        if logs:
            logger.info(f"   Sample log: {logs[0] if logs else 'None'}")
        else:
            logger.warning("⚠️ NO LOGS RETURNED FROM DATABASE!")
        
        response_data = {'logs': logs, 'count': len(logs)}
        logger.info(f"   Response size: {len(str(response_data))} bytes")
        logger.info("=" * 80)
        
        return jsonify(response_data), 200
    except Exception as e:
        logger.error("=" * 80)
        logger.error(f"❌ Search audit logs error: {e}")
        logger.error("=" * 80)
        import traceback
        traceback.print_exc()
        return jsonify({'message': str(e), 'error': True}), 500


@audit_bp.route('/statistics', methods=['GET'])
@token_required
def get_statistics(current_user):
    """Get audit statistics."""
    try:
        days = request.args.get('days', default=30, type=int)
        stats = container.audit_service.get_audit_statistics(days=days)
        return jsonify({'statistics': stats}), 200
    except Exception as e:
        logger.error(f"Get audit statistics error: {e}")
        return jsonify({'message': str(e)}), 500


@audit_bp.route('/user/<int:user_id>', methods=['GET'])
@token_required
def get_user_actions(current_user, user_id):
    """Get audit logs for specific user."""
    try:
        days = request.args.get('days', default=30, type=int)
        limit = request.args.get('limit', default=100, type=int)
        
        logs = container.audit_service.search_audit_logs(
            user_id=user_id,
            days=days,
            limit=limit
        )
        
        return jsonify({'logs': logs, 'count': len(logs)}), 200
    except Exception as e:
        logger.error(f"Get user actions error: {e}")
        return jsonify({'message': str(e)}), 500


@audit_bp.route('/action-types', methods=['GET'])
@token_required
def get_action_types(current_user):
    """Get all available action types."""
    try:
        action_types = container.audit_service.get_action_types()
        return jsonify({'action_types': action_types}), 200
    except Exception as e:
        logger.error(f"Get action types error: {e}")
        return jsonify({'message': str(e)}), 500


@audit_bp.route('/archive', methods=['POST'])
@token_required
def archive_old_logs(current_user):
    """Archive old audit logs (admin only)."""
    # Check if user is admin
    user_info = container.rbac_service.get_user_by_id(current_user['user_id'])
    if not user_info or not user_info.get('is_admin'):
        return jsonify({'message': 'Unauthorized'}), 403
    
    try:
        data = request.json
        days = data.get('days', 365)
        archived_count = container.audit_service.archive_old_logs(days)
        
        # Log this action
        container.audit_service.log_action(
            user_id=current_user['user_id'],
            username=current_user['username'],
            action_type='archive_audit_logs',
            description=f"Archived {archived_count} audit logs older than {days} days",
            ip_address=request.remote_addr
        )
        
        return jsonify({
            'message': f'Archived {archived_count} logs',
            'archived_count': archived_count
        }), 200
    except Exception as e:
        logger.error(f"Archive logs error: {e}")
        return jsonify({'message': str(e)}), 500
