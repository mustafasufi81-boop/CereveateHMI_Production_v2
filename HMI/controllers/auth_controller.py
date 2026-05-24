from flask import Blueprint, request, jsonify
from container import container
from utils.decorators import token_required
import logging

logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')

@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.json
    if not data or not data.get('username') or not data.get('password'):
        return jsonify({'message': 'Missing username or password'}), 400
        
    try:
        result = container.auth_service.register_user(
            data['username'], 
            data['password'],
            security_questions=data.get('securityQuestions')
        )
        
        # Log user registration
        container.audit_service.log_action(
            user_id=result['user_id'],
            username=data['username'],
            action_type='USER_CREATED',
            action_category='admin',
            target_entity='user',
            target_id=str(result['user_id']),
            target_name=data['username'],
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )
        
        return jsonify({
            'message': 'Registration successful. Please save your MFA token.',
            'userId': result['user_id'],
            'mfaToken': result['mfa_token'],
            'tokenExpiry': '30 days',
            'pending': True
        }), 201
    except Exception as e:
        return jsonify({'message': str(e)}), 400

@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.json
    if not data or not data.get('username') or not data.get('password'):
        return jsonify({'message': 'Missing credentials'}), 400
        
    try:
        user = container.auth_service.verify_login(data['username'], data['password'])
    except ValueError as e:
        # Account locked - log failed login attempt
        try:
            user_id = container.auth_service.get_user_id_by_username(data['username'])
            if user_id:
                container.audit_service.log_login(
                    user_id, data['username'],
                    success=False,
                    failure_reason='Account locked',
                    ip_address=request.remote_addr,
                    user_agent=request.headers.get('User-Agent')
                )
        except:
            pass
        return jsonify({'message': str(e), 'locked': True}), 403
    except Exception as e:
        return jsonify({'message': 'Login error'}), 500
        
    if not user:
        # Log failed login attempt
        try:
            user_id = container.auth_service.get_user_id_by_username(data['username'])
            container.audit_service.log_login(
                user_id if user_id else 0,
                data['username'],
                success=False,
                failure_reason='Invalid credentials',
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent')
            )
        except:
            pass
        return jsonify({'message': 'Invalid credentials'}), 401
    
    # Check user approval status
    status = container.rbac_service.get_user_status(user['id'])
    if status == 'pending':
        return jsonify({'message': 'Your account is pending approval by an administrator.', 'pending': True}), 403
    if status == 'revoked':
        return jsonify({'message': 'Your account has been revoked. Contact an administrator.'}), 403

    # ── FORCE PASSWORD SETUP (admin reset) ──────────────────────────────────
    if user.get('must_change_password'):
        # Issue a limited "setup token" — valid only for /auth/complete-setup
        setup_token = container.auth_service.create_token(user['id'], user['username'], is_partial=True)
        return jsonify({
            'mustChangePassword': True,
            'setupToken': setup_token,
            'message': 'Your password has been reset by an administrator. Please set a new password.'
        }), 200
    user_info = container.rbac_service.get_user_by_id(user['id'])
    is_admin = user_info.get('is_admin', False) if user_info else False
    role_name = user_info.get('role_name') if user_info else None
    
    # Check if MFA is enabled
    if user['mfa_enabled']:
        # Return temp token indicating MFA is required
        token = container.auth_service.create_token(user['id'], user['username'], is_partial=True)
        return jsonify({
            'message': 'MFA required',
            'mfaRequired': True,
            'tempToken': token
        }), 202
    else:
        # Full login - create session
        token = container.auth_service.create_token(user['id'], user['username'], is_partial=False)

        # Pass device_name from request body (§17.2 device_name column)
        device_name = (data.get('device_name') or '').strip()[:150] or None

        # Create session tracking
        session_id, session_token = container.session_service.create_session(
            user['id'],
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent'),
            device_name=device_name
        )
        
        # Log successful login
        container.audit_service.log_login(
            user['id'], user['username'], 
            success=True,
            ip_address=request.remote_addr,
            session_id=session_id,
            user_agent=request.headers.get('User-Agent')
        )
        
        permissions = container.rbac_service.get_user_module_permissions(user['id'])
        return jsonify({
            'token': token,
            'sessionToken': session_token,
            'sessionId': session_id,
            'mfaRequired': False,
            'user': {
                'username': user['username'], 
                'id': user['id'],
                'isAdmin': is_admin,
                'role': role_name,
                'permissions': permissions
            }
        }), 200

@auth_bp.route('/complete-setup', methods=['POST'])
@token_required
def complete_password_setup_endpoint(current_user):
    """Step after admin reset: user sets new password + security questions.
    Requires the partial setupToken issued at login. Returns a full token + new MFA token."""
    data = request.json or {}
    new_password = data.get('newPassword', '').strip()
    security_questions = data.get('securityQuestions', [])
    user_id = current_user['user_id']
    username = current_user['username']
    try:
        container.auth_service.complete_password_setup(user_id, new_password, security_questions)

        # Generate new 6-digit MFA token
        import secrets as _secrets, string as _string, bcrypt as _bcrypt
        mfa_token = ''.join(_secrets.choice(_string.digits) for _ in range(6))
        mfa_token_hash = _bcrypt.hashpw(mfa_token.encode('utf-8'), _bcrypt.gensalt()).decode('utf-8')
        with container.auth_service._get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE historian_meta.users
                    SET backup_key_hash   = %s,
                        backup_key_expiry = NOW() + INTERVAL '30 days'
                    WHERE id = %s
                """, (mfa_token_hash, user_id))
                conn.commit()

        # Issue full token + session
        full_token = container.auth_service.create_token(user_id, username, is_partial=False)
        device_name = (request.json.get('device_name') or '').strip()[:150] or None
        session_id, session_token = container.session_service.create_session(
            user_id,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent'),
            device_name=device_name
        )
        container.audit_service.log_login(
            user_id, username,
            success=True,
            ip_address=request.remote_addr,
            session_id=session_id,
            user_agent=request.headers.get('User-Agent')
        )
        user_info = container.rbac_service.get_user_by_id(user_id)
        is_admin = user_info.get('is_admin', False) if user_info else False
        role_name = user_info.get('role_name') if user_info else None
        permissions = container.rbac_service.get_user_module_permissions(user_id)

        return jsonify({
            'token': full_token,
            'sessionToken': session_token,
            'sessionId': session_id,
            'mfaToken': mfa_token,
            'user': {
                'username': username,
                'id': user_id,
                'isAdmin': is_admin,
                'role': role_name,
                'permissions': permissions
            }
        }), 200
    except ValueError as e:
        return jsonify({'message': str(e)}), 400
    except Exception as e:
        logger.error(f"complete-setup error: {e}")
        return jsonify({'message': 'Setup failed. Please try again.'}), 500


@auth_bp.route('/mfa/setup', methods=['POST'])
@token_required
def mfa_setup(current_user):
    """Get MFA token info (6-digit token system)"""
    token = request.headers.get('Authorization').split(' ')[1]
    data = container.auth_service.decode_token(token)
    user_id = data['user_id']
    
    token_info = container.auth_service.get_current_totp(user_id)
    
    return jsonify({
        'message': 'Use your 6-digit MFA token received during registration',
        'tokenInfo': token_info,
        'note': 'If token is expired or lost, use default token: 123456'
    })

@auth_bp.route('/mfa/totp-code', methods=['GET'])
@token_required
def get_totp_code(current_user):
    """Get current MFA token info"""
    token = request.headers.get('Authorization').split(' ')[1]
    data = container.auth_service.decode_token(token)
    user_id = data['user_id']
    
    token_info = container.auth_service.get_current_totp(user_id)
    if not token_info:
        return jsonify({'message': 'MFA not setup'}), 400
    
    return jsonify(token_info)

@auth_bp.route('/mfa/enable', methods=['POST'])
@token_required
def mfa_enable(current_user):
    """Enable MFA by saving security questions (no TOTP verification required)"""
    data = request.json
    questions = data.get('securityQuestions', [])
    
    if not questions or len(questions) < 2:
        return jsonify({'message': 'At least 2 security questions required'}), 400
    
    token = request.headers.get('Authorization').split(' ')[1]
    token_data = container.auth_service.decode_token(token)
    user_id = token_data['user_id']
    
    try:
        # Save security questions
        container.auth_service.save_security_questions(user_id, questions)
        
        # Enable MFA flag
        container.auth_service.set_mfa_enabled(user_id, True)
        
        # Log MFA enablement
        container.audit_service.log_action(
            user_id=user_id,
            username=token_data['username'],
            action_type='MFA_ENABLED',
            action_category='authentication',
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )
        
        return jsonify({'message': 'MFA enabled successfully'})
    except Exception as e:
        return jsonify({'message': str(e)}), 500

@auth_bp.route('/mfa/verify', methods=['POST'])
def mfa_verify():
    """Verify MFA using either TOTP code or security question answer"""
    data = request.json
    temp_token = data.get('tempToken')
    code = data.get('code')
    question_index = data.get('questionIndex')
    answer = data.get('answer')
    
    if not temp_token:
        return jsonify({'message': 'Missing token'}), 400
    
    if not code and (question_index is None or not answer):
        return jsonify({'message': 'Missing code or answer'}), 400
        
    token_data = container.auth_service.decode_token(temp_token)
    if not token_data or not token_data.get('partial'):
        return jsonify({'message': 'Invalid temporary token'}), 401
        
    user_id = token_data['user_id']
    username = token_data['username']
    
    verified = False
    
    # Try TOTP verification
    if code:
        verified = container.auth_service.verify_mfa_token(user_id, code)
    # Try security question verification
    elif question_index is not None and answer:
        verified = container.auth_service.verify_security_answer(user_id, question_index, answer)
    
    if verified:
        # Get user role info
        user_info = container.rbac_service.get_user_by_id(user_id)
        is_admin = user_info.get('is_admin', False) if user_info else False
        role_name = user_info.get('role_name') if user_info else None
        
        final_token = container.auth_service.create_token(user_id, username, is_partial=False)

        # Create session tracking after MFA verified
        device_name = (request.json.get('device_name') or '').strip()[:150] or None
        session_id, session_token = container.session_service.create_session(
            user_id,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent'),
            device_name=device_name
        )
        
        # Log successful login
        container.audit_service.log_login(
            user_id, username,
            success=True,
            ip_address=request.remote_addr,
            session_id=session_id,
            user_agent=request.headers.get('User-Agent')
        )
        
        permissions = container.rbac_service.get_user_module_permissions(user_id)
        return jsonify({
            'token': final_token,
            'sessionToken': session_token,
            'sessionId': session_id,
            'mfaRequired': False,
            'user': {
                'username': username, 
                'id': user_id,
                'isAdmin': is_admin,
                'role': role_name,
                'permissions': permissions
            }
        })
    else:
        # Log failed MFA verification
        container.audit_service.log_login(
            user_id, username,
            success=False,
            failure_reason='Invalid MFA code or answer',
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )
    
    return jsonify({'message': 'Invalid MFA code or answer'}), 401

@auth_bp.route('/mfa/question', methods=['POST'])
def get_mfa_question():
    """Get a random security question for the user (during login MFA)"""
    data = request.json
    temp_token = data.get('tempToken')
    
    if not temp_token:
        return jsonify({'message': 'Missing token'}), 400
    
    token_data = container.auth_service.decode_token(temp_token)
    if not token_data or not token_data.get('partial'):
        return jsonify({'message': 'Invalid token'}), 401
    
    user_id = token_data['user_id']
    question_data = container.auth_service.get_random_question(user_id)
    
    if not question_data:
        return jsonify({'message': 'No security questions set up', 'available': False}), 200
    
    return jsonify({
        'available': True,
        'index': question_data['index'],
        'question': question_data['question']
    })

@auth_bp.route('/validate', methods=['GET'])
@token_required
def validate_token(current_user):
    """Validate the current token and return user info with role"""
    try:
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'valid': False}), 401
        token = auth_header.split(' ')[1]
        data = container.auth_service.decode_token(token)
        if data and not data.get('partial'):
            user_id = data['user_id']
            try:
                user_info = container.rbac_service.get_user_by_id(user_id)
            except Exception:
                user_info = None
            is_admin = user_info.get('is_admin', False) if user_info else False
            role_name = user_info.get('role_name') if user_info else None
            mfa_enabled = user_info.get('mfa_enabled', False) if user_info else False

            try:
                permissions = container.rbac_service.get_user_module_permissions(user_id)
            except Exception:
                permissions = {}
            return jsonify({
                'valid': True,
                'user': {
                    'id': data['user_id'],
                    'username': data['username'],
                    'mfaEnabled': mfa_enabled,
                    'isAdmin': is_admin,
                    'role': role_name,
                    'permissions': permissions
                }
            })
        return jsonify({'valid': False}), 401
    except Exception as e:
        logger.warning(f"validate_token error (swallowed): {e}")
        return jsonify({'valid': False}), 401


@auth_bp.route('/reset-password/check', methods=['POST'])
def reset_password_check():
    """Step 1: Check user and get security question"""
    data = request.json
    username = data.get('username')
    
    if not username:
        return jsonify({'message': 'Username required'}), 400
        
    try:
        user_id = container.auth_service.get_user_id_by_username(username)
        if not user_id:
            # Don't reveal user existence? Or maybe we have to for this flow?
            # User requirement says "Security Question will be used to reset password".
            # If we return "User not found" it allows enumeration.
            # But if we return nothing, the UI is stuck.
            # I'll return a generic "User not found" for now as it's an internal-ish tool.
            return jsonify({'message': 'User not found'}), 404
            
        question_data = container.auth_service.get_random_question(user_id)
        
        response = {'found': True}
        if question_data:
            response['question'] = {
                'index': question_data['index'],
                'text': question_data['question']
            }
            
        return jsonify(response)

    except Exception as e:
        return jsonify({'message': str(e)}), 500

@auth_bp.route('/reset-password', methods=['POST'])
def reset_password():
    """Reset password using backup key or security question"""
    data = request.json
    username = data.get('username')
    method = data.get('method') # 'key' or 'question'
    answer = data.get('answer') # answer or key
    new_password = data.get('newPassword')
    question_index = data.get('questionIndex')
    
    if not all([username, method, answer, new_password]):
        return jsonify({'message': 'Missing fields'}), 400
        
    try:
        user_id = container.auth_service.get_user_id_by_username(username)

        if not user_id:
             return jsonify({'message': 'User not found'}), 404

        verified_user_id = False
        
        if method == 'key':
            verified_user_id = container.auth_service.verify_backup_key(username, answer)
        elif method == 'question':
            if question_index is None:
                 return jsonify({'message': 'Missing question index'}), 400
            if container.auth_service.verify_security_answer(user_id, question_index, answer):
                verified_user_id = user_id
            
        if verified_user_id:
            container.auth_service.reset_password(verified_user_id, new_password)
            
            # Log password reset
            container.audit_service.log_action(
                user_id=verified_user_id,
                username=username,
                action_type='PASSWORD_RESET',
                action_category='authentication',
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent'),
                additional_data={'method': method}
            )
            
            return jsonify({'message': 'Password reset successful'})
        else:
            # Log failed password reset attempt
            try:
                container.audit_service.log_action(
                    user_id=user_id,
                    username=username,
                    action_type='PASSWORD_RESET',
                    action_category='authentication',
                    success=False,
                    failure_reason='Invalid verification information',
                    ip_address=request.remote_addr,
                    user_agent=request.headers.get('User-Agent')
                )
            except:
                pass
            return jsonify({'message': 'Invalid verification information'}), 400
            
    except Exception as e:
        return jsonify({'message': str(e)}), 500

@auth_bp.route('/logout', methods=['POST'])
@token_required
def logout(current_user):
    """Logout and end session"""
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    data = container.auth_service.decode_token(token)
    user_id = data['user_id']
    username = data['username']
    
    # Get session token from request body (optional - frontend may provide it)
    req_data = request.json or {}
    session_token = req_data.get('sessionToken')
    
    if session_token:
        # Get session info BEFORE ending it
        session_info = container.session_service.get_session_by_token(session_token)
        session_id = session_info.get('id') if session_info else None
        
        # End the session
        container.session_service.end_session(session_token, reason='user_logout')
        
        # Log logout
        container.audit_service.log_logout(
            user_id, username,
            forced=False,
            session_id=session_id
        )
    else:
        # No session token provided - just log basic logout
        container.audit_service.log_logout(
            user_id, username,
            forced=False,
            session_id=None
        )
    
    return jsonify({'message': 'Logged out successfully'})

@auth_bp.route('/backup-key/regenerate', methods=['POST'])
@token_required
def regenerate_backup_key(current_user):
    """Regenerate backup key for logged in user"""
    token = request.headers.get('Authorization').split(' ')[1]
    data = container.auth_service.decode_token(token)
    user_id = data['user_id']
    
    try:
        new_key = container.auth_service.regenerate_backup_key(user_id)
        
        # Log backup key regeneration
        container.audit_service.log_action(
            user_id=user_id,
            username=data['username'],
            action_type='PASSWORD_CHANGED',
            action_category='authentication',
            target_entity='backup_key',
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )
        
        return jsonify({
            'message': 'New backup key generated',
            'backupKey': new_key
        })
    except Exception as e:
        return jsonify({'message': str(e)}), 500
