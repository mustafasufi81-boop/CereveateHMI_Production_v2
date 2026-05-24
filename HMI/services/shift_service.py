"""
Shift Service - Shift management and validation
Handles shift-based access control and handover notes.
"""

import logging
import psycopg2
import db_pool
from psycopg2.extras import RealDictCursor
from datetime import datetime

logger = logging.getLogger(__name__)


class ShiftService:
    def __init__(self, db_config):
        self.db_config = db_config  # kept for reference only
    
    def _get_conn(self):
        return db_pool.get_conn()
    
    # ==================== Current Shift ====================
    
    def get_current_shift(self, check_time=None):
        """
        Get currently active shift.
        
        Args:
            check_time: Optional datetime to check (defaults to current time)
        
        Returns:
            dict: Current shift info or None
        """
        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT * FROM historian_meta.get_current_shift(%s)
                    """, (check_time,))
                    return cur.fetchone()
        except Exception as e:
            logger.error(f"Get current shift error: {e}")
            return None
    
    def get_active_shifts(self):
        """Get all currently active shifts."""
        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT * FROM historian_meta.current_active_shifts
                        WHERE is_currently_active = TRUE AND is_valid_day = TRUE
                    """)
                    return cur.fetchall()
        except Exception as e:
            logger.error(f"Get active shifts error: {e}")
            return []
    
    # ==================== User Shift Access ====================
    
    def check_user_shift_access(self, user_id, check_time=None):
        """
        Check if user has access in current shift.
        
        Returns:
            dict: Access status with warning messages
        """
        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT * FROM historian_meta.check_user_shift_access(%s, %s)
                    """, (user_id, check_time))
                    return cur.fetchone()
        except Exception as e:
            logger.error(f"Check user shift access error: {e}")
            return {'has_access': True, 'warning_message': None}
    
    def get_user_current_shift_status(self, user_id=None):
        """Get current shift status for user(s)."""
        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    if user_id:
                        cur.execute("""
                            SELECT * FROM historian_meta.user_current_shift_status
                            WHERE user_id = %s
                        """, (user_id,))
                    else:
                        cur.execute("""
                            SELECT * FROM historian_meta.user_current_shift_status
                        """)
                    return cur.fetchall()
        except Exception as e:
            logger.error(f"Get user shift status error: {e}")
            return []
    
    # ==================== Shift Management ====================
    
    def get_all_shifts(self):
        """Get all defined shifts."""
        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT * FROM historian_meta.shifts
                        WHERE is_active = TRUE
                        ORDER BY shift_code
                    """)
                    return cur.fetchall()
        except Exception as e:
            logger.error(f"Get all shifts error: {e}")
            return []
    
    def create_shift(self, shift_data):
        """Create a new shift."""
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO historian_meta.shifts (
                            shift_code, shift_name, description,
                            start_time, end_time, days_of_week, shift_type
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                    """, (
                        shift_data['shift_code'],
                        shift_data['shift_name'],
                        shift_data.get('description'),
                        shift_data['start_time'],
                        shift_data['end_time'],
                        shift_data['days_of_week'],
                        shift_data.get('shift_type', 'regular')
                    ))
                    shift_id = cur.fetchone()[0]
                    conn.commit()
                    return shift_id
        except Exception as e:
            logger.error(f"Create shift error: {e}")
            raise
    
    # ==================== User Shift Assignments ====================
    
    def assign_user_to_shift(self, user_id, shift_id, is_primary=True,
                            valid_from=None, valid_until=None, assigned_by=None):
        """Assign user to a shift."""
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO historian_meta.user_shift_assignments (
                            user_id, shift_id, is_primary_shift,
                            valid_from, valid_until, assigned_by
                        ) VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (user_id, shift_id, valid_from) DO UPDATE
                        SET is_primary_shift = EXCLUDED.is_primary_shift,
                            valid_until = EXCLUDED.valid_until
                        RETURNING id
                    """, (user_id, shift_id, is_primary, valid_from, valid_until, assigned_by))
                    assignment_id = cur.fetchone()[0]
                    conn.commit()
                    return assignment_id
        except Exception as e:
            logger.error(f"Assign user to shift error: {e}")
            raise
    
    def get_user_shift_assignments(self, user_id):
        """Get shift assignments for a user."""
        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT usa.*, s.shift_code, s.shift_name,
                               s.start_time, s.end_time, s.days_of_week
                        FROM historian_meta.user_shift_assignments usa
                        JOIN historian_meta.shifts s ON usa.shift_id = s.id
                        WHERE usa.user_id = %s
                        AND (usa.valid_until IS NULL OR usa.valid_until >= CURRENT_DATE)
                        ORDER BY usa.is_primary_shift DESC, s.shift_code
                    """, (user_id,))
                    return cur.fetchall()
        except Exception as e:
            logger.error(f"Get user shift assignments error: {e}")
            return []
    
    def remove_user_shift_assignment(self, assignment_id):
        """Remove a shift assignment."""
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        DELETE FROM historian_meta.user_shift_assignments
                        WHERE id = %s
                    """, (assignment_id,))
                    conn.commit()
                    return cur.rowcount > 0
        except Exception as e:
            logger.error(f"Remove shift assignment error: {e}")
            raise
    
    # ==================== Shift Handover Notes ====================
    
    def add_handover_note(self, from_shift_id, to_shift_id, created_by,
                         category, priority, subject, content):
        """Add a shift handover note."""
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT historian_meta.add_shift_handover_note(
                            %s, %s, %s, %s, %s, %s, %s
                        )
                    """, (from_shift_id, to_shift_id, created_by, 
                          category, priority, subject, content))
                    note_id = cur.fetchone()[0]
                    conn.commit()
                    return note_id
        except Exception as e:
            logger.error(f"Add handover note error: {e}")
            raise
    
    def get_handover_notes(self, shift_id=None, unacknowledged_only=False, days=7):
        """Get handover notes for a shift."""
        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    query = """
                        SELECT shn.*, 
                               u1.username as created_by_username,
                               u2.username as acknowledged_by_username,
                               s1.shift_name as from_shift_name,
                               s2.shift_name as to_shift_name
                        FROM historian_meta.shift_handover_notes shn
                        LEFT JOIN historian_meta.users u1 ON shn.created_by = u1.id
                        LEFT JOIN historian_meta.users u2 ON shn.acknowledged_by = u2.id
                        LEFT JOIN historian_meta.shifts s1 ON shn.from_shift_id = s1.id
                        LEFT JOIN historian_meta.shifts s2 ON shn.to_shift_id = s2.id
                        WHERE shn.handover_date >= CURRENT_DATE - %s * INTERVAL '1 day'
                    """
                    params = [days]
                    
                    if shift_id:
                        query += " AND shn.to_shift_id = %s"
                        params.append(shift_id)
                    
                    if unacknowledged_only:
                        query += " AND shn.is_acknowledged = FALSE"
                    
                    query += " ORDER BY shn.priority DESC, shn.created_at DESC"
                    
                    cur.execute(query, params)
                    return cur.fetchall()
        except Exception as e:
            logger.error(f"Get handover notes error: {e}")
            return []
    
    def acknowledge_handover_note(self, note_id, acknowledged_by):
        """Acknowledge a handover note."""
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT historian_meta.acknowledge_handover_note(%s, %s)
                    """, (note_id, acknowledged_by))
                    result = cur.fetchone()[0]
                    conn.commit()
                    return result
        except Exception as e:
            logger.error(f"Acknowledge handover note error: {e}")
            return False
