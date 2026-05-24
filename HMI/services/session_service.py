"""
Session Service - Session Management and Concurrent Login Prevention
Handles session lifecycle, activity tracking, and timeout enforcement.
"""

import logging
import psycopg2
import db_pool
from psycopg2.extras import RealDictCursor
import secrets
import hashlib

logger = logging.getLogger(__name__)


class SessionService:
    def __init__(self, db_config):
        self.db_config = db_config  # kept for reference only
    
    def _get_conn(self):
        return db_pool.get_conn()
    
    def _hash_token(self, token):
        """Hash session token for storage."""
        return hashlib.sha256(token.encode()).hexdigest()
    
    def _parse_user_agent(self, user_agent):
        """
        Parse user agent string to extract browser, device type, and OS.
        Simple parser for common browsers and devices.
        
        Returns:
            tuple: (device_type, browser, os_name)
        """
        if not user_agent:
            return None, None, None
        
        user_agent_lower = user_agent.lower()
        
        # Detect OS
        os_name = None
        if 'windows' in user_agent_lower:
            os_name = 'Windows'
        elif 'mac os' in user_agent_lower or 'macos' in user_agent_lower:
            os_name = 'macOS'
        elif 'linux' in user_agent_lower:
            os_name = 'Linux'
        elif 'android' in user_agent_lower:
            os_name = 'Android'
        elif 'iphone' in user_agent_lower or 'ipad' in user_agent_lower:
            os_name = 'iOS'
        
        # Detect device type
        device_type = 'desktop'
        if 'mobile' in user_agent_lower or 'android' in user_agent_lower or 'iphone' in user_agent_lower:
            device_type = 'mobile'
        elif 'tablet' in user_agent_lower or 'ipad' in user_agent_lower:
            device_type = 'tablet'
        
        # Detect browser (order matters - check specific ones first)
        browser = None
        if 'edg/' in user_agent_lower or 'edge/' in user_agent_lower:
            browser = 'Edge'
        elif 'chrome/' in user_agent_lower and 'edg/' not in user_agent_lower:
            browser = 'Chrome'
        elif 'firefox/' in user_agent_lower:
            browser = 'Firefox'
        elif 'safari/' in user_agent_lower and 'chrome/' not in user_agent_lower:
            browser = 'Safari'
        elif 'opera/' in user_agent_lower or 'opr/' in user_agent_lower:
            browser = 'Opera'
        elif 'trident/' in user_agent_lower or 'msie' in user_agent_lower:
            browser = 'IE'
        
        return device_type, browser, os_name
    
    # ==================== Session Lifecycle ====================
    
    def create_session(self, user_id, ip_address=None, user_agent=None,
                      device_type=None, browser=None, os_name=None,
                      device_name=None):
        """
        Create a new session for a user.
        Automatically handles concurrent session limits.
        Parses user_agent if device_type, browser, or os_name not provided.

        If user.allow_concurrent_sessions = False (default): existing sessions are
        superseded before the new session is created (§17.3).
        If allow_concurrent_sessions = True (admin/concurrent user): existing sessions
        are preserved and a new session is added alongside them.

        device_name: optional human-readable label, e.g. 'Control Room PC-3'

        Returns:
            tuple: (session_id, session_token)
        """
        try:
            # Parse user agent if device/browser/os not explicitly provided
            if user_agent and (not device_type or not browser or not os_name):
                parsed_device, parsed_browser, parsed_os = self._parse_user_agent(user_agent)
                device_type = device_type or parsed_device
                browser = browser or parsed_browser
                os_name = os_name or parsed_os

            # Generate secure session token
            session_token = secrets.token_urlsafe(32)
            token_hash = self._hash_token(session_token)

            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    # ── Check allow_concurrent_sessions BEFORE creating new session ──
                    # If false (default), supersede all existing active sessions first
                    cur.execute("""
                        SELECT allow_concurrent_sessions
                        FROM historian_meta.users
                        WHERE id = %s
                    """, (user_id,))
                    user_row = cur.fetchone()
                    allow_concurrent = user_row[0] if user_row else False

                    if not allow_concurrent:
                        # Supersede all existing active sessions for this user
                        cur.execute("""
                            UPDATE historian_meta.user_sessions
                            SET is_active = false,
                                logout_time = CURRENT_TIMESTAMP,
                                logout_reason = 'superseded'
                            WHERE user_id = %s AND is_active = true
                        """, (user_id,))
                        logger.debug(
                            "[Session] Superseded %d old session(s) for user %d (single-session mode).",
                            cur.rowcount, user_id
                        )

                    # ── Create the new session via stored procedure ──
                    cur.execute("""
                        SELECT historian_meta.create_session(
                            %s, %s, %s, %s, %s, %s, %s
                        )
                    """, (
                        user_id, token_hash, ip_address, user_agent,
                        device_type, browser, os_name
                    ))
                    session_id = cur.fetchone()[0]

                    # ── Set device_name (additive column, not in stored proc signature) ──
                    if device_name and session_id:
                        safe_name = str(device_name).strip()[:150] or None
                        if safe_name:
                            cur.execute("""
                                UPDATE historian_meta.user_sessions
                                SET device_name = %s
                                WHERE id = %s
                            """, (safe_name, session_id))

                    conn.commit()
                    return session_id, session_token
        except Exception as e:
            logger.error(f"Create session error: {e}")
            raise

    def validate_session_with_expiry(self, session_token) -> dict | None:
        """
        Validate a session token checking BOTH is_active AND expiry.
        Preferred over validate_session() for request middleware because
        it guards against expired rows that background cleanup has not yet processed.

        Returns dict with user info, or None if session is invalid/expired.
        """
        try:
            token_hash = self._hash_token(session_token)
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT s.id AS session_id,
                               s.user_id,
                               s.is_active,
                               s.logout_time,
                               s.forced_logout,
                               s.logout_reason,
                               u.username,
                               u.status AS user_status,
                               -- absolute_timeout from role to derive expires_at if no column
                               NOW() + (COALESCE(r.absolute_timeout_minutes, 480) * INTERVAL '1 minute')
                                   AS computed_expires_at
                        FROM historian_meta.user_sessions s
                        JOIN historian_meta.users u ON u.id = s.user_id
                        LEFT JOIN historian_meta.roles r ON r.id = u.role_id
                        WHERE s.session_token = %s
                    """, (token_hash,))
                    row = cur.fetchone()

            if not row:
                return None
            if not row['is_active']:
                return None
            if row['user_status'] != 'approved':
                return None
            # If logout_time is set and in the past, session ended
            if row['logout_time']:
                return None
            return dict(row)
        except Exception as e:
            logger.error(f"validate_session_with_expiry error: {e}")
            return None
    
    def validate_session(self, session_token):
        """
        Validate a session token and get user info.
        
        Returns:
            dict: Session info with user details, or None if invalid
        """
        try:
            token_hash = self._hash_token(session_token)
            
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT * FROM historian_meta.validate_session(%s)
                    """, (token_hash,))
                    result = cur.fetchone()
                    
                    if result and result['is_valid']:
                        return dict(result)
                    return None
        except Exception as e:
            logger.error(f"Validate session error: {e}")
            return None
    
    def get_session_by_token(self, session_token):
        """
        Get session information by token.
        
        Args:
            session_token: Unhashed session token
        
        Returns:
            dict: Session information or None if not found
        """
        try:
            token_hash = self._hash_token(session_token)
            
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT id, user_id, session_token, ip_address, user_agent,
                               login_time, last_activity, logout_time, 
                               is_active, forced_logout, logout_reason,
                               device_type, browser, os
                        FROM historian_meta.user_sessions
                        WHERE session_token = %s
                    """, (token_hash,))
                    return cur.fetchone()
        except Exception as e:
            logger.error(f"Get session by token error: {e}")
            return None
    
    def update_activity(self, session_token, activity_type='api_call', 
                       activity_details=None):
        """
        Update last activity time for a session.
        
        Returns:
            bool: True if session was updated
        """
        try:
            token_hash = self._hash_token(session_token)
            
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT historian_meta.update_session_activity(
                            %s, %s, %s
                        )
                    """, (token_hash, activity_type, 
                          psycopg2.extras.Json(activity_details) if activity_details else None))
                    result = cur.fetchone()[0]
                    conn.commit()
                    return result
        except Exception as e:
            logger.error(f"Update activity error: {e}")
            return False
    
    def end_session(self, session_token, reason='user_logout', forced=False):
        """
        End a session.
        
        Args:
            session_token: Session token to end
            reason: Reason for logout
            forced: Whether logout was forced (admin/timeout)
        
        Returns:
            bool: True if session was ended
        """
        try:
            token_hash = self._hash_token(session_token)
            
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT historian_meta.end_session(%s, %s, %s)
                    """, (token_hash, reason, forced))
                    result = cur.fetchone()[0]
                    conn.commit()
                    return result
        except Exception as e:
            logger.error(f"End session error: {e}")
            return False
    
    def end_session_by_id(self, session_id, reason='admin_terminate', forced=True):
        """
        End a session by session ID (for admin termination).
        
        Args:
            session_id: Session ID to end
            reason: Reason for logout
            forced: Whether logout was forced (default True for admin actions)
        
        Returns:
            bool: True if session was ended
        """
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE historian_meta.user_sessions
                        SET is_active = FALSE,
                            forced_logout = %s,
                            logout_time = CURRENT_TIMESTAMP,
                            logout_reason = %s
                        WHERE id = %s AND is_active = TRUE
                    """, (forced, reason, session_id))
                    conn.commit()
                    return cur.rowcount > 0
        except Exception as e:
            logger.error(f"End session by ID error: {e}")
            return False
    
    def terminate_user_sessions(self, user_id, reason='admin_terminate'):
        """
        Terminate all active sessions for a user.

        Returns:
            int: Number of sessions terminated
        """
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT historian_meta.terminate_user_sessions(%s, %s)
                    """, (user_id, reason))
                    count = cur.fetchone()[0]
                    conn.commit()
                    return count
        except Exception as e:
            logger.error(f"Terminate sessions error: {e}")
            return 0

    def end_all_user_sessions(self, user_id, except_token=None, reason='user_logout'):
        """
        End all active sessions for a user, optionally keeping one session alive.
        Used by the 'End All Others' button in SessionManager.

        Returns:
            int: Number of sessions ended
        """
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    if except_token:
                        token_hash = self._hash_token(except_token)
                        cur.execute("""
                            UPDATE historian_meta.user_sessions
                            SET is_active = false,
                                logout_time = NOW(),
                                logout_reason = %s
                            WHERE user_id = %s
                              AND is_active = true
                              AND token_hash != %s
                        """, (reason, user_id, token_hash))
                    else:
                        cur.execute("""
                            UPDATE historian_meta.user_sessions
                            SET is_active = false,
                                logout_time = NOW(),
                                logout_reason = %s
                            WHERE user_id = %s AND is_active = true
                        """, (reason, user_id))
                    count = cur.rowcount
                    conn.commit()
            logger.info(f"[Session] end_all_user_sessions: ended {count} sessions for user {user_id}")
            return count
        except Exception as e:
            logger.error(f"end_all_user_sessions error: {e}")
            return 0
    
    def cleanup_expired_sessions(self):
        """
        Cleanup expired sessions based on idle and absolute timeouts.
        
        Returns:
            dict: Counts of expired sessions by type
        """
        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("SELECT * FROM historian_meta.cleanup_expired_sessions()")
                    results = cur.fetchall()
                    conn.commit()
                    
                    return {
                        row['expired_type']: row['expired_count']
                        for row in results
                    }
        except Exception as e:
            logger.error(f"Cleanup expired sessions error: {e}")
            return {}
    
    # ==================== Session Queries ====================
    
    def get_active_sessions(self, user_id=None, include_expired_soon=False):
        """Get list of active sessions."""
        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    query = "SELECT * FROM historian_meta.active_sessions WHERE 1=1"
                    params = []
                    
                    if user_id:
                        query += " AND user_id = %s"
                        params.append(user_id)
                    
                    if not include_expired_soon:
                        query += " AND NOT is_idle_expired AND NOT is_absolute_expired"
                    
                    query += " ORDER BY last_activity DESC"
                    
                    cur.execute(query, params)
                    return cur.fetchall()
        except Exception as e:
            logger.error(f"Get active sessions error: {e}")
            return []
    
    def get_user_concurrent_sessions(self, user_id=None):
        """Get concurrent session counts by user."""
        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    if user_id:
                        cur.execute("""
                            SELECT * FROM historian_meta.user_concurrent_sessions
                            WHERE user_id = %s
                        """, (user_id,))
                    else:
                        cur.execute("""
                            SELECT * FROM historian_meta.user_concurrent_sessions
                            ORDER BY active_session_count DESC
                        """)
                    return cur.fetchall()
        except Exception as e:
            logger.error(f"Get concurrent sessions error: {e}")
            return []
    
    def get_session_history(self, user_id, days=30, limit=100):
        """Get session history for a user."""
        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT id, login_time, logout_time, 
                               EXTRACT(EPOCH FROM (COALESCE(logout_time, CURRENT_TIMESTAMP) - login_time))/60 as duration_minutes,
                               ip_address, device_type, browser, is_active,
                               forced_logout, logout_reason
                        FROM historian_meta.user_sessions
                        WHERE user_id = %s
                        AND login_time >= CURRENT_TIMESTAMP - %s * INTERVAL '1 day'
                        ORDER BY login_time DESC
                        LIMIT %s
                    """, (user_id, days, limit))
                    return cur.fetchall()
        except Exception as e:
            logger.error(f"Get session history error: {e}")
            return []
    
    def check_session_limit(self, user_id):
        """
        Check if user has reached concurrent session limit.
        
        Returns:
            dict: {at_limit: bool, current_count: int, max_allowed: int}
        """
        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT 
                            COALESCE(r.max_concurrent_sessions, 1) as max_allowed,
                            COUNT(s.id) as current_count,
                            COUNT(s.id) >= COALESCE(r.max_concurrent_sessions, 1) as at_limit
                        FROM historian_meta.users u
                        LEFT JOIN historian_meta.roles r ON u.role_id = r.id
                        LEFT JOIN historian_meta.user_sessions s ON u.id = s.user_id AND s.is_active = TRUE
                        WHERE u.id = %s
                        GROUP BY r.max_concurrent_sessions
                    """, (user_id,))
                    row = cur.fetchone()
                    return dict(row) if row else {'at_limit': False, 'current_count': 0, 'max_allowed': 1}
        except Exception as e:
            logger.error(f"Check session limit error: {e}")
            return {'at_limit': False, 'current_count': 0, 'max_allowed': 1}
    
    def get_session_by_id(self, session_id):
        """Get session details by ID."""
        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT s.id, s.user_id, u.username, s.login_time,
                               s.last_activity, s.logout_time, s.is_active,
                               s.ip_address, s.device_type, s.browser, s.os,
                               s.forced_logout, s.logout_reason
                        FROM historian_meta.user_sessions s
                        JOIN historian_meta.users u ON s.user_id = u.id
                        WHERE s.id = %s
                    """, (session_id,))
                    return cur.fetchone()
        except Exception as e:
            logger.error(f"Get session by ID error: {e}")
            return None
    
    def get_expiring_sessions(self, warning_minutes=15):
        """Get sessions that are about to expire."""
        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT s.id, s.user_id, u.username, s.session_token,
                               EXTRACT(EPOCH FROM (r.idle_timeout_minutes::INTEGER * INTERVAL '1 minute' - 
                                                   (CURRENT_TIMESTAMP - s.last_activity)))/60 as minutes_until_idle_expiry
                        FROM historian_meta.user_sessions s
                        JOIN historian_meta.users u ON s.user_id = u.id
                        LEFT JOIN historian_meta.roles r ON u.role_id = r.id
                        WHERE s.is_active = TRUE
                        AND r.idle_timeout_minutes * INTERVAL '1 minute' - 
                            (CURRENT_TIMESTAMP - s.last_activity) <= %s * INTERVAL '1 minute'
                        AND r.idle_timeout_minutes * INTERVAL '1 minute' - 
                            (CURRENT_TIMESTAMP - s.last_activity) > INTERVAL '0 minutes'
                    """, (warning_minutes,))
                    return cur.fetchall()
        except Exception as e:
            logger.error(f"Get expiring sessions error: {e}")
            return []
    
    # ==================== Admin Functions ====================
    
    def force_logout_session(self, session_id, admin_user_id, reason='admin_action'):
        """Force logout a specific session (admin only)."""
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    # Get session token
                    cur.execute("""
                        SELECT session_token FROM historian_meta.user_sessions
                        WHERE id = %s AND is_active = TRUE
                    """, (session_id,))
                    row = cur.fetchone()
                    
                    if not row:
                        return False
                    
                    session_token = row[0]
                    
                    # End the session
                    cur.execute("""
                        SELECT historian_meta.end_session(%s, %s, TRUE)
                    """, (session_token, reason))
                    
                    conn.commit()
                    return True
        except Exception as e:
            logger.error(f"Force logout error: {e}")
            return False
