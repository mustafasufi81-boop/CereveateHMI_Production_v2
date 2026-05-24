from functools import wraps
from flask import request, jsonify, g
from container import container
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Area access helpers (plant/area two-dimension model)
# ─────────────────────────────────────────────────────────────────────────────

def get_current_user_area_access():
    """
    Returns area access for the currently authenticated user (from g.user_id).

    Return values:
      None  → admin bypass — no filter needed, show all data
      []    → no areas assigned — show nothing
      [...]  → list of {plant, area, ...} dicts

    SECURITY: always re-fetches from AreaAccessService (DB-backed 30s cache).
    NEVER reads area info from the JWT token for authorization.
    """
    user_id = getattr(g, 'user_id', None)
    if not user_id:
        return []
    return container.area_access_service.get_user_area_access(user_id)


def get_area_filter_sql_join(tag_table_alias: str = "tm") -> tuple[str, dict]:
    """
    Returns (join_fragment, params) for the current request's user.

    Appends this JOIN to any query that selects from tag_master (aliased as tag_table_alias).
    Returns ("", {}) for admin users (bypass).
    Returns (" AND 1=0", {}) if user has no area assignments.

    CRITICAL: uses JOIN-based filtering — NOT plant IN (...) AND area IN (...)
    which would create a cross-product and leak data across plant/area boundaries.

    Example:
        join_sql, params = get_area_filter_sql_join("tm")
        query = f"SELECT tm.* FROM historian_meta.tag_master tm {join_sql} WHERE tm.enabled=true"
        rows = cur.execute(query, params)
    """
    user_id = getattr(g, 'user_id', None)
    if not user_id:
        return " AND 1=0 -- no user context", {}
    return container.area_access_service.get_area_filter_join(user_id, tag_table_alias)



def token_required(f):
    """Token validation decorator with optional session validation"""
    @wraps(f)
    def decorated(*args, **kwargs):
        logger.info(f"🔐 token_required decorator called for endpoint: {f.__name__}")
        
        token = request.headers.get('Authorization')
        if not token:
            logger.warning("❌ Token is missing from Authorization header!")
            return jsonify({'message': 'Token is missing!'}), 401
        
        logger.info(f"✅ Authorization header found: {token[:30]}...")
        
        if token.startswith('Bearer '):
            token = token.split(' ')[1]
            logger.info(f"✅ Extracted Bearer token: {token[:20]}...")
        else:
            logger.warning(f"⚠️  Token doesn't start with 'Bearer ': {token[:30]}")
            
        try:
            logger.info("🔍 Decoding token...")
            data = container.auth_service.decode_token(token)
            if not data:
                logger.error("❌ Token decode returned None/False")
                return jsonify({'message': 'Token is invalid!'}), 401
            
            logger.info(f"✅ Token decoded successfully: user_id={data.get('user_id')}, username={data.get('username')}")
            
            # Attach user info to Flask's g object
            g.user_id = data.get('user_id')
            g.username = data.get('username')
            g.is_admin = container.rbac_service.is_user_admin(g.user_id)
            
            logger.info(f"✅ User context set: user_id={g.user_id}, username={g.username}, is_admin={g.is_admin}")
            
            # Create current_user dictionary to pass to endpoint
            current_user = {
                'user_id': data.get('user_id'),
                'username': data.get('username'),
                'is_admin': g.is_admin
            }
            
            # Optional: Validate session if session token provided
            session_token = request.headers.get('X-Session-Token')
            if session_token:
                logger.info(f"🔍 Session token found, validating: {session_token[:20]}...")

                # Use validate_session_with_expiry: checks is_active AND logout_time
                # guards against expired rows that cleanup job has not yet processed.
                session_info = container.session_service.validate_session_with_expiry(session_token)

                if not session_info:
                    # Fall back to stored-proc validator for backward compat
                    session_validation = container.session_service.validate_session(session_token)
                    if not session_validation or not session_validation.get('is_valid'):
                        logger.warning("❌ Session expired or invalid!")
                        return jsonify({
                            'message': 'Session expired or invalid!',
                            'sessionExpired': True,
                            'code': 'SESSION_SUPERSEDED'
                        }), 401
                    # Update session activity
                    container.session_service.update_activity(session_token)
                    g.session_id = session_validation.get('session_id')
                    current_user['session_id'] = session_validation.get('session_id')
                else:
                    # Session valid from direct check
                    container.session_service.update_activity(session_token)
                    g.session_id = session_info.get('session_id')
                    current_user['session_id'] = session_info.get('session_id')

                logger.info(f"✅ Session validated and activity updated")
            else:
                logger.info("ℹ️  No session token provided (optional)")
            
            logger.info(f"✅ Calling endpoint {f.__name__} with user={current_user['username']}")
            
        except Exception as e:
            logger.error(f"❌ Exception during token validation: {e}", exc_info=True)
            return jsonify({'message': 'Token is invalid!'}), 401
            
        return f(current_user, *args, **kwargs)
    return decorated


def get_user_allowed_tag_filter():
    """
    Returns a function that checks if a tag is allowed for the current user.

    Authority: area_access_service ONLY (per-user Admin › Area Access tab).
    NO fallback to role_tag_permissions — admin sets access explicitly per user.

    Returns:
        - None               → admin (no filtering, sees all data)
        - lambda *a: False   → no area assignments (sees nothing)
        - filter function    → checks (tag_id, plant, area) against assigned areas
    """
    import logging
    logger = logging.getLogger(__name__)

    user_id = getattr(g, 'user_id', None)
    if not user_id:
        logger.warning("🔐 RBAC: No user_id found in context")
        return lambda *a: False  # No user = no access

    is_admin = getattr(g, 'is_admin', False)
    logger.info(f"🔐 RBAC: user_id={user_id}, is_admin={is_admin}")

    if is_admin:
        logger.info("🔐 RBAC: Admin user - full access granted")
        return None  # Admin = full access, no filtering needed

    # ── Area assignments (sole authority — set via Admin › Area Access tab) ──
    try:
        area_access = container.area_access_service.get_user_area_access(user_id)
    except Exception as exc:
        logger.error(f"🔐 RBAC: area_access_service error: {exc} — denying access (fail-safe)")
        return lambda *a: False  # fail-safe: deny on error, no fallback

    if area_access is None:
        # Service confirmed admin bypass
        logger.info("🔐 RBAC: area_access_service returned admin bypass")
        return None

    # Build allowed (plant, area) set from assignments
    allowed_plant_areas = set()
    for p in (area_access or []):
        plant = p.get('plant')
        area = p.get('area')
        if plant and area:
            allowed_plant_areas.add((plant, area))

    if not allowed_plant_areas:
        logger.warning(f"🔐 RBAC: User {user_id} has NO area assignments — zero access")
        return lambda *a: False  # No assignments = no data

    logger.info(f"🔐 RBAC: User {user_id} — {len(allowed_plant_areas)} area(s) assigned: {list(allowed_plant_areas)}")

    # ── Specific tag overrides (always unioned in) ────────────────────────────
    specific_perms = container.rbac_service.get_user_allowed_specific_tags(user_id) or []
    allowed_tags = set(p['tag_id'] for p in specific_perms)

    logger.info(f"🔐 RBAC RESULT: user_id={user_id}, plant_areas={len(allowed_plant_areas)}, specific_tags={len(allowed_tags)}")
    if allowed_plant_areas:
        logger.info(f"   📍 Allowed plant/areas: {list(allowed_plant_areas)}")
    if allowed_tags:
        logger.info(f"   🏷️  Specific tags: {list(allowed_tags)[:5]}...")

    if not allowed_plant_areas and not allowed_tags:
        logger.warning(f"🔐 RBAC: User {user_id} has NO permissions — no tags allowed")
        return lambda *a: False

    # Counter for debug logging (only log first few checks)
    check_counter = {'count': 0}

    def is_tag_allowed(tag_id, plant=None, area=None):
        # Debug: Log details for first 5 tags only
        check_counter['count'] += 1
        is_debug = check_counter['count'] <= 5


        if is_debug:
            logger.info(f"      🔍 Tag #{check_counter['count']}: tag_id='{tag_id}', plant='{plant}', area='{area}'")
        
        # Allow if tag is explicitly assigned
        if tag_id in allowed_tags:
            if is_debug:
                logger.info(f"      ✅ ALLOWED by SPECIFIC TAG permission")
            return True
        
        # Allow if tag belongs to an allowed plant/area combination
        if plant and area:
            lookup_key = (plant, area)
            if is_debug:
                logger.info(f"      🔍 Checking if {lookup_key} in allowed_plant_areas...")
            if lookup_key in allowed_plant_areas:
                if is_debug:
                    logger.info(f"      ✅ ALLOWED by PLANT/AREA permission")
                return True
            else:
                if is_debug:
                    logger.info(f"      ❌ NOT FOUND in allowed_plant_areas")
                    logger.info(f"      📋 Available plant/areas: {list(allowed_plant_areas)}")
        else:
            if is_debug:
                logger.info(f"      ⚠️  plant or area is None - cannot check plant/area permissions")
        
        return False
    
    return is_tag_allowed
