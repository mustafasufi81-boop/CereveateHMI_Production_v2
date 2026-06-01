from flask import Blueprint, jsonify
from container import container
from datetime import datetime
import logging
import math
import json as json_lib
import urllib.request
import urllib.error
from utils.decorators import token_required, get_user_allowed_tag_filter

logger = logging.getLogger(__name__)

tag_bp = Blueprint('tag', __name__, url_prefix='/api/tags')


def _fetch_pool_values(path: str):
    """
    Fetch live values from a C# backend pool endpoint (OPC or PLC).
    Returns a normalised list of dicts. Never raises — returns [] on any error so
    the DB-backed latest values remain the fallback.
    """
    try:
        req = urllib.request.Request(f'http://127.0.0.1:5001{path}')
        with urllib.request.urlopen(req, timeout=3) as response:
            data = json_lib.loads(response.read().decode('utf-8'))
        # C# PLC endpoint returns 'values'; OPC endpoint returns 'tags'
        raw = data.get('values')
        if raw is None:
            raw = data.get('tags')
        if raw is None:
            raw = []
        if isinstance(raw, dict):
            raw = list(raw.values())
        return raw
    except urllib.error.URLError:
        # Pool service down — silently fall back to DB values
        return []
    except Exception as e:
        logger.warning(f"⚠️ Live pool fetch failed for {path}: {e}")
        return []


def _coerce_finite(raw_val):
    """Coerce a pool value to a finite float, or None if non-numeric/non-finite."""
    num = None
    if isinstance(raw_val, bool):
        return raw_val  # booleans pass through unchanged
    if isinstance(raw_val, (int, float)):
        num = float(raw_val)
    elif isinstance(raw_val, str):
        try:
            num = float(raw_val)
        except (ValueError, TypeError):
            return None
    if num is not None and not math.isfinite(num):
        return None
    return num

@tag_bp.route('/enabled')
@token_required
def get_enabled_tags(current_user):
    """
    Get enabled tags from historian_meta.tag_master table
    Filtered by user's RBAC permissions
    """
    try:
        if not container.historical_service.connection:
            return jsonify({'error': 'Database not connected'}), 503
        
        # Get the filter function for current user
        tag_filter = get_user_allowed_tag_filter()
        
        logger.info(f"🏷️ TAG FILTER: filter_active={tag_filter is not None}")
        
        with container.historical_service.connection.cursor() as cursor:
            cursor.execute("""
                SELECT tag_id, tag_name, description, plant, area, equipment, data_type, eng_unit
                FROM historian_meta.tag_master
                WHERE enabled = true
                ORDER BY tag_id
            """)
            
            rows = cursor.fetchall()
            total_tags = len(rows)
            tags = []
            filtered_out = []
            
            for row in rows:
                tag_id = row['tag_id']
                plant = row['plant']
                area = row['area']
                
                # Apply RBAC filter (None means admin/full access)
                if tag_filter is not None:
                    is_allowed = tag_filter(tag_id, plant, area)
                    if not is_allowed:
                        filtered_out.append(f"{tag_id}({plant}/{area})")
                        continue
                
                tags.append({
                    'tagId': tag_id,
                    'tagName': row['tag_name'],
                    'description': row['description'],
                    'plant': plant,
                    'area': area,
                    'equipment': row['equipment'],
                    'dataType': row['data_type'],
                    'unit': row['eng_unit']
                })
            
            logger.info(f"🏷️ TAGS RESULT: total={total_tags}, allowed={len(tags)}, filtered_out={len(filtered_out)}")
            if filtered_out:
                logger.info(f"🏷️ FILTERED OUT: {filtered_out[:10]}...")  # Show first 10
            
            return jsonify({
                'count': len(tags),
                'tags': tags,
                'timestamp': datetime.now().isoformat()
            })
            
    except Exception as e:
        logger.error(f"❌ Failed to fetch enabled tags: {e}")
        import traceback
        logger.error(f"❌ Traceback: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

@tag_bp.route('/latest')
@token_required
def get_latest_tags(current_user):
    """
    Get latest tag values from DATABASE (historian_raw.historian_timeseries)
    Filtered by user's RBAC permissions
    """
    try:
        if not container.historical_service.connection:
            return jsonify({'error': 'Database not connected'}), 503
        
        # Get the filter function for current user
        tag_filter = get_user_allowed_tag_filter()
        
        with container.historical_service.connection.cursor() as cursor:
            # Use historian_latest_value for fast O(1) lookup per tag (updated in real-time by trigger)
            cursor.execute("""
                SELECT 
                    t.tag_id,
                    t.tag_name,
                    t.plant,
                    t.area,
                    t.data_type,
                    lv.last_value_num,
                    lv.last_value_text,
                    lv.last_value_bool,
                    lv.last_quality,
                    lv.last_time
                FROM historian_meta.tag_master t
                LEFT JOIN historian_raw.historian_latest_value lv ON lv.tag_id = t.tag_id
                WHERE t.enabled = true
                ORDER BY t.tag_id
            """)
            
            rows = cursor.fetchall()
            tags = {}
            # name/address -> tag_id lookup so we can overlay live pool values that
            # are keyed by PLC tag name or address rather than historian tag_id
            name_to_id = {}
            for row in rows:
                tag_id = row['tag_id']
                plant = row['plant']
                area = row['area']
                
                # Apply RBAC filter (None means admin/full access)
                if tag_filter is not None and not tag_filter(tag_id, plant, area):
                    continue
                
                # Pick correct value field based on data type
                raw_value = row['last_value_num']
                if raw_value is None:
                    raw_value = row['last_value_bool']
                if raw_value is None:
                    raw_value = row['last_value_text']
                
                tags[tag_id] = {
                    'value': float(raw_value) if isinstance(raw_value, (int, float)) else raw_value,
                    'quality': row['last_quality'] if row['last_quality'] else 'UNKNOWN',
                    'timestamp': row['last_time'].isoformat() if row['last_time'] else datetime.now().isoformat()
                }

                # Register lookup keys (tag_id itself + tag_name) for live overlay matching
                name_to_id[str(tag_id).upper()] = tag_id
                tag_name = row['tag_name']
                if tag_name:
                    name_to_id[str(tag_name).upper()] = tag_id

            # ---- Live overlay #1: OPC quality from C# OPC service (no DB) ----
            # /api/opc/values returns tagId + quality directly from the live OPC server.
            # This overwrites the DB-stored quality for OPC tags so we never depend on
            # the DB quality column being fresh. If OPC is down the call returns [] and
            # DB quality is used as fallback.
            opc_rows = _fetch_pool_values('/api/opc/values')
            for ov in opc_rows:
                tag_id = ov.get('tagId') or ov.get('tag_id')
                if tag_id is None:
                    continue
                if tag_id not in tags:
                    tag_id = name_to_id.get(str(tag_id).upper())
                if tag_id is None or tag_id not in tags:
                    continue
                raw_q = str(ov.get('quality') or '').strip()
                # OPC quality comes as full word ("Good","Bad","Uncertain") or OPC numeric string
                q_map = {
                    'GOOD': 'Good', '192': 'Good', 'G': 'Good',
                    'BAD': 'Bad', '0': 'Bad', 'B': 'Bad',
                    'UNCERTAIN': 'Uncertain', '64': 'Uncertain', 'U': 'Uncertain',
                }
                opc_q = q_map.get(raw_q.upper(), 'Good' if raw_q else tags[tag_id].get('quality', 'Good'))
                tags[tag_id]['quality'] = opc_q

            # ---- Live overlay #2: PLC pool (authoritative PV source for PLC tags) ----
            # PLC alarm tags (AY/TY/VYAN…) are the gap:
            # historian_latest_value lags and is written NULL for non-Good PLC reads.
            # Overlay the live PLC pool here so /api/tags/latest is the one authoritative
            # source of current PV — no second fetch in the UI.
            live_rows = _fetch_pool_values('/api/plc/values')
            overlaid = 0
            now_dt = datetime.now()
            for lv in live_rows:
                # Resolve the matching historian tag_id from any available key
                cand = (lv.get('tagId') or lv.get('tag_id')
                        or lv.get('tagName') or lv.get('address'))
                tag_id = None
                if cand is not None:
                    if cand in tags:
                        tag_id = cand
                    else:
                        tag_id = name_to_id.get(str(cand).upper())
                if tag_id is None:
                    addr = lv.get('address')
                    if addr:
                        tag_id = name_to_id.get(str(addr).upper())
                # tag_id present in `tags` also implies RBAC already allowed it
                if tag_id is None or tag_id not in tags:
                    continue

                # Live value wins; keep None when non-finite so the UI shows the
                # quality badge instead of a garbage number.
                num = _coerce_finite(lv.get('value'))
                # computedQuality from C# is the authoritative quality signal:
                # "Good" | "Stale" | "Uncertain" | "Bad"
                computed_q = lv.get('computedQuality') or lv.get('quality') or tags[tag_id].get('quality') or 'UNKNOWN'

                tags[tag_id] = {
                    'value': num,
                    'quality': computed_q,
                    'timestamp': lv.get('timestamp') or now_dt.isoformat(),
                }
                overlaid += 1

            # Tags not covered by the live pool overlay keep their DB quality.
            # No additional stale marking needed — quality field carries the signal.

            if overlaid:
                logger.debug(f"🔄 /api/tags/latest overlaid {overlaid} live pool values")

            # Normalize any single-char quality codes that were not overwritten by live overlays
            _q_expand = {'G': 'Good', 'B': 'Bad', 'U': 'Uncertain'}
            for t in tags.values():
                t['quality'] = _q_expand.get(t.get('quality'), t.get('quality') or 'Good')

            return jsonify({
                'timestamp': datetime.now().isoformat(),
                'count': len(tags),
                'tags': tags
            })
            
    except Exception as e:
        logger.error(f"❌ Failed to fetch latest tags: {e}")
        return jsonify({'error': str(e)}), 500

@tag_bp.route('/pid-mappings')
@token_required
def get_pid_tag_mappings(current_user):
    """
    Get P&ID tag mappings from tag_master for real-time visualization
    Returns tags with their equipment, description, and units for P&ID overlay
    """
    try:
        if not container.historical_service.connection:
            return jsonify({'error': 'Database not connected'}), 503
        
        # Get the filter function for current user
        tag_filter = get_user_allowed_tag_filter()
        
        with container.historical_service.connection.cursor() as cursor:
            # Get tags that are commonly used in P&IDs (pressure, temperature, flow, level, speed, etc.)
            cursor.execute("""
                SELECT 
                    tag_id,
                    tag_name,
                    description,
                    plant,
                    area,
                    equipment_name as equipment,
                    eng_unit as unit,
                    data_type,
                    hi_limit,
                    hi_warning,
                    lo_warning,
                    lo_limit
                FROM historian_meta.tag_master
                WHERE enabled = true
                AND (
                    tag_name ILIKE '%PRESSURE%' OR
                    tag_name ILIKE '%TEMP%' OR
                    tag_name ILIKE '%FLOW%' OR
                    tag_name ILIKE '%LEVEL%' OR
                    tag_name ILIKE '%SPEED%' OR
                    tag_name ILIKE '%VIBRATION%' OR
                    tag_name ILIKE '%CURRENT%' OR
                    tag_name ILIKE '%STATUS%' OR
                    tag_name ILIKE 'PT-%' OR
                    tag_name ILIKE 'TT-%' OR
                    tag_name ILIKE 'FT-%' OR
                    tag_name ILIKE 'LT-%' OR
                    tag_name ILIKE 'ST-%' OR
                    tag_name ILIKE 'VT-%' OR
                    tag_name ILIKE 'CT-%'
                )
                ORDER BY equipment_name, tag_name
            """)
            
            rows = cursor.fetchall()
            total_tags = len(rows)
            pid_tags = []
            
            for row in rows:
                tag_id = row['tag_id']
                plant = row['plant']
                area = row['area']
                
                # Apply RBAC filter
                if tag_filter is not None:
                    is_allowed = tag_filter(tag_id, plant, area)
                    if not is_allowed:
                        continue
                
                pid_tags.append({
                    'tagId': row['tag_name'],  # Use tag_name as the ID for P&ID overlay
                    'tagName': row['tag_name'],
                    'description': row['description'] or row['tag_name'],
                    'equipment': row['equipment'] or 'Unknown',
                    'unit': row['unit'] or '',
                    'dataType': row['data_type'],
                    'limits': {
                        'hiLimit': float(row['hi_limit']) if row['hi_limit'] else None,
                        'hiWarning': float(row['hi_warning']) if row['hi_warning'] else None,
                        'loWarning': float(row['lo_warning']) if row['lo_warning'] else None,
                        'loLimit': float(row['lo_limit']) if row['lo_limit'] else None
                    },
                    'plant': plant,
                    'area': area
                })
            
            logger.info(f"🎨 [P&ID] Mapped {len(pid_tags)} tags from {total_tags} candidates")
            
            return jsonify({
                'count': len(pid_tags),
                'tags': pid_tags,
                'timestamp': datetime.now().isoformat()
            })
            
    except Exception as e:
        logger.error(f"❌ Failed to fetch P&ID tag mappings: {e}")
        import traceback
        logger.error(f"❌ Traceback: {traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500
