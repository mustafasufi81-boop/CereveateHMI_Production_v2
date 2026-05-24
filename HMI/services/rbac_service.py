"""
RBAC Service - Role-Based Access Control
Handles roles, permissions, and user approval.
"""

import logging
import psycopg2
import db_pool
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)


class RBACService:
    def __init__(self, db_config):
        self.db_config = db_config  # kept for reference only
    
    def _get_conn(self):
        return db_pool.get_conn()
    
    # ==================== User Management ====================
    
    def get_all_users(self):
        """Get all users with their roles"""
        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT u.id, u.username, u.status, u.mfa_enabled, u.role_id,
                               r.name as role_name, r.is_admin
                        FROM historian_meta.users u
                        LEFT JOIN historian_meta.roles r ON u.role_id = r.id
                        ORDER BY u.id
                    """)
                    return cur.fetchall()
        except Exception as e:
            logger.error(f"Get all users error: {e}")
            raise

    def get_user_by_id(self, user_id):
        """Get user by ID with role info"""
        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT u.id, u.username, u.status, u.mfa_enabled, u.role_id,
                               r.name as role_name, r.is_admin
                        FROM historian_meta.users u
                        LEFT JOIN historian_meta.roles r ON u.role_id = r.id
                        WHERE u.id = %s
                    """, (user_id,))
                    return cur.fetchone()
        except Exception as e:
            logger.error(f"Get user error: {e}")
            raise

    def approve_user(self, user_id, role_id=None):
        """Approve a pending user and optionally assign role"""
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    if role_id:
                        cur.execute("""
                            UPDATE historian_meta.users 
                            SET status = 'approved', role_id = %s 
                            WHERE id = %s
                        """, (role_id, user_id))
                    else:
                        cur.execute("""
                            UPDATE historian_meta.users 
                            SET status = 'approved' 
                            WHERE id = %s
                        """, (user_id,))
                    conn.commit()
                    return cur.rowcount > 0
        except Exception as e:
            logger.error(f"Approve user error: {e}")
            raise

    def revoke_user(self, user_id):
        """Revoke user access"""
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE historian_meta.users 
                        SET status = 'revoked' 
                        WHERE id = %s
                    """, (user_id,))
                    conn.commit()
                    return cur.rowcount > 0
        except Exception as e:
            logger.error(f"Revoke user error: {e}")
            raise

    def assign_role(self, user_id, role_id):
        """Assign a role to a user"""
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE historian_meta.users 
                        SET role_id = %s 
                        WHERE id = %s
                    """, (role_id, user_id))
                    conn.commit()
                    return cur.rowcount > 0
        except Exception as e:
            logger.error(f"Assign role error: {e}")
            raise

    def get_user_status(self, user_id):
        """Get user status"""
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT status FROM historian_meta.users WHERE id = %s", (user_id,))
                    row = cur.fetchone()
                    return row[0] if row else None
        except Exception as e:
            logger.error(f"Get user status error: {e}")
            raise

    def is_user_admin(self, user_id):
        """Check if user has admin role"""
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT r.is_admin 
                        FROM historian_meta.users u
                        JOIN historian_meta.roles r ON u.role_id = r.id
                        WHERE u.id = %s
                    """, (user_id,))
                    row = cur.fetchone()
                    return row[0] if row else False
        except Exception as e:
            logger.error(f"Check admin error: {e}")
            raise

    # ==================== Role Management ====================

    def get_all_roles(self):
        """Get all roles"""
        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT id, name, description, is_admin, created_at
                        FROM historian_meta.roles
                        ORDER BY id
                    """)
                    return cur.fetchall()
        except Exception as e:
            logger.error(f"Get roles error: {e}")
            raise

    def create_role(self, name, description=None, is_admin=False):
        """Create a new role"""
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO historian_meta.roles (name, description, is_admin)
                        VALUES (%s, %s, %s)
                        RETURNING id
                    """, (name, description, is_admin))
                    role_id = cur.fetchone()[0]
                    conn.commit()
                    return role_id
        except Exception as e:
            logger.error(f"Create role error: {e}")
            raise

    def update_role(self, role_id, name=None, description=None, is_admin=None):
        """Update role details"""
        try:
            updates = []
            params = []
            if name is not None:
                updates.append("name = %s")
                params.append(name)
            if description is not None:
                updates.append("description = %s")
                params.append(description)
            if is_admin is not None:
                updates.append("is_admin = %s")
                params.append(is_admin)
            
            if not updates:
                return False
            
            params.append(role_id)
            query = f"UPDATE historian_meta.roles SET {', '.join(updates)} WHERE id = %s"
            
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, params)
                    conn.commit()
                    return cur.rowcount > 0
        except Exception as e:
            logger.error(f"Update role error: {e}")
            raise

    def delete_role(self, role_id):
        """Delete a role"""
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM historian_meta.roles WHERE id = %s", (role_id,))
                    conn.commit()
                    return cur.rowcount > 0
        except Exception as e:
            logger.error(f"Delete role error: {e}")
            raise

    # ==================== Tag Permissions ====================

    def get_role_tag_permissions(self, role_id):
        """Get tag permissions for a role"""
        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT id, plant, area, can_view, can_write
                        FROM historian_meta.role_tag_permissions
                        WHERE role_id = %s
                        ORDER BY plant, area
                    """, (role_id,))
                    return cur.fetchall()
        except Exception as e:
            logger.error(f"Get tag permissions error: {e}")
            raise

    def add_tag_permission(self, role_id, plant, area, can_view=True, can_write=False):
        """Add tag permission for a role"""
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO historian_meta.role_tag_permissions 
                        (role_id, plant, area, can_view, can_write)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (role_id, plant, area) DO UPDATE
                        SET can_view = EXCLUDED.can_view, can_write = EXCLUDED.can_write
                        RETURNING id
                    """, (role_id, plant, area, can_view, can_write))
                    perm_id = cur.fetchone()[0]
                    conn.commit()
                    return perm_id
        except Exception as e:
            logger.error(f"Add tag permission error: {e}")
            raise

    def remove_tag_permission(self, permission_id):
        """Remove a tag permission"""
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM historian_meta.role_tag_permissions WHERE id = %s",
                        (permission_id,)
                    )
                    conn.commit()
                    return cur.rowcount > 0
        except Exception as e:
            logger.error(f"Remove tag permission error: {e}")
            raise

    def get_user_allowed_tags(self, user_id):
        """Get list of plant/area combinations user can access"""
        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    # First check if user is admin (full access)
                    cur.execute("""
                        SELECT r.is_admin 
                        FROM historian_meta.users u
                        JOIN historian_meta.roles r ON u.role_id = r.id
                        WHERE u.id = %s
                    """, (user_id,))
                    row = cur.fetchone()
                    if row and row['is_admin']:
                        return None  # None means full access
                    
                    # Get permitted plant/area combinations
                    cur.execute("""
                        SELECT rtp.plant, rtp.area, rtp.can_view, rtp.can_write
                        FROM historian_meta.role_tag_permissions rtp
                        JOIN historian_meta.users u ON rtp.role_id = u.role_id
                        WHERE u.id = %s AND rtp.can_view = TRUE
                    """, (user_id,))
                    return cur.fetchall()
        except Exception as e:
            logger.error(f"Get user allowed tags error: {e}")
            raise

    # ==================== Alarm Permissions ====================

    def get_role_alarm_permissions(self, role_id):
        """Get alarm permissions for a role"""
        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT id, alarm_category, can_view, can_acknowledge, can_silence
                        FROM historian_meta.role_alarm_permissions
                        WHERE role_id = %s
                        ORDER BY alarm_category
                    """, (role_id,))
                    return cur.fetchall()
        except Exception as e:
            logger.error(f"Get alarm permissions error: {e}")
            raise

    def add_alarm_permission(self, role_id, alarm_category, can_view=True, 
                             can_acknowledge=False, can_silence=False, 
                             can_clear=False, requires_approval_to_clear=False):
        """Add alarm permission for a role"""
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO historian_meta.role_alarm_permissions 
                        (role_id, alarm_category, can_view, can_acknowledge, can_silence, can_clear, requires_approval_to_clear)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (role_id, alarm_category) DO UPDATE
                        SET can_view = EXCLUDED.can_view, 
                            can_acknowledge = EXCLUDED.can_acknowledge,
                            can_silence = EXCLUDED.can_silence,
                            can_clear = EXCLUDED.can_clear,
                            requires_approval_to_clear = EXCLUDED.requires_approval_to_clear
                        RETURNING id
                    """, (role_id, alarm_category, can_view, can_acknowledge, can_silence, can_clear, requires_approval_to_clear))
                    perm_id = cur.fetchone()[0]
                    conn.commit()
                    return perm_id
        except Exception as e:
            logger.error(f"Add alarm permission error: {e}")
            raise

    def remove_alarm_permission(self, permission_id):
        """Remove an alarm permission"""
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM historian_meta.role_alarm_permissions WHERE id = %s",
                        (permission_id,)
                    )
                    conn.commit()
                    return cur.rowcount > 0
        except Exception as e:
            logger.error(f"Remove alarm permission error: {e}")
            raise

    def get_user_allowed_alarms(self, user_id):
        """Get alarm categories user can access"""
        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    # Check if admin
                    cur.execute("""
                        SELECT r.is_admin 
                        FROM historian_meta.users u
                        JOIN historian_meta.roles r ON u.role_id = r.id
                        WHERE u.id = %s
                    """, (user_id,))
                    row = cur.fetchone()
                    if row and row['is_admin']:
                        return None  # Full access
                    
                    cur.execute("""
                        SELECT rap.alarm_category, rap.can_view, 
                               rap.can_acknowledge, rap.can_silence,
                               rap.can_clear, rap.requires_approval_to_clear
                        FROM historian_meta.role_alarm_permissions rap
                        JOIN historian_meta.users u ON rap.role_id = u.role_id
                        WHERE u.id = %s AND rap.can_view = TRUE
                    """, (user_id,))
                    return cur.fetchall()
        except Exception as e:
            logger.error(f"Get user allowed alarms error: {e}")
            raise

    def can_user_clear_alarm(self, user_id, alarm_category=None):
        """Check if user can clear alarms (optionally for specific category)"""
        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    # Check if admin (full access)
                    cur.execute("""
                        SELECT r.is_admin 
                        FROM historian_meta.users u
                        JOIN historian_meta.roles r ON u.role_id = r.id
                        WHERE u.id = %s
                    """, (user_id,))
                    row = cur.fetchone()
                    if row and row['is_admin']:
                        return True  # Admins can always clear
                    
                    # Check role-based clear permission
                    if alarm_category:
                        cur.execute("""
                            SELECT can_clear
                            FROM historian_meta.role_alarm_permissions rap
                            JOIN historian_meta.users u ON rap.role_id = u.role_id
                            WHERE u.id = %s AND rap.alarm_category = %s
                        """, (user_id, alarm_category))
                    else:
                        # Check if user can clear ANY alarm category
                        cur.execute("""
                            SELECT can_clear
                            FROM historian_meta.role_alarm_permissions rap
                            JOIN historian_meta.users u ON rap.role_id = u.role_id
                            WHERE u.id = %s
                            LIMIT 1
                        """, (user_id,))
                    
                    result = cur.fetchone()
                    return result and result['can_clear'] if result else False
        except Exception as e:
            logger.error(f"Can clear alarm check failed: {e}")
            return False

    def requires_approval_to_clear_alarm(self, user_id, alarm_category=None):
        """Check if user needs approval to clear alarms"""
        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    # Admins don't need approval
                    cur.execute("""
                        SELECT r.is_admin 
                        FROM historian_meta.users u
                        JOIN historian_meta.roles r ON u.role_id = r.id
                        WHERE u.id = %s
                    """, (user_id,))
                    row = cur.fetchone()
                    if row and row['is_admin']:
                        return False  # Admins don't need approval
                    
                    # Check if approval required
                    if alarm_category:
                        cur.execute("""
                            SELECT requires_approval_to_clear
                            FROM historian_meta.role_alarm_permissions rap
                            JOIN historian_meta.users u ON rap.role_id = u.role_id
                            WHERE u.id = %s AND rap.alarm_category = %s
                        """, (user_id, alarm_category))
                    else:
                        cur.execute("""
                            SELECT requires_approval_to_clear
                            FROM historian_meta.role_alarm_permissions rap
                            JOIN historian_meta.users u ON rap.role_id = u.role_id
                            WHERE u.id = %s
                            LIMIT 1
                        """, (user_id,))
                    
                    result = cur.fetchone()
                    return result and result['requires_approval_to_clear'] if result else True
        except Exception as e:
            logger.error(f"Approval check failed: {e}")
            return True  # Default to requiring approval for safety

    # ==================== Available Plants/Areas ====================

    def get_available_plants_areas(self):
        """Get distinct plant/area combinations from tag_master"""
        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT DISTINCT plant, area 
                        FROM historian_meta.tag_master
                        WHERE plant IS NOT NULL
                        ORDER BY plant, area
                    """)
                    return cur.fetchall()
        except Exception as e:
            logger.error(f"Get plants/areas error: {e}")
            raise

    # ==================== Specific Tag Permissions ====================

    def get_role_specific_tag_permissions(self, role_id):
        """Get specific tag permissions for a role"""
        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT rstp.id, rstp.tag_id, rstp.can_view, rstp.can_write,
                               tm.tag_name, tm.plant, tm.area, tm.equipment
                        FROM historian_meta.role_specific_tag_permissions rstp
                        LEFT JOIN historian_meta.tag_master tm ON rstp.tag_id::text = tm.tag_id
                        WHERE rstp.role_id = %s
                        ORDER BY rstp.tag_id
                    """, (role_id,))
                    return cur.fetchall()
        except Exception as e:
            logger.error(f"Get specific tag permissions error: {e}")
            raise

    def add_specific_tag_permission(self, role_id, tag_id, can_view=True, can_write=False):
        """Add specific tag permission for a role
        
        Args:
            tag_id: Can be either integer tag_id or string tag_name (will be looked up)
        """
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    # If tag_id is a string (tag name), look up the integer tag_id
                    if isinstance(tag_id, str):
                        cur.execute("""
                            SELECT tag_id FROM historian_meta.tag_master 
                            WHERE tag_id = %s OR tag_name = %s
                            LIMIT 1
                        """, (tag_id, tag_id))
                        result = cur.fetchone()
                        if not result:
                            raise ValueError(f"Tag not found: {tag_id}")
                        # tag_master.tag_id is VARCHAR, keep as string
                        actual_tag_id = result[0]
                    else:
                        actual_tag_id = tag_id
                    
                    cur.execute("""
                        INSERT INTO historian_meta.role_specific_tag_permissions 
                        (role_id, tag_id, can_view, can_write)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (role_id, tag_id) DO UPDATE
                        SET can_view = EXCLUDED.can_view, can_write = EXCLUDED.can_write
                        RETURNING id
                    """, (role_id, actual_tag_id, can_view, can_write))
                    perm_id = cur.fetchone()[0]
                    conn.commit()
                    return perm_id
        except Exception as e:
            logger.error(f"Add specific tag permission error: {e}")
            raise

    def remove_specific_tag_permission(self, permission_id):
        """Remove a specific tag permission"""
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM historian_meta.role_specific_tag_permissions WHERE id = %s",
                        (permission_id,)
                    )
                    conn.commit()
                    return cur.rowcount > 0
        except Exception as e:
            logger.error(f"Remove specific tag permission error: {e}")
            raise

    def get_available_tags(self):
        """Get all available tags from tag_master for selection"""
        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT tag_id, tag_name, plant, area, equipment, description
                        FROM historian_meta.tag_master
                        WHERE enabled = true
                        ORDER BY tag_id
                    """)
                    return cur.fetchall()
        except Exception as e:
            logger.error(f"Get available tags error: {e}")
            raise

    def get_user_allowed_specific_tags(self, user_id):
        """Get specific tag IDs user can access via specific tag permissions"""
        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT rstp.tag_id, rstp.can_view, rstp.can_write
                        FROM historian_meta.role_specific_tag_permissions rstp
                        JOIN historian_meta.users u ON rstp.role_id = u.role_id
                        WHERE u.id = %s AND rstp.can_view = TRUE
                    """, (user_id,))
                    return cur.fetchall()
        except Exception as e:
            logger.error(f"Get user allowed specific tags error: {e}")
            raise

    def seed_default_module_permissions(self):
        """
        Ensures every role in historian_meta.roles has a row in
        role_module_permissions for every module.  Called once at startup.

        Rules applied (when no existing row for that role+module):
          Admin role (is_admin=True)  → all True
          Viewer role (name='viewer') → canView=False for analytics + admin
          All other roles             → canView=True, others False (except admin module)
        """
        MODULES = ['hmi', 'reports', 'analytics', 'alarms', 'admin']
        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("SELECT id, name, is_admin FROM historian_meta.roles")
                    roles = cur.fetchall()
                    for role in roles:
                        role_id   = role['id']
                        is_admin  = role['is_admin']
                        is_viewer   = (role['name'] or '').lower() == 'viewer'
                        is_engineer = (role['name'] or '').lower() == 'engineer'
                        for module in MODULES:
                            if is_admin:
                                cv, co, cg, cc = True, True, True, True
                            elif module == 'admin':
                                cv, co, cg, cc = False, False, False, False
                            elif is_viewer and module == 'analytics':
                                cv, co, cg, cc = False, False, False, False
                            elif is_viewer:
                                cv, co, cg, cc = True, False, False, False
                            elif module == 'alarms':
                                # Engineer: can ack/clear alarms and generate alarm reports
                                cv, co, cg, cc = True, is_engineer, is_engineer, False
                            elif module == 'reports':
                                # Engineer: can download / generate reports (CSV etc.)
                                cv, co, cg, cc = True, False, is_engineer, False
                            else:
                                cv, co, cg, cc = True, False, False, False
                            cur.execute("""
                                INSERT INTO historian_meta.role_module_permissions
                                    (role_id, module, can_view, can_operate, can_generate, can_configure)
                                VALUES (%s, %s, %s, %s, %s, %s)
                                ON CONFLICT (role_id, module) DO NOTHING
                            """, (role_id, module, cv, co, cg, cc))
                conn.commit()
                logger.info("[RBAC] Default module permissions seeded successfully")
        except Exception as e:
            logger.warning(f"[RBAC] seed_default_module_permissions failed (non-fatal): {e}")

    # ==================== Module Permissions ====================

    def get_role_module_permissions(self, role_id):
        """Return all module permission rows for a given role (for admin UI)."""
        MODULES = ['hmi', 'reports', 'analytics', 'alarms', 'admin']
        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT module, can_view, can_operate, can_generate, can_configure
                        FROM historian_meta.role_module_permissions
                        WHERE role_id = %s
                    """, (role_id,))
                    rows = {r['module']: r for r in cur.fetchall()}
            # Return every module (fill missing with all-false)
            return [
                {
                    'module': m,
                    'can_view':      bool(rows.get(m, {}).get('can_view', False)),
                    'can_operate':   bool(rows.get(m, {}).get('can_operate', False)),
                    'can_generate':  bool(rows.get(m, {}).get('can_generate', False)),
                    'can_configure': bool(rows.get(m, {}).get('can_configure', False)),
                }
                for m in MODULES
            ]
        except Exception as e:
            logger.error(f'get_role_module_permissions error: {e}')
            raise

    def update_role_module_permission(self, role_id, module, can_view, can_operate, can_generate, can_configure):
        """Upsert a single module permission row for a role."""
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO historian_meta.role_module_permissions
                            (role_id, module, can_view, can_operate, can_generate, can_configure)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (role_id, module) DO UPDATE
                            SET can_view       = EXCLUDED.can_view,
                                can_operate    = EXCLUDED.can_operate,
                                can_generate   = EXCLUDED.can_generate,
                                can_configure  = EXCLUDED.can_configure
                    """, (role_id, module, can_view, can_operate, can_generate, can_configure))
                conn.commit()
        except Exception as e:
            logger.error(f'update_role_module_permission error: {e}')
            raise

    def get_user_module_permissions(self, user_id):
        """
        Returns a dict of {module: {can_view, can_operate, can_generate, can_configure}}
        for the given user based on their assigned role.
        Falls back to admin-full / viewer-only if table is missing.
        """
        MODULES = ['hmi', 'reports', 'analytics', 'alarms', 'admin']
        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT p.module, p.can_view, p.can_operate, p.can_generate, p.can_configure
                        FROM historian_meta.role_module_permissions p
                        JOIN historian_meta.users u ON u.role_id = p.role_id
                        WHERE u.id = %s
                    """, (user_id,))
                    rows = cur.fetchall()
                    if rows:
                        return {
                            row['module']: {
                                'canView':     row['can_view'],
                                'canOperate':  row['can_operate'],
                                'canGenerate': row['can_generate'],
                                'canConfigure':row['can_configure'],
                            }
                            for row in rows
                        }
                    # No rows: check if user is admin and return sensible fallback
                    cur.execute("""
                        SELECT r.is_admin, r.name as role_name FROM historian_meta.users u
                        JOIN historian_meta.roles r ON r.id = u.role_id
                        WHERE u.id = %s
                    """, (user_id,))
                    role_row = cur.fetchone()
                    is_admin  = role_row['is_admin'] if role_row else False
                    role_name = (role_row.get('role_name') or '').lower() if role_row else ''
                    is_viewer = (role_name == 'viewer')
                    full      = {'canView': True,  'canOperate': True,  'canGenerate': True,  'canConfigure': True}
                    view      = {'canView': True,  'canOperate': False, 'canGenerate': False, 'canConfigure': False}
                    none_p    = {'canView': False, 'canOperate': False, 'canGenerate': False, 'canConfigure': False}
                    if is_admin:
                        return {m: full for m in MODULES}
                    if is_viewer:
                        # Viewer: can see HMI + alarms + reports read-only; NO analytics, NO admin
                        return {
                            'hmi':       view,
                            'reports':   view,
                            'analytics': none_p,
                            'alarms':    view,
                            'admin':     none_p,
                        }
                    # Operator / Engineer: full view on everything except admin config
                    return {m: (view if m != 'admin' else none_p) for m in MODULES}
        except Exception as e:
            logger.warning(f"get_user_module_permissions error (graceful fallback): {e}")
            # Safe fallback: never grant analytics on error — least-privilege
            view   = {'canView': True,  'canOperate': False, 'canGenerate': False, 'canConfigure': False}
            none_p = {'canView': False, 'canOperate': False, 'canGenerate': False, 'canConfigure': False}
            return {'hmi': view, 'reports': view, 'analytics': none_p, 'alarms': view, 'admin': none_p}
