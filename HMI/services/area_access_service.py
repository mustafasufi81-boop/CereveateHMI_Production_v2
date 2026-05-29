"""
Area Access Service — Plant/Area-Based Data Scoping

Two-dimension access control:
  Role       → what the user can DO  (view/operate/generate/configure)
  Area Access → what data the user can SEE (which Plant+Area combinations)

Security rules (per PLANT_AREA_ACCESS_CONTROL_DESIGN.md):
  - Admin role (is_admin=True) bypasses ALL area filters
  - Area filter uses JOIN-based logic — never plant IN (...) AND area IN (...)
  - JWT area_access is for DISPLAY only; backend always re-fetches from DB/cache
  - Inactive areas (is_active=False) are ALWAYS excluded
  - Revoked assignments (revoked_at IS NOT NULL) are ALWAYS excluded
  - Cache TTL = 30s; invalidated immediately on assignment change
  - Every assignment change writes to access_audit_log
"""

import time
import logging
import threading
import psycopg2
import db_pool
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)


class AreaAccessService:
    """
    Manages plant/area access assignments for users.

    Thread-safe in-memory cache (dict) with 30-second TTL.
    Cache is keyed by user_id and invalidated immediately when
    admin saves a new area assignment.
    """

    CACHE_TTL_SECONDS = 30

    def __init__(self, db_config: dict):
        self.db_config = db_config
        self._cache: dict[int, tuple[float, list | None]] = {}  # {user_id: (timestamp, areas|None)}
        self._cache_lock = threading.Lock()

    # ─────────────────────────────────────────────────────────────
    # DB helpers
    # ─────────────────────────────────────────────────────────────

    def _get_conn(self):
        return db_pool.get_conn()

    # ─────────────────────────────────────────────────────────────
    # Cache helpers
    # ─────────────────────────────────────────────────────────────

    def _cache_get(self, user_id: int):
        """Returns (hit, value). value is list|None. None means admin bypass."""
        with self._cache_lock:
            entry = self._cache.get(user_id)
            if entry is None:
                return False, None
            ts, val = entry
            if time.monotonic() - ts > self.CACHE_TTL_SECONDS:
                del self._cache[user_id]
                return False, None
            return True, val

    def _cache_set(self, user_id: int, val):
        with self._cache_lock:
            self._cache[user_id] = (time.monotonic(), val)

    def invalidate_user_cache(self, user_id: int):
        """Call this immediately after saving area assignments for a user."""
        with self._cache_lock:
            self._cache.pop(user_id, None)
        logger.info(f"[AreaAccess] Cache invalidated for user_id={user_id}")

    def invalidate_all_cache(self):
        with self._cache_lock:
            self._cache.clear()

    # ─────────────────────────────────────────────────────────────
    # Core: get user's area access
    # ─────────────────────────────────────────────────────────────

    def get_user_area_access(self, user_id: int) -> list | None:
        """
        Returns the list of plant/area dicts the user can access.

        Return values:
          None  → user is admin, bypass all filters (show everything)
          []    → user has no active area assignments (show nothing)
          [...]  → list of {id, plant, area, plant_code, area_code, display_name}

        NEVER reads from JWT — always re-fetches from DB/cache.
        """
        hit, cached = self._cache_get(user_id)
        if hit:
            return cached

        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT u.id as user_id, r.is_admin,
                               pa.id as plant_area_id,
                               pa.plant, pa.area,
                               pa.plant_code, pa.area_code,
                               pa.display_name,
                               pa.server_progid
                        FROM historian_meta.users u
                        JOIN historian_meta.roles r ON r.id = u.role_id
                        LEFT JOIN historian_meta.user_area_assignments uaa
                            ON uaa.user_id = u.id
                           AND uaa.revoked_at IS NULL
                        LEFT JOIN historian_meta.plants_areas pa
                            ON pa.id = uaa.plant_area_id
                           AND pa.is_active = true
                        WHERE u.id = %s AND u.status = 'approved'
                        ORDER BY pa.plant, pa.area
                    """, (user_id,))
                    rows = cur.fetchall()

            if not rows:
                # User not found or not approved → no access
                result = []
            elif rows[0]['is_admin']:
                # Admin bypass
                result = None
            else:
                result = [
                    {
                        'id': r['plant_area_id'],
                        'plant': r['plant'],
                        'area': r['area'],
                        'plant_code': r['plant_code'],
                        'area_code': r['area_code'],
                        'display_name': r['display_name'],
                        'server_progid': r['server_progid'],
                    }
                    for r in rows
                    if r['plant_area_id'] is not None
                ]

            self._cache_set(user_id, result)
            return result

        except Exception as e:
            logger.error(f"[AreaAccess] get_user_area_access({user_id}) error: {e}")
            return []  # fail safe: no access on error

    def is_admin_bypass(self, user_id: int) -> bool:
        """Returns True if the user is an admin (area filter bypassed)."""
        return self.get_user_area_access(user_id) is None

    # ─────────────────────────────────────────────────────────────
    # SQL JOIN fragment for area filtering (use in any query)
    # ─────────────────────────────────────────────────────────────

    def get_area_filter_join(self, user_id: int, tag_table_alias: str = "tm") -> tuple[str, dict]:
        """
        Returns (join_sql, params) to append to any query that includes tag_master.

        Usage example:
            join_sql, params = area_svc.get_area_filter_join(user_id, "tm")
            if join_sql:   # None → admin bypass, no filter needed
                query += join_sql
                query_params.update(params)

        CRITICAL: uses JOIN-based filtering, NOT plant IN (...) AND area IN (...)
        This ensures EXACT (plant, area) pair matching — no cross-product leakage.
        """
        areas = self.get_user_area_access(user_id)
        if areas is None:
            return "", {}  # admin bypass

        if not areas:
            # No areas → force zero results with impossible condition
            return f" AND 1=0 -- no area access", {}

        join_sql = f"""
            JOIN historian_meta.plants_areas _pa
              ON _pa.plant = {tag_table_alias}.plant
             AND _pa.area  = {tag_table_alias}.area
             AND _pa.is_active = true
            JOIN historian_meta.user_area_assignments _uaa
              ON _uaa.plant_area_id = _pa.id
             AND _uaa.user_id = %(area_filter_user_id)s
             AND _uaa.revoked_at IS NULL
        """
        return join_sql, {"area_filter_user_id": user_id}

    # ─────────────────────────────────────────────────────────────
    # Plants & Areas Registry
    # ─────────────────────────────────────────────────────────────

    def get_all_plants_areas(self, active_only: bool = True) -> list:
        """Returns all plant/area entries with tag counts."""
        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    # RULE: never show entries with no server_progid — they have no
                    # known source and cannot be assigned meaningful data access.
                    active_clause = "pa.is_active = true AND" if active_only else ""
                    cur.execute(f"""
                        SELECT pa.id, pa.plant_code, pa.area_code, pa.plant, pa.area,
                               pa.display_name, pa.description, pa.is_active, pa.created_at,
                               pa.server_progid,
                               COUNT(tm.tag_id) as tag_count
                        FROM historian_meta.plants_areas pa
                        LEFT JOIN historian_meta.tag_master tm
                            ON tm.plant = pa.plant AND tm.area = pa.area AND tm.enabled = true
                        WHERE {active_clause} pa.server_progid IS NOT NULL
                          AND pa.server_progid <> ''
                        GROUP BY pa.id, pa.plant_code, pa.area_code, pa.plant, pa.area,
                                 pa.display_name, pa.description, pa.is_active, pa.created_at,
                                 pa.server_progid
                        ORDER BY pa.server_progid, pa.plant, pa.area
                    """)
                    return [dict(r) for r in cur.fetchall()]
        except Exception as e:
            logger.error(f"[AreaAccess] get_all_plants_areas error: {e}")
            raise

    def create_plant_area(self, plant: str, area: str, display_name: str = None,
                          description: str = None) -> dict:
        """Create a new plant/area entry. Generates immutable codes automatically."""
        import re
        plant_code = re.sub(r'[^A-Za-z0-9]', '', plant).upper()
        area_code = re.sub(r'[^A-Za-z0-9]', '', area).upper()
        dname = display_name or f"{plant} — {area}"

        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        INSERT INTO historian_meta.plants_areas
                            (plant_code, area_code, plant, area, display_name, description)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        RETURNING id, plant_code, area_code, plant, area, display_name, is_active
                    """, (plant_code, area_code, plant, area, dname, description))
                    conn.commit()
                    return dict(cur.fetchone())
        except psycopg2.errors.UniqueViolation:
            raise ValueError(f"Plant/Area '{plant}/{area}' already exists")
        except Exception as e:
            logger.error(f"[AreaAccess] create_plant_area error: {e}")
            raise

    def set_plant_area_active(self, plant_area_id: int, is_active: bool):
        """Activate or deactivate a plant/area entry."""
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE historian_meta.plants_areas
                        SET is_active = %s WHERE id = %s
                    """, (is_active, plant_area_id))
                    conn.commit()
            self.invalidate_all_cache()  # area deactivation affects all users
        except Exception as e:
            logger.error(f"[AreaAccess] set_plant_area_active error: {e}")
            raise

    def sync_from_tag_master(self):
        """
        Sync plants_areas with tag_master using trigger function.
        - Adds new combinations from tag_master
        - Marks orphans (no tags) as inactive
        - Reactivates entries that regain tags
        """
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    # Call the trigger function that handles full sync logic
                    cur.execute("SELECT historian_meta.sync_plants_areas_from_tags();")
                    
                    # Get count of active entries after sync
                    cur.execute("SELECT COUNT(*) FROM historian_meta.plants_areas WHERE is_active = true")
                    active_count = cur.fetchone()[0]
                    
                    conn.commit()
                    logger.info(f"[AreaAccess] Sync complete: {active_count} active plants_areas entries")
            return active_count
        except Exception as e:
            logger.error(f"[AreaAccess] sync_from_tag_master error: {e}")
            raise

    # ─────────────────────────────────────────────────────────────
    # User area assignment management
    # ─────────────────────────────────────────────────────────────

    def get_user_assigned_area_ids(self, user_id: int) -> list[int]:
        """Returns list of plant_area_id currently active for a user."""
        try:
            with self._get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT uaa.plant_area_id
                        FROM historian_meta.user_area_assignments uaa
                        JOIN historian_meta.plants_areas pa ON pa.id = uaa.plant_area_id
                        WHERE uaa.user_id = %s
                          AND uaa.revoked_at IS NULL
                          AND pa.is_active = true
                        ORDER BY pa.plant, pa.area
                    """, (user_id,))
                    return [r[0] for r in cur.fetchall()]
        except Exception as e:
            logger.error(f"[AreaAccess] get_user_assigned_area_ids error: {e}")
            raise

    def set_user_areas(self, user_id: int, plant_area_ids: list[int],
                       admin_user_id: int, admin_username: str, admin_ip: str = None,
                       notes: str = None):
        """
        Full replace: sets the user's area assignments to exactly plant_area_ids.
        Revokes removed areas. Adds new areas. Writes audit log.
        Invalidates cache for this user immediately.

        Raises ValueError if the number of areas exceeds the role's max_areas_per_user quota.
        NULL quota means unlimited. Admin roles always bypass quota (is_admin=True).
        """
        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:

                    # ── Role quota check (§4f) ──────────────────────────────
                    cur.execute("""
                        SELECT r.is_admin, r.max_areas_per_user, r.name as role_name
                        FROM historian_meta.users u
                        JOIN historian_meta.roles r ON r.id = u.role_id
                        WHERE u.id = %s
                    """, (user_id,))
                    role_row = cur.fetchone()
                    if role_row and not role_row['is_admin']:
                        quota = role_row['max_areas_per_user']
                        if quota is not None and len(plant_area_ids) > quota:
                            raise ValueError(
                                f"Role '{role_row['role_name']}' allows a maximum of {quota} area "
                                f"assignment{'s' if quota != 1 else ''}. "
                                f"You are trying to assign {len(plant_area_ids)}. "
                                "Reduce the selection or increase the role quota in the Roles tab."
                            )

                    # Get target username for audit log
                    cur.execute("SELECT username FROM historian_meta.users WHERE id = %s", (user_id,))
                    row = cur.fetchone()
                    target_username = row['username'] if row else str(user_id)

                    # Get old areas for audit log
                    cur.execute("""
                        SELECT STRING_AGG(pa.plant || '/' || pa.area, ', ' ORDER BY pa.plant, pa.area) AS area_list
                        FROM historian_meta.user_area_assignments uaa
                        JOIN historian_meta.plants_areas pa ON pa.id = uaa.plant_area_id
                        WHERE uaa.user_id = %s AND uaa.revoked_at IS NULL
                    """, (user_id,))
                    old_areas = (cur.fetchone() or {}).get('area_list') or ''

                    # Revoke ALL existing active assignments
                    cur.execute("""
                        UPDATE historian_meta.user_area_assignments
                        SET revoked_at = NOW()
                        WHERE user_id = %s AND revoked_at IS NULL
                    """, (user_id,))

                    # Insert new assignments
                    # No ON CONFLICT needed: revoke-all above means no active row exists
                    # for this user/area, so the partial unique index will never fire.
                    for pa_id in plant_area_ids:
                        cur.execute("""
                            INSERT INTO historian_meta.user_area_assignments
                                (user_id, plant_area_id, assigned_by, assigned_at)
                            VALUES (%s, %s, %s, NOW())
                        """, (user_id, pa_id, admin_user_id))

                    # Get new areas for audit log
                    if plant_area_ids:
                        cur.execute("""
                            SELECT STRING_AGG(plant || '/' || area, ', ' ORDER BY plant, area) AS area_list
                            FROM historian_meta.plants_areas
                            WHERE id = ANY(%s)
                        """, (plant_area_ids,))
                        new_areas = (cur.fetchone() or {}).get('area_list') or ''
                    else:
                        new_areas = ''

                    # Write audit log using JSONB state columns (§5.3 / §27.4)
                    old_state = {'areas': old_areas.split(', ') if old_areas else [],
                                 'area_count': len(old_areas.split(', ')) if old_areas else 0}
                    new_state = {'areas': new_areas.split(', ') if new_areas else [],
                                 'area_count': len(plant_area_ids)}
                    import json as _json
                    cur.execute("""
                        INSERT INTO historian_meta.access_audit_log
                            (event_time,
                             admin_user_id, admin_username, admin_ip,
                             target_user_id, target_username,
                             action, old_state, new_state, notes)
                        VALUES (NOW(),
                                %s, %s, %s, %s, %s, 'REPLACE', %s, %s, %s)
                    """, (admin_user_id, admin_username, admin_ip,
                          user_id, target_username,
                          _json.dumps(old_state), _json.dumps(new_state), notes))

                    conn.commit()

            # Invalidate cache IMMEDIATELY after commit
            self.invalidate_user_cache(user_id)
            logger.info(f"[AreaAccess] Areas set for user {user_id}: {new_areas} (by {admin_username})")

        except Exception as e:
            logger.error(f"[AreaAccess] set_user_areas error: {e}")
            raise

    # ─────────────────────────────────────────────────────────────
    # Access matrix (admin overview)
    # ─────────────────────────────────────────────────────────────

    def get_access_matrix(self) -> list:
        """Returns full user→role→areas overview for admin access matrix view."""
        try:
            with self._get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT
                            u.id as user_id,
                            u.username,
                            u.status,
                            r.name as role_name,
                            r.is_admin,
                            r.max_areas_per_user,
                            STRING_AGG(
                                pa.display_name,
                                ', ' ORDER BY pa.plant, pa.area
                            ) FILTER (
                                WHERE pa.is_active = true AND uaa.revoked_at IS NULL
                            ) as assigned_areas,
                            COUNT(uaa.id) FILTER (
                                WHERE pa.is_active = true AND uaa.revoked_at IS NULL
                            ) as area_count
                        FROM historian_meta.users u
                        JOIN historian_meta.roles r ON r.id = u.role_id
                        LEFT JOIN historian_meta.user_area_assignments uaa ON uaa.user_id = u.id
                        LEFT JOIN historian_meta.plants_areas pa ON pa.id = uaa.plant_area_id
                        GROUP BY u.id, u.username, u.status, r.name, r.is_admin, r.max_areas_per_user
                        ORDER BY u.username
                    """)
                    return [dict(r) for r in cur.fetchall()]
        except Exception as e:
            logger.error(f"[AreaAccess] get_access_matrix error: {e}")
            raise
