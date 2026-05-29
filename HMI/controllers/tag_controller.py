from flask import Blueprint, jsonify
from container import container
from datetime import datetime
import logging
from utils.decorators import token_required, get_user_allowed_tag_filter

logger = logging.getLogger(__name__)

tag_bp = Blueprint('tag', __name__, url_prefix='/api/tags')

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
