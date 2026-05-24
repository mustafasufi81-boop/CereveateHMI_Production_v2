"""
Asset Hierarchy Controller
Provides asset taxonomy tree based on tag_master hierarchy:
Plant → Area → Equipment → Sub-Equipment → Components
"""
from flask import Blueprint, jsonify, request, g
from container import container
import logging
from datetime import datetime
from utils.decorators import token_required, get_user_allowed_tag_filter

logger = logging.getLogger(__name__)

asset_bp = Blueprint('asset', __name__, url_prefix='/api/assets')


@asset_bp.route('/hierarchy')
@token_required
def get_asset_hierarchy(current_user):
    """
    Get complete asset hierarchy from tag_master
    Returns nested tree structure: Plant → Area → Equipment → Sub-Equipment → Components
    Viewers and admins can see full hierarchy
    """
    logger.info("=" * 60)
    logger.info("[API] Asset Hierarchy API Called - /api/assets/hierarchy")
    logger.info(f"[USER] Current User: {current_user}")
    logger.info("=" * 60)
    
    try:
        if not container.historical_service.connection:
            logger.error("[ERROR] Database not connected")
            return jsonify({'error': 'Database not connected'}), 503
        
        logger.info("[OK] Database connection OK")
        
        # Get user info from token (set by @token_required decorator)
        user_id = getattr(g, 'user_id', None)
        username = getattr(g, 'username', None)
        is_admin = getattr(g, 'is_admin', False)
        
        logger.info(f"[DEBUG] User Check: user_id={user_id}, username={username}, is_admin={is_admin}")
        logger.info(f"[DEBUG] Current User Dict: {current_user}")
        
        # All authenticated users (Admin/Operator/Viewer/Engineer) have hmi.canView=true.
        # No per-user tag filter — show full hierarchy to all roles.
        # Admin flag logged for audit; filtering is handled at the action level (ACK/SUPP/etc).
        tag_filter = None
        if is_admin or current_user.get('is_admin'):
            logger.info(f"[ADMIN] Admin user '{username}' - full hierarchy")
        else:
            logger.info(f"[RBAC] User '{username}' (role={current_user.get('role_id')}) - full hierarchy (canView=true for all roles)")
        
        with container.historical_service.connection.cursor() as cursor:
            logger.info("[SQL] Executing SQL query for asset hierarchy...")
            # Get all tags with asset hierarchy information
            cursor.execute("""
                SELECT DISTINCT
                    tag_id,
                    tag_name,
                    plant,
                    area,
                    equipment,
                    sub_equipment,
                    components,
                    data_type,
                    eng_unit,
                    description,
                    trip_category,
                    equipment_criticality,
                    server_progid
                FROM historian_meta.tag_master
                WHERE enabled = true
                ORDER BY plant, area, equipment, sub_equipment, components, tag_id
            """)
            
            rows = cursor.fetchall()
            
            logger.info(f"[SQL] Query returned {len(rows)} rows from database")
            logger.info(f"[DEBUG] Tag filter active: {tag_filter is not None}")
            
            if tag_filter is not None:
                logger.info(f"🔐 RBAC FILTERING ENABLED - Tags will be filtered based on user permissions")
            else:
                logger.info(f"🔓 NO FILTERING - Admin user sees all tags")
            
            # Build hierarchical structure
            hierarchy = {}
            tag_count = 0
            filtered_count = 0
            allowed_count = 0
            
            # Debug: Log first few tags from database
            if len(rows) > 0:
                logger.info("[DEBUG] SAMPLE TAGS FROM DATABASE (first 3):")
                for i, row in enumerate(rows[:3]):
                    logger.info(f"   Tag {i+1}: tag_id='{row['tag_id']}', plant='{row['plant']}', area='{row['area']}'")
            
            for row in rows:
                tag_id = row['tag_id']
                plant = row['plant'] or 'Unassigned'
                area = row['area'] or 'Unassigned'
                equipment = row['equipment'] or 'Unassigned'
                sub_equipment = row['sub_equipment'] or 'Unassigned'
                components = row['components'] or 'Unassigned'
                
                # Apply RBAC filter
                if tag_filter is not None:
                    is_allowed = tag_filter(tag_id, plant if plant != 'Unassigned' else None, 
                                     area if area != 'Unassigned' else None)
                    if not is_allowed:
                        filtered_count += 1
                        if filtered_count <= 5:  # Log first 5 filtered tags
                            logger.info(f"  [X] Tag FILTERED: {tag_id} (plant={plant}, area={area})")
                        continue
                    else:
                        allowed_count += 1
                        if allowed_count <= 5:  # Log first 5 allowed tags
                            logger.info(f"  [OK] Tag ALLOWED: {tag_id} (plant={plant}, area={area})")
                
                tag_count += 1
                
                # Initialize plant level
                if plant not in hierarchy:
                    hierarchy[plant] = {
                        'name': plant,
                        'type': 'plant',
                        'tag_count': 0,
                        'areas': {}
                    }
                
                # Initialize area level
                if area not in hierarchy[plant]['areas']:
                    hierarchy[plant]['areas'][area] = {
                        'name': area,
                        'type': 'area',
                        'tag_count': 0,
                        'equipment': {}
                    }
                
                # Initialize equipment level
                if equipment not in hierarchy[plant]['areas'][area]['equipment']:
                    hierarchy[plant]['areas'][area]['equipment'][equipment] = {
                        'name': equipment,
                        'type': 'equipment',
                        'tag_count': 0,
                        'sub_equipment': {}
                    }
                
                # Initialize sub-equipment level
                if sub_equipment not in hierarchy[plant]['areas'][area]['equipment'][equipment]['sub_equipment']:
                    hierarchy[plant]['areas'][area]['equipment'][equipment]['sub_equipment'][sub_equipment] = {
                        'name': sub_equipment,
                        'type': 'sub_equipment',
                        'tag_count': 0,
                        'components': {}
                    }
                
                # Initialize component level
                if components not in hierarchy[plant]['areas'][area]['equipment'][equipment]['sub_equipment'][sub_equipment]['components']:
                    hierarchy[plant]['areas'][area]['equipment'][equipment]['sub_equipment'][sub_equipment]['components'][components] = {
                        'name': components,
                        'type': 'component',
                        'tags': []
                    }
                
                # Add tag to component
                tag_info = {
                    'tag_id': tag_id,
                    'tag_name': row['tag_name'],
                    'data_type': row['data_type'],
                    'eng_unit': row['eng_unit'],
                    'description': row['description'],
                    'trip_category': row['trip_category'],
                    'criticality': row['equipment_criticality'],
                    # ISA-101: Include contextual information for situation awareness
                    'plant': plant,
                    'area': area,
                    'equipment': equipment,
                    'sub_equipment': sub_equipment,
                    'components': components,
                    'server_progid': row['server_progid'] or 'Unknown'
                }
                hierarchy[plant]['areas'][area]['equipment'][equipment]['sub_equipment'][sub_equipment]['components'][components]['tags'].append(tag_info)
                
                # Update tag counts
                hierarchy[plant]['tag_count'] += 1
                hierarchy[plant]['areas'][area]['tag_count'] += 1
                hierarchy[plant]['areas'][area]['equipment'][equipment]['tag_count'] += 1
                hierarchy[plant]['areas'][area]['equipment'][equipment]['sub_equipment'][sub_equipment]['tag_count'] += 1
            
            # Convert to list format for easier frontend consumption
            result = []
            for plant_name, plant_data in hierarchy.items():
                plant_node = {
                    'id': f'plant_{plant_name}',
                    'name': plant_name,
                    'type': 'plant',
                    'tag_count': plant_data['tag_count'],
                    'children': []
                }
                
                for area_name, area_data in plant_data['areas'].items():
                    area_node = {
                        'id': f'area_{plant_name}_{area_name}',
                        'name': area_name,
                        'type': 'area',
                        'tag_count': area_data['tag_count'],
                        'children': []
                    }
                    
                    for equip_name, equip_data in area_data['equipment'].items():
                        equip_node = {
                            'id': f'equip_{plant_name}_{area_name}_{equip_name}',
                            'name': equip_name,
                            'type': 'equipment',
                            'tag_count': equip_data['tag_count'],
                            'children': []
                        }
                        
                        for sub_equip_name, sub_equip_data in equip_data['sub_equipment'].items():
                            sub_equip_node = {
                                'id': f'subequip_{plant_name}_{area_name}_{equip_name}_{sub_equip_name}',
                                'name': sub_equip_name,
                                'type': 'sub_equipment',
                                'tag_count': sub_equip_data['tag_count'],
                                'children': []
                            }
                            
                            for comp_name, comp_data in sub_equip_data['components'].items():
                                comp_node = {
                                    'id': f'comp_{plant_name}_{area_name}_{equip_name}_{sub_equip_name}_{comp_name}',
                                    'name': comp_name,
                                    'type': 'component',
                                    'tags': comp_data['tags'],
                                    'tag_count': len(comp_data['tags'])
                                }
                                sub_equip_node['children'].append(comp_node)
                            
                            equip_node['children'].append(sub_equip_node)
                        
                        area_node['children'].append(equip_node)
                    
                    plant_node['children'].append(area_node)
                
                result.append(plant_node)
            
            logger.info("=" * 60)
            logger.info(f"[OK] Asset Hierarchy Built Successfully!")
            logger.info(f"[STATS] RBAC FILTERING SUMMARY:")
            logger.info(f"   Total tags in DB: {len(rows)}")
            logger.info(f"   [OK] Allowed tags: {allowed_count if tag_filter else len(rows)}")
            logger.info(f"   [X] Filtered tags: {filtered_count}")
            logger.info(f"   [TREE] Plants in hierarchy: {len(result)}")
            logger.info("=" * 60)
            
            for plant in result:
                logger.info(f"  └─ {plant['name']}: {len(plant.get('children', []))} areas, {plant.get('tag_count', 0)} tags")
            
            response_data = {
                'hierarchy': result,
                'statistics': {
                    'total_tags': tag_count,
                    'filtered_tags': filtered_count,
                    'plants': len(result),
                    'timestamp': datetime.now().isoformat()
                }
            }
            
            logger.info("=" * 60)
            logger.info("[OK] Returning asset hierarchy response")
            logger.info("=" * 60)
            
            return jsonify(response_data)
            
    except Exception as e:
        logger.error("=" * 60)
        logger.error(f"[ERROR] EXCEPTION in asset hierarchy endpoint: {e}")
        logger.exception(e)
        logger.error("=" * 60)
        return jsonify({'error': str(e)}), 500


@asset_bp.route('/flat')
@token_required
def get_asset_flat(current_user):
    """
    Get flat list of assets with full hierarchy path
    Useful for searching/filtering
    """
    try:
        if not container.historical_service.connection:
            return jsonify({'error': 'Database not connected'}), 503
        
        tag_filter = get_user_allowed_tag_filter()
        
        with container.historical_service.connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    tag_id,
                    tag_name,
                    plant,
                    area,
                    equipment,
                    sub_equipment,
                    components,
                    data_type,
                    eng_unit,
                    description,
                    trip_category,
                    equipment_criticality,
                    CONCAT_WS(' / ',
                        COALESCE(plant, 'Unassigned'),
                        COALESCE(area, 'Unassigned'),
                        COALESCE(equipment, 'Unassigned'),
                        COALESCE(sub_equipment, 'Unassigned'),
                        COALESCE(components, 'Unassigned')
                    ) as full_path
                FROM historian_meta.tag_master
                WHERE enabled = true
                ORDER BY plant, area, equipment, sub_equipment, components, tag_id
            """)
            
            rows = cursor.fetchall()
            assets = []
            
            for row in rows:
                tag_id = row['tag_id']
                plant = row['plant']
                area = row['area']
                
                # Apply RBAC filter
                if tag_filter is not None:
                    if not tag_filter(tag_id, plant, area):
                        continue
                
                assets.append({
                    'tag_id': tag_id,
                    'tag_name': row['tag_name'],
                    'full_path': row['full_path'],
                    'plant': row['plant'] or 'Unassigned',
                    'area': row['area'] or 'Unassigned',
                    'equipment': row['equipment'] or 'Unassigned',
                    'sub_equipment': row['sub_equipment'] or 'Unassigned',
                    'component': row['components'] or 'Unassigned',
                    'data_type': row['data_type'],
                    'eng_unit': row['eng_unit'],
                    'description': row['description'],
                    'trip_category': row['trip_category'],
                    'criticality': row['equipment_criticality']
                })
            
            return jsonify({
                'assets': assets,
                'count': len(assets)
            })
            
    except Exception as e:
        logger.error(f"[ERROR] Error fetching flat asset list: {e}")
        return jsonify({'error': str(e)}), 500


@asset_bp.route('/stats')
@token_required
def get_asset_statistics(current_user):
    """
    Get asset hierarchy statistics
    """
    try:
        if not container.historical_service.connection:
            return jsonify({'error': 'Database not connected'}), 503
        
        with container.historical_service.connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    COUNT(DISTINCT plant) as plant_count,
                    COUNT(DISTINCT area) as area_count,
                    COUNT(DISTINCT equipment) as equipment_count,
                    COUNT(DISTINCT sub_equipment) as sub_equipment_count,
                    COUNT(DISTINCT components) as component_count,
                    COUNT(*) as total_tags,
                    COUNT(DISTINCT CASE WHEN trip_category IS NOT NULL THEN tag_id END) as trip_tags,
                    COUNT(DISTINCT CASE WHEN equipment_criticality = 5 THEN tag_id END) as critical_equipment_tags
                FROM historian_meta.tag_master
                WHERE enabled = true
            """)
            
            stats = cursor.fetchone()
            
            return jsonify({
                'plants': stats['plant_count'],
                'areas': stats['area_count'],
                'equipment': stats['equipment_count'],
                'sub_equipment': stats['sub_equipment_count'],
                'components': stats['component_count'],
                'total_tags': stats['total_tags'],
                'trip_tags': stats['trip_tags'],
                'critical_equipment_tags': stats['critical_equipment_tags']
            })
            
    except Exception as e:
        logger.error(f"[ERROR] Error fetching asset statistics: {e}")
        return jsonify({'error': str(e)}), 500
