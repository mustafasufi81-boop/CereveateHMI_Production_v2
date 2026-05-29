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
    Proxy endpoint for OPC live values (RBAC protected).
    Tags with no plant/area (OPC/PLC simulator tags) are visible to ALL
    authenticated users — same rule as the MQTT broadcast.
    """
    try:
        tag_filter = get_user_allowed_tag_filter()

        req = urllib.request.Request('http://127.0.0.1:5001/api/opc/values')
        with urllib.request.urlopen(req, timeout=8) as response:
            data = json_lib.loads(response.read().decode('utf-8'))

        tags_raw = data.get('tags') or []
        # Normalise to list
        if isinstance(tags_raw, dict):
            tags_raw = list(tags_raw.values())

        # Apply RBAC: tags with no plant/area are visible to everyone (OPC/PLC tags)
        if tag_filter is not None:
            tags_raw = [
                t for t in tags_raw
                if t.get('plant') is None and t.get('area') is None
                or tag_filter(t.get('tagId') or t.get('tag_id', ''), t.get('plant'), t.get('area'))
            ]

        return jsonify({
            'tags': tags_raw,
            'count': len(tags_raw),
            'timestamp': data.get('timestamp') or data.get('lastUpdate'),
            'source': 'opc'
        }), 200

    except urllib.error.URLError:
        return jsonify({'error': 'OPC service not available', 'tags': [], 'count': 0}), 503
    except Exception as e:
        logger.error(f"❌ OPC proxy error: {e}")
        return jsonify({'error': str(e), 'tags': [], 'count': 0}), 500


@system_bp.route('/plc/values')
@token_required
def proxy_plc_values(current_user):
    """
    Proxy endpoint for PLC live values (RBAC protected).
    Tags with no plant/area are visible to ALL authenticated users.
    """
    try:
        req = urllib.request.Request('http://127.0.0.1:5001/api/plc/values')
        with urllib.request.urlopen(req, timeout=8) as response:
            data = json_lib.loads(response.read().decode('utf-8'))

        # C# returns key 'values' (not 'tags') for PLC endpoint
        tags_raw = data.get('values') or data.get('tags') or []
        if isinstance(tags_raw, dict):
            tags_raw = list(tags_raw.values())

        # Normalise field names: C# uses tagName, frontend expects tagId
        normalised = []
        for t in tags_raw:
            entry = dict(t)
            if 'tagId' not in entry:
                entry['tagId'] = t.get('tagName') or t.get('tag_id') or t.get('address', '')
            normalised.append(entry)

        tag_filter = get_user_allowed_tag_filter()
        if tag_filter is not None:
            normalised = [
                t for t in normalised
                if t.get('plant') is None and t.get('area') is None
                or tag_filter(t.get('tagId', ''), t.get('plant'), t.get('area'))
            ]

        return jsonify({
            'tags': normalised,
            'count': len(normalised),
            'timestamp': data.get('timestamp'),
            'source': 'plc'
        }), 200

    except urllib.error.URLError:
        return jsonify({'error': 'PLC service not available', 'tags': [], 'count': 0}), 503
    except Exception as e:
        logger.error(f"❌ PLC proxy error: {e}")
        return jsonify({'error': str(e), 'tags': [], 'count': 0}), 500
