import secrets
import random
import string
import pyotp
import qrcode
import jwt
import bcrypt
import logging
from datetime import datetime, timedelta
import io
import base64

logger = logging.getLogger(__name__)

class AuthService:
    def __init__(self, db_connection_params, secret_key):
        self.db_params = db_connection_params  # kept for reference only
        self.secret_key = secret_key
        self.conn = None  # legacy attribute — not used; pool provides connections
        
    def _get_conn(self):
        import db_pool
        return db_pool.get_conn()
        
    
    def create_system_alert(self, user_id, alert_type, message):
         """Create a system alert for admins"""
         try:
             with self._get_conn() as conn:
                 with conn.cursor() as cur:
                     cur.execute("""
                         INSERT INTO historian_meta.system_alerts (user_id, alert_type, message)
                         VALUES (%s, %s, %s)
                     """, (user_id, alert_type, message))
                     conn.commit()
         except Exception as e:
             logger.error(f"Create alert error: {e}")
             # Don't raise, just log, so we don't block auth flow for alerts 

    def register_user(self, username, password, security_questions=None):
        """
        Register a new user.
        security_questions: list of {'question': str, 'answer': str}
        Returns: {'user_id': int, 'mfa_token': str}
        """
        try:
            if not password or len(password) < 8:
                raise ValueError("Password must be at least 8 characters")
            hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            
            # Generate 6-digit MFA Token (expires in 30 days)
            mfa_token = ''.join(secrets.choice(string.digits) for _ in range(6))
            mfa_token_hash = bcrypt.hashpw(mfa_token.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    # Insert User with MFA enabled by default
                    cur.execute("""
                        INSERT INTO historian_meta.users (
                            username, password_hash, 
                            backup_key_hash, backup_key_expiry,
                            failed_login_attempts, mfa_enabled
                        )
                        VALUES (%s, %s, %s, NOW() + INTERVAL '30 days', 0, TRUE)
                        RETURNING id
                    """, (username, hashed, mfa_token_hash))
                    user_id = cur.fetchone()[0]
                    conn.commit()
            
            # Save Security Questions if provided
            if security_questions:
                self.save_security_questions(user_id, security_questions)
                
            return {
                'user_id': user_id,
                'mfa_token': mfa_token
            }
        except Exception as e:
            logger.error(f"Registration error: {e}")
            raise

    def verify_login(self, username, password):
        """
        Verify credentials with lockout logic. 
        Returns: (user_id, mfa_enabled, mfa_secret) or None
        Raises: ValueError if locked out
        """
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT id, password_hash, mfa_enabled, mfa_secret, 
                               failed_login_attempts, lockout_until, must_change_password
                        FROM historian_meta.users 
                        WHERE username = %s
                    """, (username,))
                    row = cur.fetchone()
                    
                    if not row:
                        return None
                        
                    user_id, pwd_hash, mfa_enabled, mfa_secret, failed_attempts, lockout_until, must_change_password = row
                    
                    # Check Lockout
                    if lockout_until and datetime.now() < lockout_until:
                        remaining = int((lockout_until - datetime.now()).total_seconds() / 60)
                        raise ValueError(f"Account locked. Try again in {remaining} minutes.")
                    
                    # If lockout has expired, reset the counter
                    if lockout_until and datetime.now() >= lockout_until:
                        cur.execute("""
                            UPDATE historian_meta.users 
                            SET failed_login_attempts = 0, lockout_until = NULL 
                            WHERE id = %s
                        """, (user_id,))
                        failed_attempts = 0  # Reset for this login attempt
                    
                    # Guard: admin-reset sentinel — skip bcrypt entirely
                    if pwd_hash == 'RESET_REQUIRED':
                        return {
                            'id': user_id,
                            'username': username,
                            'mfa_enabled': False,
                            'mfa_secret': None,
                            'must_change_password': True
                        }

                    if bcrypt.checkpw(password.encode('utf-8'), pwd_hash.encode('utf-8')):
                        # SUCCESS: Reset counters
                        cur.execute("""
                            UPDATE historian_meta.users 
                            SET failed_login_attempts = 0, lockout_until = NULL 
                            WHERE id = %s
                        """, (user_id,))
                        conn.commit()
                        
                        return {
                            'id': user_id,
                            'username': username,
                            'mfa_enabled': mfa_enabled,
                            'mfa_secret': mfa_secret,
                            'must_change_password': bool(must_change_password)
                        }
                    else:
                        # FAILURE: Increment attempts
                        new_attempts = (failed_attempts or 0) + 1
                        lockout_update = ""
                        
                        if new_attempts >= 3:
                            # Trigger Lockout (30 mins)
                            lockout_update = ", lockout_until = NOW() + INTERVAL '30 minutes'"
                            # Create Alert
                            self.create_system_alert(user_id, 'ACCOUNT_LOCKOUT', f"User {username} locked out after 3 failed attempts.")
                        
                        cur.execute(f"""
                            UPDATE historian_meta.users 
                            SET failed_login_attempts = %s {lockout_update}
                            WHERE id = %s
                        """, (new_attempts, user_id))
                        conn.commit()
                        
                        # Calculate remaining attempts before lockout for nice UX?
                        # Or just return None (Invalid credentials)
                        return None

        except Exception as e:
            logger.error(f"Login error: {e}")
            raise

    def generate_mfa_secret(self, user_id):
        """Generate a new random MFA secret for a user"""
        secret = pyotp.random_base32()
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE historian_meta.users 
                        SET mfa_secret = %s 
                        WHERE id = %s
                    """, (secret, user_id))
                    conn.commit()
            return secret
        except Exception as e:
            logger.error(f"Generate MFA error: {e}")
            raise

    def generate_qr_code(self, username, secret):
        """Generate QR code Base64 string for the secret"""
        totp = pyotp.TOTP(secret)
        uri = totp.provisioning_uri(name=username, issuer_name="OPS_HMI")
        
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(uri)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        
        buffered = io.BytesIO()
        img.save(buffered)
        return base64.b64encode(buffered.getvalue()).decode('utf-8')

    def verify_totp(self, secret, code):
        """Verify the provided TOTP code"""
        if not secret:
            return False
        totp = pyotp.TOTP(secret)
        return totp.verify(code)

    def enable_mfa(self, user_id, code):
        """Enable MFA for a user after verifying code"""
        try:
            # First fetch the secret to verify
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT mfa_secret FROM historian_meta.users WHERE id = %s", (user_id,))
                    row = cur.fetchone()
                    if not row or not row[0]:
                        raise ValueError("No MFA secret generated")
                    secret = row[0]
                    
            if self.verify_totp(secret, code):
                with self._get_conn() as conn:
                    with conn.cursor() as cur:
                        cur.execute("UPDATE historian_meta.users SET mfa_enabled = TRUE WHERE id = %s", (user_id,))
                        conn.commit()
                return True
            return False
        except Exception as e:
            logger.error(f"Enable MFA error: {e}")
            raise

    def set_mfa_enabled(self, user_id, enabled):
        """Directly set the mfa_enabled flag for a user"""
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE historian_meta.users SET mfa_enabled = %s WHERE id = %s",
                        (enabled, user_id)
                    )
                    conn.commit()
            return True
        except Exception as e:
            logger.error(f"Set MFA enabled error: {e}")
            raise

    def create_token(self, user_id, username, is_partial=False):
        """
        Create JWT token. 
        is_partial=True means MFA is still required (temp token).
        """
        payload = {
            'user_id': user_id,
            'username': username,
            'exp': datetime.utcnow() + timedelta(hours=24), # Long expiry for demo
            'partial': is_partial
        }
        return jwt.encode(payload, self.secret_key, algorithm='HS256')
        
    def decode_token(self, token):
        try:
            return jwt.decode(token, self.secret_key, algorithms=['HS256'])
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None

    def verify_mfa_token(self, user_id, code):
        """Verify MFA using 6-digit backup key.
        Returns False if no key is set, if the key has expired, or if the code
        does not match. There is no default/bypass code — every user must have a
        valid, non-expired backup key to use this path.
        """
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT backup_key_hash, backup_key_expiry 
                        FROM historian_meta.users 
                        WHERE id = %s
                    """, (user_id,))
                    row = cur.fetchone()
                    
                    if not row:
                        return False
                    
                    backup_key_hash, backup_key_expiry = row
                    
                    # No backup key set — reject; admin must regenerate one
                    if not backup_key_hash:
                        logger.warning("[AUTH] MFA backup key not set for user_id=%s", user_id)
                        return False
                    
                    # Expired key — reject; user must contact admin to regenerate
                    if backup_key_expiry and datetime.now() > backup_key_expiry:
                        logger.warning("[AUTH] MFA backup key expired for user_id=%s", user_id)
                        return False
                    
                    # Constant-time comparison via bcrypt
                    return bcrypt.checkpw(code.encode('utf-8'), backup_key_hash.encode('utf-8'))
        except Exception as e:
            logger.error(f"Verify MFA Token error: {e}")
            raise

    def get_current_totp(self, user_id):
        """Get the MFA backup key status (expiry info) for a user.
        Never returns the actual key value — only its validity window.
        """
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT backup_key_expiry 
                        FROM historian_meta.users 
                        WHERE id = %s
                    """, (user_id,))
                    row = cur.fetchone()
                    if not row:
                        return None
                    
                    backup_key_expiry = row[0]
                    
                    # Expired — inform user to contact admin for a new key
                    if backup_key_expiry and datetime.now() > backup_key_expiry:
                        return {
                            'expired': True,
                            'remaining': 0,
                            'message': 'MFA backup key has expired. Contact your administrator to regenerate a new key.'
                        }
                    
                    # Calculate remaining days
                    if backup_key_expiry:
                        remaining_days = (backup_key_expiry - datetime.now()).days
                    else:
                        remaining_days = 0
                    
                    return {
                        'expired': False,
                        'remaining': remaining_days,
                        'message': f'MFA backup key valid for {remaining_days} more day(s).'
                    }
        except Exception as e:
            logger.error(f"Get current MFA token info error: {e}")
            raise

    def reset_password_by_admin(self, target_user_id):
        """Admin action: clear the user's password hash and set must_change_password=True.
        User will be forced through the setup flow on next login."""
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    # Set a sentinel hash that will never match a real password.
                    # bcrypt of empty string would actually verify, so we use a
                    # deliberately invalid value that cannot be produced by bcrypt.
                    cur.execute("""
                        UPDATE historian_meta.users
                        SET must_change_password = TRUE,
                            password_hash        = 'RESET_REQUIRED',
                            security_questions   = NULL,
                            updated_at           = NOW()
                        WHERE id = %s
                    """, (target_user_id,))
                    if cur.rowcount == 0:
                        raise ValueError(f"User {target_user_id} not found")
                    conn.commit()
        except Exception as e:
            logger.error(f"Admin password reset error: {e}")
            raise

    def complete_password_setup(self, user_id, new_password, security_questions):
        """Called after admin reset: set new password + security questions, clear the flag.
        Returns a full JWT token."""
        try:
            if not new_password or len(new_password) < 8:
                raise ValueError("Password must be at least 8 characters")
            hashed = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE historian_meta.users
                        SET password_hash        = %s,
                            must_change_password = FALSE,
                            updated_at           = NOW()
                        WHERE id = %s
                    """, (hashed, user_id))
                    conn.commit()
            if security_questions:
                self.save_security_questions(user_id, security_questions)
        except Exception as e:
            logger.error(f"Complete password setup error: {e}")
            raise

    def save_security_questions(self, user_id, questions):
        """
        Save security questions for a user.
        questions: list of {'question': str, 'answer': str}
        """
        import json
        try:
            # Hash the answers for security
            hashed_questions = []
            for q in questions:
                hashed_answer = bcrypt.hashpw(
                    q['answer'].lower().strip().encode('utf-8'),
                    bcrypt.gensalt()
                ).decode('utf-8')
                hashed_questions.append({
                    'question': q['question'],
                    'answer_hash': hashed_answer
                })
            
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE historian_meta.users 
                        SET security_questions = %s 
                        WHERE id = %s
                    """, (json.dumps(hashed_questions), user_id))
                    conn.commit()
            return True
        except Exception as e:
            logger.error(f"Save security questions error: {e}")
            raise

    def get_random_question(self, user_id):
        """Get a random security question for verification"""
        import json
        import random
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT security_questions FROM historian_meta.users WHERE id = %s", (user_id,))
                    row = cur.fetchone()
                    if not row or not row[0]:
                        return None
                    questions = json.loads(row[0]) if isinstance(row[0], str) else row[0]
                    if not questions:
                        return None
                    idx = random.randint(0, len(questions) - 1)
                    return {
                        'index': idx,
                        'question': questions[idx]['question']
                    }
        except Exception as e:
            logger.error(f"Get random question error: {e}")
            raise

    def verify_security_answer(self, user_id, question_index, answer):
        """Verify a security question answer"""
        import json
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT security_questions FROM historian_meta.users WHERE id = %s", (user_id,))
                    row = cur.fetchone()
                    if not row or not row[0]:
                        return False
                    questions = json.loads(row[0]) if isinstance(row[0], str) else row[0]
                    if question_index >= len(questions):
                        return False
                    stored_hash = questions[question_index]['answer_hash']
                    return bcrypt.checkpw(
                        answer.lower().strip().encode('utf-8'),
                        stored_hash.encode('utf-8')
                    )
        except Exception as e:
            logger.error(f"Verify security answer error: {e}")
            raise



    def verify_backup_key(self, username, key):
        """Verify backup key and check expiry"""
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT id, backup_key_hash, backup_key_expiry 
                        FROM historian_meta.users 
                        WHERE username = %s
                    """, (username,))
                    row = cur.fetchone()
                    
                    if not row:
                        return False
                        
                    user_id, key_hash, expiry = row
                    
                    if not key_hash:
                        return False
                        
                    if expiry and datetime.now() > expiry:
                        return False # Expired
                        
                    if bcrypt.checkpw(key.encode('utf-8'), key_hash.encode('utf-8')):
                        return user_id
                        
            return False
        except Exception as e:
            logger.error(f"Verify backup key error: {e}")
            raise

    def reset_password(self, user_id, new_password):
        """Reset password for a user"""
        try:
            if not new_password or len(new_password) < 8:
                raise ValueError("Password must be at least 8 characters")
            hashed = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE historian_meta.users 
                        SET password_hash = %s, failed_login_attempts = 0, lockout_until = NULL
                        WHERE id = %s
                    """, (hashed, user_id))
                    conn.commit()
            return True
        except Exception as e:
            logger.error(f"Reset password error: {e}")
            raise

    def get_user_id_by_username(self, username):
        """Helper to get user ID from username"""
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT id FROM historian_meta.users WHERE username = %s", (username,))
                    row = cur.fetchone()
                    return row[0] if row else None
        except Exception as e:
            logger.error(f"Get user ID error: {e}")
            return None

    def get_system_alerts(self):
        """Get all system alerts"""
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT a.id, a.alert_type, a.message, a.created_at, u.username, a.user_id,
                               u.lockout_until
                        FROM historian_meta.system_alerts a
                        LEFT JOIN historian_meta.users u ON a.user_id = u.id
                        ORDER BY a.created_at DESC
                    """)
                    rows = cur.fetchall()
                    return [{
                        'id': r[0],
                        'type': r[1],
                        'message': r[2],
                        'createdAt': r[3],
                        'username': r[4],
                        'userId': r[5],
                        'lockoutUntil': r[6]
                    } for r in rows]
        except Exception as e:
            logger.error(f"Get alerts error: {e}")
            return []
    
    def unlock_user_account(self, user_id):
        """Unlock a user account by clearing lockout and resetting failed attempts"""
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    # Get username first
                    cur.execute("""
                        SELECT username FROM historian_meta.users WHERE id = %s
                    """, (user_id,))
                    username_row = cur.fetchone()
                    
                    if not username_row:
                        raise ValueError(f"User {user_id} not found")
                    
                    username = username_row[0]
                    
                    # Clear lockout and reset failed login attempts
                    cur.execute("""
                        UPDATE historian_meta.users 
                        SET failed_login_attempts = 0, lockout_until = NULL 
                        WHERE id = %s
                    """, (user_id,))
                    
                    # Create alert for unlock action
                    cur.execute("""
                        INSERT INTO historian_meta.system_alerts (user_id, alert_type, message)
                        VALUES (%s, %s, %s)
                    """, (user_id, 'ACCOUNT_UNLOCKED', f"User {username} account unlocked by admin."))
                    
                    conn.commit()
                    return True
        except Exception as e:
            logger.error(f"Unlock user error: {e}")
            raise
            
    def regenerate_backup_key(self, user_id):
        """Regenerate a new backup key for an existing user"""
        try:
             # Generate Backup Key (6 digit) - Secure
            backup_key = ''.join(secrets.choice(string.digits) for _ in range(6))
            backup_key_hash = bcrypt.hashpw(backup_key.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE historian_meta.users
                        SET backup_key_hash = %s, backup_key_expiry = NOW() + INTERVAL '30 days'
                        WHERE id = %s
                    """, (backup_key_hash, user_id))
                    conn.commit()
            return backup_key
        except Exception as e:
            logger.error(f"Regenerate key error: {e}")
            raise
