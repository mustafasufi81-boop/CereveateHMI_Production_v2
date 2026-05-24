"""
Equipment Permission Service - Equipment-level access control
Handles fine-grained permissions for individual equipment.
"""

import logging
import psycopg2
import db_pool
from psycopg2.extras import RealDictCursor, Json

logger = logging.getLogger(__name__)


class EquipmentPermissionService:
    def __init__(self, db_config):
        self.db_config = db_config  # kept for reference only
    
    def _get_conn(self):
        return db_pool.get_conn()
    
    # ==================== Permission Checks ====================
    
    def check_permission(self, user_id, equipment_id, permission_type):
        """
        Check if user has specific permission on equipment.
        
        Args:
            user_id: User ID
            equipment_id: Equipment ID
            permission_type: 'view', 'start', 'stop', 'change_mode', 'change_setpoint', 
                           'emergency_stop', 'override_interlock', 'reset_alarm'
        
        Returns:
            bool: True if user has permission
        """
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT historian_meta.check_user_equipment_permission(%s, %s, %s)
                    """, (user_id, equipment_id, permission_type))
                    return cur.fetchone()[0]
        except Exception as e:
            logger.error(f"Check equipment permission error: {e}")
            return False
    
    def get_user_equipment_permissions(self, user_id, equipment_id=None):
        """Get all equipment permissions for a user."""
        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT * FROM historian_meta.get_user_equipment_permissions(%s, %s)
                    """, (user_id, equipment_id))
                    return cur.fetchall()
        except Exception as e:
            logger.error(f"Get user equipment permissions error: {e}")
            return []
    
    # ==================== Role Equipment Permissions ====================
    
    def get_role_equipment_permissions(self, role_id):
        """Get equipment permissions for a role."""
        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT rep.id, rep.equipment_id, e.equipment_name, e.equipment_type,
                               rep.can_view, rep.can_start, rep.can_stop, rep.can_change_mode,
                               rep.can_change_setpoint, rep.can_emergency_stop,
                               rep.can_override_interlock, rep.can_reset_alarm,
                               rep.valid_from, rep.valid_until
                        FROM historian_meta.role_equipment_permissions rep
                        LEFT JOIN historian_meta.equipment_registry e ON rep.equipment_id = e.equipment_id
                        WHERE rep.role_id = %s
                        ORDER BY e.equipment_name
                    """, (role_id,))
                    return cur.fetchall()
        except Exception as e:
            logger.error(f"Get role equipment permissions error: {e}")
            return []
    
    def add_equipment_permission(self, role_id, equipment_id, permissions):
        """
        Add or update equipment permission for a role.
        
        Args:
            role_id: Role ID
            equipment_id: Equipment ID
            permissions: Dict with permission flags (can_view, can_start, etc.)
        
        Returns:
            int: Permission ID
        """
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT historian_meta.add_equipment_permission(
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                        )
                    """, (
                        role_id,
                        equipment_id,
                        permissions.get('can_view', True),
                        permissions.get('can_start', False),
                        permissions.get('can_stop', False),
                        permissions.get('can_change_mode', False),
                        permissions.get('can_change_setpoint', False),
                        permissions.get('can_emergency_stop', False),
                        permissions.get('can_override_interlock', False),
                        permissions.get('can_reset_alarm', False),
                        permissions.get('valid_from'),
                        permissions.get('valid_until')
                    ))
                    permission_id = cur.fetchone()[0]
                    conn.commit()
                    return permission_id
        except Exception as e:
            logger.error(f"Add equipment permission error: {e}")
            raise
    
    def remove_equipment_permission(self, permission_id):
        """Remove an equipment permission."""
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        DELETE FROM historian_meta.role_equipment_permissions
                        WHERE id = %s
                    """, (permission_id,))
                    conn.commit()
                    return cur.rowcount > 0
        except Exception as e:
            logger.error(f"Remove equipment permission error: {e}")
            raise
    
    # ==================== Equipment Registry ====================
    
    def get_equipment_registry(self, equipment_id=None, equipment_type=None, 
                              plant=None, area=None):
        """Get equipment from registry with filters."""
        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    query = """
                        SELECT * FROM historian_meta.equipment_registry
                        WHERE is_active = TRUE
                    """
                    params = []
                    
                    if equipment_id:
                        query += " AND equipment_id = %s"
                        params.append(equipment_id)
                    
                    if equipment_type:
                        query += " AND equipment_type = %s"
                        params.append(equipment_type)
                    
                    if plant:
                        query += " AND plant = %s"
                        params.append(plant)
                    
                    if area:
                        query += " AND area = %s"
                        params.append(area)
                    
                    query += " ORDER BY equipment_name"
                    
                    cur.execute(query, params)
                    return cur.fetchall()
        except Exception as e:
            logger.error(f"Get equipment registry error: {e}")
            return []
    
    def register_equipment(self, equipment_data):
        """Register new equipment in registry."""
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO historian_meta.equipment_registry (
                            equipment_id, equipment_name, equipment_type,
                            plant, area, criticality, safety_classified,
                            current_mode, requires_two_person_rule,
                            requires_supervisor_approval, tags, description
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                    """, (
                        equipment_data['equipment_id'],
                        equipment_data['equipment_name'],
                        equipment_data['equipment_type'],
                        equipment_data.get('plant'),
                        equipment_data.get('area'),
                        equipment_data.get('criticality', 'medium'),
                        equipment_data.get('safety_classified', False),
                        equipment_data.get('current_mode', 'auto'),
                        equipment_data.get('requires_two_person_rule', False),
                        equipment_data.get('requires_supervisor_approval', False),
                        Json(equipment_data.get('tags', [])),
                        equipment_data.get('description')
                    ))
                    equipment_id = cur.fetchone()[0]
                    conn.commit()
                    return equipment_id
        except Exception as e:
            logger.error(f"Register equipment error: {e}")
            raise
    
    def update_equipment(self, equipment_id, updates):
        """Update equipment in registry."""
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    set_clauses = []
                    params = []
                    
                    for key, value in updates.items():
                        if key in ['equipment_name', 'equipment_type', 'plant', 'area',
                                  'criticality', 'safety_classified', 'current_mode',
                                  'requires_two_person_rule', 'requires_supervisor_approval',
                                  'description', 'is_active', 'is_operational']:
                            set_clauses.append(f"{key} = %s")
                            params.append(value)
                        elif key == 'tags':
                            set_clauses.append("tags = %s")
                            params.append(Json(value))
                    
                    if not set_clauses:
                        return False
                    
                    params.append(equipment_id)
                    query = f"""
                        UPDATE historian_meta.equipment_registry
                        SET {', '.join(set_clauses)}
                        WHERE equipment_id = %s
                    """
                    
                    cur.execute(query, params)
                    conn.commit()
                    return cur.rowcount > 0
        except Exception as e:
            logger.error(f"Update equipment error: {e}")
            raise
    
    # ==================== Equipment Types ====================
    
    def get_equipment_types(self):
        """Get all equipment types."""
        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT * FROM historian_meta.equipment_types
                        WHERE is_active = TRUE
                        ORDER BY type_name
                    """)
                    return cur.fetchall()
        except Exception as e:
            logger.error(f"Get equipment types error: {e}")
            return []
    
    # ==================== Permission Summary ====================
    
    def get_equipment_permissions_summary(self):
        """Get summary of equipment permissions."""
        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT * FROM historian_meta.equipment_permissions_summary
                        ORDER BY criticality DESC, equipment_name
                    """)
                    return cur.fetchall()
        except Exception as e:
            logger.error(f"Get permissions summary error: {e}")
            return []
