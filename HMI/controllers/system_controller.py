from flask import Blueprint, jsonify
from container import container
import logging
import urllib.request
import json as json_lib
from utils.decorators import token_required, get_user_allowed_tag_filter

logger = logging.getLogger(__name__)
system_bp = Blueprint('system', __name__, url_prefix='/api')

@system_bp.route('/config')
def get_config():
    """Get HMI configuration and connection status"""
    config = container.config
    backend_config = config.get('csharp_backend', {})
    backend_url = f"http://{backend_config.get('host', 'localhost')}:{backend_config.get('port', 5001)}"
    
    return jsonify({
        'updateInterval': config['performance']['update_interval_ms'],
        'maxPointsLive': config['performance']['max_points_live'],
        'maxPointsHistorical': config['performance']['max_points_historical'],
        'sampling': config.get('sampling', {}),
        'backendUrl': backend_url,
        'connections': {
            'signalr': container.signalr_listener.is_connected if container.signalr_listener else False,
            'database': container.historical_service.connection is not None
        }
    })

@system_bp.route('/opc/values')
@token_required
def proxy_opc_values(current_user):
    """
    Proxy endpoint for OPC live values (RBAC protected)
    Forwards requests to C# OPC service on port 5001
    """
    try:
        # Get RBAC filter
        tag_filter = get_user_allowed_tag_filter()
        
        # Use urllib instead of requests (compatible with eventlet monkey patching)
        req = urllib.request.Request('http://127.0.0.1:5001/api/opc/values')
        with urllib.request.urlopen(req, timeout=3) as response:
            data = json_lib.loads(response.read().decode('utf-8'))
            
            # Apply RBAC filtering
            if tag_filter is not None and 'tags' in data:
                tags = data['tags']
                # OPC backend may return tags as a list OR a dict — normalise to dict
                if isinstance(tags, list):
                    tags = {t.get('tagId') or t.get('tag') or t.get('id', ''): t for t in tags}
                filtered_tags = {}
                for tag_id, tag_data in tags.items():
                    # Get plant/area info for this tag
                    plant = tag_data.get('plant')
                    area = tag_data.get('area')
                    if tag_filter(tag_id, plant, area):
                        filtered_tags[tag_id] = tag_data
                data['tags'] = filtered_tags
                data['count'] = len(filtered_tags)
            
            return jsonify(data), 200
            
    except urllib.error.URLError as e:
        return jsonify({'error': 'OPC service not available', 'tags': {}, 'count': 0}), 503
    except Exception as e:
        logger.error(f"❌ OPC proxy error: {e}")
        return jsonify({'error': str(e), 'tags': {}, 'count': 0}), 500


@system_bp.route('/plc/values')
@token_required
def proxy_plc_values(current_user):
    """
    Proxy endpoint for PLC live values (RBAC protected)
    Forwards requests to C# PLC gateway on port 5001
    Returns same shape as /api/opc/values so the frontend can handle both identically.
    """
    try:
        req = urllib.request.Request('http://127.0.0.1:5001/api/plc/values')
        with urllib.request.urlopen(req, timeout=3) as response:
            data = json_lib.loads(response.read().decode('utf-8'))

        # C# returns { success, count, timestamp, tags: [ {tagId, value, quality, ...} ] }
        tags_raw = data.get('tags') or []

        # Normalise to dict keyed by tagId
        if isinstance(tags_raw, list):
            tags_dict = {t.get('tagId') or t.get('tag_id') or t.get('id', ''): t for t in tags_raw}
        else:
            tags_dict = tags_raw

        # Apply same RBAC filter as OPC
        tag_filter = get_user_allowed_tag_filter()
        if tag_filter is not None:
            tags_dict = {
                tid: td for tid, td in tags_dict.items()
                if tag_filter(tid, td.get('plant'), td.get('area'))
            }

        return jsonify({
            'tags': tags_dict,
            'count': len(tags_dict),
            'timestamp': data.get('timestamp'),
            'source': 'plc'
        }), 200

    except urllib.error.URLError as e:
        return jsonify({'error': 'PLC service not available', 'tags': {}, 'count': 0}), 503
    except Exception as e:
        logger.error(f"❌ PLC proxy error: {e}")
        return jsonify({'error': str(e), 'tags': {}, 'count': 0}), 500
